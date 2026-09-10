"""Per-call token budget guard for confirmed Smart Director LLM calls."""
from __future__ import annotations
from typing import Any
from models import get_kv, set_kv

KEY = "smart_director_agent_max_estimated_tokens"

def read_budget() -> dict[str, int]:
    try: limit = max(0, int(get_kv(KEY, "0") or 0))
    except ValueError: limit = 0
    return {"max_estimated_tokens": limit}

def write_budget(value: int) -> dict[str, int]:
    if value < 0 or value > 100000: raise ValueError("Agent 单次 token 预算必须在 0 到 100000 之间")
    set_kv(KEY, str(value)); return read_budget()

def check_budget(estimated_tokens: int) -> dict[str, Any]:
    limit = read_budget()["max_estimated_tokens"]
    return {"configured": bool(limit), "max_estimated_tokens": limit, "estimated_tokens": estimated_tokens, "allowed": not limit or estimated_tokens <= limit}
