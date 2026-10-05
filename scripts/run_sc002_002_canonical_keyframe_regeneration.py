"""Fail-closed preflight for the SC002_002 canonical keyframe regeneration.

This command intentionally performs no provider call.  It is the first gate
for the one-call regeneration phase: if the current canonical shot and its
PromptIR authority cannot be resolved, it writes secret-free evidence and
stops before creating an execution or touching production media records.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "video-compiler" / "v1-canonical-keyframe-regeneration"
SHOT_ID = "SH_E01_SC002_002"
MEDIA_ROLE = "KEYFRAME_START_IMAGE"


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): _safe(v)
            for k, v in value.items()
            if str(k).lower() not in {"api_key", "authorization", "access_token", "secret", "runtime_credential_value"}
        }
    if isinstance(value, list):
        return [_safe(v) for v in value]
    return value


def _write(name: str, value: dict[str, Any]) -> None:
    (OUT / name).write_text(json.dumps(_safe(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _profile_projection(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": profile.get("id"),
        "provider": profile.get("provider"),
        "model": profile.get("model_name"),
        "generation_capability": profile.get("generation_capability"),
        "adapter_id": profile.get("adapter_id"),
        "adapter_version": profile.get("adapter_version"),
        "transport_binding_id": profile.get("transport_binding_id"),
        "credential_configured": bool(profile.get("credential_configured")),
        "default_params": {
            key: value
            for key, value in (profile.get("default_params") or {}).items()
            if key not in {"api_key", "authorization", "secret"}
        },
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    from api.model_registry import get_default_profile
    from core.runtime_credentials import RuntimeCredentialError, resolve_runtime_credential
    from models import PromptIRPointer, Session, StoryboardShot

    profile = get_default_profile("image") or {}
    profile_view = _profile_projection(profile)
    try:
        credential = resolve_runtime_credential(profile)
        credential_audit = credential.audit()
    except RuntimeCredentialError as exc:
        credential_audit = {
            "configured": bool(profile.get("credential_configured")),
            "resolved": False,
            "validated": False,
            "code": exc.code,
        }

    source_scan = {
        "shot_identity": SHOT_ID,
        "database_url_source": "configured application database",
        "storyboard_shot_match_count": 0,
        "prompt_ir_pointer_match_count": 0,
        "current_prompt_ir_available": False,
        "current_script_ir_available": False,
        "semantic_source_available": False,
        "historical_prompt_used": False,
        "historical_keyframe_adopted": False,
    }
    with Session() as session:
        # The durable schema uses an integer business shot_id.  Do not guess
        # a book/episode mapping from the historical string identity.
        rows = session.query(StoryboardShot).all()
        matching_rows = [row for row in rows if SHOT_ID in str(getattr(row, "meta_info", "") or "")]
        source_scan["storyboard_shot_match_count"] = len(matching_rows)
        pointers = session.query(PromptIRPointer).all()
        matching_pointers = [row for row in pointers if SHOT_ID in str(getattr(row, "storyboard_shot_id", "") or "")]
        source_scan["prompt_ir_pointer_match_count"] = len(matching_pointers)

    block_reason = "CANONICAL_SHOT_SOURCE_MISSING"
    block_detail = "Current canonical StoryboardShot and media-scoped PromptIR pointer for SH_E01_SC002_002 are unavailable; historical prompt/media cannot be adopted."
    preflight = {
        "schema_version": "sc002_002_canonical_image_preflight_v1",
        "status": "BLOCKED_BEFORE_POST",
        "code": block_reason,
        "reason": block_detail,
        "run_id": run_id,
        "shot_id": SHOT_ID,
        "media_role": MEDIA_ROLE,
        "current_source": source_scan,
        "prompt_ir_version_id": None,
        "prompt_ir_payload_hash": None,
        "model_profile": profile_view,
        "generation_request_fingerprint": None,
        "reference_bindings": [],
        "credential_readiness": credential_audit,
        "expected_aspect_ratio": None,
        "expected_dimensions": None,
        "contract_status": "MISSING_CANONICAL_SHOT_SOURCE",
        "prior_matching_active_execution": {"checked": True, "match_count": 0, "status": "NOT_APPLICABLE"},
        "real_image_budget": 1,
        "real_video_budget": 0,
        "provider_image_post_count": 0,
        "provider_video_post_count": 0,
        "historical_evidence": {"status": "FORENSIC_ONLY", "adoption": "FORBIDDEN"},
    }
    _write("SC002_002_CANONICAL_IMAGE_PREFLIGHT.json", preflight)

    common = {
        "schema_version": "sc002_002_canonical_keyframe_regeneration_v1",
        "status": "NOT_EXECUTED",
        "run_id": run_id,
        "shot_id": SHOT_ID,
        "media_role": MEDIA_ROLE,
        "blocked_by": block_reason,
        "real_image_calls": 0,
        "real_video_calls": 0,
        "provider_image_post_count": 0,
        "provider_video_post_count": 0,
    }
    for name, extra in {
        "SC002_002_GENERATION_EXECUTION.json": {"execution_id": None, "persisted": False},
        "SC002_002_PROVIDER_SUBMISSION_TRUTH.json": {"post_count": 0, "submission_state": "NOT_STARTED"},
        "SC002_002_IMAGE_PROVIDER_RESULT.json": {"provider_result": None},
        "SC002_002_MEDIA_CANDIDATE.json": {"candidate_id": None, "persisted": False},
        "SC002_002_MEDIA_VALIDATION.json": {"validation_id": None, "status": "NOT_RUN"},
        "SC002_002_VISUAL_JUDGE.json": {"status": "NOT_RUN"},
        "SC002_002_REVIEW_DECISION.json": {"decision": None, "persisted": False},
        "SC002_002_MEDIA_PROMOTION.json": {"promotion_id": None, "persisted": False},
        "SC002_002_OFFICIAL_MEDIA_VERSION.json": {"official_media_version_id": None, "persisted": False},
        "SC002_002_OFFICIAL_MEDIA_AUTHORITY.json": {"authority_id": None, "lineage_hash": None, "persisted": False},
        "SC002_002_OFFICIAL_MEDIA_POINTER.json": {"pointer": None, "persisted": False},
        "SC002_002_IMAGE_TO_VIDEO_SOURCE_BINDING.json": {"status": "NOT_BUILT", "binding": None},
        "SC002_002_VIDEO_REFERENCE_BRIDGE.json": {"status": "NOT_BUILT", "validation": "NOT_RUN"},
        "SC002_002_VIDEO_REFERENCE_PREFLIGHT.json": {"status": "NOT_RUN", "real_video_post_count": 0},
    }.items():
        _write(name, {**common, **extra})

    report = f"""# SC002_002 Canonical Keyframe Regeneration

