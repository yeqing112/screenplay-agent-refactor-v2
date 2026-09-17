"""Controlled proposer canary for targeted missing facts.

This module is deliberately a thin orchestration layer.  It never owns fact
authority and never persists a FactSnapshot: provider output is validated by
the existing targeted semantic resolver and is reported as a candidate only.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from typing import Any, Callable

from core.targeted_semantic_evidence_resolution import (
    RESOLUTION_TYPES,
    proposal_to_candidate_fact,
    resolve_semantic_evidence,
    retrieve_candidate_anchors,
)

SCHEMA_VERSION = "authorized_proposer_provider_canary_v1"
FINAL_CLASSIFICATIONS = {
    "RESOLVED", "NO_CANDIDATE_ANCHOR", "PROVIDER_UNSUPPORTED", "PROVIDER_AMBIGUOUS",
    "PROVIDER_CONFLICTED", "PROVIDER_SCHEMA_INVALID", "PROVIDER_EVIDENCE_INVALID",
    "SEMANTIC_SUPPORT_REJECTED", "AUTHORITY_CONFLICT", "SOURCE_GAP",
    "SOURCE_FACT_ABSENT", "RETRIEVAL_RECALL_GAP", "PROVIDER_NOT_CONFIGURED",
    "PROVIDER_NOT_EXECUTED", "PROVIDER_CALL_FAILED",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def build_proposer_system_prompt() -> str:
    return (
        "You are a conservative source-grounded fact proposer. Return exactly one JSON object "
        "matching the supplied schema. You may only cite the supplied candidate anchors. "
        "Do not invent evidence, anchors, authority, status, offsets, or additional fields. "
        "Preserve fact_key, subject_type, subject_id, predicate, and scope exactly. "
        "A high confidence value never substitutes for exact evidence. reasoning_summary is "
        "diagnostic only."
    )


def build_proposer_request(manifest_item: dict[str, Any], candidate_set: dict[str, Any], source_index: dict[str, Any]) -> dict[str, Any]:
    """Build the bounded provider request; no full source material is included."""
    return {
        "task": "targeted_missing_fact_proposal",
        "fact": copy.deepcopy(manifest_item),
        "candidate_anchors": copy.deepcopy(candidate_set.get("anchors") or [])[:8],
        "source_evidence_index_fingerprint": source_index.get("evidence_index_fingerprint"),
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "fact_key", "subject_type", "subject_id", "predicate", "scope", "proposed_value",
                "supporting_anchor_refs", "exact_quotes", "resolution_type", "confidence", "ambiguity",
                "conflicting_anchor_refs", "reasoning_summary",
            ],
            "properties": {
                "fact_key": {"type": "string"}, "subject_type": {"type": "string"},
                "subject_id": {"type": "string"}, "predicate": {"type": "string"},
                "scope": {"type": "string"}, "proposed_value": {},
                "supporting_anchor_refs": {"type": "array", "items": {"type": "string"}},
                "exact_quotes": {"type": "array", "items": {"type": "string"}},
                "resolution_type": {"enum": list(RESOLUTION_TYPES)},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "ambiguity": {"type": "boolean"},
                "conflicting_anchor_refs": {"type": "array", "items": {"type": "string"}},
                "reasoning_summary": {"type": "string"},
            },
        },
    }


def make_llm_provider(*, model_profile: dict[str, Any], audit_records: list[dict[str, Any]], call_fn: Callable[..., dict[str, Any]] | None = None) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Return a provider adapter backed by the existing LLM abstraction.

    ``call_fn`` is injectable for deterministic tests.  The adapter performs
    one transport call and zero parser retries per fact.
    """
    if call_fn is None:
        from core.llm import call_llm_json
        call_fn = call_llm_json

    def provider(request: dict[str, Any]) -> dict[str, Any]:
        fact = request.get("fact") if isinstance(request.get("fact"), dict) else {}
        bounded_request = build_proposer_request(
            fact,
            {"anchors": request.get("candidate_anchors") or []},
            {"evidence_index_fingerprint": request.get("source_evidence_index_fingerprint")},
        )
        prompt = json.dumps(bounded_request, ensure_ascii=False, sort_keys=True, indent=2)
        result = call_fn(
            prompt,
            system=build_proposer_system_prompt(),
            model_profile=model_profile,
            required_keys={
                "fact_key", "subject_type", "subject_id", "predicate", "scope", "proposed_value",
                "supporting_anchor_refs", "exact_quotes", "resolution_type", "confidence", "ambiguity",
                "conflicting_anchor_refs", "reasoning_summary",
            },
            json_parse_retries=0,
            retries=1,
            estimated_tokens=2500,
            response_format={"type": "json_object"},
            audit_callback=audit_records.append,
            audit_extra={
                "stage": "authorized_proposer_provider_canary",
                "fact_key": str(fact.get("fact_key") or "")[:200],
                "provider_role": "PROPOSER",
            },
        )
        return result

    return provider


