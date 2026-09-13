"""Guarded Director Quality V2.2.1 Stage A runner.

The runner reuses the benchmark-only execution boundary but compares its new
results with the frozen V2.2 Stage A artifact.  It never writes production
rows, Storyboard/media/storage objects, and it never reruns V2.2 for control.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"
V22_ARTIFACT = ARTIFACTS / "director-quality-v2-2-stage-a-mimo-pilot-20260913T145407Z.json"
CONFIRMATION_TOKEN = "CONFIRM_DIRECTOR_V22_1_REAL_MIMO_PILOT"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"artifact must be a JSON object: {path}")
    return payload


def _scene_key(scene: dict[str, Any]) -> str:
    return _text(_dict(scene.get("scene")).get("scene_id"))


def _quality_triplet(baseline: dict[str, Any], old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    old_quality = _dict(old.get("quality"))
    new_quality = _dict(new.get("quality"))
    old_dims = _dict(_dict(old_quality.get("dimensions")).get("after_repair"))
    new_dims = _dict(_dict(new_quality.get("dimensions")).get("after_repair"))
    baseline_dims = _dict(_dict(new_quality.get("dimensions")).get("baseline"))
    if not baseline_dims:
        baseline_dims = _dict(_dict(_dict(old.get("quality")).get("dimensions")).get("baseline"))
    return {
        "baseline": baseline_dims,
        "v2_2": old_dims,
        "v2_2_1": new_dims,
    }


def run_v221_pilot(*, profile: dict[str, Any], scene_limit: int = 12) -> dict[str, Any]:
    from scripts.run_director_quality_v2_2_mimo_pilot_authorized import run_authorized_pilot

    old_payload = _load_json(V22_ARTIFACT)
    old_scenes = {_scene_key(item): item for item in old_payload.get("scenes", []) if isinstance(item, dict)}
    if len(old_scenes) < scene_limit:
        raise ValueError("V2.2 control artifact does not contain the required 12 scenes")

    # This is the only real-call path.  It executes the current hardened
    # pipeline once; the prior V2.2 result is read from disk as control.
    observed = run_authorized_pilot(profile=profile, scene_limit=scene_limit)
    observed_metrics = copy.deepcopy(observed.get("metrics") or {})
    observed["protocol_version"] = "director-quality-v2-2-1"
    observed["pilot_mode"] = "real_mimo_v2_2_1_benchmark_only"
    try:
        observed["control_artifact"] = str(V22_ARTIFACT.relative_to(ROOT))
    except ValueError:
        observed["control_artifact"] = str(V22_ARTIFACT)

    quality_dimensions: dict[str, Any] = {}
    for scene in observed.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        key = _scene_key(scene)
        old = old_scenes.get(key, {})
        scene["quality_dimensions_ab"] = _quality_triplet({}, old, scene)
        quality_dimensions[key] = scene["quality_dimensions_ab"]

    v22_comparison = _dict(old_payload.get("comparison")).get("v22_observed") or {}
    v221_observed = {
        "scene_count": observed.get("scene_count"),
        "repair_calls": _dict(observed_metrics.get("repair_cost")).get("llm_repair_calls"),
        "fallback_patch_count": observed_metrics.get("fallback_patch_count"),
        "fallback_patch_rate": observed_metrics.get("fallback_patch_rate"),
        "avoidable_fallback_count": _dict(observed_metrics.get("fallback_classification")).get("avoidable_technical_fallback_count"),
        "first_schema_pass": _dict(observed_metrics.get("stages")).get("first_pass_schema_pass", {}).get("count"),
        "final_contract_pass": _dict(observed_metrics.get("stages")).get("final_contract_pass", {}).get("count"),
        "creative_retention_rate": observed_metrics.get("creative_retention_rate"),
        "creative_recovery_rate": observed_metrics.get("creative_recovery_rate"),
        "full_creative_scene_success_rate": observed_metrics.get("full_creative_scene_success_rate"),
        "director_quality_average": _dict(observed.get("comparison")).get("v22_observed", {}).get("director_quality_average"),
        "cache_hit_rate": _dict(observed.get("telemetry")).get("cache_hit_rate"),
        "avg_latency_ms": _dict(observed.get("telemetry")).get("avg_latency_ms"),
        "prompt_tokens": _dict(observed.get("telemetry")).get("total_prompt_tokens"),
        "repair_tokens": _dict(_dict(_dict(observed.get("telemetry")).get("stages")).get("director_patch_repair")).get("prompt_tokens"),
    }
    # The observed comparison field is still named v22_observed in the reused
    # runner; replace it with an explicit V2.2.1 record in this artifact.
    if v221_observed["director_quality_average"] is None:
        scores = []
        for scene in observed.get("scenes", []):
            score = _dict(_dict(scene).get("quality")).get("overall_director_quality", {}).get("after_repair")
            if isinstance(score, (int, float)):
                scores.append(float(score))
        v221_observed["director_quality_average"] = round(sum(scores) / len(scores), 2) if scores else None

    observed["comparison"] = {
        "v21_baseline": copy.deepcopy(_dict(observed.get("comparison")).get("v21_baseline") or {}),
        "v2_2_observed": copy.deepcopy(v22_comparison),
        "v2_2_1_observed": v221_observed,
        "quality_dimensions": quality_dimensions,
    }
    observed["metrics"] = {
        "v21": copy.deepcopy(_dict(_dict(observed.get("comparison")).get("v21_baseline") or {})),
        "v2_2": copy.deepcopy(v22_comparison),
        "v2_2_1": observed_metrics,
        "delta_vs_v2_2": {
            "repair_calls": (v221_observed.get("repair_calls") or 0) - (v22_comparison.get("repair_calls") or 0),
            "fallback_patch_count": (v221_observed.get("fallback_patch_count") or 0) - (v22_comparison.get("fallback_patch_count") or 0),
            "director_quality_average": (v221_observed.get("director_quality_average") or 0) - (v22_comparison.get("director_quality_average") or 0),
            "cache_hit_rate": (v221_observed.get("cache_hit_rate") or 0) - (v22_comparison.get("cache_hit_rate") or 0),
            "avg_latency_ms": (v221_observed.get("avg_latency_ms") or 0) - (v22_comparison.get("avg_latency_ms") or 0),
        },
    }
    observed["release_decision"] = "NOT_READY_FOR_PRODUCTION_SHADOW"
    observed["production_shadow"] = {"enabled": False}
    return observed


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded Director Quality V2.2.1 MiMo Stage A Pilot")
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--confirmation-token", default="")
    parser.add_argument("--profile-id", default="")
    parser.add_argument("--scene-limit", type=int, default=12)
    args = parser.parse_args()
    if not args.execute_real:
        print(json.dumps({"status": "preflight_only", "real_mimo_calls": 0, "confirmation_required": True}, ensure_ascii=False, indent=2))
        return
    if _text(args.confirmation_token) != CONFIRMATION_TOKEN:
        raise PermissionError("真实 V2.2.1 Pilot confirmation token 不匹配。")
    from api.model_registry import get_profile
    from scripts.run_director_quality_v2_2_mimo_pilot_authorized import validate_real_authorization

    profile = get_profile(args.profile_id)
    validate_real_authorization(execute_real=True, confirmation_token=CONFIRMATION_TOKEN, profile=profile)
    result = run_v221_pilot(profile=profile, scene_limit=max(12, int(args.scene_limit)))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ARTIFACTS.mkdir(exist_ok=True)
    path = ARTIFACTS / f"director-quality-v2-2-1-mimo-pilot-{stamp}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(path), "model": result.get("model"), "scene_count": result.get("scene_count"), "side_effects": result.get("side_effects")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
