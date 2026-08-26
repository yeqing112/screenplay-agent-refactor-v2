"""Apply a confirmed real-project scene asset readiness repair.

Default behavior is a safe refusal. Confirmed mode creates minimal draft
`VisualLocation` rows for storyboard scene names that currently cannot bind to
real scene assets. It does not create reference images and does not modify
storyboard shots; it only establishes the missing real asset prerequisite for
later prompt batch repair.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.server import _normalize_scene_asset_id
from models import Book, Session, StoryboardShot, VisualLocation, init_db


REPORT_PREFIX = "storyboard-scene-asset-apply"


def log(message: str) -> None:
    print(f"[storyboard-scene-assets-apply] {message}")


def explain_safe_refusal() -> None:
    log("Refused: real-project scene asset creation is disabled by default.")
    log("Run `npm run audit:scene-assets` first and review the generated JSON/Markdown report.")
    log("To create draft scene assets after explicit approval, provide:")
    log("  APPLY_STORYBOARD_SCENE_ASSETS_REAL=1")
    log("  APPLY_STORYBOARD_SCENE_ASSETS_REPORT=<artifacts/storyboard-scene-asset-readiness-*.json>")
    log("  APPLY_STORYBOARD_SCENE_ASSETS_CONFIRM=<confirmation token from that report>")
    log("No real project data was modified.")


def load_report(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT_DIR / path
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"Scene asset readiness report not found: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise RuntimeError("Scene asset readiness report must be a JSON object.")
    return report


def validate_apply_gate() -> dict[str, Any] | None:
    real_flag = os.environ.get("APPLY_STORYBOARD_SCENE_ASSETS_REAL") == "1"
    report_path = os.environ.get("APPLY_STORYBOARD_SCENE_ASSETS_REPORT", "").strip()
    confirm = os.environ.get("APPLY_STORYBOARD_SCENE_ASSETS_CONFIRM", "").strip()
    if not real_flag or not report_path or not confirm:
        explain_safe_refusal()
        return None

    report = load_report(report_path)
    expected = str(report.get("confirmationToken") or "").strip()
    if not expected or confirm != expected:
        raise RuntimeError("Confirmation token mismatch; refusing scene asset creation.")
    if report.get("mode") != "read-only-scene-asset-readiness":
        raise RuntimeError("Report mode is not read-only-scene-asset-readiness; refusing apply.")
    results = report.get("results", [])
    if not isinstance(results, list) or not results:
        raise RuntimeError("Report does not contain scene asset readiness results; refusing apply.")
    missing = [
        scene
        for item in results
        for scene in item.get("scenes", [])
        if isinstance(scene, dict) and scene.get("status") != "ready"
    ]
    if not missing:
        raise RuntimeError("Report contains no missing scene assets; refusing no-op apply.")
    return report


def scene_shots(session: Session, book_id: int, scene_name: str) -> list[StoryboardShot]:
    return (
        session.query(StoryboardShot)
        .filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.scene_name == scene_name,
        )
        .order_by(StoryboardShot.episode.asc(), StoryboardShot.shot_id.asc())
        .all()
    )


def build_location_payload(session: Session, book_id: int, scene_name: str, shots: list[StoryboardShot]) -> dict[str, Any]:
    book = session.get(Book, book_id)
    shot_ids = [f"{int(shot.episode or 1)}-{int(shot.shot_id)}" for shot in shots]
    episodes = sorted({int(shot.episode or 1) for shot in shots})
    lighting_values = [
        str(shot.lighting or "").strip()
        for shot in shots
        if str(shot.lighting or "").strip()
    ]
    action_samples = [
        str(shot.action_process or shot.start_state or shot.end_state or "").strip()
        for shot in shots[:4]
        if str(shot.action_process or shot.start_state or shot.end_state or "").strip()
    ]
    action_summary = "；".join(action_samples[:3])
    visual_prompt = (
        f"{scene_name}，由真实分镜场景名补齐的 draft 场景资产。"
        f"覆盖镜头：{', '.join(shot_ids[:12])}。"
        f"{' 分镜动作参考：' + action_summary if action_summary else ''}"
    )
    return {
        "book_id": book_id,
        "book_title": book.title if book else "",
        "name": scene_name,
        "category": "storyboard-derived-scene",
        "style": "",
        "description": (
            f"由分镜批量修复前置检查创建的最小场景资产；用于让真实项目 scene_name 能绑定到 VisualLocation。"
            f"后续仍需在资产中心补充正式场景描述和参考图。"
        ),
        "color_palette": "",
        "lighting_mood": "；".join(dict.fromkeys(lighting_values[:3])),
        "key_props": "[]",
        "episodes": json.dumps(episodes, ensure_ascii=False),
        "visual_prompt_zh": visual_prompt,
        "core_prompt_zh": visual_prompt,
        "importance": "medium",
        "notes": (
            "created-by=apply-storyboard-scene-asset-readiness; "
            "status=draft; requires-human-asset-refinement-before-production"
        ),
        "shot_ids": json.dumps(shot_ids, ensure_ascii=False),
        "asset_status": "draft",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }


def apply_scene_asset_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with Session() as session:
        for item in report["results"]:
            book_id = int(item["book_id"])
            for scene in item.get("scenes", []):
                if not isinstance(scene, dict) or scene.get("status") == "ready":
                    continue
                scene_name = str(scene.get("scene_name") or "").strip()
                if not scene_name or scene_name == "(empty scene_name)":
                    results.append({
                        "book_id": book_id,
                        "scene_name": scene_name,
                        "status": "skipped",
                        "reason": "empty scene_name cannot create VisualLocation safely",
                    })
                    continue
                existing_id = _normalize_scene_asset_id(book_id, scene_name)
                if existing_id:
                    results.append({
                        "book_id": book_id,
                        "scene_name": scene_name,
                        "status": "skipped",
                        "reason": "scene asset became bindable before apply",
                        "location_id": existing_id,
                    })
                    continue
                shots = scene_shots(session, book_id, scene_name)
                if not shots:
                    results.append({
                        "book_id": book_id,
                        "scene_name": scene_name,
                        "status": "skipped",
                        "reason": "no storyboard shots currently use this scene_name",
                    })
                    continue
                location = VisualLocation(**build_location_payload(session, book_id, scene_name, shots))
                session.add(location)
                session.flush()
                results.append({
                    "book_id": book_id,
                    "scene_name": scene_name,
                    "status": "created",
                    "location_id": location.id,
                    "asset_status": location.asset_status,
                    "affected_shots": len(shots),
                    "shots": [f"{int(shot.episode or 1)}-{int(shot.shot_id)}" for shot in shots],
                })
        session.commit()
    return results


def write_apply_report(results: list[dict[str, Any]]) -> Path:
    artifacts_dir = ROOT_DIR / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    report_path = artifacts_dir / f"{REPORT_PREFIX}-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    created = [item for item in results if item.get("status") == "created"]
    report_path.write_text(
        json.dumps(
            {
                "generatedAt": datetime.utcnow().isoformat(),
                "mode": "real-project-scene-asset-apply",
                "summary": {
                    "items": len(results),
                    "created": len(created),
                    "affected_shots": sum(int(item.get("affected_shots") or 0) for item in created),
                },
                "results": results,
                "note": "Created rows are draft VisualLocation prerequisites; refine them in Asset Center before production use.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return report_path


def apply_confirmed_scene_assets() -> None:
    report = validate_apply_gate()
    if report is None:
        return
    init_db()
    results = apply_scene_asset_report(report)
    report_path = write_apply_report(results)
    created = [item for item in results if item.get("status") == "created"]
    log(
        f"Scene asset apply summary: items={len(results)}, "
        f"created={len(created)}, "
        f"affectedShots={sum(int(item.get('affected_shots') or 0) for item in created)}"
    )
    log(f"Apply report written: {report_path}")
    if not created:
        raise RuntimeError("Confirmed scene asset apply did not create any VisualLocation rows.")


if __name__ == "__main__":
    apply_confirmed_scene_assets()
