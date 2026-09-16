from __future__ import annotations

from core.fact_evidence_authority_v2 import (
    canonicalize_fact_payload_v2,
    build_fact_request_v2,
    contract,
    provider_schema,
    resolve_evidence_refs_v1,
    schema_fingerprint,
)
from core.source_evidence_index import build_source_evidence_index, validate_source_evidence_index


PACKAGE = "SRC79f12d1b7f5eb828"
VERSION = "SRC79f12d1b7f5eb828:V01:d001bab5cc82"


def index_for(raw: bytes = "第一段。\r\n\r\n第二段。🙂\r\n".encode("utf-8")):
    return build_source_evidence_index(raw, source_package_id=PACKAGE, source_version_id=VERSION)


def test_source_evidence_index_is_deterministic():
    raw = "甲\r\n\r\n乙🙂\r\n".encode("utf-8")
    assert index_for(raw) == index_for(raw)


def test_source_evidence_anchor_exact_char_and_byte_spans():
    raw = "甲\r\n\r\n乙🙂\r\n".encode("utf-8")
    idx = index_for(raw)
    assert validate_source_evidence_index(idx, raw)["status"] == "PASS"
    row = idx["anchors"][1]
    text = raw.decode("utf-8")
    assert text[row["char_start"]:row["char_end"]] == row["exact_text"]
    assert raw[row["byte_start"]:row["byte_end"]].decode("utf-8") == row["exact_text"]
    assert row["exact_text_sha256"]


def test_source_evidence_index_handles_lf_and_unicode():
    raw = "一\n\n二😀\n".encode("utf-8")
    idx = index_for(raw)
    assert idx["anchor_count"] == 2
    assert validate_source_evidence_index(idx, raw)["status"] == "PASS"


def test_source_hash_change_changes_fingerprint():
    assert index_for(b"a\n")["evidence_index_fingerprint"] != index_for(b"b\n")["evidence_index_fingerprint"]


def test_valid_evidence_ref_resolves_exact_source():
    idx = index_for()
    resolved, errors = resolve_evidence_refs_v1(["E0001"], idx)
    assert not errors and resolved[0]["verified"] is True
    assert resolved[0]["excerpt"] == idx["anchors"][0]["exact_text"]


def test_unknown_evidence_ref_fails_closed():
    resolved, errors = resolve_evidence_refs_v1(["E9999"], index_for())
    assert resolved == []
    assert errors[0]["code"] == "SOURCE_EVIDENCE_REF_UNKNOWN"


def test_duplicate_refs_are_deterministically_deduped():
    resolved, errors = resolve_evidence_refs_v1(["E0002", "E0001", "E0002"], index_for())
    assert not errors and [r["anchor_ref"] for r in resolved] == ["E0001", "E0002"]


def test_v2_forbids_provider_excerpts_offsets_and_authority():
    idx = index_for()
    payload = {"facts": [{"subject_type": "x", "subject_label": "y", "predicate": "p", "value": 1, "epistemic_class": "SOURCE_ASSERTED_FACT", "evidence_refs": ["E0001"], "confidence": 1, "excerpt": "第一段。"}]}
    result = canonicalize_fact_payload_v2(payload, source_index=idx, book_id=1, episode=1, source_fingerprint=idx["source_raw_hash"], provenance={})
    assert result["report"]["status"] == "FAIL"
    assert any(e["code"] == "V2_PROVIDER_FORBIDDEN_FIELD" for e in result["report"]["errors"])


def test_v2_requires_refs_and_rejects_legacy_free_text():
    idx = index_for()
    payload = {"facts": [{"subject_type": "x", "subject_label": "y", "predicate": "p", "value": 1, "epistemic_class": "SOURCE_ASSERTED_FACT", "evidence": "第一段。", "confidence": 1}]}
    result = canonicalize_fact_payload_v2(payload, source_index=idx, book_id=1, episode=1, source_fingerprint=idx["source_raw_hash"], provenance={})
    assert result["report"]["status"] == "FAIL"
    assert any(e["code"] == "V2_PROVIDER_FORBIDDEN_FIELD" for e in result["report"]["errors"])


def test_epistemic_mapping_preserves_claim_and_inference_boundaries():
    idx = index_for()
    payload = {"facts": [
        {"subject_type": "character", "subject_label": "甲", "predicate": "says", "value": "x", "epistemic_class": "CHARACTER_CLAIM_CONTENT", "evidence_refs": ["E0001"], "confidence": 1},
        {"subject_type": "character", "subject_label": "甲", "predicate": "mood", "value": "tense", "epistemic_class": "MODEL_INFERENCE", "evidence_refs": ["E0001"], "confidence": 0.5},
    ]}
    result = canonicalize_fact_payload_v2(payload, source_index=idx, book_id=1, episode=1, source_fingerprint=idx["source_raw_hash"], provenance={})
    assert result["report"]["status"] == "PASS"
    rows = result["snapshot"]["records"]
    assert {row["status"] for row in rows} == {"proposed"}
    assert {row["authority"] for row in rows} == {"source_text", "model_observation"}


def test_provider_request_v2_uses_blocks_not_full_source_and_exposes_schema_fingerprint():
    idx = index_for()
    request = build_fact_request_v2(raw_text="ignored", source_package_id=PACKAGE, source_version_id=VERSION, source_raw_hash=idx["source_raw_hash"], source_index=idx, provider="openai-compatible", model="mimo-v2.5")
    assert request["task"] == "extract_source_grounded_facts_v2"
    assert "source_text" not in request
    assert request["contract"]["schema_fingerprint"] == schema_fingerprint()
    assert request["contract"]["legacy_free_text_evidence_fallback"] is False


def test_schema_fingerprint_is_stable_and_contract_forbids_authority():
    assert schema_fingerprint() == schema_fingerprint()
    assert "authority" in contract()["forbidden_provider_fields"]
    assert "excerpt" not in provider_schema()["properties"]
