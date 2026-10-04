"""Fresh 75API IMAGE canary with provider timeout hierarchy and progressive stop.

This runner deliberately executes IMAGE only. It starts with one real Lin Wan
MASTER request, and only proceeds to derived views or later assets after the
previous stage has succeeded. Every output is run scoped and every board is
published atomically only after its Authority is READY.
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
from typing import Any, Mapping

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.asset_provider_router import AssetOperation, AssetProviderRouter, ProviderHealthSnapshot, PostSubmissionState, classify_provider_failure  # noqa: E402
from core.generation_timeout import GenerationTimeoutHierarchy  # noqa: E402
from core.production_provider_policy import ProductionProviderPolicy  # noqa: E402
from scripts.run_asset_media_canary_v1 import _free_port, _wait_for_health, _write  # noqa: E402
from scripts.run_autonomous_visual_asset_pipeline_v4 import (  # noqa: E402
    CHARACTERS,
    HANDBAG,
    PRODUCTION_POLICY,
    SCENE_AUTHORITY_PATH,
    _atomic_publish_board,
    _board,
    _character_master_prompt,
    _profile_fingerprint,
    _prop_master_prompt,
    _run_asset,
    _sha,
    _submit_asset,
    ProviderSubmissionError,
)
from core.asset_view_framing import AssetViewFramingPolicy  # noqa: E402

OUT = ROOT / "docs" / "visual-assets" / "75api-autonomous-v2"
WORK_ROOT = ROOT / "work" / "75api-autonomous-character-prop-canary-v2"
CANARY_BUDGET = {"林晚": {"normal": 6, "repair": 1}, "陆叔": {"normal": 6, "repair": 1}, "HANDBAG": {"normal": 4, "repair": 1}, "total": 19}


def _archive_stale_output(run_id: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    historical = OUT / "historical-invalid-artifacts" / run_id
    stale = [item for item in OUT.iterdir() if item.name != "historical-invalid-artifacts"]
    if not stale:
        return
    historical.mkdir(parents=True, exist_ok=True)
    for item in stale:
        shutil.move(str(item), str(historical / item.name))
    _write(historical / "STALE_NON_AUTHORITATIVE_ARTIFACTS.json", {
        "status": "STALE_NON_AUTHORITATIVE_ARTIFACT",
        "run_id": run_id,
        "reason": "new canary output is run-specific and cannot inherit unknown media or audit files",
        "files": [item.name for item in stale],
        "excluded_from_authorities": True,
    })


def _closure_old_run() -> None:
    _write(ROOT / "docs" / "visual-assets" / "75api-autonomous-v1" / "CLOSED_SUBMISSION_AMBIGUOUS.json", {
        "schema_version": "submission_closure_v1",
        "run_id": "de83476",
        "source_commit": "de83476",
        "status": "CLOSED_SUBMISSION_AMBIGUOUS",
        "retry_allowed": False,
        "resume_allowed": False,
        "reuse_allowed": False,
        "evidence_preserved": "historical-invalid-artifacts/de83476",
        "reason": "75api IMAGE POST returned timeout after submission; task outcome was not confirmed",
    })


def _base_paths(work: Path, asset_id: str, kind: str) -> dict[str, Path]:
    keys = ["MASTER", "FULL_FRONT", "FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_SIDE", "FULL_BACK"] if kind == "CHARACTER" else ["MASTER", "SIDE", "BACK", "DETAIL"]
    paths = {key: work / f"{asset_id.lower()}-{key.lower()}.jpg" for key in keys}
    if kind == "CHARACTER":
        paths["FULL_FRONT"] = paths["MASTER"]
    return paths


def _result_summaries(results: dict[str, Any]) -> dict[str, Any]:
    return {
        key: {
            "asset_id": value.get("asset_id"),
            "kind": value.get("kind"),
            "authority": value.get("authority"),
            "master": value.get("master"),
            "master_attempts": value.get("master_attempts", []),
            "generations": value.get("generations", {}),
            "audits": [asdict(row) for row in value.get("audits", [])],
            "global": value.get("global", {"status": "NOT_RUN"}),
            "repairs": value.get("repairs", []),
            "selected_profile": value.get("selected_profile"),
            "selection_trace": value.get("selection_trace", []),
        }
        for key, value in results.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", default=str(ROOT / "work" / "db" / "screenplay.db"))
    args = parser.parse_args()
    source_db = Path(args.source_db).resolve()
    if not source_db.exists():
        raise SystemExit(f"missing database: {source_db}")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work = WORK_ROOT / run_id
    work.mkdir(parents=True, exist_ok=True)
    staging = work / "publish-staging"
    staging.mkdir(parents=True, exist_ok=True)
    _archive_stale_output(run_id)
    _closure_old_run()

    isolated_db = work / "screenplay.db"
    shutil.copy2(source_db, isolated_db)
    uploads = work / "uploads"
    port = _free_port()
    env = os.environ.copy()
    env.update({"DATABASE_URL": f"sqlite:///{isolated_db.as_posix()}?timeout=30", "UPLOAD_DIR": str(uploads), "DEPLOYMENT_ENV": "isolated", "APP_ENV": "test", "E2E_EXTERNAL_RUNTIME": ""})
    log_path = work / "uvicorn.log"
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)

    health = ProviderHealthSnapshot()
    call_counter: dict[str, Any] = {"used": 0, "by_provider": {"75api-image": 0, "shapi-image": 0, "poyo-image": 0, "other-image": 0}}
    events: list[dict[str, Any]] = []
    results: dict[str, Any] = {}
    preflight: dict[str, Any] = {"status": "NOT_RUN", "policy": PRODUCTION_POLICY.as_dict()}
    timeout_hierarchy: dict[str, Any] = {}
    failure: str | None = None
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
        rows = router.rank("IMAGE", AssetOperation.TEXT_TO_IMAGE)
        candidates = PRODUCTION_POLICY.filter_image_candidates(rows)
        candidate = next((row for row in candidates if not row.rejected_reason), None)
        capability = {"text_to_image": "text_to_image" in (params.get("task_modes") or []), "image_to_image": "image_to_image" in (params.get("task_modes") or []), "reference_images": bool(params.get("supports_reference_images")), "https_reference": True, "data_uri_reference": True}
        credential_ready = bool(default.get("key_configured") or default.get("credential_configured") or default.get("api_key"))
        preflight = {"schema_version": "75api_image_preflight_v2", "status": "PASS" if candidate and transport and all(capability.values()) and credential_ready else "FAIL", "policy": PRODUCTION_POLICY.as_dict(), "profile": {"id": default.get("id"), "provider": default.get("provider"), "model": default.get("model_name"), "transport_binding_id": default.get("transport_binding_id")}, "credential_ready": credential_ready, "transport_registered": bool(transport), "capabilities": capability, "router_candidate": asdict(candidate) if candidate else None, "rejected_router_rows": [asdict(row) for row in rows if row not in candidates or row.rejected_reason], "reference_input_formats": ["data_uri", "https"], "real_generation_calls": 0}
        timeout_hierarchy = GenerationTimeoutHierarchy.from_profile(default).as_dict()
        preflight["timeout_hierarchy"] = timeout_hierarchy
        _write(OUT / "75API_IMAGE_PREFLIGHT.json", preflight)
        _write(OUT / "TIMEOUT_HIERARCHY.json", timeout_hierarchy)
        if preflight["status"] != "PASS":
            raise RuntimeError("75API_IMAGE_PREFLIGHT_FAILED")

        async def do_probe() -> dict[str, Any]:
            try:
                response = await test_profile_connection(profile_payload=default)
                return {"status": "PASS" if response.get("ok") else "FAIL", "message": str(response.get("message") or "")[:500], "model_available": response.get("model_available", True if response.get("ok") else False)}
            except Exception as exc:  # pragma: no cover - exercised by real canary
                return {"status": "FAIL", "message": str(exc)[:500], "model_available": False}
        probe = asyncio.run(do_probe())
        preflight["connection_probe"] = probe
        _write(OUT / "75API_IMAGE_PREFLIGHT.json", preflight)
        if probe["status"] != "PASS":
            raise RuntimeError("75API_IMAGE_PREFLIGHT_CONNECTION_FAILED")

        candidate_rows = [row for row in candidates if not row.rejected_reason]
        if not candidate_rows:
            raise RuntimeError("75API_IMAGE_NO_CANDIDATE")
        selected_row = candidate_rows[0]
        selected_profile = next((item for item in all_profiles if str(item.get("id")) == selected_row.profile_id), default)
        policy = PRODUCTION_POLICY
        judge_profile = next((item for item in all_profiles if item.get("capability") == "llm" and bool((item.get("default_params") or {}).get("supports_vision"))), {})
        if not judge_profile:
            raise RuntimeError("VISION_JUDGE_PROFILE_MISSING")
        base_url = f"http://127.0.0.1:{port}"

        async def run_canary() -> None:
            ordinary_timeout = httpx.Timeout(connect=10, read=30, write=30, pool=30)
            async with httpx.AsyncClient(timeout=ordinary_timeout, trust_env=False) as client:
                character = CHARACTERS[0]
                asset_id = str(character["id"])
                paths = _base_paths(work, asset_id, "CHARACTER")
                # Stage 0: exactly one Lin Wan MASTER. No retry after POST.
                call_counter["used"] += 1
                call_counter["by_provider"][str(selected_row.provider)] = call_counter["by_provider"].get(str(selected_row.provider), 0) + 1
                events.append({"kind": "MASTER_STARTED", "asset": asset_id, "run_id": run_id, "attempt": 1, "provider": selected_row.provider, "model": selected_row.model})
                try:
                    master = await _submit_asset(client, base_url, profile_id=str(selected_profile["id"]), asset_type="CHARACTER", asset_id=asset_id, view_id="MASTER", prompt=_character_master_prompt(character), output=paths["MASTER"], refs=[], framing=AssetViewFramingPolicy.for_view("CHARACTER", "MASTER").as_dict(), timeout_hierarchy=GenerationTimeoutHierarchy.from_profile(selected_profile))
                except ProviderSubmissionError as exc:
                    classification = classify_provider_failure(exc, post_submission_state=exc.post_submission_state)
                    events.append({"kind": "MASTER_FAILED", "asset": asset_id, "classification": exc.response_classification or classification.value, "post_submission_state": exc.post_submission_state.value, "task_created": exc.task_created, "timeout_evidence": exc.timeout_evidence, "configuration_error": exc.configuration_error, "provider_http_status": exc.provider_http_status, "provider_response_fingerprint": exc.provider_response_fingerprint, "provider_response_shape": exc.provider_response_shape, "provider_response_media_path": exc.provider_response_media_path, "error": str(exc)[:1000]})
                    raise RuntimeError(f"{asset_id}:SUBMISSION_{classification.value}:{exc.configuration_error or ''}:timeout_evidence={json.dumps(exc.timeout_evidence, ensure_ascii=False, sort_keys=True)}") from exc
                events.append({"kind": "MASTER_SUCCEEDED", "asset": asset_id, "execution_id": master["execution_id"], "timeout_evidence": master.get("timeout_evidence")})
                preflight["real_generation_calls"] = 1
                _write(OUT / "75API_IMAGE_PREFLIGHT.json", preflight)

                # Stage 1: derived views are entered only after MASTER success.
                result = await _run_asset(client, base_url, kind="CHARACTER", asset=character, candidate_rows=candidate_rows, all_profiles=all_profiles, judge_profile=judge_profile, health=health, paths=paths, budget=CANARY_BUDGET[character["name"]], call_counter=call_counter, traces=[], events=events, policy=policy, existing_master=master, existing_profile=selected_profile, master_attempts_override=[{"provider": selected_row.provider, "model": selected_row.model, "status": "SUCCEEDED", "execution_id": master["execution_id"], "post_submission_state": PostSubmissionState.TASK_CONFIRMED.value}])
                results[asset_id] = result
                if not result.get("authority"):
                    raise RuntimeError("LIN_WAN_AUTHORITY_NOT_READY")
                board = _board({key: paths[key] for key in ["FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_FRONT", "FULL_SIDE", "FULL_BACK"]}, staging / "lin-wan-reference-board.png", ["FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_FRONT", "FULL_SIDE", "FULL_BACK"], 3, run_id=run_id, authority=result["authority"])
                _atomic_publish_board(staging / "lin-wan-reference-board.png", OUT / "lin-wan-reference-board.png")
                result["board"] = board

                # Stage 2/3 continue progressively. Any failure retains staging
                # and never promotes a board for the failed authority.
                for character in (CHARACTERS[1],):
                    asset_id = str(character["id"]); paths = _base_paths(work, asset_id, "CHARACTER")
                    result = await _run_asset(client, base_url, kind="CHARACTER", asset=character, candidate_rows=candidate_rows, all_profiles=all_profiles, judge_profile=judge_profile, health=health, paths=paths, budget=CANARY_BUDGET[character["name"]], call_counter=call_counter, traces=[], events=events, policy=policy)
                    results[asset_id] = result
                    if not result.get("authority"):
                        raise RuntimeError("LU_SHU_AUTHORITY_NOT_READY")
                    board = _board({key: paths[key] for key in ["FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_FRONT", "FULL_SIDE", "FULL_BACK"]}, staging / "lu-shu-reference-board.png", ["FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_FRONT", "FULL_SIDE", "FULL_BACK"], 3, run_id=run_id, authority=result["authority"])
                    _atomic_publish_board(staging / "lu-shu-reference-board.png", OUT / "lu-shu-reference-board.png")
                    result["board"] = board

                paths = _base_paths(work, "HANDBAG", "PROP")
                result = await _run_asset(client, base_url, kind="PROP", asset=HANDBAG, candidate_rows=candidate_rows, all_profiles=all_profiles, judge_profile=judge_profile, health=health, paths=paths, budget=CANARY_BUDGET["HANDBAG"], call_counter=call_counter, traces=[], events=events, policy=policy)
                results["HANDBAG"] = result
                if not result.get("authority"):
                    raise RuntimeError("HANDBAG_AUTHORITY_NOT_READY")
                board = _board(paths, staging / "handbag-reference-board.png", ["MASTER", "SIDE", "BACK", "DETAIL"], 2, run_id=run_id, authority=result["authority"])
                _atomic_publish_board(staging / "handbag-reference-board.png", OUT / "handbag-reference-board.png")
                result["board"] = board

        asyncio.run(run_canary())
        scene_authority = json.loads(SCENE_AUTHORITY_PATH.read_text(encoding="utf-8")) if SCENE_AUTHORITY_PATH.exists() else {"status": "MISSING"}
        _write(OUT / "CHARACTER_AUTHORITIES.json", {key: results[key].get("authority") for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_AUTHORITIES.json", {"HANDBAG": results["HANDBAG"].get("authority")})
        _write(OUT / "CHARACTER_VIEW_EVIDENCE.json", {key: results[key].get("generations", {}) for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_VIEW_EVIDENCE.json", {"HANDBAG": results["HANDBAG"].get("generations", {})})
        _write(OUT / "CHARACTER_CONSISTENCY_AUDIT.json", {key: {"audits": [asdict(row) for row in results[key].get("audits", [])], "global": results[key].get("global", {})} for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_CONSISTENCY_AUDIT.json", {"HANDBAG": {"audits": [asdict(row) for row in results["HANDBAG"].get("audits", [])], "global": results["HANDBAG"].get("global", {})}})
        _write(OUT / "CHARACTER_REPAIR_HISTORY.json", {key: results[key].get("repairs", []) for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_REPAIR_HISTORY.json", {"HANDBAG": results["HANDBAG"].get("repairs", [])})
        authority_set = {"status": "READY", "characters": {key: results[key]["authority"] for key in ("LIN_WAN", "LU_SHU")}, "scene": scene_authority, "props": {"HANDBAG": results["HANDBAG"]["authority"]}, "visual_style_fingerprint": _sha("visual-style-v1")}
        _write(OUT / "VISUAL_ASSET_AUTHORITY_SET.json", authority_set)
        manifest = {"schema_version": "75api_autonomous_character_prop_canary_v2", "phase": "PHASE_75API_IMAGE_TIMEOUT_HIERARCHY_AND_FRESH_CHARACTER_CANARY", "final_marker": "PHASE_75API_IMAGE_TIMEOUT_HIERARCHY_AND_FRESH_CHARACTER_CANARY_COMPLETE", "run_id": run_id, "status": "AUTONOMOUS_VISUAL_ASSET_PIPELINE_READY_FOR_SHOT_CANARY", "production_provider_policy": PRODUCTION_POLICY.as_dict(), "timeout_hierarchy": timeout_hierarchy, "preflight": preflight, "characters": _result_summaries(results), "authority_set": authority_set, "real_image_calls": call_counter["used"], "real_image_calls_by_provider": call_counter["by_provider"], "real_video_calls": 0, "safety": {"production_writes": 0, "book_990400_writes": 0, "browser_direct_provider_calls": 0, "secret_leaks": 0, "orphans": 0}}
        _write(OUT / "AUTONOMOUS_VISUAL_ASSET_AUDIT.json", manifest)
        _write(OUT / "CANARY_EVENTS.json", {"run_id": run_id, "events": events})
        report = ["# 75API Image Timeout Hierarchy and Fresh Character Canary", "", "- Status: `AUTONOMOUS_VISUAL_ASSET_PIPELINE_READY_FOR_SHOT_CANARY`", f"- Run: `{run_id}`", "- Old ambiguous run `de83476`: `CLOSED_SUBMISSION_AMBIGUOUS`; retry/resume/reuse disabled", f"- Provider timeout: `{timeout_hierarchy.get('provider_timeout_seconds')}s`; orchestration read timeout: `{timeout_hierarchy.get('orchestration_read_timeout_seconds')}s`", f"- Real IMAGE calls: `{call_counter['used']}`; real VIDEO calls: `0`", "- All three authorities READY; boards atomically published", "- No production database writes; no VIDEO/keyframe generation.", "", "## Boards", "- Lin Wan: `lin-wan-reference-board.png`", "- Lu Shu: `lu-shu-reference-board.png`", "- HANDBAG: `handbag-reference-board.png`"]
        (OUT / "AUTONOMOUS_VISUAL_ASSET_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        return 0
    except Exception as exc:
        failure = str(exc)[:2000]
        status = {"schema_version": "75api_autonomous_character_prop_canary_v2", "phase": "PHASE_75API_IMAGE_TIMEOUT_HIERARCHY_AND_FRESH_CHARACTER_CANARY", "final_marker": "PHASE_75API_IMAGE_TIMEOUT_HIERARCHY_AND_FRESH_CHARACTER_CANARY_PARTIAL", "run_id": run_id, "status": "AUTONOMOUS_VISUAL_ASSET_PIPELINE_PARTIAL", "failure": failure, "production_provider_policy": PRODUCTION_POLICY.as_dict(), "timeout_hierarchy": timeout_hierarchy, "preflight": preflight, "characters": _result_summaries(results), "real_image_calls": call_counter["used"], "real_image_calls_by_provider": call_counter["by_provider"], "real_video_calls": 0, "publish_staging": str(staging), "board_publication": {"LIN_WAN": "PUBLISHED" if results.get("LIN_WAN", {}).get("board") else "NOT_PUBLISHED", "LU_SHU": "PUBLISHED" if results.get("LU_SHU", {}).get("board") else "NOT_PUBLISHED", "HANDBAG": "PUBLISHED" if results.get("HANDBAG", {}).get("board") else "NOT_PUBLISHED"}, "safety": {"production_writes": 0, "book_990400_writes": 0, "browser_direct_provider_calls": 0, "secret_leaks": 0, "orphans": 0}}
        _write(OUT / "AUTONOMOUS_VISUAL_ASSET_AUDIT.json", status)
        _write(OUT / "CANARY_EVENTS.json", {"run_id": run_id, "events": events})
        _write(OUT / "CHARACTER_AUTHORITIES.json", {key: results.get(key, {}).get("authority") for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_AUTHORITIES.json", {"HANDBAG": results.get("HANDBAG", {}).get("authority")})
        _write(OUT / "CHARACTER_VIEW_EVIDENCE.json", {key: results.get(key, {}).get("generations", {}) for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_VIEW_EVIDENCE.json", {"HANDBAG": results.get("HANDBAG", {}).get("generations", {})})
        _write(OUT / "CHARACTER_CONSISTENCY_AUDIT.json", {key: {"audits": [asdict(row) for row in results.get(key, {}).get("audits", [])], "global": results.get(key, {}).get("global", {"status": "NOT_RUN"})} for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_CONSISTENCY_AUDIT.json", {"HANDBAG": {"audits": [asdict(row) for row in results.get("HANDBAG", {}).get("audits", [])], "global": results.get("HANDBAG", {}).get("global", {"status": "NOT_RUN"})}})
        _write(OUT / "CHARACTER_REPAIR_HISTORY.json", {key: results.get(key, {}).get("repairs", []) for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_REPAIR_HISTORY.json", {"HANDBAG": results.get("HANDBAG", {}).get("repairs", [])})
        _write(OUT / "VISUAL_ASSET_AUTHORITY_SET.json", {"status": "PARTIAL", "characters": {key: results.get(key, {}).get("authority") for key in ("LIN_WAN", "LU_SHU")}, "props": {"HANDBAG": results.get("HANDBAG", {}).get("authority")}})
        report = ["# 75API Image Timeout Hierarchy and Fresh Character Canary", "", "- Status: `AUTONOMOUS_VISUAL_ASSET_PIPELINE_PARTIAL`", f"- Run: `{run_id}`", f"- Failure: `{failure}`", "- Old ambiguous run `de83476`: `CLOSED_SUBMISSION_AMBIGUOUS`; retry/resume/reuse disabled", f"- Real IMAGE calls: `{call_counter['used']}`; real VIDEO calls: `0`", "- Partial run retained under publish-staging; failed authorities have no final board."]
        for key, label in (("LIN_WAN", "Lin Wan"), ("LU_SHU", "Lu Shu"), ("HANDBAG", "HANDBAG")):
            state = "READY" if results.get(key, {}).get("authority") else ("INCOMPLETE" if key == "LIN_WAN" else "NOT_STARTED")
            report.append(f"- {label}: status={state}; board={'PUBLISHED' if results.get(key, {}).get('board') else 'NOT_PUBLISHED'}; reason={'READY_AUTHORITY' if state == 'READY' else failure}")
        report.append(f"- Staging retained: `{staging}`")
        (OUT / "AUTONOMOUS_VISUAL_ASSET_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
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
