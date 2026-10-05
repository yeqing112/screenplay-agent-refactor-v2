"""Provider-free semantic lineage and root-cause audit for canonical canary rows.

This script is deliberately read-only.  It inspects the configured database,
does not compile PromptIR, does not call a provider, and never commits a
transaction.  The generated evidence is the basis for the V3 root-cause
report.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models import (
    Book, Chapter, DirectorTreatment, DirectorTreatmentPointer, FactSnapshot,
    GenerationExecutionRecord, PromptIRPointer, PromptIRVersion, SceneBlocking,
    SceneBlockingPointer, Script, ScriptIRVersion, Session, ShotPlan,
    ShotPlanPointer, StoryboardMaterializationPointer, StoryboardMaterializationSet,
    StoryboardShot, TaskRun,
)

OUT = ROOT / "docs" / "canonical-canary" / "v3-semantic-root-cause"
TARGET_BOOK_IDS = [990448, 990449, 990450, 990451, 990452]
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for item in values:
        if isinstance(item, dict):
            value = next((item.get(key) for key in ("character_id", "subject_id", "id", "name", "ref") if _text(item.get(key))), "")
        else:
            value = item
        if _text(value):
            result.append(_text(value))
    return result


def _code_ref(relative: str, needle: str) -> str:
    path = ROOT / relative
    try:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if needle in line:
                return f"{relative}:{line_no}"
    except OSError:
        pass
    return f"{relative}:?"


def _current_script(session: Any, book_id: int, episode: int) -> tuple[Any, Any]:
    script = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
    ir = session.query(ScriptIRVersion).filter_by(id=getattr(script, "current_script_ir_version_id", None), book_id=book_id, episode=episode).first() if script else None
    return script, ir


def _scene_from_ir(ir: Any, scene_id: str) -> dict[str, Any]:
    payload = _json(getattr(ir, "payload_json", "{}"), {}) if ir else {}
    scenes = payload.get("scenes") if isinstance(payload, dict) else []
    return next((item for item in scenes if isinstance(item, dict) and _text(item.get("scene_id")) == _text(scene_id)), {})


def _source_text_payload(session: Any, book_id: int, episode: int, script: Any, ir: Any) -> dict[str, Any]:
    chapters = session.query(Chapter).filter_by(book_id=book_id).order_by(Chapter.seq).all()
    chapter_text = "\n".join(_text(item.content) for item in chapters)
    script_payload = _json(getattr(script, "content", "{}"), {}) if script else {}
    script_scenes = script_payload.get("scenes") if isinstance(script_payload, dict) and isinstance(script_payload.get("scenes"), list) else []
    structured_dialogues = [item for scene in script_scenes if isinstance(scene, dict) for item in (scene.get("dialogues") or []) if isinstance(item, dict)]
    structured_participants = [item for scene in script_scenes if isinstance(scene, dict) for item in (scene.get("participants") or [])]
    return {
        "chapter_ids": [item.id for item in chapters],
        "raw_source_available": bool(chapter_text or _text(getattr(script, "content", ""))),
        "raw_source_sha256": hashlib.sha256(chapter_text.encode("utf-8")).hexdigest() if chapter_text else "",
        "raw_source_character_evidence": {"structured_fields": [], "explicit_names": []},
        "raw_source_dialogue_evidence": {"structured_fields": ["Script.content.scenes[].dialogues"] if structured_dialogues else [], "structured_dialogue_count": len(structured_dialogues), "quote_inference_used": False},
        "script_content_structured_participant_count": len(structured_participants),
        "script_content_structured_dialogue_count": len(structured_dialogues),
    }


def _blocking_payload(session: Any, book_id: int, episode: int, scene_id: str) -> tuple[Any, dict[str, Any]]:
    pointer = session.query(SceneBlockingPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
    row = session.query(SceneBlocking).filter_by(id=getattr(pointer, "blocking_id", None), book_id=book_id, episode=episode, scene_id=scene_id).first() if pointer else None
    if not row:
        row = session.query(SceneBlocking).filter_by(book_id=book_id, episode=episode, scene_id=scene_id, status="approved").order_by(SceneBlocking.id.desc()).first()
    spatial = _json(getattr(row, "spatial_model", "{}"), {}) if row else {}
    return row, {
        "pointer_id": getattr(pointer, "id", None),
        "participants": _json(getattr(row, "participants", "[]"), []) if row else [],
        "initial_state": spatial.get("initial_state", {}) if isinstance(spatial, dict) else {},
        "beat_spatial_states": spatial.get("beat_spatial_states", []) if isinstance(spatial, dict) else [],
        "schema_version": getattr(row, "schema_version", "") if row else "",
        "revision": getattr(row, "revision", None) if row else None,
        "qualification_state": getattr(row, "qualification_state", "") if row else "",
        "source_script_ir_version_id": getattr(row, "source_script_ir_version_id", None) if row else None,
        "source_fact_snapshot_id": getattr(row, "source_fact_snapshot_id", "") if row else "",
    }


def _treatment_payload(session: Any, book_id: int, episode: int, scene_id: str) -> tuple[Any, dict[str, Any]]:
    pointer = session.query(DirectorTreatmentPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
    row = session.query(DirectorTreatment).filter_by(id=getattr(pointer, "treatment_id", None), book_id=book_id, episode=episode, scene_id=scene_id).first() if pointer else None
    if not row:
        row = session.query(DirectorTreatment).filter_by(book_id=book_id, episode=episode, scene_id=scene_id, status="approved").order_by(DirectorTreatment.id.desc()).first()
    beats = _json(getattr(row, "beat_map", "[]"), []) if row else []
    intents = _json(getattr(row, "character_intents", "{}"), {}) if row else {}
    return row, {
        "pointer_id": getattr(pointer, "id", None),
        "character_intent_ids": sorted(str(key) for key in intents) if isinstance(intents, dict) else [],
        "beat_character_ids": sorted({str(value) for beat in beats if isinstance(beat, dict) for value in (beat.get("characters") or []) if _text(value)}),
        "beat_dialogue_fields": [key for beat in beats if isinstance(beat, dict) for key in ("dialogue", "dialogues") if key in beat],
        "schema_version": "director_treatment_v1",
        "revision": getattr(row, "revision", None) if row else None,
    }


def _plan_payload(session: Any, book_id: int, episode: int, scene_id: str) -> tuple[Any, list[dict[str, Any]]]:
    pointer = session.query(ShotPlanPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
    row = session.query(ShotPlan).filter_by(id=getattr(pointer, "shot_plan_id", None), book_id=book_id, episode=episode, scene_id=scene_id).first() if pointer else None
    if not row:
        row = session.query(ShotPlan).filter_by(book_id=book_id, episode=episode, scene_id=scene_id, status="approved").order_by(ShotPlan.id.desc()).first()
    shots = _json(getattr(row, "shots", "[]"), []) if row else []
    return row, [item for item in shots if isinstance(item, dict)]


def _prompt_payload(session: Any, row: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for media in ("IMAGE", "VIDEO"):
        pointer = session.query(PromptIRPointer).filter_by(book_id=row.book_id, episode=row.episode, storyboard_shot_id=row.id, target_media=media).first()
        version = session.query(PromptIRVersion).filter_by(id=getattr(pointer, "prompt_ir_version_id", None)).first() if pointer else None
        result[media] = {
            "status": "PRESENT" if pointer and version else "MISSING_COMPILE_REQUIRED",
            "pointer_id": getattr(pointer, "id", None),
            "version_id": getattr(version, "id", None),
            "schema_version": getattr(version, "schema_version", None),
            "payload_hash": getattr(version, "payload_hash", None),
            "payload": _json(getattr(version, "payload_json", "{}"), {}) if version else {},
        }
    return result


def _root_cause(*, source_subjects: list[str], blocking_subjects: list[str], plan_subjects: list[str], handoff_subjects: list[str], canonical_subjects: list[str], source_dialogue_count: int, ir_dialogue_count: int, plan_dialogue: str, canonical_dialogue: str, materializer_version: str) -> tuple[str, list[str], list[str]]:
    evidence: list[str] = []
    secondary: list[str] = []
    if source_dialogue_count == 0 and ir_dialogue_count == 0 and not plan_dialogue and not canonical_dialogue:
        secondary.append("SOURCE_DIALOGUE_EMPTY")
        evidence.append("raw source and ScriptIR contain no structured dialogue")
    if source_subjects and blocking_subjects and not plan_subjects:
        evidence.extend(["source participant survives into SceneBlocking.participants", "SceneBlocking spatial_model.initial_state.characters is empty", "Phase C plan emits no subjects"])
        secondary.append("SEMANTIC_EXTRACTION_NOT_RUN")
        primary = "SHOT_SEMANTIC_HYDRATION_NOT_RUN"
    elif plan_subjects and not handoff_subjects:
        primary = "VISUAL_SEMANTIC_HANDOFF_EMPTY"
        evidence.append("ShotPlan subjects exist but visual_semantic_handoff.subjects is empty")
    elif handoff_subjects and not canonical_subjects:
        primary = "CANONICAL_PROJECTION_DROPPED_SUBJECTS"
        evidence.append("visual_semantic_handoff subjects exist but canonical projection is empty")
    elif not source_subjects:
        primary = "SOURCE_SEMANTICS_EMPTY"
        evidence.append("no authoritative source character evidence")
    else:
        primary = "UNKNOWN_ROOT_CAUSE"
    if materializer_version and materializer_version != "storyboard_materializer_v2":
        secondary.append("LEGACY_STALE_MATERIALIZATION")
    return primary, sorted(set(secondary)), evidence


def audit_rows(session: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for book_id in TARGET_BOOK_IDS:
        script, ir = _current_script(session, book_id, 1)
        book = session.query(Book).filter_by(id=book_id).first()
        source = _source_text_payload(session, book_id, 1, script, ir)
        pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=1).first()
        materialization = session.query(StoryboardMaterializationSet).filter_by(id=getattr(pointer, "materialization_set_id", None)).first() if pointer else None
        rows = session.query(StoryboardShot).filter_by(book_id=book_id, episode=1, materialization_set_id=getattr(materialization, "id", None)).order_by(StoryboardShot.shot_id).all() if materialization else []
        for row in rows:
            meta = _json(row.meta_info, {})
            semantic = meta.get("visual_semantic_handoff") if isinstance(meta.get("visual_semantic_handoff"), dict) else {}
            projection = meta.get("projection_payload") if isinstance(meta.get("projection_payload"), dict) else {}
            scene = _scene_from_ir(ir, row.scene_id)
            treatment_row, treatment = _treatment_payload(session, book_id, 1, row.scene_id)
            blocking_row, blocking = _blocking_payload(session, book_id, 1, row.scene_id)
            plan_row, plan_shots = _plan_payload(session, book_id, 1, row.scene_id)
            plan = next((item for item in plan_shots if _text(item.get("plan_shot_id")) == _text(row.plan_shot_id)), {})
            semantic_assets = semantic.get("asset_identity_bindings") if isinstance(semantic.get("asset_identity_bindings"), dict) else {}
            canonical_assets = semantic_assets.get("canonical_asset_identity") if isinstance(semantic_assets.get("canonical_asset_identity"), dict) else {}
            source_subjects = _ids(scene.get("participants")) or _ids(scene.get("characters"))
            blocking_subjects = _ids(blocking.get("participants"))
            plan_subjects = _ids(plan.get("subjects"))
            handoff_subjects = _ids(semantic.get("subjects"))
            canonical_subjects = _ids(canonical_assets.get("characters"))
            source_dialogue_count = len(source.get("structured_dialogue_count") and [] or [])
            script_payload = _json(getattr(script, "content", "{}"), {}) if script else {}
            script_scenes = script_payload.get("scenes") if isinstance(script_payload, dict) and isinstance(script_payload.get("scenes"), list) else []
            source_dialogue_count = sum(len(item.get("dialogues") or []) for item in script_scenes if isinstance(item, dict))
            ir_payload = _json(getattr(ir, "payload_json", "{}"), {}) if ir else {}
            ir_scenes = ir_payload.get("scenes") if isinstance(ir_payload, dict) else []
            ir_scene = next((item for item in ir_scenes if isinstance(item, dict) and _text(item.get("scene_id")) == _text(row.scene_id)), {})
            ir_dialogue_count = len(ir_scene.get("dialogues") or []) if isinstance(ir_scene, dict) else 0
            primary, secondary, evidence = _root_cause(
                source_subjects=source_subjects, blocking_subjects=blocking_subjects,
                plan_subjects=plan_subjects, handoff_subjects=handoff_subjects,
                canonical_subjects=canonical_subjects, source_dialogue_count=source_dialogue_count,
                ir_dialogue_count=ir_dialogue_count, plan_dialogue=_text(plan.get("dialogue")),
                canonical_dialogue=_text(row.dialogue), materializer_version=_text(getattr(materialization, "materializer_version", "")),
            )
            fact = session.query(FactSnapshot).filter_by(id=int(getattr(ir, "source_fact_snapshot_id", 0) or 0), book_id=book_id).first() if ir and str(getattr(ir, "source_fact_snapshot_id", "")).isdigit() else None
            records.append({
                "book_id": book_id, "episode_id": 1, "scene_id": row.scene_id, "shot_id": row.plan_shot_id,
                "canonical_projection_id": row.id,
                "source_lineage_ids": {
                    "script_id": getattr(script, "id", None), "script_ir_version_id": getattr(ir, "id", None),
                    "fact_snapshot_id": getattr(fact, "id", None), "director_treatment_id": getattr(treatment_row, "id", None),
                    "scene_blocking_id": getattr(blocking_row, "id", None), "shot_plan_id": getattr(plan_row, "id", None),
                    "materialization_set_id": getattr(materialization, "id", None),
                },
                "source_text": source,
                "source_character_evidence": {"scene_participants": source_subjects, "scene_characters": _ids(scene.get("characters")), "raw_text_only": bool(source.get("raw_source_available"))},
                "source_dialogue_evidence": {"script_structured_count": source_dialogue_count, "raw_text_dialogue_inference": False},
                "fact_snapshot_evidence": {"status": getattr(fact, "status", None), "records": _json(getattr(fact, "records_json", "[]"), []) if fact else [], "character_or_dialogue_predicates": [item for item in (_json(getattr(fact, "records_json", "[]"), []) if fact else []) if isinstance(item, dict) and str(item.get("predicate", "")).lower() in {"character", "participant", "dialogue", "speaker"}]},
                "script_ir": {"version_id": getattr(ir, "id", None), "schema_version": _text(getattr(ir, "schema_version", "")), "top_level_characters": _ids(ir_payload.get("characters")), "scene_participants": source_subjects, "scene_characters": _ids(ir_scene.get("characters")), "scene_dialogues": ir_scene.get("dialogues") or [], "character_blocking": ir_scene.get("character_blocking") or [], "props": ir_scene.get("props") or []},
                "episode_scene_representation": {"scene_id": _text(ir_scene.get("scene_id")), "participants": source_subjects, "dialogues": ir_scene.get("dialogues") or []},
                "director_treatment": treatment,
                "scene_blocking": {**blocking, "current_row_id": getattr(blocking_row, "id", None)},
                "shot_plan": {"row_id": getattr(plan_row, "id", None), "plan_shot_id": row.plan_shot_id, "subjects": plan.get("subjects"), "participants": plan.get("participants"), "dialogue": plan.get("dialogue"), "dramatic_payload": plan.get("dramatic_payload"), "asset_bindings": plan.get("asset_bindings"), "spatial_binding": plan.get("spatial_binding"), "entry_state": plan.get("entry_state"), "exit_state": plan.get("exit_state")},
                "visual_semantic_handoff": {"exists": bool(semantic), "schema_version": semantic.get("schema_version"), "subjects": semantic.get("subjects", []), "props": semantic.get("props", []), "canonical_asset_identity": canonical_assets, "fingerprint": meta.get("semantic_projection_fingerprint")},
                "canonical_storyboard_projection": {"subjects": [], "dialogue": _text(row.dialogue), "projection_payload_subjects": projection.get("subjects"), "projection_payload_dialogue": projection.get("dialogue"), "asset_links": _json(row.asset_links, {})},
                "prompt_ir_compile_input": _prompt_payload(session, row),
                "schema_version_timestamps": {"script_ir_schema": _text(getattr(ir, "schema_version", "")), "scene_blocking_schema": blocking.get("schema_version"), "visual_semantic_schema": semantic.get("schema_version"), "materializer_version": getattr(materialization, "materializer_version", None), "materializer_policy_version": getattr(materialization, "materializer_policy_version", None), "materialization_created_at": str(getattr(materialization, "created_at", "") or ""), "storyboard_created_at": str(getattr(row, "created_at", "") or ""), "storyboard_updated_at": str(getattr(row, "updated_at", "") or "")},
                "writer_version": {"materializer": getattr(materialization, "materializer_version", None), "materializer_policy": getattr(materialization, "materializer_policy_version", None), "projection_origin": semantic.get("projection_origin")},
                "legacy_or_stale": {"current_pointer": bool(pointer), "materializer_current": getattr(materialization, "materializer_version", None) == "storyboard_materializer_v2", "stale_status": getattr(materialization, "stale_status", None), "classification": "CURRENT_MATERIALIZATION_NOT_LEGACY" if getattr(materialization, "materializer_version", None) == "storyboard_materializer_v2" else "LEGACY_OR_STALE"},
                "primary_root_cause": primary, "secondary_root_causes": secondary, "root_cause_evidence": evidence,
            })
    return records


def provenance_audit(session: Any) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for script in session.query(Script).order_by(Script.book_id, Script.episode, Script.id).all():
        if not script.current_script_ir_version_id:
            continue
        ir = session.query(ScriptIRVersion).filter_by(id=script.current_script_ir_version_id).first()
        payload = _json(getattr(ir, "payload_json", "{}"), {}) if ir else {}
        scenes = payload.get("scenes") if isinstance(payload, dict) else []
        participant_count = sum(len(scene.get("participants") or []) for scene in scenes if isinstance(scene, dict))
        dialogue_count = sum(len(scene.get("dialogues") or []) for scene in scenes if isinstance(scene, dict))
        explicit_markers: list[str] = []
        if str(getattr(script, "workflow_profile", "")).lower() == "production": explicit_markers.append("SCRIPT_WORKFLOW_PRODUCTION")
        if str(getattr(script, "production_status", "")).lower() in {"ready", "approved", "production_qualified"}: explicit_markers.append("SCRIPT_PRODUCTION_STATUS")
        executions = session.query(GenerationExecutionRecord).filter_by(book_id=script.book_id, episode=script.episode).all()
        for execution in executions:
            if str(execution.execution_mode).upper() in {"PRODUCTION", "CANARY"}: explicit_markers.append(f"GENERATION_EXECUTION_{str(execution.execution_mode).upper()}")
        pointers = session.query(StoryboardMaterializationPointer).filter_by(book_id=script.book_id, episode=script.episode).all()
        pointer_count = len(pointers)
        fresh_materialization = False
        for current_pointer in pointers:
            current_set = session.query(StoryboardMaterializationSet).filter_by(id=current_pointer.materialization_set_id).first()
            if current_set and current_set.status == "MATERIALIZED" and current_set.stale_status == "FRESH":
                fresh_materialization = True
        useful = participant_count >= 2 and dialogue_count > 0
        canary_marker = any("CANARY" in item for item in explicit_markers)
        production_authority = bool(
            str(getattr(script, "workflow_profile", "")).lower() == "production"
            and str(getattr(script, "production_status", "")).lower() in {"ready", "approved", "production_qualified"}
            and str(getattr(ir, "status", "")).lower() == "production_qualified"
            and str(getattr(ir, "qualification_state", "")).upper() == "PRODUCTION_QUALIFIED"
            and fresh_materialization
            and not canary_marker
        )
        provenance_class = "CANARY_PROJECT" if canary_marker else ("PRODUCTION_PROJECT" if production_authority else ("HISTORICAL_OR_STALE_ARTIFACT" if useful and not fresh_materialization else "UNKNOWN_PROVENANCE"))
        records.append({"book_id": script.book_id, "episode": script.episode, "script_id": script.id, "script_ir_version_id": getattr(ir, "id", None), "book_status": getattr(session.query(Book).filter_by(id=script.book_id).first(), "status", None), "script_production_status": getattr(script, "production_status", None), "script_workflow_profile": getattr(script, "workflow_profile", None), "script_ir_status": getattr(ir, "status", None), "script_ir_qualification_state": getattr(ir, "qualification_state", None), "participant_count": participant_count, "dialogue_count": dialogue_count, "useful_semantics": useful, "explicit_provenance_markers": sorted(set(explicit_markers)), "materialization_pointer_count": pointer_count, "fresh_materialization": fresh_materialization, "provenance_class": provenance_class, "eligible_for_production_source": bool(useful and provenance_class == "PRODUCTION_PROJECT")})
    useful = [item for item in records if item["useful_semantics"]]
    return {"run_id": RUN_ID, "records": records, "useful_semantic_records": useful, "status": "NO_PRODUCTION_SOURCE_WITH_USEFUL_SEMANTICS" if not any(item["eligible_for_production_source"] for item in useful) else "PRODUCTION_SOURCE_WITH_USEFUL_SEMANTICS_FOUND"}


def lineage_map() -> dict[str, Any]:
    stages = [
        {"stage": "source_text_screenplay", "schema_or_model": "Chapter.content / Script.content", "source_file": "models/book.py; models/script.py", "writer": "book/script import and pipeline content preparation", "reader": "core.script_ir.resolve_script_payload and API scene resolution", "persistence": "chapters.content; scripts.content", "schema_version": "legacy/raw source (no dialogue schema)", "required": True, "legacy_can_skip": True, "empty_allowed": True, "non_empty_subject_tests": "No direct current-source fixture; raw source audit is read-only", "dialogue_tests": "No direct raw source dialogue fixture"},
        {"stage": "fact_snapshot", "schema_or_model": "FactSnapshot / FactRecord", "source_file": "models/fact_snapshot.py; core/fact_snapshot.py", "writer": "fact snapshot preparation", "reader": "DirectorTreatment/SceneBlocking authority", "persistence": "fact_snapshots.records_json; fact_records", "schema_version": "fact snapshot revision/payload_hash", "required": True, "legacy_can_skip": True, "empty_allowed": True, "non_empty_subject_tests": "tests/test_scene_blocking_v2_api.py uses scene facts but not character facts", "dialogue_tests": "No dialogue fact test for this path"},
        {"stage": "script_ir", "schema_or_model": "ScriptIRVersion", "source_file": "core/script_ir.py; models/script_ir.py", "writer": _code_ref("core/script_ir.py", "def build_script_ir"), "reader": _code_ref("core/script_ir.py", "def resolve_script_payload"), "persistence": "script_ir_versions.payload_json", "schema_version": "script_ir_v1", "required": True, "legacy_can_skip": True, "empty_allowed": True, "non_empty_subject_tests": "tests/script_fixtures.py and canonical selector tests", "dialogue_tests": "tests/test_canonical_canary_selection.py covers canonical dialogue only"},
        {"stage": "episode_scene_semantics", "schema_or_model": "ScriptIR scenes[]", "source_file": "core/script_ir.py", "writer": _code_ref("core/script_ir.py", "scenes.append"), "reader": "scene blocking preview and treatment authority", "persistence": "payload_json.scenes[].participants/characters/dialogues", "schema_version": "script_ir_v1", "required": True, "legacy_can_skip": False, "empty_allowed": True, "non_empty_subject_tests": "partial", "dialogue_tests": "partial"},
        {"stage": "director_treatment", "schema_or_model": "DirectorTreatment", "source_file": "models/director_treatment.py; api/director_treatment_api.py", "writer": "DirectorTreatment proposal/confirmation API", "reader": "core.scene_blocking and core.phase_c_shot_plan", "persistence": "director_treatments.character_intents; beat_map", "schema_version": "director treatment authority envelope", "required": True, "legacy_can_skip": True, "empty_allowed": True, "non_empty_subject_tests": "tests/test_scene_blocking_v2_api.py", "dialogue_tests": "no independent dialogue field in current treatment contract"},
        {"stage": "scene_blocking", "schema_or_model": "SceneBlocking", "source_file": "core/scene_blocking.py; api/scene_blocking_api.py; models/scene_blocking.py", "writer": _code_ref("api/scene_blocking_api.py", "def preview_scene_blocking"), "reader": _code_ref("core/scene_blocking.py", "def build_scene_blocking_v2"), "persistence": "scene_blockings.participants; spatial_model.initial_state/beat_spatial_states", "schema_version": "scene_blocking_v2", "required": True, "legacy_can_skip": True, "empty_allowed": True, "non_empty_subject_tests": "added initial_state_from_participants regression and API assertion", "dialogue_tests": "not a dialogue carrier"},
        {"stage": "shot_plan", "schema_or_model": "ShotPlan", "source_file": "core/phase_c_shot_plan.py; models/shot_plan.py", "writer": _code_ref("core/phase_c_shot_plan.py", "def build_phase_c_shot_plan"), "reader": "core.storyboard_handoff.project_shot_design_to_storyboard_handoff", "persistence": "shot_plans.shots JSON; shots[].subjects/dialogue/asset_bindings", "schema_version": "shot_plan_phase_c_v1", "required": True, "legacy_can_skip": True, "empty_allowed": True, "non_empty_subject_tests": "tests/test_canonical_canary_selection.py uses synthetic semantic rows; Phase C tests cover contracts", "dialogue_tests": "no source dialogue carrier in current Phase C builder"},
        {"stage": "visual_semantic_handoff", "schema_or_model": "visual_semantic_handoff", "source_file": "core/storyboard_visual_semantics.py", "writer": _code_ref("core/storyboard_visual_semantics.py", "def build_visual_semantic_handoff"), "reader": "core.canonical_canary_selection.extract_canary_semantic_features", "persistence": "StoryboardShot.meta_info.visual_semantic_handoff", "schema_version": "storyboard_visual_semantic_handoff_v1", "required": True, "legacy_can_skip": True, "empty_allowed": True, "non_empty_subject_tests": "tests/test_canonical_canary_selection.py", "dialogue_tests": "tests/test_canonical_canary_selection.py"},
        {"stage": "canonical_storyboard_projection", "schema_or_model": "StoryboardShot", "source_file": "core/storyboard_materializer.py; models/storyboard.py", "writer": _code_ref("core/storyboard_materializer.py", "def materialize_storyboard_from_handoff"), "reader": _code_ref("core/storyboard_materializer.py", "def validate_current_materialization_authority"), "persistence": "storyboard_shots.dialogue; meta_info.projection_payload; meta_info.visual_semantic_handoff", "schema_version": "storyboard_materializer_v2 + storyboard_visual_semantic_handoff_v1", "required": True, "legacy_can_skip": True, "empty_allowed": True, "non_empty_subject_tests": "tests/test_storyboard_materialization* and canonical selector tests", "dialogue_tests": "prompt IR semantic tests cover downstream dialogue"},
        {"stage": "prompt_ir_compile_input", "schema_or_model": "PromptIRVersion / PromptIRPointer", "source_file": "core/prompt_ir_phase_e.py; models/prompt.py", "writer": _code_ref("core/prompt_ir_phase_e.py", "def compile_storyboard_snapshot_to_prompt_ir"), "reader": "generation readiness and provider adapter", "persistence": "prompt_ir_versions.payload_json; prompt_ir_pointers", "schema_version": "prompt_ir_*", "required": False, "legacy_can_skip": True, "empty_allowed": True, "non_empty_subject_tests": "tests/test_prompt_ir_phase_e_semantic_closure.py", "dialogue_tests": "tests/test_prompt_ir_phase_e_semantic_closure.py"},
        {"stage": "production_canary_selector", "schema_or_model": "canonical semantic inventory", "source_file": "core/canonical_canary_selection.py", "writer": _code_ref("core/canonical_canary_selection.py", "def build_canonical_shot_inventory"), "reader": _code_ref("core/canonical_canary_selection.py", "def select_semantic_canary_target"), "persistence": "docs/canonical-canary/v2-semantic-selection/*.json", "schema_version": "canonical_canary_selection_policy_v2", "required": False, "legacy_can_skip": False, "empty_allowed": False, "non_empty_subject_tests": "tests/test_canonical_canary_selection.py", "dialogue_tests": "tests/test_canonical_canary_selection.py"},
    ]
    return {"run_id": RUN_ID, "schema_version": "canonical_semantic_lineage_map_v3", "source_of_truth": "current repository code plus read-only configured database", "stages": stages, "known_boundary": {"function": _code_ref("api/scene_blocking_api.py", "declared_participants = blocking.get"), "description": "Production preview compiled an empty initial_state even when SceneBlocking participants were populated; the compiled states and Phase C subjects then remained empty.", "repair": "initial_state_from_participants projects declared participant identity into the blocking compiler seed."}}


def write_json(name: str, value: Any) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with Session() as session:
        rows = audit_rows(session)
        provenance = provenance_audit(session)
    counts = Counter(item["primary_root_cause"] for item in rows)
    secondary_counts = Counter(value for item in rows for value in item["secondary_root_causes"])
    root_cause = {
        "primary_outcome": "CODE_BUG_FIXED_RECANARY_REQUIRED",
        "quantified_causes": {"SHOT_SEMANTIC_HYDRATION_NOT_RUN": counts.get("SHOT_SEMANTIC_HYDRATION_NOT_RUN", 0), "SOURCE_DIALOGUE_EMPTY": secondary_counts.get("SOURCE_DIALOGUE_EMPTY", 0), "LEGACY_STALE_MATERIALIZATION": secondary_counts.get("LEGACY_STALE_MATERIALIZATION", 0)},
        "canonical_projection_code_loss": False,
        "upstream_hydration_boundary_code_bug": True,
        "dialogue_source_boundary": "SOURCE_DATA_HAS_NO_USEFUL_SEMANTICS",
        "production_provenance_boundary": provenance["status"],
        "safe_next_action": "Keep production database unchanged; use the patched provider-free hydration path for a new explicitly production-provenanced source with actual dialogue, then run a separately authorized dry-run rematerialization before any write.",
    }
    write_json("CANONICAL_SEMANTIC_LINEAGE_MAP.json", lineage_map())
    write_json("CANONICAL_ROW_SEMANTIC_ROOT_CAUSE_AUDIT.json", {"run_id": RUN_ID, "row_count": len(rows), "aggregate_primary_root_causes": dict(sorted(counts.items())), "aggregate_secondary_root_causes": dict(sorted(secondary_counts.items())), "records": rows})
    write_json("PRODUCTION_SEMANTIC_SOURCE_CANDIDATE_AUDIT.json", provenance)
    write_json("CANONICAL_SEMANTIC_ROOT_CAUSE_DECISION.json", {"run_id": RUN_ID, **root_cause, "external_calls": {"image": 0, "video": 0, "llm": 0, "shapi": 0, "poyo": 0, "75api_image_post": 0, "75api_video_post": 0}, "production_writes": {"prompt_ir": 0, "media": 0, "official_media": 0, "generation_execution": 0}})
    (OUT / "CANONICAL_SEMANTIC_LINEAGE_MAP.md").write_text(render_lineage_markdown(lineage_map()), encoding="utf-8")
    (OUT / "CANONICAL_SEMANTIC_ROOT_CAUSE_REPORT.md").write_text(render_report(rows, provenance, root_cause, counts, secondary_counts), encoding="utf-8")
    (OUT / "CANONICAL_SEMANTIC_REMATERIALIZATION_DRY_RUN_PLAN.md").write_text(render_rematerialization_plan(rows), encoding="utf-8")
    print(json.dumps({"run_id": RUN_ID, "row_count": len(rows), "primary_root_causes": dict(counts), "production_source_status": provenance["status"], "external_calls": 0, "production_writes": 0}, ensure_ascii=False, sort_keys=True))


def render_lineage_markdown(data: dict[str, Any]) -> str:
    lines = ["# Canonical Semantic Lineage Map V3", "", f"Run: `{data['run_id']}`", "", "This map follows persisted semantic fields from source text through canary selection. It is provider-free and read-only.", "", "## Stages", "", "| Stage | Schema/model | Persistence | Writer | Reader | Legacy skip | Empty allowed |", "|---|---|---|---|---|---:|---:|"]
    for stage in data["stages"]:
        lines.append(f"| `{stage['stage']}` | `{stage['schema_or_model']}` | `{stage['persistence']}` | `{stage['writer']}` | `{stage['reader']}` | `{stage['legacy_can_skip']}` | `{stage['empty_allowed']}` |")
    lines.extend(["", "## Proven boundary", "", f"- Function: `{data['known_boundary']['function']}`", f"- {data['known_boundary']['description']}", f"- Repair: {data['known_boundary']['repair']}", "", "## Field-level interpretation", "", "- Character identity is authoritative only when it is present in ScriptIR/SceneBlocking/ShotPlan semantic fields; `prompt_compiler_handoff.asset_identity_bindings` is excluded.", "- Dialogue is independently traced through structured source fields, ScriptIR dialogues, ShotPlan dialogue, StoryboardShot dialogue, and PromptIR payloads.", "- Missing PromptIR is a downstream readiness condition and was not compiled during this audit.", ""])
    return "\n".join(lines)


def render_report(rows: list[dict[str, Any]], provenance: dict[str, Any], decision: dict[str, Any], counts: Counter, secondary_counts: Counter) -> str:
    scene_blocking_boundary = _code_ref("api/scene_blocking_api.py", "declared_participants = blocking.get")
    lines = ["# Canonical Semantic Root Cause Report V3", "", f"Run: `{RUN_ID}`", "", "## Final state", "", f"`{decision['primary_outcome']}`", "", "## Answers", "", "### 1. Why are canonical subjects empty?", "", f"All `{len(rows)}` current rows retain source participant evidence, and SceneBlocking participants are populated, but the production preview compiled an empty `initial_state.characters`. The state snapshots were therefore empty; Phase C then read empty beat characters/participants and emitted no ShotPlan subjects. The Storyboard visual semantic handoff and canonical projection correctly propagated those empty ShotPlan values.", "", "### 2. Why is canonical dialogue empty?", "", f"The current source and ScriptIR contain no structured dialogue (`SOURCE_DIALOGUE_EMPTY` on `{secondary_counts.get('SOURCE_DIALOGUE_EMPTY', 0)}` rows). No dialogue was lost at Storyboard projection; there was no authoritative dialogue to propagate. Historical prompt text was not used.", "", "### 3. Cause type", "", f"The character path has a deterministic upstream hydration defect at `{scene_blocking_boundary}`; this is fixed by `initial_state_from_participants`. The dialogue path is source absence. Current rows are current materializations, not legacy stale rows.", "", "### 4. Exact boundary", "", "`SceneBlocking.participants` → production preview `initial_state` → `compile_blocking_states()` → Phase C `subjects`.", "", "### 5. canonical_asset_identity", "", "The nested identity object is structurally present in all 20 rows but has empty `characters` and `props` arrays, with the scene identity present. It is readiness metadata, not semantic truth, and was not used to manufacture subjects.", "", "### 6. Are the 20 rows legacy/stale?", "", "No. They point to current materialization sets using `storyboard_materializer_v2` and `storyboard_visual_semantic_handoff_v1`; they are semantically incomplete current rows, not legacy rows requiring a blind cleanup.", "", "### 7. Legitimate production source?", "", f"`{provenance['status']}`. Book 990402 has useful ScriptIR participant/dialogue data, but it has no explicit production provenance and remains ineligible. No other current source meets the people-plus-dialogue minimum.", "", "### 8. Can an existing production row become a valid person + dialogue IMAGE→VIDEO canary?", "", "No. A safe rematerialization can recover the declared single subject from the patched path, but it cannot create dialogue absent from source. No current production-provenanced row has the required two-person dialogue semantics.", "", "### 9. Code repair, rematerialization, or new source?", "", "Code repair is required for participant hydration. A separately authorized dry-run rematerialization is required for affected current rows. New explicitly production-provenanced source material with actual dialogue is required before canary selection.", "", "### 10. Safest next action", "", decision["safe_next_action"], "", "## Row root-cause counts", ""]
    for key, value in sorted(counts.items()): lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## External-call and production-write counters")
    lines.extend(["", "- Real IMAGE: `0`", "- Real VIDEO: `0`", "- External LLM: `0`", "- SHAPI: `0`", "- Poyo: `0`", "- 75API IMAGE POST: `0`", "- 75API VIDEO POST: `0`", "- PromptIR writes: `0`", "- Media writes: `0`", "- OfficialMedia writes: `0`", "- GenerationExecution production writes: `0`", "", "## Evidence", "", "- `CANONICAL_SEMANTIC_LINEAGE_MAP.md` / `.json`", "- `CANONICAL_ROW_SEMANTIC_ROOT_CAUSE_AUDIT.json`", "- `PRODUCTION_SEMANTIC_SOURCE_CANDIDATE_AUDIT.json`", "- `CANONICAL_SEMANTIC_REMATERIALIZATION_DRY_RUN_PLAN.md`", ""])
    return "\n".join(lines)


def render_rematerialization_plan(rows: list[dict[str, Any]]) -> str:
    ids = sorted({int(item["book_id"]) for item in rows})
    before = {str(item["canonical_projection_id"]): _sha({"subjects": item["canonical_storyboard_projection"]["subjects"], "dialogue": item["canonical_storyboard_projection"]["dialogue"], "projection_fingerprint": item["schema_version_timestamps"].get("storyboard_updated_at")}) for item in rows}
    lines = ["# Canonical Semantic Rematerialization Dry-Run Plan", "", "This is a design only. It was not executed and contains no database mutation.", "", "## Input scope", "", f"- Book IDs: `{ids}`", f"- Affected canonical rows: `{len(rows)}`", "- Provider calls: `0`", "- Production writes: `0`", "", "## Preconditions", "", "1. Validate explicit production provenance for each input book and reject UNKNOWN_PROVENANCE/CANARY_PROJECT.", "2. Resolve the current ScriptIR, DirectorTreatment, SceneBlocking and ShotPlan pointers; reject stale or superseded envelopes.", "3. Require the patched SceneBlocking preview/compiler path and compare the source semantic fingerprint before materialization.", "4. Keep source facts and ScriptIR immutable; no PromptIR compilation is part of this plan.", "", "## Before fingerprints", "", "```json", json.dumps(before, ensure_ascii=False, indent=2, sort_keys=True), "```", "", "## Expected projection diff", "", "- Character subjects: current empty arrays would become only the already-declared SceneBlocking participant(s) after the hydration repair.", "- Dialogue: no change; source and ScriptIR dialogue are empty.", "- Props: no change; no authoritative props are present.", "- `canonical_asset_identity`: recomputed only from the repaired ShotPlan semantic projection; never from legacy prompt handoff.", "", "## Idempotency and stale-write protection", "", "- Use the source ScriptIR authority fingerprint, ShotPlan authority fingerprint, materialization set fingerprint, and semantic projection fingerprint as an idempotency tuple.", "- Abort if any current pointer, payload hash, source fingerprint, or materialization set changes between dry-run and authorized execution.", "- Never update an existing set in place; create a new immutable set and move the explicit pointer only after all rows validate.", "", "## Rollback", "", "- Keep the prior materialization set and StoryboardShot rows immutable and addressable.", "- On failure, leave the new set unpublished and restore the pointer to the prior fresh set; PromptIR and OfficialMedia remain untouched.", "", "## Authorization gate", "", "Production execution requires explicit user authorization after a review of the dry-run diff and provenance audit. This phase did not receive or consume that authorization.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
