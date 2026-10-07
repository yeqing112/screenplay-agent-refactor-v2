"""Provider-free contract hardening tests for V7.6.11."""
from __future__ import annotations

import copy
import hashlib
import inspect
import json

import pytest

from api import director_treatment_api as api
from core.director_forensic import resolve_next_director_attempt_context
from core.director_progressive_authoring import (
    build_director_creative_enrichment_prompt,
    materialize_director_beat_plan_ids,
    parse_director_creative_enrichment_ir,
    render_stage_b_schema_contract,
    validate_director_creative_enrichment_ir,
    validate_director_creative_enrichment_ir_schema,
    validate_stage_b_prompt_schema_key_parity,
)
from models import DecisionPacketRecord, Session, init_db

from tests.test_director_creative_enrichment_boundary_v7_6_9 import stage_a, stage_b
from tests.test_director_creative_enrichment_execution_v7_6_10 import _payloads, _profile, _seed_packet


def _materialized():
    raw, _ = stage_a()
    return materialize_director_beat_plan_ids(raw, scene_id="E01_SC001")


def test_stage_b_prompt_has_complete_structural_contract_and_shape_example():
    materialized = _materialized()
    _, prompt = build_director_creative_enrichment_prompt(scene_id="E01_SC001", beat_plan=materialized, declared_participants=[{"id": "顾沉"}])
    contract = render_stage_b_schema_contract()
    parity = validate_stage_b_prompt_schema_key_parity(prompt)
    assert parity["status"] == "PASS"
    assert parity["structural_parity"] == "PASS"
    assert parity["prompt"]["CANONICAL_STAGE_B_INFORMATION_STRATEGY_KEYS"] == contract["information_strategy_keys"]
    assert parity["prompt"]["CANONICAL_STAGE_B_INFORMATION_REVEAL_KEYS"] == contract["information_reveal_keys"]
    assert parity["prompt"]["CANONICAL_STAGE_B_RHYTHM_STRATEGY_KEYS"] == contract["rhythm_strategy_keys"]
    assert parity["prompt"]["STAGE_B_REQUIRED_FIELDS"] == contract["nested_required"]
    assert parity["prompt"]["STAGE_B_FIELD_TYPES"] == contract["field_types"]
    assert parity["prompt"]["JSON_SHAPE_EXAMPLE_ONLY"] == contract["shape_example"]
    assert "STAGE_B_ADDITIONAL_PROPERTIES=false" in prompt
    assert json.dumps(contract["shape_example"], ensure_ascii=False, sort_keys=True, separators=(",", ":")) in prompt
    assert set(contract["shape_example"]) == set(contract["top_level_required"])


@pytest.mark.parametrize("marker", [
    "CANONICAL_STAGE_B_INFORMATION_REVEAL_KEYS=",
    "STAGE_B_REQUIRED_FIELDS=",
    "STAGE_B_FIELD_TYPES=",
    "JSON_SHAPE_EXAMPLE_ONLY=",
])
def test_structural_parity_rejects_missing_or_changed_contract_block(marker):
    materialized = _materialized()
    _, prompt = build_director_creative_enrichment_prompt(scene_id="E01_SC001", beat_plan=materialized, declared_participants=[{"id": "顾沉"}])
    lines = [line for line in prompt.splitlines() if not line.startswith(marker)]
    assert validate_stage_b_prompt_schema_key_parity("\n".join(lines))["status"] == "FAIL"


def test_structural_parity_rejects_unknown_nested_field_type():
    materialized = _materialized()
    _, prompt = build_director_creative_enrichment_prompt(scene_id="E01_SC001", beat_plan=materialized, declared_participants=[{"id": "顾沉"}])
    changed = prompt.replace('"beat_enrichments[].beat_ref":"string"', '"beat_enrichments[].beat_ref":"number"')
    assert validate_stage_b_prompt_schema_key_parity(changed)["status"] == "FAIL"


