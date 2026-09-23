"""Run the real A–E -> Phase F pilot with a deterministic local provider.

The Phase B runner owns the real SQLite/Alembic authority chain.  This wrapper
adds only the permitted provider-boundary substitution and records a trace;
all Phase F resolution and candidate persistence remain production functions.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "e2e-production-pilot"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run() -> dict:
    os.environ["PHASE_E_REAL_PILOT"] = "1"
    os.environ["PHASE_F_RETAIN_DB"] = "1"
    def load(name: str, path: Path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module
    phase_e = load("phase_e_prompt_ir_real_pilot", ROOT / "scripts" / "phase_e_prompt_ir_real_pilot.py")
    phase_b = load("run_phase_b_director_blocking_pilot", ROOT / "scripts" / "run_phase_b_director_blocking_pilot.py")
    sys.modules["scripts.phase_e_prompt_ir_real_pilot"] = phase_e

    original_materialize = phase_e.materialize_and_capture

    def post_setup(*, db_file, book_id, episode, authority):
        result = original_materialize(db_file=db_file, book_id=book_id, episode=episode, authority=authority)
        import api.generation_canary_api as canary
        from models import (
            DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer,
            GenerationExecutionRecord, MediaCandidateRecord, PromptIRAuthority, PromptIRPointer,
            PromptIRVersion, VisualAssetPointer, VisualReferenceAuthority,
            SceneBlocking, SceneBlockingAuthority, SceneBlockingPointer, ScriptIRVersion,
            ShotPlan, ShotPlanAuthority, ShotPlanPointer, StoryboardMaterializationPointer,
            StoryboardShot,
            Session,
        )

        before_models = (ScriptIRVersion, DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer, SceneBlocking, SceneBlockingAuthority, SceneBlockingPointer, ShotPlan, ShotPlanAuthority, ShotPlanPointer, StoryboardMaterializationPointer, StoryboardShot, PromptIRAuthority, PromptIRPointer)

        def authority_snapshot(session):
            """Persist identities and hashes, rather than a null/count-only proof."""
            def records(model, *, scoped=True):
                query = session.query(model)
                if scoped and hasattr(model, "book_id"):
                    query = query.filter_by(book_id=book_id)
                    if hasattr(model, "episode"):
                        query = query.filter_by(episode=episode)
                return query.all()

            def project(model, fields, *, scoped=True):
                rows = records(model, scoped=scoped)
                return [
                    {field: getattr(row, field, None) for field in fields}
                    for row in sorted(rows, key=lambda item: int(getattr(item, "id", 0) or 0))
                ]

            return {
                "script_ir": project(ScriptIRVersion, ["id", "revision", "payload_hash", "status", "stale_status"]),
                "treatment": project(DirectorTreatment, ["id", "revision", "payload_hash", "qualification_state", "stale_status"]),
                "treatment_authority": project(DirectorTreatmentAuthority, ["id", "treatment_id", "treatment_revision", "payload_hash", "envelope_fingerprint", "stale_status"]),
                "treatment_pointer": project(DirectorTreatmentPointer, ["id", "treatment_id", "treatment_revision", "authority_envelope_fingerprint"]),
                "blocking": project(SceneBlocking, ["id", "revision", "payload_hash", "qualification_state", "stale_status"]),
                "blocking_authority": project(SceneBlockingAuthority, ["id", "blocking_id", "blocking_revision", "payload_hash", "envelope_fingerprint", "stale_status"]),
                "blocking_pointer": project(SceneBlockingPointer, ["id", "blocking_id", "blocking_revision", "authority_envelope_fingerprint"]),
                "shot_plan": project(ShotPlan, ["id", "revision", "payload_hash", "qualification_state", "stale_status"]),
                "shot_plan_authority": project(ShotPlanAuthority, ["id", "shot_plan_id", "plan_revision", "payload_hash", "envelope_fingerprint", "stale_status"]),
                "shot_plan_pointer": project(ShotPlanPointer, ["id", "shot_plan_id", "plan_revision", "authority_envelope_fingerprint"]),
                "storyboard_materialization_pointer": project(StoryboardMaterializationPointer, ["id", "materialization_set_id", "shot_plan_id", "set_payload_fingerprint"]),
                "storyboard_shot": project(StoryboardShot, ["id", "shot_id", "plan_shot_id", "projection_fingerprint", "materialization_status"]),
                "prompt_ir": project(PromptIRVersion, ["id", "storyboard_shot_id", "plan_shot_id", "payload_hash", "stale_status"]),
                "prompt_ir_authority": project(PromptIRAuthority, ["id", "prompt_ir_version_id", "envelope_fingerprint", "stale_status"], scoped=False),
                "prompt_ir_pointer": project(PromptIRPointer, ["id", "storyboard_shot_id", "target_media", "prompt_ir_version_id", "payload_hash"]),
                "visual_asset_pointer": project(VisualAssetPointer, ["id", "asset_key", "current_version_id", "payload_hash", "stale_status"], scoped=False),
                "reference_authority": project(VisualReferenceAuthority, ["id", "asset_key", "asset_version_id", "authority_fingerprint", "checksum", "stale_status"], scoped=False),
            }

        def phase_f_record_counts(session):
            return {
                "generation_execution_records": session.query(GenerationExecutionRecord).count(),
                "media_candidate_records": session.query(MediaCandidateRecord).count(),
            }

        with Session() as session:
            # Phase F remains an IMAGE canary, so derive its exact scope
            # explicitly rather than relying on the legacy shot-only pointer.
            pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode, target_media="IMAGE").order_by(PromptIRPointer.storyboard_shot_id).first()
            if pointer is None:
                raise RuntimeError("real Phase E pilot did not persist a PromptIR pointer")
            prompt_version = session.query(PromptIRVersion).filter_by(id=pointer.prompt_ir_version_id).one()
            shot_id = int(pointer.storyboard_shot_id)
            before = {
                "counts": {model.__tablename__: session.query(model).filter_by(book_id=book_id, episode=episode).count() if hasattr(model, "episode") else session.query(model).filter_by(book_id=book_id).count() if hasattr(model, "book_id") else session.query(model).count() for model in before_models},
                "identities": authority_snapshot(session),
            }
            phase_f_before = phase_f_record_counts(session)

        calls = []
        async def fake_provider(*, context):
            calls.append(1)
            return await canary._fake_provider_image(request_snapshot=context["request_snapshot"], provider_request_fingerprint=context["provider_request_fingerprint"])

        old_provider = canary._call_provider
        canary._call_provider = fake_provider
        try:
            request = canary.CanaryPreviewRequest(adapter_id="image_generic", model_profile_id="builtin-mock-image")
            preview = canary.preview_generation_canary(book_id, episode, shot_id, request)
            execute = canary.CanaryExecuteRequest(execute=True, confirmation_token=preview["confirmation_token"], preview_execution_id=preview["execution"]["execution_id"])
            result = asyncio.run(canary.execute_generation_canary(book_id, episode, shot_id, execute))
        finally:
            canary._call_provider = old_provider

        with Session() as session:
            after = {
                "counts": {model.__tablename__: session.query(model).filter_by(book_id=book_id, episode=episode).count() if hasattr(model, "episode") else session.query(model).filter_by(book_id=book_id).count() if hasattr(model, "book_id") else session.query(model).count() for model in before_models},
                "identities": authority_snapshot(session),
            }
            phase_f_after = phase_f_record_counts(session)
            execution = session.query(GenerationExecutionRecord).filter_by(execution_id=result["execution"]["execution_id"]).one()
            candidate = session.query(MediaCandidateRecord).filter_by(execution_id=execution.execution_id).one()
            storyboard_row = session.query(__import__("models", fromlist=["StoryboardShot"]).StoryboardShot).filter_by(id=execution.storyboard_shot_id).one()
            trace = {
                "database": "REAL_SQLITE",
                "database_mode": "REAL_SQLITE",
                "alembic_head": "b2c3d4e5f6g7",
                "book_id": book_id, "episode": episode, "shot_id": shot_id,
                "shot": {"storyboard_shot_id": storyboard_row.id, "business_shot_id": storyboard_row.shot_id, "plan_shot_id": storyboard_row.plan_shot_id, "scene_id": storyboard_row.scene_id},
                "before_authorities": before,
                "prompt_ir": {"version_id": prompt_version.id, "authority_id": session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=prompt_version.id).one().id, "payload_hash": prompt_version.payload_hash},
                "generation_payload_fingerprint": execution.generation_payload_fingerprint,
                "provider_execution_profile_fingerprint": execution.model_profile_fingerprint,
                "provider_request_fingerprint": execution.provider_request_fingerprint,
                "execution": result["execution"],
                "candidate": {"candidate_id": candidate.candidate_id, "checksum": candidate.checksum_sha256, "width": candidate.width, "height": candidate.height, "storage_identity": candidate.storage_identity},
                "after_authorities": after,
                "phase_f_records_before": phase_f_before,
                "phase_f_records_after": phase_f_after,
                "authority_mutations": 0,
                "provider_calls": len(calls),
                "fake_provider_calls": len(calls),
                "external_provider_calls": 0,
                "real_persisted_prompt_ir": True,
                "resolver_monkeypatched": False,
                "asset_resolver_monkeypatched": False,
                "storyboard_resolver_monkeypatched": False,
                "phase_f_evidence_class": "Real Authority Integration with Fake Provider",
            }
            if before != after:
                raise AssertionError("Phase F mutated an upstream authority table")
            if phase_f_before != {"generation_execution_records": 0, "media_candidate_records": 0} or phase_f_after != {"generation_execution_records": 1, "media_candidate_records": 1}:
                raise AssertionError("Phase F persisted an unexpected record count")
            (ART / "episode_01_phase_f_real_authority_fake_provider_trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result

    phase_e.materialize_and_capture = post_setup
    phase_b.main()
    return {"status": "ok"}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
