import hashlib
import json
import unittest
from pathlib import Path

from core.source_structuring_v2 import (
    GROUNDED_VERSION,
    SCHEMA_VERSION,
    canonical_script_payload_v2,
    ground_candidate_v2,
    json_parse_attempt_budget,
    retain_forensic_response,
    resolve_exact_source_evidence,
    transport_attempt_budget,
)


RAW = "顾沉带林晚进入暗房。顾沉说胶片被人拿走了。林晚问是谁，他回答“也许是你自己”，语气像在试探。"


def _candidate(**dialogue_overrides):
    dialogue = {
        "speaker": "顾沉",
        "text": "也许是你自己",
        "utterance_evidence": ["林晚问是谁，他回答“也许是你自己”，语气像在试探。"],
        "speaker_identity_evidence": ["顾沉说胶片被人拿走了。"],
        "binding_type": "COREFERENCE_RESOLUTION",
    }
    dialogue.update(dialogue_overrides)
    return {
        "schema_version": SCHEMA_VERSION,
        "scenes": [{
            "scene_label": "暗房",
            "scene_evidence": ["顾沉带林晚进入暗房。"],
            "participants": [{"name": "林晚", "evidence": ["顾沉带林晚进入暗房。"]}, {"name": "顾沉", "evidence": ["顾沉带林晚进入暗房。"]}],
            "actions": [{"source_text": "顾沉带林晚进入暗房。"}, {"source_text": "顾沉说胶片被人拿走了。"}],
            "dialogues": [dialogue],
        }],
        "unknowns": [],
    }


