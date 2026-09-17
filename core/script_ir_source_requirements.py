"""ScriptIR source-requirement contract and deterministic compiler.

The contract is derived from the current ``core.script_ir`` builder and
validator.  It intentionally does not consume MissingFactManifest: that
manifest describes downstream production needs and cannot define ScriptIR's
source gate.  This module is provider-free and has no persistence side
effects.
"""
from __future__ import annotations

import copy
from typing import Any

from core.fact_coverage import fingerprint

CONTRACT_SCHEMA_VERSION = "script_ir_source_requirement_contract_v1"
REQUIREMENT_SET_SCHEMA_VERSION = "script_ir_source_requirement_set_v1"
STRUCTURAL_METADATA_SCHEMA_VERSION = "script_ir_structural_metadata_requirement_v1"

# These are the only ScriptIR source requirements justified by current
# consumers.  Scene ids are generated deterministically and therefore live in
# the structural metadata lane, not FactSnapshot.
_CONTRACT_REQUIREMENTS: tuple[dict[str, Any], ...] = (
    {
        "requirement_id": "SIR_SCENES_PRESENT",
        "predicate": "scene_existence",
        "semantic_definition": "The episode contains at least one source scene.",
        "consumer_field": "scenes",
        "consumer_invariant": "core.script_ir.validate_script_ir:SCENES_REQUIRED",
        "authority_class": "SOURCE_FACT",
        "value_schema": {"type": "integer", "minimum": 1},
        "scope_policy": "episode",
        "required": True,
        "optional": False,
        "blocking": True,
        "evidence_requirement": {"direct_evidence_required": True, "source_anchor_required": True},
        "derivation_policy": {"allowed": False, "reason": "scene existence cannot be inferred"},
        "provenance_requirement": {"allowed": ["source_text", "locked_fact", "approved_fact"], "minimum": "source_anchor"},
        "expansion": "episode",
    },
    {
        "requirement_id": "SIR_SCENE_NAME",
        "predicate": "scene_identity",
        "semantic_definition": "Every normalized scene has a source-supported non-empty name.",
        "consumer_field": "scenes[].name",
        "consumer_invariant": "core.script_ir.validate_script_ir:SCENE_NAME_REQUIRED/SCENE_NAME_DUPLICATE",
        "authority_class": "SOURCE_FACT",
        "value_schema": {"type": "string", "minLength": 1},
        "scope_policy": "scene",
        "required": True,
        "optional": False,
        "blocking": True,
        "evidence_requirement": {"direct_evidence_required": True, "source_anchor_required": True},
        "derivation_policy": {"allowed": False, "reason": "placeholder names would lose source identity"},
        "provenance_requirement": {"allowed": ["source_text", "locked_fact", "approved_fact"], "minimum": "source_anchor"},
        "expansion": "scene",
    },
    {
        "requirement_id": "SIR_BEAT_EVENT",
        "predicate": "event_occurrence",
        "semantic_definition": "A declared beat may carry a source event description.",
        "consumer_field": "scenes[].beats[].event",
        "consumer_invariant": "core.script_ir.validate_script_ir:SCENE_BEATS_EMPTY (warning only)",
        "authority_class": "SOURCE_FACT",
        "value_schema": {"type": "string"},
        "scope_policy": "scene_beat",
        "required": False,
        "optional": True,
        "blocking": False,
        "evidence_requirement": {"direct_evidence_required": True, "source_anchor_required": False},
        "derivation_policy": {"allowed": False, "reason": "event text is source content, not a model inference"},
        "provenance_requirement": {"allowed": ["source_text", "locked_fact", "approved_fact"], "minimum": "source_anchor_if_present"},
        "expansion": "beat_when_declared",
    },
)

