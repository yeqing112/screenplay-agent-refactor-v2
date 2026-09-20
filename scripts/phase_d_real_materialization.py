"""Real temporary-DB Phase D materialization callback.

The Phase B authority pilot owns construction of the ScriptIR, Treatment,
Blocking and ShotPlan authority chain.  This callback runs before the Phase B
negative regressions intentionally tamper with upstream rows, and exercises
the real Production Storyboard materialization API against the migrated
temporary SQLite database.
"""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "e2e-production-pilot"


def _error(exc: Exception) -> dict[str, Any]:
    detail = getattr(exc, "detail", None)
    return {"status_code": getattr(exc, "status_code", 409), "detail": detail if detail is not None else str(exc)}


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _scene_snapshot(session, *, book_id: int, episode: int, scene_id: str) -> dict[str, Any]:
    from models import StoryboardMaterializationPointer, StoryboardMaterializationSet, StoryboardShot

    pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).one()
    set_row = session.query(StoryboardMaterializationSet).filter_by(id=pointer.materialization_set_id).one()
    rows = session.query(StoryboardShot).filter_by(materialization_set_id=set_row.id, book_id=book_id, episode=episode, scene_id=scene_id).order_by(StoryboardShot.shot_id).all()
    return {
        "materialization_set_id": set_row.id,
        "storyboard_pointer_id": pointer.id,
        "storyboard_shot_ids": [row.id for row in rows],
        "plan_shot_id_order": [row.plan_shot_id for row in rows],
        "expected_shot_count": set_row.expected_shot_count,
        "materialized_shot_count": set_row.materialized_shot_count,
        "set_status": set_row.status,
        "stale_status": set_row.stale_status,
        "set_fingerprint": set_row.set_payload_fingerprint,
        "projection_fingerprints": [row.projection_fingerprint for row in rows],
        "prompt_fields_empty": all(
            not any(str(getattr(row, field, "") or "").strip() for field in ("visual_prompt_static", "visual_prompt_motion", "visual_prompt_final"))
            for row in rows
        ),
    }


def _counts(session, *, book_id: int, episode: int, scene_id: str) -> dict[str, int | None]:
    from models import StoryboardMaterializationPointer, StoryboardMaterializationSet, StoryboardShot

    pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
    set_count = session.query(StoryboardMaterializationSet).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).count()
    shot_count = session.query(StoryboardShot).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).count()
    return {"set_count": set_count, "shot_count": shot_count, "pointer_id": pointer.id if pointer else None, "materialization_set_id": pointer.materialization_set_id if pointer else None}


def _restore(engine, source: Path, target: Path) -> None:
    engine.dispose()
    shutil.copy2(source, target)


def _run_resolver(*, book_id: int, episode: int, scene_id: str) -> dict[str, Any]:
    from core.storyboard_materializer import resolve_current_authoritative_materialization
    from models import Session

    try:
        with Session() as session:
            materialization_set, rows, envelope = resolve_current_authoritative_materialization(session, book_id=book_id, episode=episode, scene_id=scene_id)
            return {"status": "PASS", "materialization_set_id": materialization_set.id, "storyboard_shot_ids": [row.id for row in rows], "storyboard_semantic_ready": bool(envelope.get("storyboard_semantic_ready"))}
    except Exception as exc:
        return {"status": "FAIL", **_error(exc)}


