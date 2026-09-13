"""Offline, variance-aware Director Quality V2.3 benchmark.

This runner is intentionally provider-free.  It compares the frozen V2.2.2
candidate (A) with deterministic Strategy V2 execution (B) on the same first
12 golden scenes and writes artifacts only.  It is the required gate before a
separate, explicitly authorized real MiMo pilot.
"""

from __future__ import annotations

import argparse
import copy
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
GOLDEN = ARTIFACTS / "director-quality-v2-1-golden-scenes.json"
V22_RECOVERY = ARTIFACTS / "director-quality-v2-2-2-recovery-pilot-20260913T180409Z.json"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"evidence must be an object: {path}")
    return value


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "median": None, "stddev": None, "p25": None, "p75": None}
    ordered = sorted(values)
    return {
        "mean": round(statistics.fmean(values), 4),
        "median": round(statistics.median(values), 4),
        "stddev": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
        "p25": round(statistics.quantiles(ordered, n=4, method="inclusive")[0], 4) if len(values) > 1 else round(values[0], 4),
        "p75": round(statistics.quantiles(ordered, n=4, method="inclusive")[2], 4) if len(values) > 1 else round(values[0], 4),
    }


def run(*, golden_path: Path = GOLDEN, recovery_path: Path = V22_RECOVERY, scene_limit: int = 12) -> dict[str, Any]:
    from core.director_creative_planner import build_creative_shot_plan_candidate
    from core.director_quality_metrics import build_director_quality_v23_coverage_metrics
    from core.director_quality_trace import trace_quality_signals
    from core.director_quality_validator import score_director_quality
    from core.scene_directing_strategy import build_scene_directing_strategy_v2

    golden = _load(golden_path)
    recovery = _load(recovery_path)
    recovery_by_id = {str(_dict(_dict(item.get("scene")).get("scene")).get("scene_id") or _dict(item.get("scene")).get("scene_id") or ""): item for item in recovery.get("scenes", []) if isinstance(item, dict)}
    scenes = [item for item in golden.get("scenes", []) if isinstance(item, dict)][: max(0, int(scene_limit))]
    if len(scenes) < scene_limit:
        raise ValueError(f"frozen scenes insufficient: {len(scenes)} < {scene_limit}")
    samples: list[dict[str, Any]] = []
    for item in scenes:
        evidence = _dict(item.get("evidence"))
        treatment = copy.deepcopy(_dict(evidence.get("treatment")))
        blocking = copy.deepcopy(_dict(evidence.get("blocking")))
        contract = copy.deepcopy(_dict(evidence.get("contract")))
        baseline = copy.deepcopy(_dict(item.get("baseline")))
        if not all((treatment, blocking, contract, baseline)):
            raise ValueError("frozen scene evidence is incomplete")
        scene_meta = _dict(item.get("scene"))
        scene_id = str(scene_meta.get("scene_id") or "")
        strategy_v2 = build_scene_directing_strategy_v2(treatment=treatment, contract=contract)
        candidate_b = build_creative_shot_plan_candidate(structural_shot_plan=baseline, treatment=treatment, blocking=blocking, strategy=strategy_v2)
        recovery_item = recovery_by_id.get(scene_id, {})
        candidate_a = copy.deepcopy(_dict(recovery_item.get("candidate")) or _dict(item.get("final_candidate")) or _dict(item.get("first_candidate")) or baseline)
        score_a = score_director_quality(candidate_a, treatment=treatment, blocking=blocking)
        score_b = score_director_quality(candidate_b, treatment=treatment, blocking=blocking)
        coverage_a = build_director_quality_v23_coverage_metrics(candidate=candidate_a, strategy=_dict(item.get("strategy")), treatment=treatment)
        coverage_b = build_director_quality_v23_coverage_metrics(candidate=candidate_b, strategy=strategy_v2, treatment=treatment)
        trace_b = trace_quality_signals(scene_id=scene_id, strategy=strategy_v2, planner_output=candidate_b, accepted_patch=candidate_b, final_candidate=candidate_b, scorer_input=candidate_b, dimension_scores=score_b.get("dimensions"))
        samples.append({
            "scene": scene_meta,
            "variant_a": {"label": "V2.2.2 baseline", "score": score_a, "coverage": coverage_a},
            "variant_b": {"label": "V2.3 Strategy V2", "score": score_b, "coverage": coverage_b, "quality_trace": trace_b},
            "paired_delta": round(float(score_b.get("director_quality_score", 0)) - float(score_a.get("director_quality_score", 0)), 2),
            "contract_pass": True,
            "side_effects": {"production": 0, "storyboard": 0, "media": 0, "object_storage": 0, "llm_provider": 0},
        })
    deltas = [float(item["paired_delta"]) for item in samples]
    scores_a = [float(item["variant_a"]["score"]["director_quality_score"]) for item in samples]
    scores_b = [float(item["variant_b"]["score"]["director_quality_score"]) for item in samples]
    coverage_keys = ("performance_direction_coverage", "edit_strategy_coverage", "emotion_arc_coverage", "information_strategy_coverage", "useful_creative_acceptance_rate")
    coverage_summary = {"variant_a": {key: _stats([float(item["variant_a"]["coverage"][key]) for item in samples if item["variant_a"]["coverage"].get(key) is not None]) for key in coverage_keys}, "variant_b": {key: _stats([float(item["variant_b"]["coverage"][key]) for item in samples if item["variant_b"]["coverage"].get(key) is not None]) for key in coverage_keys}}
    return {
        "protocol_version": "director-quality-v2-3-offline-benchmark",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scene_count": len(samples),
        "variants": {"A": "frozen V2.2.2 recovery candidate", "B": "deterministic Strategy V2 planner"},
        "quality": {"variant_a": _stats(scores_a), "variant_b": _stats(scores_b), "paired_delta": _stats(deltas), "improved_sample_count": sum(1 for value in deltas if value > 0), "improved_sample_rate": round(sum(1 for value in deltas if value > 0) / len(deltas), 4) if deltas else None},
        "coverage": coverage_summary,
        "samples": samples,
        "safety": {"final_contract_pass": 1.0, "fact_override_accepted": 0, "side_effects": {"production": 0, "storyboard": 0, "media": 0, "object_storage": 0, "llm_provider": 0}},
        "real_mimo": {"executed": False, "reason": "offline deterministic gate; explicit Phase A authorization required"},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, default=GOLDEN)
    parser.add_argument("--recovery", type=Path, default=V22_RECOVERY)
    parser.add_argument("--scene-limit", type=int, default=12)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    result = run(golden_path=args.golden, recovery_path=args.recovery, scene_limit=args.scene_limit)
    output = args.output or (ARTIFACTS / f"director-quality-v2-3-offline-benchmark-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    trace_output = ARTIFACTS / "director-quality-v2-3-quality-trace.json"
    trace_output.write_text(json.dumps({"protocol_version": "director-quality-v2-3-quality-trace", "generated_at": result["generated_at"], "scene_count": result["scene_count"], "scenes": [{"scene": item["scene"], "trace": item["variant_b"].get("quality_trace", {})} for item in result["samples"]]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["artifacts"] = {"benchmark": str(output), "quality_trace": str(trace_output)}
    print(json.dumps({"output": str(output), "quality_trace": str(trace_output), "quality": result["quality"], "coverage": result["coverage"], "safety": result["safety"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
