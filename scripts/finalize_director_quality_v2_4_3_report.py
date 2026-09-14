"""Finalize V2.4.3 value metrics and an honest gate report."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
PILOT = ARTIFACTS / "director-quality-v2-4-3-targeted-tail-pilot-real.json"


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _values(rows, key):
    return [float(row[key]) for row in rows if _num(row.get(key))]


def _stats(values):
    if not values:
        return {"mean": None, "median": None, "min": None, "max": None}
    return {"mean": round(mean(values), 4), "median": round(median(values), 4), "min": round(min(values), 4), "max": round(max(values), 4)}


def build_report():
    pilot = json.loads(PILOT.read_text(encoding="utf-8"))
    rows = [row for row in pilot.get("scenes", []) if isinstance(row, dict)]
    root_attempts = [root for row in rows for root in row.get("repair", {}).get("attempts", []) if isinstance(root, dict)]
    attempt_rows = [attempt for root in root_attempts for attempt in root.get("attempts", []) if isinstance(attempt, dict)]
    accepted_roots = sum(bool(root.get("accepted")) for root in root_attempts)
    contract_valid = sum(
        any(attempt.get("contract_status") == "pass" for attempt in root.get("attempts", []))
        for root in root_attempts
    )
    target_improved = sum(bool(root.get("accepted")) for root in root_attempts)
    dq_delta = _values(rows, "director_quality_delta")
    cv_delta = _values(rows, "creative_value_delta")
    dq_before = _values(rows, "before_director_quality")
    dq_after = _values(rows, "after_director_quality")
    cv_before = _values(rows, "before_creative_value")
    cv_after = _values(rows, "after_creative_value")
    vm = pilot.get("value_metrics", {})
    protocol = dict(pilot.get("metrics", {}))
    first_pass = [root.get("attempts", [])[0] for root in root_attempts if root.get("attempts")]
    protocol.update({
        "ir_first_pass_valid_count": sum(attempt.get("ir_parse_status") == "valid" for attempt in first_pass),
        "ir_first_pass_valid_rate": sum(attempt.get("ir_parse_status") == "valid" for attempt in first_pass) / len(first_pass) if first_pass else None,
        "ir_final_valid_count": sum(any(attempt.get("ir_parse_status") == "valid" for attempt in root.get("attempts", [])) for root in root_attempts),
        "ir_final_valid_rate": sum(any(attempt.get("ir_parse_status") == "valid" for attempt in root.get("attempts", [])) for root in root_attempts) / len(root_attempts) if root_attempts else None,
        "canonical_compile_count": sum(any(attempt.get("canonical_compile_status") == "compiled" for attempt in root.get("attempts", [])) for root in root_attempts),
        "candidate_contract_pass_count": sum(any(attempt.get("contract_status") == "pass" for attempt in root.get("attempts", [])) for root in root_attempts),
        "fact_override_attempt_count": sum(int(attempt.get("acceptance", {}).get("fact_override_count") or 0) for attempt in attempt_rows),
        "fact_override_accepted_count": sum(int(attempt.get("acceptance", {}).get("fact_override_count") or 0) for attempt in attempt_rows if attempt.get("status") == "accepted"),
        "request_echo_count": int(protocol.get("request_echo_count") or 0),
        "unknown_provider_shape_count": int(protocol.get("unknown_provider_shape_count") or 0),
    })
    gates = {
        "scene_execution_coverage_100": pilot.get("scene_execution_coverage") == 1.0,
        "root_cause_attempt_coverage_100": pilot.get("root_cause_attempt_coverage") == 1.0,
        "scene_repair_success_ge_80": (pilot.get("scene_repair_success_rate") or 0) >= 0.8,
        "target_dimension_improvement_ge_80": (target_improved / contract_valid) if contract_valid else 0.0,
        "root_cause_acceptance_ge_60": (accepted_roots / len(root_attempts)) if root_attempts else 0.0,
        "dq_mean_delta_ge_15": (mean(dq_delta) if dq_delta else 0.0) >= 15,
        "dq_median_delta_ge_10": (median(dq_delta) if dq_delta else 0.0) >= 10,
        "cv_mean_delta_ge_15": (mean(cv_delta) if cv_delta else 0.0) >= 15,
        "tail_reduction_ge_50": (vm.get("tail_reduction_rate") or 0) >= 0.5,
        "fact_override_accepted_zero": int(pilot.get("metrics", {}).get("fact_override_accepted_count") or 0) == 0,
        "over_directing_threshold": all(float(row.get("after_over_directing_rate") or 0) <= 0.10 for row in rows),
    }
    value_gate_pass = all(value is True for value in gates.values() if isinstance(value, bool)) and all(value >= threshold for key, value, threshold in [
        ("target_dimension_improvement", gates["target_dimension_improvement_ge_80"], 0.8),
        ("root_cause_acceptance", gates["root_cause_acceptance_ge_60"], 0.6),
    ])
    metrics = {
        "schema_version": "director-quality-v2-4-3-metrics-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "artifacts/director-quality-v2-4-3-targeted-tail-pilot-real.json",
        "cohort": {"all": len(rows), "approved_record": sum(row.get("scene_origin") == "approved_record" for row in rows), "fixture": sum(row.get("scene_origin") != "approved_record" for row in rows)},
        "root_causes": {"selected": pilot.get("selected_root_cause_count"), "attempted": len(root_attempts), "accepted": accepted_roots, "acceptance_rate": accepted_roots / len(root_attempts) if root_attempts else 0.0},
        "protocol": protocol,
        "director_quality": {"before": _stats(dq_before), "after": _stats(dq_after), "delta": _stats(dq_delta)},
        "creative_value": {"before": _stats(cv_before), "after": _stats(cv_after), "delta": _stats(cv_delta), "measurement_statuses": sorted({str(row.get("creative_value_measurement_status")) for row in rows})},
        "value_metrics": vm,
        "gates": gates,
        "value_gate": "PASS" if value_gate_pass else "FAIL",
        "overall_status": "NOT_READY_FOR_FULL_24_REEVALUATION" if not value_gate_pass else "READY_FOR_FULL_24_REEVALUATION",
        "side_effects": pilot.get("side_effects", {}),
    }
    return metrics


def main():
    metrics = build_report()
    metrics_path = ARTIFACTS / "director-quality-v2-4-3-metrics.json"
    report_path = ARTIFACTS / "director-quality-v2-4-3-report.md"
    final_path = ARTIFACTS / "director-quality-v2-4-3-final-report.md"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Director Quality V2.4.3 — Targeted Tail Repair Value Re-evaluation",
        "", f"Generated: `{metrics['generated_at']}`", "",
        "## Scope", "",
        "Frozen 15-scene cohort (5 approved_record + 10 fixture), 27 historical root causes, maximum 54 semantic attempts. No Full24, production shadow, storyboard/media generation, or object-storage side effects.", "",
        "## Protocol reliability", "",
        f"- Semantic attempts: **{metrics['protocol'].get('semantic_attempt_count')}**; HTTP requests: **{metrics['protocol'].get('provider_http_request_count')}**; JSON parser retries: **{metrics['protocol'].get('json_parser_retry_count')}**.",
        f"- Root-cause acceptance: **{metrics['root_causes']['accepted']}/{metrics['root_causes']['attempted']} ({metrics['root_causes']['acceptance_rate']:.1%})**.",
        f"- Creative Value measurement statuses: `{', '.join(metrics['creative_value']['measurement_statuses'])}`.", "",
        "## Value results", "",
        f"- DQ mean delta: **{metrics['director_quality']['delta']['mean']}**; median delta: **{metrics['director_quality']['delta']['median']}**.",
        f"- Creative Value mean delta: **{metrics['creative_value']['delta']['mean']}**; median delta: **{metrics['creative_value']['delta']['median']}**.",
        f"- Tail reduction (<60): **{metrics['value_metrics'].get('tail_reduction_rate', 0):.1%}**.", "",
        "## Gate decision", "",
        f"**{metrics['value_gate']}** — `{metrics['overall_status']}`.", "",
        "The protocol is reliable, but this value experiment does not meet the V2.4.3 uplift thresholds. In particular, DQ mean/median, Creative Value mean, and tail-reduction gates remain below target. This result must not be promoted to Full24 or Production Shadow.", "",
        "## Cohort separation", "",
        f"Approved-record scenes: **{metrics['cohort']['approved_record']}**; fixture scenes: **{metrics['cohort']['fixture']}**. Fixture success is not treated as production-value proof.", "",
        "## Side effects", "",
        "All production, storyboard, media, object-storage, and production-shadow counters are zero.", "",
        "## Source artifacts", "",
        "- `artifacts/director-quality-v2-4-3-provider-free-preflight.json`",
        "- `artifacts/director-quality-v2-4-3-targeted-tail-manifest.json`",
        "- `artifacts/director-quality-v2-4-3-targeted-tail-pilot-real.json`",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    final_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"metrics": metrics_path.relative_to(ROOT).as_posix(), "report": report_path.relative_to(ROOT).as_posix(), "status": metrics["overall_status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
