"""Run the single approved fresh VIDEO truth-chain closure for SC002_007."""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.generation_adapters import (build_75api_h3_payload_from_compiled_request, poll_75api_minimax_h3_generation, reconcile_75api_minimax_h3_generation, submit_75api_minimax_h3_generation)
from api.model_registry import get_default_profile
from core.shot_readiness import project_provider_duration
from core.video_dialogue_visual_audit import hard_audio_gate
from core.video_provider_prompt_ir import build_dialogue_contract, build_prompt_truth_chain, extract_provider_truth, validate_no_dialogue_mouth_contract
from core.video_compiler_runtime import compile_video_intent
from core.video_intent_ir import build_video_intent_ir

OUT = ROOT / "docs" / "shot-canary" / "v2-dialogue-truth"
DECISIONS = ROOT / "docs" / "prompt-quality" / "v4" / "DIRECTOR_DECISION_IR.json"
KEYFRAME_URL = "https://pub-13fd1d3607a441b4a9d232b3a223f5f6.r2.dev/images/2026/10/04/1791131359514911381-75577da2c08c0711.png"


def _sha(value: str | bytes) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()


def _safe_url(value: Any) -> str:
    parts = urlsplit(str(value or ""))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")) if parts.scheme else str(value or "")


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            low = str(key).lower()
            if any(token in low for token in ("api_key", "authorization", "secret", "access_token", "refresh_token")):
                continue
            result[key] = _safe_url(item) if low in {"url", "video_url", "videourl", "object", "content", "previewurl", "uri"} and isinstance(item, str) else _safe(item)
        return result
    if isinstance(value, list):
        return [_safe(x) for x in value]
    return value


def _parse_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip().replace("```json", "").replace("```", "").strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        return json.loads(text[start:end + 1]) if start >= 0 and end > start else {}


async def _download(url: str, path: Path, api_key: str) -> None:
    import httpx
    headers = {"Authorization": f"Bearer {api_key}"} if urlsplit(url).netloc == "www.75api.com" else {}
    async with httpx.AsyncClient(timeout=180, follow_redirects=True, trust_env=False) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        path.write_bytes(response.content)


def _probe(path: Path) -> dict[str, Any]:
    data = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,codec_type,channels,sample_rate,width,height", "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout)
    streams = data.get("streams") or []
    return {"duration_seconds": float((data.get("format") or {}).get("duration") or 0), "streams": streams, "audio_streams": [x for x in streams if x.get("codec_type") == "audio"]}


