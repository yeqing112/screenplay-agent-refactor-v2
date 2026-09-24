"""Canonical, typed and secret-free Phase F provider execution profile.

The model registry is a broad input surface shared by legacy pipelines. Phase F
projects it into an explicit execution-only schema before fingerprinting or
building a provider request. The projection cannot introduce PromptIR or
GenerationPayload semantics.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any, Callable

from .prompt_ir_phase_e import canonical

PROFILE_SCHEMA_VERSION = "provider_execution_profile_v2"


class ProviderExecutionProfileError(ValueError):
    """A deterministic canonical profile validation failure."""

    def __init__(self, message: str, *, code: str = "GENERATION_PROVIDER_PARAM_INVALID", field: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.field = field


@dataclass(frozen=True)
class ParamSpec:
    """Explicit type contract for one provider generation parameter."""

    kind: str
    normalize: Callable[[Any, str], Any]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _profile_mapping(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise _fail(field, "an object", value)
    return value


def _fail(field: str, expected: str, value: Any) -> ProviderExecutionProfileError:
    return ProviderExecutionProfileError(
        f"Provider execution parameter {field!r} must be {expected}; got {type(value).__name__}.",
        field=field,
    )


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise _fail(field, "a string", value)
    result = value.strip()
    if not result:
        raise ProviderExecutionProfileError(f"Provider execution parameter {field!r} cannot be empty.", field=field)
    return result


def _token(value: Any, field: str) -> str:
    result = _string(value, field)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", result):
        raise ProviderExecutionProfileError(f"Provider execution parameter {field!r} must be a simple execution token.", field=field)
    return result


def _aspect_ratio(value: Any, field: str) -> str:
    result = _string(value, field)
    if result.lower() == "auto" or re.fullmatch(r"[1-9]\d*(?:\.\d+)?:[1-9]\d*(?:\.\d+)?", result):
        return result
    raise ProviderExecutionProfileError(
        f"Provider execution parameter {field!r} must be 'auto' or WIDTH:HEIGHT ratio.",
        field=field,
    )


def _size(value: Any, field: str) -> str:
    result = _string(value, field)
    if result.lower() == "auto" or re.fullmatch(r"[1-9]\d{0,5}x[1-9]\d{0,5}", result.lower()):
        return result
    raise ProviderExecutionProfileError(f"Provider execution parameter {field!r} must be 'auto' or WIDTHxHEIGHT.", field=field)


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(field, "an integer", value)
    return value


def _positive_integer(value: Any, field: str) -> int:
    result = _integer(value, field)
    if result <= 0:
        raise ProviderExecutionProfileError(f"Provider execution parameter {field!r} must be positive.", field=field)
    return result


def _number(value: Any, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise _fail(field, "a finite number", value)
    return value


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise _fail(field, "a boolean", value)
    return value


def _moderation(value: Any, field: str) -> bool | str:
    if isinstance(value, bool):
        return value
    return _token(value, field)


def _size_map(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise _fail(field, "a map of aspect-ratio strings to size strings", value)
    result: dict[str, str] = {}
    for ratio, size in value.items():
        if not isinstance(ratio, str) or not re.fullmatch(r"[1-9]\d*(?:\.\d+)?:[1-9]\d*(?:\.\d+)?", ratio.strip()):
            raise ProviderExecutionProfileError(f"Provider execution parameter {field!r} has invalid aspect-ratio key.", field=f"{field}.{ratio}")
        result[ratio.strip()] = _size(size, f"{field}.{ratio}")
    return {key: result[key] for key in sorted(result)}


# Positive typed schema. Anything not listed here is rejected rather than
# copied and recursively redacted. Prompt semantics are explicit forbidden
# fields, so an operator cannot believe that a silently ignored setting won.
GENERATION_PARAM_SCHEMA: dict[str, ParamSpec] = {
    "size": ParamSpec("string", _size),
    "quality": ParamSpec("string", _token),
    "response_format": ParamSpec("string", _token),
    "steps": ParamSpec("integer", _positive_integer),
    "cfg": ParamSpec("number", _number),
    "seed": ParamSpec("integer", _integer),
    "sampling": ParamSpec("token", _token),
    "aspect_ratio": ParamSpec("ratio", _aspect_ratio),
    "image_size": ParamSpec("token", _token),
    "max_reference_images": ParamSpec("integer", _positive_integer),
    "max_reference_image_bytes": ParamSpec("integer", _positive_integer),
    "n": ParamSpec("integer", _positive_integer),
    "watermark": ParamSpec("boolean", _boolean),
    "guidance_scale": ParamSpec("number", _number),
    "num_inference_steps": ParamSpec("integer", _positive_integer),
    "background": ParamSpec("token", _token),
    "moderation": ParamSpec("token_or_boolean", _moderation),
    "size_by_aspect_ratio": ParamSpec("map<string,string>", _size_map),
}

GENERATION_PARAM_KEYS = frozenset(GENERATION_PARAM_SCHEMA)
CAPABILITY_PARAM_KEYS = frozenset({"supports_reference_images", "supports_negative_prompt"})
FORBIDDEN_SEMANTIC_PROFILE_PARAMS = frozenset({"negative_prompt", "style"})
_TRANSPORT_KEYS = frozenset({"timeout_seconds"})


def _endpoint_identity(profile: dict[str, Any]) -> str:
    raw = str(profile.get("endpoint_identity") or profile.get("base_url") or "").strip()
    return raw.split("?", 1)[0].rstrip("/")


def _credential_source_identity(profile: dict[str, Any]) -> str:
    return str(profile.get("credential_source_identity") or profile.get("credential_source") or profile.get("source") or profile.get("id") or "").strip()


def _normalize_timeout(profile: dict[str, Any]) -> int | float:
    raw_params = _profile_mapping(profile.get("default_params"), "default_params")
    raw_transport = _profile_mapping(profile.get("transport_config"), "transport_config")
    timeout = raw_params.get("timeout_seconds", raw_transport.get("timeout_seconds", 120))
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(float(timeout)):
        raise _fail("timeout_seconds", "a finite positive number", timeout)
    if timeout <= 0 or timeout > 3600:
        raise ProviderExecutionProfileError("timeout_seconds must be between 1 and 3600.", field="timeout_seconds")
    return int(timeout) if float(timeout).is_integer() else float(timeout)


def build_provider_execution_profile(
    profile: dict[str, Any],
    *,
    adapter_id: str,
    adapter_version: str,
    credential_lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical typed allowlisted Phase F execution projection."""
    raw_params = _profile_mapping(profile.get("default_params"), "default_params")
    forbidden = sorted(FORBIDDEN_SEMANTIC_PROFILE_PARAMS.intersection(raw_params))
    if forbidden:
        raise ProviderExecutionProfileError(
            f"Provider profile parameters cannot add creative semantics: {', '.join(forbidden)}.",
            code="GENERATION_PROVIDER_SEMANTIC_PARAM_FORBIDDEN",
            field=forbidden[0],
        )
    unknown = sorted(set(raw_params) - GENERATION_PARAM_KEYS - CAPABILITY_PARAM_KEYS - {"timeout_seconds"})
    if unknown:
        raise ProviderExecutionProfileError(f"Unknown provider execution parameter(s): {', '.join(str(item) for item in unknown)}.", field=str(unknown[0]))
    raw_transport = _profile_mapping(profile.get("transport_config"), "transport_config")
    unknown_transport = sorted(set(raw_transport) - _TRANSPORT_KEYS)
    if unknown_transport:
        raise ProviderExecutionProfileError(f"Unknown provider transport parameter(s): {', '.join(str(item) for item in unknown_transport)}.", field=str(unknown_transport[0]))

    generation_params = {
        key: GENERATION_PARAM_SCHEMA[key].normalize(raw_params[key], key)
        for key in sorted(GENERATION_PARAM_SCHEMA)
        if key in raw_params
    }
    capabilities = {
        key: _boolean(raw_params[key], key)
        for key in sorted(CAPABILITY_PARAM_KEYS)
        if key in raw_params
    }
    credential = {
        "configured": bool(profile.get("key_configured") or str(profile.get("api_key") or "").strip()),
        "source_identity": _credential_source_identity(profile),
    }
    # Canonical J3 callers may add the resolver lifecycle projection.  The
    # legacy Phase F shape remains byte-for-byte compatible when omitted.
    if isinstance(credential_lifecycle, dict):
        credential = {
            "credential_ref": str(credential_lifecycle.get("credential_ref") or credential["source_identity"]),
            "configured": bool(credential_lifecycle.get("configured")),
            "resolved": bool(credential_lifecycle.get("resolved")),
            "validated": bool(credential_lifecycle.get("validated")),
        }
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "profile_id": str(profile.get("id") or ""),
        "capability": str(profile.get("capability") or "image"),
        "provider": str(profile.get("provider") or ""),
        "model": str(profile.get("model_name") or profile.get("model") or ""),
        "endpoint_identity": _endpoint_identity(profile),
        "generation_params": generation_params,
        "transport_config": {"timeout_seconds": _normalize_timeout(profile)},
        "credential": credential,
        "capabilities": capabilities,
        "adapter": {"adapter_id": str(adapter_id or ""), "adapter_version": str(adapter_version or "")},
    }


