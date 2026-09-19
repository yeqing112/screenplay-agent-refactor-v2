"""Phase C structured ShotPlan contracts and deterministic compilers.

This module is deliberately provider free.  It turns current Director and
Blocking payloads into an auditable ShotPlan proposal; prose remains a reader
projection and never participates in qualification.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

SHOT_PLAN_CONTRACT_VERSION = "shot_plan_phase_c_v1"
COVERAGE_ROLES = {
    "PRIMARY_BEAT_COVERAGE", "REACTION_COVERAGE", "INSERT_EVIDENCE",
    "RELATIONAL_COVERAGE", "SPATIAL_ORIENTATION", "TRANSITION_COVERAGE",
    "BRIDGE_COVERAGE", "SCENE_EXIT_COVERAGE",
}
PURPOSES = {
    "ESTABLISH_SPACE", "ESTABLISH_RELATIONSHIP", "INTRODUCE_INFORMATION",
    "REVEAL_INFORMATION", "WITHHOLD_INFORMATION", "REDIRECT_ATTENTION",
    "CAPTURE_REACTION", "ESCALATE_THREAT", "SHIFT_POWER", "CONFIRM_EVIDENCE",
    "FOLLOW_ACTION", "ISOLATE_CHARACTER", "CONNECT_CHARACTERS",
    "SHOW_SPATIAL_RELATION", "SHOW_PROP_STATE", "BRIDGE_BEATS", "SCENE_EXIT",
}
FRAMINGS = {"EXTREME_WIDE", "WIDE", "MEDIUM_WIDE", "MEDIUM", "MEDIUM_CLOSE", "CLOSE", "EXTREME_CLOSE", "INSERT", "OVER_SHOULDER", "TWO_SHOT", "GROUP_SHOT", "POV"}
MOVEMENTS = {"NONE", "PAN", "TILT", "DOLLY_IN", "DOLLY_OUT", "TRACK", "ARC", "HANDHELD_FOLLOW", "REFRAME"}
INFORMATION_VISIBILITY = {"AUDIENCE_ONLY", "CHARACTER_AND_AUDIENCE", "SPECIFIC_CHARACTER_AND_AUDIENCE", "WITHHELD", "AMBIGUOUS", "AUDIENCE_OBSERVES_CHARACTER_DOUBT"}
INFORMATION_DELTA_FIELDS = ("knowledge_added", "knowledge_confirmed", "knowledge_invalidated", "belief_shift", "open_question_added", "open_question_resolved")

def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode()).hexdigest()

def _beats(treatment: dict[str, Any]) -> list[dict[str, Any]]:
    return [b for b in treatment.get("beat_map", []) if isinstance(b, dict) and str(b.get("beat_id") or "").strip()]

def _decisions(treatment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = treatment.get("director_beat_decisions") or treatment.get("director_decisions") or []
    if isinstance(raw, dict):
        raw = raw.get("director_beat_decisions") or raw.get("decisions") or []
    return {str(d.get("beat_ref") or d.get("beat_id")): d for d in raw if isinstance(d, dict) and str(d.get("beat_ref") or d.get("beat_id") or "").strip()}

def _blocking_state(blocking: dict[str, Any], beat_id: str) -> dict[str, Any]:
    for key in ("beat_spatial_states", "states", "blocking_states"):
        for state in blocking.get(key, []) if isinstance(blocking.get(key), list) else []:
            if isinstance(state, dict) and str(state.get("beat_ref") or state.get("beat_id") or "") == beat_id:
                characters = state.get("characters") or state.get("subject_zones") or {}
                zones = {str(k): (v.get("zone") if isinstance(v, dict) else v) for k, v in characters.items()} if isinstance(characters, dict) else {}
                return {**state, "state_ref": str(state.get("state_ref") or beat_id), "subject_zones": zones, "prop_states": state.get("props") if isinstance(state.get("props"), dict) else {}}
    participants = blocking.get("participants") if isinstance(blocking.get("participants"), list) else []
    zones = {str(p.get("character_id")): p.get("start_position", p.get("position")) for p in participants if isinstance(p, dict) and p.get("character_id")}
    return {"state_ref": beat_id, "subject_zones": zones, "prop_states": {}, "source": "current_scene_blocking"}

def _changed_props(blocking: dict[str, Any], beat_id: str) -> list[str]:
    """Materialize prop evidence only from BlockingState transitions."""
    states = []
    for item in blocking.get("beat_spatial_states", []) if isinstance(blocking.get("beat_spatial_states"), list) else []:
        if isinstance(item, dict): states.append(item)
    prior = {}
    current = {}
    for item in states:
        props = item.get("props") if isinstance(item.get("props"), dict) else {}
        if str(item.get("beat_ref")) == beat_id: current = props; break
        prior = {str(k): (v.get("state") if isinstance(v, dict) else v) for k, v in props.items()}
    now = {str(k): (v.get("state") if isinstance(v, dict) else v) for k, v in current.items()}
    return sorted(k for k, value in now.items() if prior.get(k) != value and value not in (None, "", "ABSENT"))

def _interaction_axes(blocking: dict[str, Any]) -> list[dict[str, Any]]:
    raw = blocking.get("interaction_axes")
    if not isinstance(raw, list):
        raw = blocking.get("camera_axis") if isinstance(blocking.get("camera_axis"), list) else []
    return [a for a in raw if isinstance(a, dict) and str(a.get("axis_id") or a.get("axis_ref") or "").strip()]

def _axis_refs_for_beat(*, beat: dict[str, Any], blocking: dict[str, Any]) -> list[str]:
    beat_id = str(beat.get("beat_id") or "")
    subjects = {str(x) for x in (beat.get("characters") or beat.get("participants") or [])}
    refs = []
    for axis in _interaction_axes(blocking):
        axis_id = str(axis.get("axis_id") or axis.get("axis_ref") or "")
        established = str(axis.get("established_at_beat") or "")
        axis_subjects = {str(x) for x in (axis.get("subjects") or axis.get("participants") or [])}
        if established == beat_id or (axis_subjects and subjects & axis_subjects and (not established or beat_id >= established)):
            refs.append(axis_id)
    return sorted(set(refs))

def _reaction_refs(decision: dict[str, Any], beat_id: str) -> list[dict[str, Any]]:
    refs = []
    for reaction in decision.get("reaction_contracts", []) if isinstance(decision.get("reaction_contracts"), list) else []:
        if not isinstance(reaction, dict):
            continue
        character = str(reaction.get("character_ref") or reaction.get("character_id") or "")
        refs.append({"reaction_contract_ref": str(reaction.get("contract_id") or f"RC_{beat_id}_{character}"), "character_ref": character, "reaction_type": str(reaction.get("reaction_type") or ""), "required": bool(reaction.get("required", True))})
    return refs

def compile_information_requirements(*, treatment: dict[str, Any]) -> list[dict[str, Any]]:
    """Project stable information obligations from structured Phase B deltas."""
    result: list[dict[str, Any]] = []
    for beat in _beats(treatment):
        beat_id = str(beat["beat_id"])
        decision = _decisions(treatment).get(beat_id, {})
        delta = decision.get("audience_state_delta") if isinstance(decision.get("audience_state_delta"), dict) else {}
        ordinal = 0
        for field in INFORMATION_DELTA_FIELDS:
            values = delta.get(field) if isinstance(delta.get(field), list) else []
            for value in values:
                content = str(value or "").strip()
                if not content:
                    continue
                ordinal += 1
                result.append({
                    "information_ref": f"INFO_{beat_id.replace('-', '_')}_{ordinal:03d}",
                    "content": content,
                    "source_ref": str(decision.get("decision_id") or beat_id),
                    "source_field": f"audience_state_delta.{field}",
                    "beat_ref": beat_id,
                })
    return result

def build_shot_requirements(*, treatment: dict[str, Any], blocking: dict[str, Any], script_authority: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compile deterministic obligations only; this function never authors a shot."""
    decisions = _decisions(treatment)
    information_by_beat: dict[str, list[dict[str, Any]]] = {}
    for item in compile_information_requirements(treatment=treatment):
        information_by_beat.setdefault(str(item["beat_ref"]), []).append(item)
    requirements = []
    beats = _beats(treatment)
    for index, beat in enumerate(beats):
        beat_id = str(beat["beat_id"])
        decision = decisions.get(beat_id, {})
        reaction_refs = _reaction_refs(decision, beat_id)
        prop_refs = list(beat.get("prop_refs") or beat.get("critical_prop_refs") or []) or _changed_props(blocking, beat_id)
        axis_refs = _axis_refs_for_beat(beat=beat, blocking=blocking)
        required_coverages = ["PRIMARY_BEAT_COVERAGE"]
        if any(r["required"] for r in reaction_refs) or beat.get("requires_reaction") or beat.get("reaction_required"):
            required_coverages.append("REACTION_COVERAGE")
        if prop_refs or str(beat.get("beat_type") or beat.get("type") or "").upper() in {"PROP", "EVIDENCE"}:
            required_coverages.append("INSERT_EVIDENCE")
        if index == len(beats) - 1:
            required_coverages.append("SCENE_EXIT_COVERAGE")
        information = information_by_beat.get(beat_id, [])
        requirements.append({"requirement_id": f"REQ_{beat_id}", "beat_refs": [beat_id], "director_decision_refs": [str(decision.get("decision_id"))] if decision.get("decision_id") else [], "required_coverages": sorted(set(required_coverages)), "required_subjects": sorted({str(x) for x in (beat.get("characters") or beat.get("participants") or []) if str(x).strip()}), "reaction_contracts": reaction_refs, "reaction_contract_refs": [x["reaction_contract_ref"] for x in reaction_refs], "blocking_state_refs": [beat_id], "required_axis_refs": axis_refs, "required_prop_refs": sorted({str(x) for x in prop_refs if str(x).strip()}), "required_information": information, "required_information_refs": [x["information_ref"] for x in information], "information_requirements": [x["content"] for x in information]})
    return {"contract_version": SHOT_PLAN_CONTRACT_VERSION, "requirements": requirements, "coverage_contracts": requirements, "continuity_constraints": [{"requirement_ref": r["requirement_id"], "axis_refs": r["required_axis_refs"], "blocking_state_refs": r["blocking_state_refs"]} for r in requirements], "axis_constraints": [{"axis_ref": axis, "policy": "PRESERVE_UNLESS_MOTIVATED_CROSS"} for axis in sorted({a for r in requirements for a in r["required_axis_refs"]})], "source_lineage": script_authority or {}, "provider_provenance": {"origin": "REQUIREMENTS_COMPILER", "provider_calls": 0}}

