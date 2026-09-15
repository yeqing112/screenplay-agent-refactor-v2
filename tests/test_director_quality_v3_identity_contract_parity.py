import copy
import pytest

from core.director_scene_strategy import SceneStrategyError, build_runtime_strategy_contract, canonicalize_allowed_characters, strategy_fingerprint
from core.director_scene_strategy_semantic_spec_v2 import build_provider_skeleton
from core.director_strategy_prompt import build_scene_strategy_ir_v2_prompt


def bindings():
    return [
        {"character_id": "20", "canonical_name": "顾沉", "canonical_identity_id": None, "scope": "book-level"},
        {"character_id": "19", "canonical_name": "林晚", "canonical_identity_id": None, "scope": "book-level"},
    ]


def test_same_identity_different_order_has_same_fingerprint():
    assert strategy_fingerprint(canonicalize_allowed_characters(bindings(), book_id="990402")) == strategy_fingerprint(canonicalize_allowed_characters(list(reversed(bindings())), book_id="990402"))


@pytest.mark.parametrize("field", ["character_id", "canonical_name", "canonical_identity_id", "scope"])
def test_identity_field_change_changes_fingerprint(field):
    base = canonicalize_allowed_characters(bindings(), book_id="990402")
    changed = copy.deepcopy(base)
    if field == "character_id": changed[0][field] = "99"
    elif field == "canonical_name": changed[0][field] = "林婉"
    elif field == "canonical_identity_id": changed[0][field] = "book:990402:character:99"
    else: changed[0][field] = "project-level"
    assert strategy_fingerprint(base) != strategy_fingerprint(changed)


@pytest.mark.parametrize("value,kwargs,code", [
    ([{"character_id": "19", "canonical_name": ""}], {"book_id": "990402"}, "IDENTITY_CONTRACT_INVALID"),
    ([{"character_id": "19", "canonical_name": "林晚"}], {}, "IDENTITY_CONTRACT_MISSING_BOOK_ID"),
    ([{"character_id": "19", "canonical_name": "林晚"}, {"character_id": "19", "canonical_name": "顾沉"}], {"book_id": "990402"}, "IDENTITY_CONTRACT_CONFLICT"),
])
def test_identity_validation_fail_closed(value, kwargs, code):
    with pytest.raises(SceneStrategyError, match="") as exc:
        canonicalize_allowed_characters(value, **kwargs)
    assert exc.value.code == code


def test_provider_skeleton_contains_complete_identity_projection():
    runtime = {"book_id": "990402", "allowed_characters": bindings(), "source_ref_contract": {"allowed_source_refs": []}}
    skeleton = build_provider_skeleton(scene_id="s", beat_ids=["B1"], character_ids=["19", "20"], runtime_contract=runtime)
    assert skeleton["allowed_characters"] == canonicalize_allowed_characters(bindings(), book_id="990402")


def test_full_prompt_fingerprint_includes_identity_projection():
    runtime = {"book_id": "990402", "scene_id": "s", "beat_ids": ["B1"], "character_ids": ["19", "20"], "allowed_characters": bindings(), "source_ref_contract": {"allowed_source_refs": [], "beat_alias_table": {}, "allowed_ids": {}}}
    prompt = build_scene_strategy_ir_v2_prompt(evidence={"strategy_contract": runtime}, model_profile={"model_name": "mimo-v2.5"})
    altered = copy.deepcopy(prompt["provider_contract"])
    altered["allowed_characters"][0]["canonical_name"] = "林婉"
    assert prompt["identity_binding_fingerprint"] != strategy_fingerprint(altered["allowed_characters"])
