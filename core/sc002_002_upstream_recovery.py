"""Provider-free, exact upstream authority inspection for SC002_002.

The recovery phase must identify a shot from the current ShotPlan payload and
its authority pointer.  This module deliberately does not infer identity from
documents, filenames, provider URLs, or a guessed book id, and it never writes
production rows.
"""

from __future__ import annotations

import json
from typing import Any

from models import (
    DirectorTreatment,
    DirectorTreatmentAuthority,
    DirectorTreatmentPointer,
    FactSnapshot,
    PromptIRPointer,
    PromptIRVersion,
    SceneBlocking,
    SceneBlockingAuthority,
    SceneBlockingPointer,
    Script,
    ScriptIRVersion,
    ShotPlan,
    ShotPlanAuthority,
    ShotPlanPointer,
    StoryboardMaterializationPointer,
    StoryboardMaterializationSet,
    StoryboardShot,
)


TARGET_PLAN_SHOT_ID = "SH_E01_SC002_002"


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def exact_shot_plan_payload_matches(rows: list[Any], target_plan_shot_id: str = TARGET_PLAN_SHOT_ID) -> list[dict[str, Any]]:
    """Return only exact structured plan_shot_id matches, never substrings."""
    target = str(target_plan_shot_id or "").strip()
    matches: list[dict[str, Any]] = []
    for row in rows:
        shots = _json(getattr(row, "shots", "[]"), [])
        if not isinstance(shots, list):
            continue
        for index, shot in enumerate(shots):
            if isinstance(shot, dict) and str(shot.get("plan_shot_id") or "").strip() == target:
                matches.append({"row": row, "shot": shot, "shot_index": index})
    return matches


def _shot_plan_authority_projection(session: Any, row: Any) -> dict[str, Any]:
    from core.shot_plan_authority import shot_plan_payload_from_row

    pointer = session.query(ShotPlanPointer).filter_by(
        book_id=row.book_id, episode=row.episode, scene_id=str(row.scene_id or ""), shot_plan_id=row.id
    ).first()
    authority = session.query(ShotPlanAuthority).filter_by(shot_plan_id=row.id).first()
    pointer_matches = bool(pointer and int(pointer.shot_plan_id) == int(row.id) and int(pointer.plan_revision) == int(row.revision))
    authority_matches = bool(
        authority
        and str(authority.payload_hash or "") == str(row.payload_hash or "")
        and str(authority.stale_status or "") == "FRESH"
        and str(authority.qualification_state or "") == "AUTHORITY_BOUND"
        and pointer
        and str(pointer.authority_envelope_fingerprint or "") == str(authority.envelope_fingerprint or "")
    )
    payload = shot_plan_payload_from_row(row)
    phase_c_ready = payload.get("phase_c_semantic_ready") is True
    production_ready = bool(
        pointer_matches
        and authority_matches
        and str(pointer.qualification_state or "") == "PRODUCTION_QUALIFIED"
        and str(row.qualification_state or "") == "PRODUCTION_QUALIFIED"
        and str(row.stale_status or "") == "FRESH"
        and str(row.production_status or "") in {"ready", "production_ready", "qualified"}
        and phase_c_ready
    )
    return {
        "shot_plan_id": row.id,
        "book_id": row.book_id,
        "episode": row.episode,
        "scene_id": row.scene_id,
        "scene_name": row.scene_name,
        "revision": row.revision,
        "status": row.status,
        "production_status": row.production_status,
        "qualification_state": row.qualification_state,
        "stale_status": row.stale_status,
        "payload_hash": row.payload_hash,
        "pointer": {
            "id": getattr(pointer, "id", None),
            "shot_plan_id": getattr(pointer, "shot_plan_id", None),
            "plan_revision": getattr(pointer, "plan_revision", None),
            "authority_envelope_fingerprint": getattr(pointer, "authority_envelope_fingerprint", None),
            "qualification_state": getattr(pointer, "qualification_state", None),
            "matches_row": pointer_matches,
        },
        "authority": {
            "id": getattr(authority, "id", None),
            "envelope_fingerprint": getattr(authority, "envelope_fingerprint", None),
            "qualification_state": getattr(authority, "qualification_state", None),
            "stale_status": getattr(authority, "stale_status", None),
            "matches_row": authority_matches,
        },
        "authoritative_current": production_ready,
        "phase_c_semantic_ready": phase_c_ready,
    }


def resolve_exact_canonical_identity(session: Any, target_plan_shot_id: str = TARGET_PLAN_SHOT_ID) -> dict[str, Any]:
    """Resolve the exact current ShotPlan identity without mutating state."""
    rows = session.query(ShotPlan).all()
    exact = exact_shot_plan_payload_matches(rows, target_plan_shot_id)
    projections = [_shot_plan_authority_projection(session, item["row"]) | {"shot_index": item["shot_index"]} for item in exact]
    authoritative = [item for item in projections if item["authoritative_current"]]
    if len(authoritative) == 1:
        return {"status": "EXACT_ONE", "target_plan_shot_id": target_plan_shot_id, "matches": projections, "authoritative_match": authoritative[0]}
    if len(authoritative) > 1:
        return {"status": "AMBIGUOUS", "target_plan_shot_id": target_plan_shot_id, "matches": projections, "authoritative_matches": authoritative}
    return {"status": "ZERO", "target_plan_shot_id": target_plan_shot_id, "matches": projections, "authoritative_matches": []}


