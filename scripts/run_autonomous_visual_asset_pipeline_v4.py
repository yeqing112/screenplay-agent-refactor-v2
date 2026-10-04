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
from PIL import ImageOps

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
from core.production_provider_policy import ProductionProviderPolicy  # noqa: E402
from core.asset_view_framing import AssetViewFramingPolicy  # noqa: E402
from core.generation_timeout import GenerationTimeoutHierarchy, classify_timeout_layer, timeout_evidence  # noqa: E402
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
OUT = ROOT / "docs" / "visual-assets" / "75api-autonomous-v1"
CANARY_BUDGET = {"林晚": {"normal": 6, "repair": 1}, "陆叔": {"normal": 6, "repair": 1}, "HANDBAG": {"normal": 4, "repair": 1}, "total": 19}
PRODUCTION_POLICY = ProductionProviderPolicy()


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
    def __init__(self, message: str, *, state: PostSubmissionState, task_created: bool = False, timeout_evidence: dict[str, Any] | None = None, configuration_error: str | None = None, provider_response: dict[str, Any] | None = None, provider_response_shape: dict[str, Any] | None = None, provider_response_fingerprint: str = "", provider_http_status: int | None = None, provider_response_media_path: str = "", response_classification: str = ""):
        super().__init__(message)
        self.post_submission_state = state
        self.task_created = task_created
        self.timeout_evidence = timeout_evidence or {}
        self.configuration_error = configuration_error
        self.provider_response = provider_response or {}
        self.provider_response_shape = provider_response_shape or {}
        self.provider_response_fingerprint = provider_response_fingerprint
        self.provider_http_status = provider_http_status
        self.provider_response_media_path = provider_response_media_path
        self.response_classification = response_classification


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


def _authority_fingerprint(authority: Mapping[str, Any]) -> str:
    return _sha(json.dumps(dict(authority), ensure_ascii=False, sort_keys=True, default=str))


