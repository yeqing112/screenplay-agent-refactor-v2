"""Provider-independent diagnostics for real V3 SceneDirectingStrategy output.

These diagnostics are deliberately status/evidence based.  They are not a
human preference score and are never used as a substitute for a creative
director review.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

from core.director_scene_strategy_ir_compiler import creative_core_fingerprint


GENERIC_PHRASES = (
    "增强情绪", "营造紧张感", "适当使用特写", "使用不同景别", "根据剧情调整镜头",
    "加强节奏", "展现情绪", "突出氛围", "增强戏剧性", "show the beat",
    "show the event", "help audience follow", "make action visible",
)
FORBIDDEN_SHOT_KEYS = {"shots", "plan_shot_id", "shot_ids", "patches", "duration_ladder"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    return _text(value)


def _finding(dimension: str, status: str, evidence: str, *, issue_code: str = "", fields: Iterable[str] = ()) -> dict[str, Any]:
    return {
        "dimension": dimension,
        "status": status,
        "evidence": evidence,
        "issue_code": issue_code,
        "fields": list(fields),
    }


def _refs(row: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for key in ("beat_id", "phase_id", "character_id", "trigger", "source_fact_refs"):
        value = row.get(key)
        if isinstance(value, list):
            out.update(_text(item) for item in value if _text(item))
        elif _text(value):
            out.add(_text(value))
    out.update(_text(item) for item in _list(row.get("beat_ids")) if _text(item))
    return out


def detect_generic_strategy(strategy: dict[str, Any]) -> list[dict[str, Any]]:
    """Find generic prose only when it lacks concrete evidence bindings."""
    findings: list[dict[str, Any]] = []
    for field in ("dramatic_objective", "scene_question", "visual_grammar", "camera_principles", "edit_arc", "must_avoid", "creative_risks", "shot_architecture_guidance"):
        value = strategy.get(field)
        text = _flatten_text(value)
        if not text:
            continue
        hits = [phrase for phrase in GENERIC_PHRASES if phrase.lower() in text.lower()]
        refs = set()
        for row in _list(value):
            if isinstance(row, dict):
                refs |= _refs(row)
        # A generic phrase is acceptable when it is explicitly bound to a
        # supplied phase/beat/character.  Unbound boilerplate is a warning.
        if hits and not refs and not re.search(r"\b(?:B\d+|P\d+|C\d+|CHAR[_-]\w+)\b", text):
            findings.append(_finding(field, "WEAK", f"unbound generic language: {', '.join(hits[:3])}", issue_code="GENERIC_DIRECTOR_STRATEGY", fields=[field]))
    return findings


def _arc_status(strategy: dict[str, Any], field: str, required_keys: tuple[str, ...], *, issue_code: str) -> dict[str, Any]:
    rows = [row for row in _list(strategy.get(field)) if isinstance(row, dict)]
    missing: list[str] = []
    for index, row in enumerate(rows):
        for key in required_keys:
            if not row.get(key):
                missing.append(f"{field}[{index}].{key}")
    if not rows:
        return _finding(field, "FAIL", "no ordered arc entries", issue_code=issue_code, fields=[field])
    if missing:
        return _finding(field, "WEAK", "missing concrete arc evidence: " + ", ".join(missing[:8]), issue_code=issue_code, fields=[field])
    return _finding(field, "PASS", f"{len(rows)} ordered entries include required triggers/transitions", fields=[field])


def diagnose_scene_strategy(*, strategy: dict[str, Any], source_evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return dimensions, evidence-backed issues and a non-numeric outcome."""
    source_evidence = _dict(source_evidence)
    findings: list[dict[str, Any]] = []
    findings.extend(detect_generic_strategy(strategy))

    objective = _text(strategy.get("dramatic_objective"))
    question = _text(strategy.get("scene_question"))
    findings.append(_finding("dramatic_objective", "PASS" if len(objective) >= 20 else "WEAK", f"objective length={len(objective)}", issue_code="BEAT_UNDERSTANDING_WEAK" if len(objective) < 20 else "", fields=["dramatic_objective"]))
    findings.append(_finding("scene_question", "PASS" if len(question) >= 8 else "WEAK", f"question length={len(question)}", issue_code="AUDIENCE_ARC_WEAK" if len(question) < 8 else "", fields=["scene_question"]))

    knowledge = _arc_status(strategy, "audience_knowledge_arc", ("phase_id", "does_not_know_yet", "suspects"), issue_code="AUDIENCE_ARC_WEAK")
    emotion = _arc_status(strategy, "emotional_arc", ("trigger", "emotion_state", "transition_reason"), issue_code="EMOTION_ARC_WEAK")
    findings.extend([knowledge, emotion])

    performance_rows = [row for row in _list(strategy.get("performance_arc")) if isinstance(row, dict)]
    performance_ok = all(row.get("objective") and len(_list(row.get("tactic_progression"))) >= 2 and len(_list(row.get("visible_behavior_progression"))) >= 2 and row.get("turning_point") for row in performance_rows)
    findings.append(_finding("performance_arc", "PASS" if performance_rows and performance_ok else "WEAK", f"characters={len(performance_rows)}; each has objective/tactic/visible progression/turning point={performance_ok}", issue_code="PERFORMANCE_ARC_WEAK" if not (performance_rows and performance_ok) else "", fields=["performance_arc"]))

    edit = _dict(strategy.get("edit_arc"))
    edit_keys = ("tempo_progression", "hold_points", "cut_motivations", "reveal_timing")
    edit_ok = all(edit.get(key) for key in edit_keys)
    findings.append(_finding("edit_arc", "PASS" if edit_ok else "WEAK", "edit arc includes tempo, holds, cut motivations and reveal timing" if edit_ok else "edit arc is missing director logic", issue_code="EDIT_STRATEGY_WEAK" if not edit_ok else "", fields=["edit_arc"]))

    grammar = _dict(strategy.get("visual_grammar"))
    grammar_ok = bool(_text(grammar.get("overall")) and _list(grammar.get("phases")))
    findings.append(_finding("visual_grammar", "PASS" if grammar_ok else "WEAK", f"overall principle and phase rules present={grammar_ok}", issue_code="VISUAL_GRAMMAR_WEAK" if not grammar_ok else "", fields=["visual_grammar"]))

    camera = _list(strategy.get("camera_principles"))
    camera_text = _flatten_text(camera).lower()
    camera_ok = bool(camera) and any(marker in camera_text for marker in ("只有", "当", "if", "when", "认知", "权力", "节拍", "beat", "phase"))
    findings.append(_finding("camera_principles", "PASS" if camera_ok else "WEAK", "camera movement is bound to a change/condition" if camera_ok else "camera principles do not state a motivation condition", issue_code="CAMERA_PRINCIPLE_GENERIC" if not camera_ok else "", fields=["camera_principles"]))

    info = _list(strategy.get("information_reveal_plan"))
    info_ok = bool(info) and all(isinstance(row, dict) and ("reveal" in row or "withhold" in row) for row in info)
    findings.append(_finding("information_reveal_plan", "PASS" if info_ok else "WEAK", f"ordered reveal/withhold entries={len(info)}", issue_code="INFORMATION_STRATEGY_WEAK" if not info_ok else "", fields=["information_reveal_plan"]))

    avoid_text = _flatten_text(strategy.get("must_avoid"))
    risk_text = _flatten_text(strategy.get("creative_risks"))
    findings.append(_finding("must_avoid", "PASS" if avoid_text and len(_list(strategy.get("must_avoid"))) >= 2 else "WEAK", "scene-specific anti-patterns recorded" if avoid_text else "must_avoid is empty", issue_code="GENERIC_DIRECTOR_STRATEGY" if not avoid_text else "", fields=["must_avoid"]))
    findings.append(_finding("creative_risks", "PASS" if risk_text else "WEAK", "creative risk recorded" if risk_text else "creative_risks is empty", issue_code="MODEL_DIRECTING_WEAKNESS" if not risk_text else "", fields=["creative_risks"]))

    leakage = sorted(FORBIDDEN_SHOT_KEYS & set(strategy))
    if leakage:
        findings.append(_finding("protocol", "FAIL", "forbidden ShotPlan keys: " + ", ".join(leakage), issue_code="STRATEGY_LAYER_LEAKAGE", fields=leakage))

    severe = {"FAIL"}
    weak_count = sum(1 for item in findings if item["status"] == "WEAK")
    has_severe = any(item["status"] in severe or item.get("issue_code") in {"STRATEGY_LAYER_LEAKAGE", "DIRECTOR_FACT_INVENTION", "REVEAL_CHRONOLOGY_INVALID"} for item in findings)
    outcome = "STRATEGY_INVALID" if has_severe else "STRATEGY_WEAK" if weak_count >= 4 else "STRATEGY_USABLE" if weak_count else "STRATEGY_STRONG"
    # Keep the legacy outcome for callers, but expose independent protocol and
    # directing statuses so a malformed provider shape cannot erase creative
    # evidence.
    protocol_status = "PROTOCOL_INVALID" if has_severe else "PROTOCOL_VALID"
    directing_content_status = "DIRECTING_WEAK" if weak_count >= 4 else "DIRECTING_USABLE" if weak_count else "DIRECTING_STRONG"
    return {
        "diagnostic_schema_version": "director-quality-v3-phase1-strategy-quality-v1",
        "outcome": outcome,
        "findings": findings,
        "weak_dimension_count": weak_count,
        "source_evidence_available": sorted(source_evidence),
        "protocol_status": protocol_status,
        "directing_content_status": directing_content_status,
    }


