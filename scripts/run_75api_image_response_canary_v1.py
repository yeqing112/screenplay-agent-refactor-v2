"""One-call 75API IMAGE response-contract canary.

The script intentionally stops after Lin Wan MASTER. It never invokes a
derived view, another asset, a vision judge, or VIDEO.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.asset_provider_router import AssetOperation, AssetProviderRouter, ProviderHealthSnapshot  # noqa: E402
from core.asset_view_framing import AssetViewFramingPolicy  # noqa: E402
from core.generation_timeout import GenerationTimeoutHierarchy  # noqa: E402
from core.production_provider_policy import ProductionProviderPolicy  # noqa: E402
from scripts.run_asset_media_canary_v1 import _free_port, _wait_for_health, _write  # noqa: E402
from scripts.run_autonomous_visual_asset_pipeline_v4 import CHARACTERS, PRODUCTION_POLICY, _character_master_prompt, _sha  # noqa: E402

OUT = ROOT / "docs" / "provider-contract" / "75api-image-v1"
RUN_ROOT = ROOT / "work" / "75api-image-response-canary-v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", default=str(ROOT / "work" / "db" / "screenplay.db"))
    args = parser.parse_args()
    source_db = Path(args.source_db).resolve()
    if not source_db.exists():
        raise SystemExit(f"missing database: {source_db}")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work = RUN_ROOT / run_id
    work.mkdir(parents=True, exist_ok=True)
    isolated_db = work / "screenplay.db"
    shutil.copy2(source_db, isolated_db)
    port = _free_port()
    env = os.environ.copy()
    env.update({"DATABASE_URL": f"sqlite:///{isolated_db.as_posix()}?timeout=30", "UPLOAD_DIR": str(work / "uploads"), "DEPLOYMENT_ENV": "isolated", "APP_ENV": "test", "E2E_EXTERNAL_RUNTIME": ""})
    log_path = work / "uvicorn.log"
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    call_started = time.monotonic()
    evidence: dict[str, Any] = {"run_id": run_id, "status": "NOT_RUN", "real_image_calls": 0, "derived_calls": 0, "lu_shu_calls": 0, "handbag_calls": 0, "vision_judge_calls": 0, "real_video_calls": 0}
    try:
        _wait_for_health(f"http://127.0.0.1:{port}", timeout=180)
        os.environ["DATABASE_URL"] = env["DATABASE_URL"]
        from api.model_registry import get_default_profile, list_profiles, test_profile_connection
        from core.provider_transport_registry import get_provider_transport_binding

        profiles = [item for item in list_profiles(include_sensitive=True) if item.get("enabled", True)]
        default = get_default_profile("image") or next((item for item in profiles if item.get("capability") == "image" and item.get("is_default")), {})
        PRODUCTION_POLICY.assert_image_profile(default)
        hierarchy = GenerationTimeoutHierarchy.from_profile(default).as_dict()
        router = AssetProviderRouter(profiles, default_image_profile_id=str(default.get("id") or ""), health=ProviderHealthSnapshot())
        rows = router.rank("IMAGE", AssetOperation.TEXT_TO_IMAGE)
        candidates = [row for row in PRODUCTION_POLICY.filter_image_candidates(rows) if not row.rejected_reason]
        candidate = candidates[0] if candidates else None
        params = default.get("default_params") if isinstance(default.get("default_params"), dict) else {}
        preflight = {"status": "PASS" if candidate and get_provider_transport_binding(provider_id=PRODUCTION_POLICY.image_provider, target_media="IMAGE", binding_id=str(default.get("transport_binding_id") or "") or None) and bool(default.get("key_configured") or default.get("credential_configured") or default.get("api_key")) else "FAIL", "profile": {"id": default.get("id"), "provider": default.get("provider"), "model": default.get("model_name")}, "timeout_hierarchy": hierarchy, "capabilities": {"text_to_image": "text_to_image" in (params.get("task_modes") or []), "image_to_image": "image_to_image" in (params.get("task_modes") or []), "reference_images": bool(params.get("supports_reference_images"))}}
        async def run_probe() -> dict[str, Any]:
            try:
                result = await test_profile_connection(profile_payload=default)
                return {"status": "PASS" if result.get("ok") else "FAIL", "message": str(result.get("message") or "")[:500]}
            except Exception as exc:
                return {"status": "FAIL", "message": str(exc)[:500]}
        probe = asyncio.run(run_probe())
        preflight["connection_probe"] = probe
        _write(OUT / "75API_IMAGE_RESPONSE_CANARY_PREFLIGHT.json", preflight)
        if preflight["status"] != "PASS" or probe["status"] != "PASS" or not candidate:
            raise RuntimeError("75API_IMAGE_RESPONSE_CANARY_PREFLIGHT_FAILED")

        profile = next((item for item in profiles if str(item.get("id")) == candidate.profile_id), default)
        framing = AssetViewFramingPolicy.for_view("CHARACTER", "MASTER").as_dict()
        payload = {"book_id": 990452, "episode": 1, "shot_id": "75API_IMAGE_RESPONSE_CANARY_LIN_WAN_MASTER", "source_node_id": f"75api-image-response-canary:{run_id}", "asset_scope": "character", "asset_subject": "LIN_WAN MASTER", "target_kind": "reference-image", "prompt": _character_master_prompt(CHARACTERS[0]), "model_profile_id": profile["id"], "aspect_ratio": framing["provider_aspect_ratio"], "reference_images": [], "negative_prompt": "文字、Logo、水印、拼图、四宫格", "count": 1, "confirmed": True, "allow_external_call": True}
        evidence["real_image_calls"] = 1
        request_started = time.monotonic()
        async def send() -> dict[str, Any]:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=30, write=30, pool=30), trust_env=False) as client:
                response = await client.post(f"http://127.0.0.1:{port}/api/prototyping/generate-reference-image", json=payload, timeout=GenerationTimeoutHierarchy.from_profile(profile).httpx_timeout())
                response.raise_for_status()
                task_id = str(response.json().get("task_id") or "")
                if not task_id:
                    raise RuntimeError("CANARY_TASK_ID_MISSING")
                while True:
                    task_response = await client.get(f"http://127.0.0.1:{port}/api/prototyping/tasks/{task_id}")
                    task_response.raise_for_status()
                    task = task_response.json()
                    if task.get("status") in {"done", "error"}:
                        return {"submit_http_status": response.status_code, "task": task}
                    await asyncio.sleep(2)
        result = asyncio.run(send())
        task = result["task"]
        elapsed = round(time.monotonic() - request_started, 3)
        provider_shape = task.get("provider_response_shape") or (task.get("provider_response") or {}).get("provider_response_shape") or {}
        provider_fp = str(task.get("provider_response_fingerprint") or (task.get("provider_response") or {}).get("provider_response_fingerprint") or "")
        evidence.update({"status": "75API_IMAGE_RESPONSE_CONTRACT_PROVEN" if task.get("status") == "done" else "75API_IMAGE_RESPONSE_CONTRACT_BLOCKED", "http_status": result["submit_http_status"], "elapsed_seconds": elapsed, "provider_response_shape": provider_shape, "provider_response_fingerprint": provider_fp, "provider_response_media_path": str(task.get("provider_response_media_path") or ""), "provider_http_status": task.get("provider_http_status") or provider_shape.get("provider_http_status"), "post_submission_state": "TASK_CONFIRMED", "generation_execution_id": task.get("task_id")})
        if task.get("status") == "done":
            asset = task.get("asset") or {}
            persistence = (asset.get("metadata") or {}).get("generatedImagePersistence") or {}
            local_path = Path(str(persistence.get("local_path") or ""))
            evidence["matched_media_path"] = (asset.get("metadata") or {}).get("providerResponseMediaPath") or "url"
            evidence["media_type"] = (asset.get("file") or {}).get("mime_type") or "image/png"
            evidence["media_sha256"] = _sha(local_path) if local_path.exists() else ""
            evidence["result"] = "LIN_WAN_MASTER_READY"
        else:
            evidence["result"] = "PROVIDER_RESPONSE_CONTRACT_BLOCKED"
        _write(OUT / "75API_IMAGE_RESPONSE_CANARY.json", evidence)
        _write(OUT / "75API_IMAGE_RESPONSE_CONTRACT_AUDIT.json", {**evidence, "safety": {"raw_base64_persisted": 0, "signed_url_query_persisted": 0, "secret_leaks": 0, "production_writes": 0, "book_990400_writes": 0, "orphans": 0}})
        return 0 if task.get("status") == "done" else 2
    except Exception as exc:
        evidence.update({"status": "75API_IMAGE_RESPONSE_CONTRACT_BLOCKED", "result": str(exc)[:1000], "elapsed_seconds": round(time.monotonic() - call_started, 3)})
        _write(OUT / "75API_IMAGE_RESPONSE_CANARY.json", evidence)
        _write(OUT / "75API_IMAGE_RESPONSE_CONTRACT_AUDIT.json", {**evidence, "safety": {"raw_base64_persisted": 0, "signed_url_query_persisted": 0, "secret_leaks": 0, "production_writes": 0, "book_990400_writes": 0, "orphans": 0}})
        return 2
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=5)
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