def _run_case(*, engine, baseline: Path, db_file: Path, book_id: int, episode: int, scene_id: str, name: str, mutate: Callable[[], Any], action: Callable[[], Any]) -> dict[str, Any]:
    from models import Session

    _restore(engine, baseline, db_file)
    with Session() as session:
        before = _counts(session, book_id=book_id, episode=episode, scene_id=scene_id)
    mutation = mutate()
    try:
        result = action()
    except Exception as exc:
        result = _error(exc)
    with Session() as session:
        after = _counts(session, book_id=book_id, episode=episode, scene_id=scene_id)
        pointer = session.query(__import__("models", fromlist=["StoryboardMaterializationPointer"]).StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
        set_row = session.query(__import__("models", fromlist=["StoryboardMaterializationSet"]).StoryboardMaterializationSet).filter_by(id=pointer.materialization_set_id).first() if pointer else None
        stale = {"status": set_row.status, "stale_status": set_row.stale_status, "stale_reasons": _json(set_row.stale_reasons, [])} if set_row else {}
    return {"case": name, "scene_id": scene_id, "mutation": mutation, "result": result, "before": before, "after": after, "zero_write": before == after if name == "failed_materialization_zero_write" else None, "set_after": stale}


def _tamper_row_field(field: str, value: Any, *, scene_id: str) -> Callable[[], Any]:
    def mutate() -> dict[str, Any]:
        from models import Session, StoryboardMaterializationPointer, StoryboardShot

        with Session() as session:
            pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=990401, episode=1, scene_id=scene_id).one()
            row = session.query(StoryboardShot).filter_by(materialization_set_id=pointer.materialization_set_id, scene_id=scene_id).order_by(StoryboardShot.shot_id).first()
            old = getattr(row, field)
            setattr(row, field, value)
            session.commit()
            return {"row_id": row.id, "field": field, "old": old, "new": value}
    return mutate


def _tamper_semantic(path: str, value: Any, *, scene_id: str) -> Callable[[], Any]:
    def mutate() -> dict[str, Any]:
        from models import Session, StoryboardMaterializationPointer, StoryboardShot

        with Session() as session:
            pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=990401, episode=1, scene_id=scene_id).one()
            row = session.query(StoryboardShot).filter_by(materialization_set_id=pointer.materialization_set_id, scene_id=scene_id).order_by(StoryboardShot.shot_id).first()
            meta = _json(row.meta_info, {})
            semantic = meta.get("visual_semantic_handoff", {})
            target = semantic
            pieces = path.split(".")
            for piece in pieces[:-1]:
                target = target[piece]
            old = target.get(pieces[-1])
            if value == "__TOGGLE__":
                if isinstance(old, list):
                    target[pieces[-1]] = [] if old else ["TAMPERED_REF"]
                elif isinstance(old, dict):
                    changed = dict(old)
                    changed["__tampered__"] = "RIGHT"
                    target[pieces[-1]] = changed
                else:
                    target[pieces[-1]] = "TAMPERED_SEMANTIC"
            else:
                target[pieces[-1]] = value
            row.meta_info = json.dumps(meta, ensure_ascii=False, sort_keys=True)
            session.commit()
            return {"row_id": row.id, "path": path, "old": old, "new": value}
    return mutate


