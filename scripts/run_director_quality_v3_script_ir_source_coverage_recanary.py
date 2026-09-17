"""Recompute the ScriptIR source-fact gate after requirement reclassification.

This is a provider-free, read-only recanary.  The formal path derives
requirements from the ScriptIR consumer contract; the legacy manifest path is
kept only for replay compatibility and is explicitly reported as baseline.
Neither path creates or updates a FactSnapshot or ScriptIR.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_MANIFEST = ROOT / "artifacts" / "director-quality-v3-targeted-missing-fact-manifest.json"
DEFAULT_SNAPSHOT = ROOT / "artifacts" / "director-quality-v3-fact-evidence-attempt2-result.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()


def _requirements(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in manifest.get("items", []) if isinstance(item, dict)]


def run_formal(*, source_structure: dict[str, Any], records: list[dict[str, Any]] | None = None, downstream_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the formal ScriptIR consumer-derived source requirement gate."""

    from core.script_ir_source_requirements import audit_script_ir_consumers, compile_script_ir_source_requirements, evaluate_script_ir_source_coverage, script_ir_source_requirement_contract
    requirement_set = compile_script_ir_source_requirements(source_structure=source_structure)
    coverage = evaluate_script_ir_source_coverage(requirement_set, records=records or [])
    downstream = []
    if isinstance(downstream_manifest, dict):
        from core.fact_requirement_semantics import build_authoring_decision_request, classify_requirement
        for raw in _requirements(downstream_manifest):
            classified = classify_requirement(raw)
            if not classified.get("gate_eligible"):
                downstream.append(build_authoring_decision_request(classified))
    counts = {
        "total": requirement_set.get("blocking_requirement_count", 0),
        "covered": coverage.get("counts", {}).get("covered", 0),
        "derived_covered": coverage.get("counts", {}).get("derived_covered", 0),
        "missing": coverage.get("counts", {}).get("missing", 0),
        "ambiguous": coverage.get("counts", {}).get("ambiguous", 0),
        "conflicted": coverage.get("counts", {}).get("conflicted", 0),
        "invalid": coverage.get("counts", {}).get("invalid", 0),
    }
    status = coverage.get("status")
    return {
        "schema_version": "director_quality_v3_script_ir_source_requirement_contract_recanary_v1",
        "status": status,
        "script_ir_consumer_audit": audit_script_ir_consumers(),
        "script_ir_source_requirement_contract": script_ir_source_requirement_contract(),
        "script_ir_source_requirement_set": requirement_set,
        "script_ir_source_coverage": coverage,
        "script_ir_required_source_facts": counts,
        "source_fact_only_missing_manifest": coverage.get("source_fact_only_missing_manifest"),
        "downstream_requirement_backlog": downstream,
        "downstream_requirement_backlog_count": len(downstream),
        "script_ir_authority_readiness": "SCRIPT_IR_AUTHORITY_ACTIVATION_READY" if status == "SCRIPT_IR_SOURCE_CONTRACT_COVERAGE_SUFFICIENT" else "SCRIPT_IR_AUTHORITY_BLOCKED",
        "provider_calls": 0,
        "production_writes": 0,
    }


