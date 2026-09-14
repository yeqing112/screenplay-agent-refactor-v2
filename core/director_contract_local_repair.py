"""Patch-level contract recovery for Director Quality V2.4.

The compiler and validator are intentionally strict.  This module provides
the bounded orchestration that sits *after* their first pass: valid fields are
kept, each failed field is repaired independently when the routing policy
allows it, and an unsuccessful repair is dropped so the baseline remains the
safe fallback.  It is provider-neutral; callers must inject a repair callable
for any external model invocation.

No scene, shot identity, immutable fact, or contract boundary is inferred by
this module.  The failed target and path are derived from compiler evidence,
and the injected callable receives only that field-scoped context.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

from core.director_patch_repair import repair_failed_patch
from core.director_patch_schema import (
    CreativePatchSchemaError,
    parse_creative_patch,
    parse_creative_patch_partial,
)
from core.director_partial_acceptance import apply_partial_acceptance
from core.director_patch_path_resolver import PatchPathResolutionError, resolve_patch_path
from core.director_contract_failure import build_contract_failure
from core.issue_router import route_director_repair


CONTRACT_LOCAL_REPAIR_SCHEMA_VERSION = "director-quality-v2-4-contract-local-repair-v1"
MAX_CONTRACT_REPAIR_ATTEMPTS = 2


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _patches(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _list(document.get("patches")) if isinstance(item, dict)]


def _known_ids(plan: dict[str, Any]) -> list[str]:
    return [
        _text(item.get("plan_shot_id"))
        for item in _list(plan.get("shots"))
        if isinstance(item, dict) and _text(item.get("plan_shot_id"))
    ]


def _find_patch(document: dict[str, Any], target_id: str) -> dict[str, Any] | None:
    for patch in _patches(document):
        if _text(patch.get("plan_shot_id")) == _text(target_id):
            return copy.deepcopy(patch)
    return None


def _relative_path(raw_path: Any, *, target_id: str, known_ids: list[str]) -> str:
    """Resolve a failure path without requiring it to be contract-allowed.

    A forbidden path is still useful as diagnostic evidence, but it must not be
    sent to the repair callable.  Returning an empty string makes that case
    fail closed while allowing valid creative paths to be selected exactly.
    """

    try:
        return resolve_patch_path(
            raw_path,
            plan_shot_id=target_id,
            known_plan_shot_ids=known_ids,
            allowed_patch_paths=None,
        ).path
    except (PatchPathResolutionError, TypeError, ValueError):
        return ""


def _failure_path(
    failure: dict[str, Any],
    patch: dict[str, Any],
    *,
    target_id: str,
    known_ids: list[str],
) -> str:
    """Return the one failed change path, or empty for an ambiguous error."""

    changes = _dict(patch.get("changes"))
    raw_error_path = _text(failure.get("path"))
    resolved_error = _relative_path(raw_error_path, target_id=target_id, known_ids=known_ids) if raw_error_path else ""
    if resolved_error:
        for raw_path in changes:
            if _relative_path(raw_path, target_id=target_id, known_ids=known_ids) == resolved_error:
                return resolved_error
    if len(changes) == 1:
        raw_path = next(iter(changes))
        return _relative_path(raw_path, target_id=target_id, known_ids=known_ids) or _text(raw_path)
    return ""


def _value_for_path(patch: dict[str, Any], path: str, *, target_id: str, known_ids: list[str]) -> Any:
    for raw_path, value in _dict(patch.get("changes")).items():
        if _relative_path(raw_path, target_id=target_id, known_ids=known_ids) == path:
            return copy.deepcopy(value)
    return None


def _merge_patch(document: dict[str, Any], patch: dict[str, Any]) -> None:
    """Merge a repaired single-field patch into a normalized document."""

    target = _text(patch.get("plan_shot_id"))
    changes = _dict(patch.get("changes"))
    if not target or not changes:
        return
    for existing in _patches(document):
        if _text(existing.get("plan_shot_id")) != target:
            continue
        existing_changes = existing.setdefault("changes", {})
        for path, value in changes.items():
            existing_changes[path] = copy.deepcopy(value)
        # The compiler recomputes normalization metadata/fingerprint.  Never
        # carry the first-pass fingerprint after changing the document.
        document.pop("patch_fingerprint", None)
        document.pop("normalization_metadata", None)
        return
    document.setdefault("patches", []).append(copy.deepcopy(patch))
    document.pop("patch_fingerprint", None)
    document.pop("normalization_metadata", None)


def _normalize_input(raw: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]], bool]:
    """Return normalized input, parse diagnostics, and fatal flag."""

    try:
        return parse_creative_patch(raw), [], False
    except CreativePatchSchemaError as exc:
        partial = parse_creative_patch_partial(raw)
        errors = [build_contract_failure(item) for item in _list(partial.get("errors"))]
        document = partial.get("document") if isinstance(partial.get("document"), dict) else None
        return document, errors, bool(partial.get("fatal"))


def repair_contract_failures(
    *,
    structural_shot_plan: dict[str, Any],
    patch_document: dict[str, Any],
    contract: dict[str, Any],
    repair_callable: Callable[[dict[str, Any]], Any] | None = None,
    treatment: dict[str, Any] | None = None,
    blocking: dict[str, Any] | None = None,
    max_attempts: int = MAX_CONTRACT_REPAIR_ATTEMPTS,
    session: Any | None = None,
    repair_context: dict[str, Any] | None = None,
    model: str = "",
    prompt_fingerprint: str = "",
) -> dict[str, Any]:
    """Recover invalid patch fields while preserving valid first-pass output.

    The function is deterministic until ``repair_callable`` is explicitly
    supplied.  At most two calls are made per failed field.  A failed or
    non-repairable field is omitted from the final patch document, which is
    equivalent to applying its baseline value and cannot invalidate the rest
    of the scene.
    """

    if not isinstance(structural_shot_plan, dict) or not isinstance(contract, dict):
        raise ValueError("structural_shot_plan and contract must be objects")
    baseline = copy.deepcopy(structural_shot_plan)
    normalized, parse_errors, parse_fatal = _normalize_input(patch_document)
    if normalized is None or parse_fatal:
        return {
            "schema_version": CONTRACT_LOCAL_REPAIR_SCHEMA_VERSION,
            "status": "fallback",
            "candidate": baseline,
            "accepted_patch_document": {"schema_version": "director_creative_patch_v1", "patches": [], "auxiliary_shot_proposals": []},
            "first_pass": {"contract_pass": False, "accepted_patch_count": 0, "rejected_patch_count": 0},
            "final": {"contract_pass": False, "accepted_patch_count": 0, "rejected_patch_count": 0},
            "failures": parse_errors,
            "outcomes": [],
            "repair_attempts": [],
            "metrics": {
                "patch_contract_first_pass_rate": 0.0,
                "patch_contract_final_pass_rate": 0.0,
                "scene_contract_first_pass": False,
                "scene_contract_final_pass": False,
                "contract_repair_attempts": 0,
                "contract_repair_success_count": 0,
                "fallback_patch_count": 0,
            },
        }

    initial = apply_partial_acceptance(
        baseline,
        normalized,
        contract,
        treatment=treatment,
        blocking=blocking,
    )
    compilation = _dict(initial.get("compilation"))
    accepted_doc = copy.deepcopy(compilation.get("accepted_patch_document") or {
        "schema_version": "director_creative_patch_v1",
        "patches": [],
        "auxiliary_shot_proposals": [],
    })
    failures = [build_contract_failure(item) for item in _list(initial.get("rejected_patches"))]
    # Parse-level errors are retained as diagnostics.  They do not get sent to
    # a field repair callable because no safe target/path exists.
    failures.extend(parse_errors)
    known_ids = _known_ids(baseline)
    outcomes: list[dict[str, Any]] = []
    repair_attempts: list[dict[str, Any]] = []
    working = copy.deepcopy(accepted_doc)
    limit = max(0, min(int(max_attempts), MAX_CONTRACT_REPAIR_ATTEMPTS))

    for index, failure in enumerate(failures):
        target_id = _text(failure.get("plan_shot_id") or failure.get("target_id"))
        source_patch = _find_patch(normalized, target_id) if target_id else None
        path = _failure_path(failure, source_patch or {}, target_id=target_id, known_ids=known_ids)
        code = _text(failure.get("code")) or "UNKNOWN_CONTRACT_FAILURE"
        route = route_director_repair(code)
        outcome: dict[str, Any] = {
            "failure_id": f"failure-{index + 1}",
            "category": _text(failure.get("category")) or "UNKNOWN_CONTRACT_FAILURE",
            "code": code,
            "plan_shot_id": target_id,
            "path": path,
            "first_pass": False,
            "repairable": bool(source_patch and path and route.get("llm_allowed") and repair_callable and limit),
            "status": "fallback",
            "attempt_count": 0,
            "fallback_to_baseline": True,
        }
        if not source_patch or not path:
            outcome["non_repairable_reason"] = "AMBIGUOUS_FAILURE_SCOPE" if source_patch else "SOURCE_PATCH_NOT_FOUND"
            outcomes.append(outcome)
            continue
        if not route.get("llm_allowed"):
            outcome["non_repairable_reason"] = "CONTRACT_BOUNDARY_REJECT"
            outcomes.append(outcome)
            continue
        if repair_callable is None or limit == 0:
            outcome["non_repairable_reason"] = "REPAIR_CALLABLE_UNAVAILABLE"
            outcomes.append(outcome)
            continue

        failed_patch = {
            "plan_shot_id": target_id,
            "changes": {path: _value_for_path(source_patch, path, target_id=target_id, known_ids=known_ids)},
        }
        issue = {
            **copy.deepcopy(failure),
            "target_id": target_id,
            "target_layer": "DIRECTOR_CREATIVE",
            "allowed_repair_paths": [path],
            "repair_scope": "single_patch_field",
            "exact_error": {
                "code": code,
                "category": failure.get("category"),
                "path": failure.get("path", ""),
                "message": failure.get("message", ""),
            },
        }

        def scoped_repair(request: dict[str, Any]) -> Any:
            # Keep the request minimal even if the lower-level compatibility
            # helper adds a broad contract projection internally.
            scoped = copy.deepcopy(request)
            scoped["allowed_repair_paths"] = [path]
            scoped["issue"] = copy.deepcopy(issue)
            contract_subset = _dict(scoped.get("contract_subset"))
            contract_subset["allowed_patch_paths"] = [path]
            scoped["contract_subset"] = contract_subset
            return repair_callable(scoped)

        repaired = repair_failed_patch(
            structural_shot_plan=baseline,
            failed_patch=failed_patch,
            issue=issue,
            contract=contract,
            repair_callable=scoped_repair,
            max_attempts=limit,
            session=session,
            repair_context=repair_context,
            model=model,
            prompt_fingerprint=prompt_fingerprint,
            repair_level=2,
            repair_engine="contract_local_repair",
            # The V2.4 budget is explicit: a field receives at most two
            # attempts.  Even when a provider repeats the same malformed
            # response, consuming the second bounded attempt keeps the
            # ledger and fallback metrics truthful.
            stop_on_same_error=False,
        )
        outcome["attempt_count"] = int(repaired.get("attempt_count") or 0)
        outcome["attempts"] = copy.deepcopy(repaired.get("attempts") or [])
        repair_attempts.extend(copy.deepcopy(repaired.get("attempts") or []))
        if repaired.get("status") == "repaired" and isinstance(repaired.get("accepted_patch"), dict):
            _merge_patch(working, repaired["accepted_patch"])
            outcome["status"] = "repaired"
            outcome["repairable"] = True
            outcome["fallback_to_baseline"] = False
        outcomes.append(outcome)

    final = apply_partial_acceptance(
        baseline,
        # ``working`` may be the first-pass compiler's accepted document.  Its
        # fingerprint is intentionally discarded after any field repair (and
        # also when all failed fields are dropped) so the strict parser can
        # recompute it from the actual final patch set.
        {key: value for key, value in working.items() if key not in {"patch_fingerprint", "normalization_metadata"}},
        contract,
        treatment=treatment,
        blocking=blocking,
    )
    final_validation = _dict(final.get("validation"))
    final_rejected = _list(final.get("rejected_patches"))
    total_input = len(_patches(normalized))
    first_accepted = int(_dict(initial.get("partial_acceptance")).get("accepted_patch_count") or 0)
    repaired_count = sum(1 for item in outcomes if item.get("status") == "repaired")
    fallback_count = sum(1 for item in outcomes if item.get("fallback_to_baseline"))
    final_accepted = int(_dict(final.get("partial_acceptance")).get("accepted_patch_count") or 0)
    return {
        "schema_version": CONTRACT_LOCAL_REPAIR_SCHEMA_VERSION,
        "status": "valid" if bool(final_validation.get("contract_pass")) and not final_rejected else "partial",
        "candidate": copy.deepcopy(final.get("candidate") or baseline),
        "accepted_patch_document": copy.deepcopy(_dict(final.get("compilation")).get("accepted_patch_document") or working),
        "first_pass": {
            "contract_pass": bool(_dict(initial.get("validation")).get("contract_pass")) and not failures,
            "accepted_patch_count": first_accepted,
            "rejected_patch_count": len(failures),
            "rejections": copy.deepcopy(failures),
        },
        "final": {
            "contract_pass": bool(final_validation.get("contract_pass")) and not final_rejected,
            "accepted_patch_count": final_accepted,
            "rejected_patch_count": len(final_rejected),
            "rejections": copy.deepcopy(final_rejected),
        },
        "failures": copy.deepcopy(failures),
        "outcomes": outcomes,
        "repair_attempts": repair_attempts,
        "validation": copy.deepcopy(final_validation),
        "metrics": {
            "patch_contract_first_pass_rate": (first_accepted / total_input) if total_input else 1.0,
            "patch_contract_final_pass_rate": (final_accepted / total_input) if total_input else 1.0,
            "scene_contract_first_pass": not bool(failures),
            "scene_contract_final_pass": bool(final_validation.get("contract_pass")) and not final_rejected,
            "contract_repair_attempts": sum(int(item.get("attempt_count") or 0) for item in outcomes),
            "contract_repair_success_count": repaired_count,
            "contract_repair_success_rate": (repaired_count / len(outcomes)) if outcomes else 1.0,
            "fallback_patch_count": fallback_count,
            "retained_valid_patch_count": final_accepted,
        },
    }


# Explicit aliases make the boundary discoverable without creating separate
# implementations or provider-specific code paths.
repair_failed_contract_patches = repair_contract_failures
run_contract_local_repair = repair_contract_failures
apply_contract_local_repair = repair_contract_failures


__all__ = [
    "CONTRACT_LOCAL_REPAIR_SCHEMA_VERSION",
    "MAX_CONTRACT_REPAIR_ATTEMPTS",
    "repair_contract_failures",
    "repair_failed_contract_patches",
    "run_contract_local_repair",
    "apply_contract_local_repair",
]
