"""模型注册表与默认模型解析。"""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from typing import Any

import httpx

import config
from models import get_kv, set_kv

MODEL_REGISTRY_PROFILES_KEY = "model_registry_profiles"
MODEL_REGISTRY_DEFAULTS_KEY = "model_registry_defaults"

CAPABILITIES = ("llm", "embedding", "image", "video")

MOCK_PROVIDER = "prototype-task-adapter"
OPENAI_COMPATIBLE_PROVIDER = "openai-compatible"
OLLAMA_PROVIDER = "ollama"
POYO_ASYNC_PROVIDER = "poyo-async"
MINIMAX_H3_ASYNC_PROVIDER = "minimax-h3-async"

VIDEO_REAL_DEFAULT_ENABLED = True


def _builtin_profiles() -> list[dict[str, Any]]:
    return [
        {
            "id": "builtin-llm-env",
            "name": "环境默认 LLM",
            "capability": "llm",
            "provider": OPENAI_COMPATIBLE_PROVIDER,
            "base_url": config.OPENAI_BASE_URL.rstrip("/"),
            "model_name": config.LLM_MODEL,
            "default_params": {
                "temperature": config.LLM_TEMPERATURE,
                "max_tokens": config.LLM_MAX_TOKENS,
                "thinking": {"type": "disabled"},
            },
            "enabled": True,
            "is_default": True,
            "key_configured": bool(str(config.OPENAI_API_KEY or "").strip() and config.OPENAI_API_KEY != "sk-placeholder"),
            "builtin": True,
            "source": "env",
            "uses_mock": False,
        },
        {
            "id": "builtin-embedding-env",
            "name": "环境默认向量模型",
            "capability": "embedding",
            "provider": OLLAMA_PROVIDER,
            "base_url": config.OLLAMA_BASE_URL.rstrip("/"),
            "model_name": config.EMBEDDING_MODEL,
            "default_params": {
                "dimension": config.EMBEDDING_DIM,
            },
            "enabled": True,
            "is_default": True,
            "key_configured": True,
            "builtin": True,
            "source": "env",
            "uses_mock": False,
        },
        {
            "id": "builtin-mock-image",
            "name": "Mock 图片模型",
            "capability": "image",
            "provider": MOCK_PROVIDER,
            "base_url": "",
            "model_name": "mock-image-v1",
            "default_params": {
                "size": "1024x1024",
            },
            "enabled": True,
            "is_default": True,
            "key_configured": True,
            "builtin": True,
            "source": "builtin",
            "uses_mock": True,
        },
        {
            "id": "builtin-mock-video",
            "name": "Mock 视频模型",
            "capability": "video",
            "provider": MOCK_PROVIDER,
            "base_url": "",
            "model_name": "mock-video-v1",
            "default_params": {
                "duration_seconds": 5,
            },
            "enabled": True,
            "is_default": True,
            "key_configured": True,
            "builtin": True,
            "source": "builtin",
            "uses_mock": True,
        },
    ]


def _builtin_default_map() -> dict[str, str]:
    return {
        "llm": "builtin-llm-env",
        "embedding": "builtin-embedding-env",
        "image": "builtin-mock-image",
        "video": "builtin-mock-video",
    }


def _clone_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(profile)


def _profile_uses_mock(profile: dict[str, Any]) -> bool:
    return profile.get("provider") == MOCK_PROVIDER


