from core.director_creative_contract import build_director_creative_contract
from core.director_creative_planner import build_creative_patch_candidate
from core.scene_directing_strategy import build_scene_directing_strategy
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
    strategy = build_scene_directing_strategy(treatment=treatment, contract=contract)
    return plan, contract, strategy


def test_patch_planner_does_not_call_llm_without_both_explicit_gates():
    plan, contract, strategy = _inputs()
    calls = []

    def fake_llm(_evidence):
        calls.append(True)
        return {"schema_version": "director_creative_patch_v1", "patches": [], "auxiliary_shot_proposals": []}

    result = build_creative_patch_candidate(structural_shot_plan=plan, contract=contract, strategy=strategy, llm_callable=fake_llm)
    assert calls == []
    assert result["director_mode"] == "deterministic_fallback"
    assert result["patch_document"]["patches"] == []


def test_patch_planner_calls_mock_only_after_confirmation_and_returns_patch_document():
    plan, contract, strategy = _inputs()
    calls = []

    def fake_llm(evidence):
        calls.append(evidence)
        return {
            "schema_version": "director_creative_patch_v1",
            "patches": [{"plan_shot_id": "S01", "changes": {"camera.shot_size": "CU"}}],
            "auxiliary_shot_proposals": [],
        }

    result = build_creative_patch_candidate(
        structural_shot_plan=plan,
        contract=contract,
        strategy=strategy,
        llm_callable=fake_llm,
        confirmed=True,
        allow_external_call=True,
    )
    assert len(calls) == 1
    assert result["model_info"]["llm_called"] is True
    assert result["patch_document"]["patches"][0]["plan_shot_id"] == "S01"
    assert "shots" not in result["patch_document"]


def test_patch_planner_rejects_complete_shot_plan_and_falls_back():
    plan, contract, strategy = _inputs()
    result = build_creative_patch_candidate(
        structural_shot_plan=plan,
        contract=contract,
        strategy=strategy,
        llm_output={"shots": plan["shots"]},
    )
    assert result["director_mode"] == "deterministic_fallback"
    assert result["patch_document"]["patches"] == []
    assert "schema rejected" in result["model_info"]["planner_error"]
    assert result["model_info"]["schema_pass"] is False
    assert result["model_info"]["forbidden_field_attempt"] is True
    assert result["model_info"]["schema_error_code"] == "DIRECTOR_PATCH_FIELD_FORBIDDEN"


def test_patch_planner_preserves_valid_items_when_one_model_patch_is_malformed():
    plan, contract, strategy = _inputs()
    # Add a second structural shot so the valid and invalid items target
    # independent IDs; the malformed item must not erase S01.
    plan["shots"].append({"plan_shot_id": "S02", "beat_id": "B01", "event": "进入"})
    result = build_creative_patch_candidate(
        structural_shot_plan=plan,
        contract=contract,
        strategy=strategy,
        llm_output={
            "schema_version": "director_creative_patch_v1",
            "patches": [
                {"plan_shot_id": "S01", "changes": {"camera.shot_size": "CU"}},
                {"plan_shot_id": "S02", "changes": {"scene_name": "改写事实"}},
            ],
            "auxiliary_shot_proposals": [],
        },
    )
    assert result["director_mode"] == "partial_creative_planner"
    assert [item["plan_shot_id"] for item in result["patch_document"]["patches"]] == ["S01"]
    assert result["model_info"]["schema_pass"] is False
    assert result["model_info"]["forbidden_field_attempt"] is True
    assert result["model_info"]["schema_rejections"][0]["code"] == "DIRECTOR_FACT_OVERRIDE"
