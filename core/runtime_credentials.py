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

    def audit(self) -> dict[str, Any]:
        """Return the secret-free lifecycle projection."""
        return {
            "credential_ref": self.credential_ref,
            "configured": self.configured,
            "resolved": self.resolved,
            "validated": self.validated,
        }


Resolver = Callable[[str], str | None]


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
    validator: Callable[[str], bool] | None = None,
    allow_mock: bool = True,
) -> RuntimeCredential:
    """Resolve and validate a credential without reading registry ``api_key``.

    A legacy plaintext ``api_key`` therefore cannot silently become a new
    canonical credential.  Operators must configure an environment-backed or
    injected resolver explicitly.  Mock profiles use an in-memory sentinel
    strictly as a deterministic transport dependency.
    """
    ref = credential_reference(profile)
    if not ref:
        raise RuntimeCredentialError("RUNTIME_CREDENTIAL_NOT_RESOLVED", "Canonical generation requires a credential reference.")

    provider = str(profile.get("provider") or "").strip()
    configured = bool(profile.get("credential_configured", profile.get("key_configured", False)))
    if provider == "prototype-task-adapter" and allow_mock:
        runtime = RuntimeCredential(ref, "mock-runtime-credential", True, True, True)
        return runtime
    if not configured:
        raise RuntimeCredentialError("RUNTIME_CREDENTIAL_NOT_RESOLVED", "The selected profile has no configured runtime credential reference.", credential_ref=ref)

    if resolver is None:
        env_name = str(profile.get("credential_env") or "").strip()
        resolver = lambda name: os.getenv(name) if name else None
        lookup = env_name or ref
    else:
        lookup = ref
    value = resolver(lookup)
    if not isinstance(value, str) or not value:
        raise RuntimeCredentialError("RUNTIME_CREDENTIAL_NOT_RESOLVED", "The runtime credential reference could not be resolved.", credential_ref=ref)
    check = validator(value) if validator is not None else True
    if not check:
        raise RuntimeCredentialError("RUNTIME_CREDENTIAL_NOT_VALIDATED", "The resolved runtime credential failed validation.", credential_ref=ref)
    return RuntimeCredential(ref, value, True, True, True)


__all__ = ["RuntimeCredential", "RuntimeCredentialError", "credential_reference", "resolve_runtime_credential"]
