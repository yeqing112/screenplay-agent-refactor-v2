"""Evidence locked autonomous scene reference derivation canary v2."""
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

from core.autonomous_asset_generation import (
    AssetGenerationBudgetPolicy,
    AssetRepairContext,
    AutonomousAssetGeneration,
    MediaEvidenceBinding,
    SceneConsistencyAudit,
    SceneDerivedViewPlan,
    SceneGeometryIR,
    geometry_constrained_prompt,
)
from scripts.run_asset_media_canary_v1 import _free_port, _image_meta, _redact, _wait_for_health, _write
from scripts.run_autonomous_scene_asset_pipeline_v1 import (
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

SOURCE_DB = ROOT / "work" / "db" / "screenplay.db"
OUT = ROOT / "docs" / "visual-assets" / "autonomous-v2"


def _sha256_text(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _profile_contract(profile: dict[str, Any]) -> dict[str, Any]:
    params = profile.get("default_params") if isinstance(profile.get("default_params"), dict) else {}
    return {
        "id": profile.get("id"),
        "provider": profile.get("provider"),
        "model_name": profile.get("model_name"),
        "supports_reference_images": bool(params.get("supports_reference_images")),
        "supports_image_url": bool(params.get("supports_image_url")),
        "supports_file_upload": bool(params.get("supports_file_upload")),
        "transport_binding_id": profile.get("transport_binding_id"),
    }


def _discover_profiles() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    from api.model_registry import get_default_profile, list_profiles

    profiles = [item for item in list_profiles(include_sensitive=True) if item.get("enabled", True)]
    images = [item for item in profiles if item.get("capability") == "image" and item.get("provider") != "75api-image"]
    reference = [item for item in images if bool((item.get("default_params") or {}).get("supports_reference_images"))]
    if not reference:
        raise RuntimeError("REFERENCE_IMAGE_PROVIDER_NOT_CONFIGURED")
    default_image = get_default_profile("image") or {}
    master = default_image if default_image in images else (images[0] if images else {})
    if not master:
        raise RuntimeError("IMAGE_PROVIDER_NOT_CONFIGURED")
    derived = next((item for item in reference if item.get("provider") == "shapi-gemini-image"), reference[0])
    llms = [item for item in profiles if item.get("capability") == "llm" and bool((item.get("default_params") or {}).get("supports_vision"))]
    judge = llms[0] if llms else {}
    if not judge:
        raise RuntimeError("VISUAL_JUDGE_NOT_CONFIGURED")
    return master, derived, derived, judge


async def _submit_view(client: httpx.AsyncClient, base_url: str, profile_id: str, view_id: str, prompt: str, output: Path, *, reference_images: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    refs = reference_images or []
    payload = {
        "book_id": BOOK_ID,
        "episode": EPISODE,
        "shot_id": f"AUTO_SCENE_V2_{SCENE_ID}_{view_id}",
        "source_node_id": f"autonomous-scene-v2:{SCENE_ID}:{view_id}",
        "source_asset_id": None,
        "asset_scope": "location",
        "asset_subject": f"{SCENE_ID} {view_id}",
        "target_kind": "reference-image",
        "prompt": prompt,
        "model_profile_id": profile_id,
        "aspect_ratio": "16:9",
        "reference_images": refs,
        "negative_prompt": NEGATIVE,
        "count": 1,
        "confirmed": True,
        "allow_external_call": True,
    }
    response = await client.post(f"{base_url}/api/prototyping/generate-reference-image", json=payload)
    response.raise_for_status()
    task_id = response.json()["task_id"]
    deadline = time.time() + 900
    task: dict[str, Any] = {}
    while time.time() < deadline:
        poll = await client.get(f"{base_url}/api/prototyping/tasks/{task_id}")
        poll.raise_for_status()
        task = poll.json()
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
    meta = _image_meta(output)
    meta["sha256"] = _sha256_file(output)
    provider_payload = task.get("provider_request_payload") or (asset.get("metadata") or {}).get("providerRequestPayload") or {}
    serialized_payload = json.dumps(provider_payload, ensure_ascii=False, sort_keys=True, default=str)
    inline_reference_attached = "inlineData" in serialized_payload or "inline_data" in serialized_payload
    return {
        "view_id": view_id,
        "execution_id": task_id,
        "provider": task.get("provider"),
        "model_profile_id": task.get("model_profile_id") or profile_id,
        "candidate_status": "CANDIDATE",
        "prompt_fingerprint": _sha256_text(prompt),
        "reference_image_count": len(refs),
        "reference_image_sha256": refs[0].get("reference_sha256") if refs else "",
        "reference_role": refs[0].get("role") if refs else "",
        "provider_inline_reference_attached": inline_reference_attached,
        "provider_request_payload": _redact(provider_payload),
        "file": meta,
        "path": str(output),
    }


def _judge_pair(profile: dict[str, Any], master: Path, derived: Path, plan: SceneDerivedViewPlan, geometry: SceneGeometryIR) -> tuple[str, dict[str, Any], str, str]:
    import core.llm as llm_client

    prompt = (
        "你是严格的场景空间连续性审计器。比较 MASTER 与 DERIVED 两张图片，判断 DERIVED 是否是 MASTER 同一物理空间在指定新机位下的合理视图。"
        "SceneGeometryIR 和 SceneDerivedViewPlan 是拓扑约束，不是可被图片推翻的事实。"
        "评分必须严格使用 0–100 整数，不得使用 0–10。只输出 JSON，不要 Markdown："
        '{"same_physical_space":true,"architecture_score":0,"landmark_score":0,"furniture_score":0,"lighting_score":0,"critical_topology_violations":[],"violations":[]}'
        f"\nSceneGeometryIR: {json.dumps(asdict(geometry), ensure_ascii=False, sort_keys=True)}"
        f"\nSceneDerivedViewPlan: {json.dumps(asdict(plan), ensure_ascii=False, sort_keys=True)}"
        "\n必须核对门、窗、水槽、连续橱柜、餐桌、材质、时间、天气和灯光方向。"
    )
    request_fp = _sha256_text(prompt + _sha256_file(master) + _sha256_file(derived))
    try:
        raw = llm_client.call_llm(prompt, system="scene pairwise consistency judge v2", model_profile=profile, retries=1, estimated_tokens=1800, max_tokens=2400, image_data_urls=[_data_uri(master), _data_uri(derived)])
        response_fp = _sha256_text(raw)
        parsed = _safe_parse_json(raw)
        if not parsed:
            return "VISION_JUDGE_INVALID", {"status": "VISION_JUDGE_INVALID", "raw_excerpt": str(raw)[:1000]}, request_fp, response_fp
        score_keys = ("architecture_score", "landmark_score", "furniture_score", "lighting_score")
        scores = [parsed.get(key) for key in score_keys]
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 100 for value in scores):
            return "VISION_JUDGE_INVALID_SCORE_SCALE", {"status": "VISION_JUDGE_INVALID_SCORE_SCALE", "raw": parsed}, request_fp, response_fp
        parsed["status"] = "PASS" if bool(parsed.get("same_physical_space")) and min(scores) >= 80 and not parsed.get("critical_topology_violations") else "REPAIR"
        return "VISION_JUDGE_EXECUTED", parsed, request_fp, response_fp
    except Exception as exc:
        return "VISION_JUDGE_UNAVAILABLE", {"status": "VISION_JUDGE_UNAVAILABLE", "error": str(exc)[:500]}, request_fp, _sha256_text(str(exc))


def _judge_global(profile: dict[str, Any], paths: dict[str, Path], geometry: SceneGeometryIR) -> tuple[str, dict[str, Any], str, str]:
    import core.llm as llm_client

    prompt = (
        "你是最终场景板连续性审计器。比较 MASTER、REVERSE、SIDE、DETAIL 四张已经分别通过 pairwise 的图片，检查三张 derived 之间是否存在互相矛盾的门、窗、水槽、橱柜、餐桌、材质或灯光事实。"
        "只输出 JSON：{\"status\":\"PASS|FAIL\",\"same_physical_space\":true,\"cross_derived_violations\":[]}。"
        f"\nSceneGeometryIR: {json.dumps(asdict(geometry), ensure_ascii=False, sort_keys=True)}"
    )
    request_fp = _sha256_text(prompt + "|".join(_sha256_file(paths[key]) for key in ("MASTER", "REVERSE", "SIDE", "DETAIL")))
    try:
        raw = llm_client.call_llm(prompt, system="scene global consistency judge v2", model_profile=profile, retries=1, estimated_tokens=1800, max_tokens=1600, image_data_urls=[_data_uri(paths[key]) for key in ("MASTER", "REVERSE", "SIDE", "DETAIL")])
        response_fp = _sha256_text(raw)
        parsed = _safe_parse_json(raw) or {"status": "VISION_JUDGE_INVALID"}
        parsed["status"] = "PASS" if parsed.get("status") == "PASS" and parsed.get("same_physical_space") is True and not parsed.get("cross_derived_violations") else "FAIL"
        return "VISION_JUDGE_EXECUTED", parsed, request_fp, response_fp
    except Exception as exc:
        return "VISION_JUDGE_UNAVAILABLE", {"status": "VISION_JUDGE_UNAVAILABLE", "error": str(exc)[:500]}, request_fp, _sha256_text(str(exc))


def _audit(view_id: str, attempt: int, media: dict[str, Any], master: dict[str, Any], judge: dict[str, Any], judge_status: str, request_fp: str, response_fp: str, judge_profile: dict[str, Any], generated_at: str, judged_at: str) -> SceneConsistencyAudit:
    scores = {key: int(judge.get(key) or 0) for key in ("architecture_score", "landmark_score", "furniture_score", "lighting_score")}
    same = bool(judge.get("same_physical_space"))
    critical = [str(item) for item in (judge.get("critical_topology_violations") or [])]
    violations = [str(item) for item in (judge.get("violations") or [])]
    status = "PASS" if judge_status == "VISION_JUDGE_EXECUTED" and same and scores["architecture_score"] >= 85 and scores["landmark_score"] >= 85 and scores["furniture_score"] >= 80 and scores["lighting_score"] >= 80 and not critical else "REPAIR"
    evidence = MediaEvidenceBinding(
        view_id=view_id,
        attempt_number=attempt,
        master_sha256=str(master["file"]["sha256"]),
        derived_sha256=str(media["file"]["sha256"]),
        master_generation_execution_id=str(master["execution_id"]),
        derived_generation_execution_id=str(media["execution_id"]),
        judge_profile_id=str(judge_profile.get("id") or ""),
        judge_model=str(judge_profile.get("model_name") or ""),
        judge_request_fingerprint=request_fp,
        judge_response_fingerprint=response_fp,
        judge_raw_scores=scores,
        judge_normalized_scores=scores,
        generated_at=generated_at,
        judged_at=judged_at,
    )
    return SceneConsistencyAudit(view_id=view_id, status=status, same_physical_space=same, architecture_score=scores["architecture_score"], landmark_score=scores["landmark_score"], furniture_score=scores["furniture_score"], lighting_score=scores["lighting_score"], critical_topology_violations=critical, violations=violations, judge_status=judge_status, attempt_number=attempt, media_evidence=evidence)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", default=str(SOURCE_DB))
    args = parser.parse_args()
    source_db = Path(args.source_db).resolve()
    if not source_db.exists():
        raise SystemExit(f"missing database: {source_db}")
    budget = AssetGenerationBudgetPolicy(normal_calls_max=7, max_attempts_per_view=2)
    runtime = AutonomousAssetGeneration(asset_type="SCENE", asset_id=SCENE_ID, budget=budget)
    runtime.plan_scene(GEOMETRY, PLANS)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work = ROOT / "work" / "autonomous-scene-reference-canary-v2" / run_id
    work.mkdir(parents=True, exist_ok=True)
    isolated_db = work / "screenplay.db"
    shutil.copy2(source_db, isolated_db)
    uploads = work / "uploads"
    port = _free_port()
    env = os.environ.copy()
    env.update({"DATABASE_URL": f"sqlite:///{isolated_db.as_posix()}?timeout=30", "UPLOAD_DIR": str(uploads), "DEPLOYMENT_ENV": "isolated", "APP_ENV": "test", "E2E_EXTERNAL_RUNTIME": ""})
    log = (work / "uvicorn.log").open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    paths = {"MASTER": work / "scene-master.jpg", "REVERSE": work / "scene-reverse.jpg", "SIDE": work / "scene-side.jpg", "DETAIL": work / "scene-detail.jpg"}
    generations: dict[str, dict[str, Any]] = {}
    audit_rows: list[SceneConsistencyAudit] = []
    events: list[dict[str, Any]] = []
    try:
        _wait_for_health(f"http://127.0.0.1:{port}", timeout=180)
        os.environ["DATABASE_URL"] = env["DATABASE_URL"]
        master_profile, derived_profile, repair_profile, judge_profile = _discover_profiles()
        if derived_profile.get("provider") == "75api-image":
            raise RuntimeError("REFERENCE_IMAGE_PROVIDER_NOT_CONFIGURED")
        base_url = f"http://127.0.0.1:{port}"
        async def generate_initial() -> None:
            async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                runtime.claim_image_call()
                generations["MASTER"] = await _submit_view(client, base_url, str(master_profile["id"]), "MASTER", _master_prompt(), paths["MASTER"])
                runtime.record_primary(generations["MASTER"])
                events.append({"view_id": "MASTER", "attempt": 1, "call": runtime.image_calls, "provider": master_profile.get("provider"), "model": master_profile.get("model_name")})
                runtime.begin_derivation()
                for plan in PLANS:
                    ref_sha = _sha256_file(paths["MASTER"])
                    prompt = "这是同一间厨房。参考图是 MASTER 权威空间。保持门窗、水槽、连续橱柜、餐桌、瓷砖、台面、灯具和磨损状态完全不变，只改变摄影机位置和自然遮挡。禁止重新设计厨房。\n" + geometry_constrained_prompt(GEOMETRY, plan)
                    refs = [{"image_url": _data_uri(paths["MASTER"]), "reference_sha256": ref_sha, "reference_name": "SCENE_MASTER", "role": "scene", "reference_purpose": "same physical room topology"}]
                    runtime.claim_image_call()
                    generations[plan.view_id] = await _submit_view(client, base_url, str(derived_profile["id"]), plan.view_id, prompt, paths[plan.view_id], reference_images=refs)
                    generations[plan.view_id]["reference_image_sha256"] = ref_sha
                    runtime.record_derived(plan.view_id, generations[plan.view_id])
                    events.append({"view_id": plan.view_id, "attempt": 1, "call": runtime.image_calls, "provider": derived_profile.get("provider"), "model": derived_profile.get("model_name"), "reference_image_count": 1, "reference_image_sha256": ref_sha, "provider_inline_reference_attached": generations[plan.view_id]["provider_inline_reference_attached"]})
        asyncio.run(generate_initial())
        for plan in PLANS:
            status, judge, req_fp, resp_fp = _judge_pair(judge_profile, paths["MASTER"], paths[plan.view_id], plan, GEOMETRY)
            row = _audit(plan.view_id, 1, generations[plan.view_id], generations["MASTER"], judge, status, req_fp, resp_fp, judge_profile, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
            runtime.record_audit(row)
            audit_rows.append(row)
        for plan in PLANS:
            latest = next(item for item in reversed(audit_rows) if item.view_id == plan.view_id)
            if latest.passes or runtime.image_calls >= budget.normal_calls_max:
                continue
            context = AssetRepairContext(view_id=plan.view_id, previous_prompt=geometry_constrained_prompt(GEOMETRY, plan), failed_output=generations[plan.view_id], violations=latest.violations + latest.critical_topology_violations, required_corrections=[f"保持 {item}" for item in plan.required_landmarks] + ["必须继续使用 MASTER reference，不得重设计物理房间"], attempt_number=2)
            runtime.prepare_repair(context)
            runtime.claim_image_call()
            async def repair_one() -> None:
                async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                    ref_sha = _sha256_file(paths["MASTER"])
                    prompt = geometry_constrained_prompt(GEOMETRY, plan, repair=context) + "\n只修复 Judge 指出的违规，继续使用 MASTER reference。"
                    refs = [{"image_url": _data_uri(paths["MASTER"]), "reference_sha256": ref_sha, "reference_name": "SCENE_MASTER", "role": "scene", "reference_purpose": "same physical room topology"}]
                    generations[plan.view_id] = await _submit_view(client, base_url, str(repair_profile["id"]), plan.view_id, prompt, paths[plan.view_id], reference_images=refs)
                    generations[plan.view_id]["reference_image_sha256"] = ref_sha
            asyncio.run(repair_one())
            events.append({"view_id": plan.view_id, "attempt": 2, "call": runtime.image_calls, "kind": "REPAIRING", "reference_image_count": 1, "reference_image_sha256": generations[plan.view_id]["reference_image_sha256"], "provider_inline_reference_attached": generations[plan.view_id]["provider_inline_reference_attached"]})
            runtime.record_derived(plan.view_id, generations[plan.view_id])
            status, judge, req_fp, resp_fp = _judge_pair(judge_profile, paths["MASTER"], paths[plan.view_id], plan, GEOMETRY)
            row = _audit(plan.view_id, 2, generations[plan.view_id], generations["MASTER"], judge, status, req_fp, resp_fp, judge_profile, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
            runtime.record_audit(row)
            audit_rows.append(row)
        latest = {item.view_id: item for item in audit_rows}
        global_status, global_judge, global_req, global_resp = _judge_global(judge_profile, paths, GEOMETRY) if all(latest.get(plan.view_id) and latest[plan.view_id].passes for plan in PLANS) else ("NOT_RUN", {"status": "NOT_RUN", "same_physical_space": False, "cross_derived_violations": ["pairwise gate failed"]}, "", "")
        authority = None
        if global_status == "VISION_JUDGE_EXECUTED" and global_judge.get("status") == "PASS":
            authority = runtime.lock()
        OUT.mkdir(parents=True, exist_ok=True)
        for path in paths.values():
            shutil.copy2(path, OUT / path.name)
        if BASELINE.exists():
            shutil.copy2(BASELINE, OUT / "scene-v0-failed-baseline.jpg")
        board = _compose_board({key: OUT / path.name for key, path in paths.items()}, OUT / "scene-reference-board.png")
        pairwise = {"schema_version": "scene_pairwise_consistency_audit_v2", "judge_profile_id": judge_profile.get("id"), "judge_model": judge_profile.get("model_name"), "audits": [asdict(item) for item in audit_rows]}
        global_audit = {"schema_version": "scene_global_consistency_audit_v2", "status": global_judge.get("status"), "same_physical_space": global_judge.get("same_physical_space"), "cross_derived_violations": global_judge.get("cross_derived_violations", []), "judge_request_fingerprint": global_req, "judge_response_fingerprint": global_resp}
        manifest = {"schema_version": "autonomous_asset_pipeline_audit_v2", "status": "AUTONOMOUS_SCENE_ASSET_PIPELINE_READY" if authority else "ASSET_CONSISTENCY_GENERATION_FAILED", "scene_id": SCENE_ID, "state": runtime.state.value, "result": "READY" if authority else "FAILED", "manual_approvals_required": 0, "manual_view_selection": 0, "previous_v1_truth": {"status": "ASSET_CONSISTENCY_GENERATION_FAILED", "source": "8c1ab62", "real_image_calls": 7}, "provider_routing": {"master": _profile_contract(master_profile), "derived": _profile_contract(derived_profile), "repair": _profile_contract(repair_profile), "judge": _profile_contract(judge_profile)}, "geometry": {**asdict(GEOMETRY), "fingerprint": GEOMETRY.fingerprint, "authority": "topology"}, "derived_route": "REFERENCE_IMAGE_DERIVATION", "generation": {"master_calls": 1, "derived_calls": runtime.image_calls - 1, "repair_calls": len(runtime.repairs), "total_image_calls": runtime.image_calls, "real_video_calls": 0}, "scene_view_evidence": generations, "pairwise_consistency": pairwise, "global_consistency": global_audit, "authority": authority, "final_board": board, "budget": asdict(budget)}
        _write(OUT / "SCENE_GEOMETRY_IR.json", {**asdict(GEOMETRY), "fingerprint": GEOMETRY.fingerprint, "authority": "topology"})
        _write(OUT / "SCENE_PROVIDER_ROUTING.json", manifest["provider_routing"])
        _write(OUT / "SCENE_VIEW_EVIDENCE.json", generations)
        _write(OUT / "SCENE_PAIRWISE_CONSISTENCY_AUDIT.json", pairwise)
        _write(OUT / "SCENE_GLOBAL_CONSISTENCY_AUDIT.json", global_audit)
        _write(OUT / "SCENE_REPAIR_HISTORY.json", {"repairs": [asdict(item) for item in runtime.repairs], "events": events})
        _write(OUT / "AUTONOMOUS_ASSET_PIPELINE_AUDIT.json", manifest)
        _write(OUT / "SCENE_AUTHORITY.json", authority or {"status": "FAILED", "scene_id": SCENE_ID, "geometry_fingerprint": GEOMETRY.fingerprint})
        lines = ["# Autonomous Visual Asset Pipeline V1.1 Reference Derivation", "", f"- Status: {manifest['status']}", "- Previous v1 truth: ASSET_CONSISTENCY_GENERATION_FAILED (8c1ab62, 7 IMAGE calls)", f"- Master provider: {master_profile.get('provider')} / {master_profile.get('model_name')}", f"- Derived provider: {derived_profile.get('provider')} / {derived_profile.get('model_name')}", f"- Judge provider: {judge_profile.get('provider')} / {judge_profile.get('model_name')}", "- Manual approvals required: 0", "- Manual view selection: 0", "", "## Generation", "", f"- Total real IMAGE calls: {runtime.image_calls}", f"- Repair calls: {len(runtime.repairs)}", "- Real VIDEO calls: 0", "", "## Pairwise consistency", ""]
        for plan in PLANS:
            row = latest.get(plan.view_id)
            lines.append(f"- {plan.view_id}: {row.status if row else 'MISSING'}; attempts={row.attempt_number if row else 0}; SHA={row.media_evidence.derived_sha256 if row and row.media_evidence else ''}; scores={row.media_evidence.judge_normalized_scores if row and row.media_evidence else {}}; critical={row.critical_topology_violations if row else []}")
        lines.extend(["", "## Global scene judge", "", f"- status: {global_audit['status']}", f"- same physical space: {global_audit['same_physical_space']}", f"- violations: {global_audit['cross_derived_violations']}", "", "## Authority", "", f"- SceneAuthority: {manifest['status']}", ""])
        (OUT / "AUTONOMOUS_ASSET_PIPELINE_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
        print(json.dumps({"status": manifest["status"], "state": runtime.state.value, "image_calls": runtime.image_calls, "video_calls": 0, "derived_provider": derived_profile.get("provider"), "output": str(OUT)}, ensure_ascii=False, indent=2))
        return 0 if authority else 2
    except Exception as exc:
        OUT.mkdir(parents=True, exist_ok=True)
        failure_code = str(exc).split(":", 1)[0] or "AUTONOMOUS_SCENE_CANARY_FAILED"
        failure = {
            "schema_version": "autonomous_asset_pipeline_audit_v2",
            "status": "ASSET_CONSISTENCY_GENERATION_FAILED",
            "scene_id": SCENE_ID,
            "state": "FAILED",
            "result": "FAILED",
            "manual_approvals_required": 0,
            "manual_view_selection": 0,
            "failure_code": failure_code,
            "failure_message": str(exc)[:500],
            "previous_v1_truth": {"status": "ASSET_CONSISTENCY_GENERATION_FAILED", "source": "8c1ab62", "real_image_calls": 7},
            "derived_route": "REFERENCE_IMAGE_DERIVATION",
            "generation": {"attempted_image_calls": runtime.image_calls, "real_video_calls": 0},
            "scene_view_evidence": generations,
            "authority": None,
        }
        _write(OUT / "AUTONOMOUS_ASSET_PIPELINE_AUDIT.json", failure)
        _write(OUT / "SCENE_PROVIDER_ROUTING.json", {"status": "FAILED", "failure_code": failure_code})
        _write(OUT / "SCENE_VIEW_EVIDENCE.json", generations)
        _write(OUT / "SCENE_PAIRWISE_CONSISTENCY_AUDIT.json", {"status": "NOT_RUN", "reason": "generation failed before pairwise Judge"})
        _write(OUT / "SCENE_GLOBAL_CONSISTENCY_AUDIT.json", {"status": "NOT_RUN", "reason": "pairwise gate not satisfied"})
        _write(OUT / "SCENE_REPAIR_HISTORY.json", {"repairs": [], "events": events})
        _write(OUT / "SCENE_AUTHORITY.json", {"status": "FAILED", "scene_id": SCENE_ID, "reason": failure_code})
        _write(OUT / "SCENE_GEOMETRY_IR.json", {**asdict(GEOMETRY), "fingerprint": GEOMETRY.fingerprint, "authority": "topology"})
        (OUT / "AUTONOMOUS_ASSET_PIPELINE_REPORT.md").write_text(
            "\n".join([
                "# Autonomous Visual Asset Pipeline V1.1 Reference Derivation",
                "",
                "- Status: ASSET_CONSISTENCY_GENERATION_FAILED",
                "- Previous v1 truth: ASSET_CONSISTENCY_GENERATION_FAILED (8c1ab62, 7 IMAGE calls)",
                f"- Failure code: {failure_code}",
                f"- Failure message: {str(exc)[:500]}",
                f"- Attempted real IMAGE calls: {runtime.image_calls}",
                "- Real VIDEO calls: 0",
                "- SceneAuthority: FAILED",
                "- No READY promotion was performed.",
            ]),
            encoding="utf-8",
        )
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
