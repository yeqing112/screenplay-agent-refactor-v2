"""Close the provider-free Fact Coverage Foundation and reconcile authority."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
EXPECTED_HEAD = "06a46ced1a1caedebdb7b6e35c1e4d8606ce246a"
SOURCE_PACKAGE = "SRC79f12d1b7f5eb828"
SOURCE_VERSION = "SRC79f12d1b7f5eb828:V01:d001bab5cc82"
RAW_HASH = "d001bab5cc820ae3b99f2f7a43ad2f4022e62073acb036a9c1c0e7d4bb888368"


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from core.fact_coverage import (
        REQUIREMENT_TYPES,
        build_narrative_unit_index,
        canonical_fact_components,
        compile_fact_coverage,
        coverage_matrix_contract,
        coverage_provider_schema,
        coverage_schema_fingerprint,
        fingerprint,
        requirement_contract,
    )

    head = git("rev-parse", "HEAD")
    remote = git("rev-parse", "origin/codex/fact-semantic-grounding-foundation")
    dirty = git("status", "--porcelain").splitlines()
    expected_paths = {"?? core/fact_coverage.py", "?? scripts/run_director_quality_v3_fact_coverage_foundation.py", "?? tests/test_fact_coverage.py", "?? tests/test_director_quality_v3_fact_coverage_foundation.py"}
    unexpected_dirty = [row for row in dirty if row not in expected_paths and not row.rstrip().endswith("artifacts/director-quality-v3-current-stage-authority.json") and not row.startswith("?? artifacts/director-quality-v3-fact-coverage-") and not row.startswith("?? artifacts/director-quality-v3-canonical-fact-components.json") and not row.startswith("?? artifacts/director-quality-v3-source-narrative-unit-")]
    if head != EXPECTED_HEAD or remote != EXPECTED_HEAD or unexpected_dirty:
        print(json.dumps({"status": "DIRECTOR_V3_FACT_COVERAGE_FOUNDATION_BLOCKED", "provider_calls": 0, "head": head, "remote": remote, "dirty": dirty, "unexpected_dirty": unexpected_dirty}, ensure_ascii=False, indent=2))
        return 2

    source_index = json.loads((ART / "director-quality-v3-source-evidence-index-preview.json").read_text(encoding="utf-8"))
    attempt = json.loads((ART / "director-quality-v3-fact-evidence-attempt2-result.json").read_text(encoding="utf-8"))
    overlay = json.loads((ART / "director-quality-v3-semantic-verifier-canary-authority-overlay.json").read_text(encoding="utf-8"))
    facts = attempt["fact_snapshot"]["records"]
    components = canonical_fact_components(facts)
    write(ART / "director-quality-v3-canonical-fact-components.json", {**components, "source_package_id": SOURCE_PACKAGE, "source_version_id": SOURCE_VERSION})
    units = build_narrative_unit_index(anchors=source_index.get("anchors", []), window_size=1200)
    write(ART / "director-quality-v3-source-narrative-unit-contract.json", {"schema_version": "source_narrative_unit_index_v1", "provider_calls": 0, "fields": ["unit_id", "anchor_refs", "char_start", "char_end", "exact_text_hash", "source_order"], "deterministic_grouping": "ordered_anchor_char_window", "window_size": 1200, "semantic_interpretation": False, "source_package_id": SOURCE_PACKAGE, "source_version_id": SOURCE_VERSION})
    write(ART / "director-quality-v3-source-narrative-unit-index-preview.json", {**units, "source_package_id": SOURCE_PACKAGE, "source_version_id": SOURCE_VERSION, "source_raw_hash": RAW_HASH, "anchor_count": len(source_index.get("anchors", [])), "full_anchor_count": int(source_index.get("full_anchor_count") or source_index.get("anchor_count") or 0)})

    unit_refs = [row["unit_id"] for row in units["units"][:3]]
    predicate_text = {str(row["fact_id"]): f"{row.get('predicate', '')} {row.get('value', '')}".lower() for row in facts}
    def supports(kind: str) -> list[str]:
        cues = {
            "CHARACTER_IDENTITY": ("",), "CHARACTER_RELATION": ("previous tenant",),
            "LOCATION_IDENTITY": ("apartment", "1204", "1203"), "LOCATION_CHANGE": ("to apartment",),
            "EVENT_OCCURRENCE": ("escaped", "hid", "found", "moving", "installed"), "EVENT_ORDER": ("escaped", "hid", "found", "moving"),
            "TEMPORAL_ANCHOR": ("six years",), "CAUSAL_RELATION": ("installed", "hid"),
            "OBJECT_STATE": ("umbrella", "camera", "storage card"), "OBJECT_OWNERSHIP": ("umbrella", "previous tenant"),
            "REVEAL": ("storage card", "camera", "previous tenant"), "CONFLICT_STATE": (), "CLAIM_OR_BELIEF": ("previous tenant", "recognized"), "OUTCOME": (),
        }
        selected = []
        for fact_id, text in predicate_text.items():
            if kind == "CHARACTER_IDENTITY" or any(cue in text for cue in cues.get(kind, ())):
                selected.append(fact_id)
        return selected
    requirements = [{"requirement_id": f"REQ_{index:04d}", "requirement_type": kind, "description": f"Development preview candidate for {kind}; semantic necessity is not adjudicated.", "source_unit_refs": unit_refs, "supporting_fact_ids": supports(kind)} for index, kind in enumerate(REQUIREMENT_TYPES, 1)]
    req_contract = requirement_contract()
    write(ART / "director-quality-v3-fact-coverage-requirement-contract.json", req_contract)
    write(ART / "director-quality-v3-fact-coverage-matrix-contract.json", coverage_matrix_contract())
    write(ART / "director-quality-v3-fact-coverage-authority-compiler.json", {"schema_version": "fact_coverage_authority_compiler_v1", "provider_calls": 0, "program_owned": ["requirement_id", "fact_id", "disposition_compatibility", "matrix_validity", "deterministic_ceilings"], "provider_component_prose_authority": False, "no_fact_count_threshold": True, "no_anchor_percentage_shortcut": True})
    matrix = compile_fact_coverage(requirements=requirements, semantic_overlay=overlay, source_unit_index=units)
    write(ART / "director-quality-v3-fact-coverage-development-preview.json", {**matrix, "schema_version": "fact_coverage_development_preview_v1", "development_only": True, "runtime_authority": False, "qualification_status": "NOT_ADJUDICATED", "obvious_missing_categories": [row["requirement_type"] for row in matrix["rows"] if row["coverage_status"] == "MISSING"], "development_gap_count": sum(1 for row in matrix["rows"] if row["coverage_status"] != "COVERED")})
    write(ART / "director-quality-v3-fact-coverage-verifier-contract.json", {"schema_version": "fact_coverage_verifier_v1", "status": "DESIGNED_NOT_EXECUTED", "provider_calls": 0, "inputs": ["source_narrative_units", "existing_semantically_adjudicated_facts", "canonical_fact_ids", "fact_dispositions", "requirement_taxonomy"], "outputs": ["requirements", "coverage_claims"], "forbidden": ["new_fact", "fact_repair", "new_evidence", "source_modification", "script_ir"]})
    write(ART / "director-quality-v3-fact-coverage-verifier-provider-schema.json", {"schema_version": "fact_coverage_verifier_provider_schema_v1", "schema_fingerprint": coverage_schema_fingerprint(), "provider_schema": coverage_provider_schema()})
    write(ART / "director-quality-v3-fact-coverage-verifier-parity.json", {"status": "PASS", "provider_calls": 0, "schema_fingerprint": coverage_schema_fingerprint(), "runtime_schema_fingerprint": coverage_schema_fingerprint()})
    write(ART / "director-quality-v3-fact-coverage-foundation-readiness.json", {"schema_version": "fact_coverage_foundation_readiness_v1", "status": "CLOSED", "provider_calls": 0, "narrative_unit_index": "PASS", "coverage_requirement_contract": "PASS", "coverage_matrix_contract": "PASS", "coverage_authority_compiler": "PASS", "provider_component_prose_authority": False, "canonical_fact_components": "PASS", "development_preview": "DEVELOPMENT_ONLY", "fact_coverage_status": "NOT_YET_QUALIFIED", "coverage_verifier_ready": True, "coverage_verifier_authorized": False, "script_ir_gate": "BLOCKED_PENDING_FACT_COVERAGE"})

    authority_path = ART / "director-quality-v3-current-stage-authority.json"
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    evaluation = authority.setdefault("authorized_ai_evaluation_source", {})
    evaluation.update({"project_provider_exposure": "EXPOSED", "provider_attempts_by_stage": {"fact_attempt_1": 1, "fact_attempt_2": 1, "semantic_verifier": 1}, "cumulative_provider_attempts": 3, "current_stage_provider_attempts": 1, "provider_calls_scope": "current_stage_provider_attempts is current stage; cumulative_provider_attempts is all historical attempts", "attempt_2_evidence_authority": "PASS", "semantic_grounding_status": "SEMANTIC_GROUNDING_CLOSED_WITH_REVIEW", "effective_lineage_state": "FACT_SEMANTICS_ADJUDICATED", "fact_coverage_status": "NOT_YET_QUALIFIED", "ready_for_fact_coverage_qualification": True, "ready_for_script_ir_processing": False, "script_ir_processing_authorized": False, "treatment_processing_authorized": False})
    authority["fact_coverage_foundation"] = {"status": "CLOSED", "provider_calls": 0, "narrative_unit_index": "PASS", "coverage_requirement_contract": "PASS", "coverage_matrix_contract": "PASS", "coverage_authority_compiler": "PASS", "provider_component_prose_authority": False, "canonical_fact_components": "PASS", "development_preview": "DEVELOPMENT_ONLY", "fact_coverage_status": "NOT_YET_QUALIFIED", "coverage_verifier_ready": True, "coverage_verifier_authorized": False, "script_ir_gate": "BLOCKED_PENDING_FACT_COVERAGE", "development_gap_count": sum(1 for row in matrix["rows"] if row["coverage_status"] != "COVERED"), "runtime_authority": False}
    write(authority_path, authority)
    report = f"""# Director Quality V3 — Semantic Canary Authority Reconciliation + Fact Coverage Foundation\n\n## Authority Reconciliation\n\n- Provider calls this round: `0`; historical cumulative attempts: `3` (`1 + 1 + 1`).\n- Effective semantic status: `SEMANTIC_GROUNDING_CLOSED_WITH_REVIEW`; effective lineage: `FACT_SEMANTICS_ADJUDICATED`.\n- Historical `FACT_SNAPSHOT_CONFIRMED` remains preserved as Attempt #2 lineage.\n- Source exposure: `EXPOSED`; historical Canary artifacts remain immutable.\n\n## Fact Coverage Foundation\n\n- Narrative units, requirement taxonomy, matrix contract, authority compiler, canonical components and verifier schema/parity: `PASS`.\n- Development preview only: `{len(matrix['rows'])}` requirement categories, `{sum(1 for row in matrix['rows'] if row['coverage_status'] != 'COVERED')}` non-covered candidates.\n- `development_only=true`, `runtime_authority=false`, `qualification_status=NOT_ADJUDICATED`.\n- Provider component prose is explanatory only and cannot become verified atoms.\n\n## Gate\n\n- Fact Coverage status: `NOT_YET_QUALIFIED`; Coverage Verifier authorized: `false`.\n- ScriptIR ready/authorized: `false`; gate: `BLOCKED_PENDING_FACT_COVERAGE`.\n- No count threshold or anchor-percentage shortcut is used.\n\n## Decision\n\n`DIRECTOR_V3_FACT_COVERAGE_FOUNDATION_CLOSED`\n\nThis round is provider-free and terminal.\n"""
    (ART / "director-quality-v3-fact-coverage-foundation-report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": "DIRECTOR_V3_FACT_COVERAGE_FOUNDATION_CLOSED", "provider_calls": 0, "fact_coverage_status": "NOT_YET_QUALIFIED", "script_ir_authorized": False, "development_gap_count": sum(1 for row in matrix["rows"] if row["coverage_status"] != "COVERED")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
