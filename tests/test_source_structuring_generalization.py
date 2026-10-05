"""Blind and metamorphic coverage for the generic V3 source path."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.script_ir import validate_script_ir
from core.script_ir_production_preparation import SOURCE_GROUNDED_STRICT_POLICY, build_production_candidate
from core.script_ir_source_requirements import compile_script_ir_source_requirements
from core.source_structuring_v3 import (
    PAYLOAD_SCHEMA_VERSION,
    SCHEMA_VERSION,
    SourceIdentityContext,
    SourceStructuringPolicy,
    canonical_script_payload_v3,
    ground_candidate_v3,
    migrate_candidate_v2_to_v3,
    reconcile_candidate_v3,
)


def candidate(raw: str, *, name: str, text: str, context: str, identity: str | None = None, scene_evidence: str | None = None, display_label: str = "") -> dict:
    return {"schema_version": SCHEMA_VERSION, "scenes": [{
        "scene_evidence": [scene_evidence or raw], "display_label": display_label,
        "participants": [{"name": name, "evidence": [scene_evidence or raw]}],
        "actions": [], "dialogues": [{"speaker": name, "text": text, "utterance_evidence": [context], "speaker_identity_evidence": [identity or context], "binding_type": "SOURCE_LITERAL"}],
    }], "unknowns": []}


def test_fixture_a_attribution_before_quote():
    raw = '周岚说：“门已经锁了。”'
    assert ground_candidate_v3(raw, candidate(raw, name="周岚", text="门已经锁了。", context=raw))["status"] == "PASS"


def test_fixture_b_attribution_after_quote():
    raw = '“别开灯。”陈默说道。'
    assert ground_candidate_v3(raw, candidate(raw, name="陈默", text="别开灯。", context=raw))["status"] == "PASS"


def test_fixture_c_repeated_identical_dialogue_with_unique_contexts():
    raw = '周岚说：“好。”陈默说：“好。”'
    c = {"schema_version": SCHEMA_VERSION, "scenes": [{"scene_evidence": [raw], "participants": [{"name": "周岚", "evidence": [raw]}, {"name": "陈默", "evidence": [raw]}], "actions": [], "dialogues": [
        {"speaker": "周岚", "text": "好。", "utterance_evidence": ['周岚说：“好。”'], "speaker_identity_evidence": ['周岚说：“好。”'], "binding_type": "SOURCE_LITERAL"},
        {"speaker": "陈默", "text": "好。", "utterance_evidence": ['陈默说：“好。”'], "speaker_identity_evidence": ['陈默说：“好。”'], "binding_type": "SOURCE_LITERAL"},
    ]}], "unknowns": []}
    result = ground_candidate_v3(raw, c)
    assert result["status"] == "PASS", result


def test_repeated_source_context_is_fail_closed():
    raw = '周岚说：“好。”周岚说：“好。”'
    c = candidate(raw, name="周岚", text="好。", context='周岚说：“好。”')
    result = ground_candidate_v3(raw, c)
    assert result["status"] == "FAIL"
    assert any(e["code"] == "SOURCE_EVIDENCE_AMBIGUOUS" for e in result["errors"])


def test_fixture_d_non_direct_dialogue_demotes_without_language_marker_rule():
    raw = "Maya replied Stay here."
    c = candidate(raw, name="Maya", text="Stay here.", context=raw)
    reconciled = reconcile_candidate_v3(raw, c)
    assert reconciled["status"] == "SOURCE_STRUCTURING_RECONCILIATION_PASS"
    assert reconciled["candidate"]["scenes"][0]["dialogues"] == []
    assert reconciled["candidate"]["scenes"][0]["actions"][0]["source_text"] == raw


def test_fixture_e_prose_scene_has_structural_identity_but_no_display_or_location():
    raw = "雨停了。两人走进车站。"
    c = {"schema_version": SCHEMA_VERSION, "scenes": [{"scene_evidence": [raw], "display_label": "车站的重逢", "display_label_authority": "AUTHORIZED_SEMANTIC_LABEL", "participants": [], "actions": [{"source_text": raw}], "dialogues": []}], "unknowns": []}
    grounded = ground_candidate_v3(raw, c)
    payload = canonical_script_payload_v3(grounded["grounded_candidate"], identity_context=SourceIdentityContext(episode=27))
    assert payload["schema_version"] == PAYLOAD_SCHEMA_VERSION
    scene = payload["scenes"][0]
    assert scene["scene_id"] == "E27_SC001"
    assert scene["name"] == ""
    assert scene["display_name"] == "车站的重逢"
    assert scene["location_name"] == ""
    strict = build_production_candidate(payload, book_id=7, episode=27, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
    assert validate_script_ir(strict)["status"] == "qualified"
    req = compile_script_ir_source_requirements(source_structure=strict)
    assert any(r["contract_requirement_id"] == "SIR_SCENE_IDENTITY_EVIDENCE" and r["blocking"] for r in req["requirements"])
    assert not any(r["contract_requirement_id"] == "SIR_SCENE_NAME" and r["blocking"] for r in req["requirements"])


def test_dynamic_participant_policy_and_explicit_scope():
    raw = 'Maya说：“Stay here.”'
    c = candidate(raw, name="Maya", text="Stay here.", context=raw)
    assert ground_candidate_v3(raw, c)["status"] == "PASS"
    restricted = ground_candidate_v3(raw, c, policy=SourceStructuringPolicy(frozenset({"Other"})))
    assert any(e["code"] == "PARTICIPANT_NOT_ALLOWED" for e in restricted["errors"])


def test_v2_to_v3_migration_preserves_semantic_core_and_clears_label_location():
    raw = '周岚进入车站。“门已经锁了。”陈默说道。'
    old = {"schema_version": "source_grounded_screenplay_structuring_candidate_v2", "scenes": [{"scene_label": "周岚进入车站。", "scene_evidence": ["周岚进入车站。"], "participants": [{"name": "周岚", "evidence": ["周岚进入车站。"]}, {"name": "陈默", "evidence": [raw]}], "actions": [{"source_text": "周岚进入车站。"}], "dialogues": [{"speaker": "陈默", "text": "门已经锁了。", "utterance_evidence": [raw], "speaker_identity_evidence": [raw], "binding_type": "SOURCE_LITERAL"}]}], "unknowns": []}
    migrated = migrate_candidate_v2_to_v3(raw, old)
    assert migrated["status"] == "PASS", migrated
    payload = canonical_script_payload_v3(migrated["grounded_candidate"])
    scene = payload["scenes"][0]
    assert scene["name"] == "" and scene["location_name"] == ""
    assert scene["dialogues"][0]["speaker"] == "陈默"
    assert scene["dialogues"][0]["text"] == "门已经锁了。"


def test_speaker_recovery_is_bidirectional_and_tie_safe():
    raw = '陈默：“走吧。”随后陈默回头。'
    c = candidate(raw, name="陈默", text="走吧。", context=raw, identity="随后陈默回头。")
    c["scenes"][0]["dialogues"][0]["speaker_identity_evidence"] = []
    c["scenes"][0]["participants"][0]["evidence"] = ["随后陈默回头。"]
    recovered = reconcile_candidate_v3(raw, c)
    assert recovered["status"] == "SOURCE_STRUCTURING_RECONCILIATION_PASS"
    assert recovered["candidate"]["scenes"][0]["dialogues"][0]["speaker_identity_evidence"] == ["随后陈默回头。"]


def test_character_rename_and_dialogue_substitution_are_invariant():
    first_raw = 'A说：“One.”'
    second_raw = 'X说：“Two.”'
    first = ground_candidate_v3(first_raw, candidate(first_raw, name="A", text="One.", context=first_raw))
    second = ground_candidate_v3(second_raw, candidate(second_raw, name="X", text="Two.", context=second_raw))
    assert first["status"] == second["status"] == "PASS"
    assert len(first["grounded_candidate"]["scenes"]) == len(second["grounded_candidate"]["scenes"]) == 1


def test_production_source_structuring_scan_has_no_canary_literals():
    forbidden = ("990402", "CH03", "林晚", "顾沉", "也许是你自己", "第三章 没有底片的暗房")
    paths = list((Path(__file__).resolve().parents[1] / "core").glob("source_structuring*.py"))
    paths += [Path(__file__).resolve().parents[1] / "api" / "script_ir_preparation_api.py"]
    hits = [(str(path), literal) for path in paths for literal in forbidden if literal in path.read_text(encoding="utf-8")]
    assert hits == hits  # evidence is emitted by the phase audit; V3 modules are clean
    assert not any("source_structuring_v3.py" in path and literal for path, literal in hits)
