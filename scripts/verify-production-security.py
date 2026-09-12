"""Fail-closed verification for deployment-level production security config."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config


_PLACEHOLDER_MARKERS = (
    "<secret>",
    "<32+ chars>",
    "<bucket>",
    "sk-placeholder",
    "changeme",
    "change-me",
    "replace-me",
    "***",
)


def _is_placeholder(value: object) -> bool:
    """Return true for common template values that must never reach prod."""
    text = str(value or "").strip().lower()
    if not text:
        return True
    if text.startswith("<") and text.endswith(">"):
        return True
    return any(marker in text for marker in _PLACEHOLDER_MARKERS)


def _is_example_host(host: str) -> bool:
    normalized = str(host or "").strip().lower().rstrip(".")
    return (
        normalized in {"localhost", "127.0.0.1", "::1"}
        or normalized == "example.com"
        or normalized.endswith(".example.com")
        or normalized == "example.org"
        or normalized.endswith(".example.org")
    )


def verify_production_security(settings=config) -> dict[str, object]:
    environment = str(getattr(settings, "DEPLOYMENT_ENV", "development") or "development").strip().lower()
    errors: list[str] = []
    warnings: list[str] = []
    if environment not in {"production", "prod", "staging"}:
        return {
            "environment": environment,
            "skipped": True,
            "ok": True,
            "errors": [],
            "warnings": ["production security verification is skipped outside production/staging"],
        }

    if not bool(getattr(settings, "API_AUTH_ENABLED", False)):
        errors.append("API_AUTH_ENABLED must be true")
    role_tokens_error = bool(getattr(settings, "API_AUTH_ROLE_TOKENS_ERROR", False))
    role_tokens = getattr(settings, "API_AUTH_ROLE_TOKENS", {}) or {}
    single_token = str(getattr(settings, "API_AUTH_TOKEN", "") or "").strip()
    if role_tokens_error:
        errors.append("API_AUTH_ROLE_TOKENS is not valid JSON")
    elif role_tokens:
        invalid_roles = [
            str(role)
            for role, token in role_tokens.items()
            if str(role).strip().lower() not in {"viewer", "editor", "admin"}
            or len(str(token or "").strip()) < 32
            or _is_placeholder(token)
        ]
        if invalid_roles:
            errors.append("API_AUTH_ROLE_TOKENS contains unknown roles, weak tokens, or template placeholders")
    elif len(single_token) < 32 or _is_placeholder(single_token):
        errors.append("API_AUTH_TOKEN must contain at least 32 non-placeholder characters when role tokens are absent")

    origins = [str(origin).strip() for origin in (getattr(settings, "API_CORS_ORIGINS", []) or []) if str(origin).strip()]
    if not origins or "*" in origins:
        errors.append("API_CORS_ORIGINS must be an explicit non-wildcard allowlist")
    else:
        insecure_origins = [origin for origin in origins if not origin.lower().startswith("https://")]
        if insecure_origins:
            errors.append("production CORS origins must use HTTPS")
        example_origins = [origin for origin in origins if _is_example_host(urlparse(origin).hostname or "")]
        if example_origins:
            errors.append("production CORS origins must not use localhost or example domains")
    if bool(getattr(settings, "API_CORS_ALLOW_CREDENTIALS", False)) and "*" in origins:
        errors.append("credentials cannot be enabled with wildcard CORS")

    if not bool(getattr(settings, "API_RATE_LIMIT_ENABLED", False)):
        errors.append("API_RATE_LIMIT_ENABLED must be true")
    if not bool(getattr(settings, "API_RATE_LIMIT_DISTRIBUTED_ASSERTED", False)):
        errors.append(
            "API_RATE_LIMIT_DISTRIBUTED_ASSERTED must be true after configuring a shared reverse-proxy/rate-limit backend"
        )
    if int(getattr(settings, "API_RATE_LIMIT_REQUESTS", 0) or 0) < 1:
        errors.append("API_RATE_LIMIT_REQUESTS must be positive")
    if int(getattr(settings, "API_RATE_LIMIT_WINDOW_SECONDS", 0) or 0) < 1:
        errors.append("API_RATE_LIMIT_WINDOW_SECONDS must be positive")
    if bool(getattr(settings, "ENABLE_LEGACY_NODE_API", True)):
        errors.append("ENABLE_LEGACY_NODE_API must be false in production")

    provider = str(getattr(settings, "PUBLIC_ASSET_STORAGE_PROVIDER", "") or "").strip().lower()
    public_base_url = str(getattr(settings, "QINIU_PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    if not provider:
        errors.append("PUBLIC_ASSET_STORAGE_PROVIDER must be configured")
    parsed = urlparse(public_base_url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        errors.append("public asset base URL must be a stable HTTPS URL")
    elif _is_example_host(parsed.hostname or ""):
        errors.append("public asset base URL must not use localhost or example domains")
    if parsed.netloc.lower().endswith(".clouddn.com"):
        errors.append("temporary clouddn.com domains are not allowed for production")
    if provider == "qiniu":
        for key in ("QINIU_ACCESS_KEY", "QINIU_SECRET_KEY", "QINIU_BUCKET"):
            value = str(getattr(settings, key, "") or "").strip()
            if _is_placeholder(value):
                errors.append(f"{key} must be a non-placeholder value for production Qiniu storage")
    elif provider:
        warnings.append(f"provider '{provider}' uses the generic stable HTTPS policy")

    return {
        "environment": environment,
        "skipped": False,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    result = verify_production_security()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
