"""Deterministic shot-intent and action-timing planners.

The planners deliberately operate on facts already declared in Shot Schema /
Prompt IR.  They do not infer story meaning from keywords and they never
rewrite a shot.  Their output is an auditable plan that can be shown to a
reviewer and consumed by the executability gate.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _beat_text(beat: dict[str, Any]) -> str:
    return _text(beat.get("description") or beat.get("action") or beat.get("text"))


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def build_shot_intent_plan(
    *,
    shot_purpose: Any = "",
    core_action: Any = "",
    action_process: Any = "",
    action_beats: list[dict[str, Any]] | None = None,
    emotion_arc: dict[str, Any] | None = None,
    start_state: Any = "",
    end_state: Any = "",
) -> dict[str, Any]:
    """Build a traceable intent summary from declared shot fields.

    Missing fields remain explicit in ``unknowns``.  In particular, the
    planner does not manufacture a dramatic purpose, subject or emotion from
    prose.  This keeps a plan useful for review without turning it into a
    hidden heuristic rewrite layer.
    """

    beats = [beat for beat in (action_beats or []) if isinstance(beat, dict) and _beat_text(beat)]
    primary_action = _text(core_action)
    primary_source = "core_action" if primary_action else ""
    if not primary_action and beats:
        primary_action = _beat_text(beats[0])
        primary_source = "action_beats[0]"
    if not primary_action and _text(action_process):
        primary_action = _text(action_process)
        primary_source = "action_process"

    arc = emotion_arc if isinstance(emotion_arc, dict) else {}
    emotion = {
        "start": _text(arc.get("start")),
        "end": _text(arc.get("end")),
        "intensity": _text(arc.get("intensity")),
    }
    unknowns: list[str] = []
    if not primary_action:
        unknowns.append("core_action")
    if not _text(shot_purpose):
        unknowns.append("shot_purpose")
    if not _text(start_state):
        unknowns.append("start_state")
    if not _text(end_state):
        unknowns.append("end_state")

    payload = {
        "schema_version": "shot_intent_plan_v1",
        "status": "ready" if not unknowns else "needs_information",
        "purpose": _text(shot_purpose),
        "primary_action": primary_action,
        "primary_action_source": primary_source,
        "action_count": len(beats) or (1 if primary_action else 0),
        "emotion_arc": emotion,
        "start_state": _text(start_state),
        "end_state": _text(end_state),
        "unknowns": unknowns,
    }
    payload["fingerprint"] = _canonical_fingerprint({k: v for k, v in payload.items() if k != "fingerprint"})
    return payload


def build_action_timing_plan(
    *,
    duration: Any,
    action_beats: list[dict[str, Any]] | None = None,
    fallback_action: Any = "",
) -> dict[str, Any]:
    """Allocate a shot's declared beats to a deterministic millisecond timeline.

    Explicit per-beat durations are preserved.  Unspecified beats share the
    remaining time; when no durations are declared, all beats share the shot
    duration equally.  A negative remainder is a conflict rather than an
    automatic compression, so callers can block or ask for a revision.
    """

    try:
        seconds = float(duration)
    except (TypeError, ValueError):
        seconds = 0
    total_ms = int(round(seconds * 1000)) if math.isfinite(seconds) and seconds > 0 else 0
    source_beats = [beat for beat in (action_beats or []) if isinstance(beat, dict) and _beat_text(beat)]
    if not source_beats and _text(fallback_action):
        source_beats = [{"description": _text(fallback_action), "_synthetic": True}]

    unknowns: list[str] = []
    if total_ms <= 0:
        unknowns.append("duration")
    if not source_beats:
        unknowns.append("action_beats")
    if unknowns:
        payload = {
            "schema_version": "action_timing_plan_v1",
            "status": "needs_information",
            "duration_ms": max(total_ms, 0),
            "segments": [],
            "unknowns": unknowns,
        }
        payload["fingerprint"] = _canonical_fingerprint({k: v for k, v in payload.items() if k != "fingerprint"})
        return payload

    explicit: list[float | None] = []
    for beat in source_beats:
        explicit.append(
            _positive_number(
                beat.get("duration_ms")
                if beat.get("duration_ms") is not None
                else beat.get("duration_seconds")
                if beat.get("duration_seconds") is not None
                else beat.get("duration")
            )
        )
    # Values over 20 are treated as milliseconds; smaller values are seconds.
    explicit_ms = [
        (int(round(value)) if value is not None and value > 20 else int(round(value * 1000)) if value is not None else None)
        for value in explicit
    ]
    declared_total = sum(value for value in explicit_ms if value is not None)
    missing_count = sum(value is None for value in explicit_ms)
    remainder = total_ms - declared_total
    if remainder < 0:
        payload = {
            "schema_version": "action_timing_plan_v1",
            "status": "conflict",
            "duration_ms": total_ms,
            "segments": [],
            "unknowns": ["declared_beat_durations_exceed_shot_duration"],
            "declared_duration_ms": declared_total,
        }
        payload["fingerprint"] = _canonical_fingerprint({k: v for k, v in payload.items() if k != "fingerprint"})
        return payload

    if missing_count:
        base, extra = divmod(remainder, missing_count)
        allocations = [value if value is not None else base for value in explicit_ms]
        for index, value in enumerate(explicit_ms):
            if value is None and extra:
                allocations[index] += 1
                extra -= 1
    else:
        allocations = explicit_ms
    if all(value is None for value in explicit_ms):
        base, extra = divmod(total_ms, len(source_beats))
        allocations = [base + (1 if index < extra else 0) for index in range(len(source_beats))]

    segments: list[dict[str, Any]] = []
    cursor = 0
    for index, (beat, allocated) in enumerate(zip(source_beats, allocations), start=1):
        allocated = max(int(allocated or 0), 0)
        segment = {
            "sequence": index,
            "start_ms": cursor,
            "end_ms": cursor + allocated,
            "duration_ms": allocated,
            "action": _beat_text(beat),
            "source": "declared" if explicit_ms[index - 1] is not None else "equal_remainder",
        }
        segments.append(segment)
        cursor += allocated
    payload = {
        "schema_version": "action_timing_plan_v1",
        "status": "ready",
        "duration_ms": total_ms,
        "segments": segments,
        "allocation": "declared" if missing_count == 0 and any(value is not None for value in explicit_ms) else "equal",
        "unknowns": [],
    }
    payload["fingerprint"] = _canonical_fingerprint({k: v for k, v in payload.items() if k != "fingerprint"})
    return payload

