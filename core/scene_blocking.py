"""Evidence-first SceneBlocking with explicit spatial authority boundaries.

V2 separates source evidence extraction from director spatial planning.  The
planner may fill director-level choices, but every such choice is labelled
``CREATIVE_CHOICE``; deterministic continuity data is labelled
``DERIVED_CONSTRAINT``.  The legacy builder remains available so old records
and creative-draft clients retain their original semantics.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.qualification_loop import qualify_candidate

SOURCE_FACT = "SOURCE_FACT"
CREATIVE_CHOICE = "CREATIVE_CHOICE"
DERIVED_CONSTRAINT = "DERIVED_CONSTRAINT"
SPATIAL_AUTHORITIES = {SOURCE_FACT, CREATIVE_CHOICE, DERIVED_CONSTRAINT}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _name(value: Any) -> str:
    return str(value or "").strip()


def _unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _name(value)
        if text and text not in result:
            result.append(text)
    return result


def _merge_space(scene: dict[str, Any], canonical: dict[str, Any] | None) -> dict[str, list[str]]:
    """Normalize SceneCanonical geometry without inventing structures."""
    sources: list[dict[str, Any]] = [item for item in (scene, canonical or {}) if isinstance(item, dict)]
    for source in list(sources):
        nested = source.get("canonical_facts")
        nested = _json(nested, {}) if isinstance(nested, str) else nested
        if isinstance(nested, dict):
            sources.append(nested)
    aliases = {
        "anchors": ("anchors", "spatial_anchors", "key_anchors"),
        "zones": ("zones", "spatial_zones"),
        "entrances": ("entrances", "entries", "doors"),
        "exits": ("exits",),
        "fixed_objects": ("fixed_objects", "fixed_props", "key_props", "props"),
    }
    out: dict[str, list[str]] = {key: [] for key in aliases}
    for target, names in aliases.items():
        for source in sources:
            for alias in names:
                raw = source.get(alias)
                if isinstance(raw, dict):
                    raw = list(raw.keys())
                if not isinstance(raw, list):
                    continue
                for entry in raw:
                    value = entry.get("id") or entry.get("name") or entry.get("label") if isinstance(entry, dict) else entry
                    text = _name(value)
                    if text and text not in out[target]:
                        out[target].append(text)
    return out


def _character_intents(treatment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = treatment.get("character_intents")
    if not isinstance(raw, dict):
        return {}
    return {str(key): value if isinstance(value, dict) else {"name": str(value)} for key, value in raw.items()}


def _blocking_index(scene: dict[str, Any]) -> dict[str, dict[str, Any]]:
    declared = scene.get("character_blocking") or scene.get("blocking") or []
    if isinstance(declared, dict):
        declared = list(declared.values())
    if not isinstance(declared, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in declared:
        if not isinstance(item, dict):
            continue
        for key in (item.get("id"), item.get("character_id"), item.get("name"), item.get("character")):
            key = _name(key)
            if key:
                result[key] = item
    return result


def extract_spatial_evidence(*, scene: dict[str, Any], treatment: dict[str, Any], scene_canonical: dict[str, Any] | None = None, fact_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Step A: project existing spatial evidence only."""
    space = _merge_space(scene, scene_canonical)
    index = _blocking_index(scene)
    facts: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    raw_facts = scene.get("spatial_facts") or scene.get("spatial_constraints") or []
    if isinstance(raw_facts, list):
        for i, raw in enumerate(raw_facts, start=1):
            if not isinstance(raw, dict):
                continue
            subject = _name(raw.get("subject_id") or raw.get("character_id") or raw.get("subject") or raw.get("character"))
            predicate = _name(raw.get("predicate") or raw.get("relation") or "position")
            value = raw.get("value", raw.get("position") or raw.get("anchor"))
            if subject and predicate and value not in (None, ""):
                facts.append({"fact_id": _name(raw.get("fact_id")) or f"SPATIAL_{i:04d}", "subject_id": subject, "predicate": predicate, "value": value, "authority": SOURCE_FACT, "evidence_ref": _name(raw.get("evidence_ref") or raw.get("source") or "script")})
    for character_id, intent in _character_intents(treatment).items():
        character_name = _name(intent.get("name")) or character_id
        block = index.get(character_id) or index.get(character_name)
        if not block:
            continue
        mappings = (
            ("position", block.get("position") or block.get("screen_position") or block.get("blocking")),
            ("anchor", block.get("anchor") or block.get("spatial_anchor")),
            ("facing", block.get("facing") or block.get("screen_direction")),
            ("entry", block.get("entry") or block.get("entry_point")),
            ("exit", block.get("exit") or block.get("exit_point")),
            ("movement_path", block.get("movement_path") or block.get("path")),
        )
        for predicate, value in mappings:
            if value not in (None, "", []):
                facts.append({"fact_id": f"{character_id}:{predicate}", "subject_id": character_id, "predicate": predicate, "value": value, "authority": SOURCE_FACT, "evidence_ref": "script.character_blocking"})
    records = (fact_snapshot or {}).get("records") if isinstance(fact_snapshot, dict) else []
    intent_name_to_id = {_name(value.get("name")): key for key, value in _character_intents(treatment).items() if _name(value.get("name"))}
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict) or _name(record.get("predicate")).lower() not in {"position", "anchor", "facing", "entry", "exit", "blocking"}:
            continue
        value = record.get("value")
        if value not in (None, "", []):
            subject = _name(record.get("subject_id")); subject = intent_name_to_id.get(subject, subject)
            facts.append({"fact_id": _name(record.get("fact_id")) or f"FACT_SPATIAL_{len(facts)+1:04d}", "subject_id": subject, "predicate": _name(record.get("predicate")), "value": value, "authority": SOURCE_FACT, "evidence_ref": record.get("evidence") or ["fact_snapshot"]})
    seen: dict[tuple[str, str], Any] = {}
    deduped: list[dict[str, Any]] = []
    for fact in facts:
        key = (_name(fact.get("subject_id")), _name(fact.get("predicate")))
        if key in seen and seen[key] != fact.get("value"):
            conflicts.append({"code": "FACT_SPATIAL_CONFLICT", "subject_id": key[0], "predicate": key[1], "values": [seen[key], fact.get("value")], "severity": "blocker"})
            continue
        seen[key] = fact.get("value")
        if not any(_name(item.get("subject_id")) == key[0] and _name(item.get("predicate")) == key[1] for item in deduped):
            deduped.append(fact)
    available = set(_unique(space.get("anchors", []) + space.get("zones", []) + space.get("entrances", []) + space.get("exits", []) + space.get("fixed_objects", [])))
    required = scene.get("required_anchors") or scene.get("required_spatial_anchors") or []
    if isinstance(required, dict):
        required = list(required.keys())
    if isinstance(required, list):
        for anchor in required:
            anchor_name = _name(anchor.get("id") or anchor.get("name")) if isinstance(anchor, dict) else _name(anchor)
            if anchor_name and anchor_name not in available:
                unresolved.append({"code": "MISSING_SCENE_ANCHOR", "required": anchor_name, "severity": "blocker", "message": f"required scene anchor is not present in SceneCanonical: {anchor_name}"})
    return {"space": space, "source_spatial_facts": deduped, "unresolved_facts": unresolved, "conflicts": conflicts}


