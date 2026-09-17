"""Targeted semantic evidence resolution over immutable source anchors.

This module deliberately separates retrieval, semantic proposal, and authority
validation.  Retrieval never creates facts.  A proposer (deterministic or an
explicitly injected provider adapter) can only return a proposal; the proposal
is accepted only after exact anchor and semantic-support checks against the
immutable :class:`SourceEvidenceIndex`.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Callable

from core.fact_coverage import fact_key
from core.source_evidence_index import build_source_evidence_index
from core.targeted_missing_fact_extraction import build_source_index, merge_fact_snapshot_records

SCHEMA_VERSION = "targeted_semantic_evidence_resolution_v1"
RESOLUTION_TYPES = (
    "EXPLICIT_DECLARATION",
    "DIRECT_SOURCE_STATEMENT",
    "COREFERENCE_RESOLVED",
    "CONTEXTUAL_INFERENCE",
    "AMBIGUOUS",
    "CONFLICTED",
    "UNSUPPORTED",
)
SUPPORT_STATUSES = ("SUPPORTED", "NOT_SUPPORTED", "AMBIGUOUS", "CONFLICTED")
PROVIDER_PROPOSER_FIELDS = {
    "fact_key", "subject_type", "subject_id", "predicate", "scope",
    "proposed_value", "supporting_anchor_refs", "exact_quotes", "evidence",
    "resolution_type", "confidence", "ambiguity", "conflicting_anchor_refs",
    "reasoning_summary",
}
PROVIDER_PROPOSER_REQUIRED_FIELDS = {
    "fact_key", "subject_type", "subject_id", "predicate", "scope", "proposed_value",
    "resolution_type", "confidence", "ambiguity", "conflicting_anchor_refs", "reasoning_summary",
}
_DECLARATION_RE = re.compile(r"(?:FACT|事实)\s*:", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_WORD_RE = re.compile(r"[\w\-]+", re.UNICODE)
_PRONOUNS = {"他", "她", "它", "其", "该人", "这个人", "the man", "the woman", "he", "she", "they", "it"}
_LEXICAL_STOPWORDS = {"a", "an", "the", "this", "that", "of", "to", "in", "on", "is", "are", "was", "were"}
_VALUE_DECLARATION_RE = re.compile(r"(?:value|值)\s*[=:]\s*[\"']?([^;；,，\s\"']+)", re.IGNORECASE)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _tokens(value: Any) -> list[str]:
    """Return deterministic lexical tokens without requiring a tokenizer."""
    text = _text(value).lower()
    if not text:
        return []
    result: list[str] = []
    for token in _WORD_RE.findall(text):
        if token not in result:
            result.append(token)
    # Whole CJK entities/predicates are high-signal; individual characters are
    # only used when the complete phrase is absent from an anchor.
    cjk = "".join(_CJK_RE.findall(text))
    if cjk and cjk not in result:
        result.append(cjk)
    if len(cjk) > 1:
        for char in cjk:
            if char not in result:
                result.append(char)
    return result


def _aliases(item: dict[str, Any], current_snapshot: dict[str, Any] | None = None) -> list[str]:
    values: list[str] = []
    raw = item.get("aliases") or item.get("entity_aliases") or []
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, (list, tuple, set)):
        values.extend(_text(value) for value in raw)
    entity = _text(item.get("entity") or item.get("subject_id"))
    if entity:
        values.append(entity)
    for row in (current_snapshot or {}).get("records", []) if isinstance(current_snapshot, dict) else []:
        if not isinstance(row, dict) or _text(row.get("subject_id")) != entity:
            continue
        raw_aliases = row.get("aliases") or row.get("entity_aliases") or []
        if isinstance(raw_aliases, str):
            raw_aliases = [raw_aliases]
        if isinstance(raw_aliases, (list, tuple, set)):
            values.extend(_text(value) for value in raw_aliases)
    return list(dict.fromkeys(value for value in values if value))


def _predicate_terms(item: dict[str, Any]) -> list[str]:
    values = [_text(item.get("predicate")), _text(item.get("description"))]
    try:
        from core.fact_requirement_semantics import get_requirement_semantics
        semantics = get_requirement_semantics(item.get("predicate"), requirement=item)
        retrieval = semantics.get("retrieval_semantics") if isinstance(semantics.get("retrieval_semantics"), dict) else {}
        values.extend(retrieval.get("terms") or [])
        values.extend(retrieval.get("aliases") or [])
    except Exception:
        pass
    terms: list[str] = []
    for value in values:
        for token in _tokens(value):
            if token not in terms:
                terms.append(token)
    return terms


def _scope_allowed(item: dict[str, Any], anchor: dict[str, Any]) -> bool:
    allowed = item.get("source_scope")
    if not isinstance(allowed, list) or not allowed:
        return True
    # source_scope may name a surface or a concrete package/version.  A
    # narrative-unit reference is intentionally not treated as a package.
    values = {str(anchor.get(key) or "") for key in ("source_package_id", "source_version_id", "unit_type", "anchor_surface_class")}
    return not values.isdisjoint({str(value) for value in allowed}) or any(str(value) in {"source_material", "immutable_source_material"} for value in allowed)


def _contains_pronoun(text: str) -> bool:
    lower = text.lower()
    return any(token in lower for token in _PRONOUNS)


def retrieve_candidate_anchors(
    manifest_item: dict[str, Any],
    source_index: dict[str, Any],
    current_snapshot: dict[str, Any] | None = None,
    *,
    max_candidates: int = 8,
) -> dict[str, Any]:
    """Rank only potentially relevant immutable anchors for one missing fact."""
    item = manifest_item if isinstance(manifest_item, dict) else {}
    aliases = _aliases(item, current_snapshot)
    entity_terms = [alias.lower() for alias in aliases]
    entity_terms.extend(token for alias in aliases for token in _tokens(alias) if len(token) > 1 and token not in _LEXICAL_STOPWORDS)
    entity_terms = list(dict.fromkeys(entity_terms))
    predicate_terms = _predicate_terms(item)
    try:
        from core.fact_requirement_semantics import get_requirement_semantics
        retrieval = get_requirement_semantics(item.get("predicate"), requirement=item).get("retrieval_semantics") or {}
        source_surfaces = [str(value) for value in retrieval.get("source_surfaces") or []]
    except Exception:
        source_surfaces = []
    expected_terms = _tokens(item.get("expected_value"))
    query_terms = list(dict.fromkeys(entity_terms + predicate_terms + expected_terms))
    anchors = [row for row in (source_index or {}).get("anchors", []) if isinstance(row, dict)]
    ranked: list[dict[str, Any]] = []
    for index, anchor in enumerate(anchors):
        if not _scope_allowed(item, anchor):
            continue
        text = _text(anchor.get("exact_text"))
        lower = text.lower()
        entity_matches = [term for term in entity_terms if term and term.lower() in lower]
        predicate_matches = [term for term in predicate_terms if term and term.lower() in lower]
        expected_matches = [term for term in expected_terms if term and term.lower() in lower]
        surface_match = [surface for surface in source_surfaces if surface.lower() in str(anchor.get("anchor_surface_class") or "").lower() or surface.lower() in str(anchor.get("unit_type") or "").lower()]
        # Surface taxonomy is a ranking tie-breaker only; it must never turn
        # every narrative anchor into a candidate when entity/predicate/value
        # terms are absent.
        score = len(entity_matches) * 5 + len(predicate_matches) * 2 + len(expected_matches) * 3
        if score > 0:
            score += len(surface_match)
        # A nearby anchor can be useful for pronoun resolution, but it must be
        # explicitly marked as context and never promoted on its own.
        coreference_to = None
        if not entity_matches and _contains_pronoun(text) and (expected_matches or predicate_matches) and index > 0:
            # Resolve only a single, explicit antecedent in the immediately
            # preceding anchor.  Multiple antecedents stay unresolved rather
            # than guessing across a wider narrative window.
            previous = _text(anchors[index - 1].get("exact_text"))
            antecedents = [alias for alias in aliases if alias and alias.lower() in previous.lower()]
            if len(set(antecedents)) == 1:
                coreference_to = antecedents[0]
                score = max(score, len(predicate_matches) * 2 + len(expected_matches) * 3 + 1)
        if score <= 0:
            continue
        ranked.append({
            "anchor_ref": anchor.get("anchor_ref"),
            "exact_text": anchor.get("exact_text"),
            "source_package_id": anchor.get("source_package_id"),
            "source_version_id": anchor.get("source_version_id"),
            "source_raw_hash": anchor.get("source_raw_hash"),
            "char_start": anchor.get("char_start"),
            "char_end": anchor.get("char_end"),
            "byte_start": anchor.get("byte_start"),
            "byte_end": anchor.get("byte_end"),
            "scope": _text(item.get("scope") or "global"),
            "retrieval_reason": "entity_and_predicate_overlap" if entity_matches and predicate_matches else "entity_overlap" if entity_matches else "surface_and_semantic_overlap" if surface_match else "predicate_or_value_overlap",
            "lexical_entity_matches": entity_matches,
            "lexical_predicate_matches": predicate_matches,
            "lexical_expected_value_matches": expected_matches,
            "ranking_score": score,
            "semantic_surface_matches": surface_match,
        })
        if coreference_to:
            ranked[-1]["retrieval_reason"] = "coreference_context"
            ranked[-1]["coreference_resolved_to"] = coreference_to
    ranked.sort(key=lambda row: (-int(row["ranking_score"]), int(row.get("char_start") or 0), str(row.get("anchor_ref") or "")))
    return {
        "schema_version": "candidate_anchor_set_v1",
        "fact_key": _text(item.get("fact_key")) or fact_key(item),
        "anchor_count": min(len(ranked), max_candidates),
        "anchors": ranked[: max(0, int(max_candidates))],
        "query": {"entity_aliases": aliases, "predicate_terms": predicate_terms, "expected_value_terms": expected_terms, "source_surfaces": source_surfaces, "semantic_registry": True},
        "source_evidence_index_fingerprint": (source_index or {}).get("evidence_index_fingerprint"),
        "source_raw_hash": (source_index or {}).get("source_raw_hash"),
    }


def _anchor_map(source_index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("anchor_ref")): row for row in (source_index or {}).get("anchors", []) if isinstance(row, dict) and row.get("anchor_ref")}


def validate_candidate_anchor_set(candidate_set: dict[str, Any], source_index: dict[str, Any], manifest_item: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    by_ref = _anchor_map(source_index)
    # Carry retrieval-only context markers (for example a conservative
    # ``coreference_resolved_to`` annotation) into support validation while
    # keeping the immutable anchor text/offsets sourced from source_index.
    for row in candidate_set.get("anchors", []) if isinstance(candidate_set, dict) else []:
        ref = _text(row.get("anchor_ref")) if isinstance(row, dict) else ""
        if ref in by_ref and isinstance(row, dict):
            by_ref[ref] = {**by_ref[ref], **{key: row[key] for key in ("coreference_resolved_to", "scope") if key in row}}
    if _text(candidate_set.get("fact_key")) != (_text(manifest_item.get("fact_key")) or fact_key(manifest_item)):
        errors.append({"code": "ANCHOR_SET_OUT_OF_SCOPE", "message": "Candidate anchors are not scoped to the manifest fact."})
    for row in candidate_set.get("anchors", []) if isinstance(candidate_set, dict) else []:
        if not isinstance(row, dict) or _text(row.get("anchor_ref")) not in by_ref:
            errors.append({"code": "SOURCE_LOCATOR_INVALID", "message": "Candidate anchor is absent from the immutable source index."})
            continue
        anchor = by_ref[_text(row.get("anchor_ref"))]
        if row.get("exact_text") != anchor.get("exact_text"):
            errors.append({"code": "ANCHOR_EXCERPT_MISMATCH", "message": "Candidate anchor text differs from immutable source."})
        if row.get("source_raw_hash") != anchor.get("source_raw_hash") or row.get("source_raw_hash") != source_index.get("source_raw_hash"):
            errors.append({"code": "ANCHOR_SOURCE_HASH_MISMATCH", "message": "Candidate anchor hash differs from immutable source."})
        for field in ("char_start", "char_end", "byte_start", "byte_end"):
            if row.get(field) != anchor.get(field):
                errors.append({"code": "ANCHOR_OFFSET_MISMATCH", "message": f"Candidate anchor {field} differs from immutable source."})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


def _direct_support(item: dict[str, Any], anchor: dict[str, Any], *, aliases: list[str]) -> dict[str, Any]:
    text = _text(anchor.get("exact_text"))
    lower = text.lower()
    entity = _text(item.get("entity") or item.get("subject_id"))
    entity_present = any(alias.lower() in lower for alias in aliases if alias) or bool(anchor.get("coreference_resolved_to"))
    expected = item.get("expected_value")
    if expected is None:
        declaration = _VALUE_DECLARATION_RE.search(text)
        if declaration:
            expected = declaration.group(1)
    expected_text = _text(expected)
    expected_present = bool(expected_text and expected_text.lower() in lower)
    predicate_terms = _predicate_terms(item)
    predicate_present = any(term and term.lower() in lower for term in predicate_terms)
    declaration = bool(_DECLARATION_RE.search(text))
    if declaration and entity_present and expected is not None and (item.get("expected_value") is None or expected_present):
        return {"status": "SUPPORTED", "resolution_type": "EXPLICIT_DECLARATION", "value": expected, "reason": "explicit structured declaration"}
    if entity_present and expected_present and predicate_present:
        return {"status": "SUPPORTED", "resolution_type": "COREFERENCE_RESOLVED" if anchor.get("coreference_resolved_to") else "DIRECT_SOURCE_STATEMENT", "value": expected, "reason": "entity, predicate and expected value co-occur"}
    if entity_present and expected_present:
        return {"status": "AMBIGUOUS", "resolution_type": "AMBIGUOUS", "value": expected, "reason": "entity and value occur without a predicate signal"}
    return {"status": "NOT_SUPPORTED", "resolution_type": "UNSUPPORTED", "value": expected, "reason": "anchor does not explicitly support requested value"}


def validate_semantic_support(proposal: dict[str, Any], candidate_set: dict[str, Any], source_index: dict[str, Any], manifest_item: dict[str, Any]) -> dict[str, Any]:
    """Validate support independently from evidence existence."""
    refs = proposal.get("supporting_anchor_refs") if isinstance(proposal, dict) else []
    quotes = proposal.get("exact_quotes") if isinstance(proposal, dict) else []
    evidence_rows = proposal.get("evidence") if isinstance(proposal, dict) else []
    if isinstance(evidence_rows, list) and evidence_rows:
        refs = [row.get("anchor_ref") for row in evidence_rows if isinstance(row, dict)]
        quotes = [row.get("quote_span") for row in evidence_rows if isinstance(row, dict)]
    refs = refs if isinstance(refs, list) else []
    quotes = quotes if isinstance(quotes, list) else []
    by_ref = _anchor_map(source_index)
    # Carry retrieval-only context markers (for example a conservative
    # ``coreference_resolved_to`` annotation) into support validation while
    # keeping immutable text/offsets sourced from source_index.
    for row in candidate_set.get("anchors", []) if isinstance(candidate_set, dict) else []:
        ref = _text(row.get("anchor_ref")) if isinstance(row, dict) else ""
        if ref in by_ref and isinstance(row, dict):
            by_ref[ref] = {**by_ref[ref], **{key: row[key] for key in ("coreference_resolved_to", "scope") if key in row}}
    errors: list[dict[str, str]] = []
    expected_identity = {
        "fact_key": _text(manifest_item.get("fact_key")) or fact_key(manifest_item),
        "subject_type": _text(manifest_item.get("subject_type") or manifest_item.get("semantic_type")),
        "subject_id": _text(manifest_item.get("entity") or manifest_item.get("subject_id")),
        "predicate": _text(manifest_item.get("predicate")),
        "scope": _text(manifest_item.get("scope") or "global"),
    }
    actual_identity = {
        "fact_key": _text(proposal.get("fact_key")),
        "subject_type": _text(proposal.get("subject_type")),
        "subject_id": _text(proposal.get("subject_id")),
        "predicate": _text(proposal.get("predicate")),
        "scope": _text(proposal.get("scope") or "global"),
    }
    for field, expected in expected_identity.items():
        if expected and actual_identity.get(field) != expected:
            errors.append({"code": "PROPOSAL_OUT_OF_SCOPE", "message": f"Proposal {field} does not match MissingFactManifest."})
    if _text(proposal.get("resolution_type")) not in RESOLUTION_TYPES:
        errors.append({"code": "PROPOSAL_RESOLUTION_TYPE_INVALID", "message": "Proposal resolution_type is not supported."})
    if not refs:
        errors.append({"code": "SUPPORT_ANCHOR_REQUIRED", "message": "Semantic proposal must cite at least one anchor."})
    for ref in refs:
        if _text(ref) not in by_ref:
            errors.append({"code": "SUPPORT_ANCHOR_UNKNOWN", "message": f"Unknown supporting anchor: {ref}"})
    if quotes and len(quotes) != len(refs):
        errors.append({"code": "SUPPORT_QUOTE_COUNT_MISMATCH", "message": "exact_quotes must align one-to-one with anchor refs."})
    for index, ref in enumerate(refs):
        if _text(ref) not in by_ref:
            continue
        expected_quote = by_ref[_text(ref)].get("exact_text")
        quote = quotes[index] if index < len(quotes) else ""
        # V2 providers return a substring; the program still resolves the
        # immutable full anchor and computes offsets.  A repeated span is not
        # accepted without an explicit disambiguator.
        if not isinstance(quote, str) or not quote or quote not in str(expected_quote or ""):
            errors.append({"code": "SUPPORT_QUOTE_NOT_SUBSTRING", "message": f"Quote span for {ref} is not a substring of the immutable anchor."})
        elif str(expected_quote).count(quote) > 1:
            errors.append({"code": "SUPPORT_QUOTE_AMBIGUOUS", "message": f"Quote span for {ref} occurs multiple times; disambiguation is required."})
    if errors:
        return {"status": "NOT_SUPPORTED", "errors": errors}
    aliases = _aliases(manifest_item)
    support_item = {**manifest_item, "expected_value": proposal.get("proposed_value")}
    outcomes = [_direct_support(support_item, by_ref[_text(ref)], aliases=aliases) for ref in refs]
    statuses = {outcome["status"] for outcome in outcomes}
    if "CONFLICTED" in statuses or len({_canonical(outcome.get("value")) for outcome in outcomes}) > 1:
        status = "CONFLICTED"
    elif "AMBIGUOUS" in statuses:
        status = "AMBIGUOUS"
    elif all(outcome["status"] == "SUPPORTED" for outcome in outcomes):
        status = "SUPPORTED"
    else:
        status = "NOT_SUPPORTED"
    return {"status": status, "errors": [], "anchor_outcomes": outcomes}


def validate_provider_proposal_shape(
    proposal: Any,
    request: dict[str, Any],
) -> dict[str, Any]:
    """Validate the proposer envelope before semantic validation.

    The provider is never allowed to create source evidence.  This check is
    intentionally independent of ``validate_semantic_support`` so malformed
    or out-of-scope responses are classified as provider contract failures.
    """
    errors: list[dict[str, str]] = []
    if not isinstance(proposal, dict):
        return {"status": "FAIL", "errors": [{"code": "PROVIDER_SCHEMA_INVALID", "message": "proposal must be an object"}]}
    keys = set(proposal)
    strict = bool(request.get("strict_provider_contract"))
    # Existing deterministic/provider-injection callers predate V1's full
    # diagnostics envelope.  Keep that public resolver seam compatible while
    # the authorized canary opts into the strict all-fields contract.
    required_fields = PROVIDER_PROPOSER_REQUIRED_FIELDS if strict else {
        "fact_key", "subject_type", "subject_id", "predicate", "scope", "proposed_value",
        "supporting_anchor_refs", "exact_quotes", "resolution_type", "confidence",
    }
    missing = sorted(required_fields - keys)
    if strict and "evidence" not in keys and not {"supporting_anchor_refs", "exact_quotes"}.issubset(keys):
        errors.append({"code": "PROVIDER_SCHEMA_INVALID", "message": "evidence is required (legacy supporting_anchor_refs/exact_quotes pair may be replayed only for compatibility)"})
    extra = sorted(keys - PROVIDER_PROPOSER_FIELDS)
    if missing:
        errors.append({"code": "PROVIDER_SCHEMA_INVALID", "message": f"missing fields: {','.join(missing)}"})
    if extra:
        errors.append({"code": "PROVIDER_SCHEMA_INVALID", "message": f"forbidden fields: {','.join(extra)}"})
    fact = request.get("fact") if isinstance(request.get("fact"), dict) else {}
    expected = {
        "fact_key": _text(fact.get("fact_key")),
        "subject_type": _text(fact.get("subject_type") or fact.get("semantic_type")),
        "subject_id": _text(fact.get("entity") or fact.get("subject_id")),
        "predicate": _text(fact.get("predicate")),
        "scope": _text(fact.get("scope") or "global"),
    }
    for field, value in expected.items():
        if value and _text(proposal.get(field) or ("global" if field == "scope" else "")) != value:
            errors.append({"code": "PROVIDER_IDENTITY_MISMATCH", "message": f"{field} does not match manifest"})
    resolution = _text(proposal.get("resolution_type"))
    if resolution not in RESOLUTION_TYPES:
        errors.append({"code": "PROVIDER_SCHEMA_INVALID", "message": "invalid resolution_type"})
    refs = proposal.get("supporting_anchor_refs")
    quotes = proposal.get("exact_quotes")
    evidence_rows = proposal.get("evidence")
    conflicts = proposal.get("conflicting_anchor_refs")
    if strict and "evidence" in proposal:
        if not isinstance(evidence_rows, list) or not evidence_rows:
            errors.append({"code": "PROVIDER_SCHEMA_INVALID", "message": "evidence must be a non-empty object array"})
        for row in evidence_rows or []:
            if not isinstance(row, dict) or set(row) != {"anchor_ref", "quote_span"} or not isinstance(row.get("anchor_ref"), str) or not isinstance(row.get("quote_span"), str) or not row.get("quote_span"):
                errors.append({"code": "PROVIDER_SCHEMA_INVALID", "message": "evidence items require anchor_ref and quote_span only"})
        refs = [row.get("anchor_ref") for row in evidence_rows or [] if isinstance(row, dict)]
        quotes = [row.get("quote_span") for row in evidence_rows or [] if isinstance(row, dict)]
    else:
        if not isinstance(refs, list) or not all(isinstance(ref, str) and ref.strip() for ref in refs):
            errors.append({"code": "PROVIDER_SCHEMA_INVALID", "message": "supporting_anchor_refs must be a string array"})
        if not isinstance(quotes, list) or not all(isinstance(quote, str) for quote in quotes):
            errors.append({"code": "PROVIDER_SCHEMA_INVALID", "message": "exact_quotes must be a string array"})
        if isinstance(refs, list) and isinstance(quotes, list) and len(refs) != len(quotes):
            errors.append({"code": "PROVIDER_SCHEMA_INVALID", "message": "exact_quotes must align with supporting_anchor_refs"})
    if conflicts is not None and (not isinstance(conflicts, list) or not all(isinstance(ref, str) for ref in conflicts)):
        errors.append({"code": "PROVIDER_SCHEMA_INVALID", "message": "conflicting_anchor_refs must be a string array"})
    confidence = proposal.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        errors.append({"code": "PROVIDER_SCHEMA_INVALID", "message": "confidence must be between 0 and 1"})
    if strict and not isinstance(proposal.get("ambiguity"), bool):
        errors.append({"code": "PROVIDER_SCHEMA_INVALID", "message": "ambiguity must be boolean"})
    if strict and not isinstance(proposal.get("reasoning_summary"), str):
        errors.append({"code": "PROVIDER_SCHEMA_INVALID", "message": "reasoning_summary must be a string"})
    candidate_refs = {
        _text(row.get("anchor_ref")) for row in (request.get("candidate_anchors") or [])
        if isinstance(row, dict) and _text(row.get("anchor_ref"))
    }
    for ref in (refs or []) + (conflicts or []):
        if ref not in candidate_refs:
            errors.append({"code": "PROVIDER_EVIDENCE_INVALID", "message": f"anchor ref outside candidate set: {ref}"})
    for ref, quote in zip(refs or [], quotes or []):
        anchor = next((row for row in request.get("candidate_anchors") or [] if isinstance(row, dict) and row.get("anchor_ref") == ref), None)
        if anchor is not None and (not isinstance(quote, str) or quote not in str(anchor.get("exact_text") or "")):
            errors.append({"code": "PROVIDER_EVIDENCE_INVALID", "message": f"quote span is not contained in immutable anchor for {ref}"})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


def _provider_proposal(provider: Callable[..., dict[str, Any]], request: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    try:
        response = provider(request)
    except Exception as exc:  # provider failure is always fail-closed
        return None, {"status": "PROVIDER_ERROR", "error": str(exc)[:500], "provider_calls": 1}
    shape = validate_provider_proposal_shape(response, request)
    if shape["status"] != "PASS":
        return None, {"status": "PROVIDER_SCHEMA_INVALID", "provider_calls": 1, "errors": shape["errors"]}
    if request.get("strict_provider_contract") and isinstance(response, dict) and isinstance(response.get("evidence"), list):
        # Normalize the new provider-owned span envelope into the existing
        # resolver seam.  The full immutable anchor remains program-owned.
        response = {
            **response,
            "supporting_anchor_refs": [row.get("anchor_ref") for row in response["evidence"] if isinstance(row, dict)],
            "exact_quotes": [row.get("quote_span") for row in response["evidence"] if isinstance(row, dict)],
        }
    return response, {"status": "PROVIDER_RESPONSE_RECEIVED", "provider_calls": 1}


def resolve_semantic_evidence(
    manifest_item: dict[str, Any],
    candidate_set: dict[str, Any],
    source_index: dict[str, Any],
    *,
    provider: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve one candidate set into a proposal, never directly into a fact."""
    anchor_validation = validate_candidate_anchor_set(candidate_set, source_index, manifest_item)
    if anchor_validation["status"] != "PASS":
        return {"schema_version": "semantic_fact_proposal_v1", "fact_key": manifest_item.get("fact_key"), "proposal": None, "resolution_type": "UNSUPPORTED", "support_status": "NOT_SUPPORTED", "diagnostics": anchor_validation, "provider_calls": 0}
    anchors = candidate_set.get("anchors") or []
    aliases = _aliases(manifest_item)
    outcomes = [_direct_support(manifest_item, row, aliases=aliases) for row in anchors]
    supported = [row for row, outcome in zip(anchors, outcomes) if outcome["status"] == "SUPPORTED"]
    provider_calls = 0
    provider_meta: dict[str, Any] = {"status": "NOT_USED", "provider_calls": 0}
    proposal: dict[str, Any] | None = None
    if supported:
        supported_outcomes = [_direct_support(manifest_item, row, aliases=aliases) for row in supported]
        resolution_type = supported_outcomes[0]["resolution_type"]
        resolved_value = supported_outcomes[0].get("value")
        values = {_canonical(outcome.get("value")) for outcome in supported_outcomes}
        if len(values) > 1:
            return {"schema_version": "semantic_fact_proposal_v1", "fact_key": manifest_item.get("fact_key"), "proposal": None, "resolution_type": "CONFLICTED", "support_status": "CONFLICTED", "diagnostics": {"anchor_validation": anchor_validation, "provider": provider_meta, "support": {"status": "CONFLICTED", "anchor_outcomes": supported_outcomes}}, "provider_calls": provider_calls}
        proposal = {"fact_key": manifest_item.get("fact_key"), "subject_type": manifest_item.get("subject_type"), "subject_id": manifest_item.get("entity") or manifest_item.get("subject_id"), "predicate": manifest_item.get("predicate"), "proposed_value": manifest_item.get("expected_value"), "scope": manifest_item.get("scope") or "global", "supporting_anchor_refs": [row.get("anchor_ref") for row in supported], "exact_quotes": [row.get("exact_text") for row in supported], "resolution_type": resolution_type, "confidence": 1.0 if resolution_type == "EXPLICIT_DECLARATION" else 0.9, "ambiguity": False, "conflicting_anchor_refs": []}
        proposal["proposed_value"] = resolved_value
    elif provider is not None and anchors:
        request = {"fact": copy.deepcopy(manifest_item), "candidate_anchors": copy.deepcopy(anchors), "source_evidence_index_fingerprint": source_index.get("evidence_index_fingerprint"), "strict_provider_contract": bool(manifest_item.get("strict_provider_contract"))}
        proposal, provider_meta = _provider_proposal(provider, request)
        provider_calls = int(provider_meta.get("provider_calls") or 0)
    if proposal is None:
        has_entity = any(outcome.get("status") == "AMBIGUOUS" for outcome in outcomes)
        return {"schema_version": "semantic_fact_proposal_v1", "fact_key": manifest_item.get("fact_key"), "proposal": None, "resolution_type": "AMBIGUOUS" if has_entity else "UNSUPPORTED", "support_status": "AMBIGUOUS" if has_entity else "NOT_SUPPORTED", "diagnostics": {"anchor_validation": anchor_validation, "provider": provider_meta, "anchor_outcomes": outcomes}, "provider_calls": provider_calls}
    if _text(proposal.get("resolution_type")) not in {"EXPLICIT_DECLARATION", "DIRECT_SOURCE_STATEMENT", "COREFERENCE_RESOLVED"}:
        return {"schema_version": "semantic_fact_proposal_v1", "fact_key": manifest_item.get("fact_key"), "proposal": None, "resolution_type": _text(proposal.get("resolution_type")) or "UNSUPPORTED", "support_status": "NOT_SUPPORTED", "diagnostics": {"anchor_validation": anchor_validation, "provider": provider_meta, "provider_resolution_type": _text(proposal.get("resolution_type")) or "UNSUPPORTED", "reason": "resolution type requires a separate semantic authority review"}, "provider_calls": provider_calls}
    support = validate_semantic_support(proposal, candidate_set, source_index, manifest_item)
    if support["status"] != "SUPPORTED":
        return {"schema_version": "semantic_fact_proposal_v1", "fact_key": manifest_item.get("fact_key"), "proposal": None, "resolution_type": "CONFLICTED" if support["status"] == "CONFLICTED" else "AMBIGUOUS" if support["status"] == "AMBIGUOUS" else "UNSUPPORTED", "support_status": support["status"], "diagnostics": {"anchor_validation": anchor_validation, "provider": provider_meta, "support": support}, "provider_calls": provider_calls}
    return {"schema_version": "semantic_fact_proposal_v1", "fact_key": manifest_item.get("fact_key"), "proposal": proposal, "resolution_type": proposal.get("resolution_type"), "support_status": "SUPPORTED", "diagnostics": {"anchor_validation": anchor_validation, "provider": provider_meta, "support": support}, "provider_calls": provider_calls}


