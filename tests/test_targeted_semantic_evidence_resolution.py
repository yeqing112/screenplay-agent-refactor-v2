from core.source_evidence_index import build_source_evidence_index
from core.targeted_semantic_evidence_resolution import (
    RESOLUTION_TYPES,
    resolve_semantic_evidence,
    retrieve_candidate_anchors,
    run_targeted_semantic_evidence_resolution,
    validate_candidate_anchor_set,
    validate_semantic_support,
)


def _source():
    return "Alice is red.\n\nShe carries the red key.\n\nBob enters the blue room.\n"


def _index():
    return build_source_evidence_index(_source().encode(), source_package_id="pkg", source_version_id="v1")


def _item(**overrides):
    value = {"fact_key": "character|Alice|is|global", "semantic_type": "character", "subject_type": "character", "entity": "Alice", "subject_id": "Alice", "predicate": "is", "scope": "global", "expected_value": "red", "required": True}
    value.update(overrides)
    return value


def test_retrieval_ranks_entity_and_predicate_matches_without_generating_fact():
    result = retrieve_candidate_anchors(_item(), _index())
    assert result["anchor_count"] >= 1
    assert result["anchors"][0]["anchor_ref"] == "E0001"
    assert result["anchors"][0]["exact_text"] == "Alice is red.\n"
    assert result["anchors"][0]["source_raw_hash"] == _index()["source_raw_hash"]
    assert "proposal" not in result


def test_byte_source_preserves_immutable_line_endings_and_hash():
    raw = b"Alice is red.\r\n\r\nAlice is blue.\r\n"
    from core.targeted_missing_fact_extraction import build_source_index
    import hashlib
    index = build_source_index(raw, source_package_id="pkg", source_version_id="v1")
    assert index["source_raw_hash"] == hashlib.sha256(raw).hexdigest()
    assert index["anchors"][0]["exact_text"] == "Alice is red.\r\n"
    assert index["anchors"][1]["byte_start"] == len(b"Alice is red.\r\n\r\n")


def test_direct_natural_language_statement_resolves_with_exact_quote():
    result = run_targeted_semantic_evidence_resolution(_source(), {}, {"items": [_item()]}, source_package_id="pkg", source_version_id="v1")
    resolution = result["results"][0]["resolution"]
    assert resolution["support_status"] == "SUPPORTED"
    assert resolution["resolution_type"] == "DIRECT_SOURCE_STATEMENT"
    assert resolution["proposal"]["exact_quotes"] == ["Alice is red.\n"]
    assert result["provider_calls"] == 0
    assert result["merge"]["changed"] is True
    assert result["coverage_after"]["status"] == "FACT_COVERAGE_SUFFICIENT"
    assert result["coverage_after"]["script_ir_gate"]["allowed"] is True


def test_alias_retrieval_and_simple_pronoun_resolution_are_conservative():
    item = _item(fact_key="character|the woman|carries|global", entity="the woman", subject_id="the woman", predicate="carries", expected_value="red key", aliases=["the woman"])
    source = "the woman enters the red room.\n\nShe carries the red key.\n"
    result = run_targeted_semantic_evidence_resolution(source, {}, {"items": [item]}, source_package_id="pkg", source_version_id="v1")
    rows = result["results"][0]["candidate_anchor_set"]["anchors"]
    assert any(row.get("coreference_resolved_to") == "the woman" for row in rows)
    assert result["results"][0]["resolution"]["resolution_type"] == "COREFERENCE_RESOLVED"


def test_unknown_anchor_and_forged_quote_are_rejected():
    index = _index()
    item = _item()
    candidate_set = retrieve_candidate_anchors(item, index)
    candidate_set["anchors"][0]["anchor_ref"] = "E9999"
    assert validate_candidate_anchor_set(candidate_set, index, item)["status"] == "FAIL"
    forged = {"fact_key": item["fact_key"], "subject_type": "character", "subject_id": "Alice", "predicate": "is", "scope": "global", "proposed_value": "red", "supporting_anchor_refs": ["E0001"], "exact_quotes": ["forged quote"], "resolution_type": "DIRECT_SOURCE_STATEMENT", "confidence": 1.0}
    assert validate_semantic_support(forged, retrieve_candidate_anchors(item, index), index, item)["status"] == "NOT_SUPPORTED"


def test_quote_exists_but_does_not_support_value_is_rejected():
    index = _index()
    item = _item(expected_value="green")
    candidate_set = retrieve_candidate_anchors(item, index)
    proposal = {"fact_key": item["fact_key"], "subject_type": "character", "subject_id": "Alice", "predicate": "is", "proposed_value": "green", "supporting_anchor_refs": ["E0001"], "exact_quotes": [index["anchors"][0]["exact_text"]], "resolution_type": "DIRECT_SOURCE_STATEMENT", "confidence": 1.0}
    assert validate_semantic_support(proposal, candidate_set, index, item)["status"] == "NOT_SUPPORTED"


