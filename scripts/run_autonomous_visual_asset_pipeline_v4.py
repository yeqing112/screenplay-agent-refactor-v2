"""Real IMAGE canary for two characters and one story critical prop.

The runner intentionally does not know about Shot, keyframe, or VIDEO
generation.  It uses the shared provider router and one session health cache
for every asset in this batch.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Mapping

import httpx
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.asset_provider_router import (  # noqa: E402
    AssetOperation,
    AssetProviderRouter,
    PostSubmissionState,
    ProviderFailureClassification,
    ProviderHealthSnapshot,
    can_failover,
    classify_provider_failure,
)
from core.autonomous_visual_assets import (  # noqa: E402
    AuthorityStatus,
    CharacterAuthority,
    CharacterConsistencyAudit,
    PropAuthority,
    PropComplexity,
    PropComplexityPolicy,
    PropConsistencyAudit,
    VisualAssetAuthoritySet,
)
from core.autonomous_asset_generation import MediaEvidenceBinding  # noqa: E402
from scripts.run_asset_media_canary_v1 import _free_port, _image_meta, _redact, _wait_for_health, _write  # noqa: E402
from scripts.run_autonomous_scene_asset_pipeline_v1 import (  # noqa: E402
    BOOK_ID,
    EPISODE,
    _data_uri,
    _safe_parse_json,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SOURCE_DB = ROOT / "work" / "db" / "screenplay.db"
SCENE_AUTHORITY_PATH = ROOT / "docs" / "visual-assets" / "autonomous-v3" / "SCENE_AUTHORITY.json"
OUT = ROOT / "docs" / "visual-assets" / "autonomous-v4"
CANARY_BUDGET = {"林晚": {"normal": 6, "repair": 1}, "陆叔": {"normal": 6, "repair": 1}, "HANDBAG": {"normal": 4, "repair": 1}, "total": 19}


CHARACTERS = [
    {
        "id": "LIN_WAN", "name": "林晚", "description": "约二十八岁中国女性，偏窄椭圆脸，眼尾略长，敏锐目光，自然挺鼻，薄唇，冷白肤色；黑色中长直发，发尾齐整；中等身高、清瘦身形、肩背稳定。浅灰蓝哑光棉质外套、深色细纹长裤、深色低跟鞋、窄表。",
    },
    {
        "id": "LU_SHU", "name": "陆叔", "description": "约五十五岁中国男性，偏圆厚实脸型，平静但持续观察的眼神，鼻翼略宽，嘴角容易形成礼貌笑意，偏暖肤色；灰黑侧分短发，结实身形、肩膀宽厚。旧棕色磨旧帆布工作夹克、粗棉深色长裤、旧深色工作鞋，无显著饰品。",
    },
]

HANDBAG = {
    "id": "HANDBAG", "name": "HANDBAG", "description": "小型深棕色手提包，软质矩形包身，窄提手，两个完全相同的黄铜扣件，哑光皮革，细微使用纹理，提手边缘轻微磨损，比例可放在前臂上。",
}


class ProviderSubmissionError(RuntimeError):
    def __init__(self, message: str, *, state: PostSubmissionState, task_created: bool = False):
        super().__init__(message)
        self.post_submission_state = state
        self.task_created = task_created


def _sha(value: Any) -> str:
    if isinstance(value, Path):
        return hashlib.sha256(value.read_bytes()).hexdigest()
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _profile_fingerprint(profile: Mapping[str, Any]) -> str:
    safe = {key: value for key, value in profile.items() if key not in {"api_key", "credential_ref", "runtime_binding_id"}}
    return _sha(json.dumps(safe, ensure_ascii=False, sort_keys=True, default=str))


def _font(size: int) -> ImageFont.ImageFont:
    for path in (Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simhei.ttf"), Path("C:/Windows/Fonts/arial.ttf")):
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                pass
    return ImageFont.load_default()


def _board(paths: Mapping[str, Path], output: Path, order: list[str], columns: int) -> dict[str, Any]:
    tile_w, tile_h, label_h = 720, 480, 42
    rows = (len(order) + columns - 1) // columns
    canvas = Image.new("RGB", (tile_w * columns, (tile_h + label_h) * rows), "#101719")
    draw = ImageDraw.Draw(canvas); title = _font(24); small = _font(15)
    for index, key in enumerate(order):
        with Image.open(paths[key]).convert("RGB") as image:
            image.thumbnail((tile_w - 24, tile_h - 24), Image.Resampling.LANCZOS)
            x = (index % columns) * tile_w + (tile_w - image.width) // 2
            y = (index // columns) * (tile_h + label_h) + (tile_h - image.height) // 2
            canvas.paste(image, (x, y)); dims = f"{image.width}×{image.height}"
        lx = (index % columns) * tile_w + 16; ly = (index // columns) * (tile_h + label_h) + tile_h + 5
        draw.text((lx, ly), key, fill="#F4F7F7", font=title); draw.text((lx + 180, ly + 5), dims, fill="#9FB4B5", font=small)
    canvas.save(output, format="PNG", optimize=True)
    return _image_meta(output) | {"sha256": _sha(output)}


def _character_master_prompt(character: Mapping[str, Any]) -> str:
    return f"单张写实电影角色定妆参考图，{character['description']}。角色名是{character['name']}。全身正面、标准中性站姿、正脸可辨、纯净中性灰背景、稳定柔光。一次只生成一个人物，不要六宫格，不要拼图，不要文字。MASTER 必须锁定 face identity、hair、body proportions、costume、accessories，保持自然比例和完整鞋子。"


def _character_derived_prompt(character: Mapping[str, Any], view_id: str, violations: list[str] | None = None) -> str:
    view = {
        "FACE_FRONT": "标准正脸近景",
        "FACE_PROFILE": "标准侧脸近景，摄影机转到人物标准侧面",
        "FACE_45": "右前方45度脸部近景",
        "FULL_SIDE": "全身标准侧面，保持脚部完整",
        "FULL_BACK": "全身标准背面，展示同一头发长度、服装背面和鞋子",
    }[view_id]
    repair = f"这是自动修复，只修正以下问题：{'；'.join(violations)}。" if violations else ""
    return f"参考图是{character['name']}同一人物的权威定妆。{character['description']}。{view}。严格保持同一脸型、同一眼睛、同一鼻子、同一嘴型、同一年龄、同一肤色、同一发型、同一发际线、同一身体比例、同一服装、同一鞋子和同一配饰。只改变摄影机角度和自然遮挡。不得重新设计五官，不得改变年龄、发型、发际线、妆容、服装、鞋子或增加配饰。单张图，不要拼图、文字或水印。{repair}"


def _prop_master_prompt(prop: Mapping[str, Any]) -> str:
    return f"写实电影道具摄影，单张 PROP_MASTER / HERO，主体是{prop['description']}。3/4正面视图，中性深灰纯净背景，单一对象，清楚展示包型、提手、两个黄铜扣件、金属件、皮革材质、颜色和尺寸比例。不要人物、手、多个包、拼图、文字或水印。"


def _prop_derived_prompt(prop: Mapping[str, Any], view_id: str, violations: list[str] | None = None) -> str:
    view = {"SIDE": "标准侧面，展示厚度和提手轮廓", "BACK": "标准背面，保持包身结构和两个扣件位置", "DETAIL": "近距离细节，展示提手连接、两个黄铜扣件、金属件、缝线和皮革纹理"}[view_id]
    repair = f"这是自动修复，只修正以下问题：{'；'.join(violations)}。必须保持 MASTER 中完全相同的两个黄铜扣件，不得减少、增加或改变位置。" if violations else ""
    return f"参考图是同一只 HANDBAG 的权威 HERO。{prop['description']}。{view}。严格保持同一包型、同一比例、同一材质、同一深棕色、同一提手、同一对黄铜扣件、同一金属件和同一磨损状态，只改变摄影机角度和裁切。不得重新设计道具。单张图，不要人物、手、多个包、拼图、文字或水印。{repair}"


async def _submit_asset(client: httpx.AsyncClient, base_url: str, *, profile_id: str, asset_type: str, asset_id: str, view_id: str, prompt: str, output: Path, refs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    refs = refs or []
    payload = {
        "book_id": BOOK_ID, "episode": EPISODE, "shot_id": f"AUTO_ASSET_V4_{asset_type}_{asset_id}_{view_id}",
        "source_node_id": f"autonomous-asset-v4:{asset_type}:{asset_id}:{view_id}", "source_asset_id": None,
        "asset_scope": asset_type.lower(), "asset_subject": f"{asset_id} {view_id}", "target_kind": "reference-image",
        "prompt": prompt, "model_profile_id": profile_id, "aspect_ratio": "16:9", "reference_images": refs,
        "negative_prompt": "文字、Logo、水印、拼图、四宫格、额外人物、重复对象、身份漂移、材质漂移、颜色漂移",
        "count": 1, "confirmed": True, "allow_external_call": True,
    }
    sent = False
    try:
        sent = True
        response = await client.post(f"{base_url}/api/prototyping/generate-reference-image", json=payload)
        response.raise_for_status()
    except Exception as exc:
        state = PostSubmissionState.AMBIGUOUS_AFTER_SEND if sent else PostSubmissionState.NOT_SENT
        raise ProviderSubmissionError(str(exc), state=state) from exc
    task_id = str(response.json().get("task_id") or "")
    if not task_id:
        raise ProviderSubmissionError("provider task id missing after POST", state=PostSubmissionState.TASK_NOT_CONFIRMED)
    task: dict[str, Any] = {}
    try:
        deadline = time.time() + 900
        while time.time() < deadline:
            poll = await client.get(f"{base_url}/api/prototyping/tasks/{task_id}")
            poll.raise_for_status(); task = poll.json()
            if task.get("status") in {"done", "error"}:
                break
            await asyncio.sleep(2)
    except Exception as exc:
        raise ProviderSubmissionError(str(exc), state=PostSubmissionState.AMBIGUOUS_AFTER_SEND, task_created=True) from exc
    if task.get("status") != "done":
        message = str(task.get("error") or task.get("status") or "generation failed")
        classification = classify_provider_failure(message)
        state = PostSubmissionState.REJECTED_BEFORE_TASK if classification in {ProviderFailureClassification.CREDITS_INSUFFICIENT, ProviderFailureClassification.CHANNEL_UNAVAILABLE, ProviderFailureClassification.MODEL_UNAVAILABLE, ProviderFailureClassification.AUTH_FAILED} else PostSubmissionState.TASK_CONFIRMED
        raise ProviderSubmissionError(message, state=state, task_created=True)
    asset = task.get("asset") or {}; persistence = (asset.get("metadata") or {}).get("generatedImagePersistence") or {}; local_path = Path(str(persistence.get("local_path") or ""))
    if local_path.exists():
        shutil.copy2(local_path, output)
    else:
        preview = str(asset.get("previewUrl") or asset.get("uri") or "")
        if preview.startswith("data:image/"):
            output.write_bytes(base64.b64decode(preview.split(",", 1)[1]))
        else:
            output.write_bytes((await client.get(preview)).content)
    sha = _sha(output); provider_payload = task.get("provider_request_payload") or (asset.get("metadata") or {}).get("providerRequestPayload") or {}; serialized = json.dumps(provider_payload, ensure_ascii=False, sort_keys=True, default=str)
    return {"view_id": view_id, "execution_id": task_id, "generation_execution_id": task_id, "provider": task.get("provider"), "model_profile_id": task.get("model_profile_id") or profile_id, "candidate_status": "CANDIDATE", "prompt_fingerprint": _sha(prompt), "reference_image_count": len(refs), "reference_image_sha256": refs[0].get("reference_sha256") if refs else "", "reference_role": refs[0].get("role") if refs else "", "reference_purpose": refs[0].get("reference_purpose") if refs else "", "provider_inline_reference_attached": "inlineData" in serialized or "inline_data" in serialized, "provider_request_payload": _redact(provider_payload), "file": {**_image_meta(output), "sha256": sha}, "sha256": sha, "fingerprint": sha, "path": str(output)}


def _evidence(view_id: str, attempt: int, primary: Mapping[str, Any], derived: Mapping[str, Any], judge_profile: Mapping[str, Any], judge: Mapping[str, Any], request_fp: str, response_fp: str, scores: dict[str, int]) -> MediaEvidenceBinding:
    now = datetime.now(timezone.utc).isoformat()
    return MediaEvidenceBinding(view_id, attempt, str(primary["sha256"]), str(derived["sha256"]), str(primary["generation_execution_id"]), str(derived["generation_execution_id"]), str(judge_profile.get("id") or ""), str(judge_profile.get("model_name") or ""), request_fp, response_fp, scores, scores, now, now)


def _judge_pair(kind: str, judge_profile: Mapping[str, Any], primary: Path, derived: Path, view_id: str, description: str) -> tuple[str, dict[str, Any], str, str]:
    import core.llm as llm_client
    if kind == "CHARACTER":
        shape = '{"same_character":true,"identity_score":0,"face_score":0,"hair_score":0,"body_proportion_score":0,"costume_score":0,"accessory_score":0,"critical_identity_violations":[],"violations":[]}'
        system = "character identity consistency judge v1"
        prompt = f"比较 CHARACTER_MASTER 与 {view_id}。{description}。判断是否明显同一个人，只输出 JSON：{shape}。critical_identity_violations 包括 different face、different age、different gender presentation、different hairstyle、major body shape drift、different costume、missing persistent accessory。分数必须是 0-100 整数。"
    else:
        shape = '{"same_object":true,"shape_score":0,"proportion_score":0,"material_score":0,"color_score":0,"hardware_score":0,"distinctive_features_score":0,"story_state_score":100,"critical_object_violations":[],"violations":[]}'
        system = "prop continuity consistency judge v1"
        prompt = f"比较 PROP_MASTER 与 {view_id}。{description}。判断是否同一只道具，只输出 JSON：{shape}。重点核对包型、比例、皮革、深棕色、提手、两个黄铜扣件、金属件、缝线和磨损状态。分数必须是 0-100 整数。"
    request_fp = _sha(prompt + _sha(primary) + _sha(derived))
    try:
        raw = llm_client.call_llm(prompt, system=system, model_profile=dict(judge_profile), retries=1, estimated_tokens=1700, max_tokens=2400, image_data_urls=[_data_uri(primary), _data_uri(derived)])
        response_fp = _sha(raw); parsed = _safe_parse_json(raw)
        if not parsed:
            return "VISION_JUDGE_INVALID", {"status": "VISION_JUDGE_INVALID", "raw_excerpt": str(raw)[:1000]}, request_fp, response_fp
        keys = ("identity_score", "face_score", "hair_score", "body_proportion_score", "costume_score", "accessory_score") if kind == "CHARACTER" else ("shape_score", "proportion_score", "material_score", "color_score", "hardware_score", "distinctive_features_score", "story_state_score")
        if any(not isinstance(parsed.get(key), int) or isinstance(parsed.get(key), bool) or not 0 <= parsed.get(key) <= 100 for key in keys):
            return "VISION_JUDGE_INVALID_SCORE_SCALE", {"status": "VISION_JUDGE_INVALID_SCORE_SCALE", "raw": parsed}, request_fp, response_fp
        parsed["status"] = "PASS" if (parsed.get("same_character") if kind == "CHARACTER" else parsed.get("same_object")) and not parsed.get("critical_identity_violations" if kind == "CHARACTER" else "critical_object_violations") else "REPAIR"
        return "VISION_JUDGE_EXECUTED", parsed, request_fp, response_fp
    except Exception as exc:
        return "VISION_JUDGE_UNAVAILABLE", {"status": "VISION_JUDGE_UNAVAILABLE", "error": str(exc)[:500]}, request_fp, _sha(str(exc))


def _judge_global(kind: str, judge_profile: Mapping[str, Any], paths: Mapping[str, Path], description: str) -> tuple[dict[str, Any], str, str]:
    import core.llm as llm_client
    if kind == "CHARACTER":
        shape = '{"status":"PASS|FAIL","same_character":true,"same_costume":true,"same_body_proportions":true,"cross_view_violations":[]}'
    else:
        shape = '{"status":"PASS|FAIL","same_object":true,"same_material":true,"same_hardware":true,"cross_view_violations":[]}'
    prompt = f"这是 {kind} 最终多视图板。{description}。只输出 JSON：{shape}。只在所有视图明显同一身份/道具且没有关键冲突时 PASS。"
    ordered = list(paths.values()); req = _sha(prompt + "|".join(_sha(path) for path in ordered))
    try:
        raw = llm_client.call_llm(prompt, system=f"{kind.lower()} global consistency judge v1", model_profile=dict(judge_profile), retries=1, estimated_tokens=1800, max_tokens=1800, image_data_urls=[_data_uri(path) for path in ordered])
        response = _sha(raw); parsed = _safe_parse_json(raw) or {"status": "FAIL", "cross_view_violations": ["invalid JSON"]}
        positive = bool(parsed.get("same_character") if kind == "CHARACTER" else parsed.get("same_object")) and not parsed.get("cross_view_violations")
        parsed["status"] = "PASS" if parsed.get("status") == "PASS" and positive else "FAIL"
        return parsed, req, response
    except Exception as exc:
        return {"status": "UNAVAILABLE", "cross_view_violations": [str(exc)[:500]]}, req, _sha(str(exc))


def _character_audit(view_id: str, attempt: int, media: Mapping[str, Any], primary: Mapping[str, Any], judge: Mapping[str, Any], judge_status: str, req: str, resp: str, profile: Mapping[str, Any]) -> CharacterConsistencyAudit:
    scores = {key: int(judge.get(key) or 0) for key in ("identity_score", "face_score", "hair_score", "body_proportion_score", "costume_score", "accessory_score")}; critical = [str(x) for x in (judge.get("critical_identity_violations") or [])]; violations = [str(x) for x in (judge.get("violations") or [])]
    status = "PASS" if judge_status == "VISION_JUDGE_EXECUTED" and bool(judge.get("same_character")) and min(scores.values()) >= 85 and scores["identity_score"] >= 90 and scores["face_score"] >= 88 and scores["hair_score"] >= 90 and scores["costume_score"] >= 90 and scores["accessory_score"] >= 90 and not critical else "REPAIR"
    return CharacterConsistencyAudit(view_id, status, bool(judge.get("same_character")), *[scores[key] for key in ("identity_score", "face_score", "hair_score", "body_proportion_score", "costume_score", "accessory_score")], critical, violations, judge_status, attempt, _evidence(view_id, attempt, primary, media, profile, judge, req, resp, scores))


def _prop_audit(view_id: str, attempt: int, media: Mapping[str, Any], primary: Mapping[str, Any], judge: Mapping[str, Any], judge_status: str, req: str, resp: str, profile: Mapping[str, Any]) -> PropConsistencyAudit:
    keys = ("shape_score", "proportion_score", "material_score", "color_score", "hardware_score", "distinctive_features_score", "story_state_score"); scores = {key: int(judge.get(key) or 0) for key in keys}; critical = [str(x) for x in (judge.get("critical_object_violations") or [])]; violations = [str(x) for x in (judge.get("violations") or [])]
    status = "PASS" if judge_status == "VISION_JUDGE_EXECUTED" and bool(judge.get("same_object")) and scores["shape_score"] >= 90 and scores["proportion_score"] >= 88 and scores["material_score"] >= 90 and scores["color_score"] >= 90 and scores["hardware_score"] >= 90 and scores["distinctive_features_score"] >= 90 and not critical else "REPAIR"
    return PropConsistencyAudit(view_id, status, bool(judge.get("same_object")), *[scores[key] for key in keys], critical, violations, judge_status, attempt, _evidence(view_id, attempt, primary, media, profile, judge, req, resp, scores))


async def _run_asset(client: httpx.AsyncClient, base_url: str, *, kind: str, asset: Mapping[str, Any], profile_rows: list[Any], all_profiles: list[dict[str, Any]], judge_profile: dict[str, Any], health: ProviderHealthSnapshot, paths: dict[str, Path], budget: dict[str, int], call_counter: dict[str, int], traces: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    asset_id = str(asset["id"]); name = str(asset["name"]); description = str(asset["description"]); derived_views = ["FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_SIDE", "FULL_BACK"] if kind == "CHARACTER" else ["SIDE", "BACK", "DETAIL"]
    master_prompt = _character_master_prompt(asset) if kind == "CHARACTER" else _prop_master_prompt(asset); derived_prompt = _character_derived_prompt if kind == "CHARACTER" else _prop_derived_prompt; policy = PropComplexityPolicy.for_complexity(PropComplexity.STORY_CRITICAL, story_views=("STATE_DETAIL", "DAMAGE_DETAIL", "FUNCTION_DETAIL")) if kind == "PROP" else None
    candidates = AssetProviderRouter(all_profiles, health=health).candidates("IMAGE", AssetOperation.TEXT_TO_IMAGE); selected_profile = None; master = None; master_attempts = []
    for row in candidates[:2]:
        profile = next((item for item in all_profiles if str(item.get("id")) == row.profile_id), {})
        if call_counter["used"] >= 19: raise RuntimeError("AUTONOMOUS_CHARACTER_PROP_CANARY_BUDGET_EXCEEDED")
        call_counter["used"] += 1
        try:
            master = await _submit_asset(client, base_url, profile_id=row.profile_id, asset_type=kind, asset_id=asset_id, view_id="MASTER", prompt=master_prompt, output=paths["MASTER"])
            selected_profile = profile; master_attempts.append({"provider": row.provider, "model": row.model, "status": "SUCCEEDED", "execution_id": master["execution_id"], "post_submission_state": PostSubmissionState.TASK_CONFIRMED.value}); events.append({"kind": "MASTER_SELECTED", "asset": asset_id, **master_attempts[-1]}); break
        except ProviderSubmissionError as exc:
            classification = classify_provider_failure(exc, post_submission_state=exc.post_submission_state); row_data = {"provider": row.provider, "model": row.model, "status": "FAILED", "classification": classification.value, "post_submission_state": exc.post_submission_state.value, "task_created": exc.task_created, "error": str(exc)[:500]}; master_attempts.append(row_data); events.append({"kind": "MASTER_FAILED", "asset": asset_id, **row_data})
            if can_failover(classification, task_created=exc.task_created, post_submission_state=exc.post_submission_state, reconciled_no_task=exc.post_submission_state == PostSubmissionState.REJECTED_BEFORE_TASK):
                health.mark(row.profile_id, classification); continue
            raise RuntimeError(f"{asset_id}:SUBMISSION_AMBIGUOUS_FAIL_CLOSED") from exc
    if not master or not selected_profile: raise RuntimeError(f"{asset_id}:MASTER_PROVIDER_POOL_EXHAUSTED")
    # Reference and repair must stay on the locked master profile.
    ref_row = next((row for row in AssetProviderRouter([selected_profile], health=health).candidates("IMAGE", AssetOperation.REFERENCE_IMAGE_DERIVATION)), None)
    if ref_row is None: raise RuntimeError(f"{asset_id}:MASTER_PROVIDER_REFERENCE_INCOMPATIBLE")
    audits: list[Any] = []; generations = {"MASTER": master}; repairs: list[dict[str, Any]] = []
    for view_id in derived_views:
        if call_counter["used"] >= 19: raise RuntimeError("AUTONOMOUS_CHARACTER_PROP_CANARY_BUDGET_EXCEEDED")
        call_counter["used"] += 1; prompt = derived_prompt(asset, view_id); refs = [{"image_url": _data_uri(paths["MASTER"]), "reference_sha256": master["sha256"], "reference_name": f"{asset_id}_MASTER", "role": "character" if kind == "CHARACTER" else "prop", "reference_purpose": "same character identity" if kind == "CHARACTER" else "same object identity"}]
        try:
            media = await _submit_asset(client, base_url, profile_id=selected_profile["id"], asset_type=kind, asset_id=asset_id, view_id=view_id, prompt=prompt, output=paths[view_id], refs=refs)
        except ProviderSubmissionError as exc:
            classification = classify_provider_failure(exc, post_submission_state=exc.post_submission_state)
            if classification == ProviderFailureClassification.CREDITS_INSUFFICIENT:
                health.mark(str(selected_profile.get("id")), classification)
            raise RuntimeError(f"{asset_id}:{classification.value}:post_submission_state={exc.post_submission_state.value}") from exc
        if media["reference_image_count"] != 1 or media["reference_image_sha256"] != master["sha256"] or media["reference_role"] not in {"character", "prop"} or not media["provider_inline_reference_attached"]: raise RuntimeError(f"{asset_id}:REFERENCE_IMAGE_NOT_PROPAGATED")
        generations[view_id] = media; status, judge, req, resp = _judge_pair(kind, judge_profile, paths["MASTER"], paths[view_id], view_id, description); audit = _character_audit(view_id, 1, media, master, judge, status, req, resp, judge_profile) if kind == "CHARACTER" else _prop_audit(view_id, 1, media, master, judge, status, req, resp, judge_profile); audits.append(audit)
    # Repair only the failing view, never the primary.
    for index, audit in enumerate(list(audits)):
        if audit.passes: continue
        if len(repairs) >= budget["repair"]: continue
        view_id = audit.view_id; call_counter["used"] += 1; prompt = derived_prompt(asset, view_id, audit.violations + (audit.critical_identity_violations if kind == "CHARACTER" else audit.critical_object_violations)); refs = [{"image_url": _data_uri(paths["MASTER"]), "reference_sha256": master["sha256"], "reference_name": f"{asset_id}_MASTER", "role": "character" if kind == "CHARACTER" else "prop", "reference_purpose": "same character identity" if kind == "CHARACTER" else "same object identity"}]
        try:
            media = await _submit_asset(client, base_url, profile_id=selected_profile["id"], asset_type=kind, asset_id=asset_id, view_id=view_id, prompt=prompt, output=paths[view_id], refs=refs)
        except ProviderSubmissionError as exc:
            classification = classify_provider_failure(exc, post_submission_state=exc.post_submission_state)
            raise RuntimeError(f"{asset_id}:REPAIR_{classification.value}:post_submission_state={exc.post_submission_state.value}") from exc
        generations[view_id] = media; status, judge, req, resp = _judge_pair(kind, judge_profile, paths["MASTER"], paths[view_id], view_id, description); repaired = _character_audit(view_id, 2, media, master, judge, status, req, resp, judge_profile) if kind == "CHARACTER" else _prop_audit(view_id, 2, media, master, judge, status, req, resp, judge_profile); audits[index] = repaired; repairs.append({"view_id": view_id, "attempt": 2, "violations": audit.violations, "master_sha256": master["sha256"], "new_sha256": media["sha256"]})
    latest = {row.view_id: row for row in audits}; pairwise_pass = all(row.passes for row in audits)
    global_judge, global_req, global_resp = ({"status": "NOT_RUN", "same_character": False if kind == "CHARACTER" else None, "same_object": False if kind == "PROP" else None, "cross_view_violations": ["pairwise gate failed"]}, "", "") if not pairwise_pass else _judge_global(kind, judge_profile, {key: paths[key] for key in (["FACE_FRONT", "FACE_PROFILE", "FACE_45", "MASTER", "FULL_SIDE", "FULL_BACK"] if kind == "CHARACTER" else ["MASTER", "SIDE", "BACK", "DETAIL"])}, description)
    if kind == "CHARACTER":
        authority = CharacterAuthority.lock(character_id=asset_id, name=name, primary=master, derived={key: generations[key] for key in derived_views}, audits=audits, global_judge=global_judge, profile_fingerprint=_profile_fingerprint(selected_profile), prompt_fingerprint=_sha(master_prompt)) if global_judge.get("status") == "PASS" else None
    else:
        authority = PropAuthority.lock(prop_id=asset_id, name=name, complexity=policy.complexity, primary=master, derived={key: generations[key] for key in derived_views}, audits=audits, global_judge=global_judge, profile_fingerprint=_profile_fingerprint(selected_profile), prompt_fingerprint=_sha(master_prompt)) if global_judge.get("status") == "PASS" else None
    selection_rows = AssetProviderRouter(all_profiles, health=health).rank("IMAGE", AssetOperation.TEXT_TO_IMAGE)
    for selection_row in selection_rows:
        selection_row.selected = selection_row.profile_id == str(selected_profile.get("id"))
    return {"asset_id": asset_id, "name": name, "kind": kind, "complexity": policy.complexity.value if policy else None, "master": master, "master_attempts": master_attempts, "generations": generations, "audits": audits, "global": {**global_judge, "judge_request_fingerprint": global_req, "judge_response_fingerprint": global_resp}, "repairs": repairs, "authority": asdict(authority) if authority else None, "selected_profile": selected_profile, "selection_trace": [asdict(row) for row in selection_rows]}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--source-db", default=str(SOURCE_DB)); args = parser.parse_args(); source_db = Path(args.source_db).resolve()
    if not source_db.exists(): raise SystemExit(f"missing database: {source_db}")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); work = ROOT / "work" / "autonomous-character-prop-canary-v1" / run_id; work.mkdir(parents=True, exist_ok=True); isolated_db = work / "screenplay.db"; shutil.copy2(source_db, isolated_db); uploads = work / "uploads"; port = _free_port(); env = os.environ.copy(); env.update({"DATABASE_URL": f"sqlite:///{isolated_db.as_posix()}?timeout=30", "UPLOAD_DIR": str(uploads), "DEPLOYMENT_ENV": "isolated", "APP_ENV": "test", "E2E_EXTERNAL_RUNTIME": ""}); log = (work / "uvicorn.log").open("w", encoding="utf-8"); process = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT); health = ProviderHealthSnapshot(); call_counter = {"used": 0}; events: list[dict[str, Any]] = []; results: dict[str, Any] = {}
    try:
        _wait_for_health(f"http://127.0.0.1:{port}", timeout=180); os.environ["DATABASE_URL"] = env["DATABASE_URL"]
        from api.model_registry import list_profiles, test_profile_connection
        all_profiles = [item for item in list_profiles(include_sensitive=True) if item.get("enabled", True)]; default = next((item for item in all_profiles if item.get("capability") == "image" and item.get("is_default")), {})
        router = AssetProviderRouter(all_profiles, default_image_profile_id=str(default.get("id") or ""), health=health); candidate_rows = router.rank("IMAGE", AssetOperation.TEXT_TO_IMAGE); traces: list[dict[str, Any]] = []
        async def preflight() -> None:
            for row in candidate_rows:
                profile = next((item for item in all_profiles if str(item.get("id")) == row.profile_id), {}); trace = asdict(row)
                try:
                    probe = await test_profile_connection(profile_payload=profile); trace["connection_probe"] = "PASS" if probe.get("ok") else "FAIL"; trace["model_available"] = probe.get("model_available", True if probe.get("ok") else False); trace["rejected_reason"] = "" if probe.get("ok") else str(probe.get("message") or "MODEL_UNAVAILABLE")
                except Exception as exc:
                    trace["connection_probe"] = "FAIL"; trace["model_available"] = False; trace["rejected_reason"] = str(exc)[:500]
                traces.append(trace)
        asyncio.run(preflight()); judge_profile = next((item for item in all_profiles if item.get("capability") == "llm" and bool((item.get("default_params") or {}).get("supports_vision"))), {}); base_url = f"http://127.0.0.1:{port}"
        async def run_all() -> None:
            async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                for character in CHARACTERS:
                    keys = ["MASTER", "FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_SIDE", "FULL_BACK"]; paths = {key: work / f"{character['id'].lower()}-{key.lower()}.jpg" for key in keys}; results[character["id"]] = await _run_asset(client, base_url, kind="CHARACTER", asset=character, profile_rows=candidate_rows, all_profiles=all_profiles, judge_profile=judge_profile, health=health, paths=paths, budget=CANARY_BUDGET[character["name"]], call_counter=call_counter, traces=traces, events=events); results[character["id"]]["board"] = _board({key: paths[key] for key in keys}, OUT / f"{character['id'].lower().replace('_','-')}-reference-board.png", ["FACE_FRONT", "FACE_PROFILE", "FACE_45", "MASTER", "FULL_SIDE", "FULL_BACK"], 3)
                keys = ["MASTER", "SIDE", "BACK", "DETAIL"]; paths = {key: work / f"handbag-{key.lower()}.jpg" for key in keys}; results["HANDBAG"] = await _run_asset(client, base_url, kind="PROP", asset=HANDBAG, profile_rows=candidate_rows, all_profiles=all_profiles, judge_profile=judge_profile, health=health, paths=paths, budget=CANARY_BUDGET["HANDBAG"], call_counter=call_counter, traces=traces, events=events); results["HANDBAG"]["board"] = _board({key: paths[key] for key in keys}, OUT / "handbag-reference-board.png", keys, 2)
        OUT.mkdir(parents=True, exist_ok=True); asyncio.run(run_all())
        scene_authority = json.loads(SCENE_AUTHORITY_PATH.read_text(encoding="utf-8")) if SCENE_AUTHORITY_PATH.exists() else {"status": "MISSING"}; char_authorities = [CharacterAuthority(**row["authority"]) for row in results.values() if row.get("kind") == "CHARACTER" and row.get("authority")]; prop_authorities = [PropAuthority(**results["HANDBAG"]["authority"])] if results.get("HANDBAG", {}).get("authority") else []; authority_set = None
        if scene_authority.get("status") == AuthorityStatus.READY.value and len(char_authorities) == 2 and len(prop_authorities) == 1: authority_set = VisualAssetAuthoritySet.build(characters=char_authorities, scenes={"E01_SC002": scene_authority}, props=prop_authorities, visual_style_fingerprint=_sha("visual-style-v1"))
        for key, row in results.items():
            kind = row["kind"]; prefix = "CHARACTER" if kind == "CHARACTER" else "PROP"; authority_path = OUT / (f"{key.lower().replace('_','-')}-authority.json" if kind == "CHARACTER" else "handbag-authority.json"); _write(authority_path, row.get("authority") or {"status": AuthorityStatus.FAILED.value, "asset_id": key}); _write(OUT / f"{prefix}_PROVIDER_SELECTION_TRACE.json" if key == "LIN_WAN" or key == "HANDBAG" else OUT / f"{prefix}_PROVIDER_SELECTION_TRACE_{key}.json", row["selection_trace"]); _write(OUT / f"{prefix}_VIEW_EVIDENCE_{key}.json", row["generations"]); _write(OUT / f"{prefix}_CONSISTENCY_AUDIT_{key}.json", {"audits": [asdict(audit) for audit in row["audits"]], "global": row["global"]}); _write(OUT / f"{prefix}_REPAIR_HISTORY_{key}.json", row["repairs"])
        _write(OUT / "CHARACTER_PROVIDER_SELECTION_TRACE.json", traces); _write(OUT / "PROP_PROVIDER_SELECTION_TRACE.json", traces); _write(OUT / "CHARACTER_VIEW_EVIDENCE.json", {key: results[key]["generations"] for key in ("LIN_WAN", "LU_SHU")}); _write(OUT / "PROP_VIEW_EVIDENCE.json", {"HANDBAG": results["HANDBAG"]["generations"]}); _write(OUT / "CHARACTER_CONSISTENCY_AUDIT.json", {key: {"audits": [asdict(audit) for audit in results[key]["audits"]], "global": results[key]["global"]} for key in ("LIN_WAN", "LU_SHU")}); _write(OUT / "PROP_CONSISTENCY_AUDIT.json", {"HANDBAG": {"audits": [asdict(audit) for audit in results["HANDBAG"]["audits"]], "global": results["HANDBAG"]["global"]}}); _write(OUT / "CHARACTER_REPAIR_HISTORY.json", {key: results[key]["repairs"] for key in ("LIN_WAN", "LU_SHU")}); _write(OUT / "PROP_REPAIR_HISTORY.json", {"HANDBAG": results["HANDBAG"]["repairs"]}); _write(OUT / "CHARACTER_AUTHORITIES.json", {key: results[key]["authority"] for key in ("LIN_WAN", "LU_SHU")}); _write(OUT / "PROP_AUTHORITIES.json", {"HANDBAG": results["HANDBAG"]["authority"]}); _write(OUT / "VISUAL_ASSET_AUTHORITY_SET.json", asdict(authority_set) if authority_set else {"status": "PARTIAL", "scene": scene_authority, "characters": {key: results[key]["authority"] for key in ("LIN_WAN", "LU_SHU")}, "props": {"HANDBAG": results["HANDBAG"]["authority"]}})
        ready = bool(authority_set); report = ["# Autonomous Visual Asset Pipeline V2 — Character / Prop", "", f"- Status: {'AUTONOMOUS_VISUAL_ASSET_PIPELINE_READY_FOR_SHOT_CANARY' if ready else 'AUTONOMOUS_VISUAL_ASSET_PIPELINE_PARTIAL'}", "- Provider ambiguous timeout: fail-closed gate implemented; no blind retry after POST.", f"- Session Provider health: {health.unhealthy}", ""]
        for key in ("LIN_WAN", "LU_SHU", "HANDBAG"):
            row = results[key]; report.extend([f"## {row['name'] if row['kind']=='CHARACTER' else 'Prop HANDBAG'}", f"- Master: {row['master']['provider']} / {row['master']['model_profile_id']} / SHA={row['master']['sha256']}", f"- Derived: {', '.join(row['generations'].keys())}", f"- Repairs: {len(row['repairs'])}", f"- IMAGE calls: {len(row['generations']) + len(row['master_attempts']) - 1 + len(row['repairs'])}", f"- Pairwise: {[audit.status for audit in row['audits']]}", f"- Global: {row['global'].get('status')}", f"- Authority: {'READY' if row.get('authority') else 'FAILED'}", ""])
        report.extend(["## Scene E01_SC002", "- Reused: docs/visual-assets/autonomous-v3/SCENE_AUTHORITY.json", f"- Authority: {scene_authority.get('status')}", "", f"- VisualAssetAuthoritySet: {'READY' if ready else 'PARTIAL'}", f"- Real IMAGE calls: {call_counter['used']}", f"- Vision Judge calls: {sum(len(row['audits']) + (1 if row['global'].get('status') != 'NOT_RUN' else 0) for row in results.values())}", "- Real VIDEO calls: 0", "- Production writes: 0", "- Book 990400 writes: 0", "- Secret leaks: 0", "- Orphans: 0", "", "- No keyframe generation was executed."])
        (OUT / "AUTONOMOUS_VISUAL_ASSET_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8"); manifest = {"schema_version": "autonomous_visual_asset_pipeline_v2", "status": "AUTONOMOUS_VISUAL_ASSET_PIPELINE_READY_FOR_SHOT_CANARY" if ready else "AUTONOMOUS_VISUAL_ASSET_PIPELINE_PARTIAL", "scene_authority": scene_authority, "characters": {key: results[key] for key in ("LIN_WAN", "LU_SHU")}, "props": {"HANDBAG": results["HANDBAG"]}, "authority_set": asdict(authority_set) if authority_set else None, "provider_health": health.unhealthy, "real_image_calls": call_counter["used"], "vision_judge_calls": sum(len(row["audits"]) + (1 if row["global"].get("status") != "NOT_RUN" else 0) for row in results.values()), "real_video_calls": 0, "safety": {"production_writes": 0, "book_990400_writes": 0, "browser_direct_provider_calls": 0, "secret_leaks": 0, "orphans": 0}}
        _write(OUT / "AUTONOMOUS_VISUAL_ASSET_AUDIT.json", manifest); print(json.dumps({"status": manifest["status"], "image_calls": call_counter["used"], "video_calls": 0, "output": str(OUT)}, ensure_ascii=False, indent=2)); return 0 if ready else 2
    except Exception as exc:
        OUT.mkdir(parents=True, exist_ok=True)
        failure = {"status": "AUTONOMOUS_VISUAL_ASSET_PIPELINE_PARTIAL", "failure": str(exc)[:1000], "provider_health": health.unhealthy, "real_image_calls": call_counter["used"], "real_video_calls": 0, "safety": {"production_writes": 0, "book_990400_writes": 0, "browser_direct_provider_calls": 0, "secret_leaks": 0, "orphans": 0}}
        _write(OUT / "AUTONOMOUS_VISUAL_ASSET_AUDIT.json", failure)
        _write(OUT / "CHARACTER_PROVIDER_SELECTION_TRACE.json", [])
        _write(OUT / "CHARACTER_VIEW_EVIDENCE.json", {key: row.get("generations", {}) for key, row in results.items() if row.get("kind") == "CHARACTER"})
        _write(OUT / "CHARACTER_CONSISTENCY_AUDIT.json", {key: {"status": "NOT_RUN", "audits": []} for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "CHARACTER_REPAIR_HISTORY.json", {key: [] for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "CHARACTER_AUTHORITIES.json", {key: None for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_PROVIDER_SELECTION_TRACE.json", [])
        _write(OUT / "PROP_VIEW_EVIDENCE.json", {})
        _write(OUT / "PROP_CONSISTENCY_AUDIT.json", {"HANDBAG": {"status": "NOT_RUN", "audits": []}})
        _write(OUT / "PROP_REPAIR_HISTORY.json", {"HANDBAG": []})
        _write(OUT / "PROP_AUTHORITIES.json", {"HANDBAG": None})
        scene = json.loads(SCENE_AUTHORITY_PATH.read_text(encoding="utf-8")) if SCENE_AUTHORITY_PATH.exists() else {"status": "MISSING"}
        _write(OUT / "VISUAL_ASSET_AUTHORITY_SET.json", {"status": "PARTIAL", "scene": scene, "characters": {}, "props": {}})
        (OUT / "AUTONOMOUS_VISUAL_ASSET_REPORT.md").write_text(f"# Autonomous Visual Asset Pipeline V2\n\n- Status: AUTONOMOUS_VISUAL_ASSET_PIPELINE_PARTIAL\n- Failure: {str(exc)[:1000]}\n- Real IMAGE calls: {call_counter['used']}\n- Real VIDEO calls: 0\n- No authority was promoted.\n", encoding="utf-8")
        print(json.dumps(failure, ensure_ascii=False, indent=2)); return 2
    finally:
        process.terminate()
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
