"""Apply a confirmed storyboard batch prompt repair to real projects.

Default behavior is a safe refusal with no real-project writes. To actually
apply, the caller must provide all of:

- APPLY_STORYBOARD_BATCH_REPAIR_REAL=1
- APPLY_STORYBOARD_BATCH_REPAIR_PREFLIGHT=<path to preflight JSON>
- APPLY_STORYBOARD_BATCH_REPAIR_CONFIRM=<confirmation token from that report>
- APPLY_STORYBOARD_BATCH_REPAIR_MOCK=1 for a deterministic local gray run, or
  APPLY_STORYBOARD_BATCH_REPAIR_USE_REAL_LLM=1 for a real compiler run

The apply path creates a current-snapshot baseline prompt version before each
compile, then writes an apply report with rollback endpoints. Do not run the
confirmed mode without explicit user approval.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

BATCH_HELPER_PATH = ROOT_DIR / "scripts" / "validate-storyboard-batch-repair-clone.py"
spec = importlib.util.spec_from_file_location("storyboard_batch_repair_helper", BATCH_HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load batch helper script: {BATCH_HELPER_PATH}")
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)

from api.server import _persist_storyboard_prompt_compile
from core.model_adapter import adapt_ir_to_model
from core.prompt_ir import build_shot_ir_from_context
from core.rule_compiler import compile_rules
from models import Session, StoryboardPromptVersion, StoryboardShot, init_db


REPORT_PREFIX = "storyboard-batch-repair-apply"


def log(message: str) -> None:
    print(f"[storyboard-batch-apply] {message}")


def load_preflight_report(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT_DIR / path
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"Preflight report not found: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise RuntimeError("Preflight report must be a JSON object.")
    return report


def explain_safe_refusal() -> None:
    log("Refused: real-project batch apply is disabled by default.")
    log("Run `npm run plan:storyboard-batch-repair` first and review the generated JSON/Markdown report.")
    log("To apply after explicit approval, provide all required environment variables:")
    log("  APPLY_STORYBOARD_BATCH_REPAIR_REAL=1")
    log("  APPLY_STORYBOARD_BATCH_REPAIR_PREFLIGHT=<artifacts/storyboard-batch-repair-preflight-*.json>")
    log("  APPLY_STORYBOARD_BATCH_REPAIR_CONFIRM=<confirmation token from that report>")
    log("  APPLY_STORYBOARD_BATCH_REPAIR_MOCK=1  # deterministic local gray run")
    log("  # or APPLY_STORYBOARD_BATCH_REPAIR_USE_REAL_LLM=1 after validating the real compiler")
    log("No real project data was modified.")


def apply_mode() -> str | None:
    mock_flag = os.environ.get("APPLY_STORYBOARD_BATCH_REPAIR_MOCK") == "1"
    real_llm_flag = os.environ.get("APPLY_STORYBOARD_BATCH_REPAIR_USE_REAL_LLM") == "1"
    if mock_flag and real_llm_flag:
        raise RuntimeError("Choose either MOCK=1 or USE_REAL_LLM=1, not both; refusing real-project apply.")
    if mock_flag:
        return "deterministic-mock"
    if real_llm_flag:
        return "real-llm"
    return None


def validate_apply_gate() -> dict[str, Any] | None:
    real_flag = os.environ.get("APPLY_STORYBOARD_BATCH_REPAIR_REAL") == "1"
    preflight_path = os.environ.get("APPLY_STORYBOARD_BATCH_REPAIR_PREFLIGHT", "").strip()
    confirm = os.environ.get("APPLY_STORYBOARD_BATCH_REPAIR_CONFIRM", "").strip()
    if not real_flag or not preflight_path or not confirm:
        explain_safe_refusal()
        return None

    mode = apply_mode()
    if mode is None:
        raise RuntimeError(
            "Confirmed real-project apply also requires an explicit compiler mode: "
            "APPLY_STORYBOARD_BATCH_REPAIR_MOCK=1 for deterministic local gray testing, "
            "or APPLY_STORYBOARD_BATCH_REPAIR_USE_REAL_LLM=1 for a real LLM run."
        )

    report = load_preflight_report(preflight_path)
    expected = str(report.get("confirmationToken") or "").strip()
    if not expected or confirm != expected:
        raise RuntimeError("Confirmation token mismatch; refusing real-project apply.")
    if report.get("mode") != "dry-run-preflight":
        raise RuntimeError("Preflight report mode is not dry-run-preflight; refusing apply.")
    status = report.get("status", {}) if isinstance(report.get("status"), dict) else {}
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    if not status.get("ready_for_human_review"):
        raise RuntimeError("Preflight report is not ready for human review; refusing apply.")
    if int(summary.get("after_errors") or 0) != 0:
        raise RuntimeError("Preflight report still has after_errors; refusing apply.")
    results = report.get("results", [])
    if not isinstance(results, list) or not results:
        raise RuntimeError("Preflight report does not contain repair results; refusing apply.")
    missing_readiness = [
        item
        for item in results
        if not isinstance(item, dict) or not isinstance(item.get("real_apply_readiness"), dict)
    ]
    if missing_readiness:
        raise RuntimeError(
            "Preflight report does not contain real_apply_readiness checks; "
            "regenerate it with the current `npm run plan:storyboard-batch-repair` before apply."
        )
    real_apply_blockers = [
        {
            "book_id": item.get("book_id"),
            "episode": item.get("episode"),
            "shot_id": item.get("shot_id"),
            "blocker": blocker,
        }
        for item in results
        for blocker in item.get("real_apply_readiness", {}).get("blockers", [])
    ]
    if real_apply_blockers:
        raise RuntimeError(
            "Preflight contains real apply blocker(s); refusing apply: "
            + json.dumps(real_apply_blockers, ensure_ascii=False)
        )
    report["_apply_mode"] = mode
    return report


def structured_from_shot_meta(shot: StoryboardShot) -> dict[str, Any]:
    meta = batch.helper.safe_json_loads(shot.meta_info, {})
    return batch.structured_from_meta(meta)


def latest_prompt_version(session: Session, book_id: int, episode: int, shot_id: int):
    return (
        session.query(StoryboardPromptVersion)
        .filter(
            StoryboardPromptVersion.book_id == book_id,
            StoryboardPromptVersion.episode == episode,
            StoryboardPromptVersion.shot_id == shot_id,
        )
        .order_by(StoryboardPromptVersion.version.desc())
        .first()
    )


def create_current_baseline_prompt_version(session: Session, shot: StoryboardShot) -> StoryboardPromptVersion:
    latest = latest_prompt_version(session, int(shot.book_id), int(shot.episode), int(shot.shot_id))
    next_version = (latest.version if latest else 0) + 1
    meta = batch.helper.safe_json_loads(shot.meta_info, {})
    version_meta = {
        "structured_shot": batch.structured_from_meta(meta),
        "prompt_compile_context": meta.get("prompt_compile_context", {}) if isinstance(meta, dict) else {},
        "used_assets": meta.get("used_assets", []) if isinstance(meta, dict) else [],
        "reference_images": meta.get("reference_images", []) if isinstance(meta, dict) else [],
        "reference_asset_ids": meta.get("reference_asset_ids", []) if isinstance(meta, dict) else [],
        "compiler_warnings": ["baseline created before confirmed batch prompt repair"],
        "compiler_diagnostics": {},
    }
    baseline = StoryboardPromptVersion(
        book_id=shot.book_id,
        episode=shot.episode,
        shot_id=shot.shot_id,
        version=next_version,
        compile_reason="batch-quality-repair-current-baseline",
        prompt_static=shot.visual_prompt_static or "",
        prompt_motion=shot.visual_prompt_motion or "",
        negative_prompt=shot.visual_prompt_final or "",
        meta_info=json.dumps(version_meta, ensure_ascii=False),
    )
    session.add(baseline)
    session.flush()
    return baseline


def build_mock_llm_payload_for_real_shot(book_id: int, episode: int, shot: StoryboardShot) -> dict[str, Any]:
    meta_info = batch.helper.safe_json_loads(shot.meta_info, {})
    seed = {
        "shot_id": shot.shot_id,
        "scene_name": shot.scene_name,
        "makeup_prompts": batch.helper._load_episode_makeup_prompt_stub(book_id, episode),
        "action_process": shot.action_process,
        "dialogue": shot.dialogue,
        "start_state": shot.start_state,
        "end_state": shot.end_state,
        "duration": shot.duration,
        "camera_angle": shot.camera_angle,
        "camera_movement": shot.camera_movement,
        "transition": shot.transition,
    }
    structured = batch.helper._auto_bind_structured_shot_assets(
        book_id,
        episode,
        batch.helper._derive_structured_shot_payload(meta_info, seed),
        seed,
    )
    scene_name = str(shot.scene_name or "").strip()
    asset_link_summary = batch.helper._build_storyboard_reference_summary(
        batch.helper._load_asset_links(shot.asset_links),
        scene_name,
    )
    compile_context = batch.helper._build_prompt_compile_context_v2(
        book_id,
        shot,
        structured,
        {},
        asset_link_summary,
    )
    compile_context["reference_summary"] = batch.helper._build_storyboard_reference_summary_from_bound_assets(
        compile_context.get("bound_assets", []),
        str(compile_context.get("scene_name") or shot.scene_name or "").strip(),
    )
    bound_assets = [item for item in compile_context.get("bound_assets", []) if isinstance(item, dict)]
    shot_ir = compile_rules(
        build_shot_ir_from_context(compile_context),
        compile_context.get("production_skill", {}),
    )
    adapter_output = adapt_ir_to_model(shot_ir, str(compile_context.get("target_model") or "jimeng"))
    used_assets = [
        {
            "asset_type": item.get("asset_type"),
            "asset_id": item.get("asset_id"),
            "asset_name": item.get("asset_name"),
            "reference_token": item.get("reference_token"),
            "reference_status": item.get("reference_status"),
        }
        for item in bound_assets
    ]
    return {
        "visual_prompt_static": str(adapter_output.get("static_prompt") or "").strip(),
        "visual_prompt_motion": str(adapter_output.get("motion_prompt") or "").strip(),
        "negative_prompt": str(adapter_output.get("negative_prompt") or "").strip(),
        "used_assets": used_assets,
        "warnings": ["deterministic real-project apply uses Model Adapter baseline"],
    }


def persist_with_selected_compiler_mode(
    session: Session,
    book_id: int,
    episode: int,
    shot: StoryboardShot,
    compile_reason: str,
    mode: str,
) -> dict[str, Any]:
    if mode == "deterministic-mock":
        mock_payload = build_mock_llm_payload_for_real_shot(book_id, episode, shot)
        with patch("core.llm.call_llm_json", return_value=mock_payload):
            return _persist_storyboard_prompt_compile(session, book_id, episode, shot, compile_reason)
    if mode == "real-llm":
        return _persist_storyboard_prompt_compile(session, book_id, episode, shot, compile_reason)
    raise RuntimeError(f"Unsupported compiler mode: {mode}")


def apply_one(sample: dict[str, Any], mode: str) -> dict[str, Any]:
    book_id = int(sample["book_id"])
    episode = int(sample["episode"])
    shot_id = int(sample["shot_id"])
    with Session() as session:
        shot = (
            session.query(StoryboardShot)
            .filter(
                StoryboardShot.book_id == book_id,
                StoryboardShot.episode == episode,
                StoryboardShot.shot_id == shot_id,
            )
            .first()
        )
        if not shot:
            raise RuntimeError(f"Storyboard shot not found: #{book_id}:{episode}:{shot_id}")

        before_audit = batch.audit_source_shot(shot)
        baseline = create_current_baseline_prompt_version(session, shot)
        result = persist_with_selected_compiler_mode(
            session,
            book_id,
            episode,
            shot,
            "batch-quality-repair-confirmed",
            mode,
        )
        compiled = result["compiled"]
        after_audit = batch.audit_snapshot(
            static_prompt=result["row"].prompt_static,
            motion_prompt=result["row"].prompt_motion,
            scene_name=shot.scene_name,
            structured=result["structured"],
            diagnostics=compiled.get("compiler_diagnostics") if isinstance(compiled.get("compiler_diagnostics"), dict) else {},
        )
        session.commit()
        session.refresh(result["row"])
        return {
            "book_id": book_id,
            "book_title": sample.get("book_title"),
            "episode": episode,
            "shot_id": shot_id,
            "scene_name": sample.get("scene_name"),
            "before_audit": before_audit,
            "after_audit": after_audit,
            "baseline_anchor": {
                "version_id": baseline.id,
                "version": baseline.version,
                "compile_reason": baseline.compile_reason,
            },
            "applied_version": {
                "version_id": result["row"].id,
                "version": result["row"].version,
                "compile_reason": result["row"].compile_reason,
            },
            "apply_mode": mode,
            "rollback": {
                "method": "POST",
                "path": f"/api/books/{book_id}/storyboard/{episode}/{shot_id}/prompt-versions/{baseline.id}/rollback",
                "body": {"reason": "batch-quality-repair-rollback"},
            },
        }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    before_errors = sum(len(item["before_audit"]["issues"]) for item in results)
    before_warnings = sum(len(item["before_audit"]["warnings"]) for item in results)
    after_errors = sum(len(item["after_audit"]["issues"]) for item in results)
    after_warnings = sum(len(item["after_audit"]["warnings"]) for item in results)
    return {
        "samples": len(results),
        "before_errors": before_errors,
        "before_warnings": before_warnings,
        "after_errors": after_errors,
        "after_warnings": after_warnings,
        "error_reduction": before_errors - after_errors,
        "warning_reduction": before_warnings - after_warnings,
    }


def write_apply_report(preflight: dict[str, Any], results: list[dict[str, Any]], summary: dict[str, Any]) -> Path:
    artifacts_dir = ROOT_DIR / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    stamp = batch.helper.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    report_path = artifacts_dir / f"{REPORT_PREFIX}-{stamp}.json"
    report_path.write_text(
        json.dumps(
            {
                "generatedAt": batch.helper.datetime.utcnow().isoformat(),
                "mode": "real-project-apply",
                "compilerMode": preflight.get("_apply_mode"),
                "confirmationToken": preflight.get("confirmationToken"),
                "summary": summary,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return report_path


def apply_confirmed_batch() -> None:
    report = validate_apply_gate()
    if report is None:
        return

    init_db()
    mode = str(report["_apply_mode"])
    results: list[dict[str, Any]] = []
    for sample in report["results"]:
        log(f"Applying confirmed repair to #{sample['book_id']}:{sample['episode']}:{sample['shot_id']} with {mode} compiler...")
        results.append(apply_one(sample, mode))
    summary = summarize(results)
    report_path = write_apply_report(report, results, summary)
    log(
        "Apply summary: "
        f"samples={summary['samples']}, "
        f"errors {summary['before_errors']} -> {summary['after_errors']}, "
        f"warnings {summary['before_warnings']} -> {summary['after_warnings']}"
    )
    log(f"Apply report written: {report_path}")
    if summary["after_errors"] > 0:
        raise RuntimeError(f"Confirmed apply left {summary['after_errors']} error(s).")


if __name__ == "__main__":
    apply_confirmed_batch()
