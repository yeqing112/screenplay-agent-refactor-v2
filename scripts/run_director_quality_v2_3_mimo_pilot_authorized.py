"""Guarded Director Quality V2.3 Phase A MiMo pilot.

The command is preflight-only by default.  A real run requires
``--execute-real``, the exact confirmation token and an enabled saved MiMo
profile.  It is artifact-only: no production, storyboard, media or object
storage mutation is reachable from this runner.
"""

from __future__ import annotations

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
CONFIRMATION_TOKEN = "CONFIRM_DIRECTOR_V23_STAGE_A_REAL_MIMO_PILOT"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_real_authorization(*, execute_real: bool, confirmation_token: str, profile: dict[str, Any] | None) -> dict[str, str]:
    if not execute_real:
        raise PermissionError("真实 V2.3 Pilot 默认关闭；必须显式提供 --execute-real。")
    if _text(confirmation_token) != CONFIRMATION_TOKEN:
        raise PermissionError("真实 V2.3 Pilot confirmation token 不匹配。")
    if not isinstance(profile, dict):
        raise ValueError("必须显式指定已保存的 MiMo LLM profile。")
    if _text(profile.get("capability")) != "llm" or _text(profile.get("provider")) != "openai-compatible":
        raise ValueError("V2.3 Pilot 需要 openai-compatible LLM profile。")
    if not bool(profile.get("enabled", True)):
        raise ValueError("Pilot profile 已禁用。")
    if "mimo" not in _text(profile.get("model_name")).lower():
        raise ValueError("V2.3 Pilot 只允许显式指定 MiMo 模型 profile。")
    if not _text(profile.get("api_key")) or not _text(profile.get("base_url")):
        raise ValueError("Pilot profile 缺少 API Key 或 base_url。")
    return {"profile_id": _text(profile.get("id")), "provider": _text(profile.get("provider")), "model_name": _text(profile.get("model_name"))}


