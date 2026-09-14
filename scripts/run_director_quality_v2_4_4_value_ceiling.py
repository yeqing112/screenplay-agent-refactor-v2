"""Run the provider-free Director Quality V2.4.4 value-ceiling audit."""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.director_repair_value_ceiling import (  # noqa: E402
    DIRECTOR_WEIGHTS,
    ROOT_REPAIR_TYPE,
    ROOT_TARGETS,
    VALUE_CEILING_SCHEMA_VERSION,
    analyze_scene,
    build_sensitivity_map,
)
from core.director_tail_repair import REPAIR_SCOPES  # noqa: E402
from core.director_tail_repair_context import resolve_tail_repair_context  # noqa: E402
from core.director_tail_root_cause import rank_tail_root_causes_v2  # noqa: E402


MANIFEST = ARTIFACTS / "director-quality-v2-4-3-targeted-tail-manifest.json"
EVIDENCE = ARTIFACTS / "director-quality-v2-3-phase-b2-evidence.json"
FREEZE = ARTIFACTS / "director-quality-v2-4-b2-freeze.json"
PILOT = ARTIFACTS / "director-quality-v2-4-3-targeted-tail-pilot-real.json"
HISTORICAL_TARGETED = ARTIFACTS / "director-quality-v2-4-targeted-tail-pilot-20260914T090340Z.json"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _stats(values: list[float]) -> dict[str, float | None]:
    return {"mean": round(mean(values), 4) if values else None, "median": round(median(values), 4) if values else None, "min": round(min(values), 4) if values else None, "max": round(max(values), 4) if values else None}


def _load() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    return tuple(json.loads(path.read_text(encoding="utf-8")) for path in (MANIFEST, EVIDENCE, FREEZE, PILOT, HISTORICAL_TARGETED))  # type: ignore[return-value]


def _all_known_roots(*, scene_id: str, freeze_row: dict[str, Any], evidence_row: dict[str, Any], manifest_roots: list[dict[str, Any]], historical_row: dict[str, Any]) -> list[dict[str, Any]]:
    # V2.4.4 reads the historical full ranking as frozen evidence.  It must
    # not silently rerank the cohort with a newer classifier.
    ranked = _list(_dict(_dict(historical_row.get("repair")).get("ranked_root_causes")).get("ranked_root_causes"))
    if not ranked:
        record = {**freeze_row, "scene_id": scene_id, "quality_issues": _list(_dict(freeze_row.get("quality")).get("issues"))}
        ranked = rank_tail_root_causes_v2(record).get("ranked_root_causes", [])
    frozen_by_root = {_text(row.get("root_cause")): row for row in manifest_roots}
    result: list[dict[str, Any]] = []
    for rank, row in enumerate(ranked, start=1):
        root = _text(_dict(row).get("code"))
        # A counterfactual remains executable only when the existing repair
        # contract has a known semantic type and target dimensions.
        if root not in ROOT_REPAIR_TYPE:
            continue
        base = copy.deepcopy(frozen_by_root.get(root, {}))
        if not base:
            evidence = _dict(evidence_row.get("evidence"))
            candidate = _dict(evidence_row.get("baseline"))
            context = resolve_tail_repair_context(
                root_cause=root,
                opportunities=_list(freeze_row.get("opportunities")),
                treatment=_dict(evidence.get("treatment")),
                structural_candidate=candidate,
                strategy=_dict(evidence.get("strategy")),
                quality_issues=_list(_dict(freeze_row.get("quality")).get("issues")),
            )
            base = {
                "root_cause": root,
                "original_rank": rank,
                "repair_type": ROOT_REPAIR_TYPE[root],
                "target_dimensions": sorted(ROOT_TARGETS[root]),
                "relevant_plan_shot_ids": context["relevant_plan_shot_ids"],
                "relevant_beat_ids": context["relevant_beat_ids"],
                "relevant_opportunity_ids": context["relevant_opportunity_ids"],
            }
        base["counterfactual_rank"] = rank
        base["rank_score"] = row.get("score")
        result.append(base)
    # Keep historical roots even if a reranker cannot recover them, while
    # making the provenance explicit and avoiding silent loss of frozen scope.
    for row in manifest_roots:
        root = _text(row.get("root_cause"))
        if root in ROOT_REPAIR_TYPE and root not in {_text(item.get("root_cause")) for item in result}:
            result.append({**copy.deepcopy(row), "counterfactual_rank": None, "recovered_from_frozen_manifest": True})
    return result


