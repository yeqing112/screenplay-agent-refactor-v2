from core.director_creative_contract import build_director_creative_contract
from core.director_quality_v22 import process_patch_pipeline
from core.scene_directing_strategy import build_scene_directing_strategy
from core.shot_plan import build_shot_plan


def _inputs():
    treatment = {"scene_id": "E", "scene_name": "门厅", "beat_map": [{"beat_id": "B01", "event": "进入"}]}
    blocking = {"scene_id": "E", "scene_name": "门厅", "participants": [{"character_id": "C1", "name": "林晚"}]}
    plan = build_shot_plan(treatment=treatment, blocking=blocking)
    contract = build_director_creative_contract(treatment=treatment, blocking=blocking, structural_shot_plan=plan)
    strategy = build_scene_directing_strategy(treatment=treatment, contract=contract)
    return treatment, blocking, plan, contract, strategy


def test_pipeline_normalizes_equivalent_path_and_never_calls_level2():
    treatment, blocking, plan, contract, strategy = _inputs()
    calls = []
    result = process_patch_pipeline(
        structural_shot_plan=plan,
        contract=contract,
        strategy=strategy,
        treatment=treatment,
        blocking=blocking,
        raw_output={
            "schema_version": "director_creative_patch_v1",
            "patches": [{"plan_shot_id": "S01", "patch": [{"op": "replace", "path": "/shots/*/camera/shot_size", "value": "close-up"}]}],
            "auxiliary_shot_proposals": [],
        },
        llm_repair_callable=lambda request: calls.append(request) or {"plan_shot_id": "S01", "changes": {"camera.angle": "low_angle"}},
    )
    assert calls == []
    assert result["fallbacks"] == []
    assert result["candidate"]["shots"][0]["camera"]["shot_size"] == "CU"
    assert result["metrics"]["repair_cost"]["llm_repair_calls"] == 0


def test_pipeline_routes_invalid_creative_value_to_level2_only():
    treatment, blocking, plan, contract, strategy = _inputs()
    requests = []

    def repair(request):
        requests.append(request)
        return {"plan_shot_id": "S01", "changes": {"camera.angle": "low_angle"}}

    result = process_patch_pipeline(
        structural_shot_plan=plan,
        contract=contract,
        strategy=strategy,
        treatment=treatment,
        blocking=blocking,
        raw_output={
            "schema_version": "director_creative_patch_v1",
            "patches": [{"plan_shot_id": "S01", "changes": {"camera.angle": ""}}],
            "auxiliary_shot_proposals": [],
        },
        llm_repair_callable=repair,
    )
    assert len(requests) == 1
    assert requests[0]["failed_patch"]["plan_shot_id"] == "S01"
    assert result["repair_attempts"][0]["status"] == "repaired"
    assert result["fallbacks"] == []


def test_pipeline_rejects_unknown_target_without_level2_call():
    _, _, plan, contract, strategy = _inputs()
    calls = []
    result = process_patch_pipeline(
        structural_shot_plan=plan,
        contract=contract,
        strategy=strategy,
        raw_output={
            "schema_version": "director_creative_patch_v1",
            "patches": [{"plan_shot_id": "S99", "changes": {"camera.angle": "low_angle"}}],
            "auxiliary_shot_proposals": [],
        },
        llm_repair_callable=lambda request: calls.append(request),
    )
    assert calls == []
    assert result["fallbacks"][0]["root_cause"] == "UNKNOWN"


def test_pipeline_keeps_valid_sibling_when_one_patch_has_authority_violation():
    _, _, plan, contract, strategy = _inputs()
    result = process_patch_pipeline(
        structural_shot_plan=plan,
        contract=contract,
        strategy=strategy,
        raw_output={
            "schema_version": "director_creative_patch_v1",
            "patches": [
                {"plan_shot_id": "S01", "changes": {"camera.angle": "low_angle"}},
                {"plan_shot_id": "S01", "changes": {"event": "改写事实"}},
            ],
            "auxiliary_shot_proposals": [],
        },
    )
    assert result["candidate"]["shots"][0]["camera"]["angle"] == "low_angle"
    assert any(item["root_cause"] == "FACT_OVERRIDE" for item in result["fallbacks"])
