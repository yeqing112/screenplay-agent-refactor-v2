"""Provider-free structural feedback and final completeness regressions."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from api import director_treatment_api as api
from core import director_progressive_authoring as pa
from core.director_progressive_authoring import (
    build_director_creative_enrichment_prompt,
    compile_progressive_director_proposal,
    materialize_director_beat_plan_ids,
    validate_director_creative_enrichment_ir_schema,
    validate_director_creative_enrichment_text_completeness,
    validate_stage_b_prompt_schema_key_parity,
)
from core.director_revision import derive_structural_revision_feedback, structural_revision_feedback_fingerprint
from core.director_semantic_grounding import validate_director_creative_semantic_review_v2
from tests.test_director_creative_enrichment_boundary_v7_6_9 import stage_a, stage_b
from tests.test_director_semantic_v2_production_wiring_v7_6_17 import _patch_runtime, _request, _seed_attempt9
from models import DecisionPacketRecord, Session, init_db


def _materialized():
    raw, _ = stage_a()
    return materialize_director_beat_plan_ids(raw, scene_id="E01_SC001")


def _failure_info(*, latest: str = "attempt-10", active: str = "attempt-9"):
    materialized = _materialized()
    parent_fp = "parent-ir-fp"
    archive = {
        "attempt_id": latest,
        "authoring_stage": "CREATIVE_ENRICHMENT",
        "structural_status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_SCHEMA_INVALID",
        "revision_parent": {
            "revision_parent_attempt_id": active,
            "revision_parent_stage_b_ir_fingerprint": parent_fp,
        },
        "raw_forensic": {"raw_response_sha256": "raw-sha"},
        "provider_request_identity": {"provider_request_fingerprint_v2": "request-fp"},
        "validation": {
            "schema": {
                "status": "FAIL",
                "errors": [{"path": "$", "code": "SCHEMA_REQUIRED_FIELD_MISSING", "field": "visual_priority"}],
            }
        },
    }
    return {
        "director_llm_attempts": [{"attempt_id": f"attempt-{i}", "status": "OLD"} for i in range(1, 10)]
        + [{"attempt_id": latest, "status": archive["structural_status"]}],
        "progressive_director_authoring": {
            "stage_b": {"attempt_id": active, "ir_fingerprint": parent_fp, "authoring_stage": "CREATIVE_ENRICHMENT", "status": "VALIDATED"},
            "stage_b_attempts": [archive],
            "stage_a": {"attempt_id": "attempt-7", "materialized_beat_plan": materialized},
        },
    }


def test_final_completeness_gate_is_schema_derived(monkeypatch):
    materialized = _materialized()
    original = copy.deepcopy(pa.DIRECTOR_CREATIVE_ENRICHMENT_IR_SCHEMA)
    monkeypatch.setitem(pa.DIRECTOR_CREATIVE_ENRICHMENT_IR_SCHEMA["properties"], "future_required", {"type": "string"})
    monkeypatch.setitem(pa.DIRECTOR_CREATIVE_ENRICHMENT_IR_SCHEMA, "required", original["required"] + ["future_required"])
    _, prompt = build_director_creative_enrichment_prompt(scene_id="E01_SC001", beat_plan=materialized)
    parity = validate_stage_b_prompt_schema_key_parity(prompt)
    assert parity["status"] == "PASS"
    assert "future_required" in parity["prompt"]["FINAL_OUTPUT_REQUIRED_TOP_LEVEL_KEYS"]
    assert parity["prompt"]["FINAL_OUTPUT_REQUIRED_TOP_LEVEL_KEY_COUNT"] == 12


def test_missing_each_required_top_level_key_is_schema_failure():
    materialized = _materialized()
    valid = stage_b(materialized)
    required = pa.render_stage_b_schema_contract()["top_level_required"]
    for key in required:
        candidate = copy.deepcopy(valid)
        candidate.pop(key)
        report = validate_director_creative_enrichment_ir_schema(candidate)
        assert report["status"] == "FAIL"
        assert any(error.get("code") == "SCHEMA_REQUIRED_FIELD_MISSING" and error.get("field") == key for error in report["errors"])


def test_complete_golden_fixture_passes_schema_text_and_compile():
    raw_stage_a, units = stage_a()
    materialized = materialize_director_beat_plan_ids(raw_stage_a, scene_id="E01_SC001")
    enrichment = stage_b(materialized)
    assert validate_director_creative_enrichment_ir_schema(enrichment)["status"] == "PASS"
    assert validate_director_creative_enrichment_text_completeness(enrichment)["status"] == "PASS"
    compiled = compile_progressive_director_proposal(
        beat_plan_ir=raw_stage_a,
        enrichment_ir=enrichment,
        baseline_treatment={"scene_id": "E01_SC001", "source_constraints": {"source_authoring_units": units}},
        source_scene={"scene_id": "E01_SC001", "participants": [{"id": "顾沉"}]},
        materialized_beat_plan=materialized,
        materialized_fingerprint=hashlib.sha256(json.dumps(materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    )
    assert compiled["compiler_report"]["status"] == "PASS"


def test_structural_feedback_is_latest_failure_bound_to_attempt_9():
    feedback = derive_structural_revision_feedback(_failure_info())
    assert feedback["status"] == "ELIGIBLE"
    assert feedback["failed_attempt_id"] == "attempt-10"
    assert feedback["parent_attempt_id"] == "attempt-9"
    assert feedback["constraints"] == [{
        "category": "REQUIRED_TOP_LEVEL_FIELD_MISSING",
        "path": "$",
        "field": "visual_priority",
        "expected_type": "array<string>",
        "constraint": "The required top-level property visual_priority must be present and must satisfy the source-grounded Stage B schema (array<string>).",
        "source": "persisted_attempt_failure_validation",
    }]
    assert feedback["structural_feedback_fingerprint"] == structural_revision_feedback_fingerprint(feedback)


def test_structural_feedback_becomes_stale_after_later_success():
    info = _failure_info(latest="attempt-11", active="attempt-11")
    info["director_llm_attempts"][-1]["status"] = "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_VALIDATED"
    info["progressive_director_authoring"]["stage_b"]["status"] = "VALIDATED"
    info["progressive_director_authoring"]["stage_b_attempts"].append({"attempt_id": "attempt-11", "authoring_stage": "CREATIVE_ENRICHMENT", "structural_status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_VALIDATED"})
    assert derive_structural_revision_feedback(info)["status"] == "NOT_ELIGIBLE"


def test_prompt_keeps_semantic_and_structural_feedback_independent_and_final_gate_last():
    _, prompt = build_director_creative_enrichment_prompt(
        scene_id="E01_SC001",
        beat_plan=_materialized(),
        revision_feedback={"schema_version": "director_revision_feedback_v2", "constraints": [{"category": "UNSUPPORTED_CERTAINTY_COLLAPSE"}]},
        structural_feedback=derive_structural_revision_feedback(_failure_info()),
    )
    assert "REVISION_FEEDBACK=" in prompt
    assert "STRUCTURAL_REVISION_FEEDBACK=" in prompt
    assert prompt.rfind("FINAL_OUTPUT_COMPLETENESS_GATE=") > prompt.rfind("REVISION_GENERATION_CONTRACT=")
    assert validate_stage_b_prompt_schema_key_parity(prompt)["status"] == "PASS"


def test_mock_complete_response_passes_all_structural_gates(monkeypatch):
    init_db()
    scene, treatment, clean_stage_b, parent_stage_b, _ = _seed_attempt9("v7619-complete")
    _patch_runtime(monkeypatch, treatment, scene, "v7619-complete")
    parent_review = validate_director_creative_semantic_review_v2(parent_stage_b, source_authoring_units=treatment["source_constraints"]["source_authoring_units"], declared_participants=treatment["source_constraints"].get("declared_participants", []))
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **kwargs: kwargs["audit_callback"]({"finish_reason": "stop"}) or json.dumps(clean_stage_b, ensure_ascii=False))
    req = _request("v7619-complete", parent_stage_b, parent_review, confirmed=True, allow_external_call=True, authorization_id="mock-v7619")
    result = api.generate_director_creative_enrichment_revision_llm_draft(990453, 1, req)
    assert result["status"].endswith("_VALIDATED")
    assert result["confirm_allowed"] is True
    assert result["provider"]["called"] is True


def test_mock_missing_visual_priority_archives_failure_and_keeps_parent(monkeypatch):
    init_db()
    scene, treatment, clean_stage_b, parent_stage_b, _ = _seed_attempt9("v7619-missing-visual")
    _patch_runtime(monkeypatch, treatment, scene, "v7619-missing-visual")
    parent_review = validate_director_creative_semantic_review_v2(parent_stage_b, source_authoring_units=treatment["source_constraints"]["source_authoring_units"], declared_participants=treatment["source_constraints"].get("declared_participants", []))
    missing = copy.deepcopy(clean_stage_b)
    missing.pop("visual_priority")
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **kwargs: kwargs["audit_callback"]({"finish_reason": "stop"}) or json.dumps(missing, ensure_ascii=False))
    req = _request("v7619-missing-visual", parent_stage_b, parent_review, confirmed=True, allow_external_call=True, authorization_id="mock-v7619")
    with pytest.raises(api.HTTPException) as exc:
        api.generate_director_creative_enrichment_revision_llm_draft(990453, 1, req)
    assert exc.value.detail["code"].endswith("_SCHEMA_INVALID")
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(packet_fingerprint="v7619-missing-visual").first()
        info = json.loads(row.model_info)
        assert info["progressive_director_authoring"]["stage_b"]["attempt_id"] == "attempt-9"
        assert info["progressive_director_authoring"]["stage_b_attempts"][-1]["attempt_id"] == "attempt-10"
        assert not any(item.get("attempt_id") == "attempt-11" for item in info["director_llm_attempts"])


def test_mock_semantic_blocked_and_pass_have_distinct_review_boundaries(monkeypatch):
    for packet_fp, blocked, expected_confirm in (("v7619-semantic-blocked", True, False), ("v7619-semantic-pass", False, True)):
        init_db()
        scene, treatment, clean_stage_b, parent_stage_b, _ = _seed_attempt9(packet_fp)
        _patch_runtime(monkeypatch, treatment, scene, packet_fp)
        parent_review = validate_director_creative_semantic_review_v2(parent_stage_b, source_authoring_units=treatment["source_constraints"]["source_authoring_units"], declared_participants=treatment["source_constraints"].get("declared_participants", []))
        candidate = copy.deepcopy(clean_stage_b)
        if blocked:
            candidate["beat_enrichments"][0]["character_effects"][0]["effect"] = "首次进入后带到铁盒前并打开铁盒。"
        monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **kwargs: kwargs["audit_callback"]({"finish_reason": "stop"}) or json.dumps(candidate, ensure_ascii=False))
        req = _request(packet_fp, parent_stage_b, parent_review, confirmed=True, allow_external_call=True, authorization_id="mock-v7619")
        result = api.generate_director_creative_enrichment_revision_llm_draft(990453, 1, req)
        assert result["confirm_allowed"] is expected_confirm
        assert result["semantic_review"]["status"] == ("BLOCKED" if blocked else "PASS")
        assert result["next_state"] == ("DIRECTOR_TREATMENT_SEMANTIC_REVIEW_REQUIRED" if blocked else "DIRECTOR_TREATMENT_REVIEW_REQUIRED")
