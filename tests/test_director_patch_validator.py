from core.director_creative_contract import build_director_creative_contract
from core.director_patch_compiler import compile_creative_patches
from core.director_patch_validator import validate_compiled_patch_result
from core.director_patch_schema import parse_creative_patch
from core.shot_plan import build_shot_plan


def _inputs():
    treatment = {
        "scene_id": "E01_SC01",
        "scene_name": "雨夜门厅",
        "beat_map": [{"beat_id": "B01", "type": "reveal", "event": "林晚发现照片"}],
    }
    blocking = {
        "scene_id": "E01_SC01",
        "scene_name": "雨夜门厅",
        "participants": [{"character_id": "C1", "name": "林晚"}],
    }
    plan = build_shot_plan(treatment=treatment, blocking=blocking)
    contract = build_director_creative_contract(treatment=treatment, blocking=blocking, structural_shot_plan=plan)
    return treatment, blocking, plan, contract


def test_validator_separates_contract_pass_from_quality_warnings():
    treatment, blocking, plan, contract = _inputs()
    document = parse_creative_patch({
        "schema_version": "director_creative_patch_v1",
        "patches": [{"plan_shot_id": "S01", "changes": {"camera.shot_size": "CU"}}],
        "auxiliary_shot_proposals": [],
    })
    compilation = compile_creative_patches(plan, document, contract)
    report = validate_compiled_patch_result(compilation, plan, contract, treatment=treatment, blocking=blocking)
    assert report["contract_pass"] is True
    assert report["status"] == "valid"
    assert isinstance(report["warnings"], list)


def test_validator_blocks_shot_count_expansion_and_unbound_auxiliary():
    treatment, blocking, plan, contract = _inputs()
    candidate = {**plan, "shots": [*plan["shots"], {"plan_shot_id": "AUX_1", "event": "new"}]}
    report = validate_compiled_patch_result({"candidate": candidate, "compiled_patches": [], "rejected_patches": [], "auxiliary_shot_proposals": []}, plan, contract, treatment=treatment, blocking=blocking)
    assert report["contract_pass"] is False
    assert report["status"] == "invalid"
    assert any(item["code"] == "SHOT_COUNT_EXPANSION" for item in report["errors"])

    bad_aux = {
        "candidate": plan,
        "compiled_patches": [],
        "rejected_patches": [],
        "auxiliary_shot_proposals": [{
            "proposal_id": "AUX_1",
            "proposal_type": "reaction",
            "source_beat_id": "B99",
            "insert_after_plan_shot_id": "S01",
            "purpose": "reaction",
            "why_needed": "need reaction",
            "participants": ["C1"],
            "camera": {"shot_size": "CU"},
        }],
    }
    report = validate_compiled_patch_result(bad_aux, plan, contract)
    assert report["contract_pass"] is True
    assert report["status"] == "partial"
    assert any(item["code"] == "AUXILIARY_SHOT_UNBOUND_BEAT" for item in report["errors"])
