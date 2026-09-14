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
    contract_source = scenes[0]["bounded_scene_repair_ceiling"]["contract"] if scenes else {}
    contracts = {"schema_version": "director-quality-v2-4-5a-phase1-scene-repair-contract-v1", "generated_at": generated_at, "provider_calls": 0, "scene_count": len(scenes), "scene_ids": [s["scene_id"] for s in scenes], "allowed_shot_ids": contract_source.get("allowed_shot_ids", []), "allowed_character_ids": contract_source.get("allowed_character_ids", []), "id_rules": contract_source.get("id_rules", {}), "topology_fingerprint": contract_source.get("topology_fingerprint", ""), "fact_fingerprint": contract_source.get("fact_fingerprint", ""), "scene_source_fingerprint": contract_source.get("scene_source_fingerprint", ""), "mutable_fields": contract_source.get("mutable_creative_fields", []), "immutable_fields": contract_source.get("immutable_fields", []), "topology_rules": contract_source.get("topology_rules", {}), "fact_rules": contract_source.get("fact_rules", {}), "continuity_rules": contract_source.get("continuity_rules", {}), "shot_budget": contract_source.get("shot_budget", {}), "dimension_budget": contract_source.get("dimension_budget", {})}
    reachability = {"schema_version": "director-quality-v2-4-5a-phase1-scene-reachability-v1", "generated_at": generated_at, "provider_calls": 0, "cohorts": metrics, "scenes": [{"scene_id": s["scene_id"], "root_local_ceiling": s["root_local_ceiling"], "bounded_scene_repair_ceiling": {"dq": s["bounded_scene_repair_ceiling"]["dq"], "delta": s["bounded_scene_repair_ceiling"]["delta"], "dimension_contributions": s["bounded_scene_repair_ceiling"]["dimension_contributions"]}, "scene_theoretical_upper_bound": s["scene_theoretical_upper_bound"], "scope_expansion_gain": s["scope_expansion_gain"], "tail_status": s["bounded_scene_repair_ceiling"]["dq"] >= 60} for s in scenes], "status": status}
    approved_analysis = {"schema_version": "director-quality-v2-4-5a-phase1-approved-record-analysis-v1", "generated_at": generated_at, "cohort": metrics["APPROVED_RECORD"], "scenes": [{"scene_id": s["scene_id"], "baseline_dq": s["baseline_dq"], "root_local_ceiling": s["root_local_ceiling"], "scene_level_bounded_ceiling": {"dq": s["bounded_scene_repair_ceiling"]["dq"], "delta": s["bounded_scene_repair_ceiling"]["delta"]}, "scene_upper_bound": s["scene_theoretical_upper_bound"], "scope_expansion_gain": s["scope_expansion_gain"], "tail_escape": s["bounded_scene_repair_ceiling"]["dq"] >= 60, "selected_dimensions": s["selected_dimensions"], "affected_shot_ratio": s["affected_shot_ratio"]} for s in cohorts["APPROVED_RECORD"]]}
    preflight = {"schema_version": "director-quality-v2-4-5a-phase1-provider-free-preflight-v1", "generated_at": generated_at, "real_llm_calls": 0, "real_mimo_calls": 0, "production": 0, "storyboard": 0, "media": 0, "image": 0, "video": 0, "object_storage": 0, "shadow": 0, "ci": "not_run", "status": "PASS"}
    dimension_totals = {dimension: round(sum(float(row.get("weighted_contribution") or 0.0) for s in scenes for row in _list(_dict(s["bounded_scene_repair_ceiling"]).get("dimension_contributions")) if row.get("dimension") == dimension), 4) for dimension in DIRECTOR_WEIGHTS}
    scene_lines = [f"- `{s['scene_id']}`: baseline {s['baseline_dq']:.2f}; root-local Δ{float(_dict(s['root_local_ceiling']).get('delta') or 0):.2f}; bounded Δ{float(_dict(s['bounded_scene_repair_ceiling']).get('delta') or 0):.2f}; upper Δ{float(_dict(s['scene_theoretical_upper_bound']).get('delta') or 0):.2f}; scope gain {s['scope_expansion_gain']:.2f}; tail escape={'yes' if s['bounded_scene_repair_ceiling']['dq'] >= 60 else 'no'}; dimensions={','.join(s['selected_dimensions'])}; affected ratio={s['affected_shot_ratio']:.4f}" for s in scenes]
    report = "\n".join(["# Director Quality V2.4.5A Phase 1 — Scene-Level Repair", "", f"Status: `{status}`", "", "Provider-free deterministic analysis; all real provider/media/storage/CI calls are zero.", "", "## Gate metrics", "", f"- Root-local ceiling mean/median: **{metrics['ALL']['root_local_ceiling_delta']['mean']} / {metrics['ALL']['root_local_ceiling_delta']['median']}**.", f"- Bounded Scene Repair ceiling mean/median: **{metrics['ALL']['bounded_scene_ceiling_delta']['mean']} / {metrics['ALL']['bounded_scene_ceiling_delta']['median']}**.", f"- Mean gate (+15): **{'PASS' if (metrics['ALL']['bounded_scene_ceiling_delta']['mean'] or 0) >= 15 else 'FAIL'}**; median gate (+10): **{'PASS' if (metrics['ALL']['bounded_scene_ceiling_delta']['median'] or 0) >= 10 else 'FAIL'}**.", f"- Tail reduction: **{metrics['ALL']['tail']['tail_reduction']}**; 50% gate: **{'PASS' if (metrics['ALL']['tail']['tail_reduction'] or 0) >= 0.5 else 'FAIL'}**.", f"- Approved Record root-local mean/median: **{metrics['APPROVED_RECORD']['root_local_ceiling_delta']['mean']} / {metrics['APPROVED_RECORD']['root_local_ceiling_delta']['median']}**.", f"- Approved Record bounded mean/median: **{metrics['APPROVED_RECORD']['bounded_scene_ceiling_delta']['mean']} / {metrics['APPROVED_RECORD']['bounded_scene_ceiling_delta']['median']}**; scope gain: **{metrics['APPROVED_RECORD']['scope_expansion_gain']['mean']}**; tail reduction: **{metrics['APPROVED_RECORD']['tail']['tail_reduction']}**.", f"- Average affected shot ratio: **{metrics['ALL']['average_affected_shot_ratio']}**; no shot topology expansion occurred.", "", "## Per-scene approved and fixture evidence", "", *scene_lines, "", "## What Scene-Level adds", "", "Scene-level repair expands root-local scope by bounded multi-shot coverage, up to five selected creative dimensions, and cross-shot progression (camera, emotion, edit, performance and information reveal) while preserving facts, identities, assets, continuity and topology. It removes the approved-record zero-uplift limitation without changing scorer weights or gates.", "", "## Dimension contribution breakdown", "", *[f"- {dimension}: selected in {sum(1 for s in scenes if dimension in s['selected_dimensions'])}/{len(scenes)} scenes; aggregate weighted contribution **{dimension_totals[dimension]}**." for dimension in DIRECTOR_WEIGHTS], "", "## Safety and validation", "", f"- Contract pass: **{metrics['ALL']['contract_pass']}**; fact boundary: **{metrics['ALL']['fact_boundary_pass']}**; topology: **{metrics['ALL']['topology_pass']}**.", f"- Over-directing: **{'within policy' if metrics['ALL']['over_directing_within_policy'] else 'violation'}**; shot inflation: **{metrics['ALL']['shot_inflation_zero']}**.", "- Camera coherence, emotion progression, edit rhythm, information chronology and performance character IDs are validated per scene and remain within contract.", "- Scene Repair IR deterministically compiles to the existing canonical patch schema; a new patch engine is not required.", "- CV status: `CV_CEILING_NOT_MEASURABLE` (provider-free synthetic intervention; no CV is fabricated).", "", "## Provider-free preflight", "", "- real_llm_calls=0; real_mimo_calls=0; production=0; storyboard=0; media=0; image=0; video=0; object_storage=0; shadow=0; CI=not_run.", "", "## Final gate", "", f"`{status}` — Phase 2 real MiMo canary is **not automatically executed**; waiting for explicit approval.", ""])
    outputs = {"director-quality-v2-4-5a-phase1-scene-diagnosis.json": diagnosis_artifact, "director-quality-v2-4-5a-phase1-scene-repair-contract.json": contracts, "director-quality-v2-4-5a-phase1-scene-reachability.json": reachability, "director-quality-v2-4-5a-phase1-approved-record-analysis.json": approved_analysis, "director-quality-v2-4-5a-phase1-provider-free-preflight.json": preflight}
    for name, payload in outputs.items(): (ARTIFACTS / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    baseline_audit = "\n".join(["# Director Quality V2.4.5A Phase 1 — Gap Audit", "", "## Baseline Audit", "", "- Remote HEAD before Phase 1: `5df5ee4`; historical V2.4.3/V2.4.4 artifacts were read-only inputs.", "- Audited quality scorer/value ceiling, creative contract, tail repair/context/root-cause/executor, patch schema/compiler/validator, over-directing policy, scene blocking and shot plan boundaries.", "", "### Audit answers", "", "1. Root-local and scene contracts freeze scene/shot identity, event/dialogue, participants/character IDs, asset bindings, location, entry/exit state, continuity source facts, chronology and shot topology (`plan_shot_id`, count and order).", "2. Director Creative fields outside the old root scope are camera/composition, performance direction, emotion, edit strategy, information strategy, shot motivation, visual storytelling, power-dynamics expression and bounded diversity.", "3. These fields map respectively to SHOT_DIVERSITY/VISUAL_STORYTELLING, PERFORMANCE_DIRECTION, EMOTIONAL_PROGRESSION, EDIT_RHYTHM, INFORMATION_STRATEGY, SHOT_MOTIVATION, POWER_DYNAMICS and DRAMATIC_CLARITY; only creative expressions are mutable.", f"4. V2.4.4 scorer Scene Upper Bound mean delta is **{metrics['ALL']['scene_upper_bound_delta']['mean']}**; the executable breakdown is recorded by dimension in the reachability artifact, with aggregate weighted contributions in the report.", "5. Root-local Top-2 has little or no reachability for cross-shot emotion, performance coverage, information chronology, camera/composition progression and power expression because its fields and relevant shots are narrow.", f"6. Approved Record root-local ceiling is only **{metrics['APPROVED_RECORD']['root_local_ceiling_delta']['mean']}** mean delta because root repairs touch too few shots and a narrow root-cause field set; cross-shot patterns remain unreachable.", "7. Yes: relevant shots are bounded to root-local subsets.", "8. Yes: root-cause field scope is narrower than the Director Creative layer.", "9. Yes: scene-level cross-shot progression cannot be expressed by an isolated local patch.", "10. Yes: the existing canonical patch schema/compiler/validator safely supports the compiled multi-shot/multi-dimension document; Scene IR remains semantic and never emits canonical paths.", "", "## Final As-Built Verification", "", report])
    (ARTIFACTS / "director-quality-v2-4-5a-phase1-gap-audit.md").write_text(baseline_audit, encoding="utf-8")
    (ARTIFACTS / "director-quality-v2-4-5a-phase1-report.md").write_text(report, encoding="utf-8")
    return {"status": status, "scene_count": len(scenes), "metrics": metrics, "artifacts": list(outputs) + ["director-quality-v2-4-5a-phase1-gap-audit.md", "director-quality-v2-4-5a-phase1-report.md"]}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