def _classify(row: dict[str, Any], *, provider_enabled: bool, execution_authorized: bool = False) -> str:
    resolution = row.get("resolution") if isinstance(row.get("resolution"), dict) else {}
    diagnostics = resolution.get("diagnostics") if isinstance(resolution.get("diagnostics"), dict) else {}
    provider = diagnostics.get("provider") if isinstance(diagnostics.get("provider"), dict) else {}
    support = diagnostics.get("support") if isinstance(diagnostics.get("support"), dict) else {}
    if not row.get("candidate_anchor_count"):
        return "NO_CANDIDATE_ANCHOR"
    if not row.get("provider_called"):
        if not provider_enabled:
            return "PROVIDER_NOT_CONFIGURED" if execution_authorized else "PROVIDER_NOT_EXECUTED"
        return "PROVIDER_NOT_EXECUTED"
    if provider.get("status") == "PROVIDER_SCHEMA_INVALID":
        errors = provider.get("errors") or []
        return "PROVIDER_EVIDENCE_INVALID" if any("EVIDENCE" in str(e.get("code")) for e in errors if isinstance(e, dict)) else "PROVIDER_SCHEMA_INVALID"
    if provider.get("status") == "PROVIDER_ERROR":
        return "PROVIDER_CALL_FAILED"
    if provider.get("status") == "PROVIDER_UNSUPPORTED":
        return "PROVIDER_UNSUPPORTED"
    if support.get("status") == "CONFLICTED" or resolution.get("resolution_type") == "CONFLICTED":
        return "PROVIDER_CONFLICTED"
    if support.get("status") in {"AMBIGUOUS"} or resolution.get("resolution_type") in {"AMBIGUOUS", "CONTEXTUAL_INFERENCE"}:
        return "PROVIDER_AMBIGUOUS"
    if resolution.get("support_status") == "SUPPORTED" and resolution.get("proposal"):
        return "RESOLVED"
    if resolution.get("proposal") and provider.get("status") == "PROVIDER_RESPONSE_RECEIVED":
        return "SEMANTIC_SUPPORT_REJECTED"
    if provider_enabled and provider.get("status") == "NOT_USED":
        return "SOURCE_GAP"
    return "SOURCE_FACT_ABSENT" if provider_enabled else "PROVIDER_NOT_EXECUTED"


def _semantic_rejection_diagnosis(item: dict[str, Any], resolution: dict[str, Any]) -> str:
    """Explain a support rejection without weakening the validator."""
    proposal = resolution.get("proposal") if isinstance(resolution.get("proposal"), dict) else {}
    support = resolution.get("diagnostics", {}).get("support", {}) if isinstance(resolution.get("diagnostics"), dict) else {}
    if not proposal or support.get("status") in {"SUPPORTED", "CONFLICTED", "AMBIGUOUS"}:
        return ""
    if proposal.get("resolution_type") == "CONTEXTUAL_INFERENCE":
        return "CONTEXTUAL_INFERENCE_REQUIRES_AUTHORITY_REVIEW"
    quotes = proposal.get("exact_quotes") if isinstance(proposal.get("exact_quotes"), list) else []
    subject = str(item.get("entity") or item.get("subject_id") or "").strip().lower()
    predicate = str(item.get("predicate") or "").strip().lower()
    joined = " ".join(str(q).lower() for q in quotes)
    if joined and subject and subject in joined and predicate and predicate in joined:
        return "SEMANTIC_VALIDATOR_LEXICAL_LIMITATION"
    return ""