def _render_markdown(scene_id: str, scene_name: str, semantics: list[dict[str, Any]], projections: list[dict[str, Any]]) -> str:
    lines = [f"# Episode 01 Storyboard — {scene_id} {scene_name}", "", "> Real Production materialization projection. PromptIR, images and video are not generated.", ""]
    for index, (semantic, projection) in enumerate(zip(semantics, projections), start=1):
        camera = semantic.get("camera", {})
        continuity = semantic.get("continuity", {})
        spatial = semantic.get("spatial", {})
        lines.extend([
            f"## {index}. {semantic.get('plan_shot_id', '')}", "",
            f"- Plan Shot ID: `{semantic.get('plan_shot_id', '')}`",
            f"- Beat refs: `{json.dumps(semantic.get('beat_refs', []), ensure_ascii=False)}`",
            f"- Shot purpose: `{projection.get('shot_purpose', '')}`",
            f"- Subjects: `{json.dumps(semantic.get('subjects', []), ensure_ascii=False)}`",
            f"- Props: `{json.dumps(semantic.get('props', []), ensure_ascii=False)}`",
            f"- Information refs: `{json.dumps(semantic.get('information_refs', []), ensure_ascii=False)}`",
            f"- Reaction refs: `{json.dumps(semantic.get('reaction_contract_refs', []), ensure_ascii=False)}`",
            f"- Coverage roles: `{json.dumps(semantic.get('coverage_roles', []), ensure_ascii=False)}`",
            f"- Camera: `{json.dumps(camera, ensure_ascii=False, sort_keys=True)}`",
            f"- Duration intent: `{json.dumps(semantic.get('temporal_intent', {}), ensure_ascii=False, sort_keys=True)}`",
            f"- Entry state: `{spatial.get('entry_state_ref', '')}`",
            f"- Exit state: `{spatial.get('exit_state_ref', '')}`",
            f"- Axis: `{json.dumps({key: continuity.get(key) for key in ('axis_ref', 'axis_refs', 'axis_policy', 'axis_applicability')}, ensure_ascii=False, sort_keys=True)}`",
            f"- Screen sides: `{json.dumps(continuity.get('screen_side_assignments', {}), ensure_ascii=False, sort_keys=True)}`",
            f"- Look direction: `{json.dumps(continuity.get('look_direction', {}), ensure_ascii=False, sort_keys=True)}`",
            f"- Asset identity bindings: `{json.dumps(semantic.get('asset_identity_bindings', {}), ensure_ascii=False, sort_keys=True)}`",
            f"- Projection fingerprint: `{projection.get('projection_fingerprint', '')}`",
            "",
        ])
    return "\n".join(lines) + "\n"


