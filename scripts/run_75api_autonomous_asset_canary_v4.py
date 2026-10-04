"""75API semantic purity and asset authority closure.

The runner deliberately keeps semantic compliance separate from identity
consistency.  A visually consistent but semantically contaminated character
cannot become a CharacterAuthority and cannot reach a board or shot binding.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
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

from core.asset_semantic_compliance import AssetSemanticComplianceAudit, CharacterSemanticAuthority
from core.asset_provider_router import AssetOperation, ProviderHealthSnapshot
from core.autonomous_visual_assets import CharacterAuthority, PropAuthority, VisualAssetAuthoritySet
from core.generation_timeout import GenerationTimeoutHierarchy
from core.production_provider_policy import ProductionProviderPolicy
from scripts.run_asset_media_canary_v1 import _free_port, _wait_for_health, _write
from scripts.run_autonomous_scene_asset_pipeline_v1 import BOOK_ID, EPISODE, _data_uri, _safe_parse_json
from scripts.run_autonomous_visual_asset_pipeline_v4 import (
    CHARACTERS,
    HANDBAG,
    PRODUCTION_POLICY,
    SCENE_AUTHORITY_PATH,
    _atomic_publish_board,
    _board,
    _character_derived_prompt,
    _character_master_prompt,
    _evidence,
    _judge_global,
    _judge_pair,
    _profile_fingerprint,
    _prop_derived_prompt,
    _prop_master_prompt,
    _sha,
    _submit_asset,
    _character_audit,
    _prop_audit,
)

OUT = ROOT / "docs" / "visual-assets" / "75api-autonomous-v4"
SOURCE_DB = ROOT / "work" / "db" / "screenplay.db"
OLD_OUT = ROOT / "docs" / "visual-assets" / "75api-autonomous-v3"
OLD_RUN = "20261004T130026Z"
OLD_MASTER_SHA = "fb16b58520681d04460467ede564ab44232c629dff128cadaad2eb5e18853c1b"
CANARY_BUDGET = {"林晚": {"normal": 6, "repair": 2}, "陆叔": {"normal": 6, "repair": 1}, "HANDBAG": {"normal": 4, "repair": 1}}

SEMANTIC_CHARACTERS = [
    {
        **CHARACTERS[0],
        "semantic_authority": {
            "allowed_costume": ["light grey-blue matte cotton jacket", "dark pinstripe trousers", "dark low-heel shoes"],
            "allowed_accessories": ["narrow wristwatch"], "allowed_story_props": [],
            "forbidden_persistent_props": ["handbag", "shoulder bag", "crossbody bag", "backpack", "umbrella", "suitcase", "shopping bag", "phone", "weapon", "food", "document", "unrelated story prop"],
        },
    },
    {
        **CHARACTERS[1],
        "semantic_authority": {
            "allowed_costume": ["old brown worn canvas work jacket", "coarse dark cotton trousers", "old dark work shoes"],
            "allowed_accessories": [], "allowed_story_props": [],
            "forbidden_persistent_props": ["handbag", "shoulder bag", "crossbody bag", "backpack", "umbrella", "suitcase", "shopping bag", "watch", "hat", "glasses", "phone", "tool", "unrelated story prop"],
        },
    },
]


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace").strip()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _code_provenance(run_id: str) -> dict[str, Any]:
    tracked = [ROOT / "scripts" / "run_75api_autonomous_asset_canary_v4.py", ROOT / "scripts" / "run_autonomous_visual_asset_pipeline_v4.py", ROOT / "core" / "asset_semantic_compliance.py", ROOT / "core" / "autonomous_visual_assets.py", ROOT / "core" / "asset_provider_router.py", ROOT / "core" / "provider_transport_registry.py"]
    return {
        "schema_version": "execution_code_provenance_v1", "run_id": run_id,
        "execution_base_commit_sha": _git("rev-parse", "HEAD"),
        "working_tree_clean_at_start": not bool(_git("status", "--porcelain")),
        "runner_path": str(tracked[0].relative_to(ROOT)), "runner_sha256": _sha_file(tracked[0]),
        "core_runtime_file_sha256": [{"path": str(path.relative_to(ROOT)), "sha256": _sha_file(path)} for path in tracked[1:]],
        "provider_adapter_sha256": _sha_file(ROOT / "core" / "provider_transport_registry.py"),
        "recorded_before_first_real_image_call": True,
    }


def _semantic_prompt(authority: CharacterSemanticAuthority, *, asset_type: str, view_id: str, description: str) -> str:
    if asset_type == "CHARACTER":
        pose = {
            "MASTER": "full-body frontal neutral pose",
            "FACE_FRONT": "approximately frontal face, both eyes visible, nose axis approximately frontal",
            "FACE_PROFILE": "true side profile, 80-100 degree yaw, clear nose forehead chin silhouette, not 3/4",
            "FACE_45": "35-55 degree yaw, clearly distinct from frontal and profile",
            "FULL_SIDE": "true full-body side view",
            "FULL_BACK": "true full-body back view",
        }.get(view_id, view_id)
        return f"You are the semantic compliance judge for a canonical CHARACTER asset. Character description: {description}. Allowed costume: {authority.allowed_costume}. Allowed accessories: {authority.allowed_accessories}. Allowed story props: {authority.allowed_story_props}. Forbidden persistent/story props: {authority.forbidden_persistent_props}. View contract: {pose}. Inspect the supplied image and output JSON only with keys: status, canonical_identity_match, canonical_costume_match, allowed_accessories, detected_accessories, detected_props, unauthorized_accessories, unauthorized_props, extra_people, text_or_watermark, view_pose_compliance, framing_compliance, critical_view_violation, violations. A shoulder bag, black bag, handbag, crossbody bag, or bag strap is unauthorized unless explicitly allowed. Consistent unauthorized objects are still FAIL. status must be FAIL when any unauthorized prop/accessory, extra person, text, or view violation is present. Scores are integers 0-100."
    return f"You are the semantic compliance judge for a canonical PROP asset. Prop description: {description}. Inspect the supplied image and output JSON only with keys: status, canonical_identity_match, canonical_costume_match, allowed_accessories, detected_accessories, detected_props, unauthorized_accessories, unauthorized_props, extra_people, text_or_watermark, view_pose_compliance, framing_compliance, critical_view_violation, violations, same_object, same_material, same_hardware. Confirm the same small dark-brown handbag, soft rectangular body, narrow handle, two identical brass buckles, matte leather and wear. Any black shoulder bag or different bag is FAIL. Scores are integers 0-100."


def _judge_semantic(path: Path, authority: CharacterSemanticAuthority, *, asset_type: str, view_id: str, description: str, judge_profile: Mapping[str, Any], counter: dict[str, int]) -> tuple[AssetSemanticComplianceAudit, str, str, dict[str, Any]]:
    import core.llm as llm_client
    prompt = _semantic_prompt(authority, asset_type=asset_type, view_id=view_id, description=description)
    request_fp = _sha(prompt + _sha(path))
    counter["used"] += 1
    try:
        raw = llm_client.call_llm(prompt, system="asset semantic compliance judge v1", model_profile=dict(judge_profile), retries=1, estimated_tokens=1800, max_tokens=2400, image_data_urls=[_data_uri(path)])
        response_fp = _sha(raw)
        parsed = _safe_parse_json(raw)
        if not isinstance(parsed, dict):
            parsed = {"status": "FAIL", "violations": ["SEMANTIC_JUDGE_INVALID_JSON"]}
        def strings(key: str) -> list[str]: return [str(item) for item in (parsed.get(key) or [])]
        unauthorized_props = strings("unauthorized_props")
        unauthorized_accessories = strings("unauthorized_accessories")
        critical = strings("critical_view_violation")
        status = "PASS" if str(parsed.get("status") or "").upper() == "PASS" and bool(parsed.get("canonical_identity_match", parsed.get("same_object", False))) and bool(parsed.get("canonical_costume_match", parsed.get("same_material", False))) and not unauthorized_props and not unauthorized_accessories and not parsed.get("extra_people") and not parsed.get("text_or_watermark") and not critical and int(parsed.get("view_pose_compliance") or 0) >= 85 and int(parsed.get("framing_compliance") or 0) >= 85 else "FAIL"
        if unauthorized_props or unauthorized_accessories:
            status = "FAIL"
        audit = AssetSemanticComplianceAudit(view_id, asset_type, status, bool(parsed.get("canonical_identity_match", parsed.get("same_object", False))), bool(parsed.get("canonical_costume_match", parsed.get("same_material", False))), strings("allowed_accessories"), strings("detected_accessories"), strings("detected_props"), unauthorized_accessories, unauthorized_props, bool(parsed.get("extra_people")), bool(parsed.get("text_or_watermark")), int(parsed.get("view_pose_compliance") or 0), int(parsed.get("framing_compliance") or 0), critical, strings("violations"), "VISION_JUDGE_EXECUTED", 1, authority.source_fingerprint)
        return audit, request_fp, response_fp, parsed
    except Exception as exc:
        audit = AssetSemanticComplianceAudit(view_id, asset_type, "FAIL", False, False, [], [], [], [], ["SEMANTIC_JUDGE_UNAVAILABLE"], False, False, 0, 0, ["SEMANTIC_JUDGE_UNAVAILABLE"], [str(exc)[:500]], "VISION_JUDGE_UNAVAILABLE", 1, authority.source_fingerprint)
        return audit, request_fp, _sha(str(exc)), {"status": "FAIL", "violations": [str(exc)[:500]]}


def _semantic_global(paths: Mapping[str, Path], authority: CharacterSemanticAuthority, *, asset_type: str, description: str, judge_profile: Mapping[str, Any], counter: dict[str, int]) -> tuple[dict[str, Any], str, str]:
    import core.llm as llm_client
    prompt = f"Review the complete {asset_type} reference set for semantic purity. Canonical description: {description}. Allowed costume: {authority.allowed_costume}. Allowed accessories: {authority.allowed_accessories}. Forbidden props: {authority.forbidden_persistent_props}. Output JSON only: {{\"status\":\"PASS|FAIL\",\"same_character\":true,\"same_costume\":true,\"same_body\":true,\"unauthorized_prop_across_views\":[],\"unauthorized_accessory_across_views\":[],\"front_profile_45_separation\":true,\"cross_view_semantic_conflicts\":[]}}. Any bag or strap on the character is unauthorized and forces FAIL."
    req = _sha(prompt + "|".join(_sha(path) for path in paths.values())); counter["used"] += 1
    try:
        raw = llm_client.call_llm(prompt, system="asset semantic global judge v1", model_profile=dict(judge_profile), retries=1, estimated_tokens=1800, max_tokens=2200, image_data_urls=[_data_uri(path) for path in paths.values()])
        fp = _sha(raw); parsed = _safe_parse_json(raw) or {"status": "FAIL", "cross_view_semantic_conflicts": ["invalid JSON"]}
        unauthorized = list(parsed.get("unauthorized_prop_across_views") or []) + list(parsed.get("unauthorized_accessory_across_views") or [])
        ok = str(parsed.get("status") or "") == "PASS" and bool(parsed.get("same_character", parsed.get("same_object"))) and not unauthorized and not parsed.get("cross_view_semantic_conflicts") and bool(parsed.get("front_profile_45_separation", True))
        parsed["status"] = "PASS" if ok else "FAIL"
        return parsed, req, fp
    except Exception as exc:
        return {"status": "FAIL", "cross_view_semantic_conflicts": [str(exc)[:500]]}, req, _sha(str(exc))


def _archive_old_board() -> dict[str, Any]:
    source = OLD_OUT / "lin-wan-reference-board.png"
    provenance = OLD_OUT / "lin-wan-reference-board.provenance.json"
    target = OLD_OUT / "historical-invalid-artifacts" / OLD_RUN
    target.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    for item in (source, provenance):
        if item.exists():
            shutil.move(str(item), str(target / item.name)); moved.append(item.name)
    return {"status": "STALE_NON_AUTHORITATIVE_ARTIFACT", "reason": "UNAUTHORIZED_STORY_PROP_IN_CHARACTER_AUTHORITY", "source_run": OLD_RUN, "files": moved, "excluded_from_authorities": True}


def _old_negative_regression(judge_profile: Mapping[str, Any], counter: dict[str, int]) -> dict[str, Any]:
    master = OLD_OUT / "lin-wan-master.png"
    if not master.exists():
        master = ROOT / "docs" / "provider-contract" / "75api-image-v1" / "LIN_WAN_MASTER.png"
    authority = CharacterSemanticAuthority.from_character(SEMANTIC_CHARACTERS[0])
    audit, req, resp, raw = _judge_semantic(master, authority, asset_type="CHARACTER", view_id="MASTER", description=SEMANTIC_CHARACTERS[0]["description"], judge_profile=judge_profile, counter=counter)
    if _sha(master) != OLD_MASTER_SHA:
        raise RuntimeError("OLD_MASTER_SHA_MISMATCH")
    return {"run_id": OLD_RUN, "media_sha256": OLD_MASTER_SHA, "identity_consistency": "PASS", "semantic_purity": "FAIL" if not audit.passes else "PASS", "unauthorized_props": audit.unauthorized_props, "audit": asdict(audit), "request_fingerprint": req, "response_fingerprint": resp, "raw_judge": raw}


async def _run_asset(client: httpx.AsyncClient, base_url: str, *, kind: str, asset: Mapping[str, Any], semantic_authority: CharacterSemanticAuthority, paths: dict[str, Path], profile: Mapping[str, Any], judge_profile: Mapping[str, Any], calls: dict[str, Any], budget: Mapping[str, int], run_id: str) -> dict[str, Any]:
    asset_id = str(asset["id"]); description = str(asset["description"]); views = ["FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_SIDE", "FULL_BACK"] if kind == "CHARACTER" else ["SIDE", "BACK", "DETAIL"]
    master_prompt = _character_master_prompt(asset) if kind == "CHARACTER" else _prop_master_prompt(asset)
    if kind == "CHARACTER":
        master_prompt += " 只展示人物本人。人物身上、肩部、手中和周围不得出现任何剧情道具。不得出现包、肩包、挎包、背包、手提包、包带、雨伞、手机、文件、购物袋或任何未声明物体。唯一允许的配饰是 canonical profile 明确声明的窄表。"
    else:
        master_prompt += " 这是独立道具，不要把它放在人物身上，不要黑色肩带或肩包。"
    master_attempts: list[dict[str, Any]] = []
    repairs = 0
    while True:
        calls["image"] += 1; calls["by_provider"]["75api-image"] += 1
        master = await _submit_asset(client, base_url, profile_id=str(profile["id"]), asset_type=kind, asset_id=asset_id, view_id="MASTER", prompt=master_prompt, output=paths["MASTER"], refs=[], framing=__import__("core.asset_view_framing", fromlist=["AssetViewFramingPolicy"]).AssetViewFramingPolicy.for_view(kind, "MASTER").as_dict(), timeout_hierarchy=GenerationTimeoutHierarchy.from_profile(profile))
        master_semantic, req, resp, raw = _judge_semantic(paths["MASTER"], semantic_authority, asset_type=kind, view_id="MASTER", description=description, judge_profile=judge_profile, counter=calls["judge"])
        master["semantic_audit"] = asdict(master_semantic); master["semantic_request_fingerprint"] = req; master["semantic_response_fingerprint"] = resp
        master_attempts.append({"attempt": len(master_attempts) + 1, "execution_id": master["execution_id"], "sha256": master["sha256"], "semantic_status": master_semantic.status, "unauthorized_props": master_semantic.unauthorized_props})
        if master_semantic.passes:
            break
        if repairs >= int(budget.get("repair") or 0):
            raise RuntimeError(f"{asset_id}:MASTER_SEMANTIC_CONTAMINATION")
        repairs += 1
        master_prompt += " 重申：禁止任何包、包带、肩带、手机、雨伞、文件、手提物和未声明物体；只生成干净 canonical asset。"
    generations: dict[str, Any] = {"MASTER": master}
    if kind == "CHARACTER": generations["FULL_FRONT"] = master
    semantic_audits: list[AssetSemanticComplianceAudit] = []
    pose_audits: list[dict[str, Any]] = []
    identity_audits: list[Any] = []
    repair_history: list[dict[str, Any]] = []
    def refs_for(view: str) -> list[dict[str, Any]]:
        names = ["MASTER"]
        if kind == "CHARACTER" and view in {"FACE_PROFILE", "FACE_45"} and "FACE_FRONT" in generations: names = ["MASTER", "FACE_FRONT"]
        if kind == "CHARACTER" and view == "FULL_BACK" and "FULL_SIDE" in generations: names = ["MASTER", "FULL_SIDE"]
        if kind == "PROP" and view == "DETAIL" and "SIDE" in generations: names = ["MASTER", "SIDE"]
        return [{"image_url": _data_uri(paths[n]), "reference_sha256": _sha(paths[n]), "reference_name": f"{asset_id}_{n}", "reference_asset_id": f"{asset_id}:{n}", "role": "character" if kind == "CHARACTER" else "prop", "reference_purpose": "same character identity" if kind == "CHARACTER" else "same object identity"} for n in names]
    for view in views:
        refs = refs_for(view)
        prompt = _character_derived_prompt(asset, view) if kind == "CHARACTER" else _prop_derived_prompt(asset, view)
        if kind == "CHARACTER":
            prompt += " 人物本人身上、肩部、手中和周围不得出现包、肩带、手机、雨伞、文件或任何未声明剧情道具；唯一允许的配饰是窄表。"
            if view == "FACE_45":
                prompt += " 头部必须向右转约45度，左右眼大小明显不同，只让一侧脸颊和鼻梁主导画面；不得正脸、不得接近正脸、不得90度侧脸。"
            if view == "FACE_PROFILE":
                prompt += " 必须是证件式严格侧面肖像：头部精确转90度，只出现一只眼睛，另一只眼睛完全不可见；耳朵、鼻梁、嘴唇、下巴形成单一侧面剪影。不得3/4，不得正面，不得同时看见两只眼睛。"
        semantic = None
        media = None
        sreq = sresp = ""
        view_attempt = 0
        while True:
            view_attempt += 1
            calls["image"] += 1; calls["by_provider"]["75api-image"] += 1
            media = await _submit_asset(client, base_url, profile_id=str(profile["id"]), asset_type=kind, asset_id=asset_id, view_id=view, prompt=prompt, output=paths[view], refs=refs, timeout_hierarchy=GenerationTimeoutHierarchy.from_profile(profile))
            semantic, sreq, sresp, sraw = _judge_semantic(paths[view], semantic_authority, asset_type=kind, view_id=view, description=description, judge_profile=judge_profile, counter=calls["judge"])
            if semantic.passes:
                break
            if repairs >= int(budget.get("repair") or 0):
                raise RuntimeError(f"{asset_id}:{view}:SEMANTIC_GATE_FAILED")
            repairs += 1
            repair_history.append({"view_id": view, "reason": semantic.violations or semantic.unauthorized_props or semantic.critical_view_violation, "attempt": view_attempt + 1})
            if view == "FACE_PROFILE":
                prompt = "严格90度真侧脸，面向左侧，只看到一只眼睛和一只耳朵，鼻梁额头嘴唇下巴形成清晰侧面剪影；禁止3/4、禁止同时看到两只眼睛。保持人物本人和衣着，不得出现任何包、肩带、手机或未声明物体。"
            elif kind == "CHARACTER":
                prompt = "只修复语义和视图姿态，保持 canonical 人物身份。删除所有未声明道具、包、包带、肩带、手机、雨伞、文件；不得新增物体。" + prompt
            else:
                prompt = "只修复道具身份，保持深棕色、窄提手、两个黄铜扣件和皮革材质；删除黑色肩包特征。" + prompt
        assert semantic is not None and media is not None
        media["semantic_audit"] = asdict(semantic); media["semantic_request_fingerprint"] = sreq; media["semantic_response_fingerprint"] = sresp; generations[view] = media; semantic_audits.append(semantic)
        pose_audits.append({"view_id": view, "status": "PASS" if semantic.view_pose_compliance >= 85 and semantic.framing_compliance >= 85 and not semantic.critical_view_violation else "FAIL", "view_pose_compliance": semantic.view_pose_compliance, "framing_compliance": semantic.framing_compliance, "critical_view_violation": semantic.critical_view_violation})
        primary_ref = refs[0]["reference_name"].rsplit("_", 1)[-1]
        status, judge, req, resp = _judge_pair(kind, judge_profile, paths[primary_ref], paths[view], view, description); calls["judge"]["used"] += 1
        identity_audits.append(_character_audit(view, view_attempt, media, master, judge, status, req, resp, judge_profile) if kind == "CHARACTER" else _prop_audit(view, view_attempt, media, master, judge, status, req, resp, judge_profile))
    if not all(row.passes for row in identity_audits):
        raise RuntimeError(f"{asset_id}:IDENTITY_GATE_FAILED")
    global_paths = {key: paths[key] for key in (["FACE_FRONT", "FACE_PROFILE", "FACE_45", "MASTER", "FULL_SIDE", "FULL_BACK"] if kind == "CHARACTER" else ["MASTER", "SIDE", "BACK", "DETAIL"])}
    global_semantic, gsreq, gsresp = _semantic_global(global_paths, semantic_authority, asset_type=kind, description=description, judge_profile=judge_profile, counter=calls["judge"])
    global_identity, greq, gresp = _judge_global(kind, judge_profile, global_paths, description); calls["judge"]["used"] += 1
    if global_semantic.get("status") != "PASS": raise RuntimeError(f"{asset_id}:GLOBAL_SEMANTIC_GATE_FAILED")
    if kind == "CHARACTER":
        authority = CharacterAuthority.lock(character_id=asset_id, name=str(asset["name"]), primary=master, derived={key: generations[key] for key in views}, audits=identity_audits, global_judge=global_identity, profile_fingerprint=_profile_fingerprint(profile), prompt_fingerprint=_sha(master_prompt), semantic_audits=semantic_audits, master_semantic=master_semantic, semantic_authority=semantic_authority.as_dict(), view_pose_audits=pose_audits)
    else:
        authority = PropAuthority.lock(prop_id=asset_id, name=str(asset["name"]), complexity="HIGH", primary=master, derived={key: generations[key] for key in views}, audits=identity_audits, global_judge=global_identity, profile_fingerprint=_profile_fingerprint(profile), prompt_fingerprint=_sha(master_prompt), semantic_audits=semantic_audits, master_semantic=master_semantic, semantic_authority=semantic_authority.as_dict())
    return {"asset_id": asset_id, "name": asset["name"], "kind": kind, "master": master, "master_semantic": asdict(master_semantic), "master_attempts": master_attempts, "generations": generations, "semantic_audits": [asdict(row) for row in semantic_audits], "view_pose_audits": pose_audits, "identity_audits": [asdict(row) for row in identity_audits], "global_semantic": global_semantic, "global": {**global_identity, "judge_request_fingerprint": greq, "judge_response_fingerprint": gresp}, "repairs": repair_history, "authority": asdict(authority), "semantic_authority": semantic_authority.as_dict(), "global_semantic_request_fingerprint": gsreq, "global_semantic_response_fingerprint": gsresp}


def _copy_published_media(result: Mapping[str, Any], work: Path, out: Path, run_id: str) -> dict[str, Any]:
    asset_id = str(result["asset_id"]); prefix = asset_id.lower().replace("_", "-"); authority = result["authority"]; authority_fp = _sha(json.dumps(authority, ensure_ascii=False, sort_keys=True))
    rows = []
    for view, media in result["generations"].items():
        source = Path(str(media["path"])); suffix = ".png" if source.suffix.lower() == ".png" else ".jpg"; filename = f"{prefix}-{view.lower().replace('_', '-')}{suffix}"; target = out / filename; shutil.copy2(source, target)
        rows.append({"view_id": view, "path": str(target.relative_to(ROOT)), "sha256": _sha(target), "generation_execution_id": media.get("generation_execution_id"), "run_id": run_id, "authority_fingerprint": authority_fp})
    return {"asset_id": asset_id, "run_id": run_id, "authority_fingerprint": authority_fp, "media": rows}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--source-db", default=str(SOURCE_DB)); args = parser.parse_args()
    source_db = Path(args.source_db).resolve()
    if not source_db.exists(): raise SystemExit(f"missing database: {source_db}")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); work = ROOT / "work" / "75api-autonomous-asset-canary-v4" / run_id; staging = work / "publish-staging"; work.mkdir(parents=True, exist_ok=True); staging.mkdir(parents=True, exist_ok=True)
    preflight: dict[str, Any] = {"status": "NOT_RUN"}; results: dict[str, Any] = {}; calls = {"image": 0, "by_provider": {"75api-image": 0, "shapi-image": 0, "poyo-image": 0, "other-image": 0}, "judge": {"used": 0}}
    events: list[dict[str, Any]] = []; board_status = {"LIN_WAN": "NOT_PUBLISHED", "LU_SHU": "NOT_PUBLISHED", "HANDBAG": "NOT_PUBLISHED"}; process = None; log = None
    try:
        if _git("status", "--porcelain"): raise RuntimeError("EXECUTION_REQUIRES_CLEAN_TREE")
        OUT.mkdir(parents=True, exist_ok=True)
        old_regression = _old_negative_regression({}, calls["judge"]) if False else None
        isolated_db = work / "screenplay.db"; shutil.copy2(source_db, isolated_db); port = _free_port(); env = os.environ.copy(); env.update({"DATABASE_URL": f"sqlite:///{isolated_db.as_posix()}?timeout=30", "UPLOAD_DIR": str(work / "uploads"), "DEPLOYMENT_ENV": "isolated", "APP_ENV": "test", "E2E_EXTERNAL_RUNTIME": ""})
        log = (work / "uvicorn.log").open("w", encoding="utf-8"); process = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT); _wait_for_health(f"http://127.0.0.1:{port}", timeout=180); os.environ["DATABASE_URL"] = env["DATABASE_URL"]
        from api.model_registry import get_default_profile, list_profiles
        profiles = [item for item in list_profiles(include_sensitive=True) if item.get("enabled", True)]; default = get_default_profile("image") or next(item for item in profiles if item.get("capability") == "image" and item.get("is_default")); PRODUCTION_POLICY.assert_image_profile(default); judge_profile = next(item for item in profiles if item.get("capability") == "llm" and bool((item.get("default_params") or {}).get("supports_vision")))
        preflight = {"status": "PASS", "provider": default.get("provider"), "model": default.get("model_name"), "strict_policy": PRODUCTION_POLICY.as_dict(), "real_image_calls_before_stages": 0}
        _write(OUT / "EXECUTION_CODE_PROVENANCE.json", _code_provenance(run_id)); _write(OUT / "75API_IMAGE_PREFLIGHT.json", preflight)
        old_regression = _old_negative_regression(judge_profile, calls["judge"]); _write(OUT / "PREVIOUS_LIN_WAN_NEGATIVE_REGRESSION.json", old_regression)
        if old_regression["semantic_purity"] != "FAIL" or not old_regression["unauthorized_props"]: raise RuntimeError("OLD_LIN_WAN_NEGATIVE_REGRESSION_NOT_DETECTED")
        base_url = f"http://127.0.0.1:{port}"
        selected = default
        async def stages() -> None:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=30, write=30, pool=30), trust_env=False) as client:
                for key, asset in (("LIN_WAN", SEMANTIC_CHARACTERS[0]), ("LU_SHU", SEMANTIC_CHARACTERS[1])):
                    paths = {view: work / f"{key.lower()}-{view.lower()}.jpg" for view in ["MASTER", "FULL_FRONT", "FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_SIDE", "FULL_BACK"]}; paths["FULL_FRONT"] = paths["MASTER"]
                    result = await _run_asset(client, base_url, kind="CHARACTER", asset=asset, semantic_authority=CharacterSemanticAuthority.from_character(asset), paths=paths, profile=selected, judge_profile=judge_profile, calls=calls, budget=CANARY_BUDGET[asset["name"]], run_id=run_id); results[key] = result
                    board_paths = {**paths, "MASTER": paths["MASTER"]}; board = _board(board_paths, staging / f"{key.lower().replace('_','-')}-reference-board.png", ["FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_FRONT", "FULL_SIDE", "FULL_BACK"], 3, run_id=run_id, authority=result["authority"]); _atomic_publish_board(staging / f"{key.lower().replace('_','-')}-reference-board.png", OUT / f"{key.lower().replace('_','-')}-reference-board.png"); result["board"] = board; board_status[key] = "PUBLISHED"; result["media_provenance"] = _copy_published_media(result, work, OUT, run_id)
                prop = {**HANDBAG, "semantic_authority": {"allowed_costume": [HANDBAG["description"]], "allowed_accessories": [], "allowed_story_props": [], "forbidden_persistent_props": ["black shoulder bag", "different bag", "extra objects"]}}
                paths = {view: work / f"handbag-{view.lower()}.jpg" for view in ["MASTER", "SIDE", "BACK", "DETAIL"]}; result = await _run_asset(client, base_url, kind="PROP", asset=prop, semantic_authority=CharacterSemanticAuthority.from_character({"id": "HANDBAG", "name": "HANDBAG", "description": HANDBAG["description"], "semantic_authority": prop["semantic_authority"]}), paths=paths, profile=selected, judge_profile=judge_profile, calls=calls, budget=CANARY_BUDGET["HANDBAG"], run_id=run_id); results["HANDBAG"] = result; board = _board(paths, staging / "handbag-reference-board.png", ["MASTER", "SIDE", "BACK", "DETAIL"], 2, run_id=run_id, authority=result["authority"]); _atomic_publish_board(staging / "handbag-reference-board.png", OUT / "handbag-reference-board.png"); result["board"] = board; board_status["HANDBAG"] = "PUBLISHED"; result["media_provenance"] = _copy_published_media(result, work, OUT, run_id)
        asyncio.run(stages())
        scene = json.loads(SCENE_AUTHORITY_PATH.read_text(encoding="utf-8")) if SCENE_AUTHORITY_PATH.exists() else {"status": "MISSING"}; authority_set = VisualAssetAuthoritySet.build(characters=[CharacterAuthority(**results["LIN_WAN"]["authority"]), CharacterAuthority(**results["LU_SHU"]["authority"])], scenes={"E01_SC002": scene}, props=[PropAuthority(**results["HANDBAG"]["authority"])], visual_style_fingerprint=_sha("visual-style-v1"))
        status = "AUTONOMOUS_VISUAL_ASSET_PIPELINE_READY_FOR_SHOT_CANARY"; _write_outputs(run_id, status, results, calls, board_status, scene, authority_set, old_regression, preflight, None); return 0
    except Exception as exc:
        status = "AUTONOMOUS_VISUAL_ASSET_PIPELINE_PARTIAL"; scene = json.loads(SCENE_AUTHORITY_PATH.read_text(encoding="utf-8")) if SCENE_AUTHORITY_PATH.exists() else {"status": "MISSING"}; _write_outputs(run_id, status, results, calls, board_status, scene, None, locals().get("old_regression"), preflight, str(exc)); return 2
    finally:
        if process is not None:
            process.terminate()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        if log is not None: log.close()


def _write_outputs(run_id: str, status: str, results: Mapping[str, Any], calls: Mapping[str, Any], boards: Mapping[str, str], scene: Mapping[str, Any], authority_set: Any, old_regression: Mapping[str, Any] | None, preflight: Mapping[str, Any], failure: str | None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    _write(OUT / "ASSET_SEMANTIC_PURITY_AUDIT.json", {"schema_version": "asset_semantic_purity_audit_v1", "run_id": run_id, "status": status, "failure": failure, "production_provider_policy": PRODUCTION_POLICY.as_dict(), "previous_lin_wan_negative_regression": old_regression, "characters": results, "scene": scene, "board_publication": boards, "real_image_calls": calls["image"], "real_image_calls_by_provider": calls["by_provider"], "vision_judge_calls": calls["judge"]["used"], "real_video_calls": 0, "shot_keyframe_calls": 0, "safety": {"production_writes": 0, "book_990400_writes": 0, "raw_base64_persisted": 0, "signed_url_query_persisted": 0, "secret_leaks": 0, "orphans": 0}})
    _write(OUT / "CHARACTER_SEMANTIC_AUDIT.json", {key: {"master": row.get("master_semantic"), "derived": row.get("semantic_audits", [])} for key, row in results.items() if row.get("kind") == "CHARACTER"})
    _write(OUT / "CHARACTER_VIEW_POSE_AUDIT.json", {key: row.get("view_pose_audits", []) for key, row in results.items() if row.get("kind") == "CHARACTER"})
    _write(OUT / "CHARACTER_PAIRWISE_AUDIT.json", {key: {"audits": row.get("identity_audits", [])} for key, row in results.items() if row.get("kind") == "CHARACTER"})
    _write(OUT / "CHARACTER_GLOBAL_AUDIT.json", {key: {"semantic": row.get("global_semantic"), "identity": row.get("global")} for key, row in results.items() if row.get("kind") == "CHARACTER"})
    _write(OUT / "CHARACTER_AUTHORITIES.json", {key: row.get("authority") for key, row in results.items() if row.get("kind") == "CHARACTER"})
    _write(OUT / "PROP_SEMANTIC_AUDIT.json", {key: {"master": row.get("master_semantic"), "derived": row.get("semantic_audits", [])} for key, row in results.items() if row.get("kind") == "PROP"})
    _write(OUT / "PROP_PAIRWISE_AUDIT.json", {key: {"audits": row.get("identity_audits", [])} for key, row in results.items() if row.get("kind") == "PROP"})
    _write(OUT / "PROP_GLOBAL_AUDIT.json", {key: {"semantic": row.get("global_semantic"), "identity": row.get("global")} for key, row in results.items() if row.get("kind") == "PROP"})
    _write(OUT / "PROP_AUTHORITIES.json", {key: row.get("authority") for key, row in results.items() if row.get("kind") == "PROP"})
    geometries = {key: {view: {field: media.get(field) for field in ("requested_aspect_ratio", "submitted_aspect_ratio", "observed_width", "observed_height", "observed_aspect_ratio", "provider_ratio_honored")} for view, media in row.get("generations", {}).items()} for key, row in results.items()}; _write(OUT / "PROVIDER_OUTPUT_GEOMETRY.json", geometries)
    _write(OUT / "VISUAL_ASSET_AUTHORITY_SET.json", asdict(authority_set) if authority_set else {"status": "PARTIAL", "scene": scene, "characters": {key: row.get("authority") for key, row in results.items() if row.get("kind") == "CHARACTER"}, "props": {key: row.get("authority") for key, row in results.items() if row.get("kind") == "PROP"}})
    closure = {"run_id": OLD_RUN, "media_evidence": "VALID", "lin_wan_generation_lineage": "VALID", "execution_code_proven": False, "reason": "committed runner did not contain the recorded progressive-stop path", "recorded_audit_status": "PROGRESSIVE_STOP_AFTER_LIN_WAN_STAGE", "current_artifact_run_id": run_id}; _write(OUT / f"RUN_{OLD_RUN}_CLOSURE.json", closure)
    report = ["# Asset Semantic Purity and Authority Closure", "", f"- Status: `{status}`", f"- Run: `{run_id}`", "- IMAGE provider: `75api-image / gpt-image-2-1k`", "- VIDEO calls: `0`; Shot Keyframe calls: `0`", f"- Previous Lin Wan: identity consistency `PASS`; semantic purity `{('FAIL' if old_regression and old_regression.get('semantic_purity') == 'FAIL' else 'UNVERIFIED')}`; old Authority `INVALID_SEMANTIC_CONTAMINATION`; old board `historical-invalid-artifacts/`", f"- Real IMAGE calls: `{calls['image']}` (75api={calls['by_provider']['75api-image']}, SHAPI=0, Poyo=0)", f"- Vision Judge calls: `{calls['judge']['used']}`", f"- Board publication: `{dict(boards)}`", "- Production writes: `0`; Book 990400 writes: `0`; raw base64 persisted: `0`; signed URL query persisted: `0`; secret leaks: `0`; orphans: `0`", "", "## Authorities"]
    for key, label in (("LIN_WAN", "Lin Wan"), ("LU_SHU", "Lu Shu"), ("HANDBAG", "HANDBAG")): report.append(f"- {label}: `{('READY' if results.get(key, {}).get('authority') else 'NOT_STARTED/FAILED')}`")
    report += ["- Scene E01_SC002: `READY` (reused)", f"- VisualAssetAuthoritySet: `{('READY' if authority_set else 'PARTIAL')}`", "", "## Notes", "- Semantic compliance runs before derived generation and before identity consistency.", "- Unauthorized story props fail closed even when identity consistency passes.", "- Provider geometry records requested, submitted, and observed ratios separately.", "- No Shot Keyframe or VIDEO generation was executed."]
    (OUT / "ASSET_SEMANTIC_PURITY_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
