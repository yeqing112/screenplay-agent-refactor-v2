from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.video_compiler_runtime import compile_video_intent
from core.video_compilers import VideoModelCapabilities, default_video_compiler_registry
from core.video_compilers.minimax_h3 import H3_CAPABILITIES, MiniMaxH3Compiler
from core.video_intent_ir import build_video_intent_ir


ROOT = Path(__file__).resolve().parents[1]
DECISIONS = json.loads((ROOT / "docs/prompt-quality/v4/DIRECTOR_DECISION_IR.json").read_text(encoding="utf-8"))["canary_shots"]


def decision(shot_id: str) -> dict:
    return next(x for x in DECISIONS if x["shot_id"] == shot_id)


def profile() -> dict:
    return {"video_compiler_id": "minimax-h3", "model_family": "minimax-h3", "model_name": "minimax_h3", "default_params": {}}


def test_intent_is_model_independent_and_none_dialogue_is_closed():
    intent = build_video_intent_ir(decision("SH_E01_SC002_007"))
    serialized = json.dumps(intent.as_dict(), ensure_ascii=False).lower()
    for token in ("75api", "minimax", "http://", "https://", "<d>", "integrated_multimodal_description"):
        assert token not in serialized
    assert intent.dialogue.mode == "NONE"
    assert intent.dialogue.visual_lipsync_policy == "NO_SPEAKING_MOTION"
    assert "lips slightly parted" not in serialized


def test_none_golden_has_no_dialogue_block_and_no_positive_mouth_state():
    compiled = MiniMaxH3Compiler().compile(build_video_intent_ir(decision("SH_E01_SC002_007")), H3_CAPABILITIES)
    assert "<d>" not in compiled.prompt
    assert "lips slightly parted" not in compiled.prompt.lower()
    assert "overall_soundscape:\nN/A" in compiled.prompt
    assert "non_diegetic_music:\nN/A" in compiled.prompt


def test_dialogue_golden_preserves_exact_text_and_stable_speaker_ids():
    d = decision("SH_E01_SC002_002")
    intent = build_video_intent_ir(d)
    first = MiniMaxH3Compiler().compile(intent, H3_CAPABILITIES)
    second = MiniMaxH3Compiler().compile(intent, H3_CAPABILITIES)
    exact = d["dialogue_beats"][0]["authoritative_text"]
    assert exact in first.prompt
    assert "<d>[Chinese]" in first.prompt
    assert "(S1)" in first.prompt or "(S2)" in first.prompt
    assert first.prompt == second.prompt
    assert first.compiled_request_fingerprint == second.compiled_request_fingerprint


def test_unauthorized_props_are_not_carried_into_sc002_002_but_apple_is_explicit():
    no_props = build_video_intent_ir(decision("SH_E01_SC002_002"), prop_states=[])
    assert "bag" not in json.dumps(no_props.as_dict(), ensure_ascii=False).lower()
    apple = build_video_intent_ir(decision("SH_E01_SC002_006"), prop_states=[{"prop_id": "APPLE", "present": True, "holder": "LIN_WAN"}])
    assert "APPLE" in json.dumps(apple.as_dict(), ensure_ascii=False)


def test_registry_and_profile_binding_fail_closed_when_missing():
    registry = default_video_compiler_registry()
    assert registry.resolve(compiler_id="minimax-h3").compiler_id == "minimax-h3"
    with pytest.raises(LookupError, match="VIDEO_COMPILER_NOT_CONFIGURED"):
        compile_video_intent(build_video_intent_ir(decision("SH_E01_SC002_007")), {"model_name": "minimax_h3"})


def test_capability_gates_are_explicit():
    intent = build_video_intent_ir(decision("SH_E01_SC002_007"))
    unsupported = VideoModelCapabilities(**(H3_CAPABILITIES.as_dict() | {"supports_first_frame": False, "allowed_aspect_ratios": tuple(H3_CAPABILITIES.allowed_aspect_ratios)}))
    with pytest.raises(ValueError, match="FIRST_FRAME_UNSUPPORTED"):
        MiniMaxH3Compiler().compile(intent, unsupported)


def test_compiled_request_contains_no_credentials_or_transport_fields():
    compiled = MiniMaxH3Compiler().compile(build_video_intent_ir(decision("SH_E01_SC002_007")), H3_CAPABILITIES)
    payload = compiled.as_dict()
    text = json.dumps(payload, ensure_ascii=False).lower()
    for token in ("api_key", "authorization", "credential", "base_url", "http://", "https://"):
        assert token not in text


def test_fractional_duration_uses_canonical_terminal_hold_projection():
    d = dict(decision("SH_E01_SC002_007"))
    d["duration_seconds"] = 5.25
    compiled = MiniMaxH3Compiler().compile(build_video_intent_ir(d), H3_CAPABILITIES)
    assert compiled.duration_seconds == 6
