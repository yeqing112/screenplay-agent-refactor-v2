"""Deterministic salvage contract tests; no provider or production writes."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from core.script_ir import validate_script_ir
from core.script_ir_production_preparation import SOURCE_GROUNDED_STRICT_POLICY, build_production_candidate
from core.script_ir_source_requirements import compile_script_ir_source_requirements
from core.source_structuring_salvage import salvage_candidate_v2
from core.source_structuring_v2 import canonical_script_payload_v2, ground_candidate_v2, semantic_diff_source_to_script_ir
ROOT = Path(__file__).resolve().parents[1]
PARSED = ROOT / "docs" / "canonical-canary" / "v5_3-authorized-source-structuring-v2" / "PARSED_CANDIDATE_V2.json"
EXPECTED_SOURCE_SHA = "190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1"
TARGET = "也许是你自己"
TEST_RAW_SOURCE = json.loads(r'''"\u987e\u6c89\u5e26\u6797\u665a\u8fdb\u5165\u6697\u623f\u3002\u7ea2\u8272\u5b89\u5168\u706f\u5ffd\u660e\u5ffd\u6697\uff0c\u5899\u4e0a\u7684\u6c34\u6e0d\u50cf\u4e00\u5f20\u5f20\u5012\u7f6e\u7684\u5730\u56fe\u3002\u6697\u623f\u4e2d\u592e\u6446\u7740\u4e00\u53ea\u94c1\u76d2\uff0c\u76d2\u76d6\u4e0a\u8d34\u7740\u6bcd\u4eb2\u7684\u624b\u5199\u6807\u7b7e\uff1a\u7b2c\u4e03\u6b21\u6f6e\u6c50\u3002\n\n\u94c1\u76d2\u662f\u7a7a\u7684\uff0c\u53ea\u6709\u4e00\u5c0f\u6bb5\u70e7\u7126\u7684\u80f6\u7247\u548c\u4e00\u679a\u6d77\u9e25\u522b\u9488\u3002\u6797\u665a\u8ba4\u51fa\u522b\u9488\u4e0e\u7167\u7247\u91cc\u5c0f\u5973\u5b69\u4f69\u6234\u7684\u4e00\u6a21\u4e00\u6837\uff0c\u5374\u60f3\u4e0d\u8d77\u81ea\u5df1\u7ae5\u5e74\u662f\u5426\u6765\u8fc7\u8fd9\u91cc\u3002\n\n\u987e\u6c89\u8bf4\u80f6\u7247\u88ab\u4eba\u62ff\u8d70\u4e86\u3002\u6797\u665a\u95ee\u662f\u8c01\uff0c\u4ed6\u56de\u7b54\u201c\u4e5f\u8bb8\u662f\u4f60\u81ea\u5df1\u201d\uff0c\u8bed\u6c14\u50cf\u5728\u8bd5\u63a2\u3002\u4e24\u4eba\u540c\u65f6\u542c\u89c1\u95e8\u5916\u94dc\u94c3\u54cd\u4e86\u4e00\u58f0\uff0c\u987e\u6c89\u7184\u706d\u5b89\u5168\u706f\uff0c\u62c9\u7740\u6797\u665a\u8eb2\u5230\u836f\u6c34\u67dc\u540e\u3002\n\n\u95e8\u7f1d\u4e0b\u51fa\u73b0\u4e00\u53cc\u6e7f\u900f\u7684\u76ae\u978b\u3002\u90a3\u4eba\u6ca1\u6709\u8fdb\u95e8\uff0c\u53ea\u628a\u4e00\u5f20\u8f66\u7968\u585e\u8fdb\u6765\u3002\u8f66\u7968\u80cc\u9762\u5199\u7740\uff1a\u4eca\u665a\u5341\u70b9\uff0c\u5317\u5824\u4ed3\u5e93\uff0c\u5e26\u94a5\u5319\uff0c\u4e0d\u8981\u5e26\u987e\u6c89\u3002"''')


@pytest.fixture(scope="module")
def fixture():
    raw = TEST_RAW_SOURCE
    candidate = json.loads(PARSED.read_text(encoding="utf-8"))["candidate"]
    original_grounding = ground_candidate_v2(raw, candidate, expected_source_fingerprint=EXPECTED_SOURCE_SHA)
    salvage = salvage_candidate_v2(raw, candidate)
    assert salvage["status"] == "PASS"
    salvaged = salvage["candidate"]
    salvaged_grounding = ground_candidate_v2(raw, salvaged, expected_source_fingerprint=EXPECTED_SOURCE_SHA)
    payload = canonical_script_payload_v2(salvaged_grounding["grounded_candidate"])
    strict = build_production_candidate(payload, book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
    return {"raw": raw, "candidate": candidate, "original_grounding": original_grounding, "salvage": salvage, "salvaged": salvaged, "salvaged_grounding": salvaged_grounding, "payload": payload, "strict": strict}


def _dialogues(candidate):
    return [row for scene in candidate.get("scenes", []) for row in scene.get("dialogues", [])]


def test_original_failure_exact_replay(fixture):
    codes = [row["code"] for row in fixture["original_grounding"]["errors"]]
    assert codes == ["DIALOGUE_NOT_DIRECT_QUOTE", "REPORTED_SPEECH_PROMOTED", "DIALOGUE_NOT_DIRECT_QUOTE", "REPORTED_SPEECH_PROMOTED", "SPEAKER_IDENTITY_EVIDENCE_MISSING"]


def test_two_non_direct_dialogues_are_demoted(fixture):
    assert len(fixture["salvage"]["demotions"]) == 2


def test_demotions_use_full_exact_utterance_evidence(fixture):
    for row in fixture["salvage"]["demotions"]:
        assert row["demoted_action"]["source_text"] == row["source_evidence"]["text"]


def test_demotions_do_not_paraphrase(fixture):
    assert all(row["no_semantic_rewrite"] for row in fixture["salvage"]["demotions"])


def test_duplicate_demoted_action_is_prevented(fixture):
    candidate = copy.deepcopy(fixture["candidate"])
    candidate["scenes"][0]["actions"].append({"source_text": fixture["salvage"]["demotions"][0]["demoted_action"]["source_text"]})
    result = salvage_candidate_v2(fixture["raw"], candidate)
    assert result["status"] == "PASS"
    assert result["demotions"][0]["duplicate_action_prevented"] is True


def test_target_speaker_unchanged(fixture):
    assert next(row for row in _dialogues(fixture["candidate"]) if row["text"] == TARGET)["speaker"] == next(row for row in _dialogues(fixture["salvaged"]) if row["text"] == TARGET)["speaker"]


def test_target_text_unchanged(fixture):
    assert [row["text"] for row in _dialogues(fixture["salvaged"]) if row["text"] == TARGET] == [TARGET]


def test_target_binding_type_unchanged(fixture):
    original = next(row for row in _dialogues(fixture["candidate"]) if row["text"] == TARGET)
    salvaged = next(row for row in _dialogues(fixture["salvaged"]) if row["text"] == TARGET)
    assert salvaged["binding_type"] == original["binding_type"] == "COREFERENCE_RESOLUTION"


def test_speaker_recovery_uses_same_participant_pool(fixture):
    recovery = fixture["salvage"]["recoveries"][0]
    assert recovery["speaker"] == "顾沉"
    assert recovery["rule"].startswith("same_scene_same_participant")


def test_recovered_evidence_contains_speaker_literal(fixture):
    recovery = fixture["salvage"]["recoveries"][0]
    assert "顾沉" in recovery["recovered_evidence"]["text"]


def test_recovered_evidence_precedes_utterance(fixture):
    recovery = fixture["salvage"]["recoveries"][0]
    assert recovery["recovered_evidence"]["char_start"] < 150


def test_nearest_preceding_evidence_selected_deterministically(fixture):
    recovery = fixture["salvage"]["recoveries"][0]
    assert recovery["recovered_evidence"]["char_start"] == 129


def test_zero_speaker_evidence_fails_closed(fixture):
    candidate = copy.deepcopy(fixture["candidate"])
    candidate["scenes"][0]["participants"] = [row for row in candidate["scenes"][0]["participants"] if row["name"] != "顾沉"]
    result = salvage_candidate_v2(fixture["raw"], candidate)
    assert result["status"] == "DETERMINISTIC_SALVAGE_NOT_PROVABLE"
    assert any(row["code"] == "SPEAKER_IDENTITY_RECOVERY_NOT_PROVABLE" for row in result["errors"])


def test_scene_label_is_audited_as_non_literal(fixture):
    assert fixture["salvage"]["scene_audits"][0]["status"] == "SCENE_LABEL_NOT_SOURCE_LITERAL"


def test_strict_scene_identity_comes_from_exact_source_evidence(fixture):
    assert fixture["salvaged"]["scenes"][0]["scene_label"] == "顾沉带林晚进入暗房。"


def test_no_new_source_text_is_introduced(fixture):
    original_evidence = set()
    for scene in fixture["candidate"]["scenes"]:
        original_evidence.update(scene.get("scene_evidence") or [])
        original_evidence.update(row.get("source_text") for row in scene.get("actions") or [])
        for participant in scene.get("participants") or []:
            original_evidence.update(participant.get("evidence") or [])
        for dialogue in scene.get("dialogues") or []:
            original_evidence.update(dialogue.get("utterance_evidence") or [])
            original_evidence.update(dialogue.get("speaker_identity_evidence") or [])
    new_actions = {row["source_text"] for scene in fixture["salvaged"]["scenes"] for row in scene["actions"]}
    assert new_actions - original_evidence == set()


def test_no_new_semantic_decision_is_added(fixture):
    assert fixture["salvage"]["recoveries"][0]["classification"] == "DETERMINISTIC_SPEAKER_IDENTITY_EVIDENCE_RECOVERY"
    assert fixture["salvage"]["demotions"][0]["classification"] == "DETERMINISTIC_REPORTED_SPEECH_DEMOTION"


def test_salvaged_grounding_passes(fixture):
    assert fixture["salvaged_grounding"]["status"] == "PASS"


def test_salvaged_reported_speech_promotion_count_zero(fixture):
    assert not any(row["code"] == "REPORTED_SPEECH_PROMOTED" for row in fixture["salvaged_grounding"]["errors"])


def test_strict_script_ir_preflight_qualified(fixture):
    assert validate_script_ir(fixture["strict"])["status"] == "qualified"


def test_semantic_diff_zero(fixture):
    diff = semantic_diff_source_to_script_ir(fixture["payload"], fixture["strict"])
    assert diff["status"] == "SOURCE_TO_SCRIPT_IR_SEMANTIC_DIFF_EMPTY"


def test_source_requirement_pass(fixture):
    requirements = compile_script_ir_source_requirements(source_structure=fixture["strict"])
    assert not any(row.get("blocking") and isinstance(row.get("expected_value"), dict) and row["expected_value"].get("actual") == 0 for row in requirements["requirements"])


def test_provider_calls_zero(fixture):
    assert fixture["salvage"].get("provider_calls", 0) == 0


def test_database_writes_zero(fixture):
    assert fixture["salvage"].get("production_writes", 0) == 0
