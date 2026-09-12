"""Apply reviewed scene reference plan updates to VisualLocation rows.

This is the companion to `plan-storyboard-scene-reference-assets.py`.
It does not generate images. It only promotes scene assets after references
already exist, using the reviewed plan:

- replace draft scene descriptions with formal descriptions
- set asset_status=ref_ready
- set jimeng_ref_name / negative_prompt / shot_ids
- clean generated scene reference notes for the affected scene references

Safe by default; real writes require APPLY_SCENE_REFERENCE_PLAN_REAL=1 and the
plan confirmation token.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models import Session, VisualLocation, VisualReferenceAsset, init_db
from core.scene_reference_plan import scene_location_fingerprint


REPORT_PREFIX = "storyboard-scene-reference-plan-apply"


def load_plan(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT_DIR / path
    if not path.exists():
        raise RuntimeError(f"Scene reference plan not found: {path}")
    plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or plan.get("mode") != "readonly-scene-reference-plan":
        raise RuntimeError("Plan mode must be readonly-scene-reference-plan.")
    return plan


def validate_real_gate(plan: dict[str, Any]) -> bool:
    real = os.environ.get("APPLY_SCENE_REFERENCE_PLAN_REAL") == "1"
    if not real:
        return False
    expected = str(plan.get("confirmationToken") or "").strip()
    actual = os.environ.get("APPLY_SCENE_REFERENCE_PLAN_CONFIRM", "").strip()
    if not expected:
        raise RuntimeError("Plan does not contain confirmationToken; regenerate the plan before real apply.")
    if actual != expected:
        raise RuntimeError("Confirmation token mismatch; refusing scene reference plan apply.")
    return True


def planned_updates(plan: dict[str, Any]) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for item in plan.get("items") or []:
        if not isinstance(item, dict) or item.get("status") != "planned":
            continue
        planned = item.get("planned_asset_update") if isinstance(item.get("planned_asset_update"), dict) else {}
        patch = planned.get("visual_asset_patch") if isinstance(planned.get("visual_asset_patch"), dict) else {}
        location_id = item.get("location_id")
        if not location_id:
            continue
        updates.append({
            "scene_name": item.get("scene_name"),
            "location_id": int(location_id),
            "formal_description": str(planned.get("formal_description") or "").strip(),
            "lighting_mood": str(planned.get("lighting_mood") or "").strip(),
            "negative_prompt": str(patch.get("negative_prompt") or "").strip(),
            "jimeng_ref_name": str(patch.get("jimeng_ref_name") or f"@{item.get('scene_name')}").strip(),
            "shot_ids": [str(value).strip() for value in patch.get("shot_ids") or item.get("shot_ids") or [] if str(value).strip()],
            "source_fingerprint": str(item.get("source_fingerprint") or "").strip(),
        })
    return updates


def apply_updates(plan: dict[str, Any], updates: list[dict[str, Any]], real: bool) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if not real:
        return [
            {
                **item,
                "status": "dry_run",
            }
            for item in updates
        ]

    now = datetime.utcnow()
    with Session() as session:
        for item in updates:
            row = session.query(VisualLocation).filter(
                VisualLocation.book_id == int(plan.get("book_id")),
                VisualLocation.id == int(item["location_id"]),
            ).first()
            if row is None:
                results.append({**item, "status": "missing_visual_location"})
                continue
            expected_fingerprint = str(item.get("source_fingerprint") or "").strip()
            if not expected_fingerprint or scene_location_fingerprint(row) != expected_fingerprint:
                results.append({**item, "status": "stale", "reason": "scene asset changed after plan generation; regenerate the readonly plan"})
                continue
            refs = session.query(VisualReferenceAsset).filter(
                VisualReferenceAsset.book_id == int(plan.get("book_id")),
                VisualReferenceAsset.asset_type == "scene",
                VisualReferenceAsset.asset_id == str(item["location_id"]),
                VisualReferenceAsset.status.in_(["selected", "locked"]),
            ).all()
            refs_with_image = [
                ref for ref in refs
                if str(ref.image_url or "").strip() or str(ref.local_path or "").strip()
            ]
            if not refs_with_image:
                results.append({**item, "status": "blocked", "reason": "selected/locked scene reference image is still missing"})
                continue

            row.description = item["formal_description"] or row.description
            row.visual_prompt_zh = item["formal_description"] or row.visual_prompt_zh
            row.core_prompt_zh = item["formal_description"] or row.core_prompt_zh
            if item["lighting_mood"]:
                row.lighting_mood = item["lighting_mood"]
            row.negative_prompt = item["negative_prompt"] or row.negative_prompt
            row.jimeng_ref_name = item["jimeng_ref_name"] or row.jimeng_ref_name
            row.shot_ids = json.dumps(item["shot_ids"], ensure_ascii=False)
            row.asset_status = "ref_ready"
            row.notes = f"scene-reference-plan-applied; status=ref_ready; source=book{int(plan.get('book_id'))}-scene-reference-plan"
            row.updated_at = now

            cleaned_notes = 0
            for ref in refs:
                if "瑙" in str(ref.notes or ""):
                    ref.notes = f"视觉资产库生成 · {now.strftime('%Y-%m-%d %H:%M')}"
                    ref.updated_at = now
                    cleaned_notes += 1

            results.append({
                **item,
                "status": "updated",
                "selected_or_locked_references": len(refs_with_image),
                "cleaned_reference_notes": cleaned_notes,
            })
        session.commit()
    return results


def write_report(plan_path: str, real: bool, updates: list[dict[str, Any]], results: list[dict[str, Any]]) -> Path:
    artifacts_dir = ROOT_DIR / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    path = artifacts_dir / f"{REPORT_PREFIX}-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    updated = [item for item in results if item.get("status") == "updated"]
    path.write_text(
        json.dumps(
            {
                "generatedAt": datetime.utcnow().isoformat(),
                "mode": "real-apply" if real else "dry-run",
                "planPath": plan_path,
                "summary": {
                    "updates": len(updates),
                    "updated": len(updated),
                    "blocked": sum(1 for item in results if item.get("status") == "blocked"),
                },
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply reviewed scene reference plan updates.")
    parser.add_argument("--plan", default="artifacts/book75-scene-reference-plan.json")
    args = parser.parse_args()

    init_db()
    plan = load_plan(args.plan)
    updates = planned_updates(plan)
    if not updates:
        raise RuntimeError("Plan contains no planned scene updates.")
    real = validate_real_gate(plan)
    results = apply_updates(plan, updates, real)
    report = write_report(args.plan, real, updates, results)
    if real:
        print(f"Scene reference plan apply report written: {report}")
    else:
        print("Dry-run only. Real apply requires:")
        print("  APPLY_SCENE_REFERENCE_PLAN_REAL=1")
        print(f"  APPLY_SCENE_REFERENCE_PLAN_CONFIRM={plan.get('confirmationToken')}")
        print(f"Dry-run report written: {report}")
    blocked = [item for item in results if item.get("status") == "blocked"]
    if blocked:
        raise RuntimeError("Scene reference plan apply still has blocked item(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