def _source_for(facts: list[dict[str, Any]], subject: str, predicate: str) -> dict[str, Any] | None:
    return next((fact for fact in facts if _name(fact.get("subject_id")) == subject and _name(fact.get("predicate")) == predicate), None)


def plan_director_spatial(*, evidence: dict[str, Any], treatment: dict[str, Any], previous_blocking: dict[str, Any] | None = None) -> dict[str, Any]:
    """Step B: fill director-level spatial choices with explicit authority."""
    facts = evidence.get("source_spatial_facts") if isinstance(evidence.get("source_spatial_facts"), list) else []
    intents = _character_intents(treatment)
    ids = list(intents)
    participants: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    space = evidence.get("space") if isinstance(evidence.get("space"), dict) else {}
    known_anchors = space.get("anchors") or []
    known_zones = space.get("zones") or []
    for index, character_id in enumerate(ids):
        intent = intents[character_id]
        name = _name(intent.get("name")) or character_id
        position_fact = _source_for(facts, character_id, "position") or _source_for(facts, character_id, "anchor")
        facing_fact = _source_for(facts, character_id, "facing")
        entry_fact = _source_for(facts, character_id, "entry")
        exit_fact = _source_for(facts, character_id, "exit")
        path_fact = _source_for(facts, character_id, "movement_path")
        if position_fact:
            start_value, start_authority = position_fact.get("value"), SOURCE_FACT
        elif known_anchors:
            start_value, start_authority = known_anchors[min(index, len(known_anchors) - 1)], CREATIVE_CHOICE
        elif known_zones:
            start_value, start_authority = known_zones[min(index, len(known_zones) - 1)], CREATIVE_CHOICE
        else:
            start_value, start_authority = "scene_center", CREATIVE_CHOICE
        facing_value = facing_fact.get("value") if facing_fact else (ids[1] if len(ids) > 1 and index == 0 else ids[0] if len(ids) > 1 else "scene_action")
        facing_authority = SOURCE_FACT if facing_fact else CREATIVE_CHOICE
        eyeline_value = ids[1] if len(ids) > 1 and index == 0 else ids[0] if len(ids) > 1 else "scene_action"
        participant = {
            "character_id": character_id, "name": name,
            "start_position": {"value": start_value, "authority": start_authority},
            "facing": {"value": facing_value, "authority": facing_authority},
            "eyeline_target": {"value": eyeline_value, "authority": CREATIVE_CHOICE},
            "screen_side": {"value": "left" if index % 2 == 0 else "right", "authority": DERIVED_CONSTRAINT},
            "movement_path": path_fact.get("value") if path_fact and isinstance(path_fact.get("value"), list) else ([path_fact.get("value")] if path_fact else []),
            # V1 projection retained for ShotPlan and older clients.
            "position": start_value, "anchor": start_value if position_fact and position_fact.get("predicate") == "anchor" else None,
            "source": "script_declared" if position_fact else "director_choice",
        }
        if entry_fact:
            participant["entry"] = {"value": entry_fact.get("value"), "authority": SOURCE_FACT}
        if exit_fact:
            participant["exit"] = {"value": exit_fact.get("value"), "authority": SOURCE_FACT}
        participants.append(participant)
        if not position_fact:
            decisions.append({"decision": "start_position", "subject_id": character_id, "value": start_value, "authority": CREATIVE_CHOICE, "reason": "source did not specify a required position"})
        decisions.extend([
            {"decision": "eyeline_target", "subject_id": character_id, "value": eyeline_value, "authority": CREATIVE_CHOICE},
            {"decision": "facing", "subject_id": character_id, "value": facing_value, "authority": facing_authority},
        ])
    camera_axis = {"subject_a": ids[0] if ids else "", "subject_b": ids[1] if len(ids) > 1 else "", "preferred_side": "center", "authority": CREATIVE_CHOICE}
    if len(ids) > 1:
        decisions.append({"decision": "camera_axis", "value": camera_axis, "authority": CREATIVE_CHOICE})
    return {
        "space": space, "participants": participants, "camera_axis": camera_axis, "creative_decisions": decisions,
        "derived_constraints": {"screen_direction": "maintain_previous" if previous_blocking else "establish_from_camera_axis", "axis": {"subject_a": camera_axis["subject_a"], "subject_b": camera_axis["subject_b"], "preferred_side": camera_axis["preferred_side"]}, "movement_continuity": "preserve_entry_and_exit_states", "teleport_detection": True},
    }


