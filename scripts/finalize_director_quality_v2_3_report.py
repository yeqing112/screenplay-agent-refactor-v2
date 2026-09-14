"""Build the Director Quality V2.3 metrics/report from recorded artifacts.

The command is provider-free.  It only reads JSON artifacts and writes the
two final report artifacts; it cannot trigger LLM, media, production, or
storage work.  Missing real runs remain ``NOT_READY`` instead of being
silently treated as a pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
DEFAULT_OFFLINE = ARTIFACTS / "director-quality-v2-3-offline-benchmark-current.json"
DEFAULT_SAMPLES = ARTIFACTS / "director-quality-v2-3-variance-samples.json"

TARGETS = {
    "performance_direction_coverage": 0.85,
    "edit_strategy_coverage": 0.80,
    "emotion_arc_coverage": 0.90,
    "information_strategy_coverage": 0.85,
    "useful_creative_acceptance_rate": 0.80,
    "director_quality_mean": 70.0,
    "director_quality_median": 70.0,
    "quality_delta": 15.0,
    "improved_run_count": 2,
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"artifact must be a JSON object: {path}")
    return value


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _value_from_stats(stats: dict[str, Any], key: str) -> float | None:
    value = _number(stats.get(key))
    return value


def _coverage_means(aggregate: dict[str, Any], variant: str = "B") -> dict[str, float | None]:
    return {
        key: _value_from_stats(_dict(_dict(aggregate.get("coverage")).get(variant)), "mean")
        for key in (
            "performance_direction_coverage",
            "edit_strategy_coverage",
            "emotion_arc_coverage",
            "information_strategy_coverage",
            "useful_creative_acceptance_rate",
        )
    }


def _aggregate_payload(offline: dict[str, Any], samples_payload: dict[str, Any] | None) -> dict[str, Any]:
    from core.director_quality_v23_benchmark import aggregate_variance, samples_from_offline_benchmark

    if samples_payload and isinstance(samples_payload.get("samples"), list):
        return aggregate_variance(samples_payload["samples"])
    return aggregate_variance(samples_from_offline_benchmark(offline, run_id=1))


def build_metrics(*, offline: dict[str, Any], aggregate: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    quality_b = _dict(_dict(aggregate.get("quality")).get("B"))
    delta = _dict(aggregate.get("paired_delta"))
    coverage = _coverage_means(aggregate)
    safety = _dict(aggregate.get("safety"))
    side_effects = _dict(safety.get("side_effects"))
    side_effect_total = sum(int(value or 0) for value in side_effects.values() if isinstance(value, (int, float)) and not isinstance(value, bool))
    quality_checks = {
        "director_quality_mean": _value_from_stats(quality_b, "mean"),
        "director_quality_median": _value_from_stats(quality_b, "median"),
        "quality_delta": _value_from_stats(delta, "mean"),
        "coverage": coverage,
        "improved_run_count": int(aggregate.get("improved_run_count") or 0),
        "independent_run_count": int(aggregate.get("independent_run_count") or 0),
    }
    safety_gate = {
        "final_contract_pass_rate": safety.get("final_contract_pass_rate"),
        "fact_override_accepted": int(safety.get("fact_override_accepted") or 0),
        "side_effect_total": side_effect_total,
        "passed": safety.get("final_contract_pass_rate") == 1.0 and int(safety.get("fact_override_accepted") or 0) == 0 and side_effect_total == 0,
    }
    checks = {
        "director_quality_mean": quality_checks["director_quality_mean"] is not None and quality_checks["director_quality_mean"] >= TARGETS["director_quality_mean"],
        "director_quality_median": quality_checks["director_quality_median"] is not None and quality_checks["director_quality_median"] >= TARGETS["director_quality_median"],
        "quality_delta": quality_checks["quality_delta"] is not None and quality_checks["quality_delta"] >= TARGETS["quality_delta"],
        "improved_runs": quality_checks["improved_run_count"] >= TARGETS["improved_run_count"] and quality_checks["independent_run_count"] >= 3,
        "coverage": {key: value is not None and value >= TARGETS[key] for key, value in coverage.items()},
    }
    coverage_pass = all(checks["coverage"].values())
    value_gate = {
        "passed": bool(safety_gate["passed"] and checks["director_quality_mean"] and checks["director_quality_median"] and checks["quality_delta"] and checks["improved_runs"] and coverage_pass),
        "checks": checks,
    }
    return {
        "protocol_version": "director-quality-v2-3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "READY_TO_SHADOW" if value_gate["passed"] else "NOT_READY",
        "sources": sources,
        "safety": safety_gate,
        "quality": {
            "director_quality_mean": quality_checks["director_quality_mean"],
            "director_quality_median": quality_checks["director_quality_median"],
            "director_quality_stddev": _value_from_stats(quality_b, "stddev"),
            "director_quality_p25": _value_from_stats(quality_b, "p25"),
            "director_quality_p75": _value_from_stats(quality_b, "p75"),
            "paired_delta": delta,
            "dimensions": _dict(_dict(aggregate.get("dimension_stats")).get("B")),
        },
        "coverage": coverage,
        "stability": {
            "independent_run_count": quality_checks["independent_run_count"],
            "improved_run_count": quality_checks["improved_run_count"],
            "degraded_run_count": int(aggregate.get("degraded_run_count") or 0),
            "per_scene_paired_delta": aggregate.get("per_scene_paired_delta") or {},
            "run_comparisons": aggregate.get("run_comparisons") or [],
            "variance": aggregate.get("variance") or {},
        },
        "cost": aggregate.get("cost") or {},
        "gates": {"safe_to_shadow": safety_gate["passed"], "valuable_enough_to_shadow": value_gate["passed"], "safety": safety_gate, "value": value_gate},
        "offline_reference": _dict(offline.get("quality")),
    }


def render_report(metrics: dict[str, Any]) -> str:
    quality = _dict(metrics.get("quality"))
    safety = _dict(metrics.get("safety"))
    stability = _dict(metrics.get("stability"))
    coverage = _dict(metrics.get("coverage"))
    lines = [
        "# Director Quality V2.3 Report",
        "",
        f"Status: **{metrics.get('status', 'NOT_READY')}**",
        "",
        "## Safety",
        "",
        f"- Final Contract Pass Rate: `{safety.get('final_contract_pass_rate')}`",
        f"- Fact Override Accepted: `{safety.get('fact_override_accepted')}`",
        f"- Side-effect total: `{safety.get('side_effect_total')}`",
        f"- SAFE_TO_SHADOW: `{_dict(metrics.get('gates')).get('safe_to_shadow')}`",
        "",
        "## Quality and Coverage",
        "",
        f"- Director Quality mean / median: `{quality.get('director_quality_mean')}` / `{quality.get('director_quality_median')}`",
        f"- Paired delta mean: `{_dict(quality.get('paired_delta')).get('mean')}`",
    ]
    for key, value in coverage.items():
        lines.append(f"- {key}: `{value}`")
    lines += [
        "",
        "## Stability",
        "",
        f"- Independent runs: `{stability.get('independent_run_count')}`",
        f"- Improved runs: `{stability.get('improved_run_count')}`",
        f"- Degraded runs: `{stability.get('degraded_run_count')}`",
        "",
        "## Interpretation",
        "",
        "This report is artifact-driven. Missing real MiMo runs or missing paired samples remain NOT_READY; offline deterministic results are not treated as real-provider evidence.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize provider-free Director Quality V2.3 report")
    parser.add_argument("--offline", type=Path, default=DEFAULT_OFFLINE)
    parser.add_argument("--samples", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=ARTIFACTS)
    args = parser.parse_args(argv)
    offline = _load(args.offline)
    sample_payload = _load(args.samples) if args.samples else None
    aggregate = _aggregate_payload(offline, sample_payload)
    metrics = build_metrics(offline=offline, aggregate=aggregate, sources={"offline": str(args.offline), "samples": str(args.samples) if args.samples else None})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = args.output_dir / "director-quality-v2-3-metrics.json"
    report_path = args.output_dir / "director-quality-v2-3-report.md"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(render_report(metrics), encoding="utf-8")
    print(json.dumps({"status": metrics["status"], "metrics": str(metrics_path), "report": str(report_path), "safe_to_shadow": metrics["gates"]["safe_to_shadow"], "valuable_enough_to_shadow": metrics["gates"]["valuable_enough_to_shadow"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
