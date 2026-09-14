"""Provider-neutral Director Quality V2.4 scene pipeline.

This module is the deterministic integration seam for the V2.4 value and
tail-repair work.  It deliberately accepts provider callables as arguments;
the default path never calls an LLM.  A real pilot can inject a bounded
callable after its explicit authorization boundary, while replay/tests can
use a local fixture or no callable at all.

The pipeline keeps the stage order auditable:

contract local repair -> opportunity detection/eligibility -> value
intervention trace -> tail detection/ranking -> targeted tail repair.

It does not persist production, storyboard, media, or object-storage state.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Iterable

from core.director_contract_local_repair import repair_contract_failures
from core.director_creative_contract import build_director_creative_contract
from core.director_creative_value import (
    build_creative_value_score,
    evaluate_useful_creative_acceptance_v3,
)
from core.director_intervention_trace import build_intervention_trace
from core.director_opportunity_detector import detect_creative_opportunities
from core.director_opportunity_eligibility import apply_opportunity_eligibility
from core.director_opportunity_planner import normalize_planner_decisions
from core.director_opportunity_model import build_opportunity_outcome, normalize_opportunity
from core.director_overdirecting import detect_over_directing
from core.director_quality_validator import score_director_quality
from core.director_tail_repair import build_tail_repair_plan
from core.director_tail_repair_executor import execute_tail_repair
from core.director_tail_root_cause import rank_tail_root_causes_v2
from core.director_patch_compiler import compile_creative_patches
from core.director_patch_validator import validate_compiled_patch_result
from core.local_repair import fingerprint


V24_PIPELINE_SCHEMA_VERSION = "director-quality-v2-4-pipeline-v1"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _scene_parts(scene: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    metadata = _dict(scene.get("scene")) or scene
    evidence = _dict(scene.get("evidence"))
    treatment = _dict(scene.get("treatment")) or _dict(evidence.get("treatment"))
    blocking = _dict(scene.get("blocking")) or _dict(evidence.get("blocking"))
    contract = _dict(scene.get("contract")) or _dict(evidence.get("contract"))
    baseline = _dict(scene.get("baseline")) or _dict(evidence.get("structural_shot_plan"))
    if not contract and baseline:
        contract = build_director_creative_contract(structural_shot_plan=baseline, treatment=treatment)
    return metadata, treatment, blocking, {"contract": contract, "baseline": baseline, "evidence": evidence}


def _patch_ids(document: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for index, patch in enumerate(_list(document.get("patches"))):
        if not isinstance(patch, dict):
            continue
        result.append(_text(patch.get("patch_id")) or f"patch:{_text(patch.get('plan_shot_id')) or index + 1}")
    return result


def _dimensions(before: dict[str, Any], after: dict[str, Any]) -> dict[str, float]:
    before_dims = _dict(before.get("dimensions"))
    after_dims = _dict(after.get("dimensions"))
    keys = set(before_dims) | set(after_dims)
    return {
        str(key): round(float(after_dims.get(key, 0) or 0) - float(before_dims.get(key, 0) or 0), 4)
        for key in sorted(keys)
        if isinstance(before_dims.get(key, after_dims.get(key)), (int, float))
        and not isinstance(before_dims.get(key, after_dims.get(key)), bool)
    }


def _patch_dimension_map(document: dict[str, Any]) -> dict[str, set[str]]:
    mapping = {
        "camera": {"camera_language", "shot_motivation"},
        "composition": {"spatial_clarity", "shot_motivation", "visual_storytelling"},
        "why_this_shot": {"shot_motivation"},
        "dramatic_function": {"shot_motivation"},
        "emotion": {"emotion_arc"},
        "performance_direction": {"performance_direction"},
        "edit": {"edit_strategy"},
        "information_strategy": {"information_strategy"},
        "visual_emphasis": {"visual_storytelling"},
    }
    result: dict[str, set[str]] = {}
    for patch in _list(document.get("patches")):
        if not isinstance(patch, dict):
            continue
        shot_id = _text(patch.get("plan_shot_id"))
        if not shot_id:
            continue
        dimensions = result.setdefault(shot_id, set())
        for raw_path in _dict(patch.get("changes")):
            parts = [part for part in str(raw_path).replace("/", ".").split(".") if part]
            if parts and parts[0] == "shots":
                parts = parts[2:]
            if parts:
                dimensions.update(mapping.get(parts[0], set()))
    return result


def _interventions(
    *,
    opportunities: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    baseline: dict[str, Any],
    first_document: dict[str, Any],
    final_document: dict[str, Any],
    first_score: dict[str, Any],
    final_score: dict[str, Any],
    final_validation: dict[str, Any],
) -> list[dict[str, Any]]:
    decision_by_id = {_text(item.get("opportunity_id")): item for item in decisions}
    first_map = _patch_dimension_map(first_document)
    final_map = _patch_dimension_map(final_document)
    rejected = bool(_list(final_validation.get("errors"))) or not bool(final_validation.get("contract_pass"))
    delta = _dimensions(first_score, final_score)
    rows: list[dict[str, Any]] = []
    for opportunity in opportunities:
        oid = _text(opportunity.get("opportunity_id"))
        if not opportunity.get("eligible"):
            continue
        decision = decision_by_id.get(oid, {})
        if _text(decision.get("decision")).upper() != "ACT":
            continue
        beat_id = _text(opportunity.get("beat_id"))
        shot_id = ""
        for shot in _list(baseline.get("shots")):
            if isinstance(shot, dict) and _text(shot.get("beat_id")) == beat_id:
                shot_id = _text(shot.get("plan_shot_id")); break
        for patch in _list(final_document.get("patches")):
            if isinstance(patch, dict) and _text(patch.get("beat_id")) == beat_id:
                shot_id = _text(patch.get("plan_shot_id")); break
        recommended = {_text(item) for item in _list(opportunity.get("recommended_directing_dimensions"))}
        patch_dims = final_map.get(shot_id, set())
        first_dims = first_map.get(shot_id, set())
        addressed = bool(patch_dims & recommended)
        changed = bool(patch_dims - first_dims) or addressed
        rows.append({
            "opportunity_id": oid,
            "patch_valid": bool(changed and not rejected),
            "applied": bool(changed and not rejected),
            "fact_contract_pass": not rejected,
            "new_blocker": False,
            "quality_delta": float(final_score.get("director_quality_score", 0) or 0) - float(first_score.get("director_quality_score", 0) or 0) if changed and not rejected else 0.0,
            "dimension_deltas": {key: value for key, value in delta.items() if key.lower() in recommended or key in recommended},
        })
    return rows


def run_v24_scene_pipeline(
    scene: dict[str, Any],
    *,
    patch_document: dict[str, Any] | None = None,
    planner_decisions: Iterable[dict[str, Any]] | dict[str, Any] | None = None,
    contract_repair_callable: Callable[[dict[str, Any]], Any] | None = None,
    tail_repair_callable: Callable[[dict[str, Any]], Any] | None = None,
    session: Any | None = None,
    model: str = "",
) -> dict[str, Any]:
    """Run one replayable V2.4 scene without provider side effects."""

    metadata, treatment, blocking, parts = _scene_parts(scene)
    baseline = copy.deepcopy(parts["baseline"])
    contract = copy.deepcopy(parts["contract"])
    if not baseline or not contract:
        raise ValueError("V2.4 scene requires structural_shot_plan and contract evidence")
    scene_id = _text(metadata.get("scene_id") or scene.get("scene_id"))
    first_document = copy.deepcopy(patch_document or {"schema_version": "director_creative_patch_v1", "patches": [], "auxiliary_shot_proposals": []})
    repair = repair_contract_failures(
        structural_shot_plan=baseline,
        patch_document=first_document,
        contract=contract,
        repair_callable=contract_repair_callable,
        treatment=treatment,
        blocking=blocking,
        session=session,
        repair_context={"scene_id": scene_id},
        model=model,
    )
    final_document = _dict(repair.get("accepted_patch_document"))
    candidate = copy.deepcopy(repair.get("candidate") or baseline)
    first_score = score_director_quality(baseline, treatment=treatment, blocking=blocking)
    final_score = score_director_quality(candidate, treatment=treatment, blocking=blocking)
    first_compilation = compile_creative_patches(baseline, first_document, contract, allow_partial=True)
    first_validation = validate_compiled_patch_result(first_compilation, baseline, contract, treatment=treatment, blocking=blocking)
    final_compilation = compile_creative_patches(baseline, final_document, contract, allow_partial=True)
    final_validation = validate_compiled_patch_result(final_compilation, baseline, contract, treatment=treatment, blocking=blocking)
    opportunities_detected = detect_creative_opportunities(
        script_scene=_dict(parts["evidence"].get("scene_canonical")) or metadata,
        treatment=treatment,
        blocking=blocking,
        structural_shot_plan=baseline,
    )
    eligibility = apply_opportunity_eligibility(
        opportunities_detected,
        script_scene=_dict(parts["evidence"].get("scene_canonical")) or metadata,
        treatment=treatment,
        blocking=blocking,
        structural_shot_plan=baseline,
    )
    opportunities = eligibility["opportunities"]
    decisions_input = planner_decisions if planner_decisions is not None else {"schema_version": "director_opportunity_planner_decision_v1", "decisions": []}
    try:
        decisions = normalize_planner_decisions(decisions_input, opportunities)
        decision_errors: list[dict[str, Any]] = []
    except Exception as exc:
        decisions = []
        decision_errors = [{"code": getattr(exc, "code", "OPPORTUNITY_DECISION_INVALID"), "message": str(exc)}]
    interventions = _interventions(
        opportunities=opportunities,
        decisions=decisions,
        baseline=baseline,
        first_document=first_document,
        final_document=final_document,
        first_score=first_score,
        final_score=final_score,
        final_validation=final_validation,
    )
    if decision_errors:
        # Missing/invalid planner output is a fail-closed pipeline state.  Do
        # not turn it into a valid skip (which would improve address-rate
        # metrics); retain an explicit missed outcome for each eligible
        # opportunity so the caller can see the exact blocking condition.
        normalized_opportunities = [normalize_opportunity(item) for item in opportunities]
        outcomes = [
            build_opportunity_outcome(
                opportunity=item,
                planner_decision="ACT" if item["eligible"] else "NOT_APPLICABLE",
                decision_reason="未收到可验证的完整机会决策",
                final_status="MISSED_OPPORTUNITY" if item["eligible"] else "SKIPPED_VALID_REASON",
            )
            for item in normalized_opportunities
        ]
        eligible_outcomes = [item for item in outcomes if item["eligible"]]
        value = {
            "schema_version": "director_useful_creative_acceptance_v3",
            "eligible_opportunity_count": len(eligible_outcomes),
            "useful_accepted_count": 0,
            "accepted_count": 0,
            "accepted_no_measurable_value_count": 0,
            "rejected_contract_count": 0,
            "rejected_quality_count": 0,
            "fallback_baseline_count": 0,
            "valid_skip_count": 0,
            "missed_opportunity_count": len(eligible_outcomes),
            "useful_creative_acceptance_rate": 0.0 if eligible_outcomes else None,
            "useful_creative_acceptance_v3_rate": 0.0 if eligible_outcomes else None,
            "act_count": len(eligible_outcomes),
            "act_realization_rate": 0.0 if eligible_outcomes else None,
            "opportunity_address_rate": 0.0 if eligible_outcomes else None,
            "valid_skip_rate": 0.0 if eligible_outcomes else None,
            "missed_opportunity_rate": 1.0 if eligible_outcomes else None,
            "outcomes": outcomes,
        }
    else:
        value = evaluate_useful_creative_acceptance_v3(opportunities=opportunities, decisions=decisions, interventions=interventions)
    eligible = int(value.get("eligible_opportunity_count") or 0)
    handled = eligible - int(value.get("missed_opportunity_count") or 0)
    cv = build_creative_value_score(
        opportunity_coverage=(handled / eligible) if eligible else 1.0,
        useful_creative_acceptance=value.get("useful_creative_acceptance_v3_rate") if eligible else 1.0,
        edit_strategy=1.0,
        emotion_arc=1.0,
        information_strategy=1.0,
        tail_stability=1.0 if float(final_score.get("director_quality_score", 0) or 0) >= 70 else 0.0,
    )
    patch_ids = _patch_ids(final_document)
    trace = build_intervention_trace(
        opportunities=opportunities,
        planner_decisions=decisions,
        patch_document=final_document,
        compilation=final_compilation,
        validation=final_validation,
        applied_patch_ids=patch_ids,
        rejected_patch_ids=[],
        dimension_deltas_before={item["opportunity_id"]: first_score.get("dimensions", {}) for item in opportunities},
        dimension_deltas_after={item["opportunity_id"]: final_score.get("dimensions", {}) for item in opportunities},
        final_statuses={item["opportunity_id"]: item["final_status"] for item in value.get("outcomes", []) if isinstance(item, dict)},
    )
    row: dict[str, Any] = {
        "schema_version": V24_PIPELINE_SCHEMA_VERSION,
        "scene": copy.deepcopy(metadata),
        "scene_id": scene_id,
        "status": "valid" if not decision_errors else "needs_information",
        "contract_pass": bool(repair.get("final", {}).get("contract_pass")),
        "contract_local_repair": repair,
        "opportunities": opportunities,
        "eligibility": eligibility["metrics"],
        "planner_decisions": decisions,
        "decision_errors": decision_errors,
        "opportunity_outcomes": value.get("outcomes", []),
        "opportunity_value": value,
        "quality": {"director_quality_score": final_score.get("director_quality_score"), "dimensions": final_score.get("dimensions")},
        "director_quality_score": final_score.get("director_quality_score"),
        "creative_value": cv,
        "intervention_trace": trace,
        "tail_root_cause": rank_tail_root_causes_v2({"scene_id": scene_id, "director_quality_score": final_score.get("director_quality_score"), "creative_value": cv, "eligible_coverage": {}}),
        "tail_repair": None,
        "fingerprints": {"baseline": fingerprint(baseline), "candidate": fingerprint(candidate)},
        "side_effects": {"production": 0, "storyboard": 0, "media": 0, "object_storage": 0},
    }
    row["tail_repair"] = execute_tail_repair(
        candidate=candidate,
        record={
            "scene_id": scene_id,
            "director_quality_score": final_score.get("director_quality_score"),
            "creative_value": cv,
            "eligible_coverage": {},
            "quality_issues": final_score.get("issues") or [],
            "relevant_beats": [],
            "relevant_shots": [],
        },
        contract=contract,
        repair_callable=tail_repair_callable,
        treatment=treatment,
        blocking=blocking,
        opportunities=opportunities,
        strategy=_dict(scene.get("strategy")) or _dict(parts["evidence"].get("strategy")),
        session=session,
        repair_context={"scene_id": scene_id},
        model=model,
        require_repair_ir=True,
    )
    return row


__all__ = ["V24_PIPELINE_SCHEMA_VERSION", "run_v24_scene_pipeline"]
