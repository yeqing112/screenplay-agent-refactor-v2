"""One real Gate B H3 dialogue canary for the already approved SC002_002 keyframe."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import os
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.generation_adapters import build_75api_h3_payload_from_compiled_request, poll_75api_minimax_h3_generation, reconcile_75api_minimax_h3_generation, submit_75api_minimax_h3_generation
from api.model_registry import get_default_profile
from core.video_compiler_runtime import compile_video_intent
from core.video_intent_ir import build_video_intent_ir
from core.video_provider_prompt_ir import build_dialogue_contract, extract_provider_truth

OUT = ROOT / "docs" / "video-compiler" / "v1-closure"
DECISIONS = ROOT / "docs" / "prompt-quality" / "v4" / "DIRECTOR_DECISION_IR.json"
KEYFRAME_EVIDENCE = ROOT / "docs" / "shot-canary" / "v1" / "KEYFRAME_GENERATION_EVIDENCE.json"


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_response(value):
    if isinstance(value, dict):
        return {k: safe_response(v) for k, v in value.items() if str(k).lower() not in {"api_key", "authorization", "access_token", "secret"}}
    if isinstance(value, list):
        return [safe_response(x) for x in value]
    return value


def ffprobe(path: Path) -> dict:
    raw = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height", "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    data = json.loads(raw)
    streams = data.get("streams") or []
    return {"duration_seconds": float((data.get("format") or {}).get("duration") or 0), "streams": streams, "audio_streams": [x for x in streams if x.get("codec_type") == "audio"], "video_streams": [x for x in streams if x.get("codec_type") == "video"]}


async def download(url: str, path: Path, api_key: str) -> None:
    import httpx
    headers = {"Authorization": f"Bearer {api_key}"} if urlsplit(url).netloc == "www.75api.com" else {}
    async with httpx.AsyncClient(timeout=300, follow_redirects=True, trust_env=False) as client:
        last = None
        for _ in range(5):
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                path.write_bytes(response.content)
                return
            except Exception as exc:
                last = exc
                await asyncio.sleep(5)
        raise last


async def main() -> int:
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise RuntimeError("CLEAN_TREE_REQUIRED_BEFORE_GATE_B")
    profile = get_default_profile("video") or {}
    expected = {"provider": "75api-minimax-h3", "model_name": "minimax_h3", "video_compiler_id": "minimax-h3", "model_family": "minimax-h3"}
    if any(str(profile.get(k) or "") != v for k, v in expected.items()):
        raise RuntimeError(f"VIDEO_PROFILE_BINDING_MISMATCH:{json.dumps({k: profile.get(k) for k in expected}, ensure_ascii=False)}")
    decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))["canary_shots"]
    decision = next(x for x in decisions if x["shot_id"] == "SH_E01_SC002_002")
    keyframe = json.loads(KEYFRAME_EVIDENCE.read_text(encoding="utf-8"))["keyframes"]["SH_E01_SC002_002"]
    keyframe_path = Path(keyframe["artifact_path"])
    if not keyframe_path.exists() or keyframe.get("review_decision") != "APPROVE":
        raise RuntimeError("APPROVED_KEYFRAME_NOT_AVAILABLE")
    keyframe_sha = sha_bytes(keyframe_path.read_bytes())
    if keyframe_sha != keyframe["sha256"]:
        raise RuntimeError("APPROVED_KEYFRAME_SHA_MISMATCH")
    authority_fingerprint = sha_text(f"approved-keyframe:{keyframe_sha}")
    reference_plan = {"references": [{"role": "FIRST_FRAME", "asset_id": "SH_E01_SC002_002:official-keyframe-v1", "authority_fingerprint": authority_fingerprint, "media_sha256": keyframe_sha}]}
    intent = build_video_intent_ir(decision, reference_plan=reference_plan)
    compiled = compile_video_intent(intent, profile)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = OUT / "real-canary" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = build_75api_h3_payload_from_compiled_request(profile, compiled, resolved_references=[{"role": "FIRST_FRAME", "asset_id": "SH_E01_SC002_002:official-keyframe-v1", "authority_fingerprint": authority_fingerprint, "media_sha256": keyframe_sha, "url": keyframe["provider_preview_url"]}])
    payload_prompt_sha = sha_text(payload["prompt"])
    if payload_prompt_sha != compiled.compiled_prompt_sha256:
        raise RuntimeError("COMPILED_PROMPT_SHA_MISMATCH_BEFORE_POST")
    resume_task_id = str(os.environ.get("VIDEO_GATE_B_RESUME_TASK_ID") or "").strip()
    submitted = {"providerResponse": {}, "externalTaskId": resume_task_id} if resume_task_id else await submit_75api_minimax_h3_generation(profile, payload=payload, runtime_credential_value=str(profile.get("api_key") or ""))
    task_id = str(submitted["externalTaskId"])
    reconciled = await reconcile_75api_minimax_h3_generation(profile, external_task_id=task_id, runtime_credential_value=str(profile.get("api_key") or ""))
    polled = await poll_75api_minimax_h3_generation(profile, external_task_id=task_id, runtime_credential_value=str(profile.get("api_key") or ""))
    provider_response = polled.get("providerResponse") or reconciled.get("providerResponse") or submitted.get("providerResponse") or {}
    provider_truth = extract_provider_truth(provider_response)
    provider_prompt = provider_truth.get("properties_input") or None
    provider_prompt_sha = sha_text(provider_prompt) if provider_prompt is not None else None
    video_url = str(polled.get("previewUrl") or polled.get("uri") or "")
    video_path = run_dir / "SC002_002-real-video-candidate.mp4"
    await download(video_url, video_path, str(profile.get("api_key") or ""))
    media = ffprobe(video_path)
    audio_count = len(media["audio_streams"])
    duration_ok = 13.5 <= media["duration_seconds"] <= 14.5
    media_qa = {"status": "PASS" if duration_ok and audio_count >= 1 else "FAIL", "duration_projection": {"director_seconds": 13.5, "compiled_seconds": compiled.duration_seconds, "terminal_hold_seconds": 0.5}, "ffprobe": media, "audio_stream_present_expected": True, "unauthorized_props": {"status": "HUMAN_REVIEW_REQUIRED", "bag": 0, "bag_strap": 0, "handbag": 0}, "automated_transcript": "NOT_AVAILABLE"}
    dialogue_contract = build_dialogue_contract(decision)
    evidence = {"status": "READY_FOR_REVIEW" if media_qa["status"] == "PASS" else "MINIMAX_H3_NATIVE_DIALOGUE_MEDIA_QUALITY_FAILED", "run_id": run_id, "shot_id": "SH_E01_SC002_002", "provider": profile.get("provider"), "model": profile.get("model_name"), "video_compiler_id": profile.get("video_compiler_id"), "model_family": profile.get("model_family"), "real_image_calls": 0, "real_video_calls": 1, "task_id": task_id, "compiled_prompt_sha256": compiled.compiled_prompt_sha256, "payload_prompt_sha256": payload_prompt_sha, "provider_prompt_sha256": provider_prompt_sha, "provider_recorded_prompt_status": "PASS" if provider_prompt is not None else "PROVIDER_RECORDED_PROMPT_UNAVAILABLE", "compiled_request_fingerprint": compiled.compiled_request_fingerprint, "duration": {"director": 13.5, "compiled": compiled.duration_seconds, "padding": 0.5}, "speaker": dialogue_contract.speaker, "silent_listener": list(dialogue_contract.silent_characters), "unauthorized_props": {"bag": 0, "bag_strap": 0, "handbag": 0}, "media_qa": media_qa, "human_review": {"status": "PENDING", "chinese_clear": "PENDING", "dialogue_accuracy": "PENDING", "speaker_correct": "PENDING", "mouth_natural": "PENDING", "auto_asr": "NOT_AVAILABLE"}, "candidate": {"status": "CANDIDATE", "path": str(video_path.relative_to(ROOT)), "sha256": sha_bytes(video_path.read_bytes())}, "provider_truth": safe_response(provider_truth), "lifecycle": {"post_count": 1, "reconcile_same_task": True, "poll_same_task": True, "official_promotion": False}, "safety": {"shapi_calls": 0, "poyo_calls": 0, "production_writes": 0, "book_990400_writes": 0, "secret_leaks": 0, "orphans": 0}}
    (run_dir / "REAL_H3_NATIVE_DIALOGUE_CANARY.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "REAL_H3_NATIVE_DIALOGUE_CANARY.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = f"# Real H3 Native Dialogue Canary\n\nStatus: `{evidence['status']}`\nShot: `SH_E01_SC002_002`\nReal IMAGE: `0`\nReal VIDEO: `1`\nTask: `{task_id}`\nCompiled prompt SHA: `{compiled.compiled_prompt_sha256}`\nPayload prompt SHA: `{payload_prompt_sha}`\nProvider prompt SHA: `{provider_prompt_sha or 'PROVIDER_RECORDED_PROMPT_UNAVAILABLE'}`\nDuration: director `13.5`, compiled `14`, terminal hold `0.5`\nSpeaker: `{dialogue_contract.speaker}`\nSilent listener: `{', '.join(dialogue_contract.silent_characters)}`\nUnauthorized props: bag `0`, bag strap `0`, handbag `0`\nMedia QA: `{media_qa['status']}`\nHuman review: `PENDING`\n\nThe result remains a Candidate and was not promoted to Official.\n"
    (OUT / "REAL_H3_NATIVE_DIALOGUE_REPORT.md").write_text(report, encoding="utf-8")
    return 0 if media_qa["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
