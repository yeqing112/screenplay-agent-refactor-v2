"""Bounded, patch-level Local Repair for Director Quality V2.1."""

from __future__ import annotations

import copy
from typing import Any, Callable

from core.director_creative_contract import IMMUTABLE_FIELDS
from core.director_auxiliary import validate_auxiliary_shot_proposal
from core.director_patch_compiler import DirectorPatchCompileError, compile_single_patch
from core.director_patch_schema import CreativePatchSchemaError, parse_creative_patch
from core.local_repair import fingerprint
from core.repair_ledger import record_repair_attempt


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _target_shot(plan: dict[str, Any], plan_shot_id: str) -> dict[str, Any]:
    for shot in _list(plan.get("shots")):
        if isinstance(shot, dict) and _text(shot.get("plan_shot_id")) == plan_shot_id:
            return copy.deepcopy(shot)
    return {}


def _contract_subset(contract: dict[str, Any], plan_shot_id: str) -> dict[str, Any]:
    projection = _dict(_dict(contract).get("immutable_projection"))
    shots = [shot for shot in _list(projection.get("shots")) if isinstance(shot, dict) and _text(shot.get("plan_shot_id")) == plan_shot_id]
    return {
        "immutable_fields": list(IMMUTABLE_FIELDS),
        "allowed_patch_paths": copy.deepcopy(_list(contract.get("allowed_patch_paths"))),
        "source_beat_map": copy.deepcopy(_dict(contract).get("source_beat_map") or {}),
        "target_shot": shots[0] if shots else {},
    }


def _strategy_subset(strategy: dict[str, Any] | None, issue: dict[str, Any]) -> dict[str, Any]:
    """Select only the strategy slice relevant to one Level 2 repair.

    The old V2.1 request serialized the complete scene strategy.  Keeping the
    selection deterministic reduces repair context without removing any
    authority constraint.
    """

    source = _dict(strategy)
    code = _text(issue.get("code") or issue.get("issue_code")).upper()
    result: dict[str, Any] = {"schema_version": source.get("schema_version", "")}
    if code in {"EMOTIONAL_FLATLINE", "POWER_SHIFT_NOT_VISUALIZED"}:
        for key in ("emotional_curve", "power_curve", "camera_language"):
            if key in source:
                result[key] = copy.deepcopy(source[key])
    elif code in {"INFORMATION_REVEAL_CONFLICT"}:
        for key in ("information_strategy", "visual_strategy", "camera_language"):
            if key in source:
                result[key] = copy.deepcopy(source[key])
    elif code in {"GRATUITOUS_CAMERA_MOVEMENT", "REDUNDANT_SHOT"}:
        for key in ("camera_language", "rhythm_strategy", "forbidden_tendencies"):
            if key in source:
                result[key] = copy.deepcopy(source[key])
    else:
        for key in ("scene_objective", "visual_strategy", "camera_language", "forbidden_tendencies"):
            if key in source:
                result[key] = copy.deepcopy(source[key])
    return result


