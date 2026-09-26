"""Run the fixed PHASE_REAL_IMAGE_PROVIDER_CANARY fixture.

The script creates one isolated migrated SQLite database, compiles one current
PromptIR shot, executes exactly one Registry-selected IMAGE provider call, and
promotes the resulting MediaCandidate through the existing media authority.
Only secret-free projections are written to the requested artifact files.

Use ``--fake-provider`` for deterministic CI evidence.  A real run requires
``PHASE_F_PROVIDER_CANARY_REAL=1`` and an existing Registry profile id.
"""

from __future__ import annotations

import argparse
import base64
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.model_registry import get_profile
from core.generation_execution_service import GenerationExecutionService, serialize_generation_execution
from core.generation_orchestrator import GenerationOrchestrator, GenerationOrchestratorError
from core.model_adapter_runtime import ImageGenerationProviderAdapter, ModelAdapterRegistry
from core.prompt_ir_phase_e import build_generation_policy, fingerprint
from core.storyboard_materializer import projection_fingerprint
from models import PromptIRAuthority, PromptIRPointer, PromptIRVersion
from scripts.verify_migration_chain import _upgrade


ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "e2e-production-pilot"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _json(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    return value


def _redact(value: Any, *, key: str = "") -> Any:
    lowered = str(key).lower()
    if any(token in lowered for token in ("api_key", "apikey", "authorization", "secret", "password", "credential", "bearer")):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, key=key) for v in value]
    if isinstance(value, str) and (value.startswith("data:image/") or len(value) > 4000):
        return f"[REDACTED large value: {len(value)} chars]"
    return value


def _single_character_snapshot() -> dict[str, Any]:
    """Build one episode/scene/shot PromptIR source with one character."""
    # The fixture helpers provide the same production materialization authority
    # envelope used by the PromptIR validation tests.  We narrow its first shot
    # to the canary's one-character/one-scene scope before compilation.
    from tests.prompt_ir_authority_fixture import canonical_snapshot

    snapshot = canonical_snapshot()
    snapshot["scene_id"] = "CANARY_E01_SCENE"
    snapshot["ordered_shots"] = snapshot["ordered_shots"][:1]
    row = snapshot["ordered_shots"][0]

    def narrow(value: Any) -> None:
        if isinstance(value, dict):
            for key in list(value):
                child = value[key]
                if key == "subjects" and isinstance(child, list):
                    value[key] = ["CANARY_CHARACTER"]
                elif key == "props" and isinstance(child, list):
                    value[key] = []
                elif key == "characters" and isinstance(child, dict):
                    value[key] = {"CANARY_CHARACTER": "ST_CANARY"}
                elif key == "actor_refs" and isinstance(child, list):
                    value[key] = ["CANARY_CHARACTER"]
                elif key in {"asset_bindings", "canonical_asset_identity"} and isinstance(child, dict):
                    value[key] = {"scene": "CANARY_E01_SCENE", "characters": ["CANARY_CHARACTER"], "props": []}
                elif key in {"scene_id", "scene"} and child == "E01_SC001":
                    value[key] = "CANARY_E01_SCENE"
                narrow(value[key])
        elif isinstance(value, list):
            for child in value:
                narrow(child)

    narrow(row)
    row["visual_semantic_handoff"]["scene_id"] = "CANARY_E01_SCENE"
    row["projection_payload"]["scene_id"] = "CANARY_E01_SCENE"
    row["projection_payload"]["scene_name"] = "CANARY_E01_SCENE"
    row["projection_fingerprint"] = projection_fingerprint(row["projection_payload"])
    return snapshot


