"""Controlled director-level creative planning for ShotPlan V2.

The deterministic :mod:`core.shot_plan` builder remains the structural
baseline.  This module is an optional creative layer that may change only
camera and other explicitly creative fields.  It never changes story facts,
beat order, asset identity, blocking source facts, or production chronology.

The public functions are pure by default.  A caller may provide an already
reviewed/mock ``llm_output`` or an ``llm_callable`` together with both
``confirmed=True`` and ``allow_external_call=True``.  No provider, network,
database, or media side effect is performed by this module.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Callable


PROTOCOL_VERSION = "director-quality-v2-controlled-planner-2026-09"
DIRECTOR_CREATIVE_LAYER = "DIRECTOR_CREATIVE"

# These are the only fields a creative planner is allowed to author or
# replace.  Structural fields are copied from the baseline and then frozen.
CREATIVE_SHOT_FIELDS = {
    "purpose",
    "dramatic_function",
    "why_this_shot",
    "emotion",
    "performance_direction",
    "camera",
    "composition",
    "edit",
    "information_strategy",
    "visual_emphasis",
}
AUXILIARY_FIELDS = {"source_shot_id", "source_beat_id", "auxiliary_type"}
CAMERA_FIELDS = {"shot_size", "angle", "movement", "speed", "camera_side"}
IMMUTABLE_SHOT_FIELDS = {
    "plan_shot_id",
    "scene_id",
    "beat_id",
    "event",
    "participants",
    "action_beats",
    "entry_state",
    "exit_state",
    "asset_bindings",
    "continuity_contract",
    "continuity",
    "spatial_source",
    "duration_hint_seconds",
}


class DirectorCreativeError(ValueError):
    """Base error for a rejected creative candidate."""

    code = "DIRECTOR_CREATIVE_INVALID"


class DirectorFactOverride(DirectorCreativeError):
    """Raised when a candidate attempts to overwrite an authoritative fact."""

    code = "DIRECTOR_FACT_OVERRIDE"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _shot_id(shot: dict[str, Any], index: int) -> str:
    return _text(shot.get("plan_shot_id")) or f"S{index + 1:02d}"


def _protected_projection(plan: dict[str, Any]) -> dict[str, Any]:
    """Return the structural/factual projection which must remain unchanged."""
    shots = []
    for index, raw in enumerate(_list(plan.get("shots"))):
        if not isinstance(raw, dict):
            continue
        shots.append({key: copy.deepcopy(raw.get(key)) for key in sorted(IMMUTABLE_SHOT_FIELDS) if key in raw})
    return {
        "scene_name": plan.get("scene_name"),
        "shots": shots,
        "unknowns": copy.deepcopy(_list(plan.get("unknowns"))),
    }


def _fact_projection(
    *,
    treatment: dict[str, Any],
    blocking: dict[str, Any],
    fact_snapshot: dict[str, Any] | None,
    scene_canonical: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a redacted immutable evidence projection for fingerprints."""
    snapshot = fact_snapshot if isinstance(fact_snapshot, dict) else {}
    source_facts = blocking.get("source_spatial_facts") if isinstance(blocking.get("source_spatial_facts"), list) else []
    return {
        "scene_name": _text(treatment.get("scene_name") or blocking.get("scene_name")),
        "scene_id": _text(treatment.get("scene_id") or blocking.get("scene_id")),
        "beat_map": copy.deepcopy(_list(treatment.get("beat_map"))),
        "participants": copy.deepcopy(_list(blocking.get("participants"))),
        "source_spatial_facts": copy.deepcopy(source_facts),
        "fact_snapshot": copy.deepcopy(snapshot),
        "scene_canonical": copy.deepcopy(scene_canonical if isinstance(scene_canonical, dict) else {}),
    }


def _beat_by_id(treatment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_list(treatment.get("beat_map"))):
        if not isinstance(raw, dict):
            continue
        result[_text(raw.get("beat_id") or raw.get("id") or f"B{index + 1:02d}")] = raw
    return result


