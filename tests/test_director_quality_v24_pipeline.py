from core.director_creative_contract import build_director_creative_contract
from core.director_quality_v24_pipeline import run_v24_scene_pipeline


def _scene():
    script = {
        "scene_id": "SCENE_01",
        "episode": 1,
        "state_out": {"result": "key found"},
    }
    treatment = {
        "scene_id": "SCENE_01",
        "scene_name": "门厅",
        "beat_map": [
            {
                "beat_id": "B01",
                "type": "reveal",
                "event": "C1发现钥匙",
                "information_change": "钥匙属于失踪者",
                "emotion_change": "警觉",
                "participants": ["C1"],
            }
        ],
    }
    blocking = {"scene_id": "SCENE_01", "participants": ["C1"]}
    plan = {
        "scene_id": "SCENE_01",
        "scene_name": "门厅",
        "shots": [
            {
                "plan_shot_id": "S01",
                "scene_id": "SCENE_01",
                "beat_id": "B01",
                "event": "C1发现钥匙",
                "participants": ["C1"],
                "duration_hint_seconds": 3,
                "asset_bindings": {},
                "continuity_contract": {},
            }
        ],
    }
    contract = build_director_creative_contract(
        script_scene=script,
        treatment=treatment,
        blocking=blocking,
        structural_shot_plan=plan,
    )
    return {
        "scene": {"scene_id": "SCENE_01", "scene_name": "门厅"},
        "evidence": {
            "scene_canonical": script,
            "treatment": treatment,
            "blocking": blocking,
            "structural_shot_plan": plan,
        },
        "contract": contract,
    }


def test_v24_pipeline_is_provider_free_and_fail_closed_without_decisions():
    calls = []
    result = run_v24_scene_pipeline(
        _scene(),
        contract_repair_callable=lambda request: calls.append(request),
        tail_repair_callable=lambda request: calls.append(request),
    )

    assert result["status"] == "needs_information"
    assert result["decision_errors"]
    assert result["side_effects"] == {"production": 0, "storyboard": 0, "media": 0, "object_storage": 0}
    # A clean first-pass contract does not invoke contract repair; the tail
    # executor may report non-repairable, but missing planner decisions never
    # trigger an external provider call.
    assert calls == []
    assert result["intervention_trace"]["trace_complete"] is True


def test_v24_pipeline_connects_eligibility_trace_and_value_stages():
    scene = _scene()
    # The detector is authoritative; use its IDs and a matching explicit
    # decision so the integration assertion remains generic as detector rules
    # evolve.
    from core.director_opportunity_detector import detect_creative_opportunities

    detected = detect_creative_opportunities(
        script_scene=scene["evidence"]["scene_canonical"],
        treatment=scene["evidence"]["treatment"],
        blocking=scene["evidence"]["blocking"],
        structural_shot_plan=scene["evidence"]["structural_shot_plan"],
    )
    decisions = [
        {"opportunity_id": item["opportunity_id"], "decision": "ACT", "strategy": "让观众先看见钥匙再切反应"}
        for item in detected
    ]
    result = run_v24_scene_pipeline(
        scene,
        patch_document={
            "schema_version": "director_creative_patch_v1",
            "patches": [
                {
                    "plan_shot_id": "S01",
                    "changes": {"information_strategy.reveals": ["钥匙属于失踪者"]},
                }
            ],
            "auxiliary_shot_proposals": [],
        },
        planner_decisions=decisions,
    )
    assert result["status"] == "valid"
    assert result["intervention_trace"]["trace_complete"] is True
    assert result["intervention_trace"]["eligible_count"] == result["opportunity_value"]["eligible_opportunity_count"]
    assert result["opportunity_value"]["schema_version"] == "director_useful_creative_acceptance_v3"
    assert result["tail_repair"]["schema_version"]
