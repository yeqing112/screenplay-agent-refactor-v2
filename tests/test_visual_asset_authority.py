import json

import pytest

from core.asset_registry_sync import sync_assets_from_script_ir
from core.prompt_ir_authority import compile_prompt_ir_from_handoff
from core.visual_asset_authority import (
    AUTHORING_PENDING,
    REFERENCE_LOCKED,
    SPEC_APPROVED,
    VisualAssetAuthorityError,
    asset_readiness,
    build_asset_key,
    build_reference_generation_request_draft,
    build_reference_media_authority,
    classify_reference_asset,
    compile_visual_asset_spec,
    production_asset_binding,
    reference_requirement_policy,
    reference_stale_reasons,
)


def test_stable_identity_is_not_a_display_name():
    assert build_asset_key(book_id=7, asset_type="character", canonical_id="CHAR_01") == "book:7:character:CHAR_01"
    assert build_asset_key(book_id=7, asset_type="character", canonical_id="CHAR_01") == build_asset_key(book_id=7, asset_type="character", canonical_id="CHAR_01")
    with pytest.raises(VisualAssetAuthorityError):
        build_asset_key(book_id=7, asset_type="character", canonical_id="")


def test_source_constraints_are_immutable_and_silent_fields_are_authorable():
    spec = compile_visual_asset_spec(asset_type="character", asset_key="book:7:character:C1", canonical_identity={"character_id": "C1"}, source_constraints=[{"field": "gender", "value": "female", "source_ref": "fact:1"}], authoring_decisions=[{"field": "baseline_hairstyle", "value": "short hair", "decision_id": "D1"}])
    assert spec["canonical_spec"]["gender"] == "female"
    assert spec["authoring_spec"]["baseline_hairstyle"] == "short hair"
    with pytest.raises(VisualAssetAuthorityError) as exc:
        compile_visual_asset_spec(asset_type="character", asset_key="book:7:character:C1", canonical_identity={"character_id": "C1"}, source_constraints=[{"field": "gender", "value": "female"}], authoring_decisions=[{"field": "gender", "value": "male"}])
    assert exc.value.code == "SOURCE_AUTHORING_CONFLICT"


def test_character_variant_does_not_replace_canonical_spec():
    spec = compile_visual_asset_spec(asset_type="character", asset_key="book:7:character:C1", canonical_identity={"character_id": "C1"}, source_constraints=[{"field": "face", "value": "oval"}], variant_decisions=[{"field": "wardrobe", "value": "raincoat", "decision_id": "V1"}], scope={"episode": 2})
    assert spec["canonical_spec"]["face"] == "oval"
    assert spec["variant_spec"]["wardrobe"] == "raincoat"
    assert spec["scope"] == {"episode": 2}


def test_scene_geometry_and_prop_continuity_conflicts_fail_closed():
    with pytest.raises(VisualAssetAuthorityError) as scene_exc:
        compile_visual_asset_spec(asset_type="scene", asset_key="book:7:scene:S1", canonical_identity={"scene_id": "S1"}, geometry_authority={"conflicts": [{"field": "door", "code": "GEOMETRY_CONFLICT"}]})
    assert scene_exc.value.code == "SCENE_GEOMETRY_CONFLICT"
    with pytest.raises(VisualAssetAuthorityError) as prop_exc:
        compile_visual_asset_spec(asset_type="prop", asset_key="book:7:prop:P1", canonical_identity={"prop_id": "P1"}, continuity_authority={"conflicts": [{"field": "state", "code": "STATE_CONFLICT"}]})
    assert prop_exc.value.code == "PROP_CONTINUITY_CONFLICT"


