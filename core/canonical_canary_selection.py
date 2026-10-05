"""Provider-free canonical canary inventory and semantic selection policy."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from api.prompt_ir_authority_api import _production_asset_authority
from core.storyboard_materializer import validate_current_materialization_authority
from models import (
    DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer,
    PromptIRPointer, PromptIRVersion, SceneBlocking, SceneBlockingAuthority,
    SceneBlockingPointer, Script, ScriptIRVersion, ShotPlan, ShotPlanAuthority,
    ShotPlanPointer, StoryboardMaterializationPointer, StoryboardMaterializationSet,
)

SELECTION_POLICY_VERSION = "canonical_canary_selection_policy_v2"


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _fresh(value: Any) -> bool:
    return str(value or "").upper() == "FRESH"


def _ref_id(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("canonical_id", "asset_id", "character_id", "prop_id", "subject_id", "id", "ref", "name"):
            if str(value.get(key) or "").strip():
                return str(value[key]).strip()
        return _canonical(value)
    return str(value or "").strip()


def _refs(values: Any) -> list[str]:
    if not isinstance(values, list):
        values = [values] if values not in (None, "") else []
    return [_ref_id(item) for item in values if _ref_id(item)]


def _ref_projection(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        values = [values] if values not in (None, "") else []
    result = []
    for item in values:
        identity = _ref_id(item)
        if identity:
            result.append({"identity": identity, "raw_type": type(item).__name__})
    return result


def _dialogue_fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _semantic_fingerprint_projection(value: Any) -> Any:
    """Remove lineage identifiers while retaining observable shot semantics."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"projection_provenance", "shot_design_ref", "plan_shot_id", "scene_id", "director_decision_refs", "requirement_refs"} or "fingerprint" in lowered or "authority" in lowered:
                continue
            result[str(key)] = _semantic_fingerprint_projection(item)
        return result
    if isinstance(value, list):
        return [_semantic_fingerprint_projection(item) for item in value]
    return value


