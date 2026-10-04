from __future__ import annotations

import json
from pathlib import Path

from core.shot_readiness import project_provider_duration
from core.video_provider_prompt_ir import build_prompt_truth_chain, build_video_provider_prompt_ir, extract_provider_truth


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
    assert "完全无对白" in ir.rendered_prompt
    assert "按照对白执行" not in ir.rendered_prompt
    assert "对白时间" not in ir.rendered_prompt
    assert "不得出现明显的对白式张嘴、闭嘴循环" in ir.rendered_prompt


def test_motion_and_camera_beats_are_projected_from_director_ir():
    ir = build_video_provider_prompt_ir(_decision("SH_E01_SC002_007"), project_provider_duration(5.0))
    assert len(ir.performance_beats) == 4
    assert len(ir.camera_beats) == 2
    assert "[0.0–1.2]" in ir.rendered_prompt
    assert "[2.5–5.0]" in ir.rendered_prompt
    assert "slow lateral drift" in ir.rendered_prompt


def test_dialogue_contract_preserves_exact_text_speaker_and_phrase_windows():
    ir = build_video_provider_prompt_ir(_decision("SH_E01_SC002_002"), project_provider_duration(13.5))
    source = _decision("SH_E01_SC002_002")
    contract = ir.dialogue_contract
    assert contract.dialogue_mode == "AUTHORITATIVE"
    assert contract.speaker == source["dialogue_beats"][0]["speaker"]
    assert contract.authoritative_text == source["dialogue_beats"][0]["authoritative_text"]
    assert len(contract.phrase_windows) == len(source["dialogue_beats"][0]["phrase_windows"])
    assert contract.silent_characters == ("林晚",)
    assert contract.authoritative_text in ir.rendered_prompt


def test_prompt_truth_chain_requires_all_three_fingerprints():
    chain = build_prompt_truth_chain("canonical", "canonical", "canonical")
    assert chain["status"] == "PASS"
    broken = build_prompt_truth_chain("canonical", "other", "other")
    assert broken["status"] == "VIDEO_PROMPT_TRUTH_CHAIN_BROKEN"


def test_provider_truth_parser_and_model_mapping_fields():
    parsed = extract_provider_truth({"properties": {"input": "prompt", "origin_model_name": "minimax_h3_no_audios", "upstream_model_name": "75api-minimax-h3-ref-20260916"}, "model": "75api-minimax-h3-fast-20260911"})
    assert parsed == {"properties_input": "prompt", "origin_model_name": "minimax_h3_no_audios", "upstream_model_name": "75api-minimax-h3-ref-20260916", "reported_completion_model": "75api-minimax-h3-fast-20260911"}
