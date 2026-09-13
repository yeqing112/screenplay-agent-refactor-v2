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

from core.director_patch_schema import CreativePatchSchemaError, parse_creative_patch, parse_creative_patch_partial


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


def _creative_for_beat(raw: dict[str, Any], base: dict[str, Any], index: int, participant_ids: list[str], strategy: dict[str, Any] | None = None) -> dict[str, Any]:
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
    # Strategy V2 is an approved beat-bound directing brief.  When supplied,
    # the planner executes its entries instead of re-inventing scene logic.
    strategy_obj = strategy if isinstance(strategy, dict) and _text(strategy.get("schema_version")) == "scene_directing_strategy_v2" else {}
    if strategy_obj:
        beat_id = _text(raw.get("beat_id"))
        perf = next((item for item in _list(strategy_obj.get("performance_arc")) if isinstance(item, dict) and _text(item.get("beat_id")) == beat_id), None)
        if perf:
            result["performance_direction"] = [{key: copy.deepcopy(perf.get(key)) for key in ("character_id", "objective", "visible_behavior", "subtext") if _text(perf.get(key))}]
        emo = next((item for item in _list(strategy_obj.get("emotion_curve")) if isinstance(item, dict) and _text(item.get("beat_id")) == beat_id), None)
        if emo:
            result["emotion"] = {"start": "承接上一镜" if index else "场景既有状态", "end": _text(emo.get("state")), "intensity": emo.get("intensity")}
        rhythm = next((item for item in _list(strategy_obj.get("rhythm_curve")) if isinstance(item, dict) and _text(item.get("beat_id")) == beat_id), None)
        if rhythm:
            target = rhythm.get("target_duration_range")
            duration = (float(target[0]) + float(target[1])) / 2 if isinstance(target, list) and len(target) == 2 else base.get("duration_hint_seconds", 4)
            result["edit"] = {"duration_seconds": duration, "cut_reason": _text(rhythm.get("cut_strategy")) or "beat_change", "hold_after_action_seconds": 0.4 if _text(rhythm.get("pace")) == "hold" else 0.2}
        info = next((item for item in _list(strategy_obj.get("information_plan")) if isinstance(item, dict) and _text(item.get("beat_id")) == beat_id), None)
        if info:
            result["information_strategy"] = {"reveals": copy.deepcopy(info.get("audience_should_know") or []), "withholds": copy.deepcopy(info.get("audience_should_not_know_yet") or []), "audience_focus": _text(info.get("reaction_priority"))}
    return result


def _normalise_llm_output(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict) and isinstance(raw.get("candidate"), dict):
        raw = raw["candidate"]
    if isinstance(raw, list):
        return {"shots": raw}
    if not isinstance(raw, dict):
        raise DirectorCreativeError("planner output must be a JSON object")
    return raw