def repair_failed_patch(
    *,
    structural_shot_plan: dict[str, Any],
    failed_patch: dict[str, Any],
    issue: dict[str, Any],
    contract: dict[str, Any],
    strategy: dict[str, Any] | None = None,
    repair_callable: Callable[[dict[str, Any]], Any] | None = None,
    max_attempts: int = 2,
    session: Any | None = None,
    repair_context: dict[str, Any] | None = None,
    model: str = "",
    prompt_fingerprint: str = "",
    repair_level: int = 2,
    repair_engine: str = "llm",
    stop_on_same_error: bool = False,
) -> dict[str, Any]:
    """Repair a single failed patch without rerunning scene planning."""

    if not isinstance(structural_shot_plan, dict) or not isinstance(failed_patch, dict):
        raise ValueError("structural_shot_plan and failed_patch must be objects")
    plan_shot_id = _text(failed_patch.get("plan_shot_id"))
    if not plan_shot_id:
        raise ValueError("failed_patch.plan_shot_id is required")
    attempts_limit = max(0, min(int(max_attempts), 2))
    request = {
        "protocol_version": "director-quality-v2-1-local-repair",
        "failed_patch": copy.deepcopy(failed_patch),
        "issue": copy.deepcopy(issue) if isinstance(issue, dict) else {},
        "contract_subset": _contract_subset(contract, plan_shot_id),
        "source_shot": _target_shot(structural_shot_plan, plan_shot_id),
        "strategy": _strategy_subset(strategy, issue),
        "repair_level": int(repair_level),
        "repair_engine": _text(repair_engine) or "llm",
    }
    attempts: list[dict[str, Any]] = []
    def record_attempt(*, attempt_number: int, status: str, repair: dict[str, Any] | None = None, error: str = "") -> None:
        if session is None and repair_context is None:
            return
        baseline_fp = fingerprint(structural_shot_plan)
        repair_payload = repair if isinstance(repair, dict) else {
            "issue_code": _text(issue.get("code") or issue.get("issue_code")) or "DIRECTOR_PATCH_REPAIR",
            "target_id": plan_shot_id,
            "target_layer": "DIRECTOR_CREATIVE",
            "patch": [],
            "before_fingerprint": baseline_fp,
            "after_fingerprint": baseline_fp,
            "changed": False,
        }
        context = {
            **(_dict(repair_context)),
            "attempt_number": attempt_number,
            "repair_level": int(repair_level),
            "repair_engine": _text(repair_engine) or "llm",
            "revalidation_status": status,
            "revalidation_details": {"error": error} if error else {},
            "model": model,
            "prompt_fingerprint": prompt_fingerprint,
            "shot_id": plan_shot_id,
        }
        record_repair_attempt(
            repair=repair_payload,
            issue={**(_dict(issue)), "target_layer": "DIRECTOR_CREATIVE", "target_id": plan_shot_id},
            context=context,
            session=session,
        )
    if repair_callable is None or attempts_limit == 0:
        return {
            "status": "fallback",
            "attempts": attempts,
            "attempt_count": 0,
            "accepted_patch": None,
            "fallback_to_baseline": True,
            "request": request,
        }
    previous_error_signature = ""
    for attempt_number in range(1, attempts_limit + 1):
        if stop_on_same_error and attempt_number > 1 and previous_error_signature:
            break
        try:
            repaired_raw = repair_callable(copy.deepcopy(request))
            # Repairers may return a single patch or a one-item patch document;
            # both are normalized through the same strict schema boundary.
            if isinstance(repaired_raw, dict) and "patches" in repaired_raw:
                parsed = parse_creative_patch(repaired_raw)
                patches = parsed["patches"]
                if len(patches) != 1:
                    raise ValueError("local repair must return exactly one patch")
                repaired_patch = patches[0]
            else:
                parsed = parse_creative_patch({
                    "schema_version": "director_creative_patch_v1",
                    "patches": [repaired_raw],
                    "auxiliary_shot_proposals": [],
                })
                repaired_patch = parsed["patches"][0]
            if _text(repaired_patch.get("plan_shot_id")) != plan_shot_id:
                raise ValueError("local repair may only target the failed patch shot")
            compiled = compile_single_patch(structural_shot_plan, repaired_patch, contract)
            attempts.append({"attempt_number": attempt_number, "status": "accepted", "error": ""})
            record_attempt(attempt_number=attempt_number, status="accepted", repair={
                "issue_code": _text(issue.get("code") or issue.get("issue_code")) or "DIRECTOR_PATCH_REPAIR",
                "target_id": plan_shot_id,
                "target_layer": "DIRECTOR_CREATIVE",
                "patch": compiled.get("operations", []),
                "before_fingerprint": compiled.get("before_fingerprint", ""),
                "after_fingerprint": compiled.get("after_fingerprint", ""),
                "changed": compiled.get("changed", False),
            })
            return {
                "status": "repaired",
                "attempts": attempts,
                "attempt_count": attempt_number,
                "accepted_patch": repaired_patch,
                "compiled": compiled,
                "fallback_to_baseline": False,
                "request": request,
            }
        except (CreativePatchSchemaError, DirectorPatchCompileError, ValueError, TypeError) as exc:
            code = getattr(exc, "code", "DIRECTOR_PATCH_REPAIR_INVALID")
            error_text = str(exc)
            signature = f"{code}:{error_text}"
            attempts.append({"attempt_number": attempt_number, "status": "rejected", "error": error_text, "code": code})
            record_attempt(attempt_number=attempt_number, status="rejected", error=str(exc))
            if stop_on_same_error and not previous_error_signature:
                previous_error_signature = signature
    return {
        "status": "fallback",
        "attempts": attempts,
        "attempt_count": len(attempts),
        "accepted_patch": None,
        "fallback_to_baseline": True,
        "request": request,
    }


