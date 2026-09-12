import importlib.util
from pathlib import Path
from types import SimpleNamespace


_SCRIPT = Path(__file__).parents[1] / "scripts" / "verify-production-security.py"
_SPEC = importlib.util.spec_from_file_location("verify_production_security", _SCRIPT)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _settings(**overrides):
    values = {
        "DEPLOYMENT_ENV": "production",
        "API_AUTH_ENABLED": True,
        "API_AUTH_ROLE_TOKENS": {"viewer": "v" * 40, "editor": "e" * 40, "admin": "a" * 40},
        "API_AUTH_ROLE_TOKENS_ERROR": False,
        "API_AUTH_TOKEN": "",
        "API_CORS_ORIGINS": ["https://studio.mystudio.net"],
        "API_CORS_ALLOW_CREDENTIALS": False,
        "API_RATE_LIMIT_ENABLED": True,
        "API_RATE_LIMIT_REQUESTS": 120,
        "API_RATE_LIMIT_WINDOW_SECONDS": 60,
        "API_RATE_LIMIT_DISTRIBUTED_ASSERTED": True,
        "ENABLE_LEGACY_NODE_API": False,
        "PUBLIC_ASSET_STORAGE_PROVIDER": "qiniu",
        "QINIU_PUBLIC_BASE_URL": "https://cdn.mystudio.net",
        "QINIU_ACCESS_KEY": "ak-production-value",
        "QINIU_SECRET_KEY": "sk-production-value",
        "QINIU_BUCKET": "screenplay-production",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_development_verification_is_explicitly_skipped():
    result = _MODULE.verify_production_security(_settings(DEPLOYMENT_ENV="development"))
    assert result["ok"] is True
    assert result["skipped"] is True


def test_production_security_passes_with_explicit_safe_configuration():
    result = _MODULE.verify_production_security(_settings())
    assert result["ok"] is True
    assert result["errors"] == []


def test_production_security_rejects_http_and_temporary_storage_domains():
    result = _MODULE.verify_production_security(
        _settings(
            API_CORS_ORIGINS=["http://studio.mystudio.net"],
            QINIU_PUBLIC_BASE_URL="http://temporary.clouddn.com",
        )
    )
    assert result["ok"] is False
    assert any("HTTPS" in message for message in result["errors"])
    assert any("temporary clouddn.com" in message for message in result["errors"])


def test_production_security_rejects_missing_auth_and_rate_limit():
    result = _MODULE.verify_production_security(
        _settings(API_AUTH_ENABLED=False, API_AUTH_ROLE_TOKENS={}, API_AUTH_TOKEN="", API_RATE_LIMIT_ENABLED=False)
    )
    assert result["ok"] is False
    assert "API_AUTH_ENABLED must be true" in result["errors"]
    assert "API_RATE_LIMIT_ENABLED must be true" in result["errors"]


def test_production_security_requires_distributed_rate_limit_attestation():
    result = _MODULE.verify_production_security(_settings(API_RATE_LIMIT_DISTRIBUTED_ASSERTED=False))
    assert result["ok"] is False
    assert any("API_RATE_LIMIT_DISTRIBUTED_ASSERTED" in message for message in result["errors"])


def test_production_security_rejects_legacy_execution_api():
    result = _MODULE.verify_production_security(_settings(ENABLE_LEGACY_NODE_API=True))
    assert result["ok"] is False
    assert "ENABLE_LEGACY_NODE_API must be false in production" in result["errors"]


def test_production_security_rejects_template_secrets_and_example_hosts():
    result = _MODULE.verify_production_security(
        _settings(
            API_AUTH_ROLE_TOKENS={"viewer": "<32+ chars>", "editor": "e" * 40, "admin": "a" * 40},
            API_CORS_ORIGINS=["https://studio.example.com"],
            QINIU_PUBLIC_BASE_URL="https://cdn.example.com",
            QINIU_ACCESS_KEY="<secret>",
            QINIU_SECRET_KEY="replace-me",
            QINIU_BUCKET="<bucket>",
        )
    )
    assert result["ok"] is False
    assert any("template placeholders" in message for message in result["errors"])
    assert any("example domains" in message for message in result["errors"])