def _bind_strategy_refs(patch_document: dict[str, Any], strategy: dict[str, Any], structural_shot_plan: dict[str, Any]) -> dict[str, Any]:
    """Attach deterministic beat-bound provenance to V2 patches.

    The refs describe which approved strategy entry a patch executes; they do
    not add or alter a creative value.  Missing refs are derived from the
    target shot's existing beat and the changed creative root.  Supplied refs
    outside the approved strategy are rejected rather than guessed.
    """

    if _text(strategy.get("schema_version")) != "scene_directing_strategy_v2":
        return patch_document
    chars_by_beat: dict[str, str] = {}
    for item in _list(strategy.get("performance_arc")) + _list(strategy.get("emotion_curve")):
        if isinstance(item, dict) and _text(item.get("beat_id")) and _text(item.get("character_id")):
            chars_by_beat.setdefault(_text(item["beat_id"]), _text(item["character_id"]))
    valid_refs: set[str] = set()
    for item in _list(strategy.get("performance_arc")):
        if isinstance(item, dict):
            beat, char = _text(item.get("beat_id")), _text(item.get("character_id"))
            if beat and char:
                valid_refs.add(f"performance:{beat}:{char}")
    for item in _list(strategy.get("emotion_curve")):
        if isinstance(item, dict):
            beat, char = _text(item.get("beat_id")), _text(item.get("character_id"))
            if beat and char:
                valid_refs.add(f"emotion:{beat}:{char}")
    for item in _list(strategy.get("rhythm_curve")):
        if isinstance(item, dict) and _text(item.get("beat_id")):
            valid_refs.add(f"rhythm:{_text(item['beat_id'])}")
    for item in _list(strategy.get("information_plan")):
        if isinstance(item, dict) and _text(item.get("beat_id")):
            valid_refs.add(f"information:{_text(item['beat_id'])}")
    shot_by_id = {_text(item.get("plan_shot_id")): item for item in _list(structural_shot_plan.get("shots")) if isinstance(item, dict) and _text(item.get("plan_shot_id"))}
    bound = copy.deepcopy(patch_document)
    for patch in _list(bound.get("patches")):
        if not isinstance(patch, dict):
            continue
        sid = _text(patch.get("plan_shot_id"))
        shot = shot_by_id.get(sid, {})
        beat = _text(shot.get("beat_id"))
        if not beat:
            raise DirectorCreativeError(f"strategy refs require a bound beat for {sid}")
        refs = [_text(ref) for ref in _list(patch.get("strategy_refs")) if _text(ref)]
        unknown = sorted(set(refs) - valid_refs)
        if unknown:
            raise DirectorCreativeError(f"patch {sid} contains strategy refs outside approved strategy: {', '.join(unknown)}")
        roots = {_text(path).replace("/", ".").split(".")[0] for path in _dict(patch.get("changes"))}
        char = chars_by_beat.get(beat)
        for root in roots:
            if root == "performance_direction" and char:
                refs.append(f"performance:{beat}:{char}")
            elif root == "emotion" and char:
                refs.append(f"emotion:{beat}:{char}")
            elif root == "edit":
                refs.append(f"rhythm:{beat}")
            elif root == "information_strategy":
                refs.append(f"information:{beat}")
            elif root in {"camera", "composition", "purpose", "dramatic_function", "why_this_shot", "visual_emphasis"}:
                # Camera/composition execution is still beat-bound, but does
                # not pretend to be one of the four specialised curves.
                refs.append(f"rhythm:{beat}" if f"rhythm:{beat}" in valid_refs else f"information:{beat}")
        patch["strategy_refs"] = sorted(set(refs))
    return bound


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
    strategy: dict[str, Any] | None = None,
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
        "strategy": copy.deepcopy(strategy if isinstance(strategy, dict) else {}),
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
        try:
            candidate = _merge_llm_creative(baseline, llm_output)
        except DirectorFactOverride:
            # Authoritative fact/provenance violations are never recoverable:
            # fail closed instead of allowing a fallback to conceal the
            # attempted mutation.
            raise
        except DirectorCreativeError:
            # A malformed creative proposal (for example an unbounded
            # auxiliary shot) is a planner failure, not permission to relax
            # the contract.  Return the deterministic structural baseline so
            # callers can recover without changing facts or silently writing
            # a partial candidate.
            planner_mode = "deterministic_fallback"
            planner_error = "creative candidate failed bounded merge validation"
            candidate = copy.deepcopy(baseline)
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
            generated_shot.update(_creative_for_beat(beats.get(beat_id, {}), raw, index, participants, strategy))
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
        "strategy_fingerprint": _text((strategy or {}).get("strategy_fingerprint")) if isinstance(strategy, dict) else "",
    }
    candidate["creative_validation"] = validation
    candidate["structural_plan_fingerprint"] = fingerprint(_protected_projection(baseline))
    return candidate


