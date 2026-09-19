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
from core.director_semantics import validate_director_contract
from core.director_provenance import confirmation_event, project_legacy_flags, proposal_provenance, resolve_canonical_origin
from core.director_treatment_authority import (
    build_treatment_authority_envelope,
    classify_asset_authority,
    payload_hash as treatment_payload_hash,
    resolve_scene_for_treatment,
    treatment_payload_from_row,
    validate_treatment_candidate,
)
from core.decision_packet import decision_packet_fingerprint, normalize_decision_packet
from core.script_ir import resolve_script_payload
import core.llm as llm_client
from models import DecisionPacketRecord, DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer, Script, ScriptIRVersion, Session, VisualMakeup, VisualReferenceAsset


router = APIRouter(prefix="/api/books", tags=["director-treatment"])


class DirectorTreatmentPreviewRequest(BaseModel):
    episode: int | None = Field(default=None, ge=1)
    scene_name: str = Field(default="", validation_alias=AliasChoices("scene_name", "sceneName"))
    scene_id: str = Field(default="", validation_alias=AliasChoices("scene_id", "sceneId"))
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
        "scope": {"book_id": book_id, "episode": episode, "scene_id": evidence.get("scene_id", ""), "scene_name": evidence["scene_name"], "treatment_fingerprint": treatment["prompt_fingerprint"]},
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
    # Phase B enrichments are stored in the existing director_decisions
    # projection and remain candidate-only until the normal confirmation
    # boundary succeeds.
    "scene_objective", "dramatic_question", "audience_state_in", "audience_state_out",
    "suspicion_or_information_strategy", "character_directions", "beat_directions",
    "director_beat_decisions", "director_contract_version", "performance_arc", "rhythm_strategy", "visual_priority", "scene_exit_intent",
    "prohibited_interpretations",
    "proposal_origin", "proposal_provenance",
}