def extract_canary_semantic_features(row: Any, prompt_payloads: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Read semantic truth from visual_semantic_handoff, never asset counts."""
    meta = _json(getattr(row, "meta_info", "{}"), {})
    projection = meta.get("projection_payload") if isinstance(meta, dict) and isinstance(meta.get("projection_payload"), dict) else {}
    semantic = meta.get("visual_semantic_handoff") if isinstance(meta, dict) and isinstance(meta.get("visual_semantic_handoff"), dict) else {}
    if not semantic and isinstance(projection.get("visual_semantic_handoff"), dict):
        semantic = projection["visual_semantic_handoff"]
    prompt_handoff = meta.get("prompt_compiler_handoff") if isinstance(meta, dict) and isinstance(meta.get("prompt_compiler_handoff"), dict) else {}
    semantic_assets = semantic.get("asset_identity_bindings") if isinstance(semantic.get("asset_identity_bindings"), dict) else {}
    canonical_assets = semantic_assets.get("canonical_asset_identity") if isinstance(semantic_assets.get("canonical_asset_identity"), dict) else {}
    subjects_raw = semantic.get("subjects") if isinstance(semantic.get("subjects"), list) else []
    props_raw = semantic.get("props") if isinstance(semantic.get("props"), list) else []
    subject_ids, prop_ids = _refs(subjects_raw), _refs(props_raw)
    canonical_character_ids, canonical_prop_ids = _refs(canonical_assets.get("characters", [])), _refs(canonical_assets.get("props", []))
    dialogue = str(getattr(row, "dialogue", "") or "").strip()
    projection_dialogue = str(projection.get("dialogue", "") or "").strip()
    consistency_errors: list[str] = []
    if projection and projection_dialogue != dialogue:
        consistency_errors.append("DIALOGUE_PROJECTION_MISMATCH")
    prompt_dialogues: list[str] = []
    for payload in (prompt_payloads or {}).values():
        parsed = _json(payload, {})
        if isinstance(parsed, dict):
            prompt_dialogues.append(str(parsed.get("dialogue") or "").strip()) if "dialogue" in parsed else None
            semantic_payload = parsed.get("semantic_payload") if isinstance(parsed.get("semantic_payload"), dict) else {}
            prompt_dialogues.append(str(semantic_payload.get("dialogue") or "").strip()) if "dialogue" in semantic_payload else None
    if prompt_dialogues and any(item != dialogue for item in prompt_dialogues):
        consistency_errors.append("DIALOGUE_PROMPT_IR_MISMATCH")
    camera = semantic.get("camera") if isinstance(semantic.get("camera"), dict) else {}
    if not camera:
        camera = meta.get("camera") if isinstance(meta.get("camera"), dict) else {}
    framing = str(camera.get("framing_class") or camera.get("shot_size") or "").upper()
    movement = str(camera.get("movement") or "").upper()
    support = str(camera.get("support") or "").upper()
    temporal = semantic.get("temporal_intent") if isinstance(semantic.get("temporal_intent"), dict) else {}
    continuity = semantic.get("continuity") if isinstance(semantic.get("continuity"), dict) else {}
    spatial = semantic.get("spatial") if isinstance(semantic.get("spatial"), dict) else {}
    entry_state = spatial.get("entry_state_ref") or prompt_handoff.get("entry_state") or ""
    exit_state = spatial.get("exit_state_ref") or prompt_handoff.get("exit_state") or ""
    reaction_refs = semantic.get("reaction_contract_refs") if isinstance(semantic.get("reaction_contract_refs"), list) else []
    action_beats = prompt_handoff.get("action_beats") if isinstance(prompt_handoff.get("action_beats"), list) else []
    semantic_payload = {"subjects": subject_ids, "props": prop_ids, "dialogue": dialogue, "duration": getattr(row, "duration", None), "camera": camera, "temporal_intent": temporal, "entry_state": entry_state, "exit_state": exit_state, "continuity": continuity, "visual_semantic_handoff": semantic}
    return {
        "subjects": _ref_projection(subjects_raw), "subject_ids": subject_ids, "subject_count": len(subject_ids),
        "props": _ref_projection(props_raw), "prop_ids": prop_ids, "prop_count": len(prop_ids),
        "canonical_asset_identity": {"scene": str(canonical_assets.get("scene") or ""), "characters": canonical_character_ids, "props": canonical_prop_ids},
        "dialogue_present": bool(dialogue), "dialogue_length": len(dialogue), "dialogue_fingerprint": _dialogue_fingerprint(dialogue),
        "dialogue_consistency": "PASS" if not consistency_errors else "FAIL", "dialogue_consistency_errors": sorted(set(consistency_errors)),
        "duration": getattr(row, "duration", None), "camera": {"framing": framing, "movement": movement, "support": support, "raw": camera},
        "camera_complexity": "LOW" if movement in {"", "NONE", "STATIC"} and support in {"", "STATIC"} else "MEDIUM",
        "temporal_intent_presence": bool(temporal), "reaction_or_performance_presence": bool(reaction_refs or temporal.get("performance") or temporal.get("reaction") or (action_beats and subject_ids)),
        "entry_state_presence": bool(entry_state), "exit_state_presence": bool(exit_state), "continuity_data_presence": bool(continuity),
        "visual_semantic_fingerprint": _sha(_semantic_fingerprint_projection(semantic_payload)),
        "stored_visual_semantic_fingerprint": str(meta.get("semantic_projection_fingerprint") or ""),
        "asset_identity_refs": {"scene": str(canonical_assets.get("scene") or ""), "characters": canonical_character_ids, "props": canonical_prop_ids},
        "semantic_source": "StoryboardShot.meta_info.visual_semantic_handoff",
    }


def _authority_ok(row: Any, authority: Any, pointer: Any, *, qualification: str = "PRODUCTION_QUALIFIED") -> bool:
    pointer_target = getattr(pointer, "shot_plan_id", None) or getattr(pointer, "treatment_id", None) or getattr(pointer, "blocking_id", None)
    return bool(row and authority and pointer and str(getattr(row, "qualification_state", "")) == qualification and _fresh(getattr(row, "stale_status", "")) and str(getattr(pointer, "qualification_state", "")) == qualification and str(getattr(authority, "qualification_state", "")) in {"AUTHORITY_BOUND", qualification} and _fresh(getattr(authority, "stale_status", "")) and str(getattr(pointer, "authority_envelope_fingerprint", "")) == str(getattr(authority, "envelope_fingerprint", "")) and str(pointer_target) == str(getattr(row, "id", "")))


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


def _asset_gate(session: Any, *, book_id: int, handoff: dict[str, Any], semantic_features: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[str]]:
    features = semantic_features or {}
    refs = features.get("asset_identity_refs") if isinstance(features.get("asset_identity_refs"), dict) else None
    if refs is None:
        bindings = handoff.get("asset_identity_bindings") if isinstance(handoff.get("asset_identity_bindings"), dict) else {}
        canonical = bindings.get("canonical_asset_identity") if isinstance(bindings.get("canonical_asset_identity"), dict) else bindings
        refs = {"scene": canonical.get("scene") or "", "characters": _refs(canonical.get("characters", [])), "props": _refs(canonical.get("props", []))}
    canonical_handoff = {"asset_identity_bindings": {"canonical_asset_identity": refs}}
    result = _production_asset_authority(session, book_id=book_id, handoff=canonical_handoff)
    bindings = [item for item in result.get("bindings", []) if isinstance(item, dict)]
    by_type = {kind: [item for item in bindings if str(item.get("asset_type") or "").lower() == kind] for kind in ("scene", "character", "prop")}
    resolved_ids = {kind: [_ref_id(item.get("canonical_asset_id") or item.get("asset_key")) for item in rows] for kind, rows in by_type.items()}
    blockers: list[str] = []
    if not refs.get("scene") or not by_type["scene"]: blockers.append("ASSET_AUTHORITY_SCENE_MISSING")
    semantic_chars, semantic_props = list(features.get("subject_ids") or refs.get("characters") or []), list(features.get("prop_ids") or refs.get("props") or [])
    if len(by_type["character"]) != len(semantic_chars) and semantic_chars: blockers.append("ASSET_AUTHORITY_REQUIRED_CHARACTERS_MISSING")
    elif set(resolved_ids["character"]) != set(semantic_chars): blockers.append("ASSET_AUTHORITY_CHARACTER_IDENTITY_MISMATCH") if semantic_chars else None
    if len(by_type["prop"]) != len(semantic_props) and semantic_props: blockers.append("ASSET_AUTHORITY_REQUIRED_PROPS_MISSING")
    elif set(resolved_ids["prop"]) != set(semantic_props): blockers.append("ASSET_AUTHORITY_PROP_IDENTITY_MISMATCH") if semantic_props else None
    return {"status": "PASS" if not blockers else "FAIL", "semantic_character_ids": semantic_chars, "semantic_prop_ids": semantic_props, "resolved_character_ids": resolved_ids["character"], "resolved_prop_ids": resolved_ids["prop"], "bindings": bindings, "authority_fingerprint": result.get("authority_fingerprint")}, blockers


def _prompt_status(session: Any, *, book_id: int, episode: int, row: Any) -> tuple[dict[str, str], list[str], list[str], dict[str, Any]]:
    status, compile_required, integrity, payloads = {}, [], [], {}
    for media in ("IMAGE", "VIDEO"):
        pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=row.id, target_media=media).first()
        version = session.query(PromptIRVersion).filter_by(id=getattr(pointer, "prompt_ir_version_id", None)).first() if pointer else None
        if not pointer or not version:
            status[media] = "MISSING_COMPILE_REQUIRED"; compile_required.append(media); continue
        if not _fresh(version.stale_status) or str(version.qualification_state) != "PROMPT_IR_QUALIFIED" or str(pointer.payload_hash) != str(version.payload_hash):
            status[media] = "INVALID_CURRENT_AUTHORITY"; integrity.append(f"PROMPT_IR_{media}_INVALID_CURRENT_AUTHORITY")
        else:
            status[media] = "PRESENT_CURRENT"; payloads[media] = _json(version.payload_json, {})
    return status, compile_required, integrity, payloads


def _reference_requirements(features: dict[str, Any], *, image_profile: dict[str, Any] | None = None, prompt_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    image_profile = image_profile or {}; params = image_profile.get("default_params") if isinstance(image_profile.get("default_params"), dict) else {}
    policy = (prompt_payload or {}).get("generation_policy") if isinstance((prompt_payload or {}).get("generation_policy"), dict) else {}
    required_classes = {str(item).upper() for item in policy.get("required_asset_classes", []) if str(item).strip()}
    result: dict[str, Any] = {"provider_supports_reference_images": bool(params.get("supports_reference_images", False)), "scene": "OPTIONAL", "character": "OPTIONAL", "prop": "OPTIONAL", "required_asset_classes": sorted(required_classes)}
    if required_classes & {"SCENE", "SCENE_ASSET"}: result["scene"] = "REQUIRED"
    if required_classes & {"CHARACTER", "CHARACTERS"}: result["character"] = "REQUIRED"
    if required_classes & {"PROP", "PROPS"}: result["prop"] = "REQUIRED"
    return result


def reference_readiness_blockers(features: dict[str, Any], assets: dict[str, Any], requirements: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for kind in ("scene", "character", "prop"):
        if requirements.get(kind) != "REQUIRED":
            continue
        has_asset = bool(features.get("asset_identity_refs", {}).get(kind + "s" if kind != "scene" else "scene"))
        rows_for_kind = [item for item in assets.get("bindings", []) if str(item.get("asset_type") or "").lower() == kind]
        if has_asset and (not rows_for_kind or any(str(item.get("reference_status") or "").upper() not in {"LOCKED", "REFERENCE_LOCKED"} for item in rows_for_kind)):
            blockers.append(f"REQUIRED_{kind.upper()}_REFERENCE_NOT_READY")
    return blockers


def build_canonical_shot_inventory(session: Any, *, book_provenance: Mapping[int, dict[str, Any]] | None = None, image_profile: dict[str, Any] | None = None, video_profile: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Build a complete authority inventory; PromptIR missing is readiness only."""
    inventory, provenance = [], book_provenance or {}
    for pointer in session.query(ShotPlanPointer).all():
        plan = session.query(ShotPlan).filter_by(id=pointer.shot_plan_id, book_id=pointer.book_id, episode=pointer.episode, scene_id=pointer.scene_id).first()
        authority = session.query(ShotPlanAuthority).filter_by(shot_plan_id=getattr(plan, "id", None)).first() if plan else None
        blockers: list[str] = []
        script, script_blockers = _script_state(session, pointer.book_id, pointer.episode); blockers.extend(script_blockers)
        if not _authority_ok(plan, authority, pointer): blockers.append("SHOT_PLAN_AUTHORITY_INVALID")
        treatment_pointer = session.query(DirectorTreatmentPointer).filter_by(book_id=pointer.book_id, episode=pointer.episode, scene_id=pointer.scene_id).first()
        treatment = session.query(DirectorTreatment).filter_by(id=getattr(treatment_pointer, "treatment_id", None)).first() if treatment_pointer else None
        treatment_authority = session.query(DirectorTreatmentAuthority).filter_by(treatment_id=getattr(treatment, "id", None)).first() if treatment else None
        if not _authority_ok(treatment, treatment_authority, treatment_pointer, qualification="PRODUCTION_QUALIFIED"): blockers.append("TREATMENT_AUTHORITY_INVALID")
        blocking_pointer = session.query(SceneBlockingPointer).filter_by(book_id=pointer.book_id, episode=pointer.episode, scene_id=pointer.scene_id).first()
        blocking = session.query(SceneBlocking).filter_by(id=getattr(blocking_pointer, "blocking_id", None)).first() if blocking_pointer else None
        blocking_authority = session.query(SceneBlockingAuthority).filter_by(blocking_id=getattr(blocking, "id", None)).first() if blocking else None
        blocking_ok = _authority_ok(blocking, blocking_authority, blocking_pointer, qualification="PRODUCTION_QUALIFIED") and not _json(getattr(blocking, "unknowns", "[]"), []) and not _json(getattr(blocking, "unresolved_facts", "[]"), [])
        if not blocking_ok: blockers.append("SCENE_BLOCKING_AUTHORITY_INVALID")
        materialization_pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=pointer.book_id, episode=pointer.episode, scene_id=pointer.scene_id).first()
        materialization_set = session.query(StoryboardMaterializationSet).filter_by(id=getattr(materialization_pointer, "materialization_set_id", None)).first() if materialization_pointer else None
        materialization_result = validate_current_materialization_authority(session, book_id=pointer.book_id, episode=pointer.episode, scene_id=pointer.scene_id) if materialization_pointer else {"valid": False, "errors": ["MATERIALIZATION_POINTER_MISSING"]}
        if not materialization_result.get("valid"): blockers.extend(str(item) for item in (materialization_result.get("errors") or ["MATERIALIZATION_INVALID"]))
        plan_shot_ids = {str(item.get("plan_shot_id") or "") for item in (_json(getattr(plan, "shots", "[]"), []) if plan else []) if isinstance(item, dict)}
        for row in materialization_result.get("rows") or []:
            meta = _json(getattr(row, "meta_info", "{}"), {}); handoff = meta.get("prompt_compiler_handoff") if isinstance(meta, dict) and isinstance(meta.get("prompt_compiler_handoff"), dict) else {}
            prompt_status, compile_required, prompt_integrity, prompt_payloads = _prompt_status(session, book_id=pointer.book_id, episode=pointer.episode, row=row)
            features = extract_canary_semantic_features(row, prompt_payloads)
            semantic_blockers = list(features.get("dialogue_consistency_errors") or [])
            if str(getattr(row, "plan_shot_id", "") or "") not in plan_shot_ids: semantic_blockers.append("SHOT_PLAN_MEMBERSHIP_INVALID")
            assets, asset_blockers = _asset_gate(session, book_id=pointer.book_id, handoff=handoff, semantic_features=features)
            prompt_payload = prompt_payloads.get("IMAGE") if isinstance(prompt_payloads.get("IMAGE"), dict) else {}
            reference_requirements = _reference_requirements(features, image_profile=image_profile, prompt_payload=prompt_payload)
            reference_blockers = reference_readiness_blockers(features, assets, reference_requirements)
            canonical_blockers = list(blockers) + semantic_blockers + asset_blockers + prompt_integrity + reference_blockers
            book_info = provenance.get(pointer.book_id, {"provenance_class": "UNKNOWN_PROVENANCE", "eligible": False})
            if not book_info.get("eligible", False): canonical_blockers.append("PROJECT_PROVENANCE_NOT_PRODUCTION_ELIGIBLE")
            canonical_eligibility = "PASS" if not canonical_blockers else "FAIL"
            semantic_useful = bool((features["subject_count"] >= 2 and features["dialogue_present"]) or (features["subject_count"] >= 1 and (features["reaction_or_performance_presence"] or features["temporal_intent_presence"])))
            inventory.append({"book_id": pointer.book_id, "book": book_info, "episode": pointer.episode, "scene_id": pointer.scene_id, "scene_name": getattr(plan, "scene_name", ""), "shot_plan_id": getattr(plan, "id", None), "shot_plan_revision": getattr(plan, "revision", None), "plan_shot_id": getattr(row, "plan_shot_id", None), "storyboard_shot_id": row.id, "materialization_set_id": getattr(materialization_set, "id", None), "script_ir": script, "treatment_id": getattr(treatment, "id", None), "treatment_authority_fingerprint": getattr(treatment_authority, "envelope_fingerprint", None), "scene_blocking_id": getattr(blocking, "id", None), "scene_blocking_authority_fingerprint": getattr(blocking_authority, "envelope_fingerprint", None), "shot_plan_authority_fingerprint": getattr(authority, "envelope_fingerprint", None), "materialization_fingerprint": getattr(materialization_set, "set_payload_fingerprint", None), "semantic_features": features, "asset_authority": assets, "reference_requirements": reference_requirements, "prompt_ir_readiness": prompt_status, "prompt_compile_required": compile_required, "canonical_eligibility": canonical_eligibility, "execution_readiness": {"image_prompt_ir": prompt_status.get("IMAGE"), "video_prompt_ir": prompt_status.get("VIDEO"), "references": "BLOCKED" if reference_blockers else ("OPTIONAL_PENDING" if any(item.get("reference_status") == "REFERENCE_PENDING" for item in assets.get("bindings", [])) else "READY"), "provider_preflight": "NOT_RUN", "execution_blockers": sorted(set(prompt_integrity + reference_blockers + asset_blockers))}, "hard_gate": canonical_eligibility, "blockers": sorted(set(canonical_blockers)), "semantic_completeness": "PASS" if semantic_useful else "INSUFFICIENT", "semantic_useful": semantic_useful, "camera": features.get("camera"), "dialogue_present": features.get("dialogue_present"), "duration": features.get("duration"), "characters": features.get("subject_count"), "props": features.get("prop_count")})
    return inventory


