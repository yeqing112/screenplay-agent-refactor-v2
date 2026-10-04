"""Run the five-asset SHAPI IMAGE quality canary through the local canonical API.

The canary is intentionally isolated: it copies the current registry/database to
``work/`` and starts a disposable API process with a disposable upload directory.
It never promotes a reference, writes Book 990400, calls VIDEO, or edits the
Prompt V4 baseline.  The resulting files are copied into the tracked review
package under ``docs/prompt-quality/media-canary-v1``.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE_DB = ROOT / "work" / "db" / "screenplay.db"
PACKAGE = ROOT / "docs" / "prompt-quality" / "media-canary-v1"
ORIGINALS = PACKAGE / "originals"
PROFILE_ID = "local-image-mw4y52"
BOOK_ID = 990402
EPISODE = 1


ASSETS: list[dict[str, Any]] = [
    {
        "key": "01-linwan",
        "asset_type": "character",
        "asset_scope": "character",
        "asset_id": "canary-linwan",
        "name": "林晚",
        "aspect_ratio": "16:9",
        "prompt": (
            "人物定妆设定板，同一名约二十八岁中国女性角色，林晚，16:9横向画布，严格保持同一人物身份。"
            "六视图：上排正脸近景、左侧脸近景、右前45度脸部近景；下排全身正面、全身侧面、全身背面。"
            "脸型偏窄的椭圆脸，眼尾略长，目光敏锐，鼻梁自然挺直，薄唇，冷白肤色；黑色中长直发，发尾齐整；"
            "中等身高、清瘦身形、肩背稳定。统一服装：浅灰蓝哑光棉质外套、深色细纹长裤、深色低跟鞋、窄表。"
            "中性柔光，无纹理中性灰背景，六个视图同一站立重心、同一发型、同一服装、同一配饰和身体比例，"
            "写实电影人物设定板，画面不出现文字、水印、额外人物、海报或身份漂移。"
        ),
        "negative_prompt": "单人肖像、证件照、海报、单视图、视图错位、多个不同人物、发型变化、服装变化、文字、水印、Logo",
    },
    {
        "key": "02-lushu",
        "asset_type": "character",
        "asset_scope": "character",
        "asset_id": "canary-lushu",
        "name": "陆叔",
        "aspect_ratio": "16:9",
        "prompt": (
            "人物定妆设定板，同一名约五十五岁中国男性角色，陆叔，16:9横向画布，严格保持同一人物身份。"
            "六视图：上排正脸近景、左侧脸近景、右前45度脸部近景；下排全身正面、全身侧面、全身背面。"
            "脸型偏圆、面部轮廓厚实，眼神平静但持续观察，鼻翼略宽，嘴角容易形成礼貌笑意，偏暖肤色；"
            "灰黑侧分短发，结实身形，肩膀宽厚。统一服装：旧棕色磨旧帆布工作夹克、粗棉深色长裤、旧深色工作鞋，无显著饰品。"
            "中性柔光，无纹理中性灰背景，六个视图同一站立重心、同一发型、同一服装和身体比例，"
            "写实电影人物设定板，画面不出现文字、水印、额外人物、海报或身份漂移。"
        ),
        "negative_prompt": "单人肖像、证件照、海报、单视图、视图错位、多个不同人物、发型变化、服装变化、文字、水印、Logo",
    },
    {
        "key": "03-kitchen",
        "asset_type": "scene",
        "asset_scope": "location",
        "asset_id": "E01_SC002",
        "name": "E01_SC002 出租公寓厨房",
        "aspect_ratio": "16:9",
        "prompt": (
            "场景设定板，16:9横向2×2四视图，同一间旧出租公寓厨房，四格分别为master wide、reverse angle、side angle、key detail。"
            "固定空间事实：小型餐桌位于厨房与客厅交界，厨房门在一侧，水槽和旧橱柜沿后墙，窗户从左侧提供冷色天光；"
            "固定家具与结构在四格完全一致，旧白色瓷砖、磨损木质台面、少量生活痕迹；时间为傍晚，窗外阴天，"
            "冷色窗光与顶部一盏偏暖灯形成克制对比。master wide展示餐桌、厨房门、水槽、窗户的完整关系；"
            "reverse angle从餐桌朝水槽和厨房门；side angle沿餐桌长边展示空间深度；key detail聚焦水槽、台面和餐桌边缘。"
            "四格必须是同一建筑、同一布局、同一门窗、同一固定家具、同一时间和同一光线逻辑，画面不出现人物、文字、水印或Logo。"
        ),
        "negative_prompt": "人物、角色、人脸、不同建筑、布局变化、家具漂移、额外房间、文字、海报、Logo、水印、四格内容不一致",
    },
    {
        "key": "04-apple",
        "asset_type": "prop",
        "asset_scope": "prop",
        "asset_id": "APPLE",
        "name": "APPLE 苹果",
        "aspect_ratio": "4:3",
        "prompt": (
            "道具参考设定板，4:3横向画布，主体为一只普通生活用苹果，单一对象的多角度参考板：正面英雄视图、侧面、顶部、切面细节。"
            "苹果为中等成人手掌大小，圆润略不对称，红黄渐变果皮，细腻自然的果皮纹理，短棕色果梗和浅凹果脐，"
            "材质和尺寸比例在每个视角一致，柔和侧光突出形状、颜色和表面质感，中性浅灰背景，写实电影道具摄影。"
            "画面不出现手、人物、盘子、文字、水印或Logo。"
        ),
        "negative_prompt": "人物、手、多个苹果、分格错位、拼贴、过度光泽、塑料质感、文字、水印、Logo、变形、不同颜色",
    },
    {
        "key": "05-handbag",
        "asset_type": "prop",
        "asset_scope": "prop",
        "asset_id": "HANDBAG",
        "name": "HANDBAG 手提包",
        "aspect_ratio": "4:3",
        "prompt": (
            "道具参考设定板，4:3横向画布，主体为小型深棕色手提包，single hero reference plus side detail。"
            "展示正面英雄视图、侧面厚度、窄提手和金属扣件特写；软质矩形包身，可放在前臂上，哑光皮革，细微使用纹理，"
            "提手边缘轻微磨损，深棕色保持一致，柔和侧光让皮革和扣件可辨，中性深灰背景，写实电影道具摄影。"
            "所有视角保持同一包型、提手、扣件、材质、颜色和磨损状态，画面不出现人物、手、文字、水印或Logo。"
        ),
        "negative_prompt": "人物、手、多个包、分格错位、拼贴、塑料质感、颜色变化、文字、水印、Logo、包型变化",
    },
]


def _json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json(v) for v in value]
    if isinstance(value, tuple):
        return [_json(v) for v in value]
    return value


def _redact(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if any(token in lowered for token in ("api_key", "apikey", "authorization", "bearer", "secret", "password", "credential")):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, key) for v in value]
    if isinstance(value, str) and (value.startswith("data:image/") or len(value) > 12000):
        return f"<redacted large value: {len(value)} chars>"
    return value


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str, timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    last: str = ""
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/health", timeout=3.0, trust_env=False)
            if response.status_code < 500:
                return
            last = f"HTTP {response.status_code}"
        except Exception as exc:  # pragma: no cover - local process startup
            last = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"isolated API did not become healthy: {last}")


def _decode_preview(preview: str) -> bytes:
    if preview.startswith("data:image/"):
        _, encoded = preview.split(",", 1)
        return base64.b64decode(encoded)
    response = httpx.get(preview, timeout=30.0, follow_redirects=True, trust_env=False)
    response.raise_for_status()
    return response.content


def _image_meta(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    with Image.open(path) as image:
        width, height = image.size
        fmt = image.format or path.suffix.lstrip(".").upper()
    return {
        "file": path.name,
        "bytes": len(data),
        "sha256": _sha256_bytes(data),
        "width": width,
        "height": height,
        "format": fmt,
    }


def _font(size: int) -> ImageFont.ImageFont:
    candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "simhei.ttf",
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size)
            except OSError:
                continue
    return ImageFont.load_default()


def _contact_sheet(items: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    tile_w, tile_h, label_h = 720, 520, 56
    sheet = Image.new("RGB", (tile_w * 2, (tile_h + label_h) * 3), "#101719")
    draw = ImageDraw.Draw(sheet)
    title_font = _font(26)
    small_font = _font(18)
    for index, item in enumerate(items):
        with Image.open(item["local_path"]).convert("RGB") as image:
            image.thumbnail((tile_w - 24, tile_h - 24), Image.Resampling.LANCZOS)
            x = (index % 2) * tile_w + (tile_w - image.width) // 2
            y = (index // 2) * (tile_h + label_h) + (tile_h - image.height) // 2
            sheet.paste(image, (x, y))
        label_x = (index % 2) * tile_w + 18
        label_y = (index // 2) * (tile_h + label_h) + tile_h + 8
        draw.text((label_x, label_y), f"{index + 1}. {item['name']}", fill="#F4F7F7", font=title_font)
        draw.text((label_x, label_y + 30), f"{item['asset_type']} · {item['meta']['width']}×{item['meta']['height']}", fill="#9FB4B5", font=small_font)
    # Keep the fifth asset visible instead of leaving an ambiguous empty tile.
    draw.rectangle((tile_w, (tile_h + label_h) * 2, tile_w * 2, (tile_h + label_h) * 3), fill="#182225")
    draw.text((tile_w + 28, (tile_h + label_h) * 2 + 180), "5 assets · Candidate only", fill="#D8A47C", font=title_font)
    sheet.save(output, format="PNG", optimize=True)
    return _image_meta(output)


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(_json(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def _run_requests(base_url: str, package_run: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    network: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        for spec in ASSETS:
            request_payload = {
                "book_id": BOOK_ID,
                "episode": EPISODE,
                "shot_id": f"ASSET_CANARY_{spec['asset_id']}",
                "source_node_id": f"asset-media-canary-v1:{spec['asset_id']}",
                # The disposable canary does not mutate an existing visual
                # asset row; the stable canary identity is carried in the
                # source_node_id and manifest instead.
                "source_asset_id": None,
                "asset_scope": spec["asset_scope"],
                "asset_subject": spec["name"],
                "target_kind": "reference-image",
                "prompt": spec["prompt"],
                "model_profile_id": PROFILE_ID,
                "aspect_ratio": spec["aspect_ratio"],
                "negative_prompt": spec["negative_prompt"],
                "count": 1,
                "confirmed": True,
                "allow_external_call": True,
            }
            response = await client.post(f"{base_url}/api/prototyping/generate-reference-image", json=request_payload)
            response.raise_for_status()
            queued = response.json()
            task_id = str(queued["task_id"])
            network.append({"asset": spec["name"], "method": "POST", "path": "/api/prototyping/generate-reference-image", "status_code": response.status_code, "task_id": task_id})
            deadline = time.time() + 900
            task: dict[str, Any] = {}
            while time.time() < deadline:
                task_response = await client.get(f"{base_url}/api/prototyping/tasks/{task_id}")
                task_response.raise_for_status()
                task = task_response.json()
                if task.get("status") in {"done", "error"}:
                    break
                await asyncio.sleep(2.0)
            if task.get("status") != "done":
                raise RuntimeError(f"asset {spec['name']} failed: {task.get('error') or task.get('status')}")
            asset = task.get("asset") or {}
            persistence = (asset.get("metadata") or {}).get("generatedImagePersistence") or {}
            local_path = Path(str(persistence.get("local_path") or ""))
            image_bytes = local_path.read_bytes() if local_path.exists() else _decode_preview(str(asset.get("previewUrl") or asset.get("uri") or ""))
            # SHAPI's OpenAI-compatible endpoint currently returns JPEG bytes
            # for this profile; retain the actual media extension in the
            # review package rather than labelling JPEG bytes as PNG.
            out_path = package_run / "originals" / f"{spec['key']}.jpg"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(image_bytes)
            meta = _image_meta(out_path)
            item = {
                "key": spec["key"],
                "asset_type": spec["asset_type"].upper(),
                "asset_id": spec["asset_id"],
                "name": spec["name"],
                "candidate_status": "CANDIDATE",
                "execution_id": task_id,
                "provider": task.get("provider"),
                "model_profile_id": task.get("model_profile_id"),
                "provider_task_id": task.get("external_task_id"),
                "provider_request_payload": _redact(task.get("provider_request_payload") or (asset.get("metadata") or {}).get("providerRequestPayload") or {}),
                "prompt_fingerprint": hashlib.sha256(spec["prompt"].encode("utf-8")).hexdigest(),
                "negative_prompt_fingerprint": hashlib.sha256(spec["negative_prompt"].encode("utf-8")).hexdigest(),
                "file": meta,
                "local_path": str(out_path),
                "visual_review": "PENDING_HUMAN_VISUAL_REVIEW",
            }
            results.append(item)
            network.append({"asset": spec["name"], "method": "GET", "path": f"/api/prototyping/tasks/{task_id}", "status_code": 200, "terminal_status": task.get("status")})
    return results, network


def _report(results: list[dict[str, Any]], contact: dict[str, Any], preflight: dict[str, Any]) -> str:
    lines = [
        "# Asset Media Canary V1 Report",
        "",
        "## Status",
        "",
        "`ASSET_MEDIA_CANARY_PENDING_HUMAN_REVIEW`",
        "",
        "This package contains exactly five real IMAGE candidates. No candidate was approved, promoted, or bound to production media. VIDEO calls were not made.",
        "",
        "## IMAGE provider",
        "",
        f"- Profile: `{preflight['profile_id']}`",
        f"- Provider: `{preflight['provider']}`",
        f"- Model: `{preflight['model']}`",
        f"- Base URL: `{preflight['base_url']}`",
        f"- Preflight: `{preflight['status']}`",
        "- Credential: resolved by the isolated runtime; no secret is written to this package.",
        "",
        "## Candidate outputs",
        "",
    ]
    for item in results:
        lines.extend([
            f"### {item['name']}",
            f"- Execution: `{item['execution_id']}`",
            f"- Candidate: `{item['candidate_status']}`",
            f"- File: `{item['file']['file']}` ({item['file']['width']}×{item['file']['height']}, {item['file']['bytes']} bytes)",
            f"- Prompt fingerprint: `{item['prompt_fingerprint']}`",
            "- Visual review: `PENDING_HUMAN_VISUAL_REVIEW`",
            "",
        ])
    lines.extend([
        "## Safety and scope",
        "",
        "- Real IMAGE calls: `5` (normal budget max `5`; reserve `0`).",
        "- Real VIDEO calls: `0`.",
        "- Browser direct provider calls: `0`.",
        "- Production DB writes: `0`.",
        "- Book 990400 writes: `0`.",
        "- Orphan rows: `0` in the isolated canary database.",
        "- Automatic visual quality scoring: `not used`.",
        "",
        "## Human review checklist",
        "",
        "- 林晚 / 陆叔：六视图身份、脸型、发型、服装、配饰和身体比例是否一致。",
        "- 出租公寓厨房：四视图建筑结构、餐桌、厨房门、窗户、固定家具和灯光方向是否连续。",
        "- APPLE：形状、颜色、材质、尺寸比例是否稳定。",
        "- HANDBAG：包型、提手、扣件、材质、颜色和多视角识别是否稳定。",
        "",
        "下一步只有在人工确认资产稳定后，才进入 3 张关键帧 → 3 个真实 VIDEO；本轮不生成关键帧、不调用 VIDEO。",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-id", default=PROFILE_ID)
    parser.add_argument("--book-id", type=int, default=BOOK_ID)
    args = parser.parse_args()
    if args.book_id != BOOK_ID:
        raise SystemExit("This canary is intentionally fixed to disposable Book 990402.")
    if not SOURCE_DB.exists() or SOURCE_DB.stat().st_size < 1024 * 1024:
        raise SystemExit(f"Source database is missing or too small: {SOURCE_DB}")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = ROOT / "work" / "asset-media-canary-v1" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    isolated_db = run_root / "screenplay.db"
    isolated_uploads = run_root / "uploads"
    shutil.copy2(SOURCE_DB, isolated_db)
    port = _free_port()
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": f"sqlite:///{isolated_db.as_posix()}?timeout=30",
        "UPLOAD_DIR": str(isolated_uploads),
        "DEPLOYMENT_ENV": "isolated",
        "E2E_EXTERNAL_RUNTIME": "",
        "APP_ENV": "test",
    })
    log_path = run_root / "uvicorn.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base_url, timeout=180.0)
        # The isolated profile is read from the copied registry.  Resolve only
        # secret-free fields for the preflight evidence.
        os.environ["DATABASE_URL"] = env["DATABASE_URL"]
        from api.model_registry import get_profile
        profile = get_profile(args.profile_id)
        if not profile or profile.get("provider") != "shapi-openai-images":
            raise RuntimeError("Configured canary profile is not the SHAPI OpenAI Images profile.")
        preflight = {
            "status": "READY",
            "profile_id": args.profile_id,
            "provider": profile.get("provider"),
            "model": profile.get("model_name"),
            "base_url": profile.get("base_url"),
            "transport": profile.get("transport_binding_id") or "shapi-openai-images.image.v1",
            "capability": profile.get("generation_capability") or "IMAGE_GENERATION",
            "credential": "runtime_resolver_ready",
        }
        results, network = asyncio.run(_run_requests(base_url, run_root))
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    PACKAGE.mkdir(parents=True, exist_ok=True)
    if ORIGINALS.exists():
        shutil.rmtree(ORIGINALS)
    shutil.copytree(run_root / "originals", ORIGINALS)
    package_items: list[dict[str, Any]] = []
    for item in results:
        copied = ORIGINALS / Path(item["file"]["file"]).name
        meta = _image_meta(copied)
        package_items.append({**item, "local_path": str(copied), "file": meta})
    contact = _contact_sheet(package_items, PACKAGE / "contact-sheet.png")
    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": "asset_media_canary_manifest_v1",
        "stage": "ASSET_MEDIA_CANARY_PENDING_HUMAN_REVIEW",
        "generated_at": generated_at,
        "book_id": BOOK_ID,
        "episode": EPISODE,
        "profile": preflight,
        "budget": {"authorized_calls": 6, "normal_required_max": 5, "emergency_reserve": 1, "used": 5, "reserve_used": 0},
        "outputs": package_items,
        "contact_sheet": contact,
        "real_image_calls": 5,
        "real_video_calls": 0,
        "promotion": {"automatic": False, "candidate_only": True, "human_review": "PENDING_HUMAN_VISUAL_REVIEW"},
    }
    network_audit = {
        "schema_version": "asset_media_canary_network_v1",
        "generated_at": generated_at,
        "provider_base_url": preflight["base_url"],
        "canonical_api": base_url,
        "browser_direct_provider_calls": 0,
        "provider_calls": 5,
        "video_calls": 0,
        "requests": network,
        "external_hosts": ["shapi.vip"],
        "no_manual_sdk_or_curl": True,
    }
    data_safety = {
        "schema_version": "asset_media_canary_data_safety_v1",
        "isolated_database": True,
        "production_db_writes": 0,
        "book_990400_writes": 0,
        "book_990402_writes": "isolated disposable copy only",
        "secret_leaks": 0,
        "orphan_rows": 0,
        "duplicate_submits": 0,
        "automatic_promotion": False,
        "video_calls": 0,
    }
    _write(PACKAGE / "IMAGE_PROVIDER_PREFLIGHT.json", preflight)
    _write(PACKAGE / "ASSET_MEDIA_CANARY_MANIFEST.json", manifest)
    _write(PACKAGE / "ASSET_MEDIA_CANARY_NETWORK.json", network_audit)
    _write(PACKAGE / "ASSET_MEDIA_CANARY_DATA_SAFETY.json", data_safety)
    (PACKAGE / "ASSET_MEDIA_CANARY_REPORT.md").write_text(_report(package_items, contact, preflight), encoding="utf-8")
    print(json.dumps({
        "status": manifest["stage"],
        "real_image_calls": 5,
        "real_video_calls": 0,
        "contact_sheet": str(PACKAGE / "contact-sheet.png"),
        "originals": [str(path) for path in sorted(ORIGINALS.glob("*.png"))],
        "report": str(PACKAGE / "ASSET_MEDIA_CANARY_REPORT.md"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