_STRUCTURAL_REQUIREMENTS: tuple[dict[str, Any], ...] = (
    {
        "requirement_id": "SIR_SCENE_ID",
        "field": "scenes[].scene_id",
        "consumer": "build_script_ir:scene_id + validate_script_ir:SCENE_ID_INVALID",
        "required": True,
        "derivation_policy": "deterministic E{episode:02d}_SC{ordinal:03d}; explicit source id is preserved",
        "provenance": "structural_metadata",
    },
    {
        "requirement_id": "SIR_EPISODE_NUMBER",
        "field": "episode",
        "consumer": "build_script_ir:episode",
        "required": True,
        "derivation_policy": "request scope, not a story fact",
        "provenance": "request_context",
    },
)

_DERIVED_POLICIES: tuple[dict[str, Any], ...] = (
    {
        "predicate": "scene_identity",
        "allowed": False,
        "supporting_source_anchors_required": True,
        "provenance": "direct_only",
        "reason": "the builder's fallback name is not authoritative source identity",
    },
    {
        "predicate": "event_occurrence",
        "allowed": False,
        "supporting_source_anchors_required": True,
        "provenance": "direct_only",
        "reason": "ScriptIR does not authorize inferred events",
    },
)


def script_ir_source_requirement_contract() -> dict[str, Any]:
    """Return the versioned, immutable contract as a defensive copy."""

    payload = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "script_ir_schema_version": "script_ir_v1",
        "consumer_module": "core.script_ir",
        "requirements": copy.deepcopy(list(_CONTRACT_REQUIREMENTS)),
        "structural_metadata_requirements": copy.deepcopy(list(_STRUCTURAL_REQUIREMENTS)),
        "derived_fact_policies": copy.deepcopy(list(_DERIVED_POLICIES)),
        "provider_calls": 0,
    }
    payload["fingerprint"] = fingerprint(payload)
    return payload


# Public aliases make the contract easy to consume from API/report code while
# retaining the descriptive function name used by the recanary.
get_script_ir_source_requirement_contract = script_ir_source_requirement_contract


def audit_script_ir_consumers() -> dict[str, Any]:
    """Describe what the current implementation consumes and validates."""

    result = {
        "schema_version": "script_ir_consumer_audit_v1",
        "status": "SCRIPT_IR_CONSUMER_AUDIT",
        "schema": {
            "top_level_fields": ["schema_version", "book_id", "episode", "fact_snapshot_id", "title", "episode_objective", "characters", "scenes", "payload_hash"],
            "scene_fields": ["scene_id", "name", "location_id", "location_name", "time_of_day", "weather", "participants", "beats", "actions", "dialogues", "state_in", "state_out", "required_visual_proofs", "blocking_hints", "character_blocking", "props", "asset_mentions"],
            "beat_fields": ["beat_id", "type", "event", "dramatic_function", "information_change", "emotion_change"],
        },
        "source_fields": [
            {"field": "scenes", "reason": "validated non-empty and passed to every downstream stage"},
            {"field": "scenes[].name", "reason": "validated required and unique; used as scene identity by treatment/blocking"},
            {"field": "scenes[].beats[].event", "reason": "preserved as source event; empty beats are warning-only"},
            {"field": "title", "reason": "preserved/rendered but not validation-blocking"},
            {"field": "episode_objective", "reason": "preserved/rendered but not validation-blocking"},
            {"field": "characters", "reason": "preserved and projected to asset registry/treatment; not ScriptIR validation-blocking"},
        ],
        "deterministic_transforms": [
            {"field": "scene_id", "rule": "explicit id or E{episode:02d}_SC{ordinal:03d}"},
            {"field": "beat_id", "rule": "explicit beat_id/id or {scene_id}_B{ordinal:02d}"},
            {"field": "location_name", "rule": "explicit location_name or scene name"},
            {"field": "legacy_markdown", "rule": "best-effort headings/beats reconstruction; always needs_review"},
            {"field": "payload_hash", "rule": "canonical SHA-256"},
        ],
        "later_authoring": [
            "visual identity", "wardrobe", "production geometry", "camera", "lighting", "scene blocking", "production prop continuity", "shot design",
        ],
        "blocking_missing": [
            {"requirement_id": "SIR_SCENES_PRESENT", "failure": "SCENES_REQUIRED"},
            {"requirement_id": "SIR_SCENE_NAME", "failure": "SCENE_NAME_REQUIRED or duplicate identity"},
        ],
        "optional_or_nonblocking": ["title", "episode_objective", "characters", "participants", "dialogues", "actions", "state_in", "state_out", "required_visual_proofs", "blocking_hints", "character_blocking", "props", "asset_mentions", "beat event text"],
        "provenance_requirements": "blocking source requirements require source anchor or an approved FactSnapshot record; structural metadata uses request_context or deterministic_transform",
        "consumer_traceability": copy.deepcopy(list(_CONTRACT_REQUIREMENTS)),
        "provider_calls": 0,
    }
    result["fingerprint"] = fingerprint(result)
    return result


