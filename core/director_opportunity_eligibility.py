"""Evidence-gated Opportunity Eligibility V2.

The detector intentionally emits possible directing choices.  Eligibility is
the second, reviewable boundary: every detected record receives a deterministic
decision and reason.  A record is never silently removed from the denominator;
it is classified as ``ELIGIBLE``, ``NOT_APPLICABLE``, ``REDUNDANT``,
``WEAK_EVIDENCE`` or ``ALREADY_COVERED``.
"""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Iterable

from core.director_opportunity_model import normalize_opportunity, OpportunityModelError


ELIGIBILITY_V2_SCHEMA_VERSION = "director_opportunity_eligibility_v2"
ELIGIBILITY_STATUSES = (
    "ELIGIBLE",
    "NOT_APPLICABLE",
    "REDUNDANT",
    "WEAK_EVIDENCE",
    "ALREADY_COVERED",
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _all_text(*sources: Any) -> str:
    values: list[str] = []
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        else:
            text = _text(value)
            if text:
                values.append(text)
    for source in sources:
        visit(source)
    return " ".join(values).lower()


def _beat_map(*sources: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for source in sources:
        raw = source.get("beat_map") if isinstance(source.get("beat_map"), list) else source.get("beats")
        for item in _list(raw):
            if not isinstance(item, dict):
                continue
            beat_id = _text(item.get("beat_id") or item.get("id"))
            if beat_id and beat_id not in result:
                result[beat_id] = copy.deepcopy(item)
    return result


def _shots_by_beat(plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for shot in _list(plan.get("shots")):
        if not isinstance(shot, dict):
            continue
        beat_id = _text(shot.get("beat_id"))
        if beat_id:
            result.setdefault(beat_id, []).append(shot)
    return result


def _specific_reference(ref: Any, opportunity_type: str) -> bool:
    """Check that a reference names a trigger field, not just a collection."""

    value = _text(ref).lower()
    if not value:
        return False
    trigger_tokens = {
        "OPP_EMOTION_TURN": ("emotion_change", "emotion_turn", "emotional_shift", "emotion"),
        "OPP_REACTION": ("reaction", "action", "dialogue", "event"),
        "OPP_INFORMATION_WITHHOLD": ("withhold", "audience_should_not_know", "information_change"),
        "OPP_INFORMATION_REVEAL": ("information_change", "reveal", "event"),
        "OPP_POWER_SHIFT": ("power", "dominance", "conflict", "confrontation", "type"),
        "OPP_RHYTHM_CHANGE": ("duration", "rhythm", "type"),
        "OPP_PROP_EMPHASIS": ("prop_asset", "props", "asset_bindings", "prop", "event"),
        "OPP_SPATIAL_ISOLATION": ("frame_relationship", "participants", "composition"),
        "OPP_CHARACTER_ENTRANCE": ("entry", "entrance", "presence", "participants", "blocking"),
        "OPP_CHARACTER_EXIT": ("exit", "exited", "presence", "participants", "blocking"),
        "OPP_VISUAL_REVEAL": ("visual", "reveal", "event"),
        "OPP_SILENCE_HOLD": ("silence", "pause", "dialogue", "event"),
        "OPP_DIALOGUE_PRESSURE": ("dialogue", "conflict", "interruption", "dominance", "pressure", "subtext"),
        "OPP_ACTION_ACCELERATION": ("action", "accelerat", "chase", "type"),
        "OPP_SCENE_BUTTON": ("state_out", "scene_button", "button", "plot_result", "ending", "release", "hold"),
    }
    tokens = trigger_tokens.get(opportunity_type, ())
    if not any(token in value for token in tokens):
        return False
    # A collection-only path (e.g. ``treatment.beat_map``) is not precise
    # evidence.  ``participants`` remains valid only for entrance/exit and
    # spatial rules where it is itself the trigger field.
    collection_suffixes = (".beat_map", ".beats", ".shots", ".participants", ".props", ".asset_bindings")
    if value.endswith(collection_suffixes) and opportunity_type not in {"OPP_CHARACTER_ENTRANCE", "OPP_CHARACTER_EXIT", "OPP_SPATIAL_ISOLATION", "OPP_PROP_EMPHASIS"}:
        return False
    return True


def _explicit_presence_signal(beat: dict[str, Any], blocking: dict[str, Any], *, entering: bool) -> bool:
    keys = ("entry", "entry_state", "entrance", "entered", "presence_in") if entering else ("exit", "exit_state", "exits", "exited", "presence_out")
    for source in (beat, blocking):
        for key in keys:
            value = source.get(key)
            if value not in (None, "", [], {}):
                return True
    text = _all_text(beat)
    tokens = ("enter", "arrive", "进入", "出现") if entering else ("exit", "leave", "depart", "离开", "退场")
    return any(token in text for token in tokens)


def _dialogue_pressure_signal(beat: dict[str, Any], shot: dict[str, Any]) -> bool:
    text = _all_text(beat, shot)
    return any(token in text for token in (
        "conflict", "interruption", "dominance", "pressure", "subtext", "confrontation",
        "对峙", "冲突", "打断", "压迫", "逼问", "质问", "权力", "潜台词",
    ))


def _scene_button_signal(beat: dict[str, Any], script_scene: dict[str, Any], treatment: dict[str, Any]) -> bool:
    if _dict(script_scene.get("state_out")) or _dict(treatment.get("state_out")):
        return True
    return bool(_text(beat.get("scene_button") or beat.get("button") or beat.get("plot_result") or beat.get("ending") or beat.get("release")))


def _covered_dimensions(shot: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    camera = _dict(shot.get("camera"))
    if any(_text(camera.get(key)) for key in ("shot_size", "angle", "movement", "speed", "camera_side")):
        result.add("camera_language")
    if _text(shot.get("why_this_shot") or shot.get("dramatic_function")):
        result.add("shot_motivation")
    if _dict(shot.get("edit")):
        result.add("edit_strategy")
    if _dict(shot.get("emotion")):
        result.add("emotion_arc")
    if _dict(shot.get("performance_direction")):
        result.add("performance_direction")
    if _dict(shot.get("information_strategy")):
        result.add("information_strategy")
    composition = _dict(shot.get("composition"))
    if composition:
        result.add("spatial_clarity")
        if _text(composition.get("visual_emphasis")):
            result.add("visual_storytelling")
    if _text(shot.get("visual_emphasis")):
        result.add("visual_storytelling")
    return result


def evaluate_opportunity_eligibility(
    opportunities: Iterable[dict[str, Any]],
    *,
    script_scene: dict[str, Any] | None = None,
    treatment: dict[str, Any] | None = None,
    blocking: dict[str, Any] | None = None,
    structural_shot_plan: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return one deterministic eligibility decision for every candidate."""

    script = _dict(script_scene)
    treatment_obj = _dict(treatment)
    blocking_obj = _dict(blocking)
    plan = _dict(structural_shot_plan)
    beats = _beat_map(treatment_obj, script)
    shots = _shots_by_beat(plan)
    seen_keys: set[tuple[str, str]] = set()
    decisions: list[dict[str, Any]] = []
    for index, raw in enumerate(opportunities):
        try:
            opportunity = normalize_opportunity(raw)
        except OpportunityModelError as exc:
            raise OpportunityModelError(f"opportunities[{index}] is invalid: {exc}", code=exc.code, path=f"opportunities[{index}].{exc.path}") from exc
        opportunity_type = opportunity["type"]
        beat_id = opportunity["beat_id"]
        beat = beats.get(beat_id, {})
        beat_shots = shots.get(beat_id, [])
        shot = beat_shots[0] if beat_shots else {}
        refs = opportunity.get("evidence_refs") or []
        specific_refs = [ref for ref in refs if _specific_reference(ref, opportunity_type)]
        status = "ELIGIBLE"
        reason = "证据字段具体、目标未被覆盖，保留为可执行导演机会"
        # Presence, dialogue-pressure, and scene-button candidates have a
        # stronger negative decision than generic evidence: without the
        # required semantic trigger they are *not applicable*, even if a
        # detector supplied a broad collection reference.
        if opportunity_type == "OPP_CHARACTER_ENTRANCE" and not _explicit_presence_signal(beat, blocking_obj, entering=True):
            status = "NOT_APPLICABLE"
            reason = "只有参与者集合变化，没有明确入场/出现证据"
        elif opportunity_type == "OPP_CHARACTER_EXIT" and not _explicit_presence_signal(beat, blocking_obj, entering=False):
            status = "NOT_APPLICABLE"
            reason = "只有参与者集合变化，没有明确离场/退场证据"
        elif opportunity_type == "OPP_DIALOGUE_PRESSURE" and not _dialogue_pressure_signal(beat, shot):
            status = "NOT_APPLICABLE"
            reason = "存在对白，但没有冲突、打断、权力或潜台词压力证据"
        elif opportunity_type == "OPP_SCENE_BUTTON" and not _scene_button_signal(beat, script, treatment_obj):
            status = "NOT_APPLICABLE"
            reason = "没有结尾落点、释放、停留或视觉标点证据"
        elif not refs or not specific_refs:
            status = "WEAK_EVIDENCE"
            reason = "evidence_refs 未精确指向该机会的触发字段"
        else:
            key = (opportunity_type, beat_id)
            if key in seen_keys:
                status = "REDUNDANT"
                reason = "同一节拍已有同类型机会记录"
            elif shot and set(opportunity.get("recommended_directing_dimensions", [])) <= _covered_dimensions(shot):
                status = "ALREADY_COVERED"
                reason = "结构化镜头已经显式覆盖该机会的全部目标维度"
            seen_keys.add(key)
        decisions.append({
            "schema_version": ELIGIBILITY_V2_SCHEMA_VERSION,
            "opportunity_id": opportunity["opportunity_id"],
            "type": opportunity_type,
            "scene_id": opportunity["scene_id"],
            "beat_id": beat_id,
            "status": status,
            "eligible": status == "ELIGIBLE",
            "reason": reason,
            "evidence_refs": copy.deepcopy(refs),
            "specific_evidence_refs": copy.deepcopy(specific_refs),
            "recommended_directing_dimensions": copy.deepcopy(opportunity["recommended_directing_dimensions"]),
        })
    return decisions


def apply_opportunity_eligibility(
    opportunities: Iterable[dict[str, Any]],
    **evidence: Any,
) -> dict[str, Any]:
    """Apply V2 statuses while retaining one output record per detection."""

    normalized = [normalize_opportunity(item) for item in opportunities]
    decisions = evaluate_opportunity_eligibility(normalized, **evidence)
    decision_by_id = {item["opportunity_id"]: item for item in decisions}
    updated: list[dict[str, Any]] = []
    for item in normalized:
        decision = decision_by_id[item["opportunity_id"]]
        updated.append({**item, "eligible": bool(decision["eligible"])})
    return {
        "schema_version": ELIGIBILITY_V2_SCHEMA_VERSION,
        "opportunities": updated,
        "decisions": decisions,
        "metrics": build_eligibility_v2_metrics(decisions),
    }


def build_eligibility_v2_metrics(decisions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [item for item in decisions if isinstance(item, dict)]
    counts = Counter(_text(item.get("status")) for item in rows)
    total = len(rows)
    eligible = int(counts.get("ELIGIBLE", 0))
    return {
        "schema_version": ELIGIBILITY_V2_SCHEMA_VERSION,
        "detected_opportunity_count": total,
        "eligible_opportunity_count": eligible,
        "non_applicable_count": int(counts.get("NOT_APPLICABLE", 0)),
        "redundant_opportunity_count": int(counts.get("REDUNDANT", 0)),
        "weak_evidence_count": int(counts.get("WEAK_EVIDENCE", 0)),
        "already_covered_count": int(counts.get("ALREADY_COVERED", 0)),
        "eligibility_rate": (eligible / total) if total else None,
        "status_counts": {status: int(counts.get(status, 0)) for status in ELIGIBILITY_STATUSES},
        "decision_trace": copy.deepcopy(rows),
    }


# Naming aliases for integration callers and replay tools.
validate_opportunity_eligibility = evaluate_opportunity_eligibility
build_opportunity_eligibility = apply_opportunity_eligibility


__all__ = [
    "ELIGIBILITY_V2_SCHEMA_VERSION",
    "ELIGIBILITY_STATUSES",
    "evaluate_opportunity_eligibility",
    "validate_opportunity_eligibility",
    "apply_opportunity_eligibility",
    "build_opportunity_eligibility",
    "build_eligibility_v2_metrics",
]