def validate_scene_blocking(blocking: dict[str, Any], *, scene_canonical: dict[str, Any] | None = None, previous_blocking: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate authority, references and continuity; never mutate input."""
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    participants = blocking.get("participants") if isinstance(blocking.get("participants"), list) else []
    ids = {_name(item.get("character_id")) for item in participants if isinstance(item, dict)}
    facts = blocking.get("source_spatial_facts", []) if isinstance(blocking.get("source_spatial_facts"), list) else []
    for fact in facts:
        subject, predicate = _name(fact.get("subject_id")), _name(fact.get("predicate"))
        if subject not in ids:
            errors.append({"code": "INVALID_PARTICIPANT_ID", "severity": "blocker", "message": f"source fact references unknown participant: {subject}"}); continue
        if fact.get("authority") != SOURCE_FACT:
            errors.append({"code": "SOURCE_AUTHORITY_REQUIRED", "severity": "blocker", "message": "source spatial facts must be SOURCE_FACT"})
        if predicate in {"position", "anchor"}:
            participant = next(item for item in participants if _name(item.get("character_id")) == subject)
            current = participant.get("start_position") if isinstance(participant.get("start_position"), dict) else {}
            if current.get("value") != fact.get("value"):
                errors.append({"code": "SOURCE_FACT_OVERRIDDEN", "severity": "blocker", "target_id": subject, "message": f"locked source {predicate} was changed"})
    space = blocking.get("space") if isinstance(blocking.get("space"), dict) else {}
    canonical_space = _merge_space({}, scene_canonical)
    known = set(_unique((space.get("anchors") or []) + (space.get("zones") or []) + (canonical_space.get("anchors") or []) + (canonical_space.get("zones") or [])))
    source_anchor_subjects = {_name(fact.get("subject_id")): fact.get("value") for fact in facts if _name(fact.get("predicate")) == "anchor"}
    for participant in participants:
        if not isinstance(participant, dict):
            errors.append({"code": "PARTICIPANT_INVALID", "severity": "blocker", "message": "participant must be an object"}); continue
        target_obj = participant.get("eyeline_target") if isinstance(participant.get("eyeline_target"), dict) else {}
        target = _name(target_obj.get("value"))
        if target and target not in ids and target not in known and target not in {"scene_action", "camera"}:
            errors.append({"code": "INVALID_EYELINE_TARGET", "severity": "blocker", "target_id": _name(participant.get("character_id")), "message": f"eyeline target does not exist: {target}"})
        position = participant.get("start_position") if isinstance(participant.get("start_position"), dict) else {}
        if position.get("authority") not in SPATIAL_AUTHORITIES:
            errors.append({"code": "SPATIAL_AUTHORITY_INVALID", "severity": "blocker", "target_id": _name(participant.get("character_id")), "message": "participant spatial fields require a recognized authority"})
        if position.get("authority") == SOURCE_FACT and position.get("value") is None:
            errors.append({"code": "SOURCE_POSITION_EMPTY", "severity": "blocker", "target_id": _name(participant.get("character_id")), "message": "SOURCE_FACT position cannot be empty"})
        subject = _name(participant.get("character_id"))
        if position.get("authority") == SOURCE_FACT and subject in source_anchor_subjects and known and source_anchor_subjects[subject] not in known:
            errors.append({"code": "INVALID_ANCHOR", "severity": "blocker", "target_id": _name(participant.get("character_id")), "message": f"source anchor does not exist: {position.get('value')}"})
        for field in ("facing", "eyeline_target", "screen_side"):
            value = participant.get(field)
            if isinstance(value, dict) and value.get("authority") not in SPATIAL_AUTHORITIES:
                errors.append({"code": "SPATIAL_AUTHORITY_INVALID", "severity": "blocker", "target_id": subject, "message": f"{field} has an unknown authority"})
    axis = blocking.get("camera_axis") if isinstance(blocking.get("camera_axis"), dict) else {}
    if _name(axis.get("subject_a")) not in ids or (_name(axis.get("subject_b")) and _name(axis.get("subject_b")) not in ids):
        errors.append({"code": "INVALID_AXIS_SUBJECT", "severity": "blocker", "message": "camera axis subjects must be participants"})
    if axis.get("crossed_axis") is True or axis.get("axis_violation") is True:
        errors.append({"code": "AXIS_VIOLATION", "severity": "blocker", "message": "camera placement crosses the established 180-degree axis"})
    for participant in participants:
        side = participant.get("screen_side") if isinstance(participant.get("screen_side"), dict) else {}
        if side and side.get("authority") != DERIVED_CONSTRAINT:
            warnings.append({"code": "SCREEN_SIDE_AUTHORITY_INVALID", "severity": "warning", "message": "screen side should be a derived constraint"})
    if previous_blocking:
        previous_axis = previous_blocking.get("camera_axis") if isinstance(previous_blocking.get("camera_axis"), dict) else {}
        if previous_axis.get("preferred_side") and axis.get("preferred_side") and previous_axis.get("preferred_side") != axis.get("preferred_side"):
            warnings.append({"code": "AXIS_SIDE_CHANGE", "severity": "warning", "message": "camera side changed between adjacent scenes"})
    for unresolved in blocking.get("unresolved_facts", []) if isinstance(blocking.get("unresolved_facts"), list) else []:
        errors.append({**unresolved, "code": unresolved.get("code") or "SPATIAL_FACT_UNRESOLVED", "severity": "blocker"})
    for conflict in blocking.get("conflicts", []) if isinstance(blocking.get("conflicts"), list) else []:
        errors.append({**conflict, "code": conflict.get("code") or "FACT_SPATIAL_CONFLICT", "severity": "blocker"})
    return {"status": "qualified" if not errors else "blocked", "errors": errors, "warnings": warnings, "blocker_count": len(errors), "warning_count": len(warnings)}


def build_scene_blocking_v2(*, scene: dict[str, Any], treatment: dict[str, Any], source_script_hash: str = "", scene_canonical: dict[str, Any] | None = None, fact_snapshot: dict[str, Any] | None = None, previous_blocking: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence = extract_spatial_evidence(scene=scene, treatment=treatment, scene_canonical=scene_canonical, fact_snapshot=fact_snapshot)
    plan = plan_director_spatial(evidence=evidence, treatment=treatment, previous_blocking=previous_blocking)
    candidate = {**plan, "scene_name": _name(scene.get("name") or treatment.get("scene_name")) or "未命名场景", "scene_id": _name(scene.get("scene_id") or treatment.get("scene_id") or scene.get("id")), "source_spatial_facts": evidence["source_spatial_facts"], "unresolved_facts": evidence["unresolved_facts"], "conflicts": evidence["conflicts"]}
    validation = validate_scene_blocking(candidate, scene_canonical=scene_canonical, previous_blocking=previous_blocking)
    unknowns = [str(item.get("message") or item.get("code")) for item in validation["errors"] if item.get("severity") == "blocker"]
    fingerprint_payload = {key: value for key, value in candidate.items() if key != "validation"}
    evidence_fingerprint = hashlib.sha256(_canonical({"source_script_hash": source_script_hash, "payload": fingerprint_payload}).encode("utf-8")).hexdigest()
    beats = treatment.get("beat_map") if isinstance(treatment.get("beat_map"), list) else []
    return {
        **candidate, "schema_version": "scene_blocking_v2",
        "beat_transitions": [{"beat_id": _name(beat.get("beat_id")) or f"B{idx:02d}", "event": _name(beat.get("event")), "blocking_change": "preserve_existing_spatial_relationship", "entry_state": "same_as_previous" if idx > 1 else "scene_start", "exit_state": "same_as_next"} for idx, beat in enumerate(beats, start=1) if isinstance(beat, dict)],
        "spatial_rules": ["locked_source_fact_is_immutable", "creative_choice_must_be_labeled", "derived_constraints_are_program_validated", "preserve_screen_direction_without_declared_transition"],
        "unknowns": unknowns, "treatment_fingerprint": _name(treatment.get("prompt_fingerprint")), "source_script_hash": source_script_hash,
        "evidence_fingerprint": evidence_fingerprint, "validation": validation,
        "model_info": {"mode": "deterministic_spatial_authority_v2", "llm_called": False}, "status": "needs_information" if validation["status"] == "blocked" else "ready_for_review",
    }


def _build_scene_blocking_v1(*, scene: dict[str, Any], treatment: dict[str, Any], source_script_hash: str = "") -> dict[str, Any]:
    """Original V1 behavior retained for old creative-draft callers."""
    scene_name = str(scene.get("name") or treatment.get("scene_name") or "未命名场景").strip()
    intents = treatment.get("character_intents") if isinstance(treatment.get("character_intents"), dict) else {}
    by_key = _blocking_index(scene)
    participants, unknowns = [], []
    for character_id, intent in intents.items():
        intent = intent if isinstance(intent, dict) else {}
        name = str(intent.get("name") or character_id)
        block = by_key.get(str(character_id)) or by_key.get(name)
        position = str((block or {}).get("position") or (block or {}).get("screen_position") or (block or {}).get("blocking") or "").strip()
        facing = str((block or {}).get("facing") or (block or {}).get("screen_direction") or "").strip()
        anchor = str((block or {}).get("anchor") or (block or {}).get("spatial_anchor") or "").strip()
        if not position:
            unknowns.append(f"未声明 {name} 的画面位置")
        participants.append({"character_id": str(character_id), "name": name, "position": position or None, "facing": facing or None, "anchor": anchor or None, "source": "script_declared" if block else "missing"})
    beats = treatment.get("beat_map") if isinstance(treatment.get("beat_map"), list) else []
    transitions = [{"beat_id": str(beat.get("beat_id") or f"B{index + 1:02d}"), "event": str(beat.get("event") or ""), "blocking_change": "preserve_existing_spatial_relationship", "entry_state": "same_as_previous" if index else "scene_start", "exit_state": "same_as_next"} for index, beat in enumerate(beats) if isinstance(beat, dict)]
    payload = {"scene_name": scene_name, "participants": participants, "beat_transitions": transitions, "spatial_rules": ["locked_asset_identity_is_immutable", "do_not_change_screen_direction_without_declared_transition", "do_not_invent_character_position_when_script_is_silent", "carry_forward_unresolved_positions_to_shot_plan_review"], "unknowns": unknowns, "treatment_fingerprint": str(treatment.get("prompt_fingerprint") or ""), "source_script_hash": source_script_hash}
    return {**payload, "status": "needs_information" if unknowns else "ready_for_review", "evidence_fingerprint": hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(), "model_info": {"mode": "shadow_deterministic", "llm_called": False}, "schema_version": "scene_blocking_v1"}


def build_scene_blocking(*, scene: dict[str, Any], treatment: dict[str, Any], source_script_hash: str = "", schema_version: str = "scene_blocking_v1", **kwargs: Any) -> dict[str, Any]:
    """Compatibility entrypoint; opt into V2 explicitly."""
    if str(schema_version).lower() in {"scene_blocking_v2", "v2"}:
        return build_scene_blocking_v2(scene=scene, treatment=treatment, source_script_hash=source_script_hash, **kwargs)
    return _build_scene_blocking_v1(scene=scene, treatment=treatment, source_script_hash=source_script_hash)


def repair_scene_blocking(candidate: dict[str, Any], *, max_attempts: int = 2) -> dict[str, Any]:
    """Bounded local repair for creative blocking diagnostics."""
    current = copy.deepcopy(candidate)

    def validator(value: dict[str, Any]) -> list[dict[str, Any]]:
        report = validate_scene_blocking(value)
        issues = []
        for error in report["errors"]:
            code = error.get("code")
            issue = {**error, "target_layer": "BLOCKING", "blocking": True}
            if code == "INVALID_EYELINE_TARGET":
                target = _name(error.get("target_id"))
                for idx, participant in enumerate(value.get("participants", [])):
                    if _name(participant.get("character_id")) == target:
                        issue["patch"] = [{"op": "replace", "path": f"/participants/{idx}/eyeline_target/value", "value": "scene_action"}]
                        break
            elif code == "AXIS_SIDE_CHANGE":
                issue["patch"] = [{"op": "replace", "path": "/camera_axis/preferred_side", "value": "center"}]
            elif code == "AXIS_VIOLATION":
                issue["patch"] = [{"op": "replace", "path": "/camera_axis/axis_violation", "value": False}, {"op": "replace", "path": "/camera_axis/crossed_axis", "value": False}]
            issues.append(issue)
        return issues

    return qualify_candidate(current, [validator], max_attempts=max_attempts)
