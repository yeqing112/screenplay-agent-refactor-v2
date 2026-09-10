"""Independent model selection for the smart director runtime.

The Agent stores only a reference to an existing LLM profile in the model
registry.  It never duplicates API keys and it never changes the production
LLM default.  Actual model invocation is deliberately deferred to Phase 2.
"""
from __future__ import annotations

from typing import Any

from api.model_registry import get_profile
from models import get_kv, set_kv


AGENT_MODEL_PROFILE_ID_KEY = "smart_director_agent_model_profile_id"
AGENT_THINKING_MODE_KEY = "smart_director_agent_thinking_mode"
AGENT_VISION_ENABLED_KEY = "smart_director_agent_vision_enabled"


def _read_bool(value: str, default: bool = False) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on", "enabled"}


def _public_profile(profile: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a profile safe to send to a browser.

    ``get_profile`` is intentionally an internal registry accessor and
    includes the credential so generation adapters can call a provider.  The
    Agent settings endpoint only needs descriptive metadata; returning the
    raw object here would leak the provider key to every settings-page user.
    """
    if not profile:
        return None
    return {key: value for key, value in profile.items() if key != "api_key"}


def read_agent_model_config() -> dict[str, Any]:
    profile_id = get_kv(AGENT_MODEL_PROFILE_ID_KEY, "").strip()
    profile = get_profile(profile_id) if profile_id else None
    if profile and profile.get("capability") != "llm":
        profile = None
    return {
        "profile_id": profile_id,
        "configured": bool(profile),
        "profile": _public_profile(profile),
        "uses_production_default": False,
        "runtime_policy": read_agent_runtime_policy(),
    }


def read_agent_runtime_policy() -> dict[str, Any]:
    thinking = get_kv(AGENT_THINKING_MODE_KEY, "disabled").strip().lower()
    if thinking not in {"enabled", "disabled"}:
        thinking = "disabled"
    return {
        "thinking": thinking,
        "vision_enabled": _read_bool(get_kv(AGENT_VISION_ENABLED_KEY, "0")),
    }


def write_agent_runtime_policy(*, thinking: str | None = None, vision_enabled: bool | None = None) -> dict[str, Any]:
    current = read_agent_runtime_policy()
    next_thinking = str(thinking if thinking is not None else current["thinking"]).strip().lower()
    if next_thinking not in {"enabled", "disabled"}:
        raise ValueError("Agent 思考模式只能是 enabled 或 disabled")
    set_kv(AGENT_THINKING_MODE_KEY, next_thinking)
    if vision_enabled is not None:
        set_kv(AGENT_VISION_ENABLED_KEY, "1" if bool(vision_enabled) else "0")
    return read_agent_runtime_policy()


def get_agent_model_profile_for_invocation() -> dict[str, Any] | None:
    """Return the credential-bearing profile for server-side use only.

    This must never be returned from an API route.  A future controlled Agent
    invocation uses this helper explicitly, so it cannot silently fall back
    to the production default model.
    """
    profile_id = get_kv(AGENT_MODEL_PROFILE_ID_KEY, "").strip()
    profile = get_profile(profile_id) if profile_id else None
    if not profile or profile.get("capability") != "llm" or not profile.get("enabled", True):
        return None
    return profile


def write_agent_model_config(profile_id: str) -> dict[str, Any]:
    normalized_id = str(profile_id or "").strip()
    if not normalized_id:
        set_kv(AGENT_MODEL_PROFILE_ID_KEY, "")
        return read_agent_model_config()
    profile = get_profile(normalized_id)
    if not profile or profile.get("capability") != "llm":
        raise ValueError("智能导演台只能选择已启用的 LLM 模型配置")
    if not profile.get("enabled", True):
        raise ValueError("所选 LLM 模型已停用，不能用于智能导演台")
    set_kv(AGENT_MODEL_PROFILE_ID_KEY, normalized_id)
    return read_agent_model_config()