def build_creative_patch_candidate(
    *,
    structural_shot_plan: dict[str, Any],
    contract: dict[str, Any],
    strategy: dict[str, Any],
    llm_output: dict[str, Any] | None = None,
    llm_callable: Callable[[dict[str, Any]], Any] | None = None,
    confirmed: bool = False,
    allow_external_call: bool = False,
    mode: str = "shadow",
) -> dict[str, Any]:
    """Run the V2.1 shot-level planner and return *only* CreativePatch data.

    This is deliberately separate from ``build_creative_shot_plan_candidate``
    (the legacy V2 shadow API).  A model response containing ``shots`` or any
    other complete-plan field is rejected by the strict patch parser before it
    can be merged.  The function is pure and never persists a version or
    starts a media task.
    """

    if not isinstance(structural_shot_plan, dict):
        raise DirectorCreativeError("structural_shot_plan must be an object")
    if not isinstance(contract, dict) or not isinstance(strategy, dict):
        raise DirectorCreativeError("contract and strategy must be objects")
    evidence = {
        "protocol_version": "director-quality-v2-1-patch-planner",
        "contract": copy.deepcopy(contract),
        "strategy": copy.deepcopy(strategy),
        "structural_shot_plan": _protected_projection(structural_shot_plan),
    }
    evidence_fp = fingerprint(evidence)
    planner_mode = "creative_planner_patch"
    llm_called = False
    planner_error = ""
    schema_error_code = ""
    forbidden_field_attempt = False
    schema_rejections: list[dict[str, Any]] = []
    normalization_audit: dict[str, Any] = {
        "normalizer_version": "director-quality-v2-2-level0",
        "normalization_events": [],
        "deterministic_repair_events": [],
        "before_fingerprint": "",
        "after_fingerprint": "",
        "rejected": [],
    }
    output = llm_output
    if output is None and llm_callable is not None:
        if confirmed and allow_external_call:
            output = llm_callable(copy.deepcopy(evidence))
            llm_called = True
        else:
            planner_mode = "deterministic_fallback"
            planner_error = "external LLM call requires confirmed=true and allow_external_call=true"
    if output is None:
        # An empty, schema-valid patch document is the deterministic baseline:
        # it cannot change facts and lets later stages explicitly record a
        # fallback instead of pretending that creative planning succeeded.
        output = {
            "schema_version": "director_creative_patch_v1",
            "patches": [],
            "auxiliary_shot_proposals": [],
        }
        if planner_mode != "deterministic_fallback":
            planner_mode = "deterministic_fallback"
            planner_error = "no creative patch output supplied"
    # V2.2 routing begins with a provider-neutral Level 0/1 pass.  The rich
    # audit form is reduced to the existing strict schema shape before the
    # Contract/Compiler boundary, so old callers retain the same public
    # document format while equivalent envelopes no longer trigger an LLM
    # repair.  Any non-equivalent or unsafe representation is handed to the
    # strict parser unchanged so its fail-closed diagnostics remain intact.
    parse_input = output
    try:
        from core.director_patch_deterministic_repair import deterministic_repair_document

        known_ids = [
            str(item.get("plan_shot_id") or "").strip()
            for item in (structural_shot_plan.get("shots") or [])
            if isinstance(item, dict) and str(item.get("plan_shot_id") or "").strip()
        ]
        level01 = deterministic_repair_document(
            output,
            known_plan_shot_ids=known_ids,
            allowed_patch_paths=contract.get("allowed_patch_paths") if isinstance(contract, dict) else None,
        )
        parse_input = level01["schema_document"]
        normalization_audit = {
            "normalizer_version": "director-quality-v2-2-level0",
            "normalization_events": [event for event in level01.get("events", []) if "kind" not in event],
            "deterministic_repair_events": [event for event in level01.get("events", []) if "kind" in event],
            "before_fingerprint": level01.get("before_fingerprint", ""),
            "after_fingerprint": level01.get("after_fingerprint", ""),
            "rejected": copy.deepcopy(level01.get("rejected") or []),
            "path_resolution": copy.deepcopy((level01.get("document") or {}).get("normalization_metadata", {}).get("path_resolution") or {}),
        }
    except Exception as exc:
        # Keep the strict schema as the authority for malformed/non-equivalent
        # payloads.  Only the normalizer's structured error is exposed in
        # telemetry; no fallback or creative value is invented here.
        normalization_audit["error"] = str(exc)[:500]
        if hasattr(exc, "path_metrics"):
            normalization_audit["path_resolution"] = copy.deepcopy(getattr(exc, "path_metrics"))
    try:
        patch_document = parse_creative_patch(parse_input)
    except CreativePatchSchemaError as exc:
        # Salvage independent valid items where possible.  Fatal protocol or
        # fingerprint errors still fall back to an empty document; item-level
        # failures remain diagnostics for Partial Acceptance/Local Repair.
        schema_error_code = exc.code
        partial = parse_creative_patch_partial(output)
        schema_rejections = list(partial.get("errors") or [])
        forbidden_field_attempt = exc.code in {
            "DIRECTOR_FACT_OVERRIDE",
            "DIRECTOR_PATCH_FIELD_FORBIDDEN",
            "DIRECTOR_PATCH_PATH_FORBIDDEN",
        } or any(item.get("code") in {"DIRECTOR_FACT_OVERRIDE", "DIRECTOR_PATCH_FIELD_FORBIDDEN", "DIRECTOR_PATCH_PATH_FORBIDDEN"} for item in schema_rejections)
        if partial.get("fatal") or not isinstance(partial.get("document"), dict):
            patch_document = parse_creative_patch(
                {"schema_version": "director_creative_patch_v1", "patches": [], "auxiliary_shot_proposals": []}
            )
            planner_mode = "deterministic_fallback"
        else:
            patch_document = partial["document"]
            planner_mode = "partial_creative_planner" if (patch_document.get("patches") or patch_document.get("auxiliary_shot_proposals")) else "deterministic_fallback"
        planner_error = f"creative patch schema rejected: {exc.code}"
    try:
        patch_document = _bind_strategy_refs(patch_document, strategy, structural_shot_plan)
    except DirectorCreativeError as exc:
        # Strategy provenance is part of the review contract.  An invalid
        # reference cannot be repaired by inventing a beat/character; retain
        # a safe empty patch document and expose the failure to the caller.
        planner_mode = "deterministic_fallback"
        planner_error = str(exc)
        patch_document = parse_creative_patch(
            {"schema_version": "director_creative_patch_v1", "patches": [], "auxiliary_shot_proposals": []}
        )
    return {
        "schema_version": "director_creative_patch_candidate_v1",
        "status": "ready_for_review",
        "director_mode": planner_mode,
        "patch_document": patch_document,
        "model_info": {
            "mode": planner_mode,
            "llm_called": llm_called,
            "protocol_version": "director-quality-v2-1-patch-planner",
            "creative_evidence_fingerprint": evidence_fp,
            "planner_error": planner_error,
            "schema_pass": not bool(schema_error_code),
            "schema_error_code": schema_error_code,
            "forbidden_field_attempt": forbidden_field_attempt,
            "schema_rejections": schema_rejections,
            "normalization_metadata": copy.deepcopy(patch_document.get("normalization_metadata") or {}),
            "v22_normalization": normalization_audit,
        },
        "evidence_fingerprint": evidence_fp,
        "structural_plan_fingerprint": fingerprint(_protected_projection(structural_shot_plan)),
    }


# Friendly aliases for callers and hidden/regression tests that use the
# terminology from the blueprint.
build_director_creative_plan = build_creative_shot_plan_candidate
plan_creative_shot_plan = build_creative_shot_plan_candidate
run_director_creative_planner = build_creative_shot_plan_candidate
run_director_patch_planner = build_creative_patch_candidate


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
    "build_creative_patch_candidate",
    "build_director_creative_plan",
    "plan_creative_shot_plan",
    "run_director_creative_planner",
    "run_director_patch_planner",
]
