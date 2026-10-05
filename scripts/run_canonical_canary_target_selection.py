"""Provider-free canonical canary identity scan and deterministic target selection."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "docs" / "canonical-canary" / "v1-target-selection"
BENCHMARK_IDS = ["SH_E01_SC002_002", "SH_E01_SC002_006", "SH_E01_SC002_007"]


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _safe(item)
            for key, item in value.items()
            if str(key).lower() not in {"api_key", "authorization", "access_token", "secret", "runtime_credential_value", "raw_base64"}
        }
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _write(name: str, value: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(_safe(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _profile(capability: str) -> dict[str, Any]:
    from api.model_registry import get_default_profile

    profile = get_default_profile(capability) or {}
    return {
        "id": profile.get("id"),
        "provider": profile.get("provider"),
        "model": profile.get("model_name"),
        "capability": profile.get("capability"),
        "adapter_id": profile.get("adapter_id"),
        "adapter_version": profile.get("adapter_version"),
        "transport_binding_id": profile.get("transport_binding_id"),
        "credential_configured": bool(profile.get("credential_configured")),
    }


def _forensic_history() -> dict[str, Any]:
    from core.canary_identity_boundary import classify_canary_identity

    runner = ROOT / "scripts" / "run_shot_canary_v1.py"
    runner_text = runner.read_text(encoding="utf-8") if runner.exists() else ""
    old_dirs = [ROOT / "docs" / "shot-canary", ROOT / "docs" / "video-compiler"]
    records = []
    for identity in BENCHMARK_IDS:
        classification = classify_canary_identity(identity)
        records.append({
            **classification,
            "historical_documents_retained": True,
            "historical_media_retained_for_forensics_only": True,
            "historical_runner_reference_detected": identity in runner_text,
            "historical_media_authority": False,
            "production_canonical": False,
            "forbidden_production_authority_uses": classification["forbidden_usage"],
            "retention_roots": [str(item.relative_to(ROOT)).replace("\\", "/") for item in old_dirs if item.exists()],
        })
    return {
        "schema_version": "historical_canary_identity_classification_v1",
        "benchmark_fixture_ids": BENCHMARK_IDS,
        "records": records,
        "historical_media_authority_count": 0,
        "production_canonical_count": 0,
        "adoption": "FORBIDDEN",
    }


def _identity_audit(session: Any) -> dict[str, Any]:
    from core.canary_identity_boundary import CanaryIdentityError, require_production_canonical_identity

    records = []
    for identity in BENCHMARK_IDS:
        try:
            require_production_canonical_identity(session, identity)
            records.append({"identity": identity, "status": "UNEXPECTED_PASS", "error_code": None})
        except CanaryIdentityError as exc:
            records.append({"identity": identity, "status": "BLOCKED", "error_code": exc.code})
    return {
        "schema_version": "canary_identity_boundary_audit_v1",
        "production_identity_rule": "exact structured ShotPlan.shots[*].plan_shot_id + current ShotPlanPointer + current ShotPlanAuthority",
        "records": records,
        "all_benchmark_blocked": all(item["error_code"] == "BENCHMARK_IDENTITY_NOT_PRODUCTION_CANONICAL" for item in records),
        "real_image_calls": 0,
        "real_video_calls": 0,
        "external_llm_calls": 0,
    }


def _authority_snapshot(selection: dict[str, Any], inventory: list[dict[str, Any]]) -> dict[str, Any]:
    selected = selection.get("selected")
    targets = selection.get("top_candidates") or []
    if not targets:
        targets = [item for item in inventory if item.get("hard_gate") == "PASS"][:20]
    return {
        "schema_version": "canonical_canary_authority_snapshot_v1",
        "status": "READY_FOR_REVIEW" if selected else "NOT_APPLICABLE_UNTIL_SELECTION_RESOLVED",
        "selection_status": selection.get("status"),
        "targets": [{
            "book_id": item.get("book_id"),
            "episode": item.get("episode"),
            "scene_id": item.get("scene_id"),
            "shot_plan_id": item.get("shot_plan_id"),
            "plan_shot_id": item.get("plan_shot_id"),
            "storyboard_shot_id": item.get("storyboard_shot_id"),
            "script_ir": item.get("script_ir"),
            "treatment_id": item.get("treatment_id"),
            "treatment_authority_fingerprint": item.get("treatment_authority_fingerprint"),
            "scene_blocking_id": item.get("scene_blocking_id"),
            "scene_blocking_authority_fingerprint": item.get("scene_blocking_authority_fingerprint"),
            "shot_plan_authority_fingerprint": item.get("shot_plan_authority_fingerprint"),
            "materialization_set_id": item.get("materialization_set_id"),
            "materialization_fingerprint": item.get("materialization_fingerprint"),
            "asset_authority": item.get("asset_authority"),
        } for item in targets],
        "production_media_writes": 0,
    }


def _prompt_readiness(inventory: list[dict[str, Any]], selection: dict[str, Any]) -> dict[str, Any]:
    chosen = selection.get("selected")
    rows = [chosen] if chosen else [item for item in inventory if item.get("hard_gate") == "PASS"]
    return {
        "schema_version": "canonical_canary_prompt_ir_readiness_v1",
        "status": "READY" if chosen and chosen.get("prompt_ir", {}).get("IMAGE") == "PRESENT_CURRENT" and chosen.get("prompt_ir", {}).get("VIDEO") == "PRESENT_CURRENT" else "BLOCKED_UNTIL_UNIQUE_TARGET",
        "selection_status": selection.get("status"),
        "rows": [{"plan_shot_id": item.get("plan_shot_id"), "storyboard_shot_id": item.get("storyboard_shot_id"), "prompt_ir": item.get("prompt_ir")} for item in rows],
        "provider_prompt_compilation_calls": 0,
        "real_image_calls": 0,
        "real_video_calls": 0,
    }


def _report(*, run_id: str, history: dict[str, Any], identity_audit: dict[str, Any], inventory: list[dict[str, Any]], selection: dict[str, Any], image: dict[str, Any], video: dict[str, Any]) -> str:
    status = selection.get("status")
    hard_pass = sum(item.get("hard_gate") == "PASS" for item in inventory)
    blockers: dict[str, int] = selection.get("blocker_counts") or {}
    blocker_text = ", ".join(f"`{key}`={value}" for key, value in blockers.items()) or "none"
    selected = selection.get("selected")
    selected_text = f"`{selected.get('plan_shot_id')}` (book `{selected.get('book_id')}`, storyboard `{selected.get('storyboard_shot_id')}`)" if selected else "none"
    return f"""# Canonical Canary Target Selection V1

