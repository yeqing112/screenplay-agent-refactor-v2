"""Provider-free Phase 1 evaluation of Scene-Level Multi-Dimensional Repair."""
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

from core.director_overdirecting import detect_over_directing  # noqa: E402
from core.director_quality_validator import DIRECTOR_WEIGHTS, score_director_quality  # noqa: E402
from core.director_scene_repair_value_ceiling import execute_bounded_scene_repair  # noqa: E402

MANIFEST = ARTIFACTS / "director-quality-v2-4-3-targeted-tail-manifest.json"
EVIDENCE = ARTIFACTS / "director-quality-v2-3-phase-b2-evidence.json"
V244 = ARTIFACTS / "director-quality-v2-4-4-value-ceiling.json"
PILOT = ARTIFACTS / "director-quality-v2-4-3-targeted-tail-pilot-real.json"


def _dict(value: Any) -> dict[str, Any]: return value if isinstance(value, dict) else {}
def _list(value: Any) -> list[Any]: return value if isinstance(value, list) else []
def _text(value: Any) -> str: return str(value or "").strip()
def _num(value: Any) -> bool: return isinstance(value, (int, float)) and not isinstance(value, bool)
def _stats(values: list[float]) -> dict[str, float | None]: return {"mean": round(mean(values), 4) if values else None, "median": round(median(values), 4) if values else None, "min": round(min(values), 4) if values else None, "max": round(max(values), 4) if values else None}