def _text(value: Any) -> str:
    return str(value or "").strip()


def _scene_list(payload: Any) -> list[dict[str, Any]]:
    source = payload if isinstance(payload, dict) else {}
    return [row for row in (source.get("scenes") if isinstance(source.get("scenes"), list) else []) if isinstance(row, dict)]


def _requirement(*, template: dict[str, Any], fact_key: str, subject_type: str, subject_id: str, scope: str, expected_value: Any, source_value: Any = None, source_path: str = "") -> dict[str, Any]:
    return {
        "requirement_id": fact_key,
        "contract_requirement_id": template["requirement_id"],
        "fact_key": fact_key,
        "predicate": template["predicate"],
        "semantic_definition": template["semantic_definition"],
        "consumer": template["consumer_invariant"],
        "consumer_field": template["consumer_field"],
        "authority_class": template["authority_class"],
        "subject_type": subject_type,
        "subject_id": subject_id,
        "scope": scope,
        "required": bool(template["required"]),
        "optional": bool(template["optional"]),
        "blocking": bool(template["blocking"]),
        "severity": "blocking" if template["blocking"] else "optional",
        "value_schema": copy.deepcopy(template["value_schema"]),
        "scope_policy": template["scope_policy"],
        "evidence_requirement": copy.deepcopy(template["evidence_requirement"]),
        "derivation_policy": copy.deepcopy(template["derivation_policy"]),
        "provenance_requirement": copy.deepcopy(template["provenance_requirement"]),
        "expected_value": copy.deepcopy(expected_value),
        "source_value": copy.deepcopy(source_value),
        "source_path": source_path,
        "source_evidence_refs": [source_path] if source_path else [],
    }


