"""Build Director Quality V2.4 reports from a frozen B2 artifact.

This command is intentionally offline.  It never imports the provider
runtime, never calls an LLM, and never writes production/storyboard/media or
object-storage state.  It is the report/replay runner used before the guarded
Targeted Tail Pilot.
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
DEFAULT_PILOT = ARTIFACTS / "director-quality-v2-3-phase-b2-pilot-20260914T040506Z.json"
DEFAULT_EVIDENCE = ARTIFACTS / "director-quality-v2-3-phase-b2-evidence.json"
# This replay consumes a frozen historical B2 package produced on the
# historical branch below.  Keep that source identity explicit instead of
# accidentally stamping the branch used to run today's offline replay.
HISTORICAL_SOURCE_GIT_CONTEXT = {"branch": "codex/unify-formal-workspace"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _repo_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _contract_failures(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from core.director_contract_failure import aggregate_contract_failures, build_contract_failure

    failures: list[dict[str, Any]] = []
    for row in rows:
        detailed = _list(row.get("contract_failures"))
        if detailed:
            failures.extend(build_contract_failure(item, plan_shot_id=_text(item.get("plan_shot_id") or item.get("target_id"))) for item in detailed if isinstance(item, dict))
            continue
        rejected_count = int(_dict(row.get("validation")).get("rejected_patch_count") or 0)
        # Older B2 rows only persisted a count, not field-level error records.
        # Preserve that limitation explicitly instead of inventing a code/path.
        for index in range(rejected_count):
            failures.append(build_contract_failure({
                "code": "UNKNOWN_CONTRACT_FAILURE",
                "message": "B2 source artifact omitted field-level rejection details",
                "target_id": _text(row.get("scene_id")),
                "path": "",
                "category": "UNKNOWN_CONTRACT_FAILURE",
                "source_index": index,
            }))
    return aggregate_contract_failures(failures)


def _trace_for_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from core.director_intervention_trace import build_intervention_trace

    records: list[dict[str, Any]] = []
    for row in rows:
        existing = _dict(row.get("intervention_trace"))
        if _list(existing.get("records")):
            records.extend(_list(existing.get("records")))
            continue
        opportunities = [item for item in _list(row.get("opportunities")) if isinstance(item, dict)]
        if not opportunities:
            continue
        outcomes = {"%s" % _text(item.get("opportunity_id")): _text(item.get("final_status")) for item in _list(row.get("opportunity_outcomes")) if isinstance(item, dict)}
        scene_trace = build_intervention_trace(
            opportunities=opportunities,
            planner_decisions=row.get("planner_decisions") or [],
            compilation=row.get("compilation") or {},
            validation=row.get("validation") or {},
            final_statuses=outcomes,
        )
        records.extend(_list(scene_trace.get("records")))
    counts: dict[str, int] = {}
    for item in records:
        status = _text(_dict(item).get("final_status"))
        if status:
            counts[status] = counts.get(status, 0) + 1
    return {
        "schema_version": "director_opportunity_intervention_trace_v1",
        "records": records,
        "trace_complete": all(_text(_dict(item).get("opportunity_id")) and _text(_dict(item).get("final_status")) for item in records),
        "eligible_count": sum(1 for item in records if bool(_dict(item).get("eligible"))),
        "summary": dict(sorted(counts.items())),
    }


def build_offline_replay(*, pilot_path: Path, evidence_path: Path) -> dict[str, Any]:
    from core.director_conversion_funnel import build_conversion_funnel
    from core.director_quality_provenance import build_provenance
    from core.director_quality_v24_metrics import build_director_quality_v24_metrics
    from core.director_success_tail_comparison import compare_success_tail
    from core.director_shadow_gate import evaluate_shadow_gate, get_shadow_gate_policy

    pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
    rows = [item for item in _list(pilot.get("scenes")) if isinstance(item, dict)]
    trace = _trace_for_rows(rows)
    funnel = build_conversion_funnel(trace)
    failures = _contract_failures(rows)
    comparison = compare_success_tail(rows)
    summary = _dict(pilot.get("summary"))
    quality = _dict(summary.get("director_quality"))
    creative = _dict(summary.get("creative_value"))
    policy = get_shadow_gate_policy()
    gate = evaluate_shadow_gate(
        contract_pass_rate=summary.get("contract_pass_rate"),
        fact_override_accepted=summary.get("fact_override_accepted_count", 0),
        unknown_root_cause_count=summary.get("unknown_root_cause_count", 0),
        director_quality_mean=quality.get("mean"), director_quality_median=quality.get("median"),
        director_quality_p10=quality.get("p10"), director_quality_min=quality.get("min"),
        creative_value_mean=creative.get("mean"), creative_value_median=creative.get("median"),
        useful_creative_acceptance=summary.get("useful_creative_acceptance"),
        edit_strategy_eligible_coverage=summary.get("edit_strategy_eligible_coverage"),
        emotion_arc_eligible_coverage=summary.get("emotion_arc_eligible_coverage"),
        information_strategy_eligible_coverage=summary.get("information_strategy_eligible_coverage"),
        over_directing_rate=summary.get("over_directing_rate"),
        shot_inflation_rate=summary.get("shot_inflation_rate"),
    )
    metrics = build_director_quality_v24_metrics(
        scenes=rows,
        funnel=funnel,
        contract_metrics={
            **failures,
            "patch_contract_first_pass_rate": summary.get("patch_contract_first_pass_rate"),
            "patch_contract_final_pass_rate": summary.get("patch_contract_final_pass_rate"),
        },
        creative_value_metrics=summary,
        tail_metrics={
            "execution_coverage": summary.get("tail_repair_execution_coverage", 0.0),
            "success_rate": summary.get("tail_repair_success_rate"),
            "before_mean": quality.get("mean"),
            "after_mean": quality.get("mean"),
        },
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    provenance = build_provenance(
        protocol_version="director-quality-v2-4-offline-replay",
        model=pilot.get("model"),
        model_profile=pilot.get("model"),
        scenes=rows,
        source_artifacts=[pilot_path, evidence_path],
        evidence_path=evidence_path,
        gate_version=_text(gate.get("schema_version")),
        metric_schema_version=_text(metrics.get("schema_version")),
        generated_at=generated_at,
        git_context_override=HISTORICAL_SOURCE_GIT_CONTEXT,
    )
    return {
        "protocol_version": "director-quality-v2-4-offline-replay",
        "generated_at": generated_at,
        "scene_count": len(rows),
        "source": {"pilot": _repo_path(pilot_path), "evidence": _repo_path(evidence_path)},
        "provenance": provenance,
        "policy": policy,
        "gate": gate,
        "trace": trace,
        "funnel": funnel,
        "contract_failures": failures,
        "comparison": comparison,
        "metrics": metrics,
        "scenes": rows,
        "side_effects": {"production": 0, "storyboard": 0, "media": 0, "object_storage": 0, "production_shadow": 0},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Director Quality V2.4 replay")
    parser.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output-dir", type=Path, default=ARTIFACTS)
    args = parser.parse_args(argv)
    result = build_offline_replay(pilot_path=args.pilot, evidence_path=args.evidence)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outputs = {
        "provenance": args.output_dir / "director-quality-v2-4-provenance-audit.json",
        "contract_failures": args.output_dir / "director-quality-v2-4-contract-failures.json",
        "funnel": args.output_dir / "director-quality-v2-4-conversion-funnel.json",
        "comparison": args.output_dir / "director-quality-v2-4-success-tail-comparison.json",
        "metrics": args.output_dir / "director-quality-v2-4-metrics.json",
        "replay": args.output_dir / f"director-quality-v2-4-offline-replay-{stamp}.json",
    }
    _write(outputs["provenance"], result["provenance"])
    _write(outputs["contract_failures"], result["contract_failures"])
    _write(outputs["funnel"], result["funnel"])
    _write(outputs["comparison"], result["comparison"])
    _write(outputs["metrics"], result["metrics"])
    _write(outputs["replay"], result)
    print(json.dumps({"status": "offline_replay_complete", "outputs": {key: _repo_path(value) for key, value in outputs.items()}, "scene_count": result["scene_count"], "shadow_gate": result["gate"], "side_effects": result["side_effects"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