def _normalize_default_params(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _serialize_profile(profile: dict[str, Any], *, is_default: bool) -> dict[str, Any]:
    api_key = str(profile.get("api_key") or "").strip()
    out = {
        "id": str(profile.get("id") or uuid.uuid4().hex[:12]),
        "name": str(profile.get("name") or "未命名模型"),
        "capability": str(profile.get("capability") or ""),
        "provider": str(profile.get("provider") or ""),
        "base_url": str(profile.get("base_url") or ""),
        "model_name": str(profile.get("model_name") or ""),
        "default_params": _normalize_default_params(profile.get("default_params")),
        "enabled": bool(profile.get("enabled", True)),
        "is_default": bool(is_default),
        "key_configured": bool(api_key) or bool(profile.get("key_configured")),
        "builtin": bool(profile.get("builtin", False)),
        "source": str(profile.get("source") or ("builtin" if profile.get("builtin") else "user")),
        "uses_mock": _profile_uses_mock(profile),
    }
    if api_key:
        out["api_key"] = api_key
    return out


def _load_saved_profiles() -> list[dict[str, Any]]:
    raw = get_kv(MODEL_REGISTRY_PROFILES_KEY, "[]")
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        items = []
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        capability = str(item.get("capability") or "")
        if capability not in CAPABILITIES:
            continue
        normalized.append(
            {
                "id": str(item.get("id") or uuid.uuid4().hex[:12]),
                "name": str(item.get("name") or "未命名模型"),
                "capability": capability,
                "provider": str(item.get("provider") or ""),
                "base_url": str(item.get("base_url") or ""),
                "model_name": str(item.get("model_name") or ""),
                "default_params": _normalize_default_params(item.get("default_params")),
                "enabled": bool(item.get("enabled", True)),
                "builtin": False,
                "source": "user",
                "api_key": str(item.get("api_key") or "").strip(),
            }
        )
    return normalized


def _load_saved_defaults() -> dict[str, str]:
    raw = get_kv(MODEL_REGISTRY_DEFAULTS_KEY, "{}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = {}
    if not isinstance(value, dict):
        return {}
    defaults: dict[str, str] = {}
    for capability in CAPABILITIES:
        profile_id = value.get(capability)
        if isinstance(profile_id, str) and profile_id.strip():
            defaults[capability] = profile_id.strip()
    return defaults


def _build_profile_index(profiles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {profile["id"]: profile for profile in profiles}


def _find_builtin_profile(capability: str) -> dict[str, Any] | None:
    for profile in _builtin_profiles():
        if profile["capability"] == capability:
            return profile
    return None


def _all_profiles_raw() -> list[dict[str, Any]]:
    profiles = [_clone_profile(profile) for profile in _builtin_profiles()]
    profiles.extend(_clone_profile(profile) for profile in _load_saved_profiles())
    return profiles


def _is_profile_allowed_as_default(profile: dict[str, Any] | None) -> bool:
    if not profile:
        return False
    if not profile.get("enabled", True):
        return False
    capability = profile.get("capability")
    if capability == "video":
        provider = str(profile.get("provider") or "")
        if provider in {POYO_ASYNC_PROVIDER, MINIMAX_H3_ASYNC_PROVIDER}:
            return True
        if provider != MOCK_PROVIDER and not VIDEO_REAL_DEFAULT_ENABLED:
            return False
        if provider not in {MOCK_PROVIDER, POYO_ASYNC_PROVIDER, MINIMAX_H3_ASYNC_PROVIDER}:
            return False
    return True


def _resolve_default_for_capability(
    capability: str,
    requested_id: str | None,
    profile_index: dict[str, dict[str, Any]],
) -> str:
    builtin_default_id = _builtin_default_map()[capability]
    if requested_id:
        profile = profile_index.get(requested_id)
        if profile and profile.get("capability") == capability and _is_profile_allowed_as_default(profile):
            return requested_id
    builtin_profile = profile_index.get(builtin_default_id)
    if builtin_profile and _is_profile_allowed_as_default(builtin_profile):
        return builtin_default_id
    for profile in profile_index.values():
        if profile.get("capability") == capability and _is_profile_allowed_as_default(profile):
            return profile["id"]
    return builtin_default_id


def resolve_defaults() -> dict[str, str]:
    profiles = [_serialize_profile(profile, is_default=False) for profile in _all_profiles_raw()]
    profile_index = _build_profile_index(profiles)
    saved_defaults = _load_saved_defaults()
    return {
        capability: _resolve_default_for_capability(capability, saved_defaults.get(capability), profile_index)
        for capability in CAPABILITIES
    }


def list_profiles(*, include_sensitive: bool = False) -> list[dict[str, Any]]:
    profiles = _all_profiles_raw()
    defaults = resolve_defaults() if include_sensitive else None
    serialized: list[dict[str, Any]] = []
    for profile in profiles:
        is_default = defaults.get(profile["capability"]) == profile["id"] if defaults else False
        serialized_profile = _serialize_profile(profile, is_default=is_default)
        if not include_sensitive:
            serialized_profile.pop("api_key", None)
        serialized.append(serialized_profile)
    return serialized


def serialize_registry_payload() -> dict[str, Any]:
    defaults = resolve_defaults()
    profiles = list_profiles(include_sensitive=False)
    profile_index = {profile["id"]: profile for profile in profiles}
    default_profiles = {
        capability: profile_index.get(defaults.get(capability)) for capability in CAPABILITIES
    }
    return {
        "profiles": profiles,
        "defaults": defaults,
        "default_profiles": default_profiles,
    }


def get_profile(profile_id: str | None) -> dict[str, Any] | None:
    if not profile_id:
        return None
    for profile in list_profiles(include_sensitive=True):
        if profile["id"] == profile_id:
            return profile
    return None


def get_default_profile(capability: str) -> dict[str, Any] | None:
    defaults = resolve_defaults()
    profile_id = defaults.get(capability)
    return get_profile(profile_id) if profile_id else None


def _require_fields(profile: dict[str, Any], fields: list[str]) -> None:
    missing = [field for field in fields if not str(profile.get(field) or "").strip()]
    if missing:
        raise ValueError(f"{profile.get('name') or '模型配置'} 缺少必要字段：{', '.join(missing)}")


def _validate_profile(profile: dict[str, Any]) -> dict[str, Any]:
    capability = str(profile.get("capability") or "")
    provider = str(profile.get("provider") or "")
    if capability not in CAPABILITIES:
        raise ValueError(f"不支持的模型能力：{capability}")
    if not str(profile.get("name") or "").strip():
        raise ValueError("模型名称不能为空")
    if not provider:
        raise ValueError("模型 provider 不能为空")

    normalized = {
        "id": str(profile.get("id") or uuid.uuid4().hex[:12]),
        "name": str(profile.get("name") or "").strip(),
        "capability": capability,
        "provider": provider,
        "base_url": str(profile.get("base_url") or "").strip().rstrip("/"),
        "model_name": str(profile.get("model_name") or "").strip(),
        "default_params": _normalize_default_params(profile.get("default_params")),
        "enabled": bool(profile.get("enabled", True)),
        "builtin": False,
        "source": "user",
        "api_key": str(profile.get("api_key") or "").strip(),
    }

    if provider == MOCK_PROVIDER:
        return normalized

    if capability == "embedding":
        if provider != OLLAMA_PROVIDER:
            raise ValueError("当前只支持通过 Ollama 配置向量模型")
        _require_fields(normalized, ["base_url", "model_name"])
        return normalized

    if provider == OPENAI_COMPATIBLE_PROVIDER:
        _require_fields(normalized, ["base_url", "model_name"])
        return normalized

    if provider == POYO_ASYNC_PROVIDER:
        if capability not in {"image", "video"}:
            raise ValueError("PoYo provider 目前只支持 image / video 能力")
        _require_fields(normalized, ["base_url", "model_name"])
        return normalized

    if provider == MINIMAX_H3_ASYNC_PROVIDER:
        if capability != "video":
            raise ValueError("MiniMax H3 provider 目前只支持 video 能力")
        _require_fields(normalized, ["base_url", "model_name"])
        return normalized

    raise ValueError(f"暂不支持 provider：{provider}")


def save_registry(*, profiles: list[dict[str, Any]], defaults: dict[str, str]) -> dict[str, Any]:
    existing_saved_profiles = {profile["id"]: profile for profile in _load_saved_profiles()}
    normalized_profiles: list[dict[str, Any]] = []
    for item in profiles:
        normalized = _validate_profile(item)
        existing = existing_saved_profiles.get(normalized["id"])
        if (
            not normalized.get("api_key")
            and existing
            and str(existing.get("api_key") or "").strip()
            and normalized.get("provider") != MOCK_PROVIDER
        ):
            normalized["api_key"] = str(existing.get("api_key") or "").strip()
        normalized_profiles.append(normalized)
    set_kv(MODEL_REGISTRY_PROFILES_KEY, json.dumps(normalized_profiles, ensure_ascii=False, indent=2))

    builtin_profiles = [_serialize_profile(item, is_default=False) for item in _builtin_profiles()]
    profile_index = _build_profile_index(builtin_profiles + [_serialize_profile(item, is_default=False) for item in normalized_profiles])
    resolved_defaults = {
        capability: _resolve_default_for_capability(capability, defaults.get(capability), profile_index)
        for capability in CAPABILITIES
    }
    set_kv(MODEL_REGISTRY_DEFAULTS_KEY, json.dumps(resolved_defaults, ensure_ascii=False, indent=2))
    return serialize_registry_payload()


def _friendly_http_error(prefix: str, exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in {401, 403}:
            return f"{prefix}失败：认证未通过，请检查 API Key。"
        if status == 404:
            return f"{prefix}失败：接口地址不存在，请检查 base_url。"
        return f"{prefix}失败：上游服务返回 HTTP {status}。"
    if isinstance(exc, httpx.ConnectError):
        return f"{prefix}失败：无法连接到服务，请检查地址和网络。"
    if isinstance(exc, httpx.TimeoutException):
        return f"{prefix}失败：请求超时。"
    return f"{prefix}失败：{exc}"


async def _test_openai_compatible_profile(profile: dict[str, Any]) -> dict[str, Any]:
    _require_fields(profile, ["base_url", "model_name"])
    api_key = str(profile.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("真实模型测试连接需要 API Key。")

    base_url = str(profile.get("base_url") or "").rstrip("/")
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # pragma: no cover - covered by tests via public API
            raise ValueError(_friendly_http_error("测试真实模型连接", exc)) from exc

    model_ids = [str(item.get("id")) for item in data.get("data", []) if isinstance(item, dict)]
    configured = str(profile.get("model_name") or "")
    message = "连接成功"
    if model_ids and configured not in model_ids:
        message = f"连接成功，但远端模型列表中未发现 {configured}"

    return {"ok": True, "message": message}


async def _test_embedding_profile(profile: dict[str, Any]) -> dict[str, Any]:
    if profile.get("provider") != OLLAMA_PROVIDER:
        raise ValueError("当前只支持通过 Ollama 测试向量模型。")
    _require_fields(profile, ["base_url", "model_name"])
    base_url = str(profile.get("base_url") or "").rstrip("/")
    payload = {"model": profile["model_name"], "input": ["stage8 embedding smoke test"]}
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(f"{base_url}/api/embed", json=payload)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # pragma: no cover - covered by tests via public API
            raise ValueError(_friendly_http_error("测试向量模型连接", exc)) from exc

    embeddings = data.get("embeddings") or []
    first = embeddings[0] if embeddings else []
    dimension = len(first) if isinstance(first, list) else 0
    return {
        "ok": True,
        "message": f"连接成功，返回 {dimension} 维向量" if dimension else "连接成功",
        "dimension": dimension,
    }


async def test_profile_connection(
    *,
    profile_id: str | None = None,
    profile_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    saved_profile = get_profile(profile_id) if profile_id else None
    profile: dict[str, Any] | None = None

    if profile_payload:
        normalized_payload = _validate_profile(profile_payload)
        if (
            saved_profile
            and not str(normalized_payload.get("api_key") or "").strip()
            and str(saved_profile.get("api_key") or "").strip()
            and normalized_payload.get("provider") != MOCK_PROVIDER
        ):
            normalized_payload["api_key"] = str(saved_profile.get("api_key") or "").strip()
        merged_profile = {**(saved_profile or {}), **normalized_payload}
        profile = _serialize_profile(merged_profile, is_default=False)
    elif saved_profile:
        profile = saved_profile

    if not profile:
        raise ValueError("未找到要测试的模型配置。")

    if profile.get("provider") == MOCK_PROVIDER:
        return {
            "ok": True,
            "message": "Mock provider 可用。",
            "profile": _serialize_profile(profile, is_default=False),
        }

    if profile.get("provider") == POYO_ASYNC_PROVIDER:
        _require_fields(profile, ["base_url", "model_name"])
        response_profile = _serialize_profile(profile, is_default=False)
        return {
            "ok": True,
            "message": "PoYo 配置结构校验通过。当前测试不会发起真实扣费任务。",
            "profile": response_profile,
        }

    if profile.get("provider") == MINIMAX_H3_ASYNC_PROVIDER:
        _require_fields(profile, ["base_url", "model_name"])
        response_profile = _serialize_profile(profile, is_default=False)
        return {
            "ok": True,
            "message": "MiniMax H3 配置结构校验通过。当前测试不会发起真实扣费视频任务。",
            "profile": response_profile,
        }

    if profile.get("capability") == "video":
        return {
            "ok": False,
            "message": "真实视频 provider 尚未接入当前工作台，请继续使用 Mock 视频模型。",
            "profile": _serialize_profile(profile, is_default=False),
        }

    if profile.get("capability") == "embedding":
        result = await _test_embedding_profile(profile)
    else:
        result = await _test_openai_compatible_profile(profile)

    response_profile = _serialize_profile(profile, is_default=False)
    if "dimension" in result:
        default_params = dict(response_profile.get("default_params") or {})
        default_params["dimension"] = result["dimension"]
        response_profile["default_params"] = default_params

    return {
        "ok": bool(result.get("ok")),
        "message": str(result.get("message") or "连接成功"),
        "profile": response_profile,
    }
