"""Clone-only gray validation for the real storyboard prompt compiler.

This script is intentionally non-destructive to real projects:

- It selects real storyboard shots.
- It clones one shot at a time into a temporary book.
- It compiles prompts through the normal backend compile API.
- It rolls the clone back to its baseline version.
- It removes the temporary book data.

By default it refuses to run. Use one explicit compiler mode:

- STORYBOARD_REAL_LLM_GRAY_MOCK=1 for deterministic local validation.
- STORYBOARD_REAL_LLM_GRAY_USE_REAL_LLM=1 for a real LLM/API validation.

The real LLM mode also requires STORYBOARD_REAL_LLM_GRAY_RUN=1 and an effective
LLM API key from env or the model registry. It never writes to source books.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

HELPER_PATH = ROOT_DIR / "scripts" / "validate-storyboard-batch-repair-clone.py"
spec = importlib.util.spec_from_file_location("storyboard_batch_repair_helper", HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load batch helper script: {HELPER_PATH}")
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)

import config
from models import Book, Session, StoryboardShot, init_db


REPORT_PREFIX = "storyboard-real-llm-gray"
DEFAULT_BOOK_IDS = "75,5,3,1,14"
DEFAULT_SAMPLE_COUNT = 1


def log(message: str) -> None:
    print(f"[storyboard-real-llm-gray] {message}")


def elapsed_seconds(started_at: float) -> float:
    return round(time.monotonic() - started_at, 3)


def parse_csv_ints(raw: str) -> list[int]:
    values: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if token:
            values.append(int(token))
    return values


def parse_book_ids() -> list[int]:
    return parse_csv_ints(os.environ.get("STORYBOARD_REAL_LLM_GRAY_BOOK_IDS", DEFAULT_BOOK_IDS))


def sample_count() -> int:
    return max(1, int(os.environ.get("STORYBOARD_REAL_LLM_GRAY_SHOT_COUNT", str(DEFAULT_SAMPLE_COUNT))))


def parse_targets() -> list[tuple[int, int, int]]:
    raw = os.environ.get("STORYBOARD_REAL_LLM_GRAY_TARGETS", "").strip()
    if not raw:
        return []
    targets: list[tuple[int, int, int]] = []
    for token in raw.split(","):
        parts = [part.strip() for part in token.strip().split(":")]
        if len(parts) != 3 or not all(parts):
            raise RuntimeError(
                "STORYBOARD_REAL_LLM_GRAY_TARGETS must use comma-separated book_id:episode:shot_id entries."
            )
        targets.append((int(parts[0]), int(parts[1]), int(parts[2])))
    return targets


def compiler_mode() -> str | None:
    mock = os.environ.get("STORYBOARD_REAL_LLM_GRAY_MOCK") == "1"
    real = os.environ.get("STORYBOARD_REAL_LLM_GRAY_USE_REAL_LLM") == "1"
    if mock and real:
        raise RuntimeError("Choose either STORYBOARD_REAL_LLM_GRAY_MOCK=1 or STORYBOARD_REAL_LLM_GRAY_USE_REAL_LLM=1, not both.")
    if mock:
        return "deterministic-mock"
    if real:
        return "real-llm"
    return None


def effective_llm_profile() -> dict[str, Any]:
    try:
        from api.model_registry import get_default_profile

        profile = get_default_profile("llm")
        if isinstance(profile, dict) and profile:
            return dict(profile)
    except Exception as exc:  # pragma: no cover - defensive preflight only
        log(f"Unable to inspect model registry profile, falling back to env config: {exc}")
    return {
        "api_key": config.OPENAI_API_KEY,
        "base_url": config.OPENAI_BASE_URL,
        "model_name": config.LLM_MODEL,
    }


def has_real_api_key() -> bool:
    profile = effective_llm_profile()
    api_key = str(profile.get("api_key") or config.OPENAI_API_KEY or "").strip()
    return bool(api_key and api_key != "sk-placeholder")


def explain_refusal() -> None:
    log("Refused: real LLM gray validation is disabled by default.")
    log("No real project data was modified.")
    profile = effective_llm_profile()
    profile_name = str(profile.get("name") or profile.get("id") or "env/default").strip()
    profile_model = str(profile.get("model_name") or "").strip()
    profile_key_status = "configured" if has_real_api_key() else "missing"
    log(
        "Effective default LLM profile: "
        f"{profile_name}"
        + (f" / {profile_model}" if profile_model else "")
        + f" / key={profile_key_status}."
    )
    log("For a local safety-path validation:")
    log("  STORYBOARD_REAL_LLM_GRAY_MOCK=1 npm run validate:storyboard-real-llm-gray")
    log("For a real LLM clone-only gray run after confirming cost/key:")
    log("  STORYBOARD_REAL_LLM_GRAY_RUN=1")
    log("  STORYBOARD_REAL_LLM_GRAY_USE_REAL_LLM=1")
    log("  STORYBOARD_REAL_LLM_GRAY_SHOT_COUNT=1")
    log("  npm run validate:storyboard-real-llm-gray")


def validate_gate() -> str | None:
    mode = compiler_mode()
    if mode is None:
        explain_refusal()
        return None
    if mode == "real-llm":
        if os.environ.get("STORYBOARD_REAL_LLM_GRAY_RUN") != "1":
            raise RuntimeError("Real LLM gray validation requires STORYBOARD_REAL_LLM_GRAY_RUN=1.")
        if not has_real_api_key():
            raise RuntimeError("Real LLM gray validation requires a configured non-placeholder LLM API key.")
    return mode


def select_samples(book_ids: list[int], limit: int) -> list[dict[str, Any]]:
    explicit_targets = parse_targets()
    samples: list[dict[str, Any]] = []
    with Session() as session:
        if explicit_targets:
            books = {
                int(book.id): book
                for book in session.query(Book).filter(Book.id.in_([target[0] for target in explicit_targets])).all()
            }
            for book_id, episode, shot_id in explicit_targets:
                book = books.get(book_id)
                shot = (
                    session.query(StoryboardShot)
                    .filter(
                        StoryboardShot.book_id == book_id,
                        StoryboardShot.episode == episode,
                        StoryboardShot.shot_id == shot_id,
                    )
                    .first()
                )
                if not book or not shot:
                    raise RuntimeError(f"Target storyboard shot not found: #{book_id}:{episode}:{shot_id}")
                samples.append(sample_payload(book, shot))
            return samples[:limit]

        books = {int(book.id): book for book in session.query(Book).filter(Book.id.in_(book_ids)).all()}
        by_book: dict[int, list[dict[str, Any]]] = {}
        for book_id in book_ids:
            book = books.get(book_id)
            if not book:
                by_book[book_id] = []
                continue
            rows = (
                session.query(StoryboardShot)
                .filter(StoryboardShot.book_id == book_id)
                .order_by(StoryboardShot.episode.asc(), StoryboardShot.shot_id.asc())
                .all()
            )
            by_book[book_id] = [sample_payload(book, shot) for shot in rows]
            log(f"#{book_id}: available storyboard shots={len(by_book[book_id])}")

    seen: set[tuple[int, int, int]] = set()
    while len(samples) < limit:
        added = False
        for book_id in book_ids:
            offset = sum(1 for item in samples if item["book_id"] == book_id)
            candidates = by_book.get(book_id, [])
            if offset >= len(candidates):
                continue
            item = candidates[offset]
            key = (item["book_id"], item["episode"], item["shot_id"])
            if key in seen:
                continue
            samples.append(item)
            seen.add(key)
            added = True
            if len(samples) >= limit:
                break
        if not added:
            break
    if not samples:
        raise RuntimeError("No storyboard samples found for real LLM gray validation.")
    return samples


def sample_payload(book: Book, shot: StoryboardShot) -> dict[str, Any]:
    return {
        "book_id": int(book.id),
        "book_title": book.title,
        "episode": int(shot.episode or 1),
        "shot_id": int(shot.shot_id),
        "scene_name": shot.scene_name,
        "source_audit": batch.audit_source_shot(shot),
    }


def compile_clone(client: TestClient, clone: dict[str, Any], sample: dict[str, Any], mode: str):
    url = f"/api/books/{batch.helper.TEMP_BOOK_ID}/storyboard/{clone['episode']}/{clone['shot_id']}/compile-prompts"
    body = {
        "compileReason": f"real-llm-gray-{mode}",
        "force": True,
        # The endpoint intentionally rejects implicit provider calls.  The
        # gray runner is an explicit operator-controlled validation tool; in
        # deterministic mode the provider call is still locally mocked.
        "confirmed": True,
        "allowExternalCall": True,
    }
    if mode == "deterministic-mock":
        mock_payload = batch.helper.build_mock_llm_payload(sample["episode"], sample["shot_id"])
        with patch("core.llm.call_llm_json", return_value=mock_payload):
            return client.post(url, json=body)
    return client.post(url, json=body)


def verify_rollback(clone: dict[str, Any]) -> None:
    with Session() as session:
        rolled_back = (
            session.query(StoryboardShot)
            .filter(
                StoryboardShot.book_id == batch.helper.TEMP_BOOK_ID,
                StoryboardShot.episode == clone["episode"],
                StoryboardShot.shot_id == int(clone["shot_id"]),
            )
            .first()
        )
        if not rolled_back:
            raise RuntimeError("Clone disappeared before rollback verification.")
        rollback_meta = batch.helper.safe_json_loads(rolled_back.meta_info, {})
        rollback_structured = batch.structured_from_meta(rollback_meta)
        expected_scene_asset_id = str(clone.get("baseline_structured", {}).get("scene_asset_id") or "").strip()
        actual_scene_asset_id = str(rollback_structured.get("scene_asset_id") or "").strip()
        if rolled_back.visual_prompt_static != clone["baseline_static"] or rolled_back.visual_prompt_motion != clone["baseline_motion"]:
            raise RuntimeError("Rollback did not restore source baseline prompt text.")
        if actual_scene_asset_id != expected_scene_asset_id:
            raise RuntimeError("Rollback did not restore source baseline structured_shot.scene_asset_id.")


def compact_structured_summary(structured: dict[str, Any]) -> dict[str, Any]:
    structured = structured if isinstance(structured, dict) else {}
    return {
        "scene_asset_id": str(structured.get("scene_asset_id") or "").strip(),
        "character_asset_ids": structured.get("character_asset_ids", [])
        if isinstance(structured.get("character_asset_ids", []), list)
        else [],
        "prop_asset_ids": structured.get("prop_asset_ids", [])
        if isinstance(structured.get("prop_asset_ids", []), list)
        else [],
        "action_beats_count": len(structured.get("action_beats", []))
        if isinstance(structured.get("action_beats", []), list)
        else 0,
        "camera_angle": structured.get("camera_angle"),
        "camera_movement": structured.get("camera_movement"),
        "duration": structured.get("duration"),
    }


def validate_sample(client: TestClient, sample: dict[str, Any], mode: str) -> dict[str, Any]:
    sample_started_at = time.monotonic()
    timings: dict[str, float] = {}
    clone_started_at = time.monotonic()
    clone = batch.helper.clone_source_to_temp(
        sample["book_id"],
        sample["episode"],
        sample["shot_id"],
        baseline_mode="source",
    )
    timings["clone_seconds"] = elapsed_seconds(clone_started_at)
    log(
        f"Cloned #{sample['book_id']} {sample['episode']}-{sample['shot_id']} "
        f"into temp book #{clone['temp_book_id']} using {mode} compiler."
    )

    try:
        compile_started_at = time.monotonic()
        response = compile_clone(client, clone, sample, mode)
        timings["compile_seconds"] = elapsed_seconds(compile_started_at)
        if response.status_code != 200:
            return {
                **sample,
                "passed": False,
                "failure_stage": "compile",
                "http_status": response.status_code,
                "response_text": response.text[:4000],
                "timings": timings,
                "elapsed_seconds": elapsed_seconds(sample_started_at),
            }

        audit_started_at = time.monotonic()
        compiled = response.json()
        with Session() as session:
            repaired_shot = (
                session.query(StoryboardShot)
                .filter(
                    StoryboardShot.book_id == batch.helper.TEMP_BOOK_ID,
                    StoryboardShot.episode == clone["episode"],
                    StoryboardShot.shot_id == int(clone["shot_id"]),
                )
                .first()
            )
            if not repaired_shot:
                raise RuntimeError("Compiled clone disappeared before audit.")
            repaired_meta = batch.helper.safe_json_loads(repaired_shot.meta_info, {})
            repaired_structured = batch.structured_from_meta(repaired_meta)

        after_audit = batch.audit_snapshot(
            static_prompt=compiled.get("prompt_static") or repaired_shot.visual_prompt_static,
            motion_prompt=compiled.get("prompt_motion") or repaired_shot.visual_prompt_motion,
            scene_name=repaired_shot.scene_name,
            structured=repaired_structured,
            diagnostics=compiled.get("compiler_diagnostics") if isinstance(compiled.get("compiler_diagnostics"), dict) else {},
        )
        timings["audit_seconds"] = elapsed_seconds(audit_started_at)

        rollback_started_at = time.monotonic()
        rollback_response = client.post(
            f"/api/books/{batch.helper.TEMP_BOOK_ID}/storyboard/{clone['episode']}/{clone['shot_id']}/prompt-versions/{clone['baseline_version_id']}/rollback",
            json={"reason": f"real-llm-gray-{mode}-rollback"},
        )
        timings["rollback_seconds"] = elapsed_seconds(rollback_started_at)
        if rollback_response.status_code != 200:
            return {
                **sample,
                "passed": False,
                "failure_stage": "rollback",
                "http_status": rollback_response.status_code,
                "response_text": rollback_response.text[:4000],
                "after_audit": after_audit,
                "timings": timings,
                "elapsed_seconds": elapsed_seconds(sample_started_at),
            }
        verify_started_at = time.monotonic()
        verify_rollback(clone)
        timings["rollback_verify_seconds"] = elapsed_seconds(verify_started_at)

        diagnostics = compiled.get("compiler_diagnostics", {}) if isinstance(compiled.get("compiler_diagnostics"), dict) else {}
        passed = not after_audit["issues"] and not diagnostics.get("blocking_issues")
        return {
            **sample,
            "passed": passed,
            "failure_stage": None if passed else "audit",
            "compiler_mode": mode,
            "after_audit": after_audit,
            "compiled_version": compiled.get("version"),
            "diagnostics_status": diagnostics.get("status"),
            "compiler_diagnostics_summary": compact_diagnostics_summary(diagnostics),
            "repair_attempted": bool(compiled.get("repair_attempted")),
            "prompt_lengths": after_audit.get("prompt_lengths", {}),
            "timings": timings,
            "elapsed_seconds": elapsed_seconds(sample_started_at),
            "compiled_prompt_preview": {
                "static": str(compiled.get("prompt_static") or repaired_shot.visual_prompt_static or "").strip(),
                "motion": str(compiled.get("prompt_motion") or repaired_shot.visual_prompt_motion or "").strip(),
                "negative": str(compiled.get("negative_prompt") or repaired_shot.visual_prompt_final or "").strip(),
            },
            "compiled_structured_summary": compact_structured_summary(repaired_structured),
        }
    except Exception as exc:
        return {
            **sample,
            "passed": False,
            "failure_stage": "exception",
            "error": str(exc)[:4000],
            "timings": timings,
            "elapsed_seconds": elapsed_seconds(sample_started_at),
        }
    finally:
        cleanup_started_at = time.monotonic()
        batch.helper.cleanup_temp_book()
        log(
            f"Cleaned temp book #{batch.helper.TEMP_BOOK_ID}. "
            f"sample_elapsed={elapsed_seconds(sample_started_at)}s, cleanup={elapsed_seconds(cleanup_started_at)}s."
        )


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    elapsed_values = [
        float(item.get("elapsed_seconds") or 0)
        for item in results
        if item.get("elapsed_seconds") is not None
    ]
    return {
        "samples": len(results),
        "passed": sum(1 for item in results if item.get("passed")),
        "failed": sum(1 for item in results if not item.get("passed")),
        "after_errors": sum(len(item.get("after_audit", {}).get("issues", [])) for item in results),
        "after_warnings": sum(len(item.get("after_audit", {}).get("warnings", [])) for item in results),
        "total_elapsed_seconds": round(sum(elapsed_values), 3),
        "average_elapsed_seconds": round(sum(elapsed_values) / len(elapsed_values), 3) if elapsed_values else 0,
        "max_elapsed_seconds": round(max(elapsed_values), 3) if elapsed_values else 0,
        "compiler_warnings": sum(
            len(item.get("compiler_diagnostics_summary", {}).get("warnings", []))
            for item in results
            if isinstance(item.get("compiler_diagnostics_summary", {}), dict)
        ),
    }


def compact_diagnostics_summary(diagnostics: dict[str, Any]) -> dict[str, Any]:
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    checks = diagnostics.get("checks", []) if isinstance(diagnostics.get("checks", []), list) else []
    return {
        "status": diagnostics.get("status"),
        "warnings": [
            str(item).strip()
            for item in (diagnostics.get("warnings", []) if isinstance(diagnostics.get("warnings", []), list) else [])
            if str(item).strip()
        ],
        "blocking_issues": [
            str(item).strip()
            for item in (diagnostics.get("blocking_issues", []) if isinstance(diagnostics.get("blocking_issues", []), list) else [])
            if str(item).strip()
        ],
        "failed_checks": [
            {
                "key": str(item.get("key") or "").strip(),
                "message": str(item.get("message") or "").strip(),
                "details": item.get("details", []) if isinstance(item.get("details", []), list) else [],
            }
            for item in checks
            if isinstance(item, dict) and not bool(item.get("passed"))
        ],
    }


def write_reports(mode: str, results: list[dict[str, Any]], summary: dict[str, Any]) -> tuple[Path, Path]:
    artifacts_dir = ROOT_DIR / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    json_path = artifacts_dir / f"{REPORT_PREFIX}-{stamp}.json"
    md_path = artifacts_dir / f"{REPORT_PREFIX}-{stamp}.md"
    payload = {
        "generatedAt": datetime.utcnow().isoformat(),
        "mode": "clone-only-gray-validation",
        "compilerMode": mode,
        "tempBookId": batch.helper.TEMP_BOOK_ID,
        "summary": summary,
        "results": results,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Storyboard Real LLM Gray Validation",
        "",
        f"- Generated at: `{payload['generatedAt']}`",
        f"- Compiler mode: `{mode}`",
        f"- Temp book id: `{batch.helper.TEMP_BOOK_ID}`",
        f"- Samples: `{summary['samples']}`",
        f"- Passed / failed: `{summary['passed']} / {summary['failed']}`",
        f"- After audit errors / warnings: `{summary['after_errors']} / {summary['after_warnings']}`",
        f"- Compiler diagnostics warnings: `{summary['compiler_warnings']}`",
        f"- Total / average / max elapsed: `{summary['total_elapsed_seconds']}s / {summary['average_elapsed_seconds']}s / {summary['max_elapsed_seconds']}s`",
        "",
        "## Samples",
        "",
    ]
    for item in results:
        lines.extend(
            [
                f"- `#{item.get('book_id')}:{item.get('episode')}:{item.get('shot_id')}` "
                f"{item.get('book_title') or ''} / {item.get('scene_name') or ''} "
                f"=> {'PASS' if item.get('passed') else 'FAIL'}"
            ]
        )
        if item.get("failure_stage"):
            lines.append(f"  - failure_stage: `{item.get('failure_stage')}`")
        if item.get("elapsed_seconds") is not None:
            lines.append(f"  - elapsed: `{item.get('elapsed_seconds')}s`")
        timings = item.get("timings", {}) if isinstance(item.get("timings", {}), dict) else {}
        if timings:
            lines.append(
                "  - timings: `"
                + ", ".join(f"{key}={value}s" for key, value in timings.items())
                + "`"
            )
        if item.get("diagnostics_status"):
            lines.append(f"  - diagnostics_status: `{item.get('diagnostics_status')}`")
        diagnostics_summary = item.get("compiler_diagnostics_summary", {}) if isinstance(item.get("compiler_diagnostics_summary", {}), dict) else {}
        compiler_warnings = diagnostics_summary.get("warnings", []) if isinstance(diagnostics_summary.get("warnings", []), list) else []
        if compiler_warnings:
            lines.append("  - compiler_warnings: `" + " | ".join(str(warning) for warning in compiler_warnings[:3]) + "`")
        failed_checks = diagnostics_summary.get("failed_checks", []) if isinstance(diagnostics_summary.get("failed_checks", []), list) else []
        if failed_checks:
            lines.append(
                "  - failed_checks: `"
                + ", ".join(str(item.get("key") or "") for item in failed_checks if isinstance(item, dict))
                + "`"
            )
        after_audit = item.get("after_audit", {}) if isinstance(item.get("after_audit", {}), dict) else {}
        warnings = after_audit.get("warnings", []) if isinstance(after_audit.get("warnings", []), list) else []
        if warnings:
            lines.append("  - warnings: `" + ", ".join(str(warning) for warning in warnings) + "`")
        structured = item.get("compiled_structured_summary", {}) if isinstance(item.get("compiled_structured_summary", {}), dict) else {}
        if structured:
            lines.append(
                "  - structured: "
                f"scene=`{structured.get('scene_asset_id')}`, "
                f"characters=`{len(structured.get('character_asset_ids') or [])}`, "
                f"props=`{len(structured.get('prop_asset_ids') or [])}`, "
                f"action_beats=`{structured.get('action_beats_count')}`"
            )
        preview = item.get("compiled_prompt_preview", {}) if isinstance(item.get("compiled_prompt_preview", {}), dict) else {}
        if preview:
            static_preview = str(preview.get("static") or "").replace("\n", " ")[:180]
            motion_preview = str(preview.get("motion") or "").replace("\n", " ")[:180]
            lines.append(f"  - static_preview: {static_preview}")
            lines.append(f"  - motion_preview: {motion_preview}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def run_gray_validation() -> None:
    mode = validate_gate()
    if mode is None:
        return

    init_db()
    samples = select_samples(parse_book_ids(), sample_count())
    log("Selected samples: " + ", ".join(f"#{item['book_id']}:{item['episode']}:{item['shot_id']}" for item in samples))
    client = TestClient(batch.helper.app)
    results = [validate_sample(client, sample, mode) for sample in samples]
    summary = summarize(results)
    json_path, md_path = write_reports(mode, results, summary)
    log(
        "Gray validation summary: "
        f"samples={summary['samples']}, passed={summary['passed']}, failed={summary['failed']}, "
        f"after_errors={summary['after_errors']}, after_warnings={summary['after_warnings']}, "
        f"total_elapsed={summary['total_elapsed_seconds']}s"
    )
    log(f"JSON report written: {json_path}")
    log(f"Markdown report written: {md_path}")
    if summary["failed"] > 0 or summary["after_errors"] > 0:
        raise RuntimeError("Storyboard real LLM gray validation failed; inspect the generated report.")


if __name__ == "__main__":
    run_gray_validation()
