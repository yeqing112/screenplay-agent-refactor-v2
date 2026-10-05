import copy
import hashlib
import json
import unittest
from pathlib import Path

from core.script_ir import validate_script_ir
from core.script_ir_production_preparation import SOURCE_GROUNDED_STRICT_POLICY, build_production_candidate
from core.source_structuring_v2 import (
    canonical_script_payload_v2,
    ground_candidate_v2,
    retain_forensic_response,
    semantic_diff_source_to_script_ir,
)
from scripts.run_authorized_source_structuring_contract_reconcile_v1 import fixture


RAW = "顾沉带林晚进入暗房。红色安全灯忽明忽暗，墙上的水渍像一张张倒置的地图。暗房中央摆着一只铁盒，盒盖上贴着母亲的手写标签：第七次潮汐。\n\n铁盒是空的，只有一小段烧焦的胶片和一枚海鸥别针。林晚认出别针与照片里小女孩佩戴的一模一样，却想不起自己童年是否来过这里。\n\n顾沉说胶片被人拿走了。林晚问是谁，他回答“也许是你自己”，语气像在试探。两人同时听见门外铜铃响了一声，顾沉熄灭安全灯，拉着林晚躲到药水柜后。\n\n门缝下出现一双湿透的皮鞋。那人没有进门，只把一张车票塞进来。车票背面写着：今晚十点，北堤仓库，带钥匙，不要带顾沉。"


def _grounded():
    result = ground_candidate_v2(RAW, fixture(RAW), source_fingerprint=hashlib.sha256(RAW.encode()).hexdigest())
    assert result["status"] == "PASS", result
    return result["grounded_candidate"]


