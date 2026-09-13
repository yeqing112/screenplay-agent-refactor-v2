"""Blind-review helpers for Director Quality Benchmark V2.

The module only anonymises and records review metadata.  It never decides a
winner and never calls a judge model, so a report can distinguish deterministic
metrics from human/LLM blind preference evidence.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _fingerprint(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def prepare_blind_review(comparison: dict[str, Any], *, salt: str = "director-quality-v2") -> dict[str, Any]:
    """Return Version A/B payloads with baseline/planner roles removed."""
    if not isinstance(comparison, dict):
        raise ValueError("comparison must be an object")
    versions = []
    for key in ("version_a", "version_b"):
        value = comparison.get(key) if isinstance(comparison.get(key), dict) else {}
        if not value:
            raise ValueError(f"missing {key}")
        quality = value.get("director_quality") if isinstance(value.get("director_quality"), dict) else {}
        versions.append({"label": "Version A" if key == "version_a" else "Version B", "payload": {"director_quality": quality, "shot_count": value.get("shot_count"), "shots": value.get("shots")}})
    # Stable pseudo-random order prevents a reviewer from learning that A is
    # always the baseline while remaining reproducible in audit/replay.
    token = _fingerprint({"salt": salt, "comparison": comparison})
    if int(token[-1], 16) % 2:
        versions.reverse()
    return {
        "review_id": _fingerprint({"salt": salt, "comparison": comparison}),
        "versions": versions,
        "source_roles_hidden": True,
        "reviewer_type": "blind_review",
        "preferred_version": None,
        "reason": None,
        "judge_fingerprint": None,
    }


def record_blind_preference(review: dict[str, Any], *, preferred_version: str, reason: str = "", judge_fingerprint: str = "", reviewer_type: str = "blind_judge") -> dict[str, Any]:
    """Record a reviewer's preference without exposing source roles."""
    if not isinstance(review, dict) or not isinstance(review.get("versions"), list):
        raise ValueError("invalid blind review")
    allowed = {str(item.get("label")) for item in review["versions"] if isinstance(item, dict)}
    if preferred_version not in allowed:
        raise ValueError("preferred_version must be one of the anonymised versions")
    return {**review, "preferred_version": preferred_version, "reason": str(reason or ""), "judge_fingerprint": str(judge_fingerprint or ""), "reviewer_type": str(reviewer_type or "blind_judge")}


__all__ = ["prepare_blind_review", "record_blind_preference"]
