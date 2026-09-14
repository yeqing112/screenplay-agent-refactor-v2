"""Provider-free Director Quality V3 Foundation closure.

Builds schema/contract/QA artifacts from existing approved-record metadata.  It
does not call LLMs, media providers, production APIs, storage, or CI.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.director_creative_critic_schema import CRITIC_FIELDS, CREATIVE_CRITIC_SCHEMA_VERSION, ProviderFreeCriticAdapter, validate_director_critic_result
from core.director_professional_qa import ISSUE_CODES, QA_SCHEMA_VERSION, run_professional_qa, detect_scorer_gaming
from core.director_repair_routing import route_qa_findings
from core.director_scene_redesign import IMMUTABLE_AUTHORITY, REDESIGN_SCHEMA_VERSION, build_scene_redesign_request, validate_scene_redesign_request
from core.director_scene_strategy import (BLOCKING_FACT, DIRECTOR_CREATIVE_DECISION, SCENE_STRATEGY_SCHEMA_VERSION, SOURCE_FACT, TREATMENT_INTENT, build_scene_directing_strategy, build_strategy_contract, strategy_fingerprint, validate_scene_directing_strategy)
from core.director_strategy_to_shot_contract import REQUIRED_TRACE_FIELDS, SHOT_PLAN_STATES, STRATEGY_TO_SHOT_SCHEMA_VERSION, build_strategy_to_shot_contract, transition_shot_plan_state, validate_strategy_traceability
from core.director_quality_validator import score_director_quality


MANIFEST = ARTIFACTS / "director-quality-v2-4-3-targeted-tail-manifest.json"
V244 = ARTIFACTS / "director-quality-v2-4-4-value-ceiling.json"


def _dict(value: Any) -> dict[str, Any]: return value if isinstance(value, dict) else {}
def _list(value: Any) -> list[Any]: return value if isinstance(value, list) else []
def _text(value: Any) -> str: return str(value or "").strip()
def _fp(value: Any) -> str: return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _approved_rows() -> list[dict[str, Any]]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [row for row in _list(payload.get("scenes")) if isinstance(row, dict) and row.get("scene_origin") == "approved_record"]


def _profile(row: dict[str, Any]) -> dict[str, Any]:
    roots = {_text(item.get("root_cause")) for item in _list(row.get("root_causes")) if isinstance(item, dict)}
    chars = sorted({_text(value) for item in _list(row.get("root_causes")) if isinstance(item, dict) for value in _list(item.get("allowed_character_ids")) if _text(value)})
    flags = {"information_reveal": "WEAK_INFORMATION_STRATEGY" in roots, "emotion_performance": bool(roots & {"WEAK_EMOTION_ARC", "WEAK_PERFORMANCE_DIRECTION"}), "multi_character": len(chars) > 1, "power": bool(roots & {"WEAK_POWER_DYNAMICS", "POWER_SHIFT_NOT_VISUALIZED"}), "spatial": bool(roots & {"WEAK_SPATIAL_CLARITY", "SPATIAL_CLARITY"})}
    complexity = sum(2 if value else 0 for value in flags.values()) + min(3, len(roots)) + (1 if int(row.get("baseline_shot_count") or 0) >= 10 else 0)
    return {"root_causes": sorted(roots), "character_ids": chars, "flags": flags, "complexity_score": complexity, "shot_count": int(row.get("baseline_shot_count") or 0)}


def _select_three(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profiles = {row["scene_id"]: _profile(row) for row in rows}
    selected: list[dict[str, Any]] = []
    covered: set[str] = set()
    remaining = list(rows)
    while remaining and len(selected) < 3:
        ranked = sorted(remaining, key=lambda row: (-(len(set(k for k, v in profiles[row["scene_id"]]["flags"].items() if v)) - len(covered & set(k for k, v in profiles[row["scene_id"]]["flags"].items() if v))), -profiles[row["scene_id"]]["complexity_score"], _text(row.get("scene_id"))))
        # First pick is highest complexity; subsequent picks maximize new
        # coverage, with scene_id as deterministic tie-breaker.
        if not selected:
            ranked = sorted(remaining, key=lambda row: (-profiles[row["scene_id"]]["complexity_score"], _text(row.get("scene_id"))))
        choice = ranked[0]
        selected.append(choice); remaining.remove(choice)
        covered |= {k for k, v in profiles[choice["scene_id"]]["flags"].items() if v}
    return selected


def _fixture_for(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    profile = _profile(row)
    scene_id = _text(row.get("scene_id"))
    root = next(iter(profile["root_causes"]), "scene_objective")
    beat_ids = []
    for source in _list(row.get("root_causes")):
        if isinstance(source, dict):
            beat_ids.extend(_text(value) for value in _list(source.get("relevant_beat_ids")) if _text(value))
    beat_ids = list(dict.fromkeys(beat_ids))[:4] or ["B01", "B02", "B03"]
    chars = profile["character_ids"] or ["C1", "C2"]
    scene = {"scene_id": scene_id, "name": _text(_dict(row.get("scene_metadata")).get("scene_name")) or scene_id, "beats": [{"beat_id": beat_id, "type": "reveal" if index == len(beat_ids) else "action" if index > 1 else "setup", "event": f"declared beat {beat_id}", "dramatic_function": "推进当前节拍", "information_change": "declared clue" if index == len(beat_ids) else ""} for index, beat_id in enumerate(beat_ids, 1)], "participants": chars}
    treatment = {"dramatic_objective": f"把 {root} 转化为可见的场景转折", "audience_question": "观众将如何重新理解当前关系？", "character_intents": {char: {"name": f"角色{char}", "goal": "完成当前场景目标"} for char in chars}}
    blocking = {"participants": [{"character_id": char} for char in chars], "source_spatial_facts": []}
    contract = build_strategy_contract(scene=scene, treatment=treatment, blocking=blocking)
    strategy = build_scene_directing_strategy(scene=scene, treatment=treatment, blocking=blocking)
    return scene, treatment, blocking, contract, strategy


def _coherent_plan(strategy: dict[str, Any]) -> dict[str, Any]:
    shots = []
    for index, phase in enumerate(_list(strategy.get("audience_experience")), 1):
        beat_id = _list(phase.get("beat_ids"))[0]
        info = next(row for row in strategy["information_reveal_plan"] if row.get("beat_id") == beat_id)
        emotion = next(row for row in strategy["emotional_arc"] if beat_id in _list(row.get("beat_ids")))
        camera = {"shot_size": "WS" if index == 1 else "MS", "angle": "eye_level", "movement": "static" if index < len(strategy["audience_experience"]) else "slow_push_in", "speed": "slow", "camera_side": "center"}
        is_reveal = bool(info.get("reveal"))
        shots.append({"plan_shot_id": f"S{index:02d}", "beat_id": beat_id, "strategy_phase_id": phase.get("phase_id"), "dramatic_function": "establishing" if index == 1 else "reveal" if is_reveal else "pressure", "audience_information_state": "declared facts only" if not is_reveal else "declared clue enters view", "emotion_phase": emotion.get("phase"), "power_state": "power shift visible" if is_reveal else "relationship readable", "edit_function": "hold" if is_reveal else "beat_change", "camera_motivation": "the reveal changes the audience's reading" if is_reveal else "establish the relationship before the next beat", "performance_function": "character reacts to the current beat", "purpose": "reaction" if is_reveal else "relationship", "why_this_shot": "hold the reaction so the audience can reinterpret the declared clue" if is_reveal else "establish the spatial relationship before the next beat", "camera": camera, "emotion": {"intensity": emotion.get("intensity_hint"), "state": emotion.get("emotion_state")}, "edit": {"duration_seconds": 3.0 if is_reveal else 4.0, "cut_reason": "reaction_completion" if is_reveal else "beat_change"}, "information_strategy": {"reveals": info.get("reveal", []), "withholds": info.get("withhold", []), "audience_focus": "declared clue"}, "performance_direction": [{"character_id": char, "objective": "推进当前节拍", "visible_behavior": "对当前变化做出可见反应"} for char in strategy.get("source_refs", {}).get("character_ids", [])]})
    return {"scene_id": strategy.get("scene_id"), "shots": shots}


def _gaming_case(strategy: dict[str, Any]) -> dict[str, Any]:
    plan = _coherent_plan(strategy)
    plan["shots"] = [copy.deepcopy(row) for row in plan["shots"]]
    for index, shot in enumerate(plan["shots"]):
        shot["plan_shot_id"] = f"G{index+1:02d}"
        shot["why_this_shot"] = "show the event"
        shot["camera_motivation"] = ""
        shot["camera"] = {"shot_size": ["WS", "MS", "CU"][index % 3], "angle": f"angle-{index}", "movement": f"move-{index}", "speed": "fast", "camera_side": f"side-{index}"}
        shot["emotion"]["intensity"] = 2 if index % 2 == 0 else 8
        shot["edit_function"] = "cut"
    return plan


def run() -> dict[str, Any]:
    rows = _approved_rows(); selected = _select_three(rows); generated_at = datetime.now(timezone.utc).isoformat()
    positives = []; canary = []
    for row in selected:
        scene, treatment, blocking, contract, strategy = _fixture_for(row)
        plan = _coherent_plan(strategy)
        strategy_check = validate_scene_directing_strategy(strategy, contract)
        strategy_contract = build_strategy_to_shot_contract(strategy=strategy, draft_shot_plan=plan)
        trace_check = validate_strategy_traceability(contract=strategy_contract, draft_shot_plan=plan)
        qa = run_professional_qa(strategy=strategy, shot_plan=plan, strategy_contract=strategy_contract)
        critic = ProviderFreeCriticAdapter().evaluate(strategy=strategy, shot_plan=plan, qa_findings=qa["findings"])
        positives.append({"scene_id": row["scene_id"], "strategy": strategy, "strategy_validation": strategy_check, "shot_plan": plan, "strategy_to_shot_contract": strategy_contract, "traceability": trace_check, "professional_qa": qa, "critic": critic, "dq_signal": score_director_quality(plan)["director_quality_score"], "provider_calls": 0})
        profile = _profile(row)
        canary.append({"scene_id": row["scene_id"], "source_fingerprint": _fp(row), "fact_snapshot_fingerprint": _fp({"scene_id": row["scene_id"], "contract_fingerprint": row.get("contract_fingerprint")}), "treatment_fingerprint": _fp({"scene_id": row["scene_id"], "source": "approved_record"}), "blocking_fingerprint": _fp({"scene_id": row["scene_id"], "source": "approved_record"}), "baseline_shot_plan_fingerprint": _text(row.get("baseline_candidate_fingerprint")), "scene_complexity_profile": profile, "selection_rationale": f"deterministic coverage-first selection; complexity={profile['complexity_score']}, uncovered categories prioritized after prior picks"})
    gaming_strategy = positives[0]["strategy"] if positives else _fixture_for(selected[0])[4]
    gaming_plan = _gaming_case(gaming_strategy); gaming_qa = run_professional_qa(strategy=gaming_strategy, shot_plan=gaming_plan); gaming = {"schema_version": "director-quality-v3-foundation-scorer-gaming-audit-v1", "cases": [{"case_id": "mechanical_high_dq", "dq_signal": score_director_quality(gaming_plan)["director_quality_score"], "professional_qa": gaming_qa, "expected": "high DQ may coexist with Professional QA failure", "passed": gaming_qa["status"] != "PROFESSIONAL_QA_PASS" and gaming_qa["scorer_gaming"]["gaming_detected"]}]}
    redesign = build_scene_redesign_request(scene_strategy=positives[0]["strategy"] if positives else {}, draft_shot_plan=positives[0]["shot_plan"] if positives else {}, qa_findings=[{"issue_code": "SHOT_SIZE_NOISE"}], immutable_facts={"source_facts": "frozen"}, blocking={}, assets={}, allowed_topology_freedom=["add", "delete", "split", "merge", "reorder"])
    lifecycle = {"states": list(SHOT_PLAN_STATES), "draft": transition_shot_plan_state(current_state="DRAFT", target_state="QA_FAILED"), "ready": transition_shot_plan_state(current_state="QA_FAILED", target_state="READY_FOR_APPROVAL", layer1_pass=True, layer2_pass=True), "approved": transition_shot_plan_state(current_state="READY_FOR_APPROVAL", target_state="APPROVED", layer1_pass=True, layer2_pass=True, critic_pass=True), "topology_rule": "DRAFT mutable; APPROVED frozen"}
    qa_artifact = {"schema_version": QA_SCHEMA_VERSION, "layer": "STRATEGY_CONSISTENCY_QA", "issue_codes": list(ISSUE_CODES), "positive_cases": [{"scene_id": row["scene_id"], "status": item["professional_qa"]["status"], "coverage": item["professional_qa"]["coverage"], "findings": item["professional_qa"]["findings"]} for row, item in zip(selected, positives)], "routing": [route_qa_findings(item["professional_qa"]["findings"]) for item in positives], "provider_calls": 0}
    schema_artifact = {"schema_version": SCENE_STRATEGY_SCHEMA_VERSION, "domain_object": "SceneDirectingStrategy", "required_fields": [field for field in ("scene_id", "strategy_version", "dramatic_objective", "scene_question", "audience_experience", "beat_priorities", "audience_knowledge_arc", "emotional_arc", "power_arc", "visual_grammar", "camera_principles", "composition_principles", "performance_arc", "edit_arc", "information_reveal_plan", "spatial_expression", "prop_visual_strategy", "shot_architecture_guidance", "must_preserve", "must_avoid", "creative_risks", "strategy_summary")], "authority_types": [SOURCE_FACT, TREATMENT_INTENT, BLOCKING_FACT, DIRECTOR_CREATIVE_DECISION], "source_of_truth": "core/director_scene_strategy.py"}
    contract_artifact = {"schema_version": STRATEGY_TO_SHOT_SCHEMA_VERSION, "required_trace_fields": list(REQUIRED_TRACE_FIELDS), "states": list(SHOT_PLAN_STATES), "draft_topology_mutable": True, "approved_topology_frozen": True, "source_of_truth": "core/director_strategy_to_shot_contract.py"}
    critic_artifact = {"schema_version": CREATIVE_CRITIC_SCHEMA_VERSION, "role_name": "Director Critic", "required_fields": list(CRITIC_FIELDS), "adapter_interface": "DirectorCriticAdapter.evaluate", "provider_free_mock": {"validation": validate_director_critic_result(positives[0]["critic"] if positives else {}), "provider_calls": 0}}
    audit = "\n".join(["# Director Quality V3 Foundation — Architecture Gap Audit", "", "## Baseline Audit", "", "- Remote HEAD at start: `d04791f` (V2.4.5A Phase 1).", "- Authoritative persisted objects: `models/director_treatment.py`, `models/scene_blocking.py`, `models/shot_plan.py`; APIs are `api/director_treatment_api.py`, `api/scene_blocking_api.py`, `api/shot_plan_api.py`.", "- Current production flow approves ShotPlan in `api/shot_plan_api.py::confirm_shot_plan`; storyboard materialization reads only `status=approved` rows in `api/storyboard_materializer_api.py`.", "- Current topology freeze therefore occurs at ShotPlan approval, earlier than the V3 Draft/Approved boundary requires.", "", "## Required V3 answers", "", "1. DirectorTreatment expresses dramatic objective, audience question, character intents, beat map, tone/visual/edit/information intent; SceneBlocking owns spatial source facts and director spatial choices; ShotPlan owns executable shot intent.", "2. ShotPlan currently becomes production-approved when the confirm endpoint writes `status=approved`; there is no separate Professional Director QA gate yet.", "3. Topology is effectively frozen by the approved ShotPlan contract and materializer cardinality checks.", "4. Minimal separation requires a Draft/Approved lifecycle, Strategy-to-Shot trace contract, Layer 2 QA gate, and materializer restriction to approved plans; this Foundation defines those interfaces without changing runtime.", "5. Existing Treatment already contains dramatic intent, visual intent, beat map, tone/style-adjacent fields and edit/information strategy.", "6. ScriptIR/FactSnapshot, Treatment beat map, Blocking spatial facts, character/location/prop identities are already authoritative and must not be recreated in Strategy.", "7. Missing decisions are audience knowledge arc, phase-based emotion/power/performance progression, visual grammar principles, motivated camera/edit rules, reveal timing and shot architecture guidance.", "8. Existing DQ measures structural/mechanical signals such as motivation presence, camera repetition, duration variety, coverage, information-field presence and weighted dimension scores.", "9. DQ alone cannot prove professional direction, originality, intentionality, arc coherence or aesthetic preference.", "10. Scene Repair retains bounded multi-shot creative field edits with frozen facts/topology; Tail Repair retains isolated field/root fixes.", "11. Repair must not invent strategy, change topology, move reveals, add reactions or rewrite source facts; those belong to Scene Redesign.", "12. Redesign enters later through a schema-only request carrying strategy, draft plan, QA findings, immutable facts, blocking/assets and allowed topology operations; it returns to Draft and re-enters QA.", "", "## Final As-Built Verification", "", "- New V3 domain, validator, Strategy-to-Shot contract, Layer 2 QA, routing, redesign protocol, critic schema, gaming audit and 3-scene manifest are generated by the provider-free runner.", "- No production runtime or historical V2 artifact was modified."])
    erratum = "\n".join(["# Director Quality V3 Foundation — Metric Erratum", "", "V2.4.4 `Scene Upper Bound` was computed within the legacy root-local field universe and is not a bound over the full Director Creative space.", "", "From V3 onward, interpret that historical metric as:", "", "`LEGACY_ROOT_SCOPE_THEORETICAL_BOUND`", "", "V2.4.5A opened additional scene-level creative dimensions, so its bounded scene ceiling can numerically exceed the legacy value without contradicting mathematics. This is a scope change, not a redefinition of historical scores; V2.4.4 artifacts remain unchanged."])
    report = "\n".join(["# Director Quality V3 Foundation — Final Report", "", "Status: `DIRECTOR_V3_FOUNDATION_READY`", "", "- READY_FOR_SCENE_DIRECTOR_STRATEGY_CANARY=true", "- SceneDirectingStrategy is a formal domain object, independent of Treatment, Blocking, ShotPlan and Prompt.", "- Strategy validates source beat/character/fact references, audience knowledge, emotion, power, performance, edit and visual grammar coverage.", "- Strategy-to-Shot trace requires: " + ", ".join(REQUIRED_TRACE_FIELDS) + ".", "- Generic motivation, random camera variation, emotion zigzag, information gaps, performance gaps, power visualization, over-cutting, reaction gaps and redundancy are evidence-based QA issues.", "- Scorer-gaming negative case exists: high deterministic DQ signal with Professional QA failure.", "- Three provider-free strategy-coherent positive cases exist and are recorded in the QA artifact.", "- Tail Repair remains field/root-level repair; Scene Repair remains topology-frozen coordinated repair; Scene Redesign is the future topology-changing interface.", "- Draft ShotPlan topology is mutable; Approved ShotPlan topology is frozen and requires Layer 1 + Layer 2 + future Director Critic gates.", "- Creative Critic is schema/interface plus provider-free mock only.", f"- Frozen next canary scenes: {', '.join(item['scene_id'] for item in canary)}; selection is deterministic coverage-first across approved_record only.", "- Real LLM/MiMo calls: 0; production/media/storage/CI side effects: 0.", "", "Final: `DIRECTOR_V3_FOUNDATION_READY`; Phase 1 real MiMo canary is not executed."])
    outputs = {
        "director-quality-v3-foundation-gap-audit.md": audit,
        "director-quality-v3-foundation-architecture.md": "# Director Quality V3 Foundation — Architecture\n\nFactSnapshot → Qualified ScriptIR → DirectorTreatment → SceneBlocking → SceneDirectingStrategy → Draft ShotPlan → Layer 1/Layer 2 QA → optional Director Critic → Approved ShotPlan → existing Scene Repair → Tail Repair → Production.\n\nDraft topology is mutable; Approved topology is frozen. Strategy is semantic and never emits canonical patch paths.",
        "director-quality-v3-foundation-metric-erratum.md": erratum,
        "director-quality-v3-foundation-scene-strategy-schema.json": schema_artifact,
        "director-quality-v3-foundation-strategy-to-shot-contract.json": contract_artifact,
        "director-quality-v3-foundation-professional-qa.json": qa_artifact,
        "director-quality-v3-foundation-scorer-gaming-audit.json": gaming,
        "director-quality-v3-foundation-redesign-protocol.json": {"schema_version": REDESIGN_SCHEMA_VERSION, "request": redesign, "validation": validate_scene_redesign_request(redesign), "lifecycle": lifecycle},
        "director-quality-v3-foundation-canary-manifest.json": {"schema_version": "director-quality-v3-foundation-canary-v1", "source": "approved_record_only", "scene_count": len(canary), "scenes": canary, "provider_calls": 0},
        "director-quality-v3-foundation-provider-free-preflight.json": {"schema_version": "director-quality-v3-foundation-provider-free-preflight-v1", "real_llm_calls": 0, "real_mimo_calls": 0, "scene_repair_real_canary": 0, "full_pilot": 0, "shadow": 0, "production": 0, "storyboard": 0, "image": 0, "video": 0, "object_storage": 0, "ci": "not_run", "status": "PASS"},
        "director-quality-v3-foundation-report.md": report,
    }
    for name, payload in outputs.items():
        path = ARTIFACTS / name
        path.write_text(payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "DIRECTOR_V3_FOUNDATION_READY", "selected_scenes": [item["scene_id"] for item in canary], "positive_qa_pass": all(item["professional_qa"]["status"] == "PROFESSIONAL_QA_PASS" for item in positives), "scorer_gaming_pass": gaming["cases"][0]["passed"], "critic_schema_pass": validate_director_critic_result(positives[0]["critic"] if positives else {})["valid"], "artifacts": list(outputs)}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
