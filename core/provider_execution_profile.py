"""Canonical, secret-free Phase F provider execution profile.

The model registry profile is an input surface shared by several products.  A
Phase F execution must instead bind to a small, explicit projection so that
transport settings and credentials cannot accidentally become generation
semantics or leak into audit fingerprints.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .prompt_ir_phase_e import canonical

PROFILE_SCHEMA_VERSION = "provider_execution_profile_v1"

# Positive allowlist for image generation knobs used by the supported bridges.
# Registry fields outside this set are intentionally discarded.
GENERATION_PARAM_KEYS = frozenset(
    {
        "size", "quality", "response_format", "steps", "cfg", "seed", "sampling",
        "aspect_ratio", "image_size", "max_reference_images", "max_reference_image_bytes",
        "supports_reference_images", "supports_negative_prompt", "negative_prompt",
        "n", "watermark", "style", "guidance_scale", "num_inference_steps",
        "background", "moderation", "user", "size_by_aspect_ratio",
    }
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _endpoint_identity(profile: dict[str, Any]) -> str:
    raw = str(profile.get("endpoint_identity") or profile.get("base_url") or "").strip()
    return raw.split("?", 1)[0].rstrip("/")


def _credential_source_identity(profile: dict[str, Any]) -> str:
    # Source identity is metadata, never the secret itself.  Prefer an
    # operator-provided stable ref and fall back to the registry source/id.
    return str(
        profile.get("credential_source_identity")
        or profile.get("credential_source")
        or profile.get("source")
        or profile.get("id")
        or ""
    ).strip()


def build_provider_execution_profile(
    profile: dict[str, Any],
    *,
    adapter_id: str,
    adapter_version: str,
) -> dict[str, Any]:
    """Build the canonical allowlisted Phase F execution projection."""
    raw_params = _as_dict(profile.get("default_params"))
    generation_params = {
        key: raw_params[key]
        for key in sorted(GENERATION_PARAM_KEYS)
        if key in raw_params
    }
    timeout = raw_params.get("timeout_seconds")
    if timeout is None:
        timeout = _as_dict(profile.get("transport_config")).get("timeout_seconds")
    try:
        timeout_seconds = float(timeout) if timeout is not None else 120.0
    except (TypeError, ValueError):
        timeout_seconds = 120.0
    if timeout_seconds <= 0:
        timeout_seconds = 120.0
    if timeout_seconds.is_integer():
        timeout_seconds = int(timeout_seconds)
    configured = bool(profile.get("key_configured") or str(profile.get("api_key") or "").strip())
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "profile_id": str(profile.get("id") or ""),
        "capability": str(profile.get("capability") or "image"),
        "provider": str(profile.get("provider") or ""),
        "model": str(profile.get("model_name") or profile.get("model") or ""),
        "endpoint_identity": _endpoint_identity(profile),
        "generation_params": generation_params,
        "transport_config": {"timeout_seconds": timeout_seconds},
        "credential": {
            "configured": configured,
            "source_identity": _credential_source_identity(profile),
        },
        "adapter": {
            "adapter_id": str(adapter_id or ""),
            "adapter_version": str(adapter_version or ""),
        },
    }


def fingerprint_provider_execution_profile(profile: dict[str, Any]) -> str:
    """Fingerprint only the canonical, secret-free profile projection."""
    return hashlib.sha256(canonical(profile).encode("utf-8")).hexdigest()


def provider_generation_params(profile: dict[str, Any]) -> dict[str, Any]:
    canonical_profile = profile.get("provider_execution_profile") if isinstance(profile, dict) else None
    if isinstance(canonical_profile, dict):
        return dict(_as_dict(canonical_profile.get("generation_params")))
    return {
        key: _as_dict(profile.get("default_params"))[key]
        for key in sorted(GENERATION_PARAM_KEYS)
        if key in _as_dict(profile.get("default_params"))
    }


def provider_timeout_seconds(profile: dict[str, Any], default: int = 120) -> int:
    canonical_profile = profile.get("provider_execution_profile") if isinstance(profile, dict) else None
    value = _as_dict(_as_dict(canonical_profile).get("transport_config")).get("timeout_seconds") if isinstance(canonical_profile, dict) else None
    if value is None:
        value = _as_dict(profile.get("default_params") if isinstance(profile, dict) else {}).get("timeout_seconds")
    try:
        value = int(float(value))
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, 3600))


__all__ = [
    "PROFILE_SCHEMA_VERSION",
    "GENERATION_PARAM_KEYS",
    "build_provider_execution_profile",
    "fingerprint_provider_execution_profile",
    "provider_generation_params",
    "provider_timeout_seconds",
]
