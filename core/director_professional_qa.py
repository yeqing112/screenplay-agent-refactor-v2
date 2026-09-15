"""Deterministic Professional Director QA Foundation (Layer 2).

This is a consistency/traceability layer, not an artistic truth score.  It
deliberately keeps the existing DQ signal separate and emits evidence-rich
findings with repairability routing.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

from core.director_strategy_to_shot_contract import REQUIRED_TRACE_FIELDS, validate_strategy_traceability


QA_SCHEMA_VERSION = "director_professional_qa_v1"
QA_STATUSES = ("PROFESSIONAL_QA_PASS", "PROFESSIONAL_QA_REPAIRABLE", "PROFESSIONAL_QA_REDESIGN_REQUIRED", "PROFESSIONAL_QA_HUMAN_REVIEW")
ISSUE_CODES = ("STRATEGY_PHASE_UNCOVERED", "GENERIC_SHOT_MOTIVATION", "UNMOTIVATED_CAMERA_CHANGE", "VISUAL_GRAMMAR_BREAK", "EMOTION_ARC_MISMATCH", "EMOTION_ZIGZAG", "REVEAL_TOO_EARLY", "REVEAL_TOO_LATE", "INFORMATION_ARC_GAP", "PERFORMANCE_ARC_GAP", "POWER_SHIFT_NOT_VISUALIZED", "EDIT_ARC_MISMATCH", "OVER_CUTTING", "REACTION_MISSING", "REDUNDANT_COVERAGE", "CAMERA_MOVEMENT_OVERUSE", "SHOT_SIZE_NOISE", "RANDOM_VARIATION", "UNMOTIVATED_VARIATION", "TRACE_FIELD_MISSING")
GENERIC_MOTIVATION = {"show the beat", "show the event", "help audience follow", "make action visible", "展示当前节拍", "帮助观众理解", "让动作可见"}


def _text(value: Any) -> str: return str(value or "").strip()
def _dict(value: Any) -> dict[str, Any]: return value if isinstance(value, dict) else {}
def _list(value: Any) -> list[Any]: return value if isinstance(value, list) else []


def _finding(code: str, *, dimension: str, evidence: str, shot_ids: list[str] | None = None, strategy_reference: str = "", repairability: str = "SCENE_REPAIR", suggested_action: str = "") -> dict[str, Any]:
    return {"dimension": dimension, "status": "FAIL", "evidence": evidence, "shot_ids": shot_ids or [], "strategy_reference": strategy_reference, "issue_code": code, "repairability": repairability, "suggested_action": suggested_action or f"route {repairability.lower()} and preserve source facts"}


def _strategy_maps(strategy: dict[str, Any]) -> tuple[dict[str, str], dict[str, float], dict[str, list[str]], dict[str, list[str]]]:
    phases = {}
    emotion = {}
    reveals = {}
    performance: dict[str, list[str]] = {}
    # V2 is phase-centric; V1 remains supported for historical replay.
    phase_rows = _list(strategy.get("scene_phases")) or _list(strategy.get("audience_experience"))
    for row in phase_rows:
        if isinstance(row, dict):
            for beat in _list(row.get("beat_ids")): phases[_text(beat)] = _text(row.get("phase_id"))
            if not _list(row.get("beat_ids")) and _text(row.get("beat_id")):
                phases[_text(row.get("beat_id"))] = _text(row.get("phase_id") or row.get("phase"))
            if isinstance(row.get("emotion"), dict):
                e = _dict(row.get("emotion"))
                for beat in _list(row.get("beat_ids")):
                    emotion[_text(beat)] = float(e.get("intensity_hint") or 0)
            if isinstance(row.get("information"), dict):
                info = _dict(row.get("information"))
                for beat in _list(row.get("beat_ids")):
                    reveals[_text(beat)] = [_text(v) for v in _list(info.get("reveal")) if _text(v)]
            if isinstance(row.get("performance"), list):
                for perf in row["performance"]:
                    if isinstance(perf, dict):
                        performance.setdefault(_text(perf.get("character_id")), []).extend(_list(row.get("beat_ids")))
    for row in _list(strategy.get("emotional_arc")):
        if isinstance(row, dict):
            for beat in _list(row.get("beat_ids")) or [_text(row.get("beat_id"))]:
                if _text(beat): emotion[_text(beat)] = float(row.get("intensity_hint") or 0)
    for row in _list(strategy.get("information_reveal_plan")):
        if isinstance(row, dict): reveals[_text(row.get("beat_id"))] = [_text(v) for v in _list(row.get("reveal")) if _text(v)]
    for row in _list(strategy.get("performance_arc")):
        if isinstance(row, dict): performance[_text(row.get("character_id"))] = [_text(v) for v in _list(row.get("beat_ids")) if _text(v)]
    return phases, emotion, reveals, performance


def _issue_route(code: str) -> str:
    if code in {"GENERIC_SHOT_MOTIVATION", "TRACE_FIELD_MISSING"}: return "TAIL_REPAIR"
    if code in {"STRATEGY_PHASE_UNCOVERED", "INFORMATION_ARC_GAP", "PERFORMANCE_ARC_GAP", "EMOTION_ARC_MISMATCH", "EMOTION_ZIGZAG", "EDIT_ARC_MISMATCH", "VISUAL_GRAMMAR_BREAK", "POWER_SHIFT_NOT_VISUALIZED", "REACTION_MISSING", "REDUNDANT_COVERAGE", "UNMOTIVATED_CAMERA_CHANGE", "CAMERA_MOVEMENT_OVERUSE"}: return "SCENE_REPAIR"
    if code in {"SHOT_SIZE_NOISE", "RANDOM_VARIATION", "UNMOTIVATED_VARIATION", "OVER_CUTTING"}: return "SCENE_REDESIGN"
    return "HUMAN_REVIEW"


def detect_scorer_gaming(*, strategy: dict[str, Any], shot_plan: dict[str, Any]) -> dict[str, Any]:
    shots = [row for row in _list(_dict(shot_plan).get("shots")) if isinstance(row, dict)]
    motivations = [_text(row.get("why_this_shot")) for row in shots]
    cameras = [_dict(row.get("camera")) for row in shots]
    emotions = [float(_dict(row.get("emotion")).get("intensity")) for row in shots if isinstance(_dict(row.get("emotion")).get("intensity"), (int, float))]
    repeated_generic = sum(1 for value in motivations if value.lower() in GENERIC_MOTIVATION or value.lower().startswith("show the "))
    camera_unique = len({tuple(_text(camera.get(k)) for k in ("shot_size", "angle", "movement", "speed", "camera_side")) for camera in cameras})
    zigzag = len(emotions) >= 4 and all((emotions[i] - emotions[i - 1]) * (emotions[i + 1] - emotions[i]) < 0 for i in range(1, len(emotions) - 1))
    signals = []
    if repeated_generic >= max(2, len(shots) // 2): signals.append("generic_motivation_fill")
    if shots and camera_unique == len(shots) and len(shots) >= 4: signals.append("camera_diversity_without_strategy")
    if zigzag: signals.append("mechanical_emotion_zigzag")
    return {"schema_version": "director_scorer_gaming_audit_v1", "gaming_detected": bool(signals), "signals": signals, "evidence": {"generic_motivation_count": repeated_generic, "shot_count": len(shots), "unique_camera_count": camera_unique, "emotion_values": emotions}, "professional_qa_required": bool(signals)}


def run_professional_qa(*, strategy: dict[str, Any], shot_plan: dict[str, Any], strategy_contract: dict[str, Any] | None = None) -> dict[str, Any]:
    strategy_obj, plan = _dict(strategy), _dict(shot_plan)
    shots = [row for row in _list(plan.get("shots")) if isinstance(row, dict)]
    phases, emotion_targets, reveal_targets, performance_targets = _strategy_maps(strategy_obj)
    findings: list[dict[str, Any]] = []
    traces = []
    for index, shot in enumerate(shots, 1):
        sid = _text(shot.get("plan_shot_id") or f"S{index:02d}")
        beat = _text(shot.get("beat_id"))
        phase = _text(shot.get("strategy_phase_id"))
        missing = [field for field in REQUIRED_TRACE_FIELDS if not _text(shot.get(field))]
        if missing:
            findings.extend(_finding("TRACE_FIELD_MISSING", dimension="strategy_trace", evidence=f"{sid} lacks required trace fields: {', '.join(missing)}", shot_ids=[sid], strategy_reference=phase or beat, repairability="TAIL_REPAIR", suggested_action="fill trace metadata from approved strategy; do not alter facts" ) for _ in [0])
        if beat not in phases:
            findings.append(_finding("STRATEGY_PHASE_UNCOVERED", dimension="strategy_coverage", evidence=f"{sid} beat {beat} has no strategy phase", shot_ids=[sid], strategy_reference=beat, repairability="SCENE_REPAIR"))
        motivation = _text(shot.get("why_this_shot"))
        camera_motivation = _text(shot.get("camera_motivation"))
        generic_values = [value.lower() for value in (motivation, camera_motivation) if value]
        if any(value in GENERIC_MOTIVATION or value.startswith(("show the beat", "show the event", "help audience follow", "make action visible")) for value in generic_values):
            findings.append(_finding("GENERIC_SHOT_MOTIVATION", dimension="shot_motivation_specificity", evidence=f"{sid} motivation is a reusable template: {motivation or camera_motivation}", shot_ids=[sid], strategy_reference=phase or beat, repairability="TAIL_REPAIR"))
        traces.append({"shot_id": sid, "beat_id": beat, "phase_id": phase})
    if strategy_contract:
        trace_result = validate_strategy_traceability(contract=strategy_contract, strategy=None, draft_shot_plan=plan)
        if not trace_result["valid"]:
            for error in trace_result["errors"]:
                findings.append(_finding("TRACE_FIELD_MISSING", dimension="strategy_trace", evidence=json_evidence(error), repairability="TAIL_REPAIR"))
    signatures = [tuple(_text(_dict(row.get("camera")).get(key)) for key in ("shot_size", "angle", "movement", "speed", "camera_side")) for row in shots]
    for index in range(1, len(signatures)):
        if signatures[index] != signatures[index - 1] and not _text(shots[index].get("camera_motivation") or shots[index].get("why_this_shot")):
            findings.append(_finding("UNMOTIVATED_CAMERA_CHANGE", dimension="visual_grammar", evidence=f"camera changes from {signatures[index-1]} to {signatures[index]} without a stated visual reason", shot_ids=[_text(shots[index].get("plan_shot_id"))], strategy_reference=_text(shots[index].get("strategy_phase_id")), repairability="SCENE_REPAIR"))
        elif signatures[index] != signatures[index - 1] and _text(shots[index].get("camera_motivation")) in GENERIC_MOTIVATION:
            findings.append(_finding("UNMOTIVATED_VARIATION", dimension="visual_grammar", evidence=f"{_text(shots[index].get('plan_shot_id'))} changes camera with a generic reason", shot_ids=[_text(shots[index].get("plan_shot_id"))], strategy_reference=_text(shots[index].get("strategy_phase_id")), repairability="SCENE_REPAIR"))
    if len(signatures) >= 3 and len(set(signatures)) == len(signatures) and all(not _text(row.get("camera_motivation")) for row in shots):
        findings.append(_finding("RANDOM_VARIATION", dimension="camera_progression", evidence="every shot uses a unique camera signature without a repeated visual grammar rule", shot_ids=[_text(s.get("plan_shot_id")) for s in shots], repairability="SCENE_REDESIGN"))
    movements = [_text(_dict(row.get("camera")).get("movement")) for row in shots]
    if len(movements) >= 3 and sum(value not in {"", "static", "hold"} for value in movements) / len(movements) > 0.75:
        findings.append(_finding("CAMERA_MOVEMENT_OVERUSE", dimension="camera_progression", evidence="camera movement appears in more than 75% of shots", shot_ids=[_text(s.get("plan_shot_id")) for s in shots], repairability="SCENE_REPAIR"))
    sizes = [_text(_dict(row.get("camera")).get("shot_size")) for row in shots]
    if len(sizes) >= 4 and all(sizes[i] != sizes[i - 1] for i in range(1, len(sizes))) and all(not _text(row.get("camera_motivation")) for row in shots):
        findings.append(_finding("SHOT_SIZE_NOISE", dimension="visual_grammar", evidence="shot size alternates on every cut without a phase rule", shot_ids=[_text(s.get("plan_shot_id")) for s in shots], repairability="SCENE_REDESIGN"))
    grammar_by_phase = {_text(row.get("phase_id")): _text(row.get("grammar")) for row in _list(_dict(strategy_obj.get("visual_grammar")).get("phases")) if isinstance(row, dict)}
    for row in shots:
        phase = _text(row.get("strategy_phase_id")); movement = _text(_dict(row.get("camera")).get("movement")).lower()
        if "客观" in grammar_by_phase.get(phase, "") and movement not in {"", "static", "hold"}:
            findings.append(_finding("VISUAL_GRAMMAR_BREAK", dimension="visual_grammar", evidence=f"{_text(row.get('plan_shot_id'))} moves camera during an objective-relationship phase", shot_ids=[_text(row.get("plan_shot_id"))], strategy_reference=phase, repairability="SCENE_REPAIR"))
    intensities = [float(_dict(row.get("emotion")).get("intensity")) for row in shots if isinstance(_dict(row.get("emotion")).get("intensity"), (int, float))]
    if len(intensities) >= 4:
        deltas = [intensities[i] - intensities[i - 1] for i in range(1, len(intensities))]
        signs = [1 if value > 0 else -1 if value < 0 else 0 for value in deltas]
        sign_changes = sum(1 for left, right in zip(signs, signs[1:]) if left and right and left != right)
        if sign_changes >= 2:
            findings.append(_finding("EMOTION_ZIGZAG", dimension="emotion_arc_execution", evidence=f"intensity changes reverse repeatedly: {intensities}", shot_ids=[_text(s.get("plan_shot_id")) for s in shots], strategy_reference="emotional_arc", repairability="SCENE_REPAIR"))
    for row in shots:
        beat, sid = _text(row.get("beat_id")), _text(row.get("plan_shot_id"))
        actual = _dict(row.get("information_strategy")); actual_reveals = [_text(v) for v in _list(actual.get("reveals") or actual.get("reveal")) if _text(v)]
        expected = reveal_targets.get(beat, [])
        if expected and not set(expected).intersection(actual_reveals):
            findings.append(_finding("INFORMATION_ARC_GAP", dimension="audience_information_arc", evidence=f"{sid} does not execute the reveal planned for beat {beat}: {expected}", shot_ids=[sid], strategy_reference=beat, repairability="SCENE_REPAIR"))
        unknown_reveals = [value for value in actual_reveals if value not in {item for values in reveal_targets.values() for item in values}]
        if unknown_reveals:
            findings.append(_finding("REVEAL_TOO_EARLY", dimension="audience_information_arc", evidence=f"{sid} reveals information not present in strategy/source: {unknown_reveals}", shot_ids=[sid], strategy_reference=beat, repairability="SCENE_REDESIGN"))
    beat_order = {beat: index for index, beat in enumerate(phases)}
    for index, row in enumerate(shots):
        beat, sid = _text(row.get("beat_id")), _text(row.get("plan_shot_id"))
        expected = reveal_targets.get(beat, [])
        if expected and not _list(_dict(row.get("information_strategy")).get("reveals") or _dict(row.get("information_strategy")).get("reveal")):
            later = any(set(expected).intersection(_list(_dict(later_row.get("information_strategy")).get("reveals") or _dict(later_row.get("information_strategy")).get("reveal"))) for later_row in shots[index + 1:])
            if later:
                findings.append(_finding("REVEAL_TOO_LATE", dimension="audience_information_arc", evidence=f"reveal planned at beat {beat} is postponed to a later shot", shot_ids=[sid], strategy_reference=beat, repairability="SCENE_REPAIR"))
    expected_pairs = {(character, beat) for character, beats in performance_targets.items() for beat in beats}
    actual_pairs = set()
    for row in shots:
        for perf in _list(row.get("performance_direction")):
            if isinstance(perf, dict) and _text(perf.get("character_id")) and _text(row.get("beat_id")):
                actual_pairs.add((_text(perf.get("character_id")), _text(row.get("beat_id"))))
    missing_pairs = sorted(expected_pairs - actual_pairs)
    if missing_pairs:
        findings.append(_finding("PERFORMANCE_ARC_GAP", dimension="performance_arc_execution", evidence=f"missing character/beat performance entries: {missing_pairs}", shot_ids=[_text(s.get("plan_shot_id")) for s in shots], strategy_reference="performance_arc", repairability="SCENE_REPAIR"))
    has_power_shift = any(_text(row.get("shift")).lower() not in {"", "maintain", "维持既有控制关系"} for row in _list(strategy_obj.get("power_arc")) if isinstance(row, dict))
    if has_power_shift and not any(_text(row.get("power_state")) or _text(_dict(row.get("composition")).get("frame_relationship")) in {"power contrast", "isolation", "dominance"} for row in shots):
        findings.append(_finding("POWER_SHIFT_NOT_VISUALIZED", dimension="power_arc_execution", evidence="strategy declares a power shift but no shot carries a visual power state or contrast", shot_ids=[_text(s.get("plan_shot_id")) for s in shots], strategy_reference="power_arc", repairability="SCENE_REPAIR"))
    if _list(_dict(strategy_obj.get("edit_arc")).get("hold_points")) and not any(_text(row.get("edit_function")).lower() == "hold" for row in shots):
        findings.append(_finding("EDIT_ARC_MISMATCH", dimension="edit_arc_execution", evidence="strategy requires hold points but no shot executes a hold function", shot_ids=[_text(s.get("plan_shot_id")) for s in shots], strategy_reference="edit_arc", repairability="SCENE_REPAIR"))
    if shots and len(shots) >= 4 and all(_text(row.get("edit_function")) == "cut" for row in shots):
        findings.append(_finding("OVER_CUTTING", dimension="edit_arc_execution", evidence="every shot is marked as an undifferentiated cut with no hold/reaction function", shot_ids=[_text(s.get("plan_shot_id")) for s in shots], strategy_reference="edit_arc", repairability="SCENE_REDESIGN"))
    required_functions = {_text(value).lower() for value in _list(_dict(strategy_obj.get("shot_architecture_guidance")).get("required_functions"))}
    if "reaction" in required_functions and not any(_text(row.get("purpose")).lower() == "reaction" or _text(row.get("dramatic_function")).lower() == "reaction" for row in shots):
        findings.append(_finding("REACTION_MISSING", dimension="performance_arc_execution", evidence="strategy/shot metadata references reaction but no reaction shot is present", shot_ids=[_text(s.get("plan_shot_id")) for s in shots], strategy_reference="shot_architecture_guidance", repairability="SCENE_REDESIGN"))
    for left, right in zip(shots, shots[1:]):
        if _text(left.get("beat_id")) == _text(right.get("beat_id")) and _text(left.get("purpose")) == _text(right.get("purpose")) and tuple(_text(_dict(left.get("camera")).get(k)) for k in ("shot_size", "angle", "movement")) == tuple(_text(_dict(right.get("camera")).get(k)) for k in ("shot_size", "angle", "movement")):
            findings.append(_finding("REDUNDANT_COVERAGE", dimension="visual_grammar", evidence=f"adjacent shots {_text(left.get('plan_shot_id'))}/{_text(right.get('plan_shot_id'))} cover the same beat with identical intent", shot_ids=[_text(left.get("plan_shot_id")), _text(right.get("plan_shot_id"))], strategy_reference=_text(right.get("strategy_phase_id")), repairability="SCENE_REPAIR"))
    counts = Counter(item["issue_code"] for item in findings)
    redesign = any(item["repairability"] == "SCENE_REDESIGN" for item in findings)
    human = any(item["repairability"] == "HUMAN_REVIEW" for item in findings)
    status = "PROFESSIONAL_QA_HUMAN_REVIEW" if human else "PROFESSIONAL_QA_REDESIGN_REQUIRED" if redesign else "PROFESSIONAL_QA_REPAIRABLE" if findings else "PROFESSIONAL_QA_PASS"
    protocol_status = "PROTOCOL_INVALID" if findings and any(item["issue_code"] in {"TRACE_FIELD_MISSING", "STRATEGY_PHASE_UNCOVERED"} for item in findings) else "PROTOCOL_VALID"
    directing_content_status = "DIRECTING_INCONCLUSIVE" if not strategy_obj else "DIRECTING_USABLE" if findings else "DIRECTING_STRONG"
    return {"schema_version": QA_SCHEMA_VERSION, "status": status, "layer": "STRATEGY_CONSISTENCY_QA", "findings": findings, "issue_counts": dict(counts), "protocol_status": protocol_status, "directing_content_status": directing_content_status, "coverage": {"strategy_phase_coverage": round(sum(1 for row in traces if row["beat_id"] in phases) / len(traces), 4) if traces else 0.0, "audience_knowledge_coverage": round(sum(1 for row in shots if row.get("information_strategy")) / len(shots), 4) if shots else 0.0, "emotional_arc_coverage": round(sum(1 for row in shots if _dict(row.get("emotion"))) / len(shots), 4) if shots else 0.0, "performance_arc_coverage": round(len(actual_pairs & expected_pairs) / len(expected_pairs), 4) if expected_pairs else 1.0}, "scorer_gaming": detect_scorer_gaming(strategy=strategy_obj, shot_plan=plan)}


def json_evidence(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


__all__ = ["QA_SCHEMA_VERSION", "QA_STATUSES", "ISSUE_CODES", "run_professional_qa", "detect_scorer_gaming"]