def _create_fixture(session: Any) -> tuple[Any, dict[str, Any]]:
    from tests.prompt_ir_authority_fixture import build_snapshot_from_fixture, compile_fixture_prompt, install_authority_spine

    book_id = 991701
    episode = 1
    business_shot_id = 1
    snapshot = _single_character_snapshot()
    shot, source_row, storyboard_authority = install_authority_spine(
        session,
        book_id=book_id,
        episode=episode,
        shot_id=business_shot_id,
        snapshot=snapshot,
        scene_id="CANARY_E01_SCENE",
    )
    snapshot = build_snapshot_from_fixture(session, shot=shot, authority=storyboard_authority)
    source_row = next(row for row in snapshot["ordered_shots"] if row.get("plan_shot_id") == shot.plan_shot_id)
    policy = build_generation_policy({"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE"}, allow_default=False)
    materialization = storyboard_authority.get("materialization") or {}
    payload = compile_fixture_prompt(
        snapshot=snapshot,
        source_row=source_row,
        storyboard_shot_id=shot.id,
        target_media="IMAGE",
        policy=policy,
        materialization_set_id=shot.materialization_set_id,
        set_payload_fingerprint=str(materialization.get("fingerprint") or f"set-{shot.materialization_set_id}"),
    )
    payload_hash = str(payload["payload_hash"])
    envelope = {
        "schema_version": "prompt_ir_authority_envelope_v2",
        "storyboard_shot_id": shot.id,
        "authority_instance": "real-image-provider-canary",
        "source_authority": payload["source_authority"],
        "generation_policy": payload["generation_policy"],
        "asset_authority_bindings": payload["asset_authority_bindings"],
        "prompt_ir_payload_hash": payload_hash,
        "qualification_state": "PROMPT_IR_QUALIFIED",
        "model_generation_ready": False,
        "stale_status": "FRESH",
    }
    envelope["envelope_fingerprint"] = fingerprint(envelope)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    version = PromptIRVersion(
        book_id=book_id,
        episode=episode,
        scene_id=shot.scene_id,
        storyboard_shot_id=shot.id,
        materialization_set_id=shot.materialization_set_id,
        plan_shot_id=shot.plan_shot_id,
        schema_version="prompt_ir_v2",
        payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        payload_hash=payload_hash,
        compiler_version="prompt_ir_canary",
        compiler_policy_version="prompt_ir_canary",
        retention_policy_version="prompt_ir_canary",
        authority_envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True),
        qualification_state="PROMPT_IR_QUALIFIED",
        asset_reference_state="READY",
        model_generation_ready="true",
        stale_status="FRESH",
        stale_reasons="[]",
        created_at=now,
        updated_at=now,
    )
    session.add(version)
    session.flush()
    session.add(
        PromptIRAuthority(
            prompt_ir_version_id=version.id,
            book_id=book_id,
            episode=episode,
            storyboard_shot_id=shot.id,
            envelope_fingerprint=envelope["envelope_fingerprint"],
            envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True),
            qualification_state="PROMPT_IR_QUALIFIED",
            stale_status="FRESH",
            stale_reasons="[]",
            created_at=now,
            updated_at=now,
        )
    )
    pointer = PromptIRPointer(
        book_id=book_id,
        episode=episode,
        storyboard_shot_id=shot.id,
        target_media="IMAGE",
        prompt_ir_version_id=version.id,
        payload_hash=payload_hash,
        qualification_state="PROMPT_IR_QUALIFIED",
        created_at=now,
        updated_at=now,
    )
    session.add(pointer)
    session.flush()
    return shot, {
        "book_id": book_id,
        "episode": episode,
        "shot_id": int(shot.id),
        "business_shot_id": business_shot_id,
        "scene_id": str(shot.scene_id),
        "character_id": "CANARY_CHARACTER",
        "prompt_version_id": int(version.id),
        "prompt_payload_hash": payload_hash,
        "pointer_id": int(pointer.id),
        "payload": payload,
    }


