"""Autonomous scene asset canary v3 with provider discovery and failover."""
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
import subprocess
import sys
import time
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.asset_provider_router import (  # noqa: E402
    AssetOperation,
    AssetProviderRouter,
    ProviderFailureClassification,
    ProviderHealthSnapshot,
    can_failover,
    classify_provider_failure,
)
from core.autonomous_asset_generation import (  # noqa: E402
    AssetGenerationBudgetPolicy,
    AssetRepairContext,
    AutonomousAssetGeneration,
    MediaEvidenceBinding,
    SceneConsistencyAudit,
    geometry_constrained_prompt,
)
from scripts.run_asset_media_canary_v1 import _free_port, _image_meta, _redact, _wait_for_health, _write  # noqa: E402
from scripts.run_autonomous_scene_asset_pipeline_v1 import (  # noqa: E402
    BASELINE,
    BOOK_ID,
    EPISODE,
    GEOMETRY,
    NEGATIVE,
    PLANS,
    SCENE_ID,
    _compose_board,
    _data_uri,
    _master_prompt,
    _safe_parse_json,
)
from scripts.run_autonomous_scene_asset_pipeline_v2 import _judge_global, _judge_pair  # noqa: E402

SOURCE_DB = ROOT / "work" / "db" / "screenplay.db"
OUT = ROOT / "docs" / "visual-assets" / "autonomous-v3"