def detect_semantic_clone_groups(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in inventory:
        f = item.get("semantic_features") or {}
        key = _sha({"semantic": f.get("visual_semantic_fingerprint"), "subjects": f.get("subject_ids"), "props": f.get("prop_ids"), "dialogue": f.get("dialogue_fingerprint"), "duration": f.get("duration"), "camera": f.get("camera"), "continuity": f.get("continuity_data_presence")})
        groups.setdefault(key, []).append(item)
    result = []
    for fingerprint, members in groups.items():
        if len(members) < 2 or len({item.get("book_id") for item in members}) < 2: continue
        clone_group_id = f"clone-{fingerprint[:16]}"
        for member in members:
            member["clone_group_id"] = clone_group_id
        result.append({"clone_group_id": clone_group_id, "semantic_fingerprint": fingerprint, "member_book_ids": sorted({item.get("book_id") for item in members}), "member_plan_shot_ids": sorted({item.get("plan_shot_id") for item in members}), "disposition": "EXCLUDED_UNTIL_PROJECT_PROVENANCE_PROVES_OFFICIAL_CANARY_FAMILY"})
    return sorted(result, key=lambda item: item["clone_group_id"])


def _score(item: dict[str, Any]) -> int:
    f = item.get("semantic_features") or {}
    score = 0
    score += 25 if f.get("subject_count") == 2 else 12 if f.get("subject_count", 0) == 1 else 0
    score += 20 if f.get("dialogue_present") else 0
    score += 10 if f.get("reaction_or_performance_presence") else 0
    score += 8 if f.get("entry_state_presence") and f.get("exit_state_presence") else 0
    score += 8 if str(f.get("camera", {}).get("framing") or "").upper() in {"MEDIUM", "MEDIUM_CLOSE", "MS", "MCU"} else 0
    score += 8 if f.get("camera_complexity") == "LOW" else 0
    score += 8 if 3 <= int(f.get("duration") or 0) <= 14 else 0
    score += 6 if f.get("prop_count") == 0 else 3 if f.get("prop_count") == 1 else 0
    score += 10 if (item.get("asset_authority") or {}).get("status") == "PASS" else 0
    prompt = item.get("prompt_ir_readiness") or item.get("prompt_ir", {})
    score += 4 if prompt.get("IMAGE") == "PRESENT_CURRENT" else 0
    score += 4 if prompt.get("VIDEO") == "PRESENT_CURRENT" else 0
    return score


def rank_canary_candidates(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [item for item in inventory if item.get("canonical_eligibility", item.get("hard_gate")) == "PASS"]
    for item in candidates: item["selection_score"] = _score(item)
    return sorted(candidates, key=lambda item: (-int(item.get("selection_score", 0)), int(item.get("book_id", 0)), int(item.get("episode", 0)), str(item.get("plan_shot_id", "")), int(item.get("storyboard_shot_id", 0))))


def select_canary_target(inventory: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = rank_canary_candidates(inventory)
    if not ranked: return {"status": "NO_CANONICAL_CANARY_TARGET_READY", "candidates": [], "top_candidates": [], "blocker_counts": _blocker_counts(inventory)}
    top_score = ranked[0]["selection_score"]; tied = [item for item in ranked if item["selection_score"] == top_score]
    if len(tied) != 1: return {"status": "CANONICAL_CANARY_TARGET_AMBIGUOUS", "candidates": ranked, "top_candidates": tied, "selection_score": top_score, "blocker_counts": _blocker_counts(inventory)}
    return {"status": "CANONICAL_CANARY_TARGET_SELECTED", "candidates": ranked, "top_candidates": tied, "selected": tied[0], "selection_score": top_score, "blocker_counts": _blocker_counts(inventory)}


def select_semantic_canary_target(inventory: list[dict[str, Any]], clone_groups: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    clone_groups = clone_groups or detect_semantic_clone_groups(inventory); ranked = rank_canary_candidates(inventory); useful = [item for item in ranked if item.get("semantic_useful") and not item.get("clone_group_id")]
    if not useful:
        provenance_ok = [item for item in ranked if item.get("book", {}).get("eligible")]
        status = "NO_PRODUCTION_CANARY_PROJECT_ELIGIBLE" if not provenance_ok and ranked else "NO_SEMANTICALLY_USEFUL_CANONICAL_CANARY_TARGET"
        return {"status": status, "candidates": ranked, "top_candidates": [], "clone_groups": clone_groups, "blocker_counts": _blocker_counts(inventory)}
    top_score = useful[0]["selection_score"]; tied = [item for item in useful if item["selection_score"] == top_score]
    if len(tied) != 1: return {"status": "CANONICAL_CANARY_TARGET_AMBIGUOUS", "candidates": useful, "top_candidates": tied, "clone_groups": clone_groups, "selection_score": top_score, "blocker_counts": _blocker_counts(inventory)}
    return {"status": "CANONICAL_CANARY_TARGET_SELECTED", "candidates": useful, "top_candidates": tied, "selected": tied[0], "clone_groups": clone_groups, "selection_score": top_score, "blocker_counts": _blocker_counts(inventory)}


def _blocker_counts(inventory: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in inventory:
        for blocker in item.get("blockers", []): counts[blocker] = counts.get(blocker, 0) + 1
    return dict(sorted(counts.items()))


__all__ = ["SELECTION_POLICY_VERSION", "extract_canary_semantic_features", "build_canonical_shot_inventory", "detect_semantic_clone_groups", "rank_canary_candidates", "select_canary_target", "select_semantic_canary_target", "reference_readiness_blockers"]
