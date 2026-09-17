"""Run the provider-free targeted missing-fact stage and write audit artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.fact_coverage_verifier import run_targeted_missing_fact_extraction  # noqa: E402

ART = ROOT / "artifacts"
DEFAULT_SOURCE = ROOT / "work/intake/director_v3/evaluation_packages/SRC79f12d1b7f5eb828.raw"
DEFAULT_SNAPSHOT = ART / "director-quality-v3-fact-evidence-attempt2-result.json"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _default_requirements(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a generic missing-fact contract from the current snapshot.

    The policy asks for production identity/state fields for the first two
    character entities and two scene-level fields.  Entity IDs come from the
    snapshot; no book or fixture identifiers are encoded in the extractor.
    """
    records = [row for row in (snapshot.get("fact_snapshot", snapshot).get("records") or []) if isinstance(row, dict)]
    characters = []
    for row in records:
        if str(row.get("subject_type") or "") == "character" and str(row.get("subject_id") or "") not in characters:
            characters.append(str(row.get("subject_id")))
    requirements: list[dict[str, Any]] = []
    for entity in characters[:2]:
        for predicate in ("visual_identity", "current_state"):
            requirements.append({"subject_type": "character", "subject_id": entity, "predicate": predicate, "scope": "global", "consumer": "script_ir", "required": True, "severity": "blocking", "source_scope": ["immutable_source_material"]})
    requirements.extend([
        {"subject_type": "scene", "subject_id": "production_scene", "predicate": "geometry", "scope": "global", "consumer": "scene_blocking", "required": True, "severity": "blocking", "source_scope": ["immutable_source_material"]},
        {"subject_type": "prop", "subject_id": "production_props", "predicate": "state", "scope": "global", "consumer": "shot_plan", "required": True, "severity": "blocking", "source_scope": ["immutable_source_material"]},
    ])
    return requirements


def _write(path: Path, value: Any, *, sort_keys: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--requirements", default="")
    args = parser.parse_args(argv)
    source_path = Path(args.source)
    snapshot_raw = _read_json(Path(args.snapshot))
    snapshot = snapshot_raw.get("fact_snapshot", snapshot_raw) if isinstance(snapshot_raw, dict) else {}
    requirements = _read_json(Path(args.requirements)) if args.requirements else _default_requirements(snapshot_raw)
    if not isinstance(requirements, list):
        raise ValueError("requirements must be a JSON array")
    source_material = source_path.read_text(encoding="utf-8")
    result = run_targeted_missing_fact_extraction(source_material, snapshot, requirements, source_scope=["immutable_source_material"], source_package_id="SRC79f12d1b7f5eb828", source_version_id="SRC79f12d1b7f5eb828:V01:d001bab5cc82")
    before = result["coverage_before"]
    after = result["coverage_after"]
    _write(ART / "director-quality-v3-targeted-missing-fact-manifest.json", before["missing_fact_manifest"])
    _write(ART / "director-quality-v3-targeted-missing-fact-extraction-result.json", result["extraction"])
    _write(ART / "director-quality-v3-targeted-missing-fact-merge.json", result["merge"])
    _write(ART / "director-quality-v3-targeted-missing-fact-coverage-recheck.json", after)
    stage = {"schema_version": "director_quality_v3_targeted_missing_fact_extraction_stage_v1", "status": "CLOSED_PROVIDER_FREE", "provider_calls": 0, "manifest_count": before["missing_fact_manifest"]["count"], "validated_candidate_count": len(result["extraction"]["candidates"]), "unresolved_count": len(result["extraction"]["unresolved"]), "merge_status": "CHANGED" if result["merge"]["changed"] else "NO_CHANGE", "fact_coverage_status": after["status"], "script_ir_gate": after["script_ir_gate"]["status"], "idempotency_key": result["extraction"]["idempotency_key"]}
    _write(ART / "director-quality-v3-targeted-missing-fact-extraction-stage.json", stage)
    authority_path = ART / "director-quality-v3-current-stage-authority.json"
    if authority_path.exists():
        authority = _read_json(authority_path)
        authority["targeted_missing_fact_extraction"] = {
            "status": "CLOSED_PROVIDER_FREE",
            "provider_calls": 0,
            "manifest_count": stage["manifest_count"],
            "validated_candidate_count": stage["validated_candidate_count"],
            "unresolved_count": stage["unresolved_count"],
            "merge_status": stage["merge_status"],
            "fact_coverage_status": stage["fact_coverage_status"],
            "script_ir_gate": stage["script_ir_gate"],
            "idempotency_key": stage["idempotency_key"],
            "runtime_authority": False,
        }
        _write(authority_path, authority, sort_keys=False)
    report = "\n".join([
        "# Director Quality V3 — Targeted Missing Fact Extraction",
        "",
        "## Baseline Audit",
        "",
        f"- Source evidence is immutable and provider-free; requirements: `{before['required_count']}`; missing manifest items: `{before['missing_fact_manifest']['count']}`.",
        f"- Existing FactSnapshot records are read-only input; provider calls: `0`.",
        "",
        "## Targeted Extraction",
        "",
        f"- Candidates validated: `{len(result['extraction']['candidates'])}`; unresolved: `{len(result['extraction']['unresolved'])}`.",
        "- Only explicit `FACT:` declarations are eligible; natural-language guesses are unresolved.",
        "- Evidence locators, exact excerpts, source hashes, value support, scope and authoritative conflicts are validated.",
        "",
        "## Merge and Coverage Recheck",
        "",
        f"- Merge: `{'CHANGED' if result['merge']['changed'] else 'NO_CHANGE'}`; conflicts: `{len(result['merge']['conflicts'])}`; unresolved: `{len(result['merge']['unresolved'])}`.",
        f"- Coverage after recheck: `{after['status']}`.",
        f"- ScriptIR gate: `{after['script_ir_gate']['status']}`.",
        "- No threshold was lowered and no unresolved/conflicted fact was promoted.",
        "",
        "## Decision",
        "",
        f"`{stage['script_ir_gate']}`",
        "",
    ])
    (ART / "director-quality-v3-targeted-missing-fact-extraction-report.md").write_text(report, encoding="utf-8")
    print(json.dumps(stage, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
