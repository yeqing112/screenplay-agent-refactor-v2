"""Provider-free inventory and deterministic selection of a production canary."""

from __future__ import annotations

import json
from typing import Any

from api.prompt_ir_authority_api import _production_asset_authority
from core.storyboard_materializer import validate_current_materialization_authority
from models import (
    DirectorTreatment,
    DirectorTreatmentAuthority,
    DirectorTreatmentPointer,
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
    PromptIRPointer,
    PromptIRVersion,
)


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _fresh(value: Any) -> bool:
    return str(value or "").upper() == "FRESH"


def _authority_ok(row: Any, authority: Any, pointer: Any, *, qualification: str = "PRODUCTION_QUALIFIED") -> bool:
    return bool(
        row and authority and pointer
        and str(getattr(row, "qualification_state", "")) == qualification
        and _fresh(getattr(row, "stale_status", ""))
        and str(getattr(pointer, "qualification_state", "")) == qualification
        and str(getattr(authority, "qualification_state", "")) in {"AUTHORITY_BOUND", qualification}
        and _fresh(getattr(authority, "stale_status", ""))
        and str(getattr(pointer, "authority_envelope_fingerprint", "")) == str(getattr(authority, "envelope_fingerprint", ""))
        and str(getattr(pointer, "shot_plan_id", getattr(pointer, "treatment_id", getattr(pointer, "blocking_id", "")))) == str(getattr(row, "id", ""))
    )


def _script_state(session: Any, book_id: int, episode: int) -> tuple[dict[str, Any], list[str]]:
    scripts = session.query(Script).filter_by(book_id=book_id, episode=episode).all()
    current = [item for item in scripts if item.current_script_ir_version_id]
    if len(current) != 1:
        return {"count": len(scripts), "current_count": len(current), "status": "INVALID"}, ["SCRIPT_CURRENT_POINTER_INVALID"]
    script = current[0]
    ir = session.query(ScriptIRVersion).filter_by(id=script.current_script_ir_version_id, book_id=book_id, episode=episode).first()
    envelope = _json(getattr(ir, "authority_envelope_json", "{}"), {}) if ir else {}
    ok = bool(ir and str(ir.status) == "production_qualified" and str(ir.qualification_state) == "PRODUCTION_QUALIFIED" and _fresh(ir.stale_status) and envelope.get("envelope_fingerprint"))
    details = {"script_id": script.id, "book_id": book_id, "episode": episode, "script_ir_version_id": getattr(ir, "id", None), "revision": getattr(ir, "revision", None), "status": getattr(ir, "status", None), "qualification_state": getattr(ir, "qualification_state", None), "stale_status": getattr(ir, "stale_status", None), "payload_hash": getattr(ir, "payload_hash", None), "authority_fingerprint": envelope.get("envelope_fingerprint"), "status_result": "PASS" if ok else "FAIL"}
    return details, [] if ok else ["SCRIPT_IR_AUTHORITY_INVALID"]


