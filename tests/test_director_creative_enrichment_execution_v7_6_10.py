import copy
import json

import pytest

from api import director_treatment_api as api
from core.director_progressive_authoring import materialize_director_beat_plan_ids
from core.director_source_grounded import build_source_grounded_director_preview
from models import DecisionPacketRecord, DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer, Session, init_db


def _scene():
    return {
        "source_grounded_schema_version": "source_grounded_script_payload_v3_1",
        "timeline_origin": "SOURCE_GROUNDED", "scene_id": "E01_SC001", "participants": [{"id": "顾沉", "name": "顾沉"}],
        "source_identity_evidence": [], "required_visual_proofs": [],
        "actions": [{"action_id": f"A{i}", "text": f"动作{i}。", "source_evidence": []} for i in range(1, 5)],
        "dialogues": [], "beats": [],
        "script_blocks": [{"type": "ACTION", "ref": f"A{i}", "order": i} for i in range(1, 5)],
    }


def _payloads():
    scene = _scene()
    treatment = build_source_grounded_director_preview(scene=scene)
    units = treatment["source_constraints"]["source_authoring_units"]
    stage_a = {
        "version": "director_beat_plan_ir_v1", "scene_label": "暗房", "scene_objective": "线索把关系推向不信任。", "dramatic_question": "谁在操控这场相遇？",
        "beats": [{"refs": [unit["unit_id"]], "purpose": "建立戒备。", "objective": "确认线索。", "information_change": "观众知道线索出现。", "hook": i == 0} for i, unit in enumerate(units)],
        "passthrough_refs": [], "unknowns": [], "confidence": 0.8, "note": "固定夹具。",
    }
    materialized = materialize_director_beat_plan_ids(stage_a, scene_id="E01_SC001")
    stage_b = {
        "version": "director_creative_enrichment_ir_v1",
        "beat_enrichments": [{"beat_ref": beat["beat_ref"], "audience_effect": "观众感到不安。", "performance": "人物压住情绪。", "transition": "视线转向门口。", "character_effects": [{"character_ref": "顾沉", "effect": "继续试探。"}]} for beat in materialized["beats"]],
        "character_directions": [{"character_ref": "顾沉", "direction": "克制地试探。"}],
        "performance_arc": [{"phase": "IN", "state": "戒备。"}],
        "information_strategy": {"schema_version": "director_information_strategy_v2", "known_to_audience": ["线索出现。"], "withheld_from_audience": ["动机。"], "reveal_plan": [{"beat_id": materialized["beats"][0]["beat_ref"], "reveals": ["线索"], "withholds": ["动机"], "audience_should_notice": "线索被确认。", "audience_should_not_yet_know": "动机。"}], "reaction_priority": ["顾沉"], "audience_focus": ["线索"]},
        "rhythm_strategy": {"opening": "收紧。", "reveal": "延迟。", "escalation": "压缩。", "button": "停住。"},
        "visual_priority": ["线索"], "scene_exit_intent": "关系留下裂缝。", "prohibited_interpretations": ["不得确定动机。"], "confidence": 0.8, "note": "固定夹具。",
    }
    return scene, treatment, stage_a, materialized, stage_b