def proposal_to_candidate_fact(proposal: dict[str, Any], source_index: dict[str, Any]) -> dict[str, Any]:
    """Convert only a verified proposal into the existing FactSnapshot shape."""
    refs = proposal.get("supporting_anchor_refs") or []
    by_ref = _anchor_map(source_index)
    evidence = []
    for ref in refs:
        anchor = by_ref.get(_text(ref))
        if not anchor:
            continue
        evidence.append({"anchor_ref": anchor.get("anchor_ref"), "excerpt": anchor.get("exact_text"), "char_start": anchor.get("char_start"), "char_end": anchor.get("char_end"), "byte_start": anchor.get("byte_start"), "byte_end": anchor.get("byte_end"), "source_raw_hash": anchor.get("source_raw_hash"), "verified": True})
    return {"fact_id": f"SEMANTIC_{_hash({'fact_key': proposal.get('fact_key'), 'value': proposal.get('proposed_value'), 'refs': refs})[:16]}", "subject_type": proposal.get("subject_type"), "subject_id": proposal.get("subject_id"), "predicate": proposal.get("predicate"), "value": copy.deepcopy(proposal.get("proposed_value")), "scope": proposal.get("scope") or "global", "authority": "source_text", "status": "confirmed", "confidence": min(float(proposal.get("confidence") or 0.0), 1.0), "evidence": evidence}