def compile_script_ir_source_requirements(*, source_structure: dict[str, Any] | None = None, script_ir: dict[str, Any] | None = None, fact_snapshot: dict[str, Any] | None = None, source_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compile requirements from ScriptIR consumers and source structure.

    ``fact_snapshot`` is accepted only to carry non-authoritative evidence
    fingerprints into the result; requirement discovery never reads legacy
    MissingFactManifest.  The returned set is deterministic for equal inputs.
    """

    contract = script_ir_source_requirement_contract()
    payload = source_structure if isinstance(source_structure, dict) else (script_ir if isinstance(script_ir, dict) else {})
    scenes = _scene_list(payload)
    templates = {row["requirement_id"]: row for row in contract["requirements"]}
    requirements: list[dict[str, Any]] = []
    if not scenes:
        requirements.append(_requirement(template=templates["SIR_SCENES_PRESENT"], fact_key="episode|scenes|scene_existence|episode", subject_type="episode", subject_id=_text(payload.get("episode")) or "episode", scope="episode", expected_value={"minimum": 1}, source_path="scenes"))
    else:
        requirements.append(_requirement(template=templates["SIR_SCENES_PRESENT"], fact_key="episode|scenes|scene_existence|episode", subject_type="episode", subject_id=_text(payload.get("episode")) or "episode", scope="episode", expected_value={"minimum": 1, "actual": len(scenes)}, source_value=len(scenes), source_path="scenes"))
        names_seen: set[str] = set()
        for index, scene in enumerate(scenes, 1):
            name = _text(scene.get("name") or scene.get("scene_name"))
            subject_id = name or f"scene-{index:03d}"
            requirements.append(_requirement(template=templates["SIR_SCENE_NAME"], fact_key=f"scene|{subject_id}|scene_identity|scene", subject_type="scene", subject_id=subject_id, scope="scene", expected_value=name, source_value=name, source_path=f"scenes[{index - 1}].name"))
            names_seen.add(name)
            beats = scene.get("beats") if isinstance(scene.get("beats"), list) else []
            for beat_index, beat in enumerate(beats, 1):
                if not isinstance(beat, dict):
                    continue
                event = _text(beat.get("event") or beat.get("description") or beat.get("content"))
                if event:
                    beat_id = _text(beat.get("beat_id") or beat.get("id")) or f"B{beat_index:02d}"
                    requirements.append(_requirement(template=templates["SIR_BEAT_EVENT"], fact_key=f"beat|{subject_id}:{beat_id}|event_occurrence|scene_beat", subject_type="beat", subject_id=f"{subject_id}:{beat_id}", scope="scene_beat", expected_value=event, source_value=event, source_path=f"scenes[{index - 1}].beats[{beat_index - 1}].event"))

    # Duplicate names are rejected by validate_script_ir and therefore remain
    # a formal source blocker even though each individual name is non-empty.
    names = [_text(scene.get("name") or scene.get("scene_name")) for scene in scenes]
    duplicate_names = {name for name in names if name and names.count(name) > 1}
    if duplicate_names:
        for row in requirements:
            if row.get("contract_requirement_id") == "SIR_SCENE_NAME" and row.get("source_value") in duplicate_names:
                row["source_conflict"] = "duplicate_scene_name"

    structural = []
    for index, scene in enumerate(scenes, 1):
        explicit = _text(scene.get("scene_id"))
        structural.append({"requirement_id": f"SIR_SCENE_ID[{index}]", "template_id": "SIR_SCENE_ID", "field": f"scenes[{index - 1}].scene_id", "expected_value": explicit or f"E{int(payload.get('episode') or 1):02d}_SC{index:03d}", "satisfied_by": "explicit_source" if explicit else "deterministic_transform", "provenance": "source_structure" if explicit else "deterministic_transform"})
    structural.append({"requirement_id": "SIR_EPISODE_NUMBER", "template_id": "SIR_EPISODE_NUMBER", "field": "episode", "expected_value": payload.get("episode"), "satisfied_by": "request_context", "provenance": "request_context"})
    result = {
        "schema_version": REQUIREMENT_SET_SCHEMA_VERSION,
        "contract_schema_version": CONTRACT_SCHEMA_VERSION,
        "requirements": requirements,
        "structural_metadata_requirements": structural,
        "source_metadata": copy.deepcopy(source_metadata or {}),
        "fact_snapshot_fingerprint": (fact_snapshot or {}).get("payload_hash") or (fact_snapshot or {}).get("source_fingerprint") or "",
        "consumer_audit": audit_script_ir_consumers(),
        "provider_calls": 0,
    }
    result["requirement_count"] = len(requirements)
    result["blocking_requirement_count"] = sum(1 for row in requirements if row["blocking"])
    result["optional_requirement_count"] = sum(1 for row in requirements if row["optional"])
    result["derived_requirement_count"] = sum(1 for row in requirements if row["authority_class"] == "DERIVED_SOURCE_FACT")
    result["fingerprint"] = fingerprint(result)
    return result


compile_script_ir_source_requirement_set = compile_script_ir_source_requirements


def evaluate_script_ir_source_coverage(requirement_set: dict[str, Any], records: list[dict[str, Any]] | None = None, *, source_evidence_index: dict[str, Any] | None = None, allow_source_structure_fallback: bool = True) -> dict[str, Any]:
    """Evaluate only formal ScriptIR requirements against authoritative records."""

    rows = [row for row in (records or []) if isinstance(row, dict)]
    coverage: list[dict[str, Any]] = []
    for requirement in requirement_set.get("requirements", []) if isinstance(requirement_set, dict) else []:
        matches = [row for row in rows if str(row.get("fact_key") or "") == requirement.get("fact_key") or (str(row.get("predicate") or "") == requirement.get("predicate") and str(row.get("subject_id") or "") == requirement.get("subject_id"))]
        satisfied = False
        reason = "ABSENT"
        if requirement.get("source_conflict"):
            reason = "CONFLICTED"
        elif matches:
            values = {repr(row.get("value")) for row in matches}
            if len(values) > 1:
                reason = "CONFLICTED"
            elif any(str(row.get("status") or "").lower() == "confirmed" and row.get("evidence") for row in matches):
                satisfied, reason = True, None
            else:
                reason = "INSUFFICIENT_EVIDENCE"
        elif allow_source_structure_fallback and requirement.get("source_value") not in (None, "", [], {}) and requirement.get("source_evidence_refs") and not requirement.get("source_conflict"):
            # Source structure is itself an explicit source anchor when the
            # caller supplies it; this is not an inferred FactSnapshot claim.
            satisfied, reason = True, None
        coverage.append({"requirement_id": requirement.get("requirement_id"), "contract_requirement_id": requirement.get("contract_requirement_id"), "fact_key": requirement.get("fact_key"), "blocking": bool(requirement.get("blocking")), "optional": bool(requirement.get("optional")), "coverage_status": "COVERED" if satisfied else ("OPTIONAL_MISSING" if requirement.get("optional") else reason), "reason": reason, "supporting_fact_ids": [str(row.get("fact_id")) for row in matches if row.get("fact_id") is not None], "source_evidence_refs": list(requirement.get("source_evidence_refs") or [])})
    blocking_rows = [row for row in coverage if row["blocking"]]
    counts = {key: sum(1 for row in blocking_rows if row["coverage_status"] == value) for key, value in (("covered", "COVERED"), ("missing", "ABSENT"), ("ambiguous", "AMBIGUOUS"), ("conflicted", "CONFLICTED"), ("invalid", "INVALID"))}
    counts["derived_covered"] = sum(1 for row in coverage if row["coverage_status"] == "COVERED" and any(req.get("requirement_id") == row["requirement_id"] and req.get("authority_class") == "DERIVED_SOURCE_FACT" for req in requirement_set.get("requirements", [])))
    return {"schema_version": "script_ir_source_coverage_v1", "status": "SCRIPT_IR_SOURCE_CONTRACT_COVERAGE_SUFFICIENT" if not any(row["coverage_status"] != "COVERED" for row in blocking_rows) and bool(requirement_set.get("requirements")) else ("REQUIREMENT_CONTRACT_EMPTY_ERROR" if not requirement_set.get("requirements") else "SCRIPT_IR_SOURCE_CONTRACT_COVERAGE_INSUFFICIENT"), "counts": counts, "coverage": coverage, "source_fact_only_missing_manifest": {"schema_version": "missing_fact_manifest_v1", "status": "FACT_COVERAGE_SUFFICIENT" if not any(row["coverage_status"] != "COVERED" for row in blocking_rows) else "FACT_COVERAGE_INSUFFICIENT", "items": [row for row in coverage if row["blocking"] and row["coverage_status"] != "COVERED"], "count": sum(1 for row in coverage if row["blocking"] and row["coverage_status"] != "COVERED")}, "source_evidence_index_fingerprint": (source_evidence_index or {}).get("fingerprint", ""), "provider_calls": 0}


__all__ = ["CONTRACT_SCHEMA_VERSION", "REQUIREMENT_SET_SCHEMA_VERSION", "STRUCTURAL_METADATA_SCHEMA_VERSION", "script_ir_source_requirement_contract", "get_script_ir_source_requirement_contract", "audit_script_ir_consumers", "compile_script_ir_source_requirements", "compile_script_ir_source_requirement_set", "evaluate_script_ir_source_coverage"]