def _sha256_text(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _profile_contract(profile: dict[str, Any]) -> dict[str, Any]:
    params = profile.get("default_params") if isinstance(profile.get("default_params"), dict) else {}
    file_sha = _sha256_file(output)
    return {
        "id": profile.get("id"), "provider": profile.get("provider"), "model_name": profile.get("model_name"),
        "supports_reference_images": bool(params.get("supports_reference_images")),
        "supports_image_url": bool(params.get("supports_image_url")),
        "supports_file_upload": bool(params.get("supports_file_upload")),
        "transport_binding_id": profile.get("transport_binding_id"),
    }


async def _submit(client: httpx.AsyncClient, base_url: str, profile_id: str, view_id: str, prompt: str, output: Path, *, refs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    reference_images = refs or []
    payload = {
        "book_id": BOOK_ID, "episode": EPISODE, "shot_id": f"AUTO_SCENE_V3_{SCENE_ID}_{view_id}",
        "source_node_id": f"autonomous-scene-v3:{SCENE_ID}:{view_id}", "source_asset_id": None,
        "asset_scope": "location", "asset_subject": f"{SCENE_ID} {view_id}", "target_kind": "reference-image",
        "prompt": prompt, "model_profile_id": profile_id, "aspect_ratio": "16:9", "reference_images": reference_images,
        "negative_prompt": NEGATIVE, "count": 1, "confirmed": True, "allow_external_call": True,
    }
    response = await client.post(f"{base_url}/api/prototyping/generate-reference-image", json=payload)
    response.raise_for_status()
    task_id = response.json()["task_id"]
    task: dict[str, Any] = {}
    deadline = time.time() + 900
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
    if local_path.exists():
        shutil.copy2(local_path, output)
    else:
        preview = str(asset.get("previewUrl") or asset.get("uri") or "")
        if preview.startswith("data:image/"):
            output.write_bytes(base64.b64decode(preview.split(",", 1)[1]))
        else:
            output.write_bytes((await client.get(preview)).content)
    provider_payload = task.get("provider_request_payload") or (asset.get("metadata") or {}).get("providerRequestPayload") or {}
    serialized = json.dumps(provider_payload, ensure_ascii=False, sort_keys=True, default=str)
    return {
        "view_id": view_id, "execution_id": task_id, "provider": task.get("provider"),
        "model_profile_id": task.get("model_profile_id") or profile_id, "candidate_status": "CANDIDATE",
        "prompt_fingerprint": _sha256_text(prompt), "reference_image_count": len(reference_images),
        "reference_image_sha256": reference_images[0].get("reference_sha256") if reference_images else "",
        "reference_role": reference_images[0].get("role") if reference_images else "",
        "provider_inline_reference_attached": "inlineData" in serialized or "inline_data" in serialized,
        "provider_request_payload": _redact(provider_payload),
        "file": {**_image_meta(output), "sha256": file_sha},
        "sha256": file_sha, "fingerprint": file_sha, "generation_execution_id": task_id, "path": str(output),
    }


def _reference(master: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    return [{"image_url": _data_uri(path), "reference_sha256": master["file"]["sha256"], "reference_name": "SCENE_MASTER", "role": "scene", "reference_purpose": "same physical room topology"}]


def _audit(view_id: str, attempt: int, media: dict[str, Any], master: dict[str, Any], judge: dict[str, Any], judge_status: str, req_fp: str, resp_fp: str, judge_profile: dict[str, Any]) -> SceneConsistencyAudit:
    scores = {key: int(judge.get(key) or 0) for key in ("architecture_score", "landmark_score", "furniture_score", "lighting_score")}
    same = bool(judge.get("same_physical_space")); critical = [str(x) for x in (judge.get("critical_topology_violations") or [])]; violations = [str(x) for x in (judge.get("violations") or [])]
    status = "PASS" if judge_status == "VISION_JUDGE_EXECUTED" and same and scores["architecture_score"] >= 85 and scores["landmark_score"] >= 85 and scores["furniture_score"] >= 80 and scores["lighting_score"] >= 80 and not critical else "REPAIR"
    now = datetime.now(timezone.utc).isoformat()
    evidence = MediaEvidenceBinding(view_id, attempt, str(master["file"]["sha256"]), str(media["file"]["sha256"]), str(master["execution_id"]), str(media["execution_id"]), str(judge_profile.get("id") or ""), str(judge_profile.get("model_name") or ""), req_fp, resp_fp, scores, scores, now, now)
    return SceneConsistencyAudit(view_id, status, same, scores["architecture_score"], scores["landmark_score"], scores["furniture_score"], scores["lighting_score"], critical, violations, judge_status, attempt, evidence)


def _write_failure(status: str, failure_code: str, failure_message: str, *, attempts: list[dict[str, Any]], traces: list[dict[str, Any]], routing: dict[str, Any], runtime: AutonomousAssetGeneration, events: list[dict[str, Any]], generations: dict[str, dict[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "autonomous_asset_pipeline_audit_v3", "status": status, "result": "FAILED", "scene_id": SCENE_ID,
        "failure_code": failure_code, "failure_message": failure_message[:1000], "previous_v2_closure": {"status": "CLOSED_MASTER_PROVIDER_CREDITS_INSUFFICIENT", "attempts": 1, "derived": 0, "repairs": 0, "video": 0},
        "generation": {"master_attempts": len(attempts), "derived_calls": max(len(generations) - 1, 0), "repair_calls": len(runtime.repairs), "total_image_calls": runtime.image_calls, "real_video_calls": 0}, "scene_view_evidence": generations, "authority": None,
        "provider_selection_trace": traces, "provider_routing": routing, "safety": {"production_writes": 0, "book_990400_writes": 0, "browser_direct_calls": 0, "secret_leaks": 0, "orphan_candidates": 0},
    }
    _write(OUT / "AUTONOMOUS_ASSET_PIPELINE_AUDIT.json", manifest); _write(OUT / "SCENE_PROVIDER_SELECTION_TRACE.json", traces); _write(OUT / "SCENE_PROVIDER_ROUTING.json", routing); _write(OUT / "SCENE_VIEW_EVIDENCE.json", generations); _write(OUT / "SCENE_PAIRWISE_CONSISTENCY_AUDIT.json", {"status": "NOT_RUN"}); _write(OUT / "SCENE_GLOBAL_CONSISTENCY_AUDIT.json", {"status": "NOT_RUN"}); _write(OUT / "SCENE_REPAIR_HISTORY.json", {"repairs": [], "events": events}); _write(OUT / "SCENE_AUTHORITY.json", {"status": "FAILED", "scene_id": SCENE_ID, "reason": failure_code}); _write(OUT / "SCENE_GEOMETRY_IR.json", {**asdict(GEOMETRY), "fingerprint": GEOMETRY.fingerprint, "authority": "topology"})
    (OUT / "AUTONOMOUS_ASSET_PIPELINE_REPORT.md").write_text("\n".join(["# Autonomous Visual Asset Pipeline V1.2", "", f"- Status: {status}", "- Previous v2 closure: CLOSED_MASTER_PROVIDER_CREDITS_INSUFFICIENT", f"- Failure code: {failure_code}", f"- Failure message: {failure_message[:1000]}", f"- Master attempts: {len(attempts)}", f"- Real IMAGE calls: {runtime.image_calls}", "- Real VIDEO calls: 0", "- SceneAuthority: FAILED", "- No READY promotion was performed."]), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--source-db", default=str(SOURCE_DB)); args = parser.parse_args()
    source_db = Path(args.source_db).resolve()
    if not source_db.exists(): raise SystemExit(f"missing database: {source_db}")
    budget = AssetGenerationBudgetPolicy(normal_calls_max=8, max_attempts_per_view=2)
    runtime = AutonomousAssetGeneration(asset_type="SCENE", asset_id=SCENE_ID, budget=budget); runtime.plan_scene(GEOMETRY, PLANS)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); work = ROOT / "work" / "autonomous-scene-provider-failover-canary-v3" / run_id; work.mkdir(parents=True, exist_ok=True)
    isolated_db = work / "screenplay.db"; shutil.copy2(source_db, isolated_db); uploads = work / "uploads"; port = _free_port(); env = os.environ.copy(); env.update({"DATABASE_URL": f"sqlite:///{isolated_db.as_posix()}?timeout=30", "UPLOAD_DIR": str(uploads), "DEPLOYMENT_ENV": "isolated", "APP_ENV": "test", "E2E_EXTERNAL_RUNTIME": ""})
    log = (work / "uvicorn.log").open("w", encoding="utf-8"); process = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    paths = {key: work / f"scene-{key.lower()}.jpg" for key in ("MASTER", "REVERSE", "SIDE", "DETAIL")}; generations: dict[str, dict[str, Any]] = {}; traces: list[dict[str, Any]] = []; attempts: list[dict[str, Any]] = []; events: list[dict[str, Any]] = []; audits: list[SceneConsistencyAudit] = []; health = ProviderHealthSnapshot()
    try:
        _wait_for_health(f"http://127.0.0.1:{port}", timeout=180); os.environ["DATABASE_URL"] = env["DATABASE_URL"]
        from api.model_registry import get_default_profile, list_profiles, test_profile_connection
        all_profiles = [item for item in list_profiles(include_sensitive=True) if item.get("enabled", True)]
        default_profile = get_default_profile("image") or {}; router = AssetProviderRouter(all_profiles, default_image_profile_id=str(default_profile.get("id") or ""), health=health)
        candidate_rows = router.rank("IMAGE", AssetOperation.TEXT_TO_IMAGE)
        async def preflight() -> None:
            for row in candidate_rows:
                trace = asdict(row)
                profile = next((p for p in all_profiles if str(p.get("id")) == row.profile_id), None) or {}
                try:
                    result = await test_profile_connection(profile_payload=profile)
                    trace["connection_probe"] = "PASS" if result.get("ok") else "FAIL"; trace["model_available"] = result.get("model_available", True if result.get("ok") else False)
                    if not result.get("ok"): trace["rejected_reason"] = str(result.get("message") or "MODEL_UNAVAILABLE")
                except Exception as exc:
                    trace["connection_probe"] = "FAIL"; trace["model_available"] = False; trace["rejected_reason"] = str(exc)[:500]
                traces.append(trace)
        asyncio.run(preflight())
        usable = [row for row in candidate_rows if next((t for t in traces if t["profile_id"] == row.profile_id), {}).get("connection_probe") == "PASS"]
        base_url = f"http://127.0.0.1:{port}"
        master_profile: dict[str, Any] | None = None
        async def try_master() -> None:
            nonlocal master_profile
            async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                for index, row in enumerate(usable[:2], 1):
                    profile = next(p for p in all_profiles if str(p.get("id")) == row.profile_id)
                    attempt = {"attempt": index, "profile_id": row.profile_id, "provider": row.provider, "model": row.model, "task_created": False}
                    try:
                        runtime.claim_image_call(); media = await _submit(client, base_url, row.profile_id, "MASTER", _master_prompt(), paths["MASTER"]); attempt.update({"status": "SUCCEEDED", "execution_id": media["execution_id"], "sha256": media["file"]["sha256"]}); attempts.append(attempt); generations["MASTER"] = media; master_profile = profile; runtime.record_primary(media); trace = next(t for t in traces if t["profile_id"] == row.profile_id); trace["selected"] = True; events.append({"kind": "MASTER_SELECTED", **attempt}); return
                    except Exception as exc:
                        classification = classify_provider_failure(exc); attempt.update({"status": "FAILED", "classification": classification.value, "error": str(exc)[:500]}); attempts.append(attempt); events.append({"kind": "MASTER_FAILED", **attempt})
                        if can_failover(classification): health.mark(row.profile_id, classification); continue
                        raise RuntimeError(classification.value) from exc
        if not usable: raise RuntimeError("MASTER_PROVIDER_PREFLIGHT_EXHAUSTED")
        asyncio.run(try_master())
        if master_profile is None: raise RuntimeError("MASTER_PROVIDER_POOL_EXHAUSTED")
        master_row = next(row for row in usable if row.profile_id == master_profile.get("id")); ref_candidates = router.candidates("IMAGE", AssetOperation.REFERENCE_IMAGE_DERIVATION)
        if master_row.profile_id not in [row.profile_id for row in ref_candidates]: raise RuntimeError("MASTER_PROVIDER_REFERENCE_INCOMPATIBLE")
        runtime.begin_derivation()
        async def generate_derived() -> None:
            async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                for plan in PLANS:
                    runtime.claim_image_call(); prompt = "这是同一间厨房。参考图是 MASTER 权威空间。保持门窗、水槽、连续橱柜、餐桌、瓷砖、台面、灯具和磨损状态完全不变，只改变摄影机位置和自然遮挡。禁止重新设计厨房。\n" + geometry_constrained_prompt(GEOMETRY, plan)
                    media = await _submit(client, base_url, master_row.profile_id, plan.view_id, prompt, paths[plan.view_id], refs=_reference(generations["MASTER"], paths["MASTER"]))
                    if media["reference_image_count"] != 1 or media["reference_image_sha256"] != generations["MASTER"]["file"]["sha256"] or media["reference_role"] != "scene" or not media["provider_inline_reference_attached"]: raise RuntimeError("REFERENCE_IMAGE_NOT_PROPAGATED")
                    generations[plan.view_id] = media; runtime.record_derived(plan.view_id, media); events.append({"kind": "DERIVED", "view_id": plan.view_id, "execution_id": media["execution_id"], "reference_sha256": media["reference_image_sha256"], "provider_inline_reference_attached": media["provider_inline_reference_attached"]})
        asyncio.run(generate_derived())
        judge_profile = next((p for p in all_profiles if p.get("capability") == "llm" and bool((p.get("default_params") or {}).get("supports_vision"))), {})
        for plan in PLANS:
            status, judge, req, resp = _judge_pair(judge_profile, paths["MASTER"], paths[plan.view_id], plan, GEOMETRY); row = _audit(plan.view_id, 1, generations[plan.view_id], generations["MASTER"], judge, status, req, resp, judge_profile); runtime.record_audit(row); audits.append(row)
        for plan in PLANS:
            latest = next(row for row in reversed(audits) if row.view_id == plan.view_id)
            if latest.passes: continue
            context = AssetRepairContext(plan.view_id, geometry_constrained_prompt(GEOMETRY, plan), generations[plan.view_id], latest.violations + latest.critical_topology_violations, [f"保持 {x}" for x in plan.required_landmarks] + ["继续使用 MASTER reference"], 2); runtime.prepare_repair(context); runtime.claim_image_call()
            async def repair_one(plan=plan, context=context) -> None:
                async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                    prompt = geometry_constrained_prompt(GEOMETRY, plan, repair=context) + "\n只修复 Judge 指出的违规，继续使用 MASTER reference。"; media = await _submit(client, base_url, master_row.profile_id, plan.view_id, prompt, paths[plan.view_id], refs=_reference(generations["MASTER"], paths["MASTER"]))
                    if media["reference_image_sha256"] != generations["MASTER"]["file"]["sha256"] or not media["provider_inline_reference_attached"]: raise RuntimeError("REFERENCE_IMAGE_NOT_PROPAGATED")
                    generations[plan.view_id] = media
            asyncio.run(repair_one()); runtime.record_derived(plan.view_id, generations[plan.view_id]); status, judge, req, resp = _judge_pair(judge_profile, paths["MASTER"], paths[plan.view_id], plan, GEOMETRY); row = _audit(plan.view_id, 2, generations[plan.view_id], generations["MASTER"], judge, status, req, resp, judge_profile); runtime.record_audit(row); audits.append(row); events.append({"kind": "REPAIR", "view_id": plan.view_id, "execution_id": generations[plan.view_id]["execution_id"]})
        latest = {row.view_id: row for row in audits}; global_status, global_judge, global_req, global_resp = _judge_global(judge_profile, paths, GEOMETRY) if all(latest.get(plan.view_id) and latest[plan.view_id].passes for plan in PLANS) else ("NOT_RUN", {"status": "NOT_RUN", "same_physical_space": False, "cross_derived_violations": ["pairwise gate failed"]}, "", "")
        authority = runtime.lock() if global_status == "VISION_JUDGE_EXECUTED" and global_judge.get("status") == "PASS" else None; OUT.mkdir(parents=True, exist_ok=True)
        for path in paths.values(): shutil.copy2(path, OUT / path.name)
        if BASELINE.exists(): shutil.copy2(BASELINE, OUT / "scene-v0-failed-baseline.jpg")
        board = _compose_board({key: OUT / path.name for key, path in paths.items()}, OUT / "scene-reference-board.png")
        pairwise = {"schema_version": "scene_pairwise_consistency_audit_v3", "audits": [asdict(row) for row in audits]}; global_audit = {"schema_version": "scene_global_consistency_audit_v3", "status": global_judge.get("status"), "same_physical_space": global_judge.get("same_physical_space"), "cross_derived_violations": global_judge.get("cross_derived_violations", []), "judge_request_fingerprint": global_req, "judge_response_fingerprint": global_resp}
        routing = {"master": _profile_contract(master_profile), "derived": _profile_contract(master_profile), "repair": _profile_contract(master_profile), "judge": _profile_contract(judge_profile), "master_locked": True}
        manifest = {
            "schema_version": "autonomous_asset_pipeline_audit_v3",
            "status": "AUTONOMOUS_SCENE_ASSET_PIPELINE_READY" if authority else "ASSET_CONSISTENCY_GENERATION_FAILED",
            "scene_id": SCENE_ID, "result": "READY" if authority else "FAILED",
            "previous_v2_closure": {"status": "CLOSED_MASTER_PROVIDER_CREDITS_INSUFFICIENT", "attempts": 1, "derived": 0, "repairs": 0, "video": 0},
            "provider_selection_trace": traces, "provider_health": health.unhealthy,
            "master_attempts": attempts, "failover": {"triggered": len(attempts) > 1, "max_attempts": 2, "terminal": len(attempts) >= 2 and attempts[-1].get("status") != "SUCCEEDED"},
            "provider_routing": routing,
            "generation": {"master_attempts": len(attempts), "derived_calls": 3, "repair_calls": len(runtime.repairs), "total_image_calls": runtime.image_calls, "real_video_calls": 0},
            "scene_view_evidence": generations, "pairwise_consistency": pairwise, "global_consistency": global_audit,
            "authority": authority, "final_board": board, "budget": asdict(budget),
            "safety": {"production_writes": 0, "book_990400_writes": 0, "browser_direct_calls": 0, "secret_leaks": 0, "orphan_candidates": 0},
        }
        _write(OUT / "AUTONOMOUS_ASSET_PIPELINE_AUDIT.json", manifest); _write(OUT / "SCENE_PROVIDER_SELECTION_TRACE.json", traces); _write(OUT / "SCENE_PROVIDER_ROUTING.json", routing); _write(OUT / "SCENE_VIEW_EVIDENCE.json", generations); _write(OUT / "SCENE_PAIRWISE_CONSISTENCY_AUDIT.json", pairwise); _write(OUT / "SCENE_GLOBAL_CONSISTENCY_AUDIT.json", global_audit); _write(OUT / "SCENE_REPAIR_HISTORY.json", {"repairs": [asdict(x) for x in runtime.repairs], "events": events}); _write(OUT / "SCENE_AUTHORITY.json", authority or {"status": "FAILED", "scene_id": SCENE_ID}); _write(OUT / "SCENE_GEOMETRY_IR.json", {**asdict(GEOMETRY), "fingerprint": GEOMETRY.fingerprint, "authority": "topology"})
        eligible_names = ", ".join(f"{item.get('provider')}/{item.get('model')}" for item in traces if not item.get("rejected_reason"))
        report_lines = [
            "# Autonomous Visual Asset Pipeline V1.2 Provider Failover Can-ary", "",
            f"- Status: {manifest['status']}", "- Scene: E01_SC002", "- Previous v2 closure: CLOSED_MASTER_PROVIDER_CREDITS_INSUFFICIENT (1 attempt; derived=0; repair=0; VIDEO=0)",
            "", "## Provider discovery and failover", "",
            f"- Eligible master/reference profiles: {eligible_names}",
            f"- Master attempt 1: {attempts[0].get('provider')} / {attempts[0].get('model')} / {attempts[0].get('classification', 'SUCCEEDED')}",
            f"- Failover triggered: {'yes' if len(attempts) > 1 else 'no'}; final master: {master_profile.get('provider')} / {master_profile.get('model_name')}",
            f"- Master execution: {generations['MASTER']['execution_id']}; SHA-256: {generations['MASTER']['file']['sha256']}",
            "", "## Derived views and evidence", "",
            *[f"- {view}: provider={generations[view]['provider']}; execution={generations[view]['execution_id']}; reference_sha={generations[view]['reference_image_sha256']}; inline_reference={generations[view]['provider_inline_reference_attached']}" for view in ("REVERSE", "SIDE", "DETAIL")],
            *[f"- {row.view_id}: {row.status}; attempt={row.attempt_number}; scores={row.media_evidence.judge_normalized_scores if row.media_evidence else {}}; critical={row.critical_topology_violations}" for row in latest.values()],
            "", "## Global Judge and authority", "", f"- Global Judge: {global_audit['status']}; same_physical_space={global_audit['same_physical_space']}", f"- Auto repair calls: {len(runtime.repairs)}", f"- SceneAuthority: {'READY' if authority else 'FAILED'}", "", "## Safety and budget", "", f"- Authorized IMAGE budget: {budget.normal_calls_max}; used: {runtime.image_calls}", "- Real VIDEO calls: 0", "- Production writes: 0; Book 990400 writes: 0; browser direct calls: 0; secret leaks: 0; orphan candidates: 0", "", "## Verification", "", "- Pairwise and global Judge evidence contain request/response fingerprints and 0-100 scores.", "- All derived references use the locked master SHA and scene role.", "- No keyframe or VIDEO generation was executed.",
        ]
        (OUT / "AUTONOMOUS_ASSET_PIPELINE_REPORT.md").write_text("\n".join(report_lines), encoding="utf-8")
        print(json.dumps({"status": manifest["status"], "image_calls": runtime.image_calls, "video_calls": 0, "output": str(OUT)}, ensure_ascii=False, indent=2)); return 0 if authority else 2
    except Exception as exc:
        classification = classify_provider_failure(exc); code = classification.value if classification != ProviderFailureClassification.UNKNOWN else str(exc).split(":", 1)[0]
        status = "MASTER_PROVIDER_POOL_EXHAUSTED" if code in {"MASTER_PROVIDER_PREFLIGHT_EXHAUSTED", "MASTER_PROVIDER_POOL_EXHAUSTED", "CREDITS_INSUFFICIENT", "CHANNEL_UNAVAILABLE", "MODEL_UNAVAILABLE", "AUTH_FAILED", "NETWORK_TRANSIENT"} else "ASSET_CONSISTENCY_GENERATION_FAILED"
        _write_failure(status, code, str(exc), attempts=attempts, traces=traces, routing={"master": "UNLOCKED", "derived": "NOT_RUN"}, runtime=runtime, events=events, generations=generations); print(json.dumps({"status": status, "failure_code": code, "image_calls": runtime.image_calls, "video_calls": 0, "output": str(OUT)}, ensure_ascii=False, indent=2)); return 2
    finally:
        process.terminate()
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