def test_provider_cannot_introduce_forged_anchor_and_timeout_is_fail_closed():
    index = _index()
    item = _item(expected_value=None)
    candidate_set = retrieve_candidate_anchors(item, index)

    def forged(_request):
        return {"fact_key": item["fact_key"], "subject_type": "character", "subject_id": "Alice", "predicate": "color", "proposed_value": "red", "supporting_anchor_refs": ["E9999"], "exact_quotes": ["not source"], "resolution_type": "DIRECT_SOURCE_STATEMENT", "confidence": 0.99}

    rejected = resolve_semantic_evidence(item, candidate_set, index, provider=forged)
    assert rejected["proposal"] is None and rejected["provider_calls"] == 1

    def timeout(_request):
        raise TimeoutError("timeout")

    failed = resolve_semantic_evidence(item, candidate_set, index, provider=timeout)
    assert failed["proposal"] is None and failed["provider_calls"] == 1
    assert failed["diagnostics"]["provider"]["status"] == "PROVIDER_ERROR"


def test_provider_proposal_is_verified_against_immutable_anchor_and_scope():
    index = _index()
    item = _item(expected_value=None)
    candidate_set = retrieve_candidate_anchors(item, index)

    def proposer(request):
        anchor = request["candidate_anchors"][0]
        return {"fact_key": item["fact_key"], "subject_type": "character", "subject_id": "Alice", "predicate": "is", "scope": "global", "proposed_value": "red", "supporting_anchor_refs": [anchor["anchor_ref"]], "exact_quotes": [anchor["exact_text"]], "resolution_type": "DIRECT_SOURCE_STATEMENT", "confidence": 0.8}

    resolved = resolve_semantic_evidence(item, candidate_set, index, provider=proposer)
    assert resolved["support_status"] == "SUPPORTED"
    assert resolved["proposal"]["proposed_value"] == "red"


def test_existing_authoritative_fact_is_never_overwritten_by_semantic_proposal():
    index = _index()
    item = _item()
    candidate_set = retrieve_candidate_anchors(item, index)
    existing = [{"subject_type": "character", "subject_id": "Alice", "predicate": "is", "scope": "global", "value": "blue", "authority": "source_text", "status": "confirmed", "evidence": [{"anchor_ref": "E0001", "excerpt": index["anchors"][0]["exact_text"], "source_raw_hash": index["source_raw_hash"], "verified": True}]}]
    from core.targeted_semantic_evidence_resolution import merge_resolved_proposals
    result = run_targeted_semantic_evidence_resolution(_source(), {"book_id": 1, "episode": 1, "records": existing}, {"items": [item]}, source_package_id="pkg", source_version_id="v1")
    assert result["merge"]["changed"] is False
    assert any(row["value"] == "blue" for row in result["merge"]["snapshot"]["records"])


def test_idempotency_and_unrelated_anchor_scope_are_stable():
    manifest = {"items": [_item()]}
    a = run_targeted_semantic_evidence_resolution(_source(), {}, manifest, source_package_id="pkg", source_version_id="v1")
    b = run_targeted_semantic_evidence_resolution(_source(), {}, manifest, source_package_id="pkg", source_version_id="v1")
    assert a["result_fingerprint"] == b["result_fingerprint"]
    assert all("Bob" not in row["candidate_anchor_set"]["anchors"][0]["exact_text"] for row in a["results"] if row["candidate_anchor_set"]["anchors"])
    assert set(a["counts"]).issuperset(RESOLUTION_TYPES)


def test_multi_anchor_conflict_is_not_promoted():
    source = "Alice is red.\n\nAlice is blue.\n"
    item = _item(predicate="color", expected_value=None)
    # A provider can cite both exact anchors; deterministic support must retain
    # the disagreement instead of choosing one value.
    index = build_source_evidence_index(source.encode(), source_package_id="pkg", source_version_id="v1")
    candidate_set = {"schema_version": "candidate_anchor_set_v1", "fact_key": item["fact_key"], "anchors": [{**a, "scope": "global", "ranking_score": 1} for a in index["anchors"]]}
    proposal = {"fact_key": item["fact_key"], "subject_type": "character", "subject_id": "Alice", "predicate": "is", "scope": "global", "proposed_value": "red", "supporting_anchor_refs": ["E0001", "E0002"], "exact_quotes": [index["anchors"][0]["exact_text"], index["anchors"][1]["exact_text"]], "resolution_type": "DIRECT_SOURCE_STATEMENT", "confidence": 1.0}
    support = validate_semantic_support(proposal, candidate_set, index, item)
    assert support["status"] in {"CONFLICTED", "NOT_SUPPORTED"}