def _asset_gate(session: Any, *, book_id: int, handoff: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    bindings = handoff.get("asset_identity_bindings") if isinstance(handoff.get("asset_identity_bindings"), dict) else {}
    canonical = bindings.get("canonical_asset_identity") if isinstance(bindings.get("canonical_asset_identity"), dict) else bindings
    chars = canonical.get("characters") if isinstance(canonical.get("characters"), list) else []
    props = canonical.get("props") if isinstance(canonical.get("props"), list) else []
    scene = canonical.get("scene") or ""
    result = _production_asset_authority(session, book_id=book_id, handoff=handoff)
    resolved = {str(item.get("asset_type")): item for item in result.get("bindings", []) if isinstance(item, dict)}
    blockers: list[str] = []
    if not scene or "scene" not in resolved:
        blockers.append("ASSET_AUTHORITY_SCENE_MISSING")
    if chars and len([item for item in result.get("bindings", []) if item.get("asset_type") == "character"]) != len(chars):
        blockers.append("ASSET_AUTHORITY_REQUIRED_CHARACTERS_MISSING")
    if props and len([item for item in result.get("bindings", []) if item.get("asset_type") == "prop"]) != len(props):
        blockers.append("ASSET_AUTHORITY_REQUIRED_PROPS_MISSING")
    return {"status": "PASS" if not blockers else "FAIL", "required_character_ids": chars, "required_prop_ids": props, "bindings": result.get("bindings", []), "authority_fingerprint": result.get("authority_fingerprint")}, blockers


def build_canonical_shot_inventory(session: Any) -> list[dict[str, Any]]:
    """Build an auditable inventory; only hard-gate complete shots are candidates."""
    inventory: list[dict[str, Any]] = []
    for pointer in session.query(ShotPlanPointer).all():
        plan = session.query(ShotPlan).filter_by(id=pointer.shot_plan_id, book_id=pointer.book_id, episode=pointer.episode, scene_id=pointer.scene_id).first()
        authority = session.query(ShotPlanAuthority).filter_by(shot_plan_id=getattr(plan, "id", None)).first() if plan else None
        blockers: list[str] = []
        script, script_blockers = _script_state(session, pointer.book_id, pointer.episode)
        blockers.extend(script_blockers)
        plan_ok = _authority_ok(plan, authority, pointer)
        if not plan_ok:
            blockers.append("SHOT_PLAN_AUTHORITY_INVALID")
        treatment_pointer = session.query(DirectorTreatmentPointer).filter_by(book_id=pointer.book_id, episode=pointer.episode, scene_id=pointer.scene_id).first()
        treatment = session.query(DirectorTreatment).filter_by(id=getattr(treatment_pointer, "treatment_id", None)).first() if treatment_pointer else None
        treatment_authority = session.query(DirectorTreatmentAuthority).filter_by(treatment_id=getattr(treatment, "id", None)).first() if treatment else None
        treatment_ok = _authority_ok(treatment, treatment_authority, treatment_pointer, qualification="PRODUCTION_QUALIFIED") and bool(treatment_pointer and str(treatment_pointer.authority_envelope_fingerprint) == str(getattr(treatment_authority, "envelope_fingerprint", "")))
        if not treatment_ok: blockers.append("TREATMENT_AUTHORITY_INVALID")
        blocking_pointer = session.query(SceneBlockingPointer).filter_by(book_id=pointer.book_id, episode=pointer.episode, scene_id=pointer.scene_id).first()
        blocking = session.query(SceneBlocking).filter_by(id=getattr(blocking_pointer, "blocking_id", None)).first() if blocking_pointer else None
        blocking_authority = session.query(SceneBlockingAuthority).filter_by(blocking_id=getattr(blocking, "id", None)).first() if blocking else None
        blocking_ok = _authority_ok(blocking, blocking_authority, blocking_pointer, qualification="PRODUCTION_QUALIFIED") and not _json(getattr(blocking, "unknowns", "[]"), []) and not _json(getattr(blocking, "unresolved_facts", "[]"), [])
        if not blocking_ok: blockers.append("SCENE_BLOCKING_AUTHORITY_INVALID")
        materialization_pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=pointer.book_id, episode=pointer.episode, scene_id=pointer.scene_id).first()
        materialization_set = session.query(StoryboardMaterializationSet).filter_by(id=getattr(materialization_pointer, "materialization_set_id", None)).first() if materialization_pointer else None
        materialization_result = validate_current_materialization_authority(session, book_id=pointer.book_id, episode=pointer.episode, scene_id=pointer.scene_id) if materialization_pointer else {"valid": False, "errors": ["MATERIALIZATION_POINTER_MISSING"]}
        if not materialization_result.get("valid"):
            blockers.extend(str(item) for item in (materialization_result.get("errors") or ["MATERIALIZATION_INVALID"]))
        rows = materialization_result.get("rows") or []
        plan_shot_ids = {
            str(item.get("plan_shot_id") or "")
            for item in (_json(getattr(plan, "shots", "[]"), []) if plan else [])
            if isinstance(item, dict)
        }
        for row in rows:
            meta = _json(getattr(row, "meta_info", "{}"), {})
            handoff = meta.get("prompt_compiler_handoff") if isinstance(meta, dict) and isinstance(meta.get("prompt_compiler_handoff"), dict) else {}
            assets, asset_blockers = _asset_gate(session, book_id=pointer.book_id, handoff=handoff)
            prompt_status = {}
            for media in ("IMAGE", "VIDEO"):
                pp = session.query(PromptIRPointer).filter_by(book_id=pointer.book_id, episode=pointer.episode, storyboard_shot_id=row.id, target_media=media).first()
                pv = session.query(PromptIRVersion).filter_by(id=getattr(pp, "prompt_ir_version_id", None)).first() if pp else None
                if not pp: prompt_status[media] = "MISSING_COMPILE_REQUIRED"
                elif not pv or not _fresh(pv.stale_status) or str(pv.qualification_state) != "PROMPT_IR_QUALIFIED" or str(pp.payload_hash) != str(pv.payload_hash): prompt_status[media] = "INVALID"
                else: prompt_status[media] = "PRESENT_CURRENT"
            row_blockers = list(blockers) + asset_blockers
            if str(getattr(row, "plan_shot_id", "") or "") not in plan_shot_ids:
                row_blockers.append("SHOT_PLAN_MEMBERSHIP_INVALID")
            for media in ("IMAGE", "VIDEO"):
                if prompt_status.get(media) != "PRESENT_CURRENT":
                    row_blockers.append(f"PROMPT_IR_{media}_NOT_CURRENT")
            if str(getattr(row, "materialization_set_id", "")) != str(getattr(materialization_set, "id", "")): row_blockers.append("STORYBOARD_SHOT_NOT_IN_CURRENT_SET")
            inventory.append({
                "book_id": pointer.book_id, "episode": pointer.episode, "scene_id": pointer.scene_id, "scene_name": getattr(plan, "scene_name", ""), "shot_plan_id": getattr(plan, "id", None), "shot_plan_revision": getattr(plan, "revision", None), "plan_shot_id": getattr(row, "plan_shot_id", None), "storyboard_shot_id": row.id, "materialization_set_id": getattr(materialization_set, "id", None), "duration": getattr(row, "duration", None), "dialogue_present": bool(str(getattr(row, "dialogue", "") or "").strip()), "characters": len(((_json(getattr(row, "meta_info", "{}"), {}) or {}).get("prompt_compiler_handoff", {}) or {}).get("asset_identity_bindings", {}).get("characters", []) or []), "props": len(((_json(getattr(row, "meta_info", "{}"), {}) or {}).get("prompt_compiler_handoff", {}) or {}).get("asset_identity_bindings", {}).get("props", []) or []), "script_ir": script, "treatment_id": getattr(treatment, "id", None), "treatment_authority_fingerprint": getattr(treatment_authority, "envelope_fingerprint", None), "scene_blocking_id": getattr(blocking, "id", None), "scene_blocking_authority_fingerprint": getattr(blocking_authority, "envelope_fingerprint", None), "shot_plan_authority_fingerprint": getattr(authority, "envelope_fingerprint", None), "materialization_fingerprint": getattr(materialization_set, "set_payload_fingerprint", None), "asset_authority": assets, "prompt_ir": prompt_status, "hard_gate": "PASS" if not row_blockers else "FAIL", "blockers": sorted(set(row_blockers), key=str), "camera": (_json(getattr(row, "meta_info", "{}"), {}) or {}).get("camera", {})})
    return inventory


