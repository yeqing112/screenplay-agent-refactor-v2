"""DirectorTreatment Shadow/Assist boundary API.

The first M1 slice is intentionally read-only by default.  It builds a frozen
scene evidence snapshot from the current script and declared visual assets,
then produces a deterministic treatment draft.  ``persist=true`` only stores
that draft as a ``DirectorTreatment`` row; it never calls an LLM or mutates
Script/StoryboardShot/AgentPlan.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from core.director_treatment import build_shadow_treatment
from core.decision_packet import decision_packet_fingerprint, normalize_decision_packet
from core.script_ir import resolve_script_payload
import core.llm as llm_client
from models import DecisionPacketRecord, DirectorTreatment, Script, Session, VisualMakeup, VisualReferenceAsset


router = APIRouter(prefix="/api/books", tags=["director-treatment"])


class DirectorTreatmentPreviewRequest(BaseModel):
    episode: int | None = Field(default=None, ge=1)
    scene_name: str = Field(default="", validation_alias=AliasChoices("scene_name", "sceneName"))
    source_script_revision: str = Field(default="", validation_alias=AliasChoices("source_script_revision", "sourceScriptRevision"))
    skill_id: str = Field(default="", validation_alias=AliasChoices("skill_id", "skillId"))
    skill_version: str = Field(default="", validation_alias=AliasChoices("skill_version", "skillVersion"))
    persist: bool = False
    workflow_profile: str = Field(default="creative_draft", validation_alias=AliasChoices("workflow_profile", "workflowProfile"))


class DirectorTreatmentLlmDraftRequest(DirectorTreatmentPreviewRequest):
    packet_fingerprint: str = Field(default="", validation_alias=AliasChoices("packet_fingerprint", "packetFingerprint"))
    confirmed: bool = False
    allow_external_call: bool = Field(default=False, validation_alias=AliasChoices("allow_external_call", "allowExternalCall"))


class DirectorTreatmentConfirmRequest(BaseModel):
    """Human confirmation boundary for a Treatment candidate.

    ``candidate`` is optional: callers may submit an edited candidate, but it
    is always validated against the frozen baseline and the same whitelist as
    the LLM response.  No confirm operation can silently use a stale packet.
    """

    packet_id: int = Field(validation_alias=AliasChoices("packet_id", "packetId"))
    packet_fingerprint: str = Field(default="", validation_alias=AliasChoices("packet_fingerprint", "packetFingerprint"))
    confirmed: bool = False
    candidate: dict[str, Any] | None = None
    workflow_profile: str = Field(default="creative_draft", validation_alias=AliasChoices("workflow_profile", "workflowProfile"))


def _json_object(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _script_payload(row: Script) -> dict[str, Any]:
    parsed = _json_object(row.content, {})
    return parsed if isinstance(parsed, dict) else {"raw_content": str(row.content or "")}


def _find_scene(script: dict[str, Any], scene_name: str) -> dict[str, Any]:
    scenes = script.get("scenes") if isinstance(script.get("scenes"), list) else []
    wanted = scene_name.strip()
    if wanted:
        for scene in scenes:
            if isinstance(scene, dict) and str(scene.get("name") or "").strip() == wanted:
                return scene
        raise HTTPException(status_code=404, detail=f"Scene not found: {wanted}")
    if scenes and isinstance(scenes[0], dict):
        return scenes[0]
    raise HTTPException(status_code=404, detail="The selected episode has no structured scenes.")


def _evidence_fingerprint(evidence: dict[str, Any]) -> str:
    canonical = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _candidate_fingerprint(candidate: dict[str, Any], evidence_fingerprint: str) -> str:
    """Fingerprint the reviewed content separately from its source evidence."""
    canonical = json.dumps({"evidence": evidence_fingerprint, "candidate": candidate}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _make_decision_packet(book_id: int, episode: int, treatment: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    evidence_items = [
        {"id": f"script:{evidence['script']['id']}", "tier": "source_text", "summary": json.dumps(evidence["scene"], ensure_ascii=False), "version": evidence["script"]["revision"]},
        {"id": f"treatment:{treatment['prompt_fingerprint']}", "tier": "derived_fact", "summary": json.dumps(treatment, ensure_ascii=False), "version": "shadow-v1"},
        {"id": f"assets:{book_id}:{episode}", "tier": "approved_fact", "summary": json.dumps({"characters": evidence["characters"], "locked_references": evidence["locked_references"]}, ensure_ascii=False), "version": "current"},
    ]
    packet = normalize_decision_packet({
        "domain": "director_treatment",
        "scope": {"book_id": book_id, "episode": episode, "scene_name": evidence["scene_name"], "treatment_fingerprint": treatment["prompt_fingerprint"]},
        "evidence": evidence_items,
        "unknowns": treatment.get("unknowns") or [],
        "conflicts": [],
        "allowed_operations": ["propose_director_treatment", "request_missing_information"],
    })
    packet["packet_fingerprint"] = decision_packet_fingerprint(packet)
    return packet


TREATMENT_CANDIDATE_FIELDS = {
    "dramatic_objective", "audience_question", "character_intents", "beat_map",
    "relationship_power_shift", "audience_emotion", "information_strategy",
    "performance_direction", "visual_strategy", "coverage_strategy", "sound_strategy",
    "edit_rhythm", "constraints", "unknowns",
}


def _validate_llm_candidate(raw: Any, baseline: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("DirectorTreatment LLM output must be a JSON object")
    # Models often echo the frozen scene identity. It is evidence, not an
    # editable candidate field: accept it only when it exactly matches the
    # baseline, then omit it from the persisted proposal.
    permitted = TREATMENT_CANDIDATE_FIELDS | {"scene_name", "decision", "confidence", "human_confirmation_required", "note"}
    unexpected = sorted(set(raw) - permitted)
    if unexpected:
        raise ValueError(f"LLM candidate contains non-whitelisted fields: {', '.join(unexpected)}")
    if "scene_name" in raw and str(raw.get("scene_name") or "").strip() != str(baseline.get("scene_name") or "").strip():
        raise ValueError("LLM candidate scene_name must match the frozen scene")
    candidate = {field: raw.get(field, baseline.get(field)) for field in TREATMENT_CANDIDATE_FIELDS}
    base_intents = baseline.get("character_intents") if isinstance(baseline.get("character_intents"), dict) else {}
    intents = candidate.get("character_intents")
    if not isinstance(intents, dict) or not set(intents).issubset(set(base_intents)):
        raise ValueError("LLM candidate character_intents must use only declared character ids")
    base_beats = baseline.get("beat_map") if isinstance(baseline.get("beat_map"), list) else []
    beat_ids = {str(item.get("beat_id")) for item in base_beats if isinstance(item, dict)}
    beats = candidate.get("beat_map")
    if not isinstance(beats, list) or any(not isinstance(item, dict) or str(item.get("beat_id")) not in beat_ids for item in beats):
        raise ValueError("LLM candidate beat_map must use only declared beat ids")
    candidate["decision"] = str(raw.get("decision") or "ready_for_review")
    candidate["confidence"] = raw.get("confidence", 0.0)
    candidate["human_confirmation_required"] = True
    candidate["note"] = str(raw.get("note") or "LLM candidate only; no domain write performed.")
    return candidate


def _build_preview(book_id: int, req: DirectorTreatmentPreviewRequest) -> tuple[dict[str, Any], dict[str, Any], Script]:
    with Session() as session:
        script_row = (
            session.query(Script)
            .filter_by(book_id=book_id, episode=req.episode)
            .order_by(Script.id.desc())
            .first()
        )
        if not script_row:
            raise HTTPException(status_code=404, detail="No script found for this episode.")
        script = resolve_script_payload(session, script_row, workflow_profile=req.workflow_profile)
        scene = _find_scene(script, req.scene_name)
        characters = []
        for row in session.query(VisualMakeup).filter_by(book_id=book_id, episode=req.episode).order_by(VisualMakeup.id):
            meta = _json_object(row.meta_info, {})
            structured = meta.get("structured_result") if isinstance(meta, dict) else {}
            characters.append({
                "id": str(row.id),
                "name": row.character_name,
                "gender": str(structured.get("gender") or "") if isinstance(structured, dict) else "",
                "asset_status": row.asset_status,
                "stage_name": row.stage_name,
                "refined_outfit": row.refined_outfit,
                "hair_style": row.hair_style,
            })
        locked_refs = [
            {"id": row.id, "asset_type": row.asset_type, "asset_id": row.asset_id, "asset_name": row.asset_name, "status": row.status}
            for row in session.query(VisualReferenceAsset)
            .filter_by(book_id=book_id, episode=req.episode, status="locked")
            .order_by(VisualReferenceAsset.id)
        ]

        script_hash = hashlib.sha256((script_row.content or "").encode("utf-8")).hexdigest()
        source_revision = req.source_script_revision.strip() or f"script-{script_row.id}"
        evidence = {
            "book_id": book_id,
            "episode": req.episode,
            "scene": scene,
            "scene_name": str(scene.get("name") or "").strip(),
            "script": {"id": script_row.id, "revision": source_revision, "hash": script_hash},
            "characters": characters,
            "locked_references": locked_refs,
            "constraints": ["locked_asset_facts_are_immutable", "treatment_does_not_mutate_shots"],
        }
        evidence["evidence_fingerprint"] = _evidence_fingerprint(evidence)
        treatment = build_shadow_treatment(
            scene=scene,
            characters=characters,
            source_script_revision=source_revision,
            skill_id=req.skill_id.strip(),
            skill_version=req.skill_version.strip(),
        )
        treatment["source_script_hash"] = script_hash
        treatment["evidence_fingerprint"] = evidence["evidence_fingerprint"]
        return treatment, evidence, script_row


def _treatment_row_payload(row: DirectorTreatment) -> dict[str, Any]:
    """Return a stable, JSON-friendly representation for UI and audit clients."""
    return {
        "id": row.id,
        "book_id": row.book_id,
        "episode": row.episode,
        "scene_name": row.scene_name,
        "revision": row.revision,
        "status": row.status,
        "execution_status": row.execution_status,
        "quality_status": row.quality_status,
        "production_status": row.production_status,
        "workflow_profile": row.workflow_profile,
        "source_script_revision": row.source_script_revision,
        "source_script_hash": row.source_script_hash,
        "dramatic_objective": row.dramatic_objective,
        "audience_question": row.audience_question,
        "character_intents": _json_object(row.character_intents, {}),
        "beat_map": _json_object(row.beat_map, []),
        "relationship_power_shift": row.relationship_power_shift,
        "audience_emotion": row.audience_emotion,
        "information_strategy": row.information_strategy,
        "performance_direction": row.performance_direction,
        "visual_strategy": row.visual_strategy,
        "coverage_strategy": row.coverage_strategy,
        "sound_strategy": row.sound_strategy,
        "edit_rhythm": row.edit_rhythm,
        "constraints": _json_object(row.constraints, []),
        "unknowns": _json_object(row.unknowns, []),
        "skill_id": row.skill_id,
        "skill_version": row.skill_version,
        "decision_packet_id": row.decision_packet_id,
        "model_info": _json_object(row.model_info, {}),
        "prompt_fingerprint": row.prompt_fingerprint,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


_TREATMENT_DIFF_FIELDS = (
    "dramatic_objective", "audience_question", "character_intents", "beat_map",
    "relationship_power_shift", "audience_emotion", "information_strategy",
    "performance_direction", "visual_strategy", "coverage_strategy", "sound_strategy",
    "edit_rhythm", "constraints", "unknowns",
)


def _treatment_diff(previous: DirectorTreatment | None, current: DirectorTreatment) -> dict[str, Any]:
    """Build a compact, deterministic diff suitable for history/replay UI."""
    if not previous:
        return {"from_revision": None, "changed_fields": list(_TREATMENT_DIFF_FIELDS), "changes": {}}
    changes: dict[str, dict[str, Any]] = {}
    for field in _TREATMENT_DIFF_FIELDS:
        before = getattr(previous, field)
        after = getattr(current, field)
        if field in {"character_intents", "beat_map", "constraints", "unknowns"}:
            before_value = _json_object(before, {} if field == "character_intents" else [])
            after_value = _json_object(after, {} if field == "character_intents" else [])
        else:
            before_value, after_value = before or "", after or ""
        if before_value != after_value:
            changes[field] = {"before": before_value, "after": after_value}
    return {"from_revision": previous.revision, "changed_fields": sorted(changes), "changes": changes}


@router.post("/{book_id}/episodes/{episode}/director-treatment/preview")
def preview_director_treatment(book_id: int, episode: int, req: DirectorTreatmentPreviewRequest) -> dict[str, Any]:
    if req.episode is not None and episode != req.episode:
        raise HTTPException(status_code=400, detail="Episode in path and body must match.")
    req.episode = episode
    treatment, evidence, script_row = _build_preview(book_id, req)
    packet = _make_decision_packet(book_id, episode, treatment, evidence)
    persisted_id = None
    if req.persist:
        with Session() as session:
            existing = (
                session.query(DirectorTreatment)
                .filter_by(book_id=book_id, episode=episode, scene_name=treatment["scene_name"], prompt_fingerprint=treatment["prompt_fingerprint"])
                .order_by(DirectorTreatment.id.desc())
                .first()
            )
            if existing:
                persisted_id = existing.id
            else:
                row = DirectorTreatment(
                    book_id=book_id,
                    episode=episode,
                    scene_name=treatment["scene_name"],
                    revision=1,
                    status="draft",
                    source_script_revision=treatment["source_script_revision"],
                    source_script_hash=treatment["source_script_hash"],
                    dramatic_objective=treatment["dramatic_objective"],
                    audience_question=treatment["audience_question"],
                    character_intents=json.dumps(treatment["character_intents"], ensure_ascii=False),
                    beat_map=json.dumps(treatment["beat_map"], ensure_ascii=False),
                    relationship_power_shift=treatment["relationship_power_shift"],
                    audience_emotion=treatment["audience_emotion"],
                    information_strategy=treatment["information_strategy"],
                    performance_direction=treatment["performance_direction"],
                    visual_strategy=treatment["visual_strategy"],
                    coverage_strategy=treatment["coverage_strategy"],
                    sound_strategy=treatment["sound_strategy"],
                    edit_rhythm=treatment["edit_rhythm"],
                    constraints=json.dumps(treatment["constraints"], ensure_ascii=False),
                    unknowns=json.dumps(treatment["unknowns"], ensure_ascii=False),
                    skill_id=treatment["skill_id"],
                    skill_version=treatment["skill_version"],
                    model_info=json.dumps(treatment["model_info"], ensure_ascii=False),
                    prompt_fingerprint=treatment["prompt_fingerprint"],
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    workflow_profile=req.workflow_profile,
                )
                session.add(row)
                session.commit()
                persisted_id = row.id
    return {
        "mode": "shadow_deterministic",
        "llm_called": False,
        "mutated": bool(persisted_id),
        "persisted_draft_id": persisted_id,
        "script_id": script_row.id,
        "evidence": evidence,
        "packet_fingerprint": packet["packet_fingerprint"],
        "treatment": treatment,
        "requires_approval": True,
        "message": "这是只读导演方案草案；批准门禁和 SceneBlocking 尚未执行。",
    }


@router.post("/{book_id}/episodes/{episode}/director-treatment/llm-draft")
def generate_director_treatment_llm_draft(book_id: int, episode: int, req: DirectorTreatmentLlmDraftRequest) -> dict[str, Any]:
    """Generate a reviewable Treatment candidate after explicit confirmation.

    The endpoint follows the DecisionPacket boundary: it freezes and validates
    the current evidence, requires ``confirmed`` + ``allowExternalCall``,
    deduplicates an identical completed request, and stores only a proposal in
    the packet record.  It never creates an approved Treatment or changes a
    script/shot.
    """
    if req.episode is not None and req.episode != episode:
        raise HTTPException(status_code=400, detail="Episode in path and body must match.")
    if not (req.confirmed and req.allow_external_call):
        raise HTTPException(status_code=409, detail="Calling the Treatment LLM requires confirmed=true and allowExternalCall=true.")
    req.episode = episode
    treatment, evidence, _ = _build_preview(book_id, req)
    packet = _make_decision_packet(book_id, episode, treatment, evidence)
    if req.packet_fingerprint and req.packet_fingerprint != packet["packet_fingerprint"]:
        raise HTTPException(status_code=409, detail="Treatment evidence changed; reload the preview before calling the LLM.")

    prompt = (
        "你是受证据约束的影视导演方案助手。仅输出 JSON object，不要 Markdown。\n"
        "根据以下冻结证据生成 DirectorTreatment 候选。只能改写候选字段，必须沿用已有 character id 和 beat_id；"
        "不得新增角色、道具、场景事实，不得输出镜头或执行操作。所有候选仍需人工确认。\n\n"
        f"FROZEN_EVIDENCE={json.dumps(evidence, ensure_ascii=False, sort_keys=True)}\n"
        f"BASE_TREATMENT={json.dumps(treatment, ensure_ascii=False, sort_keys=True)}\n"
        f"RETURN_FIELDS={json.dumps(sorted(TREATMENT_CANDIDATE_FIELDS), ensure_ascii=False)}"
    )

    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(book_id=book_id, packet_fingerprint=packet["packet_fingerprint"]).first()
        if not row:
            row = DecisionPacketRecord(
                book_id=book_id,
                domain="director_treatment",
                scope=json.dumps(packet["scope"], ensure_ascii=False),
                packet_fingerprint=packet["packet_fingerprint"],
                evidence=json.dumps(packet["evidence"], ensure_ascii=False),
                unknowns=json.dumps(packet["unknowns"], ensure_ascii=False),
                conflicts=json.dumps(packet["conflicts"], ensure_ascii=False),
                allowed_operations=json.dumps(packet["allowed_operations"], ensure_ascii=False),
                proposal=json.dumps({"decision": "awaiting_llm"}, ensure_ascii=False),
                model_info=json.dumps({"mode": "director_treatment_llm_draft", "llm_generated": False}, ensure_ascii=False),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
        info = _json_object(row.model_info, {})
        if isinstance(info, dict) and info.get("llm_draft_in_progress"):
            raise HTTPException(status_code=409, detail="This Treatment evidence packet already has an LLM request in progress.")
        if isinstance(info, dict) and info.get("llm_generated"):
            return {"packet_id": row.id, "packet_fingerprint": row.packet_fingerprint, "candidate": _json_object(row.proposal, {}), "llm_called": False, "deduplicated": True, "domain_write_performed": False}
        row.model_info = json.dumps({**(info if isinstance(info, dict) else {}), "llm_draft_in_progress": True, "llm_draft_started_at": datetime.now().isoformat()}, ensure_ascii=False)
        row.status = "draft"
        session.commit()
        packet_id = row.id

    try:
        raw = llm_client.call_llm_json(
            prompt,
            system="你是受证据约束的 DirectorTreatment 编译器。",
            required_keys={"dramatic_objective", "audience_question", "character_intents", "beat_map", "visual_strategy"},
            estimated_tokens=5000,
        )
        candidate = _validate_llm_candidate(raw, treatment)
    except Exception as exc:
        with Session() as session:
            row = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
            if row:
                info = _json_object(row.model_info, {})
                row.model_info = json.dumps({**(info if isinstance(info, dict) else {}), "llm_draft_in_progress": False, "last_llm_draft_failure": str(exc)[:500]}, ensure_ascii=False)
                session.commit()
        raise HTTPException(status_code=502, detail=f"DirectorTreatment LLM draft failed: {str(exc)[:500]}") from exc

    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
        if not row:
            raise HTTPException(status_code=409, detail="Treatment decision packet disappeared while the LLM was running.")
        info = _json_object(row.model_info, {})
        row.proposal = json.dumps(candidate, ensure_ascii=False)
        row.model_info = json.dumps({**(info if isinstance(info, dict) else {}), "llm_draft_in_progress": False, "llm_generated": True, "generated_at": datetime.now().isoformat()}, ensure_ascii=False)
        row.status = "draft"
        row.updated_at = datetime.now()
        session.commit()
        return {"packet_id": row.id, "packet_fingerprint": row.packet_fingerprint, "candidate": candidate, "llm_called": True, "deduplicated": False, "domain_write_performed": False}


@router.get("/{book_id}/episodes/{episode}/director-treatments")
def list_director_treatments(book_id: int, episode: int) -> dict[str, Any]:
    """List Treatment revisions for the episode without exposing secrets."""
    with Session() as session:
        rows = (
            session.query(DirectorTreatment)
            .filter_by(book_id=book_id, episode=episode)
            .order_by(DirectorTreatment.scene_name, DirectorTreatment.revision.asc(), DirectorTreatment.id.asc())
            .all()
        )
    items = []
    previous_by_scene: dict[str, DirectorTreatment] = {}
    for row in rows:
        item = _treatment_row_payload(row)
        item["diff"] = _treatment_diff(previous_by_scene.get(row.scene_name), row)
        items.append(item)
        previous_by_scene[row.scene_name] = row
    items.sort(key=lambda item: (str(item["scene_name"]), -int(item["revision"]), -int(item["id"])))
    return {"items": items}


@router.get("/{book_id}/episodes/{episode}/director-treatment/candidates")
def list_director_treatment_candidates(book_id: int, episode: int) -> dict[str, Any]:
    """List auditable LLM candidates for history/replay without secrets."""
    with Session() as session:
        packets = (
            session.query(DecisionPacketRecord)
            .filter_by(book_id=book_id, domain="director_treatment")
            .order_by(DecisionPacketRecord.id.desc())
            .all()
        )
    items = []
    for packet in packets:
        scope = _json_object(packet.scope, {})
        if not isinstance(scope, dict) or int(scope.get("episode") or 0) != episode:
            continue
        items.append({
            "packet_id": packet.id,
            "packet_fingerprint": packet.packet_fingerprint,
            "scene_name": str(scope.get("scene_name") or ""),
            "status": packet.status,
            "candidate": _json_object(packet.proposal, {}),
            "model_info": _json_object(packet.model_info, {}),
            "confirmed_at": packet.confirmed_at.isoformat() if packet.confirmed_at else None,
            "created_at": packet.created_at.isoformat() if packet.created_at else None,
            "updated_at": packet.updated_at.isoformat() if packet.updated_at else None,
        })
    return {"items": items}


@router.post("/{book_id}/episodes/{episode}/director-treatment/confirm")
def confirm_director_treatment(book_id: int, episode: int, req: DirectorTreatmentConfirmRequest) -> dict[str, Any]:
    """Approve a reviewable candidate and create a new immutable revision.

    The packet is re-derived from the current script before any write.  A
    changed script, scene, or asset evidence invalidates the candidate and
    leaves the existing approved revision untouched.
    """
    if not req.confirmed:
        raise HTTPException(status_code=409, detail="Treatment approval requires confirmed=true.")

    with Session() as session:
        packet = session.query(DecisionPacketRecord).filter_by(id=req.packet_id, book_id=book_id).first()
        if not packet or packet.domain != "director_treatment":
            raise HTTPException(status_code=404, detail="DirectorTreatment decision packet not found.")
        if req.packet_fingerprint and req.packet_fingerprint != packet.packet_fingerprint:
            raise HTTPException(status_code=409, detail="Treatment packet fingerprint does not match.")
        if packet.status in {"confirmed", "superseded"}:
            raise HTTPException(status_code=409, detail="This Treatment packet has already been finalized.")
        info = _json_object(packet.model_info, {})
        if not isinstance(info, dict) or not info.get("llm_generated"):
            raise HTTPException(status_code=409, detail="Only an LLM-generated candidate can be approved.")
        scope = _json_object(packet.scope, {})
        scene_name = str(scope.get("scene_name") or "").strip() if isinstance(scope, dict) else ""

    # Rebuild outside the transaction so the expensive evidence read does not
    # hold the packet row lock.  The fingerprint check below is the commit
    # boundary and protects against a changed script during the read.
    baseline, evidence, _ = _build_preview(book_id, DirectorTreatmentPreviewRequest(episode=episode, scene_name=scene_name, workflow_profile=req.workflow_profile))
    current_packet = _make_decision_packet(book_id, episode, baseline, evidence)
    if current_packet["packet_fingerprint"] != packet.packet_fingerprint:
        with Session() as session:
            stale = session.query(DecisionPacketRecord).filter_by(id=req.packet_id, book_id=book_id).first()
            if stale and stale.status == "draft":
                stale.status = "superseded"
                stale.updated_at = datetime.now()
                session.commit()
        raise HTTPException(status_code=409, detail="Treatment evidence changed; candidate is stale and must be regenerated.")

    raw_candidate = req.candidate if req.candidate is not None else _json_object(packet.proposal, {})
    try:
        candidate = _validate_llm_candidate(raw_candidate, baseline)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"Treatment candidate is invalid: {exc}") from exc

    with Session() as session:
        packet = session.query(DecisionPacketRecord).filter_by(id=req.packet_id, book_id=book_id).first()
        if not packet or packet.status in {"confirmed", "superseded"}:
            raise HTTPException(status_code=409, detail="This Treatment packet has already been finalized.")
        previous = (
            session.query(DirectorTreatment)
            .filter_by(book_id=book_id, episode=episode, scene_name=baseline["scene_name"], status="approved")
            .order_by(DirectorTreatment.revision.desc(), DirectorTreatment.id.desc())
            .first()
        )
        next_revision = (previous.revision + 1) if previous else 1
        previous_id = previous.id if previous else None
        if previous:
            previous.status = "superseded"
            previous.updated_at = datetime.now()
        model_info = {
            **(baseline.get("model_info") if isinstance(baseline.get("model_info"), dict) else {}),
            "mode": "confirmed_llm_candidate",
            "llm_called": True,
            "candidate_decision": candidate.get("decision"),
            "candidate_fingerprint": _candidate_fingerprint(candidate, current_packet["packet_fingerprint"]),
            "confirmed_at": datetime.now().isoformat(),
            "rollback_anchor": {"previous_treatment_id": previous_id, "previous_revision": previous.revision if previous else None},
        }
        row = DirectorTreatment(
            book_id=book_id, episode=episode, scene_name=baseline["scene_name"], revision=next_revision, status="approved",
            source_script_revision=baseline["source_script_revision"], source_script_hash=baseline["source_script_hash"],
            dramatic_objective=candidate["dramatic_objective"], audience_question=candidate["audience_question"],
            character_intents=json.dumps(candidate["character_intents"], ensure_ascii=False), beat_map=json.dumps(candidate["beat_map"], ensure_ascii=False),
            relationship_power_shift=candidate["relationship_power_shift"], audience_emotion=candidate["audience_emotion"], information_strategy=candidate["information_strategy"],
            performance_direction=candidate["performance_direction"], visual_strategy=candidate["visual_strategy"], coverage_strategy=candidate["coverage_strategy"],
            sound_strategy=candidate["sound_strategy"], edit_rhythm=candidate["edit_rhythm"], constraints=json.dumps(candidate["constraints"], ensure_ascii=False),
            unknowns=json.dumps(candidate["unknowns"], ensure_ascii=False), skill_id=baseline["skill_id"], skill_version=baseline["skill_version"],
            decision_packet_id=packet.id, model_info=json.dumps(model_info, ensure_ascii=False), prompt_fingerprint=_candidate_fingerprint(candidate, current_packet["packet_fingerprint"]),
            created_at=datetime.now(), updated_at=datetime.now(), workflow_profile=req.workflow_profile,
        )
        session.add(row)
        packet.status = "confirmed"
        packet.confirmed_at = datetime.now()
        packet.proposal = json.dumps(candidate, ensure_ascii=False)
        packet.updated_at = datetime.now()
        session.commit()
        session.refresh(row)
        return {
            "approved": True,
            "treatment": _treatment_row_payload(row),
            "packet_id": packet.id,
            "packet_fingerprint": packet.packet_fingerprint,
            "rollback_anchor": model_info["rollback_anchor"],
            "mutated": True,
            "production_operations": [],
        }