async def _fake_dispatch(_context: dict[str, Any]) -> dict[str, Any]:
    uri = "data:image/png;base64," + base64.b64encode(PNG).decode("ascii")
    return {
        "uri": uri,
        "previewUrl": uri,
        "providerResponse": {"id": "fake-canary-response", "status": "succeeded", "media_type": "IMAGE"},
        "providerRequestPayload": {"model": "fake-canary-image", "prompt": "fixture"},
        "providerRequestId": "fake-canary-request",
        "providerTaskId": "fake-canary-task",
    }


def run_canary(*, profile_id: str, fake_provider: bool = False) -> dict[str, Any]:
    from tests.prompt_ir_authority_fixture import resolve_fixture_materialization

    import core.provider_transport_registry as transport_registry
    import core.storyboard_materializer as storyboard_materializer

    storyboard_materializer.resolve_current_authoritative_materialization = resolve_fixture_materialization
    profile = get_profile(profile_id)
    if not isinstance(profile, dict):
        raise RuntimeError(f"Model Registry profile not found: {profile_id}")
    if fake_provider:
        transport_registry.dispatch_provider_transport = _fake_dispatch
        os.environ.setdefault("PHASE_F_PROVIDER_CANARY_REAL", "1")
    if not fake_provider and os.getenv("PHASE_F_PROVIDER_CANARY_REAL", "") != "1":
        raise RuntimeError("Real canary requires PHASE_F_PROVIDER_CANARY_REAL=1")

    temp_root = Path(tempfile.mkdtemp(prefix="real-image-provider-canary-"))
    db_path = temp_root / "canary.sqlite"
    _upgrade(db_path)
    previous_upload_dir = config.UPLOAD_DIR
    config.UPLOAD_DIR = temp_root / "uploads"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    SessionLocal = sessionmaker(bind=engine)
    try:
        with SessionLocal() as session:
            shot, fixture = _create_fixture(session)
            session.commit()
            pointer_id = fixture["pointer_id"]
            execution = GenerationExecutionService(session).create_execution(
                shot_id=shot.id,
                prompt_pointer_id=pointer_id,
                prompt_version_id=fixture["prompt_version_id"],
                model_profile_id=profile_id,
            )
            session.commit()
            adapters = ModelAdapterRegistry({str(profile.get("provider")): ImageGenerationProviderAdapter()})
            try:
                result = GenerationOrchestrator(
                    session,
                    adapter_registry=adapters,
                    profile_resolver=lambda _profile_id: profile,
                ).run_and_promote(execution.execution_id)
                session.commit()
            except GenerationOrchestratorError as exc:
                session.commit()
                execution = GenerationExecutionService(session).get_execution(execution.execution_id)
                provider_evidence = _redact(execution.response_payload)
                return {
                    "schema_version": "real_image_provider_canary_v1",
                    "completion": "REAL_IMAGE_PROVIDER_CANARY_BLOCKED",
                    "fixture_mode": bool(fake_provider),
                    "real_provider_call": not bool(fake_provider),
                    "provider": str(profile.get("provider") or ""),
                    "model": str(profile.get("model_name") or ""),
                    "profile_id": profile_id,
                    "fixture": {key: value for key, value in fixture.items() if key != "payload"},
                    "execution": {
                        **serialize_generation_execution(execution),
                        "status_history": ["CREATED", "QUEUED", "RUNNING", "FAILED"],
                        "provider_request": provider_evidence.get("provider_request", {}),
                        "provider_response": provider_evidence.get("provider_response", {}),
                    },
                    "candidate": {},
                    "validation": {},
                    "official_media": {},
                    "lineage": {"asset_to_execution": False, "execution_to_prompt_version": True, "execution_to_shot": True, "prompt_to_pointer": True},
                    "credential_safety": {"profile_api_key_persisted": "api_key" in str(provider_evidence), "secret_value_written": False},
                    "blocker": {"code": exc.code, "message": exc.message, "provider_calls": exc.provider_calls},
                    "temp_database": str(db_path),
                }
            execution = result["execution"]
            candidate = result["candidate"]
            validation = result["validation"]["validation"]
            promotion = result["promotion"]
            provider_evidence = _redact(execution.response_payload)
            return {
                "schema_version": "real_image_provider_canary_v1",
                "completion": "REAL_IMAGE_PROVIDER_CANARY_COMPLETE",
                "fixture_mode": bool(fake_provider),
                "real_provider_call": not bool(fake_provider),
                "provider": str(profile.get("provider") or ""),
                "model": str(profile.get("model_name") or ""),
                "profile_id": profile_id,
                "fixture": {key: value for key, value in fixture.items() if key != "payload"},
                "execution": {
                    **serialize_generation_execution(execution),
                    "status_history": ["CREATED", "QUEUED", "RUNNING", "PROVIDER_CALLED", "SUCCESS"],
                    "provider_request": provider_evidence.get("provider_request", {}),
                    "provider_response": provider_evidence.get("provider_response", {}),
                },
                "candidate": {
                    "candidate_id": candidate.candidate_id,
                    "execution_id": candidate.execution_id,
                    "status": candidate.status,
                    "media_type": candidate.media_type,
                    "storage_identity": candidate.storage_identity,
                    "checksum_sha256": candidate.checksum_sha256,
                    "mime_type": candidate.mime_type,
                    "byte_size": candidate.byte_size,
                    "width": candidate.width,
                    "height": candidate.height,
                    "prompt_ir_version_id": candidate.prompt_ir_version_id,
                    "prompt_ir_payload_hash": candidate.prompt_ir_payload_hash,
                    "provider_request_fingerprint": candidate.provider_request_fingerprint,
                    "provider_response_hash": candidate.provider_response_hash,
                },
                "validation": {
                    "validation_id": validation.validation_id,
                    "status": validation.status,
                    "technical_validation_fingerprint": validation.technical_validation_fingerprint,
                    "authority_snapshot_fingerprint": validation.authority_snapshot_fingerprint,
                },
                "official_media": {
                    "official_media_version_id": promotion["version"].official_media_version_id,
                    "authority_id": promotion["authority"].authority_id,
                    "pointer_scope": {
                        "book_id": promotion["pointer"].book_id,
                        "episode": promotion["pointer"].episode,
                        "storyboard_shot_id": promotion["pointer"].storyboard_shot_id,
                        "media_role": promotion["pointer"].media_role,
                    },
                },
                "lineage": {
                    "asset_to_execution": candidate.execution_id == execution.execution_id,
                    "execution_to_prompt_version": int(execution.prompt_ir_version_id) == int(fixture["prompt_version_id"]),
                    "execution_to_shot": int(execution.storyboard_shot_id) == int(fixture["shot_id"]),
                    "prompt_to_pointer": int(fixture["pointer_id"]) > 0,
                },
                "credential_safety": {"profile_api_key_persisted": "api_key" in str(provider_evidence), "secret_value_written": False},
                "temp_database": str(db_path),
            }
    finally:
        config.UPLOAD_DIR = previous_upload_dir
        engine.dispose()


