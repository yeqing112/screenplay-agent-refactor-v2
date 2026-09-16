"""Contract and authority compiler for the one-call semantic verifier canary."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

VERIFIER_SCHEMA_VERSION = "fact_semantic_verifier_v1"
VERDICTS = ("ENTAILED", "PARTIAL", "CLAIM_ONLY", "INFERENCE", "CONTRADICTED", "AMBIGUOUS")
FORBIDDEN_FIELDS = ("new_fact", "corrected_fact", "replacement_fact", "new_evidence_refs", "recommended_evidence_refs", "source_search", "final_authority", "final_status", "script_ir")
ALLOWED_RESULT_FIELDS = {"fact_id", "verdict", "supported_components", "unsupported_components", "rationale"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def schema_fingerprint() -> str:
    return hashlib.sha256(_canonical({"contract": contract(), "provider_schema": provider_schema()})).hexdigest()


def provider_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["results"],
        "additionalProperties": False,
        "properties": {"results": {"type": "array", "items": {"type": "object", "required": ["fact_id", "verdict", "supported_components", "unsupported_components", "rationale"], "additionalProperties": False, "properties": {"fact_id": {"type": "string", "pattern": "^FACT_[0-9]{4}$"}, "verdict": {"enum": list(VERDICTS)}, "supported_components": {"type": "array", "items": {"type": "string"}}, "unsupported_components": {"type": "array", "items": {"type": "string"}}, "rationale": {"type": "string"}}}}},
    }


def contract() -> dict[str, Any]:
    return {
        "schema_version": VERIFIER_SCHEMA_VERSION,
        "role": "semantic_verifier_not_fact_writer_or_retriever",
        "provider_owns": ["semantic_verdict", "supported_components", "unsupported_components", "rationale"],
        "program_owns": ["fact_id", "canonical_fact", "evidence_refs", "resolved_evidence", "final_authority", "final_status", "downstream_eligibility"],
        "verdicts": list(VERDICTS),
        "forbidden_provider_fields": list(FORBIDDEN_FIELDS),
        "interfaces": {
            "request_projection": "build_verifier_request",
            "parser": "parse_verifier_payload",
            "validator": "validate_verifier_payload",
            "authority_compiler": "compile_semantic_authority",
        },
        "input_restrictions": ["existing_facts_only", "existing_resolved_evidence_only", "no_source_text", "no_anchor_corpus", "no_development_forensic_answers"],
        "exact_cardinality": "one_result_per_supplied_fact_id",
        "provider_calls": 1,
        "retries": 0,
    }


def build_verifier_request(*, facts: list[dict[str, Any]], machine_context: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a frozen seven-fact projection; no source retrieval is possible."""
    context_by_id = {str(row.get("fact_id")): row for row in machine_context if isinstance(row, dict)}
    items: list[dict[str, Any]] = []
    for fact in facts:
        fact_id = str(fact.get("fact_id") or "")
        context = context_by_id.get(fact_id, {})
        items.append({
            "fact_id": fact_id,
            "assertion": {"subject": fact.get("subject_id"), "predicate": fact.get("predicate"), "value": copy.deepcopy(fact.get("value"))},
            "provider_epistemic_class": context.get("provider_epistemic_class"),
            "evidence_refs": [row.get("anchor_ref") for row in fact.get("evidence") or []],
            "resolved_evidence": copy.deepcopy(context.get("resolved_evidence") or []),
            "anchor_surface_classes": list(context.get("anchor_surface_classes") or []),
            "confirmation_ceilings": copy.deepcopy(context.get("confirmation_ceilings") or []),
            "machine_guard_findings": copy.deepcopy(context.get("machine_guard_findings") or []),
        })
    return {"task": "judge_existing_fact_semantic_support_v1", "contract": {**contract(), "schema_fingerprint": schema_fingerprint(), "output_schema": provider_schema()}, "facts": items}


def parse_verifier_payload(raw: Any) -> dict[str, Any]:
    """Parse a provider response without repair, coercion, or fallback.

    The canary accepts only a JSON object (or an already decoded mapping).
    Partial JSON, prose-wrapped JSON, and malformed values fail closed before
    validation so a retry or repair path cannot be introduced accidentally.
    """
    if isinstance(raw, dict):
        return copy.deepcopy(raw)
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("VERIFIER_OUTPUT_JSON_INVALID") from exc
        if isinstance(value, dict):
            return value
    raise ValueError("VERIFIER_OUTPUT_OBJECT_REQUIRED")


