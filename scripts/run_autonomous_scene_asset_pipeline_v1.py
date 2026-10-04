"""Run the autonomous E01_SC002 scene asset pipeline.

The run is deliberately isolated from the production database.  It uses the
canonical reference-image API for one master and three derived single views,
then invokes the configured vision-capable LLM as a structured judge.  Failed
views are repaired automatically up to the shared image budget; no view is
manually approved or selected.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.autonomous_asset_generation import (  # noqa: E402
    AssetGenerationBudgetPolicy,
    AssetRepairContext,
    AutonomousAssetGeneration,
    SceneConsistencyAudit,
    SceneDerivedViewPlan,
    SceneGeometryIR,
    geometry_constrained_prompt,
)
from scripts.run_asset_media_canary_v1 import (  # noqa: E402
    _free_port,
    _image_meta,
    _redact,
    _wait_for_health,
    _write,
)


BOOK_ID = 990402
EPISODE = 1
SCENE_ID = "E01_SC002"
PROFILE_ID = "local-image-mw4y52"
VISION_PROFILE_ID = "local-llm-2vydoz"
SOURCE_DB = ROOT / "work" / "db" / "screenplay.db"
OUT = ROOT / "docs" / "visual-assets" / "autonomous-v1"
BASELINE = ROOT / "docs" / "prompt-quality" / "media-canary-v1" / "originals" / "03-kitchen.jpg"


GEOMETRY = SceneGeometryIR(
    scene_id=SCENE_ID,
    walls=["LEFT", "BACK", "RIGHT", "FRONT"],
    zones=["KITCHEN_REAR", "DINING_CENTER_FOREGROUND", "KITCHEN_DOOR_RIGHT", "WINDOW_LEFT"],
    doors=[{"id": "kitchen_door", "zone": "REAR_RIGHT", "wall": "RIGHT", "opens_to": "living_room"}],
    windows=[{"id": "left_window", "wall": "LEFT", "zone": "WINDOW_LEFT", "daylight": "cool_overcast"}],
    fixed_furniture=[
        {"id": "sink", "wall": "LEFT", "relation": "directly_below_left_window"},
        {"id": "cabinet", "wall": "BACK", "relation": "behind_sink_and_counter"},
        {"id": "dining_table", "zone": "CENTER_FOREGROUND", "relation": "between_camera_and_sink"},
        {"id": "two_chairs", "zone": "CENTER_FOREGROUND", "relation": "opposite_long_edges_of_table"},
    ],
    fixed_props=[
        {"id": "dish_rack", "zone": "LEFT_COUNTER", "relation": "near_sink"},
        {"id": "small_kitchen_items", "zone": "BACK_COUNTER", "relation": "fixed_sparse_cluster"},
    ],
    landmarks=["left_window", "sink_below_window", "back_cabinet", "rear_right_kitchen_door", "center_foreground_dining_table"],
    relative_positions=[
        {"subject": "sink", "relation": "below", "object": "left_window"},
        {"subject": "dining_table", "relation": "in_front_of", "object": "sink"},
        {"subject": "kitchen_door", "relation": "rear_right_of", "object": "dining_table"},
        {"subject": "cabinet", "relation": "behind", "object": "sink"},
    ],
    adjacency=[
        {"a": "window_left", "b": "sink", "relation": "vertical_adjacent"},
        {"a": "sink", "b": "back_cabinet", "relation": "same_rear_work_zone"},
        {"a": "dining_table", "b": "kitchen_door", "relation": "door_visible_beyond_table_right"},
    ],
    lighting_sources=["cool overcast daylight through left window", "single warm ceiling bulb"],
    lighting_directions=["cool light from LEFT toward CENTER", "warm light from CEILING downward"],
    materials=["old white ceramic wall tile", "worn wood countertop", "matte painted cabinet", "scuffed wood dining table", "aged apartment plaster"],
    time="early evening",
    weather="overcast after rain",
)

PLANS = [
    SceneDerivedViewPlan(
        view_id="REVERSE", view_type="REVERSE", camera_position="near rear kitchen work zone facing toward dining table",
        camera_direction="toward the center foreground and rear-right kitchen door",
        visible_landmarks=["dining_table", "rear_right_kitchen_door", "left_window_edge", "sink_edge"],
        occluded_landmarks=["back_cabinet_partial"], required_landmarks=["dining_table", "rear_right_kitchen_door", "left_window_edge"],
        forbidden_changes=["redesigning the room", "moving the door", "moving the sink below the window", "changing fixed furniture", "adding people or text"],
    ),
    SceneDerivedViewPlan(
        view_id="SIDE", view_type="SIDE", camera_position="along the long side of the dining table",
        camera_direction="across the table toward the left window and rear work zone",
        visible_landmarks=["dining_table", "sink_below_window", "back_cabinet", "rear_right_kitchen_door"],
        occluded_landmarks=["near chair underside"], required_landmarks=["dining_table", "sink_below_window", "back_cabinet"],
        forbidden_changes=["redesigning the room", "changing table orientation", "moving the window", "changing fixed furniture", "adding people or text"],
    ),
    SceneDerivedViewPlan(
        view_id="DETAIL", view_type="DETAIL", camera_position="close camera at the left counter beside the sink",
        camera_direction="toward sink, worn counter, left window lower frame and cabinet edge",
        visible_landmarks=["sink_below_window", "left_window", "worn_counter", "back_cabinet_edge"],
        occluded_landmarks=["dining_table", "kitchen_door"], required_landmarks=["sink_below_window", "worn_counter", "left_window"],
        forbidden_changes=["inventing another kitchen", "moving the sink away from the window", "changing tile or counter material", "adding people or text"],
    ),
]

NEGATIVE = "人物、角色、人脸、文字、标签、Logo、水印、拼图、四宫格、不同房间、移动门窗、水槽漂移、家具新增或消失、超现实建筑"


def _master_prompt() -> str:
    geometry = json.dumps(asdict(GEOMETRY), ensure_ascii=False, sort_keys=True)
    return (
        "单张写实电影场景空间主参考图，16:9横向，不要拼图，不要四宫格，不要人物，不要文字标签。"
        "这是E01_SC002旧出租公寓厨房的完整master wide，必须清楚表现真实房间比例和拓扑：左墙窗户，水槽严格位于左墙窗户正下方，"
        "后墙橱柜和工作台，前景中央餐桌与两把椅子，右后方厨房门通往客厅。旧白瓷砖、磨损木台面、哑光柜体、旧木餐桌；"
        "傍晚阴天雨后，左侧冷色天光与顶部单盏暖灯并存。画面要让门、窗、水槽、橱柜、餐桌的相对位置一次看清。"
        f"\n权威SceneGeometryIR：{geometry}"
    )


def _safe_parse_json(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(raw[start : end + 1])
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _data_uri(path: Path) -> str:
    content = path.read_bytes()
    mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    return f"data:{mime};base64," + base64.b64encode(content).decode("ascii")


def _font(size: int) -> ImageFont.ImageFont:
    for path in (Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simhei.ttf"), Path("C:/Windows/Fonts/arial.ttf")):
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                pass
    return ImageFont.load_default()


def _compose_board(paths: dict[str, Path], output: Path) -> dict[str, Any]:
    tile_w, tile_h, label_h = 840, 520, 48
    board = Image.new("RGB", (tile_w * 2, (tile_h + label_h) * 2), "#101719")
    draw = ImageDraw.Draw(board)
    title_font, small_font = _font(26), _font(17)
    for index, view_id in enumerate(("MASTER", "REVERSE", "SIDE", "DETAIL")):
        with Image.open(paths[view_id]).convert("RGB") as image:
            image.thumbnail((tile_w - 24, tile_h - 24), Image.Resampling.LANCZOS)
            x = (index % 2) * tile_w + (tile_w - image.width) // 2
            y = (index // 2) * (tile_h + label_h) + (tile_h - image.height) // 2
            board.paste(image, (x, y))
            meta = {"width": image.width, "height": image.height}
        lx = (index % 2) * tile_w + 18
        ly = (index // 2) * (tile_h + label_h) + tile_h + 6
        draw.text((lx, ly), view_id, fill="#F4F7F7", font=title_font)
        draw.text((lx + 160, ly + 6), f"{meta['width']}×{meta['height']}", fill="#9FB4B5", font=small_font)
    board.save(output, format="PNG", optimize=True)
    return _image_meta(output)


async def _submit_view(client: httpx.AsyncClient, base_url: str, view_id: str, prompt: str, output: Path) -> dict[str, Any]:
    payload = {
        "book_id": BOOK_ID, "episode": EPISODE, "shot_id": f"AUTO_SCENE_{SCENE_ID}_{view_id}",
        "source_node_id": f"autonomous-scene-v1:{SCENE_ID}:{view_id}", "source_asset_id": None,
        "asset_scope": "location", "asset_subject": f"{SCENE_ID} {view_id}", "target_kind": "reference-image",
        "prompt": prompt, "model_profile_id": PROFILE_ID, "aspect_ratio": "16:9",
        "negative_prompt": NEGATIVE, "count": 1, "confirmed": True, "allow_external_call": True,
    }
    response = await client.post(f"{base_url}/api/prototyping/generate-reference-image", json=payload)
    response.raise_for_status()
    task_id = response.json()["task_id"]
    deadline = time.time() + 900
    task: dict[str, Any] = {}
    while time.time() < deadline:
        poll = await client.get(f"{base_url}/api/prototyping/tasks/{task_id}")
        poll.raise_for_status(); task = poll.json()
        if task.get("status") in {"done", "error"}:
            break
        await asyncio.sleep(2)
    if task.get("status") != "done":
        raise RuntimeError(f"{view_id} generation failed: {task.get('error') or task.get('status')}")
    asset = task.get("asset") or {}
    persistence = (asset.get("metadata") or {}).get("generatedImagePersistence") or {}
    local_path = Path(str(persistence.get("local_path") or ""))
    if not local_path.exists():
        preview = str(asset.get("previewUrl") or asset.get("uri") or "")
        if preview.startswith("data:image/"):
            output.write_bytes(base64.b64decode(preview.split(",", 1)[1]))
        else:
            output.write_bytes((await client.get(preview)).content)
    else:
        shutil.copy2(local_path, output)
    meta = _image_meta(output)
    return {
        "view_id": view_id, "execution_id": task_id, "provider": task.get("provider"),
        "model_profile_id": task.get("model_profile_id"), "candidate_status": "CANDIDATE",
        "prompt_fingerprint": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "provider_request_payload": _redact(task.get("provider_request_payload") or (asset.get("metadata") or {}).get("providerRequestPayload") or {}),
        "file": meta, "path": str(output), "visual_review": "PENDING_HUMAN_VISUAL_REVIEW",
    }


def _judge(profile: dict[str, Any] | None, paths: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    if not profile or not bool((profile.get("default_params") or {}).get("supports_vision")):
        return "VISUAL_JUDGE_NOT_CONFIGURED", {"status": "VISUAL_JUDGE_NOT_CONFIGURED", "views": {}}
    import core.llm as llm_client

    prompt = (
        "你是场景连续性审计器。比较四张输入图：MASTER、REVERSE、SIDE、DETAIL。"
        "只输出 JSON，不要 markdown。判断它们是否表现同一个物理厨房，重点检查门窗水槽餐桌橱柜的拓扑、材质、时间天气和灯光方向。"
        "输出格式：{\"status\":\"PASS|REPAIR|FAIL\",\"views\":{\"REVERSE\":{\"same_physical_space\":true,\"architecture_score\":0,\"landmark_score\":0,\"furniture_score\":0,\"lighting_score\":0,\"critical_topology_violations\":[],\"violations\":[]},\"SIDE\":{},\"DETAIL\":{}}}。"
        "分数必须是整数，不能因为提示词相似而忽略画面事实。"
    )
    images = [_data_uri(paths[key]) for key in ("MASTER", "REVERSE", "SIDE", "DETAIL")]
    try:
        raw = llm_client.call_llm(prompt, system="vision consistency judge v1", model_profile=profile, retries=1, estimated_tokens=1800, max_tokens=3000, image_data_urls=images)
        parsed = _safe_parse_json(raw)
        if parsed is None:
            return "VISUAL_JUDGE_INVALID", {"status": "VISUAL_JUDGE_INVALID", "raw_excerpt": str(raw)[:1000], "views": {}}
        parsed.setdefault("status", "REPAIR")
        return "VISION_JUDGE_EXECUTED", parsed
    except Exception as exc:
        return "VISUAL_JUDGE_UNAVAILABLE", {"status": "VISUAL_JUDGE_UNAVAILABLE", "error": str(exc)[:500], "views": {}}


def _normalized_audit(view_id: str, raw: dict[str, Any], attempt: int, judge_status: str) -> SceneConsistencyAudit:
    data = raw if isinstance(raw, dict) else {}
    critical = [str(x) for x in (data.get("critical_topology_violations") or [])]
    violations = [str(x) for x in (data.get("violations") or [])]
    same = bool(data.get("same_physical_space"))
    scores = {key: int(data.get(key) or 0) for key in ("architecture_score", "landmark_score", "furniture_score", "lighting_score")}
    status = "PASS" if same and min(scores.values()) >= (80 if view_id == "DETAIL" else 85) and not critical else "REPAIR"
    if judge_status != "VISION_JUDGE_EXECUTED":
        status = "FAIL"
        violations.append(judge_status)
    return SceneConsistencyAudit(view_id=view_id, status=status, same_physical_space=same, attempt_number=attempt, judge_status=judge_status, critical_topology_violations=critical, violations=violations, **scores)


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--profile-id", default=PROFILE_ID); parser.add_argument("--vision-profile-id", default=VISION_PROFILE_ID); args = parser.parse_args()
    if not SOURCE_DB.exists():
        raise SystemExit(f"missing database: {SOURCE_DB}")
    budget = AssetGenerationBudgetPolicy(normal_calls_max=7, max_attempts_per_view=3)
    runtime = AutonomousAssetGeneration(asset_type="SCENE", asset_id=SCENE_ID, budget=budget)
    runtime.plan_scene(GEOMETRY, PLANS)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work = ROOT / "work" / "autonomous-scene-asset-v1" / run_id; work.mkdir(parents=True, exist_ok=True)
    isolated_db = work / "screenplay.db"; shutil.copy2(SOURCE_DB, isolated_db); uploads = work / "uploads"
    port = _free_port(); env = os.environ.copy(); env.update({"DATABASE_URL": f"sqlite:///{isolated_db.as_posix()}?timeout=30", "UPLOAD_DIR": str(uploads), "DEPLOYMENT_ENV": "isolated", "APP_ENV": "test", "E2E_EXTERNAL_RUNTIME": ""})
    log = (work / "uvicorn.log").open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base_url = f"http://127.0.0.1:{port}"
    paths: dict[str, Path] = {}; generations: dict[str, dict[str, Any]] = {}; generation_events: list[dict[str, Any]] = []
    try:
        _wait_for_health(base_url, timeout=180)
        os.environ["DATABASE_URL"] = env["DATABASE_URL"]
        from api.model_registry import get_profile
        image_profile = get_profile(args.profile_id); vision_profile = get_profile(args.vision_profile_id)
        capability = {"image_reference_input": bool((image_profile or {}).get("default_params", {}).get("supports_reference_images")), "image_edit": bool((image_profile or {}).get("default_params", {}).get("supports_image_edit")), "image_text_only": True}
        # SHAPI profile currently has no verified IMAGE reference/edit contract;
        # use the honest geometry constrained text derivation route.
        route = "REFERENCE_IMAGE_DERIVATION" if capability["image_reference_input"] or capability["image_edit"] else "GEOMETRY_CONSTRAINED_TEXT_DERIVATION"
        paths["MASTER"] = work / "scene-master.jpg"
        master = _master_prompt()
        async def generate_initial() -> None:
            async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                generations["MASTER"] = await _submit_view(client, base_url, "MASTER", master, paths["MASTER"])
                runtime.record_primary(generations["MASTER"]); generation_events.append({"view_id":"MASTER","attempt":1,"kind":"PRIMARY_GENERATING","call":runtime.image_calls})
                runtime.begin_derivation()
                for plan in PLANS:
                    paths[plan.view_id] = work / f"scene-{plan.view_id.lower()}.jpg"
                    prompt = geometry_constrained_prompt(GEOMETRY, plan)
                    runtime.claim_image_call(); generations[plan.view_id] = await _submit_view(client, base_url, plan.view_id, prompt, paths[plan.view_id]); runtime.record_derived(plan.view_id, generations[plan.view_id]); generation_events.append({"view_id":plan.view_id,"attempt":1,"kind":"DERIVING","call":runtime.image_calls,"route":route})
        asyncio.run(generate_initial())

        # Copy the baseline and the first generated set into the tracked output
        # only after all calls complete; failed intermediate runs stay isolated.
        OUT.mkdir(parents=True, exist_ok=True)
        for old in OUT.glob("scene-*.jpg"): old.unlink()
        for view_id, source in paths.items(): shutil.copy2(source, OUT / f"scene-{view_id.lower()}.jpg"); paths[view_id] = OUT / f"scene-{view_id.lower()}.jpg"
        if BASELINE.exists(): shutil.copy2(BASELINE, OUT / "scene-v0-failed-baseline.jpg")

        judge_status, judge = _judge(vision_profile, paths)
        audit_rows: list[SceneConsistencyAudit] = []
        for plan in PLANS:
            row = _normalized_audit(plan.view_id, (judge.get("views") or {}).get(plan.view_id, {}), 1, judge_status); runtime.record_audit(row); audit_rows.append(row)
        # Repair only failed views, automatically and within the seven-call cap.
        for plan in PLANS:
            while True:
                latest = next((row for row in reversed(audit_rows) if row.view_id == plan.view_id), None)
                if latest and latest.passes: break
                attempts = latest.attempt_number if latest else 1
                if attempts >= budget.max_attempts_per_view or runtime.image_calls >= budget.normal_calls_max: break
                corrections = [f"保持 {value}" for value in plan.required_landmarks] + ["不得改变 SceneGeometryIR 的门窗水槽餐桌橱柜拓扑"]
                context = AssetRepairContext(view_id=plan.view_id, previous_prompt=geometry_constrained_prompt(GEOMETRY, plan), failed_output=generations.get(plan.view_id, {}), violations=(latest.violations if latest else ["judge did not pass"]), required_corrections=corrections, attempt_number=attempts + 1)
                runtime.prepare_repair(context); runtime.claim_image_call()
                async def repair_one() -> dict[str, Any]:
                    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                        return await _submit_view(client, base_url, plan.view_id, geometry_constrained_prompt(GEOMETRY, plan, repair=context), paths[plan.view_id])
                generations[plan.view_id] = asyncio.run(repair_one()); runtime.record_derived(plan.view_id, generations[plan.view_id]); generation_events.append({"view_id":plan.view_id,"attempt":attempts+1,"kind":"REPAIRING","call":runtime.image_calls,"route":route,"corrections":corrections})
                judge_status, judge = _judge(vision_profile, paths)
                row = _normalized_audit(plan.view_id, (judge.get("views") or {}).get(plan.view_id, {}), attempts + 1, judge_status); runtime.record_audit(row); audit_rows.append(row)

        latest_by_view = {row.view_id: row for row in audit_rows}
        authority = None
        try:
            authority = runtime.lock()
        except RuntimeError:
            pass
        board = _compose_board(paths, OUT / "scene-reference-board.png")
        geometry_payload = {**asdict(GEOMETRY), "fingerprint": GEOMETRY.fingerprint, "authority": "topology"}
        plans_payload = [asdict(item) for item in PLANS]
        audit_payload = {"schema_version":"scene_consistency_audit_v1","scene_id":SCENE_ID,"judge_status":judge_status,"judge":judge,"views":[asdict(item) for item in audit_rows],"latest_views":{key:asdict(value) for key,value in latest_by_view.items()},"thresholds":asdict(budget)}
        repair_payload = {"schema_version":"asset_repair_history_v1","repairs":[asdict(item) for item in runtime.repairs],"generation_events":generation_events}
        manifest = {"schema_version":"autonomous_asset_pipeline_audit_v1","status":"AUTONOMOUS_SCENE_ASSET_PIPELINE_READY" if authority else "ASSET_CONSISTENCY_GENERATION_FAILED","scene_id":SCENE_ID,"state":runtime.state.value,"manual_approvals_required":0,"manual_view_selection":0,"result":"READY" if authority else "FAILED","geometry":geometry_payload,"derived_route":route,"image_capabilities":capability,"generation":{"master_calls":1,"reverse_calls":sum(1 for event in generation_events if event['view_id']=='REVERSE'),"side_calls":sum(1 for event in generation_events if event['view_id']=='SIDE'),"detail_calls":sum(1 for event in generation_events if event['view_id']=='DETAIL'),"repair_calls":len(runtime.repairs),"total_image_calls":runtime.image_calls},"consistency":audit_payload,"authority":authority,"final_board":board,"real_image_calls":runtime.image_calls,"real_video_calls":0,"v0_failed_baseline":str(OUT/'scene-v0-failed-baseline.jpg')}
        _write(OUT / "SCENE_GEOMETRY_IR.json", geometry_payload); _write(OUT / "SCENE_DERIVED_VIEW_PLANS.json", plans_payload); _write(OUT / "SCENE_CONSISTENCY_AUDIT.json", audit_payload); _write(OUT / "SCENE_REPAIR_HISTORY.json", repair_payload); _write(OUT / "AUTONOMOUS_ASSET_PIPELINE_AUDIT.json", manifest)
        _write(OUT / "SCENE_AUTHORITY.json", authority or {"status":"FAILED","scene_id":SCENE_ID,"geometry_fingerprint":GEOMETRY.fingerprint})
        report = ["# Autonomous Visual Asset Pipeline V1 Report", "", f"- Status: `{manifest['status']}`", "- Scene: `E01_SC002`", "- Manual approvals required: `0`", "- Manual view selection: `0`", f"- Derived route: `{route}`", f"- Visual judge: `{judge_status}`", "", "## Generation", "", f"- Master calls: `{manifest['generation']['master_calls']}`", f"- Reverse calls: `{manifest['generation']['reverse_calls']}`", f"- Side calls: `{manifest['generation']['side_calls']}`", f"- Detail calls: `{manifest['generation']['detail_calls']}`", f"- Repair calls: `{manifest['generation']['repair_calls']}`", f"- Total IMAGE calls: `{manifest['generation']['total_image_calls']}`", "- Real VIDEO calls: `0`", "", "## Geometry authority", "", "- window: LEFT wall", "- sink: LEFT wall, directly below window", "- door: REAR_RIGHT zone", "- table: CENTER_FOREGROUND", "- cabinet: BACK wall", "- Geometry is authoritative; the Master image is its visual implementation.", "", "## Consistency", ""]
        for view_id in ("REVERSE", "SIDE", "DETAIL"):
            row = latest_by_view.get(view_id); report.append(f"- `{view_id}`: `{row.status if row else 'MISSING'}`; architecture={row.architecture_score if row else 0}, landmarks={row.landmark_score if row else 0}, furniture={row.furniture_score if row else 0}, lighting={row.lighting_score if row else 0}; critical={row.critical_topology_violations if row else []}")
        report.extend(["", "## Automatic repair", "", f"- Views repaired: `{sorted({item.view_id for item in runtime.repairs})}`", f"- Attempts: `{[event for event in generation_events if event['kind']=='REPAIRING']}`", "- No human approval or view selection was requested during the run.", "", "The prior 2×2 generated scene is retained as `scene-v0-failed-baseline.jpg`; it is not Scene Authority.", ""])
        (OUT / "AUTONOMOUS_ASSET_PIPELINE_REPORT.md").write_text("\n".join(report), encoding="utf-8")
        print(json.dumps({"status":manifest["status"],"state":runtime.state.value,"judge_status":judge_status,"image_calls":runtime.image_calls,"video_calls":0,"output":str(OUT)},ensure_ascii=False,indent=2))
        return 0 if authority else 2
    finally:
        process.terminate()
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