repair_director_patch = repair_failed_patch
repair_single_patch = repair_failed_patch


def repair_failed_auxiliary_proposal(
    *,
    structural_shot_plan: dict[str, Any],
    failed_proposal: dict[str, Any],
    issue: dict[str, Any],
    contract: dict[str, Any],
    strategy: dict[str, Any] | None = None,
    repair_callable: Callable[[dict[str, Any]], Any] | None = None,
    max_attempts: int = 2,
    session: Any | None = None,
    repair_context: dict[str, Any] | None = None,
    model: str = "",
    prompt_fingerprint: str = "",
    repair_level: int = 2,
    repair_engine: str = "llm",
    stop_on_same_error: bool = False,
) -> dict[str, Any]:
    """Repair exactly one AuxiliaryShotProposal without rerunning a scene.

    The proposal identity and source beat are immutable for this repair.  A
    repairer may only correct proposal metadata (type, motivation, camera,
    participants, duration) while the deterministic auxiliary validator
    remains the authority boundary.
    """
    if not isinstance(structural_shot_plan, dict) or not isinstance(failed_proposal, dict):
        raise ValueError("structural_shot_plan and failed_proposal must be objects")
    proposal_id = _text(failed_proposal.get("proposal_id"))
    source_beat_id = _text(failed_proposal.get("source_beat_id"))
    if not proposal_id:
        raise ValueError("failed_proposal.proposal_id is required")
    attempts_limit = max(0, min(int(max_attempts), 2))
    request = {
        "protocol_version": "director-quality-v2-1-auxiliary-local-repair",
        "failed_proposal": copy.deepcopy(failed_proposal),
        "issue": copy.deepcopy(issue) if isinstance(issue, dict) else {},
        "contract_subset": {
            "source_beat_map": copy.deepcopy(_dict(contract).get("source_beat_map") or {}),
            "auxiliary_shot_policy": copy.deepcopy(_dict(contract).get("auxiliary_shot_policy") or {}),
            "known_plan_shot_ids": [
                _text(item.get("plan_shot_id"))
                for item in _list(structural_shot_plan.get("shots"))
                if isinstance(item, dict) and _text(item.get("plan_shot_id"))
            ],
        },
        "strategy": _strategy_subset(strategy, issue),
        "repair_level": int(repair_level),
        "repair_engine": _text(repair_engine) or "llm",
    }
    attempts: list[dict[str, Any]] = []

    def record_attempt(*, attempt_number: int, status: str, repair: dict[str, Any] | None = None, error: str = "") -> None:
        if session is None and repair_context is None:
            return
        baseline_fp = fingerprint(failed_proposal)
        repair_payload = repair if isinstance(repair, dict) else {
            "issue_code": _text(issue.get("code") or issue.get("issue_code")) or "DIRECTOR_AUXILIARY_REPAIR",
            "target_id": proposal_id,
            "target_layer": "DIRECTOR_CREATIVE",
            "patch": [],
            "before_fingerprint": baseline_fp,
            "after_fingerprint": baseline_fp,
            "changed": False,
        }
        context = {
            **(_dict(repair_context)),
            "attempt_number": attempt_number,
            "repair_level": int(repair_level),
            "repair_engine": _text(repair_engine) or "llm",
            "revalidation_status": status,
            "revalidation_details": {"error": error} if error else {},
            "model": model,
            "prompt_fingerprint": prompt_fingerprint,
            "proposal_id": proposal_id,
            "shot_id": "",
        }
        record_repair_attempt(
            repair=repair_payload,
            issue={**(_dict(issue)), "target_layer": "DIRECTOR_CREATIVE", "target_id": proposal_id},
            context=context,
            session=session,
        )

    if repair_callable is None or attempts_limit == 0:
        return {"status": "fallback", "attempts": attempts, "attempt_count": 0, "accepted_proposal": None, "fallback_to_baseline": True, "request": request}

    previous_error_signature = ""
    for attempt_number in range(1, attempts_limit + 1):
        if stop_on_same_error and attempt_number > 1 and previous_error_signature:
            break
        try:
            repaired_raw = repair_callable(copy.deepcopy(request))
            if isinstance(repaired_raw, dict) and isinstance(repaired_raw.get("auxiliary_shot_proposals"), list):
                proposals = repaired_raw["auxiliary_shot_proposals"]
                if len(proposals) != 1:
                    raise ValueError("local auxiliary repair must return exactly one proposal")
                repaired = proposals[0]
            else:
                repaired = repaired_raw
            if not isinstance(repaired, dict):
                raise ValueError("local auxiliary repair must return a proposal object")
            if _text(repaired.get("proposal_id")) != proposal_id:
                raise ValueError("local auxiliary repair may not change proposal_id")
            if _text(repaired.get("source_beat_id")) != source_beat_id:
                raise ValueError("local auxiliary repair may not change source_beat_id")
            validated = validate_auxiliary_shot_proposal(repaired, structural_shot_plan, contract)
            before_fp = fingerprint(failed_proposal)
            after_fp = fingerprint(validated)
            attempts.append({"attempt_number": attempt_number, "status": "accepted", "error": ""})
            record_attempt(
                attempt_number=attempt_number,
                status="accepted",
                repair={
                    "issue_code": _text(issue.get("code") or issue.get("issue_code")) or "DIRECTOR_AUXILIARY_REPAIR",
                    "target_id": proposal_id,
                    "target_layer": "DIRECTOR_CREATIVE",
                    "patch": [{"op": "replace", "path": f"/auxiliary_shot_proposals/{proposal_id}", "value": copy.deepcopy(validated)}],
                    "before_fingerprint": before_fp,
                    "after_fingerprint": after_fp,
                    "changed": before_fp != after_fp,
                },
            )
            return {"status": "repaired", "attempts": attempts, "attempt_count": attempt_number, "accepted_proposal": validated, "fallback_to_baseline": False, "request": request}
        except (ValueError, TypeError) as exc:
            code = getattr(exc, "code", "DIRECTOR_AUXILIARY_REPAIR_INVALID")
            error_text = str(exc)
            attempts.append({"attempt_number": attempt_number, "status": "rejected", "error": error_text, "code": code})
            record_attempt(attempt_number=attempt_number, status="rejected", error=str(exc))
            if stop_on_same_error and not previous_error_signature:
                previous_error_signature = f"{code}:{error_text}"
    return {"status": "fallback", "attempts": attempts, "attempt_count": len(attempts), "accepted_proposal": None, "fallback_to_baseline": True, "request": request}


__all__ = ["repair_failed_patch", "repair_director_patch", "repair_single_patch", "repair_failed_auxiliary_proposal"]
