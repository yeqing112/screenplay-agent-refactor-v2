"""Run targeted semantic evidence resolution without invoking a provider."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.targeted_semantic_evidence_resolution import run_targeted_semantic_evidence_resolution  # noqa: E402

ART = ROOT / "artifacts"
DEFAULT_SOURCE = ROOT / "work/intake/director_v3/evaluation_packages/SRC79f12d1b7f5eb828.raw"
DEFAULT_MANIFEST = ART / "director-quality-v3-targeted-missing-fact-manifest.json"
DEFAULT_SNAPSHOT = ART / "director-quality-v3-fact-evidence-attempt2-result.json"


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    args = parser.parse_args(argv)
    manifest = _read(Path(args.manifest))
    raw_snapshot = _read(Path(args.snapshot))
    snapshot = raw_snapshot.get("fact_snapshot", raw_snapshot) if isinstance(raw_snapshot, dict) else {}
    # Read bytes so SourceEvidenceIndex preserves the immutable source's
    # original CRLF/LF layout and byte offsets.
    source = Path(args.source).read_bytes()
    result = run_targeted_semantic_evidence_resolution(
        source_material=source,
        current_snapshot=snapshot,
        missing_manifest=manifest,
        source_package_id="SRC79f12d1b7f5eb828",
        source_version_id="SRC79f12d1b7f5eb828:V01:d001bab5cc82",
    )
    _write(ART / "director-quality-v3-targeted-semantic-evidence-resolution-result.json", result)
    summary = {
        "schema_version": "director_quality_v3_targeted_semantic_evidence_resolution_stage_v1",
        "status": "CLOSED_PROVIDER_FREE",
        "provider_calls": result["provider_calls"],
        "required": len(result["results"]),
        "resolved": sum(1 for row in result["results"] if row["resolution"].get("support_status") == "SUPPORTED"),
        "ambiguous": result["counts"].get("AMBIGUOUS", 0),
        "conflicted": result["counts"].get("CONFLICTED", 0),
        "unsupported": result["counts"].get("UNSUPPORTED", 0),
        "remaining_unresolved": sum(1 for row in result["results"] if row["resolution"].get("proposal") is None),
        "merge_status": "CHANGED" if result["merge"].get("changed") else "NO_CHANGE",
        "fact_coverage_status": result.get("coverage_after", {}).get("status", "FACT_COVERAGE_INSUFFICIENT"),
        "script_ir_gate": result.get("coverage_after", {}).get("script_ir_gate", {}).get("status", "BLOCKED_PENDING_TARGETED_MISSING_FACTS"),
        "result_fingerprint": result["result_fingerprint"],
    }
    _write(ART / "director-quality-v3-targeted-semantic-evidence-resolution-stage.json", summary)
    lines = [
        "# Director Quality V3 — Targeted Semantic Evidence Resolution",
        "",
        "## Baseline / Retrieval",
        "",
        f"- Required manifest items: `{summary['required']}`; candidate anchor retrieval is scoped per fact and provider-free.",
        "- Retrieval returns immutable exact text, source hash, character/byte offsets, lexical matches and ranking; it never creates facts.",
        "",
        "## Resolution",
        "",
        f"- Resolved: `{summary['resolved']}`; ambiguous: `{summary['ambiguous']}`; conflicted: `{summary['conflicted']}`; unsupported: `{summary['unsupported']}`; remaining unresolved: `{summary['remaining_unresolved']}`.",
        "- Exact quote and anchor validation run before any proposal can be converted to a FactSnapshot candidate.",
        "- No provider adapter was supplied; provider calls: `0`.",
        "",
        "## Decision",
        "",
        "- This stage does not mutate FactSnapshot or alter coverage thresholds.",
        f"- Merge: `{summary['merge_status']}`; coverage recheck: `{summary['fact_coverage_status']}`; ScriptIR gate: `{summary['script_ir_gate']}`.",
        "",
    ]
    (ART / "director-quality-v3-targeted-semantic-evidence-resolution-report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
