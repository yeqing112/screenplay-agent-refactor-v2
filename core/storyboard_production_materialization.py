"""Reviewed automatic StoryboardPlan -> production materialization runtime.

This module is the bridge between the reviewable automatic storyboard draft and
the existing production ``StoryboardShot`` / materialization set authority.
It deliberately reuses the existing materializer, set and pointer tables.  No
provider is called and no ScriptIR or source fact is ever written.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Mapping

from models import (
    DirectorPlan,
    ProductionGenerationIntent,
    ProductionPromptVersion,
    Session,
    ShotDirection,
    ShotPlan,
    StoryboardMaterializationPointer,
    StoryboardMaterializationSet,
    StoryboardPlan,
    StoryboardPlanShot,
    StoryboardShot,
)

from core.production_prompt_lineage import (
    create_production_generation_intent,
    create_production_prompt_version,
)
from core.shot_direction import create_shot_direction, validate_shot_direction
from core.storyboard_materializer import (
    MATERIALIZER_POLICY_VERSION,
    MATERIALIZER_VERSION,
    materialization_set_fingerprint,
    materialize_storyboard_from_shot_plan,
    projection_fingerprint,
    projection_payload,
    validate_materialization_set,
)


MATERIALIZATION_RUNTIME_VERSION = "storyboard_production_materialization_v1"


class StoryboardProductionMaterializationError(ValueError):
    status_code = 409
    code = "STORYBOARD_PRODUCTION_MATERIALIZATION_BLOCKED"

    def __init__(self, message: str, diagnostics: list[dict[str, Any]] | None = None, *, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics or []
        if code:
            self.code = code

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "diagnostics": self.diagnostics}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return parsed if parsed is not None else fallback


def _obj(value: Any) -> dict[str, Any]:
    parsed = _json(value, {})
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _list(value: Any) -> list[Any]:
    parsed = _json(value, [])
    return list(parsed) if isinstance(parsed, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _episode_numbers(episode_id: str, *, book_id: int = 0, episode_number: int = 0) -> tuple[int, int]:
    episode = int(episode_number or 0)
    if not episode:
        try:
            episode = int(episode_id)
        except (TypeError, ValueError):
            episode = 0
    return int(book_id or 0), episode


def _resolve_storyboard_plan(session: Any, *, episode_id: str, storyboard_plan_id: int | None, storyboard_version: int | None) -> StoryboardPlan:
    if storyboard_version is None:
        raise StoryboardProductionMaterializationError(
            "StoryboardPlan version must be explicit before materialization.",
            [{"code": "STORYBOARD_VERSION_REQUIRED"}],
        )
    query = session.query(StoryboardPlan).filter_by(episode_id=str(episode_id), version=int(storyboard_version))
    row = query.one_or_none()
    if row is None:
        raise StoryboardProductionMaterializationError(
            "StoryboardPlan version does not exist.",
            [{"code": "STORYBOARD_NOT_FOUND", "episode_id": str(episode_id), "version": int(storyboard_version)}],
        )
    if storyboard_plan_id is not None and int(row.id) != int(storyboard_plan_id):
        raise StoryboardProductionMaterializationError(
            "StoryboardPlan id and version do not identify the same row.",
            [{"code": "STORYBOARD_ID_VERSION_MISMATCH", "storyboard_plan_id": storyboard_plan_id, "version": storyboard_version}],
        )
    return row


def _validate_review_gate(row: StoryboardPlan) -> dict[str, Any]:
    if row.status != "APPROVED":
        raise StoryboardProductionMaterializationError(
            "Only an explicitly human-approved StoryboardPlan can materialize.",
            [{"code": "STORYBOARD_REVIEW_REQUIRED", "status": row.status}],
        )
    lineage = _obj(row.lineage_json)
    validation = lineage.get("compile_validation") if isinstance(lineage.get("compile_validation"), Mapping) else {}
    if validation.get("status") != "PASS":
        raise StoryboardProductionMaterializationError(
            "StoryboardPlan compile validation must pass before materialization.",
            [{"code": "STORYBOARD_COMPILE_VALIDATION_REQUIRED", "validation": validation}],
        )
    if not row.compiled_shot_plan_ids:
        raise StoryboardProductionMaterializationError(
            "Approved StoryboardPlan has no compiled ShotPlan lineage.",
            [{"code": "SHOT_PLAN_LINEAGE_MISSING"}],
        )
    if row.director_reasoning_id is None or row.director_reasoning_version is None:
        raise StoryboardProductionMaterializationError(
            "DirectorReasoning lineage is required for production materialization.",
            [{"code": "DIRECTOR_REASONING_LINEAGE_MISSING"}],
        )
    storyboard = _obj(row.storyboard_json)
    shots = storyboard.get("shots") if isinstance(storyboard.get("shots"), list) else []
    scene_ids = {str(item) for item in validation.get("scene_ids", [])}
    character_ids = {str(item) for item in validation.get("character_ids", [])}
    style_ids = {str(item) for item in validation.get("visual_style_ids", [])}
    diagnostics: list[dict[str, Any]] = []
    sequences = [int(item.get("sequence") or 0) for item in shots if isinstance(item, Mapping)]
    if sequences != list(range(1, len(sequences) + 1)):
        diagnostics.append({"code": "SHOT_ORDER_INVALID", "actual": sequences})
    for item in shots:
        if not isinstance(item, Mapping):
            diagnostics.append({"code": "SHOT_OBJECT_INVALID"})
            continue
        scene_id = _text(item.get("scene_id"))
        style_id = _text(item.get("visual_style_id"))
        if scene_ids and scene_id not in scene_ids:
            diagnostics.append({"code": "SCENE_NOT_FOUND", "scene_id": scene_id})
        if style_ids and style_id not in style_ids:
            diagnostics.append({"code": "VISUAL_STYLE_NOT_FOUND", "visual_style_id": style_id})
        actions = item.get("character_actions") if isinstance(item.get("character_actions"), Mapping) else {}
        refs = actions.get("characters") if isinstance(actions.get("characters"), list) else []
        for ref in refs:
            if character_ids and str(ref) not in character_ids:
                diagnostics.append({"code": "CHARACTER_NOT_FOUND", "character_id": str(ref)})
        source_lineage = item.get("source_lineage") if isinstance(item.get("source_lineage"), Mapping) else {}
        if source_lineage.get("storyboard_plan_id") != row.id or source_lineage.get("storyboard_plan_version") != row.version or source_lineage.get("director_reasoning_id") != row.director_reasoning_id or source_lineage.get("director_reasoning_version") != row.director_reasoning_version:
            diagnostics.append({"code": "SOURCE_LINEAGE_INVALID", "shot_id": item.get("shot_id")})
    if diagnostics:
        raise StoryboardProductionMaterializationError("Reviewed StoryboardPlan validation no longer matches its approved snapshot.", diagnostics)
    return validation


def _load_plan_shots(session: Any, row: StoryboardPlan) -> list[ShotPlan]:
    ids = [int(item) for item in _list(row.compiled_shot_plan_ids) if str(item).isdigit()]
    if not ids:
        raise StoryboardProductionMaterializationError("StoryboardPlan has no compiled ShotPlan ids.", [{"code": "SHOT_PLAN_LINEAGE_MISSING"}])
    plans = session.query(ShotPlan).filter(ShotPlan.id.in_(ids)).order_by(ShotPlan.id.asc()).all()
    by_id = {int(item.id): item for item in plans}
    missing = [item for item in ids if item not in by_id]
    if missing:
        raise StoryboardProductionMaterializationError("Compiled ShotPlan lineage is incomplete.", [{"code": "SHOT_PLAN_NOT_FOUND", "ids": missing}])
    for plan in plans:
        if int(getattr(plan, "storyboard_plan_id", 0) or 0) != int(row.id) or int(getattr(plan, "storyboard_plan_version", 0) or 0) != int(row.version):
            raise StoryboardProductionMaterializationError(
                "ShotPlan does not point to the requested StoryboardPlan version.",
                [{"code": "SHOT_PLAN_STORYBOARD_LINEAGE_MISMATCH", "shot_plan_id": plan.id}],
            )
        if _text(getattr(plan, "status", "")) not in {"draft", "ready_for_materialization", "approved"}:
            raise StoryboardProductionMaterializationError(
                "ShotPlan is not eligible for materialization.",
                [{"code": "SHOT_PLAN_NOT_READY", "shot_plan_id": plan.id, "status": plan.status}],
            )
        if _obj(getattr(plan, "reasoning_lineage", "{}")).get("director_reasoning_id") is None:
            raise StoryboardProductionMaterializationError(
                "ShotPlan reasoning lineage is incomplete.",
                [{"code": "SHOT_PLAN_REASONING_LINEAGE_MISSING", "shot_plan_id": plan.id}],
            )
    return plans


def _canonical_shot_plan(row: StoryboardPlan, plan: ShotPlan) -> dict[str, Any]:
    shots = _list(plan.shots)
    if not shots:
        raise StoryboardProductionMaterializationError("ShotPlan contains no shots.", [{"code": "SHOT_PLAN_EMPTY", "shot_plan_id": plan.id}])
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, source in enumerate(shots, start=1):
        if not isinstance(source, Mapping):
            raise StoryboardProductionMaterializationError("ShotPlan shot is not an object.", [{"code": "SHOT_PLAN_SHOT_INVALID", "shot_plan_id": plan.id, "index": index}])
        item = dict(source)
        plan_shot_id = _text(item.get("plan_shot_id") or item.get("shot_id"))
        if not plan_shot_id or plan_shot_id in seen:
            raise StoryboardProductionMaterializationError("ShotPlan shot ids must be present and unique.", [{"code": "SHOT_ORDER_INVALID", "shot_plan_id": plan.id, "index": index}])
        seen.add(plan_shot_id)
        camera = dict(item.get("camera") or {}) if isinstance(item.get("camera"), Mapping) else {}
        duration = item.get("duration_hint_seconds", item.get("duration", item.get("duration_seconds")))
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0 or duration > 60:
            raise StoryboardProductionMaterializationError("Shot duration is invalid.", [{"code": "DURATION_INVALID", "shot_id": plan_shot_id, "duration": duration}])
        purpose = _text(item.get("shot_purpose") or item.get("purpose") or item.get("emotion"))
        if not purpose:
            raise StoryboardProductionMaterializationError("Shot purpose is required.", [{"code": "SHOT_PURPOSE_REQUIRED", "shot_id": plan_shot_id}])
        # Automatic Storyboard compilation writes this canonical shape.  Do
        # not recover creative values from legacy StoryboardShot columns.
        required = {
            "plan_shot_id": plan_shot_id,
            "beat_id": _text(item.get("beat_id") or plan_shot_id),
            "beat_refs": list(item.get("beat_refs") or [_text(item.get("beat_id") or plan_shot_id)]),
            "subjects": list(item.get("subjects") or []),
            "shot_purpose": purpose,
            "purpose": purpose,
            "camera": camera,
            "duration_hint_seconds": float(duration),
            "event": str(item.get("event") or item.get("action") or ""),
            "action_beats": list(item.get("action_beats") or []),
            "entry_state": item.get("entry_state") if isinstance(item.get("entry_state"), (dict, list)) else {"state_ref": f"{plan_shot_id}:entry"},
            "exit_state": item.get("exit_state") if isinstance(item.get("exit_state"), (dict, list)) else {"state_ref": f"{plan_shot_id}:exit"},
            "asset_bindings": dict(item.get("asset_bindings") or {}) if isinstance(item.get("asset_bindings"), Mapping) else {},
            "continuity_contract": dict(item.get("continuity_contract") or {}) if isinstance(item.get("continuity_contract"), Mapping) else {},
            "transition": str(item.get("transition") or "cut"),
            "lighting": str(item.get("lighting") or ""),
            "shot_direction": dict(item.get("shot_direction") or {}) if isinstance(item.get("shot_direction"), Mapping) else {},
        }
        if not required["action_beats"]:
            raise StoryboardProductionMaterializationError("Shot action beats are required.", [{"code": "SHOT_ACTION_CONTRACT_INVALID", "shot_id": plan_shot_id}])
        if not required["shot_direction"]:
            raise StoryboardProductionMaterializationError(
                "ShotDirection candidate is missing.",
                [{"code": "SHOT_DIRECTION_MISSING", "shot_id": plan_shot_id}],
                code="SHOT_DIRECTION_INVALID",
            )
        if not required["asset_bindings"]:
            raise StoryboardProductionMaterializationError("Shot asset identity bindings are required.", [{"code": "ASSET_BINDING_MISSING", "shot_id": plan_shot_id}])
        normalized.append(required)
    return {
        "scene_id": _text(plan.scene_id),
        "scene_name": _text(plan.scene_name),
        "schema_version": "shot_plan_v1",
        "shots": normalized,
        "payload_hash": _text(plan.payload_hash),
        "phase_c_semantic_ready": False,
    }


def _validate_direction_candidate(candidate: Mapping[str, Any], *, shot_id: str) -> None:
    required_profiles = {
        "camera_profile": ("lens", "angle", "distance", "movement", "speed"),
        "composition_profile": ("framing", "subject_position", "foreground", "background", "depth"),
        "performance_profile": ("expression", "gesture", "body_motion", "eye_direction"),
    }
    errors: list[dict[str, Any]] = []
    if not _text(candidate.get("shot_type")):
        errors.append({"code": "SHOT_TYPE_MISSING", "shot_id": shot_id})
    for profile, fields in required_profiles.items():
        value = candidate.get(profile)
        if not isinstance(value, Mapping):
            errors.append({"code": "SHOT_DIRECTION_PROFILE_INCOMPLETE", "profile": profile, "shot_id": shot_id})
            continue
        missing = [field for field in fields if not _text(value.get(field))]
        if missing:
            errors.append({"code": "SHOT_DIRECTION_PROFILE_INCOMPLETE", "profile": profile, "missing": missing, "shot_id": shot_id})
    if not isinstance(candidate.get("movement_profile"), Mapping) or not candidate.get("movement_profile"):
        errors.append({"code": "MOVEMENT_PROFILE_INCOMPLETE", "shot_id": shot_id})
    if not isinstance(candidate.get("emotion_profile"), Mapping) or not candidate.get("emotion_profile"):
        errors.append({"code": "EMOTION_PROFILE_INCOMPLETE", "shot_id": shot_id})
    if errors:
        raise StoryboardProductionMaterializationError("ShotDirection validation failed.", errors, code="SHOT_DIRECTION_INVALID")


def _existing_prompt(session: Any, prompt_id: str, prompt_text: str, structure: Mapping[str, Any]) -> dict[str, Any] | None:
    expected = "sha256:" + hashlib.sha256(_canonical({"prompt_text": prompt_text, "prompt_structure": dict(structure)}).encode("utf-8")).hexdigest()
    row = session.query(ProductionPromptVersion).filter_by(prompt_id=prompt_id).order_by(ProductionPromptVersion.version_number.desc()).first()
    if row is None or row.prompt_fingerprint != expected:
        return None
    return {"prompt_version_id": row.prompt_version_id, "prompt_id": row.prompt_id, "version_number": int(row.version_number), "prompt_fingerprint": row.prompt_fingerprint, "storyboard_plan_id": row.storyboard_plan_id, "storyboard_plan_version": row.storyboard_plan_version}


def _set_payload(row: StoryboardMaterializationSet, *, pointer: StoryboardMaterializationPointer | None = None, shots: list[StoryboardShot] | None = None) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "materialization_set_id": int(row.id),
        "scene_id": row.scene_id,
        "status": row.status,
        "stale_status": row.stale_status,
        "storyboard_plan_id": row.storyboard_plan_id,
        "storyboard_plan_version": row.storyboard_plan_version,
        "director_reasoning_id": row.director_reasoning_id,
        "director_reasoning_version": row.director_reasoning_version,
        "shot_plan_id": row.shot_plan_id,
        "shot_plan_revision": row.shot_plan_revision,
        "expected_shot_count": int(row.expected_shot_count),
        "materialized_shot_count": int(row.materialized_shot_count),
        "set_payload_fingerprint": row.set_payload_fingerprint,
        "authority_fingerprint": row.shot_plan_authority_fingerprint,
        "pointer_active": bool(pointer and int(pointer.materialization_set_id) == int(row.id)),
        "shot_ids": [int(item.id) for item in (shots or [])],
    }


def _reuse_result(session: Any, *, row: StoryboardPlan, set_row: StoryboardMaterializationSet, pointer: StoryboardMaterializationPointer | None, book_id: int, episode: int) -> dict[str, Any]:
    shots = session.query(StoryboardShot).filter_by(materialization_set_id=set_row.id, book_id=book_id, episode=episode, scene_id=set_row.scene_id).order_by(StoryboardShot.shot_id.asc()).all()
    if len(shots) != int(set_row.expected_shot_count):
        raise StoryboardProductionMaterializationError("Existing materialization set is incomplete.", [{"code": "MATERIALIZATION_SET_INCOMPLETE", "materialization_set_id": set_row.id}])
    return {"status": "MATERIALIZED", "mutated": False, "reused": True, "materialization_set_ids": [int(set_row.id)], "storyboard_shot_ids": [int(item.id) for item in shots], "generation_intent_ids": [item.generation_intent_id for item in session.query(ProductionGenerationIntent).filter(ProductionGenerationIntent.shot_id.in_([item.id for item in shots])).all()], "prompt_version_ids": [item.prompt_version_id for item in session.query(ProductionPromptVersion).filter(ProductionPromptVersion.storyboard_plan_id == row.id, ProductionPromptVersion.storyboard_plan_version == row.version).all()], "active_pointer": _set_payload(set_row, pointer=pointer, shots=shots), "source": {"storyboard_plan_id": row.id, "storyboard_plan_version": row.version, "director_reasoning_id": row.director_reasoning_id, "director_reasoning_version": row.director_reasoning_version}, "human_review_required": True, "provider_calls": 0}


def materialize_storyboard_plan(
    session: Any,
    *,
    episode_id: str,
    storyboard_plan_id: int | None = None,
    storyboard_version: int | None = None,
    book_id: int = 0,
    episode_number: int = 0,
) -> dict[str, Any]:
    """Materialize one approved StoryboardPlan atomically per session."""
    row = _resolve_storyboard_plan(session, episode_id=episode_id, storyboard_plan_id=storyboard_plan_id, storyboard_version=storyboard_version)
    validation = _validate_review_gate(row)
    # Resolve the exact immutable DirectorReasoningIR version; never
    # materialize an orphaned lineage reference.
    from models import DirectorReasoning
    reasoning = session.query(DirectorReasoning).filter_by(id=int(row.director_reasoning_id), version=int(row.director_reasoning_version)).one_or_none()
    if reasoning is None:
        raise StoryboardProductionMaterializationError("DirectorReasoning lineage row is missing.", [{"code": "DIRECTOR_REASONING_NOT_FOUND", "director_reasoning_id": row.director_reasoning_id, "director_reasoning_version": row.director_reasoning_version}])
    book_id, episode = _episode_numbers(episode_id, book_id=book_id, episode_number=episode_number)
    shot_plans = _load_plan_shots(session, row)
    results: list[dict[str, Any]] = []

    # Validate every scene before writing any production rows (fail closed).
    candidates: list[tuple[ShotPlan, dict[str, Any], list[dict[str, Any]], dict[str, Any]]] = []
    for plan in shot_plans:
        canonical = _canonical_shot_plan(row, plan)
        direction_candidates = [dict(item.get("shot_direction") or {}) for item in canonical["shots"]]
        for candidate, source in zip(direction_candidates, canonical["shots"]):
            _validate_direction_candidate(candidate, shot_id=_text(source.get("plan_shot_id")))
        try:
            projections = materialize_storyboard_from_shot_plan(canonical, production=True)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            code = str(exc).split(":", 1)[0] if ":" in str(exc) else "SHOT_PLAN_MATERIALIZATION_BLOCKED"
            raise StoryboardProductionMaterializationError(str(exc), [{"code": code, "shot_plan_id": plan.id}]) from exc
        expected_ids = [_text(item.get("plan_shot_id")) for item in canonical["shots"]]
        mapping_errors = validate_materialization_set(expected_plan_shot_ids=expected_ids, projections=projections)
        if mapping_errors:
            raise StoryboardProductionMaterializationError("ShotPlan projection cardinality failed.", mapping_errors)
        authority = {
            "runtime_version": MATERIALIZATION_RUNTIME_VERSION,
            "materializer_version": MATERIALIZER_VERSION,
            "materializer_policy_version": MATERIALIZER_POLICY_VERSION,
            "storyboard_plan": {"id": row.id, "version": row.version, "payload_hash": row.payload_hash, "status": row.status},
            "director_reasoning": {"id": row.director_reasoning_id, "version": row.director_reasoning_version},
            "shot_plan": {"id": plan.id, "revision": plan.revision, "payload_hash": plan.payload_hash, "scene_id": plan.scene_id},
            "compile_validation": validation,
        }
        set_fp = materialization_set_fingerprint(authority_envelope=authority, projections=projections)
        candidates.append((plan, canonical, projections, {"authority": authority, "set_fingerprint": set_fp, "expected_ids": expected_ids}))

    for plan, canonical, projections, authority in candidates:
        scene_id = _text(plan.scene_id)
        pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
        set_row = session.query(StoryboardMaterializationSet).filter_by(set_payload_fingerprint=authority["set_fingerprint"]).first()
        if set_row is not None:
            if set_row.status == "STALE" or set_row.stale_status == "STALE":
                raise StoryboardProductionMaterializationError("A stale materialization set cannot be reactivated.", [{"code": "MATERIALIZATION_SET_STALE", "materialization_set_id": set_row.id}])
            results.append(_reuse_result(session, row=row, set_row=set_row, pointer=pointer, book_id=book_id, episode=episode))
            if pointer is None:
                pointer = StoryboardMaterializationPointer(book_id=book_id, episode=episode, scene_id=scene_id, materialization_set_id=set_row.id, shot_plan_id=plan.id, shot_plan_revision=plan.revision, set_payload_fingerprint=set_row.set_payload_fingerprint, qualification_state="MATERIALIZED", created_at=datetime.now(), updated_at=datetime.now())
                session.add(pointer)
            elif int(pointer.materialization_set_id) != int(set_row.id):
                pointer.materialization_set_id = set_row.id
                pointer.shot_plan_id = plan.id
                pointer.shot_plan_revision = plan.revision
                pointer.set_payload_fingerprint = set_row.set_payload_fingerprint
                pointer.qualification_state = "MATERIALIZED"
                pointer.updated_at = datetime.now()
            continue

        old_set = session.query(StoryboardMaterializationSet).filter_by(id=pointer.materialization_set_id).first() if pointer else None
        if old_set is not None and old_set.set_payload_fingerprint != authority["set_fingerprint"]:
            old_set.status = "SUPERSEDED"
            old_set.updated_at = datetime.now()
            session.query(StoryboardShot).filter_by(materialization_set_id=old_set.id).update({"materialization_status": "SUPERSEDED", "production_status": "blocked"}, synchronize_session=False)

        set_row = StoryboardMaterializationSet(
            book_id=book_id,
            episode=episode,
            scene_id=scene_id,
            shot_plan_id=plan.id,
            shot_plan_revision=plan.revision,
            shot_plan_payload_hash=_text(plan.payload_hash),
            shot_plan_authority_fingerprint=_fingerprint(authority["authority"]),
            storyboard_plan_id=row.id,
            storyboard_plan_version=row.version,
            director_reasoning_id=row.director_reasoning_id,
            director_reasoning_version=row.director_reasoning_version,
            expected_shot_count=len(projections),
            materialized_shot_count=0,
            ordered_plan_shot_ids=_canonical(authority["expected_ids"]),
            set_payload_fingerprint=authority["set_fingerprint"],
            materializer_version=MATERIALIZER_VERSION,
            materializer_policy_version=MATERIALIZER_POLICY_VERSION,
            authority_envelope_json=_canonical({**authority["authority"], "source_lineage": {"storyboard_plan_id": row.id, "storyboard_plan_version": row.version, "director_reasoning_id": row.director_reasoning_id, "director_reasoning_version": row.director_reasoning_version}}),
            status="MATERIALIZED",
            stale_status="FRESH",
            stale_reasons="[]",
            created_at=datetime.now(),
            activated_at=datetime.now(),
            updated_at=datetime.now(),
        )
        session.add(set_row)
        session.flush()
        created_shots: list[StoryboardShot] = []
        direction_sources = { _text(item.get("plan_shot_id")): item for item in canonical["shots"] }
        for ordinal, projection in enumerate(projections, start=1):
            plan_shot_id = _text(projection.get("plan_shot_id"))
            lineage = {"director_reasoning_id": row.director_reasoning_id, "director_reasoning_version": row.director_reasoning_version, "storyboard_plan_id": row.id, "storyboard_plan_version": row.version, "shot_plan_id": plan.id, "shot_plan_revision": plan.revision, "plan_shot_id": plan_shot_id, "authority_fingerprint": set_row.shot_plan_authority_fingerprint}
            meta = dict(projection.get("meta_info") or {})
            meta["projection_payload"] = projection_payload(projection)
            meta["storyboard_lineage"] = lineage
            shot = StoryboardShot(
                book_id=book_id, episode=episode, scene_name=_text(projection.get("scene_name")), scene_id=scene_id,
                plan_shot_id=plan_shot_id, materialization_set_id=set_row.id, source_shot_plan_id=plan.id,
                source_shot_plan_revision=plan.revision, source_shot_plan_authority_fingerprint=set_row.shot_plan_authority_fingerprint,
                storyboard_plan_id=row.id, storyboard_plan_version=row.version, director_reasoning_id=row.director_reasoning_id,
                director_reasoning_version=row.director_reasoning_version, storyboard_lineage=_canonical(lineage),
                projection_fingerprint=projection_fingerprint(projection), materialization_status="MATERIALIZED", shot_id=ordinal,
                dialogue=str(projection.get("dialogue") or ""), duration=int(round(float(projection.get("duration") or 1))), camera_angle=_text(projection.get("camera_angle")),
                camera_movement=_text(projection.get("camera_movement")), camera_speed=_text(projection.get("camera_speed")), shot_purpose=_text(projection.get("shot_purpose")),
                transition=_text(projection.get("transition")) or "cut", lighting=str(projection.get("lighting") or ""),
                start_state=_canonical(projection.get("start_state")) if isinstance(projection.get("start_state"), (dict, list)) else str(projection.get("start_state") or ""),
                action_process=str(projection.get("action_process") or ""), end_state=_canonical(projection.get("end_state")) if isinstance(projection.get("end_state"), (dict, list)) else str(projection.get("end_state") or ""),
                asset_links=_canonical(projection.get("asset_bindings") or {}), meta_info=_canonical(meta), visual_prompt_static="", visual_prompt_motion="", visual_prompt_final="",
                execution_status="queued", quality_status="materialized", production_status="blocked", workflow_profile="production", created_at=datetime.now(), updated_at=datetime.now(),
            )
            session.add(shot)
            created_shots.append(shot)
        session.flush()

        intent_ids: list[str] = []
        prompt_ids: list[str] = []
        for ordinal, shot in enumerate(created_shots, start=1):
            source = direction_sources.get(_text(shot.plan_shot_id)) or {}
            direction = dict(source.get("shot_direction") or {})
            create_shot_direction(
                session,
                shot_id=shot.id,
                shot_type=_text(direction.get("shot_type")),
                camera_profile=dict(direction.get("camera_profile") or {}),
                movement_profile=dict(direction.get("movement_profile") or {}),
                composition_profile=dict(direction.get("composition_profile") or {}),
                performance_profile=dict(direction.get("performance_profile") or {}),
                emotion_profile=dict(direction.get("emotion_profile") or {}),
            )
            direction_validation = validate_shot_direction(session, shot_id=shot.id)
            if direction_validation.get("status") != "PASS":
                raise StoryboardProductionMaterializationError("Persisted ShotDirection failed validation.", direction_validation.get("errors") or [], code="SHOT_DIRECTION_INVALID")
            shot_requirement = {"shot_id": shot.plan_shot_id, "scene_id": scene_id, "shot_type": source.get("shot_type") or direction.get("shot_type"), "camera": source.get("camera") or {}, "duration": shot.duration, "action": shot.action_process, "shot_direction": direction, "source_lineage": {"storyboard_plan_id": row.id, "storyboard_plan_version": row.version, "shot_plan_id": plan.id, "shot_plan_revision": plan.revision}}
            lineage = {"storyboard_plan_id": row.id, "storyboard_plan_version": row.version, "shot_plan_id": plan.id, "shot_plan_revision": plan.revision, "storyboard_shot_id": shot.id, "plan_shot_id": shot.plan_shot_id}
            intent = create_production_generation_intent(session, shot_id=shot.id, shot_requirement=shot_requirement, camera_requirements=source.get("camera") or {}, style_requirements={"visual_style_id": source.get("visual_style_id") or ""}, constraint_snapshot={"materialization_set_id": set_row.id, "human_review_required": True, "provider_calls": 0}, storyboard_plan_id=row.id, storyboard_plan_version=row.version, storyboard_lineage=lineage, director_reasoning_id=row.director_reasoning_id, director_reasoning_version=row.director_reasoning_version, reasoning_lineage={"director_reasoning_id": row.director_reasoning_id, "director_reasoning_version": row.director_reasoning_version, "storyboard_plan_id": row.id, "storyboard_plan_version": row.version})
            intent_ids.append(intent["generation_intent_id"])
            prompt_id = f"storyboard-{row.id}-v{row.version}-{shot.plan_shot_id}"
            prompt_text = f"Storyboard shot {shot.plan_shot_id}: {shot.action_process or shot.shot_purpose}."
            prompt_structure = {"source": "StoryboardPlan", "shot_id": shot.plan_shot_id, "shot_direction": direction, "generation_intent_id": intent["generation_intent_id"], "lineage": lineage}
            existing_prompt = _existing_prompt(session, prompt_id, prompt_text, prompt_structure)
            prompt = existing_prompt or create_production_prompt_version(session, prompt_id=prompt_id, prompt_text=prompt_text, prompt_structure=prompt_structure, created_from="STORYBOARD_MATERIALIZATION", storyboard_plan_id=row.id, storyboard_plan_version=row.version, storyboard_lineage=lineage)
            prompt_ids.append(prompt["prompt_version_id"])
        set_row.materialized_shot_count = len(created_shots)
        set_row.authority_envelope_json = _canonical({**authority["authority"], "generation_intent_ids": intent_ids, "prompt_version_ids": prompt_ids, "source_lineage": {"storyboard_plan_id": row.id, "storyboard_plan_version": row.version, "director_reasoning_id": row.director_reasoning_id, "director_reasoning_version": row.director_reasoning_version}})
        if pointer is None:
            pointer = StoryboardMaterializationPointer(book_id=book_id, episode=episode, scene_id=scene_id, materialization_set_id=set_row.id, shot_plan_id=plan.id, shot_plan_revision=plan.revision, set_payload_fingerprint=set_row.set_payload_fingerprint, qualification_state="MATERIALIZED", created_at=datetime.now(), updated_at=datetime.now())
            session.add(pointer)
        else:
            pointer.materialization_set_id = set_row.id
            pointer.shot_plan_id = plan.id
            pointer.shot_plan_revision = plan.revision
            pointer.set_payload_fingerprint = set_row.set_payload_fingerprint
            pointer.qualification_state = "MATERIALIZED"
            pointer.updated_at = datetime.now()
        plan.status = "approved"
        plan.execution_status = "ready"
        plan.quality_status = "qualified"
        plan.production_status = "blocked"
        plan.workflow_profile = "production"
        plan.updated_at = datetime.now()
        results.append({"status": "MATERIALIZED", "mutated": True, "reused": False, "materialization_set_ids": [int(set_row.id)], "storyboard_shot_ids": [int(item.id) for item in created_shots], "generation_intent_ids": intent_ids, "prompt_version_ids": prompt_ids, "source": {"storyboard_plan_id": row.id, "storyboard_plan_version": row.version, "director_reasoning_id": row.director_reasoning_id, "director_reasoning_version": row.director_reasoning_version, "shot_plan_id": plan.id, "shot_plan_revision": plan.revision}, "human_review_required": True, "provider_calls": 0})

    all_set_ids = [item for result in results for item in result.get("materialization_set_ids", [])]
    all_shot_ids = [item for result in results for item in result.get("storyboard_shot_ids", [])]
    return {"status": "MATERIALIZED", "mutated": any(item.get("mutated") for item in results), "reused": bool(results) and all(not item.get("mutated") for item in results), "materialization_set_ids": all_set_ids, "storyboard_shot_ids": all_shot_ids, "generation_intent_ids": [item for result in results for item in result.get("generation_intent_ids", [])], "prompt_version_ids": [item for result in results for item in result.get("prompt_version_ids", [])], "scene_results": results, "source": {"storyboard_plan_id": row.id, "storyboard_plan_version": row.version, "director_reasoning_id": row.director_reasoning_id, "director_reasoning_version": row.director_reasoning_version}, "human_review_required": True, "provider_calls": 0}


def get_storyboard_materialization(session: Any, *, episode_id: str, book_id: int = 0, episode_number: int = 0) -> dict[str, Any]:
    book_id, episode = _episode_numbers(episode_id, book_id=book_id, episode_number=episode_number)
    pointers = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode).all()
    active: list[dict[str, Any]] = []
    for pointer in pointers:
        set_row = session.query(StoryboardMaterializationSet).filter_by(id=pointer.materialization_set_id).first()
        if set_row is None:
            continue
        shots = session.query(StoryboardShot).filter_by(materialization_set_id=set_row.id).order_by(StoryboardShot.shot_id.asc()).all()
        active.append(_set_payload(set_row, pointer=pointer, shots=shots))
    single = active[0] if len(active) == 1 else None
    return {"episode_id": str(episode_id), "status": "MATERIALIZED" if active else "NOT_MATERIALIZED", "active_set": single, "active_sets": active, "source_storyboard_version": single.get("storyboard_plan_version") if single else None, "shot_count": sum(item["expected_shot_count"] for item in active), "authority_fingerprint": single.get("authority_fingerprint") if single else None, "materialization_count": len(active), "human_review_required": True}


def rollback_storyboard_materialization(session: Any, *, episode_id: str, target_storyboard_version: int | None = None, target_materialization_set_id: int | None = None, book_id: int = 0, episode_number: int = 0) -> dict[str, Any]:
    book_id, episode = _episode_numbers(episode_id, book_id=book_id, episode_number=episode_number)
    if target_storyboard_version is None and target_materialization_set_id is None:
        raise StoryboardProductionMaterializationError("Rollback requires a target materialization set or StoryboardPlan version.", [{"code": "ROLLBACK_TARGET_REQUIRED"}])
    pointers = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode).all()
    if not pointers:
        raise StoryboardProductionMaterializationError("No active materialization pointer exists.", [{"code": "MATERIALIZATION_POINTER_MISSING"}])
    switched: list[dict[str, Any]] = []
    for pointer in pointers:
        current = session.query(StoryboardMaterializationSet).filter_by(id=pointer.materialization_set_id).first()
        if target_materialization_set_id is not None:
            target = session.query(StoryboardMaterializationSet).filter_by(id=int(target_materialization_set_id), book_id=book_id, episode=episode, scene_id=pointer.scene_id).first()
        else:
            target = session.query(StoryboardMaterializationSet).filter_by(book_id=book_id, episode=episode, scene_id=pointer.scene_id, storyboard_plan_version=int(target_storyboard_version)).order_by(StoryboardMaterializationSet.id.asc()).first()
        if target is None:
            raise StoryboardProductionMaterializationError("Rollback target is not available for every active scene.", [{"code": "ROLLBACK_TARGET_NOT_FOUND", "scene_id": pointer.scene_id, "target_storyboard_version": target_storyboard_version, "target_materialization_set_id": target_materialization_set_id}])
        if target.stale_status == "STALE":
            raise StoryboardProductionMaterializationError("A stale materialization set cannot be restored.", [{"code": "ROLLBACK_TARGET_STALE", "materialization_set_id": target.id}])
        if current is not None and int(current.id) != int(target.id):
            current.status = "SUPERSEDED"
            current.updated_at = datetime.now()
            session.query(StoryboardShot).filter_by(materialization_set_id=current.id).update({"materialization_status": "SUPERSEDED", "production_status": "blocked"}, synchronize_session=False)
        target.status = "MATERIALIZED"
        target.updated_at = datetime.now()
        session.query(StoryboardShot).filter_by(materialization_set_id=target.id).update({"materialization_status": "MATERIALIZED", "production_status": "blocked"}, synchronize_session=False)
        pointer.materialization_set_id = target.id
        pointer.shot_plan_id = target.shot_plan_id
        pointer.shot_plan_revision = target.shot_plan_revision
        pointer.set_payload_fingerprint = target.set_payload_fingerprint
        pointer.qualification_state = "MATERIALIZED"
        pointer.updated_at = datetime.now()
        switched.append({"scene_id": pointer.scene_id, "from_set_id": current.id if current else None, "to_set_id": target.id, "storyboard_plan_version": target.storyboard_plan_version})
    return {"status": "ROLLED_BACK", "episode_id": str(episode_id), "switched": switched, "history_preserved": True, "source_fact_mutations": 0, "script_ir_mutations": 0}


__all__ = [
    "MATERIALIZATION_RUNTIME_VERSION",
    "StoryboardProductionMaterializationError",
    "materialize_storyboard_plan",
    "get_storyboard_materialization",
    "rollback_storyboard_materialization",
]
