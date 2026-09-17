"""Recompute the ScriptIR source-fact gate after requirement reclassification.

This is a provider-free, read-only recanary.  It consumes the existing
MissingFactManifest and historical FactSnapshot artifacts, applies the
semantic registry, and writes only a report/result artifact.  It never creates
or updates a FactSnapshot or ScriptIR.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "artifacts" / "director-quality-v3-targeted-missing-fact-manifest.json"
DEFAULT_SNAPSHOT = ROOT / "artifacts" / "director-quality-v3-fact-evidence-attempt2-result.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()


def _requirements(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in manifest.get("items", []) if isinstance(item, dict)]


def run(*, manifest: dict[str, Any], snapshot_payload: dict[str, Any]) -> dict[str, Any]:
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
    args = parser.parse_args(argv)
    before = _git("status", "--porcelain")
    result = run(manifest=_load(args.manifest), snapshot_payload=_load(args.snapshot))
    result["clean_tree_preflight"] = before == ""
    result["git"] = {"branch": _git("branch", "--show-current"), "head": _git("rev-parse", "HEAD"), "dirty_paths_before": before.splitlines() if before else []}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "director-quality-v3-script-ir-source-coverage-recanary-result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
