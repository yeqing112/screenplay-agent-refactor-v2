from core.asset_view_framing import AssetViewFramingPolicy
from scripts.run_autonomous_visual_asset_pipeline_v4 import _character_derived_prompt


def test_character_face_and_full_views_use_distinct_semantic_framing():
    face = AssetViewFramingPolicy.for_view("CHARACTER", "FACE_PROFILE")
    full = AssetViewFramingPolicy.for_view("CHARACTER", "FULL_SIDE")
    assert (face.framing_class, face.requested_aspect_ratio, face.provider_aspect_ratio) == ("FACE", "1:1", "1:1")
    assert (full.framing_class, full.requested_aspect_ratio, full.provider_aspect_ratio) == ("FULL_BODY", "2:3", "9:16")
    assert full.projection_reason != "requested_ratio_supported"


def test_provider_ratio_projection_is_explicit():
    framing = AssetViewFramingPolicy.for_view("CHARACTER", "MASTER", provider_ratios=("1:1", "16:9"))
    assert framing.provider_aspect_ratio == "1:1"
    assert framing.projection_reason == "requested_ratio_projected_to_nearest_legal_provider_ratio"


def test_prop_and_scene_framing_contracts():
    assert AssetViewFramingPolicy.for_view("PROP", "DETAIL").requested_aspect_ratio == "1:1"
    assert AssetViewFramingPolicy.for_view("SCENE", "MASTER").requested_aspect_ratio == "16:9"


def test_character_prompt_contains_face_and_full_framing_contracts():
    character = {"name": "林晚", "description": "stable identity"}
    face_prompt = _character_derived_prompt(character, "FACE_FRONT")
    full_prompt = _character_derived_prompt(character, "FULL_BACK")
    assert "头肩构图" in face_prompt and "不出现全身" in face_prompt
    assert "完整头部和完整鞋脚" in full_prompt and "全身高度" in full_prompt
