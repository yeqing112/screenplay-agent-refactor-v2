"""Stable-prefix prompt builder for Director Quality local repair."""

from __future__ import annotations

import hashlib
from typing import Any

from core.prompt_cache import canonical_json


REPAIR_PROMPT_PROTOCOL_VERSION = "director-quality-v2-2-1-repair-prompt-v1"

REPAIR_STABLE_PREFIX = """[DIRECTOR_REPAIR_PROTOCOL: director-quality-v2-2-1-repair-prompt-v1]
SECTION 1 — REPAIR ROLE
You are a bounded local repairer. Return one validated replacement only.

SECTION 2 — REPAIR CONTRACT
The program has already fixed the target shot and path. Preserve both exactly.
Authoritative facts, identity, participants, assets, chronology, continuity,
entry/exit state and duration are immutable.

SECTION 3 — REPAIR OUTPUT SCHEMA
Return exactly:
{"schema_version":"director_patch_repair_v1","target":{"plan_shot_id":"S03","path":"camera.shot_size"},"replacement_value":"CU","reason":"..."}

SECTION 4 — ALLOWED BEHAVIOR
Replace only the value at the supplied target. Use only the supplied allowed
repair paths and values justified by the issue and evidence.

SECTION 5 — FORBIDDEN BEHAVIOR
Never return patches[], shots, a complete scene/ShotPlan, new assets, facts,
events, participants, duration, continuity, identity, or a different target.
If the evidence is insufficient, return a contract-valid refusal object rather
than inventing information.
"""


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_director_repair_prompt(request: dict[str, Any]) -> dict[str, Any]:
    """Build a stable system prefix plus canonical variable request tail."""

    tail = "REPAIR_REQUEST\n" + canonical_json(request if isinstance(request, dict) else {})
    system_prompt = REPAIR_STABLE_PREFIX.strip()
    stable_hash = _sha256(system_prompt)
    return {
        "protocol_version": REPAIR_PROMPT_PROTOCOL_VERSION,
        "system_prompt": system_prompt,
        "user_prompt": tail,
        "stable_prefix_hash": stable_hash,
        "stable_prefix_length": len(system_prompt),
        "variable_tail_hash": _sha256(tail),
        "prompt_prefix_fingerprint": stable_hash,
    }


__all__ = ["REPAIR_PROMPT_PROTOCOL_VERSION", "REPAIR_STABLE_PREFIX", "build_director_repair_prompt"]