def validate_verifier_payload(payload: Any, expected_fact_ids: list[str]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return {"status": "FAIL", "errors": [{"code": "VERIFIER_OUTPUT_SCHEMA_INVALID"}], "results": []}
    results = payload["results"]
    seen: set[str] = set()
    for index, row in enumerate(results, 1):
        if not isinstance(row, dict):
            errors.append({"code": "VERIFIER_RESULT_INVALID", "index": index}); continue
        forbidden = sorted(set(row).intersection(FORBIDDEN_FIELDS))
        if forbidden:
            errors.append({"code": "VERIFIER_FORBIDDEN_FIELD", "index": index, "fields": forbidden})
        extra = sorted(set(row) - ALLOWED_RESULT_FIELDS)
        if extra:
            errors.append({"code": "VERIFIER_UNEXPECTED_FIELD", "index": index, "fields": extra})
        fact_id = str(row.get("fact_id") or "")
        if fact_id in seen:
            errors.append({"code": "VERIFIER_DUPLICATE_FACT_ID", "fact_id": fact_id})
        seen.add(fact_id)
        if fact_id not in expected_fact_ids:
            errors.append({"code": "VERIFIER_UNKNOWN_FACT_ID", "fact_id": fact_id})
        if row.get("verdict") not in VERDICTS:
            errors.append({"code": "VERIFIER_VERDICT_INVALID", "fact_id": fact_id})
        for key in ("supported_components", "unsupported_components"):
            if not isinstance(row.get(key), list) or not all(isinstance(item, str) for item in row.get(key)):
                errors.append({"code": "VERIFIER_COMPONENTS_INVALID", "fact_id": fact_id, "field": key})
        if not isinstance(row.get("rationale"), str):
            errors.append({"code": "VERIFIER_RATIONALE_INVALID", "fact_id": fact_id})
    missing = sorted(set(expected_fact_ids) - seen)
    errors.extend({"code": "VERIFIER_MISSING_FACT_ID", "fact_id": fact_id} for fact_id in missing)
    return {"status": "PASS" if not errors and len(results) == len(expected_fact_ids) else "FAIL", "errors": errors, "results": results}


def compile_semantic_authority(*, facts: list[dict[str, Any]], verifier_results: list[dict[str, Any]], machine_guards: dict[str, dict[str, Any]] | None = None, evidence_authority_status: str = "PASS") -> dict[str, Any]:
    """Compile provider verdicts with deterministic guard precedence.

    ``evidence_authority_status`` and the machine confirmation ceilings are
    program-owned inputs.  A provider ``ENTAILED`` verdict can never promote a
    fact when either prerequisite is missing or blocked.
    """
    by_id = {str(row.get("fact_id")): row for row in verifier_results}
    guards = machine_guards or {}
    rows: list[dict[str, Any]] = []
    for fact in facts:
        fact_id = str(fact.get("fact_id"))
        result = by_id.get(fact_id, {})
        verdict = result.get("verdict")
        guard = guards.get(fact_id) or {}
        blockers = list(guard.get("hard_blockers") or [])
        if str(evidence_authority_status) not in {"PASS", "qualified"}:
            blockers.append("EVIDENCE_AUTHORITY_NOT_PASS")
        ceilings = guard.get("confirmation_ceilings") or []
        if any(isinstance(ceiling, dict) and ceiling.get("allowed") is False for ceiling in ceilings):
            blockers.append("CONFIRMATION_CEILING_BLOCKED")
        disposition = "AMBIGUOUS_REVIEW"
        authority = "model_observation"
        status = "proposed"
        downstream = False
        review = True
        if verdict == "CONTRADICTED":
            disposition = "CONTRADICTED_REJECTED"
        elif verdict == "CLAIM_ONLY":
            disposition = "CLAIM_SUPPORTED"
        elif verdict == "INFERENCE":
            disposition = "INFERENCE_PROPOSED"
        elif verdict == "PARTIAL":
            disposition = "PARTIAL_SUPPORT_REVIEW"
        elif verdict == "ENTAILED" and not blockers:
            disposition = "WORLD_FACT_CONFIRMED"
            authority = "source_text"
            status = "confirmed"
            downstream = True
            review = False
        elif verdict == "ENTAILED" and any(blocker in blockers for blocker in ("QUOTED_TEXT_WORLD_FACT_CONFIRMATION_BLOCKED", "CONFIRMATION_CEILING_BLOCKED", "EVIDENCE_AUTHORITY_NOT_PASS")):
            disposition = "CLAIM_SUPPORTED"
        elif verdict in {"ENTAILED", "AMBIGUOUS"}:
            disposition = "AMBIGUOUS_REVIEW"
        rows.append({"fact_id": fact_id, "semantic_disposition": disposition, "effective_authority": authority, "effective_status": status, "downstream_eligible": downstream, "review_required": review, "verifier_verdict": verdict, "supported_components": list(result.get("supported_components") or []), "unsupported_components": list(result.get("unsupported_components") or []), "rationale": str(result.get("rationale") or ""), "machine_guard_overrides": blockers})
    counts = {name: sum(1 for row in rows if row["semantic_disposition"] == name) for name in ("WORLD_FACT_CONFIRMED", "CLAIM_SUPPORTED", "INFERENCE_PROPOSED", "PARTIAL_SUPPORT_REVIEW", "CONTRADICTED_REJECTED", "AMBIGUOUS_REVIEW")}
    global_status = "SEMANTIC_GROUNDING_CLOSED_WITH_REVIEW" if any(row["review_required"] for row in rows) else "SEMANTIC_GROUNDING_CLOSED"
    return {"schema_version": "semantic_authority_overlay_v1", "status": global_status, "runtime_authority": True, "provider_verdicts_are_non_authoritative": True, "facts": rows, "counts": counts, "fact_coverage_status": "NOT_YET_QUALIFIED", "ready_for_fact_coverage_qualification": True, "ready_for_script_ir_processing": False, "script_ir_processing_authorized": False, "treatment_processing_authorized": False}


__all__ = ["VERDICTS", "FORBIDDEN_FIELDS", "contract", "provider_schema", "schema_fingerprint", "build_verifier_request", "parse_verifier_payload", "validate_verifier_payload", "compile_semantic_authority"]