def _retrieval_diagnostic(item: dict[str, Any], candidate_set: dict[str, Any], source_index: dict[str, Any]) -> dict[str, Any]:
    """Explain zero-ranked retrieval without broadening the search scope."""
    anchors = [row for row in (source_index or {}).get("anchors", []) if isinstance(row, dict)]
    texts = [str(row.get("exact_text") or "").lower() for row in anchors]
    scene_terms = ("scene", "int.", "ext.", "室内", "室外", "场景", "地点", "门口", "房间")
    prop_terms = ("桌", "门", "椅", "车", "手机", "箱", "道具", "prop", "table", "door", "phone")
    scene_heading = any(any(term in text for term in scene_terms) for text in texts)
    environment = any(any(term in text for term in ("灯", "光", "雨", "夜", "天气", "室内", "室外", "environment", "weather")) for text in texts)
    prop_mentions = any(any(term in text for term in prop_terms) for text in texts)
    semantic_type = str(item.get("semantic_type") or item.get("subject_type") or "").lower()
    taxonomy_mismatch = semantic_type in {"scene", "prop", "location", "object"} and (scene_heading or environment or prop_mentions)
    return {
        "query_terms": (candidate_set.get("query") or {}).get("expected_value_terms", []) + (candidate_set.get("query") or {}).get("predicate_terms", []),
        "entity_terms": (candidate_set.get("query") or {}).get("entity_aliases", []),
        "predicate_terms": (candidate_set.get("query") or {}).get("predicate_terms", []),
        "source_scope": item.get("source_scope") or [],
        "scene_heading_present": scene_heading,
        "environment_description_present": environment,
        "prop_noun_mentions_present": prop_mentions,
        "ranking_zero_reason": "no anchor matched entity/predicate/expected-value terms",
        "retrieval_taxonomy_mismatch": taxonomy_mismatch,
        "classification_hint": "RETRIEVAL_RECALL_GAP" if taxonomy_mismatch else "LIKELY_SOURCE_FACT_ABSENT",
    }


def _simulated_coverage(current_snapshot: dict[str, Any], accepted: list[dict[str, Any]], requirements: list[dict[str, Any]], source_index: dict[str, Any]) -> dict[str, Any]:
    records = list((current_snapshot or {}).get("records") or [])
    records.extend(proposal_to_candidate_fact(proposal, source_index) for proposal in accepted)
    try:
        from core.fact_coverage_verifier import verify_fact_coverage
        return verify_fact_coverage(records=records, requirements=requirements, source_scope=None)
    except Exception as exc:  # pragma: no cover - defensive report path
        return {"status": "FACT_COVERAGE_INSUFFICIENT", "error": str(exc)[:300]}


