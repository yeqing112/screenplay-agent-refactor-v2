"""Provider-free ProposalIR integrity closure tests."""
from __future__ import annotations

import copy
import json

import pytest
from fastapi import HTTPException

from api import director_treatment_api as api
from core.director_forensic import append_director_attempt, hydrate_director_attempt_history
from core.director_proposal_ir import (
    compile_director_proposal_ir,
    creative_semantic_diff,
    validate_director_proposal_ir,
    validate_director_proposal_ir_schema,
)
from core.director_source_grounded import build_source_grounded_director_preview, project_source_authoring_units, validate_director_contract_v2
from tests.test_director_proposal_ir_v7_4 import ir12, scene12


def _compiled():
    scene = scene12(); baseline = build_source_grounded_director_preview(scene=scene)
    return scene, baseline, compile_director_proposal_ir(ir12(), baseline, scene)


def test_compiler_proposal_status_and_never_confirmed():
    _, _, candidate = _compiled()
    assert candidate["creative_projection"]["status"] == "PROPOSED"
    assert candidate["creative_projection"]["status"] != "CONFIRMED"
    assert candidate["human_confirmation_required"] is True
    assert candidate["decision"] == "ready_for_review"


def test_proposal_validator_accepts_and_production_validator_rejects_unconfirmed():
    scene, _, candidate = _compiled()
    assert validate_director_contract_v2(candidate, scene=scene, production=False)["status"] == "qualified"
    report = validate_director_contract_v2(candidate, scene=scene, production=True)
    assert report["status"] == "blocked"
    assert any(item["code"] == "DIRECTOR_CREATIVE_PROJECTION_NOT_CONFIRMED" for item in report["errors"])


def test_confirm_service_flips_state_and_changes_no_creative_semantics():
    _, _, candidate = _compiled()
    before = copy.deepcopy(candidate)
    confirmed = copy.deepcopy(candidate)
    confirmed["creative_projection"]["status"] = "CONFIRMED"
    confirmed["creative_projection"]["confirmation_event_ref"] = "production_confirm_service"
    for beat in confirmed["creative_projection"]["creative_beats"]:
        beat["confirmation_event_ref"] = "production_confirm_service"
    diff = creative_semantic_diff(before, confirmed)
    assert diff["equal"] is True
    assert diff["creative_semantic_change_count"] == 0


def test_confirmed_candidate_passes_production_validator():
    scene, _, candidate = _compiled()
    candidate["creative_projection"]["status"] = "CONFIRMED"
    candidate["creative_projection"]["confirmation_event_ref"] = "production_confirm_service"
    assert validate_director_contract_v2(candidate, scene=scene, production=True)["status"] == "qualified"


def test_schema_and_runtime_accept_same_valid_ir():
    value = ir12(); units = project_source_authoring_units(scene12())
    assert validate_director_proposal_ir_schema(value)["status"] == "PASS"
    assert validate_director_proposal_ir(value, source_units=units, declared_participants=scene12()["participants"])["status"] == "qualified"


def test_provider_direction_shorthand_is_schema_and_runtime_safe():
    value = ir12()
    value["character_directions"] = [{"character_ref": "P1", "direction": "withhold certainty"}]
    units = project_source_authoring_units(scene12())
    assert validate_director_proposal_ir_schema(value)["status"] == "PASS"
    assert validate_director_proposal_ir(value, source_units=units, declared_participants=scene12()["participants"])["status"] == "qualified"
    baseline = build_source_grounded_director_preview(scene=scene12())
    candidate = compile_director_proposal_ir(value, baseline, scene12())
    assert candidate["creative_projection"]["character_directions"][0]["direction"] == "withhold certainty"


@pytest.mark.parametrize("mutate", [
    lambda x: x.update({"extra_top": True}),
    lambda x: x["beats"][0].update({"extra_beat": True}),
    lambda x: x["beats"][0].pop("objective"),
    lambda x: x["beats"][0].update({"hook": "yes"}),
    lambda x: x["beats"][0].update({"refs": "SAU_E01_SC001_001"}),
    lambda x: x["beats"][0].update({"character_effects": [{"character_ref": "P1"}]}),
])
def test_invalid_fixtures_fail_formal_schema_and_runtime(mutate):
    value = ir12(); mutate(value)
    schema = validate_director_proposal_ir_schema(value)
    runtime = validate_director_proposal_ir(value, source_units=project_source_authoring_units(scene12()), declared_participants=scene12()["participants"])
    assert schema["status"] == "FAIL"
    assert runtime["status"] == "blocked"


def test_history_hydration_is_idempotent_and_next_attempt_is_three():
    canonical = [
        {"attempt_id": "v7_3_attempt_1", "authorization_id": "v7_3-real-director-creative-proposal-authorization-1", "request_fingerprint": "f241d63965020afab0e9e8fc92f0c7ec05f22761e9f75214102f02a0f22c0e8c", "raw_response_sha256": "9a4792265b52e9f42c91c925f296d3ef110649c4318edf614ff7f439ef6b3566", "status": "PARSE_FAILED"},
        {"attempt_id": "v7_3_attempt_2", "authorization_id": "v7_3-real-director-creative-proposal-retry-json-mode-authorization-2", "request_fingerprint": "f241d63965020afab0e9e8fc92f0c7ec05f22761e9f75214102f02a0f22c0e8c", "raw_response_sha256": "9a4792265b52e9f42c91c925f296d3ef110649c4318edf614ff7f439ef6b3566", "status": "PARSE_FAILED"},
    ]
    first, audit1 = hydrate_director_attempt_history({}, canonical)
    second, audit2 = hydrate_director_attempt_history(first, canonical)
    assert audit1["writes"] == 1 and audit1["history_row_count"] == 2
    assert audit2["writes"] == 0 and audit2["duplicates"] == 2
    assert second == first
    future = append_director_attempt(second, request_fingerprint="new", raw_response_sha256="newsha", authorization_id="v7_5-authorization-3")
    assert future["director_llm_attempts"][-1]["attempt_id"] == "attempt-3"
    assert future["director_llm_attempts"][-1]["authorization_id"] == "v7_5-authorization-3"


def test_append_requires_authorization_at_raw_persist(monkeypatch):
    with pytest.raises(ValueError, match="DIRECTOR_LLM_AUTHORIZATION_ID_REQUIRED"):
        api._persist_v3_raw_forensic(packet_id=1, book_id=1, packet_fingerprint_value="p", raw_response="{}", profile_snapshot={"profile_id": "p", "model": "m", "base_host": "mock"}, request_fingerprint="r", provider_record={}, event_trace=[])


def test_source_grounded_execution_without_authorization_makes_no_provider_call(monkeypatch):
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider call")))
    with pytest.raises(HTTPException) as exc:
        api._execute_source_grounded_v3_proposal(book_id=1, packet_id=1, packet_fingerprint_value="p", treatment={"schema_version": "director_treatment_v3"}, evidence={})
    assert exc.value.detail["code"] == "DIRECTOR_LLM_AUTHORIZATION_ID_REQUIRED"