def rank_canary_candidates(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [item for item in inventory if item.get("hard_gate") == "PASS"]
    for item in candidates:
        score = 0
        score += 20 if item.get("characters") == 2 else 10 if item.get("characters") else 0
        score += 15 if item.get("dialogue_present") else 0
        score += 10 if int(item.get("props") or 0) == 0 else 5
        score += 10 if 3 <= int(item.get("duration") or 0) <= 14 else 0
        score += 5 if item.get("prompt_ir", {}).get("IMAGE") == "PRESENT_CURRENT" else 0
        item["selection_score"] = score
    return sorted(candidates, key=lambda item: (-int(item.get("selection_score", 0)), int(item.get("book_id", 0)), int(item.get("episode", 0)), str(item.get("plan_shot_id", "")), int(item.get("storyboard_shot_id", 0))))


def select_canary_target(inventory: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = rank_canary_candidates(inventory)
    if not ranked:
        return {"status": "NO_CANONICAL_CANARY_TARGET_READY", "candidates": [], "top_candidates": [], "blocker_counts": _blocker_counts(inventory)}
    top_score = ranked[0]["selection_score"]
    tied = [item for item in ranked if item["selection_score"] == top_score]
    if len(tied) != 1:
        return {"status": "CANONICAL_CANARY_TARGET_AMBIGUOUS", "candidates": ranked, "top_candidates": tied, "selection_score": top_score, "blocker_counts": _blocker_counts(inventory)}
    return {"status": "CANONICAL_CANARY_TARGET_SELECTED", "candidates": ranked, "top_candidates": tied, "selected": tied[0], "selection_score": top_score, "blocker_counts": _blocker_counts(inventory)}


def _blocker_counts(inventory: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in inventory:
        for blocker in item.get("blockers", []): counts[blocker] = counts.get(blocker, 0) + 1
    return dict(sorted(counts.items()))


__all__ = ["build_canonical_shot_inventory", "rank_canary_candidates", "select_canary_target"]