@pytest.mark.parametrize("mutate", [
    lambda value: value.pop("note"),
    lambda value: value["character_directions"][0].pop("direction"),
    lambda value: value["information_strategy"]["reveal_plan"][0].pop("beat_id"),
    lambda value: value["information_strategy"]["reveal_plan"].__setitem__(0, {**value["information_strategy"]["reveal_plan"][0], "reveals": "wrong"}),
    lambda value: value["character_directions"][0].__setitem__("方向", value["character_directions"][0].pop("direction")),
])
def test_malformed_stage_b_structures_fail_closed(mutate):
    materialized = _materialized()
    value = stage_b(materialized)
    mutate(value)
    assert validate_director_creative_enrichment_ir_schema(value)["status"] == "FAIL"


def test_unknown_dbp_beat_ref_and_duplicate_key_fail_closed():
    materialized = _materialized()
    value = stage_b(materialized)
    value["beat_enrichments"][0]["beat_ref"] = "DBP_UNKNOWN"
    result = validate_director_creative_enrichment_ir(value, beat_plan=materialized, declared_participants=[{"id": "顾沉"}])
    assert result["status"] == "blocked"
    with pytest.raises(ValueError, match="DIRECTOR_CREATIVE_ENRICHMENT_DUPLICATE_JSON_KEY"):
        parse_director_creative_enrichment_ir('{"version":"director_creative_enrichment_ir_v1","version":"director_creative_enrichment_ir_v1"}')


def test_stage_b_attempt_context_generalizes_history_7_8_9():
    for count, expected in [(7, "attempt-8"), (8, "attempt-9"), (9, "attempt-10")]:
        info = {"director_llm_attempts": [{"attempt_id": f"attempt-{i}", "status": "OLD"} for i in range(1, count + 1)]}
        context = resolve_next_director_attempt_context(info, authoring_stage="CREATIVE_ENRICHMENT")
        assert context.attempt_id == expected


def test_stage_b_executor_has_no_concrete_attempt_hardcode():
    source = inspect.getsource(api._execute_source_grounded_creative_enrichment)
    assert "attempt-7" not in source
    assert "ATTEMPT8" not in source


