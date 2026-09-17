from __future__ import annotations

import copy

import pytest

from core.authorized_proposer_canary import (
    build_proposer_request,
    run_authorized_proposer_canary,
)
from core.source_evidence_index import build_source_evidence_index
from core.targeted_semantic_evidence_resolution import (
    resolve_semantic_evidence,
    retrieve_candidate_anchors,
)


def _fixture():
    source = "宋知夏的职业是演员。\r\n\r\n她穿着红色外套。\r\n\r\n程雨走进房间。\r\n"
    index = build_source_evidence_index(source.encode(), source_package_id="pkg", source_version_id="v1")
    manifest = {"items": [{
        "fact_key": "character|宋知夏|visual_identity|global",
        "semantic_type": "character", "entity": "宋知夏", "subject_type": "character",
        "predicate": "职业", "scope": "global", "expected_value": None,
        "required": True, "missing_reason": "ABSENT",
    }]}
    return source.encode(), index, manifest


def _proposal(request, **changes):
    fact = request["fact"]
    anchor = request["candidate_anchors"][0]
    value = changes.pop("proposed_value", "演员")
    result = {
        "fact_key": fact["fact_key"], "subject_type": fact["subject_type"],
        "subject_id": fact["entity"], "predicate": fact["predicate"], "scope": fact["scope"],
        "proposed_value": value, "supporting_anchor_refs": [anchor["anchor_ref"]],
        "exact_quotes": [anchor["exact_text"]], "resolution_type": "DIRECT_SOURCE_STATEMENT",
        "confidence": 0.91, "ambiguity": False, "conflicting_anchor_refs": [],
        "reasoning_summary": "anchor contains the subject and requested evidence",
    }
    result.update(changes)
    return result


def test_deterministic_supported_short_circuits_provider():
    source, index, manifest = _fixture()
    item = copy.deepcopy(manifest["items"][0]); item["expected_value"] = "演员"
    calls = []
    candidate = retrieve_candidate_anchors(item, index)
    result = resolve_semantic_evidence(item, candidate, index, provider=lambda req: calls.append(req))
    assert result["support_status"] in {"SUPPORTED", "AMBIGUOUS"}
    assert calls == []


def test_unsupported_with_anchors_calls_provider_once_and_accepts_candidate():
    source, _, manifest = _fixture(); calls = []
    def provider(req):
        calls.append(req); return _proposal(req)
    result = run_authorized_proposer_canary(source_material=source, current_snapshot={"records": []}, missing_manifest=manifest, source_package_id="pkg", source_version_id="v1", provider=provider)
    assert len(calls) == 1
    assert result["summary"]["provider_calls"] == 1
    assert result["summary"]["acceptable_candidates"] == 1
    assert result["persistence"]["fact_snapshot_writes"] == 0


def test_empty_anchor_set_does_not_call_provider():
    source, _, manifest = _fixture(); calls = []
    manifest["items"][0]["entity"] = "__missing_entity__"
    manifest["items"][0]["predicate"] = "__missing_predicate__"
    result = run_authorized_proposer_canary(source_material=source, current_snapshot={}, missing_manifest=manifest, source_package_id="pkg", source_version_id="v1", provider=lambda req: calls.append(req))
    assert calls == []
    assert result["results"][0]["final_classification"] == "NO_CANDIDATE_ANCHOR"


def test_unexecuted_provider_is_not_misreported_as_source_gap():
    source, _, manifest = _fixture()
    result = run_authorized_proposer_canary(source_material=source, current_snapshot={}, missing_manifest=manifest, source_package_id="pkg", source_version_id="v1")
    assert result["results"][0]["final_classification"] == "PROVIDER_NOT_EXECUTED"


def test_authorized_but_unconfigured_provider_is_distinct():
    source, _, manifest = _fixture()
    result = run_authorized_proposer_canary(source_material=source, current_snapshot={}, missing_manifest=manifest, source_package_id="pkg", source_version_id="v1", execution_authorized=True)
    assert result["results"][0]["final_classification"] == "PROVIDER_NOT_CONFIGURED"


def test_out_of_scope_anchor_and_quote_are_rejected():
    source, index, manifest = _fixture(); item = manifest["items"][0]
    candidate = retrieve_candidate_anchors(item, index)
    def provider(req):
        return _proposal(req, supporting_anchor_refs=["E9999"], exact_quotes=["伪造证据"])
    result = resolve_semantic_evidence(item, candidate, index, provider=provider)
    assert result["proposal"] is None
    assert result["diagnostics"]["provider"]["status"] == "PROVIDER_SCHEMA_INVALID"


@pytest.mark.parametrize("bad", [
    {"fact_key": "wrong"},
    {"subject_id": "other"},
    {"scope": "episode:99"},
])
def test_identity_or_schema_mutation_fails_closed(bad):
    source, index, manifest = _fixture(); item = manifest["items"][0]
    candidate = retrieve_candidate_anchors(item, index)
    def provider(req):
        return _proposal(req, **bad)
    result = resolve_semantic_evidence(item, candidate, index, provider=provider)
    assert result["proposal"] is None
    assert result["diagnostics"]["provider"]["status"] == "PROVIDER_SCHEMA_INVALID"


def test_schema_invalid_timeout_and_exception_are_fail_closed():
    source, index, manifest = _fixture(); item = manifest["items"][0]
    candidate = retrieve_candidate_anchors(item, index)
    for provider in (lambda req: {"unexpected": True}, lambda req: (_ for _ in ()).throw(TimeoutError("timeout"))):
        result = resolve_semantic_evidence(item, candidate, index, provider=provider)
        assert result["proposal"] is None
        assert result["provider_calls"] == 1


def test_confidence_does_not_replace_evidence_and_dry_run_has_no_merge():
    source, _, manifest = _fixture()
    def provider(req):
        return _proposal(req, proposed_value="医生", exact_quotes=[req["candidate_anchors"][0]["exact_text"]]) | {"confidence": 0.99}
    result = run_authorized_proposer_canary(source_material=source, current_snapshot={"records": []}, missing_manifest=manifest, source_package_id="pkg", source_version_id="v1", provider=provider)
    assert result["persistence"] == {"fact_snapshot_writes": 0, "authoritative_record_writes": 0, "production_writes": 0}
    assert result["summary"]["acceptable_candidates"] == 0


def test_request_is_bounded_and_contains_no_full_source():
    source, index, manifest = _fixture(); item = manifest["items"][0]
    candidate = retrieve_candidate_anchors(item, index)
    request = build_proposer_request(item, candidate, index)
    assert "source_material" not in request
    assert len(request["candidate_anchors"]) <= 8
    assert request["output_schema"]["additionalProperties"] is False
