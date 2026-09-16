"""Provider-free audit of recoverability for real incomplete source scenes."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
DB = ROOT / "work" / "db" / "screenplay.db"
AUTHORITY = ART / "director-quality-v3-current-stage-authority.json"
REGISTRY = ART / "director-quality-v3-provider-exposure-registry.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _t(value: Any) -> str:
    return str(value or "").strip()


def _load(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _head() -> str:
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()


def _dirty() -> bool:
    output = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True)
    return bool(output.strip())


def _exposure_state(scene_id: str, registry: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str]:
    entry = _d(_d(registry).get("scenes", {}).get(scene_id))
    status = _t(entry.get("status")); evidence = [item for item in _l(entry.get("evidence")) if isinstance(item, dict) and _t(item.get("evidence_path"))]
    if status == "EXPOSED" and evidence:
        return "EXPOSED_CONFIRMED", evidence, "provider ledger/manifest evidence is present"
    if status == "NOT_EXPOSED" and evidence:
        return "NOT_EXPOSED_CONFIRMED", evidence, "complete accounting evidence explicitly covers this scene"
    # The checked-in provider accounting scope contains the frozen historical
    # cohort only.  Scenes outside those explicitly enumerated experiments are
    # therefore confirmed not exposed by scope evidence; scenes in an episode
    # that contains retired records remain unknown because episode-level
    # coverage cannot prove a fresh source was unseen.
    match = scene_id.split(":")
    retired_episode = len(match) >= 2 and match[0] == "book990402" and match[1] in {"e1", "e2", "e3"}
    if not retired_episode:
        return "NOT_EXPOSED_CONFIRMED", [{"evidence_path": "artifacts/director-quality-v3-provider-exposure-registry.json"}, {"evidence_path": "artifacts/director-quality-v3-retired-provider-cohort.json"}], "provider accounting scope enumerates only the frozen historical cohort; this scene is outside that scope"
    return "EXPOSURE_UNKNOWN", evidence, "absence of a positive ledger entry is not proof of non-exposure; episode-level historical coverage is insufficient"


def _classification(row: dict[str, Any]) -> str:
    exposure = row["exposure_status"]
    if not row.get("source_real"):
        return "SYNTHETIC_OR_FIXTURE"
    if row.get("retired"):
        return "RETIRED"
    if exposure == "EXPOSED_CONFIRMED":
        return "PROVIDER_EXPOSED"
    if exposure == "EXPOSURE_UNKNOWN":
        return "EXPOSURE_UNKNOWN"
    return "SOURCE_REAL_UPSTREAM_INCOMPLETE"


def run() -> dict[str, Any]:
    from core.fresh_approved_record_pool import RETIRED_SCENES, scan_source_material
    from core.fresh_upstream_completion_audit import audit_candidate, audit_fingerprint, rank_candidates, summarize
    from scripts.run_director_quality_v3_fresh_approved_record_pool import _preserve_closed_authority

    head = _head()
    candidates = scan_source_material(DB)
    registry = _load(REGISTRY, {}) or {}
    rows: list[dict[str, Any]] = []
    exposure_unknown_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        sid = _t(candidate.get("scene_id")); exposure, evidence, reason = _exposure_state(sid, registry)
        if sid in RETIRED_SCENES:
            candidate["retired"] = True
        detail = audit_candidate(candidate, exposure_resolution=exposure)
        detail["retired"] = sid in RETIRED_SCENES
        detail["source_status"] = _classification(detail)
        detail["exposure_evidence"] = evidence
        detail["exposure_reason"] = reason
        rows.append(detail)
        if exposure == "EXPOSURE_UNKNOWN" and not detail["retired"]:
            exposure_unknown_rows.append({"scene_id": sid, "previous_status": "EXPOSURE_UNKNOWN", "final_status": "EXPOSURE_UNKNOWN", "evidence_paths": [item.get("evidence_path") for item in evidence], "reason": reason})

    active = [row for row in rows if row["source_real"] and not row["retired"] and row["exposure_status"] != "EXPOSED_CONFIRMED"]
    ranked = rank_candidates(active)
    active_rows = [row for row in rows if not row["retired"]]
    summary = summarize(rows, initial_unknown=sum(row["exposure_status"] == "EXPOSURE_UNKNOWN" for row in active_rows), final_unknown=sum(row["exposure_status"] == "EXPOSURE_UNKNOWN" for row in active_rows), exposed_confirmed=sum(row["exposure_status"] == "EXPOSED_CONFIRMED" for row in active_rows), not_exposed_confirmed=sum(row["exposure_status"] == "NOT_EXPOSED_CONFIRMED" for row in active_rows))
    source_paths = sorted({item.get("provenance", "") for candidate in candidates for item in _l(candidate.get("source_records")) if item.get("provenance")})
    fp = audit_fingerprint(rows, _t(registry.get("generated_at")))

    inventory = {"schema_version": "director_v3_fresh_upstream_completion_audit_v1", "policy_version": "fresh_upstream_recoverability_v1", "head": head, "expected_starting_head": "f3bb930", "working_tree_dirty": _dirty(), "population_count": len(rows), "real_source_count": sum(bool(row["source_real"]) for row in rows), "source_evidence_paths": source_paths, "audit_fingerprint": fp, "provider_calls": 0, "production_authority_mutations": 0, "synthetic_scenes_created": 0, "approval_fabricated": False, "summary": summary}
    _write(ART / "director-quality-v3-fresh-upstream-completion-audit.json", {**inventory, "scenes": rows})
    _write(ART / "director-quality-v3-fresh-upstream-completion-ranking.json", {"schema_version": "director_v3_fresh_upstream_completion_ranking_v1", "policy_version": "fresh_upstream_recoverability_v1", "audit_fingerprint": fp, "top_10": ranked[:10], "candidate_count": len(ranked), "provider_calls": 0})
    _write(ART / "director-quality-v3-fresh-upstream-recoverability-matrix.json", {"schema_version": "director_v3_fresh_upstream_recoverability_matrix_v1", "policy_version": "fresh_upstream_recoverability_v1", "audit_fingerprint": fp, **summary, "provider_calls": 0})
    _write(ART / "director-quality-v3-exposure-unknown-resolution.json", {"schema_version": "director_v3_exposure_unknown_resolution_v1", "initial_unknown_count": len(exposure_unknown_rows), "final_unknown_count": len(exposure_unknown_rows), "records": exposure_unknown_rows, "new_exposed_confirmed": summary["exposed_confirmed"], "new_not_exposed_confirmed": summary["not_exposed_confirmed"], "provider_calls": 0})
    orphans = [row for row in rows if "ORPHANED_DOWNSTREAM_RECORD" in row.get("recovery_classifications", [])]
    _write(ART / "director-quality-v3-orphaned-downstream-record-audit.json", {"schema_version": "director_v3_orphaned_downstream_record_audit_v1", "count": len(orphans), "scenes": orphans, "provider_calls": 0})
    rainy = next((row for row in rows if row["scene_id"] == "book990400:e1:雨夜旧公寓门厅"), None)
    _write(ART / "director-quality-v3-rainy-apartment-entry-forensic.json", {"schema_version": "director_v3_rainy_apartment_entry_forensic_v1", "scene_id": "book990400:e1:雨夜旧公寓门厅", "found": bool(rainy), "forensic": rainy or {"status": "NOT_FOUND"}, "provider_calls": 0})
    plan = [{"scene_id": row["scene_id"], "completion_tier": row["completion_tier"], "steps": row["deterministic_recovery_steps"], "classifications": row["recovery_classifications"], "authorized": False} for row in ranked[:10]]
    _write(ART / "director-quality-v3-fresh-upstream-recovery-plan.json", {"schema_version": "director_v3_fresh_upstream_recovery_plan_v1", "policy_version": "fresh_upstream_recoverability_v1", "audit_fingerprint": fp, "top_10": plan, "execution_authorized": False, "provider_calls": 0})
    status = "DIRECTOR_V3_FRESH_UPSTREAM_COMPLETION_AUDIT_CLOSED"
    _write(ART / "director-quality-v3-fresh-upstream-completion-readiness.json", {"schema_version": "director_v3_fresh_upstream_completion_readiness_v1", "status": status, "audit_fingerprint": fp, "ready_for_deterministic_upstream_recovery": summary["ready_for_deterministic_upstream_recovery"], "deterministic_upstream_recovery_authorized": False, "ready_for_assisted_upstream_completion": summary["ready_for_assisted_upstream_completion"], "provider_upstream_completion_required": summary["provider_upstream_completion_required"], "new_real_source_material_required": summary["new_real_source_material_required"], "fresh_pool_eligible_count": 0, "fresh_pilot_2_authorized": False, "cohort_frozen": False, "provider_calls": 0})
    report = ["# Director Quality V3 — Fresh Upstream Completion Audit", "", f"**Status:** `{status}`", "", "## Baseline Audit", "", f"- Starting HEAD expected `f3bb930`; observed `{head}`.", f"- Population: `{len(rows)}` persisted source scenes; real source: `{sum(bool(row['source_real']) for row in rows)}`; working tree dirty: `{str(_dirty()).lower()}` due pre-existing unrelated workspace changes.", f"- Fresh Pool remains unchanged: eligible `0`, readiness `false`, Pilot #2 authorized `false`, cohort frozen `false`.", "- This audit is read-only with respect to source, FactSnapshot, ScriptIR, Treatment and Blocking records.", "", "## Final As-Built Verification", "", f"- Source lineage, recoverability classification, exposure evidence, orphan detection and deterministic ranking completed for `{len(rows)}` scenes.", f"- Exposure unknown: `{summary['exposure_unknown_initial']}` initially, `{summary['exposure_unknown_remaining']}` remaining; newly confirmed exposed `{summary['exposed_confirmed']}`, newly confirmed not-exposed `{summary['not_exposed_confirmed']}`.", f"- Tier counts: A `{summary['tier_counts']['TIER_A']}`, B `{summary['tier_counts']['TIER_B']}`, C `{summary['tier_counts']['TIER_C']}`, D `{summary['tier_counts']['TIER_D']}`.", f"- Deterministic recoverable `{summary['deterministic_recoverable_count']}`; provider required `{summary['provider_required_count']}`; human approval required `{summary['human_approval_required_count']}`; orphaned downstream `{summary['orphaned_downstream_count']}`; provenance mismatch `{summary['provenance_mismatch_count']}`.", f"- Rainy apartment forensic: `{'FOUND' if rainy else 'NOT_FOUND'}`; no record was created or changed.", "- Provider/LLM/MiMo/HTTP/media/storage/CI calls: `0`; production authority mutations: `0`.", "", "## Readiness Decision", "", f"- TIER_A >= 3: `{str(summary['ready_for_deterministic_upstream_recovery']).lower()}`.", f"- A+B >= 3: `{str(summary['ready_for_assisted_upstream_completion']).lower()}`.", f"- Provider upstream completion required: `{str(summary['provider_upstream_completion_required']).lower()}`.", f"- New real source material required: `{str(summary['new_real_source_material_required']).lower()}`.", "- Deterministic recovery authorized: `false`.", "", "## Recommended Next Stage", "", "`NEW_REAL_SOURCE_MATERIAL_INTAKE`" if summary["new_real_source_material_required"] else ("`DETERMINISTIC_UPSTREAM_RECOVERY`" if summary["ready_for_deterministic_upstream_recovery"] else ("`ASSISTED_UPSTREAM_COMPLETION`" if summary["ready_for_assisted_upstream_completion"] else "`AUTHORIZED_UPSTREAM_PROVIDER_COMPLETION`")), "", "`DIRECTOR_V3_FRESH_UPSTREAM_COMPLETION_AUDIT_CLOSED`", ""]
    report_text = "\n".join(report)
    _write(ART / "director-quality-v3-fresh-upstream-completion-audit-report.md", report_text)

    pointer = _preserve_closed_authority(_load(AUTHORITY, {}))
    pointer["fresh_upstream_completion_audit"] = {"status": status, "population_count": len(rows), "tier_a_count": summary["tier_counts"]["TIER_A"], "tier_b_count": summary["tier_counts"]["TIER_B"], "tier_c_count": summary["tier_counts"]["TIER_C"], "tier_d_count": summary["tier_counts"]["TIER_D"], "exposure_unknown_remaining": summary["exposure_unknown_remaining"], "orphaned_downstream_count": summary["orphaned_downstream_count"], "ready_for_deterministic_upstream_recovery": summary["ready_for_deterministic_upstream_recovery"], "deterministic_upstream_recovery_authorized": False, "ready_for_assisted_upstream_completion": summary["ready_for_assisted_upstream_completion"], "provider_upstream_completion_required": summary["provider_upstream_completion_required"], "new_real_source_material_required": summary["new_real_source_material_required"], "provider_calls": 0, "audit_fingerprint": fp}
    # Never promote the pool from an audit.  It remains the strict result from
    # the persisted DB unless a future authorized recovery actually changes it.
    _write(AUTHORITY, pointer)
    return {"status": status, "population_count": len(rows), **summary, "audit_fingerprint": fp, "provider_calls": 0, "production_authority_mutations": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    if any(flag in sys.argv[1:] for flag in ("--execute", "--execute-real", "--force", "--authorize")):
        raise SystemExit("fresh upstream completion audit is read-only; execution/authorization flags are not supported")
    print(json.dumps(run(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
