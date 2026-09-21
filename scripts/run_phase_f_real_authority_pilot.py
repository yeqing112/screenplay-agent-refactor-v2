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
            SceneBlocking, SceneBlockingAuthority, SceneBlockingPointer, ScriptIRVersion,
            ShotPlan, ShotPlanAuthority, ShotPlanPointer, StoryboardMaterializationPointer,
            StoryboardShot,
            Session,
        )

        before_models = (ScriptIRVersion, DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer, SceneBlocking, SceneBlockingAuthority, SceneBlockingPointer, ShotPlan, ShotPlanAuthority, ShotPlanPointer, StoryboardMaterializationPointer, StoryboardShot, PromptIRAuthority, PromptIRPointer)
        with Session() as session:
            pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode).order_by(PromptIRPointer.storyboard_shot_id).first()
            if pointer is None:
                raise RuntimeError("real Phase E pilot did not persist a PromptIR pointer")
            prompt_version = session.query(__import__("models", fromlist=["PromptIRVersion"]).PromptIRVersion).filter_by(id=pointer.prompt_ir_version_id).one()
            shot_id = int(pointer.storyboard_shot_id)
            before = {}
            for model in before_models:
                before[model.__tablename__] = session.query(model).filter_by(book_id=book_id, episode=episode).count() if hasattr(model, "book_id") else 0

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
            after = {}
            for model in before_models:
                after[model.__tablename__] = session.query(model).filter_by(book_id=book_id, episode=episode).count() if hasattr(model, "book_id") else 0
            execution = session.query(GenerationExecutionRecord).filter_by(execution_id=result["execution"]["execution_id"]).one()
            candidate = session.query(MediaCandidateRecord).filter_by(execution_id=execution.execution_id).one()
            trace = {
                "database": "REAL_SQLITE",
                "alembic_head": "y8h9i0j1k2l3",
                "book_id": book_id, "episode": episode, "shot_id": shot_id,
                "before_authorities": before,
                "prompt_ir": {"version_id": prompt_version.id, "authority_id": session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=prompt_version.id).one().id, "payload_hash": prompt_version.payload_hash},
                "generation_payload_fingerprint": execution.generation_payload_fingerprint,
                "provider_execution_profile_fingerprint": execution.model_profile_fingerprint,
                "provider_request_fingerprint": execution.provider_request_fingerprint,
                "execution": result["execution"],
                "candidate": {"candidate_id": candidate.candidate_id, "checksum": candidate.checksum_sha256, "width": candidate.width, "height": candidate.height, "storage_identity": candidate.storage_identity},
                "after_authorities": after,
                "authority_mutations": 0,
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
            (ART / "episode_01_phase_f_real_authority_fake_provider_trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result

    phase_e.materialize_and_capture = post_setup
    phase_b.main()
    return {"status": "ok"}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
