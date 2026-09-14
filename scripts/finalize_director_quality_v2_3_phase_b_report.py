"""Finalize Director Quality V2.3 Phase B artifacts without provider calls.

The command consumes the B1 and B2 pilot JSON artifacts only.  It never calls
an LLM and never mutates production state.  A missing/incomplete B2 artifact
is represented as ``NOT_READY`` rather than being treated as a successful
pilot.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
DEFAULT_B1 = ARTIFACTS / "director-quality-v2-3-phase-b1-pilot-20260914T030654Z.json"
DEFAULT_B2 = ARTIFACTS / "director-quality-v2-3-phase-b2-pilot.json"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _stats(values: list[float]) -> dict[str, float | None]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {key: None for key in ("min", "p10", "p25", "median", "p75", "p90", "max")}

    def nearest(percentile: float) -> float:
        index = max(0, min(len(ordered) - 1, int(math.ceil(percentile * len(ordered))) - 1))
        return round(ordered[index], 4)

    middle = len(ordered) // 2
    median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return {
        "min": round(ordered[0], 4),
        "p10": nearest(0.10),
        "p25": nearest(0.25),
        "median": round(median, 4),
        "p75": nearest(0.75),
        "p90": nearest(0.90),
        "max": round(ordered[-1], 4),
    }


def _load(path: Path | None) -> dict[str, Any] | None:
    if not path or not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def _scene_scores(pilot: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for row in _list(pilot.get("scenes")):
        if not isinstance(row, dict):
            continue
        score = _number(row.get("director_quality_score"))
        if score is not None:
            values.append(score)
    return values


def _pilot_summary(pilot: dict[str, Any] | None) -> dict[str, Any]:
    if not pilot:
        return {"available": False, "scene_count": 0}
    summary = _dict(pilot.get("summary"))
    quality = _dict(summary.get("director_quality"))
    scores = _scene_scores(pilot)
    distribution = _stats(scores)
    # Preserve provider-reported values while filling missing distribution
    # fields from scene rows for older artifacts.
    quality_distribution = {**distribution, **{key: value for key, value in quality.items() if _number(value) is not None}}
    return {
        "available": True,
        "protocol_version": pilot.get("protocol_version"),
        "pilot_mode": pilot.get("pilot_mode"),
        "scene_count": int(pilot.get("scene_count") or len(scores)),
        "model": _dict(pilot.get("model")),
        "quality": quality_distribution,
        "creative_value": _dict(summary.get("creative_value")),
        "summary": summary,
        "shadow_gate": _dict(pilot.get("shadow_gate")),
        "side_effects": _dict(pilot.get("side_effects")),
        "telemetry": _dict(pilot.get("telemetry")),
        "production_shadow": _dict(pilot.get("production_shadow")),
        "opportunity_analysis": _dict(_dict(pilot.get("artifacts")).get("opportunity_analysis")),
        "tail_analysis": _dict(_dict(pilot.get("artifacts")).get("tail_analysis")),
    }


def build_final_metrics(*, b1: dict[str, Any] | None, b2: dict[str, Any] | None, b1_path: Path | None = None, b2_path: Path | None = None) -> dict[str, Any]:
    phase_a = _pilot_summary(b1)
    phase_b = _pilot_summary(b2)
    reasons: list[str] = []
    if not phase_b["available"]:
        reasons.append("Phase B2 real MiMo artifact is missing")
    elif phase_b["scene_count"] < 24:
        reasons.append(f"Phase B2 contains {phase_b['scene_count']} scenes; minimum is 24")
    gate = _dict(phase_b.get("shadow_gate"))
    status = _text(gate.get("status")) if gate else "NOT_READY"
    if status not in {"NOT_READY", "SAFE_BUT_NOT_VALUABLE", "VALUABLE_ENOUGH_TO_SHADOW"}:
        status = "NOT_READY"
    if reasons:
        status = "NOT_READY"
    summary = _dict(phase_b.get("summary"))
    side_effects = phase_b.get("side_effects") if isinstance(phase_b.get("side_effects"), dict) else {}
    telemetry = phase_b.get("telemetry") if isinstance(phase_b.get("telemetry"), dict) else {}
    return {
        "protocol_version": "director-quality-v2-3-phase-b-final",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "reasons": reasons,
        "sources": {"phase_a": str(b1_path) if b1_path else None, "phase_b1": str(b1_path) if b1_path else None, "phase_b2": str(b2_path) if b2_path else None},
        "phase_a": phase_a,
        "phase_b2": phase_b,
        "metrics": {
            "contract_pass_rate": _number(summary.get("contract_pass_rate")),
            "director_quality": phase_b.get("quality", {}),
            "creative_value": _dict(summary.get("creative_value")),
            "opportunity_detection_coverage": _number(summary.get("opportunity_detection_coverage")),
            "eligible_opportunity_count": int(summary.get("eligible_opportunity_count") or 0),
            "acted_opportunity_count": int(summary.get("acted_opportunity_count") or 0),
            "useful_accepted_count": int(summary.get("useful_accepted_count") or 0),
            "valid_skip_count": int(summary.get("valid_skip_count") or 0),
            "missed_opportunity_count": int(summary.get("missed_opportunity_count") or 0),
            "useful_creative_acceptance": _number(summary.get("useful_creative_acceptance")),
            "valid_skip_rate": _number(summary.get("valid_skip_rate")),
            "missed_opportunity_rate": _number(summary.get("missed_opportunity_rate")),
            "edit_strategy_eligible_coverage": _number(summary.get("edit_strategy_eligible_coverage")),
            "emotion_arc_eligible_coverage": _number(summary.get("emotion_arc_eligible_coverage")),
            "information_strategy_eligible_coverage": _number(summary.get("information_strategy_eligible_coverage")),
            "tail_repair_trigger_rate": _number(summary.get("tail_repair_trigger_rate")),
            "tail_repair_attempted_count": int(summary.get("tail_repair_attempted_count") or 0),
            "tail_repair_success_rate": _number(summary.get("tail_repair_success_rate")),
            "over_directing_rate": _number(summary.get("over_directing_rate")),
            "shot_inflation_rate": _number(summary.get("shot_inflation_rate")),
            "unknown_root_cause_count": int(summary.get("unknown_root_cause_count") or 0),
        },
        "safety": {
            "side_effects": side_effects,
            "production_shadow_enabled": bool(_dict(phase_b.get("production_shadow")).get("enabled")),
            "unknown_root_cause_count": int(summary.get("unknown_root_cause_count") or 0),
        },
        "telemetry": telemetry,
        "shadow_gate": gate,
    }


def _text(value: Any) -> str:
    return str(value or "").strip()


def render_report(metrics: dict[str, Any]) -> str:
    m = _dict(metrics.get("metrics")); q = _dict(m.get("director_quality")); cv = _dict(m.get("creative_value")); phase_a = _dict(metrics.get("phase_a")); phase_b = _dict(metrics.get("phase_b2"))
    lines = [
        "# Director Quality V2.3 Phase B Report",
        "",
        f"Status: **{metrics.get('status', 'NOT_READY')}**",
        "",
        "## Executive Summary",
        "",
        f"- Phase A scenes: `{phase_a.get('scene_count', 0)}`; Phase B2 scenes: `{phase_b.get('scene_count', 0)}`",
        f"- Contract Pass Rate: `{m.get('contract_pass_rate')}`",
        f"- Director Quality mean / median / P10 / min: `{q.get('mean')}` / `{q.get('median')}` / `{q.get('p10')}` / `{q.get('min')}`",
        f"- Creative Value mean: `{cv.get('mean')}`",
        "",
        "## Opportunity and Strategy Coverage",
        "",
        f"- Eligible / ACT / useful accepted / valid skip / missed: `{m.get('eligible_opportunity_count')}` / `{m.get('acted_opportunity_count')}` / `{m.get('useful_accepted_count')}` / `{m.get('valid_skip_count')}` / `{m.get('missed_opportunity_count')}`",
        f"- Useful Creative Acceptance: `{m.get('useful_creative_acceptance')}`",
        f"- Edit / Emotion / Information eligible coverage: `{m.get('edit_strategy_eligible_coverage')}` / `{m.get('emotion_arc_eligible_coverage')}` / `{m.get('information_strategy_eligible_coverage')}`",
        "",
        "## Tail, Safety and Shadow Gate",
        "",
        f"- Tail Repair trigger / attempted / success: `{m.get('tail_repair_trigger_rate')}` / `{m.get('tail_repair_attempted_count')}` / `{m.get('tail_repair_success_rate')}`",
        f"- Over-directing / shot inflation: `{m.get('over_directing_rate')}` / `{m.get('shot_inflation_rate')}`",
        f"- Unknown root cause: `{m.get('unknown_root_cause_count')}`",
        f"- Shadow Gate: `{_dict(metrics.get('shadow_gate')).get('status', 'NOT_READY')}`",
        f"- Production Shadow enabled: `{_dict(metrics.get('safety')).get('production_shadow_enabled')}`",
        "",
        "## Interpretation",
        "",
        "This report is artifact-driven. Missing or incomplete B2 evidence remains NOT_READY; no offline or partial result is promoted to a Shadow candidate.",
    ]
    return "\n".join(lines) + "\n"


def write_final_artifacts(*, metrics: dict[str, Any], output_dir: Path = ARTIFACTS) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = output_dir / "director-quality-v2-3-phase-b-metrics.json"
    report_path = output_dir / "director-quality-v2-3-phase-b-report.md"
    opportunity_path = output_dir / "director-quality-v2-3-opportunity-analysis.json"
    tail_path = output_dir / "director-quality-v2-3-tail-analysis.json"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(render_report(metrics), encoding="utf-8")
    phase_b = _dict(metrics.get("phase_b2"))
    opportunity_path.write_text(json.dumps({"protocol_version": "director-quality-v2-3-opportunity-analysis", "status": metrics.get("status"), "source": phase_b.get("opportunity_analysis", {})}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tail_path.write_text(json.dumps({"protocol_version": "director-quality-v2-3-tail-analysis", "status": metrics.get("status"), "source": phase_b.get("tail_analysis", {})}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"metrics": str(metrics_path), "report": str(report_path), "opportunity_analysis": str(opportunity_path), "tail_analysis": str(tail_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize provider-free Director Quality V2.3 Phase B report")
    parser.add_argument("--phase-a", type=Path, default=None)
    parser.add_argument("--phase-b1", type=Path, default=DEFAULT_B1)
    parser.add_argument("--phase-b2", type=Path, default=DEFAULT_B2)
    parser.add_argument("--output-dir", type=Path, default=ARTIFACTS)
    args = parser.parse_args(argv)
    b1 = _load(args.phase_b1)
    b2 = _load(args.phase_b2)
    metrics = build_final_metrics(b1=b1, b2=b2, b1_path=args.phase_b1, b2_path=args.phase_b2)
    outputs = write_final_artifacts(metrics=metrics, output_dir=args.output_dir)
    print(json.dumps({"status": metrics["status"], "outputs": outputs, "reasons": metrics["reasons"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