def _validate_llm_candidate(raw: Any, baseline: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("DirectorTreatment LLM output must be a JSON object")
    # Models often echo the frozen scene identity. It is evidence, not an
    # editable candidate field: accept it only when it exactly matches the
    # baseline, then omit it from the persisted proposal.
    permitted = TREATMENT_CANDIDATE_FIELDS | {"scene_id", "scene_name", "decision", "confidence", "human_confirmation_required", "note"}
    unexpected = sorted(set(raw) - permitted)
    if unexpected:
        raise ValueError(f"LLM candidate contains non-whitelisted fields: {', '.join(unexpected)}")
    if "scene_name" in raw and str(raw.get("scene_name") or "").strip() != str(baseline.get("scene_name") or "").strip():
        raise ValueError("LLM candidate scene_name must match the frozen scene")
    if "scene_id" in raw and str(raw.get("scene_id") or "").strip() != str(baseline.get("scene_id") or "").strip():
        raise ValueError("LLM candidate scene_id must match the frozen scene")
    candidate = {field: raw.get(field, baseline.get(field)) for field in TREATMENT_CANDIDATE_FIELDS}
    base_intents = baseline.get("character_intents") if isinstance(baseline.get("character_intents"), dict) else {}
    intents = candidate.get("character_intents")
    if not isinstance(intents, dict) or not set(intents).issubset(set(base_intents)):
        raise ValueError("LLM candidate character_intents must use only declared character ids")
    # Character identity is evidence, not a creative field.  Merge editable
    # intent suggestions onto the frozen baseline and always retain the
    # baseline name (and any omitted fields) so an LLM response cannot turn an
    # asset id into a display name or silently drop a declared participant.
    candidate["character_intents"] = {
        key: {
            **(base_intents.get(key) if isinstance(base_intents.get(key), dict) else {}),
            **(intents.get(key) if isinstance(intents.get(key), dict) else {}),
        }
        for key in base_intents
    }
    for key, base_intent in base_intents.items():
        if isinstance(base_intent, dict) and base_intent.get("name"):
            candidate["character_intents"][key]["name"] = base_intent["name"]
    base_beats = baseline.get("beat_map") if isinstance(baseline.get("beat_map"), list) else []
    beat_ids = {str(item.get("beat_id")) for item in base_beats if isinstance(item, dict)}
    beats = candidate.get("beat_map")
    # A proposer may omit derived beat annotations, but it may not alter the
    # source beat identity, type or event.  Normalize partial echoes back to
    # the frozen source representation before persisting the candidate.
    if not isinstance(beats, list) or len(beats) != len(base_beats):
        raise ValueError("LLM candidate beat_map must preserve the source beat set")
    for proposed, source in zip(beats, base_beats):
        if not isinstance(proposed, dict) or str(proposed.get("beat_id") or "") != str(source.get("beat_id") or ""):
            raise ValueError("LLM candidate beat_map must preserve source beat ids and order")
        for key in ("type", "event", "dramatic_function", "information_change", "emotion_change"):
            if key in proposed and proposed.get(key) != source.get(key):
                raise ValueError(f"LLM candidate beat_map source field is immutable: {key}")
    candidate["beat_map"] = base_beats
    candidate["decision"] = str(raw.get("decision") or "ready_for_review")
    candidate["confidence"] = raw.get("confidence", 0.0)
    candidate["human_confirmation_required"] = True
    candidate["note"] = str(raw.get("note") or "LLM candidate only; no domain write performed.")
    return validate_treatment_candidate(candidate, baseline)


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
        profile = str(req.workflow_profile or "creative_draft").strip().lower()
        if profile == "production":
            scene, script_ir_version, script, script_ir_envelope = resolve_scene_for_treatment(
                session, script_row, scene_id=req.scene_id, scene_name=req.scene_name, workflow_profile=profile
            )
        else:
            script = resolve_script_payload(session, script_row, workflow_profile=profile)
            scene = _find_scene(script, req.scene_name)
            script_ir_version = None
            script_ir_envelope = None
        characters = []
        makeup_rows = session.query(VisualMakeup).filter_by(book_id=book_id, episode=req.episode).order_by(VisualMakeup.id).all()
        # A treatment is scene-scoped.  When ScriptIR explicitly declares the
        # scene participants, only those bound assets belong in the treatment
        # evidence.  Falling back to all episode assets when the declaration is
        # absent preserves legacy behaviour and keeps missing participant data
        # visible as a blocker instead of silently guessing.
        participant_refs: set[str] = set()
        raw_participants = scene.get("participants") if isinstance(scene, dict) else []
        if isinstance(raw_participants, list):
            for item in raw_participants:
                if isinstance(item, dict):
                    for key in ("id", "character_id", "name", "character"):
                        value = str(item.get(key) or "").strip()
                        if value:
                            participant_refs.add(value)
                else:
                    value = str(item or "").strip()
                    if value:
                        participant_refs.add(value)
        if participant_refs:
            makeup_rows = [
                row for row in makeup_rows
                if str(row.id) in participant_refs or str(row.character_name or "").strip() in participant_refs
            ]
        for row in makeup_rows:
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
        if profile == "production" and participant_refs and not characters:
            # Preserve ScriptIR-declared participant identity as advisory
            # context when no locked makeup asset exists.  This keeps the
            # semantic contract referenceable without promoting a draft asset
            # into production authority.
            characters = [{"id": value, "name": value, "gender": "", "asset_status": "draft", "stage_name": "", "refined_outfit": "", "hair_style": ""} for value in sorted(participant_refs)]
        locked_refs = [
            {"id": row.id, "asset_type": row.asset_type, "asset_id": row.asset_id, "asset_name": row.asset_name, "status": row.status, "image_url": row.image_url, "local_path": row.local_path, "reference_token": row.reference_token, "revision": row.updated_at.isoformat() if row.updated_at else ""}
            for row in session.query(VisualReferenceAsset)
            .filter_by(book_id=book_id, episode=req.episode, status="locked")
            .order_by(VisualReferenceAsset.id)
        ]

        legacy_script_hash = hashlib.sha256((script_row.content or "").encode("utf-8")).hexdigest()
        if profile == "production":
            source_revision = str(script_ir_version.revision)
            source_hash = str(script_ir_version.payload_hash or "")
            source_authority_fingerprint = str((script_ir_envelope or {}).get("envelope_fingerprint") or "")
        else:
            # Client source revision is intentionally retained only for the
            # creative/legacy path.  Production takes all lineage from the
            # current ScriptIR authority envelope.
            source_revision = req.source_script_revision.strip() or f"script-{script_row.id}"
            source_hash = legacy_script_hash
            source_authority_fingerprint = ""
        script_evidence = {"id": script_row.id, "revision": source_revision, "hash": source_hash, "script_ir_version_id": getattr(script_ir_version, "id", None), "script_ir_payload_hash": getattr(script_ir_version, "payload_hash", ""), "script_ir_authority_fingerprint": source_authority_fingerprint}
        if profile != "production":
            script_evidence["legacy_content_hash"] = legacy_script_hash
        evidence = {
            "book_id": book_id,
            "episode": req.episode,
            "scene": scene,
            "scene_id": str(scene.get("scene_id") or "").strip(),
            "scene_name": str(scene.get("name") or "").strip(),
            "scene_identity": {"scene_id": str(scene.get("scene_id") or "").strip(), "scene_name": str(scene.get("name") or "").strip()},
            "script": script_evidence,
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
        treatment["scene_id"] = str(scene.get("scene_id") or "").strip()
        treatment["source_script_hash"] = source_hash
        treatment["source_script_ir_version_id"] = getattr(script_ir_version, "id", None)
        treatment["source_script_ir_revision"] = getattr(script_ir_version, "revision", None)
        treatment["source_script_ir_hash"] = getattr(script_ir_version, "payload_hash", "")
        treatment["source_script_authority_fingerprint"] = source_authority_fingerprint
        treatment["source_fact_snapshot_id"] = (script_ir_envelope or {}).get("fact_snapshot_id", "") if profile == "production" else ""
        treatment["source_fact_snapshot_revision"] = (script_ir_envelope or {}).get("fact_snapshot_revision") if profile == "production" else None
        treatment["source_fact_snapshot_hash"] = (script_ir_envelope or {}).get("fact_snapshot_payload_hash", "") if profile == "production" else ""
        treatment["source_constraints"] = {
            "scene_identity": evidence["scene_identity"],
            "declared_participants": scene.get("participants") if isinstance(scene.get("participants"), list) else [],
            "source_beats": treatment.get("beat_map", []),
            "explicit_story_constraints": scene.get("required_visual_proofs") if isinstance(scene.get("required_visual_proofs"), list) else [],
        }
        treatment["director_decisions"] = {field: treatment.get(field) for field in ("dramatic_objective", "audience_question", "character_intents", "relationship_power_shift", "audience_emotion", "information_strategy", "performance_direction", "visual_strategy", "coverage_strategy", "sound_strategy", "edit_rhythm", "scene_objective", "dramatic_question", "audience_state_in", "audience_state_out", "suspicion_or_information_strategy", "character_directions", "beat_directions", "director_beat_decisions", "director_contract_version", "performance_arc", "rhythm_strategy", "visual_priority", "scene_exit_intent", "prohibited_interpretations") if treatment.get(field) not in (None, "", [], {})}
        treatment["asset_authority"] = classify_asset_authority({"characters": characters, "locked_references": locked_refs})
        treatment["qualification_state"] = "REVIEW_REQUIRED" if profile == "production" else "DRAFT"
        treatment["proposal_origin"] = "GENERATED_DRAFT"
        treatment["proposal_provenance"] = proposal_provenance("GENERATED_DRAFT", provider={"called": False, "calls": 0}, human_input=False)
        treatment["evidence_fingerprint"] = evidence["evidence_fingerprint"]
        return treatment, evidence, script_row


def _treatment_row_payload(row: DirectorTreatment) -> dict[str, Any]:
    """Return a stable, JSON-friendly representation for UI and audit clients."""
    return {
        "id": row.id,
        "book_id": row.book_id,
        "episode": row.episode,
        "scene_id": getattr(row, "scene_id", ""),
        "scene_name": row.scene_name,
        "revision": row.revision,
        "status": row.status,
        "execution_status": row.execution_status,
        "quality_status": row.quality_status,
        "production_status": row.production_status,
        "workflow_profile": row.workflow_profile,
        "source_script_revision": row.source_script_revision,
        "source_script_hash": row.source_script_hash,
        "source_script_ir_version_id": getattr(row, "source_script_ir_version_id", None),
        "source_script_ir_revision": getattr(row, "source_script_ir_revision", None),
        "source_script_ir_hash": getattr(row, "source_script_ir_hash", ""),
        "source_script_authority_fingerprint": getattr(row, "source_script_authority_fingerprint", ""),
        "source_fact_snapshot_id": getattr(row, "source_fact_snapshot_id", ""),
        "source_fact_snapshot_revision": getattr(row, "source_fact_snapshot_revision", None),
        "source_fact_snapshot_hash": getattr(row, "source_fact_snapshot_hash", ""),
        "dramatic_objective": row.dramatic_objective,
        "audience_question": row.audience_question,
        "character_intents": _json_object(row.character_intents, {}),
        "beat_map": _json_object(row.beat_map, []),
        "source_constraints": _json_object(getattr(row, "source_constraints", "{}"), {}),
        "director_decisions": _json_object(getattr(row, "director_decisions", "{}"), {}),
        "unknown_unresolved": _json_object(getattr(row, "unknown_unresolved", "[]"), []),
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
        "payload_hash": getattr(row, "payload_hash", ""),
        "authority_envelope_id": getattr(row, "authority_envelope_id", None),
        "qualification_state": getattr(row, "qualification_state", "DRAFT"),
        "stale_status": getattr(row, "stale_status", "UNKNOWN"),
        "stale_reasons": _json_object(getattr(row, "stale_reasons", "[]"), []),
        "approved_at": getattr(row, "approved_at", None).isoformat() if getattr(row, "approved_at", None) else None,
        "activated_at": getattr(row, "activated_at", None).isoformat() if getattr(row, "activated_at", None) else None,
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
                .filter_by(book_id=book_id, episode=episode, scene_name=treatment["scene_name"], scene_id=treatment.get("scene_id", ""), prompt_fingerprint=treatment["prompt_fingerprint"])
                .order_by(DirectorTreatment.id.desc())
                .first()
            )
            if existing:
                persisted_id = existing.id
            else:
                row = DirectorTreatment(
                    book_id=book_id,
                    episode=episode,
                    scene_id=treatment.get("scene_id", ""),
                    scene_name=treatment["scene_name"],
                    revision=1,
                    status="draft",
                    source_script_revision=treatment["source_script_revision"],
                    source_script_hash=treatment["source_script_hash"],
                    source_script_ir_version_id=treatment.get("source_script_ir_version_id"),
                    source_script_ir_revision=treatment.get("source_script_ir_revision"),
                    source_script_ir_hash=treatment.get("source_script_ir_hash", ""),
                    source_script_authority_fingerprint=treatment.get("source_script_authority_fingerprint", ""),
                    source_fact_snapshot_id=str(treatment.get("source_fact_snapshot_id") or ""),
                    source_fact_snapshot_revision=treatment.get("source_fact_snapshot_revision"),
                    source_fact_snapshot_hash=treatment.get("source_fact_snapshot_hash", ""),
                    dramatic_objective=treatment["dramatic_objective"],
                    audience_question=treatment["audience_question"],
                    character_intents=json.dumps(treatment["character_intents"], ensure_ascii=False),
                    beat_map=json.dumps(treatment["beat_map"], ensure_ascii=False),
                    source_constraints=json.dumps(treatment.get("source_constraints", {}), ensure_ascii=False),
                    director_decisions=json.dumps(treatment.get("director_decisions", {}), ensure_ascii=False),
                    unknown_unresolved=json.dumps(treatment.get("unknowns", []), ensure_ascii=False),
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
                    payload_hash=treatment_payload_hash({key: treatment.get(key) for key in ("scene_id", "scene_name", *TREATMENT_CANDIDATE_FIELDS)}),
                    qualification_state=treatment.get("qualification_state", "DRAFT"),
                    stale_status="FRESH" if req.workflow_profile == "production" else "UNKNOWN",
                    stale_reasons="[]",
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
        "authority_context": {
            "workflow_profile": req.workflow_profile,
            "scene_id": evidence.get("scene_id", ""),
            "source_constraints": treatment.get("source_constraints", {}),
            "director_decisions": treatment.get("director_decisions", {}),
            "unknown_unresolved": treatment.get("unknowns", []),
            "asset_authority": treatment.get("asset_authority", {}),
        },
        "requires_approval": True,
        "review_status": "REVIEW_REQUIRED" if str(req.workflow_profile or "").strip().lower() == "production" else "DRAFT",
        "production_contract_required": str(req.workflow_profile or "").strip().lower() == "production",
        "required_production_fields": ["director_contract_version", "director_beat_decisions"] if str(req.workflow_profile or "").strip().lower() == "production" else [],
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
                model_info=json.dumps({"mode": "director_treatment_proposal", "proposal_provenance": proposal_provenance("GENERATED_DRAFT", provider={"called": False, "calls": 0})}, ensure_ascii=False),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
        info = _json_object(row.model_info, {})
        if isinstance(info, dict) and info.get("llm_draft_in_progress"):
            raise HTTPException(status_code=409, detail="This Treatment evidence packet already has an LLM request in progress.")
        existing_provenance = info.get("proposal_provenance") if isinstance(info, dict) else None
        if isinstance(existing_provenance, dict) and existing_provenance.get("proposal_origin") == "PROVIDER_PROPOSAL":
            return {"packet_id": row.id, "packet_fingerprint": row.packet_fingerprint, "candidate": _json_object(row.proposal, {}), **project_legacy_flags(existing_provenance), "deduplicated": True, "domain_write_performed": False}
        row.model_info = json.dumps({**(info if isinstance(info, dict) else {}), "llm_draft_in_progress": True, "llm_draft_started_at": datetime.now().isoformat()}, ensure_ascii=False)
        row.status = "draft"
        session.commit()
        packet_id = row.id

    audit_records: list[dict[str, Any]] = []
    try:
        raw = llm_client.call_llm_json(
            prompt,
            system="你是受证据约束的 DirectorTreatment 编译器。",
            required_keys={"dramatic_objective", "audience_question", "character_intents", "beat_map", "visual_strategy"},
            audit_callback=lambda record: audit_records.append(dict(record)) if isinstance(record, dict) else None,
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
        provider_record = audit_records[-1] if audit_records else {}
        provider = {"called": bool(audit_records), "calls": len(audit_records), "profile_id": provider_record.get("profile_id"), "model": provider_record.get("vendor_model"), "request_fingerprint": provider_record.get("request_fingerprint"), "response_fingerprint": provider_record.get("response_sha256")}
        provenance = proposal_provenance("PROVIDER_PROPOSAL", provider=provider)
        candidate["proposal_origin"] = "PROVIDER_PROPOSAL"
        candidate["proposal_provenance"] = provenance
        row.proposal = json.dumps(candidate, ensure_ascii=False)
        row.model_info = json.dumps({**(info if isinstance(info, dict) else {}), "llm_draft_in_progress": False, "proposal_provenance": provenance, "provider_audit": provider_record, "generated_at": datetime.now().isoformat(), **project_legacy_flags(provenance)}, ensure_ascii=False)
        row.status = "draft"
        row.updated_at = datetime.now()
        session.commit()
        return {"packet_id": row.id, "packet_fingerprint": row.packet_fingerprint, "candidate": candidate, **project_legacy_flags(provenance), "deduplicated": False, "domain_write_performed": False}


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

    # Production approval is a single atomic boundary: the reviewed candidate
    # is persisted, its immutable authority envelope is created, and the
    # scene's current pointer is updated in one transaction.  Creative draft
    # retains the historical approval behaviour below.
    if str(req.workflow_profile or "creative_draft").strip().lower() == "production":
        return _confirm_production_director_treatment(book_id, episode, req)

    with Session() as session:
        packet = session.query(DecisionPacketRecord).filter_by(id=req.packet_id, book_id=book_id).first()
        if not packet or packet.domain != "director_treatment":
            raise HTTPException(status_code=404, detail="DirectorTreatment decision packet not found.")
        if req.packet_fingerprint and req.packet_fingerprint != packet.packet_fingerprint:
            raise HTTPException(status_code=409, detail="Treatment packet fingerprint does not match.")
        if packet.status in {"confirmed", "superseded"}:
            raise HTTPException(status_code=409, detail="This Treatment packet has already been finalized.")
        info = _json_object(packet.model_info, {})
        if not isinstance(info, dict):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PROVENANCE_REQUIRED", "message": "Production confirmation requires proposal provenance."})
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


def _confirm_production_director_treatment(book_id: int, episode: int, req: DirectorTreatmentConfirmRequest) -> dict[str, Any]:
    """Authority-bound production Treatment activation; provider-free."""
    from core.director_treatment_authority import resolve_scene_for_treatment
    with Session() as session:
        packet = session.query(DecisionPacketRecord).filter_by(id=req.packet_id, book_id=book_id, domain="director_treatment").first()
        if not packet:
            raise HTTPException(status_code=404, detail="DirectorTreatment decision packet not found.")
        if req.packet_fingerprint and req.packet_fingerprint != packet.packet_fingerprint:
            raise HTTPException(status_code=409, detail="Treatment packet fingerprint does not match.")
        info = _json_object(packet.model_info, {})
        if not isinstance(info, dict):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PROVENANCE_REQUIRED", "message": "Production confirmation requires proposal provenance."})
        scope = _json_object(packet.scope, {})
        scene_id = str(scope.get("scene_id") or "").strip() if isinstance(scope, dict) else ""
        scene_name = str(scope.get("scene_name") or "").strip() if isinstance(scope, dict) else ""
        if not scene_id:
            raise HTTPException(status_code=409, detail={"code": "SCENE_ID_REQUIRED", "message": "Production Treatment approval requires scene_id."})
        script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not script_row:
            raise HTTPException(status_code=404, detail="No script found for this episode.")
        try:
            scene, script_ir_version, script_ir_payload, script_ir_envelope = resolve_scene_for_treatment(session, script_row, scene_id=scene_id, scene_name=scene_name, workflow_profile="production")
        except HTTPException:
            raise

        # Rebuild the packet from current authoritative evidence.  This check
        # prevents a candidate from being approved against an old ScriptIR,
        # FactSnapshot, scene identity or asset snapshot.
        baseline, evidence, _ = _build_preview(book_id, DirectorTreatmentPreviewRequest(episode=episode, scene_id=scene_id, scene_name=scene_name, workflow_profile="production"))
        current_packet = _make_decision_packet(book_id, episode, baseline, evidence)
        if current_packet["packet_fingerprint"] != packet.packet_fingerprint:
            packet.status = "superseded"; packet.updated_at = datetime.now(); session.commit()
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_EVIDENCE_STALE", "message": "Treatment evidence changed; candidate must be regenerated."})
        raw_candidate = req.candidate if req.candidate is not None else _json_object(packet.proposal, {})
        if not isinstance(raw_candidate, dict):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_SEMANTIC_CONTRACT_REQUIRED", "message": "Production confirmation requires a structured Director semantic contract."})
        missing_contract = [key for key in ("director_contract_version", "director_beat_decisions") if key not in raw_candidate or raw_candidate.get(key) in (None, "", [])]
        if missing_contract:
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_SEMANTIC_CONTRACT_REQUIRED", "message": "Production confirmation requires director_contract_version and director_beat_decisions.", "missing": missing_contract})
        raw_provenance = info.get("proposal_provenance") or raw_candidate.get("proposal_provenance")
        if not isinstance(raw_provenance, dict):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PROVENANCE_REQUIRED", "message": "Production confirmation requires explicit proposal provenance."})
        try:
            provenance = proposal_provenance(raw_provenance.get("proposal_origin", ""), provider=raw_provenance.get("provider"), human_input=(raw_provenance.get("authoring") or {}).get("human_input", False))
            event = confirmation_event(provenance, confirmed_at=datetime.now().isoformat())
            canonical_origin = resolve_canonical_origin(provenance, event)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PROVENANCE_INVALID", "message": str(exc)}) from exc
        try:
            candidate = _validate_llm_candidate(raw_candidate, baseline)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_CANDIDATE_INVALID", "message": str(exc)}) from exc
        candidate["proposal_origin"] = provenance["proposal_origin"]
        candidate["proposal_provenance"] = provenance
        decisions = []
        for decision in candidate.get("director_beat_decisions", []):
            normalized = dict(decision)
            normalized["proposal_origin"] = provenance["proposal_origin"]
            normalized["decision_origin"] = canonical_origin
            normalized["confirmation_event_ref"] = "production_confirm_service"
            normalized["review_status"] = "CONFIRMED"
            decisions.append(normalized)
        candidate["director_beat_decisions"] = decisions
        semantic_report = validate_director_contract(candidate, scene=scene, production=True)
        if semantic_report.get("status") != "qualified":
            first = (semantic_report.get("errors") or [{}])[0]
            code = first.get("code") if isinstance(first, dict) else "DIRECTOR_TREATMENT_CONTRACT_INVALID"
            raise HTTPException(status_code=409, detail={"code": code or "DIRECTOR_TREATMENT_CONTRACT_INVALID", "message": "structured DirectorBeatDecision contract is not production-qualified", "validation": semantic_report})

        previous = session.query(DirectorTreatment).filter_by(book_id=book_id, episode=episode, scene_id=scene_id, status="approved").order_by(DirectorTreatment.revision.desc(), DirectorTreatment.id.desc()).first()
        next_revision = previous.revision + 1 if previous else 1
        previous_id = previous.id if previous else None
        if previous:
            previous.status = "superseded"; previous.stale_status = "STALE"; previous.qualification_state = "STALE"; previous.stale_reasons = json.dumps(["SUPERSEDED_BY_NEW_AUTHORITY"], ensure_ascii=False); previous.updated_at = datetime.now()
        # Keep legacy payload hashes stable when a candidate does not use the
        # additive Phase B projection fields.  Empty optional projections are
        # not semantic decisions and must not be written as ``null`` keys.
        legacy_fields = {"dramatic_objective", "audience_question", "character_intents", "beat_map", "relationship_power_shift", "audience_emotion", "information_strategy", "performance_direction", "visual_strategy", "coverage_strategy", "sound_strategy", "edit_rhythm", "constraints", "unknowns"}
        formal = {key: candidate.get(key) for key in ("scene_id", "scene_name", *TREATMENT_CANDIDATE_FIELDS) if key not in {"proposal_origin", "proposal_provenance"} and (key in legacy_fields or candidate.get(key) not in (None, "", [], {}))}
        model_info = {"mode": "confirmed_director_candidate", "proposal_provenance": provenance, "confirmation_event": event, "canonical_origin": canonical_origin, **project_legacy_flags(provenance), "candidate_fingerprint": _candidate_fingerprint(candidate, current_packet["packet_fingerprint"]), "confirmed_at": datetime.now().isoformat(), "rollback_anchor": {"previous_treatment_id": previous_id, "previous_revision": previous.revision if previous else None}, "authority_state": "pending_binding"}
        row = DirectorTreatment(
            book_id=book_id, episode=episode, scene_id=scene_id, scene_name=baseline["scene_name"], revision=next_revision, status="approved",
            source_script_revision=str(script_ir_version.revision), source_script_hash=str(script_ir_version.payload_hash or ""), source_script_ir_version_id=script_ir_version.id, source_script_ir_revision=script_ir_version.revision, source_script_ir_hash=str(script_ir_version.payload_hash or ""), source_script_authority_fingerprint=str(script_ir_envelope.get("envelope_fingerprint") or ""), source_fact_snapshot_id=str(script_ir_envelope.get("fact_snapshot_id") or ""), source_fact_snapshot_revision=script_ir_envelope.get("fact_snapshot_revision"), source_fact_snapshot_hash=str(script_ir_envelope.get("fact_snapshot_payload_hash") or ""),
            dramatic_objective=formal["dramatic_objective"], audience_question=formal["audience_question"], character_intents=json.dumps(formal["character_intents"], ensure_ascii=False), beat_map=json.dumps(formal["beat_map"], ensure_ascii=False), source_constraints=json.dumps(baseline.get("source_constraints", {}), ensure_ascii=False), director_decisions=json.dumps({field: formal.get(field) for field in ("dramatic_objective", "audience_question", "character_intents", "relationship_power_shift", "audience_emotion", "information_strategy", "performance_direction", "visual_strategy", "coverage_strategy", "sound_strategy", "edit_rhythm", "scene_objective", "dramatic_question", "audience_state_in", "audience_state_out", "suspicion_or_information_strategy", "character_directions", "beat_directions", "director_beat_decisions", "director_contract_version", "performance_arc", "rhythm_strategy", "visual_priority", "scene_exit_intent", "prohibited_interpretations") if formal.get(field) not in (None, "", [], {})}, ensure_ascii=False), unknown_unresolved=json.dumps(formal.get("unknowns", []), ensure_ascii=False), relationship_power_shift=formal["relationship_power_shift"], audience_emotion=formal["audience_emotion"], information_strategy=formal["information_strategy"], performance_direction=formal["performance_direction"], visual_strategy=formal["visual_strategy"], coverage_strategy=formal["coverage_strategy"], sound_strategy=formal["sound_strategy"], edit_rhythm=formal["edit_rhythm"], constraints=json.dumps(formal["constraints"], ensure_ascii=False), unknowns=json.dumps(formal["unknowns"], ensure_ascii=False), skill_id=baseline.get("skill_id", ""), skill_version=baseline.get("skill_version", ""), decision_packet_id=packet.id, model_info=json.dumps(model_info, ensure_ascii=False), prompt_fingerprint=_candidate_fingerprint(candidate, current_packet["packet_fingerprint"]), payload_hash=treatment_payload_hash(formal), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", stale_reasons="[]", approved_at=datetime.now(), activated_at=datetime.now(), created_at=datetime.now(), updated_at=datetime.now(), workflow_profile="production",
        )
        session.add(row); session.flush()
        envelope = build_treatment_authority_envelope(treatment=formal, evidence=evidence, script_ir=script_ir_payload, script_ir_version=script_ir_version, script_ir_envelope=script_ir_envelope, treatment_id=row.id, treatment_revision=row.revision, qualification_state="PRODUCTION_QUALIFIED", provenance=provenance, confirmation=event, canonical_origin=canonical_origin)
        authority = DirectorTreatmentAuthority(book_id=book_id, episode=episode, scene_id=scene_id, treatment_id=row.id, treatment_revision=row.revision, payload_hash=row.payload_hash, envelope_fingerprint=envelope["envelope_fingerprint"], envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", stale_reasons="[]", approved_at=row.approved_at, activated_at=row.activated_at, created_at=datetime.now(), updated_at=datetime.now())
        session.add(authority); session.flush(); row.authority_envelope_id = authority.id
        pointer = session.query(DirectorTreatmentPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
        if pointer:
            pointer.treatment_id = row.id; pointer.treatment_revision = row.revision; pointer.authority_envelope_fingerprint = envelope["envelope_fingerprint"]; pointer.qualification_state = "PRODUCTION_QUALIFIED"; pointer.updated_at = datetime.now()
        else:
            session.add(DirectorTreatmentPointer(book_id=book_id, episode=episode, scene_id=scene_id, treatment_id=row.id, treatment_revision=row.revision, authority_envelope_fingerprint=envelope["envelope_fingerprint"], qualification_state="PRODUCTION_QUALIFIED", created_at=datetime.now(), updated_at=datetime.now()))
        model_info["authority_state"] = "production_qualified"; row.model_info = json.dumps(model_info, ensure_ascii=False)
        packet.status = "confirmed"; packet.confirmed_at = datetime.now(); packet.proposal = json.dumps(candidate, ensure_ascii=False); packet.updated_at = datetime.now()
        session.commit(); session.refresh(row)
        return {"approved": True, "authority_bound": True, "qualification_state": "PRODUCTION_QUALIFIED", "treatment": _treatment_row_payload(row), "authority_envelope": envelope, "packet_id": packet.id, "packet_fingerprint": packet.packet_fingerprint, "rollback_anchor": model_info["rollback_anchor"], "mutated": True, "production_operations": ["director_treatment_authority_bound", "current_treatment_pointer_updated"], "provider_calls": 0}


@router.get("/{book_id}/episodes/{episode}/director-treatment/authority/{scene_id}")
def get_director_treatment_authority(book_id: int, episode: int, scene_id: str) -> dict[str, Any]:
    """Return the explicit current Treatment authority for a scene."""
    from core.director_treatment_authority import resolve_current_authoritative_treatment
    with Session() as session:
        treatment, envelope = resolve_current_authoritative_treatment(session, book_id=book_id, episode=episode, scene_id=scene_id)
        return {"scene_id": scene_id, "treatment": _treatment_row_payload(treatment), "authority_envelope": envelope, "production_qualified": bool(envelope.get("phase_b_semantic_ready", False)), "phase_b_semantic_ready": bool(envelope.get("phase_b_semantic_ready", False))}
