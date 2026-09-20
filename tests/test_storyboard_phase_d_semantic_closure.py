"""Provider-free Phase D semantic projection and diff contracts."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from core.storyboard_handoff import project_shot_design_to_storyboard_handoff
from core.storyboard_materializer import build_storyboard_production_snapshot, materialize_storyboard_from_handoff
from core.storyboard_visual_semantics import (
    VISUAL_SEMANTIC_HANDOFF_SCHEMA_VERSION,
    compare_shotplan_storyboard_semantics,
    semantic_projection_fingerprint,
    validate_asset_identity_bindings,
)


ART = Path(__file__).resolve().parents[1] / "artifacts" / "e2e-production-pilot"


def _pilot():
    plans = json.loads((ART / "episode_01_shot_plan_phase_c.json").read_text(encoding="utf-8"))["plans"]
    blocking = json.loads((ART / "episode_01_scene_blocking_phase_b.json").read_text(encoding="utf-8"))["scenes"]
    for plan, block in zip(plans, blocking):
        source = copy.deepcopy(plan)
        source["scene_name"] = source["scene_id"]
        handoff = project_shot_design_to_storyboard_handoff(source, blocking=block, require_phase_c=True)
        yield source, handoff


def test_visual_semantic_handoff_preserves_structured_refs_and_never_prompt_text():
    plan, handoff = next(_pilot())
    projections = materialize_storyboard_from_handoff(handoff, production=True, shot_plan_id=2, source_authority_fingerprint="sp", blocking_authority_fingerprint="bp")
    semantic = projections[1]["visual_semantic_handoff"]
    assert semantic["schema_version"] == VISUAL_SEMANTIC_HANDOFF_SCHEMA_VERSION
    assert semantic["information_refs"] == plan["shots"][1]["information_refs"]
    assert semantic["reaction_contract_refs"] == plan["shots"][1]["reaction_contract_refs"]
    assert semantic["coverage_roles"] == plan["shots"][1]["coverage_roles"]
    assert semantic["camera"]["movement"] == plan["shots"][1]["camera_state"]["movement"]
    assert semantic["camera"]["movement_trigger"] == plan["shots"][1]["camera_state"]["movement_trigger"]
    assert semantic["temporal_intent"] == plan["shots"][1]["temporal_intent"]
    assert semantic["information_visibility"] == plan["shots"][1]["information_visibility"]
    assert "prompt" not in json.dumps(semantic, ensure_ascii=False).lower()
    assert semantic["projection_provenance"]["source_shot_plan_authority_fingerprint"] == "sp"


def test_structured_semantic_diff_has_camera_continuity_asset_and_missing_categories():
    _plan, handoff = list(_pilot())[1]
    projections = materialize_storyboard_from_handoff(handoff, production=True)
    expected = [item["visual_semantic_handoff"] for item in projections]
    actual = copy.deepcopy(expected)
    actual[0]["camera"]["movement"] = "STATIC_TAMPER"
    actual[0]["continuity"]["screen_side_assignments"] = {"unexpected": "LEFT"}
    actual[0]["asset_identity_bindings"]["canonical_asset_identity"]["props"] = ["UNEXPECTED_PROP"]
    actual.pop()
    diff = compare_shotplan_storyboard_semantics(expected, actual)
    assert not diff["empty"]
    assert diff["missing_shots"]
    assert diff["camera_mismatch"]
    assert diff["continuity_mismatch"]
    assert diff["asset_binding_mismatch"]


def test_semantic_projection_fingerprint_is_deterministic_and_detects_tamper():
    _plan, handoff = next(_pilot())
    semantic = materialize_storyboard_from_handoff(handoff, production=True)[0]["visual_semantic_handoff"]
    assert semantic_projection_fingerprint(semantic) == semantic_projection_fingerprint(copy.deepcopy(semantic))
    tampered = copy.deepcopy(semantic)
    tampered["information_refs"].append("UNEXPECTED_INFO")
    assert semantic_projection_fingerprint(tampered) != semantic_projection_fingerprint(semantic)


def test_asset_identity_gate_requires_only_declared_subjects_and_props():
    _plan, handoff = list(_pilot())[1]
    semantic = materialize_storyboard_from_handoff(handoff, production=True)[3]["visual_semantic_handoff"]
    assert validate_asset_identity_bindings(semantic=semantic, required_subjects=["林晚", "陆叔"], required_props=["POCKET_HARD_OBJECT"], scene_id="E01_SC002") == []
    broken = copy.deepcopy(semantic)
    broken["asset_identity_bindings"]["canonical_asset_identity"]["props"] = []
    assert validate_asset_identity_bindings(semantic=broken, required_subjects=["林晚", "陆叔"], required_props=["POCKET_HARD_OBJECT"], scene_id="E01_SC002")


def test_production_snapshot_is_read_only_structured_boundary():
    _plan, handoff = next(_pilot())
    projections = materialize_storyboard_from_handoff(handoff, production=True)

    class SetRow:
        id = 7
        set_payload_fingerprint = "set-fp"
        status = "MATERIALIZED"
        stale_status = "FRESH"

    class Row:
        def __init__(self, value):
            self.id = value.get("shot_id")
            self.plan_shot_id = value.get("plan_shot_id")
            self.projection_fingerprint = value.get("projection_fingerprint")
            self.meta_info = json.dumps(value.get("meta_info", {}), ensure_ascii=False)

    snapshot = build_storyboard_production_snapshot(materialization_set=SetRow(), rows=[Row(item) for item in projections], authority_envelope={"storyboard_handoff": {"handoff_fingerprint": handoff["handoff_fingerprint"]}})
    assert snapshot["schema_version"] == "storyboard_production_snapshot_v1"
    assert len(snapshot["ordered_shots"]) == len(projections)
    assert snapshot["prompt_prose"] is False
    assert snapshot["media_state"] == "NOT_GENERATED"
