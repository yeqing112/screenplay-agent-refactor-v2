"""Enqueue real scene reference image generation from a reviewed plan.

Safe by default:

- without ENQUEUE_SCENE_REFERENCES_REAL=1 it only writes a dry-run report
- real execution requires the confirmation token embedded in the plan
- only `planned` scene items with a complete API request are submitted

The script uses the project's existing creative generation task pipeline, so
completed images are persisted as selected VisualReferenceAsset rows by the
same code path the UI uses.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.server import (
    CreativeGenerationRequest,
    _creative_tasks,
    _enqueue_creative_task,
    _run_creative_task,
)


REPORT_PREFIX = "storyboard-scene-reference-generation"


class ImmediateBackgroundTasks:
    """Collect background tasks without running them automatically."""

    def __init__(self) -> None:
        self.tasks: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []

    def add_task(self, func, *args, **kwargs) -> None:
        self.tasks.append((func, args, kwargs))


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


def planned_requests(plan: dict[str, Any]) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for item in plan.get("items") or []:
        if not isinstance(item, dict) or item.get("status") != "planned":
            continue
        generation = item.get("reference_generation") if isinstance(item.get("reference_generation"), dict) else {}
        request_payload = generation.get("api_request") if isinstance(generation.get("api_request"), dict) else {}
        if not request_payload:
            continue
        requests.append({
            "scene_name": item.get("scene_name"),
            "location_id": item.get("location_id"),
            "shot_count": item.get("shot_count"),
            "api_request": request_payload,
        })
    return requests


def filter_requests(
    requests: list[dict[str, Any]],
    scene_name: str = "",
    limit: int = 0,
) -> list[dict[str, Any]]:
    selected = requests
    if scene_name:
        selected = [
            item for item in selected
            if str(item.get("scene_name") or "").strip() == scene_name.strip()
        ]
    if limit > 0:
        selected = selected[:limit]
    return selected


def validate_real_gate(plan: dict[str, Any]) -> bool:
    real = os.environ.get("ENQUEUE_SCENE_REFERENCES_REAL") == "1"
    if not real:
        return False
    expected = str(plan.get("confirmationToken") or "").strip()
    actual = os.environ.get("ENQUEUE_SCENE_REFERENCES_CONFIRM", "").strip()
    if not expected:
        raise RuntimeError("Plan does not contain confirmationToken; regenerate the plan before real enqueue.")
    if actual != expected:
        raise RuntimeError("Confirmation token mismatch; refusing real scene reference generation.")
    return True


async def enqueue_one(request_payload: dict[str, Any], run_now: bool) -> dict[str, Any]:
    req = CreativeGenerationRequest.model_validate(request_payload)
    bg = ImmediateBackgroundTasks()
    queued = await _enqueue_creative_task(req, bg, "reference-image")
    task_id = str(queued.get("task_id") or "").strip()
    result: dict[str, Any] = {
        "task_id": task_id,
        "queued": queued,
        "ran_now": False,
        "final_task": None,
    }
    if run_now and task_id:
        await _run_creative_task(task_id, "reference-image", req)
        result["ran_now"] = True
        result["final_task"] = _creative_tasks.get(task_id)
    return result


def write_report(plan_path: str, real: bool, results: list[dict[str, Any]], requests: list[dict[str, Any]], error: str = "") -> Path:
    artifacts_dir = ROOT_DIR / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    path = artifacts_dir / f"{REPORT_PREFIX}-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    done = [
        item for item in results
        if isinstance(item.get("final_task"), dict) and item["final_task"].get("status") == "done"
    ]
    failed = [
        item for item in results
        if item.get("error") or (isinstance(item.get("final_task"), dict) and item["final_task"].get("status") == "error")
    ]
    path.write_text(
        json.dumps(
            {
                "generatedAt": datetime.utcnow().isoformat(),
                "mode": "real-enqueue" if real else "dry-run",
                "planPath": plan_path,
                "summary": {
                    "requests": len(requests),
                    "submitted": len(results),
                    "done": len(done),
                    "failed": len(failed),
                    "error": bool(error or failed),
                },
                "requests": requests,
                "results": results,
                "error": error,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


async def run(args: argparse.Namespace) -> int:
    plan = load_plan(args.plan)
    requests = filter_requests(planned_requests(plan), scene_name=args.scene_name, limit=args.limit)
    real = validate_real_gate(plan)
    if not requests:
        raise RuntimeError("Plan contains no planned scene reference generation requests.")

    if not real:
        report = write_report(args.plan, False, [], requests)
        print(f"Dry-run only. Real enqueue requires:")
        print("  ENQUEUE_SCENE_REFERENCES_REAL=1")
        print(f"  ENQUEUE_SCENE_REFERENCES_CONFIRM={plan.get('confirmationToken')}")
        print(f"Dry-run report written: {report}")
        return 0

    results: list[dict[str, Any]] = []
    error = ""
    for index, item in enumerate(requests, start=1):
        try:
            print(
                f"[scene-reference-generation] ({index}/{len(requests)}) submitting "
                f"{item.get('scene_name')} / location {item.get('location_id')}...",
                flush=True,
            )
            payload = dict(item["api_request"])
            if args.model_profile_id:
                payload["modelProfileId"] = args.model_profile_id
            result = {
                "scene_name": item.get("scene_name"),
                "location_id": item.get("location_id"),
                **await enqueue_one(payload, run_now=not args.queue_only),
            }
            results.append(result)
            final_task = result.get("final_task") if isinstance(result.get("final_task"), dict) else {}
            print(
                f"[scene-reference-generation] ({index}/{len(requests)}) finished "
                f"{item.get('scene_name')} status={final_task.get('status') or 'queued'}",
                flush=True,
            )
        except Exception as exc:
            error = str(exc)
            results.append({
                "scene_name": item.get("scene_name"),
                "location_id": item.get("location_id"),
                "error": error,
            })
            if not args.continue_on_error:
                break

    report = write_report(args.plan, True, results, requests, error)
    print(f"Generation enqueue report written: {report}")
    if error:
        raise RuntimeError(error)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Enqueue reviewed scene reference generation requests.")
    parser.add_argument("--plan", default="artifacts/book75-scene-reference-plan.json")
    parser.add_argument("--model-profile-id", default="")
    parser.add_argument("--queue-only", action="store_true", help="Queue tasks but do not run provider submission in this process.")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--scene-name", default="", help="Only submit the planned request for this exact scene name.")
    parser.add_argument("--limit", type=int, default=0, help="Submit at most N planned requests after filtering.")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