def run_authorized_pilot(*, profile: dict[str, Any], golden_path: Path = GOLDEN_PATH, scene_limit: int = 12) -> dict[str, Any]:
    """Run one V2.3 sample per frozen scene using the real provider."""

    from core.director_creative_planner import build_creative_patch_candidate
    from core.director_prompt import build_director_patch_prompt
    from core.director_quality_metrics import build_director_quality_metrics, build_director_quality_v23_coverage_metrics
    from core.director_quality_trace import trace_quality_signals
    from core.director_quality_validator import score_director_quality
    from core.director_quality_v22 import process_patch_pipeline
    from core.llm import call_llm_json
    from core.pilot_instrumentation import PilotInvocationRecorder
    from core.scene_directing_strategy import build_scene_directing_strategy_v2

    payload = json.loads(golden_path.read_text(encoding="utf-8"))
    scenes = [item for item in _list(payload.get("scenes")) if isinstance(item, dict)][: max(0, int(scene_limit))]
    if len(scenes) < scene_limit:
        raise ValueError(f"Frozen scene count {len(scenes)} is below required {scene_limit}")
    recorder = PilotInvocationRecorder()
    results: list[dict[str, Any]] = []
    for scene in scenes:
        metadata = _dict(scene.get("scene"))
        scene_id = _text(metadata.get("scene_id"))
        evidence = _dict(scene.get("evidence"))
        treatment, blocking, contract, baseline = (_dict(evidence.get(key)) for key in ("treatment", "blocking", "contract", "structural_shot_plan"))
        if not baseline:
            baseline = copy.deepcopy(_dict(scene.get("baseline")))
        if not all((scene_id, treatment, blocking, contract, baseline)):
            raise ValueError(f"{scene_id or '<unknown>'}: frozen evidence is incomplete")
        strategy = build_scene_directing_strategy_v2(treatment=treatment, contract=contract)
        scene_start = len(recorder.records)
        prompt = build_director_patch_prompt(contract=contract, strategy=strategy, structural_shot_plan=baseline, model_profile=profile, stage="director_quality_v2_3_mimo_pilot")
        with recorder.span(stage="director_patch_planner_v23", episode=metadata.get("episode", 1), scene=metadata.get("scene_name", scene_id)):
            raw = call_llm_json(prompt["user_prompt"], system=prompt["system_prompt"], model_profile=profile, required_keys={"schema_version", "patches", "auxiliary_shot_proposals"}, estimated_tokens=5000, audit_extra={"stage": "director_patch_planner_v23", "scene_id": scene_id, "prompt_request_fingerprint": prompt["request_fingerprint"]})

        def repair_call(request: dict[str, Any]) -> Any:
            from core.director_repair_prompt import build_director_repair_prompt

            repair_prompt = build_director_repair_prompt(request)
            with recorder.span(stage="director_patch_repair_v23", episode=metadata.get("episode", 1), scene=metadata.get("scene_name", scene_id), repair_attempt=1):
                return call_llm_json(repair_prompt["user_prompt"], system=repair_prompt["system_prompt"], model_profile=profile, required_keys={"target", "replacement_value"}, estimated_tokens=1800, audit_extra={"stage": "director_patch_repair_v23", "scene_id": scene_id})

        result = process_patch_pipeline(structural_shot_plan=baseline, contract=contract, strategy=strategy, treatment=treatment, blocking=blocking, raw_output=raw, llm_repair_callable=repair_call, max_llm_attempts=2, scene_id=scene_id, episode=metadata.get("episode", 1))
        candidate = copy.deepcopy(result.get("candidate") or baseline)
        quality = build_director_quality_metrics(baseline=baseline, first_candidate=candidate, final_candidate=candidate, treatment=treatment, blocking=blocking, partial_acceptance=_dict(result.get("partial_acceptance")), strategy=strategy, proposed_patch_document=_dict(raw))
        quality["v23_coverage"] = build_director_quality_v23_coverage_metrics(candidate=candidate, strategy=strategy, treatment=treatment, proposed_patch_document=_dict(raw), accepted_patch_document=_dict(result.get("patch_document")))
        quality["scorer_direct"] = score_director_quality(candidate, treatment=treatment, blocking=blocking)
        trace = trace_quality_signals(scene_id=scene_id, strategy=strategy, planner_output=_dict(raw), accepted_patch=_dict(result.get("patch_document")), final_candidate=candidate, scorer_input=candidate, dimension_scores=quality["scorer_direct"].get("dimensions"))
        results.append({"scene": metadata, "status": result.get("status"), "raw_digest": _digest(raw), "candidate": candidate, "quality": quality, "quality_trace": trace, "stage_counts": copy.deepcopy(result.get("stage_counts") or {}), "partial_acceptance": copy.deepcopy(result.get("partial_acceptance") or {}), "fallbacks": copy.deepcopy(result.get("fallbacks") or []), "repair_attempts": copy.deepcopy(result.get("repair_attempts") or []), "planner_calls": sum(1 for item in recorder.records[scene_start:] if _dict(item.get("extra")).get("stage") == "director_patch_planner_v23"), "repair_calls": sum(1 for item in recorder.records[scene_start:] if _dict(item.get("extra")).get("stage") == "director_patch_repair_v23"), "side_effects": {"production": 0, "storyboard": 0, "media": 0, "object_storage": 0}})
    scores = [float(_dict(_dict(item.get("quality")).get("scorer_direct")).get("director_quality_score")) for item in results if isinstance(_dict(_dict(item.get("quality")).get("scorer_direct")).get("director_quality_score"), (int, float))]
    return {"protocol_version": "director-quality-v2-3", "pilot_mode": "real_mimo_phase_a_artifact_only", "generated_at": datetime.now(timezone.utc).isoformat(), "scene_count": len(results), "model": {"profile_id": _text(profile.get("id")), "provider": _text(profile.get("provider")), "model_name": _text(profile.get("model_name"))}, "summary": {"director_quality": {"mean": round(sum(scores) / len(scores), 4) if scores else None}, "unknown_root_cause_count": sum(int(_dict(item.get("quality_trace")).get("unknown_root_cause_count") or 0) for item in results)}, "scenes": results, "telemetry": recorder.summary(), "side_effects": {"production_rows_written": 0, "storyboard_shots_created": 0, "media_calls": 0, "object_storage_calls": 0}, "production_shadow": {"enabled": False}}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Guarded Director Quality V2.3 Phase A MiMo pilot")
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--confirmation-token", default="")
    parser.add_argument("--profile-id", default="")
    parser.add_argument("--scene-limit", type=int, default=12)
    args = parser.parse_args()
    if not args.execute_real:
        print(json.dumps({"status": "preflight_only", "real_mimo_calls": 0, "confirmation_required": True, "confirmation_token_name": "CONFIRM_DIRECTOR_V23_STAGE_A_REAL_MIMO_PILOT"}, ensure_ascii=False, indent=2))
        return
    from api.model_registry import get_profile

    profile = get_profile(args.profile_id)
    safe_model = validate_real_authorization(execute_real=True, confirmation_token=args.confirmation_token, profile=profile)
    result = run_authorized_pilot(profile=profile, scene_limit=max(12, int(args.scene_limit)))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = ARTIFACTS / f"director-quality-v2-3-smoke-pilot-{stamp}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(path), "model": safe_model, "scene_count": result["scene_count"], "side_effects": result["side_effects"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
