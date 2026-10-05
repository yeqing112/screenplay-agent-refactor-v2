from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.video_compilers.minimax_h3 import H3_CAPABILITIES, MiniMaxH3Compiler
from core.video_dialogue_coverage import DialogueCoverageError, audit_dialogue_phrase_coverage
from core.video_intent_ir import build_video_intent_ir


ROOT = Path(__file__).resolve().parents[1]
DECISIONS = json.loads((ROOT / "docs/prompt-quality/v4/DIRECTOR_DECISION_IR.json").read_text(encoding="utf-8"))["canary_shots"]


def _decision(shot_id: str) -> dict:
    return next(x for x in DECISIONS if x["shot_id"] == shot_id)


def test_sc002_002_single_emission_and_occurrence_contract():
    intent = build_video_intent_ir(_decision("SH_E01_SC002_002"))
    compiled = MiniMaxH3Compiler().compile(intent, H3_CAPABILITIES)
    prompt = compiled.prompt
    exact = intent.dialogue.authoritative_text
    assert prompt.count("<d>") == 4
    assert exact not in prompt
    assert [x["total_occurrences"] for x in compiled.provider_capability_requirements["dialogue_occurrence_audit"]["phrase_occurrences"]] == [1, 1, 1, 1]
    assert compiled.provider_capability_requirements["dialogue_occurrence_audit"]["plain_full_authoritative_occurrence"] == 0
    assert "Authoritative dialogue text" not in prompt


def test_phrase_coverage_duplicate_missing_and_order_fail_closed():
    with pytest.raises(DialogueCoverageError, match="DIALOGUE_PHRASE_DUPLICATION"):
        audit_dialogue_phrase_coverage("ABC", [{"start_time": 0, "text": "A"}, {"start_time": 1, "text": "B"}, {"start_time": 2, "text": "B"}, {"start_time": 3, "text": "C"}])
    with pytest.raises(DialogueCoverageError, match="DIALOGUE_PHRASE_COVERAGE_INCOMPLETE"):
        audit_dialogue_phrase_coverage("ABC", [{"start_time": 0, "text": "A"}, {"start_time": 1, "text": "C"}])
    with pytest.raises(DialogueCoverageError, match="DIALOGUE_PHRASE_ORDER_MISMATCH"):
        audit_dialogue_phrase_coverage("ABC", [{"start_time": 0, "text": "B"}, {"start_time": 1, "text": "A"}, {"start_time": 2, "text": "C"}])


def test_intents_are_provider_neutral_and_camera_is_subtle():
    intent = build_video_intent_ir(_decision("SH_E01_SC002_002"))
    serialized = json.dumps(intent.as_dict(), ensure_ascii=False).lower()
    for token in ("minimax", "h3", "75api", "<d>", "prompt syntax"):
        assert token not in serialized
    assert intent.performance_realism.reaction_delay == "0.2-0.6 seconds"
    assert intent.camera_realism.stability == "restrained_handheld"
    assert intent.camera_realism.micro_drift == "very_subtle"
    assert intent.camera_realism.mechanical_precision is False


def test_density_terminal_hold_and_prop_purity():
    intent = build_video_intent_ir(_decision("SH_E01_SC002_002"))
    compiled = MiniMaxH3Compiler().compile(intent, H3_CAPABILITIES)
    audit = compiled.prompt_complexity
    assert audit.micro_actions >= 0
    assert audit.camera_realism_modifiers >= 0
    assert compiled.prompt.count("handbag") == 1
    assert compiled.prompt.count("bag strap") == 1
    assert compiled.prompt.count("apple") == 0
    assert compiled.prompt.split("13.5–14s:", 1)[1].count("<d>") == 0
    assert "shaky camera" not in compiled.prompt.lower()