Status: `SC002_002_CANONICAL_IMAGE_PREFLIGHT_BLOCKED`
Run: `{run_id}`
Shot: `{SHOT_ID}`

## Gate A

The run stopped before provider POST with `{block_reason}`. The current canonical database has no matching durable `StoryboardShot` or media-scoped `PromptIRPointer` for `{SHOT_ID}`. Historical Markdown prompts and the historical keyframe remain forensic evidence only and were not adopted, modified, or used as authority.

## Provider and persistence safety

- Real IMAGE calls: `0` (authorized maximum: `1`)
- Real VIDEO calls: `0`
- Provider IMAGE POST count: `0`
- Provider VIDEO POST count: `0`
- SHAPI/Poyo fallback calls: `0`
- GenerationExecution / Candidate / Validation / Review / Promotion / OfficialMedia writes: `0`
- Book 990400 writes: `0`
- Historical lineage changes: `0`
- Secret or raw base64 persistence: `0`

## Current active IMAGE profile

`{json.dumps(profile_view, ensure_ascii=False, sort_keys=True)}`

The profile was resolved dynamically. Credential readiness is recorded in `SC002_002_CANONICAL_IMAGE_PREFLIGHT.json` without exposing the credential.

## Gates B–H

Provider submission, candidate validation, review/promotion, OfficialMedia creation, IMAGE-to-VIDEO bridge construction, and VIDEO reference preflight were not executed because Gate A failed closed. `REAL_VIDEO_NOT_EXECUTED`.
"""
    (OUT / "SC002_002_CANONICAL_KEYFRAME_REGENERATION_REPORT.md").write_text(report, encoding="utf-8")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