def fingerprint_provider_execution_profile(profile: dict[str, Any]) -> str:
    """Fingerprint only a canonical, typed and secret-free profile."""
    if not isinstance(profile, dict) or profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ProviderExecutionProfileError("Only a canonical provider execution profile may be fingerprinted.")
    return hashlib.sha256(canonical(profile).encode("utf-8")).hexdigest()


def _canonical_from_profile(profile: dict[str, Any] | None, *, strict: bool = False) -> dict[str, Any] | None:
    canonical_profile = profile.get("provider_execution_profile") if isinstance(profile, dict) else None
    if isinstance(canonical_profile, dict):
        if canonical_profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
            raise ProviderExecutionProfileError("Phase F requires provider_execution_profile_v2.")
        return canonical_profile
    if strict or bool(isinstance(profile, dict) and profile.get("phase_f_strict")):
        raise ProviderExecutionProfileError("Phase F transport requires a canonical provider execution profile.")
    return None


def provider_generation_params(profile: dict[str, Any], *, strict: bool = False) -> dict[str, Any]:
    canonical_profile = _canonical_from_profile(profile, strict=strict)
    if canonical_profile is not None:
        return dict(_as_dict(canonical_profile.get("generation_params")))
    raw_params = _as_dict(profile.get("default_params") if isinstance(profile, dict) else {})
    return {key: GENERATION_PARAM_SCHEMA[key].normalize(raw_params[key], key) for key in sorted(GENERATION_PARAM_SCHEMA) if key in raw_params}


def provider_timeout_seconds(profile: dict[str, Any], default: int = 120, *, strict: bool = False) -> int:
    canonical_profile = _canonical_from_profile(profile, strict=strict)
    value = _as_dict(_as_dict(canonical_profile).get("transport_config")).get("timeout_seconds") if canonical_profile else _as_dict(profile.get("default_params") if isinstance(profile, dict) else {}).get("timeout_seconds")
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise _fail("timeout_seconds", "a finite positive number", value)
    if value <= 0 or value > 3600:
        raise ProviderExecutionProfileError("timeout_seconds must be between 1 and 3600.", field="timeout_seconds")
    return int(float(value))


__all__ = [
    "PROFILE_SCHEMA_VERSION",
    "GENERATION_PARAM_SCHEMA",
    "GENERATION_PARAM_KEYS",
    "CAPABILITY_PARAM_KEYS",
    "FORBIDDEN_SEMANTIC_PROFILE_PARAMS",
    "ProviderExecutionProfileError",
    "build_provider_execution_profile",
    "fingerprint_provider_execution_profile",
    "provider_generation_params",
    "provider_timeout_seconds",
]
