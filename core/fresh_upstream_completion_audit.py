"""Deterministic, provider-free audit of incomplete upstream authority records.

The audit never repairs production records or promotes a candidate to the
Fresh Approved Record Pool.  It only classifies recoverability from persisted
source/upstream metadata and produces stable planning evidence.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

POLICY_VERSION = "fresh_upstream_recoverability_v1"
TIERS = ("TIER_A", "TIER_B", "TIER_C", "TIER_D")
PROVENANCE_ORDER = {"EXACT": 0, "MISSING": 1, "STALE": 2, "AMBIGUOUS": 3, "MISMATCH": 4}


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _t(value: Any) -> str:
    return str(value or "").strip()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _source_hashes(candidate: dict[str, Any]) -> set[str]:
    fps = _d(candidate.get("fingerprints"))
    return {_t(value) for value in fps.values() if _t(value)}


def _lineage_edge(name: str, source_id: Any, target_id: Any, source_fp: str, target_fp: str) -> dict[str, Any]:
    source_id, target_id, target_fp = _t(source_id), _t(target_id), _t(target_fp)
    if not target_id or not target_fp:
        status = "MISSING"
    elif source_fp and target_fp == source_fp:
        status = "EXACT"
    elif source_fp and target_fp not in {source_fp}:
        status = "MISMATCH"
    else:
        status = "AMBIGUOUS"
    return {"edge": name, "source_id": source_id or None, "target_id": target_id or None, "source_fingerprint": source_fp, "target_expected_source_fingerprint": target_fp, "lineage_status": status}


def audit_lineage(candidate: dict[str, Any]) -> dict[str, Any]:
    """Build source→Fact→IR→Treatment→Blocking lineage evidence."""
    upstream = _d(candidate.get("upstream")); source_fp = _d(candidate.get("fingerprints")).get("source_fingerprint", "")
    fact, ir = _d(upstream.get("fact_snapshot")), _d(upstream.get("script_ir"))
    treatment, blocking = _d(upstream.get("director_treatment")), _d(upstream.get("scene_blocking"))
    fact_fp = _t(fact.get("source_fingerprint")); ir_fp = _t(ir.get("source_fingerprint")) or _t(ir.get("payload_hash"))
    treatment_fp = _t(treatment.get("source_script_hash")); blocking_fp = _t(blocking.get("source_script_hash"))
    edges = [
        _lineage_edge("source→fact_snapshot", candidate.get("scene_id"), fact.get("id"), source_fp, fact_fp),
        _lineage_edge("fact_snapshot→script_ir", fact.get("id"), ir.get("id"), fact_fp or source_fp, ir_fp),
        _lineage_edge("script_ir→director_treatment", ir.get("id"), treatment.get("id"), ir_fp or source_fp, treatment_fp),
        _lineage_edge("director_treatment→scene_blocking", treatment.get("id"), blocking.get("id"), treatment_fp or ir_fp or source_fp, blocking_fp),
    ]
    statuses = [edge["lineage_status"] for edge in edges]
    return {"status": "EXACT" if all(value == "EXACT" for value in statuses) else ("MISMATCH" if "MISMATCH" in statuses else ("STALE" if "STALE" in statuses else ("MISSING" if "MISSING" in statuses else "AMBIGUOUS"))), "edges": edges}


def _source_is_structured(candidate: dict[str, Any]) -> bool:
    text = _t(candidate.get("source_text"))
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return isinstance(parsed, dict) and isinstance(parsed.get("beats"), list) or isinstance(parsed, dict) and isinstance(parsed.get("name"), str)


def classify_recovery(candidate: dict[str, Any], lineage: dict[str, Any]) -> dict[str, Any]:
    """Classify missing requirements without treating creative work as repair."""
    upstream = _d(candidate.get("upstream")); missing: list[dict[str, Any]] = []
    fact = _d(upstream.get("fact_snapshot")); ir = _d(upstream.get("script_ir")); treatment = _d(upstream.get("director_treatment")); blocking = _d(upstream.get("scene_blocking"))
    source_structured = _source_is_structured(candidate)
    if _t(fact.get("status")) != "confirmed":
        classification = "SOURCE_REIMPORT_REQUIRED" if not source_structured else "PROVIDER_GENERATION_REQUIRED"
        missing.append({"requirement": "FactSnapshot", "classification": classification, "reason": "confirmed FactSnapshot is absent; no existing canonical fact record is linked"})
    if not ir.get("qualified"):
        classification = "DETERMINISTIC_REBUILDABLE" if source_structured else "PROVIDER_GENERATION_REQUIRED"
        missing.append({"requirement": "Qualified ScriptIR", "classification": classification, "reason": "qualified ScriptIR is absent"})
    if _t(treatment.get("status")) != "approved":
        missing.append({"requirement": "Approved DirectorTreatment", "classification": "PROVIDER_GENERATION_REQUIRED", "requires_human_approval": True, "reason": "approved treatment evidence is absent"})
    if _t(blocking.get("status")) != "approved":
        missing.append({"requirement": "Approved SceneBlocking", "classification": "PROVIDER_GENERATION_REQUIRED", "requires_human_approval": True, "reason": "approved blocking evidence is absent"})
    if lineage.get("status") in {"MISMATCH", "STALE", "AMBIGUOUS"}:
        missing.append({"requirement": "Source lineage", "classification": "PROVENANCE_REPAIR_REQUIRED", "reason": f"lineage status is {lineage['status']}"})
    if any(edge["lineage_status"] == "MISSING" for edge in lineage.get("edges", [])) and (_t(treatment.get("status")) == "approved" or _t(blocking.get("status")) == "approved"):
        missing.append({"requirement": "Downstream approval lineage", "classification": "ORPHANED_DOWNSTREAM_RECORD", "reason": "approved downstream record lacks a provable upstream link"})
    classifications = {item["classification"] for item in missing}
    provider_required = "PROVIDER_GENERATION_REQUIRED" in classifications
    human_required = any(bool(item.get("requires_human_approval")) for item in missing) or "HUMAN_APPROVAL_REQUIRED" in classifications
    provenance_risk = lineage.get("status", "AMBIGUOUS")
    if "ORPHANED_DOWNSTREAM_RECORD" in classifications or "SOURCE_REIMPORT_REQUIRED" in classifications or provenance_risk in {"MISMATCH", "STALE", "AMBIGUOUS"}:
        tier = "TIER_D"
    elif not provider_required and not human_required:
        tier = "TIER_A"
    elif not provider_required:
        tier = "TIER_B"
    else:
        tier = "TIER_C"
    if not missing and lineage.get("status") != "EXACT":
        tier = "TIER_D"
    return {"missing_requirements": missing, "recovery_classifications": sorted(classifications), "requires_new_provider_generation": provider_required, "requires_human_approval": human_required, "provenance_risk": provenance_risk, "completion_tier": tier}


def rank_candidates(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple[Any, ...]:
        return (bool(row.get("requires_new_provider_generation")), bool(row.get("requires_human_approval")), PROVENANCE_ORDER.get(_t(row.get("provenance_risk")), 99), len(_l(row.get("deterministic_recovery_steps"))), len(_l(row.get("missing_requirements"))), stable_hash(row.get("scene_id")))
    return sorted(rows, key=key)


def audit_candidate(candidate: dict[str, Any], *, exposure_resolution: str = "EXPOSURE_UNKNOWN") -> dict[str, Any]:
    lineage = audit_lineage(candidate)
    recovery = classify_recovery(candidate, lineage)
    upstream = _d(candidate.get("upstream"))
    steps = []
    for item in recovery["missing_requirements"]:
        cls = item["classification"]
        if cls == "DETERMINISTIC_REBUILDABLE": steps.append("deterministic compile/validate missing upstream record")
        elif cls == "SOURCE_REIMPORT_REQUIRED": steps.append("re-import and establish source provenance")
        elif cls == "PROVENANCE_REPAIR_REQUIRED": steps.append("repair and re-verify source lineage")
        elif cls == "ORPHANED_DOWNSTREAM_RECORD": steps.append("quarantine orphaned approval and obtain authoritative upstream evidence")
        elif cls == "PROVIDER_GENERATION_REQUIRED": steps.append("authorized provider generation, then human review/approval")
    return {"scene_id": candidate.get("scene_id"), "book_id": candidate.get("book_id"), "episode": candidate.get("episode"), "scene_name": candidate.get("scene_name"), "source_fingerprint": _d(candidate.get("fingerprints")).get("source_fingerprint", ""), "source_real": bool(candidate.get("source_real")), "exposure_status": exposure_resolution, "retired": bool(candidate.get("retired")), "source_status": candidate.get("classification", "SOURCE_REAL_UPSTREAM_INCOMPLETE"), "fact_snapshot_status": _t(_d(upstream.get("fact_snapshot")).get("status")) or "missing", "script_ir_status": _t(_d(upstream.get("script_ir")).get("status")) or "missing", "treatment_status": _t(_d(upstream.get("director_treatment")).get("status")) or "missing", "blocking_status": _t(_d(upstream.get("scene_blocking")).get("status")) or "missing", "lineage": lineage, **recovery, "deterministic_recovery_steps": steps, "blockers": list(candidate.get("eligibility_reasons") or []) + [item["reason"] for item in recovery["missing_requirements"]]}


def audit_fingerprint(rows: Iterable[dict[str, Any]], exposure_registry_fingerprint: str = "") -> str:
    relevant = [{"scene_id": row.get("scene_id"), "source": row.get("source_fingerprint"), "lineage": row.get("lineage", {}).get("status"), "classifications": row.get("recovery_classifications", [])} for row in rows]
    return stable_hash({"policy_version": POLICY_VERSION, "rows": relevant, "exposure_registry_fingerprint": exposure_registry_fingerprint})


def summarize(rows: list[dict[str, Any]], *, initial_unknown: int, final_unknown: int, exposed_confirmed: int, not_exposed_confirmed: int) -> dict[str, Any]:
    counts = {tier: sum(row.get("completion_tier") == tier for row in rows) for tier in TIERS}
    deterministic = sum(not row.get("requires_new_provider_generation") for row in rows)
    provider = sum(bool(row.get("requires_new_provider_generation")) for row in rows)
    human = sum(bool(row.get("requires_human_approval")) for row in rows)
    orphaned = sum("ORPHANED_DOWNSTREAM_RECORD" in row.get("recovery_classifications", []) for row in rows)
    mismatch = sum(row.get("provenance_risk") == "MISMATCH" for row in rows)
    a_plus_b = counts["TIER_A"] + counts["TIER_B"]
    return {"tier_counts": counts, "deterministic_recoverable_count": deterministic, "provider_required_count": provider, "human_approval_required_count": human, "orphaned_downstream_count": orphaned, "provenance_mismatch_count": mismatch, "exposure_unknown_initial": initial_unknown, "exposure_unknown_remaining": final_unknown, "exposed_confirmed": exposed_confirmed, "not_exposed_confirmed": not_exposed_confirmed, "ready_for_deterministic_upstream_recovery": counts["TIER_A"] >= 3, "deterministic_upstream_recovery_authorized": False, "ready_for_assisted_upstream_completion": counts["TIER_A"] < 3 and a_plus_b >= 3, "provider_upstream_completion_required": counts["TIER_A"] + counts["TIER_B"] < 3 and provider > 0, "new_real_source_material_required": counts["TIER_A"] + counts["TIER_B"] + counts["TIER_C"] == 0}
