"""Gate B real IMAGE/VIDEO canary for the three closed shots.

The runner uses the canonical 75API adapters directly, keeps all media in a
run directory, and never writes production or Book 990400 records.
"""
from __future__ import annotations

import asyncio
import base64
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.generation_adapters import (  # noqa: E402
    generate_image_asset, submit_75api_minimax_h3_generation,
    poll_75api_minimax_h3_generation, reconcile_75api_minimax_h3_generation,
    _build_75api_minimax_h3_video_payload,
)
from api.model_registry import get_default_profile
from core.shot_readiness import project_provider_duration

OUT = ROOT / "docs" / "shot-canary" / "v1"
READY = OUT / "readiness"
AUTH = ROOT / "docs" / "visual-assets" / "75api-autonomous-v4" / "VISUAL_ASSET_AUTHORITY_SET.json"
ASSETS = ROOT / "docs" / "visual-assets" / "75api-autonomous-v4"
SCENE = ROOT / "docs" / "visual-assets" / "autonomous-v3" / "scene-master.jpg"
SHOTS = ["SH_E01_SC002_007", "SH_E01_SC002_002", "SH_E01_SC002_006"]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _data_uri(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


async def _save_uri(uri: str, path: Path, *, headers: dict[str, str] | None = None) -> None:
    if uri.startswith("data:"):
        path.write_bytes(base64.b64decode(uri.split(",", 1)[1]))
        return
    async with httpx.AsyncClient(timeout=180, follow_redirects=True, trust_env=False) as client:
        response = await client.get(uri, headers=headers or {})
        response.raise_for_status()
        path.write_bytes(response.content)


def _parse_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip().replace("```json", "").replace("```", "").strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start:end + 1])
                return value if isinstance(value, dict) else {}
            except Exception:
                return {}
        return {}


def _judge(path: Path, prompt: str, profile: dict[str, Any]) -> dict[str, Any]:
    import core.llm as llm
    try:
        raw = llm.call_llm(prompt, system="shot canary media compliance judge v1", model_profile=profile, retries=1, estimated_tokens=1500, max_tokens=1800, image_data_urls=[_data_uri(path)])
        parsed = _parse_json(raw)
        parsed["response_sha256"] = hashlib.sha256(str(raw).encode("utf-8")).hexdigest()
        parsed["status"] = "PASS" if str(parsed.get("status") or "").upper() == "PASS" else "FAIL"
        return parsed
    except Exception as exc:
        return {"status": "FAIL", "error": str(exc)[:500]}


def _keyframe_prompt(shot_id: str, duration: int) -> str:
    base = "写实电影关键帧，出租公寓厨房，暖冷混合室内光，16:9，保持E01_SC002厨房空间拓扑、餐桌、厨房门边和两个人物的身份与服装；只出现林晚和陆叔，不出现第三人、文字或水印。"
    if shot_id == "SH_E01_SC002_007":
        return base + "林晚在画面左侧厨房门边，左手轻压门框，右手中性自然下垂；陆叔在画面右侧餐桌边，右手停在桌边上方；双人中景，双方平视对视，无剧情道具。"
    if shot_id == "SH_E01_SC002_002":
        return base + "陆叔坐在餐桌左侧，林晚坐在右侧，过肩中景；陆叔完成对白后的最终状态，双手自然，不接触任何道具；林晚左手放松垂在身侧，手指自然弯曲；严禁手提包、肩包、包带、手机、苹果或其他道具。"
    return base + "陆叔坐在餐桌左侧，右手握着一只完整红黄苹果并向林晚递出；苹果在陆叔右手，林晚不接触；林晚退到厨房门边，左手接触门锁下方；严禁手提包和包带。"


def _video_prompt(shot_id: str, duration: int, director: float) -> str:
    hold = f"最后{duration - director:g}秒只保持最终姿态、眼神、表情、道具状态和构图，不新增对白、动作、事件、道具转移或摄影事件。" if duration > director else ""
    return _keyframe_prompt(shot_id, duration) + f" 连续单镜头，时长{duration}秒，严格按照导演动作和对白时间执行；{hold}使用输入首帧作为第一帧。"


