"""Inspect and, only when already authoritative, materialize SC002_002 upstream.

The current repository run is intentionally provider-free.  This command stops
at the earliest missing authority and emits a complete, secret-free evidence
packet.  It does not create ShotPlan, StoryboardShot, PromptIR, or provider
records on a blocked path.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "video-compiler" / "v1-canonical-upstream-recovery"
SHOT_ID = "SH_E01_SC002_002"


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items() if str(k).lower() not in {"api_key", "authorization", "access_token", "secret", "runtime_credential_value"}}
    if isinstance(value, list):
        return [_safe(v) for v in value]
    return value


def _write(name: str, value: dict[str, Any]) -> None:
    (OUT / name).write_text(json.dumps(_safe(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _profile() -> dict[str, Any]:
    from api.model_registry import get_default_profile

    profile = get_default_profile("image") or {}
    return {"id": profile.get("id"), "provider": profile.get("provider"), "model": profile.get("model_name"), "adapter_id": profile.get("adapter_id"), "adapter_version": profile.get("adapter_version"), "transport_binding_id": profile.get("transport_binding_id"), "credential_configured": bool(profile.get("credential_configured"))}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    from core.sc002_002_upstream_recovery import inspect_script_ir_state, resolve_exact_canonical_identity
    from models import Session

    with Session() as session:
        identity = resolve_exact_canonical_identity(session, SHOT_ID)
        script_state = inspect_script_ir_state(session)
        resolved = identity.get("authoritative_match") if identity.get("status") == "EXACT_ONE" else None
        if resolved:
            materialization = {"status": "NOT_RUN", "reason": "RECOVERY_SCRIPT_REQUIRES_EXPLICIT_CANONICAL_MATERIALIZATION_REVIEW", "book_id": resolved["book_id"], "episode": resolved["episode"], "scene_id": resolved["scene_id"]}
        else:
            materialization = {"status": "NOT_APPLICABLE", "reason": "SC002_002_CANONICAL_IDENTITY_NOT_FOUND" if identity.get("status") == "ZERO" else "SC002_002_CANONICAL_IDENTITY_AMBIGUOUS"}

    identity_status = identity.get("status")
    if identity_status == "ZERO":
        final_status = "SC002_002_CANONICAL_IDENTITY_NOT_FOUND"
    elif identity_status == "AMBIGUOUS":
        final_status = "SC002_002_CANONICAL_IDENTITY_AMBIGUOUS"
    else:
        final_status = "SC002_002_UPSTREAM_RECOVERY_REQUIRES_REVIEW"

    common = {"schema_version": "sc002_002_canonical_upstream_recovery_v1", "run_id": run_id, "shot_id": SHOT_ID, "status": final_status, "real_image_calls": 0, "real_video_calls": 0, "external_llm_calls": 0}
    _write("SC002_002_IDENTITY_RESOLUTION.json", {**common, "identity": identity})
    _write("SC002_002_SCRIPT_IR_AUTHORITY.json", {**common, "script_ir": script_state, "scope": "UNSCOPED_UNTIL_IDENTITY_RESOLVED"})
    for filename, label in [
        ("SC002_002_TREATMENT_AUTHORITY.json", "DirectorTreatment"),
        ("SC002_002_SCENE_BLOCKING_AUTHORITY.json", "SceneBlocking"),
        ("SC002_002_SHOT_PLAN_AUTHORITY.json", "ShotPlan"),
    ]:
        _write(filename, {**common, "authority_type": label, "status": "NOT_RUN", "reason": final_status})
    _write("SC002_002_STORYBOARD_MATERIALIZATION.json", {**common, "materialization": materialization, "writes": 0})
    _write("SC002_002_STORYBOARD_SHOT_IDENTITY.json", {**common, "storyboard_shot_id": None, "materialization_set_id": None, "exact_match_count": 0})
    _write("SC002_002_IMAGE_PROMPT_IR_AUTHORITY.json", {**common, "status": "NOT_RUN", "target_media": "IMAGE", "prompt_ir_pointer_id": None, "prompt_ir_version_id": None, "payload_hash": None})
    _write("SC002_002_VISUAL_ASSET_AUTHORITY.json", {**common, "status": "NOT_RUN", "bindings": [], "reason": final_status})
    _write("SC002_002_IMAGE_PREFLIGHT.json", {**common, "status": "BLOCKED_BEFORE_POST", "model_profile": _profile(), "provider_image_post_count": 0, "provider_video_post_count": 0, "generation_request_fingerprint": None, "real_image_budget": 0, "real_video_budget": 0})
    report = f"""# SC002_002 Canonical Upstream Authority Recovery

Status: `{final_status}`
Run: `{run_id}`
Shot identity: `{SHOT_ID}`

The live canonical database was scanned by exact structured `ShotPlan.shots[*].plan_shot_id` equality. No historical document, filename, provider URL, or guessed Book scope was used. The scan found `{len(identity.get('matches') or [])}` exact ShotPlan payload match(es), `{len(identity.get('authoritative_matches') or [])}` current authoritative match(es), and stopped at the earliest identity gate.

Real IMAGE: `0`
Real VIDEO: `0`
IMAGE POST: `0`
VIDEO POST: `0`
External LLM: `0`
Materialization / PromptIR / production writes: `0`
Historical adoption: `0`

ScriptIR and FactSnapshot status are recorded from the live database in `SC002_002_SCRIPT_IR_AUTHORITY.json`; they are explicitly unscoped until the exact production identity resolves.
"""
    (OUT / "SC002_002_CANONICAL_UPSTREAM_RECOVERY_REPORT.md").write_text(report, encoding="utf-8")
    return 0 if identity_status == "EXACT_ONE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