class SourceGroundedPreparationPurityTests(unittest.TestCase):
    def test_strict_mode_does_not_create_beats(self):
        payload = canonical_script_payload_v2(_grounded())
        candidate = build_production_candidate(payload, book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
        self.assertEqual(candidate["scenes"][0]["beats"], [])

    def test_strict_mode_does_not_create_hook(self):
        candidate = build_production_candidate(canonical_script_payload_v2(_grounded()), book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
        self.assertFalse(any(str(beat.get("type")).upper() == "HOOK" for beat in candidate["scenes"][0]["beats"]))

    def test_strict_mode_does_not_set_critical(self):
        candidate = build_production_candidate(canonical_script_payload_v2(_grounded()), book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
        self.assertFalse(any(beat.get("importance") == "critical" for beat in candidate["scenes"][0]["beats"]))

    def test_strict_mode_does_not_set_requires_reaction(self):
        candidate = build_production_candidate(canonical_script_payload_v2(_grounded()), book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
        self.assertFalse(any(beat.get("requires_reaction") is True for beat in candidate["scenes"][0]["beats"]))

    def test_strict_mode_does_not_create_transition_event(self):
        candidate = build_production_candidate(canonical_script_payload_v2(_grounded()), book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
        self.assertEqual(candidate["scene_transitions"], [])

    def test_strict_mode_does_not_create_causal_reason(self):
        candidate = build_production_candidate(canonical_script_payload_v2(_grounded()), book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
        self.assertFalse(any(t.get("causal_reason") for t in candidate["scene_transitions"]))

    def test_strict_mode_does_not_default_objective_fact(self):
        candidate = build_production_candidate(canonical_script_payload_v2(_grounded()), book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
        self.assertEqual(candidate["scenes"][0]["dialogues"][0]["assertion_mode"], "")

    def test_legacy_mode_behavior_remains_unchanged(self):
        candidate = build_production_candidate({"scenes": [{"name": "门厅", "actions": [{"text": "进入门厅"}]}]}, book_id=1, episode=1)
        self.assertTrue(candidate["scenes"][0]["beats"])
        self.assertEqual(candidate["scenes"][0]["beats"][-1]["type"], "HOOK")

    def test_participant_evidence_must_contain_participant_name(self):
        candidate = fixture(RAW)
        candidate["scenes"][0]["participants"][0]["evidence"] = ["顾沉说胶片被人拿走了。"]
        result = ground_candidate_v2(RAW, candidate)
        self.assertTrue(any(e["code"] == "PARTICIPANT_EVIDENCE_IDENTITY_MISSING" for e in result["errors"]))

    def test_speaker_identity_evidence_must_contain_speaker(self):
        candidate = fixture(RAW)
        candidate["scenes"][0]["dialogues"][0]["speaker_identity_evidence"] = ["红色安全灯忽明忽暗，墙上的水渍像一张张倒置的地图。"]
        result = ground_candidate_v2(RAW, candidate)
        self.assertTrue(any(e["code"] == "SPEAKER_IDENTITY_EVIDENCE_MISSING" for e in result["errors"]))

    def test_utterance_evidence_must_contain_dialogue(self):
        candidate = fixture(RAW)
        candidate["scenes"][0]["dialogues"][0]["utterance_evidence"] = ["顾沉说胶片被人拿走了。"]
        result = ground_candidate_v2(RAW, candidate)
        self.assertTrue(any(e["code"] == "UTTERANCE_EVIDENCE_DIALOGUE_MISSING" for e in result["errors"]))

    def test_source_actions_and_dialogues_are_ordered_by_char_start(self):
        payload = canonical_script_payload_v2(_grounded())
        blocks = payload["scenes"][0]["script_blocks"]
        self.assertEqual([block["type"] for block in blocks], ["ACTION", "ACTION", "DIALOGUE", "ACTION"])

    def test_unresolved_timeline_order_fails_closed(self):
        grounded = _grounded()
        grounded["scenes"][0]["dialogues"][0]["utterance"]["char_start"] = grounded["scenes"][0]["actions"][0]["source_evidence"]["char_start"]
        with self.assertRaisesRegex(ValueError, "SOURCE_TIMELINE_ORDER_UNRESOLVED"):
            canonical_script_payload_v2(grounded)

    def test_raw_candidate_cannot_enter_strict_preparation(self):
        with self.assertRaisesRegex(ValueError, "SOURCE_GROUNDED_SOURCE_REQUIRED|SOURCE_TIMELINE_REQUIRED"):
            build_production_candidate(fixture(RAW), book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)

    def test_grounded_candidate_enters_strict_preparation(self):
        payload = canonical_script_payload_v2(_grounded())
        candidate = build_production_candidate(payload, book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
        self.assertEqual(candidate["preparation_policy"], SOURCE_GROUNDED_STRICT_POLICY)
        self.assertEqual(candidate["scenes"][0]["timeline_origin"], "SOURCE_GROUNDED")

    def test_strict_script_ir_validates_qualified_with_warnings(self):
        candidate = build_production_candidate(canonical_script_payload_v2(_grounded()), book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
        validation = validate_script_ir(candidate)
        self.assertEqual(validation["status"], "qualified")
        self.assertTrue(any(item["code"] == "SCENE_BEATS_EMPTY" for item in validation["warnings"]))

    def test_semantic_diff_finds_zero_invented_dialogue(self):
        payload = canonical_script_payload_v2(_grounded()); candidate = build_production_candidate(payload, book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
        self.assertEqual(semantic_diff_source_to_script_ir(payload, candidate)["invented_dialogue_count"], 0)

    def test_semantic_diff_finds_zero_invented_action(self):
        payload = canonical_script_payload_v2(_grounded()); candidate = build_production_candidate(payload, book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
        self.assertEqual(semantic_diff_source_to_script_ir(payload, candidate)["invented_action_count"], 0)

    def test_semantic_diff_finds_zero_invented_beat(self):
        payload = canonical_script_payload_v2(_grounded()); candidate = build_production_candidate(payload, book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
        self.assertEqual(semantic_diff_source_to_script_ir(payload, candidate)["invented_beat_count"], 0)

    def test_semantic_diff_finds_zero_invented_transition(self):
        payload = canonical_script_payload_v2(_grounded()); candidate = build_production_candidate(payload, book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
        self.assertEqual(semantic_diff_source_to_script_ir(payload, candidate)["invented_transition_count"], 0)

    def test_semantic_diff_finds_zero_invented_dramatic_classification(self):
        payload = canonical_script_payload_v2(_grounded()); candidate = build_production_candidate(payload, book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
        self.assertEqual(semantic_diff_source_to_script_ir(payload, candidate)["invented_dramatic_classification_count"], 0)

    def test_dry_run_fingerprint_is_distinguished_from_actual(self):
        audit = json.loads(Path("docs/canonical-canary/v5_1-structuring-contract-reconcile/LLM_REQUEST_V2_DRY_RUN.json").read_text(encoding="utf-8"))
        self.assertFalse(audit["request_sent"])
        self.assertNotEqual(audit["request_fingerprint"], "NOT_COMPUTED_NOT_SENT")

    def test_next_runner_retains_raw_response_before_parse(self):
        evidence = retain_forensic_response(run_id="r", response="{bad", provider="p", model="m")
        self.assertTrue(evidence["validation_not_yet_run"])
        self.assertEqual(evidence["response_length"], 4)

    def test_provider_calls_are_zero(self):
        readiness = json.loads(Path("docs/canonical-canary/v5_1-structuring-contract-reconcile/REAUTHORIZATION_READINESS.json").read_text(encoding="utf-8"))
        self.assertEqual(readiness["provider_calls"], 0)
        self.assertEqual(readiness["db_writes"], 0)


if __name__ == "__main__":
    unittest.main()