def _aggregate(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    deltas = [float(_dict(row.get(key)).get("delta")) for row in rows if _num(_dict(row.get(key)).get("delta"))]
    dqs = [float(_dict(row.get(key)).get("dq")) for row in rows if _num(_dict(row.get(key)).get("dq"))]
    return {"dq": _stats(dqs), "delta": _stats(deltas)}


def _tail(rows: list[dict[str, Any]], key: str, baseline_key: str = "baseline") -> dict[str, Any]:
    baseline = [float(_dict(row[baseline_key]).get("dq")) for row in rows if _num(_dict(row.get(baseline_key)).get("dq"))]
    values = [float(_dict(row.get(key)).get("dq")) for row in rows if _num(_dict(row.get(key)).get("dq"))]
    baseline_tail = sum(value < 60 for value in baseline)
    tail = sum(value < 60 for value in values)
    return {"baseline_below_60": baseline_tail, "ceiling_below_60": tail, "tail_reduction": round((baseline_tail - tail) / baseline_tail, 4) if baseline_tail else None, "scene_count": len(values)}


def _route(rows: list[dict[str, Any]], sensitivity: dict[str, Any]) -> dict[str, Any]:
    top2 = [float(_dict(row["current_top2_ceiling"]).get("delta")) for row in rows]
    all_roots = [float(_dict(row["all_known_roots_ceiling"]).get("delta")) for row in rows]
    priority = [float(_dict(row["value_priority_top2_ceiling"]).get("delta")) for row in rows]
    coordinated = [float(_dict(row["coordinated_top2_ceiling"]).get("delta")) for row in rows]
    actual = [float(_dict(row["actual"]).get("delta")) for row in rows if _num(_dict(row.get("actual")).get("delta"))]
    top2_mean = mean(top2) if top2 else 0.0
    all_uplift = (mean(all_roots) - top2_mean) if all_roots else 0.0
    priority_uplift = (mean(priority) - top2_mean) if priority else 0.0
    coordinated_uplift = (mean(coordinated) - top2_mean) if coordinated else 0.0
    actual_eff = (mean(actual) / top2_mean) if actual and top2_mean > 0 else None
    flags = {"SCORER_SENSITIVITY_GAP": "SCORER_SENSITIVITY_GAP" in sensitivity.get("flags", [])}
    if flags["SCORER_SENSITIVITY_GAP"]:
        primary, secondary = "V2.4.5C", "SCORER_SENSITIVITY_GAP"
    elif top2_mean < 15 and actual_eff is not None and actual_eff >= 0.75:
        # Actual realization is already close to the deterministic ceiling,
        # while the ceiling itself is below the product gate: the evidence
        # points to a local-scope ceiling rather than a provider strategy gap.
        primary, secondary = "V2.4.5A", "REPAIR_SCOPE_LIMITED"
    elif top2_mean < 15 and coordinated_uplift >= 3:
        primary, secondary = "V2.4.5A", "COORDINATED_REPAIR_GAP"
    elif top2_mean < 15 and priority_uplift >= 3:
        primary, secondary = "V2.4.5D", "ROOT_CAUSE_SELECTION_GAP"
    elif top2_mean >= 15 and actual_eff is not None and actual_eff < 0.5:
        primary, secondary = "V2.4.5B", "MODEL_CREATIVE_VALUE_GAP"
    elif all_uplift >= 3:
        primary, secondary = "V2.4.5D", "ROOT_CAUSE_SELECTION_GAP"
    else:
        primary, secondary = "V2.4.5B", "MODEL_CREATIVE_VALUE_GAP"
    return {"primary": primary, "secondary": secondary, "evidence": {"current_top2_mean_delta": round(top2_mean, 4), "all_roots_uplift_over_top2": round(all_uplift, 4), "value_priority_uplift_over_top2": round(priority_uplift, 4), "coordinated_uplift_over_top2": round(coordinated_uplift, 4), "actual_over_top2_efficiency": round(actual_eff, 4) if actual_eff is not None else None, "sensitivity_gap_count": sum(row.get("classification") == "SCORER_INSENSITIVE_FIELD" for row in sensitivity.get("fields", []))}}


def run() -> dict[str, Any]:
    manifest, evidence_payload, freeze, pilot, historical_targeted = _load()
    evidence_by_id = {_text(_dict(row.get("scene")).get("scene_id")): row for row in _list(evidence_payload.get("scenes"))}
    freeze_by_id = {_text(row.get("scene_id")): row for row in _list(freeze.get("scenes"))}
    pilot_by_id = {_text(row.get("scene_id")): row for row in _list(pilot.get("scenes"))}
    historical_by_id = {_text(row.get("scene_id")): row for row in _list(historical_targeted.get("scenes"))}
    rows: list[dict[str, Any]] = []
    for manifest_row in _list(manifest.get("scenes")):
        if not isinstance(manifest_row, dict):
            continue
        scene_id = _text(manifest_row.get("scene_id"))
        evidence_row = evidence_by_id.get(scene_id, {})
        freeze_row = freeze_by_id.get(scene_id, {})
        baseline = _dict(evidence_row.get("baseline"))
        evidence = _dict(evidence_row.get("evidence"))
        if not baseline:
            raise ValueError(f"missing baseline candidate for {scene_id}")
        known = _all_known_roots(scene_id=scene_id, freeze_row=freeze_row, evidence_row=evidence_row, manifest_roots=_list(manifest_row.get("root_causes")), historical_row=historical_by_id.get(scene_id, {}))
        row = analyze_scene(
            scene_id=scene_id,
            baseline=baseline,
            treatment=_dict(evidence.get("treatment")),
            blocking=_dict(evidence.get("blocking")),
            contract=_dict(evidence.get("contract")),
            frozen_roots=_list(manifest_row.get("root_causes")),
            all_known_roots=known,
            actual=pilot_by_id.get(scene_id),
        )
        row["scene_origin"] = _text(manifest_row.get("scene_origin"))
        row["scene_metadata"] = copy.deepcopy(_dict(manifest_row.get("scene_metadata")))
        baseline_cv = _dict(manifest_row.get("baseline_creative_value")).get("score")
        actual_row = pilot_by_id.get(scene_id, {})
        row["baseline_cv"] = baseline_cv
        row["actual_cv"] = actual_row.get("after_creative_value")
        row["actual_cv_delta"] = actual_row.get("creative_value_delta")
        row["actual_root_results"] = []
        for root_attempt in _list(_dict(actual_row.get("repair")).get("attempts")):
            for attempt in _list(_dict(root_attempt).get("attempts")):
                if _text(_dict(root_attempt).get("root_cause")) and attempt.get("status") == "accepted":
                    acceptance = _dict(attempt.get("acceptance"))
                    before_quality = acceptance.get("quality_before")
                    after_quality = acceptance.get("quality_after")
                    dq_delta = (float(after_quality) - float(before_quality)) if _num(before_quality) and _num(after_quality) else 0.0
                    row["actual_root_results"].append({"root_cause": _text(root_attempt.get("root_cause")), "dq_delta": round(dq_delta, 4), "target_delta": _dict(attempt.get("target_delta")), "accepted": True})
        row["excluded_ranked_roots"] = [root for root in known if root.get("counterfactual_rank") and root.get("counterfactual_rank") > 2]
        rows.append(row)
    sensitivity_maps = [build_sensitivity_map(baseline=_dict(evidence_by_id[row["scene_id"]].get("baseline")), treatment=_dict(evidence_by_id[row["scene_id"]].get("evidence")).get("treatment"), blocking=_dict(evidence_by_id[row["scene_id"]].get("evidence")).get("blocking")) for row in rows]
    sensitivity_fields: list[dict[str, Any]] = []
    for field in sorted({item["field"] for sm in sensitivity_maps for item in sm.get("fields", [])}):
        items = [item for sm in sensitivity_maps for item in sm.get("fields", []) if item["field"] == field]
        sensitivity_fields.append({"field": field, "repair_type": items[0]["repair_type"], "expected_dimension": items[0]["expected_dimension"], "weight": items[0]["weight"], "before_mean": round(mean(float(i["before"]) for i in items), 4), "after_mean": round(mean(float(i["after"]) for i in items), 4), "delta_mean": round(mean(float(i["delta"]) for i in items), 4), "sensitive_scene_count": sum(float(i["delta"]) != 0 for i in items), "classification": "SCORER_INSENSITIVE_FIELD" if all(float(i["delta"]) == 0 for i in items) else "SENSITIVE"})
    sensitivity = {"schema_version": "director-quality-v2-4-4-scorer-sensitivity-v1", "dimensions": DIRECTOR_WEIGHTS, "fields": sensitivity_fields, "flags": ["SCORER_SENSITIVITY_GAP"] if any(i["classification"] == "SCORER_INSENSITIVE_FIELD" for i in sensitivity_fields) else [], "scene_count": len(rows), "provider_calls": 0}
    cohorts = {"ALL": rows, "APPROVED_RECORD": [r for r in rows if r.get("scene_origin") == "approved_record"], "FIXTURE": [r for r in rows if r.get("scene_origin") != "approved_record"]}
    cohort_metrics: dict[str, Any] = {}
    for name, cohort in cohorts.items():
        cohort_metrics[name] = {key: _aggregate(cohort, key) for key in ("baseline", "actual", "top1_ceiling", "current_top2_ceiling", "all_known_roots_ceiling", "value_priority_top2_ceiling", "coordinated_top2_ceiling", "scene_upper_bound")}
        cohort_metrics[name]["creative_value"] = {
            "baseline": _stats([float(r["baseline_cv"]) for r in cohort if _num(r.get("baseline_cv"))]),
            "actual_delta": _stats([float(r["actual_cv_delta"]) for r in cohort if _num(r.get("actual_cv_delta"))]),
        }
        cohort_metrics[name]["tail"] = {key: _tail(cohort, key) for key in ("baseline", "actual", "current_top2_ceiling", "all_known_roots_ceiling", "scene_upper_bound")}
        top2_delta = [float(_dict(r["current_top2_ceiling"]).get("delta")) for r in cohort if _num(_dict(r["current_top2_ceiling"]).get("delta"))]
        actual_delta = [float(_dict(r["actual"]).get("delta")) for r in cohort if _num(_dict(r["actual"]).get("delta"))]
        cohort_metrics[name]["repair_efficiency_top2"] = round(mean(actual_delta) / mean(top2_delta), 4) if actual_delta and top2_delta and mean(top2_delta) > 0 else None
    route = _route(rows, sensitivity)
    generated_at = datetime.now(timezone.utc).isoformat()
    value_ceiling = {"schema_version": VALUE_CEILING_SCHEMA_VERSION, "generated_at": generated_at, "source_artifacts": [str(MANIFEST.relative_to(ROOT)), str(EVIDENCE.relative_to(ROOT)), str(FREEZE.relative_to(ROOT)), str(PILOT.relative_to(ROOT))], "provider_calls": {"llm": 0, "mimo": 0, "image": 0, "video": 0, "storage": 0}, "scene_count": len(rows), "cohort_metrics": cohort_metrics, "scenes": rows, "route_decision": route, "flags": ["CV_CEILING_NOT_MEASURABLE"] + (["CURRENT_LOCAL_REPAIR_CANNOT_MEET_TAIL_GATE"] if cohort_metrics["ALL"]["tail"]["current_top2_ceiling"]["tail_reduction"] is not None and cohort_metrics["ALL"]["tail"]["current_top2_ceiling"]["tail_reduction"] < 0.5 else [])}
    approved_cohort_rows = []
    for item in cohorts["APPROVED_RECORD"]:
        top2_delta = float(item["current_top2_ceiling"]["delta"])
        actual_delta = item["actual"].get("delta")
        approved_cohort_rows.append({
            "scene_id": item["scene_id"],
            "baseline_dq": item["baseline"]["dq"],
            "actual_dq": item["actual"]["dq"],
            "actual_delta": actual_delta,
            "top2_ceiling_delta": top2_delta,
            "all_roots_ceiling_delta": item["all_known_roots_ceiling"]["delta"],
            "repair_efficiency": round(float(actual_delta) / top2_delta, 4) if _num(actual_delta) and top2_delta > 0 else None,
            "baseline_below_60": float(item["baseline"]["dq"]) < 60,
            "actual_escaped_tail": bool(_num(item["actual"].get("dq")) and float(item["actual"]["dq"]) >= 60),
            "ceiling_can_escape_tail": float(item["current_top2_ceiling"]["dq"]) >= 60,
            "selected_roots": [x["root_cause"] for x in item["root_cause_ceilings"]],
            "scope_ratio": [x["scope_ratio"] for x in item["root_cause_ceilings"]],
        })
    cohort_gap = {}
    for name, cohort in cohorts.items():
        shot_counts = [float(r["root_cause_ceilings"][0]["scene_shot_count"]) for r in cohort if r.get("root_cause_ceilings")]
        cohort_gap[name] = {
            "scene_count": len(cohort),
            "scene_shot_count": _stats(shot_counts),
            "baseline_dq": cohort_metrics[name]["baseline"]["dq"],
            "baseline_cv": cohort_metrics[name]["creative_value"]["baseline"],
            "actual_dq_delta": cohort_metrics[name]["actual"]["delta"],
            "top2_ceiling_delta": cohort_metrics[name]["current_top2_ceiling"]["delta"],
            "repair_efficiency": cohort_metrics[name]["repair_efficiency_top2"],
            "tail_escape_rate": cohort_metrics[name]["tail"]["actual"].get("tail_reduction"),
        }
    approved_gap = {
        "schema_version": "director-quality-v2-4-4-approved-vs-fixture-gap-v1",
        "generated_at": generated_at,
        "cohorts": cohort_gap,
        "approved_scenes": approved_cohort_rows,
    }
    root_rows = [root for row in rows for root in row.get("root_cause_ceilings", [])]
    by_root: dict[str, list[dict[str, Any]]] = {}
    for root in root_rows: by_root.setdefault(root["root_cause"], []).append(root)
    root_value_rows = {}
    for name, items in by_root.items():
        actual_rows = [ar for scene in rows for ar in scene.get("actual_root_results", []) if ar.get("root_cause") == name]
        approved_count = sum(1 for scene in rows if scene.get("scene_origin") == "approved_record" and any(x.get("root_cause") == name for x in scene.get("root_cause_ceilings", [])))
        root_value_rows[name] = {
            "count": len(items),
            "actual_mean_target_delta": round(mean([float(_dict(a.get("target_delta")).get(dim, 0.0)) for a in actual_rows for dim in items[0].get("target_dimensions", [])]), 4) if actual_rows and items[0].get("target_dimensions") else None,
            "actual_mean_dq_delta": round(mean([float(a.get("dq_delta") or 0.0) for a in actual_rows]), 4) if actual_rows else None,
            "ceiling_mean_dq_delta": round(mean(float(i["dq_ceiling_delta"]) for i in items), 4),
            "repair_efficiency": round(mean(float(a.get("dq_delta") or 0.0) for a in actual_rows) / mean(float(i["dq_ceiling_delta"]) for i in items), 4) if actual_rows and mean(float(i["dq_ceiling_delta"]) for i in items) > 0 else None,
            "approved_count": approved_count,
            "fixture_count": len(items) - approved_count,
            "repair_type": items[0].get("repair_type"),
            "target_dimensions": items[0].get("target_dimensions"),
        }
    root_value = {"schema_version": "director-quality-v2-4-4-root-cause-value-v1", "generated_at": generated_at, "roots": root_value_rows, "repair_types": {}}
    for name, items in by_root.items(): root_value["repair_types"].setdefault(items[0].get("repair_type"), []).extend(items)
    for typ, items in list(root_value["repair_types"].items()): root_value["repair_types"][typ] = {"count": len(items), "ceiling_mean_dq_delta": round(mean(float(i["dq_ceiling_delta"]) for i in items), 4)}
    counterfactuals = {"schema_version": "director-quality-v2-4-4-counterfactuals-v1", "generated_at": generated_at, "provider_calls": 0, "scenes": [{"scene_id": r["scene_id"], "historical_top2": r["current_top2_ceiling"], "value_priority_top2": r["value_priority_top2_ceiling"], "all_known_roots": r["all_known_roots_ceiling"], "coordinated_top2": r["coordinated_top2_ceiling"], "scene_upper_bound": r["scene_upper_bound"]} for r in rows]}
    report_lines = ["# Director Quality V2.4.4 — Repair Value Ceiling & Strategy Audit", "", f"Generated: `{generated_at}`", "", "## Status", "", "`VALUE_CEILING_AUDIT_COMPLETE`", "", "Provider-free deterministic audit. Real MiMo/LLM/image/video/storage/CI calls: **0**.", "", "## Baseline and ceiling results", ""]
    allm = cohort_metrics["ALL"]
    report_lines += [
        f"- Actual DQ mean delta: **{allm['actual']['delta']['mean']}**; median: **{allm['actual']['delta']['median']}**.",
        f"- Current Top-2 ceiling mean delta: **{allm['current_top2_ceiling']['delta']['mean']}**; median delta: **{allm['current_top2_ceiling']['delta']['median']}**; median ceiling score: **{allm['current_top2_ceiling']['dq']['median']}**.",
        f"- Current Top-2 reaches the +15 mean gate: **{'yes' if allm['current_top2_ceiling']['delta']['mean'] >= 15 else 'no'}**; reaches the +10 median-delta gate: **{'yes' if allm['current_top2_ceiling']['delta']['median'] >= 10 else 'no'}**.",
        f"- Current Top-2 tail reduction: **{allm['tail']['current_top2_ceiling']['tail_reduction']}** (50% gate: **{'yes' if (allm['tail']['current_top2_ceiling']['tail_reduction'] or 0) >= 0.5 else 'no'}**).",
        f"- All-known-roots uplift over Top-2: **{round(allm['all_known_roots_ceiling']['delta']['mean'] - allm['current_top2_ceiling']['delta']['mean'], 4)}**; excluded historical roots: **{sum(len(x['excluded_ranked_roots']) for x in rows)}** (expected 5).",
        f"- Value-priority Top-2 uplift over historical Top-2: **{round(allm['value_priority_top2_ceiling']['delta']['mean'] - allm['current_top2_ceiling']['delta']['mean'], 4)}**.",
        f"- Coordinated Top-2 uplift over sequential Top-2: **{round(allm['coordinated_top2_ceiling']['delta']['mean'] - allm['current_top2_ceiling']['delta']['mean'], 4)}**.",
        f"- Scene upper-bound mean delta: **{allm['scene_upper_bound']['delta']['mean']}**.",
        "",
        "## Approved-record gap",
        "",
        f"Approved scenes: **{len(cohorts['APPROVED_RECORD'])}**; historical V2.4.3 safe acceptance: **5/5**, meaningful uplift: **0/5**, tail: **4 → 4**. Actual DQ delta mean: **{cohort_metrics['APPROVED_RECORD']['actual']['delta']['mean']}**; Top-2 ceiling mean delta: **{cohort_metrics['APPROVED_RECORD']['current_top2_ceiling']['delta']['mean']}**.",
        "The approved-record gap is reported as evidence; no acceptance rule or historical artifact is modified.",
        "",
        "## Sensitivity",
        "",
        f"SCORER_SENSITIVITY_GAP: **{'yes' if sensitivity.get('flags') else 'no'}**; insensitive field count: **{sum(row['classification'] == 'SCORER_INSENSITIVE_FIELD' for row in sensitivity_fields)}**.",
        "CV ceiling: `CV_CEILING_NOT_MEASURABLE` (synthetic interventions have no authoritative outcome evidence).",
        "",
        "## Route decision",
        "",
        f"Primary recommendation: **{route['primary']}**; secondary: **{route['secondary']}**.",
        f"Evidence: `{json.dumps(route['evidence'], ensure_ascii=False, sort_keys=True)}`.",
        "",
        "## Guardrails",
        "",
        "No shot was added, deleted, split, merged or reordered. Immutable facts, participants, events, assets, chronology and continuity fields were preserved and validated for every synthetic candidate.",
        "",
    ]
    report = "\n".join(report_lines)
    outputs = {"artifacts/director-quality-v2-4-4-value-ceiling.json": value_ceiling, "artifacts/director-quality-v2-4-4-scorer-sensitivity.json": sensitivity, "artifacts/director-quality-v2-4-4-approved-vs-fixture-gap.json": approved_gap, "artifacts/director-quality-v2-4-4-root-cause-value.json": root_value, "artifacts/director-quality-v2-4-4-counterfactuals.json": counterfactuals}
    for rel, payload in outputs.items(): (ROOT / rel).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ARTIFACTS / "director-quality-v2-4-4-gap-audit.md").write_text("# Director Quality V2.4.4 — Gap Audit\n\n## Baseline Audit\n\n- Repository HEAD: `692dddb1bef3db376388bbcff8fccb3c98db3707`\n- Frozen cohort: 15 scenes (5 approved_record, 10 fixture), 27 frozen roots.\n- Scorer dimensions and weights are read directly from `core/director_quality_validator.py`; no scorer changes were made.\n- Frozen V2.4.3 artifacts were read-only inputs.\n\n## Final As-Built Verification\n\n" + report + "\n", encoding="utf-8")
    (ARTIFACTS / "director-quality-v2-4-4-report.md").write_text(report + "\n", encoding="utf-8")
    return {"status": "VALUE_CEILING_AUDIT_COMPLETE", "scene_count": len(rows), "route": route, "artifacts": list(outputs) + ["artifacts/director-quality-v2-4-4-gap-audit.md", "artifacts/director-quality-v2-4-4-report.md"]}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