def run_authorized_proposer_canary(*, source_material: Any, current_snapshot: dict[str, Any], missing_manifest: dict[str, Any], source_package_id: str = "targeted-source", source_version_id: str = "v1", provider: Callable[[dict[str, Any]], dict[str, Any]] | None = None, model: dict[str, Any] | None = None, max_candidates: int = 8, execution_authorized: bool = False) -> dict[str, Any]:
    """Run a bounded, dry-run-only proposer canary."""
    from core.targeted_missing_fact_extraction import build_source_index
    source_index = build_source_index(source_material, source_package_id=source_package_id, source_version_id=source_version_id)
    items = [item for item in (missing_manifest or {}).get("items", []) if isinstance(item, dict) and item.get("required", True)]
    results: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    for item in items:
        canary_item = {**item, "strict_provider_contract": True}
        candidate_set = retrieve_candidate_anchors(canary_item, source_index, current_snapshot, max_candidates=max_candidates)
        resolution = resolve_semantic_evidence(canary_item, candidate_set, source_index, provider=provider if candidate_set.get("anchors") else None)
        row = {
            "fact_key": item.get("fact_key"),
            "missing_reason": item.get("missing_reason") or "",
            "candidate_anchor_count": candidate_set.get("anchor_count", 0),
            "top_candidate_anchors": [
                {key: anchor.get(key) for key in ("anchor_ref", "ranking_score", "retrieval_reason", "exact_text", "char_start", "char_end")}
                for anchor in (candidate_set.get("anchors") or [])[:3]
            ],
            "provider_called": int(resolution.get("provider_calls") or 0) > 0,
            "provider": (model or {}).get("provider") if model else "",
            "model": (model or {}).get("model_name") if model else "",
            "resolution": resolution,
        }
        row["retrieval_diagnostic"] = _retrieval_diagnostic(item, candidate_set, source_index) if not candidate_set.get("anchors") else {}
        row["proposed_value"] = (resolution.get("proposal") or {}).get("proposed_value") if isinstance(resolution.get("proposal"), dict) else None
        row["supporting_anchor_refs"] = (resolution.get("proposal") or {}).get("supporting_anchor_refs", []) if isinstance(resolution.get("proposal"), dict) else []
        row["exact_quotes"] = (resolution.get("proposal") or {}).get("exact_quotes", []) if isinstance(resolution.get("proposal"), dict) else []
        row["provider_confidence"] = (resolution.get("proposal") or {}).get("confidence") if isinstance(resolution.get("proposal"), dict) else None
        row["exact_evidence_validation"] = (resolution.get("diagnostics") or {}).get("anchor_validation", {})
        row["semantic_support_validation"] = (resolution.get("diagnostics") or {}).get("support", {})
        row["semantic_support_rejection_reason"] = _semantic_rejection_diagnosis(item, resolution)
        row["final_classification"] = _classify(row, provider_enabled=provider is not None, execution_authorized=execution_authorized)
        row["accepted"] = row["final_classification"] == "RESOLVED"
        row["reject_reason"] = "" if row["accepted"] else row["final_classification"]
        if row["accepted"]:
            accepted.append(resolution["proposal"])
        results.append(row)
    provider_calls = sum(1 for row in results if row["provider_called"])
    return {
        "schema_version": SCHEMA_VERSION,
        "dry_run": True,
        "not_fact_snapshot": True,
        "not_authority": True,
        "source_index": source_index,
        "results": results,
        "summary": {
            "required_facts": len(results),
            "provider_calls": provider_calls,
            "provider_calls_maximum": len(results),
            "proposal_count": sum(1 for row in results if row["provider_called"]),
            "exact_evidence_pass": sum(1 for row in results if row["resolution"].get("proposal") and row["exact_evidence_validation"].get("status") == "PASS"),
            "semantic_support_pass": sum(1 for row in results if row["semantic_support_validation"].get("status") == "SUPPORTED"),
            "acceptable_candidates": sum(1 for row in results if row["accepted"]),
            "semantic_validator_lexical_limitations": sum(1 for row in results if row.get("semantic_support_rejection_reason") == "SEMANTIC_VALIDATOR_LEXICAL_LIMITATION"),
            "contextual_inference_authority_reviews": sum(1 for row in results if row.get("semantic_support_rejection_reason") == "CONTEXTUAL_INFERENCE_REQUIRES_AUTHORITY_REVIEW"),
            "classifications": {classification: sum(1 for row in results if row["final_classification"] == classification) for classification in sorted(FINAL_CLASSIFICATIONS)},
        },
        "simulated_coverage": _simulated_coverage(current_snapshot, accepted, items, source_index),
        "persistence": {"fact_snapshot_writes": 0, "authoritative_record_writes": 0, "production_writes": 0},
        "result_fingerprint": _hash(results),
    }


__all__ = ["SCHEMA_VERSION", "build_proposer_system_prompt", "build_proposer_request", "make_llm_provider", "run_authorized_proposer_canary"]
