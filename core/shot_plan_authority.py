"""Production authority contract for ShotPlan.

The module is provider-free.  It binds a deterministic ShotPlan candidate to
the current ScriptIR, DirectorTreatment and SceneBlocking authorities, then
exposes one pointer-based resolver for downstream production consumers.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from core.executability import preflight_shot_plan


SCHEMA_VERSION = "shot_plan_authority_envelope_v1"
CONTRACT_SCHEMA_VERSION = "shot_plan_authority_contract_v1"
AUTHORITY_POLICY_VERSION = "shot_plan_authority_policy_v1"
DEFAULT_POLICY_VERSION = "shot_plan_default_policy_v1"

UPSTREAM_CONSTRAINT = "UPSTREAM_CONSTRAINT"
SHOT_AUTHORING_DECISION = "SHOT_AUTHORING_DECISION"
PRODUCTION_CONTINUITY_STATE = "PRODUCTION_CONTINUITY_STATE"
DERIVED_EXECUTION_CONSTRAINT = "DERIVED_EXECUTION_CONSTRAINT"
UNKNOWN_UNRESOLVED = "UNKNOWN_UNRESOLVED"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def shot_plan_contract() -> dict[str, Any]:
    fields = [
        {"field": "scene_id", "semantic_definition": "stable ScriptIR scene identity", "authority_class": UPSTREAM_CONSTRAINT, "value_schema": "string", "required": True, "storyboard_blocking": True, "prompt_compiler_blocking": True, "mutation": "immutable", "provenance": "ScriptIR + current SceneBlocking", "stale": ["script_ir", "scene_blocking"]},
        {"field": "scene_name", "semantic_definition": "source-supported display identity", "authority_class": UPSTREAM_CONSTRAINT, "value_schema": "string", "required": True, "storyboard_blocking": True, "prompt_compiler_blocking": False, "mutation": "immutable_display_identity", "provenance": "ScriptIR", "stale": ["script_ir"]},
        {"field": "plan_shot_id", "semantic_definition": "stable shot identity within the plan", "authority_class": UPSTREAM_CONSTRAINT, "value_schema": "string", "required": True, "storyboard_blocking": True, "prompt_compiler_blocking": True, "mutation": "immutable_until_new_revision", "provenance": "ShotPlan candidate", "stale": ["shot_plan_contract"]},
        {"field": "beat_id", "semantic_definition": "ordered upstream beat binding", "authority_class": UPSTREAM_CONSTRAINT, "value_schema": "string", "required": True, "storyboard_blocking": True, "prompt_compiler_blocking": True, "mutation": "immutable_and_ordered", "provenance": "DirectorTreatment beat_map", "stale": ["treatment"]},
        {"field": "participants", "semantic_definition": "participant identity carried from blocking", "authority_class": UPSTREAM_CONSTRAINT, "value_schema": "string[]", "required": True, "storyboard_blocking": True, "prompt_compiler_blocking": True, "mutation": "preserve_identity", "provenance": "SceneBlocking", "stale": ["scene_blocking"]},
        {"field": "event", "semantic_definition": "source/director event expressed by the shot", "authority_class": UPSTREAM_CONSTRAINT, "value_schema": "string", "required": False, "storyboard_blocking": True, "prompt_compiler_blocking": True, "mutation": "preserve_meaning", "provenance": "Treatment beat_map", "stale": ["treatment"]},
        {"field": "camera", "semantic_definition": "shot-level camera authoring decision", "authority_class": SHOT_AUTHORING_DECISION, "value_schema": "object", "required": True, "storyboard_blocking": True, "prompt_compiler_blocking": True, "mutation": "reviewed_edit", "provenance": "author or deterministic default", "stale": ["shot_plan_contract"]},
        {"field": "duration_hint_seconds", "semantic_definition": "shot duration and timing budget", "authority_class": SHOT_AUTHORING_DECISION, "value_schema": "positive number", "required": True, "storyboard_blocking": True, "prompt_compiler_blocking": True, "mutation": "reviewed_edit_with_preflight", "provenance": "source/director/default + executability", "stale": ["executability_policy"]},
        {"field": "action_beats", "semantic_definition": "timed action units inside the shot", "authority_class": DERIVED_EXECUTION_CONSTRAINT, "value_schema": "timed object[]", "required": True, "storyboard_blocking": True, "prompt_compiler_blocking": True, "mutation": "reviewed_edit_with_source_preservation", "provenance": "beat + authoring + timing validation", "stale": ["executability_policy"]},
        {"field": "entry_state", "semantic_definition": "shot entry character/prop continuity state", "authority_class": PRODUCTION_CONTINUITY_STATE, "value_schema": "object", "required": True, "storyboard_blocking": True, "prompt_compiler_blocking": True, "mutation": "inherit_or_author_with_provenance", "provenance": "SceneBlocking exit/entry state", "stale": ["scene_blocking", "continuity"]},
        {"field": "exit_state", "semantic_definition": "shot exit character/prop continuity state", "authority_class": PRODUCTION_CONTINUITY_STATE, "value_schema": "object", "required": True, "storyboard_blocking": True, "prompt_compiler_blocking": True, "mutation": "author_with_transition_provenance", "provenance": "ShotPlan transition", "stale": ["continuity"]},
        {"field": "asset_bindings", "semantic_definition": "canonical asset identity and reference readiness", "authority_class": UPSTREAM_CONSTRAINT, "value_schema": "object", "required": True, "storyboard_blocking": True, "prompt_compiler_blocking": True, "mutation": "preserve_identity_distinguish_pending", "provenance": "SceneBlocking/asset registry", "stale": ["locked_assets"]},
        {"field": "continuity_contract", "semantic_definition": "screen direction, eyeline and prop transition rules", "authority_class": PRODUCTION_CONTINUITY_STATE, "value_schema": "object", "required": True, "storyboard_blocking": True, "prompt_compiler_blocking": True, "mutation": "reviewed_edit_with_validation", "provenance": "blocking + adjacent shot derivation", "stale": ["continuity"]},
        {"field": "camera_provenance", "semantic_definition": "why camera fields have their values", "authority_class": SHOT_AUTHORING_DECISION, "value_schema": "object", "required": True, "storyboard_blocking": False, "prompt_compiler_blocking": True, "mutation": "immutable_provenance", "provenance": "author/default policy", "stale": ["shot_plan_contract"]},
        {"field": "duration_provenance", "semantic_definition": "why duration was selected", "authority_class": DERIVED_EXECUTION_CONSTRAINT, "value_schema": "object", "required": True, "storyboard_blocking": False, "prompt_compiler_blocking": True, "mutation": "immutable_provenance", "provenance": "timing source/default/preflight", "stale": ["executability_policy"]},
        {"field": "unknowns", "semantic_definition": "unresolved plan information", "authority_class": UNKNOWN_UNRESOLVED, "value_schema": "string[]", "required": False, "storyboard_blocking": True, "prompt_compiler_blocking": True, "mutation": "resolve_with_evidence_only", "provenance": "upstream or explicit closure", "stale": ["upstream"]},
    ]
    upstream_fields = {"scene_id", "scene_name", "plan_shot_id", "beat_id", "participants", "event", "asset_bindings"}
    continuity_fields = {"entry_state", "exit_state", "continuity_contract"}
    asset_fields = {"asset_bindings"}
    executability_fields = {"duration_hint_seconds", "action_beats", "duration_provenance"}
    for item in fields:
        field = item["field"]
        item["optional"] = not bool(item.get("required"))
        item["mutation_policy"] = item.get("mutation", "reviewed_edit")
        item["provenance_requirement"] = item.get("provenance", "explicit authority or deterministic derivation")
        item["upstream_dependency"] = ["ScriptIR", "DirectorTreatment", "SceneBlocking"] if field in upstream_fields else []
        item["continuity_dependency"] = ["SceneBlocking", "adjacent ShotPlan"] if field in continuity_fields else []
        item["asset_dependency"] = ["asset registry", "locked reference authority"] if field in asset_fields else []
        item["executability_dependency"] = ["core.executability.preflight_shot_plan"] if field in executability_fields else []
        item["stale_dependency"] = list(item.get("stale", []))
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "authority_policy_version": AUTHORITY_POLICY_VERSION,
        "default_policy_version": DEFAULT_POLICY_VERSION,
        "fields": fields,
        "upstream_constraint_fields": ["scene_id", "scene_name", "plan_shot_id", "beat_id", "participants", "event", "asset_bindings"],
        "shot_authoring_fields": ["camera", "duration_hint_seconds", "camera_provenance", "duration_provenance"],
        "continuity_fields": ["entry_state", "exit_state", "continuity_contract"],
        "derived_execution_fields": ["action_beats"],
        "unknown_fields": ["unknowns"],
        "consumer_basis": ["core/storyboard_materializer.py", "api/storyboard_materializer_api.py", "core/prompt_ir_compiler.py", "core/executability.py", "api/shot_plan_api.py"],
        "production_selection": "shot_plan_pointers -> ShotPlanAuthority -> PRODUCTION_QUALIFIED row",
    }


def contract_fingerprint() -> str:
    return fingerprint(shot_plan_contract())


def _envelope_fingerprint(value: dict[str, Any]) -> str:
    return fingerprint({key: item for key, item in value.items() if key != "envelope_fingerprint"})


def shot_plan_payload_from_dict(plan: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "scene_id": _text(plan.get("scene_id")),
        "scene_name": _text(plan.get("scene_name")),
        "schema_version": _text(plan.get("schema_version") or "shot_plan_v2"),
        "shots": plan.get("shots") if isinstance(plan.get("shots"), list) else [],
        "unknowns": plan.get("unknowns") if isinstance(plan.get("unknowns"), list) else [],
    }
    if isinstance(plan.get("phase_c_contract"), dict):
        payload["phase_c_contract"] = plan["phase_c_contract"]
        payload["phase_c_semantic_ready"] = bool(plan.get("phase_c_semantic_ready"))
    return payload


def shot_plan_payload_from_row(row: Any) -> dict[str, Any]:
    payload = {
        "scene_id": getattr(row, "scene_id", ""),
        "scene_name": getattr(row, "scene_name", ""),
        "schema_version": getattr(row, "schema_version", "shot_plan_v2"),
        "shots": _json(getattr(row, "shots", "[]"), []),
        "unknowns": _json(getattr(row, "unknowns", "[]"), []),
    }
    model_info = _json(getattr(row, "model_info", "{}"), {})
    contract = model_info.get("phase_c_contract") if isinstance(model_info, dict) else None
    if not isinstance(contract, dict) and isinstance(model_info, dict) and isinstance(model_info.get("phase_c_plan"), dict):
        # Read old rows for audit only; they are not Phase C ready.
        contract = {key: value for key, value in model_info["phase_c_plan"].items() if key != "shots"}
    if isinstance(contract, dict):
        payload["phase_c_contract"] = contract
        payload["phase_c_semantic_ready"] = bool(model_info.get("phase_c_semantic_ready")) and model_info.get("shot_design_status") == "CANONICAL_CONFIRMED"
    return shot_plan_payload_from_dict(payload)


def shot_plan_payload_hash(plan: dict[str, Any]) -> str:
    return fingerprint(shot_plan_payload_from_dict(plan))


def _state_map(value: Any, key: str) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    raw = data.get(key)
    if isinstance(raw, dict):
        return {str(item): state for item, state in raw.items()}
    if isinstance(raw, list):
        result: dict[str, Any] = {}
        for item in raw:
            if isinstance(item, dict):
                identifier = item.get("character_id") or item.get("id") or item.get("prop_id")
                if _text(identifier):
                    result[_text(identifier)] = item
        return result
    return {}


def _prop_map(value: Any, *, prefer_exit: bool = False) -> dict[str, dict[str, Any]]:
    data = value if isinstance(value, dict) else {}
    items = data.get("props") if isinstance(data.get("props"), list) else []
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict) and _text(item.get("prop_id")):
            normalized = dict(item)
            if prefer_exit and "exit_state" in normalized:
                normalized["state"] = normalized.get("exit_state")
            elif not prefer_exit and "entry_state" in normalized:
                normalized["state"] = normalized.get("entry_state")
            result[_text(item["prop_id"])] = normalized
    return result


def validate_shot_continuity(*, shots: list[dict[str, Any]], scene_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not shots:
        errors.append({"code": "SHOT_PLAN_EMPTY", "severity": "blocked", "message": "Production ShotPlan must contain at least one shot."})
        return {"status": "blocked", "errors": errors, "warnings": warnings, "fingerprint": fingerprint({"errors": errors, "warnings": warnings})}
    first = shots[0]
    expected_ids = set()
    previous_exit: dict[str, Any] | None = None
    previous_props: dict[str, dict[str, Any]] = {}
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            errors.append({"code": "SHOT_OBJECT_INVALID", "severity": "blocked", "index": index})
            continue
        shot_id = _text(shot.get("plan_shot_id"))
        if not shot_id or shot_id in expected_ids:
            errors.append({"code": "SHOT_ID_DUPLICATE_OR_MISSING", "severity": "blocked", "index": index, "plan_shot_id": shot_id})
        expected_ids.add(shot_id)
        participants = [str(item) for item in (shot.get("participants") or []) if str(item).strip()]
        entry = shot.get("entry_state") if isinstance(shot.get("entry_state"), dict) else {}
        exit_state = shot.get("exit_state") if isinstance(shot.get("exit_state"), dict) else {}
        entry_chars = _state_map(entry, "characters")
        exit_chars = _state_map(exit_state, "characters")
        if set(entry_chars) - set(participants) or set(exit_chars) - set(participants):
            errors.append({"code": "CHARACTER_CONTINUITY_UNKNOWN_PARTICIPANT", "severity": "blocked", "plan_shot_id": shot_id})
        if index == 0:
            scene_chars = _state_map(scene_entry, "states") if isinstance(scene_entry, dict) else {}
            if scene_chars and set(scene_chars) - set(participants):
                errors.append({"code": "SCENE_ENTRY_CHARACTER_MISSING", "severity": "blocked", "plan_shot_id": shot_id})
        elif previous_exit is not None:
            previous_chars = _state_map(previous_exit, "characters")
            for character_id, previous_state in previous_chars.items():
                current_state = entry_chars.get(character_id)
                if current_state is None:
                    errors.append({"code": "CHARACTER_CONTINUITY_BREAK", "severity": "blocked", "plan_shot_id": shot_id, "character_id": character_id})
                elif isinstance(previous_state, dict) and isinstance(current_state, dict):
                    for field in ("position", "facing", "state"):
                        before = previous_state.get(field)
                        after = current_state.get(field)
                        if before not in (None, "", {}) and after not in (None, "", {}) and before != after:
                            # A changed state is legal only when the shot declares
                            # an explicit movement/state transition.
                            if not shot.get("action_beats") and not shot.get("event"):
                                errors.append({"code": "CHARACTER_STATE_TRANSITION_UNDECLARED", "severity": "blocked", "plan_shot_id": shot_id, "character_id": character_id, "field": field})
        props = _prop_map(entry)
        exit_props = _prop_map(exit_state, prefer_exit=True)
        if index > 0:
            for prop_id, before in previous_props.items():
                after = props.get(prop_id)
                if after is None:
                    errors.append({"code": "PROP_CONTINUITY_BREAK", "severity": "blocked", "plan_shot_id": shot_id, "prop_id": prop_id})
                else:
                    for field in ("state", "location", "holder", "visibility"):
                        if before.get(field) not in (None, "", {}) and after.get(field) not in (None, "", {}) and before.get(field) != after.get(field):
                            if not shot.get("action_beats") and not shot.get("event"):
                                errors.append({"code": "PROP_STATE_TRANSITION_UNDECLARED", "severity": "blocked", "plan_shot_id": shot_id, "prop_id": prop_id, "field": field})
        prior_direction = ""
        if previous_exit is not None:
            prior_direction = _text((shots[index - 1].get("continuity_contract") or {}).get("screen_direction")) if isinstance(shots[index - 1].get("continuity_contract"), dict) else ""
        current_direction = _text((shot.get("continuity_contract") or {}).get("screen_direction")) if isinstance(shot.get("continuity_contract"), dict) else ""
        if prior_direction and current_direction and prior_direction != current_direction and not shot.get("continuity_contract", {}).get("declared_transition"):
            errors.append({"code": "SCREEN_DIRECTION_BREAK", "severity": "blocked", "plan_shot_id": shot_id, "from": prior_direction, "to": current_direction})
        previous_exit = exit_state
        previous_props = exit_props
    if isinstance(scene_entry, dict) and scene_entry.get("unresolved"):
        errors.extend({"code": "SCENE_CONTINUITY_UNRESOLVED", "severity": "blocked", **item} if isinstance(item, dict) else {"code": "SCENE_CONTINUITY_UNRESOLVED", "severity": "blocked", "message": str(item)} for item in scene_entry["unresolved"])
    report = {"status": "blocked" if errors else "pass", "errors": errors, "warnings": warnings}
    report["fingerprint"] = fingerprint(report)
    return report


def validate_shot_plan_candidate_authority(raw: dict[str, Any], baseline: dict[str, Any], *, scene_entry: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not isinstance(raw, dict):
        raise ValueError("ShotPlan candidate must be an object")
    allowed = {"scene_id", "scene_name", "schema_version", "shots", "unknowns", "unknown_resolutions", "phase_c_plan", "phase_c_semantic_ready"}
    unexpected = sorted(set(raw) - allowed)
    if unexpected:
        raise ValueError(f"candidate contains non-whitelisted fields: {', '.join(unexpected)}")
    if _text(raw.get("scene_id", baseline.get("scene_id"))) != _text(baseline.get("scene_id")):
        raise ValueError("scene_id is an immutable upstream constraint")
    if _text(raw.get("scene_name", baseline.get("scene_name"))) != _text(baseline.get("scene_name")):
        raise ValueError("scene_name is an immutable upstream identity")
    baseline_shots = baseline.get("shots") if isinstance(baseline.get("shots"), list) else []
    shots = raw.get("shots", baseline_shots)
    if not isinstance(shots, list) or any(not isinstance(item, dict) for item in shots):
        raise ValueError("shots must be a list of objects")
    base_ids = [_text(item.get("plan_shot_id")) for item in baseline_shots]
    candidate_ids = [_text(item.get("plan_shot_id")) for item in shots]
    if candidate_ids != base_ids:
        raise ValueError("plan_shot_id order/cardinality is immutable; create a new authoritative revision")
    base_beats = {_text(item.get("plan_shot_id")): (_text(item.get("beat_id")), _text(item.get("event")), list(item.get("participants") or [])) for item in baseline_shots}
    for item in shots:
        shot_id = _text(item.get("plan_shot_id"))
        if not isinstance(item.get("camera"), dict) or not _text(item["camera"].get("shot_size")) or not _text(item["camera"].get("movement")):
            raise ValueError(f"{shot_id} must define camera.shot_size and camera.movement")
        duration = item.get("duration_hint_seconds")
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise ValueError(f"{shot_id} must define a positive duration_hint_seconds")
        expected_beat, expected_event, expected_participants = base_beats[shot_id]
        if _text(item.get("beat_id")) != expected_beat or _text(item.get("event")) != expected_event:
            raise ValueError(f"{shot_id} cannot change upstream beat identity or event")
        if list(item.get("participants") or []) != expected_participants:
            raise ValueError(f"{shot_id} cannot change participant identity")
        if not isinstance(item.get("camera_provenance"), dict) or not _text(item["camera_provenance"].get("authority_class")):
            raise ValueError(f"{shot_id} camera provenance is required")
        if not isinstance(item.get("duration_provenance"), dict) or not _text(item["duration_provenance"].get("source")):
            raise ValueError(f"{shot_id} duration provenance is required")
        for action in item.get("action_beats") if isinstance(item.get("action_beats"), list) else []:
            if not isinstance(action, dict):
                raise ValueError(f"{shot_id} action_beats must be objects")
            start, end = action.get("start_seconds", action.get("at", 0)), action.get("end_seconds", action.get("at", 0))
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or start < 0 or end < start or end > duration:
                raise ValueError(f"{shot_id} action timing must fit within duration")
        intervals = []
        for action in item.get("action_beats") if isinstance(item.get("action_beats"), list) else []:
            start = action.get("start_seconds", action.get("at", 0)) if isinstance(action, dict) else 0
            end = action.get("end_seconds", action.get("at", 0)) if isinstance(action, dict) else 0
            if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                intervals.append((float(start), float(end), bool(action.get("allow_overlap") or action.get("concurrent"))))
        ordered_intervals = sorted(intervals)
        for prior, current in zip(ordered_intervals, ordered_intervals[1:]):
            if current[0] < prior[1] and not (prior[2] or current[2]):
                raise ValueError(f"{shot_id} action timing contains an undeclared overlap")
    unknowns = raw.get("unknowns", baseline.get("unknowns", []))
    if not isinstance(unknowns, list):
        raise ValueError("unknowns must be a list")
    base_unknowns = {_canonical(item) for item in (baseline.get("unknowns") if isinstance(baseline.get("unknowns"), list) else [])}
    candidate_unknowns = {_canonical(item) for item in unknowns}
    removed = base_unknowns - candidate_unknowns
    resolutions = raw.get("unknown_resolutions") if isinstance(raw.get("unknown_resolutions"), list) else []
    resolved = {_canonical(item.get("unknown")) for item in resolutions if isinstance(item, dict) and _text(item.get("status")) in {"RESOLVED_BY_UPSTREAM", "RESOLVED_BY_AUTHORING_DECISION", "RESOLVED_BY_DERIVATION"}}
    if not removed.issubset(resolved):
        raise ValueError("unknowns cannot be silently removed")
    if unknowns:
        raise ValueError("ShotPlan production activation requires all blocking unknowns resolved")
    continuity = validate_shot_continuity(shots=shots, scene_entry=scene_entry)
    executability = preflight_shot_plan(shots)
    if executability.get("status") == "blocked":
        raise ValueError("ShotPlan executability is blocked")
    result = {"scene_id": _text(baseline.get("scene_id")), "scene_name": _text(baseline.get("scene_name")), "schema_version": _text(raw.get("schema_version") or baseline.get("schema_version") or "shot_plan_v2"), "shots": shots, "unknowns": []}
    if isinstance(raw.get("phase_c_plan"), dict):
        result["phase_c_contract"] = raw["phase_c_plan"]
        result["phase_c_semantic_ready"] = bool(raw.get("phase_c_semantic_ready", raw["phase_c_plan"].get("phase_c_semantic_ready")))
    return result, continuity, executability


def build_shot_plan_authority_envelope(*, plan: dict[str, Any], book_id: int, episode: int, plan_id: int, plan_revision: int, script_ir: Any, script_ir_envelope: dict[str, Any], treatment: Any, treatment_envelope: dict[str, Any], blocking: Any, blocking_envelope: dict[str, Any], executability: dict[str, Any], continuity: dict[str, Any]) -> dict[str, Any]:
    blocking_payload_hash = _text(blocking_envelope.get("payload_hash") or getattr(blocking, "payload_hash", ""))
    fact_meta = blocking_envelope.get("fact_snapshot") if isinstance(blocking_envelope.get("fact_snapshot"), dict) else {}
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "authority_policy_version": AUTHORITY_POLICY_VERSION,
        "default_policy_version": DEFAULT_POLICY_VERSION,
        "workflow_profile": "production",
        "book_id": int(book_id), "episode": int(episode), "scene_id": _text(plan.get("scene_id")),
        "shot_plan_id": int(plan_id), "plan_revision": int(plan_revision), "schema_version_payload": _text(plan.get("schema_version") or "shot_plan_v2"),
        "payload_hash": shot_plan_payload_hash(plan),
        "script_ir": {"id": getattr(script_ir, "id", None), "revision": getattr(script_ir, "revision", None), "payload_hash": _text(getattr(script_ir, "payload_hash", "")), "authority_envelope_fingerprint": _text(script_ir_envelope.get("envelope_fingerprint"))},
        "treatment": {"id": getattr(treatment, "id", None), "revision": getattr(treatment, "revision", None), "payload_hash": _text(getattr(treatment, "payload_hash", "")), "authority_envelope_fingerprint": _text(treatment_envelope.get("envelope_fingerprint"))},
        "scene_blocking": {"id": getattr(blocking, "id", None), "revision": getattr(blocking, "revision", None), "payload_hash": blocking_payload_hash, "authority_envelope_fingerprint": _text(blocking_envelope.get("envelope_fingerprint"))},
        "source_lineage": {"immutable_source_raw_hash": _text(script_ir_envelope.get("source_lineage", {}).get("immutable_source_raw_hash") if isinstance(script_ir_envelope.get("source_lineage"), dict) else ""), "source_evidence_index_fingerprint": _text(script_ir_envelope.get("source_evidence_index_fingerprint"))},
        "fact_snapshot": fact_meta,
        "asset_authority": blocking_envelope.get("asset_authority", {}) if isinstance(blocking_envelope.get("asset_authority"), dict) else {},
        "contract": {"schema_version": CONTRACT_SCHEMA_VERSION, "fingerprint": contract_fingerprint(), "requirement_set_fingerprint": fingerprint({"fields": shot_plan_contract()["fields"]})},
        "executability": {"report": executability, "fingerprint": fingerprint(executability)},
        "continuity": {"report": continuity, "fingerprint": fingerprint(continuity)},
        "phase_c": {"contract_version": _text(plan.get("phase_c_contract", {}).get("contract_version")) if isinstance(plan.get("phase_c_contract"), dict) else "", "payload_hash": _text(plan.get("phase_c_contract", {}).get("payload_hash")) if isinstance(plan.get("phase_c_contract"), dict) else "", "semantic_ready": bool(plan.get("phase_c_semantic_ready"))},
        "qualification_state": "PRODUCTION_QUALIFIED", "stale_status": "FRESH", "stale_reasons": [],
        "approved_at": datetime.now(timezone.utc).isoformat(), "activated_at": datetime.now(timezone.utc).isoformat(),
    }
    envelope["envelope_fingerprint"] = _envelope_fingerprint(envelope)
    return envelope


def mark_shot_plan_stale(session: Any, plan: Any, reasons: list[str]) -> None:
    from models import ShotPlanAuthority, ShotPlanPointer
    normalized = sorted({_text(item) for item in reasons if _text(item)})
    plan.status = "stale"; plan.production_status = "blocked"; plan.qualification_state = "STALE"; plan.stale_status = "STALE"; plan.stale_reasons = json.dumps(normalized, ensure_ascii=False); plan.updated_at = datetime.now()
    authority = session.query(ShotPlanAuthority).filter_by(shot_plan_id=plan.id).first()
    if authority:
        authority.qualification_state = "STALE"; authority.stale_status = "STALE"; authority.stale_reasons = json.dumps(normalized, ensure_ascii=False); authority.updated_at = datetime.now()
    session.query(ShotPlanPointer).filter_by(shot_plan_id=plan.id).delete(synchronize_session=False)


def _raise(code: str, message: str, **extra: Any) -> None:
    raise HTTPException(status_code=409, detail={"code": code, "message": message, **extra})


def _validate_envelope(envelope: dict[str, Any], *, row: Any, authority: Any, pointer: Any, book_id: int, episode: int) -> list[str]:
    errors: list[str] = []
    if _text(envelope.get("schema_version")) != SCHEMA_VERSION or _text(envelope.get("authority_policy_version")) != AUTHORITY_POLICY_VERSION:
        errors.append("SHOT_PLAN_AUTHORITY_POLICY_CHANGED")
    if str(envelope.get("book_id")) != str(book_id) or str(envelope.get("episode")) != str(episode):
        errors.append("SHOT_PLAN_SCOPE_MISMATCH")
    if _text(envelope.get("envelope_fingerprint")) != _envelope_fingerprint(envelope):
        errors.append("SHOT_PLAN_AUTHORITY_TAMPERED")
    expected = shot_plan_payload_hash(shot_plan_payload_from_row(row))
    if _text(envelope.get("payload_hash")) != expected or _text(getattr(row, "payload_hash", "")) != expected or _text(getattr(authority, "payload_hash", "")) != expected:
        errors.append("SHOT_PLAN_PAYLOAD_TAMPERED")
    if str(envelope.get("shot_plan_id")) != str(row.id) or str(envelope.get("plan_revision")) != str(row.revision) or str(pointer.plan_revision) != str(row.revision):
        errors.append("SHOT_PLAN_POINTER_LINEAGE_CHANGED")
    if _text(pointer.authority_envelope_fingerprint) != _text(envelope.get("envelope_fingerprint")) or _text(authority.envelope_fingerprint) != _text(envelope.get("envelope_fingerprint")):
        errors.append("SHOT_PLAN_AUTHORITY_TAMPERED")
    if _text((envelope.get("contract") or {}).get("fingerprint")) != contract_fingerprint():
        errors.append("SHOT_PLAN_CONTRACT_CHANGED")
    return errors


def resolve_current_authoritative_shot_plan(session: Any, *, book_id: int, episode: int, scene_id: str) -> tuple[Any, dict[str, Any]]:
    from models import FactSnapshot, Script, ScriptIRVersion, ShotPlan, ShotPlanAuthority, ShotPlanPointer
    from core.scene_blocking_authority import resolve_current_authoritative_scene_blocking
    from core.director_treatment_authority import resolve_current_authoritative_treatment
    scene_id = _text(scene_id)
    if not scene_id:
        _raise("SCENE_ID_REQUIRED", "Production ShotPlan requires a stable scene_id.")
    pointer = session.query(ShotPlanPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
    if not pointer:
        _raise("SHOT_PLAN_POINTER_MISSING", "No current authoritative ShotPlan pointer for scene.")
    row = session.query(ShotPlan).filter_by(id=pointer.shot_plan_id, book_id=book_id, episode=episode, scene_id=scene_id).first()
    authority = session.query(ShotPlanAuthority).filter_by(shot_plan_id=pointer.shot_plan_id, envelope_fingerprint=pointer.authority_envelope_fingerprint).first()
    if not row or not authority or row.status != "approved" or row.qualification_state != "PRODUCTION_QUALIFIED" or authority.qualification_state != "PRODUCTION_QUALIFIED" or authority.stale_status == "STALE" or row.stale_status == "STALE" or pointer.qualification_state != "PRODUCTION_QUALIFIED":
        _raise("SHOT_PLAN_NOT_PRODUCTION_QUALIFIED", "Current ShotPlan is not production-qualified.")
    envelope = _json(authority.envelope_json, {})
    errors = _validate_envelope(envelope, row=row, authority=authority, pointer=pointer, book_id=book_id, episode=episode)
    if errors:
        mark_shot_plan_stale(session, row, errors); session.commit(); _raise(errors[0], "ShotPlan authority envelope or payload is invalid.", stale_reasons=errors)
    blocking, blocking_envelope = resolve_current_authoritative_scene_blocking(session, book_id=book_id, episode=episode, scene_id=scene_id)
    treatment, treatment_envelope = resolve_current_authoritative_treatment(session, book_id=book_id, episode=episode, scene_id=scene_id)
    from core.director_treatment_authority import treatment_payload_from_row
    from core.scene_blocking_authority import blocking_payload_from_row
    from core.phase_c_shot_plan import validate_shot_design
    blocking_meta = envelope.get("scene_blocking") if isinstance(envelope.get("scene_blocking"), dict) else {}
    if str(blocking_meta.get("id")) != str(blocking.id) or str(blocking_meta.get("revision")) != str(blocking.revision) or _text(blocking_meta.get("payload_hash")) != _text(blocking_envelope.get("payload_hash")) or _text(blocking_meta.get("authority_envelope_fingerprint")) != _text(blocking_envelope.get("envelope_fingerprint")):
        mark_shot_plan_stale(session, row, ["SCENE_BLOCKING_CHANGED"]); session.commit(); _raise("SCENE_BLOCKING_CHANGED", "ShotPlan SceneBlocking lineage is stale.")
    treatment_meta = envelope.get("treatment") if isinstance(envelope.get("treatment"), dict) else {}
    if str(treatment_meta.get("id")) != str(treatment.id) or str(treatment_meta.get("revision")) != str(treatment.revision) or _text(treatment_meta.get("authority_envelope_fingerprint")) != _text(treatment_envelope.get("envelope_fingerprint")):
        mark_shot_plan_stale(session, row, ["DIRECTOR_TREATMENT_CHANGED"]); session.commit(); _raise("DIRECTOR_TREATMENT_CHANGED", "ShotPlan Treatment lineage is stale.")
    fact_meta = blocking_envelope.get("fact_snapshot") if isinstance(blocking_envelope.get("fact_snapshot"), dict) else {}
    plan_fact_meta = envelope.get("fact_snapshot") if isinstance(envelope.get("fact_snapshot"), dict) else {}
    if _canonical(fact_meta) != _canonical(plan_fact_meta):
        mark_shot_plan_stale(session, row, ["FACT_SNAPSHOT_CHANGED"]); session.commit(); _raise("FACT_SNAPSHOT_CHANGED", "ShotPlan FactSnapshot lineage is stale.")
    plan = shot_plan_payload_from_row(row)
    row_model_info = _json(getattr(row, "model_info", "{}"), {})
    canonical_phase_c = isinstance(row_model_info, dict) and row_model_info.get("shot_design_status") == "CANONICAL_CONFIRMED"
    phase_c_contract = plan.get("phase_c_contract") if isinstance(plan.get("phase_c_contract"), dict) else None
    if canonical_phase_c and (not phase_c_contract or not plan.get("phase_c_semantic_ready")):
        mark_shot_plan_stale(session, row, ["SHOT_PLAN_PHASE_C_NOT_READY"]); session.commit(); _raise("SHOT_PLAN_PHASE_C_NOT_READY", "Current ShotPlan is legacy or Phase C semantic-not-ready.")
    if not canonical_phase_c:
        # Legacy compatibility rows remain readable for existing creative
        # workflows, but they are not reported as Phase C semantic-ready.
        return row, envelope
    phase_meta = envelope.get("phase_c") if isinstance(envelope.get("phase_c"), dict) else {}
    if _text(phase_meta.get("payload_hash")) != _text(phase_c_contract.get("payload_hash")) or not phase_meta.get("semantic_ready"):
        mark_shot_plan_stale(session, row, ["SHOT_PLAN_PHASE_C_TAMPERED"]); session.commit(); _raise("SHOT_PLAN_PHASE_C_TAMPERED", "Phase C contract lineage is invalid.")
    phase_validation = validate_shot_design(shots=plan["shots"], requirements=phase_c_contract, treatment=treatment_payload_from_row(treatment), blocking=blocking_payload_from_row(blocking), authoring_provenance=phase_c_contract.get("authoring_provenance"))
    if not phase_validation.get("valid"):
        mark_shot_plan_stale(session, row, ["SHOT_PLAN_PHASE_C_INVALID"]); session.commit(); _raise("SHOT_PLAN_PHASE_C_INVALID", "Current Phase C contract is no longer valid.", errors=phase_validation.get("errors", []))
    script = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
    ir = session.query(ScriptIRVersion).filter_by(id=getattr(script, "current_script_ir_version_id", None), book_id=book_id, episode=episode).first() if script else None
    script_meta = envelope.get("script_ir") if isinstance(envelope.get("script_ir"), dict) else {}
    if not ir or str(script_meta.get("id")) != str(ir.id) or str(script_meta.get("revision")) != str(ir.revision) or _text(script_meta.get("payload_hash")) != _text(ir.payload_hash):
        mark_shot_plan_stale(session, row, ["SCRIPT_IR_CHANGED"]); session.commit(); _raise("SCRIPT_IR_CHANGED", "ShotPlan ScriptIR lineage is stale.")
    continuity = phase_validation.get("continuity") if isinstance(phase_validation.get("continuity"), dict) else {"valid": False, "errors": [{"code": "SHOT_CONTINUITY_CONTRACT_INVALID"}]}
    executability = preflight_shot_plan(plan["shots"])
    if not continuity.get("valid"):
        mark_shot_plan_stale(session, row, ["SHOT_CONTINUITY_CONTRACT_INVALID"]); session.commit(); _raise("SHOT_PLAN_PHASE_C_INVALID", "Current ShotPlan continuity is no longer valid.", errors=continuity.get("errors", []))
    if executability.get("status") == "blocked":
        mark_shot_plan_stale(session, row, ["SHOT_EXECUTABILITY_CHANGED"]); session.commit(); _raise("SHOT_EXECUTABILITY_CHANGED", "Current ShotPlan executability is no longer valid.")
    return row, envelope


__all__ = [
    "SCHEMA_VERSION", "CONTRACT_SCHEMA_VERSION", "AUTHORITY_POLICY_VERSION", "DEFAULT_POLICY_VERSION",
    "UPSTREAM_CONSTRAINT", "SHOT_AUTHORING_DECISION", "PRODUCTION_CONTINUITY_STATE", "DERIVED_EXECUTION_CONSTRAINT", "UNKNOWN_UNRESOLVED",
    "shot_plan_contract", "contract_fingerprint", "fingerprint", "shot_plan_payload_from_dict", "shot_plan_payload_from_row", "shot_plan_payload_hash",
    "validate_shot_continuity", "validate_shot_plan_candidate_authority", "build_shot_plan_authority_envelope", "mark_shot_plan_stale", "resolve_current_authoritative_shot_plan",
]
