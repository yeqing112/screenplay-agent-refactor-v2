"""Guarded Director Quality V2.2 MiMo Stage A runner.

The CLI is preflight-only unless the operator supplies all three explicit
guards: ``--execute-real``, the exact confirmation token, and a saved MiMo
LLM profile.  The real path is benchmark-only and writes one timestamped
artifact; it never writes production rows, Storyboard rows, media, or object
storage.  Importing this module does not initialize a provider client.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"
GOLDEN_PATH = ARTIFACTS / "director-quality-v2-1-golden-scenes.json"
V21_BASELINE_PATH = ARTIFACTS / "director-quality-v2-1-mimo-pilot-20260913T093747Z.json"
CONFIRMATION_TOKEN = "CONFIRM_DIRECTOR_V22_REAL_MIMO_PILOT"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取 Golden evidence：{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Golden evidence 必须是 JSON object")
    return value


def validate_real_authorization(
    *, execute_real: bool, confirmation_token: str, profile: dict[str, Any] | None,
) -> dict[str, str]:
    """Fail closed unless the operator explicitly authorizes a V2.2 run."""

    if not execute_real:
        raise PermissionError("真实 V2.2 Pilot 默认关闭；必须显式提供 --execute-real。")
    if _text(confirmation_token) != CONFIRMATION_TOKEN:
        raise PermissionError("真实 V2.2 Pilot confirmation token 不匹配。")
    if not isinstance(profile, dict):
        raise ValueError("必须显式指定已保存的 MiMo LLM profile。")
    if _text(profile.get("capability")) != "llm":
        raise ValueError("Pilot profile 必须是 LLM 能力。")
    if _text(profile.get("provider")) != "openai-compatible":
        raise ValueError("真实 MiMo Pilot 需要 openai-compatible provider。")
    if not bool(profile.get("enabled", True)):
        raise ValueError("Pilot profile 已禁用。")
    model_name = _text(profile.get("model_name"))
    if "mimo" not in model_name.lower():
        raise ValueError("真实 V2.2 Pilot 只允许显式指定 MiMo 模型 profile。")
    if not _text(profile.get("api_key")):
        raise ValueError("Pilot profile 缺少 API Key。")
    if not _text(profile.get("base_url")):
        raise ValueError("Pilot profile 缺少 base_url。")
    return {"profile_id": _text(profile.get("id")), "provider": _text(profile.get("provider")), "model_name": model_name}


def _scene_context(scene: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    evidence = _dict(scene.get("evidence"))
    treatment = _dict(evidence.get("treatment"))
    blocking = _dict(evidence.get("blocking"))
    contract = _dict(evidence.get("contract"))
    strategy = _dict(evidence.get("strategy"))
    baseline = _dict(scene.get("baseline"))
    if not all((treatment, blocking, contract, strategy, baseline)):
        scene_id = _text(_dict(scene.get("scene")).get("scene_id")) or "<unknown>"
        raise ValueError(f"{scene_id}: frozen evidence is incomplete")
    return treatment, blocking, contract, strategy, baseline


def _repair_prompts(request: dict[str, Any]) -> dict[str, Any]:
    from core.director_repair_prompt import build_director_repair_prompt

    return build_director_repair_prompt(request)


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _aggregate_counts() -> dict[str, int]:
    return {
        "raw_parse_pass": 0, "normalized_parse_pass": 0, "first_pass_schema_pass": 0,
        "first_pass_contract_pass": 0, "post_normalization_contract_pass": 0,
        "post_deterministic_repair_pass": 0, "post_llm_repair_pass": 0,
        "final_contract_pass": 0, "total_scenes": 0, "evaluated_patch_count": 0,
        "fallback_patch_count": 0,
    }


def _aggregate_cost() -> dict[str, Any]:
    return {
        "normalization_events": 0, "deterministic_repair_events": 0,
        "llm_repair_calls": 0, "repair_token_cost": 0, "repair_latency_ms": 0,
        "fallback_after_repair_count": 0,
        "successful_repairs": 0,
        "failed_repairs": 0,
        "creative_patches_saved_by_llm_repair": 0,
        "fallbacks_prevented_by_repair": 0,
    }


def _baseline_summary(path: Path) -> dict[str, Any]:
    """Read only non-secret V2.1 baseline telemetry/quality for A/B output."""

    try:
        payload = _load_json(path)
    except Exception:
        return {"available": False, "source": str(path)}
    scenes = [item for item in (payload.get("scenes") or []) if isinstance(item, dict)]
    telemetry = _dict(payload.get("telemetry"))
    stage = _dict(_dict(telemetry.get("stages")).get("director_patch_planner"))
    repair_stage = _dict(_dict(telemetry.get("stages")).get("director_patch_repair"))
    scores = []
    for scene in scenes:
        overall = _dict(_dict(scene.get("metrics")).get("overall_director_quality"))
        value = overall.get("after_repair")
        if isinstance(value, (int, float)):
            scores.append(float(value))
    return {
        "available": True,
        "source": str(path.relative_to(ROOT)) if path.is_absolute() and path.is_relative_to(ROOT) else str(path),
        "scene_count": len(scenes),
        "repair_calls": int(repair_stage.get("total_calls") or 0),
        "fallback_patch_count": sum(int(_dict(scene.get("partial_acceptance")).get("fallback_patch_count") or 0) for scene in scenes),
        "first_schema_pass": sum(int(bool(_dict(scene.get("metrics")).get("contract_reliability", {}).get("schema_pass"))) for scene in scenes),
        "final_contract_pass": sum(int(bool(_dict(scene.get("validation")).get("contract_pass"))) for scene in scenes),
        "cache_hit_rate": telemetry.get("cache_hit_rate"),
        "avg_latency_ms": telemetry.get("avg_latency_ms"),
        "planner_calls": int(stage.get("total_calls") or 0),
        "director_quality_average": round(sum(scores) / len(scores), 2) if scores else None,
    }


def run_authorized_pilot(*, profile: dict[str, Any], golden_path: Path = GOLDEN_PATH, baseline_path: Path = V21_BASELINE_PATH, scene_limit: int = 12) -> dict[str, Any]:
    """Run V2.2 against frozen evidence with real provider calls only here."""

    from core.director_prompt import build_director_patch_prompt
    from core.director_quality_metrics import build_director_quality_metrics, build_director_quality_v22_metrics
    from core.director_quality_v22 import process_patch_pipeline
    from core.pilot_instrumentation import PilotInvocationRecorder
    from core.llm import call_llm_json

    payload = _load_json(golden_path)
    scenes = [item for item in (payload.get("scenes") or []) if isinstance(item, dict)]
    if len(scenes) < scene_limit:
        raise ValueError(f"Frozen Golden scene count {len(scenes)} is below required {scene_limit}")

    recorder = PilotInvocationRecorder()
    counts = _aggregate_counts()
    cost = _aggregate_cost()
    results: list[dict[str, Any]] = []
    total_creative = 0
    retained_creative = 0
    fallback_free = 0
    quality_scores: list[float] = []
    creative_recoverable_total = 0
    creative_recovered_total = 0
    safe_fallback_total = 0
    avoidable_fallback_total = 0
    path_resolution_total = {
        "path_resolution_attempt_count": 0, "path_resolution_success_count": 0,
        "path_resolution_failure_count": 0, "path_alias_hit_count": 0,
        "ambiguous_path_count": 0, "forbidden_path_count": 0,
    }

    for scene in scenes[:scene_limit]:
        metadata = _dict(scene.get("scene"))
        scene_id = _text(metadata.get("scene_id")) or "<unknown>"
        scene_name = _text(metadata.get("scene_name")) or scene_id
        episode = metadata.get("episode", 1)
        scene_start = len(recorder.records)
        error = ""
        result: dict[str, Any] | None = None
        raw: Any = None
        try:
            treatment, blocking, contract, strategy, baseline = _scene_context(scene)
            prompt = build_director_patch_prompt(
                contract=contract, strategy=strategy, structural_shot_plan=baseline,
                model_profile=profile, stage="director_quality_v2_2_mimo_pilot",
            )
            with recorder.span(stage="director_patch_planner", episode=episode, scene=scene_name):
                raw = call_llm_json(
                    prompt["user_prompt"], system=prompt["system_prompt"], model_profile=profile,
                    required_keys={"schema_version", "patches", "auxiliary_shot_proposals"},
                    estimated_tokens=5000,
                    audit_extra={
                        "stage": "director_patch_planner", "episode": episode, "scene_name": scene_name,
                        "prompt_prefix_fingerprint": prompt["prompt_prefix_fingerprint"],
                        "prompt_request_fingerprint": prompt["request_fingerprint"],
                        "stable_prefix_hash": prompt["stable_prefix_hash"],
                        "stable_prefix_length": prompt["stable_prefix_length"],
                        "variable_tail_hash": prompt["variable_tail_hash"],
                    },
                )

            def repair_call(request: dict[str, Any]) -> Any:
                repair_prompt = _repair_prompts(request)
                attempt = len([
                    item for item in recorder.records
                    if _dict(item.get("extra")).get("pilot_stage") == "director_patch_repair"
                    and _dict(item.get("extra")).get("pilot_scene") == scene_name
                ]) + 1
                with recorder.span(stage="director_patch_repair", episode=episode, scene=scene_name, repair_attempt=attempt):
                    return call_llm_json(
                        repair_prompt["user_prompt"], system=repair_prompt["system_prompt"], model_profile=profile,
                        required_keys={"target", "replacement_value"}, estimated_tokens=1800,
                        audit_extra={
                            "stage": "director_patch_repair", "episode": episode, "scene_name": scene_name,
                            "stable_prefix_hash": repair_prompt["stable_prefix_hash"],
                            "stable_prefix_length": repair_prompt["stable_prefix_length"],
                            "variable_tail_hash": repair_prompt["variable_tail_hash"],
                        },
                    )

            result = process_patch_pipeline(
                structural_shot_plan=baseline, contract=contract, strategy=strategy,
                treatment=treatment, blocking=blocking, raw_output=raw,
                llm_repair_callable=repair_call, max_llm_attempts=2,
            )
            result["candidate"] = copy.deepcopy(result.get("candidate") or baseline)
            accepted_meta = _dict(result.get("partial_acceptance"))
            patch_count = len(_dict(raw).get("patches") or []) if isinstance(raw, dict) else 0
            fallback_count = len(result.get("fallbacks") or [])
            creative_recoverable_total += int(result.get("creative_recoverable_patch_count") or 0)
            creative_recovered_total += int(result.get("creative_recovered_patch_count") or 0)
            safe_fallback_total += int(result.get("safe_fallback_count") or 0)
            avoidable_fallback_total += int(result.get("avoidable_fallback_count") or 0)
            for key in path_resolution_total:
                path_resolution_total[key] += int(_dict(result.get("path_resolution")).get(key) or 0)
            cost["successful_repairs"] += int(result.get("successful_repairs") or 0)
            cost["failed_repairs"] += int(result.get("failed_repairs") or 0)
            total_creative += patch_count + fallback_count
            retained_creative += int(accepted_meta.get("accepted_patch_count") or 0)
            fallback_free += int(not result.get("fallbacks"))
            counts["total_scenes"] += 1
            counts["evaluated_patch_count"] += patch_count + fallback_count
            counts["fallback_patch_count"] += fallback_count
            for key in ("raw_parse_pass", "normalized_parse_pass", "first_pass_schema_pass", "first_pass_contract_pass", "post_normalization_contract_pass", "post_deterministic_repair_pass", "post_llm_repair_pass", "final_contract_pass"):
                counts[key] += int(_dict(result.get("stage_counts")).get(key) or 0)
            quality = build_director_quality_metrics(
                baseline=baseline,
                first_candidate=result.get("candidate"),
                final_candidate=result.get("candidate"),
                treatment=treatment,
                blocking=blocking,
                partial_acceptance=accepted_meta,
            )
            score = _dict(quality.get("overall_director_quality")).get("after_repair")
            if isinstance(score, (int, float)):
                quality_scores.append(float(score))
        except Exception as exc:
            error = str(exc)[:500]
            counts["total_scenes"] += 1

        scene_records = recorder.records[scene_start:]
        planner_calls = sum(1 for item in scene_records if _dict(item.get("extra")).get("pilot_stage") == "director_patch_planner")
        repair_calls = sum(1 for item in scene_records if _dict(item.get("extra")).get("pilot_stage") == "director_patch_repair")
        cost["llm_repair_calls"] += repair_calls
        cost["repair_token_cost"] += sum(int(_dict(item.get("usage")).get("total_tokens") or 0) for item in scene_records if _dict(item.get("extra")).get("pilot_stage") == "director_patch_repair")
        cost["repair_latency_ms"] += round(sum(float(item.get("latency_ms") or 0) for item in scene_records if _dict(item.get("extra")).get("pilot_stage") == "director_patch_repair"), 2)
        if result is None:
            results.append({"scene": metadata, "status": "error", "error": error, "planner_calls": planner_calls, "repair_calls": repair_calls, "raw_digest": _digest(raw) if raw is not None else ""})
            continue
        result_metrics = _dict(result.get("metrics"))
        cost["normalization_events"] += len(result.get("normalization_events") or [])
        cost["deterministic_repair_events"] += len(result.get("deterministic_repair_events") or [])
        results.append({
            "scene": metadata,
            "status": result.get("status"),
            "error": error,
            "raw_digest": _digest(raw),
            "stage_counts": copy.deepcopy(result.get("stage_counts") or {}),
            "partial_acceptance": copy.deepcopy(result.get("partial_acceptance") or {}),
            "repair_attempts": copy.deepcopy(result.get("repair_attempts") or []),
            "fallbacks": copy.deepcopy(result.get("fallbacks") or []),
            "candidate": copy.deepcopy(result.get("candidate") or {}),
            "validation": copy.deepcopy(result.get("validation") or {}),
            "planner_calls": planner_calls,
            "repair_calls": repair_calls,
            "side_effects": copy.deepcopy(result.get("side_effects") or {}),
            "path_resolution": copy.deepcopy(result.get("path_resolution") or {}),
            "creative_recoverable_patch_count": int(result.get("creative_recoverable_patch_count") or 0),
            "creative_recovered_patch_count": int(result.get("creative_recovered_patch_count") or 0),
            "safe_fallback_count": int(result.get("safe_fallback_count") or 0),
            "avoidable_fallback_count": int(result.get("avoidable_fallback_count") or 0),
            "successful_repairs": int(result.get("successful_repairs") or 0),
            "failed_repairs": int(result.get("failed_repairs") or 0),
            "quality": quality,
        })

    metrics = build_director_quality_v22_metrics(
        stage_counts=counts, repair_cost=cost, creative_patch_count=total_creative,
        retained_creative_patch_count=retained_creative, fallback_free_scene_count=fallback_free,
        scene_count=counts["total_scenes"],
        creative_recoverable_patch_count=creative_recoverable_total,
        creative_recovered_patch_count=creative_recovered_total,
        safe_fallback_count=safe_fallback_total,
        avoidable_fallback_count=avoidable_fallback_total,
    )
    metrics["path_resolution"] = {
        **path_resolution_total,
        "path_resolution_success_rate": round(
            path_resolution_total["path_resolution_success_count"] / path_resolution_total["path_resolution_attempt_count"], 4
        ) if path_resolution_total["path_resolution_attempt_count"] else None,
    }
    v22_quality_average = round(sum(quality_scores) / len(quality_scores), 2) if quality_scores else None
    v21 = _baseline_summary(baseline_path)
    comparison = {
        "v21_baseline": v21,
        "v22_observed": {
            "scene_count": counts["total_scenes"],
            "repair_calls": cost["llm_repair_calls"],
            "fallback_patch_count": counts["fallback_patch_count"],
            "first_schema_pass": counts["first_pass_schema_pass"],
            "final_contract_pass": counts["final_contract_pass"],
            "cache_hit_rate": _dict(recorder.summary()).get("cache_hit_rate"),
            "avg_latency_ms": _dict(recorder.summary()).get("avg_latency_ms"),
            "director_quality_average": v22_quality_average,
        },
    }
    if v21.get("available") and v22_quality_average is not None and isinstance(v21.get("director_quality_average"), (int, float)):
        comparison["quality_delta_vs_v21"] = round(v22_quality_average - float(v21["director_quality_average"]), 2)
    return {
        "protocol_version": "director-quality-v2-2",
        "pilot_mode": "real_mimo_benchmark_only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scene_count": len(results),
        "model": {"profile_id": _text(profile.get("id")), "provider": _text(profile.get("provider")), "model_name": _text(profile.get("model_name"))},
        "metrics": metrics,
        "comparison": comparison,
        "scenes": results,
        "telemetry": recorder.summary(),
        "side_effects": {"production_rows_written": 0, "storyboard_shots_created": 0, "media_calls": 0, "object_storage_calls": 0},
        "blind_judge": {"status": "not_run"},
        "production_shadow": {"enabled": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded Director Quality V2.2 MiMo Stage A Pilot")
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--confirmation-token", default="")
    parser.add_argument("--profile-id", default="")
    parser.add_argument("--scene-limit", type=int, default=12)
    args = parser.parse_args()
    if not args.execute_real:
        print(json.dumps({"status": "preflight_only", "real_mimo_calls": 0, "confirmation_required": True}, ensure_ascii=False, indent=2))
        return
    from api.model_registry import get_profile
    profile = get_profile(args.profile_id)
    safe_model = validate_real_authorization(execute_real=True, confirmation_token=args.confirmation_token, profile=profile)
    result = run_authorized_pilot(profile=profile, scene_limit=max(12, int(args.scene_limit)))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ARTIFACTS.mkdir(exist_ok=True)
    path = ARTIFACTS / f"director-quality-v2-2-stage-a-mimo-pilot-{stamp}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(path), "model": safe_model, "scene_count": result["scene_count"], "telemetry": result["telemetry"], "side_effects": result["side_effects"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
