"""Resume/finalize an interrupted autonomous scene canary without new setup.

This helper is used when the isolated provider process has already produced a
master and derived candidates but the local orchestration process stopped while
entering the repair loop.  It consumes the same isolated database, enforces the
remaining seven-call budget, and always writes a terminal READY or FAILED audit.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path
import shutil
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.autonomous_asset_generation import (  # noqa: E402
    AssetGenerationBudgetPolicy,
    AssetRepairContext,
    AutonomousAssetGeneration,
    AutonomousAssetState,
    SceneConsistencyAudit,
    geometry_constrained_prompt,
)
from api.model_registry import get_profile  # noqa: E402
from scripts.run_autonomous_scene_asset_pipeline_v1 import (  # noqa: E402
    BASELINE,
    BOOK_ID,
    EPISODE,
    GEOMETRY,
    NEGATIVE,
    OUT,
    PLANS,
    PROFILE_ID,
    SCENE_ID,
    _compose_board,
    _image_meta,
    _judge,
    _master_prompt,
    _normalized_audit,
    _submit_view,
    _wait_for_health,
)
from scripts.run_asset_media_canary_v1 import _free_port, _write


def _task_rows(db: Path) -> list[dict]:
    import sqlite3
    conn = sqlite3.connect(db)
    rows = conn.execute("select task_id,payload from task_runs where task_kind='creative-reference-image' and book_id=? order by updated_at asc", (BOOK_ID,)).fetchall()
    output = []
    for task_id, payload in rows:
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            value = {}
        output.append({"task_id": task_id, "payload": value})
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    run_dir = Path(args.run_dir).resolve()
    db = run_dir / "screenplay.db"
    if not db.exists():
        raise SystemExit(f"missing isolated run database: {db}")
    task_rows = _task_rows(db)
    if len(task_rows) < 4:
        raise SystemExit("resume requires master plus three derived task rows")

    budget = AssetGenerationBudgetPolicy(normal_calls_max=7, max_attempts_per_view=3)
    runtime = AutonomousAssetGeneration(asset_type="SCENE", asset_id=SCENE_ID, budget=budget)
    runtime.plan_scene(GEOMETRY, PLANS)
    runtime.image_calls = len(task_rows)
    runtime.state = AutonomousAssetState.PRIMARY_READY
    paths = {view_id: OUT / f"scene-{view_id.lower()}.jpg" for view_id in ("MASTER", "REVERSE", "SIDE", "DETAIL")}
    if not all(path.exists() for path in paths.values()):
        raise SystemExit("tracked scene outputs are incomplete; cannot resume safely")
    runtime.media = {key: {"path": str(path), "fingerprint": _image_meta(path)["sha256"]} for key, path in paths.items()}
    for plan in PLANS:
        runtime.record_derived(plan.view_id, runtime.media[plan.view_id])

    port = _free_port()
    uploads = run_dir / "uploads"
    env = os.environ.copy()
    env.update({"DATABASE_URL": f"sqlite:///{db.as_posix()}?timeout=30", "UPLOAD_DIR": str(uploads), "DEPLOYMENT_ENV": "isolated", "APP_ENV": "test", "E2E_EXTERNAL_RUNTIME": ""})
    log = (run_dir / "uvicorn-resume.log").open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base_url = f"http://127.0.0.1:{port}"
    events = [{"view_id": "MASTER" if "MASTER" in (row["payload"].get("asset") or {}).get("title", "") else "REVERSE" if "REVERSE" in (row["payload"].get("asset") or {}).get("title", "") else "SIDE" if "SIDE" in (row["payload"].get("asset") or {}).get("title", "") else "DETAIL", "attempt": index + 1, "kind": "RESUMED_EXISTING_GENERATION"} for index, row in enumerate(task_rows)]
    audit_rows: list[SceneConsistencyAudit] = []
    repairs: list[AssetRepairContext] = []
    try:
        _wait_for_health(base_url, timeout=180)
        os.environ["DATABASE_URL"] = env["DATABASE_URL"]
        vision_profile = get_profile("local-llm-2vydoz")
        judge_status, judge = _judge(vision_profile, paths)
        for plan in PLANS:
            row = _normalized_audit(plan.view_id, (judge.get("views") or {}).get(plan.view_id, {}), 2 if plan.view_id == "REVERSE" else 1, judge_status)
            runtime.record_audit(row); audit_rows.append(row)
        async def repair_one(view_id: str, prompt: str) -> dict:
            async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                return await _submit_view(client, base_url, view_id, prompt, paths[view_id])
        for plan in PLANS:
            while True:
                latest = next((item for item in reversed(audit_rows) if item.view_id == plan.view_id), None)
                if latest and latest.passes:
                    break
                attempts = latest.attempt_number if latest else 1
                if attempts >= budget.max_attempts_per_view or runtime.image_calls >= budget.normal_calls_max:
                    break
                corrections = [f"保持 {landmark} 的位置和材质" for landmark in plan.required_landmarks] + ["必须与 MASTER 是同一物理房间，禁止更换门、窗、水槽、橱柜、餐桌"]
                context = AssetRepairContext(view_id=plan.view_id, previous_prompt=geometry_constrained_prompt(GEOMETRY, plan), failed_output={}, violations=latest.violations if latest else ["judge failed"], required_corrections=corrections, attempt_number=attempts + 1)
                runtime.prepare_repair(context); repairs.append(context); runtime.claim_image_call()
                result = asyncio.run(repair_one(plan.view_id, geometry_constrained_prompt(GEOMETRY, plan, repair=context)))
                runtime.record_derived(plan.view_id, result); events.append({"view_id": plan.view_id, "attempt": attempts + 1, "kind": "REPAIRING", "call": runtime.image_calls, "corrections": corrections})
                judge_status, judge = _judge(vision_profile, paths)
                row = _normalized_audit(plan.view_id, (judge.get("views") or {}).get(plan.view_id, {}), attempts + 1, judge_status)
                runtime.record_audit(row); audit_rows.append(row)
        latest_by_view = {row.view_id: row for row in audit_rows}
        try:
            authority = runtime.lock()
        except RuntimeError:
            authority = None
        board = _compose_board(paths, OUT / "scene-reference-board.png")
        audit_payload = {"schema_version": "scene_consistency_audit_v1", "scene_id": SCENE_ID, "judge_status": judge_status, "judge": judge, "views": [asdict(row) for row in audit_rows], "latest_views": {key: asdict(value) for key, value in latest_by_view.items()}, "thresholds": asdict(budget)}
        repair_payload = {"schema_version": "asset_repair_history_v1", "repairs": [asdict(item) for item in repairs], "generation_events": events}
        manifest = {"schema_version": "autonomous_asset_pipeline_audit_v1", "status": "AUTONOMOUS_SCENE_ASSET_PIPELINE_READY" if authority else "ASSET_CONSISTENCY_GENERATION_FAILED", "scene_id": SCENE_ID, "state": runtime.state.value, "manual_approvals_required": 0, "manual_view_selection": 0, "result": "READY" if authority else "FAILED", "geometry": {**asdict(GEOMETRY), "fingerprint": GEOMETRY.fingerprint, "authority": "topology"}, "derived_route": "GEOMETRY_CONSTRAINED_TEXT_DERIVATION", "image_capabilities": {"image_reference_input": False, "image_edit": False, "image_text_only": True}, "generation": {"master_calls": 1, "reverse_calls": sum(1 for event in events if event["view_id"] == "REVERSE"), "side_calls": sum(1 for event in events if event["view_id"] == "SIDE"), "detail_calls": sum(1 for event in events if event["view_id"] == "DETAIL"), "repair_calls": len(repairs), "total_image_calls": runtime.image_calls}, "consistency": audit_payload, "authority": authority, "final_board": board, "real_image_calls": runtime.image_calls, "real_video_calls": 0, "v0_failed_baseline": str(OUT / "scene-v0-failed-baseline.jpg")}
        _write(OUT / "SCENE_GEOMETRY_IR.json", {**asdict(GEOMETRY), "fingerprint": GEOMETRY.fingerprint, "authority": "topology"}); _write(OUT / "SCENE_DERIVED_VIEW_PLANS.json", [asdict(plan) for plan in PLANS]); _write(OUT / "SCENE_CONSISTENCY_AUDIT.json", audit_payload); _write(OUT / "SCENE_REPAIR_HISTORY.json", repair_payload); _write(OUT / "AUTONOMOUS_ASSET_PIPELINE_AUDIT.json", manifest); _write(OUT / "SCENE_AUTHORITY.json", authority or {"status": "FAILED", "scene_id": SCENE_ID, "geometry_fingerprint": GEOMETRY.fingerprint})
        lines = ["# Autonomous Visual Asset Pipeline V1 Report", "", f"- Status: `{manifest['status']}`", f"- Scene: `{SCENE_ID}`", "- Manual approvals required: `0`", "- Manual view selection: `0`", "- Derived route: `GEOMETRY_CONSTRAINED_TEXT_DERIVATION`", f"- Visual judge: `{judge_status}`", "", "## Generation", "", f"- Master calls: `1`", f"- Reverse calls: `{manifest['generation']['reverse_calls']}`", f"- Side calls: `{manifest['generation']['side_calls']}`", f"- Detail calls: `{manifest['generation']['detail_calls']}`", f"- Repair calls: `{manifest['generation']['repair_calls']}`", f"- Total IMAGE calls: `{runtime.image_calls}`", "- Real VIDEO calls: `0`", "", "## Geometry", "", "- window: LEFT wall", "- sink: LEFT wall, directly below window", "- door: REAR_RIGHT zone", "- table: CENTER_FOREGROUND", "- cabinet: BACK wall", "- Geometry IR is topology authority; the Master image is its visual implementation.", "", "## Consistency", ""]
        for view_id in ("REVERSE", "SIDE", "DETAIL"):
            row = latest_by_view.get(view_id); lines.append(f"- `{view_id}`: `{row.status if row else 'MISSING'}`; architecture={row.architecture_score if row else 0}, landmarks={row.landmark_score if row else 0}, furniture={row.furniture_score if row else 0}, lighting={row.lighting_score if row else 0}; critical={row.critical_topology_violations if row else []}")
        lines.extend(["", "## Automatic repair", "", f"- Views repaired: `{sorted({item.view_id for item in repairs})}`", f"- Repair attempts: `{len(repairs)}`", "- No human approval or view selection was requested.", "", "The old 2×2 generated scene is retained as `scene-v0-failed-baseline.jpg`; it is not Scene Authority.", ""])
        (OUT / "AUTONOMOUS_ASSET_PIPELINE_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
        print(json.dumps({"status":manifest["status"],"state":runtime.state.value,"judge_status":judge_status,"image_calls":runtime.image_calls,"video_calls":0,"output":str(OUT)},ensure_ascii=False,indent=2))
        return 0 if authority else 2
    finally:
        process.terminate()
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
