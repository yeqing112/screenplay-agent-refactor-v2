import copy

from core.director_creative_critic_schema import CREATIVE_CRITIC_SCHEMA_VERSION, ProviderFreeCriticAdapter, validate_director_critic_result
from core.director_professional_qa import run_professional_qa, detect_scorer_gaming
from core.director_repair_routing import route_qa_findings
from core.director_scene_redesign import build_scene_redesign_request, validate_scene_redesign_request
from core.director_scene_strategy import build_scene_directing_strategy, build_strategy_contract, validate_scene_directing_strategy
from core.director_strategy_to_shot_contract import build_strategy_to_shot_contract, transition_shot_plan_state, validate_strategy_traceability


def evidence():
    scene = {"scene_id": "SC1", "name": "雨夜门厅", "beats": [
        {"beat_id": "B1", "type": "setup", "event": "人物进入门厅", "dramatic_function": "建立关系"},
        {"beat_id": "B2", "type": "obstacle", "event": "人物发现异常", "dramatic_function": "增加压力"},
        {"beat_id": "B3", "type": "reveal", "event": "照片暴露线索", "dramatic_function": "揭示信息", "information_change": "照片线索"},
    ]}
    treatment = {"dramatic_objective": "让观众从相信转向怀疑", "audience_question": "谁在隐瞒照片的来源？", "character_intents": {"C1": {"name": "林晚", "goal": "保护线索"}, "C2": {"name": "神秘人", "goal": "夺回主动权"}}}
    blocking = {"participants": [{"character_id": "C1"}, {"character_id": "C2"}], "source_spatial_facts": [{"fact_id": "F1", "subject_id": "C1", "predicate": "position", "value": "door"}]}
    contract = build_strategy_contract(scene=scene, treatment=treatment, blocking=blocking)
    strategy = build_scene_directing_strategy(scene=scene, treatment=treatment, blocking=blocking)
    return scene, treatment, blocking, contract, strategy


def coherent_plan(strategy):
    rows = []
    for index, phase in enumerate(strategy["audience_experience"], 1):
        beat_id = phase["beat_ids"][0]
        reveal = next(row for row in strategy["information_reveal_plan"] if row["beat_id"] == beat_id)
        emotion = next(row for row in strategy["emotional_arc"] if beat_id in row["beat_ids"])
        camera = {"shot_size": "WS" if index == 1 else "MS", "angle": "eye_level", "movement": "static" if index < 3 else "slow_push_in", "speed": "slow", "camera_side": "center"}
        rows.append({
            "plan_shot_id": f"S{index:02d}", "beat_id": beat_id, "strategy_phase_id": phase["phase_id"],
            "dramatic_function": "establishing" if index == 1 else "reveal" if reveal["reveal"] else "pressure",
            "audience_information_state": "known facts only" if not reveal["reveal"] else "line of sight to declared clue",
            "emotion_phase": emotion["phase"], "power_state": "power shift visible" if index == 3 else "relationship readable",
            "edit_function": "hold" if index == 3 else "beat_change", "camera_motivation": "the reveal changes the audience's reading" if index == 3 else "establish the relationship before the next beat",
            "performance_function": "C1 reacts and C2 observes", "purpose": "reaction" if index == 3 else "relationship",
            "why_this_shot": "hold the reaction so the audience can reinterpret the declared clue" if index == 3 else "establish the spatial relationship before the next beat",
            "camera": camera, "emotion": {"intensity": emotion["intensity_hint"], "state": emotion["emotion_state"]},
            "edit": {"duration_seconds": 3.0 if index == 3 else 4.0, "cut_reason": "reaction_completion" if index == 3 else "beat_change"},
            "information_strategy": {"reveals": reveal["reveal"], "withholds": reveal["withhold"], "audience_focus": "declared clue"},
            "performance_direction": [{"character_id": "C1", "objective": "protect the clue", "visible_behavior": "shifts gaze after the reveal"}, {"character_id": "C2", "objective": "recover control", "visible_behavior": "holds position and watches"}],
        })
    return {"scene_id": strategy["scene_id"], "shots": rows}


def test_strategy_schema_and_authority_boundary():
    _, _, _, contract, strategy = evidence()
    result = validate_scene_directing_strategy(strategy, contract)
    assert result["valid"] is True
    assert set(strategy["authority"]) == {"SOURCE_FACT", "TREATMENT_INTENT", "BLOCKING_FACT", "DIRECTOR_CREATIVE_DECISION"}


def test_strategy_missing_objective_fails():
    _, _, _, contract, strategy = evidence()
    broken = copy.deepcopy(strategy); broken["dramatic_objective"] = ""
    result = validate_scene_directing_strategy(broken, contract)
    assert result["valid"] is False and result["errors"][0]["code"] == "STRATEGY_SCHEMA_INCOMPLETE"


def test_strategy_unknown_beat_and_character_fail():
    _, _, _, contract, strategy = evidence()
    broken = copy.deepcopy(strategy); broken["beat_priorities"][0]["beat_id"] = "B99"
    assert validate_scene_directing_strategy(broken, contract)["valid"] is False


def test_strategy_reveal_chronology_and_internal_contradiction_fail():
    _, _, _, contract, strategy = evidence()
    broken = copy.deepcopy(strategy); broken["information_reveal_plan"] = list(reversed(broken["information_reveal_plan"]))
    assert validate_scene_directing_strategy(broken, contract)["valid"] is False
    broken = copy.deepcopy(strategy); broken["information_reveal_plan"][0]["reveal"] = ["declared beat B1"]; broken["information_reveal_plan"][0]["withhold"] = ["declared beat B1"]
    assert validate_scene_directing_strategy(broken, contract)["valid"] is False
    broken = copy.deepcopy(strategy); broken["performance_arc"][0]["character_id"] = "C99"
    assert validate_scene_directing_strategy(broken, contract)["valid"] is False


