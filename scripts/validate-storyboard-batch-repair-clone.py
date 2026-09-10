"""Validate batch-style reversible storyboard prompt repair on real failing samples.

This script does not mutate real project rows. It selects real storyboard shots
that currently fail the prompt audit baseline, clones each one into a temporary
book with source prompt text preserved, repairs the clone through the normal
backend compile API, rolls the clone back to baseline, and removes the temp data.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("VALIDATE_STORYBOARD_REPAIR_TEMP_BOOK_ID", "999905")

HELPER_PATH = ROOT_DIR / "scripts" / "validate-storyboard-quality-repair-clone.py"
spec = importlib.util.spec_from_file_location("storyboard_repair_clone_helper", HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load helper script: {HELPER_PATH}")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

from models import Book, Session, StoryboardShot, init_db


DEFAULT_BOOK_IDS = "14,5,75,3,1"
DEFAULT_TARGET_SHOT_COUNT = 10
MIN_STATIC_LENGTH = int(os.environ.get("BATCH_REPAIR_MIN_STATIC_LENGTH", "80"))
MIN_MOTION_LENGTH = int(os.environ.get("BATCH_REPAIR_MIN_MOTION_LENGTH", "50"))
BATCH_REPAIR_INCLUDE_WARNINGS = os.environ.get("BATCH_REPAIR_INCLUDE_WARNINGS") == "1"
BATCH_REPAIR_WARNING_CODES = {
    token.strip()
    for token in os.environ.get("BATCH_REPAIR_WARNING_CODES", "").split(",")
    if token.strip()
}
INTERNAL_REPAIR_MARKERS = (
    "真实项目灰度修复",
    "真实项目克隆",
    "deterministic",
    "E2E storyboard prompt mock",
)
GENERIC_MOTION_MARKERS = (
    "按原分镜过程自然推进",
    "最后停在关键反应瞬间",
    "情绪逐步增强",
)


def log(message: str) -> None:
    print(f"[storyboard-batch-repair] {message}")


def parse_book_ids() -> list[int]:
    raw = os.environ.get("BATCH_REPAIR_BOOK_IDS", DEFAULT_BOOK_IDS)
    book_ids: list[int] = []
    for token in raw.split(","):
        value = token.strip()
        if not value:
            continue
        book_ids.append(int(value))
    if not book_ids:
        raise RuntimeError("No BATCH_REPAIR_BOOK_IDS configured.")
    return book_ids


def target_shot_count() -> int:
    return max(1, int(os.environ.get("BATCH_REPAIR_SHOT_COUNT", str(DEFAULT_TARGET_SHOT_COUNT))))


def parse_repair_targets() -> list[tuple[int, int, int]]:
    raw = os.environ.get("BATCH_REPAIR_TARGETS", "").strip()
    if not raw:
        return []
    targets: list[tuple[int, int, int]] = []
    for token in raw.split(","):
        parts = [part.strip() for part in token.strip().split(":")]
        if len(parts) != 3 or not all(parts):
            raise RuntimeError(
                "BATCH_REPAIR_TARGETS must use comma-separated book_id:episode:shot_id entries."
            )
        targets.append((int(parts[0]), int(parts[1]), int(parts[2])))
    return targets


def structured_from_meta(meta: dict[str, Any]) -> dict[str, Any]:
    if isinstance(meta.get("structured_shot"), dict):
        return meta["structured_shot"]
    prompt_compiler = meta.get("prompt_compiler")
    if isinstance(prompt_compiler, dict) and isinstance(prompt_compiler.get("structured_shot"), dict):
        return prompt_compiler["structured_shot"]
    return {}


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _scene_match_text(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .replace("·", "")
        .replace("・", "")
        .replace("•", "")
        .replace(" ", "")
        .replace("\t", "")
        .replace("\n", "")
        .replace("-", "")
        .replace("—", "")
        .replace("_", "")
        .replace("/", "")
        .replace("\\", "")
        .replace("，", "")
        .replace("。", "")
        .replace("、", "")
        .replace("；", "")
        .replace("：", "")
        .replace("（", "")
        .replace("）", "")
        .replace("(", "")
        .replace(")", "")
    )


def _scene_name_parts(scene_text: str) -> list[str]:
    return [
        item
        for item in re.split(r"[·・•\s\t\n\r\-_/\\—，。；：:、（）()]+", str(scene_text or "").strip())
        if len(item.strip()) >= 2
    ]


def _static_prompt_contains_scene_name(static_text: str, scene_text: str) -> bool:
    if not scene_text:
        return True
    if scene_text in static_text:
        return True
    normalized_scene = _scene_match_text(scene_text)
    normalized_static = _scene_match_text(static_text)
    if normalized_scene and normalized_scene in normalized_static:
        return True
    parts = _scene_name_parts(scene_text)
    return bool(len(parts) >= 2 and all(_scene_match_text(part) in normalized_static for part in parts))


def _structured_action_text(structured: dict[str, Any]) -> str:
    beats = structured.get("action_beats") if isinstance(structured, dict) else []
    if not isinstance(beats, list):
        return ""
    return " ".join(
        str(item.get("description") or "")
        for item in beats
        if isinstance(item, dict) and str(item.get("description") or "").strip()
    )


def _is_expected_characterless_snapshot(scene_name: Any, structured: dict[str, Any] | None) -> bool:
    structured = structured or {}
    text = " ".join([
        str(scene_name or ""),
        str(structured.get("camera_angle") or ""),
        str(structured.get("start_state") or ""),
        str(structured.get("action_process") or ""),
        str(structured.get("end_state") or ""),
        str(structured.get("dialogue") or ""),
        _structured_action_text(structured),
    ])
    object_or_screen_focus_terms = (
        "监控画面",
        "监控屏",
        "屏幕",
        "画面静止",
        "照片",
        "杯子印记",
        "水渍",
        "台面",
        "物件",
        "道具",
        "空镜",
        "空无一人",
        "无人物",
        "无人物形象",
        "只见手",
        "手从画面",
        "第一人称",
        "高空",
        "树冠",
        "泥地",
        "乱葬岗",
        "坟茔",
        "墓碑",
        "铜钟",
        "钟楼",
        "鳞片",
        "鱼鳞",
        "蛇鳞",
        "布条缝隙",
    )
    human_action_terms = (
        "说",
        "低声",
        "看",
        "盯",
        "走",
        "坐",
        "站",
        "转身",
        "表情",
        "眼神",
        "身体",
    )
    dialogue = str(structured.get("dialogue") or "").strip()
    has_dialogue = bool(
        dialogue
        and not _contains_any(dialogue, ("无台词", "无对白", "内心独白", "旁白", "风声", "环境声"))
    )
    has_human_action = _contains_any(str(structured.get("action_process") or ""), human_action_terms)
    return _contains_any(text, object_or_screen_focus_terms) and not has_dialogue and not has_human_action


def audit_snapshot(
    *,
    static_prompt: Any,
    motion_prompt: Any,
    scene_name: Any,
    structured: dict[str, Any] | None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    static_text = str(static_prompt or "").strip()
    motion_text = str(motion_prompt or "").strip()
    scene_text = str(scene_name or "").strip()
    structured = structured or {}
    diagnostics = diagnostics or {}
    issues: list[str] = []
    warnings: list[str] = []

    if not static_text:
        issues.append("missing_static_prompt")
    elif len(static_text) < MIN_STATIC_LENGTH:
        issues.append("short_static_prompt")
    if not motion_text:
        issues.append("missing_motion_prompt")
    elif len(motion_text) < MIN_MOTION_LENGTH:
        issues.append("short_motion_prompt")
    if _contains_any(static_text, INTERNAL_REPAIR_MARKERS) or _contains_any(motion_text, INTERNAL_REPAIR_MARKERS):
        issues.append("internal_repair_marker_in_prompt")
    if _contains_any(motion_text, GENERIC_MOTION_MARKERS):
        issues.append("generic_motion_prompt")
    if not str(structured.get("scene_asset_id") or "").strip():
        issues.append("missing_structured_scene_asset")

    blocking = diagnostics.get("blocking_issues") if isinstance(diagnostics, dict) else []
    if isinstance(blocking, list) and blocking:
        issues.append("compiler_blocking_issues_present")

    if scene_text and static_text and not _static_prompt_contains_scene_name(static_text, scene_text):
        warnings.append("scene_name_not_in_static_prompt")
    if not structured.get("character_asset_ids") and not _is_expected_characterless_snapshot(scene_name, structured):
        warnings.append("missing_structured_character_assets")
    if not structured.get("action_beats"):
        warnings.append("missing_action_beats")

    return {
        "issues": issues,
        "warnings": warnings,
        "prompt_lengths": {
            "static": len(static_text),
            "motion": len(motion_text),
        },
        "structured_scene_asset_id": str(structured.get("scene_asset_id") or "").strip(),
    }


def audit_source_shot(shot: StoryboardShot) -> dict[str, Any]:
    meta = helper.safe_json_loads(shot.meta_info, {})
    return audit_snapshot(
        static_prompt=shot.visual_prompt_static,
        motion_prompt=shot.visual_prompt_motion,
        scene_name=shot.scene_name,
        structured=structured_from_meta(meta),
        diagnostics=meta.get("compiler_diagnostics") if isinstance(meta.get("compiler_diagnostics"), dict) else {},
    )


def select_failing_samples(book_ids: list[int], limit: int) -> list[dict[str, Any]]:
    explicit_targets = parse_repair_targets()
    if explicit_targets:
        samples: list[dict[str, Any]] = []
        with Session() as session:
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
                samples.append({
                    "book_id": book_id,
                    "book_title": book.title,
                    "episode": int(shot.episode or 1),
                    "shot_id": int(shot.shot_id),
                    "scene_name": shot.scene_name,
                    "source_audit": audit_source_shot(shot),
                })
        log(
            "Using explicit targets: "
            + ", ".join(f"#{item['book_id']}:{item['episode']}:{item['shot_id']}" for item in samples)
        )
        return samples[:limit]

    by_book: dict[int, list[dict[str, Any]]] = {}
    with Session() as session:
        books = {int(book.id): book for book in session.query(Book).filter(Book.id.in_(book_ids)).all()}
        for book_id in book_ids:
            book = books.get(book_id)
            if not book:
                continue
            rows = (
                session.query(StoryboardShot)
                .filter(StoryboardShot.book_id == book_id)
                .order_by(StoryboardShot.episode.asc(), StoryboardShot.shot_id.asc())
                .all()
            )
            failing: list[dict[str, Any]] = []
            for shot in rows:
                audit = audit_source_shot(shot)
                warning_match = (
                    BATCH_REPAIR_INCLUDE_WARNINGS
                    and bool(audit["warnings"])
                    and (
                        not BATCH_REPAIR_WARNING_CODES
                        or bool(set(audit["warnings"]) & BATCH_REPAIR_WARNING_CODES)
                    )
                )
                if not audit["issues"] and not warning_match:
                    continue
                failing.append({
                    "book_id": book_id,
                    "book_title": book.title,
                    "episode": int(shot.episode or 1),
                    "shot_id": int(shot.shot_id),
                    "scene_name": shot.scene_name,
                    "source_audit": audit,
                })
            failing.sort(
                key=lambda item: (
                    -len(item["source_audit"]["issues"]),
                    -len(item["source_audit"]["warnings"]),
                    item["episode"],
                    item["shot_id"],
                )
            )
            by_book[book_id] = failing
            log(f"#{book_id}: failing candidates={len(failing)}")

    if not any(by_book.values()):
        raise RuntimeError("No failing storyboard shots found in configured books.")

    per_book = max(1, math.ceil(limit / max(1, len(book_ids))))
    selected: list[dict[str, Any]] = []
    seen: set[tuple[int, int, int]] = set()
    for book_id in book_ids:
        for item in by_book.get(book_id, [])[:per_book]:
            key = (item["book_id"], item["episode"], item["shot_id"])
            if key not in seen and len(selected) < limit:
                selected.append(item)
                seen.add(key)
    for book_id in book_ids:
        for item in by_book.get(book_id, []):
            key = (item["book_id"], item["episode"], item["shot_id"])
            if key in seen:
                continue
            if len(selected) >= limit:
                break
            selected.append(item)
            seen.add(key)
    return selected


def repair_clone_sample(client: TestClient, sample: dict[str, Any]) -> dict[str, Any]:
    clone = helper.clone_source_to_temp(
        sample["book_id"],
        sample["episode"],
        sample["shot_id"],
        baseline_mode="source",
    )
    log(
        f"Cloned #{sample['book_id']} {sample['episode']}-{sample['shot_id']} "
        f"with source baseline into temp book #{clone['temp_book_id']}."
    )

    try:
        mock_payload = helper.build_mock_llm_payload(sample["episode"], sample["shot_id"])
        with patch("core.llm.call_llm_json", return_value=mock_payload):
            # The compiler now has a mandatory two-factor external-call gate.
            # This clone run is still fully local because call_llm_json is
            # patched above, but it must carry the same explicit consent fields
            # as the production route so the dry-run stays protocol-compatible.
            response = client.post(
                f"/api/books/{helper.TEMP_BOOK_ID}/storyboard/{clone['episode']}/{clone['shot_id']}/compile-prompts",
                json={
                    "compileReason": "batch-clone-quality-repair",
                    "force": True,
                    "confirmed": True,
                    "allowExternalCall": True,
                },
            )
        compiled = response.json() if response.content else {}
        repair_blocked = response.status_code != 200
        if repair_blocked:
            # A modern compiler can fail closed with a structured 422 when a
            # candidate still violates a production diagnostic.  Preserve that
            # candidate and diagnostics in the dry-run report instead of
            # crashing the entire batch preflight.  No real project is mutated
            # by this clone command, and the caller can review the exact
            # remaining blockers before deciding on a human-confirmed repair.
            detail = compiled.get("detail") if isinstance(compiled, dict) else None
            if isinstance(detail, dict):
                compiled = {
                    "compiler_diagnostics": detail.get("compiler_diagnostics") or {},
                    "candidate_output": detail.get("candidate_output") or {},
                    "blocked_message": detail.get("message") or "compile blocked",
                }
            else:
                raise RuntimeError(f"Compile failed: {response.status_code} {response.text}")
        with Session() as session:
            repaired_shot = (
                session.query(StoryboardShot)
                .filter(
                    StoryboardShot.book_id == helper.TEMP_BOOK_ID,
                    StoryboardShot.episode == clone["episode"],
                    StoryboardShot.shot_id == int(clone["shot_id"]),
                )
                .first()
            )
            if not repaired_shot:
                raise RuntimeError("Repaired clone disappeared before audit.")
            repaired_meta = helper.safe_json_loads(repaired_shot.meta_info, {})

        after_audit = audit_snapshot(
            static_prompt=(compiled.get("prompt_static")
                           or compiled.get("candidate_output", {}).get("visual_prompt_static")
                           or repaired_shot.visual_prompt_static),
            motion_prompt=(compiled.get("prompt_motion")
                           or compiled.get("candidate_output", {}).get("visual_prompt_motion")
                           or repaired_shot.visual_prompt_motion),
            scene_name=repaired_shot.scene_name,
            structured=structured_from_meta(repaired_meta),
            diagnostics=compiled.get("compiler_diagnostics") if isinstance(compiled.get("compiler_diagnostics"), dict) else {},
        )
        if repair_blocked:
            # No version was written when the compiler failed closed.  The
            # candidate diagnostics are retained above, while the before/after
            # quality comparison must not double-count those diagnostics as a
            # second set of persisted errors.
            after_audit = sample["source_audit"]

        rollback_response = client.post(
            f"/api/books/{helper.TEMP_BOOK_ID}/storyboard/{clone['episode']}/{clone['shot_id']}/prompt-versions/{clone['baseline_version_id']}/rollback",
            json={"reason": "batch-clone-quality-repair-rollback"},
        )
        if rollback_response.status_code != 200:
            raise RuntimeError(f"Rollback failed: {rollback_response.status_code} {rollback_response.text}")

        with Session() as session:
            rolled_back = (
                session.query(StoryboardShot)
                .filter(
                    StoryboardShot.book_id == helper.TEMP_BOOK_ID,
                    StoryboardShot.episode == clone["episode"],
                    StoryboardShot.shot_id == int(clone["shot_id"]),
                )
                .first()
            )
            if not rolled_back:
                raise RuntimeError("Clone disappeared before rollback verification.")
            rollback_meta = helper.safe_json_loads(rolled_back.meta_info, {})
            rollback_structured = structured_from_meta(rollback_meta)
            expected_scene_asset_id = str(clone.get("baseline_structured", {}).get("scene_asset_id") or "").strip()
            actual_scene_asset_id = str(rollback_structured.get("scene_asset_id") or "").strip()
            if rolled_back.visual_prompt_static != clone["baseline_static"] or rolled_back.visual_prompt_motion != clone["baseline_motion"]:
                raise RuntimeError("Rollback did not restore source baseline prompt text.")
            if actual_scene_asset_id != expected_scene_asset_id:
                raise RuntimeError("Rollback did not restore source baseline structured_shot.scene_asset_id.")

        return {
            **sample,
            "after_audit": after_audit,
            "repaired_version": compiled.get("version"),
            "repair_blocked": repair_blocked,
            "blocked_message": compiled.get("blocked_message") if repair_blocked else None,
            "diagnostics_status": compiled.get("compiler_diagnostics", {}).get("status")
            if isinstance(compiled.get("compiler_diagnostics"), dict)
            else None,
        }
    finally:
        helper.cleanup_temp_book()
        log(f"Cleaned temp book #{helper.TEMP_BOOK_ID}.")


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    before_errors = sum(len(item["source_audit"]["issues"]) for item in results)
    before_warnings = sum(len(item["source_audit"]["warnings"]) for item in results)
    after_errors = sum(len(item["after_audit"]["issues"]) for item in results)
    after_warnings = sum(len(item["after_audit"]["warnings"]) for item in results)
    repair_blocked = sum(1 for item in results if item.get("repair_blocked"))
    return {
        "samples": len(results),
        "before_errors": before_errors,
        "before_warnings": before_warnings,
        "after_errors": after_errors,
        "after_warnings": after_warnings,
        "error_reduction": before_errors - after_errors,
        "warning_reduction": before_warnings - after_warnings,
        "repair_blocked": repair_blocked,
    }


def write_report(results: list[dict[str, Any]], summary: dict[str, Any]) -> Path:
    artifacts_dir = ROOT_DIR / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    report_path = artifacts_dir / f"storyboard-batch-repair-clone-{helper.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    report_path.write_text(
        json.dumps(
            {
                "generatedAt": helper.datetime.utcnow().isoformat(),
                "tempBookId": helper.TEMP_BOOK_ID,
                "summary": summary,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return report_path


def validate_batch_repair() -> None:
    init_db()
    client = TestClient(helper.app)
    book_ids = parse_book_ids()
    limit = target_shot_count()
    samples = select_failing_samples(book_ids, limit)
    if not samples:
        raise RuntimeError("No batch repair samples selected.")
    log(
        "Selected samples: "
        + ", ".join(f"#{item['book_id']}:{item['episode']}:{item['shot_id']}" for item in samples)
    )

    results = [repair_clone_sample(client, sample) for sample in samples]
    summary = summarize(results)
    report_path = write_report(results, summary)
    log(
        "Batch clone repair summary: "
        f"samples={summary['samples']}, "
        f"errors {summary['before_errors']} -> {summary['after_errors']}, "
        f"warnings {summary['before_warnings']} -> {summary['after_warnings']}"
    )
    log(f"Report written: {report_path}")
    if summary["after_errors"] > 0:
        raise RuntimeError(f"Batch clone repair left {summary['after_errors']} error(s).")


if __name__ == "__main__":
    validate_batch_repair()
