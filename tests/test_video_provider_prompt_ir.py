from __future__ import annotations

import json
from pathlib import Path
import pytest

from core.shot_readiness import project_provider_duration
from core.video_provider_prompt_ir import build_prompt_truth_chain, build_video_provider_prompt_ir, extract_provider_truth, find_no_dialogue_mouth_conflicts, project_no_dialogue_mouth_state
from core.video_dialogue_visual_audit import aggregate_no_dialogue_verdict, derive_character_temporal_regions, hard_audio_gate, build_window_verdicts, sample_video_dense
from core.video_dialogue_verdict import HumanMediaReview, VideoDialogueVerdict


ROOT = Path(__file__).resolve().parents[1]


def _decision(shot_id: str) -> dict:
    raw = json.loads((ROOT / "docs/prompt-quality/v4/DIRECTOR_DECISION_IR.json").read_text(encoding="utf-8"))
    return next(item for item in raw["canary_shots"] if item["shot_id"] == shot_id)


def test_none_dialogue_contract_has_explicit_silence_and_no_leak():
    ir = build_video_provider_prompt_ir(_decision("SH_E01_SC002_007"), project_provider_duration(5.0))
    contract = ir.dialogue_contract
    assert contract.dialogue_mode == "NONE"
    assert contract.speaker is None
    assert contract.authoritative_text == ""
    assert list(contract.phrase_windows) == []
    assert set(contract.silent_characters) == {"林晚", "陆叔"}
    assert contract.visual_lipsync_required is False
    assert contract.audio_generation_allowed is False
    assert contract.mouth_motion_outside_dialogue_allowed is False
    assert "All characters remain silent" in ir.rendered_prompt
    assert "按照对白执行" not in ir.rendered_prompt
    assert "对白时间" not in ir.rendered_prompt
    assert "speaking-like motion" in ir.rendered_prompt
    assert contract.mouth_state_contract == "CLOSED_RELAXED_STABLE"
    assert find_no_dialogue_mouth_conflicts(ir.rendered_prompt) == ()


def test_motion_and_camera_beats_are_projected_from_director_ir():
    ir = build_video_provider_prompt_ir(_decision("SH_E01_SC002_007"), project_provider_duration(5.0))
    assert len(ir.performance_beats) == 4
    assert len(ir.camera_beats) == 2
    assert "H3 temporal event stream:" in ir.rendered_prompt
    assert "restrained intensity" in ir.rendered_prompt


def test_dialogue_contract_preserves_exact_text_speaker_and_phrase_windows():
    ir = build_video_provider_prompt_ir(_decision("SH_E01_SC002_002"), project_provider_duration(13.5))
    source = _decision("SH_E01_SC002_002")
    contract = ir.dialogue_contract
    assert contract.dialogue_mode == "AUTHORITATIVE"
    assert contract.speaker == source["dialogue_beats"][0]["speaker"]
    assert contract.authoritative_text == source["dialogue_beats"][0]["authoritative_text"]
    assert len(contract.phrase_windows) == len(source["dialogue_beats"][0]["phrase_windows"])
    assert contract.silent_characters == ("林晚",)
    assert contract.authoritative_text not in ir.rendered_prompt
    assert ir.rendered_prompt.count("<d>") == 4


def test_prompt_truth_chain_requires_all_three_fingerprints():
    chain = build_prompt_truth_chain("canonical", "canonical", "canonical")
    assert chain["status"] == "PASS"
    broken = build_prompt_truth_chain("canonical", "other", "other")
    assert broken["status"] == "VIDEO_PROMPT_TRUTH_CHAIN_BROKEN"


def test_provider_truth_parser_and_model_mapping_fields():
    parsed = extract_provider_truth({"properties": {"input": "prompt", "origin_model_name": "minimax_h3_no_audios", "upstream_model_name": "75api-minimax-h3-ref-20260916"}, "model": "75api-minimax-h3-fast-20260911"})
    assert parsed == {"properties_input": "prompt", "origin_model_name": "minimax_h3_no_audios", "upstream_model_name": "75api-minimax-h3-ref-20260916", "reported_completion_model": "75api-minimax-h3-fast-20260911"}


def test_none_dialogue_projection_sanitizes_mouth_open_beat_without_mutating_source():
    decision = _decision("SH_E01_SC002_007")
    original = decision["performance_beats"][2]["facial_action"]
    projection = project_no_dialogue_mouth_state(decision)
    assert projection.mouth_state_contract == "CLOSED_RELAXED_STABLE"
    assert projection.source_conflict_count == 1
    assert "lips slightly parted" in original
    assert all("lips slightly parted" not in str(beat) for beat in projection.sanitized_performance_beats)
    assert decision["performance_beats"][2]["facial_action"] == original


def test_temporal_regions_are_derived_from_blocking_and_hard_audio_gate_is_deterministic():
    regions = derive_character_temporal_regions(_decision("SH_E01_SC002_007"))
    assert len(regions) == 2
    assert all(region.source.startswith("DirectorDecisionIR") for region in regions)
    assert hard_audio_gate(1, audio_generation_allowed=False)["code"] == "UNEXPECTED_AUDIO_STREAM"
    assert hard_audio_gate(0, audio_generation_allowed=False)["status"] == "PASS"


def test_human_review_overrides_automated_pass_and_short_window_fails_none_dialogue():
    strips = {"characters": {"Lin Wan": {"windows": [{"window_index": 1, "start_time": 1.0, "end_time": 1.5, "path": "strip.jpg"}]}}}
    verdicts = build_window_verdicts(strips, automated_labels={("Lin Wan", 1): {"label": "mouth_closed_stable", "confidence": 0.95}}, human_labels={("Lin Wan", 1): {"label": "speech_like_open_close_cycle", "first_evidence_time": 1.05, "last_evidence_time": 1.48}})
    result = aggregate_no_dialogue_verdict(verdicts)
    assert result["status"] == "FAIL"
    assert result["automated_visual_judge_false_negative"] is True


def test_two_fps_contact_sheet_is_not_an_authoritative_label():
    with pytest.raises(ValueError, match="sampling_fps"):
        sample_video_dense(Path("missing-golden.mp4"), Path("unused"), sampling_fps=2)


def test_media_verdict_separates_contract_failure_from_prompt_root_cause():
    review = HumanMediaReview("SH_E01_SC002_007", "sha", True, True, 3, "UNINTELLIGIBLE")
    verdict = VideoDialogueVerdict("FAILED", "PROVIDER_RECORDED_PROMPT_UNAVAILABLE", "PARTIAL", "FAIL", "FAIL", "FAIL", "FALSE_NEGATIVE", "FAIL", ("UNEXPECTED_AUDIO_STREAM",))
    assert review.as_dict()["approximate_utterance_count"] == 3
    assert verdict.as_dict()["media_contract_status"] == "FAILED"
    assert verdict.as_dict()["root_cause_attribution_status"] == "PARTIAL"