def test_reference_lineage_and_staleness_classification():
    with pytest.raises(VisualAssetAuthorityError) as exc:
        build_reference_media_authority(asset_key="book:7:character:C1", asset_version_id=1, asset_version_fingerprint="fp", reference_scope={}, image_identity="", checksum="sha")
    assert exc.value.code == "REFERENCE_LINEAGE_REQUIRED"
    authority = build_reference_media_authority(asset_key="book:7:character:C1", asset_version_id=1, asset_version_fingerprint="fp", reference_scope={"role": "front"}, image_identity="img-1", checksum="sha", storage_reference={"local_path": "x"}, generation_provenance={"mode": "manual"})
    assert classify_reference_asset(authority, current_asset_version={"payload_hash": "fp"})["classification"] == "AUTHORITY_BINDABLE"
    assert classify_reference_asset(authority, current_asset_version={"payload_hash": "changed"})["classification"] == "STALE"
    assert reference_stale_reasons(authority, current_asset_version={"payload_hash": "fp"}, expected_checksum="changed") == ["IMAGE_CHECKSUM_CHANGED"]
    legacy = classify_reference_asset({"status": "LOCKED", "image_url": "old"})
    assert legacy["status"] == "LEGACY_REFERENCE_MIGRATION_REQUIRED"


def test_reference_policy_and_generation_draft_are_provider_free():
    assert reference_requirement_policy(asset_type="character", identity_importance="critical")["requirement"] == "REQUIRED"
    draft = build_reference_generation_request_draft(version={"id": 1, "asset_key": "book:7:scene:S1", "payload": {"canonical_spec": {"material": "brick"}}}, reference_purpose="four_view", aspect_layout_requirement={"aspect": "16:9"}, board_type="four_view_board")
    assert draft["status"] == "READY_FOR_PROVIDER_CANARY"
    assert draft["provider_not_called"] is True


def test_readiness_states_are_separate():
    assert asset_readiness(identity_ready=True, authoring_status=AUTHORING_PENDING, spec_approved=False, reference_required=True, reference_locked=False)["status"] == "ASSET_AUTHORING_PENDING"
    assert asset_readiness(identity_ready=True, authoring_status=SPEC_APPROVED, spec_approved=True, reference_required=True, reference_locked=False)["status"] == "ASSET_REFERENCE_PENDING"
    assert asset_readiness(identity_ready=True, authoring_status=SPEC_APPROVED, spec_approved=True, reference_required=True, reference_locked=True)["status"] == "ASSET_REFERENCE_READY"


def test_production_asset_binding_and_prompt_ir_do_not_invent_visual_facts():
    binding = production_asset_binding(asset_key="book:7:character:C1", asset_type="character", version={}, reference={})
    assert binding["authority_status"] == AUTHORING_PENDING
    handoff = {"schema_version": "storyboard_prompt_handoff_v1", "materialization_set_id": 1, "storyboard_shot_id": 2, "plan_shot_id": "S1", "beat_id": "B1", "scene_id": "SC1", "shot_plan_id": 3, "shot_plan_revision": 1, "shot_plan_authority_fingerprint": "sp", "storyboard_projection_fingerprint": "bp", "camera": {"shot_size": "MS", "angle": "eye", "movement": "static", "speed": "slow"}, "duration": 3, "action_beats": [{"description": "wait"}], "entry_state": {}, "exit_state": {}, "continuity_contract": {}, "asset_identity_bindings": {"canonical_asset_identity": {"characters": ["C1"]}}}
    ir = compile_prompt_ir_from_handoff(handoff, asset_authority={"bindings": [{**binding, "canonical_asset_id": "C1"}]})
    assert ir["asset_reference_state"] == "ASSET_AUTHORING_PENDING"
    assert ir["model_generation_ready"] is False
    assert not ir["assets"]["bindings"][0]["visual_facts"]


def test_registry_production_requires_stable_ids_and_reuses_identity():
    class Query:
        def filter_by(self, **kwargs): return self
        def first(self): return None
    class Session:
        def query(self, model): return Query()
        def add(self, row): pass
    with pytest.raises(ValueError, match="PRODUCTION_CHARACTER_ID_REQUIRED"):
        sync_assets_from_script_ir(Session(), {"characters": [{"name": "display only"}]}, book_id=7, episode=1, workflow_profile="production")
