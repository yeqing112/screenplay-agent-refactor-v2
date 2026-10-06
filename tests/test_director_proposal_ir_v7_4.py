"""Provider-free V7.4 DirectorProposalIR boundary tests."""
from __future__ import annotations

import copy
import json

import pytest

from core.director_proposal_ir import (
    DIRECTOR_PROPOSAL_IR_VERSION,
    DirectorProposalIRValidationError,
    compile_director_proposal_ir,
    parse_director_proposal_ir,
    validate_director_proposal_ir,
)
from core.director_source_grounded import build_source_grounded_director_preview, project_source_authoring_units


def scene12() -> dict:
    actions = [{"action_id": f"E01_SC001_A{i:03d}", "text": f"action {i}", "source_evidence": {"evidence_id": f"A{i:03d}"}} for i in range(1, 9)]
    dialogues = [{"dialogue_id": f"E01_SC001_D{i:03d}", "speaker": "P1", "text": f"line {i}", "speaker_binding": {"classification": "SOURCE_LITERAL_BINDING", "binding_type": "SOURCE_LITERAL"}, "source_evidence": {"evidence_id": f"D{i:03d}"}} for i in range(1, 5)]
    blocks = []
    refs = [("ACTION", x["action_id"]) for x in actions] + [("DIALOGUE", x["dialogue_id"]) for x in dialogues]
    for order, (kind, ref) in enumerate(refs, 1):
        blocks.append({"order": order * 10, "type": kind, "ref": ref})
    return {"scene_id": "E01_SC001", "name": "", "timeline_origin": "SOURCE_GROUNDED", "source_grounded_schema_version": "source_grounded_script_payload_v3_1", "source_identity_evidence": [{"evidence_id": "SCENE"}], "participants": [{"id": "P1", "name": "P1"}], "actions": actions, "dialogues": dialogues, "script_blocks": blocks, "beats": []}


def ir12() -> dict:
    units = project_source_authoring_units(scene12())
    beats = []
    for i in range(0, 12, 3):
        beats.append({"refs": [unit["unit_id"] for unit in units[i:i + 3]], "purpose": f"purpose {i}", "objective": f"objective {i}", "information_change": f"change {i}", "audience_effect": f"effect {i}", "performance": f"performance {i}", "transition": f"transition {i}", "hook": i == 9, "character_effects": []})
    return {"version": DIRECTOR_PROPOSAL_IR_VERSION, "scene_label": "warehouse", "scene_objective": "hold the uncertainty", "dramatic_question": "who moves first?", "beats": beats, "character_directions": [], "performance_arc": [], "information_strategy": [], "rhythm_strategy": {}, "visual_priority": [], "scene_exit_intent": "leave the choice open", "prohibited_interpretations": [], "passthrough_refs": [], "unknowns": [], "confidence": 0.8, "note": "offline golden"}


def test_flat_schema_and_forbidden_fields():
    ir = ir12(); report = validate_director_proposal_ir(ir, source_units=project_source_authoring_units(scene12()), declared_participants=scene12()["participants"])
    assert report["status"] == "qualified"
    for field in ("creative_projection", "creative_beat_id", "authority", "source_constraints", "dialogue", "speaker"):
        bad = copy.deepcopy(ir); bad[field] = {}
        assert any(x["code"] == "DIRECTOR_PROPOSAL_IR_FORBIDDEN_FIELD" for x in validate_director_proposal_ir(bad, source_units=project_source_authoring_units(scene12()), declared_participants=scene12()["participants"])["errors"])


def test_unknown_ref_missing_coverage_and_unknown_participant_fail():
    units = project_source_authoring_units(scene12()); ir = ir12()
    bad = copy.deepcopy(ir); bad["beats"][0]["refs"] = ["UNKNOWN"]
    assert any(x["code"] == "DIRECTOR_PROPOSAL_IR_SOURCE_REF_INVALID" for x in validate_director_proposal_ir(bad, source_units=units, declared_participants=scene12()["participants"])["errors"])
    bad = copy.deepcopy(ir); bad["beats"] = bad["beats"][:-1]
    assert any(x["code"] == "DIRECTOR_PROPOSAL_IR_SOURCE_COVERAGE_INCOMPLETE" for x in validate_director_proposal_ir(bad, source_units=units, declared_participants=scene12()["participants"])["errors"])
    bad = copy.deepcopy(ir); bad["beats"][0]["character_effects"] = [{"character_ref": "invented", "effect": "anything"}]
    assert any(x["code"] == "DIRECTOR_PROPOSAL_IR_PARTICIPANT_INVALID" for x in validate_director_proposal_ir(bad, source_units=units, declared_participants=scene12()["participants"])["errors"])


def test_five_beat_parse_compile_pass_and_local_metadata():
    scene = scene12(); baseline = build_source_grounded_director_preview(scene=scene); ir = ir12()
    candidate = compile_director_proposal_ir(ir, baseline, scene)
    assert candidate["compiler_report"]["local_compiler_new_creative_decision_count"] == 0
    assert [b["creative_beat_id"] for b in candidate["creative_projection"]["creative_beats"]] == [f"DCB_E01_SC001_{i:03d}" for i in range(1, 5)]
    assert all(b["authority"] == "AUTHORIZED_CREATIVE_PROJECTION" for b in candidate["creative_projection"]["creative_beats"])
    assert candidate["source_constraints"] == baseline["source_constraints"]
    assert candidate["compiler_report"]["compiled_contract_validation"]["status"] == "qualified"
    assert parse_director_proposal_ir(json.dumps(ir, ensure_ascii=False))["version"] == DIRECTOR_PROPOSAL_IR_VERSION


def test_compiler_is_deterministic_and_dialogue_source_is_unchanged():
    scene = scene12(); baseline = build_source_grounded_director_preview(scene=scene); ir = ir12()
    first = compile_director_proposal_ir(ir, baseline, scene); second = compile_director_proposal_ir(ir, baseline, scene)
    assert first == second
    dialogue = [u for u in first["source_constraints"]["source_authoring_units"] if u["source_type"] == "SOURCE_DIALOGUE"]
    assert [(u["speaker"], u["text"], u["binding_type"]) for u in dialogue] == [("P1", "line 1", "SOURCE_LITERAL"), ("P1", "line 2", "SOURCE_LITERAL"), ("P1", "line 3", "SOURCE_LITERAL"), ("P1", "line 4", "SOURCE_LITERAL")]


def test_historical_malformed_response_remains_parse_failure():
    malformed = '{"creative_projection":{"creative_beats":[]}} {"creative_beat_id":"DCB_E01_SC001_03"}'
    with pytest.raises(Exception):
        parse_director_proposal_ir(malformed)


def test_invalid_ir_never_reaches_compiler():
    scene = scene12(); baseline = build_source_grounded_director_preview(scene=scene); bad = ir12(); bad["beats"][0]["refs"] = ["unknown"]
    with pytest.raises(DirectorProposalIRValidationError):
        compile_director_proposal_ir(bad, baseline, scene)

