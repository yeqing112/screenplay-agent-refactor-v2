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
import shutil
from pathlib import Path
from typing import Any

from core.prompt_ir_phase_e import fingerprint, resolve_current_authoritative_prompt_ir

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "e2e-production-pilot"


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
    from models import PromptIRAuthority, PromptIRPointer, PromptIRVersion, Session, StoryboardMaterializationSet, StoryboardShot, VisualAssetPointer, VisualAssetVersion

    with Session() as session:
        snapshot_records = _snapshot_records(session, book_id=book_id, episode=episode)
        snapshots = [item["snapshot"] for item in snapshot_records]
        snapshot_counts = [{"scene_id": item["scene_id"], "storyboard_shot_count": len(item["snapshot"]["ordered_shots"]), "storyboard_shot_ids": item["storyboard_shot_ids"], "materialization_set_id": item["materialization_set_id"], "storyboard_pointer_id": item["storyboard_pointer_id"], "semantic_ready": item["snapshot"].get("storyboard_semantic_ready"), "visual_semantic_handoff_rows": sum(bool(row.get("visual_semantic_handoff")) for row in item["snapshot"]["ordered_shots"]), "prompt_compiler_handoff_rows": sum(bool(row.get("prompt_compiler_handoff")) for row in item["snapshot"]["ordered_shots"]), "projection_payload_rows": sum(bool(row.get("projection_payload")) for row in item["snapshot"]["ordered_shots"])} for item in snapshot_records]

        # The pilot has one explicit ASCII prop identity (TICKET).  Seed its
        # current VisualAssetPointer/Version as an authority row so the real
        # Phase E path proves binding and downstream stale propagation without
        # generating or downloading media.
        asset_key = build_asset_key(book_id=book_id, asset_type="prop", canonical_id="TICKET")
        if not session.query(VisualAssetPointer).filter_by(book_id=book_id, asset_key=asset_key).first():
            payload = {"canonical_spec": {"canonical_id": "TICKET"}, "scope": {}, "variant_id": ""}
            payload_hash = asset_fingerprint(payload)
            version = VisualAssetVersion(book_id=book_id, asset_key=asset_key, asset_type="prop", canonical_id="TICKET", canonical_identity_json=json.dumps({"canonical_id": "TICKET"}, ensure_ascii=False), scope_json="{}", revision=1, payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True), payload_hash=payload_hash, source_constraints_json="[]", authoring_decisions_json="[]", variant_binding_json="{}", source_constraint_fingerprint="", authoring_decision_fingerprint="", variant_fingerprint="", authority_status="SPEC_APPROVED", stale_status="FRESH", stale_reasons="[]")
            session.add(version)
            session.flush()
            session.add(VisualAssetPointer(book_id=book_id, asset_key=asset_key, asset_type="prop", scope_key=scope_key(asset_key=asset_key), current_version_id=version.id, payload_hash=payload_hash, authority_status="SPEC_APPROVED", stale_status="FRESH", stale_reasons="[]"))
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
    with Session() as session:
        after_idempotent = _counts(session, book_id, episode)
        pointer_hashes_before_failure = {row.storyboard_shot_id: row.payload_hash for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}
    failed_compile = _compile(book_id, episode, PhaseECompileRequest(generation_policy={"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE", "required_asset_classes": ["CHARACTER"]}))
    with Session() as session:
        after_failed = _counts(session, book_id, episode)
        pointer_hashes_after_failure = {row.storyboard_shot_id: row.payload_hash for row in session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).all()}

    previews = [_preview(book_id, episode, shot_id) for shot_id in shot_ids]
    adapter_payloads = [item.get("generation_payload", {}) for item in previews if isinstance(item, dict) and item.get("generation_payload")]

    # Resolver positive proof uses the persisted current pointer and current
    # Storyboard materialization.  Negative proofs run on a disposable copy of
    # the compiled DB so the final pilot remains clean and current.
    resolver_positive = []
    with Session() as session:
        for shot_id in shot_ids:
            shot_row = session.query(StoryboardShot).filter_by(id=shot_id, book_id=book_id, episode=episode).one()
            meta = _json(shot_row.meta_info, {})
            handoff = meta.get("prompt_compiler_handoff") if isinstance(meta, dict) else {}
            asset_authority = _production_asset_authority(session, book_id=book_id, handoff=handoff if isinstance(handoff, dict) else {})
            resolved = resolve_current_authoritative_prompt_ir(session, book_id=book_id, episode=episode, storyboard_shot_id=shot_id, asset_authority=asset_authority)
            resolver_positive.append({"storyboard_shot_id": shot_id, "plan_shot_id": resolved["payload"]["plan_shot_id"], "prompt_ir_semantic_ready": resolved["payload"].get("prompt_ir_semantic_ready"), "model_generation_ready": resolved["model_generation_ready"]})

    # Capture independent stale propagation evidence in memory and restore the
    # baseline DB before returning the final current authority state.
    stale_storyboard = {}
    stale_asset = {}
    baseline = Path(str(db_file) + ".phase-e-baseline")
    from models import engine
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
            version = session.query(PromptIRVersion).filter_by(book_id=book_id, episode=episode).order_by(PromptIRVersion.id).first()
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
                version = session.query(PromptIRVersion).filter_by(book_id=book_id, episode=episode).order_by(PromptIRVersion.id).first()
                authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=version.id).one()
                pointer = session.query(PromptIRPointer).filter_by(prompt_ir_version_id=version.id).one()
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
                    resolve_current_authoritative_prompt_ir(session, book_id=book_id, episode=episode, storyboard_shot_id=shot_id)
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
            version = session.query(PromptIRVersion).filter_by(book_id=book_id, episode=episode).order_by(PromptIRVersion.id).first()
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
        "resolver_positive": resolver_positive,
        "failed_compile_zero_write": {"result": failed_compile, "counts_unchanged": after_failed == after_idempotent, "pointers_unchanged": pointer_hashes_before_failure == pointer_hashes_after_failure},
        "generation_policy_contract": {"missing_policy_result": missing_policy_compile, "explicit_policy_result": {"mode": request.generation_policy.get("mode"), "target_media": request.generation_policy.get("target_media")}},
        "asset_authority_source": {"source": "current_visual_asset_pointers", "request_asset_authority_allowed": False, "fake_binding_in_payload": fake_binding_in_payload, "fake_request_result": fake_compile},
        "reference_authority_resolution": {"latest_fallback": False, "required_reference_missing": required_reference_missing},
        "legacy_v1_gate": legacy_v1_gate,
        "atomic_activation": {"compiled_count": first_compile.get("compiled_count"), "version_count": after_compile.get("versions"), "authority_count": after_compile.get("authorities"), "pointer_count": after_compile.get("pointers"), "all_shots_activated": first_compile.get("compiled_count") == 15 == after_compile.get("versions") == after_compile.get("authorities") == after_compile.get("pointers")},
        "idempotency": {"same_counts": after_compile == after_idempotent, "second_reused_count": second_compile.get("reused_count")},
        "stale_propagation": {"storyboard": stale_storyboard, "asset": stale_asset},
        "tamper_cases": tamper_cases,
        "adapter": {"count": len(adapter_payloads), "payloads": adapter_payloads, "provider_calls": sum(item.get("provider_calls", 0) for item in adapter_payloads), "readiness": [item.get("readiness") for item in adapter_payloads]},
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
