import json
import importlib.util
from pathlib import Path

import pytest

from core.shot_architecture import atomicity_audit, normalize_architecture_ir, parse_architecture_envelope


def _forensic_module():
    spec = importlib.util.spec_from_file_location("forensic", "scripts/run_director_quality_v3_shot_architecture_forensic.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _shot(**overrides):
    value = {
        "phase_id": "P01", "beat_refs": ["B1"], "function": "观察", "subject": "character:C1",
        "shot_size": "中景", "camera_position": "门口", "camera_movement": "固定",
        "composition_intent": "保持空间关系", "performance_focus": "观察", "information_focus": "线索",
        "prop_focus": "none", "spatial_anchor": "门口", "entry_state": "开始", "exit_state": "停留",
        "cut_in_motivation": "建立空间", "cut_out_motivation": "注意转移", "hold_logic": "让观众消化",
        "continuity_requirements": "门的位置一致", "must_preserve_refs": "door",
    }
    value.update(overrides)
    return value


def test_outer_envelope_wins_over_large_nested_shot():
    raw = json.dumps({"architecture_summary": "建立。推进。收束。", "shots": [_shot()]}, ensure_ascii=False)
    parsed = parse_architecture_envelope(raw)
    assert "shots" in parsed and "architecture_summary" in parsed
    assert parsed["shots"][0]["phase_id"] == "P01"


def test_envelope_requires_both_top_level_keys():
    with pytest.raises(ValueError):
        parse_architecture_envelope(json.dumps({"shots": [_shot()]}))
    with pytest.raises(ValueError):
        parse_architecture_envelope(json.dumps({"architecture_summary": "x"}))


def test_lossless_normalization_handles_b_refs_nullable_lists_and_motion_conflict():
    raw = {"architecture_summary": "建立。推进。收束。", "shots": [_shot(camera_movement="固定，轻微手持晃动", continuity_requirements="保持门轴", must_preserve_refs=None)]}
    result = normalize_architecture_ir(raw, scene_id="s1", strategy_fingerprint="fp")
    shot = result["ir"]["shots"][0]
    assert shot["beat_refs"] == ["beat:1"]
    assert shot["continuity_requirements"] == ["保持门轴"]
    assert shot["must_preserve_refs"] == []
    assert shot["camera_movement"] == "HANDHELD_SUBTLE"
    assert result["normalization_audit"][0]["camera_movement"]["reason"].startswith("most_specific_motion_wins")


def test_unknown_motion_is_review_required_not_none():
    result = normalize_architecture_ir({"architecture_summary": "建立。推进。收束。", "shots": [_shot(camera_movement="镜头自由漂移")]}, scene_id="s1", strategy_fingerprint="fp")
    assert result["ir"]["shots"][0]["camera_movement"] == ""
    assert result["normalization_audit"][0]["camera_movement"]["review_required"] is True


def test_atomicity_flags_composite_coverage_bundle():
    raw = {"architecture_summary": "建立。推进。收束。", "shots": [_shot(shot_size="中近景正反打", composition_intent="先A再切B")]}
    ir = normalize_architecture_ir(raw, scene_id="s1", strategy_fingerprint="fp")["ir"]
    audit = atomicity_audit(raw, ir)
    assert audit["status"] == "FAIL"
    assert audit["composite_bundle_count"] == 1
    assert "COMPOSITE_COVERAGE_BUNDLE" == audit["findings"][0]["code"]


def test_current_stage_pointer_uses_exact_final_strategy_fingerprints():
    module = _forensic_module()
    pointer = json.loads(Path("artifacts/director-quality-v3-current-stage-authority.json").read_text(encoding="utf-8"))
    scenes = pointer["strategy_layer"]["scenes"]
    assert set(scenes) == set(module.EXPECTED_CURRENT)
    assert {scene: scenes[scene]["fingerprint"] for scene in scenes} == module.EXPECTED_CURRENT
    assert pointer["director_critic_review"]["status"] == "PASS_WITH_NOTES"
    assert pointer["human_preference_review"]["status"] == "NOT_RECORDED"