def test_strategy_to_shot_trace_complete_and_lifecycle():
    _, _, _, contract, strategy = evidence(); plan = coherent_plan(strategy)
    contract_doc = build_strategy_to_shot_contract(strategy=strategy, draft_shot_plan=plan)
    trace = validate_strategy_traceability(contract=contract_doc, draft_shot_plan=plan)
    assert trace["valid"] is True and trace["coverage"]["complete_trace_count"] == 3
    assert transition_shot_plan_state(current_state="DRAFT", target_state="READY_FOR_APPROVAL", layer1_pass=True, layer2_pass=True)["topology_mutable"] is True
    approved = transition_shot_plan_state(current_state="READY_FOR_APPROVAL", target_state="APPROVED", layer1_pass=True, layer2_pass=True, critic_pass=True)
    assert approved["topology_frozen"] is True


def test_generic_motivation_and_arc_issues_route_to_repairs():
    _, _, _, _, strategy = evidence(); plan = coherent_plan(strategy)
    plan["shots"][0]["why_this_shot"] = "show the beat"
    plan["shots"][1]["why_this_shot"] = "help audience follow"
    result = run_professional_qa(strategy=strategy, shot_plan=plan)
    codes = {item["issue_code"] for item in result["findings"]}
    assert "GENERIC_SHOT_MOTIVATION" in codes
    assert route_qa_findings(result["findings"])["next_route"] in {"TAIL_REPAIR", "SCENE_REPAIR"}


def test_scene_repair_issue_families_are_evidence_based():
    _, _, _, _, strategy = evidence(); plan = coherent_plan(strategy)
    for shot in plan["shots"]:
        shot["performance_direction"] = []
        shot["power_state"] = ""
        shot["edit_function"] = "beat_change"
        shot["purpose"] = "relationship"
    result = run_professional_qa(strategy=strategy, shot_plan=plan)
    codes = {item["issue_code"] for item in result["findings"]}
    assert "PERFORMANCE_ARC_GAP" in codes and "POWER_SHIFT_NOT_VISUALIZED" in codes and "EDIT_ARC_MISMATCH" in codes and "REACTION_MISSING" in codes
    assert route_qa_findings(result["findings"])["next_route"] == "SCENE_REDESIGN"


def test_reveal_timing_and_unknown_reveal_are_detected():
    _, _, _, _, strategy = evidence(); plan = coherent_plan(strategy)
    strategy["information_reveal_plan"][1]["reveal"] = ["declared beat B2"]
    reveal_shot = plan["shots"][-1]
    reveal_shot["information_strategy"]["reveals"] = ["declared beat B2"]
    plan["shots"][0]["information_strategy"]["reveals"] = ["declared beat B3"]
    result = run_professional_qa(strategy=strategy, shot_plan=plan)
    codes = {item["issue_code"] for item in result["findings"]}
    assert "REVEAL_TOO_EARLY" in codes and "REVEAL_TOO_LATE" in codes


def test_progression_noise_is_redesign_required():
    _, _, _, _, strategy = evidence(); plan = coherent_plan(strategy)
    for index, shot in enumerate(plan["shots"]):
        shot["camera"] = {"shot_size": ["WS", "CU", "ECU"][index], "angle": f"angle-{index}", "movement": f"move-{index}", "speed": "fast", "camera_side": f"side-{index}"}
        shot["camera_motivation"] = ""
        shot["why_this_shot"] = "specific but omitted"
    result = run_professional_qa(strategy=strategy, shot_plan=plan)
    assert any(item["issue_code"] in {"RANDOM_VARIATION", "SHOT_SIZE_NOISE"} for item in result["findings"])
    assert result["status"] == "PROFESSIONAL_QA_REDESIGN_REQUIRED"


def test_emotion_zigzag_and_scorer_gaming_detection():
    _, _, _, _, strategy = evidence(); plan = coherent_plan(strategy)
    plan["shots"] *= 2
    for index, shot in enumerate(plan["shots"]):
        shot["plan_shot_id"] = f"S{index+1:02d}"; shot["emotion"]["intensity"] = 2 if index % 2 == 0 else 8
        shot["why_this_shot"] = "show the event"; shot["camera"]["movement"] = f"move-{index}"
    result = run_professional_qa(strategy=strategy, shot_plan=plan)
    gaming = detect_scorer_gaming(strategy=strategy, shot_plan=plan)
    assert any(item["issue_code"] == "EMOTION_ZIGZAG" for item in result["findings"])
    assert gaming["gaming_detected"] is True


def test_redesign_protocol_is_interface_only():
    _, _, _, _, strategy = evidence(); plan = coherent_plan(strategy)
    request = build_scene_redesign_request(scene_strategy=strategy, draft_shot_plan=plan, qa_findings=[{"issue_code": "SHOT_SIZE_NOISE"}])
    assert validate_scene_redesign_request(request)["valid"] is True
    assert request["execution_status"] == "interface_only" and request["provider_calls"] == 0


def test_critic_schema_and_provider_free_adapter():
    _, _, _, _, strategy = evidence(); plan = coherent_plan(strategy)
    result = ProviderFreeCriticAdapter().evaluate(strategy=strategy, shot_plan=plan, qa_findings=[])
    assert result["schema_version"] == CREATIVE_CRITIC_SCHEMA_VERSION
    assert validate_director_critic_result(result)["valid"] is True