def compare_strategies(strategies: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministically detect exact or suspicious cross-scene template reuse."""
    rows: list[dict[str, Any]] = []
    for index, left in enumerate(strategies):
        for right in strategies[index + 1:]:
            fields = ("dramatic_objective", "scene_question", "visual_grammar", "camera_principles", "edit_arc", "must_avoid", "strategy_summary")
            exact = [field for field in fields if left.get(field) == right.get(field)]
            left_tokens = set(_flatten_text({field: left.get(field) for field in fields}).lower().split())
            right_tokens = set(_flatten_text({field: right.get(field) for field in fields}).lower().split())
            similarity = round(len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens)), 4)
            left_core = creative_core_fingerprint(left)
            right_core = creative_core_fingerprint(right)
            # Provider-supplied fingerprints are deliberately ignored.  A hard
            # failure requires identical creative core plus concrete evidence,
            # not a reused or malformed computed field.
            true_reuse = left_core == right_core and len(exact) >= 5
            rows.append({"scene_a": _text(left.get("scene_id")), "scene_b": _text(right.get("scene_id")), "exact_core_fields": exact, "jaccard_token_similarity": similarity, "creative_core_fingerprint_a": left_core, "creative_core_fingerprint_b": right_core, "provider_fingerprint_ignored": True, "status": "HARD_FAILURE" if true_reuse else "WARNING" if similarity >= 0.75 else "PASS", "issue_code": "CROSS_SCENE_TEMPLATE_LEAKAGE" if true_reuse else ""})
    return {"schema_version": "director-quality-v3-phase1-1-distinctiveness-v1", "comparisons": rows, "hard_failure": any(row["status"] == "HARD_FAILURE" for row in rows), "policy": "program-owned creative_core_fingerprint; provider fingerprints ignored"}


def diagnose_protocol(*, strategy: dict[str, Any], contract: dict[str, Any] | None = None) -> dict[str, Any]:
    """Protocol-only diagnostics independent of directing quality."""
    errors: list[dict[str, Any]] = []
    if not isinstance(strategy, dict):
        errors.append({"code": "STRATEGY_NOT_OBJECT"})
    else:
        forbidden = sorted(FORBIDDEN_SHOT_KEYS & set(strategy))
        if forbidden:
            errors.append({"code": "STRATEGY_LAYER_LEAKAGE", "fields": forbidden})
        if strategy.get("strategy_fingerprint") and strategy.get("provider_fingerprint"):
            errors.append({"code": "COMPUTED_FIELD_PROVIDER_ERROR"})
    return {"protocol_status": "PROTOCOL_INVALID" if errors else "PROTOCOL_VALID", "errors": errors}


def diagnose_directing_content(*, strategy: dict[str, Any], source_evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """Content-only view; protocol errors do not force WEAK."""
    if isinstance(strategy, dict) and _list(strategy.get("scene_phases")):
        phases = [row for row in _list(strategy.get("scene_phases")) if isinstance(row, dict)]
        issues = []
        if len(phases) < 2:
            issues.append("PHASE_PROGRESS_NOT_ESTABLISHED")
        if not _text(strategy.get("dramatic_objective")):
            issues.append("OBJECTIVE_MISSING")
        if not _text(strategy.get("scene_question")):
            issues.append("SCENE_QUESTION_MISSING")
        if any(not _text(_dict(row.get("emotion")).get("state")) for row in phases):
            issues.append("EMOTION_PROGRESSION_INCONCLUSIVE")
        if any(not _text(_dict(row.get("visual")).get("visual_grammar")) for row in phases):
            issues.append("VISUAL_PROGRESSION_INCONCLUSIVE")
        status = "DIRECTING_INCONCLUSIVE" if not phases else "DIRECTING_WEAK" if len(issues) >= 3 else "DIRECTING_USABLE"
        return {"directing_content_status": status, "findings": [{"issue_code": code} for code in issues], "evidence": ["scene_phases"]}
    result = diagnose_scene_strategy(strategy=strategy, source_evidence=source_evidence)
    return {"directing_content_status": result["directing_content_status"], "findings": result["findings"], "evidence": result["source_evidence_available"]}


def compare_strategy_to_baseline(*, strategy: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Read-only insight about strategy implications versus an old plan."""
    shots = [row for row in _list(_dict(baseline).get("shots")) if isinstance(row, dict)]
    functions = set(_text(item) for item in _list(_dict(strategy.get("shot_architecture_guidance")).get("required_functions")) if _text(item))
    baseline_text = json.dumps(shots, ensure_ascii=False)
    gaps: list[str] = []
    if "reaction" in functions and "reaction" not in baseline_text.lower():
        gaps.append("REACTION_NEEDED")
    if _list(strategy.get("information_reveal_plan")) and "information_strategy" not in baseline_text:
        gaps.append("INFORMATION_STRATEGY_UNSUPPORTED")
    if _list(strategy.get("performance_arc")) and "performance_direction" not in baseline_text:
        gaps.append("PERFORMANCE_ARC_UNSUPPORTED")
    return {"schema_version": "director-quality-v3-phase1-strategy-vs-baseline-v1", "baseline_shot_count": len(shots), "strategy_implied_gaps": gaps, "baseline_read_only": True}


__all__ = ["diagnose_scene_strategy", "diagnose_protocol", "diagnose_directing_content", "compare_strategies", "compare_strategy_to_baseline", "detect_generic_strategy"]
