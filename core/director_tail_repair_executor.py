"""Provider-neutral Tail Repair Executor for Director Quality V2.4."""

from __future__ import annotations

import copy
from typing import Any, Callable, Iterable

from core.director_creative_contract import IMMUTABLE_FIELDS
from core.director_patch_compiler import DirectorPatchCompileError, compile_creative_patches
from core.director_patch_schema import CreativePatchSchemaError, parse_creative_patch
from core.director_patch_validator import validate_compiled_patch_result
from core.director_quality_validator import score_director_quality
from core.director_tail_repair_acceptance import evaluate_repair_acceptance
from core.director_tail_repair import REPAIR_SCOPES, build_tail_repair_plan
from core.director_tail_root_cause import rank_tail_root_causes_v2
from core.local_repair import fingerprint
from core.repair_ledger import record_repair_attempt
from core.director_tail_repair_ir import RepairIRSchemaError, validate_repair_ir
from core.director_tail_repair_semantic_spec import minimal_valid_skeleton, typed_constraints_for
from core.director_tail_repair_ir_compiler import compile_repair_ir
from core.director_overdirecting import detect_over_directing
from core.director_tail_repair_request import REPAIR_REQUEST_SCHEMA_VERSION, build_repair_request, with_attempt


TAIL_REPAIR_EXECUTOR_SCHEMA_VERSION = "director-quality-v2-4-tail-repair-executor-v1"
TARGET_DIMENSIONS = {
    "WEAK_EDIT_STRATEGY": {"EDIT_RHYTHM"},
    "WEAK_EMOTION_ARC": {"EMOTIONAL_PROGRESSION", "PERFORMANCE_DIRECTION"},
    "WEAK_INFORMATION_STRATEGY": {"INFORMATION_STRATEGY"},
    "PERFORMANCE_DIRECTION_WEAK": {"PERFORMANCE_DIRECTION"},
    "CAMERA_LANGUAGE_GENERIC": {"SHOT_DIVERSITY", "VISUAL_STORYTELLING"},
    "OVER_DIRECTING": {"EDIT_RHYTHM", "SHOT_DIVERSITY"},
    "UNDER_DIRECTING": {"EDIT_RHYTHM", "EMOTIONAL_PROGRESSION"},
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _scope_root(path: Any) -> str:
    parts = [part for part in _text(path).replace("/", ".").split(".") if part]
    if parts and parts[0] == "shots":
        return parts[2] if len(parts) >= 3 else ""
    return parts[0] if parts else ""


def _target_delta(before: dict[str, Any], after: dict[str, Any], dimensions: set[str]) -> dict[str, float]:
    before_dims = _dict(before.get("dimensions"))
    after_dims = _dict(after.get("dimensions"))
    return {dimension: round(float(after_dims.get(dimension, 0)) - float(before_dims.get(dimension, 0)), 4) for dimension in sorted(dimensions)}


def _minimal_context(
    *,
    root_cause: str,
    record: dict[str, Any],
    opportunities: list[dict[str, Any]],
    contract: dict[str, Any],
    strategy: dict[str, Any] | None,
    target_metric: dict[str, Any],
    previous_intervention: Any,
) -> dict[str, Any]:
    dimensions = TARGET_DIMENSIONS.get(root_cause, set())
    relevant_opportunities = [
        copy.deepcopy(item)
        for item in opportunities
        if isinstance(item, dict) and dimensions.intersection({_text(value).upper() for value in _list(item.get("recommended_directing_dimensions"))})
    ][:5]
    immutable_subset = {
        "immutable_fields": list(IMMUTABLE_FIELDS),
        "scene": copy.deepcopy(_dict(contract.get("scene"))),
        "shots": copy.deepcopy(_list(_dict(contract.get("immutable_projection")).get("shots"))),
        "source_beat_map": copy.deepcopy(_dict(contract.get("source_beat_map"))),
    }
    return build_repair_request(
        root_cause=root_cause,
        target_dimensions=sorted(dimensions),
        relevant_opportunities=relevant_opportunities,
        relevant_beats=_list(record.get("relevant_beats")),
        relevant_shots=_list(record.get("relevant_shots")),
        allowed_plan_shot_ids=[
            _text(value) for value in (_list(record.get("allowed_plan_shot_ids")) or [
                _dict(item).get("plan_shot_id") for item in _list(record.get("relevant_shots"))
            ]) if _text(value)
        ],
        allowed_character_ids=[_text(value) for value in _list(record.get("allowed_character_ids")) if _text(value)],
        strategy_subset=_dict(strategy),
        immutable_contract=immutable_subset,
        previous_intervention=previous_intervention,
        validator_findings=_list(record.get("quality_issues")) + _list(_dict(record.get("validation")).get("quality_issues")),
        target_metric=target_metric,
    )


def _within_scope(document: dict[str, Any], root_cause: str) -> tuple[bool, str]:
    allowed = set(REPAIR_SCOPES.get(root_cause, set()))
    for patch in _list(document.get("patches")):
        if not isinstance(patch, dict):
            return False, "patch must be an object"
        for path in _dict(patch.get("changes")):
            root = _scope_root(path)
            if root not in allowed:
                return False, f"path {path} is outside {root_cause} repair scope"
    if _list(document.get("auxiliary_shot_proposals")) and "shots" not in allowed:
        return False, "auxiliary proposals are outside this root-cause scope"
    return True, ""


def _record_attempt(
    *,
    session: Any | None,
    repair_context: dict[str, Any] | None,
    root_cause: str,
    attempt_number: int,
    before: str,
    after: str,
    status: str,
    model: str,
    error: str = "",
    ledger_metadata: dict[str, Any] | None = None,
) -> None:
    if session is None and repair_context is None:
        return
    record_repair_attempt(
        repair={
            "issue_code": root_cause,
            "target_layer": "DIRECTOR_CREATIVE",
            "patch": [],
            "before_fingerprint": before,
            "after_fingerprint": after,
            "changed": before != after,
            "ledger_metadata": copy.deepcopy(ledger_metadata or {}),
        },
        issue={"code": root_cause, "target_layer": "DIRECTOR_CREATIVE", "target_id": _text(_dict(repair_context).get("scene_id"))},
        context={**(_dict(repair_context)), "attempt_number": attempt_number, "revalidation_status": status, "revalidation_details": {"error": error} if error else {}, "model": model},
        session=session,
    )


def _numeric(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _creative_value_score(value: Any) -> float | None:
    if isinstance(value, dict):
        return _numeric(value.get("score"))
    return _numeric(value)


def _repair_response_to_patch(
    raw: Any,
    *,
    structural_shot_plan: dict[str, Any],
    contract: dict[str, Any],
    allowed_character_ids: set[str] | None = None,
    allow_legacy_canonical: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convert one model response through IR, then deterministic compiler.

    A canonical response is accepted only for provider-free legacy callers
    that omit a model name; real/provider-bound execution is IR-only.
    """
    if isinstance(raw, dict) and _text(raw.get("schema_version")) == "director_tail_repair_ir_v1":
        known = {_text(item.get("plan_shot_id")) for item in _list(structural_shot_plan.get("shots")) if isinstance(item, dict)}
        ir = validate_repair_ir(raw, known_plan_shot_ids=known, allowed_character_ids=allowed_character_ids)
        return compile_repair_ir(ir, structural_shot_plan=structural_shot_plan, contract=contract), {"ir": ir, "protocol": "ir"}
    if allow_legacy_canonical and isinstance(raw, dict) and _text(raw.get("schema_version")) == "director_creative_patch_v1":
        return copy.deepcopy(raw), {"protocol": "legacy_canonical_compat"}
    raise RepairIRSchemaError("model response must be director_tail_repair_ir_v1; canonical patch output is not accepted")


def execute_tail_repair(
    *,
    candidate: dict[str, Any],
    record: dict[str, Any],
    contract: dict[str, Any],
    repair_callable: Callable[[dict[str, Any]], Any] | None = None,
    treatment: dict[str, Any] | None = None,
    blocking: dict[str, Any] | None = None,
    opportunities: Iterable[dict[str, Any]] = (),
    strategy: dict[str, Any] | None = None,
    max_root_causes: int = 2,
    max_attempts_per_root_cause: int = 2,
    session: Any | None = None,
    repair_context: dict[str, Any] | None = None,
    model: str = "",
    require_repair_ir: bool = False,
    root_causes: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Execute at most two targeted root-cause repairs and accept/rollback."""

    baseline = copy.deepcopy(candidate)
    source = record if isinstance(record, dict) else {}
    ranked = rank_tail_root_causes_v2(source)
    if root_causes is not None:
        ranked_causes = [
            _text(value)
            for value in root_causes
            if _text(value) in REPAIR_SCOPES
        ][: max(0, min(int(max_root_causes), 2))]
    else:
        ranked_causes = [
            _text(item.get("code"))
            for item in _list(ranked.get("ranked_root_causes"))
            if _text(item.get("code")) in REPAIR_SCOPES
        ][: max(0, min(int(max_root_causes), 2))]
    if not ranked_causes:
        plan = build_tail_repair_plan(source, root_causes=[ranked.get("root_cause") or "UNKNOWN_ROOT_CAUSE"])
        return {
            "schema_version": TAIL_REPAIR_EXECUTOR_SCHEMA_VERSION,
            "status": "not_triggered" if not plan.get("triggered") else "non_repairable",
            "candidate": baseline,
            "before_fingerprint": fingerprint(baseline),
            "after_fingerprint": fingerprint(baseline),
            "ranked_root_causes": ranked,
            "attempts": [],
            "accepted": [],
                "rolled_back": [],
                "execution_coverage": 0.0,
                "scene_execution_coverage": 0.0,
                "root_cause_attempt_coverage": 0.0,
                "repair_acceptance_rate": 0.0,
                "scene_repair_success_rate": 0.0,
                "non_repairable_reasons": ["NO_ELIGIBLE_REPAIR_SCOPE"] if plan.get("triggered") else [],
        }

    current = copy.deepcopy(baseline)
    rows: list[dict[str, Any]] = []
    opportunities_list = [copy.deepcopy(item) for item in opportunities if isinstance(item, dict)]
    accepted_roots = 0
    attempted_roots = 0
    for root_cause in ranked_causes:
        before_candidate = copy.deepcopy(current)
        before_fp = fingerprint(before_candidate)
        before_score = score_director_quality(before_candidate, treatment=treatment, blocking=blocking)
        target_metric = {dimension: before_score.get("dimensions", {}).get(dimension) for dimension in sorted(TARGET_DIMENSIONS.get(root_cause, set()))}
        context = _minimal_context(root_cause=root_cause, record=source, opportunities=opportunities_list, contract=contract, strategy=strategy, target_metric=target_metric, previous_intervention=rows[-1] if rows else None)
        attempts: list[dict[str, Any]] = []
        accepted = False
        rollback_reason = ""
        attempt_limit = max(0, min(int(max_attempts_per_root_cause), 2))
        previous_raw: Any = None
        previous_error = ""
        previous_validation_errors: list[dict[str, Any]] = []
        previous_kind = "CREATIVE_GENERATION"
        for attempt_number in range(1, attempt_limit + 1):
            if repair_callable is None:
                rollback_reason = "REPAIR_CALLABLE_UNAVAILABLE"
                break
            if attempt_number == 1:
                attempt_kind = "CREATIVE_GENERATION"
                attempt_payload = {"number": attempt_number, "kind": attempt_kind}
            elif previous_kind == "FORMAT_REPAIR":
                attempt_kind = "FORMAT_REPAIR"
                attempt_payload = {
                    "number": attempt_number,
                    "kind": attempt_kind,
                    "previous_raw_output": copy.deepcopy(previous_raw),
                    "previous_validation_errors": copy.deepcopy(previous_validation_errors) or ([{"path": "", "code": "DIRECTOR_REPAIR_IR_INVALID", "message": previous_error, "expected": "typed Repair IR", "actual_type": "unknown"}]),
                    "required_output_schema": "director_tail_repair_ir_v1",
                    "allowed_plan_shot_ids": [_text(item.get("plan_shot_id")) for item in _list(before_candidate.get("shots")) if isinstance(item, dict)],
                    "allowed_character_ids": [_text(value) for value in _list(context.get("allowed_character_ids")) if _text(value)],
                    "typed_constraints_subset": typed_constraints_for({"WEAK_EDIT_STRATEGY": "edit", "WEAK_EMOTION_ARC": "emotion", "WEAK_INFORMATION_STRATEGY": "information", "PERFORMANCE_DIRECTION_WEAK": "performance", "CAMERA_LANGUAGE_GENERIC": "camera"}.get(root_cause, "edit")),
                    "repair_type_minimal_skeleton": minimal_valid_skeleton({"WEAK_EDIT_STRATEGY": "edit", "WEAK_EMOTION_ARC": "emotion", "WEAK_INFORMATION_STRATEGY": "information", "PERFORMANCE_DIRECTION_WEAK": "performance", "CAMERA_LANGUAGE_GENERIC": "camera"}.get(root_cause, "edit"), character_placeholder="<replace with allowed_character_id>"),
                }
            else:
                attempt_kind = "SEMANTIC_REPAIR"
                attempt_payload = {
                    "number": attempt_number,
                    "kind": attempt_kind,
                    "previous_raw_output": copy.deepcopy(previous_raw),
                    "previous_validation_errors": copy.deepcopy(getattr(RepairIRSchemaError, "errors", [])) or ([{"path": "", "code": "DIRECTOR_REPAIR_IR_INVALID", "message": previous_error, "expected": "typed Repair IR", "actual_type": "unknown"}]),
                    "target_dimensions": sorted(TARGET_DIMENSIONS.get(root_cause, set())),
                    "scorer_signals": {"dimensions": copy.deepcopy(before_score.get("dimensions", {})), "allowed_repair_scope": sorted(REPAIR_SCOPES.get(root_cause, set()))},
                }
            request = with_attempt(context, attempt_payload)
            ir_parse_status = "not_run"
            canonical_compile_status = "not_run"
            contract_status = "not_run"
            try:
                raw = repair_callable(request)
                previous_raw = copy.deepcopy(raw)
                try:
                    document, protocol = _repair_response_to_patch(
                        raw,
                        structural_shot_plan=before_candidate,
                        contract=contract,
                        allowed_character_ids=set(_text(value) for value in _list(context.get("allowed_character_ids")) if _text(value)) or None,
                        allow_legacy_canonical=not bool(require_repair_ir),
                    )
                except (CreativePatchSchemaError, RepairIRSchemaError):
                    # A provider response was received but failed protocol
                    # parsing/validation. Preserve that distinction in the
                    # attempt ledger so "not_run" means the parser was never
                    # reached, while "invalid" means it rejected the output.
                    ir_parse_status = "invalid"
                    raise
                ir_parse_status = "valid" if protocol.get("protocol") == "ir" else "legacy_compat"
                in_scope, scope_error = _within_scope(document, root_cause)
                if not in_scope:
                    raise ValueError(scope_error)
                compilation = compile_creative_patches(before_candidate, document, contract, allow_partial=False)
                canonical_compile_status = "compiled"
                validation = validate_compiled_patch_result(compilation, before_candidate, contract, treatment=treatment, blocking=blocking)
                contract_status = "pass" if validation.get("contract_pass") else "fail"
                if not validation.get("contract_pass"):
                    raise ValueError("contract validation failed")
                after_candidate = compilation.get("candidate") if isinstance(compilation.get("candidate"), dict) else before_candidate
                after_score = score_director_quality(after_candidate, treatment=treatment, blocking=blocking)
                before_cv = _creative_value_score(source.get("creative_value"))
                after_cv = _creative_value_score(source.get("creative_value_after"))
                if after_cv is None and isinstance(source.get("creative_value_replay"), dict):
                    after_cv = _creative_value_score(source["creative_value_replay"].get("score"))
                over_before = detect_over_directing(_list(before_candidate.get("shots")), opportunities=opportunities_list, baseline_shot_count=len(_list(baseline.get("shots"))), allowed_auxiliary_count=int(_dict(contract.get("auxiliary_shot_policy")).get("max_per_source_beat") or 0)).get("over_directing_rate")
                over_after = detect_over_directing(_list(after_candidate.get("shots")), opportunities=opportunities_list, baseline_shot_count=len(_list(baseline.get("shots"))), allowed_auxiliary_count=int(_dict(contract.get("auxiliary_shot_policy")).get("max_per_source_beat") or 0)).get("over_directing_rate")
                inflation_before = detect_over_directing(_list(before_candidate.get("shots")), opportunities=opportunities_list, baseline_shot_count=len(_list(baseline.get("shots"))), allowed_auxiliary_count=int(_dict(contract.get("auxiliary_shot_policy")).get("max_per_source_beat") or 0)).get("shot_inflation_rate")
                inflation_after = detect_over_directing(_list(after_candidate.get("shots")), opportunities=opportunities_list, baseline_shot_count=len(_list(baseline.get("shots"))), allowed_auxiliary_count=int(_dict(contract.get("auxiliary_shot_policy")).get("max_per_source_beat") or 0)).get("shot_inflation_rate")
                validation_issues = _list(validation.get("errors")) + _list(validation.get("quality_issues"))
                fact_override_count = sum(1 for item in validation_issues if _text(_dict(item).get("code") or _dict(item).get("issue_code")) in {"DIRECTOR_FACT_OVERRIDE", "FACT_OVERRIDE_ATTEMPT"})
                structural_blocker_count = sum(1 for item in validation_issues if _text(_dict(item).get("severity")).lower() in {"blocker", "blocked"} or "STRUCTURAL" in _text(_dict(item).get("code")).upper())
                acceptance = evaluate_repair_acceptance(
                    before_quality=before_score,
                    after_quality=after_score,
                    target_dimensions=TARGET_DIMENSIONS.get(root_cause, set()),
                    contract_pass=bool(validation.get("contract_pass")),
                    fact_override_count=fact_override_count,
                    structural_blocker_count=structural_blocker_count,
                    creative_value_before=before_cv,
                    creative_value_after=after_cv,
                    over_directing_before=over_before,
                    over_directing_after=over_after,
                    shot_inflation_before=inflation_before,
                    shot_inflation_after=inflation_after,
                )
                delta = acceptance["target_dimension_deltas"]
                if not acceptance["accepted"]:
                    raise ValueError(acceptance["rollback_reason"] or "repair acceptance policy rejected candidate")
                after_fp = fingerprint(after_candidate)
                attempts.append({"attempt_number": attempt_number, "attempt_kind": attempt_kind, "status": "accepted", "protocol": protocol.get("protocol"), "ir_parse_status": ir_parse_status, "ir_fingerprint": _text(_dict(protocol.get("ir")).get("ir_fingerprint")), "canonical_compile_status": canonical_compile_status, "canonical_patch_fingerprint": fingerprint(document), "contract_status": contract_status, "target_delta": delta, "acceptance": acceptance, "before_fingerprint": before_fp, "after_fingerprint": after_fp})
                _record_attempt(session=session, repair_context=repair_context, root_cause=root_cause, attempt_number=attempt_number, before=before_fp, after=after_fp, status="accepted", model=model, ledger_metadata={"root_cause": root_cause, "target_dimensions": sorted(TARGET_DIMENSIONS.get(root_cause, set())), "attempt_kind": attempt_kind, "repair_request_fingerprint": fingerprint(request), "raw_response_fingerprint": fingerprint(raw), "repair_ir_fingerprint": _text(_dict(protocol.get("ir")).get("ir_fingerprint")), "canonical_patch_fingerprint": fingerprint(document), "ir_parse_status": "valid" if protocol.get("protocol") == "ir" else "legacy_compat", "canonical_compile_status": "compiled", "compile_status": "compiled", "contract_status": "pass", "target_dimension_delta": delta, "dq_before": before_score.get("director_quality_score"), "dq_after": after_score.get("director_quality_score"), "cv_before": before_cv, "cv_after": after_cv, "accepted": True, "rollback_reason": ""})
                current = copy.deepcopy(after_candidate)
                accepted = True
                accepted_roots += 1
                break
            except (CreativePatchSchemaError, DirectorPatchCompileError, RepairIRSchemaError, ValueError, TypeError) as exc:
                rollback_reason = str(exc)
                previous_error = str(exc)
                previous_kind = "FORMAT_REPAIR" if isinstance(exc, (CreativePatchSchemaError, RepairIRSchemaError)) else "SEMANTIC_REPAIR"
                structured_errors = copy.deepcopy(getattr(exc, "errors", [])) if isinstance(exc, RepairIRSchemaError) else []
                previous_validation_errors = structured_errors
                attempts.append({"attempt_number": attempt_number, "attempt_kind": attempt_kind, "status": "rejected", "ir_parse_status": ir_parse_status, "canonical_compile_status": canonical_compile_status, "contract_status": contract_status, "error": str(exc), "error_code": getattr(exc, "code", ""), "ir_validation_errors_structured": structured_errors})
                _record_attempt(session=session, repair_context=repair_context, root_cause=root_cause, attempt_number=attempt_number, before=before_fp, after=before_fp, status="rejected", model=model, error=str(exc), ledger_metadata={"root_cause": root_cause, "target_dimensions": sorted(TARGET_DIMENSIONS.get(root_cause, set())), "attempt_kind": attempt_kind, "repair_request_fingerprint": fingerprint(request), "raw_response_fingerprint": fingerprint(previous_raw) if previous_raw is not None else "", "repair_ir_fingerprint": "", "canonical_patch_fingerprint": "", "ir_parse_status": ir_parse_status, "canonical_compile_status": canonical_compile_status, "compile_status": canonical_compile_status, "contract_status": contract_status, "target_dimension_delta": {}, "dq_before": before_score.get("director_quality_score"), "dq_after": before_score.get("director_quality_score"), "cv_before": _creative_value_score(source.get("creative_value")), "cv_after": None, "accepted": False, "rollback_reason": str(exc)})
        if not accepted and not rollback_reason:
            rollback_reason = "REPAIR_ATTEMPT_BUDGET_EXHAUSTED"
        if attempts:
            attempted_roots += 1
        rows.append({
            "root_cause": root_cause,
            "repair_scope": sorted(REPAIR_SCOPES.get(root_cause, set())),
            "minimal_context": context,
            "attempts": attempts,
            "accepted": accepted,
            "rolled_back": not accepted,
            "before_fingerprint": before_fp,
            "after_fingerprint": fingerprint(current if accepted else before_candidate),
            "rollback_reason": "" if accepted else rollback_reason,
        })

    triggered_count = len(ranked_causes)
    return {
        "schema_version": TAIL_REPAIR_EXECUTOR_SCHEMA_VERSION,
        "status": "accepted" if accepted_roots else "rolled_back",
        "candidate": current,
        "before_fingerprint": fingerprint(baseline),
        "after_fingerprint": fingerprint(current),
        "ranked_root_causes": ranked,
        "attempts": rows,
        "accepted": [item["root_cause"] for item in rows if item["accepted"]],
        "rolled_back": [item["root_cause"] for item in rows if item["rolled_back"]],
        # Legacy field retained for historical reports; new fields separate
        # attempt coverage from acceptance and scene success semantics.
        "execution_coverage": round(accepted_roots / triggered_count, 4) if triggered_count else 0.0,
        "scene_execution_coverage": 1.0 if triggered_count and attempted_roots else 0.0,
        "root_cause_attempt_coverage": round(attempted_roots / triggered_count, 4) if triggered_count else 0.0,
        "repair_acceptance_rate": round(accepted_roots / attempted_roots, 4) if attempted_roots else 0.0,
        "scene_repair_success_rate": 1.0 if accepted_roots else 0.0,
        "non_repairable_reasons": [item["rollback_reason"] for item in rows if item["rolled_back"]],
    }


run_tail_repair = execute_tail_repair
execute_director_tail_repair = execute_tail_repair


__all__ = ["TAIL_REPAIR_EXECUTOR_SCHEMA_VERSION", "TARGET_DIMENSIONS", "execute_tail_repair", "run_tail_repair", "execute_director_tail_repair"]