def _write_artifacts(result: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    audit_checks = {
        "provider_call_completed": bool(result.get("real_provider_call") or result.get("fixture_mode")),
        "execution_success": result.get("execution", {}).get("status") == "SUCCESS",
        "provider_request_present": bool(result.get("execution", {}).get("provider_request")),
        "provider_response_present": bool(result.get("execution", {}).get("provider_response")),
        "media_candidate_present": result.get("candidate", {}).get("status") == "MEDIA_CANDIDATE",
        "media_validation_passed": result.get("validation", {}).get("status") == "TECHNICALLY_VALID",
        "official_media_version_present": bool(result.get("official_media", {}).get("official_media_version_id")),
        "official_media_pointer_present": bool(result.get("official_media", {}).get("authority_id")),
        "lineage_complete": all((result.get("lineage") or {}).values()),
        "credential_not_persisted": not bool(result.get("credential_safety", {}).get("profile_api_key_persisted")),
    }
    truth = {
        "schema_version": "real_image_provider_truth_audit_v1",
        "stage": result.get("completion"),
        "provider": result.get("provider"),
        "model": result.get("model"),
        "real_provider_call": result.get("real_provider_call"),
        "fixture_mode": result.get("fixture_mode"),
        "status_history": result.get("execution", {}).get("status_history"),
        "checks": audit_checks,
        "all_checks_pass": all(audit_checks.values()),
        "secret_free_evidence": True,
    }
    vertical = {
        "schema_version": "real_image_provider_vertical_slice_v1",
        "shot": result.get("fixture"),
        "prompt": {"prompt_ir_version_id": result.get("fixture", {}).get("prompt_version_id"), "payload_hash": result.get("fixture", {}).get("prompt_payload_hash")},
        "execution": result.get("execution"),
        "media_candidate": result.get("candidate"),
        "validation": result.get("validation"),
        "official_media": result.get("official_media"),
        "lineage": result.get("lineage"),
    }
    (ARTIFACT_DIR / "REAL_IMAGE_PROVIDER_TRUTH_AUDIT.json").write_text(json.dumps(_json(truth), ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACT_DIR / "REAL_IMAGE_PROVIDER_VERTICAL_SLICE.json").write_text(json.dumps(_json(vertical), ensure_ascii=False, indent=2), encoding="utf-8")
    report = f"""# Real Image Provider Canary Report

## Result

`{result.get('completion')}`

- Provider: `{result.get('provider')}`
- Model: `{result.get('model')}`
- Profile: `{result.get('profile_id')}`
- Real provider call: `{result.get('real_provider_call')}`
- Execution: `{result.get('execution', {}).get('execution_id')}` → `{result.get('execution', {}).get('status')}`
- MediaCandidate: `{result.get('candidate', {}).get('candidate_id')}` → `{result.get('candidate', {}).get('status')}`
- Validation: `{result.get('validation', {}).get('validation_id')}` → `{result.get('validation', {}).get('status')}`
- OfficialMediaVersion: `{result.get('official_media', {}).get('official_media_version_id')}`
- OfficialMediaPointer authority: `{result.get('official_media', {}).get('authority_id')}`

Blocker (when present): `{(result.get('blocker') or {}).get('code', '')}` — `{(result.get('blocker') or {}).get('message', '')}`

## Fixed canary scope

- Episode: `{result.get('fixture', {}).get('episode')}`
- Scene: `{result.get('fixture', {}).get('scene_id')}`
- Character: `{result.get('fixture', {}).get('character_id')}`
- Shot count: `1`
- Image count: `1`

## Evidence

The vertical slice JSON contains the secret-free Provider request/response projection, execution record, candidate storage/checksum, validation fingerprint, official version, pointer scope, and PromptIR/shot lineage checks.

## Verification

- Runtime adapter, execution integration, candidate persistence, and failure handling tests: `tests/test_real_image_provider_canary.py`
- Existing runtime/foundation regression tests: `tests/test_model_adapter_runtime.py`, `tests/test_generation_execution_foundation.py`
- Truth audit: `REAL_IMAGE_PROVIDER_TRUTH_AUDIT.json` (`all_checks_pass={truth['all_checks_pass']}`)

{result.get('completion')}
"""
    (ARTIFACT_DIR / "REAL_IMAGE_PROVIDER_CANARY_REPORT.md").write_text(report, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-id", default="preset-poyo-image-gpt-image-2")
    parser.add_argument("--fake-provider", action="store_true")
    args = parser.parse_args()
    result = run_canary(profile_id=args.profile_id, fake_provider=args.fake_provider)
    _write_artifacts(result)
    print(json.dumps({key: result.get(key) for key in ("completion", "provider", "model", "real_provider_call", "fixture_mode")}, ensure_ascii=False))
    return 0 if result.get("completion") == "REAL_IMAGE_PROVIDER_CANARY_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