def build_phase_c_contract(*, requirements: dict[str, Any], coverage_results: list[dict[str, Any]] | None = None, compiled_continuity: dict[str, Any] | None = None, runtime_projection: dict[str, Any] | None = None, authoring_provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    """Metadata only.  Canonical shots are intentionally absent."""
    contract = {"contract_version": requirements.get("contract_version", SHOT_PLAN_CONTRACT_VERSION), "requirements": requirements.get("requirements", []), "coverage_results": coverage_results or [], "compiled_continuity": compiled_continuity or {}, "runtime_projection": runtime_projection or {"status": "AUTHORING_DERIVED_OR_PENDING"}, "source_lineage": requirements.get("source_lineage", {}), "authoring_provenance": authoring_provenance or {}}
    contract["payload_hash"] = _hash(contract)
    return contract

def build_beat_coverage_contracts(*, treatment: dict[str, Any], blocking: dict[str, Any]) -> list[dict[str, Any]]:
    """Project objective coverage requirements from upstream semantics only."""
    result = []
    information_by_beat: dict[str, list[dict[str, Any]]] = {}
    for item in compile_information_requirements(treatment=treatment):
        information_by_beat.setdefault(str(item["beat_ref"]), []).append(item)
    for beat in _beats(treatment):
        bid = str(beat["beat_id"])
        typ = str(beat.get("beat_type") or beat.get("type") or "").upper()
        decision = _decisions(treatment).get(bid, {})
        required = ["PRIMARY_BEAT_COVERAGE"]
        reaction_contracts = decision.get("reaction_contracts") if isinstance(decision.get("reaction_contracts"), list) else []
        if reaction_contracts or beat.get("requires_reaction") or beat.get("reaction_contract") or beat.get("reaction_required"):
            required.append("REACTION_COVERAGE")
        prop_refs = list(beat.get("prop_refs") or beat.get("critical_prop_refs") or [])
        if not prop_refs:
            prop_refs = _changed_props(blocking, bid)
        if typ in {"PROP", "EVIDENCE"} or prop_refs:
            required.append("INSERT_EVIDENCE")
        if bid == _beats(treatment)[-1]["beat_id"]:
            required.append("SCENE_EXIT_COVERAGE")
        information = information_by_beat.get(bid, [])
        result.append({"beat_ref": bid, "required_coverages": sorted(set(required)), "required_subjects": sorted({str(x) for x in (beat.get("characters") or beat.get("participants") or []) if str(x).strip()}), "reaction_contract_refs": [str(x.get("contract_id") or x.get("state_delta_ref") or x.get("trigger_ref")) for x in reaction_contracts if isinstance(x, dict)] or ([str(beat.get("reaction_contract"))] if beat.get("reaction_contract") else []), "required_prop_refs": sorted({str(x) for x in prop_refs if str(x).strip()}), "required_information": information, "required_information_refs": [x["information_ref"] for x in information]})
    return result

def compile_shot_coverage(*, treatment: dict[str, Any], blocking: dict[str, Any], shots: list[dict[str, Any]], contracts: list[dict[str, Any]] | None = None, requirements: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    contracts = requirements or contracts or build_beat_coverage_contracts(treatment=treatment, blocking=blocking)
    out = []
    for contract in contracts:
        satisfied = {role: [] for role in contract["required_coverages"]}
        reaction_results = []
        prop_results = []
        subject_results = []
        state_results = []
        axis_results = []
        information_results = []
        required_information = contract.get("required_information") if isinstance(contract.get("required_information"), list) else []
        required_information_refs = [str(x.get("information_ref")) for x in required_information if isinstance(x, dict) and x.get("information_ref")]
        if not required_information_refs:
            required_information_refs = [str(x) for x in contract.get("required_information_refs", []) if str(x).strip()]
        for shot in shots:
            beat_refs = [str(x) for x in shot.get("beat_refs", [])]
            requirement_beats = [str(x) for x in contract.get("beat_refs", [contract.get("beat_ref")]) if x]
            if set(requirement_beats) & set(beat_refs):
                for role in shot.get("coverage_roles", []):
                    if role in satisfied: satisfied[role].append(str(shot.get("plan_shot_id") or shot.get("shot_id") or ""))
                shot_subjects = set(map(str, shot.get("subjects") or ([shot.get("dramatic_payload", {}).get("primary_subject")] + shot.get("dramatic_payload", {}).get("secondary_subjects", []))))
                shot_identity = str(shot.get("plan_shot_id") or shot.get("shot_id") or "")
                subject_results.append({"shot_id": shot_identity, "subjects": sorted(shot_subjects)})
                binding = shot.get("spatial_binding") if isinstance(shot.get("spatial_binding"), dict) else {}
                declared_states = set(map(str, binding.get("blocking_state_refs") or ([binding.get("blocking_state_ref")] if binding.get("blocking_state_ref") else [])))
                if set(contract.get("blocking_state_refs", [])) <= declared_states: state_results.append(shot_identity)
                axis = shot.get("axis_contract") if isinstance(shot.get("axis_contract"), dict) else shot.get("continuity_contract", {})
                declared_axes = set(map(str, axis.get("axis_refs", []))) | ({str(axis.get("axis_ref"))} if axis.get("axis_ref") else set())
                if not contract.get("required_axis_refs") or set(contract.get("required_axis_refs", [])) <= declared_axes: axis_results.append(shot_identity)
                declared_information = set(map(str, shot.get("information_refs", [])))
                if not required_information_refs and shot.get("information_visibility") in INFORMATION_VISIBILITY:
                    information_results.append({"information_ref": None, "satisfied_by": [shot_identity], "visibility": [shot.get("information_visibility")], "complete": True})
                for information_ref in required_information_refs:
                    if information_ref in declared_information and shot.get("information_visibility") in INFORMATION_VISIBILITY:
                        information_results.append({"information_ref": information_ref, "satisfied_by": [shot_identity], "visibility": [shot.get("information_visibility")], "complete": True})
                for reaction in contract.get("reaction_contracts", []):
                    if "REACTION_COVERAGE" in shot.get("coverage_roles", []) and reaction.get("character_ref") in shot_subjects and str(reaction.get("reaction_contract_ref")) in set(map(str, shot.get("reaction_contract_refs", []))):
                        reaction_results.append({"reaction_contract_ref": reaction["reaction_contract_ref"], "satisfied_by": [shot_identity], "complete": True})
                if "INSERT_EVIDENCE" in shot.get("coverage_roles", []):
                    shot_props = set(map(str, binding.get("prop_refs", [])))
                    for prop in contract.get("required_prop_refs", []):
                        if prop in shot_props: prop_results.append({"prop_ref": prop, "satisfied_by": [shot_identity], "complete": True})
        required_subjects = set(map(str, contract.get("required_subjects", [])))
        covered_subjects = set(x for item in subject_results for x in item["subjects"])
        semantic_roles = all(satisfied.values())
        reaction_complete = all(any(x["reaction_contract_ref"] == ref and x["complete"] for x in reaction_results) for ref in contract.get("reaction_contract_refs", []))
        props_complete = all(any(x["prop_ref"] == ref and x["complete"] for x in prop_results) for ref in contract.get("required_prop_refs", []))
        for information_ref in required_information_refs:
            if not any(x.get("information_ref") == information_ref and x.get("complete") for x in information_results):
                information_results.append({"information_ref": information_ref, "satisfied_by": [], "visibility": [], "complete": False})
        information_complete = all(any(x.get("information_ref") == ref and x.get("complete") for x in information_results) for ref in required_information_refs)
        complete = semantic_roles and required_subjects <= covered_subjects and reaction_complete and props_complete and bool(state_results or not contract.get("blocking_state_refs")) and bool(axis_results or not contract.get("required_axis_refs")) and information_complete
        out.append({"requirement_ref": contract.get("requirement_id", contract.get("beat_ref")), "beat_ref": contract.get("beat_ref") or (contract.get("beat_refs") or [""])[0], "required": contract["required_coverages"], "satisfied_by": satisfied, "reaction_results": reaction_results, "prop_results": prop_results, "required_subjects": sorted(required_subjects), "covered_subjects": sorted(covered_subjects), "blocking_state_satisfied_by": state_results, "axis_satisfied_by": axis_results, "information_results": information_results, "information_satisfied_by": [x["satisfied_by"][0] for x in information_results if x.get("complete")], "required_information_refs": required_information_refs, "complete": complete})
    return out

def compile_shot_continuity(*, shots: list[dict[str, Any]], blocking: dict[str, Any]) -> dict[str, Any]:
    axes = {str(a.get("axis_id") or a.get("axis_ref")) for a in _interaction_axes(blocking)}
    compiled = []
    errors = []
    previous = None
    for shot in shots:
        c = shot.get("axis_contract") or shot.get("continuity_contract") or {}
        sid = str(shot.get("plan_shot_id") or shot.get("shot_id") or "")
        axis_ref = str(c.get("axis_ref") or "")
        row = {"shot_id": sid, "axis_ref": axis_ref, "axis_policy": c.get("axis_policy", "PRESERVE"), "screen_side_assignments": c.get("screen_side_assignments", {}), "look_direction": c.get("look_direction", {}), "blocking_state_refs": (shot.get("spatial_binding") or {}).get("blocking_state_refs", [])}
        if axis_ref and axis_ref not in axes and c.get("axis_applicability") != "NOT_APPLICABLE":
            row["error"] = "SHOT_AXIS_REF_INVALID"; errors.append({"code": "SHOT_AXIS_REF_INVALID", "shot_id": sid})
        if previous and axis_ref == previous.get("axis_ref") and c.get("axis_policy") != "MOTIVATED_CROSS":
            if row.get("screen_side_assignments") != previous.get("screen_side_assignments"):
                row["error"] = "SHOT_AXIS_CONTINUITY_INVALID"; errors.append({"code": "SHOT_AXIS_CONTINUITY_INVALID", "shot_id": sid, "previous_shot_id": compiled[-1]["shot_id"]})
            if row.get("look_direction") != previous.get("look_direction"):
                row["error"] = "SHOT_LOOK_DIRECTION_CONTINUITY_INVALID"; errors.append({"code": "SHOT_LOOK_DIRECTION_CONTINUITY_INVALID", "shot_id": sid, "previous_shot_id": compiled[-1]["shot_id"]})
        compiled.append(row)
        previous = c
    result = {"compiler_version": "shot_continuity_compiler_v2", "shots": compiled, "errors": errors, "valid": not errors}
    result["continuity_hash"] = _hash(result)
    return result

def estimate_runtime(*, shots: list[dict[str, Any]]) -> dict[str, Any]:
    total = round(sum(float(s.get("estimated_duration_ms") or 0) for s in shots), 2)
    return {"estimator_version": "duration_estimator_v1", "shot_count": len(shots), "estimated_duration_ms": total, "estimated_duration_seconds": round(total / 1000, 2)}

def validate_shot_design(*, shots: list[dict[str, Any]], requirements: dict[str, Any], treatment: dict[str, Any], blocking: dict[str, Any], authoring_provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate an authored canonical ShotDesignDecision array."""
    errors: list[dict[str, Any]] = []
    requirements_list = requirements.get("requirements", []) if isinstance(requirements, dict) else []
    req_by_id = {str(r.get("requirement_id")): r for r in requirements_list if isinstance(r, dict)}
    axes = {str(a.get("axis_id") or a.get("axis_ref")) for a in _interaction_axes(blocking)}
    ids = [str(s.get("plan_shot_id") or "") for s in shots if isinstance(s, dict)]
    if not ids or len(ids) != len(set(ids)) or any(not x for x in ids): errors.append({"code": "SHOT_ID_INVALID"})
    provenance = authoring_provenance or {}
    origin = str(provenance.get("proposal_origin") or provenance.get("origin") or "")
    if origin not in {"HUMAN_INPUT", "PROVIDER_PROPOSAL", "IMPORTED_REVIEWED_PROPOSAL", "GENERATED_DRAFT"} or (origin == "GENERATED_DRAFT" and not provenance.get("confirmed")):
        errors.append({"code": "SHOT_AUTHORING_PROVENANCE_INVALID"})
    provider = provenance.get("provider") if isinstance(provenance.get("provider"), dict) else {}
    if origin == "PROVIDER_PROPOSAL" and (not provider.get("called") or int(provider.get("calls", 0) or 0) <= 0):
        errors.append({"code": "SHOT_AUTHORING_PROVENANCE_INVALID", "reason": "PROVIDER_PROPOSAL_REQUIRES_PROVIDER_CALL"})
    expected_canonical = {"HUMAN_INPUT": "HUMAN_AUTHORED", "GENERATED_DRAFT": "HUMAN_AUTHORED", "PROVIDER_PROPOSAL": "PROVIDER_PROPOSAL_CONFIRMED", "IMPORTED_REVIEWED_PROPOSAL": "IMPORTED_REVIEWED_CONFIRMED"}.get(origin)
    declared_canonical = str(provenance.get("canonical_origin") or "")
    if declared_canonical and declared_canonical != expected_canonical:
        errors.append({"code": "SHOT_AUTHORING_PROVENANCE_INVALID", "reason": "CANONICAL_ORIGIN_TRANSITION_INVALID"})
    for shot in shots:
        if not isinstance(shot, dict): errors.append({"code": "SHOT_SCHEMA_INVALID"}); continue
        sid = str(shot.get("plan_shot_id") or "")
        refs = [str(x) for x in shot.get("requirement_refs", [])]
        if not refs or any(ref not in req_by_id for ref in refs): errors.append({"code": "SHOT_REQUIREMENT_REF_INVALID", "shot_id": sid})
        if not shot.get("beat_refs"): errors.append({"code": "SHOT_BEAT_REF_INVALID", "shot_id": sid})
        if not isinstance(shot.get("director_decision_refs"), list): errors.append({"code": "SHOT_DIRECTOR_DECISION_REF_INVALID", "shot_id": sid})
        if shot.get("shot_purpose") not in PURPOSES or not set(shot.get("coverage_roles", [])) <= COVERAGE_ROLES: errors.append({"code": "SHOT_SCHEMA_INVALID", "shot_id": sid})
        subjects = shot.get("subjects") if isinstance(shot.get("subjects"), list) else []
        camera = shot.get("camera_state") if isinstance(shot.get("camera_state"), dict) else {}
        if camera.get("framing_class") not in FRAMINGS or camera.get("movement") not in MOVEMENTS or not camera.get("orientation"): errors.append({"code": "SHOT_CAMERA_STATE_INCOMPLETE", "shot_id": sid})
        if camera.get("movement") != "NONE" and not all(camera.get(x) for x in ("movement_trigger", "movement_target", "movement_end_condition")): errors.append({"code": "SHOT_CAMERA_MOVEMENT_INCOMPLETE", "shot_id": sid})
        if shot.get("continuous_take") is not True or shot.get("cut_events") not in ([], None): errors.append({"code": "SHOT_INTERNAL_CUT_INVALID", "shot_id": sid})
        binding = shot.get("spatial_binding") if isinstance(shot.get("spatial_binding"), dict) else {}
        states = set(map(str, binding.get("blocking_state_refs", [])))
        axis = shot.get("axis_contract") if isinstance(shot.get("axis_contract"), dict) else {}
        if axis.get("axis_applicability") != "NOT_APPLICABLE":
            axis_ref = str(axis.get("axis_ref") or "")
            declared_axes = set(map(str, axis.get("axis_refs", []))) | ({axis_ref} if axis_ref else set())
            if not declared_axes or not declared_axes <= axes: errors.append({"code": "SHOT_AXIS_REF_INVALID", "shot_id": sid})
            if axis.get("axis_policy") == "MOTIVATED_CROSS" and (not axis.get("cross_motivation") or not axis.get("reorientation_strategy")): errors.append({"code": "SHOT_AXIS_CROSS_INVALID", "shot_id": sid})
            if axis_ref == "AXIS_UNSPECIFIED": errors.append({"code": "SHOT_AXIS_REF_INVALID", "shot_id": sid})
        if not states or not set(map(str, binding.get("subject_zones", {}).keys())).issuperset(set(map(str, subjects))): errors.append({"code": "SHOT_SPATIAL_BINDING_INVALID", "shot_id": sid})
        if shot.get("information_visibility") not in INFORMATION_VISIBILITY: errors.append({"code": "SHOT_INFORMATION_VISIBILITY_INVALID", "shot_id": sid})
    coverage = compile_shot_coverage(treatment=treatment, blocking=blocking, shots=shots, requirements=requirements_list)
    errors.extend({"code": "SHOT_COVERAGE_INCOMPLETE", "requirement_ref": item.get("requirement_ref")} for item in coverage if not item.get("complete"))
    for item in coverage:
        for information in item.get("information_results", []):
            if not information.get("complete"):
                errors.append({"code": "SHOT_INFORMATION_COVERAGE_MISSING", "requirement_ref": item.get("requirement_ref"), "information_ref": information.get("information_ref")})
    continuity = compile_shot_continuity(shots=shots, blocking=blocking)
    if not continuity.get("valid"):
        errors.extend(dict(error) for error in continuity.get("errors", []))
    return {"valid": not errors, "errors": errors, "coverage": coverage, "continuity": continuity, "phase_c_semantic_ready": not errors}

def validate_shot_plan_contract(*, plan: dict[str, Any], treatment: dict[str, Any], blocking: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    shots = plan.get("shots") if isinstance(plan.get("shots"), list) else []
    ids = [str(s.get("shot_id") or "") for s in shots if isinstance(s, dict)]
    if len(ids) != len(set(ids)) or any(not x for x in ids): errors.append({"code": "SHOT_ID_INVALID"})
    beat_ids = {str(b["beat_id"]) for b in _beats(treatment)}
    ordered_beats = [str(b["beat_id"]) for b in _beats(treatment)]
    decision_ids = {str(d.get("decision_id")) for d in _decisions(treatment).values() if d.get("decision_id")}
    for shot in shots:
        if not isinstance(shot, dict): errors.append({"code": "SHOT_SCHEMA_INVALID"}); continue
        if not set(map(str, shot.get("beat_refs", []))) <= beat_ids: errors.append({"code": "SHOT_BEAT_REF_INVALID", "shot_id": shot.get("shot_id")})
        if any(str(ref) not in decision_ids for ref in shot.get("director_decision_refs", [])):
            errors.append({"code": "SHOT_DIRECTOR_DECISION_REF_INVALID", "shot_id": shot.get("shot_id")})
        if shot.get("shot_purpose") not in PURPOSES: errors.append({"code": "SHOT_PURPOSE_INVALID", "shot_id": shot.get("shot_id")})
        if not set(shot.get("coverage_roles", [])) <= COVERAGE_ROLES: errors.append({"code": "SHOT_COVERAGE_ROLE_INVALID"})
        camera = shot.get("camera_state") or {}
        if camera.get("framing_class") not in FRAMINGS or camera.get("movement") not in MOVEMENTS or not camera.get("orientation"): errors.append({"code": "SHOT_CAMERA_STATE_INCOMPLETE", "shot_id": shot.get("shot_id")})
        if camera.get("movement") != "NONE" and not all(camera.get(k) for k in ("movement_trigger", "movement_target", "movement_end_condition")): errors.append({"code": "SHOT_CAMERA_MOVEMENT_INCOMPLETE"})
        if len(shot.get("camera_segments", [1])) != 1: errors.append({"code": "SHOT_INTERNAL_CUT_INVALID", "shot_id": shot.get("shot_id")})
        binding = shot.get("spatial_binding") or {}
        state = _blocking_state(blocking, str((shot.get("beat_refs") or [""])[0]))
        first_beat_ref = str((shot.get("beat_refs") or [""])[0])
        if first_beat_ref not in beat_ids or str(binding.get("blocking_state_ref") or "") != str(state.get("state_ref") or first_beat_ref):
            errors.append({"code": "SHOT_BLOCKING_STATE_REF_INVALID", "shot_id": shot.get("shot_id")})
        expected_zones = state.get("subject_zones") if isinstance(state, dict) else None
        actual_zones = binding.get("subject_zones") if isinstance(binding.get("subject_zones"), dict) else {}
        if isinstance(expected_zones, dict) and expected_zones and actual_zones != expected_zones:
            errors.append({"code": "SHOT_SPATIAL_BINDING_INVALID", "shot_id": shot.get("shot_id")})
        declared_axis = (shot.get("continuity_contract") or {}).get("axis_ref")
        if not declared_axis:
            errors.append({"code": "SHOT_AXIS_CONTRACT_INVALID", "shot_id": shot.get("shot_id")})
        if not set((binding.get("prop_refs") or [])) <= set((state.get("prop_states") or {}).keys()):
            errors.append({"code": "SHOT_PROP_REF_INVALID", "shot_id": shot.get("shot_id")})
    flattened = [str(ref) for shot in shots for ref in (shot.get("beat_refs") or []) if str(ref) in beat_ids]
    if flattened != sorted(flattened, key=ordered_beats.index):
        errors.append({"code": "SHOT_BEAT_ORDER_INVALID"})
    coverage = compile_shot_coverage(treatment=treatment, blocking=blocking, shots=shots)
    for item in coverage:
        if not item["complete"]: errors.append({"code": "SHOT_COVERAGE_INCOMPLETE", "beat_ref": item["beat_ref"]})
    return {"valid": not errors, "errors": errors, "coverage": coverage}

def build_phase_c_shot_plan(*, treatment: dict[str, Any], blocking: dict[str, Any], script_authority: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a deterministic, full-scene proposal from current Phase B inputs."""
    contracts = build_beat_coverage_contracts(treatment=treatment, blocking=blocking)
    shots = []
    for i, beat in enumerate(_beats(treatment), 1):
        bid, event = str(beat["beat_id"]), str(beat.get("event") or "")
        decision = _decisions(treatment).get(bid, {})
        roles = ["PRIMARY_BEAT_COVERAGE"]
        if "REACTION_COVERAGE" in next(c["required_coverages"] for c in contracts if c["beat_ref"] == bid): roles.append("REACTION_COVERAGE")
        contract = next(c for c in contracts if c["beat_ref"] == bid)
        if "INSERT_EVIDENCE" in contract["required_coverages"]: roles.append("INSERT_EVIDENCE")
        if i == len(_beats(treatment)): roles.append("SCENE_EXIT_COVERAGE")
        state = _blocking_state(blocking, bid)
        subjects = [str(x) for x in (beat.get("characters") or beat.get("participants") or []) if str(x).strip()]
        framing = "INSERT" if "INSERT_EVIDENCE" in roles else ("MEDIUM_CLOSE" if "REACTION_COVERAGE" in roles else "MEDIUM")
        purpose_map = {"INTRODUCE_ANOMALY": "REVEAL_INFORMATION", "CONFIRM_EVIDENCE": "CONFIRM_EVIDENCE", "ESCALATE_THREAT": "ESCALATE_THREAT", "SHIFT_POWER": "SHIFT_POWER", "HOOK_NEXT_SCENE": "SCENE_EXIT", "RAISE_SUSPICION": "WITHHOLD_INFORMATION", "TRIGGER_DECISION": "REDIRECT_ATTENTION", "SETUP_RELATIONSHIP": "ESTABLISH_RELATIONSHIP"}
        decision_id = str(decision.get("decision_id") or "")
        shot = {"shot_id": f"SH_{str(treatment.get('scene_id') or blocking.get('scene_id') or 'SCENE').replace('-', '_')}_{i:03d}", "scene_id": str(treatment.get("scene_id") or blocking.get("scene_id") or ""), "beat_refs": [bid], "director_decision_refs": [decision_id] if decision_id else [], "shot_purpose": "SCENE_EXIT" if i == len(_beats(treatment)) else purpose_map.get(str(decision.get("dramatic_purpose") or ""), "FOLLOW_ACTION"), "coverage_roles": roles, "dramatic_payload": {"primary_subject": subjects[0] if subjects else "", "secondary_subjects": subjects[1:], "information_delivered": [str(x) for x in (decision.get("audience_state_delta") or {}).get("knowledge_added", [])] if isinstance(decision.get("audience_state_delta"), dict) else [], "reaction_required": [str(x.get("character_ref")) for x in (decision.get("reaction_contracts") or []) if isinstance(x, dict) and x.get("character_ref")]}, "spatial_binding": {"blocking_state_ref": state.get("state_ref", bid), "subject_zones": state.get("subject_zones", {}), "prop_refs": contract.get("required_prop_refs", [])}, "information_visibility": "CHARACTER_AND_AUDIENCE", "camera_state": {"framing_class": framing, "orientation": "EYE_LEVEL", "support": "STATIC", "movement": "NONE", "subject_binding": subjects}, "continuity_contract": {"axis_ref": str(blocking.get("interaction_axis") or blocking.get("axis_ref") or "AXIS_UNSPECIFIED"), "axis_policy": "PRESERVE", "blocking_state_ref": state.get("state_ref", bid), "screen_direction_state": {}, "prop_refs": contract.get("required_prop_refs", [])}, "temporal_intent": {"duration_mode": "REACTION_HOLD" if "REACTION_COVERAGE" in roles else "ACTION_COMPLETION", "cut_trigger": event}, "camera_segments": [{"camera_state": "single_continuous_take"}], "estimated_duration_ms": int(max(1000, float(beat.get("duration_seconds") or 3) * 1000)), "shot_description": event}
        shots.append(shot)
    coverage = compile_shot_coverage(treatment=treatment, blocking=blocking, shots=shots, contracts=contracts)
    continuity = compile_shot_continuity(shots=shots, blocking=blocking)
    runtime = estimate_runtime(shots=shots)
    plan = {"contract_version": SHOT_PLAN_CONTRACT_VERSION, "scene_id": treatment.get("scene_id") or blocking.get("scene_id") or "", "shots": shots, "coverage_contracts": contracts, "coverage_results": coverage, "compiled_continuity": continuity, "runtime_estimate": runtime, "phase_c_semantic_ready": all(x["complete"] for x in coverage), "source_lineage": script_authority or {}, "provider_provenance": {"origin": "DETERMINISTIC_BUILDER", "provider_calls": 0}}
    plan["payload_hash"] = _hash(plan)
    return plan