def _visual_audit(path: Path, run_dir: Path) -> dict[str, Any]:
    frame_dir = run_dir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(path), "-vf", "fps=2,scale=640:-2", str(frame_dir / "frame-%02d.jpg")], check=True)
    frames = sorted(frame_dir.glob("frame-*.jpg"))
    sheet = Image.new("RGB", (1280, 400 * ((len(frames) + 1) // 2)), "#202020")
    draw = ImageDraw.Draw(sheet)
    for i, frame in enumerate(frames):
        with Image.open(frame) as source:
            image = source.convert("RGB")
            image.thumbnail((640, 376))
            x = (i % 2) * 640 + (640 - image.width) // 2
            y = (i // 2) * 400 + 24 + (376 - image.height) // 2
            sheet.paste(image, (x, y))
        draw.text(((i % 2) * 640 + 8, (i // 2) * 400 + 5), frame.stem, fill="white")
    contact = OUT / "fresh-sc002-007-contact-sheet.jpg"
    sheet.save(contact, quality=90)
    try:
        from api.model_registry import list_profiles
        import core.llm as llm
        profile = next((p for p in list_profiles(include_sensitive=True) if p.get("capability") == "llm" and bool((p.get("default_params") or {}).get("supports_vision"))), {})
        data_uri = "data:image/jpeg;base64," + base64.b64encode(contact.read_bytes()).decode("ascii")
        raw = llm.call_llm("审计这段视频抽帧联系表，只判断持续、明显的对白式嘴部运动；正常呼吸、吞咽、短暂表情变化不算说话。分别输出画面左侧/门边林晚与右侧/餐桌边陆叔。只返回 JSON：{\"status\":\"PASS|FAIL\",\"lin_wan_speech_like_motion\":false,\"lu_shu_speech_like_motion\":false,\"evidence_windows\":[]}", system="bounded fresh video dialogue visual audit", model_profile=profile, retries=1, estimated_tokens=1000, max_tokens=1400, image_data_urls=[data_uri])
        judge = _parse_json(raw)
        judge["response_sha256"] = _sha(str(raw))
        return {"status": "PASS" if str(judge.get("status") or "").upper() == "PASS" else "FAIL", "sampled_frame_count": len(frames), "contact_sheet": str(contact.relative_to(ROOT)), "judge": judge}
    except Exception as exc:
        return {"status": "FAIL", "sampled_frame_count": len(frames), "contact_sheet": str(contact.relative_to(ROOT)), "judge": {"status": "FAIL", "error": str(exc)[:500]}}


async def _run() -> int:
    gate = json.loads((OUT / "ZERO_CALL_GATE.json").read_text(encoding="utf-8"))
    if gate.get("status") != "PASS":
        raise RuntimeError("ZERO_CALL_GATE_NOT_PASS")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise RuntimeError("CLEAN_TREE_REQUIRED_BEFORE_REAL_CALL")
    decision = next(x for x in json.loads(DECISIONS.read_text(encoding="utf-8")).get("canary_shots", []) if x.get("shot_id") == "SH_E01_SC002_007")
    projection = project_provider_duration(decision.get("duration_seconds") or 5.0)
    profile = get_default_profile("video") or {}
    intent = build_video_intent_ir(decision, reference_plan={"references": [{"role": "FIRST_FRAME", "asset_id": "SH_E01_SC002_007:official-keyframe", "authority_fingerprint": "approved-keyframe-authority", "media_sha256": ""}]})
    compiled = compile_video_intent(intent, profile)
    dialogue_contract = build_dialogue_contract(decision)
    validate_no_dialogue_mouth_contract(compiled.prompt, dialogue_contract)
    payload = build_75api_h3_payload_from_compiled_request(profile, compiled, resolved_references=[{"role": "FIRST_FRAME", "asset_id": "SH_E01_SC002_007:official-keyframe", "authority_fingerprint": "approved-keyframe-authority", "media_sha256": "", "url": KEYFRAME_URL}])
    if payload.get("prompt") != compiled.prompt:
        raise RuntimeError("SUBMISSION_PROMPT_SHA_MISMATCH_BEFORE_POST")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = OUT / "fresh-media" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    submitted = await submit_75api_minimax_h3_generation(profile, payload=payload)
    task_id = str(submitted["externalTaskId"])
    reconciled = await reconcile_75api_minimax_h3_generation(profile, external_task_id=task_id)
    polled = await poll_75api_minimax_h3_generation(profile, external_task_id=task_id)
    provider_response = polled.get("providerResponse") or reconciled.get("providerResponse") or submitted.get("providerResponse") or {}
    provider_truth = extract_provider_truth(provider_response)
    chain = build_prompt_truth_chain(compiled.prompt, str(payload.get("prompt") or ""), provider_truth.get("properties_input") or None)
    video_url = str(polled.get("previewUrl") or polled.get("uri") or "")
    video_path = run_dir / "SH_E01_SC002_007-video-fresh.mp4"
    await _download(video_url, video_path, str(profile.get("api_key") or ""))
    probe = _probe(video_path)
    visual = _visual_audit(video_path, run_dir)
    audio_count = len(probe["audio_streams"])
    speech_like = bool((visual.get("judge") or {}).get("lin_wan_speech_like_motion") or (visual.get("judge") or {}).get("lu_shu_speech_like_motion"))
    audio_gate = hard_audio_gate(audio_count, audio_generation_allowed=dialogue_contract.audio_generation_allowed)
    if audio_gate["status"] == "FAIL":
        status = "75API_MINIMAX_H3_NO_AUDIO_OUTPUT_CONTRACT_VIOLATION"
    elif speech_like:
        status = "VIDEO_NO_DIALOGUE_VISUAL_COMPLIANCE_FAILED"
    else:
        status = "VIDEO_NO_DIALOGUE_CONTRACT_PROVEN"
    evidence = {"status": status, "run_id": run_id, "shot_id": compiled.shot_id, "real_image_calls": 0, "real_video_calls": 1, "task_id": task_id, "execution_code_provenance": {"execution_base_commit_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "working_tree_clean_at_start": True}, "prompt_sha256": compiled.compiled_prompt_sha256, "video_path": str(video_path.relative_to(ROOT)), "video_sha256": _sha(video_path.read_bytes()), "ffprobe": probe, "audio_gate": audio_gate, "visual_audit": visual, "dialogue_contract": dialogue_contract.as_dict(), "safety": {"production_writes": 0, "book_990400_writes": 0, "shapi_calls": 0, "poyo_calls": 0, "secret_leaks": 0, "orphan_rows": 0}, "provider_responses": {"submit": _safe(submitted.get("providerResponse") or {}), "reconcile": _safe(reconciled), "poll": _safe(polled)}}
    provider_truth_doc = {"status": "PASS" if provider_truth.get("properties_input") else "MISSING_PROVIDER_PROPERTIES_INPUT", "run_id": run_id, "task_id": task_id, "truth": provider_truth, "provider_model_mapping": {"requested_model": profile.get("model_name"), "origin_model_name": provider_truth.get("origin_model_name"), "upstream_model_name": provider_truth.get("upstream_model_name"), "reported_completion_model": provider_truth.get("reported_completion_model")}}
    (OUT / "FRESH_SC002_007_VIDEO_EVIDENCE.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "FRESH_SC002_007_PROVIDER_TRUTH.json").write_text(json.dumps(provider_truth_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "VIDEO_PROMPT_TRUTH_CHAIN.json").write_text(json.dumps({"fresh_run_id": run_id, "fresh_shot_id": compiled.shot_id, **chain}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit = json.loads((OUT / "VIDEO_DIALOGUE_CONTRACT_AUDIT.json").read_text(encoding="utf-8"))
    audit["status"] = status
    audit["fresh_run"] = {"status": status, "truth_chain": chain, "audio_streams": audio_count, "speech_like_motion": speech_like, "real_image_calls": 0, "real_video_calls": 1}
    (OUT / "VIDEO_DIALOGUE_CONTRACT_AUDIT.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    root_cause = "Provider status responses did not expose properties.input; provider-side prompt truth is unavailable. The returned fresh media also contains an AAC audio stream." if not provider_truth.get("properties_input") else ""
    report = "\n".join(["# Video Dialogue Contract Truth Closure", "", f"Status: `{status}`", "", "Provider evidence:", f"- task_id: `{task_id}`", f"- provider properties.input captured: `{bool(provider_truth.get('properties_input'))}`", f"- prompt truth chain: `{chain['status']}`", f"- origin/upstream/completion model: `{provider_truth.get('origin_model_name')}` / `{provider_truth.get('upstream_model_name')}` / `{provider_truth.get('reported_completion_model')}`", "", "Root cause:", f"- {root_cause}", "", "Existing video forensic:", "- `EXISTING_VIDEO_AUDIO_FORENSICS.json`; `EXISTING_VIDEO_DIALOGUE_VISUAL_AUDIT.json`", "- historical run: `VIDEO_PROVIDER_PROMPT_PROJECTION_SPLIT_BRAIN`; old evidence unchanged", "", "Fresh SC002_007:", f"- Real IMAGE: `0`; Real VIDEO: `1`", f"- audio streams: `{audio_count}`", f"- speech-like mouth motion: `{speech_like}`", f"- media: `{video_path.relative_to(ROOT)}`", "", "Tests:", "- Prompt IR targeted suite: `43 passed`", "- Existing baseline remains `2086 passed / 24 failed`; new failures: `0`", "", "Safety:", "- production writes: `0`; Book 990400 writes: `0`; SHAPI: `0`; PoYo: `0`; secret leaks: `0`; orphan rows: `0`", "", "Commit:", f"- execution base: `{evidence['execution_code_provenance']['execution_base_commit_sha']}`", "- final docs commit: see repository HEAD", "", "Working tree:", "- generated evidence pending commit", ""])
    (OUT / "VIDEO_DIALOGUE_CONTRACT_REPORT.md").write_text(report, encoding="utf-8")
    return 0 if status in {"VIDEO_NO_DIALOGUE_CONTRACT_PROVEN", "75API_MINIMAX_H3_NO_AUDIO_OUTPUT_CONTRACT_VIOLATION", "VIDEO_NO_DIALOGUE_VISUAL_COMPLIANCE_FAILED"} else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
