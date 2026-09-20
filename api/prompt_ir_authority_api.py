"""Provider-free PromptIR authority and deterministic adapter preview APIs."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.prompt_ir_authority import (
    PromptIRAuthorityError,
    build_prompt_ir_authority_envelope,
    compile_prompt_ir_from_handoff,
    serialize_prompt_ir_to_adapter,
)
from core.prompt_ir_phase_e import (
    PromptIRPhaseEError,
    MODEL_ADAPTER_REGISTRY,
    adapt_prompt_ir_to_generation_payload,
    build_generation_policy,
    build_model_profile,
    compile_storyboard_snapshot_to_prompt_ir,
    fingerprint as phase_e_fingerprint,
    resolve_current_authoritative_prompt_ir,
)
from core.visual_asset_authority import build_asset_key, production_asset_binding
from core.storyboard_materializer import build_storyboard_production_snapshot, resolve_current_authoritative_materialization
from models import PromptIRAuthority, PromptIRPointer, PromptIRVersion, Session

router = APIRouter(prefix="/api/books", tags=["prompt-ir-authority"])


class PromptIRCompileRequest(BaseModel):
    asset_authority: dict = Field(default_factory=dict)
    retention_policy: dict = Field(default_factory=dict)


class AdapterPreviewRequest(BaseModel):
    adapter_id: str = "kling"
    capability_profile: dict = Field(default_factory=dict)
    model_profile: dict = Field(default_factory=dict)
    generation_policy: dict = Field(default_factory=dict)


class PhaseECompileRequest(BaseModel):
    generation_policy: dict = Field(default_factory=dict)
    asset_authority: dict = Field(default_factory=dict)


def _conflict(code: str, message: str, **extra):
    raise HTTPException(status_code=409, detail={"code": code, "message": message, **extra})


def _json(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _load_current(session, *, book_id: int, episode: int, shot_id: int):
    try:
        materialization_set, rows, set_envelope = resolve_current_authoritative_materialization(session, book_id=book_id, episode=episode, scene_id=_scene_id_for_shot(session, book_id, episode, shot_id))
    except HTTPException:
        raise
    row = next((item for item in rows if int(item.id) == int(shot_id) or int(item.shot_id) == int(shot_id)), None)
    if not row:
        _conflict("STORYBOARD_SHOT_NOT_IN_CURRENT_SET", "Requested StoryboardShot is not part of the current materialization set.")
    return materialization_set, row, set_envelope


def _scene_id_for_shot(session, book_id: int, episode: int, shot_id: int) -> str:
    from models import StoryboardShot
    row = session.query(StoryboardShot).filter_by(book_id=book_id, episode=episode, id=shot_id).first() or session.query(StoryboardShot).filter_by(book_id=book_id, episode=episode, shot_id=shot_id).first()
    if not row or not str(row.scene_id or "").strip():
        _conflict("STORYBOARD_SHOT_AUTHORITY_MISSING", "PromptIR requires a StoryboardShot with explicit scene_id authority.")
    return str(row.scene_id).strip()


def _production_asset_authority(session, *, book_id: int, handoff: dict) -> dict:
    """Resolve PromptIR assets only through current VisualAssetVersion pointers."""
    from models import VisualAssetPointer, VisualAssetVersion, VisualReferenceAuthority

    bindings = handoff.get("asset_identity_bindings") if isinstance(handoff.get("asset_identity_bindings"), dict) else {}
    canonical = bindings.get("canonical_asset_identity") if isinstance(bindings.get("canonical_asset_identity"), dict) else {}
    if not canonical:
        canonical = {
            "scene": bindings.get("scene") or bindings.get("scene_asset_id", ""),
            "characters": bindings.get("characters") or bindings.get("character_asset_ids", []),
            "props": bindings.get("props") or bindings.get("prop_asset_ids", []),
        }
    entries = []
    for asset_type, key_name in (("scene", "scene"), ("character", "characters"), ("prop", "props")):
        raw = canonical.get(key_name, [])
        values = raw if isinstance(raw, list) else ([raw] if raw not in (None, "") else [])
        for value in values:
            if isinstance(value, dict):
                canonical_id = str(value.get("canonical_id") or value.get("asset_id") or value.get("id") or "").strip()
                display_name = str(value.get("name") or value.get("asset_name") or "").strip()
            else:
                canonical_id = str(value or "").strip()
                display_name = ""
            if not canonical_id:
                continue
            try:
                asset_key = build_asset_key(book_id=book_id, asset_type=asset_type, canonical_id=canonical_id)
            except Exception:
                continue
            # A production asset binding must come from the current pointer
            # for a declared scope.  Never infer authority from the newest
            # historical pointer when more than one scope is present.
            pointers = session.query(VisualAssetPointer).filter_by(book_id=book_id, asset_key=asset_key).all()
            if len(pointers) == 1:
                pointer = pointers[0]
            else:
                default = [item for item in pointers if str(item.scope_key or "") in {"", "canonical"}]
                pointer = default[0] if len(default) == 1 else None
            version = session.query(VisualAssetVersion).filter_by(id=pointer.current_version_id).first() if pointer else None
            reference = None
            if version:
                authority = session.query(VisualReferenceAuthority).filter_by(asset_key=asset_key, asset_version_id=version.id, status="LOCKED", stale_status="FRESH").order_by(VisualReferenceAuthority.id.desc()).first()
                if authority:
                    reference = {"status": authority.status, "stale_status": authority.stale_status, "reference_token": _json(authority.reference_token_mapping_json, {}).get("token", ""), "reference_name": _json(authority.reference_token_mapping_json, {}).get("name", "")}
            entries.append(production_asset_binding(asset_key=asset_key, asset_type=asset_type, asset_name=display_name, version={"id": version.id, "revision": version.revision, "payload": _json(version.payload_json, {}), "payload_hash": version.payload_hash, "authority_status": version.authority_status, "stale_status": version.stale_status} if version else {}, reference=reference, reference_required=True))
    return {"bindings": entries, "authority_fingerprint": __import__("core.visual_asset_authority", fromlist=["fingerprint"]).fingerprint(entries), "source": "current_visual_asset_pointers", "provider_calls": 0}


@router.post("/{book_id}/episodes/{episode}/storyboard/{shot_id}/prompt-ir/compile")
def compile_prompt_ir(book_id: int, episode: int, shot_id: int, req: PromptIRCompileRequest):
    with Session() as session:
        materialization_set, row, _set_envelope = _load_current(session, book_id=book_id, episode=episode, shot_id=shot_id)
        meta = _json(row.meta_info, {})
        handoff = meta.get("prompt_compiler_handoff") if isinstance(meta, dict) else None
        if not isinstance(handoff, dict):
            _conflict("STORYBOARD_HANDOFF_MISSING", "Authoritative StoryboardShot has no storyboard_prompt_handoff_v1.")
        if int(handoff.get("storyboard_shot_id") or 0) != int(row.id) or str(handoff.get("storyboard_projection_fingerprint") or "") != str(row.projection_fingerprint or ""):
            _conflict("STORYBOARD_HANDOFF_STALE", "PromptIR handoff does not match the current Storyboard projection.")
        try:
            authoritative_assets = _production_asset_authority(session, book_id=book_id, handoff=handoff)
            prompt_ir = compile_prompt_ir_from_handoff(handoff, asset_authority=authoritative_assets, retention_policy=req.retention_policy)
        except PromptIRAuthorityError as exc:
            _conflict(exc.code, exc.message, diagnostics=exc.diagnostics)
        existing_pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=row.id).first()
        if existing_pointer:
            existing = session.query(PromptIRVersion).filter_by(id=existing_pointer.prompt_ir_version_id).first()
            if existing and existing.payload_hash == prompt_ir["payload_hash"] and existing.stale_status == "FRESH":
                return {"mutated": False, "reused": True, "prompt_ir_version_id": existing.id, "qualification_state": existing.qualification_state, "asset_reference_state": existing.asset_reference_state, "model_generation_ready": existing.model_generation_ready == "true", "provider_calls": 0}
            if existing:
                existing.stale_status = "STALE"
                existing.stale_reasons = json.dumps(["PROMPT_IR_RECOMPILED"], ensure_ascii=False)
                existing.updated_at = datetime.now()
        envelope = build_prompt_ir_authority_envelope(prompt_ir=prompt_ir, handoff=handoff, validation=prompt_ir.get("diagnostics", {}))
        version = PromptIRVersion(book_id=book_id, episode=episode, scene_id=str(handoff["scene_id"]), storyboard_shot_id=row.id, materialization_set_id=int(handoff["materialization_set_id"]), plan_shot_id=str(handoff["plan_shot_id"]), schema_version=prompt_ir["schema_version"], payload_json=json.dumps(prompt_ir, ensure_ascii=False, sort_keys=True), payload_hash=prompt_ir["payload_hash"], compiler_version=prompt_ir["compiler_policy"]["compiler_version"], compiler_policy_version=prompt_ir["compiler_policy"]["compiler_policy_version"], retention_policy_version=prompt_ir["retention_policy"]["version"], authority_envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state=prompt_ir["qualification_state"], asset_reference_state=prompt_ir["asset_reference_state"], model_generation_ready="true" if prompt_ir["model_generation_ready"] else "false", stale_status="FRESH", stale_reasons="[]", created_at=datetime.now(), updated_at=datetime.now())
        session.add(version)
        session.flush()
        authority = PromptIRAuthority(prompt_ir_version_id=version.id, book_id=book_id, episode=episode, storyboard_shot_id=row.id, envelope_fingerprint=envelope["envelope_fingerprint"], envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state=prompt_ir["qualification_state"], stale_status="FRESH", stale_reasons="[]", created_at=datetime.now(), updated_at=datetime.now())
        session.add(authority)
        pointer = existing_pointer or PromptIRPointer(book_id=book_id, episode=episode, storyboard_shot_id=row.id)
        pointer.prompt_ir_version_id = version.id
        pointer.payload_hash = prompt_ir["payload_hash"]
        pointer.qualification_state = prompt_ir["qualification_state"]
        pointer.updated_at = datetime.now()
        session.add(pointer)
        session.commit()
        return {"mutated": True, "reused": False, "prompt_ir_version_id": version.id, "prompt_ir_authority_id": authority.id, "qualification_state": version.qualification_state, "asset_reference_state": version.asset_reference_state, "model_generation_ready": version.model_generation_ready == "true", "payload_hash": version.payload_hash, "asset_authority_source": "current_visual_asset_pointers", "provider_calls": 0}


@router.post("/{book_id}/episodes/{episode}/storyboard/{shot_id}/prompt-ir/adapter-preview")
def preview_prompt_ir_adapter(book_id: int, episode: int, shot_id: int, req: AdapterPreviewRequest):
    with Session() as session:
        _materialization_set, row, _set_envelope = _load_current(session, book_id=book_id, episode=episode, shot_id=shot_id)
        pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=row.id).first()
        if not pointer:
            _conflict("PROMPT_IR_POINTER_MISSING", "Model Adapter requires a current qualified PromptIR pointer.")
        version = session.query(PromptIRVersion).filter_by(id=pointer.prompt_ir_version_id).first()
        if not version or version.stale_status != "FRESH" or version.qualification_state != "PROMPT_IR_QUALIFIED":
            _conflict("PROMPT_IR_NOT_QUALIFIED", "Current PromptIR is missing, stale or not qualified.")
        if version.payload_hash != pointer.payload_hash:
            _conflict("PROMPT_IR_PAYLOAD_TAMPERED", "PromptIR payload no longer matches the current pointer.")
        if version.schema_version == "prompt_ir_v2":
            meta = _json(row.meta_info, {})
            handoff = meta.get("prompt_compiler_handoff") if isinstance(meta, dict) else {}
            try:
                asset_authority = _production_asset_authority(session, book_id=book_id, handoff=handoff if isinstance(handoff, dict) else {})
                registry = MODEL_ADAPTER_REGISTRY.get(req.adapter_id.lower(), {})
                profile_input = dict(req.model_profile) if req.model_profile else {"adapter_id": req.adapter_id, "model_family": registry.get("model_family", req.adapter_id.upper()), "capabilities": req.capability_profile}
                profile = build_model_profile(profile_input)
                resolved = resolve_current_authoritative_prompt_ir(session, book_id=book_id, episode=episode, storyboard_shot_id=row.id, generation_policy=req.generation_policy or None, asset_authority=asset_authority, model_profile=profile)
                output = adapt_prompt_ir_to_generation_payload(resolved["payload"], generation_policy=req.generation_policy or None, model_profile=profile)
            except PromptIRPhaseEError as exc:
                _conflict(exc.code, exc.message, diagnostics=exc.diagnostics)
            except HTTPException:
                raise
            return {"prompt_ir_version_id": version.id, "prompt_ir_payload_hash": version.payload_hash, "model_generation_ready": bool(output.get("readiness", {}).get("ready")), "generation_payload": output, "provider_calls": 0, "llm_calls": 0, "media_generated": False}
        output = serialize_prompt_ir_to_adapter(_json(version.payload_json, {}), req.adapter_id, capability_profile=req.capability_profile)
        return {"prompt_ir_version_id": version.id, "prompt_ir_payload_hash": version.payload_hash, "model_generation_ready": version.model_generation_ready == "true" and output.get("status") == "ready", "adapter_output": output, "provider_calls": 0}


@router.post("/{book_id}/episodes/{episode}/prompt-ir/compile")
def compile_prompt_ir_phase_e(book_id: int, episode: int, req: PhaseECompileRequest):
    """Atomically compile every shot in the current Storyboard sets.

    This is the canonical Phase E path.  It resolves current materialization
    pointers first, compiles the complete read-only snapshot in memory, and
    only then mutates PromptIRVersion/Authority/Pointer rows.
    """
    with Session() as session:
        from models import StoryboardMaterializationPointer

        pointers = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode).all()
        if not pointers:
            _conflict("STORYBOARD_MATERIALIZATION_POINTER_MISSING", "No current Storyboard materialization pointers exist.")
        snapshots = []
        for pointer in sorted(pointers, key=lambda item: str(item.scene_id or "")):
            try:
                materialization_set, rows, set_envelope = resolve_current_authoritative_materialization(session, book_id=book_id, episode=episode, scene_id=str(pointer.scene_id or ""))
            except HTTPException:
                raise
            snapshots.append(build_storyboard_production_snapshot(materialization_set=materialization_set, rows=rows, authority_envelope=set_envelope))
        policy = build_generation_policy(req.generation_policy)
        asset_authority = dict(req.asset_authority or {})
        if not asset_authority:
            by_key = {}
            for snapshot in snapshots:
                for row in snapshot.get("ordered_shots", []):
                    handoff = row.get("prompt_compiler_handoff") if isinstance(row.get("prompt_compiler_handoff"), dict) else {}
                    current = _production_asset_authority(session, book_id=book_id, handoff=handoff)
                    for binding in current.get("bindings", []):
                        key = str(binding.get("asset_key") or binding.get("canonical_asset_id") or "")
                        if key:
                            by_key[key] = binding
            asset_authority = {"bindings": list(by_key.values()), "source": "current_visual_asset_pointers", "authority_fingerprint": phase_e_fingerprint(list(by_key.values()))}
        try:
            compiled = []
            for snapshot in snapshots:
                compiled.extend(compile_storyboard_snapshot_to_prompt_ir(snapshot, generation_policy=policy, asset_authority=asset_authority))
        except PromptIRPhaseEError as exc:
            # Compilation is pure; no session mutation has occurred.
            _conflict(exc.code, exc.message, diagnostics=exc.diagnostics)
        if not compiled:
            _conflict("PROMPT_IR_SNAPSHOT_EMPTY", "Current Storyboard materialization contains no shots.")

        # Reuse all identical current payloads before creating any versions.
        existing_by_shot = {int(item.storyboard_shot_id): item for item in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
        results = []
        pending_writes = []
        for ir in compiled:
            shot_id = int(ir["storyboard_shot_id"])
            existing_pointer = existing_by_shot.get(shot_id)
            existing = session.query(PromptIRVersion).filter_by(id=existing_pointer.prompt_ir_version_id).first() if existing_pointer else None
            if existing and existing.payload_hash == ir["payload_hash"] and existing.stale_status == "FRESH":
                results.append({"storyboard_shot_id": shot_id, "prompt_ir_version_id": existing.id, "reused": True, "payload_hash": existing.payload_hash})
                continue
            if existing:
                previous_payload = _json(existing.payload_json, {})
                reasons = ["PROMPT_IR_RECOMPILED"]
                if previous_payload.get("generation_policy", {}).get("fingerprint") != ir.get("generation_policy", {}).get("fingerprint"):
                    reasons.append("GENERATION_POLICY_CHANGED")
                existing.stale_status = "STALE"
                existing.stale_reasons = json.dumps(sorted(set(reasons)), ensure_ascii=False)
                existing.updated_at = datetime.now()
                previous_authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=existing.id).first()
                if previous_authority:
                    previous_authority.stale_status = "STALE"
                    previous_authority.stale_reasons = existing.stale_reasons
                    previous_authority.updated_at = datetime.now()
            pending_writes.append((ir, existing_pointer, existing))

        for ir, existing_pointer, existing in pending_writes:
            envelope = {
                "schema_version": "prompt_ir_authority_envelope_v2",
                "source_authority": ir["source_authority"],
                "compiler_provenance": ir["compiler_provenance"],
                "generation_policy": ir["generation_policy"],
                "asset_authority_bindings": ir["asset_authority_bindings"],
                "prompt_ir_payload_hash": ir["payload_hash"],
                "qualification_state": "PROMPT_IR_QUALIFIED",
                "model_generation_ready": False,
                "stale_status": "FRESH",
            }
            envelope["envelope_fingerprint"] = phase_e_fingerprint(envelope)
            version = PromptIRVersion(book_id=book_id, episode=episode, scene_id=str(ir.get("scene_id") or ""), storyboard_shot_id=int(ir["storyboard_shot_id"]), materialization_set_id=int(ir["source_authority"].get("storyboard_materialization_set_id") or 0), plan_shot_id=str(ir["plan_shot_id"]), schema_version=ir["schema_version"], payload_json=json.dumps(ir, ensure_ascii=False, sort_keys=True), payload_hash=ir["payload_hash"], compiler_version=ir["compiler_provenance"]["compiler_version"], compiler_policy_version=ir["compiler_provenance"]["compiler_policy_version"], retention_policy_version="generation_policy_v1", authority_envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state="PROMPT_IR_QUALIFIED", asset_reference_state="ASSET_REFERENCE_PENDING", model_generation_ready="false", stale_status="FRESH", stale_reasons="[]", created_at=datetime.now(), updated_at=datetime.now())
            session.add(version)
            session.flush()
            authority = PromptIRAuthority(prompt_ir_version_id=version.id, book_id=book_id, episode=episode, storyboard_shot_id=version.storyboard_shot_id, envelope_fingerprint=envelope["envelope_fingerprint"], envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state="PROMPT_IR_QUALIFIED", stale_status="FRESH", stale_reasons="[]", created_at=datetime.now(), updated_at=datetime.now())
            session.add(authority)
            session.flush()
            pointer = existing_pointer or PromptIRPointer(book_id=book_id, episode=episode, storyboard_shot_id=version.storyboard_shot_id)
            pointer.prompt_ir_version_id = version.id
            pointer.payload_hash = version.payload_hash
            pointer.qualification_state = version.qualification_state
            pointer.updated_at = datetime.now()
            session.add(pointer)
            results.append({"storyboard_shot_id": version.storyboard_shot_id, "prompt_ir_version_id": version.id, "prompt_ir_authority_id": authority.id, "reused": False, "payload_hash": version.payload_hash})
        session.commit()
        return {"schema_version": "prompt_ir_phase_e_compile_v1", "mutated": bool(pending_writes), "reused_count": sum(1 for item in results if item["reused"]), "compiled_count": len(results), "shots": results, "provider_calls": 0, "llm_calls": 0, "media_generated": False}


__all__ = ["router"]