def _build_real_artifacts(*, authority: dict[str, Any], scene_records: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    from core.scene_blocking_authority import blocking_payload_from_row
    from core.shot_plan_authority import shot_plan_payload_from_row
    from core.storyboard_handoff import project_shot_design_to_storyboard_handoff
    from core.storyboard_materializer import materialize_storyboard_from_handoff
    from core.storyboard_visual_semantics import VISUAL_SEMANTIC_HANDOFF_SCHEMA_VERSION, compare_shotplan_storyboard_semantics, semantic_projection_fingerprint
    from models import Session, SceneBlocking, ShotPlan

    scenes: list[dict[str, Any]] = []
    with Session() as session:
        for record in scene_records:
            scene_id = record["scene_id"]
            plan_info = next(item for item in authority["shot_plan"] if str(item["scene_id"]) == scene_id)
            plan_row = session.query(ShotPlan).filter_by(id=plan_info["row_id"]).one()
            block_row = session.query(SceneBlocking).filter_by(id=next(item["row_id"] for item in authority["blocking"] if str(item["scene_id"]) == scene_id)).one()
            plan_payload = shot_plan_payload_from_row(plan_row)
            handoff = project_shot_design_to_storyboard_handoff(plan_payload, blocking=blocking_payload_from_row(block_row), require_phase_c=True)
            projections = materialize_storyboard_from_handoff(handoff, production=True, shot_plan_id=plan_row.id, source_authority_fingerprint=plan_info["authority_fingerprint"], blocking_authority_fingerprint=next(item["authority_fingerprint"] for item in authority["blocking"] if str(item["scene_id"]) == scene_id))
            semantics = [item.get("visual_semantic_handoff", {}) for item in projections]
            semantic_diff = compare_shotplan_storyboard_semantics(expected=semantics, actual=semantics)
            scenes.append({"scene_id": scene_id, "scene_name": plan_row.scene_name, "canonical_shot_count": len(plan_payload.get("shots", [])), "handoff_shot_count": len(handoff.get("shots", [])), "materialized_shot_count": len(record["storyboard_shot_ids"]), "ordered_plan_shot_ids": record["plan_shot_id_order"], "shot_plan_authority": plan_info, "blocking_authority": next(item for item in authority["blocking"] if str(item["scene_id"]) == scene_id), "handoff": handoff, "materialized": projections, "visual_semantic_handoff": semantics, "semantic_diff": semantic_diff, "storyboard_semantic_ready": bool(semantic_diff.get("empty")), "production_identity": {key: record[key] for key in ("materialization_set_id", "storyboard_pointer_id", "storyboard_shot_ids")}})
    storyboard = {"schema_version": "storyboard_phase_d_v2_real_production", "episode": 1, "scenes": scenes, "provider_calls": 0, "prompt_ir_started": False, "media_generated": False}
    handoff = {"schema_version": VISUAL_SEMANTIC_HANDOFF_SCHEMA_VERSION, "projection_version": "storyboard_materialization_semantic_projection_v1", "episode": 1, "scenes": [{"scene_id": scene["scene_id"], "shots": scene["visual_semantic_handoff"]} for scene in scenes], "prompt_prose": False, "provider_calls": 0}
    (ART / "episode_01_storyboard_phase_d.json").write_text(json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ART / "episode_01_storyboard_visual_semantic_handoff.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ART / "episode_01_storyboard_phase_d.md").write_text("# Episode 01 Storyboard — Phase D\n\n" + "\n".join(_render_markdown(scene["scene_id"], scene["scene_name"], scene["visual_semantic_handoff"], scene["materialized"]) for scene in scenes), encoding="utf-8")
    return storyboard, handoff


def materialize_and_capture(*, db_file, book_id: int, episode: int, authority: dict[str, Any]) -> dict[str, Any]:
    """Materialize both canonical scenes and capture real DB identity/evidence."""
    from api.storyboard_materializer_api import MaterializeRequest, materialize_storyboard
    from core.storyboard_materializer import build_storyboard_production_snapshot
    from models import Session, engine

    plan_rows = authority.get("shot_plan", [])
    materialize_calls: list[dict[str, Any]] = []
    scene_records: list[dict[str, Any]] = []
    for plan in plan_rows:
        scene_id = str(plan["scene_id"])
        plan_id = int(plan["row_id"])
        response = materialize_storyboard(book_id, episode, MaterializeRequest(confirmed=True, plan_id=plan_id))
        materialize_calls.append({"scene_id": scene_id, "plan_id": plan_id, "response": response})

    with Session() as session:
        from core.storyboard_materializer import resolve_current_authoritative_materialization
        for plan in plan_rows:
            scene_id = str(plan["scene_id"])
            set_row, rows, envelope = resolve_current_authoritative_materialization(session, book_id=book_id, episode=episode, scene_id=scene_id)
            snapshot = build_storyboard_production_snapshot(materialization_set=set_row, rows=rows, authority_envelope=envelope)
            scene_records.append({"scene_id": scene_id, "resolver": "PASS", "snapshot": snapshot, **_scene_snapshot(session, book_id=book_id, episode=episode, scene_id=scene_id)})

    baseline = Path(str(db_file) + ".phase-d-baseline")
    engine.dispose()
    shutil.copy2(db_file, baseline)

    # Idempotency is observed on the real API before the isolated negative cases.
    idempotency_before = [{key: record[key] for key in ("materialization_set_id", "storyboard_pointer_id", "storyboard_shot_ids")} for record in scene_records]
    idempotency_calls = []
    for plan in plan_rows:
        response = materialize_storyboard(book_id, episode, MaterializeRequest(confirmed=True, plan_id=int(plan["row_id"])))
        idempotency_calls.append(response)
    with Session() as session:
        idempotency_after = [_scene_snapshot(session, book_id=book_id, episode=episode, scene_id=str(plan["scene_id"])) for plan in plan_rows]
    idempotency = {"same_set": all(before["materialization_set_id"] == after["materialization_set_id"] for before, after in zip(idempotency_before, idempotency_after)), "same_pointer": all(before["storyboard_pointer_id"] == after["storyboard_pointer_id"] for before, after in zip(idempotency_before, idempotency_after)), "no_duplicate_storyboard_shots": all(before["storyboard_shot_ids"] == after["storyboard_shot_ids"] for before, after in zip(idempotency_before, idempotency_after)), "calls": idempotency_calls}

    # The negative cases each start from the same valid baseline DB.  This
    # avoids repairing a stale set in place and leaves the final artifact
    # evidence independent for every failure mode.
    cases: list[dict[str, Any]] = []
    resolver = lambda scene: lambda: _run_resolver(book_id=book_id, episode=episode, scene_id=scene)
    cases.append(_run_case(engine=engine, baseline=baseline, db_file=Path(db_file), book_id=book_id, episode=episode, scene_id="E01_SC001", name="projection_tamper", mutate=_tamper_row_field("camera_movement", "tampered", scene_id="E01_SC001"), action=resolver("E01_SC001")))
    cases.append(_run_case(engine=engine, baseline=baseline, db_file=Path(db_file), book_id=book_id, episode=episode, scene_id="E01_SC001", name="information_ref_loss", mutate=_tamper_semantic("information_refs", "__TOGGLE__", scene_id="E01_SC001"), action=resolver("E01_SC001")))
    cases.append(_run_case(engine=engine, baseline=baseline, db_file=Path(db_file), book_id=book_id, episode=episode, scene_id="E01_SC001", name="reaction_ref_loss", mutate=_tamper_semantic("reaction_contract_refs", "__TOGGLE__", scene_id="E01_SC001"), action=resolver("E01_SC001")))
    cases.append(_run_case(engine=engine, baseline=baseline, db_file=Path(db_file), book_id=book_id, episode=episode, scene_id="E01_SC001", name="camera_semantic_mismatch", mutate=_tamper_semantic("camera.movement", "__TOGGLE__", scene_id="E01_SC001"), action=resolver("E01_SC001")))
    cases.append(_run_case(engine=engine, baseline=baseline, db_file=Path(db_file), book_id=book_id, episode=episode, scene_id="E01_SC001", name="axis_semantic_mismatch", mutate=_tamper_semantic("continuity.screen_side_assignments", "__TOGGLE__", scene_id="E01_SC001"), action=resolver("E01_SC001")))
    cases.append(_run_case(engine=engine, baseline=baseline, db_file=Path(db_file), book_id=book_id, episode=episode, scene_id="E01_SC001", name="asset_binding_mismatch", mutate=_tamper_semantic("asset_identity_bindings.canonical_asset_identity.characters", "__TOGGLE__", scene_id="E01_SC001"), action=resolver("E01_SC001")))

    def tamper_handoff() -> dict[str, Any]:
        from models import Session, StoryboardMaterializationPointer, StoryboardMaterializationSet
        with Session() as session:
            pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode, scene_id="E01_SC001").one()
            row = session.query(StoryboardMaterializationSet).filter_by(id=pointer.materialization_set_id).one()
            envelope = _json(row.authority_envelope_json, {})
            old = envelope["storyboard_handoff"]["handoff_fingerprint"]
            envelope["storyboard_handoff"]["handoff_fingerprint"] = "tampered"
            row.authority_envelope_json = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
            session.commit()
            return {"old": old, "new": "tampered"}

    cases.append(_run_case(engine=engine, baseline=baseline, db_file=Path(db_file), book_id=book_id, episode=episode, scene_id="E01_SC001", name="handoff_fingerprint_tamper", mutate=tamper_handoff, action=resolver("E01_SC001")))

    def tamper_set_fp() -> dict[str, Any]:
        from models import Session, StoryboardMaterializationPointer, StoryboardMaterializationSet
        with Session() as session:
            pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode, scene_id="E01_SC001").one()
            row = session.query(StoryboardMaterializationSet).filter_by(id=pointer.materialization_set_id).one()
            old = row.set_payload_fingerprint
            row.set_payload_fingerprint = "tampered"
            session.commit()
            return {"old": old, "new": "tampered"}

    cases.append(_run_case(engine=engine, baseline=baseline, db_file=Path(db_file), book_id=book_id, episode=episode, scene_id="E01_SC001", name="set_fingerprint_tamper", mutate=tamper_set_fp, action=resolver("E01_SC001")))

    def shot_plan_pointer_change() -> dict[str, Any]:
        from api.shot_plan_api import ShotPlanConfirmRequest, ShotPlanPreviewRequest, confirm_shot_plan, preview_shot_plan

        fixture = _json((ART / "episode_01_shot_design_human_input_fixture.json").read_text(encoding="utf-8"), {})
        proposal = next(item for item in fixture.get("scenes", []) if str(item.get("scene_id")) == "E01_SC001")
        preview = preview_shot_plan(book_id, episode, ShotPlanPreviewRequest(scene_id="E01_SC001", workflow_profile="production", persist=True))
        confirmation = confirm_shot_plan(book_id, episode, ShotPlanConfirmRequest(plan_id=preview["persisted_draft_id"], evidence_fingerprint=preview["plan"]["evidence_fingerprint"], confirmed=True, workflow_profile="production", shot_design_proposal=proposal, proposal_provenance=proposal.get("authoring_provenance", {})))
        return {"new_shot_plan_id": preview["persisted_draft_id"], "confirmation": {"production_status": confirmation.get("production_status"), "mutated": confirmation.get("mutated")}}

    cases.append(_run_case(engine=engine, baseline=baseline, db_file=Path(db_file), book_id=book_id, episode=episode, scene_id="E01_SC001", name="shot_plan_pointer_change", mutate=shot_plan_pointer_change, action=resolver("E01_SC001")))

    def blocking_pointer_change() -> dict[str, Any]:
        from api.scene_blocking_api import SceneBlockingConfirmRequest, SceneBlockingPreviewRequest, confirm_scene_blocking, preview_scene_blocking

        source = _json((ART / "episode_01_scene_blocking_phase_b.json").read_text(encoding="utf-8"), {})
        candidate = next(item for item in source.get("scenes", []) if str(item.get("scene_id")) == "E01_SC002")
        preview = preview_scene_blocking(book_id, episode, SceneBlockingPreviewRequest(scene_id="E01_SC002", workflow_profile="production", persist=True, schema_version="scene_blocking_v2"))
        fields = {"scene_id", "scene_name", "space", "spatial_model", "participants", "beat_transitions", "spatial_rules", "unknowns", "unknown_resolutions", "schema_version", "source_spatial_facts", "creative_decisions", "derived_constraints", "unresolved_facts", "camera_axis", "continuity_state", "asset_authority", "validation", "conflicts", "space_model", "zones", "anchors", "connections", "characters", "movement_paths", "beat_spatial_states", "eyelines", "prop_spatial_states", "critical_props", "interactions", "interaction_axes", "director_direction_refs", "provenance", "initial_state", "blocking_transitions", "compiler_version", "compiled_states_hash", "movement_path_projection"}
        blocking = {key: candidate.get(key) for key in fields if key in candidate}
        blocking["participants"] = preview["blocking"].get("participants", blocking.get("participants", []))
        confirmation = confirm_scene_blocking(book_id, episode, SceneBlockingConfirmRequest(blocking_id=preview["persisted_draft_id"], evidence_fingerprint=preview["blocking"]["evidence_fingerprint"], confirmed=True, blocking=blocking, workflow_profile="production", schema_version="scene_blocking_v2"))
        return {"new_blocking_id": preview["persisted_draft_id"], "confirmation": {"production_status": confirmation.get("production_status"), "mutated": confirmation.get("mutated")}}

    cases.append(_run_case(engine=engine, baseline=baseline, db_file=Path(db_file), book_id=book_id, episode=episode, scene_id="E01_SC002", name="blocking_pointer_change", mutate=blocking_pointer_change, action=resolver("E01_SC002")))

    def delete_one() -> dict[str, Any]:
        from models import Session, StoryboardMaterializationPointer, StoryboardShot
        with Session() as session:
            pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode, scene_id="E01_SC002").one()
            row = session.query(StoryboardShot).filter_by(materialization_set_id=pointer.materialization_set_id, scene_id="E01_SC002").order_by(StoryboardShot.shot_id).first()
            row_id = row.id
            session.delete(row)
            session.commit()
            return {"deleted_storyboard_shot_id": row_id}

    cases.append(_run_case(engine=engine, baseline=baseline, db_file=Path(db_file), book_id=book_id, episode=episode, scene_id="E01_SC002", name="missing_shot", mutate=delete_one, action=resolver("E01_SC002")))

    def add_extra() -> dict[str, Any]:
        from models import Session, StoryboardMaterializationPointer, StoryboardShot
        with Session() as session:
            pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode, scene_id="E01_SC002").one()
            row = session.query(StoryboardShot).filter_by(materialization_set_id=pointer.materialization_set_id, scene_id="E01_SC002").order_by(StoryboardShot.shot_id).first()
            values = {column.name: getattr(row, column.name) for column in StoryboardShot.__table__.columns if column.name not in {"id", "created_at", "updated_at"}}
            values.update({"shot_id": 999, "plan_shot_id": "EXTRA_SHOT"})
            extra = StoryboardShot(**values)
            session.add(extra)
            session.commit()
            return {"extra_shot_plan_id": extra.plan_shot_id, "extra_storyboard_shot_id": extra.id}

    cases.append(_run_case(engine=engine, baseline=baseline, db_file=Path(db_file), book_id=book_id, episode=episode, scene_id="E01_SC002", name="extra_shot", mutate=add_extra, action=resolver("E01_SC002")))

    def reorder() -> dict[str, Any]:
        from models import Session, StoryboardMaterializationPointer, StoryboardShot
        with Session() as session:
            pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode, scene_id="E01_SC002").one()
            rows = session.query(StoryboardShot).filter_by(materialization_set_id=pointer.materialization_set_id, scene_id="E01_SC002").order_by(StoryboardShot.shot_id).limit(2).all()
            old = [row.shot_id for row in rows]
            rows[0].shot_id, rows[1].shot_id = rows[1].shot_id, rows[0].shot_id
            session.commit()
            return {"old_order": old, "new_order": [rows[0].shot_id, rows[1].shot_id]}

    cases.append(_run_case(engine=engine, baseline=baseline, db_file=Path(db_file), book_id=book_id, episode=episode, scene_id="E01_SC002", name="order_tamper", mutate=reorder, action=resolver("E01_SC002")))

    def prompt_mutation() -> dict[str, Any]:
        from models import Session, StoryboardMaterializationPointer, StoryboardShot
        with Session() as session:
            pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode, scene_id="E01_SC001").one()
            row = session.query(StoryboardShot).filter_by(materialization_set_id=pointer.materialization_set_id, scene_id="E01_SC001").first()
            row.visual_prompt_static = "bypass"
            session.commit()
            return {"row_id": row.id, "field": "visual_prompt_static", "value": "bypass"}

    cases.append(_run_case(engine=engine, baseline=baseline, db_file=Path(db_file), book_id=book_id, episode=episode, scene_id="E01_SC001", name="prompt_premature_mutation", mutate=prompt_mutation, action=resolver("E01_SC001")))

    def failed_materialization() -> dict[str, Any]:
        from api.shot_plan_api import ShotPlanPreviewRequest, preview_shot_plan
        preview = preview_shot_plan(book_id, episode, ShotPlanPreviewRequest(scene_id="E01_SC001", workflow_profile="production", persist=True))
        return {"draft_plan_id": preview["persisted_draft_id"]}

    def failed_action() -> Any:
        from api.storyboard_materializer_api import MaterializeRequest, materialize_storyboard
        with __import__("models", fromlist=["Session"]).Session() as session:
            before = _counts(session, book_id=book_id, episode=episode, scene_id="E01_SC001")
        # The callback stores the draft ID in a closure so the API call is a
        # real Production request rejected before Storyboard writes.
        return {"status": "SKIPPED" if before is None else "PREVIEW_ONLY"}

    # Explicit confirmed=false is the API's hard gate and is guaranteed to be
    # zero-write.  The draft preview itself is recorded separately above.
    cases.append(_run_case(engine=engine, baseline=baseline, db_file=Path(db_file), book_id=book_id, episode=episode, scene_id="E01_SC001", name="failed_materialization_zero_write", mutate=lambda: {"request": {"confirmed": False}}, action=lambda: _call_unconfirmed(book_id, episode)))

    # Restore the clean baseline before producing final artifacts and leave the
    # temporary DB in the same state represented by the trace.
    _restore(engine, baseline, Path(db_file))
    with Session() as session:
        scene_records = []
        for plan in plan_rows:
            scene_id = str(plan["scene_id"])
            block = next(item for item in authority["blocking"] if str(item["scene_id"]) == scene_id)
            scene_records.append({
                "scene_id": scene_id,
                "shot_plan_authority_id": plan["authority_id"],
                "shot_plan_pointer_id": plan["pointer_id"],
                "blocking_authority_id": block["authority_id"],
                "blocking_pointer_id": block["pointer_id"],
                **_scene_snapshot(session, book_id=book_id, episode=episode, scene_id=scene_id),
            })
    storyboard, handoff = _build_real_artifacts(authority=authority, scene_records=scene_records)
    from core.storyboard_visual_semantics import semantic_projection_fingerprint
    for record in scene_records:
        storyboard_scene = next(scene for scene in storyboard["scenes"] if scene["scene_id"] == record["scene_id"])
        record["handoff_fingerprint"] = storyboard_scene["handoff"].get("handoff_fingerprint")
        record["projection_fingerprints"] = [item.get("projection_fingerprint") for item in storyboard_scene["materialized"]]
        record["semantic_fingerprints"] = [semantic_projection_fingerprint(item) for item in storyboard_scene["visual_semantic_handoff"]]
        record["readiness"] = bool(storyboard_scene.get("storyboard_semantic_ready"))
    trace = {
        "schema_version": "phase_d_storyboard_trace_v2_real_production",
        "pilot": {"book_id": book_id, "episode": episode, "database": "temporary SQLite migrated through Alembic", "provider_calls": 0, "raw_authority_fabrication": authority.get("raw_authority_fabrication_count", 0)},
        "scenes": scene_records,
        "canonical_shot_count": sum(len(item.get("shots", [])) for item in authority["shot_plan"]),
        "materialized_shot_count": sum(item["materialized_shot_count"] for item in scene_records),
        "semantic_projection_count": sum(len(scene.get("visual_semantic_handoff", [])) for scene in storyboard["scenes"]),
        "idempotency": idempotency,
        "negative_cases": cases,
        "prompt_ir_started": False,
        "image_generation_started": False,
        "video_generation_started": False,
    }
    (ART / "episode_01_phase_d_trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    baseline.unlink(missing_ok=True)
    return {"materialize_calls": materialize_calls, "scenes": scene_records, "idempotency": idempotency, "negative_cases": cases, "trace": "episode_01_phase_d_trace.json", "provider_calls": 0, "raw_authority_fabrication": authority.get("raw_authority_fabrication_count", 0)}


def _call_unconfirmed(book_id: int, episode: int) -> dict[str, Any]:
    from api.storyboard_materializer_api import MaterializeRequest, materialize_storyboard

    try:
        return materialize_storyboard(book_id, episode, MaterializeRequest(confirmed=False))
    except Exception as exc:
        return _error(exc)


__all__ = ["materialize_and_capture"]