def merge_resolved_proposals(current_snapshot: dict[str, Any], resolution_result: dict[str, Any], missing_manifest: dict[str, Any]) -> dict[str, Any]:
    """Send only support-validated proposals through the existing merge policy."""
    source_index = resolution_result.get("source_index") if isinstance(resolution_result, dict) else {}
    candidates = []
    for row in (resolution_result or {}).get("results", []):
        resolution = row.get("resolution") if isinstance(row, dict) else {}
        proposal = resolution.get("proposal") if isinstance(resolution, dict) else None
        if proposal and resolution.get("support_status") == "SUPPORTED":
            candidates.append(proposal_to_candidate_fact(proposal, source_index))
    return merge_fact_snapshot_records(current_snapshot or {}, candidates, missing_manifest or {}, source_index or {})


def run_targeted_semantic_evidence_resolution(
    source_material: Any,
    current_snapshot: dict[str, Any],
    missing_manifest: dict[str, Any],
    *,
    source_package_id: str = "targeted-source",
    source_version_id: str = "v1",
    provider: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source_index = build_source_index(source_material, source_package_id=source_package_id, source_version_id=source_version_id)
    items = [item for item in (missing_manifest or {}).get("items", []) if isinstance(item, dict)]
    results = []
    for item in items:
        candidate_set = retrieve_candidate_anchors(item, source_index, current_snapshot)
        resolution = resolve_semantic_evidence(item, candidate_set, source_index, provider=provider)
        results.append({"fact_key": item.get("fact_key"), "candidate_anchor_set": candidate_set, "resolution": resolution})
    counts = {key: sum(1 for row in results if row["resolution"].get("resolution_type") == key) for key in RESOLUTION_TYPES}
    result = {"schema_version": SCHEMA_VERSION, "source_index": source_index, "results": results, "counts": counts, "provider_calls": sum(int(row["resolution"].get("provider_calls") or 0) for row in results), "result_fingerprint": _hash(results)}
    result["merge"] = merge_resolved_proposals(current_snapshot or {}, result, missing_manifest or {})
    # Reuse the existing targeted evaluator; semantic resolution never owns a
    # second coverage threshold or ScriptIR decision.
    try:
        from core.fact_coverage_verifier import verify_fact_coverage
        requirements = list(items)
        result["coverage_after"] = verify_fact_coverage(records=result["merge"]["snapshot"].get("records", []), requirements=requirements, source_scope=None)
    except Exception as exc:
        result["coverage_after"] = {"status": "FACT_COVERAGE_INSUFFICIENT", "script_ir_gate": {"allowed": False, "status": "BLOCKED_PENDING_TARGETED_MISSING_FACTS"}, "diagnostics_error": str(exc)[:300]}
    return result


__all__ = [
    "SCHEMA_VERSION", "RESOLUTION_TYPES", "SUPPORT_STATUSES", "PROVIDER_PROPOSER_FIELDS", "retrieve_candidate_anchors", "validate_candidate_anchor_set", "validate_provider_proposal_shape", "validate_semantic_support", "resolve_semantic_evidence", "proposal_to_candidate_fact", "merge_resolved_proposals", "run_targeted_semantic_evidence_resolution",
]
