import pytest

from core.script_creative_quality import run_script_creative_quality_gate
from core.script_ir import build_script_ir
from core.script_renderer import render_reader_script


def _payload(scene):
    return {"title": "timeline", "scenes": [scene]}


def test_missing_timeline_is_inferred_for_draft_but_blocked_for_production():
    ir = build_script_ir(_payload({
        "scene_id": "S1", "name": "室内", "beats": [{"beat_id": "B1", "type": "ACTION", "event": "她停下。"}],
        "dialogues": [],
    }), book_id=1, episode=1)
    assert ir["scenes"][0]["timeline_origin"] == "LEGACY_INFERRED"
    assert ir["scenes"][0]["production_eligible"] is False
    assert "SCRIPT_TIMELINE_NOT_EXPLICIT" in {
        item["code"] for item in run_script_creative_quality_gate(ir, production=True)["hard_errors"]
    }
    assert "她停下。" in render_reader_script(ir)
    with pytest.raises(ValueError, match="SCRIPT_TIMELINE_NOT_EXPLICIT"):
        render_reader_script(ir, production=True)


def test_explicit_invalid_order_is_preserved_and_rejected():
    ir = build_script_ir(_payload({
        "scene_id": "S1", "name": "室内", "timeline_origin": "EXPLICIT",
        "actions": [{"action_id": "A1", "text": "她停下。"}],
        "script_blocks": [{"order": "abc", "type": "ACTION", "ref": "A1"}],
    }), book_id=1, episode=1)
    assert ir["scenes"][0]["script_blocks"][0]["order"] == "abc"
    codes = {item["code"] for item in run_script_creative_quality_gate(ir, production=True)["hard_errors"]}
    assert "SCRIPT_BLOCK_ORDER_REQUIRED" in codes


def test_missing_ref_is_not_guessed_from_alias_or_position():
    ir = build_script_ir(_payload({
        "scene_id": "S1", "name": "室内", "timeline_origin": "EXPLICIT",
        "actions": [{"action_id": "A1", "text": "她停下。"}],
        "script_blocks": [{"order": 10, "type": "ACTION", "action_ref": "A1"}],
    }), book_id=1, episode=1)
    assert ir["scenes"][0]["script_blocks"][0]["ref"] == ""
    codes = {item["code"] for item in run_script_creative_quality_gate(ir, production=True)["hard_errors"]}
    assert "SCRIPT_BLOCK_REF_MISSING" in codes


def test_story_specific_open_question_is_input_only():
    ir = build_script_ir(_payload({
        "scene_id": "S1", "name": "室内", "beats": [], "dialogues": [],
    }), book_id=1, episode=1)
    assert ir["open_questions"] == []
    supplied = build_script_ir({**_payload({"scene_id": "S1", "name": "室内"}), "open_questions": [{"code": "OPEN_QUESTION_REQUIRES_FUTURE_RESOLUTION"}]}, book_id=1, episode=1)
    assert supplied["open_questions"][0]["code"] == "OPEN_QUESTION_REQUIRES_FUTURE_RESOLUTION"
