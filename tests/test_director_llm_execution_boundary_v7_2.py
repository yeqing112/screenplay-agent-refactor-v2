"""V7.2 Director LLM execution-boundary tests.

Every provider interaction is mocked.  The tests use the hermetic pytest DB
and never touch the persisted V7 production database.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from api import director_treatment_api as api
from core import llm
from models import Book, DecisionPacketRecord, DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer, Session, init_db
from tests.test_director_source_grounded_authoring_v7_1 import _preview, _scene


def _profile():
    return {"id": "isolated-director-profile", "provider": "mock", "model_name": "director-v3-test", "base_url": "mock://director", "enabled": True, "key_configured": True, "default_params": {}}


def _packet(treatment: dict) -> tuple[int, int]:
    init_db()
    with Session() as session:
        book = Book(title="V7.2 isolated", filename="v7.2-isolated", status="imported")
        session.add(book)
        session.flush()
        row = DecisionPacketRecord(book_id=book.id, domain="director_treatment", scope=json.dumps({"book_id": book.id, "episode": 1, "scene_id": treatment["scene_id"], "scene_name": ""}), packet_fingerprint=f"v72-packet-{uuid.uuid4().hex}", evidence="[]", unknowns="[]", conflicts="[]", allowed_operations="[]", proposal=json.dumps({"decision": "awaiting_llm"}), model_info=json.dumps({"llm_draft_in_progress": True}))
        session.add(row)
        session.commit()
        return book.id, row.id


def _valid_response(treatment: dict) -> str:
    units = treatment["source_constraints"]["source_authoring_units"]
    return json.dumps({
        "version": "director_proposal_ir_v1",
        "scene_label": "",
        "scene_objective": "Hold the uncertainty.",
        "dramatic_question": "What changes after the line?",
        "beats": [{"refs": [unit["unit_id"] for unit in units], "purpose": "SETUP_RELATIONSHIP", "objective": "Observe the room.", "information_change": "The audience recognizes a pattern.", "audience_effect": "Suspicion rises.", "performance": "Withhold certainty.", "transition": "", "hook": False, "character_effects": []}],
        "character_directions": [], "performance_arc": [], "information_strategy": [], "rhythm_strategy": {}, "visual_priority": [], "scene_exit_intent": "", "prohibited_interpretations": [], "passthrough_refs": [],
        "unknowns": [],
        "confidence": 0.8,
        "note": "offline test proposal",
    }, ensure_ascii=False)


def _run(monkeypatch, response: str):
    treatment = _preview()
    evidence = {"scene": _scene(), "characters": []}
    book_id, packet_id = _packet(treatment)
    calls = []

    def fake_call(*args, **kwargs):
        calls.append(kwargs)
        callback = kwargs.get("audit_callback")
        if callback:
            callback({"profile_id": "isolated-director-profile", "vendor_model": "director-v3-test", "vendor_host": "mock://director", "request_fingerprint": "request-audit", "response_sha256": "audit-response", "provider_request_id": "request-1"})
        return response

    monkeypatch.setattr(api.llm_client, "_resolve_llm_profile", lambda *_args, **_kwargs: _profile())
    monkeypatch.setattr(api.llm_client, "call_llm", fake_call)
    with Session() as session:
        packet_fingerprint_value = session.query(DecisionPacketRecord).filter_by(id=packet_id).one().packet_fingerprint
    result = None
    error = None
    try:
        result = api._execute_source_grounded_v3_proposal(book_id=book_id, packet_id=packet_id, packet_fingerprint_value=packet_fingerprint_value, treatment=treatment, evidence=evidence, authorization_id="isolated-v7-2-authorization")
    except Exception as exc:  # test callers assert the exact HTTP detail
        error = exc
    with Session() as session:
        packet = session.query(DecisionPacketRecord).filter_by(id=packet_id).one()
        model_info = json.loads(packet.model_info)
        treatment_count = session.query(DirectorTreatment).filter_by(book_id=book_id).count()
        authority_count = session.query(DirectorTreatmentAuthority).filter_by(book_id=book_id).count()
        pointer_count = session.query(DirectorTreatmentPointer).filter_by(book_id=book_id).count()
    return result, error, calls, model_info, packet, (treatment_count, authority_count, pointer_count)


def test_v3_prompt_is_source_grounded_and_has_no_old_beat_requirement():
    system, user = api._source_grounded_v3_prompt(_preview(), {"characters": []})
    assert "SOURCE_AUTHORING_UNITS" in user
    assert "IMMUTABLE_SOURCE_CONSTRAINTS" in user
    assert "DIRECTOR_PROPOSAL_IR_V1" in system or "PROPOSAL_IR_VERSION" in user
    assert "CREATIVE_PROJECTION_SCHEMA" not in user
    assert "必须沿用已有 character id 和 beat_id" not in user
    assert "creative_projection" in system
    assert "扁平的创意提案" in system


def test_v3_prompt_freezes_advisory_asset_context_out_of_request_identity():
    _, user = api._source_grounded_v3_prompt(_preview(), {"characters": [{"id": "mutable-asset"}]})
    assert "ADVISORY_ASSET_CONTEXT=[]" in user
    assert "mutable-asset" not in user


def test_v3_execution_uses_one_transport_attempt_and_top_level_creative_projection(monkeypatch):
    result, error, calls, model_info, packet, downstream = _run(monkeypatch, _valid_response(_preview()))
    assert error is None
    assert result["domain_write_performed"] is False
    assert result["provider"]["calls"] == 1
    assert calls[0]["retries"] == 1
    assert calls[0]["temperature"] == 0.0
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert downstream == (0, 0, 0)
    assert model_info["event_trace"] == ["TRANSPORT", "RAW_PERSIST", "PARSE", "IR_VALIDATE", "COMPILE", "PROPOSAL_PERSIST"]
    assert model_info["raw_response_forensic"]["persisted_before_parse"] is True
    assert len(model_info["raw_response_forensic"]["raw_response_sha256"]) == 64
    assert json.loads(packet.proposal)["proposal_origin"] == "PROVIDER_PROPOSAL"


def test_v3_raw_forensic_is_committed_before_parser(monkeypatch):
    order = []
    original_persist = api._persist_v3_raw_forensic
    original_parse = api.parse_director_proposal_ir

    def persist(*args, **kwargs):
        order.append("RAW_PERSIST")
        return original_persist(*args, **kwargs)

    def parse(*args, **kwargs):
        order.append("PARSE")
        return original_parse(*args, **kwargs)

    monkeypatch.setattr(api, "_persist_v3_raw_forensic", persist)
    monkeypatch.setattr(api, "parse_director_proposal_ir", parse)
    result, error, *_ = _run(monkeypatch, _valid_response(_preview()))
    assert error is None
    assert result["provider"]["calls"] == 1
    assert order == ["RAW_PERSIST", "PARSE"]


def test_v3_invalid_json_keeps_raw_and_never_retries(monkeypatch):
    result, error, calls, model_info, packet, downstream = _run(monkeypatch, "not valid json")
    assert result is None
    assert error.status_code == 502
    assert error.detail["code"] == "DIRECTOR_LLM_OUTPUT_INVALID"
    assert len(calls) == 1
    assert model_info["last_llm_draft_failure"] == "DIRECTOR_LLM_OUTPUT_INVALID"
    assert model_info["raw_response_forensic"]["raw_response"] == "not valid json"
    assert model_info["raw_response_forensic"]["parse_started"] is True
    assert downstream == (0, 0, 0)


def test_v3_invalid_semantic_candidate_keeps_forensic_and_never_retries(monkeypatch):
    bad = json.loads(_valid_response(_preview()))
    bad["beats"][0]["refs"] = ["SAU_UNKNOWN"]
    result, error, calls, model_info, packet, downstream = _run(monkeypatch, json.dumps(bad, ensure_ascii=False))
    assert result is None
    assert error.detail["code"] == "DIRECTOR_PROPOSAL_IR_INVALID"
    assert len(calls) == 1
    assert model_info["raw_response_forensic"]["persisted_before_parse"] is True
    assert downstream == (0, 0, 0)


def test_v3_schema_gate_blocks_additional_provider_fields_before_runtime(monkeypatch):
    bad = json.loads(_valid_response(_preview()))
    bad["character_directions"] = [{"character_ref": "P1", "unexpected": "field"}]
    result, error, calls, model_info, packet, downstream = _run(monkeypatch, json.dumps(bad, ensure_ascii=False))
    assert result is None
    assert error.detail["code"] == "DIRECTOR_PROPOSAL_IR_SCHEMA_INVALID"
    assert len(calls) == 1
    assert model_info["event_trace"] == ["TRANSPORT", "RAW_PERSIST", "PARSE", "IR_SCHEMA_VALIDATE"]
    assert model_info["last_llm_draft_failure"] == "DIRECTOR_PROPOSAL_IR_SCHEMA_INVALID"
    assert downstream == (0, 0, 0)


def test_v3_provider_direction_shorthand_reaches_proposal_only_boundary(monkeypatch):
    value = json.loads(_valid_response(_preview()))
    value["character_directions"] = [{"character_ref": "P1", "direction": "withhold certainty"}]
    result, error, calls, model_info, packet, downstream = _run(monkeypatch, json.dumps(value, ensure_ascii=False))
    assert error is None
    assert len(calls) == 1
    assert result["domain_write_performed"] is False
    assert json.loads(packet.proposal)["creative_projection"]["character_directions"][0]["direction"] == "withhold certainty"
    assert downstream == (0, 0, 0)


def test_v3_required_keys_are_only_proposal_ir(monkeypatch):
    seen = []
    original = api.parse_director_proposal_ir

    def parse(*args, **kwargs):
        seen.append("proposal_ir")
        return original(*args, **kwargs)

    monkeypatch.setattr(api, "parse_director_proposal_ir", parse)
    result, error, *_ = _run(monkeypatch, _valid_response(_preview()))
    assert error is None
    assert seen == ["proposal_ir"]


def test_v3_candidate_does_not_need_to_echo_source_constraints(monkeypatch):
    result, error, *_ = _run(monkeypatch, _valid_response(_preview()))
    assert error is None
    assert result["candidate"]["source_constraints"]


def test_real_v3_endpoint_branch_is_proposal_only(monkeypatch):
    init_db()
    with Session() as session:
        book = Book(title="V7.2 endpoint", filename=f"endpoint-{uuid.uuid4().hex}", status="imported")
        session.add(book); session.commit(); book_id = book.id
    treatment = _preview()
    treatment["prompt_fingerprint"] = f"endpoint-preview-{uuid.uuid4().hex}"
    treatment["source_authoring_units_fingerprint"] = "units-fingerprint"
    evidence = {"scene": _scene(), "characters": [], "scene_id": "E01_SC001", "scene_name": "", "script": {"id": 1, "revision": "1"}, "locked_references": []}
    packet = {"packet_fingerprint": f"endpoint-packet-{uuid.uuid4().hex}", "scope": {"book_id": book_id, "episode": 1, "scene_id": "E01_SC001", "scene_name": ""}, "evidence": [], "unknowns": [], "conflicts": [], "allowed_operations": []}
    monkeypatch.setattr(api, "_build_preview", lambda *_args, **_kwargs: (treatment, evidence, SimpleNamespace(id=1)))
    monkeypatch.setattr(api, "_make_decision_packet", lambda *_args, **_kwargs: packet)
    calls = []
    monkeypatch.setattr(api.llm_client, "_resolve_llm_profile", lambda *_args, **_kwargs: _profile())
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *args, **kwargs: calls.append(kwargs) or _valid_response(treatment))
    req = api.DirectorTreatmentLlmDraftRequest(episode=1, confirmed=True, allow_external_call=True, workflow_profile="production", packet_fingerprint=packet["packet_fingerprint"], authorization_id="isolated-v7-2-endpoint-authorization")
    result = api.generate_director_treatment_llm_draft(book_id, 1, req)
    assert result["domain_write_performed"] is False
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["temperature"] == 0.0
    assert calls[0]["retries"] == 1
    with Session() as session:
        assert session.query(DirectorTreatment).filter_by(book_id=book_id).count() == 0
        assert session.query(DirectorTreatmentAuthority).filter_by(book_id=book_id).count() == 0
        assert session.query(DirectorTreatmentPointer).filter_by(book_id=book_id).count() == 0


def test_v3_coverage_is_twelve_units_for_real_shape():
    preview = _preview()
    assert len(preview["source_constraints"]["source_authoring_units"]) == 5
    assert api.validate_source_grounded_contract_v2(preview, scene=_scene())["covered_story_unit_count"] == 5


@pytest.mark.parametrize("failure,expected", [
    (httpx.ConnectError("connect"), "DIRECTOR_LLM_CALL_FAILED"),
    (httpx.ReadTimeout("timeout"), "DIRECTOR_LLM_SUBMISSION_AMBIGUOUS"),
])
def test_v3_transport_failures_are_single_attempt(monkeypatch, failure, expected):
    def raise_failure(*args, **kwargs):
        raise failure

    monkeypatch.setattr(api.llm_client, "_resolve_llm_profile", lambda *_args, **_kwargs: _profile())
    monkeypatch.setattr(api.llm_client, "call_llm", raise_failure)
    treatment = _preview(); evidence = {"scene": _scene(), "characters": []}; book_id, packet_id = _packet(treatment)
    with Session() as session:
        packet_fingerprint_value = session.query(DecisionPacketRecord).filter_by(id=packet_id).one().packet_fingerprint
    with pytest.raises(Exception) as exc:
        api._execute_source_grounded_v3_proposal(book_id=book_id, packet_id=packet_id, packet_fingerprint_value=packet_fingerprint_value, treatment=treatment, evidence=evidence, authorization_id="isolated-v7-2-transport-authorization")
    assert exc.value.detail["code"] == expected


def test_call_llm_429_with_one_attempt_does_not_post_again(monkeypatch):
    monkeypatch.delenv("E2E_EXTERNAL_RUNTIME", raising=False)
    class Resp:
        status_code = 429
        text = "rate limited"
        headers = {"Retry-After": "0"}

        def raise_for_status(self):
            raise httpx.HTTPStatusError("429", request=httpx.Request("POST", "http://mock"), response=httpx.Response(429, request=httpx.Request("POST", "http://mock")))

    calls = []

    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def post(self, *_args, **_kwargs): calls.append(1); return Resp()

    monkeypatch.setattr(llm.httpx, "Client", Client)
    monkeypatch.setattr(llm, "_resolve_llm_profile", lambda *_args, **_kwargs: _profile())
    monkeypatch.setattr(llm._limiter, "wait_if_needed", lambda *_args, **_kwargs: None)
    with pytest.raises(httpx.HTTPStatusError):
        llm.call_llm("prompt", model_profile=_profile(), retries=1, estimated_tokens=1)
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["connect", "timeout", "http500", "429"])
def test_call_llm_transport_matrix_has_one_post(kind, monkeypatch):
    monkeypatch.delenv("E2E_EXTERNAL_RUNTIME", raising=False)
    calls = []

    class Resp:
        status_code = 500 if kind == "http500" else 429
        text = "transport failure"
        headers = {"Retry-After": "0"}

        def raise_for_status(self):
            raise httpx.HTTPStatusError("failure", request=httpx.Request("POST", "http://mock"), response=httpx.Response(self.status_code, request=httpx.Request("POST", "http://mock")))

    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def post(self, *_args, **_kwargs):
            calls.append(1)
            if kind == "connect":
                raise httpx.ConnectError("connect", request=httpx.Request("POST", "http://mock"))
            if kind == "timeout":
                raise httpx.ReadTimeout("timeout", request=httpx.Request("POST", "http://mock"))
            return Resp()

    monkeypatch.setattr(llm.httpx, "Client", Client)
    monkeypatch.setattr(llm, "_resolve_llm_profile", lambda *_args, **_kwargs: _profile())
    monkeypatch.setattr(llm._limiter, "wait_if_needed", lambda *_args, **_kwargs: None)
    with pytest.raises((httpx.ConnectError, httpx.ReadTimeout, httpx.HTTPStatusError)):
        llm.call_llm("prompt", model_profile=_profile(), retries=1, estimated_tokens=1)
    assert len(calls) == 1


def test_call_llm_sends_json_response_format_to_provider(monkeypatch):
    monkeypatch.delenv("E2E_EXTERNAL_RUNTIME", raising=False)
    requests = []

    class Resp:
        status_code = 200
        text = '{"choices":[{"message":{"content":"{\\"ok\\":true}"}}]}'
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"ok":true}'}}], "usage": {"total_tokens": 1}}

    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def post(self, *args, **kwargs):
            requests.append((args, kwargs))
            return Resp()

    monkeypatch.setattr(llm.httpx, "Client", Client)
    monkeypatch.setattr(llm, "_resolve_llm_profile", lambda *_args, **_kwargs: _profile())
    monkeypatch.setattr(llm._limiter, "wait_if_needed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(llm._limiter, "record", lambda *_args, **_kwargs: None)

    result = llm.call_llm(
        "prompt",
        model_profile=_profile(),
        retries=1,
        estimated_tokens=1,
        response_format={"type": "json_object"},
    )

    assert result == '{"ok":true}'
    assert len(requests) == 1
    payload = requests[0][1]["json"]
    assert payload["response_format"] == {"type": "json_object"}


def test_v3_profile_preflight_does_not_persist_secret(monkeypatch):
    profile = {**_profile(), "api_key": "secret-must-not-persist"}
    monkeypatch.setattr(api.llm_client, "_resolve_llm_profile", lambda *_args, **_kwargs: profile)
    _, snapshot = api._director_llm_profile_preflight()
    assert "api_key" not in snapshot
    assert snapshot["profile_id"] == profile["id"]