def inspect_script_ir_state(session: Any, *, target_book_id: int | None = None, target_episode: int | None = None) -> dict[str, Any]:
    """Inspect actual Script → ScriptIR → FactSnapshot pointers.

    When identity is unresolved, the result is explicitly unscoped rather than
    pretending the target has no ScriptIR.  Counts and pointer integrity are
    still calculated from the live database.
    """
    scripts = session.query(Script).all()
    current_rows: list[dict[str, Any]] = []
    for script in scripts:
        if target_book_id is not None and int(script.book_id) != int(target_book_id):
            continue
        if target_episode is not None and int(script.episode) != int(target_episode):
            continue
        ir = session.query(ScriptIRVersion).filter_by(id=script.current_script_ir_version_id).first() if script.current_script_ir_version_id else None
        envelope = _json(getattr(ir, "authority_envelope_json", "{}"), {}) if ir else {}
        fact = session.query(FactSnapshot).filter_by(id=getattr(ir, "source_fact_snapshot_id", None)).first() if ir and getattr(ir, "source_fact_snapshot_id", None) else None
        current_rows.append({
            "script_id": script.id,
            "book_id": script.book_id,
            "episode": script.episode,
            "script_status": script.status,
            "script_production_status": script.production_status,
            "current_script_ir_version_id": script.current_script_ir_version_id,
            "script_ir": {
                "id": getattr(ir, "id", None),
                "revision": getattr(ir, "revision", None),
                "status": getattr(ir, "status", None),
                "qualification_state": getattr(ir, "qualification_state", None),
                "stale_status": getattr(ir, "stale_status", None),
                "payload_hash": getattr(ir, "payload_hash", None),
                "authority_fingerprint": envelope.get("envelope_fingerprint") if isinstance(envelope, dict) else None,
                "authority_envelope_valid_shape": bool(isinstance(envelope, dict) and envelope.get("schema_version")),
                "fact_snapshot_id": getattr(ir, "source_fact_snapshot_id", None),
            },
            "fact_snapshot": {
                "id": getattr(fact, "id", None),
                "revision": getattr(fact, "revision", None),
                "status": getattr(fact, "status", None),
                "payload_hash": getattr(fact, "payload_hash", None),
            },
        })
    production = [row for row in current_rows if row["script_ir"]["status"] == "production_qualified" and row["script_ir"]["stale_status"] == "FRESH"]
    return {
        "scope": "RESOLVED" if target_book_id is not None and target_episode is not None else "UNSCOPED_UNTIL_IDENTITY_RESOLVED",
        "script_count": len(current_rows),
        "current_pointer_count": sum(1 for row in current_rows if row["current_script_ir_version_id"]),
        "production_qualified_current_count": len(production),
        "rows": current_rows,
    }


def inspect_materialization_and_prompt_ir(session: Any, *, book_id: int, episode: int, scene_id: str, plan_shot_id: str) -> dict[str, Any]:
    """Inspect the canonical materialization and IMAGE PromptIR foreign-key chain."""
    pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
    set_row = session.query(StoryboardMaterializationSet).filter_by(id=getattr(pointer, "materialization_set_id", None)).first() if pointer else None
    rows = session.query(StoryboardShot).filter_by(book_id=book_id, episode=episode, scene_id=scene_id, materialization_set_id=getattr(set_row, "id", None), plan_shot_id=plan_shot_id).all() if set_row else []
    prompt_rows = []
    for shot in rows:
        prompt_pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=shot.id, target_media="IMAGE").first()
        version = session.query(PromptIRVersion).filter_by(id=getattr(prompt_pointer, "prompt_ir_version_id", None)).first() if prompt_pointer else None
        prompt_rows.append({
            "storyboard_shot_id": shot.id,
            "prompt_ir_pointer": {"id": getattr(prompt_pointer, "id", None), "target_media": getattr(prompt_pointer, "target_media", None), "payload_hash": getattr(prompt_pointer, "payload_hash", None)},
            "prompt_ir_version": {"id": getattr(version, "id", None), "payload_hash": getattr(version, "payload_hash", None), "qualification_state": getattr(version, "qualification_state", None), "stale_status": getattr(version, "stale_status", None)},
        })
    return {
        "materialization_pointer": {"id": getattr(pointer, "id", None), "materialization_set_id": getattr(pointer, "materialization_set_id", None), "qualification_state": getattr(pointer, "qualification_state", None)},
        "materialization_set": {"id": getattr(set_row, "id", None), "status": getattr(set_row, "status", None), "stale_status": getattr(set_row, "stale_status", None), "shot_plan_id": getattr(set_row, "shot_plan_id", None), "shot_plan_revision": getattr(set_row, "shot_plan_revision", None), "set_payload_fingerprint": getattr(set_row, "set_payload_fingerprint", None)},
        "storyboard_shot_matches": prompt_rows,
        "exact_storyboard_shot_count": len(rows),
    }


__all__ = ["TARGET_PLAN_SHOT_ID", "exact_shot_plan_payload_matches", "resolve_exact_canonical_identity", "inspect_script_ir_state", "inspect_materialization_and_prompt_ir"]
