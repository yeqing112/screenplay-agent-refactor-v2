import hashlib
import unittest

from scripts.run_authorized_source_structuring_v1 import (
    ALLOWLIST,
    BOOK_ID,
    CHAPTER_ID,
    TARGET_QUOTE,
    canonical_script_payload,
    validate_llm_candidate,
)


RAW = "顾沉带林晚进入暗房。林晚问是谁，他回答“也许是你自己”，语气像在试探。"


def _span(text, start=None):
    start = RAW.find(text) if start is None else start
    return {"start": start, "end": start + len(text), "text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}


def _candidate(*, dialogue_text=TARGET_QUOTE, speaker="顾沉", participant="林晚"):
    dialogue_start = RAW.find(dialogue_text)
    return {
        "source": {"book_id": BOOK_ID, "chapter_id": CHAPTER_ID, "raw_sha256": hashlib.sha256(RAW.encode()).hexdigest()},
        "scenes": [{
            "name": "暗房",
            "source_span": _span(RAW),
            "participants": [
                {"name": participant, "source_evidence": _span(participant)},
                {"name": "顾沉", "source_evidence": _span("顾沉")},
            ],
            "actions": [{"source_span": _span("顾沉带林晚进入暗房。"), "normalized_projection": "顾沉带林晚进入暗房。"}],
            "dialogues": [{
                "speaker": speaker,
                "text": dialogue_text,
                "source_span": _span(dialogue_text, dialogue_start),
                "speaker_binding_evidence": _span("顾沉"),
            }],
        }],
        "unknowns": [],
    }


class AuthorizedSourceStructuringTests(unittest.TestCase):
    def test_exact_quote_and_allowlisted_speaker_pass(self):
        result = validate_llm_candidate(_candidate(), RAW)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["reported_speech_promotion_count"], 0)

    def test_paraphrase_fails_exact_match(self):
        candidate = _candidate()
        candidate["scenes"][0]["dialogues"][0]["text"] = "可能是你自己"
        result = validate_llm_candidate(candidate, RAW)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(item["code"] == "DIALOGUE_TEXT_NOT_EXACT" for item in result["errors"]))

    def test_unknown_speaker_fails_allowlist(self):
        result = validate_llm_candidate(_candidate(speaker="陌生人"), RAW)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(item["code"] == "SPEAKER_NOT_ALLOWLISTED" for item in result["errors"]))

    def test_participant_outside_allowlist_fails(self):
        result = validate_llm_candidate(_candidate(participant="陌生人"), RAW)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(item["code"] == "PARTICIPANT_NOT_ALLOWLISTED" for item in result["errors"]))

    def test_offset_and_hash_mismatch_fail(self):
        candidate = _candidate()
        candidate["scenes"][0]["dialogues"][0]["source_span"]["start"] += 1
        result = validate_llm_candidate(candidate, RAW)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(item["code"] in {"span_shape_invalid", "span_offset_or_text_mismatch"} for item in result["errors"]))

    def test_target_quote_must_be_promoted_once(self):
        candidate = _candidate(dialogue_text="顾沉说胶片被人拿走了")
        result = validate_llm_candidate(candidate, RAW)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(item["code"] == "TARGET_QUOTE_NOT_PROMOTED_EXACTLY_ONCE" for item in result["errors"]))

    def test_action_projection_cannot_add_creative_text(self):
        candidate = _candidate()
        candidate["scenes"][0]["actions"][0]["normalized_projection"] = "顾沉带林晚进入暗房并发现秘密"
        result = validate_llm_candidate(candidate, RAW)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(item["code"] == "ACTION_PROJECTION_NOT_EXACT" for item in result["errors"]))

    def test_canonical_payload_keeps_only_validated_source_fields(self):
        payload = canonical_script_payload(_candidate())
        scene = payload["scenes"][0]
        self.assertEqual(scene["timeline_origin"], "EXPLICIT")
        self.assertEqual(scene["dialogues"][0]["text"], TARGET_QUOTE)
        self.assertEqual(scene["dialogues"][0]["speaker"], "顾沉")


if __name__ == "__main__":
    unittest.main()