class SourceStructuringV2ContractTests(unittest.TestCase):
    def test_local_locator_computes_character_offsets(self):
        result = resolve_exact_source_evidence(RAW, "进入暗房")
        self.assertEqual(RAW[result["char_start"]:result["char_end"]], "进入暗房")

    def test_local_locator_computes_utf8_byte_offsets(self):
        result = resolve_exact_source_evidence(RAW, "进入暗房")
        self.assertEqual(len(RAW[:result["char_start"]].encode("utf-8")), result["byte_start"])
        self.assertEqual(len(RAW[:result["char_end"]].encode("utf-8")), result["byte_end"])

    def test_local_locator_computes_sha(self):
        result = resolve_exact_source_evidence(RAW, "进入暗房")
        self.assertEqual(result["sha256"], hashlib.sha256("进入暗房".encode()).hexdigest())

    def test_fake_hash_is_rejected(self):
        candidate = _candidate()
        candidate["scenes"][0]["actions"][0]["sha256"] = "fake"
        result = ground_candidate_v2(RAW, candidate)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(e["code"] == "LLM_MUST_NOT_PROVIDE_LOCAL_OFFSETS_OR_HASHES" for e in result["errors"]))

    def test_fake_offset_is_rejected(self):
        candidate = _candidate()
        candidate["scenes"][0]["actions"][0]["start"] = 0
        result = ground_candidate_v2(RAW, candidate)
        self.assertEqual(result["status"], "FAIL")

    def test_zero_occurrence_fails(self):
        with self.assertRaisesRegex(ValueError, "exact source evidence was not found"):
            resolve_exact_source_evidence(RAW, "不存在的证据")

    def test_multiple_occurrence_fails(self):
        with self.assertRaisesRegex(ValueError, "occurs more than once"):
            resolve_exact_source_evidence("重复 重复", "重复")

    def test_exact_direct_quote_passes(self):
        result = ground_candidate_v2(RAW, _candidate())
        self.assertEqual(result["status"], "PASS", result)
        dialogue = result["grounded_candidate"]["scenes"][0]["dialogues"][0]
        self.assertEqual(dialogue["binding_classification"], "AUTHORIZED_SEMANTIC_BINDING")

    def test_reported_speech_cannot_become_dialogue(self):
        result = ground_candidate_v2(RAW, _candidate(text="胶片被人拿走了", utterance_evidence=["顾沉说胶片被人拿走了。"]))
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(e["code"] == "REPORTED_SPEECH_PROMOTED" for e in result["errors"]))

    def test_multi_span_speaker_evidence_is_accepted(self):
        candidate = _candidate(speaker_identity_evidence=["顾沉说胶片被人拿走了。"], utterance_evidence=["林晚问是谁，他回答“也许是你自己”，语气像在试探。"])
        result = ground_candidate_v2(RAW, candidate)
        self.assertEqual(result["status"], "PASS")

    def test_coreference_is_authorized_semantic_binding(self):
        result = ground_candidate_v2(RAW, _candidate())
        binding = result["grounded_candidate"]["scenes"][0]["dialogues"][0]["binding_classification"]
        self.assertEqual(binding, "AUTHORIZED_SEMANTIC_BINDING")

    def test_literal_binding_only_when_utterance_contains_speaker(self):
        candidate = _candidate(utterance_evidence=["顾沉回答“也许是你自己”。"])
        candidate["scenes"][0]["actions"].append({"source_text": "顾沉说胶片被人拿走了。"})
        result = ground_candidate_v2("顾沉带林晚进入暗房。顾沉说胶片被人拿走了。顾沉回答“也许是你自己”。", candidate)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["grounded_candidate"]["scenes"][0]["dialogues"][0]["binding_classification"], "SOURCE_LITERAL_BINDING")

    def test_historical_derived_evidence_is_forbidden(self):
        candidate = _candidate()
        candidate["historical_source"] = "script_ir:2"
        result = ground_candidate_v2(RAW, candidate)
        self.assertTrue(any(e["code"] == "HISTORICAL_DERIVED_EVIDENCE_FORBIDDEN" for e in result["errors"]))

    def test_other_chapter_evidence_fails(self):
        candidate = _candidate()
        candidate["scenes"][0]["scene_evidence"] = ["另一章的句子"]
        result = ground_candidate_v2(RAW, candidate)
        self.assertTrue(any(e["code"] == "SOURCE_EVIDENCE_NOT_FOUND" for e in result["errors"]))

    def test_source_hash_change_is_rejected_by_caller_fingerprint(self):
        result = ground_candidate_v2(RAW, _candidate(), expected_source_fingerprint="changed")
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(e["code"] == "AUTHORIZED_SOURCE_CHANGED" for e in result["errors"]))

    def test_empty_speaker_evidence_fails(self):
        result = ground_candidate_v2(RAW, _candidate(speaker_identity_evidence=[]))
        self.assertTrue(any(e["code"] == "SOURCE_EVIDENCE_REQUIRED" for e in result["errors"]))

    def test_coreference_without_evidence_chain_fails(self):
        result = ground_candidate_v2(RAW, _candidate(speaker_identity_evidence=[], utterance_evidence=[]))
        self.assertTrue(any(e["code"] == "SOURCE_EVIDENCE_REQUIRED" for e in result["errors"]))

    def test_raw_candidate_cannot_enter_script_payload(self):
        with self.assertRaisesRegex(ValueError, "GROUNDED_CANDIDATE_REQUIRED"):
            canonical_script_payload_v2(_candidate())

    def test_grounded_candidate_can_enter_payload(self):
        result = ground_candidate_v2(RAW, _candidate())
        payload = canonical_script_payload_v2(result["grounded_candidate"])
        self.assertEqual(payload["schema_version"], "source_grounded_script_payload_v2")
        self.assertEqual(payload["scenes"][0]["dialogues"][0]["text"], "也许是你自己")

    def test_forensic_response_is_retained_before_validation(self):
        evidence = retain_forensic_response(run_id="r1", response={"x": 1}, provider="test", model="m")
        self.assertTrue(evidence["received"])
        self.assertTrue(evidence["validation_not_yet_run"])
        self.assertEqual(evidence["secret_fields_persisted"], False)
        self.assertIsNotNone(evidence["response_sha256"])

    def test_forensic_evidence_contains_no_credentials(self):
        evidence = retain_forensic_response(run_id="r1", response={"api_key": "secret", "x": 1}, provider="test", model="m")
        self.assertNotIn("Authorization", json.dumps(evidence))
        self.assertNotIn('"api_key": "secret"', json.dumps(evidence))
        self.assertEqual(evidence["parsed_json"]["api_key"], "[REDACTED]")

    def test_retries_one_means_one_transport_attempt(self):
        self.assertEqual(transport_attempt_budget(1), 1)

    def test_json_parse_retries_zero_means_one_provider_call(self):
        self.assertEqual(json_parse_attempt_budget(0), 1)

    def test_this_phase_has_zero_provider_calls(self):
        audit = json.loads(Path("docs/canonical-canary/v5_1-structuring-contract-reconcile/GROUNDED_STRUCTURING_VALIDATION.json").read_text(encoding="utf-8"))
        self.assertEqual(audit["provider_calls"], 0)
        self.assertEqual(audit["db_writes"], 0)


if __name__ == "__main__":
    unittest.main()
