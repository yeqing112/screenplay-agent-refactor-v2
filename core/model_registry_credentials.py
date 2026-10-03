"""Server-side resolution of credentials saved by Model Management.

Only the backend may call this resolver.  It accepts a non-secret profile
reference and reads the sensitive registry value from the server-side KV
store.  The secret is returned only to the runtime credential boundary and is
never serialized into a public profile, execution snapshot, audit, or log.
"""

from __future__ import annotations

import json
from typing import Any

from models.base import get_kv


MODEL_REGISTRY_PROFILES_KEY = "model_registry_profiles"


def resolve_model_registry_profile_secret(reference: str) -> str | None:
    """Resolve ``profile:<id>`` to the saved server-side ``api_key``.

    The function intentionally returns only the secret value (or ``None``)
    and never includes registry rows in an exception or diagnostic payload.
    """

    value = str(reference or "").strip()
    if not value.startswith("profile:"):
        return None
    profile_id = value[len("profile:") :].strip()
    if not profile_id or any(char in profile_id for char in "\r\n\x00"):
        return None
    try:
        raw = get_kv(MODEL_REGISTRY_PROFILES_KEY, "[]")
        profiles: Any = json.loads(raw)
    except (OSError, TypeError, ValueError):
        return None
    if not isinstance(profiles, list):
        return None
    for profile in profiles:
        if not isinstance(profile, dict) or str(profile.get("id") or "") != profile_id:
            continue
        secret = profile.get("api_key")
        if isinstance(secret, str) and secret.strip():
            return secret.strip()
        return None
    return None


__all__ = ["MODEL_REGISTRY_PROFILES_KEY", "resolve_model_registry_profile_secret"]