Status: `{status}`  
Run: `{run_id}`

Identity boundary status: `{'BENCHMARK_PRODUCTION_IDENTITY_SEPARATED' if identity_audit.get('all_benchmark_blocked') else 'IDENTITY_BOUNDARY_FAILED'}`

## Identity boundary

- Benchmark fixtures: `{', '.join(BENCHMARK_IDS)}`.
- `production_canonical_identity`: `false` for all benchmark fixtures.
- `historical_media_authority`: `false` for all benchmark fixtures.
- Benchmark boundary audit: `{'PASS' if identity_audit.get('all_benchmark_blocked') else 'FAIL'}`; all three attempts return `BENCHMARK_IDENTITY_NOT_PRODUCTION_CANONICAL`.
- Historical documents remain retained as forensic / regression evidence. They are forbidden as production shot authority, production media authority, or official media lineage sources.

## Current canonical inventory

- ShotPlanPointer rows scanned: `{len(inventory)}` materialized shot projections.
- Hard-gate pass: `{hard_pass}`; hard-gate blocked: `{len(inventory) - hard_pass}`.
- Complete chain required: current Script → production-qualified ScriptIR → current Treatment → current SceneBlocking → current ShotPlan → current materialization → StoryboardShot → production asset authority → current IMAGE/VIDEO PromptIR.
- Blocker counts: {blocker_text}.

## Deterministic selection

- Selected target: {selected_text}.
- Ranking is deterministic: score descending, then book, episode, exact `plan_shot_id`, storyboard id.
- Selection rule: a score tie is rejected as `CANONICAL_CANARY_TARGET_AMBIGUOUS`; no candidate is auto-promoted.

## Runtime safety

- IMAGE profile: `{image.get('provider')}` / `{image.get('model')}`.
- VIDEO profile: `{video.get('provider')}` / `{video.get('model')}`.
- Real IMAGE calls: `0`.
- Real VIDEO calls: `0`.
- External LLM calls: `0`.
- SHAPI/Poyo calls: `0`.
- Production database/media writes: `0`.

The phase stops at target selection. No provider request, prompt compilation mutation, materialization mutation, media generation, or authority promotion was executed.
"""


def main() -> int:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    from core.canonical_canary_selection import build_canonical_shot_inventory, select_canary_target
    from models import Session

    history = _forensic_history()
    image = _profile("image")
    video = _profile("video")
    with Session() as session:
        identity_audit = _identity_audit(session)
        inventory = build_canonical_shot_inventory(session)
        selection = select_canary_target(inventory)

    # The fingerprint identifies this deterministic selection evidence only;
    # it is never substituted for a production authority envelope fingerprint.
    selection_fingerprint = hashlib.sha256(json.dumps(_safe(selection), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    selection_evidence = {
        "schema_version": "canonical_canary_selection_v1",
        "run_id": run_id,
        "status": selection.get("status"),
        "identity_boundary_status": "BENCHMARK_PRODUCTION_IDENTITY_SEPARATED" if identity_audit.get("all_benchmark_blocked") else "IDENTITY_BOUNDARY_FAILED",
        "selection_fingerprint": selection_fingerprint,
        "selected": selection.get("selected"),
        "top_candidates": selection.get("top_candidates"),
        "candidate_count": len(selection.get("candidates") or []),
        "blocker_counts": selection.get("blocker_counts"),
        "ranking": "score_desc_then_book_episode_exact_plan_shot_id_storyboard_id",
        "real_image_calls": 0,
        "real_video_calls": 0,
        "external_llm_calls": 0,
    }
    _write("HISTORICAL_CANARY_IDENTITY_CLASSIFICATION.json", {"run_id": run_id, **history})
    _write("CANARY_IDENTITY_BOUNDARY_AUDIT.json", {"run_id": run_id, **identity_audit})
    _write("CANONICAL_SHOT_INVENTORY.json", {"run_id": run_id, "schema_version": "canonical_shot_inventory_v1", "count": len(inventory), "items": inventory})
    _write("CANONICAL_CANARY_CANDIDATES.json", {"run_id": run_id, "schema_version": "canonical_canary_candidates_v1", "status": selection.get("status"), "candidates": selection.get("candidates"), "blocker_counts": selection.get("blocker_counts")})
    _write("CANONICAL_CANARY_SELECTION.json", selection_evidence)
    _write("CANONICAL_CANARY_AUTHORITY_SNAPSHOT.json", {"run_id": run_id, **_authority_snapshot(selection, inventory)})
    _write("CANONICAL_CANARY_PROMPT_IR_READINESS.json", {"run_id": run_id, **_prompt_readiness(inventory, selection)})
    report = _report(run_id=run_id, history=history, identity_audit=identity_audit, inventory=inventory, selection=selection, image=image, video=video)
    (OUT / "CANONICAL_CANARY_TARGET_SELECTION_REPORT.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
