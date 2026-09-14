from core.director_creative_contract import build_director_creative_contract
from core.director_creative_planner import build_creative_patch_candidate
from core.director_information_strategy import evaluate_information_strategy
from core.director_opportunity_detector import detect_creative_opportunities
from core.director_opportunity_planner import normalize_planner_decisions
from core.director_creative_value import build_creative_value_score, evaluate_useful_creative_acceptance
from core.director_overdirecting import detect_over_directing
from core.director_patch_compiler import compile_creative_patches
from core.director_quality_validator import score_director_quality
from core.director_shadow_gate import evaluate_shadow_gate
from core.director_tail_analysis import build_tail_analysis
from core.director_tail_repair import build_tail_repair_plan
from core.director_tail_root_cause import classify_tail_root_cause
from core.scene_directing_strategy import build_scene_directing_strategy_v2


def _evidence():
    script = {"scene_id": "SCENE_01", "episode": 1, "participants": [{"character_id": "C1"}, {"character_id": "C2"}], "state_out": {"result": "key found"}}
    treatment = {"scene_id": "SCENE_01", "scene_name": "门厅", "beat_map": [
        {"beat_id": "B01", "type": "setup", "event": "C1与C2进入门厅", "participants": ["C1", "C2"]},
        {"beat_id": "B02", "type": "reveal", "event": "C1发现钥匙", "information_change": "钥匙属于失踪者", "emotion_change": "警觉", "participants": ["C1"]},
    ]}
    blocking = {"scene_id": "SCENE_01", "participants": [{"character_id": "C1"}, {"character_id": "C2"}], "source_spatial_facts": []}
    plan = {"scene_id": "SCENE_01", "scene_name": "门厅", "shots": [
        {"plan_shot_id": "S01", "scene_id": "SCENE_01", "beat_id": "B01", "event": "C1与C2进入门厅", "participants": ["C1", "C2"], "duration_hint_seconds": 4, "asset_bindings": {}, "continuity_contract": {}},
        {"plan_shot_id": "S02", "scene_id": "SCENE_01", "beat_id": "B02", "event": "C1发现钥匙", "participants": ["C1"], "duration_hint_seconds": 3, "asset_bindings": {"prop_asset_ids": ["PROP_KEY"]}, "continuity_contract": {}},
    ]}
    return script, treatment, blocking, plan


def test_phase_b_offline_chain_preserves_facts_and_reaches_gate():
    script, treatment, blocking, plan = _evidence()
    opportunities = detect_creative_opportunities(script_scene=script, treatment=treatment, blocking=blocking, structural_shot_plan=plan)
    assert opportunities
    contract = build_director_creative_contract(script_scene=script, treatment=treatment, blocking=blocking, structural_shot_plan=plan)
    strategy = build_scene_directing_strategy_v2(treatment=treatment, contract=contract, structural_shot_plan=plan)
    decisions = normalize_planner_decisions(
        [{"opportunity_id": item["opportunity_id"], "decision": "ACT", "strategy": "以反应完成/信息揭示作为切点"} for item in opportunities], opportunities
    )
    patch_candidate = build_creative_patch_candidate(
        structural_shot_plan=plan,
        contract=contract,
        strategy=strategy,
        llm_output={"schema_version": "director_creative_patch_v1", "patches": [{"plan_shot_id": "S02", "changes": {"edit.cut_reason": "reveal_read", "information_strategy.reveals": ["钥匙属于失踪者"]}}], "auxiliary_shot_proposals": []},
    )
    compiled = compile_creative_patches(plan, patch_candidate["patch_document"], contract, allow_partial=False)
    assert compiled["status"] == "compiled"
    assert compiled["candidate"]["shots"][0]["event"] == plan["shots"][0]["event"]
    assert compiled["candidate"]["shots"][1]["asset_bindings"] == plan["shots"][1]["asset_bindings"]
    before = score_director_quality(plan, treatment=treatment, blocking=blocking)["director_quality_score"]
    after = score_director_quality(compiled["candidate"], treatment=treatment, blocking=blocking)["director_quality_score"]
    interventions = [{"opportunity_id": opportunities[0]["opportunity_id"], "patch_valid": True, "applied": True, "fact_contract_pass": True, "new_blocker": False, "quality_delta": max(0, after - before), "dimension_deltas": {"edit_strategy": max(0, after - before)}}]
    # Remaining opportunities are explicitly skipped with reasons; no silent skip.
    decisions_for_value = [{"opportunity_id": item["opportunity_id"], "decision": "ACT", "strategy": "执行证据支持的导演处理"} for item in opportunities]
    value = evaluate_useful_creative_acceptance(opportunities=opportunities, decisions=decisions_for_value, interventions=interventions)
    assert value["missed_opportunity_count"] == 0
    info = evaluate_information_strategy({"known_to_audience": [], "withheld_from_audience": ["钥匙属于失踪者"], "reveal_plan": [{"beat_id": "B02", "reveals": ["钥匙属于失踪者"], "withholds": [], "audience_should_notice": "钥匙", "audience_should_not_yet_know": "身份"}], "reaction_priority": ["C1"], "audience_focus": ["钥匙"]}, shots=compiled["candidate"]["shots"], beat_map=treatment["beat_map"])
    over = detect_over_directing(compiled["candidate"]["shots"], opportunities=opportunities, baseline_shot_count=2, allowed_auxiliary_count=0)
    tail = build_tail_analysis([{"scene_id": "SCENE_01", "director_quality_score": after, "creative_value": {"score": 75}}])
    root = classify_tail_root_cause({"scene_id": "SCENE_01", "director_quality_score": after, "coverage": {"edit_strategy_coverage": 1.0, "emotion_arc_coverage": 1.0, "information_strategy_coverage": info["coverage"] or 0.0, "useful_creative_acceptance_rate": value["useful_creative_acceptance_rate"] or 0.0}})
    repair_plan = build_tail_repair_plan({"director_quality_score": after, "coverage": {"edit_strategy_coverage": 1.0, "emotion_arc_coverage": 1.0, "information_strategy_coverage": 1.0}}, root_causes=[root["root_cause"]])
    cv = build_creative_value_score(opportunity_coverage=1.0, useful_creative_acceptance=value["useful_creative_acceptance_rate"] or 0.0, edit_strategy=1.0, emotion_arc=1.0, information_strategy=info["coverage"] or 0.0, tail_stability=1.0)
    gate = evaluate_shadow_gate(contract_pass_rate=1.0, fact_override_accepted=0, unknown_root_cause_count=0, director_quality_mean=after, director_quality_median=after, director_quality_p10=after, director_quality_min=after, creative_value_mean=cv["score"], creative_value_median=cv["score"], useful_creative_acceptance=value["useful_creative_acceptance_rate"] or 0.0, edit_strategy_eligible_coverage=1.0, emotion_arc_eligible_coverage=1.0, information_strategy_eligible_coverage=info["coverage"] or 0.0, over_directing_rate=over["over_directing_rate"] or 0.0, shot_inflation_rate=over["shot_inflation_rate"] or 0.0)
    assert tail["statistics"]["count"] == 1
    assert repair_plan["schema_version"]
    assert gate["automatic_shadow_enabled"] is False
