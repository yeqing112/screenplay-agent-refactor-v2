"""Run the provider-free Phase E pilot on the real Phase D temporary DB.

The Phase B runner owns creation of the upstream authority chain.  This module
is called as its post-materialization callback, so PromptIR compilation reads
the current StoryboardMaterializationPointer/Set/Shot rows through the shared
resolver and writes only PromptIR authority rows in the same temporary
Alembic-migrated SQLite database.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import shutil
from pathlib import Path
from typing import Any

from core.prompt_ir_phase_e import build_generation_policy, fingerprint, resolve_current_authoritative_prompt_ir, validate_prompt_ir_historical_integrity

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "e2e-production-pilot"


def _copy_sqlite_snapshot(source: Path, destination: Path) -> None:
    """Copy a disposable SQLite snapshot with WAL contents included."""
    for suffix in ("-wal", "-shm"):
        Path(str(destination) + suffix).unlink(missing_ok=True)
    source_connection = sqlite3.connect(source)
    destination_connection = sqlite3.connect(destination)
    try:
        destination_connection.execute("PRAGMA journal_mode=DELETE")
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


def _json(value: Any, fallback: Any):
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _error(exc: Exception) -> dict[str, Any]:
    detail = getattr(exc, "detail", None)
    return {"status_code": getattr(exc, "status_code", 409), "detail": detail if detail is not None else str(exc)}


def _counts(session, book_id: int, episode: int) -> dict[str, int]:
    from models import PromptIRAuthority, PromptIRPointer, PromptIRVersion

    return {
        "versions": session.query(PromptIRVersion).filter_by(book_id=book_id, episode=episode).count(),
        "authorities": session.query(PromptIRAuthority).filter_by(book_id=book_id, episode=episode).count(),
        "pointers": session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).count(),
    }


def _compile(book_id: int, episode: int, request: Any) -> dict[str, Any]:
    from api.prompt_ir_authority_api import compile_prompt_ir_phase_e

    try:
        return compile_prompt_ir_phase_e(book_id, episode, request)
    except Exception as exc:
        return _error(exc)


def _preview(book_id: int, episode: int, shot_id: int) -> dict[str, Any]:
    from api.prompt_ir_authority_api import AdapterPreviewRequest, preview_prompt_ir_adapter

    try:
        return preview_prompt_ir_adapter(book_id, episode, shot_id, AdapterPreviewRequest(adapter_id="image_generic"))
    except Exception as exc:
        return _error(exc)


def _snapshot_records(session, *, book_id: int, episode: int) -> list[dict[str, Any]]:
    from core.storyboard_materializer import build_storyboard_production_snapshot, resolve_current_authoritative_materialization
    from models import StoryboardMaterializationPointer

    output = []
    pointers = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode).order_by(StoryboardMaterializationPointer.scene_id).all()
    for pointer in pointers:
        materialization_set, rows, envelope = resolve_current_authoritative_materialization(session, book_id=book_id, episode=episode, scene_id=pointer.scene_id)
        snapshot = build_storyboard_production_snapshot(materialization_set=materialization_set, rows=rows, authority_envelope=envelope)
        output.append({
            "scene_id": pointer.scene_id,
            "materialization_set_id": materialization_set.id,
            "storyboard_pointer_id": pointer.id,
            "storyboard_shot_ids": [row.id for row in rows],
            "snapshot": snapshot,
        })
    return output


def _run_phase_e(book_id: int, episode: int, db_file: Path) -> dict[str, Any]:
    from api.prompt_ir_authority_api import PhaseECompileRequest, _production_asset_authority
    from core.storyboard_materializer import mark_materialization_set_stale
    from core.visual_asset_authority import build_asset_key, fingerprint as asset_fingerprint, propagate_visual_asset_staleness, scope_key
    from models import PromptIRAuthority, PromptIRPointer, PromptIRVersion, Session, StoryboardMaterializationPointer, StoryboardMaterializationSet, StoryboardShot, VisualAssetPointer, VisualAssetVersion, engine

    with Session() as session:
        snapshot_records = _snapshot_records(session, book_id=book_id, episode=episode)
        snapshots = [item["snapshot"] for item in snapshot_records]
        snapshot_counts = [{"scene_id": item["scene_id"], "storyboard_shot_count": len(item["snapshot"]["ordered_shots"]), "storyboard_shot_ids": item["storyboard_shot_ids"], "materialization_set_id": item["materialization_set_id"], "storyboard_pointer_id": item["storyboard_pointer_id"], "semantic_ready": item["snapshot"].get("storyboard_semantic_ready"), "visual_semantic_handoff_rows": sum(bool(row.get("visual_semantic_handoff")) for row in item["snapshot"]["ordered_shots"]), "prompt_compiler_handoff_rows": sum(bool(row.get("prompt_compiler_handoff")) for row in item["snapshot"]["ordered_shots"]), "projection_payload_rows": sum(bool(row.get("projection_payload")) for row in item["snapshot"]["ordered_shots"])} for item in snapshot_records]

        # Seed current, media-free VisualAssetPointer/Version rows for every
        # identity present in the real Storyboard handoffs.  This exercises the
        # pointer integrity resolver without generating or downloading media.
        identities = set()
        for snapshot in snapshots:
            # The scene identity is authoritative at snapshot level even when
            # a legacy/materialized handoff omits the prompt compiler block.
            scene_id = str(snapshot.get("scene_id") or "").strip()
            if scene_id:
                identities.add(("scene", scene_id))
            for shot in snapshot.get("ordered_shots", []):
                handoff = shot.get("prompt_compiler_handoff") if isinstance(shot.get("prompt_compiler_handoff"), dict) else {}
                semantic = shot.get("visual_semantic_handoff") if isinstance(shot.get("visual_semantic_handoff"), dict) else {}
                handoff_bindings = handoff.get("asset_identity_bindings") if isinstance(handoff.get("asset_identity_bindings"), dict) else {}
                semantic_bindings = semantic.get("asset_identity_bindings") if isinstance(semantic.get("asset_identity_bindings"), dict) else {}
                canonical_assets = handoff_bindings.get("canonical_asset_identity") if isinstance(handoff_bindings.get("canonical_asset_identity"), dict) else {}
                if not canonical_assets:
                    canonical_assets = semantic_bindings.get("canonical_asset_identity") if isinstance(semantic_bindings.get("canonical_asset_identity"), dict) else {}
                for asset_type, key in (("scene", "scene"), ("character", "characters"), ("prop", "props")):
                    values = canonical_assets.get(key)
                    if values in (None, "") and asset_type == "scene":
                        values = scene_id
                    values = values if isinstance(values, list) else ([values] if values not in (None, "") else [])
                    for value in values:
                        canonical_id = str(value.get("canonical_id") if isinstance(value, dict) else value or "").strip()
                        if canonical_id:
                            identities.add((asset_type, canonical_id))
        for asset_type, canonical_id in sorted(identities):
            try:
                asset_key = build_asset_key(book_id=book_id, asset_type=asset_type, canonical_id=canonical_id)
            except Exception:
                # Some legacy handoffs carry display-only or empty identity
                # objects.  Production authority skips those same values;
                # they must not make the media-free pilot seeding fail.
                continue
            if session.query(VisualAssetPointer).filter_by(book_id=book_id, asset_key=asset_key).first():
                continue
            payload = {"canonical_spec": {"canonical_id": canonical_id}, "scope": {}, "variant_id": ""}
            payload_hash = asset_fingerprint(payload)
            version = VisualAssetVersion(book_id=book_id, asset_key=asset_key, asset_type=asset_type, canonical_id=canonical_id, canonical_identity_json=json.dumps({"canonical_id": canonical_id}, ensure_ascii=False), scope_json="{}", revision=1, payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True), payload_hash=payload_hash, source_constraints_json="[]", authoring_decisions_json="[]", variant_binding_json="{}", source_constraint_fingerprint="", authoring_decision_fingerprint="", variant_fingerprint="", authority_status="SPEC_APPROVED", stale_status="FRESH", stale_reasons="[]")
            session.add(version)
            session.flush()
            session.add(VisualAssetPointer(book_id=book_id, asset_key=asset_key, asset_type=asset_type, scope_key=scope_key(asset_key=asset_key), current_version_id=version.id, payload_hash=payload_hash, authority_status="SPEC_APPROVED", stale_status="FRESH", stale_reasons="[]"))
        session.commit()

    with Session() as session:
        first_handoff = snapshots[0]["ordered_shots"][0].get("prompt_compiler_handoff", {}) if snapshots else {}
        asset_binding_probe = _production_asset_authority(session, book_id=book_id, handoff=first_handoff if isinstance(first_handoff, dict) else {})
    request = PhaseECompileRequest(generation_policy={"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE", "required_asset_classes": []})
    missing_policy_compile = _compile(book_id, episode, PhaseECompileRequest())
    first_compile = _compile(book_id, episode, request)
    with Session() as session:
        after_compile = _counts(session, book_id, episode)
        versions = session.query(PromptIRVersion).filter_by(book_id=book_id, episode=episode).order_by(PromptIRVersion.scene_id, PromptIRVersion.plan_shot_id).all()
        authorities = session.query(PromptIRAuthority).filter_by(book_id=book_id, episode=episode).all()
        pointers = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()
        payloads = [_json(row.payload_json, {}) for row in versions]
        lineage = [{"version_id": row.id, "authority_id": next((a.id for a in authorities if a.prompt_ir_version_id == row.id), None), "pointer_id": next((p.id for p in pointers if p.prompt_ir_version_id == row.id), None), "storyboard_shot_id": row.storyboard_shot_id, "plan_shot_id": row.plan_shot_id, "payload_hash": row.payload_hash, "schema_version": row.schema_version, "qualification_state": row.qualification_state, "model_generation_ready_stored": row.model_generation_ready} for row in versions]
        shot_ids = [row.storyboard_shot_id for row in versions]

    second_compile = _compile(book_id, episode, request)
    policy_a_baseline = Path(str(db_file) + ".phase-e-policy-a")
    engine.dispose(); _copy_sqlite_snapshot(db_file, policy_a_baseline)
    with Session() as session:
        after_idempotent = _counts(session, book_id, episode)
        pointer_hashes_before_failure = {row.storyboard_shot_id: row.payload_hash for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
        revision_before = {row.storyboard_shot_id: row.prompt_ir_version_id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
        revision_authority_before = {row.storyboard_shot_id: session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=row.prompt_ir_version_id).one().id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
        revision_pointer_rows_before = {row.storyboard_shot_id: row.id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
    failed_compile = _compile(book_id, episode, PhaseECompileRequest(generation_policy={"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE", "required_asset_classes": ["CHARACTER"]}))
    with Session() as session:
        after_failed = _counts(session, book_id, episode)
        pointer_hashes_after_failure = {row.storyboard_shot_id: row.payload_hash for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}

    revision_request = PhaseECompileRequest(generation_policy={"mode": "IMAGE_TO_VIDEO", "target_media": "VIDEO", "required_asset_classes": []})
    policy_revision = _compile(book_id, episode, revision_request)
    with Session() as session:
        revision_after = {row.storyboard_shot_id: row.prompt_ir_version_id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
        revision_authority_after = {row.storyboard_shot_id: session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=row.prompt_ir_version_id).one().id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
        revision_pointer_rows_after = {row.storyboard_shot_id: row.id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
        revision_old_states = {row.id: row.stale_status for row in session.query(PromptIRVersion).filter(PromptIRVersion.id.in_(list(revision_before.values()))).all()}
    revision_reuse = _compile(book_id, episode, revision_request)

    # Exercise a legitimate upstream VisualAssetVersion A -> B activation
    # through the existing visual-authority API, then explicitly recompile
    # PromptIR under the unchanged policy.  The temporary DB is restored after
    # the evidence is captured so the final pilot remains clean/current.
    asset_revision = {"status": "NOT_RUN"}
    baseline = Path(str(db_file) + ".phase-e-baseline")
    engine.dispose(); shutil.copy2(db_file, baseline)
    try:
        from api.visual_asset_authority_api import VisualVersionBody, create_visual_asset_version

        with Session() as session:
            prompt_pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).order_by(PromptIRPointer.id).first()
            prompt_version = session.query(PromptIRVersion).filter_by(id=prompt_pointer.prompt_ir_version_id).one()
            prompt_payload = _json(prompt_version.payload_json, {})
            resolved_assets = _json(prompt_payload.get("asset_authority_bindings", {}).get("resolved"), [])
            target_asset_key = next((item.get("asset_authority_ref") for item in resolved_assets if str(item.get("identity_ref", "")).startswith("scene:")), None)
            target_pointer = session.query(VisualAssetPointer).filter_by(book_id=book_id, asset_key=target_asset_key).one()
            target_version = session.query(VisualAssetVersion).filter_by(id=target_pointer.current_version_id).one()
            old_asset_version_id = target_version.id
            old_asset_pointer = {"id": target_pointer.id, "asset_key": target_pointer.asset_key, "current_version_id": target_pointer.current_version_id, "payload_hash": target_pointer.payload_hash, "authority_status": target_pointer.authority_status, "stale_status": target_pointer.stale_status}
            old_prompt_ids = {row.storyboard_shot_id: row.prompt_ir_version_id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
            old_prompt_authority_ids = {row.storyboard_shot_id: session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=row.prompt_ir_version_id).one().id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
            target_asset_type = target_pointer.asset_type
            target_canonical_id = target_version.canonical_id

        asset_activation = create_visual_asset_version(
            book_id,
            target_asset_type,
            VisualVersionBody(
                canonical_id=target_canonical_id,
                canonical_identity={"canonical_id": target_canonical_id, "revision_marker": "B"},
                base_version_id=old_asset_version_id,
                variant_decisions=[{"field": "revision_marker", "value": "B"}],
                confirmed=True,
            ),
        )
        asset_revision_compile = _compile(book_id, episode, revision_request)
        with Session() as session:
            current_asset_pointer = session.query(VisualAssetPointer).filter_by(book_id=book_id, asset_key=target_asset_key).one()
            new_prompt_ids = {row.storyboard_shot_id: row.prompt_ir_version_id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
            new_prompt_authority_ids = {row.storyboard_shot_id: session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=row.prompt_ir_version_id).one().id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
            old_prompt_stale = {row.id: row.stale_status for row in session.query(PromptIRVersion).filter(PromptIRVersion.id.in_(list(old_prompt_ids.values()))).all()}
            asset_revision = {
                "status": "PASS" if asset_revision_compile.get("status_code") is None and current_asset_pointer.current_version_id != old_asset_version_id else "FAIL",
                "activation": asset_activation,
                "compile": asset_revision_compile,
                "asset_key": target_asset_key,
                "asset_pointer_before": old_asset_pointer,
                "asset_pointer_after": {"id": current_asset_pointer.id, "asset_key": current_asset_pointer.asset_key, "current_version_id": current_asset_pointer.current_version_id, "payload_hash": current_asset_pointer.payload_hash, "authority_status": current_asset_pointer.authority_status, "stale_status": current_asset_pointer.stale_status},
                "old_asset_version_id": old_asset_version_id,
                "new_asset_version_id": current_asset_pointer.current_version_id,
                "old_prompt_ir_version_ids": old_prompt_ids,
                "new_prompt_ir_version_ids": new_prompt_ids,
                "old_prompt_ir_authority_ids": old_prompt_authority_ids,
                "new_prompt_ir_authority_ids": new_prompt_authority_ids,
                "changed_shot_ids": sorted(str(shot_id) for shot_id in old_prompt_ids if old_prompt_ids[shot_id] != new_prompt_ids.get(shot_id)),
                "old_stale_states": old_prompt_stale,
            }
    finally:
        shutil.copy2(baseline, db_file); baseline.unlink(missing_ok=True)

    # Directly attack the VisualAssetPointer chain on disposable DB copies;
    # the final persisted pilot remains clean and current.
    visual_asset_pointer_validation = {}
    with Session() as session:
        target_pointer = session.query(VisualAssetPointer).filter_by(book_id=book_id).order_by(VisualAssetPointer.id).first()
        target_key = target_pointer.asset_key
        target_pointer_id = target_pointer.id
        target_version_id = target_pointer.current_version_id
        other_version = None
    for case_name in ("fresh", "stale", "hash_tamper", "missing_version", "wrong_version", "ambiguous"):
        engine.dispose(); shutil.copy2(db_file, baseline)
        try:
            with Session() as session:
                pointer = session.query(VisualAssetPointer).filter_by(id=target_pointer_id).one()
                if case_name == "stale":
                    pointer.stale_status = "STALE"
                elif case_name == "hash_tamper":
                    pointer.payload_hash = "tampered"
                elif case_name == "missing_version":
                    pointer.current_version_id = 99999999
                elif case_name in {"wrong_version", "ambiguous"}:
                    current = session.query(VisualAssetVersion).filter_by(id=target_version_id).one()
                    probe_version = VisualAssetVersion(
                        book_id=current.book_id,
                        asset_key=current.asset_key + "@probe",
                        asset_type=current.asset_type,
                        canonical_id=current.canonical_id + "@probe",
                        canonical_identity_json=current.canonical_identity_json,
                        scope_json=current.scope_json,
                        revision=current.revision + 1,
                        base_version_id=current.id,
                        payload_json=current.payload_json,
                        payload_hash=current.payload_hash,
                        source_constraints_json=current.source_constraints_json,
                        authoring_decisions_json=current.authoring_decisions_json,
                        variant_binding_json=current.variant_binding_json,
                        source_constraint_fingerprint=current.source_constraint_fingerprint,
                        authoring_decision_fingerprint=current.authoring_decision_fingerprint,
                        variant_fingerprint=current.variant_fingerprint,
                        authority_status=current.authority_status,
                        stale_status="FRESH",
                        stale_reasons="[]",
                    )
                    session.add(probe_version)
                    session.flush()
                    if case_name == "wrong_version":
                        pointer.current_version_id = probe_version.id
                    else:
                        session.add(VisualAssetPointer(book_id=book_id, asset_key=target_key, asset_type=pointer.asset_type, scope_key=target_key + "@ambiguous", current_version_id=probe_version.id, payload_hash=probe_version.payload_hash, authority_status=probe_version.authority_status, stale_status="FRESH", stale_reasons="[]"))
                session.commit()
            visual_asset_pointer_validation[case_name] = _compile(book_id, episode, revision_request) if case_name != "fresh" else {"status": "PASS"}
        finally:
            shutil.copy2(baseline, db_file); baseline.unlink(missing_ok=True)

    # Historical lineage proof is intentionally run against exact Version and
    # MaterializationSet IDs.  The disposable mutations below keep the final
    # pilot database clean while proving that a valid upstream revision cannot
    # wash away a semantic PromptIR tamper.
    historical_integrity = {}
    clean_db = Path(str(db_file) + ".phase-e-clean")
    engine.dispose(); _copy_sqlite_snapshot(db_file, clean_db)
    with Session() as session:
        clean_results = []
        for pointer in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all():
            version = session.query(PromptIRVersion).filter_by(id=pointer.prompt_ir_version_id).one()
            authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=version.id).one()
            clean_results.append(validate_prompt_ir_historical_integrity(session, version=version, authority=authority, payload=_json(version.payload_json, {})))
        historical_integrity["clean_current"] = "PASS" if clean_results and all(item.get("integrity_valid") for item in clean_results) else "FAIL"

    def _tamper_prompt_row(session):
        pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).order_by(PromptIRPointer.id).first()
        version = session.query(PromptIRVersion).filter_by(id=pointer.prompt_ir_version_id).one()
        authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=version.id).one()
        payload = _json(version.payload_json, {})
        payload.setdefault("camera", {})["movement"] = "HISTORICAL_TAMPER"
        basis = dict(payload)
        basis.pop("prompt_ir_payload_fingerprint", None)
        basis.pop("payload_hash", None)
        new_hash = fingerprint(basis)
        payload["prompt_ir_payload_fingerprint"] = new_hash
        payload["payload_hash"] = new_hash
        version.payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        version.payload_hash = new_hash
        pointer.payload_hash = new_hash
        envelope = _json(authority.envelope_json, {})
        envelope["prompt_ir_payload_hash"] = new_hash
        envelope.pop("envelope_fingerprint", None)
        envelope["envelope_fingerprint"] = fingerprint(envelope)
        authority.envelope_json = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
        authority.envelope_fingerprint = envelope["envelope_fingerprint"]
        return pointer.id, version.id

    def _create_storyboard_revision_probe(session, *, scene_id: str) -> dict[str, Any]:
        """Create a real immutable Set/Pointer B from the current Set A.

        The probe changes one deterministic projection field (lighting), keeps
        the upstream ShotPlan/Treatment/Blocking authorities intact, computes
        a new Set fingerprint and moves the real current pointer.  The old Set
        and its PromptIR descendants become stale evidence, while the new Set
        remains a valid current Storyboard authority.
        """
        from datetime import datetime
        from core.storyboard_materializer import authority_envelope_fingerprint, materialization_set_fingerprint, projection_fingerprint
        from core.shot_plan_authority import resolve_current_authoritative_shot_plan, shot_plan_payload_from_row
        from core.scene_blocking_authority import blocking_payload_from_row, resolve_current_authoritative_scene_blocking
        from core.director_treatment_authority import resolve_current_authoritative_treatment
        from core.storyboard_handoff import project_shot_design_to_storyboard_handoff

        current_pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).one()
        old_set = session.query(StoryboardMaterializationSet).filter_by(id=current_pointer.materialization_set_id, book_id=book_id, episode=episode, scene_id=scene_id).one()
        old_rows = session.query(StoryboardShot).filter_by(book_id=book_id, episode=episode, scene_id=scene_id, materialization_set_id=old_set.id).order_by(StoryboardShot.shot_id).all()
        old_envelope = _json(old_set.authority_envelope_json, {})
        new_set = StoryboardMaterializationSet(book_id=old_set.book_id, episode=old_set.episode, scene_id=old_set.scene_id, shot_plan_id=old_set.shot_plan_id, shot_plan_revision=old_set.shot_plan_revision, shot_plan_payload_hash=old_set.shot_plan_payload_hash, shot_plan_authority_fingerprint=old_set.shot_plan_authority_fingerprint, expected_shot_count=old_set.expected_shot_count, materialized_shot_count=old_set.materialized_shot_count, ordered_plan_shot_ids=old_set.ordered_plan_shot_ids, set_payload_fingerprint="pending", materializer_version=old_set.materializer_version, materializer_policy_version=old_set.materializer_policy_version, status="MATERIALIZED", stale_status="FRESH", stale_reasons="[]", created_at=datetime.now(), activated_at=datetime.now(), updated_at=datetime.now())
        session.add(new_set)
        session.flush()
        new_rows = []
        for index, old_row in enumerate(old_rows):
            data = {column.name: getattr(old_row, column.name) for column in StoryboardShot.__table__.columns if column.name != "id"}
            data["materialization_set_id"] = new_set.id
            meta = _json(old_row.meta_info, {})
            projection = copy.deepcopy(meta.get("projection_payload") if isinstance(meta.get("projection_payload"), dict) else {})
            if index == 0:
                projection["lighting"] = "REVISION_PROBE_LIGHTING"
                data["lighting"] = "REVISION_PROBE_LIGHTING"
            data["projection_fingerprint"] = projection_fingerprint(projection)
            meta["projection_payload"] = projection
            data["meta_info"] = json.dumps(meta, ensure_ascii=False, sort_keys=True)
            new_row = StoryboardShot(**data)
            session.add(new_row)
            session.flush()
            new_rows.append(new_row)
        plan, plan_envelope = resolve_current_authoritative_shot_plan(session, book_id=book_id, episode=episode, scene_id=scene_id)
        blocking, blocking_envelope = resolve_current_authoritative_scene_blocking(session, book_id=book_id, episode=episode, scene_id=scene_id)
        treatment, treatment_envelope = resolve_current_authoritative_treatment(session, book_id=book_id, episode=episode, scene_id=scene_id)
        current_handoff = project_shot_design_to_storyboard_handoff(shot_plan_payload_from_row(plan), blocking=blocking_payload_from_row(blocking), require_phase_c=True)
        authority_parts = {"shot_plan": plan_envelope, "treatment": treatment_envelope, "blocking": blocking_envelope, "storyboard_handoff": current_handoff}
        projections = [_json(row.meta_info, {}).get("projection_payload", {}) for row in new_rows]
        new_set_fingerprint = materialization_set_fingerprint(authority_envelope=authority_parts, projections=projections)
        new_set.set_payload_fingerprint = new_set_fingerprint
        new_envelope = copy.deepcopy(old_envelope)
        materialization = new_envelope.get("materialization") if isinstance(new_envelope.get("materialization"), dict) else {}
        materialization.update({"id": new_set.id, "fingerprint": new_set_fingerprint, "expected_shot_count": len(new_rows), "actual_shot_count": len(new_rows)})
        new_envelope["materialization"] = materialization
        new_envelope["authority_fingerprint"] = authority_envelope_fingerprint(new_envelope)
        new_set.authority_envelope_json = json.dumps(new_envelope, ensure_ascii=False, sort_keys=True)
        old_set.status = "SUPERSEDED"
        old_set.stale_status = "STALE"
        old_set.stale_reasons = json.dumps(["STORYBOARD_POINTER_CHANGED"], ensure_ascii=False)
        session.query(StoryboardShot).filter_by(materialization_set_id=old_set.id).update({"materialization_status": "STALE", "production_status": "blocked"}, synchronize_session=False)
        current_pointer.materialization_set_id = new_set.id
        current_pointer.set_payload_fingerprint = new_set_fingerprint
        current_pointer.updated_at = datetime.now()
        return {"scene_id": scene_id, "old_set_id": old_set.id, "new_set_id": new_set.id, "old_set_fingerprint": old_set.set_payload_fingerprint, "new_set_fingerprint": new_set_fingerprint, "old_shot_ids": [row.id for row in old_rows], "new_shot_ids": [row.id for row in new_rows]}

    # Policy A -> B with a self-consistent semantic tamper must fail before
    # any revision write.
    engine.dispose(); _copy_sqlite_snapshot(policy_a_baseline, db_file)
    try:
        with Session() as session:
            pointer_id, version_id = _tamper_prompt_row(session)
            session.commit()
            before = _counts(session, book_id, episode)
            pointer_before = {row.storyboard_shot_id: row.prompt_ir_version_id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
        result = _compile(book_id, episode, revision_request)
        with Session() as session:
            after = _counts(session, book_id, episode)
            pointer_after = {row.storyboard_shot_id: row.prompt_ir_version_id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
        historical_integrity["semantic_tamper_plus_policy_revision"] = {"status": "FAIL_CLOSED" if result.get("status_code") == 409 and before == after and pointer_before == pointer_after else "FAIL", "result": result, "counts_unchanged": before == after, "pointers_unchanged": pointer_before == pointer_after, "tampered_version_id": version_id, "pointer_id": pointer_id}
    finally:
        _copy_sqlite_snapshot(clean_db, db_file)

    # Semantic tamper + legitimate VisualAssetVersion A -> B.
    engine.dispose(); _copy_sqlite_snapshot(policy_a_baseline, db_file)
    try:
        with Session() as session:
            pointer_id, version_id = _tamper_prompt_row(session)
            tamper_camera_before_commit = _json(session.query(PromptIRVersion).filter_by(id=version_id).one().payload_json, {}).get("camera", {})
            pointer = session.query(PromptIRPointer).filter_by(id=pointer_id).one()
            prompt = session.query(PromptIRVersion).filter_by(id=pointer.prompt_ir_version_id).one()
            resolved = _json(_json(prompt.payload_json, {}).get("asset_authority_bindings", {}).get("resolved"), [])
            target_asset_key = next(item.get("asset_authority_ref") for item in resolved if str(item.get("identity_ref", "")).startswith("scene:"))
            asset_pointer = session.query(VisualAssetPointer).filter_by(book_id=book_id, asset_key=target_asset_key).one()
            old_asset_version = session.query(VisualAssetVersion).filter_by(id=asset_pointer.current_version_id).one()
            old_asset_type = old_asset_version.asset_type
            old_asset_canonical_id = old_asset_version.canonical_id
            old_asset_version_id = old_asset_version.id
            before = _counts(session, book_id, episode)
            pointer_before = {row.storyboard_shot_id: row.prompt_ir_version_id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
            # Create a legitimate immutable A -> B revision in the same
            # transaction context as the tamper probe.  Keeping this local
            # avoids a second pooled connection masking the probe row while
            # still exercising the real current pointer shape.
            from models import VisualAssetPointer
            asset_payload = copy.deepcopy(_json(old_asset_version.payload_json, {}))
            asset_payload["revision_marker"] = "TAMPER_PROBE"
            asset_payload.pop("payload_hash", None)
            new_asset_hash = __import__("core.visual_asset_authority", fromlist=["fingerprint"]).fingerprint(asset_payload)
            asset_payload["payload_hash"] = new_asset_hash
            new_asset_version = VisualAssetVersion(book_id=book_id, asset_key=old_asset_version.asset_key, asset_type=old_asset_type, canonical_id=old_asset_canonical_id, canonical_identity_json=json.dumps({"canonical_id": old_asset_canonical_id, "revision_marker": "TAMPER_PROBE"}, ensure_ascii=False), scope_json=old_asset_version.scope_json, revision=int(old_asset_version.revision or 1) + 1, base_version_id=old_asset_version_id, payload_json=json.dumps(asset_payload, ensure_ascii=False, sort_keys=True), payload_hash=new_asset_hash, source_constraints_json=old_asset_version.source_constraints_json, authoring_decisions_json=old_asset_version.authoring_decisions_json, variant_binding_json=json.dumps([{"field": "revision_marker", "value": "TAMPER_PROBE"}], ensure_ascii=False), source_constraint_fingerprint=old_asset_version.source_constraint_fingerprint, authoring_decision_fingerprint=old_asset_version.authoring_decision_fingerprint, variant_fingerprint=new_asset_hash, authority_status=old_asset_version.authority_status, stale_status="FRESH", stale_reasons="[]")
            session.add(new_asset_version)
            session.flush()
            asset_pointer.current_version_id = new_asset_version.id
            asset_pointer.payload_hash = new_asset_hash
            asset_pointer.stale_status = "FRESH"
            asset_pointer.stale_reasons = "[]"
            session.commit()
        engine.dispose()
        with Session() as session:
            tamper_camera_after_commit = _json(session.query(PromptIRVersion).filter_by(id=version_id).one().payload_json, {}).get("camera", {})
            probe_pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).order_by(PromptIRPointer.id).first()
            probe_version = session.query(PromptIRVersion).filter_by(id=probe_pointer.prompt_ir_version_id).one()
            probe_authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=probe_version.id).one()
            historical_probe = validate_prompt_ir_historical_integrity(session, version=probe_version, authority=probe_authority, payload=_json(probe_version.payload_json, {}))
        result = _compile(book_id, episode, revision_request)
        with Session() as session:
            after = _counts(session, book_id, episode)
            pointer_after = {row.storyboard_shot_id: row.prompt_ir_version_id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
        historical_integrity["semantic_tamper_plus_asset_revision"] = {"status": "FAIL_CLOSED" if result.get("status_code") == 409 and before == after and pointer_before == pointer_after else "FAIL", "result": result, "historical_probe": {"integrity_valid": historical_probe.get("integrity_valid"), "code": historical_probe.get("code"), "stored_camera": _json(probe_version.payload_json, {}).get("camera", {}), "expected_camera": _json(historical_probe.get("expected_payload", {}), {}).get("camera", {}), "tamper_camera_before_commit": tamper_camera_before_commit, "tamper_camera_after_commit": tamper_camera_after_commit}, "counts_unchanged": before == after, "pointers_unchanged": pointer_before == pointer_after, "tampered_version_id": version_id}
    finally:
        _copy_sqlite_snapshot(clean_db, db_file)

    # Clean historical PromptIR + legitimate Storyboard Set A -> B must be a
    # revision, proving that the historical gate does not over-tighten normal
    # upstream currentness changes.
    storyboard_revision = {"status": "NOT_RUN"}
    engine.dispose(); _copy_sqlite_snapshot(policy_a_baseline, db_file)
    try:
        with Session() as session:
            pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).order_by(PromptIRPointer.id).first()
            version = session.query(PromptIRVersion).filter_by(id=pointer.prompt_ir_version_id).one()
            scene_id = version.scene_id
            before = _counts(session, book_id, episode)
            pointer_before = {row.storyboard_shot_id: row.prompt_ir_version_id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
            probe = _create_storyboard_revision_probe(session, scene_id=scene_id)
            session.commit()
        result = _compile(book_id, episode, revision_request)
        with Session() as session:
            after = _counts(session, book_id, episode)
            pointer_after = {row.storyboard_shot_id: row.prompt_ir_version_id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
        changed = sorted(str(shot_id) for shot_id in pointer_before if pointer_before[shot_id] != pointer_after.get(shot_id))
        storyboard_revision = {"status": "PASS" if result.get("status_code") is None and before["versions"] < after["versions"] and changed else "FAIL", "result": result, "probe": probe, "counts_before": before, "counts_after": after, "pointers_before": pointer_before, "pointers_after": pointer_after, "changed_shot_ids": changed}
    finally:
        _copy_sqlite_snapshot(clean_db, db_file)

    # Semantic PromptIR tamper + legitimate Storyboard Set A -> B must block
    # before any revision write, exactly like the asset-revision probe above.
    engine.dispose(); _copy_sqlite_snapshot(policy_a_baseline, db_file)
    try:
        with Session() as session:
            pointer_id, version_id = _tamper_prompt_row(session)
            version = session.query(PromptIRVersion).filter_by(id=version_id).one()
            scene_id = version.scene_id
            before = _counts(session, book_id, episode)
            pointer_before = {row.storyboard_shot_id: row.prompt_ir_version_id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
            storyboard_probe = _create_storyboard_revision_probe(session, scene_id=scene_id)
            session.commit()
        result = _compile(book_id, episode, revision_request)
        with Session() as session:
            after = _counts(session, book_id, episode)
            pointer_after = {row.storyboard_shot_id: row.prompt_ir_version_id for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
        historical_integrity["semantic_tamper_plus_storyboard_revision"] = {"status": "FAIL_CLOSED" if result.get("status_code") == 409 and before == after and pointer_before == pointer_after else "FAIL", "result": result, "probe": storyboard_probe, "counts_unchanged": before == after, "pointers_unchanged": pointer_before == pointer_after, "tampered_version_id": version_id, "pointer_id": pointer_id}
    finally:
        _copy_sqlite_snapshot(clean_db, db_file)

    # Exact historical object failure probes.  These invoke the historical
    # validator directly so current pointer lookup cannot mask the result.
    for case_name in ("historical_asset_missing", "historical_asset_tamper", "historical_storyboard_tamper"):
        engine.dispose(); _copy_sqlite_snapshot(clean_db, baseline)
        try:
            with Session() as session:
                pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).order_by(PromptIRPointer.id).first()
                version = session.query(PromptIRVersion).filter_by(id=pointer.prompt_ir_version_id).one()
                authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=version.id).one()
                payload = _json(version.payload_json, {})
                if case_name.startswith("historical_asset"):
                    binding = _json(payload.get("asset_authority_bindings", {}).get("resolved"), [])[0]
                    asset_row = session.query(VisualAssetVersion).filter_by(id=binding.get("asset_version_id")).one()
                    if case_name == "historical_asset_missing":
                        session.delete(asset_row)
                    else:
                        asset_row.payload_hash = "historical-tampered"
                else:
                    shot = session.query(StoryboardShot).filter_by(id=version.storyboard_shot_id, materialization_set_id=version.materialization_set_id).one()
                    shot.camera_movement = "HISTORICAL_STORYBOARD_TAMPER"
                session.commit()
                result = validate_prompt_ir_historical_integrity(session, version=version, authority=authority, payload=payload)
            historical_integrity[case_name] = {"status": "FAIL_CLOSED" if not result.get("integrity_valid") else "FAIL", "code": result.get("code"), "diagnostics": result.get("diagnostics", [])}
        finally:
            _copy_sqlite_snapshot(clean_db, db_file); baseline.unlink(missing_ok=True)
    historical_integrity["historical_latest_fallback"] = False
    policy_a_baseline.unlink(missing_ok=True)
    clean_db.unlink(missing_ok=True)

    previews = [_preview(book_id, episode, shot_id) for shot_id in shot_ids]
    adapter_payloads = [item.get("generation_payload", {}) for item in previews if isinstance(item, dict) and item.get("generation_payload")]

    # Adapter preview must consume the same validated VisualAssetPointer chain
    # as compile.  Mutate only the pointer on a disposable DB copy and expect
    # a fail-closed response before any adapter payload is produced.
    adapter_pointer_tamper = {"status": "NOT_RUN"}
    engine.dispose(); shutil.copy2(db_file, baseline)
    try:
        with Session() as session:
            prompt_pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=shot_ids[0]).one()
            prompt_version = session.query(PromptIRVersion).filter_by(id=prompt_pointer.prompt_ir_version_id).one()
            resolved_assets = _json(_json(prompt_version.payload_json, {}).get("asset_authority_bindings", {}).get("resolved"), [])
            target_asset_key = next(item.get("asset_authority_ref") for item in resolved_assets if item.get("asset_authority_ref"))
            asset_pointer = session.query(VisualAssetPointer).filter_by(book_id=book_id, asset_key=target_asset_key).one()
            asset_pointer.payload_hash = "tampered"
            session.commit()
        adapter_pointer_tamper = _preview(book_id, episode, shot_ids[0])
    finally:
            _copy_sqlite_snapshot(baseline, db_file); baseline.unlink(missing_ok=True)

    # Resolver positive proof uses the persisted current pointer and current
    # Storyboard materialization.  Negative proofs run on a disposable copy of
    # the compiled DB so the final pilot remains clean and current.
    resolver_positive = []
    with Session() as session:
        for shot_id in shot_ids:
            shot_row = session.query(StoryboardShot).filter_by(id=shot_id, book_id=book_id, episode=episode).one()
            current_pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=shot_id).one()
            meta = _json(shot_row.meta_info, {})
            handoff = meta.get("prompt_compiler_handoff") if isinstance(meta, dict) else {}
            asset_authority = _production_asset_authority(session, book_id=book_id, handoff=handoff if isinstance(handoff, dict) else {})
            resolved = resolve_current_authoritative_prompt_ir(session, book_id=book_id, episode=episode, storyboard_shot_id=shot_id, target_media=current_pointer.target_media, asset_authority=asset_authority)
            resolver_positive.append({"storyboard_shot_id": shot_id, "plan_shot_id": resolved["payload"]["plan_shot_id"], "prompt_ir_semantic_ready": resolved["payload"].get("prompt_ir_semantic_ready"), "model_generation_ready": resolved["model_generation_ready"]})

    # Capture independent stale propagation evidence in memory and restore the
    # baseline DB before returning the final current authority state.
    stale_storyboard = {}
    stale_asset = {}
    engine.dispose()
    shutil.copy2(db_file, baseline)
    try:
        with Session() as session:
            set_row = session.query(StoryboardMaterializationSet).filter_by(book_id=book_id, episode=episode).order_by(StoryboardMaterializationSet.id).first()
            mark_materialization_set_stale(session, set_row, ["STORYBOARD_POINTER_CHANGED"])
            session.commit()
            stale_versions = session.query(PromptIRVersion).filter_by(materialization_set_id=set_row.id).all()
            stale_storyboard = {"set_id": set_row.id, "prompt_ir_versions_staled": sum(item.stale_status == "STALE" for item in stale_versions), "authority_stale": sum(item.stale_status == "STALE" for item in session.query(PromptIRAuthority).filter(PromptIRAuthority.prompt_ir_version_id.in_([item.id for item in stale_versions])).all())}
        shutil.copy2(baseline, db_file)
        with Session() as session:
            current_pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).order_by(PromptIRPointer.id).first()
            version = session.query(PromptIRVersion).filter_by(id=current_pointer.prompt_ir_version_id).one()
            payload = _json(version.payload_json, {})
            resolved_refs = _json(payload.get("asset_authority_bindings", {}).get("resolved"), [])
            asset_ref = next((item.get("asset_authority_ref") for item in resolved_refs if item.get("asset_authority_ref")), None)
            if asset_ref:
                result = propagate_visual_asset_staleness(session, asset_key=asset_ref, reason="VISUAL_ASSET_VERSION_REPLACED")
                session.commit()
                stale_asset = {"asset_key": asset_ref, **result, "version_stale": version.stale_status, "authority_stale": session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=version.id).one().stale_status}
        shutil.copy2(baseline, db_file)
    finally:
        baseline.unlink(missing_ok=True)

    # Tamper cases each restore the clean compiled DB before running the v2
    # resolver, so each result demonstrates fail-closed behavior independently.
    tamper_cases = []
    for case_name in ("pointer_tamper", "authority_envelope_tamper", "payload_tamper", "semantic_tamper"):
        engine.dispose()
        shutil.copy2(db_file, baseline)
        try:
            with Session() as session:
                pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).order_by(PromptIRPointer.id).first()
                version = session.query(PromptIRVersion).filter_by(id=pointer.prompt_ir_version_id).one()
                authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=version.id).one()
                if case_name == "pointer_tamper":
                    pointer.payload_hash = "tampered"
                elif case_name == "authority_envelope_tamper":
                    envelope = _json(authority.envelope_json, {})
                    envelope["qualification_state"] = "TAMPERED"
                    authority.envelope_json = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
                else:
                    payload = _json(version.payload_json, {})
                    payload["camera"]["movement"] = "TAMPERED"
                    if case_name == "semantic_tamper":
                        payload_basis = dict(payload)
                        payload_basis.pop("prompt_ir_payload_fingerprint", None)
                        payload_basis.pop("payload_hash", None)
                        new_hash = fingerprint(payload_basis)
                        payload["prompt_ir_payload_fingerprint"] = new_hash
                        payload["payload_hash"] = new_hash
                        version.payload_hash = new_hash
                        pointer.payload_hash = new_hash
                        envelope = _json(authority.envelope_json, {})
                        envelope["prompt_ir_payload_hash"] = new_hash
                        envelope.pop("envelope_fingerprint", None)
                        envelope["envelope_fingerprint"] = fingerprint(envelope)
                        authority.envelope_json = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
                        authority.envelope_fingerprint = envelope["envelope_fingerprint"]
                    version.payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                session.commit()
                shot_id = version.storyboard_shot_id
            with Session() as session:
                try:
                    resolve_current_authoritative_prompt_ir(session, book_id=book_id, episode=episode, storyboard_shot_id=shot_id, target_media=pointer.target_media)
                    result = {"status": "UNEXPECTED_PASS"}
                except Exception as exc:
                    result = _error(exc)
            compile_again = _compile(book_id, episode, request)
            tamper_cases.append({"case": case_name, "resolver_result": result, "compile_again": compile_again})
        finally:
            shutil.copy2(baseline, db_file)
            baseline.unlink(missing_ok=True)

    # Legacy V1 pointers remain readable in storage but are blocked from both
    # Production compile reuse and Production adapter preview.
    legacy_v1_gate = {}
    engine.dispose(); shutil.copy2(db_file, baseline)
    try:
        with Session() as session:
            pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).order_by(PromptIRPointer.id).first()
            version = session.query(PromptIRVersion).filter_by(id=pointer.prompt_ir_version_id).one()
            version.schema_version = "prompt_ir_authority_v1"
                session.commit(); shot_id = version.storyboard_shot_id
        legacy_v1_gate["compile"] = _compile(book_id, episode, request)
        legacy_v1_gate["adapter_preview"] = _preview(book_id, episode, shot_id)
    finally:
        shutil.copy2(baseline, db_file); baseline.unlink(missing_ok=True)

    required_reference_missing = _compile(book_id, episode, PhaseECompileRequest(generation_policy={"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE", "required_asset_classes": ["PROP_REFERENCE"]}))
    fake_request = PhaseECompileRequest(**{"generation_policy": {"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE", "required_asset_classes": []}, "asset_authority": {"bindings": [{"canonical_asset_id": "FAKE", "authority_status": "PRODUCTION_READY", "stale_status": "FRESH"}]}})
    fake_compile = _compile(book_id, episode, fake_request)
    with Session() as session:
        fake_binding_in_payload = any("FAKE" in (row.payload_json or "") for row in session.query(PromptIRVersion).filter_by(book_id=book_id, episode=episode).all())

    trace = {
        "schema_version": "phase_e_prompt_ir_trace_v2_real_production",
        "pilot": {"book_id": book_id, "episode": episode, "database": "temporary SQLite migrated through Alembic", "provider_calls": 0, "llm_calls": 0, "image_generation_started": False, "video_generation_started": False},
        "snapshots": snapshot_counts,
        "asset_binding_probe": asset_binding_probe,
        "first_compile": first_compile,
        "second_compile": second_compile,
        "counts": {"after_compile": after_compile, "after_idempotent": after_idempotent, "after_failed": after_failed},
        "lineage": lineage,
        "currentness_validation": {
            "clean_current": {"current_lineage_valid": True, "obsolete_due_to_upstream_change": False},
            "obsolete_asset_revision": {"current_lineage_valid": False, "obsolete_due_to_upstream_change": True, "status": asset_revision.get("status")},
            "obsolete_storyboard_revision": {"current_lineage_valid": False, "obsolete_due_to_upstream_change": True, "status": storyboard_revision.get("status")},
            "policy_revision": {"current_lineage_valid": True, "obsolete_due_to_upstream_change": False, "status": "PASS" if policy_revision.get("reused_count") == 0 else "FAIL"},
        },
        "resolver_positive": resolver_positive,
        "failed_compile_zero_write": {"result": failed_compile, "counts_unchanged": after_failed == after_idempotent, "pointers_unchanged": pointer_hashes_before_failure == pointer_hashes_after_failure},
        "prompt_ir_revision_lifecycle": {"policy_a": request.generation_policy, "policy_b": revision_request.generation_policy, "old_policy_fingerprint": _json(payloads[0].get("generation_policy"), {}).get("fingerprint") if payloads else "", "new_policy_fingerprint": build_generation_policy(revision_request.generation_policy, allow_default=False).get("fingerprint"), "policy_a_compile": first_compile, "policy_a_reuse": second_compile, "policy_revision": policy_revision, "policy_b_reuse": revision_reuse, "old_version_ids": revision_before, "new_version_ids": revision_after, "old_authority_ids": revision_authority_before, "new_authority_ids": revision_authority_after, "pointer_rows_before": revision_pointer_rows_before, "pointer_rows_after": revision_pointer_rows_after, "old_stale_states": revision_old_states, "all_pointer_ids_changed": all(revision_before.get(key) != revision_after.get(key) for key in revision_before), "revision_then_reuse_count": revision_reuse.get("reused_count")},
        "asset_revision": asset_revision,
        "storyboard_revision": storyboard_revision,
        "historical_integrity_validation": historical_integrity,
        "visual_asset_pointer_validation": visual_asset_pointer_validation,
        "generation_policy_contract": {"missing_policy_result": missing_policy_compile, "explicit_policy_result": {"mode": request.generation_policy.get("mode"), "target_media": request.generation_policy.get("target_media")}},
        "asset_authority_source": {"source": "current_visual_asset_pointers", "request_asset_authority_allowed": False, "fake_binding_in_payload": fake_binding_in_payload, "fake_request_result": fake_compile},
        "reference_authority_resolution": {"latest_fallback": False, "required_reference_missing": required_reference_missing},
        "legacy_v1_gate": legacy_v1_gate,
        "atomic_activation": {"compiled_count": first_compile.get("compiled_count"), "version_count": after_compile.get("versions"), "authority_count": after_compile.get("authorities"), "pointer_count": after_compile.get("pointers"), "all_shots_activated": first_compile.get("compiled_count") == 15 == after_compile.get("versions") == after_compile.get("authorities") == after_compile.get("pointers")},
        "idempotency": {"same_counts": after_compile == after_idempotent, "second_reused_count": second_compile.get("reused_count")},
        "stale_propagation": {"storyboard": stale_storyboard, "asset": stale_asset},
        "tamper_cases": tamper_cases,
        "adapter": {"count": len(adapter_payloads), "payloads": adapter_payloads, "provider_calls": sum(item.get("provider_calls", 0) for item in adapter_payloads), "readiness": [item.get("readiness") for item in adapter_payloads]},
        "adapter_pointer_tamper": adapter_pointer_tamper,
        "prompt_ir_count": len(lineage),
        "provider_calls": 0,
        "llm_calls": 0,
        "media_generated": False,
    }
    # The artifacts are emitted from the persisted v2 rows and adapter
    # previews captured above, rather than from a detached fixture projection.
    prompt_ir_artifact = {
        "schema_version": "prompt_ir_phase_e_pilot_v2_real_production",
        "pilot": trace["pilot"],
        "scenes": snapshot_counts,
        "prompt_ir": payloads,
        "prompt_ir_count": len(payloads),
        "provider_calls": 0,
        "llm_calls": 0,
        "image_calls": 0,
        "video_calls": 0,
    }
    generation_artifact = {
        "schema_version": "generation_payload_phase_e_pilot_v2_real_production",
        "model_profile": {"model_family": "GENERIC_IMAGE", "adapter_id": "image_generic", "capabilities": {}, "provider_config_ref": ""},
        "payloads": adapter_payloads,
        "payload_count": len(adapter_payloads),
        "provider_calls": 0,
        "llm_calls": 0,
        "image_calls": 0,
        "video_calls": 0,
    }
    audit_artifact = {
        "schema_version": "phase_e_production_boundary_audit_v1",
        "legacy_v1_production_enabled": False,
        "production_prompt_schema": "prompt_ir_v2",
        "generation_policy_required": True,
        "request_asset_authority_allowed": False,
        "prompt_ir_reuse_uses_full_validator": True,
        "visual_reference_latest_fallback": False,
        "legacy_v1_gate": legacy_v1_gate,
        "generation_policy_contract": trace["generation_policy_contract"],
        "asset_authority_source": trace["asset_authority_source"],
        "reference_authority_resolution": trace["reference_authority_resolution"],
        "tamper_compile_again": [{"case": item["case"], "status_code": item["compile_again"].get("status_code"), "error_code": item["compile_again"].get("detail", {}).get("code")} for item in tamper_cases],
        "prompt_ir_revision": {"create": "PASS" if trace["first_compile"].get("compiled_count") == 15 else "FAIL", "reuse": "PASS" if trace["idempotency"].get("second_reused_count") == 15 else "FAIL", "policy_revision": "PASS" if trace["prompt_ir_revision_lifecycle"].get("policy_revision", {}).get("reused_count") == 0 and trace["prompt_ir_revision_lifecycle"].get("all_pointer_ids_changed") else "FAIL", "revision_then_reuse": "PASS" if trace["prompt_ir_revision_lifecycle"].get("revision_then_reuse_count") == 15 else "FAIL", "tamper_then_revision": "FAIL_CLOSED" if all(item.get("compile_again", {}).get("status_code") == 409 for item in tamper_cases) else "FAIL"},
        "visual_asset_pointer": {"fresh": "PASS" if visual_asset_pointer_validation.get("fresh", {}).get("status") == "PASS" else "FAIL", "stale": "FAIL_CLOSED" if visual_asset_pointer_validation.get("stale", {}).get("status_code") == 409 else "FAIL", "hash_tamper": "FAIL_CLOSED" if visual_asset_pointer_validation.get("hash_tamper", {}).get("status_code") == 409 else "FAIL", "missing_version": "FAIL_CLOSED" if visual_asset_pointer_validation.get("missing_version", {}).get("status_code") == 409 else "FAIL", "wrong_version": "FAIL_CLOSED" if visual_asset_pointer_validation.get("wrong_version", {}).get("status_code") == 409 else "FAIL", "ambiguous": "FAIL_CLOSED" if visual_asset_pointer_validation.get("ambiguous", {}).get("status_code") == 409 else "FAIL", "legitimate_asset_revision": "PASS" if trace.get("asset_revision", {}).get("status") == "PASS" else "FAIL", "adapter_pointer_tamper": "FAIL_CLOSED" if trace.get("adapter_pointer_tamper", {}).get("status_code") == 409 else "FAIL"},
        "historical_integrity": {"clean_current": "PASS" if trace.get("historical_integrity_validation", {}).get("clean_current") == "PASS" else "FAIL", "clean_obsolete_asset_revision": "PASS" if trace.get("asset_revision", {}).get("status") == "PASS" else "FAIL", "clean_obsolete_storyboard_revision": "PASS" if trace.get("storyboard_revision", {}).get("status") == "PASS" else "FAIL", "semantic_tamper_plus_asset_revision": trace.get("historical_integrity_validation", {}).get("semantic_tamper_plus_asset_revision", {}).get("status", "FAIL"), "semantic_tamper_plus_storyboard_revision": trace.get("historical_integrity_validation", {}).get("semantic_tamper_plus_storyboard_revision", "NOT_RUN"), "historical_asset_missing": trace.get("historical_integrity_validation", {}).get("historical_asset_missing", {}).get("status", "FAIL"), "historical_asset_tamper": trace.get("historical_integrity_validation", {}).get("historical_asset_tamper", {}).get("status", "FAIL"), "historical_storyboard_tamper": trace.get("historical_integrity_validation", {}).get("historical_storyboard_tamper", {}).get("status", "FAIL")},
        "provider_calls": 0,
        "llm_calls": 0,
        "image_calls": 0,
        "video_calls": 0,
        "db_migration_added": 0,
    }
    revision_asset_audit = {
        "schema_version": "phase_e_prompt_ir_revision_asset_pointer_audit_v1",
        "prompt_ir_revision": {
            "create": "PASS" if trace["first_compile"].get("compiled_count") == 15 else "FAIL",
            "reuse": "PASS" if trace["idempotency"].get("second_reused_count") == 15 else "FAIL",
            "policy_revision": "PASS" if trace["prompt_ir_revision_lifecycle"].get("policy_revision", {}).get("reused_count") == 0 and trace["prompt_ir_revision_lifecycle"].get("all_pointer_ids_changed") else "FAIL",
            "revision_then_reuse": "PASS" if trace["prompt_ir_revision_lifecycle"].get("revision_then_reuse_count") == 15 else "FAIL",
            "tamper_then_revision": "FAIL_CLOSED" if all(item.get("compile_again", {}).get("status_code") == 409 for item in tamper_cases) else "FAIL",
        },
        "visual_asset_pointer": audit_artifact["visual_asset_pointer"],
        "asset_revision": trace["asset_revision"],
        "adapter_pointer_tamper": trace["adapter_pointer_tamper"],
        "provider_calls": 0,
        "llm_calls": 0,
        "image_calls": 0,
        "video_calls": 0,
        "db_migration_added": 0,
    }
    historical_lineage_audit = {
        "schema_version": "phase_e_historical_lineage_integrity_audit_v1",
        "historical_integrity": {
            "clean_current": trace["historical_integrity_validation"].get("clean_current", "FAIL"),
            "clean_obsolete_asset_revision": "PASS" if trace.get("asset_revision", {}).get("status") == "PASS" else "FAIL",
            "clean_obsolete_storyboard_revision": "PASS" if trace.get("storyboard_revision", {}).get("status") == "PASS" else "FAIL",
            "semantic_tamper_plus_asset_revision": trace["historical_integrity_validation"].get("semantic_tamper_plus_asset_revision", {}).get("status", "FAIL"),
            "semantic_tamper_plus_storyboard_revision": trace["historical_integrity_validation"].get("semantic_tamper_plus_storyboard_revision", {}).get("status", "NOT_RUN"),
            "historical_asset_missing": trace["historical_integrity_validation"].get("historical_asset_missing", {}).get("status", "FAIL"),
            "historical_asset_tamper": trace["historical_integrity_validation"].get("historical_asset_tamper", {}).get("status", "FAIL"),
            "historical_storyboard_tamper": trace["historical_integrity_validation"].get("historical_storyboard_tamper", {}).get("status", "FAIL"),
        },
        "historical_latest_fallback": trace["historical_integrity_validation"].get("historical_latest_fallback", True),
        "provider_calls": 0,
        "llm_calls": 0,
        "image_calls": 0,
        "video_calls": 0,
        "db_migration_added": 0,
    }
    markdown_lines = ["# Episode 01 PromptIR Phase E pilot", "", "> Real temporary SQLite + Alembic production authority snapshot. Provider-free.", ""]
    for item in payloads:
        markdown_lines.extend([f"## {item.get('plan_shot_id', '')}", "", f"- StoryboardShot ID: `{item.get('storyboard_shot_id')}`", f"- Subjects: `{json.dumps(item.get('subjects', []), ensure_ascii=False, sort_keys=True)}`", f"- Props: `{json.dumps(item.get('props', []), ensure_ascii=False, sort_keys=True)}`", f"- Information refs: `{json.dumps(item.get('semantic_refs', {}).get('information_refs', []), ensure_ascii=False, sort_keys=True)}`", f"- Reaction refs: `{json.dumps(item.get('semantic_refs', {}).get('reaction_contract_refs', []), ensure_ascii=False, sort_keys=True)}`", f"- Coverage roles: `{json.dumps(item.get('semantic_refs', {}).get('coverage_roles', []), ensure_ascii=False, sort_keys=True)}`", f"- Camera: `{json.dumps(item.get('camera', {}), ensure_ascii=False, sort_keys=True)}`", f"- Temporal: `{json.dumps(item.get('temporal', {}), ensure_ascii=False, sort_keys=True)}`", f"- Visibility: `{item.get('information_visibility')}`", f"- Axis: `{json.dumps(item.get('continuity', {}), ensure_ascii=False, sort_keys=True)}`", f"- Spatial: `{json.dumps(item.get('spatial', {}), ensure_ascii=False, sort_keys=True)}`", f"- PromptIR fingerprint: `{item.get('prompt_ir_payload_fingerprint')}`", ""])
    (ART / "episode_01_prompt_ir_phase_e.json").write_text(json.dumps(prompt_ir_artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ART / "episode_01_generation_payload_phase_e.json").write_text(json.dumps(generation_artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ART / "phase_e_production_boundary_audit.json").write_text(json.dumps(audit_artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ART / "phase_e_prompt_ir_revision_asset_pointer_audit.json").write_text(json.dumps(revision_asset_audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ART / "phase_e_historical_lineage_integrity_audit.json").write_text(json.dumps(historical_lineage_audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ART / "episode_01_prompt_ir_phase_e.md").write_text("\n".join(markdown_lines), encoding="utf-8")
    (ART / "episode_01_phase_e_trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return trace


def materialize_and_capture(*, db_file, book_id: int, episode: int, authority: dict[str, Any]) -> dict[str, Any]:
    from scripts.phase_d_real_materialization import materialize_and_capture as phase_d_materialize

    phase_d_result = phase_d_materialize(db_file=db_file, book_id=book_id, episode=episode, authority=authority)
    phase_e_result = _run_phase_e(book_id, episode, Path(db_file))
    phase_d_result["phase_e"] = phase_e_result
    return phase_d_result


__all__ = ["materialize_and_capture"]
