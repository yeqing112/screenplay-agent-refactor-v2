"""Preflight the Director Quality V2.1 MiMo pilot without making calls.

The real MiMo pilot is an explicitly authorized follow-up stage.  This
command is intentionally preflight-only: it validates the offline Golden
evidence produced by ``run_director_quality_v2_1_benchmark.py`` and writes a
bounded readiness artifact.  It never imports the provider client, performs
network I/O, persists production rows, or fabricates telemetry.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
GOLDEN_PATH = ARTIFACTS / "director-quality-v2-1-golden-scenes.json"
REQUIRED_SCENE_TYPES = {
    "双人对话",
    "悬疑",
    "信息揭示",
    "情绪转折",
    "权力变化",
    "人物入场",
    "关键道具",
    "无对白",
    "多人物",
    "快节奏动作",
    "慢节奏情绪",
    "强反应镜头",
}
REQUIRED_STAGES = {"baseline", "before_repair", "after_repair"}
REQUIRED_DIMENSIONS = {
    "DRAMATIC_CLARITY",
    "SHOT_MOTIVATION",
    "EMOTIONAL_PROGRESSION",
    "VISUAL_STORYTELLING",
    "SPATIAL_CLARITY",
    "PERFORMANCE_DIRECTION",
    "EDIT_RHYTHM",
    "INFORMATION_STRATEGY",
    "POWER_DYNAMICS",
    "SHOT_DIVERSITY",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取 Golden 证据：{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Golden 证据必须是 JSON object")
    return value


def _scene_errors(scene: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    metadata = scene.get("scene") if isinstance(scene.get("scene"), dict) else {}
    scene_id = str(metadata.get("scene_id") or "<unknown>")
    if not str(_dict(scene.get("contract")).get("fingerprint") or "").strip():
        errors.append(f"{scene_id}: missing contract fingerprint")
    if not str(_dict(scene.get("strategy")).get("fingerprint") or "").strip():
        errors.append(f"{scene_id}: missing strategy fingerprint")

    evidence = _dict(scene.get("evidence"))
    for key in ("treatment", "blocking", "contract", "strategy"):
        if not evidence.get(key):
            errors.append(f"{scene_id}: missing frozen evidence.{key}")
    if evidence.get("contract") and str(_dict(evidence.get("contract")).get("contract_fingerprint") or "").strip() != str(_dict(scene.get("contract")).get("fingerprint") or "").strip():
        errors.append(f"{scene_id}: evidence contract fingerprint mismatch")
    if evidence.get("strategy") and str(_dict(evidence.get("strategy")).get("strategy_fingerprint") or "").strip() != str(_dict(scene.get("strategy")).get("fingerprint") or "").strip():
        errors.append(f"{scene_id}: evidence strategy fingerprint mismatch")

    for key in ("baseline", "first_candidate", "final_candidate"):
        if not isinstance(scene.get(key), dict):
            errors.append(f"{scene_id}: missing {key}")

    metrics = scene.get("metrics") if isinstance(scene.get("metrics"), dict) else {}
    scores = metrics.get("scores") if isinstance(metrics.get("scores"), dict) else {}
    if set(scores) != REQUIRED_STAGES:
        errors.append(f"{scene_id}: metrics.scores must contain baseline/before_repair/after_repair")
    dimensions = metrics.get("dimensions") if isinstance(metrics.get("dimensions"), dict) else {}
    if set(dimensions) != REQUIRED_STAGES:
        errors.append(f"{scene_id}: metrics.dimensions must contain baseline/before_repair/after_repair")
    for stage in REQUIRED_STAGES:
        if set(_dict(dimensions.get(stage))) != REQUIRED_DIMENSIONS:
            errors.append(f"{scene_id}: {stage} does not contain all ten Director Quality dimensions")
    reliability = metrics.get("contract_reliability") if isinstance(metrics.get("contract_reliability"), dict) else {}
    for key in ("schema_pass", "patch_path_pass", "auxiliary_binding_pass", "parse_success"):
        if key not in reliability:
            errors.append(f"{scene_id}: missing contract reliability field {key}")
    return errors


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_preflight() -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    if not GOLDEN_PATH.exists():
        errors.append(f"missing evidence artifact: {GOLDEN_PATH.name}")
        payload: dict[str, Any] = {}
    else:
        payload = _load_json(GOLDEN_PATH)

    scenes = payload.get("scenes") if isinstance(payload.get("scenes"), list) else []
    scene_types = {
        str(_dict(_dict(scene).get("scene")).get("scene_type") or "")
        for scene in scenes
        if isinstance(scene, dict)
    }
    errors.extend(_scene_errors(scene) for scene in scenes if isinstance(scene, dict))
    # Flatten the per-scene lists while preserving deterministic ordering.
    flattened: list[str] = []
    for item in errors:
        flattened.extend(item if isinstance(item, list) else [item])
    errors = flattened
    missing_types = sorted(REQUIRED_SCENE_TYPES - scene_types)
    if len(scenes) < 12:
        errors.append(f"Golden scene count is {len(scenes)}; at least 12 required")
    if missing_types:
        errors.append("missing required scene types: " + ", ".join(missing_types))
    metrics = {
        "offline_only": True,
        "provider_calls": 0,
        "media_calls": 0,
        "object_storage_calls": 0,
        "real_mimo_calls": 0,
    }
    result = {
        "protocol_version": "director-quality-v2-1",
        "preflight_only": True,
        "generated_at": generated_at,
        "status": "ready_for_authorized_real_pilot" if not errors else "blocked",
        "evidence": {
            "path": str(GOLDEN_PATH),
            "generated_at": payload.get("generated_at"),
            "scene_count": len(scenes),
            "scene_types": sorted(scene_types),
            "missing_scene_types": missing_types,
        },
        "checks": {
            "three_candidate_stages": not any("missing" in error or "metrics.scores" in error for error in errors),
            "ten_dimensions": not any("Director Quality dimensions" in error for error in errors),
            "contract_reliability": not any("contract reliability" in error for error in errors),
            "required_scene_coverage": len(scenes) >= 12 and not missing_types,
            "no_external_side_effects": True,
        },
        "telemetry": metrics,
        "errors": errors,
        "next_step": (
            "获得明确授权后，使用独立的真实 MiMo 运行器；本 preflight 不会自动执行。"
            if not errors
            else "修复上述离线证据问题后重新运行 preflight；不要通过降低门槛放行。"
        ),
    }
    return result


def main() -> None:
    result = build_preflight()
    ARTIFACTS.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = ARTIFACTS / f"director-quality-v2-1-mimo-pilot-preflight-{stamp}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**result, "artifact": str(path)}, ensure_ascii=False, indent=2))
    if result["status"] != "ready_for_authorized_real_pilot":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
