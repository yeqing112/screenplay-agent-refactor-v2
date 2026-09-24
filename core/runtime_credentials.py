"""Runtime credential resolution for canonical generation.

The model registry is an operator configuration surface.  Canonical
generation receives only a credential reference and asks this module to
resolve a short lived runtime value.  The resolved secret is deliberately not
returned in any canonical profile, fingerprint, execution snapshot, or error
payload.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping


class RuntimeCredentialError(RuntimeError):
    def __init__(self, code: str, message: str, *, credential_ref: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.credential_ref = credential_ref


@dataclass(frozen=True)
class RuntimeCredential:
    credential_ref: str
    value: str
    configured: bool
    resolved: bool
    validated: bool
    validation_method: str = ""
    validation_version: str = ""

    def audit(self) -> dict[str, Any]:
        """Return the secret-free lifecycle projection."""
        result = {
            "credential_ref": self.credential_ref,
            "configured": self.configured,
            "resolved": self.resolved,
            "validated": self.validated,
        }
        if self.validation_method:
            result["validation_method"] = self.validation_method
        if self.validation_version:
            result["validation_version"] = self.validation_version
        return result


Resolver = Callable[[str], str | None]
Validator = Callable[[str], bool]


@dataclass(frozen=True)
class RuntimeCredentialBinding:
    """Formal resolver/validator binding for one credential reference.

    Bindings are keyed by an explicit credential reference (or a registry
    binding id supplied by the model profile).  The generation core never
    chooses a validator from a provider or model string.
    """

    resolver: Resolver
    validator: Validator | None
    validation_method: str = ""
    validation_version: str = ""


_RUNTIME_CREDENTIAL_BINDINGS: dict[str, RuntimeCredentialBinding] = {}


def register_runtime_credential_binding(
    reference: str,
    *,
    resolver: Resolver,
    validator: Validator | None,
    validation_method: str = "",
    validation_version: str = "",
) -> None:
    """Register a non-secret runtime binding for canonical generation."""
    key = str(reference or "").strip()
    if not key:
        raise ValueError("runtime credential binding reference must not be empty")
    _RUNTIME_CREDENTIAL_BINDINGS[key] = RuntimeCredentialBinding(
        resolver=resolver,
        validator=validator,
        validation_method=str(validation_method or ""),
        validation_version=str(validation_version or ""),
    )


def clear_runtime_credential_bindings() -> None:
    """Clear injected bindings; intended for isolated tests and workers."""
    _RUNTIME_CREDENTIAL_BINDINGS.clear()


def _binding_for(profile: Mapping[str, Any], reference: str) -> RuntimeCredentialBinding | None:
    binding_id = str(profile.get("runtime_binding_id") or "").strip()
    return _RUNTIME_CREDENTIAL_BINDINGS.get(binding_id or reference)


def credential_reference(profile: Mapping[str, Any]) -> str:
    """Derive an explicit non-secret reference from a model profile."""
    value = str(
        profile.get("credential_ref")
        or profile.get("credential_source_identity")
        or profile.get("credential_source")
        or (f"profile:{profile.get('id')}" if profile.get("id") else "")
    ).strip()
    return value


def resolve_runtime_credential(
    profile: Mapping[str, Any],
    *,
    resolver: Resolver | None = None,
    validator: Validator | None = None,
) -> RuntimeCredential:
    """Resolve and validate a credential without reading registry ``api_key``.

    A legacy plaintext ``api_key`` therefore cannot silently become a new
    canonical credential. Operators must configure an environment-backed or
    injected resolver explicitly. Deterministic fake credentials are supplied
    only by an injected test/operations resolver; this module has no built-in
    mock secret fallback.
    """
    ref = credential_reference(profile)
    if not ref:
        raise RuntimeCredentialError("RUNTIME_CREDENTIAL_NOT_RESOLVED", "Canonical generation requires a credential reference.")

    configured = bool(profile.get("credential_configured", profile.get("key_configured", False)))
    if not configured:
        raise RuntimeCredentialError("RUNTIME_CREDENTIAL_NOT_RESOLVED", "The selected profile has no configured runtime credential reference.", credential_ref=ref)

    binding = _binding_for(profile, ref)
    validation_method = ""
    validation_version = ""
    if resolver is None and binding is not None:
        resolver = binding.resolver
        validation_method = binding.validation_method
        validation_version = binding.validation_version
        lookup = ref
    elif resolver is None:
        env_name = str(profile.get("credential_env") or "").strip()
        if not env_name and ref.startswith("env:"):
            env_name = ref[4:].strip()
        resolver = lambda name: os.getenv(name) if name else None
        lookup = env_name or ref
    else:
        lookup = ref
    value = resolver(lookup)
    if not isinstance(value, str) or not value:
        raise RuntimeCredentialError("RUNTIME_CREDENTIAL_NOT_RESOLVED", "The runtime credential reference could not be resolved.", credential_ref=ref)
    effective_validator = validator or (binding.validator if binding is not None else None)
    if effective_validator is None:
        raise RuntimeCredentialError(
            "RUNTIME_CREDENTIAL_NOT_VALIDATED",
            "The runtime credential has no configured validator.",
            credential_ref=ref,
        )
    try:
        check = bool(effective_validator(value))
    except Exception as exc:
        raise RuntimeCredentialError(
            "RUNTIME_CREDENTIAL_NOT_VALIDATED",
            "The runtime credential validator failed.",
            credential_ref=ref,
        ) from exc
    if not check:
        raise RuntimeCredentialError("RUNTIME_CREDENTIAL_NOT_VALIDATED", "The resolved runtime credential failed validation.", credential_ref=ref)
    return RuntimeCredential(ref, value, True, True, True, validation_method, validation_version)


# Built-in provider-free profiles still use the formal binding contract.  The
# binding is reference keyed and contains no provider-specific branch in the
# generation core.
register_runtime_credential_binding(
    "builtin:mock-image",
    resolver=lambda _ref: "runtime://builtin/mock-image",
    validator=lambda value: value == "runtime://builtin/mock-image",
    validation_method="deterministic-binding",
    validation_version="v1",
)
register_runtime_credential_binding(
    "builtin:mock-video",
    resolver=lambda _ref: "runtime://builtin/mock-video",
    validator=lambda value: value == "runtime://builtin/mock-video",
    validation_method="deterministic-binding",
    validation_version="v1",
)


__all__ = [
    "RuntimeCredential",
    "RuntimeCredentialBinding",
    "RuntimeCredentialError",
    "credential_reference",
    "register_runtime_credential_binding",
    "clear_runtime_credential_bindings",
    "resolve_runtime_credential",
]
