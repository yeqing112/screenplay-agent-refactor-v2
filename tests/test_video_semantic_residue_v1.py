from __future__ import annotations

import json
from pathlib import Path

from core.prompt_semantic_partition import partition_prompt
from core.unauthorized_prop_semantic_scrubber import scrub_semantic_beat
from core.video_compilers.minimax_h3 import H3_CAPABILITIES, MiniMaxH3Compiler, _camera_event
from core.video_intent_ir import build_video_intent_ir


ROOT = Path(__file__).resolve().parents[1]
DECISIONS = json.loads((ROOT / "docs/prompt-quality/v4/DIRECTOR_DECISION_IR.json").read_text(encoding="utf-8"))["canary_shots"]


def _decision(shot_id: str) -> dict:
    return next(x for x in DECISIONS if x["shot_id"] == shot_id)


def test_partial_sc002_002_projection_removes_object_relationship_without_mutating_source():
    source = _decision("SH_E01_SC002_002")
    before = json.dumps(source, ensure_ascii=False, sort_keys=True)
    intent = build_video_intent_ir(source)
    after = json.dumps(source, ensure_ascii=False, sort_keys=True)
    assert before == after
    projected = json.dumps(intent.performance_beats, ensure_ascii=False).lower()
    assert "bag strap" not in projected
    assert "gripping the strap" not in projected
    assert intent.semantic_audit["status"] == "PASS"
    lin = [x for x in intent.performance_beats if x.get("actor") == "林晚"]
    assert lin[0]["hand_action"] == "left hand starts held close to her side, then the fingers gradually relax, ending with the hand naturally loose beside her body"
    assert lin[3]["hand_action"] == "left hand makes a small unconscious adjustment near her side, then settles naturally beside her body"


def test_orphan_prop_interaction_is_fail_closed():
    projected, audit = scrub_semantic_beat({"actor": "林晚", "start_time": 0, "end_time": 1, "eye_action": "fingers remain on the bag"}, allowed_prop_ids=[])
    assert projected == {"actor": "林晚", "start_time": 0, "end_time": 1, "eye_action": "fingers remain on the bag"}
    assert audit.status == "FAIL"
    assert audit.orphan_interactions == ("beat.eye_action",)


def test_prompt_partition_has_negative_only_apple_and_one_negative_strap():
    compiled = MiniMaxH3Compiler().compile(build_video_intent_ir(_decision("SH_E01_SC002_002")), H3_CAPABILITIES)
    audit = partition_prompt(compiled.prompt)
    assert audit["positive_visual_forbidden_tokens"]["apple"] == 0
    assert audit["counts"]["strap"]["POSITIVE_VISUAL"] == 0
    assert audit["counts"]["strap"]["NEGATIVE_VISUAL"] == 1
    assert compiled.prompt.lower().count("strap") == 1
    assert compiled.prompt.count("No apple is visible in this shot.") == 1
    assert compiled.prompt.count("The apple is mentioned only in dialogue as a future action; it must not appear physically during this shot.") == 1


def test_static_camera_uses_natural_operator_grammar():
    event = _camera_event({"start_time": 0, "end_time": 3.6, "movement_type": "static", "target": "two-shot of 陆叔 and 林晚 at the kitchen table", "direction": "none"}, 0)
    assert event["primary_action"] == "The camera holds a restrained static medium two-shot of Uncle Lu and Lin Wan at the kitchen table, with barely perceptible handheld breathing drift."