def _seed_packet(treatment, stage_a, materialized, packet_fp="stage-b-execution-packet"):
    attempts = [{"attempt_id": f"attempt-{i}", "status": "OLD"} for i in range(1, 8)]
    info = {"progressive_director_authoring": {"stage_a": {"status": "DIRECTOR_BEAT_PLAN_ATTEMPT7_VALIDATED", "authoring_stage": "BEAT_PLAN", "attempt_id": "attempt-7", "ir": stage_a, "ir_fingerprint": "stage-a-ir", "materialized_beat_plan": materialized, "materialized_fingerprint": __import__("hashlib").sha256(json.dumps(materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}}, "director_llm_attempts": attempts}
    with Session() as session:
        row = DecisionPacketRecord(book_id=990453, domain="director_treatment", scope=json.dumps({"book_id": 990453, "episode": 1, "scene_id": "E01_SC001", "scene_name": ""}), packet_fingerprint=packet_fp, evidence="[]", unknowns="[]", conflicts="[]", allowed_operations="[]", proposal=json.dumps({"decision": "awaiting_llm"}), model_info=json.dumps(info, ensure_ascii=False))
        session.add(row); session.commit(); session.refresh(row)
        return row.id


def _profile():
    return {"id": "test-profile", "provider": "openai-compatible", "model_name": "mimo", "base_url": "https://example.test/v1", "default_params": {"max_tokens": 4096, "thinking": {"type": "disabled"}}}


def test_stage_b_endpoint_no_auth_is_provider_free(monkeypatch):
    init_db(); scene, treatment, stage_a, materialized, stage_b = _payloads(); _seed_packet(treatment, stage_a, materialized, "stage-b-no-auth")
    monkeypatch.setattr(api, "_build_preview", lambda *_args, **_kwargs: (treatment, {"scene": scene}, None))
    monkeypatch.setattr(api, "_make_decision_packet", lambda *_args, **_kwargs: {"packet_fingerprint": "stage-b-no-auth"})
    calls = []
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *args, **kwargs: calls.append(1))
    result = api.generate_director_creative_enrichment_llm_draft(990453, 1, api.DirectorCreativeEnrichmentLlmDraftRequest(scene_id="E01_SC001", packet_fingerprint="stage-b-no-auth"))
    assert result["status"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_AUTHORIZATION_REQUIRED"
    assert calls == []


def test_stage_b_endpoint_mock_authorized_execution_persists_proposal_only(monkeypatch):
    init_db(); scene, treatment, stage_a, materialized, stage_b = _payloads(); _seed_packet(treatment, stage_a, materialized, "stage-b-success")
    monkeypatch.setattr(api, "_build_preview", lambda *_args, **_kwargs: (treatment, {"scene": scene}, None))
    monkeypatch.setattr(api, "_make_decision_packet", lambda *_args, **_kwargs: {"packet_fingerprint": "stage-b-success"})
    monkeypatch.setattr(api, "_director_llm_profile_preflight", lambda: (_profile(), {"profile_id": "test-profile", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test", "enabled": True}))
    audit = {"finish_reason": "stop", "choice_index": 0, "provider_request_id": "mock-request", "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}, "latency_ms": 3}
    calls = []
    def mock_call(*_args, **kwargs):
        calls.append(1); kwargs["audit_callback"](audit); return json.dumps(stage_b, ensure_ascii=False)
    monkeypatch.setattr(api.llm_client, "call_llm", mock_call)
    result = api.generate_director_creative_enrichment_llm_draft(990453, 1, api.DirectorCreativeEnrichmentLlmDraftRequest(scene_id="E01_SC001", packet_fingerprint="stage-b-success", confirmed=True, allow_external_call=True, authorization_id="mock-stage-b-auth"))
    assert len(calls) == 1
    assert result["status"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_VALIDATED"
    assert result["confirm_allowed"] is True
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(packet_fingerprint="stage-b-success").first()
        info = json.loads(row.model_info); proposal = json.loads(row.proposal)
        assert len(info["director_llm_attempts"]) == 8
        assert info["director_llm_attempts"][-1]["attempt_id"] == "attempt-8"
        assert info["progressive_director_authoring"]["stage_a"]["attempt_id"] == "attempt-7"
        assert info["progressive_director_authoring"]["stage_b"]["status"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_VALIDATED"
        assert proposal["decision"] == "ready_for_review"
        assert proposal["creative_projection"]["status"] == "PROPOSED"
        assert info["llm_draft_in_progress"] is False
        assert session.query(DirectorTreatment).count() == 0
        assert session.query(DirectorTreatmentAuthority).count() == 0
        assert session.query(DirectorTreatmentPointer).count() == 0
    with pytest.raises(api.HTTPException) as repeated:
        api.generate_director_creative_enrichment_llm_draft(990453, 1, api.DirectorCreativeEnrichmentLlmDraftRequest(scene_id="E01_SC001", packet_fingerprint="stage-b-success", confirmed=True, allow_external_call=True, authorization_id="mock-stage-b-auth"))
    assert repeated.value.detail["code"] == "DIRECTOR_CREATIVE_ENRICHMENT_ALREADY_COMPLETED"
    assert len(calls) == 1


def test_stage_b_duplicate_key_fails_without_second_call(monkeypatch):
    init_db(); scene, treatment, stage_a, materialized, stage_b = _payloads(); _seed_packet(treatment, stage_a, materialized, "stage-b-duplicate")
    monkeypatch.setattr(api, "_build_preview", lambda *_args, **_kwargs: (treatment, {"scene": scene}, None))
    monkeypatch.setattr(api, "_make_decision_packet", lambda *_args, **_kwargs: {"packet_fingerprint": "stage-b-duplicate"})
    monkeypatch.setattr(api, "_director_llm_profile_preflight", lambda: (_profile(), {"profile_id": "test-profile", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test", "enabled": True}))
    calls = []
    raw = '{"version":"director_creative_enrichment_ir_v1","version":"director_creative_enrichment_ir_v1"}'
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **_kwargs: calls.append(1) or raw)
    with pytest.raises(api.HTTPException) as exc:
        api.generate_director_creative_enrichment_llm_draft(990453, 1, api.DirectorCreativeEnrichmentLlmDraftRequest(scene_id="E01_SC001", packet_fingerprint="stage-b-duplicate", confirmed=True, allow_external_call=True, authorization_id="mock-stage-b-auth"))
    assert exc.value.detail["code"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_DUPLICATE_JSON_KEY"
    assert calls == [1]


@pytest.mark.parametrize(
    "label,raw_builder,expected",
    [
        ("malformed", lambda stage_b: "not-json", "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_PARSE_FAILED"),
        ("schema", lambda stage_b: json.dumps({"version": "director_creative_enrichment_ir_v1"}), "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_SCHEMA_INVALID"),
        ("text", lambda stage_b: json.dumps({**stage_b, "note": ""}, ensure_ascii=False), "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_TEXT_INCOMPLETE"),
        ("runtime", lambda stage_b: json.dumps({**stage_b, "character_directions": [{"character_ref": "不存在", "direction": "越界。"}]}, ensure_ascii=False), "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_RUNTIME_INVALID"),
    ],
)
def test_stage_b_failure_matrix_is_single_call_and_cleans_progress(monkeypatch, label, raw_builder, expected):
    init_db(); scene, treatment, stage_a, materialized, stage_b = _payloads(); packet_fp = f"stage-b-{label}"; _seed_packet(treatment, stage_a, materialized, packet_fp)
    monkeypatch.setattr(api, "_build_preview", lambda *_args, **_kwargs: (treatment, {"scene": scene}, None))
    monkeypatch.setattr(api, "_make_decision_packet", lambda *_args, **_kwargs: {"packet_fingerprint": packet_fp})
    monkeypatch.setattr(api, "_director_llm_profile_preflight", lambda: (_profile(), {"profile_id": "test-profile", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test", "enabled": True}))
    calls = []
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **_kwargs: calls.append(1) or raw_builder(stage_b))
    with pytest.raises(api.HTTPException) as exc:
        api.generate_director_creative_enrichment_llm_draft(990453, 1, api.DirectorCreativeEnrichmentLlmDraftRequest(scene_id="E01_SC001", packet_fingerprint=packet_fp, confirmed=True, allow_external_call=True, authorization_id="mock-stage-b-auth"))
    assert exc.value.detail["code"] == expected and calls == [1]
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(packet_fingerprint=packet_fp).first()
        info = json.loads(row.model_info)
        assert info["llm_draft_in_progress"] is False
        assert len(info["director_llm_attempts"]) == 8
        assert info["director_llm_attempts"][-1]["status"] == expected


def test_stage_b_provider_failure_and_finish_length_do_not_retry(monkeypatch):
    for label, failure, finish_reason, expected in [
        ("provider-failure", RuntimeError("provider down"), None, "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_PROVIDER_FAILED"),
        ("finish-length", None, "length", "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_OUTPUT_TRUNCATED"),
    ]:
        init_db(); scene, treatment, stage_a, materialized, stage_b = _payloads(); packet_fp = f"stage-b-{label}"; _seed_packet(treatment, stage_a, materialized, packet_fp)
        monkeypatch.setattr(api, "_build_preview", lambda *_args, **_kwargs: (treatment, {"scene": scene}, None))
        monkeypatch.setattr(api, "_make_decision_packet", lambda *_args, **_kwargs: {"packet_fingerprint": packet_fp})
        monkeypatch.setattr(api, "_director_llm_profile_preflight", lambda: (_profile(), {"profile_id": "test-profile", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test", "enabled": True}))
        calls = []
        def transport(*_args, **kwargs):
            calls.append(1)
            if failure: raise failure
            kwargs["audit_callback"]({"finish_reason": finish_reason, "choice_index": 0})
            return json.dumps(stage_b, ensure_ascii=False)
        monkeypatch.setattr(api.llm_client, "call_llm", transport)
        with pytest.raises(api.HTTPException) as exc:
            api.generate_director_creative_enrichment_llm_draft(990453, 1, api.DirectorCreativeEnrichmentLlmDraftRequest(scene_id="E01_SC001", packet_fingerprint=packet_fp, confirmed=True, allow_external_call=True, authorization_id="mock-stage-b-auth"))
        assert exc.value.detail["code"] == expected and calls == [1]


def test_stage_b_binding_race_and_ledger_race_fail_closed(monkeypatch):
    scene, treatment, stage_a, materialized, stage_b = _payloads()
    base_persist = api._persist_stage_b_raw_forensic
    for label, mutate in [("binding-race", "binding"), ("ledger-race", "ledger")]:
        init_db(); packet_fp = f"stage-b-{label}"; packet_id = _seed_packet(treatment, stage_a, materialized, packet_fp)
        monkeypatch.setattr(api, "_build_preview", lambda *_args, **_kwargs: (treatment, {"scene": scene}, None))
        monkeypatch.setattr(api, "_make_decision_packet", lambda *_args, **_kwargs: {"packet_fingerprint": packet_fp})
        monkeypatch.setattr(api, "_director_llm_profile_preflight", lambda: (_profile(), {"profile_id": "test-profile", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test", "enabled": True}))
        monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **kwargs: kwargs["audit_callback"]({"finish_reason": "stop"}) or json.dumps(stage_b, ensure_ascii=False))
        def raced(*args, **kwargs):
            result = base_persist(*args, **kwargs)
            with Session() as session:
                row = session.query(DecisionPacketRecord).filter_by(id=packet_id).first(); info = json.loads(row.model_info)
                if mutate == "binding": info["progressive_director_authoring"]["stage_a"]["materialized_fingerprint"] = "drift"
                else: info["director_llm_attempts"].append({"attempt_id": "attempt-8", "status": "RACE"})
                row.model_info = json.dumps(info, ensure_ascii=False); session.commit()
            return result
        monkeypatch.setattr(api, "_persist_stage_b_raw_forensic", raced)
        with pytest.raises(api.HTTPException) as exc:
            api.generate_director_creative_enrichment_llm_draft(990453, 1, api.DirectorCreativeEnrichmentLlmDraftRequest(scene_id="E01_SC001", packet_fingerprint=packet_fp, confirmed=True, allow_external_call=True, authorization_id="mock-stage-b-auth"))
        assert "CONFLICT" in exc.value.detail["code"]


def test_confirm_gate_requires_merged_proposal_after_stage_b_validation():
    info = {"progressive_director_authoring": {"stage_b": {"status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_VALIDATED", "authoring_stage": "CREATIVE_ENRICHMENT", "merge_state": "PENDING"}}}
    assert api._progressive_stage_b_complete(info, {"decision": "awaiting_llm"}) is False
    info["progressive_director_authoring"]["stage_b"]["merge_state"] = "MERGED"
    candidate = {"decision": "ready_for_review", "creative_projection": {"status": "PROPOSED"}}
    assert api._progressive_stage_b_complete(info, candidate) is True


@pytest.mark.parametrize(
    "label,mode,expected",
    [
        ("forensic", "forensic", "DIRECTOR_CREATIVE_ENRICHMENT_FORENSIC_PERSISTENCE_FAILED"),
        ("merge", "merge", "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_COMPILED_CONTRACT_INVALID"),
        ("compiled", "compiled", "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_COMPILED_CONTRACT_INVALID"),
    ],
)
def test_stage_b_persistence_merge_and_compiled_failures_cleanup(monkeypatch, label, mode, expected):
    init_db(); scene, treatment, stage_a, materialized, stage_b = _payloads(); packet_fp = f"stage-b-{label}"; _seed_packet(treatment, stage_a, materialized, packet_fp)
    monkeypatch.setattr(api, "_build_preview", lambda *_args, **_kwargs: (treatment, {"scene": scene}, None))
    monkeypatch.setattr(api, "_make_decision_packet", lambda *_args, **_kwargs: {"packet_fingerprint": packet_fp})
    monkeypatch.setattr(api, "_director_llm_profile_preflight", lambda: (_profile(), {"profile_id": "test-profile", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test", "enabled": True}))
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **kwargs: kwargs["audit_callback"]({"finish_reason": "stop"}) or json.dumps(stage_b, ensure_ascii=False))
    if mode == "forensic":
        monkeypatch.setattr(api, "_persist_stage_b_raw_forensic", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("forensic unavailable")))
    elif mode == "merge":
        monkeypatch.setattr(api, "compile_progressive_director_proposal", lambda **_kwargs: (_ for _ in ()).throw(ValueError("merge unavailable")))
    else:
        monkeypatch.setattr(api, "validate_source_grounded_contract_v2", lambda *_args, **_kwargs: {"status": "blocked", "errors": [{"code": "MOCK_COMPILED_INVALID"}]})
    with pytest.raises(api.HTTPException) as exc:
        api.generate_director_creative_enrichment_llm_draft(990453, 1, api.DirectorCreativeEnrichmentLlmDraftRequest(scene_id="E01_SC001", packet_fingerprint=packet_fp, confirmed=True, allow_external_call=True, authorization_id="mock-stage-b-auth"))
    assert exc.value.detail["code"] == expected
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(packet_fingerprint=packet_fp).first(); info = json.loads(row.model_info)
        assert info["llm_draft_in_progress"] is False