def run(*, manifest: dict[str, Any] | None = None, snapshot_payload: dict[str, Any] | None = None, source_structure: dict[str, Any] | None = None, records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if source_structure is not None:
        return run_formal(source_structure=source_structure, records=records, downstream_manifest=manifest)
    manifest = manifest or {}
    snapshot_payload = snapshot_payload or {}
    from core.fact_coverage import build_missing_fact_manifest
    from core.fact_requirement_semantics import build_authoring_decision_request, classify_requirement, stage_gate_requirements

    requirements = _requirements(manifest)
    records = list((snapshot_payload.get("fact_snapshot") or {}).get("records") or [])
    classified = [classify_requirement(row) for row in requirements]
    source_requirements = stage_gate_requirements(requirements, "SCRIPT_IR")
    coverage = build_missing_fact_manifest(source_requirements, records)
    backlog = []
    for row in classified:
        if not row.get("gate_eligible"):
            backlog.append(build_authoring_decision_request(row))

    counts = {"total": len(source_requirements), "covered": 0, "partially_covered": 0, "missing": 0, "ambiguous": 0, "conflicted": 0, "invalid": 0}
    for row in coverage.get("coverage", []):
        reason = row.get("reason")
        if reason is None:
            counts["covered"] += 1
        elif reason == "INSUFFICIENT_EVIDENCE":
            counts["partially_covered"] += 1
        elif reason == "AMBIGUOUS":
            counts["ambiguous"] += 1
        elif reason == "CONFLICTED":
            counts["conflicted"] += 1
        elif reason == "INVALID":
            counts["invalid"] += 1
        else:
            counts["missing"] += 1

    blocking = counts["missing"] + counts["partially_covered"] + counts["ambiguous"] + counts["conflicted"] + counts["invalid"]
    status = "SCRIPT_IR_SOURCE_COVERAGE_SUFFICIENT" if blocking == 0 else "SCRIPT_IR_SOURCE_COVERAGE_INSUFFICIENT"
    return {
        "schema_version": "director_quality_v3_script_ir_source_coverage_recanary_v1",
        "status": status,
        "provider_calls": 0,
        "production_writes": 0,
        "script_ir_authority_readiness": "SCRIPT_IR_AUTHORITY_ACTIVATION_READY" if status.endswith("SUFFICIENT") else "SCRIPT_IR_AUTHORITY_BLOCKED",
        "script_ir_required_source_facts": counts,
        "source_fact_only_missing_manifest": coverage.get("missing_fact_manifest", {"status": "FACT_COVERAGE_SUFFICIENT", "items": [], "count": 0}),
        "downstream_requirement_backlog": backlog,
        "downstream_requirement_backlog_count": len(backlog),
        "reclassified_requirements": classified,
        "fact_snapshot_record_count": len(records),
        "source_manifest_fingerprint": manifest.get("fingerprint", ""),
        "historical_snapshot_revision": snapshot_payload.get("fact_snapshot", {}).get("revision"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--source", type=Path, default=None, help="Optional structured source payload for the formal consumer-derived gate.")
    args = parser.parse_args(argv)
    before = _git("status", "--porcelain")
    manifest = _load(args.manifest)
    if args.source:
        source = _load(args.source)
        snapshot = _load(args.snapshot)
        records = list((snapshot.get("fact_snapshot") or {}).get("records") or [])
        result = run(source_structure=source, records=records, manifest=manifest)
        result["source_input"] = str(args.source.relative_to(ROOT)) if args.source.is_absolute() else str(args.source)
        (args.output_dir / "director-quality-v3-script-ir-consumer-audit.json").write_text(json.dumps(result["script_ir_consumer_audit"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "director-quality-v3-script-ir-source-requirement-contract.json").write_text(json.dumps(result["script_ir_source_requirement_contract"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        result = run(manifest=manifest, snapshot_payload=_load(args.snapshot))
    result["clean_tree_preflight"] = before == ""
    result["git"] = {"branch": _git("branch", "--show-current"), "head": _git("rev-parse", "HEAD"), "dirty_paths_before": before.splitlines() if before else []}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "director-quality-v3-script-ir-source-coverage-recanary-result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.source:
        counts = result["script_ir_required_source_facts"]
        report = f"""# ScriptIR Source Requirement Contract Recanary

## Baseline Audit

- Previous baseline used historical `MissingFactManifest` reclassification.
- That baseline reported zero ScriptIR requirements, but did not prove that the ScriptIR consumer has no source inputs.
- Historical downstream backlog remains preserved: `{result['downstream_requirement_backlog_count']}` items.

## Final As-Built Verification

- Consumer audit: `SCRIPT_IR_CONSUMER_AUDIT` (see `director-quality-v3-script-ir-consumer-audit.json`).
- Source input: `{result.get('source_input', '')}` (structured payload only; no production entity was persisted).
- Contract: `script_ir_source_requirement_contract_v1` (see `director-quality-v3-script-ir-source-requirement-contract.json`).
- Formal requirement set: `{result['script_ir_source_requirement_set']['requirement_count']}` total; blocking `{counts['total']}`; optional `{result['script_ir_source_requirement_set']['optional_requirement_count']}`; derived `{result['script_ir_source_requirement_set']['derived_requirement_count']}`.
- Coverage: covered `{counts['covered']}`; derived-covered `{counts['derived_covered']}`; missing `{counts['missing']}`; ambiguous `{counts['ambiguous']}`; conflicted `{counts['conflicted']}`; invalid `{counts['invalid']}`.
- Status: `{result['status']}`; authority readiness: `{result['script_ir_authority_readiness']}`.
- `source_fact_only_missing_manifest`: `{result['source_fact_only_missing_manifest']['count']}`.
- Structural metadata is separate from FactSnapshot story facts; no visual identity, geometry, camera, lighting, blocking or shot-design requirement was promoted.

## Safety Boundary

- Provider calls: `0`; production writes: `0`.
- No ScriptIR, FactSnapshot, DirectorTreatment, SceneBlocking, ShotPlan or media record was created or modified.
- Next stage only when separately authorized: `SCRIPT_IR_AUTHORITY_ACTIVATION`.
"""
        (args.output_dir / "director-quality-v3-script-ir-source-coverage-recanary-report.md").write_text(report, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