def _participant_ids(blocking: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for item in _list(blocking.get("participants")):
        if not isinstance(item, dict):
            continue
        value = _text(item.get("character_id") or item.get("id"))
        if value and value not in result:
            result.append(value)
    return result


def _creative_for_beat(raw: dict[str, Any], base: dict[str, Any], index: int, participant_ids: list[str]) -> dict[str, Any]:
    """Produce a conservative, deterministic creative shadow candidate.

    This is intentionally a safe surrogate for an LLM in shadow/benchmark
    mode.  It uses only declared beat semantics and does not invent events.
    """
    beat_type = _text(raw.get("type")).lower()
    event = _text(raw.get("event"))
    info_change = _text(raw.get("information_change"))
    emotion_change = _text(raw.get("emotion_change"))
    mapping = {
        "setup": ("LS", "eye_level", "slow_pan", "slow", "center", "establish", "建立空间和人物关系"),
        "obstacle": ("MS", "three_quarter", "lateral_track", "medium", "center", "isolate", "把阻碍放入可见的空间关系"),
        "action": ("MLS", "eye_level", "tracking", "medium", "center", "follow_action", "跟随可观察行动完成节拍"),
        "decision": ("MCU", "low_angle", "slow_push_in", "slow", "left", "power_shift", "用距离和角度强调决策压力"),
        "power_shift": ("MCU", "low_angle", "slow_push_in", "slow", "left", "power_shift", "让权力变化在画面关系中可见"),
        "reveal": ("CU", "eye_level", "rack_focus", "slow", "center", "reveal", "以焦点和反应控制信息揭示"),
        "prop": ("insert", "eye_level", "rack_focus", "slow", "center", "emphasize_prop", "突出已声明的关键道具状态"),
        "handoff": ("insert", "over_shoulder", "rack_focus", "medium", "center", "emphasize_prop", "记录交接动作及其反应"),
    }
    shot_size, angle, movement, speed, side, purpose, reason = mapping.get(
        beat_type,
        ("MS", "eye_level", "static", "slow", "center", _text(base.get("purpose")) or "coverage", "服务当前节拍的必要覆盖"),
    )
    if index and beat_type == "setup":
        # Avoid an opening establishing shot being repeated for every setup.
        shot_size, movement, purpose, reason = "MS", "static", "reaction", "承接前一镜的可见反应"
    intensity = min(10, max(1, 4 + index))
    if beat_type in {"reveal", "decision", "power_shift"}:
        intensity = min(10, intensity + 2)
    subject = participant_ids[0] if participant_ids else ""
    performance = []
    if subject:
        performance.append({
            "character_id": subject,
            "objective": "推进当前节拍并回应已声明的局面",
            "visible_behavior": event or "通过目光、姿态或动作呈现节拍变化",
        })
    result = {
        "purpose": purpose,
        "dramatic_function": _text(raw.get("dramatic_function")) or purpose,
        "why_this_shot": reason,
        "emotion": {
            "start": "场景既有状态" if index == 0 else "承接上一镜",
            "end": emotion_change or ("信息压力上升" if beat_type in {"reveal", "decision", "power_shift"} else "状态发生可见变化"),
            "intensity": intensity,
        },
        "performance_direction": performance,
        "camera": {"shot_size": shot_size, "angle": angle, "movement": movement, "speed": speed, "camera_side": side},
        "composition": {
            "dominant_subject": subject,
            "frame_relationship": "two_shot" if len(participant_ids) > 1 and purpose not in {"isolate", "reveal", "emphasize_prop"} else "isolated",
            "negative_space": "right" if index % 2 == 0 else "left",
        },
        "edit": {
            "duration_seconds": base.get("duration_hint_seconds", 4),
            "cut_reason": "beat_change" if not purpose == "reaction" else "reaction_complete",
            "hold_after_action_seconds": 0.4 if purpose in {"reveal", "reaction", "power_shift"} else 0.2,
        },
        "information_strategy": {
            "reveals": [info_change] if info_change else [],
            "withholds": [] if info_change else ["未声明的新信息"],
            "audience_focus": "已声明节拍事件" if event else "当前人物关系",
        },
        "visual_emphasis": event or info_change,
    }
    return result


def _normalise_llm_output(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict) and isinstance(raw.get("candidate"), dict):
        raw = raw["candidate"]
    if isinstance(raw, list):
        return {"shots": raw}
    if not isinstance(raw, dict):
        raise DirectorCreativeError("planner output must be a JSON object")
    return raw


def _merge_llm_creative(base: dict[str, Any], llm_output: Any) -> dict[str, Any]:
    """Merge an LLM proposal while rejecting every non-creative mutation."""
    proposal = _normalise_llm_output(llm_output)
    allowed_top = {"scene_name", "shots", "unknowns", "creative_contract", "model_info"}
    unexpected_top = sorted(set(proposal) - allowed_top)
    if unexpected_top:
        raise DirectorFactOverride(f"candidate contains forbidden top-level fields: {', '.join(unexpected_top)}")
    if "scene_name" in proposal and _text(proposal.get("scene_name")) != _text(base.get("scene_name")):
        raise DirectorFactOverride("scene_name is authoritative")
    if "unknowns" in proposal and proposal.get("unknowns") != base.get("unknowns", []):
        raise DirectorFactOverride("unknowns cannot be changed by the creative planner")
    contract = proposal.get("creative_contract")
    if isinstance(contract, dict) and any(key in contract for key in ("facts", "source_facts", "fact_snapshot", "characters", "relationships", "dialogue", "scene_location", "time_weather", "beat_order")):
        raise DirectorFactOverride("creative_contract contains authoritative fact fields")
    proposed_shots = proposal.get("shots", [])
    if not isinstance(proposed_shots, list):
        raise DirectorCreativeError("planner shots must be a list")
    by_id = {_shot_id(item, i): item for i, item in enumerate(_list(base.get("shots"))) if isinstance(item, dict)}
    merged = copy.deepcopy(base)
    baseline_ids = list(by_id)
    seen: set[str] = set()
    seen_baseline_ids: list[str] = []
    result_shots: list[dict[str, Any]] = []
    for i, proposed in enumerate(proposed_shots):
        if not isinstance(proposed, dict):
            raise DirectorCreativeError("planner shot must be an object")
        sid = _shot_id(proposed, i)
        if sid in seen:
            raise DirectorCreativeError(f"duplicate plan_shot_id: {sid}")
        seen.add(sid)
        if sid in by_id:
            seen_baseline_ids.append(sid)
            original = by_id[sid]
            forbidden = sorted(set(proposed) - (CREATIVE_SHOT_FIELDS | IMMUTABLE_SHOT_FIELDS | AUXILIARY_FIELDS))
            if forbidden:
                raise DirectorFactOverride(f"{sid} contains forbidden fields: {', '.join(forbidden)}")
            if any(field in proposed for field in AUXILIARY_FIELDS):
                raise DirectorFactOverride(f"{sid} provenance fields are immutable")
            for field in IMMUTABLE_SHOT_FIELDS:
                if field in proposed and proposed.get(field) != original.get(field):
                    raise DirectorFactOverride(f"{sid}.{field} is authoritative")
            updated = copy.deepcopy(original)
            for field in CREATIVE_SHOT_FIELDS:
                if field in proposed:
                    updated[field] = copy.deepcopy(proposed[field])
            result_shots.append(updated)
        else:
            # New shots are allowed only as bounded auxiliary coverage and
            # must carry a source reference and an explicit motivation.
            forbidden = sorted(set(proposed) - (CREATIVE_SHOT_FIELDS | IMMUTABLE_SHOT_FIELDS | AUXILIARY_FIELDS))
            if forbidden:
                raise DirectorFactOverride(f"auxiliary {sid} contains forbidden fields: {', '.join(forbidden)}")
            source_beat = _text(proposed.get("source_beat_id") or proposed.get("beat_id"))
            aux_type = _text(proposed.get("auxiliary_type")).lower()
            if not source_beat or aux_type not in {"reaction", "insert", "establishing", "transition"}:
                raise DirectorCreativeError(f"auxiliary shot {sid} requires source_beat_id and a bounded auxiliary_type")
            if not _text(proposed.get("why_this_shot")):
                raise DirectorCreativeError(f"auxiliary shot {sid} requires why_this_shot")
            result_shots.append(copy.deepcopy(proposed))
    if seen_baseline_ids != [sid for sid in baseline_ids if sid in seen]:
        raise DirectorFactOverride("baseline plan_shot_id order must be preserved")
    merged["shots"] = result_shots
    return merged


def validate_creative_candidate(
    candidate: dict[str, Any],
    structural_plan: dict[str, Any],
    *,
    treatment: dict[str, Any] | None = None,
    blocking: dict[str, Any] | None = None,
    fact_snapshot: dict[str, Any] | None = None,
    scene_canonical: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate immutable evidence and bounded auxiliary-shot rules."""
    if not isinstance(candidate, dict) or not isinstance(structural_plan, dict):
        raise DirectorCreativeError("candidate and structural_plan must be objects")
    base_ids = [_shot_id(item, i) for i, item in enumerate(_list(structural_plan.get("shots"))) if isinstance(item, dict)]
    candidate_items = [item for item in _list(candidate.get("shots")) if isinstance(item, dict)]
    candidate_base_ids = [_shot_id(item, i) for i, item in enumerate(candidate_items) if _shot_id(item, i) in base_ids]
    if candidate_base_ids != base_ids:
        raise DirectorFactOverride("baseline ShotPlan IDs/order must be preserved")
    baseline_by_id = {_shot_id(item, i): item for i, item in enumerate(_list(structural_plan.get("shots"))) if isinstance(item, dict)}
    candidate_by_id = {_shot_id(item, i): item for i, item in enumerate(candidate_items) if _shot_id(item, i) in baseline_by_id}
    for sid in base_ids:
        original, proposed = baseline_by_id[sid], candidate_by_id[sid]
        for field in IMMUTABLE_SHOT_FIELDS:
            if field in proposed and proposed.get(field) != original.get(field):
                raise DirectorFactOverride(f"{sid}.{field} is authoritative")
        for field in AUXILIARY_FIELDS:
            if field in proposed and proposed.get(field) != original.get(field):
                raise DirectorFactOverride(f"{sid}.{field} provenance is authoritative")
    if candidate.get("scene_name") != structural_plan.get("scene_name") or candidate.get("unknowns", []) != structural_plan.get("unknowns", []):
        raise DirectorFactOverride("scene_name and unknowns are authoritative")
    beat_counts: dict[str, int] = {}
    for item in candidate_items:
        sid = _shot_id(item, 0)
        source_beat = _text(item.get("source_beat_id") or item.get("beat_id"))
        if sid not in base_ids:
            aux_type = _text(item.get("auxiliary_type")).lower()
            if aux_type not in {"reaction", "insert", "establishing", "transition"} or not _text(item.get("why_this_shot")):
                raise DirectorCreativeError(f"auxiliary shot {sid} is not bounded or motivated")
            beat_counts[source_beat] = beat_counts.get(source_beat, 0) + 1
            if beat_counts[source_beat] > 2:
                raise DirectorCreativeError(f"beat {source_beat} has more than two auxiliary shots")
        camera = _dict(item.get("camera"))
        if not _text(camera.get("shot_size")) or not _text(camera.get("movement")):
            raise DirectorCreativeError(f"{sid} requires camera.shot_size and camera.movement")
        # Baseline shots may intentionally lack creative fields; the quality
        # validator reports that as UNMOTIVATED_SHOT.  Auxiliary shots are
        # different: they must prove their bounded purpose before admission.
        if sid not in base_ids and not _text(item.get("why_this_shot")):
            raise DirectorCreativeError(f"{sid} has no director motivation")
    return {
        "status": "valid",
        "code": "OK",
        "fact_fingerprint": fingerprint(_fact_projection(treatment=treatment or {}, blocking=blocking or {}, fact_snapshot=fact_snapshot, scene_canonical=scene_canonical)),
        "structural_fingerprint": fingerprint(_protected_projection(structural_plan)),
        "shot_count": len(candidate_items),
        "baseline_shot_count": len(base_ids),
    }


def build_creative_shot_plan_candidate(
    *,
    structural_shot_plan: dict[str, Any],
    treatment: dict[str, Any] | None = None,
    blocking: dict[str, Any] | None = None,
    fact_snapshot: dict[str, Any] | None = None,
    scene_canonical: dict[str, Any] | None = None,
    llm_output: dict[str, Any] | list[dict[str, Any]] | None = None,
    llm_callable: Callable[[dict[str, Any]], Any] | None = None,
    confirmed: bool = False,
    allow_external_call: bool = False,
    mode: str = "shadow",
) -> dict[str, Any]:
    """Build a reviewable creative candidate without production side effects.

    ``llm_callable`` is invoked only when both explicit gates are true.  The
    callable receives a redacted evidence packet and must return JSON.  This
    hook is intentionally dependency-injected so tests can use a mock and
    production callers can enforce their own provider/audit boundary.
    """
    if not isinstance(structural_shot_plan, dict):
        raise DirectorCreativeError("structural_shot_plan must be an object")
    baseline = copy.deepcopy(structural_shot_plan)
    baseline.setdefault("shots", [])
    baseline.setdefault("unknowns", [])
    treatment_obj = treatment if isinstance(treatment, dict) else {}
    blocking_obj = blocking if isinstance(blocking, dict) else {}
    beats = _beat_by_id(treatment_obj)
    participants = _participant_ids(blocking_obj)
    evidence = {
        "protocol_version": PROTOCOL_VERSION,
        "treatment": copy.deepcopy(treatment_obj),
        "blocking": copy.deepcopy(blocking_obj),
        "fact_snapshot": copy.deepcopy(fact_snapshot if isinstance(fact_snapshot, dict) else {}),
        "scene_canonical": copy.deepcopy(scene_canonical if isinstance(scene_canonical, dict) else {}),
        "structural_plan": _protected_projection(baseline),
    }
    evidence_fp = fingerprint(evidence)
    llm_called = False
    planner_mode = "creative_planner_shadow"
    planner_error = ""
    if llm_output is None and llm_callable is not None:
        if confirmed and allow_external_call:
            llm_output = llm_callable(copy.deepcopy(evidence))
            llm_called = True
            planner_mode = "creative_planner_llm"
        else:
            planner_mode = "deterministic_fallback"
            planner_error = "external LLM call requires confirmed=true and allow_external_call=true"
    if llm_output is not None:
        candidate = _merge_llm_creative(baseline, llm_output)
    elif planner_mode == "deterministic_fallback":
        # A gated-but-unconfirmed external call must return the exact
        # deterministic baseline, never a creative surrogate that could be
        # mistaken for a successful planner result.
        candidate = copy.deepcopy(baseline)
    else:
        candidate = copy.deepcopy(baseline)
        generated: list[dict[str, Any]] = []
        for index, raw in enumerate(_list(baseline.get("shots"))):
            if not isinstance(raw, dict):
                raise DirectorCreativeError("structural ShotPlan contains a non-object shot")
            beat_id = _text(raw.get("beat_id"))
            generated_shot = copy.deepcopy(raw)
            generated_shot.update(_creative_for_beat(beats.get(beat_id, {}), raw, index, participants))
            generated.append(generated_shot)
        candidate["shots"] = generated
    try:
        validation = validate_creative_candidate(candidate, baseline, treatment=treatment_obj, blocking=blocking_obj, fact_snapshot=fact_snapshot, scene_canonical=scene_canonical)
    except DirectorFactOverride:
        # Fact authority is fail-closed and must never silently fall back.
        raise
    except DirectorCreativeError:
        planner_mode = "deterministic_fallback"
        planner_error = "creative candidate failed bounded validation"
        candidate = copy.deepcopy(baseline)
        validation = validate_creative_candidate(candidate, baseline, treatment=treatment_obj, blocking=blocking_obj, fact_snapshot=fact_snapshot, scene_canonical=scene_canonical)
    candidate["schema_version"] = "shot_plan_v2_creative_candidate"
    candidate["status"] = "ready_for_review"
    candidate["director_mode"] = planner_mode
    # Preserve the structural ShotPlan evidence identity so an optional
    # shadow draft can later pass the existing ShotPlan confirmation stale
    # check.  The richer creative packet gets its own separate fingerprint.
    candidate["evidence_fingerprint"] = _text(baseline.get("evidence_fingerprint")) or evidence_fp
    candidate["creative_evidence_fingerprint"] = evidence_fp
    candidate["model_info"] = {
        "mode": planner_mode,
        "llm_called": llm_called,
        "protocol_version": PROTOCOL_VERSION,
        "creative_evidence_fingerprint": evidence_fp,
        "planner_error": planner_error,
    }
    candidate["creative_validation"] = validation
    candidate["structural_plan_fingerprint"] = fingerprint(_protected_projection(baseline))
    return candidate


# Friendly aliases for callers and hidden/regression tests that use the
# terminology from the blueprint.
build_director_creative_plan = build_creative_shot_plan_candidate
plan_creative_shot_plan = build_creative_shot_plan_candidate
run_director_creative_planner = build_creative_shot_plan_candidate


__all__ = [
    "PROTOCOL_VERSION",
    "DIRECTOR_CREATIVE_LAYER",
    "CREATIVE_SHOT_FIELDS",
    "AUXILIARY_FIELDS",
    "DirectorCreativeError",
    "DirectorFactOverride",
    "fingerprint",
    "validate_creative_candidate",
    "build_creative_shot_plan_candidate",
    "build_director_creative_plan",
    "plan_creative_shot_plan",
    "run_director_creative_planner",
]