def _authorized_endpoint(monkeypatch, packet_fp, mutate_after_lock=None):
    scene, treatment, stage_a_ir, materialized, stage_b_ir = _payloads()
    _seed_packet(treatment, stage_a_ir, materialized, packet_fp)
    monkeypatch.setattr(api, "_build_preview", lambda *_args, **_kwargs: (treatment, {"scene": scene}, None))
    monkeypatch.setattr(api, "_make_decision_packet", lambda *_args, **_kwargs: {"packet_fingerprint": packet_fp})
    monkeypatch.setattr(api, "_director_llm_profile_preflight", lambda: (_profile(), {"profile_id": "test-profile", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test", "enabled": True}))
    if mutate_after_lock:
        original = api._execute_source_grounded_creative_enrichment

        def wrapper(**kwargs):
            with Session() as session:
                row = session.query(DecisionPacketRecord).filter_by(packet_fingerprint=packet_fp).first()
                info = json.loads(row.model_info)
                mutate_after_lock(row, info)
                row.model_info = json.dumps(info, ensure_ascii=False)
                session.commit()
            return original(**kwargs)

        monkeypatch.setattr(api, "_execute_source_grounded_creative_enrichment", wrapper)
    return api.DirectorCreativeEnrichmentLlmDraftRequest(scene_id="E01_SC001", packet_fingerprint=packet_fp, confirmed=True, allow_external_call=True, authorization_id="mock-stage-b-auth")


@pytest.mark.parametrize("label,mutate", [
    ("proposal", lambda row, info: row.__setattr__("proposal", json.dumps({"decision": "ready_for_review"}, ensure_ascii=False))),
    ("attempt", lambda row, info: info["progressive_director_authoring"]["stage_a"].__setitem__("attempt_id", "attempt-8")),
    ("materialized", lambda row, info: info["progressive_director_authoring"]["stage_a"].__setitem__("materialized_fingerprint", "drift")),
])
def test_pretransport_race_releases_lock_without_provider_or_append(monkeypatch, label, mutate):
    init_db()
    packet_fp = f"stage-b-pretransport-race-{label}"
    request = _authorized_endpoint(monkeypatch, packet_fp, mutate)
    calls = []
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **_kwargs: calls.append(1))
    with pytest.raises(api.HTTPException):
        api.generate_director_creative_enrichment_llm_draft(990453, 1, request)
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(packet_fingerprint=packet_fp).first()
        info = json.loads(row.model_info)
        assert info.get("llm_draft_in_progress") is False
        assert len(info.get("director_llm_attempts") or []) == 7
    assert calls == []


def test_pretransport_packet_disappeared_has_no_provider_call(monkeypatch):
    init_db()
    packet_fp = "stage-b-pretransport-packet-disappeared"
    _authorized_endpoint(monkeypatch, packet_fp)
    original = api._execute_source_grounded_creative_enrichment

    def wrapper(**kwargs):
        with Session() as session:
            row = session.query(DecisionPacketRecord).filter_by(packet_fingerprint=packet_fp).first()
            session.delete(row)
            session.commit()
        return original(**kwargs)

    monkeypatch.setattr(api, "_execute_source_grounded_creative_enrichment", wrapper)
    calls = []
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **_kwargs: calls.append(1))
    request = api.DirectorCreativeEnrichmentLlmDraftRequest(scene_id="E01_SC001", packet_fingerprint=packet_fp, confirmed=True, allow_external_call=True, authorization_id="mock-stage-b-auth")
    with pytest.raises(api.HTTPException):
        api.generate_director_creative_enrichment_llm_draft(990453, 1, request)
    assert calls == []


def test_pretransport_attempt_context_conflict_releases_lock(monkeypatch):
    init_db()
    packet_fp = "stage-b-pretransport-attempt-context"
    _authorized_endpoint(monkeypatch, packet_fp)
    monkeypatch.setattr(api, "resolve_next_director_attempt_context", lambda *_args, **_kwargs: (_ for _ in ()).throw(api.HTTPException(status_code=409, detail={"code": "ATTEMPT_CONTEXT_CONFLICT"})))
    calls = []
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **_kwargs: calls.append(1))
    request = api.DirectorCreativeEnrichmentLlmDraftRequest(scene_id="E01_SC001", packet_fingerprint=packet_fp, confirmed=True, allow_external_call=True, authorization_id="mock-stage-b-auth")
    with pytest.raises(api.HTTPException) as exc:
        api.generate_director_creative_enrichment_llm_draft(990453, 1, request)
    assert exc.value.detail["code"] == "ATTEMPT_CONTEXT_CONFLICT"
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(packet_fingerprint=packet_fp).first()
        assert json.loads(row.model_info).get("llm_draft_in_progress") is False
        assert len(json.loads(row.model_info).get("director_llm_attempts") or []) == 7
    assert calls == []


def test_compiled_authoring_required_is_not_stage_b_success(monkeypatch):
    init_db()
    scene, treatment, stage_a_ir, materialized, stage_b_ir = _payloads()
    packet_fp = "stage-b-compiled-authoring-required"
    _seed_packet(treatment, stage_a_ir, materialized, packet_fp)
    monkeypatch.setattr(api, "_build_preview", lambda *_args, **_kwargs: (treatment, {"scene": scene}, None))
    monkeypatch.setattr(api, "_make_decision_packet", lambda *_args, **_kwargs: {"packet_fingerprint": packet_fp})
    monkeypatch.setattr(api, "_director_llm_profile_preflight", lambda: (_profile(), {"profile_id": "test-profile", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test", "enabled": True}))
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **kwargs: kwargs["audit_callback"]({"finish_reason": "stop"}) or json.dumps(stage_b_ir, ensure_ascii=False))
    monkeypatch.setattr(api, "validate_source_grounded_contract_v2", lambda *_args, **_kwargs: {"status": "AUTHORING_REQUIRED", "errors": []})
    request = api.DirectorCreativeEnrichmentLlmDraftRequest(scene_id="E01_SC001", packet_fingerprint=packet_fp, confirmed=True, allow_external_call=True, authorization_id="mock-stage-b-auth")
    with pytest.raises(api.HTTPException) as exc:
        api.generate_director_creative_enrichment_llm_draft(990453, 1, request)
    assert exc.value.detail["code"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_COMPILED_CONTRACT_INVALID"
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(packet_fingerprint=packet_fp).first()
        assert json.loads(row.model_info).get("llm_draft_in_progress") is False