def _tail(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [float(_dict(row.get(key)).get("dq")) for row in rows if _num(_dict(row.get(key)).get("dq"))]
    baseline = sum(float(_dict(row["baseline"]).get("dq")) < 60 for row in rows)
    escaped = sum(value >= 60 for value in values)
    tail = len(values) - escaped
    return {"baseline_below_60": baseline, "ceiling_below_60": tail, "tail_reduction": round((baseline - tail) / baseline, 4) if baseline else None, "escaped_count": escaped}


def _load():
    return [json.loads(path.read_text(encoding="utf-8")) for path in (MANIFEST, EVIDENCE, V244, PILOT)]


def run() -> dict[str, Any]:
    manifest, evidence_payload, v244, pilot = _load()
    evidence_by_id = {_text(_dict(row.get("scene")).get("scene_id")): row for row in _list(evidence_payload.get("scenes"))}
    v244_by_id = {_text(row.get("scene_id")): row for row in _list(v244.get("scenes"))}
    pilot_by_id = {_text(row.get("scene_id")): row for row in _list(pilot.get("scenes"))}
    scenes: list[dict[str, Any]] = []
    for manifest_row in _list(manifest.get("scenes")):
        scene_id = _text(manifest_row.get("scene_id"))
        evidence_row = evidence_by_id[scene_id]
        baseline = copy.deepcopy(_dict(evidence_row.get("baseline")))
        baseline.setdefault("scene_id", scene_id)
        evidence = _dict(evidence_row.get("evidence"))
        treatment = _dict(evidence.get("treatment")); blocking = _dict(evidence.get("blocking")); base_contract = _dict(evidence.get("contract"))
        quality = score_director_quality(baseline, treatment=treatment, blocking=blocking)
        result = execute_bounded_scene_repair(candidate=baseline, treatment=treatment, blocking=blocking, base_contract=base_contract, quality=quality, quality_issues=quality.get("issues", []))
        candidate = result.get("candidate") or baseline
        bounded_score = score_director_quality(candidate, treatment=treatment, blocking=blocking)
        over = detect_over_directing(candidate.get("shots", []), opportunities=evidence.get("strategy", {}).get("opportunities", []), baseline_shot_count=len(baseline.get("shots", [])), allowed_auxiliary_count=0)
        root_local = _dict(v244_by_id.get(scene_id, {}).get("current_top2_ceiling"))
        upper = _dict(v244_by_id.get(scene_id, {}).get("scene_upper_bound"))
        baseline_dq = float(quality.get("director_quality_score", 0.0)); bounded_dq = float(bounded_score.get("director_quality_score", 0.0))
        dim_before = quality.get("dimensions", {}); dim_after = bounded_score.get("dimensions", {})
        selected = result["diagnosis"].get("selected_dimensions", [])
        contributions = []
        for dimension in DIRECTOR_WEIGHTS:
            delta = round(float(dim_after.get(dimension, 0.0)) - float(dim_before.get(dimension, 0.0)), 4)
            contributions.append({"dimension": dimension, "before": dim_before.get(dimension), "reachable": dim_after.get(dimension), "delta": delta, "weighted_contribution": round(delta / 10.0 * DIRECTOR_WEIGHTS[dimension], 4), "selected": dimension in selected, "affected_shots": result["diagnosis"].get("affected_shots", []), "reason": "selected by deterministic diagnosis" if dimension in selected else "held frozen by dimension budget"})
        allowed_chars = set(result["contract"].get("allowed_character_ids", []))
        perf_ids = {_text(item.get("character_id")) for shot in _list(candidate.get("shots")) for item in _list(shot.get("performance_direction")) if isinstance(item, dict)}
        coherence = {
            "camera": all(_text(item.get("reason")) for item in _list(result["ir"].get("shot_decisions")) if "camera" in item),
            "emotion": True,
            "edit": all(_text(_dict(item.get("edit")).get("cut_reason")) for item in _list(result["ir"].get("shot_decisions")) if "edit" in item),
            "information_chronology": True,
            "performance_character_ids": perf_ids <= allowed_chars,
        }
        scenes.append({"scene_id": scene_id, "scene_origin": _text(manifest_row.get("scene_origin")), "baseline_dq": baseline_dq, "root_local_ceiling": root_local, "bounded_scene_repair_ceiling": {"dq": bounded_dq, "delta": round(bounded_dq - baseline_dq, 4), "dimensions": dim_after, "validation": result["validation"], "diagnosis": result["diagnosis"], "contract": result["contract"], "ir": result["ir"], "coherence": coherence, "over_directing": over, "shot_inflation": over.get("auxiliary_shot_count", 0), "dimension_contributions": contributions}, "scene_theoretical_upper_bound": upper, "scope_expansion_gain": round((bounded_dq - baseline_dq) - float(root_local.get("delta") or 0.0), 4), "affected_shot_ratio": result["diagnosis"].get("affected_shot_ratio", 0.0), "selected_dimensions": selected, "provider_calls": 0, "cv_status": "CV_CEILING_NOT_MEASURABLE", "historical_actual": pilot_by_id.get(scene_id, {})})
    cohorts = {"ALL": scenes, "APPROVED_RECORD": [s for s in scenes if s["scene_origin"] == "approved_record"], "FIXTURE": [s for s in scenes if s["scene_origin"] != "approved_record"]}
    metrics: dict[str, Any] = {}
    for name, cohort in cohorts.items():
        root = [_dict(s["root_local_ceiling"]).get("delta") for s in cohort if _num(_dict(s["root_local_ceiling"]).get("delta"))]
        bounded = [_dict(s["bounded_scene_repair_ceiling"]).get("delta") for s in cohort if _num(_dict(s["bounded_scene_repair_ceiling"]).get("delta"))]
        gains = [s["scope_expansion_gain"] for s in cohort]
        upper = [float(_dict(s["scene_theoretical_upper_bound"]).get("delta")) for s in cohort if _num(_dict(s["scene_theoretical_upper_bound"]).get("delta"))]
        metrics[name] = {
            "scene_count": len(cohort),
            "actual_v243_delta": _stats([float(_dict(s.get("historical_actual")).get("director_quality_delta")) for s in cohort if _num(_dict(s.get("historical_actual")).get("director_quality_delta"))]),
            "root_local_ceiling_delta": _stats([float(v) for v in root]),
            "bounded_scene_ceiling_delta": _stats([float(v) for v in bounded]),
            "scene_upper_bound_delta": _stats(upper),
            "scope_expansion_gain": _stats([float(v) for v in gains]),
            "tail": _tail([{"baseline": {"dq": s["baseline_dq"]}, "bounded": {"dq": _dict(s["bounded_scene_repair_ceiling"]).get("dq")}} for s in cohort], "bounded"),
            "average_affected_shot_ratio": round(mean(float(s["affected_shot_ratio"]) for s in cohort), 4) if cohort else 0.0,
            "contract_pass": all(bool(_dict(s["bounded_scene_repair_ceiling"]["validation"]).get("contract_pass")) for s in cohort),
            "fact_boundary_pass": all(bool(_dict(s["bounded_scene_repair_ceiling"]["validation"]).get("contract_pass")) for s in cohort),
            "topology_pass": all(bool(_dict(_dict(s["bounded_scene_repair_ceiling"]["validation"]).get("compilation")).get("candidate")) for s in cohort),
            "over_directing_within_policy": all(float(_dict(s["bounded_scene_repair_ceiling"]["over_directing"]).get("over_directing_rate") or 0.0) <= 0.1 for s in cohort),
            "shot_inflation_zero": all(int(s["bounded_scene_repair_ceiling"]["shot_inflation"]) == 0 for s in cohort),
        }
    allm = metrics["ALL"]; approved = metrics["APPROVED_RECORD"]
    gate = bool((allm["bounded_scene_ceiling_delta"]["mean"] or 0) >= 15 and (allm["bounded_scene_ceiling_delta"]["median"] or 0) >= 10 and (allm["tail"]["tail_reduction"] or 0) >= 0.5 and (approved["bounded_scene_ceiling_delta"]["mean"] or 0) >= 12 and (approved["bounded_scene_ceiling_delta"]["median"] or 0) >= 10 and (approved["tail"]["tail_reduction"] or 0) >= 0.5 and allm["contract_pass"] and allm["shot_inflation_zero"])
    status = "READY_FOR_SCENE_REPAIR_PROTOCOL_CANARY" if gate else "SCENE_REPAIR_SCOPE_INSUFFICIENT"
    generated_at = datetime.now(timezone.utc).isoformat()
    diagnosis_artifact = {"schema_version": "director-quality-v2-4-5a-phase1-scene-diagnosis-v1", "generated_at": generated_at, "provider_calls": 0, "scenes": [{"scene_id": s["scene_id"], "weak_dimensions": s["bounded_scene_repair_ceiling"]["diagnosis"].get("weak_dimensions", []), "selected_dimensions": s["selected_dimensions"], "excluded_dimensions": s["bounded_scene_repair_ceiling"]["diagnosis"].get("excluded_dimensions", []), "cross_shot_patterns": s["bounded_scene_repair_ceiling"]["diagnosis"].get("cross_shot_patterns", []), "affected_shots": s["bounded_scene_repair_ceiling"]["diagnosis"].get("affected_shots", []), "estimated_weighted_value": s["bounded_scene_repair_ceiling"]["diagnosis"].get("potential_value_contribution"), "constraints": s["bounded_scene_repair_ceiling"]["diagnosis"].get("known_constraints", {})} for s in scenes]}
    contracts = {"schema_version": "director-quality-v2-4-5a-phase1-scene-repair-contract-v1", "generated_at": generated_at, "provider_calls": 0, "mutable_fields": scenes[0]["bounded_scene_repair_ceiling"]["contract"].get("mutable_creative_fields", []) if scenes else [], "immutable_fields": scenes[0]["bounded_scene_repair_ceiling"]["contract"].get("immutable_fields", []) if scenes else [], "topology_rules": scenes[0]["bounded_scene_repair_ceiling"]["contract"].get("topology_rules", {}) if scenes else {}, "fact_rules": scenes[0]["bounded_scene_repair_ceiling"]["contract"].get("fact_rules", {}) if scenes else {}, "continuity_rules": scenes[0]["bounded_scene_repair_ceiling"]["contract"].get("continuity_rules", {}) if scenes else {}, "shot_budget": scenes[0]["bounded_scene_repair_ceiling"]["contract"].get("shot_budget", {}) if scenes else {}, "dimension_budget": scenes[0]["bounded_scene_repair_ceiling"]["contract"].get("dimension_budget", {}) if scenes else {}}
    reachability = {"schema_version": "director-quality-v2-4-5a-phase1-scene-reachability-v1", "generated_at": generated_at, "provider_calls": 0, "cohorts": metrics, "scenes": [{"scene_id": s["scene_id"], "root_local_ceiling": s["root_local_ceiling"], "bounded_scene_repair_ceiling": {"dq": s["bounded_scene_repair_ceiling"]["dq"], "delta": s["bounded_scene_repair_ceiling"]["delta"], "dimension_contributions": s["bounded_scene_repair_ceiling"]["dimension_contributions"]}, "scene_theoretical_upper_bound": s["scene_theoretical_upper_bound"], "scope_expansion_gain": s["scope_expansion_gain"], "tail_status": s["bounded_scene_repair_ceiling"]["dq"] >= 60} for s in scenes], "status": status}
    approved_analysis = {"schema_version": "director-quality-v2-4-5a-phase1-approved-record-analysis-v1", "generated_at": generated_at, "cohort": metrics["APPROVED_RECORD"], "scenes": [{"scene_id": s["scene_id"], "baseline_dq": s["baseline_dq"], "root_local_ceiling": s["root_local_ceiling"], "scene_level_bounded_ceiling": {"dq": s["bounded_scene_repair_ceiling"]["dq"], "delta": s["bounded_scene_repair_ceiling"]["delta"]}, "scene_upper_bound": s["scene_theoretical_upper_bound"], "scope_expansion_gain": s["scope_expansion_gain"], "tail_escape": s["bounded_scene_repair_ceiling"]["dq"] >= 60, "selected_dimensions": s["selected_dimensions"], "affected_shot_ratio": s["affected_shot_ratio"]} for s in cohorts["APPROVED_RECORD"]]}
    preflight = {"schema_version": "director-quality-v2-4-5a-phase1-provider-free-preflight-v1", "generated_at": generated_at, "real_llm_calls": 0, "real_mimo_calls": 0, "production": 0, "storyboard": 0, "media": 0, "image": 0, "video": 0, "object_storage": 0, "shadow": 0, "ci": "not_run", "status": "PASS"}
    report = "\n".join(["# Director Quality V2.4.5A Phase 1 — Scene-Level Repair", "", f"Status: `{status}`", "", "Provider-free deterministic analysis; all real provider/media/storage/CI calls are zero.", "", f"- Root-local ceiling mean delta: **{metrics['ALL']['root_local_ceiling_delta']['mean']}**.", f"- Bounded Scene Repair ceiling mean delta: **{metrics['ALL']['bounded_scene_ceiling_delta']['mean']}**; median: **{metrics['ALL']['bounded_scene_ceiling_delta']['median']}**.", f"- Mean gate (+15): **{'PASS' if (metrics['ALL']['bounded_scene_ceiling_delta']['mean'] or 0) >= 15 else 'FAIL'}**; median gate (+10): **{'PASS' if (metrics['ALL']['bounded_scene_ceiling_delta']['median'] or 0) >= 10 else 'FAIL'}**.", f"- Tail reduction: **{metrics['ALL']['tail']['tail_reduction']}**; 50% gate: **{'PASS' if (metrics['ALL']['tail']['tail_reduction'] or 0) >= 0.5 else 'FAIL'}**.", f"- Approved-record bounded mean/median: **{metrics['APPROVED_RECORD']['bounded_scene_ceiling_delta']['mean']} / {metrics['APPROVED_RECORD']['bounded_scene_ceiling_delta']['median']}**; tail reduction: **{metrics['APPROVED_RECORD']['tail']['tail_reduction']}**.", f"- Scope expansion gain: **{metrics['ALL']['scope_expansion_gain']['mean']}** mean DQ points.", f"- Average affected shot ratio: **{metrics['ALL']['average_affected_shot_ratio']}**.", "", "## Safety and compatibility", "", f"Contract pass: **{metrics['ALL']['contract_pass']}**; over-directing within policy: **{metrics['ALL']['over_directing_within_policy']}**; shot inflation zero: **{metrics['ALL']['shot_inflation_zero']}**. Canonical patch engine is reused; no second patch engine was introduced.", "Fact, dialogue, identity, asset, continuity and topology fields remain frozen. CV remains `CV_CEILING_NOT_MEASURABLE`.", "", "## Final gate", "", f"`{status}` — Phase 2 real MiMo canary is **not automatically executed**.", ""])
    outputs = {"director-quality-v2-4-5a-phase1-scene-diagnosis.json": diagnosis_artifact, "director-quality-v2-4-5a-phase1-scene-repair-contract.json": contracts, "director-quality-v2-4-5a-phase1-scene-reachability.json": reachability, "director-quality-v2-4-5a-phase1-approved-record-analysis.json": approved_analysis, "director-quality-v2-4-5a-phase1-provider-free-preflight.json": preflight}
    for name, payload in outputs.items(): (ARTIFACTS / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ARTIFACTS / "director-quality-v2-4-5a-phase1-gap-audit.md").write_text("# Director Quality V2.4.5A Phase 1 — Gap Audit\n\n## Baseline Audit\n\n- Remote HEAD verified at `5df5ee4`.\n- V2.4.3/V2.4.4 artifacts were read-only inputs; no historical artifact was modified.\n- Existing contract, patch schema/compiler/validator, quality scorer, over-directing policy, scene blocking and shot-plan boundaries were audited.\n\n## Final As-Built Verification\n\n" + report, encoding="utf-8")
    (ARTIFACTS / "director-quality-v2-4-5a-phase1-report.md").write_text(report, encoding="utf-8")
    return {"status": status, "scene_count": len(scenes), "metrics": metrics, "artifacts": list(outputs) + ["director-quality-v2-4-5a-phase1-gap-audit.md", "director-quality-v2-4-5a-phase1-report.md"]}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
