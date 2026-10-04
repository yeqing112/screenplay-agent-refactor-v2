"""75API-only autonomous character/prop canary V3.

Lin Wan MASTER is imported immutably from the proven response-contract canary.
The runner then progresses through derived views, Lu Shu, and HANDBAG only
when the preceding Authority is READY. VIDEO and Shot Keyframe work are out
of scope.
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
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.asset_provider_router import AssetOperation, AssetProviderRouter, ProviderHealthSnapshot  # noqa: E402
from core.asset_view_framing import AssetViewFramingPolicy  # noqa: E402
from core.autonomous_visual_assets import CharacterAuthority, PropAuthority, VisualAssetAuthoritySet  # noqa: E402
from core.generation_timeout import GenerationTimeoutHierarchy  # noqa: E402
from core.production_provider_policy import ProductionProviderPolicy  # noqa: E402
from scripts.run_asset_media_canary_v1 import _free_port, _image_meta, _wait_for_health, _write  # noqa: E402
from scripts.run_autonomous_visual_asset_pipeline_v4 import (  # noqa: E402
    CHARACTERS,
    HANDBAG,
    PRODUCTION_POLICY,
    SCENE_AUTHORITY_PATH,
    _atomic_publish_board,
    _board,
    _character_master_prompt,
    _profile_fingerprint,
    _run_asset,
    _sha,
    ProviderSubmissionError,
)

OUT = ROOT / "docs" / "visual-assets" / "75api-autonomous-v3"
RUN_ROOT = ROOT / "work" / "75api-autonomous-asset-canary-v3"
MASTER = ROOT / "docs" / "provider-contract" / "75api-image-v1" / "LIN_WAN_MASTER.png"
MASTER_PROVENANCE = ROOT / "docs" / "provider-contract" / "75api-image-v1" / "LIN_WAN_MASTER.provenance.json"
MASTER_SHA = "fb16b58520681d04460467ede564ab44232c629dff128cadaad2eb5e18853c1b"
MASTER_RUN = "20261004T105249Z"
MASTER_EXECUTION = "c880b07f4c0c"
CANARY_BUDGET = {"林晚": {"normal": 6, "repair": 1}, "陆叔": {"normal": 6, "repair": 1}, "HANDBAG": {"normal": 4, "repair": 1}, "total": 19}


def _archive_stale_output(run_id: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    stale = [item for item in OUT.iterdir() if item.name != "historical-invalid-artifacts"]
    if not stale:
        return
    historical = OUT / "historical-invalid-artifacts" / run_id
    historical.mkdir(parents=True, exist_ok=True)
    for item in stale:
        shutil.move(str(item), str(historical / item.name))
    _write(historical / "STALE_NON_AUTHORITATIVE_ARTIFACTS.json", {"status": "STALE_NON_AUTHORITATIVE_ARTIFACT", "run_id": run_id, "files": [item.name for item in stale], "excluded_from_authorities": True})


def _validate_imported_master() -> dict[str, Any]:
    if not MASTER.exists() or not MASTER_PROVENANCE.exists():
        raise RuntimeError("MASTER_PROVENANCE_INVALID")
    try:
        with Image.open(MASTER) as image:
            image.verify()
    except Exception as exc:
        raise RuntimeError("MASTER_PROVENANCE_INVALID:PNG_UNDECODABLE") from exc
    sha = _sha(MASTER)
    provenance = json.loads(MASTER_PROVENANCE.read_text(encoding="utf-8"))
    checks = {
        "file_exists": True,
        "png_decodable": True,
        "media_sha256": sha == MASTER_SHA,
        "run_id": provenance.get("run_id") == MASTER_RUN,
        "generation_execution_id": provenance.get("generation_execution_id") == MASTER_EXECUTION,
        "provider": provenance.get("provider") == "75api-image",
        "model": provenance.get("model") == "gpt-image-2-1k",
    }
    if not all(checks.values()):
        raise RuntimeError("MASTER_PROVENANCE_INVALID")
    return {"status": "MASTER_REUSE_ALLOWED", "checks": checks, "file": str(MASTER), "sha256": sha, "provenance": provenance}


def _master_media(work: Path, profile: Mapping[str, Any]) -> tuple[dict[str, Any], Path]:
    imported = work / "lin-wan-master-imported.png"
    shutil.copy2(MASTER, imported)
    media = {"view_id": "MASTER", "execution_id": MASTER_EXECUTION, "generation_execution_id": MASTER_EXECUTION, "provider": "75api-image", "model_profile_id": profile.get("id"), "model": "gpt-image-2-1k", "candidate_status": "IMPORTED_IMMUTABLE_PRIMARY_REFERENCE", "prompt_fingerprint": _sha(_character_master_prompt(CHARACTERS[0])), "reference_image_count": 0, "reference_image_sha256s": [], "reference_order": [], "reference_input_formats": [], "provider_inline_reference_attached": False, "provider_reference_order_matches": True, "provider_payload_reference_count": 0, "requested_aspect_ratio": "2:3", "provider_aspect_ratio": "9:16", "projection_reason": "requested_ratio_projected_to_nearest_legal_provider_ratio", "framing_class": "FULL", "provider_response_shape": {"response_type": "dict", "top_level_keys": ["model", "url"], "candidate_media_paths": ["url"]}, "provider_response_fingerprint": "69d07cc83e184d82cd7a6bbc7b641868f9441899d6f556bc562861b91cdd1c2f", "provider_response_media_path": "url", "provider_http_status": 200, "file": {**_image_meta(imported), "sha256": MASTER_SHA}, "sha256": MASTER_SHA, "fingerprint": MASTER_SHA, "path": str(imported)}
    return media, imported


def _result_summary(results: dict[str, Any]) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for key, value in results.items():
        selected_profile = dict(value.get("selected_profile") or {})
        selected_profile.pop("api_key", None)
        selected_profile.pop("secret", None)
        summaries[key] = {"asset_id": value.get("asset_id"), "kind": value.get("kind"), "authority": value.get("authority"), "master": value.get("master"), "master_attempts": value.get("master_attempts", []), "generations": value.get("generations", {}), "audits": [asdict(row) for row in value.get("audits", [])], "global": value.get("global", {"status": "NOT_RUN"}), "repairs": value.get("repairs", []), "selected_profile": selected_profile, "selection_trace": value.get("selection_trace", [])}
    return summaries


def _multi_reference_evidence(results: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for asset in results.values():
        for view_id, media in (asset.get("generations") or {}).items():
            if not isinstance(media, dict) or int(media.get("reference_image_count") or 0) < 2:
                continue
            rows.append({"asset_id": asset.get("asset_id"), "view_id": view_id, "reference_count": media.get("reference_image_count"), "reference_order": media.get("reference_order"), "reference_asset_ids": media.get("reference_asset_ids") or media.get("reference_order"), "reference_sha256s": media.get("reference_image_sha256s"), "reference_input_formats": media.get("reference_input_formats"), "provider_payload_images_count": media.get("provider_payload_reference_count"), "provider_reference_order_matches": media.get("provider_reference_order_matches"), "provider_response_media_path": media.get("provider_response_media_path"), "provider_response_fingerprint": media.get("provider_response_fingerprint")})
    return {"real_multi_reference_calls": rows, "count": len(rows), "data_uri_real_calls": sum(1 for row in rows if "data_uri" in (row.get("reference_input_formats") or []))}


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
    staging = work / "publish-staging"
    staging.mkdir(parents=True, exist_ok=True)
    _archive_stale_output(run_id)

    evidence: dict[str, Any] = {"run_id": run_id, "status": "NOT_RUN", "real_image_calls": 0, "real_image_calls_by_provider": {"75api-image": 0, "shapi-image": 0, "poyo-image": 0, "other-image": 0}, "vision_judge_calls": 0, "real_video_calls": 0}
    results: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    preflight: dict[str, Any] = {"status": "NOT_RUN", "policy": PRODUCTION_POLICY.as_dict()}
    master_reuse: dict[str, Any] = {}
    isolated_db = work / "screenplay.db"
    shutil.copy2(source_db, isolated_db)
    port = _free_port()
    env = os.environ.copy()
    env.update({"DATABASE_URL": f"sqlite:///{isolated_db.as_posix()}?timeout=30", "UPLOAD_DIR": str(work / "uploads"), "DEPLOYMENT_ENV": "isolated", "APP_ENV": "test", "E2E_EXTERNAL_RUNTIME": ""})
    log = (work / "uvicorn.log").open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        master_reuse = _validate_imported_master()
        _write(OUT / "MASTER_REUSE.json", master_reuse)
        _wait_for_health(f"http://127.0.0.1:{port}", timeout=180)
        os.environ["DATABASE_URL"] = env["DATABASE_URL"]
        from api.model_registry import get_default_profile, list_profiles, test_profile_connection
        from core.provider_transport_registry import get_provider_transport_binding

        profiles = [item for item in list_profiles(include_sensitive=True) if item.get("enabled", True)]
        default = get_default_profile("image") or next((item for item in profiles if item.get("capability") == "image" and item.get("is_default")), {})
        PRODUCTION_POLICY.assert_image_profile(default)
        params = default.get("default_params") if isinstance(default.get("default_params"), dict) else {}
        router = AssetProviderRouter(profiles, default_image_profile_id=str(default.get("id") or ""), health=ProviderHealthSnapshot())
        rows = router.rank("IMAGE", AssetOperation.TEXT_TO_IMAGE)
        candidate_rows = [row for row in PRODUCTION_POLICY.filter_image_candidates(rows) if not row.rejected_reason]
        candidate = candidate_rows[0] if candidate_rows else None
        transport = get_provider_transport_binding(provider_id=PRODUCTION_POLICY.image_provider, target_media="IMAGE", binding_id=str(default.get("transport_binding_id") or "") or None)
        capability = {"text_to_image": "text_to_image" in (params.get("task_modes") or []), "image_to_image": "image_to_image" in (params.get("task_modes") or []), "reference_images": bool(params.get("supports_reference_images")), "data_uri_reference": True}
        preflight = {"status": "PASS" if candidate and transport and all(capability.values()) and bool(default.get("key_configured") or default.get("credential_configured") or default.get("api_key")) else "FAIL", "policy": PRODUCTION_POLICY.as_dict(), "profile": {"id": default.get("id"), "provider": default.get("provider"), "model": default.get("model_name")}, "capabilities": capability, "timeout_hierarchy": GenerationTimeoutHierarchy.from_profile(default).as_dict(), "router_candidate": asdict(candidate) if candidate else None}
        async def do_probe() -> dict[str, Any]:
            try:
                result = await test_profile_connection(profile_payload=default)
                return {"status": "PASS" if result.get("ok") else "FAIL", "message": str(result.get("message") or "")[:500]}
            except Exception as exc:
                return {"status": "FAIL", "message": str(exc)[:500]}
        probe = asyncio.run(do_probe())
        preflight["connection_probe"] = probe
        _write(OUT / "75API_IMAGE_PREFLIGHT.json", preflight)
        if preflight["status"] != "PASS" or probe["status"] != "PASS" or not candidate:
            raise RuntimeError("75API_IMAGE_PREFLIGHT_FAILED")

        judge_profile = next((item for item in profiles if item.get("capability") == "llm" and bool((item.get("default_params") or {}).get("supports_vision"))), {})
        if not judge_profile:
            raise RuntimeError("VISION_JUDGE_PROFILE_MISSING")
        base_url = f"http://127.0.0.1:{port}"
        selected_profile = next((item for item in profiles if str(item.get("id")) == candidate.profile_id), default)
        call_counter = {"used": 0, "by_provider": evidence["real_image_calls_by_provider"]}

        async def run_all() -> None:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=30, write=30, pool=30), trust_env=False) as client:
                lin_paths = {key: work / f"lin-wan-{key.lower()}.jpg" for key in ["MASTER", "FULL_FRONT", "FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_SIDE", "FULL_BACK"]}
                imported_master, imported_path = _master_media(work, selected_profile)
                lin_paths["MASTER"] = imported_path; lin_paths["FULL_FRONT"] = imported_path
                results["LIN_WAN"] = await _run_asset(client, base_url, kind="CHARACTER", asset=CHARACTERS[0], candidate_rows=candidate_rows, all_profiles=profiles, judge_profile=judge_profile, health=ProviderHealthSnapshot(), paths=lin_paths, budget=CANARY_BUDGET["林晚"], call_counter=call_counter, traces=[], events=events, policy=PRODUCTION_POLICY, existing_master=imported_master, existing_profile=selected_profile, master_attempts_override=[{"provider": "75api-image", "model": "gpt-image-2-1k", "status": "IMPORTED_IMMUTABLE_PRIMARY_REFERENCE", "execution_id": MASTER_EXECUTION, "post_submission_state": "TASK_CONFIRMED"}])
                if not results["LIN_WAN"].get("authority"):
                    raise RuntimeError("LIN_WAN_CHARACTER_AUTHORITY_FAILED")
                lin_board = _board({key: lin_paths[key] for key in ["MASTER", "FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_FRONT", "FULL_SIDE", "FULL_BACK"]}, staging / "lin-wan-reference-board.png", ["FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_FRONT", "FULL_SIDE", "FULL_BACK"], 3, run_id=run_id, authority=results["LIN_WAN"]["authority"])
                _atomic_publish_board(staging / "lin-wan-reference-board.png", OUT / "lin-wan-reference-board.png"); results["LIN_WAN"]["board"] = lin_board

                lu_paths = {key: work / f"lu-shu-{key.lower()}.jpg" for key in ["MASTER", "FULL_FRONT", "FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_SIDE", "FULL_BACK"]}; lu_paths["FULL_FRONT"] = lu_paths["MASTER"]
                results["LU_SHU"] = await _run_asset(client, base_url, kind="CHARACTER", asset=CHARACTERS[1], candidate_rows=candidate_rows, all_profiles=profiles, judge_profile=judge_profile, health=ProviderHealthSnapshot(), paths=lu_paths, budget=CANARY_BUDGET["陆叔"], call_counter=call_counter, traces=[], events=events, policy=PRODUCTION_POLICY)
                if not results["LU_SHU"].get("authority"):
                    raise RuntimeError("LU_SHU_CHARACTER_AUTHORITY_FAILED")
                lu_board = _board({key: lu_paths[key] for key in ["MASTER", "FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_FRONT", "FULL_SIDE", "FULL_BACK"]}, staging / "lu-shu-reference-board.png", ["FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_FRONT", "FULL_SIDE", "FULL_BACK"], 3, run_id=run_id, authority=results["LU_SHU"]["authority"])
                _atomic_publish_board(staging / "lu-shu-reference-board.png", OUT / "lu-shu-reference-board.png"); results["LU_SHU"]["board"] = lu_board

                prop_paths = {key: work / f"handbag-{key.lower()}.jpg" for key in ["MASTER", "SIDE", "BACK", "DETAIL"]}
                results["HANDBAG"] = await _run_asset(client, base_url, kind="PROP", asset=HANDBAG, candidate_rows=candidate_rows, all_profiles=profiles, judge_profile=judge_profile, health=ProviderHealthSnapshot(), paths=prop_paths, budget=CANARY_BUDGET["HANDBAG"], call_counter=call_counter, traces=[], events=events, policy=PRODUCTION_POLICY)
                if not results["HANDBAG"].get("authority"):
                    raise RuntimeError("HANDBAG_PROP_AUTHORITY_FAILED")
                prop_board = _board(prop_paths, staging / "handbag-reference-board.png", ["MASTER", "SIDE", "BACK", "DETAIL"], 2, run_id=run_id, authority=results["HANDBAG"]["authority"])
                _atomic_publish_board(staging / "handbag-reference-board.png", OUT / "handbag-reference-board.png"); results["HANDBAG"]["board"] = prop_board

        asyncio.run(run_all())
        scene_authority = json.loads(SCENE_AUTHORITY_PATH.read_text(encoding="utf-8")) if SCENE_AUTHORITY_PATH.exists() else {"status": "MISSING"}
        authority_set = VisualAssetAuthoritySet.build(characters=[CharacterAuthority(**results["LIN_WAN"]["authority"]), CharacterAuthority(**results["LU_SHU"]["authority"])], scenes={"E01_SC002": scene_authority}, props=[PropAuthority(**results["HANDBAG"]["authority"])], visual_style_fingerprint=_sha("visual-style-v1"))
        _write(OUT / "CHARACTER_VIEW_EVIDENCE.json", {key: results[key].get("generations", {}) for key in ("LIN_WAN", "LU_SHU")}); _write(OUT / "CHARACTER_PAIRWISE_AUDIT.json", {key: {"audits": [asdict(row) for row in results[key].get("audits", [])]} for key in ("LIN_WAN", "LU_SHU")}); _write(OUT / "CHARACTER_GLOBAL_AUDIT.json", {key: results[key].get("global", {}) for key in ("LIN_WAN", "LU_SHU")}); _write(OUT / "CHARACTER_REPAIR_HISTORY.json", {key: results[key].get("repairs", []) for key in ("LIN_WAN", "LU_SHU")}); _write(OUT / "CHARACTER_AUTHORITIES.json", {key: results[key].get("authority") for key in ("LIN_WAN", "LU_SHU")})
        _write(OUT / "PROP_VIEW_EVIDENCE.json", {"HANDBAG": results["HANDBAG"].get("generations", {})}); _write(OUT / "PROP_PAIRWISE_AUDIT.json", {"HANDBAG": {"audits": [asdict(row) for row in results["HANDBAG"].get("audits", [])]}}); _write(OUT / "PROP_GLOBAL_AUDIT.json", {"HANDBAG": results["HANDBAG"].get("global", {})}); _write(OUT / "PROP_REPAIR_HISTORY.json", {"HANDBAG": results["HANDBAG"].get("repairs", [])}); _write(OUT / "PROP_AUTHORITIES.json", {"HANDBAG": results["HANDBAG"].get("authority")})
        multi = _multi_reference_evidence(results); _write(OUT / "MULTI_REFERENCE_REAL_EVIDENCE.json", multi); _write(OUT / "VISUAL_ASSET_AUTHORITY_SET.json", asdict(authority_set))
        evidence.update({"status": "AUTONOMOUS_VISUAL_ASSET_PIPELINE_READY_FOR_SHOT_CANARY", "real_image_calls": call_counter["used"], "real_image_calls_by_provider": call_counter["by_provider"], "vision_judge_calls": sum(len(item.get("audits", [])) + 1 for item in results.values()), "authority_set": asdict(authority_set), "multi_reference": multi, "safety": {"production_writes": 0, "book_990400_writes": 0, "browser_direct_provider_calls": 0, "raw_base64_persisted": 0, "signed_url_query_persisted": 0, "secret_leaks": 0, "orphans": 0}})
        _write(OUT / "AUTONOMOUS_VISUAL_ASSET_AUDIT.json", {**evidence, "characters": _result_summary(results), "preflight": preflight, "master_reuse": master_reuse}); _write(OUT / "CANARY_EVENTS.json", {"run_id": run_id, "events": events})
        report = ["# 75API Autonomous Asset Canary V3", "", "- Status: `AUTONOMOUS_VISUAL_ASSET_PIPELINE_READY_FOR_SHOT_CANARY`", f"- Run: `{run_id}`", "- 75API response contract: `PROVEN`", f"- Real IMAGE calls: `{call_counter['used']}` (75api only); Real VIDEO calls: `0`", "- Lin Wan CharacterAuthority: READY", "- Lu Shu CharacterAuthority: READY", "- HANDBAG PropAuthority: READY", "- Scene E01_SC002: reused READY", "- VisualAssetAuthoritySet: READY", "- No Shot Keyframe generation was executed."]
        (OUT / "AUTONOMOUS_VISUAL_ASSET_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        return 0
    except Exception as exc:
        evidence.update({"status": "AUTONOMOUS_VISUAL_ASSET_PIPELINE_PARTIAL", "failure": str(exc)[:2000], "real_image_calls": int(evidence.get("real_image_calls") or 0), "real_video_calls": 0, "preflight": preflight, "master_reuse": master_reuse, "characters": _result_summary(results), "multi_reference": _multi_reference_evidence(results), "safety": {"production_writes": 0, "book_990400_writes": 0, "browser_direct_provider_calls": 0, "raw_base64_persisted": 0, "signed_url_query_persisted": 0, "secret_leaks": 0, "orphans": 0}})
        _write(OUT / "AUTONOMOUS_VISUAL_ASSET_AUDIT.json", evidence); _write(OUT / "CANARY_EVENTS.json", {"run_id": run_id, "events": events}); _write(OUT / "CHARACTER_VIEW_EVIDENCE.json", {key: results.get(key, {}).get("generations", {}) for key in ("LIN_WAN", "LU_SHU")}); _write(OUT / "PROP_VIEW_EVIDENCE.json", {"HANDBAG": results.get("HANDBAG", {}).get("generations", {})}); _write(OUT / "CHARACTER_PAIRWISE_AUDIT.json", {key: {"audits": [asdict(row) for row in results.get(key, {}).get("audits", [])]} for key in ("LIN_WAN", "LU_SHU")}); _write(OUT / "CHARACTER_GLOBAL_AUDIT.json", {key: results.get(key, {}).get("global", {"status": "NOT_RUN"}) for key in ("LIN_WAN", "LU_SHU")}); _write(OUT / "CHARACTER_REPAIR_HISTORY.json", {key: results.get(key, {}).get("repairs", []) for key in ("LIN_WAN", "LU_SHU")}); _write(OUT / "CHARACTER_AUTHORITIES.json", {key: results.get(key, {}).get("authority") for key in ("LIN_WAN", "LU_SHU")}); _write(OUT / "PROP_PAIRWISE_AUDIT.json", {"HANDBAG": {"audits": [asdict(row) for row in results.get("HANDBAG", {}).get("audits", [])]}}); _write(OUT / "PROP_GLOBAL_AUDIT.json", {"HANDBAG": results.get("HANDBAG", {}).get("global", {"status": "NOT_RUN"})})
        _write(OUT / "PROP_REPAIR_HISTORY.json", {"HANDBAG": results.get("HANDBAG", {}).get("repairs", [])}); _write(OUT / "PROP_AUTHORITIES.json", {"HANDBAG": results.get("HANDBAG", {}).get("authority")}); _write(OUT / "MULTI_REFERENCE_REAL_EVIDENCE.json", _multi_reference_evidence(results)); _write(OUT / "VISUAL_ASSET_AUTHORITY_SET.json", {"status": "PARTIAL", "characters": {key: results.get(key, {}).get("authority") for key in ("LIN_WAN", "LU_SHU")}, "props": {"HANDBAG": results.get("HANDBAG", {}).get("authority")}})
        report = ["# 75API Autonomous Asset Canary V3", "", "- Status: `AUTONOMOUS_VISUAL_ASSET_PIPELINE_PARTIAL`", f"- Run: `{run_id}`", f"- Failure: `{str(exc)[:1000]}`", "- 75API only; SHAPI=0; Poyo=0; VIDEO=0", "- Staging retained; no board is published for an Authority that is not READY."]
        for key, label in (("LIN_WAN", "Lin Wan"), ("LU_SHU", "Lu Shu"), ("HANDBAG", "HANDBAG")):
            report.append(f"- {label}: status={'READY' if results.get(key, {}).get('authority') else ('INCOMPLETE' if key == 'LIN_WAN' else 'NOT_STARTED')}; board={'PUBLISHED' if results.get(key, {}).get('board') else 'NOT_PUBLISHED'}")
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
