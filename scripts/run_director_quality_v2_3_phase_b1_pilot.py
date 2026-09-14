"""Guarded Director Quality V2.3 Phase B1 MiMo pilot.

The default command is a provider-free preflight.  A real run requires the
explicit B1 confirmation token and a saved MiMo profile.  The runner writes
pilot artifacts only: it never persists a ShotPlan, Storyboard, media task,
or object-storage record.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"
GOLDEN_PATH = ARTIFACTS / "director-quality-v2-1-golden-scenes.json"
OFFLINE_PATH = ARTIFACTS / "director-quality-v2-3-offline-benchmark-current.json"
CONFIRMATION_TOKEN = "CONFIRM_DIRECTOR_V23_PHASE_B1_REAL_MIMO_PILOT"
REQUIRED_SCENE_COUNT = 12


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _profile_safe(profile: dict[str, Any] | None) -> dict[str, Any]:
    value = profile if isinstance(profile, dict) else {}
    return {
        "id": _text(value.get("id")),
        "provider": _text(value.get("provider")),
        "model_name": _text(value.get("model_name")),
        "capability": _text(value.get("capability")),
        "enabled": bool(value.get("enabled", True)),
        "key_configured": bool(value.get("key_configured") or _text(value.get("api_key"))),
    }


def validate_real_authorization(*, execute_real: bool, confirmation_token: str, profile: dict[str, Any] | None) -> dict[str, str]:
    if not execute_real:
        raise PermissionError("真实 B1 Pilot 默认关闭；必须显式提供 --execute-real。")
    if _text(confirmation_token) != CONFIRMATION_TOKEN:
        raise PermissionError("真实 B1 Pilot confirmation token 不匹配。")
    if not isinstance(profile, dict):
        raise ValueError("必须显式指定已保存的 MiMo LLM profile。")
    if _text(profile.get("provider")) != "openai-compatible" or _text(profile.get("capability")) != "llm":
        raise ValueError("B1 Pilot 需要 openai-compatible LLM profile。")
    if not bool(profile.get("enabled", True)):
        raise ValueError("Pilot profile 已禁用。")
    if "mimo" not in _text(profile.get("model_name")).lower():
        raise ValueError("B1 Pilot 只允许显式指定 MiMo 模型 profile。")
    if not _text(profile.get("api_key")) or not _text(profile.get("base_url")):
        raise ValueError("Pilot profile 缺少 API Key 或 base_url。")
    return {"profile_id": _text(profile.get("id")), "provider": _text(profile.get("provider")), "model_name": _text(profile.get("model_name"))}


def _opportunity_prompt_view(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the dynamic prompt bounded while preserving every decision anchor."""

    fields = ("opportunity_id", "type", "scene_id", "beat_id", "subjects", "reason", "evidence_refs", "priority", "eligible", "recommended_directing_dimensions")
    return [{key: copy.deepcopy(item.get(key)) for key in fields} for item in opportunities]


def _decision_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        for key in ("opportunity_decisions", "decisions", "items"):
            if isinstance(raw.get(key), list):
                return [item for item in raw[key] if isinstance(item, dict)]
    return []


def _shot_for_beat(plan: dict[str, Any], beat_id: str) -> dict[str, Any]:
    for shot in _list(plan.get("shots")):
        if isinstance(shot, dict) and _text(shot.get("beat_id")) == _text(beat_id):
            return shot
    return {}


def _dimension_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, float]:
    b = _dict(before.get("dimensions")); a = _dict(after.get("dimensions"))
    keys = set(b) | set(a)
    return {str(key): round(float(a.get(key, 0) or 0) - float(b.get(key, 0) or 0), 4) for key in sorted(keys)}


def _stats(values: list[float]) -> dict[str, float | None]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {key: None for key in ("mean", "median", "p10", "min", "p25", "p75", "p90", "max")}
    def nearest(percentile: float) -> float:
        index = max(0, min(len(ordered) - 1, int(__import__("math").ceil(percentile * len(ordered))) - 1))
        return ordered[index]
    return {
        "mean": round(statistics.fmean(ordered), 4),
        "median": round(statistics.median(ordered), 4),
        "p10": round(nearest(0.10), 4),
        "min": round(ordered[0], 4),
        "p25": round(nearest(0.25), 4),
        "p75": round(nearest(0.75), 4),
        "p90": round(nearest(0.90), 4),
        "max": round(ordered[-1], 4),
    }