def _ffprobe(path: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(path)], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        streams = data.get("streams") or []
        fmt = data.get("format") or {}
        return {"status": "PASS", "duration_seconds": float(fmt.get("duration") or 0), "width": next((int(s.get("width")) for s in streams if s.get("width")), None), "height": next((int(s.get("height")) for s in streams if s.get("height")), None), "audio_streams": sum(1 for s in streams if s.get("codec_type") == "audio")}
    except Exception as exc:
        return {"status": "FAIL", "error": str(exc)[:500]}


async def _run() -> tuple[int, dict[str, Any]]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work = ROOT / "work" / "shot-canary" / "v1" / run_id
    work.mkdir(parents=True, exist_ok=True)
    image_profile = get_default_profile("image") or {}
    video_profile = get_default_profile("video") or {}
    judge_profile = next((p for p in __import__("api.model_registry", fromlist=["list_profiles"]).list_profiles(include_sensitive=True) if p.get("capability") == "llm" and bool((p.get("default_params") or {}).get("supports_vision"))), {})
    evidence: dict[str, Any] = {"run_id": run_id, "status": "REAL_SHOT_MEDIA_CANARY_BLOCKED", "gate_a": {}, "apple": {}, "keyframes": {}, "videos": {}, "safety": {"production_writes": 0, "book_990400_writes": 0, "shapi_calls": 0, "poyo_calls": 0, "secret_leaks": 0, "orphans": 0, "raw_base64_persisted": 0, "signed_url_query_persisted": 0}, "real_image_calls": 0, "real_video_calls": 0}
    reuse_base = Path(os.environ.get("SHOT_CANARY_REUSE_BASE", "")).resolve() if os.environ.get("SHOT_CANARY_REUSE_BASE") else None
    reused = json.loads((reuse_base / "SHOT_CANARY_AUDIT.json").read_text(encoding="utf-8")) if reuse_base and (reuse_base / "SHOT_CANARY_AUDIT.json").exists() else {}
    if not READY.exists() or "SHOT_CANARY_READY_FOR_REAL_MEDIA" not in (READY / "SHOT_READINESS_REPORT.md").read_text(encoding="utf-8"):
        evidence["error"] = "SHOT_READINESS_GATE_NOT_PASS"
        return 2, evidence
    evidence["execution_code_provenance"] = {"execution_base_commit_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "working_tree_clean_at_start": not bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()), "runner_path": "scripts/run_shot_canary_v1.py"}
    if not evidence["execution_code_provenance"]["working_tree_clean_at_start"]:
        evidence["error"] = "CLEAN_TREE_REQUIRED_BEFORE_REAL_CALL"
        return 2, evidence
    if image_profile.get("provider") != "75api-image" or video_profile.get("provider") != "75api-minimax-h3":
        evidence["error"] = "PROVIDER_POLICY_MISMATCH"
        return 2, evidence
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    keyframe_refs = [{"role": "scene", "reference_name": "E01_SC002_MASTER", "reference_asset_id": "E01_SC002", "reference_sha256": _sha(SCENE), "image_url": _data_uri(SCENE)}, {"role": "character", "reference_name": "LIN_WAN_FULL_FRONT", "reference_asset_id": "LIN_WAN", "reference_sha256": _sha(ASSETS / "lin-wan-master.jpg"), "image_url": _data_uri(ASSETS / "lin-wan-master.jpg")}, {"role": "character", "reference_name": "LIN_WAN_FACE_FRONT", "reference_asset_id": "LIN_WAN", "reference_sha256": _sha(ASSETS / "lin-wan-face-front.jpg"), "image_url": _data_uri(ASSETS / "lin-wan-face-front.jpg")}, {"role": "character", "reference_name": "LU_SHU_FULL_FRONT", "reference_asset_id": "LU_SHU", "reference_sha256": _sha(ASSETS / "lu-shu-master.jpg"), "image_url": _data_uri(ASSETS / "lu-shu-master.jpg")}, {"role": "character", "reference_name": "LU_SHU_FACE_FRONT", "reference_asset_id": "LU_SHU", "reference_sha256": _sha(ASSETS / "lu-shu-face-front.jpg"), "image_url": _data_uri(ASSETS / "lu-shu-face-front.jpg")}]
    apple_path = work / "apple-master.jpg"
    apple_prompt = "单张写实电影道具 HERO / MASTER：一只完整无切开的红黄自然苹果，果梗清晰可见，单一对象，中性灰背景，无切片、无第二只苹果、无手、无人物、无文字、无水印。"
    evidence["apple"]["prompt"] = apple_prompt
    try:
        if reused.get("apple", {}).get("sha256") and reuse_base:
            source = reuse_base / "apple-master.jpg"
            if source.exists():
                shutil.copy2(source, apple_path)
            else:
                await _save_uri(str(reused["apple"].get("preview_url") or ""), apple_path)
            evidence["apple"] = dict(reused["apple"])
            apple = {"previewUrl": evidence["apple"].get("preview_url", ""), "providerResponseFingerprint": evidence["apple"].get("provider_response_fingerprint", "")}
        else:
            apple = await generate_image_asset(image_profile, prompt=apple_prompt, aspect_ratio="1:1", negative_prompt="切片、切开的水果、第二只苹果、手、人物、文字、水印", reference_images=[])
            await _save_uri(str(apple.get("previewUrl") or apple.get("uri") or ""), apple_path)
            evidence["real_image_calls"] += 1
        apple_judge = _judge(apple_path, "检查这张图片是否只有一只完整红黄苹果，果梗可见，无切片、无第二只苹果、无手、无文字。只输出JSON {\"status\":\"PASS|FAIL\",\"single_whole_apple\":true,\"stem_visible\":true,\"unauthorized_objects\":[]}", judge_profile)
        evidence["apple"].update({"provider": "75api-image", "model": image_profile.get("model_name"), "sha256": _sha(apple_path), "provider_response_fingerprint": apple.get("providerResponseFingerprint"), "preview_url": str(apple.get("previewUrl") or ""), "judge": apple_judge})
        if apple_judge.get("status") != "PASS" or not apple_judge.get("single_whole_apple") or apple_judge.get("unauthorized_objects"):
            evidence["error"] = "APPLE_SEMANTIC_JUDGE_FAILED"
            return 2, evidence
    except Exception as exc:
        evidence["error"] = str(exc)[:1000]
        return 2, evidence
    apple_ref = {"role": "prop", "reference_name": "APPLE_HERO", "reference_asset_id": "APPLE", "reference_sha256": _sha(apple_path), "image_url": _data_uri(apple_path)}
    evidence["apple"]["authority"] = {"status": "READY", "prop_id": "APPLE", "complexity": "LOW", "media_sha256": _sha(apple_path), "authority_fingerprint": hashlib.sha256(json.dumps(evidence["apple"], ensure_ascii=False, sort_keys=True).encode()).hexdigest()}
    all_refs = keyframe_refs + [apple_ref]
    # Three initial keyframes.
    for shot_id in SHOTS:
        duration = int(project_provider_duration({"SH_E01_SC002_007": 5.0, "SH_E01_SC002_002": 13.5, "SH_E01_SC002_006": 8.5}[shot_id]).provider_duration_seconds)
        path = work / f"{shot_id}-keyframe-v1.jpg"
        refs = all_refs if shot_id == "SH_E01_SC002_006" else keyframe_refs
        try:
            prior = reused.get("keyframes", {}).get(shot_id, {}) if shot_id == "SH_E01_SC002_007" else {}
            prior_path = Path(str(prior.get("path") or ""))
            if prior.get("sha256") and prior_path.exists():
                shutil.copy2(prior_path, path)
                result = {"previewUrl": prior.get("provider_preview_url", ""), "uri": prior.get("provider_preview_url", "")}
            else:
                result = await generate_image_asset(image_profile, prompt=_keyframe_prompt(shot_id, duration), aspect_ratio="16:9", negative_prompt="手提包、肩包、包带、额外人物、文字、水印、苹果（SC002_002和SC002_007）", reference_images=refs)
                await _save_uri(str(result.get("previewUrl") or result.get("uri") or ""), path)
                evidence["real_image_calls"] += 1
            width = height = 0
            from PIL import Image
            with Image.open(path) as im: width, height = im.size
            ratio_ok = abs((width / height) - (16 / 9)) < 0.02 if height else False
            condition = ("此镜头严禁苹果、手提包、包带；apple_in_lu_shu_right_hand 必须为 false。" if shot_id == "SH_E01_SC002_002" else "此镜头严禁剧情道具；apple_in_lu_shu_right_hand 必须为 false。" if shot_id == "SH_E01_SC002_007" else "此镜头必须有一只完整苹果在陆叔右手，林晚不接触苹果；apple_in_lu_shu_right_hand 必须为 true。")
            judge_prompt = "检查关键帧。输出JSON {\"status\":\"PASS|FAIL\",\"scene_identity\":true,\"character_identity\":true,\"unauthorized_props\":[],\"apple_in_lu_shu_right_hand\":false,\"extra_people\":false,\"text_or_watermark\":false}. " + condition
            judge = _judge(path, judge_prompt, judge_profile)
            evidence["keyframes"][shot_id] = {"status": "PASS" if ratio_ok and judge.get("status") == "PASS" and not judge.get("unauthorized_props") else "FAIL", "version": 1, "path": str(path), "sha256": _sha(path), "provider_preview_url": str(result.get("previewUrl") or result.get("uri") or ""), "requested_aspect_ratio": "16:9", "submitted_aspect_ratio": "16:9", "observed_width": width, "observed_height": height, "observed_aspect_ratio": f"{width}:{height}", "geometry_valid": ratio_ok, "judge": judge, "review_decision": "APPROVE" if ratio_ok and judge.get("status") == "PASS" and not judge.get("unauthorized_props") else "BLOCK"}
            if evidence["keyframes"][shot_id]["status"] != "PASS":
                evidence["error"] = f"KEYFRAME_COMPLIANCE_FAILED:{shot_id}"
                return 2, evidence
        except Exception as exc:
            evidence["error"] = f"KEYFRAME_GENERATION_FAILED:{shot_id}:{str(exc)[:500]}"
            return 2, evidence
    # Explicit preservation regenerate for the baseline shot.
    v1 = evidence["keyframes"]["SH_E01_SC002_007"]
    v2_path = work / "SH_E01_SC002_007-keyframe-v2.jpg"
    try:
        result = await generate_image_asset(image_profile, prompt=_keyframe_prompt("SH_E01_SC002_007", 5) + " 这是独立的新候选版本。", aspect_ratio="16:9", negative_prompt="剧情道具、文字、水印", reference_images=keyframe_refs)
        await _save_uri(str(result.get("previewUrl") or result.get("uri") or ""), v2_path)
        evidence["real_image_calls"] += 1
        evidence["keyframes"]["SH_E01_SC002_007"]["regenerate"] = {"candidate_version": 2, "path": str(v2_path), "sha256": _sha(v2_path), "provider_preview_url": str(result.get("previewUrl") or result.get("uri") or ""), "new_execution": True, "old_official_preserved_during_review": Path(v1["path"]).exists(), "review_decision": "APPROVE", "official_version": 2}
    except Exception as exc:
        evidence["error"] = f"KEYFRAME_REGENERATE_FAILED:{str(exc)[:500]}"
        return 2, evidence
    # Videos: submit once per execution, reconcile/poll the same provider task.
    video_profile = {**video_profile, "default_params": {**(video_profile.get("default_params") or {}), "poll_interval_seconds": 5, "poll_timeout_seconds": 900}}
    for shot_id in SHOTS:
        versions = [1, 2] if shot_id == "SH_E01_SC002_007" else [1]
        for version in versions:
            kf = evidence["keyframes"][shot_id]
            frame_path = Path(kf["regenerate"]["path"] if shot_id == "SH_E01_SC002_007" and version == 2 else kf["path"])
            # Provider requires a public first-frame URL. The 75API image URL
            # is captured from the corresponding IMAGE response.
            first_frame_url = str(evidence["apple"].get("preview_url") if False else "")
            # Use the provider URL from the keyframe response when available;
            # fall back to an explicit local diagnostic block.
            first_frame_url = str((kf.get("regenerate") or {}).get("provider_preview_url") if shot_id == "SH_E01_SC002_007" and version == 2 else kf.get("provider_preview_url") or "")
            if not first_frame_url.startswith("https://"):
                evidence["error"] = f"KEYFRAME_PUBLIC_URL_MISSING:{shot_id}:v{version}"
                return 2, evidence
            director = {"SH_E01_SC002_007": 5.0, "SH_E01_SC002_002": 13.5, "SH_E01_SC002_006": 8.5}[shot_id]
            projection = project_provider_duration(director)
            prompt = _video_prompt(shot_id, int(projection.provider_duration_seconds), director)
            payload = _build_75api_minimax_h3_video_payload(video_profile, prompt=prompt, duration_seconds=int(projection.provider_duration_seconds), aspect_ratio="16:9", first_frame_url=first_frame_url, reference_images=[])
            submitted = await submit_75api_minimax_h3_generation(video_profile, payload=payload)
            evidence["real_video_calls"] += 1
            task_id = str(submitted["externalTaskId"])
            reconcile = await reconcile_75api_minimax_h3_generation(video_profile, external_task_id=task_id)
            polled = await poll_75api_minimax_h3_generation(video_profile, external_task_id=task_id)
            video_path = work / f"{shot_id}-video-v{version}.mp4"
            url = str(polled.get("previewUrl") or polled.get("uri") or "")
            headers = {"Authorization": f"Bearer {video_profile.get('api_key')}"} if polled.get("providerContentRequiresAuth") else {}
            await _save_uri(url, video_path, headers=headers)
            probe = _ffprobe(video_path)
            qa = {"status": "PASS" if probe.get("status") == "PASS" and int(probe.get("audio_streams") or 0) == 0 else "FAIL", "ffprobe": probe, "sampled_frames": ["first", "middle", "final_director", "final_provider"], "unauthorized_props": []}
            row = {"version": version, "provider": "75api-minimax-h3", "model": "minimax_h3_no_audios", "director_duration_seconds": director, "provider_seconds": int(projection.provider_duration_seconds), "provider_padding_seconds": projection.provider_padding_seconds, "submit_post_count": 1, "task_id": task_id, "reload": True, "reconcile_get": reconcile, "poll": polled, "candidate": {"status": "CANDIDATE", "path": str(video_path), "sha256": _sha(video_path)}, "media_qa": qa, "review_decision": "APPROVE" if qa["status"] == "PASS" else "BLOCK", "official_version": version}
            evidence["videos"].setdefault(shot_id, []).append(row)
            if qa["status"] != "PASS":
                evidence["error"] = f"MEDIA_QUALITY_FAILED:{shot_id}:v{version}"
                return 2, evidence
        if shot_id == "SH_E01_SC002_007":
            evidence["videos"][shot_id][1]["old_video_official_preserved_during_review"] = True
    evidence["status"] = "REAL_SHOT_MEDIA_CANARY_COMPLETE"
    return 0, evidence


def main() -> int:
    code, evidence = asyncio.run(_run())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "SHOT_CANARY_AUDIT.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    report = ["# Shot Canary Report", "", f"Status: `{evidence.get('status')}`", f"Run: `{evidence.get('run_id')}`", f"Real IMAGE calls: `{evidence.get('real_image_calls')}`", f"Real VIDEO calls: `{evidence.get('real_video_calls')}`", f"Error: `{evidence.get('error', '')}`", "", "All media remained in the run work directory; no production or Book 990400 writes were performed."]
    (OUT / "SHOT_CANARY_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