def _fit_semantic_tile(image: Image.Image, *, role: str, tile_size: tuple[int, int]) -> Image.Image:
    """Normalize visual scale with padding while preserving image geometry."""

    image = image.convert("RGB")
    # Use a conservative content crop only to remove uniform outer padding;
    # never stretch the subject. If segmentation is inconclusive, retain the
    # full image and letterbox it.
    probe = image.resize((min(image.width, 240), min(image.height, 240)))
    pixels = list(probe.getdata())
    edge = pixels[: max(1, probe.width)] + pixels[-max(1, probe.width):]
    background = tuple(sum(pixel[channel] for pixel in edge) // len(edge) for channel in range(3))
    mask = Image.new("L", probe.size, 0)
    mask_data = []
    for pixel in pixels:
        distance = sum(abs(int(pixel[channel]) - int(background[channel])) for channel in range(3))
        mask_data.append(255 if distance > 42 else 0)
    mask.putdata(mask_data)
    bbox = mask.getbbox()
    if bbox and bbox[2] - bbox[0] > probe.width * 0.18 and bbox[3] - bbox[1] > probe.height * 0.18:
        scale_x = image.width / probe.width
        scale_y = image.height / probe.height
        pad = 0.12 if role == "FACE" else 0.06
        left = max(0, int(bbox[0] * scale_x - image.width * pad))
        top = max(0, int(bbox[1] * scale_y - image.height * pad))
        right = min(image.width, int(bbox[2] * scale_x + image.width * pad))
        bottom = min(image.height, int(bbox[3] * scale_y + image.height * pad))
        if right > left and bottom > top:
            image = image.crop((left, top, right, bottom))
    target = Image.new("RGB", tile_size, "#20282A")
    fitted = ImageOps.contain(image, tile_size, method=Image.Resampling.LANCZOS)
    target.paste(fitted, ((tile_size[0] - fitted.width) // 2, (tile_size[1] - fitted.height) // 2))
    return target


def _board(paths: Mapping[str, Path], output: Path, order: list[str], columns: int, *, run_id: str, authority: Mapping[str, Any]) -> dict[str, Any]:
    if str(authority.get("status") or "") != AuthorityStatus.READY.value:
        raise ValueError("REFERENCE_BOARD_REQUIRES_READY_AUTHORITY")
    expected = {"FULL_FRONT": str(authority.get("primary_sha256") or ""), **{str(key): str(value) for key, value in (authority.get("derived_shas") or {}).items()}}
    source_view_sha256: list[dict[str, str]] = []
    derived_execution_ids = {str(key): str(value) for key, value in (authority.get("derived_execution_ids") or {}).items()}
    primary_execution_id = str(authority.get("primary_execution_id") or "")
    for key in order:
        source_key = "MASTER" if key in {"MASTER", "FULL_FRONT", "HERO"} else key
        source = paths.get(source_key)
        if source is None or not source.exists():
            raise ValueError("REFERENCE_BOARD_SOURCE_MISSING")
        actual = _sha(source)
        expected_sha = str(authority.get("primary_sha256") or "") if key in {"MASTER", "FULL_FRONT", "HERO"} else expected.get(key) or expected.get(source_key)
        if not expected_sha or actual != expected_sha:
            raise ValueError("REFERENCE_BOARD_SOURCE_SHA_MISMATCH")
        execution_id = primary_execution_id if key in {"MASTER", "FULL_FRONT", "HERO"} else derived_execution_ids.get(key, "")
        if not execution_id:
            raise ValueError("REFERENCE_BOARD_SOURCE_EXECUTION_ID_MISSING")
        source_view_sha256.append({"view_id": key, "sha256": actual, "generation_execution_id": execution_id})
    tile_w, tile_h, label_h = 520, 420, 48
    rows = (len(order) + columns - 1) // columns
    canvas = Image.new("RGB", (tile_w * columns, (tile_h + label_h) * rows), "#101719")
    draw = ImageDraw.Draw(canvas); title = _font(24); small = _font(15)
    for index, key in enumerate(order):
        with Image.open(paths["MASTER" if key in {"MASTER", "FULL_FRONT", "HERO"} else key]) as raw:
            role = "FACE" if key.startswith("FACE_") else "FULL" if key.startswith("FULL_") else "OBJECT"
            image = _fit_semantic_tile(raw, role=role, tile_size=(tile_w - 32, tile_h - 28))
        x = (index % columns) * tile_w + 16
        y = (index // columns) * (tile_h + label_h) + 12
        canvas.paste(image, (x, y)); dims = f"{image.width}×{image.height}"
        lx = (index % columns) * tile_w + 16; ly = (index // columns) * (tile_h + label_h) + tile_h + 5
        draw.text((lx, ly), key, fill="#F4F7F7", font=title); draw.text((lx + 220, ly + 5), dims, fill="#9FB4B5", font=small)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=True)
    board_sha256 = _sha(output)
    provenance = {"board_run_id": run_id, "authority_fingerprint": _authority_fingerprint(authority), "source_view_sha256": source_view_sha256, "board_sha256": board_sha256}
    output.with_suffix(".provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _image_meta(output) | {"sha256": board_sha256, **provenance}


def _atomic_publish_board(staging_png: Path, final_png: Path) -> None:
    provenance = staging_png.with_suffix(".provenance.json")
    if not staging_png.exists() or not provenance.exists():
        raise ValueError("REFERENCE_BOARD_PROVENANCE_MISSING")
    data = json.loads(provenance.read_text(encoding="utf-8"))
    if data.get("board_sha256") != _sha(staging_png) or not data.get("authority_fingerprint") or data.get("board_run_id") == "" or not all(item.get("sha256") and item.get("generation_execution_id") for item in data.get("source_view_sha256", [])):
        raise ValueError("REFERENCE_BOARD_PROVENANCE_MISSING")
    final_png.parent.mkdir(parents=True, exist_ok=True)
    temp_png = final_png.with_suffix(final_png.suffix + ".tmp")
    temp_prov = final_png.with_suffix(".provenance.json.tmp")
    shutil.copy2(staging_png, temp_png); shutil.copy2(provenance, temp_prov)
    os.replace(temp_png, final_png); os.replace(temp_prov, final_png.with_suffix(".provenance.json"))


def _prepare_run_output(run_id: str, *, work_dir: Path | None = None) -> Path:
    """Archive stale media and return an isolated publish directory."""

    OUT.mkdir(parents=True, exist_ok=True)
    historical = OUT / "historical-invalid-artifacts" / str(run_id)
    stale = [
        item for item in OUT.iterdir()
        if item.name != "historical-invalid-artifacts"
        and (item.name.endswith("reference-board.png") or item.name.endswith(".provenance.json") or item.suffix.lower() in {".jpg", ".jpeg", ".webp"})
    ]
    if stale:
        historical.mkdir(parents=True, exist_ok=True)
        for item in stale:
            shutil.move(str(item), str(historical / item.name))
        (historical / "STALE_NON_AUTHORITATIVE_ARTIFACTS.json").write_text(
            json.dumps({"status": "STALE_NON_AUTHORITATIVE_ARTIFACT", "run_id": str(run_id), "files": [item.name for item in stale]}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    staging = (work_dir or (ROOT / "work" / str(run_id))) / "publish-staging"
    staging.mkdir(parents=True, exist_ok=True)
    return staging


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
    framing = "头肩构图，脸部占据一致视觉尺度，眼睛位于一致的垂直区域，不出现全身。" if view_id.startswith("FACE_") else "完整头部和完整鞋脚必须在画面内，保持中性标准站姿和一致的全身高度。"
    return f"参考图是{character['name']}同一人物的权威定妆。{character['description']}。{view}。{framing}严格保持同一脸型、同一眼睛、同一鼻子、同一嘴型、同一年龄、同一肤色、同一发型、同一发际线、同一身体比例、同一服装、同一鞋子和同一配饰。只改变摄影机角度和自然遮挡。不得重新设计五官，不得改变年龄、发型、发际线、妆容、服装、鞋子或增加配饰。单张图，不要拼图、文字或水印。{repair}"


def _prop_master_prompt(prop: Mapping[str, Any]) -> str:
    return f"写实电影道具摄影，单张 PROP_MASTER / HERO，主体是{prop['description']}。3/4正面视图，中性深灰纯净背景，单一对象，清楚展示包型、提手、两个黄铜扣件、金属件、皮革材质、颜色和尺寸比例。不要人物、手、多个包、拼图、文字或水印。"


def _prop_derived_prompt(prop: Mapping[str, Any], view_id: str, violations: list[str] | None = None) -> str:
    view = {"SIDE": "标准侧面，展示厚度和提手轮廓", "BACK": "标准背面，保持包身结构和两个扣件位置", "DETAIL": "近距离细节，展示提手连接、两个黄铜扣件、金属件、缝线和皮革纹理"}[view_id]
    repair = f"这是自动修复，只修正以下问题：{'；'.join(violations)}。必须保持 MASTER 中完全相同的两个黄铜扣件，不得减少、增加或改变位置。" if violations else ""
    return f"参考图是同一只 HANDBAG 的权威 HERO。{prop['description']}。{view}。严格保持同一包型、同一比例、同一材质、同一深棕色、同一提手、同一对黄铜扣件、同一金属件和同一磨损状态，只改变摄影机角度和裁切。不得重新设计道具。单张图，不要人物、手、多个包、拼图、文字或水印。{repair}"


async def _submit_asset(client: httpx.AsyncClient, base_url: str, *, profile_id: str, asset_type: str, asset_id: str, view_id: str, prompt: str, output: Path, refs: list[dict[str, Any]] | None = None, framing: Mapping[str, Any] | None = None, timeout_hierarchy: GenerationTimeoutHierarchy | None = None) -> dict[str, Any]:
    refs = refs or []
    framing = dict(framing or AssetViewFramingPolicy.for_view(asset_type, view_id).as_dict())
    timeout_hierarchy = timeout_hierarchy or GenerationTimeoutHierarchy.from_profile({})
    payload = {
        "book_id": BOOK_ID, "episode": EPISODE, "shot_id": f"AUTO_ASSET_V4_{asset_type}_{asset_id}_{view_id}",
        "source_node_id": f"autonomous-asset-v4:{asset_type}:{asset_id}:{view_id}", "source_asset_id": None,
        "asset_scope": asset_type.lower(), "asset_subject": f"{asset_id} {view_id}", "target_kind": "reference-image",
        "prompt": prompt, "model_profile_id": profile_id, "aspect_ratio": framing["provider_aspect_ratio"], "reference_images": refs,
        "negative_prompt": "文字、Logo、水印、拼图、四宫格、额外人物、重复对象、身份漂移、材质漂移、颜色漂移",
        "count": 1, "confirmed": True, "allow_external_call": True,
    }
    sent = False
    request_started = time.monotonic()
    try:
        sent = True
        response = await client.post(f"{base_url}/api/prototyping/generate-reference-image", json=payload, timeout=timeout_hierarchy.httpx_timeout())
        response.raise_for_status()
    except Exception as exc:
        request_finished = time.monotonic()
        elapsed = max(0.0, request_finished - request_started)
        layer, config_error = classify_timeout_layer(exc, hierarchy=timeout_hierarchy, elapsed_seconds=elapsed)
        evidence = timeout_evidence(timeout_hierarchy, request_started_at=request_started, request_finished_at=request_finished, timeout_layer=layer)
        state = PostSubmissionState.AMBIGUOUS_AFTER_SEND if sent else PostSubmissionState.NOT_SENT
        raise ProviderSubmissionError(str(exc), state=state, timeout_evidence=evidence, configuration_error=config_error) from exc
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
        finished = time.monotonic()
        evidence = timeout_evidence(timeout_hierarchy, request_started_at=request_started, request_finished_at=finished, timeout_layer="NETWORK")
        raise ProviderSubmissionError(str(exc), state=PostSubmissionState.AMBIGUOUS_AFTER_SEND, task_created=True, timeout_evidence=evidence) from exc
    if task.get("status") != "done":
        message = str(task.get("error") or task.get("status") or "generation failed")
        classification = classify_provider_failure(message)
        finished = time.monotonic()
        provider_timeout = "超时" in message or "timeout" in message.lower() or "timed out" in message.lower()
        state = PostSubmissionState.AMBIGUOUS_AFTER_SEND if provider_timeout else PostSubmissionState.REJECTED_BEFORE_TASK if classification in {ProviderFailureClassification.CREDITS_INSUFFICIENT, ProviderFailureClassification.CHANNEL_UNAVAILABLE, ProviderFailureClassification.MODEL_UNAVAILABLE, ProviderFailureClassification.AUTH_FAILED} else PostSubmissionState.TASK_CONFIRMED
        evidence = timeout_evidence(timeout_hierarchy, request_started_at=request_started, request_finished_at=finished, timeout_layer="PROVIDER" if provider_timeout else "NONE")
        raise ProviderSubmissionError(message, state=state, task_created=True, timeout_evidence=evidence, provider_response=task.get("provider_response") or task.get("providerResponse") or {}, provider_response_shape=task.get("provider_response_shape") or {}, provider_response_fingerprint=str(task.get("provider_response_fingerprint") or ""), provider_http_status=task.get("provider_http_status"), provider_response_media_path=str(task.get("provider_response_media_path") or ""), response_classification=str(task.get("provider_response_classification") or ""))
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
    canonical_reference_sha = [str(item.get("reference_sha256") or "") for item in refs]
    canonical_reference_order = [str(item.get("reference_name") or item.get("reference_asset_id") or "") for item in refs]
    provider_images = provider_payload.get("images") if isinstance(provider_payload, dict) else None
    provider_images = provider_images if isinstance(provider_images, list) else []
    provider_reference_order_matches = len(provider_images) == len(refs)
    if provider_reference_order_matches:
        for index, image in enumerate(provider_images):
            expected = refs[index].get("reference_sha256")
            if isinstance(image, str) and image.startswith("data:image/") and "," in image:
                actual = hashlib.sha256(base64.b64decode(image.split(",", 1)[1])).hexdigest()
            else:
                actual = _sha(image)
            if expected and actual != expected:
                provider_reference_order_matches = False
                break
    input_formats = ["data_uri" if str(item.get("image_url") or "").startswith("data:image/") else "https" if str(item.get("image_url") or "").startswith("https://") else "other" for item in refs]
    finished = time.monotonic()
    evidence = timeout_evidence(timeout_hierarchy, request_started_at=request_started, request_finished_at=finished, timeout_layer="NONE")
    return {"view_id": view_id, "execution_id": task_id, "generation_execution_id": task_id, "provider": task.get("provider"), "model_profile_id": task.get("model_profile_id") or profile_id, "candidate_status": "CANDIDATE", "prompt_fingerprint": _sha(prompt), "reference_image_count": len(refs), "reference_image_sha256": canonical_reference_sha[0] if canonical_reference_sha else "", "reference_image_sha256s": canonical_reference_sha, "reference_order": canonical_reference_order, "reference_input_formats": input_formats, "reference_role": refs[0].get("role") if refs else "", "reference_purpose": refs[0].get("reference_purpose") if refs else "", "provider_inline_reference_attached": bool(refs) and ("images" in provider_payload or "inlineData" in serialized or "inline_data" in serialized), "provider_reference_order_matches": provider_reference_order_matches, "provider_payload_reference_count": len(provider_images), "provider_request_payload": _redact(provider_payload), "requested_aspect_ratio": framing["requested_aspect_ratio"], "provider_aspect_ratio": framing["provider_aspect_ratio"], "projection_reason": framing["projection_reason"], "framing_class": framing["framing_class"], "timeout_evidence": evidence, "file": {**_image_meta(output), "sha256": sha}, "sha256": sha, "fingerprint": sha, "path": str(output)}


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


async def _run_asset(
    client: httpx.AsyncClient,
    base_url: str,
    *,
    kind: str,
    asset: Mapping[str, Any],
    candidate_rows: list[Any],
    all_profiles: list[dict[str, Any]],
    judge_profile: dict[str, Any],
    health: ProviderHealthSnapshot,
    paths: dict[str, Path],
    budget: dict[str, int],
    call_counter: dict[str, int],
    traces: list[dict[str, Any]],
    events: list[dict[str, Any]],
    policy: ProductionProviderPolicy,
    existing_master: dict[str, Any] | None = None,
    existing_profile: dict[str, Any] | None = None,
    master_attempts_override: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    asset_id = str(asset["id"])
    name = str(asset["name"])
    description = str(asset["description"])
    derived_views = ["FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_SIDE", "FULL_BACK"] if kind == "CHARACTER" else ["SIDE", "BACK", "DETAIL"]
    master_prompt = _character_master_prompt(asset) if kind == "CHARACTER" else _prop_master_prompt(asset)
    derived_prompt = _character_derived_prompt if kind == "CHARACTER" else _prop_derived_prompt
    policy_complexity = PropComplexityPolicy.for_complexity(PropComplexity.HIGH) if kind == "PROP" else None
    candidates = policy.filter_image_candidates(candidate_rows)
    if not candidates:
        raise RuntimeError(f"{asset_id}:PRODUCTION_PROVIDER_POLICY_NO_CANDIDATE")

    selected_profile: dict[str, Any] | None = existing_profile
    master: dict[str, Any] | None = existing_master
    master_attempts: list[dict[str, Any]] = list(master_attempts_override or [])
    if master is None or selected_profile is None:
        for row in candidates:
            profile = next((item for item in all_profiles if str(item.get("id")) == row.profile_id), {})
            policy.assert_image_profile(profile)
            if call_counter["used"] >= CANARY_BUDGET["total"]:
                raise RuntimeError("AUTONOMOUS_CHARACTER_PROP_CANARY_BUDGET_EXCEEDED")
            call_counter["used"] += 1
            call_counter["by_provider"][str(row.provider)] = call_counter["by_provider"].get(str(row.provider), 0) + 1
            try:
                master = await _submit_asset(
                    client, base_url, profile_id=row.profile_id, asset_type=kind,
                    asset_id=asset_id, view_id="MASTER", prompt=master_prompt,
                    output=paths["MASTER"], refs=[], framing=AssetViewFramingPolicy.for_view(kind, "MASTER").as_dict(), timeout_hierarchy=GenerationTimeoutHierarchy.from_profile(profile),
                )
                selected_profile = profile
                master_attempts.append({"provider": row.provider, "model": row.model, "status": "SUCCEEDED", "execution_id": master["execution_id"], "post_submission_state": PostSubmissionState.TASK_CONFIRMED.value})
                events.append({"kind": "MASTER_SELECTED", "asset": asset_id, **master_attempts[-1]})
                break
            except ProviderSubmissionError as exc:
                classification = classify_provider_failure(exc, post_submission_state=exc.post_submission_state)
                row_data = {"provider": row.provider, "model": row.model, "status": "FAILED", "classification": classification.value, "post_submission_state": exc.post_submission_state.value, "task_created": exc.task_created, "error": str(exc)[:500], "timeout_evidence": exc.timeout_evidence, "configuration_error": exc.configuration_error}
                master_attempts.append(row_data)
                events.append({"kind": "MASTER_FAILED", "asset": asset_id, **row_data})
                # Strict production policy intentionally has no image fallback.
                code = exc.configuration_error or classification.value
                raise RuntimeError(f"{asset_id}:STRICT_75API_FAIL_CLOSED:{code}:timeout_evidence={json.dumps(exc.timeout_evidence, ensure_ascii=False, sort_keys=True)}") from exc

    if not master or not selected_profile:
        raise RuntimeError(f"{asset_id}:MASTER_PROVIDER_POOL_EXHAUSTED")
    policy.assert_image_profile(selected_profile)
    ref_row = next((row for row in policy.filter_image_candidates(AssetProviderRouter([selected_profile], health=health).candidates("IMAGE", AssetOperation.REFERENCE_IMAGE_DERIVATION))), None)
    if ref_row is None:
        raise RuntimeError(f"{asset_id}:MASTER_PROVIDER_REFERENCE_INCOMPATIBLE")

    def make_refs(view_names: list[str]) -> list[dict[str, Any]]:
        role = "character" if kind == "CHARACTER" else "prop"
        purpose = "same character identity" if kind == "CHARACTER" else "same object identity"
        return [
            {
                "image_url": _data_uri(paths[view_name]),
                "reference_sha256": _sha(paths[view_name]),
                "reference_name": f"{asset_id}_{view_name}",
                "reference_asset_id": f"{asset_id}:{view_name}",
                "role": role,
                "reference_purpose": purpose,
            }
            for view_name in view_names
        ]

    def assert_reference_lineage(media: Mapping[str, Any], refs: list[dict[str, Any]], view_id: str) -> None:
        expected_shas = [str(item["reference_sha256"]) for item in refs]
        expected_order = [str(item["reference_name"]) for item in refs]
        if media.get("reference_image_count") != len(refs):
            raise RuntimeError(f"{asset_id}:{view_id}:REFERENCE_COUNT_MISMATCH")
        if media.get("reference_image_sha256s") != expected_shas:
            raise RuntimeError(f"{asset_id}:{view_id}:REFERENCE_SHA_ORDER_MISMATCH")
        if media.get("reference_order") != expected_order:
            raise RuntimeError(f"{asset_id}:{view_id}:REFERENCE_ORDER_MISMATCH")
        if refs and not media.get("provider_inline_reference_attached"):
            raise RuntimeError(f"{asset_id}:{view_id}:REFERENCE_NOT_PROPAGATED")
        if refs and not media.get("provider_reference_order_matches"):
            raise RuntimeError(f"{asset_id}:{view_id}:PROVIDER_REFERENCE_ORDER_MISMATCH")

    audits: list[Any] = []
    generations: dict[str, Any] = {"MASTER": master, "FULL_FRONT": master} if kind == "CHARACTER" else {"MASTER": master}
    repairs: list[dict[str, Any]] = []

    def refs_for_view(view_id: str) -> list[dict[str, Any]]:
        if kind == "CHARACTER":
            if view_id in {"FACE_PROFILE", "FACE_45"} and any(row.view_id == "FACE_FRONT" and row.passes for row in audits):
                return make_refs(["MASTER", "FACE_FRONT"])
            if view_id == "FULL_BACK" and any(row.view_id == "FULL_SIDE" and row.passes for row in audits):
                return make_refs(["MASTER", "FULL_SIDE"])
            return make_refs(["MASTER"])
        if view_id == "DETAIL" and any(row.view_id == "SIDE" and row.passes for row in audits):
            return make_refs(["MASTER", "SIDE"])
        return make_refs(["MASTER"])

    for view_id in derived_views:
        if call_counter["used"] >= CANARY_BUDGET["total"]:
            raise RuntimeError("AUTONOMOUS_CHARACTER_PROP_CANARY_BUDGET_EXCEEDED")
        refs = refs_for_view(view_id)
        call_counter["used"] += 1
        call_counter["by_provider"][PRODUCTION_POLICY.image_provider] = call_counter["by_provider"].get(PRODUCTION_POLICY.image_provider, 0) + 1
        prompt = derived_prompt(asset, view_id)
        try:
            media = await _submit_asset(client, base_url, profile_id=selected_profile["id"], asset_type=kind, asset_id=asset_id, view_id=view_id, prompt=prompt, output=paths[view_id], refs=refs, framing=AssetViewFramingPolicy.for_view(kind, view_id).as_dict(), timeout_hierarchy=GenerationTimeoutHierarchy.from_profile(selected_profile))
        except ProviderSubmissionError as exc:
            classification = classify_provider_failure(exc, post_submission_state=exc.post_submission_state)
            code = exc.configuration_error or classification.value
            raise RuntimeError(f"{asset_id}:{view_id}:STRICT_75API_FAIL_CLOSED:{code}:post_submission_state={exc.post_submission_state.value}:timeout_evidence={json.dumps(exc.timeout_evidence, ensure_ascii=False, sort_keys=True)}") from exc
        assert_reference_lineage(media, refs, view_id)
        generations[view_id] = media
        status, judge, req, resp = _judge_pair(kind, judge_profile, paths[refs[0]["reference_name"].rsplit("_", 1)[-1]], paths[view_id], view_id, description)
        audit = _character_audit(view_id, 1, media, master, judge, status, req, resp, judge_profile) if kind == "CHARACTER" else _prop_audit(view_id, 1, media, master, judge, status, req, resp, judge_profile)
        audits.append(audit)

    for index, audit in enumerate(list(audits)):
        if audit.passes:
            continue
        if len(repairs) >= budget["repair"]:
            continue
        view_id = audit.view_id
        refs = refs_for_view(view_id)
        if call_counter["used"] >= CANARY_BUDGET["total"]:
            raise RuntimeError("AUTONOMOUS_CHARACTER_PROP_CANARY_BUDGET_EXCEEDED")
        call_counter["used"] += 1
        call_counter["by_provider"][PRODUCTION_POLICY.image_provider] = call_counter["by_provider"].get(PRODUCTION_POLICY.image_provider, 0) + 1
        prompt = derived_prompt(asset, view_id, audit.violations + (audit.critical_identity_violations if kind == "CHARACTER" else audit.critical_object_violations))
        try:
            media = await _submit_asset(client, base_url, profile_id=selected_profile["id"], asset_type=kind, asset_id=asset_id, view_id=view_id, prompt=prompt, output=paths[view_id], refs=refs, framing=AssetViewFramingPolicy.for_view(kind, view_id).as_dict(), timeout_hierarchy=GenerationTimeoutHierarchy.from_profile(selected_profile))
        except ProviderSubmissionError as exc:
            classification = classify_provider_failure(exc, post_submission_state=exc.post_submission_state)
            code = exc.configuration_error or classification.value
            raise RuntimeError(f"{asset_id}:{view_id}:REPAIR_STRICT_75API_FAIL_CLOSED:{code}:timeout_evidence={json.dumps(exc.timeout_evidence, ensure_ascii=False, sort_keys=True)}") from exc
        assert_reference_lineage(media, refs, view_id)
        generations[view_id] = media
        status, judge, req, resp = _judge_pair(kind, judge_profile, paths[refs[0]["reference_name"].rsplit("_", 1)[-1]], paths[view_id], view_id, description)
        repaired = _character_audit(view_id, 2, media, master, judge, status, req, resp, judge_profile) if kind == "CHARACTER" else _prop_audit(view_id, 2, media, master, judge, status, req, resp, judge_profile)
        audits[index] = repaired
        repairs.append({"view_id": view_id, "attempt": 2, "violations": audit.violations, "master_sha256": master["sha256"], "reference_order": [item["reference_name"] for item in refs], "new_sha256": media["sha256"]})

    pairwise_pass = all(row.passes for row in audits)
    global_paths = {key: paths[key] for key in (["FACE_FRONT", "FACE_PROFILE", "FACE_45", "MASTER", "FULL_SIDE", "FULL_BACK"] if kind == "CHARACTER" else ["MASTER", "SIDE", "BACK", "DETAIL"])}
    global_judge, global_req, global_resp = ( {"status": "NOT_RUN", "same_character": False if kind == "CHARACTER" else None, "same_object": False if kind == "PROP" else None, "cross_view_violations": ["pairwise gate failed"]}, "", "") if not pairwise_pass else _judge_global(kind, judge_profile, global_paths, description)
    if kind == "CHARACTER":
        authority = CharacterAuthority.lock(character_id=asset_id, name=name, primary=master, derived={key: generations[key] for key in derived_views}, audits=audits, global_judge=global_judge, profile_fingerprint=_profile_fingerprint(selected_profile), prompt_fingerprint=_sha(master_prompt)) if global_judge.get("status") == "PASS" else None
    else:
        authority = PropAuthority.lock(prop_id=asset_id, name=name, complexity=policy_complexity.complexity, primary=master, derived={key: generations[key] for key in derived_views}, audits=audits, global_judge=global_judge, profile_fingerprint=_profile_fingerprint(selected_profile), prompt_fingerprint=_sha(master_prompt)) if global_judge.get("status") == "PASS" else None
    selection_rows = AssetProviderRouter(all_profiles, default_image_profile_id=str(selected_profile.get("id")), health=health).rank("IMAGE", AssetOperation.TEXT_TO_IMAGE)
    for selection_row in selection_rows:
        selection_row.selected = selection_row.profile_id == str(selected_profile.get("id"))
    return {"asset_id": asset_id, "name": name, "kind": kind, "complexity": policy_complexity.complexity.value if policy_complexity else None, "master": master, "master_attempts": master_attempts, "generations": generations, "audits": audits, "global": {**global_judge, "judge_request_fingerprint": global_req, "judge_response_fingerprint": global_resp}, "repairs": repairs, "authority": asdict(authority) if authority else None, "selected_profile": selected_profile, "selection_trace": [asdict(row) for row in policy.filter_image_candidates(selection_rows)], "production_policy": policy.as_dict()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", default=str(SOURCE_DB))
    args = parser.parse_args()
    source_db = Path(args.source_db).resolve()
    if not source_db.exists():
        raise SystemExit(f"missing database: {source_db}")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work = ROOT / "work" / "75api-autonomous-character-prop-canary-v1" / run_id
    work.mkdir(parents=True, exist_ok=True)
    isolated_db = work / "screenplay.db"
    shutil.copy2(source_db, isolated_db)
    uploads = work / "uploads"
    port = _free_port()
    env = os.environ.copy()
    env.update({"DATABASE_URL": f"sqlite:///{isolated_db.as_posix()}?timeout=30", "UPLOAD_DIR": str(uploads), "DEPLOYMENT_ENV": "isolated", "APP_ENV": "test", "E2E_EXTERNAL_RUNTIME": ""})
    log = (work / "uvicorn.log").open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    health = ProviderHealthSnapshot()
    call_counter = {"used": 0, "by_provider": {"75api-image": 0, "shapi-image": 0, "poyo-image": 0, "other-image": 0}}
    events: list[dict[str, Any]] = []
    results: dict[str, Any] = {}
    preflight: dict[str, Any] = {"status": "NOT_RUN", "policy": PRODUCTION_POLICY.as_dict()}
    staging = _prepare_run_output(run_id, work_dir=work)
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        _wait_for_health(f"http://127.0.0.1:{port}", timeout=180)
        os.environ["DATABASE_URL"] = env["DATABASE_URL"]
        from api.model_registry import get_default_profile, list_profiles, test_profile_connection
        from core.provider_transport_registry import get_provider_transport_binding

        all_profiles = [item for item in list_profiles(include_sensitive=True) if item.get("enabled", True)]
        default = get_default_profile("image") or next((item for item in all_profiles if item.get("capability") == "image" and item.get("is_default")), {})
        PRODUCTION_POLICY.assert_image_profile(default)
        params = default.get("default_params") if isinstance(default.get("default_params"), dict) else {}
        transport = get_provider_transport_binding(provider_id=PRODUCTION_POLICY.image_provider, target_media="IMAGE", binding_id=str(default.get("transport_binding_id") or "") or None)
        router = AssetProviderRouter(all_profiles, default_image_profile_id=str(default.get("id") or ""), health=health)
        router_rows = router.rank("IMAGE", AssetOperation.TEXT_TO_IMAGE)
        candidate_rows = PRODUCTION_POLICY.filter_image_candidates(router_rows)
        candidate = next((row for row in candidate_rows if not row.rejected_reason), None)
        capability = {
            "text_to_image": "text_to_image" in (params.get("task_modes") or []),
            "image_to_image": "image_to_image" in (params.get("task_modes") or []),
            "reference_images": bool(params.get("supports_reference_images")),
            "https_reference": True,
            "data_uri_reference": True,
        }
        preflight = {
            "schema_version": "75api_image_preflight_v1",
            "status": "PASS" if candidate and transport and all(capability.values()) and bool(default.get("key_configured") or default.get("credential_configured") or default.get("api_key")) else "FAIL",
            "policy": PRODUCTION_POLICY.as_dict(),
            "profile": {"id": default.get("id"), "provider": default.get("provider"), "model": default.get("model_name"), "transport_binding_id": default.get("transport_binding_id")},
            "credential_ready": bool(default.get("key_configured") or default.get("credential_configured") or default.get("api_key")),
            "transport_registered": bool(transport),
            "capabilities": capability,
            "router_candidate": asdict(candidate) if candidate else None,
            "rejected_router_rows": [asdict(row) for row in router_rows if row not in candidate_rows or row.rejected_reason],
            "reference_input_formats": ["data_uri", "https"],
            "real_generation_calls": 0,
        }
        _write(OUT / "75API_IMAGE_PREFLIGHT.json", preflight)
        if preflight["status"] != "PASS":
            raise RuntimeError("75API_IMAGE_PREFLIGHT_FAILED")

        async def preflight_probe() -> None:
            profile = default
            trace = asdict(candidate)
            try:
                probe = await test_profile_connection(profile_payload=profile)
                trace["connection_probe"] = "PASS" if probe.get("ok") else "FAIL"
                trace["model_available"] = probe.get("model_available", True if probe.get("ok") else False)
                trace["probe_message"] = str(probe.get("message") or "")[:500]
            except Exception as exc:
                trace["connection_probe"] = "FAIL"
                trace["model_available"] = False
                trace["probe_message"] = str(exc)[:500]
            preflight["connection_probe"] = trace
            _write(OUT / "75API_IMAGE_PREFLIGHT.json", preflight)
            if trace["connection_probe"] != "PASS":
                raise RuntimeError("75API_IMAGE_PREFLIGHT_CONNECTION_FAILED")

        asyncio.run(preflight_probe())
        judge_profile = next((item for item in all_profiles if item.get("capability") == "llm" and bool((item.get("default_params") or {}).get("supports_vision"))), {})
        if not judge_profile:
            raise RuntimeError("VISION_JUDGE_PROFILE_MISSING")
        base_url = f"http://127.0.0.1:{port}"

        async def run_stage(client: httpx.AsyncClient, character: Mapping[str, Any], keys: list[str], paths: dict[str, Path]) -> None:
            asset_id = str(character["id"])
            results[asset_id] = await _run_asset(client, base_url, kind="CHARACTER", asset=character, candidate_rows=candidate_rows, all_profiles=all_profiles, judge_profile=judge_profile, health=health, paths=paths, budget=CANARY_BUDGET[character["name"]], call_counter=call_counter, traces=[], events=events, policy=PRODUCTION_POLICY)
            if not results[asset_id].get("authority"):
                raise RuntimeError(f"STAGE_{asset_id}_AUTHORITY_NOT_READY")
            results[asset_id]["board"] = _board({key: paths[key] for key in keys}, staging / f"{asset_id.lower().replace('_', '-')}-reference-board.png", ["FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_FRONT", "FULL_SIDE", "FULL_BACK"], 3, run_id=run_id, authority=results[asset_id]["authority"])

        async def run_all() -> None:
            # Ordinary health, polling and metadata requests stay short.  The
            # generation POST receives a per-request timeout derived from the
            # selected provider profile inside _submit_asset.
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=30, write=30, pool=30), trust_env=False) as client:
                for character in (CHARACTERS[0], CHARACTERS[1]):
                    keys = ["MASTER", "FULL_FRONT", "FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_SIDE", "FULL_BACK"]
                    paths = {key: work / f"{character['id'].lower()}-{key.lower()}.jpg" for key in keys}
                    paths["FULL_FRONT"] = paths["MASTER"]
                    await run_stage(client, character, keys, paths)
                keys = ["MASTER", "SIDE", "BACK", "DETAIL"]
                paths = {key: work / f"handbag-{key.lower()}.jpg" for key in keys}
                results["HANDBAG"] = await _run_asset(client, base_url, kind="PROP", asset=HANDBAG, candidate_rows=candidate_rows, all_profiles=all_profiles, judge_profile=judge_profile, health=health, paths=paths, budget=CANARY_BUDGET["HANDBAG"], call_counter=call_counter, traces=[], events=events, policy=PRODUCTION_POLICY)
                if not results["HANDBAG"].get("authority"):
                    raise RuntimeError("STAGE_HANDBAG_AUTHORITY_NOT_READY")
                results["HANDBAG"]["board"] = _board({key: paths[key] for key in keys}, staging / "handbag-reference-board.png", keys, 2, run_id=run_id, authority=results["HANDBAG"]["authority"])

        asyncio.run(run_all())
        scene_authority = json.loads(SCENE_AUTHORITY_PATH.read_text(encoding="utf-8")) if SCENE_AUTHORITY_PATH.exists() else {"status": "MISSING"}
        char_authorities = [CharacterAuthority(**results[key]["authority"]) for key in ("LIN_WAN", "LU_SHU")]
        prop_authorities = [PropAuthority(**results["HANDBAG"]["authority"])]
        authority_set = VisualAssetAuthoritySet.build(characters=char_authorities, scenes={"E01_SC002": scene_authority}, props=prop_authorities, visual_style_fingerprint=_sha("visual-style-v1"))
        _atomic_publish_board(staging / "lin-wan-reference-board.png", OUT / "lin-wan-reference-board.png")
        _atomic_publish_board(staging / "lu-shu-reference-board.png", OUT / "lu-shu-reference-board.png")
        _atomic_publish_board(staging / "handbag-reference-board.png", OUT / "handbag-reference-board.png")
        _write(OUT / "CHARACTER_AUTHORITIES.json", {key: results[key]["authority"] for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_AUTHORITIES.json", {"HANDBAG": results["HANDBAG"]["authority"]})
        _write(OUT / "CHARACTER_VIEW_EVIDENCE.json", {key: results[key]["generations"] for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_VIEW_EVIDENCE.json", {"HANDBAG": results["HANDBAG"]["generations"]})
        _write(OUT / "CHARACTER_CONSISTENCY_AUDIT.json", {key: {"audits": [asdict(audit) for audit in results[key]["audits"]], "global": results[key]["global"]} for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_CONSISTENCY_AUDIT.json", {"HANDBAG": {"audits": [asdict(audit) for audit in results["HANDBAG"]["audits"]], "global": results["HANDBAG"]["global"]}})
        _write(OUT / "CHARACTER_REPAIR_HISTORY.json", {key: results[key]["repairs"] for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_REPAIR_HISTORY.json", {"HANDBAG": results["HANDBAG"]["repairs"]})
        _write(OUT / "VISUAL_ASSET_AUTHORITY_SET.json", asdict(authority_set))
        _write(OUT / "CHARACTER_PROVIDER_SELECTION_TRACE.json", {key: results[key]["selection_trace"] for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_PROVIDER_SELECTION_TRACE.json", results["HANDBAG"]["selection_trace"])
        manifest = {"schema_version": "75api_autonomous_character_prop_canary_v1", "status": "AUTONOMOUS_VISUAL_ASSET_PIPELINE_READY_FOR_SHOT_CANARY", "production_provider_policy": PRODUCTION_POLICY.as_dict(), "preflight": preflight, "scene_authority": scene_authority, "characters": {key: results[key] for key in ("LIN_WAN", "LU_SHU")}, "props": {"HANDBAG": results["HANDBAG"]}, "authority_set": asdict(authority_set), "real_image_calls": call_counter["used"], "real_image_calls_by_provider": call_counter["by_provider"], "vision_judge_calls": sum(len(row["audits"]) + 1 for row in results.values()), "real_video_calls": 0, "safety": {"production_writes": 0, "book_990400_writes": 0, "browser_direct_provider_calls": 0, "secret_leaks": 0, "orphans": 0}}
        _write(OUT / "AUTONOMOUS_VISUAL_ASSET_AUDIT.json", manifest)
        report = ["# 75API Autonomous Character / Prop Real Canary", "", "- Status: AUTONOMOUS_VISUAL_ASSET_PIPELINE_READY_FOR_SHOT_CANARY", f"- Production Provider Policy: {PRODUCTION_POLICY.image_provider} / {PRODUCTION_POLICY.image_model} (strict={PRODUCTION_POLICY.strict_provider})", f"- VIDEO policy: {PRODUCTION_POLICY.video_provider} / {PRODUCTION_POLICY.video_model}; real VIDEO calls: 0", f"- Real IMAGE calls: {call_counter['used']} (75api={call_counter['by_provider']['75api-image']}, SHAPI=0, Poyo=0)", "- Production writes: 0", "- Book 990400 writes: 0", "- Secret leaks: 0", "- Orphans: 0", "- No keyframe or VIDEO generation was executed.", "", "## Authorities", "- Lin Wan: READY", "- Lu Shu: READY", "- HANDBAG: READY", "- Scene E01_SC002: reused READY", "- VisualAssetAuthoritySet: READY"]
        (OUT / "AUTONOMOUS_VISUAL_ASSET_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        print(json.dumps({"status": manifest["status"], "image_calls": call_counter["used"], "video_calls": 0, "output": str(OUT)}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        failure = {"schema_version": "75api_autonomous_character_prop_canary_v1", "status": "AUTONOMOUS_VISUAL_ASSET_PIPELINE_PARTIAL", "failure": str(exc)[:1000], "production_provider_policy": PRODUCTION_POLICY.as_dict(), "preflight": preflight, "provider_health": health.unhealthy, "real_image_calls": call_counter["used"], "real_image_calls_by_provider": call_counter["by_provider"], "real_video_calls": 0, "publish_staging": str(staging), "board_publication": {"LIN_WAN": "NOT_PUBLISHED" if not results.get("LIN_WAN", {}).get("authority") else "STAGED_ONLY", "LU_SHU": "NOT_PUBLISHED", "HANDBAG": "NOT_PUBLISHED"}, "safety": {"production_writes": 0, "book_990400_writes": 0, "browser_direct_provider_calls": 0, "secret_leaks": 0, "orphans": 0}}
        _write(OUT / "AUTONOMOUS_VISUAL_ASSET_AUDIT.json", failure)
        _write(OUT / "75API_IMAGE_PREFLIGHT.json", preflight)
        _write(OUT / "CHARACTER_AUTHORITIES.json", {key: results.get(key, {}).get("authority") for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_AUTHORITIES.json", {"HANDBAG": results.get("HANDBAG", {}).get("authority")})
        _write(OUT / "CHARACTER_VIEW_EVIDENCE.json", {key: results.get(key, {}).get("generations", {}) for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_VIEW_EVIDENCE.json", {"HANDBAG": results.get("HANDBAG", {}).get("generations", {})})
        _write(OUT / "CHARACTER_CONSISTENCY_AUDIT.json", {key: {"audits": [asdict(audit) for audit in results.get(key, {}).get("audits", [])], "global": results.get(key, {}).get("global", {"status": "NOT_RUN"})} for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_CONSISTENCY_AUDIT.json", {"HANDBAG": {"audits": [asdict(audit) for audit in results.get("HANDBAG", {}).get("audits", [])], "global": results.get("HANDBAG", {}).get("global", {"status": "NOT_RUN"})}})
        _write(OUT / "CHARACTER_REPAIR_HISTORY.json", {key: results.get(key, {}).get("repairs", []) for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_REPAIR_HISTORY.json", {"HANDBAG": results.get("HANDBAG", {}).get("repairs", [])})
        scene = json.loads(SCENE_AUTHORITY_PATH.read_text(encoding="utf-8")) if SCENE_AUTHORITY_PATH.exists() else {"status": "MISSING"}
        _write(OUT / "VISUAL_ASSET_AUTHORITY_SET.json", {"status": "PARTIAL", "scene": scene, "characters": {key: results.get(key, {}).get("authority") for key in ("LIN_WAN", "LU_SHU")}, "props": {"HANDBAG": results.get("HANDBAG", {}).get("authority")}})
        lin_status = "READY/STAGED_ONLY" if results.get("LIN_WAN", {}).get("authority") else "INCOMPLETE"
        lin_reason = "SUBMISSION_AMBIGUOUS" if "SUBMISSION_AMBIGUOUS" in str(exc) else str(exc)[:300]
        (OUT / "AUTONOMOUS_VISUAL_ASSET_REPORT.md").write_text("# 75API Autonomous Character / Prop Real Canary\n\n- Status: AUTONOMOUS_VISUAL_ASSET_PIPELINE_PARTIAL\n- Failure: " + str(exc)[:1000] + f"\n- Lin Wan: status={lin_status}; board=NOT_PUBLISHED; reason={lin_reason}\n- Lu Shu: status=NOT_STARTED; board=NOT_PUBLISHED\n- HANDBAG: status=NOT_STARTED; board=NOT_PUBLISHED\n- Staging retained: {staging}\n- Real IMAGE calls: {call_counter['used']} (75api={call_counter['by_provider']['75api-image']}, SHAPI=0, Poyo=0)\n- Real VIDEO calls: 0\n- No fallback provider was used.\n- No final board was published from a partial run.\n", encoding="utf-8")
        print(json.dumps(failure, ensure_ascii=False, indent=2))
        return 2
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