def run_authorized_pilot(*, profile: dict[str, Any], golden_path: Path = GOLDEN_PATH, scene_limit: int = REQUIRED_SCENE_COUNT) -> dict[str, Any]:
    """Execute B1 against frozen evidence and return artifact-only results."""

    from core.director_creative_contract import build_director_creative_contract
    from core.director_creative_planner import build_creative_patch_candidate
    from core.director_creative_value import build_creative_value_score, evaluate_useful_creative_acceptance
    from core.director_opportunity_detector import detect_creative_opportunities
    from core.director_opportunity_evaluation import build_eligibility_metrics
    from core.director_overdirecting import detect_over_directing
    from core.director_patch_compiler import compile_creative_patches
    from core.director_prompt import build_director_patch_prompt
    from core.director_quality_metrics import build_director_quality_v23_coverage_metrics
    from core.director_quality_trace import trace_quality_signals
    from core.director_quality_validator import score_director_quality
    from core.director_shadow_gate import evaluate_shadow_gate
    from core.director_tail_analysis import build_tail_analysis
    from core.director_tail_repair import build_tail_repair_plan
    from core.director_tail_root_cause import classify_tail_root_cause
    from core.llm import call_llm_json
    from core.pilot_instrumentation import PilotInvocationRecorder
    from core.scene_directing_strategy import build_scene_directing_strategy_v2

    payload = json.loads(golden_path.read_text(encoding="utf-8"))
    scenes = [item for item in _list(payload.get("scenes")) if isinstance(item, dict)][: max(0, int(scene_limit))]
    if len(scenes) < scene_limit:
        raise ValueError(f"Frozen scene count {len(scenes)} is below required {scene_limit}")
    recorder = PilotInvocationRecorder()
    rows: list[dict[str, Any]] = []
    opportunity_rows: list[dict[str, Any]] = []

    for scene in scenes:
        metadata = _dict(scene.get("scene")); evidence = _dict(scene.get("evidence"))
        treatment, blocking, contract, baseline = (_dict(evidence.get(key)) for key in ("treatment", "blocking", "contract", "structural_shot_plan"))
        if not baseline:
            baseline = copy.deepcopy(_dict(scene.get("baseline")))
        scene_id = _text(metadata.get("scene_id"))
        if not all((scene_id, treatment, blocking, contract, baseline)):
            raise ValueError(f"{scene_id or '<unknown>'}: frozen evidence is incomplete")
        opportunities = detect_creative_opportunities(script_scene=treatment, treatment=treatment, blocking=blocking, structural_shot_plan=baseline, fact_snapshot=_dict(evidence.get("fact_snapshot")), scene_canonical=_dict(evidence.get("scene_canonical")), previous_scene_continuity=_dict(evidence.get("previous_scene_continuity")))
        strategy = build_scene_directing_strategy_v2(treatment=treatment, contract=contract, structural_shot_plan=baseline)
        prompt = build_director_patch_prompt(contract=contract, strategy=strategy, structural_shot_plan=baseline, model_profile=profile, stage="director_quality_v2_3_phase_b1", opportunities=_opportunity_prompt_view(opportunities))
        scene_start = len(recorder.records)
        with recorder.span(stage="director_patch_planner_v23_b1", episode=metadata.get("episode", 1), scene=metadata.get("scene_name", scene_id)):
            raw = call_llm_json(prompt["user_prompt"], system=prompt["system_prompt"], model_profile=profile, required_keys={"schema_version", "patches", "auxiliary_shot_proposals", "opportunity_decisions"}, estimated_tokens=7000, audit_extra={"stage": "director_patch_planner_v23_b1", "scene_id": scene_id, "prompt_request_fingerprint": prompt["request_fingerprint"]})
        raw_dict = _dict(raw)
        decisions_raw = raw_dict.get("opportunity_decisions")
        patch_raw = {key: copy.deepcopy(value) for key, value in raw_dict.items() if key != "opportunity_decisions"}
        candidate_result = build_creative_patch_candidate(structural_shot_plan=baseline, contract=contract, strategy=strategy, llm_output=patch_raw)
        pipeline = _dict(candidate_result.get("patch_document"))
        compiled = compile_creative_patches(baseline, pipeline, contract, allow_partial=True)
        candidate = copy.deepcopy(_dict(compiled.get("candidate")) or baseline)
        before_score = score_director_quality(baseline, treatment=treatment, blocking=blocking)
        after_score = score_director_quality(candidate, treatment=treatment, blocking=blocking)
        # ``compile_creative_patches`` exposes compiled metadata rather than a
        # second patch document. Reconstruct the accepted subset solely for
        # the opportunity-value denominator.
        accepted_patches = _list(compiled.get("compiled_patches"))
        accepted_targets = {_text(item.get("plan_shot_id")) for item in accepted_patches if isinstance(item, dict)}
        proposed_patches = _list(pipeline.get("patches"))
        accepted_patch_document = {
            "schema_version": "director_creative_patch_v1",
            "patches": [item for item in proposed_patches if isinstance(item, dict) and _text(item.get("plan_shot_id")) in accepted_targets],
            "auxiliary_shot_proposals": [],
        }
        coverage = build_director_quality_v23_coverage_metrics(candidate=candidate, strategy=strategy, treatment=treatment, proposed_patch_document=pipeline, accepted_patch_document=accepted_patch_document)
        normalized_decisions = _decision_items(decisions_raw)
        try:
            from core.director_opportunity_planner import normalize_planner_decisions

            decisions = normalize_planner_decisions(normalized_decisions, opportunities)
            decision_errors: list[dict[str, str]] = []
        except Exception as exc:
            decisions = []
            decision_errors = [{"code": getattr(exc, "code", "OPPORTUNITY_DECISION_INVALID"), "message": str(exc)[:300]}]
        # The compiler returns compiled patch metadata (not a second
        # normalized patch document).  Accepted targets are therefore derived
        # from ``compiled_patches``; an empty rejection list is the contract
        # proof for this already-normalized candidate.
        # ``accepted_targets`` and ``proposed_patches`` were computed above.
        interventions: list[dict[str, Any]] = []
        for opportunity in opportunities:
            oid = _text(opportunity.get("opportunity_id")); beat_id = _text(opportunity.get("beat_id")); shot = _shot_for_beat(baseline, beat_id); sid = _text(shot.get("plan_shot_id"))
            patch_for_shot = any(isinstance(item, dict) and _text(item.get("plan_shot_id")) == sid for item in proposed_patches)
            dimension_deltas = _dimension_delta(before_score, after_score)
            recommended = set(_list(opportunity.get("recommended_directing_dimensions")))
            scoped_delta = {key: value for key, value in dimension_deltas.items() if key.lower() in recommended or key in recommended}
            if not scoped_delta:
                scoped_delta = dimension_deltas
            interventions.append({"opportunity_id": oid, "patch_valid": True, "applied": bool(patch_for_shot and sid in accepted_targets), "fact_contract_pass": not bool(compiled.get("rejected_patches")), "new_blocker": False, "quality_delta": float(after_score.get("director_quality_score", 0) or 0) - float(before_score.get("director_quality_score", 0) or 0), "dimension_deltas": scoped_delta})
        if decision_errors:
            # The evaluator intentionally rejects incomplete decision sets.
            # Preserve that fail-closed behavior while still emitting an
            # auditable outcome for every eligible opportunity as a missed
            # decision (never silently converting a schema failure to a
            # valid skip).
            from core.director_opportunity_model import build_opportunity_outcome, normalize_opportunity

            normalized_opportunities = [normalize_opportunity(item) for item in opportunities]
            outcomes = [
                build_opportunity_outcome(
                    opportunity=item,
                    planner_decision="ACT",
                    decision_reason="模型未返回可验证的完整机会决策",
                    final_status="MISSED_OPPORTUNITY" if item["eligible"] else "SKIPPED_VALID_REASON",
                )
                for item in normalized_opportunities
            ]
            eligible_outcomes = [item for item in outcomes if item["eligible"]]
            value = {
                "eligible_opportunity_count": len(eligible_outcomes),
                "useful_accepted_count": 0,
                "accepted_count": 0,
                "accepted_no_measurable_value_count": 0,
                "rejected_contract_count": 0,
                "rejected_quality_count": 0,
                "fallback_baseline_count": 0,
                "valid_skip_count": 0,
                "missed_opportunity_count": len(eligible_outcomes),
                "useful_creative_acceptance_rate": 0.0 if eligible_outcomes else None,
                "valid_skip_rate": 0.0 if eligible_outcomes else None,
                "missed_opportunity_rate": 1.0 if eligible_outcomes else None,
                "outcomes": outcomes,
            }
        else:
            value = evaluate_useful_creative_acceptance(opportunities=opportunities, decisions=decisions, interventions=interventions)
        eligible = int(value.get("eligible_opportunity_count") or 0)
        handled = eligible - int(value.get("missed_opportunity_count") or 0)
        cv = build_creative_value_score(opportunity_coverage=(handled / eligible) if eligible else 1.0, useful_creative_acceptance=value.get("useful_creative_acceptance_rate") if eligible else 1.0, edit_strategy=coverage.get("edit_strategy_coverage"), emotion_arc=coverage.get("emotion_arc_coverage"), information_strategy=coverage.get("information_strategy_coverage"), tail_stability=1.0 if float(after_score.get("director_quality_score", 0) or 0) >= 70 else 0.0)
        max_per_beat = int(_dict(contract).get("auxiliary_shot_policy", {}).get("max_per_source_beat", 2) or 0)
        beat_count = len(_list(treatment.get("beat_map"))) or len(_list(baseline.get("shots"))) or 1
        over = detect_over_directing(candidate.get("shots") or [], opportunities=opportunities, baseline_shot_count=len(_list(baseline.get("shots"))), allowed_auxiliary_count=max_per_beat * beat_count)
        quality_trace = trace_quality_signals(scene_id=scene_id, strategy=strategy, planner_output=patch_raw, accepted_patch=_dict(compiled.get("patch_document")), final_candidate=candidate, scorer_input=candidate, dimension_scores=after_score.get("dimensions"))
        scene_records = recorder.records[scene_start:]
        row = {
            "scene": metadata,
            "scene_id": scene_id,
            "status": "valid" if not decision_errors else "partial",
            "contract_pass": not bool(compiled.get("rejected_patches")),
            "fact_override_accepted": 0,
            "opportunities": opportunities,
            "opportunity_count": len(opportunities),
            "eligibility": build_eligibility_metrics(opportunities),
            "planner_decisions": decisions,
            "decision_errors": decision_errors,
            "opportunity_outcomes": value.get("outcomes") or [],
            "quality": {"director_quality_score": after_score.get("director_quality_score"), "dimensions": after_score.get("dimensions")},
            "director_quality_score": after_score.get("director_quality_score"),
            "creative_value": cv,
            "coverage": coverage,
            "over_directing": over,
            "quality_trace": quality_trace,
            "validation": {"contract_pass": not bool(compiled.get("rejected_patches")), "rejected_patch_count": len(_list(compiled.get("rejected_patches"))), "quality_issues": after_score.get("issues") or [], "auxiliary_shot_count": len(_list(compiled.get("auxiliary_shot_proposals"))), "baseline_shot_count": len(_list(baseline.get("shots")))},
            "pipeline_diagnostics": {"rejected_patch_count": len(_list(compiled.get("rejected_patches"))), "fallbacks": candidate_result.get("model_info", {}).get("planner_error", "")},
            "tail_repair": build_tail_repair_plan({"director_quality_score": after_score.get("director_quality_score"), "creative_value_score": cv.get("score"), "coverage": coverage}, root_causes=[]),
            "planner_calls": 1,
            "repair_calls": 0,
            "telemetry": {"total_tokens": sum(int(_dict(item.get("usage")).get("total_tokens") or 0) for item in scene_records), "total_cached_tokens": sum(int(_dict(item.get("usage")).get("cached_tokens") or 0) for item in scene_records), "avg_latency_ms": round(sum(float(item.get("latency_ms") or 0) for item in scene_records) / len(scene_records), 2) if scene_records else None},
            "side_effects": {"production": 0, "storyboard": 0, "media": 0, "object_storage": 0},
        }
        root = classify_tail_root_cause(row)
        row["tail_root_cause"] = root
        rows.append(row)
        opportunity_rows.append({"scene_id": scene_id, "opportunities": opportunities, "eligibility": row["eligibility"], "outcomes": value.get("outcomes") or []})

    quality_scores = [float(row["director_quality_score"]) for row in rows if isinstance(row.get("director_quality_score"), (int, float))]
    creative_scores = [float(_dict(row.get("creative_value")).get("score")) for row in rows if isinstance(_dict(row.get("creative_value")).get("score"), (int, float))]
    quality_stats = _stats(quality_scores); creative_stats = _stats(creative_scores)
    eligible_total = sum(int(_dict(row.get("creative_value")).get("eligible_opportunity_count") or 0) for row in rows)
    useful_total = sum(int(_dict(row.get("creative_value")).get("useful_accepted_count") or 0) for row in rows)
    skipped_total = sum(int(_dict(row.get("creative_value")).get("valid_skip_count") or 0) for row in rows)
    missed_total = sum(int(_dict(row.get("creative_value")).get("missed_opportunity_count") or 0) for row in rows)
    denominator_keys = {
        "edit_strategy_coverage": "edit_strategy_required_shot_count",
        "emotion_arc_coverage": "emotion_curve_entry_count",
        "information_strategy_coverage": "information_plan_entry_count",
    }
    def weighted(metric: str) -> float | None:
        numerator = denominator = 0
        for row in rows:
            coverage = _dict(row.get("coverage")); value = coverage.get(metric); count = int(coverage.get(denominator_keys.get(metric, "")) or 0)
            if isinstance(value, (int, float)) and count > 0:
                numerator += float(value) * count; denominator += count
        return round(numerator / denominator, 4) if denominator else None
    contract_rate = round(sum(bool(row.get("contract_pass")) for row in rows) / len(rows), 4) if rows else None
    unknown = sum(int(_dict(row.get("quality_trace")).get("unknown_root_cause_count") or 0) for row in rows)
    over_rate = round(sum(float(_dict(row.get("over_directing")).get("over_directing_rate") or 0) for row in rows) / len(rows), 4) if rows else None
    inflation_rate = round(sum(float(_dict(row.get("over_directing")).get("shot_inflation_rate") or 0) for row in rows) / len(rows), 4) if rows else None
    gate = evaluate_shadow_gate(contract_pass_rate=contract_rate, fact_override_accepted=0, unknown_root_cause_count=unknown, director_quality_mean=quality_stats["mean"], director_quality_median=quality_stats["median"], director_quality_p10=quality_stats["p10"], director_quality_min=quality_stats["min"], creative_value_mean=creative_stats["mean"], creative_value_median=creative_stats["median"], useful_creative_acceptance=(useful_total / eligible_total) if eligible_total else None, edit_strategy_eligible_coverage=weighted("edit_strategy_coverage"), emotion_arc_eligible_coverage=weighted("emotion_arc_coverage"), information_strategy_eligible_coverage=weighted("information_strategy_coverage"), over_directing_rate=over_rate, shot_inflation_rate=inflation_rate)
    return {
        "protocol_version": "director-quality-v2-3-phase-b1",
        "pilot_mode": "real_mimo_phase_b1_artifact_only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scene_count": len(rows),
        "model": {"profile_id": _text(profile.get("id")), "provider": _text(profile.get("provider")), "model_name": _text(profile.get("model_name"))},
        "summary": {"director_quality": quality_stats, "creative_value": creative_stats, "contract_pass_rate": contract_rate, "eligible_opportunity_count": eligible_total, "useful_accepted_count": useful_total, "valid_skip_count": skipped_total, "missed_opportunity_count": missed_total, "useful_creative_acceptance": (useful_total / eligible_total) if eligible_total else None, "valid_skip_rate": (skipped_total / eligible_total) if eligible_total else None, "missed_opportunity_rate": (missed_total / eligible_total) if eligible_total else None, "unknown_root_cause_count": unknown, "edit_strategy_eligible_coverage": weighted("edit_strategy_coverage"), "emotion_arc_eligible_coverage": weighted("emotion_arc_coverage"), "information_strategy_eligible_coverage": weighted("information_strategy_coverage"), "over_directing_rate": over_rate, "shot_inflation_rate": inflation_rate},
        "scenes": rows,
        "telemetry": recorder.summary(),
        "shadow_gate": gate,
        "side_effects": {"production_rows_written": 0, "storyboard_shots_created": 0, "media_calls": 0, "object_storage_calls": 0},
        "production_shadow": {"enabled": False},
        "artifacts": {"opportunity_analysis": opportunity_rows, "tail_analysis": {"director_quality": build_tail_analysis(rows, score_key="director_quality_score"), "creative_value": build_tail_analysis(rows, score_key="creative_value_score")}},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guarded Director Quality V2.3 Phase B1 MiMo pilot")
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--confirmation-token", default="")
    parser.add_argument("--profile-id", default="")
    parser.add_argument("--scene-limit", type=int, default=REQUIRED_SCENE_COUNT)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    from api.model_registry import get_profile

    profile = get_profile(args.profile_id) if args.profile_id else None
    if not args.execute_real:
        from scripts.run_director_quality_v2_3_phase_b1_preflight import build_preflight

        packet = build_preflight(profile=profile, golden_path=GOLDEN_PATH, offline_path=OFFLINE_PATH, scene_limit=args.scene_limit)
        output = args.output or (ARTIFACTS / f"director-quality-v2-3-phase-b1-preflight-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
        output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "preflight_only", "artifact": str(output), "ready_for_confirmation": packet.get("ready_for_confirmation"), "real_mimo_calls": 0}, ensure_ascii=False, indent=2)); return 0
    safe = validate_real_authorization(execute_real=True, confirmation_token=args.confirmation_token, profile=profile)
    result = run_authorized_pilot(profile=profile, scene_limit=max(REQUIRED_SCENE_COUNT, int(args.scene_limit)))
    output = args.output or (ARTIFACTS / f"director-quality-v2-3-phase-b1-pilot-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(output), "model": safe, "scene_count": result["scene_count"], "summary": result["summary"], "shadow_gate": result["shadow_gate"], "side_effects": result["side_effects"]}, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
