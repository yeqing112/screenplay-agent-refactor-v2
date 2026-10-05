from __future__ import annotations

import json
import re
from pathlib import Path

from core.video_compilers.minimax_h3 import H3_CAPABILITIES, MiniMaxH3Compiler, _camera_event, _performance_event
from core.video_intent_ir import build_video_intent_ir
from core.video_temporal_continuity import build_temporal_emission_audit, detect_performance_state_resets

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = json.loads((ROOT / "docs/prompt-quality/v4/DIRECTOR_DECISION_IR.json").read_text(encoding="utf-8"))["canary_shots"]


def _decision(shot_id: str) -> dict:
    return next(x for x in DECISIONS if x["shot_id"] == shot_id)


def test_union_boundaries_do_not_duplicate_source_events():
    intent = build_video_intent_ir(_decision("SH_E01_SC002_002"))
    compiled = MiniMaxH3Compiler().compile(intent, H3_CAPABILITIES)
    prompt = compiled.prompt
    for beat in intent.performance_beats:
        event = _performance_event(intent, dict(beat), list(intent.performance_beats).index(beat))
        assert prompt.count(event["source_beat_id"]) == 1
    for index, beat in enumerate(intent.camera_beats):
        event = _camera_event(dict(beat), index)
        assert prompt.count(event["source_beat_id"]) == 1
    assert prompt.count("slow push-in") == 1
    assert prompt.count("slow lateral drift") == 1
    assert prompt.count("slow pull-back") == 1


def test_dialogue_windows_keep_exact_source_timing_and_single_emission():
    intent = build_video_intent_ir(_decision("SH_E01_SC002_002"))
    compiled = MiniMaxH3Compiler().compile(intent, H3_CAPABILITIES)
    for phrase in intent.dialogue.phrase_windows:
        window = f"{float(phrase['start_time']):.1f}–{float(phrase['end_time']):.1f}s"
        assert compiled.prompt.count(window) >= 1
    assert compiled.prompt.count("<d>") == 4
    assert compiled.provider_capability_requirements["dialogue_occurrence_audit"]["plain_full_authoritative_occurrence"] == 0
    assert compiled.provider_capability_requirements["temporal_emission_audit"]["dialogue_timing_drift"] == []


def test_reaction_delay_is_sparse_and_terminal_hold_is_single():
    intent = build_video_intent_ir(_decision("SH_E01_SC002_002"))
    compiled = MiniMaxH3Compiler().compile(intent, H3_CAPABILITIES)
    assert compiled.prompt.count("0.2–0.6 second hesitation") == 1
    assert compiled.prompt.count("[TERMINAL_HOLD]") == 1
    assert compiled.prompt.split("[TERMINAL_HOLD]", 1)[1].count("<d>") == 0
    assert compiled.provider_capability_requirements["temporal_emission_audit"]["terminal_hold_count"] == 1


def test_temporal_audit_detects_duplicate_event_ids_and_timing_drift():
    audit = build_temporal_emission_audit(
        [{"start_time": 0, "end_time": 1}],
        [{"start_time": 0, "end_time": 1, "source_beat_id": "PERF_A"}, {"start_time": 0, "end_time": 1, "source_beat_id": "PERF_A"}],
        [{"start_time": 0, "end_time": 1}],
        [{"start_time": 0, "end_time": 1, "source_beat_id": "CAMERA_0000_0100"}],
        [{"start_time": 0, "end_time": 1, "text": "A"}],
        [{"start_time": 0, "end_time": 0.5}],
        reaction_delay_count=0,
        terminal_hold_count=1,
    )
    assert audit.status == "FAIL"
    assert audit.duplicate_performance_emissions == ("PERF_A",)
    assert audit.dialogue_timing_drift


def test_performance_continuity_detects_explicit_state_reset():
    resets = detect_performance_state_resets([
        {"actor": "A", "start_time": 0, "end_time": 1, "ending_state": "hand at waist"},
        {"actor": "A", "start_time": 1, "end_time": 2, "start_state": "hand at side"},
    ])
    assert resets[0]["code"] == "TEMPORAL_STATE_RESET_WITHOUT_TRANSITION"
