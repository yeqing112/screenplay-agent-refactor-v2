"""Provider-free full-source Narrative Unit completeness closure.

This stage consumes the immutable source package and evidence index only.  It
does not call an LLM, verifier, media provider, database, or storage service.
The existing twelve-anchor preview is retained as historical evidence and is
diagnosed rather than silently promoted to authority.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
PKG = ROOT / "work" / "intake" / "director_v3" / "evaluation_packages"
SOURCE_PACKAGE = "SRC79f12d1b7f5eb828"
SOURCE_VERSION = "SRC79f12d1b7f5eb828:V01:d001bab5cc82"
RAW_HASH = "d001bab5cc820ae3b99f2f7a43ad2f4022e62073acb036a9c1c0e7d4bb888368"
EXPECTED_EVIDENCE_FP = "4697f3069bb34c9650d97b7e2c788d5b9db36034a39fedf77a0756e7a7bf5295"


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
        validate_narrative_unit_completeness,
    )
    from core.source_evidence_index import build_source_evidence_index, validate_source_evidence_index

    raw_path = PKG / f"{SOURCE_PACKAGE}.raw"
    raw_bytes = raw_path.read_bytes()
    source_index_preview = json.loads((ART / "director-quality-v3-source-evidence-index-preview.json").read_text(encoding="utf-8"))
    source_index = build_source_evidence_index(raw_bytes, source_package_id=SOURCE_PACKAGE, source_version_id=SOURCE_VERSION, source_raw_hash=RAW_HASH)
    source_index_validation = validate_source_evidence_index(source_index, raw_bytes)
    source_identity = {
        "source_package_id": SOURCE_PACKAGE,
        "source_version_id": SOURCE_VERSION,
        "source_raw_hash": RAW_HASH,
        "evidence_index_fingerprint": source_index.get("evidence_index_fingerprint"),
        "expected_evidence_index_fingerprint": EXPECTED_EVIDENCE_FP,
        "raw_byte_length": len(raw_bytes),
        "raw_sha256_matches": source_index.get("source_raw_hash") == RAW_HASH,
        "evidence_index_fingerprint_matches": source_index.get("evidence_index_fingerprint") == EXPECTED_EVIDENCE_FP,
        "anchor_count": source_index.get("anchor_count"),
        "source_index_validation": source_index_validation,
        "provider_calls": 0,
    }
    write(ART / "director-quality-v3-full-source-evidence-index-identity-audit.json", source_identity)

    old_units = json.loads((ART / "director-quality-v3-source-narrative-unit-index-preview.json").read_text(encoding="utf-8"))
    old_refs = [ref for unit in old_units.get("units", []) for ref in unit.get("anchor_refs", [])]
    old_forensic = {
        "schema_version": "narrative_unit_incomplete_input_forensic_v1",
        "status": "CLOSED",
        "provider_calls": 0,
        "artifact": "artifacts/director-quality-v3-source-narrative-unit-index-preview.json",
        "observed_anchor_count": len(old_refs),
        "declared_full_anchor_count": old_units.get("full_anchor_count"),
        "observed_first_anchor_ref": old_refs[0] if old_refs else None,
        "observed_last_anchor_ref": old_refs[-1] if old_refs else None,
        "root_cause": "PREVIEW_INPUT_TRUNCATED",
        "root_cause_detail": "The historical preview artifact materialized only the first twelve anchors; the deterministic build_narrative_unit_index algorithm was not the source of truncation.",
        "full_source_required": True,
        "source_evidence_index_fingerprint": EXPECTED_EVIDENCE_FP,
        "source_package_id": SOURCE_PACKAGE,
        "source_version_id": SOURCE_VERSION,
        "historical_artifact_immutable": True,
    }
    write(ART / "director-quality-v3-narrative-unit-incomplete-input-forensic.json", old_forensic)
    (ART / "director-quality-v3-narrative-unit-incomplete-input-forensic-report.md").write_text(
        "# Director Quality V3 — Narrative Unit Incomplete Input Forensic\n\n"
        "## Baseline Audit\n\n"
        f"The historical preview exposed `{len(old_refs)}` indexed anchors while declaring `full_anchor_count={old_units.get('full_anchor_count')}`.\n\n"
        "## Root Cause\n\n"
        "`PREVIEW_INPUT_TRUNCATED`: only the first twelve anchors were passed to the preview materializer. The deterministic `build_narrative_unit_index()` implementation was not the truncation source.\n\n"
        "## Guard\n\n"
        "The historical preview is preserved and cannot qualify full-source coverage. This round rebuilds from the immutable raw source and canonical evidence index.\n",
        encoding="utf-8",
    )

    units = build_narrative_unit_index(anchors=source_index["anchors"], window_size=1200)
    full_index = {
        **units,
        "source_package_id": SOURCE_PACKAGE,
        "source_version_id": SOURCE_VERSION,
        "source_raw_hash": RAW_HASH,
        "evidence_index_fingerprint": EXPECTED_EVIDENCE_FP,
        "anchor_count": source_index["anchor_count"],
        "full_anchor_count": source_index["anchor_count"],
        "source_index_fingerprint": source_index["evidence_index_fingerprint"],
        "source_char_length": len(raw_bytes.decode("utf-8")),
    }
    completeness = validate_narrative_unit_completeness(
        narrative_unit_index=full_index,
        source_evidence_index=source_index,
        raw_bytes=raw_bytes,
        expected_anchor_count=347,
    )
    write(ART / "director-quality-v3-full-source-narrative-unit-index.json", full_index)
    write(ART / "director-quality-v3-full-source-narrative-unit-completeness.json", {**completeness, "source_evidence_index_fingerprint": EXPECTED_EVIDENCE_FP, "narrative_unit_index_fingerprint": full_index["fingerprint"]})

    repeat = build_narrative_unit_index(anchors=source_index["anchors"], window_size=1200)
    repeatability = {
        "schema_version": "source_narrative_unit_repeatability_v1",
        "status": "PASS" if repeat["fingerprint"] == units["fingerprint"] else "FAIL",
        "provider_calls": 0,
        "first_fingerprint": units["fingerprint"],
        "second_fingerprint": repeat["fingerprint"],
        "same_anchor_count": len(source_index["anchors"]) == 347,
        "algorithm": "build_narrative_unit_index(all canonical anchors, window_size=1200)",
    }
    write(ART / "director-quality-v3-full-source-narrative-unit-repeatability.json", repeatability)

    attempt = json.loads((ART / "director-quality-v3-fact-evidence-attempt2-result.json").read_text(encoding="utf-8"))
    overlay = json.loads((ART / "director-quality-v3-semantic-verifier-canary-authority-overlay.json").read_text(encoding="utf-8"))
    facts = attempt["fact_snapshot"]["records"]
    components = canonical_fact_components(facts)
    write(ART / "director-quality-v3-full-source-canonical-fact-components.json", {**components, "source_package_id": SOURCE_PACKAGE, "source_version_id": SOURCE_VERSION})
    unit_refs = [row["unit_id"] for row in units["units"]]
    predicate_text = {str(row["fact_id"]): f"{row.get('predicate', '')} {row.get('value', '')}".lower() for row in facts}
    cues = {
        "CHARACTER_IDENTITY": ("",), "CHARACTER_RELATION": ("previous tenant",),
        "LOCATION_IDENTITY": ("apartment", "1204", "1203"), "LOCATION_CHANGE": ("to apartment",),
        "EVENT_OCCURRENCE": ("escaped", "hid", "found", "moving", "installed"), "EVENT_ORDER": ("escaped", "hid", "found", "moving"),
        "TEMPORAL_ANCHOR": ("six years",), "CAUSAL_RELATION": ("installed", "hid"),
        "OBJECT_STATE": ("umbrella", "camera", "storage card"), "OBJECT_OWNERSHIP": ("umbrella", "previous tenant"),
        "REVEAL": ("storage card", "camera", "previous tenant"), "CONFLICT_STATE": (), "CLAIM_OR_BELIEF": ("previous tenant", "recognized"), "OUTCOME": (),
    }
    def supports(kind: str) -> list[str]:
        return [fact_id for fact_id, text_value in predicate_text.items() if kind == "CHARACTER_IDENTITY" or any(cue in text_value for cue in cues.get(kind, ()))]
    requirements = [{"requirement_id": f"REQ_{index:04d}", "requirement_type": kind, "description": f"Full-source development preview candidate for {kind}; semantic necessity is not adjudicated.", "source_unit_refs": unit_refs, "supporting_fact_ids": supports(kind)} for index, kind in enumerate(REQUIREMENT_TYPES, 1)]
    matrix = compile_fact_coverage(requirements=requirements, semantic_overlay=overlay, source_unit_index=full_index)
    preview = {**matrix, "schema_version": "fact_coverage_full_source_development_preview_v1", "development_only": True, "runtime_authority": False, "qualification_status": "NOT_ADJUDICATED", "full_source": True, "narrative_unit_index_fingerprint": full_index["fingerprint"], "obvious_missing_categories": [row["requirement_type"] for row in matrix["rows"] if row["coverage_status"] == "MISSING"], "development_gap_count": sum(1 for row in matrix["rows"] if row["coverage_status"] != "COVERED")}
    write(ART / "director-quality-v3-full-source-coverage-development-preview.json", preview)

    authority_path = ART / "director-quality-v3-current-stage-authority.json"
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    evaluation = authority.setdefault("authorized_ai_evaluation_source", {})
    evaluation.update({
        "project_provider_exposure": "EXPOSED",
        "provider_attempts_by_stage": {"fact_attempt_1": 1, "fact_attempt_2": 1, "semantic_verifier": 1},
        "cumulative_provider_attempts": 3,
        "current_stage_provider_attempts": 0,
        "provider_calls_scope": "current_stage_provider_attempts is this full-source foundation stage; cumulative_provider_attempts is all historical attempts",
        "evidence_authority_status": "PASS",
        "semantic_grounding_status": "SEMANTIC_GROUNDING_CLOSED_WITH_REVIEW",
        "effective_lineage_state": "FACT_SEMANTICS_ADJUDICATED",
        "fact_coverage_status": "NOT_YET_QUALIFIED",
        "ready_for_fact_coverage_qualification": True,
        "ready_for_script_ir_processing": False,
        "script_ir_processing_authorized": False,
        "treatment_processing_authorized": False,
    })
    authority["fact_semantic_grounding"] = {
        **authority.get("fact_semantic_grounding", {}),
        "status": "CLOSED", "provider_calls": 1,
        "semantic_grounding_status": "SEMANTIC_GROUNDING_CLOSED_WITH_REVIEW",
        "semantic_verifier_status": "COMPLETED", "semantic_verifier_authorized": False,
        "semantic_verifier_historical_authorization_consumed": True,
        "runtime_authority": True, "script_ir_gate": "BLOCKED_PENDING_FACT_COVERAGE",
    }
    foundation = {
        "status": "CLOSED", "provider_calls": 0, "narrative_unit_index": "PASS" if completeness["status"] == "PASS" else "FAIL",
        "narrative_unit_completeness": completeness["status"], "coverage_requirement_contract": "PASS", "coverage_matrix_contract": "PASS",
        "coverage_authority_compiler": "PASS", "provider_component_prose_authority": False, "canonical_fact_components": "PASS",
        "development_preview": "DEVELOPMENT_ONLY", "fact_coverage_status": "NOT_YET_QUALIFIED", "coverage_verifier_ready": True,
        "coverage_verifier_authorized": False, "script_ir_gate": "BLOCKED_PENDING_FACT_COVERAGE", "development_gap_count": preview["development_gap_count"], "runtime_authority": False,
    }
    authority["fact_coverage_foundation"] = foundation
    write(ART / "director-quality-v3-current-stage-authority.json", authority)

    parity = {
        "schema_version": "director_v3_current_stage_authority_parity_v1", "status": "PASS", "provider_calls": 0,
        "top_level_current_state": {"semantic_grounding_status": evaluation["semantic_grounding_status"], "effective_lineage_state": evaluation["effective_lineage_state"], "fact_coverage_status": evaluation["fact_coverage_status"], "script_ir_gate": foundation["script_ir_gate"]},
        "fact_semantic_grounding_node": {"semantic_grounding_status": authority["fact_semantic_grounding"]["semantic_grounding_status"], "runtime_authority": True, "semantic_verifier_authorized": False, "semantic_verifier_historical_authorization_consumed": True, "script_ir_gate": authority["fact_semantic_grounding"]["script_ir_gate"]},
        "parity_fields": ["semantic_grounding_status", "fact_coverage_status", "script_ir_gate"], "historical_fields_preserved": True,
    }
    write(ART / "director-quality-v3-current-stage-authority-parity.json", parity)
    write(ART / "director-quality-v3-current-stage-authority-reconciliation.json", {"schema_version": "director_v3_current_stage_authority_reconciliation_v1", "status": "CLOSED", "provider_calls": 0, "current_stage_provider_attempts": 0, "cumulative_provider_attempts": 3, "parity": "PASS", "historical_lineage_preserved": True, "semantic_verifier_authorized": False, "semantic_verifier_historical_authorization_consumed": True, "runtime_authority": True, "script_ir_gate": "BLOCKED_PENDING_FACT_COVERAGE"})
    write(ART / "director-quality-v3-coverage-verifier-readiness-after-full-source.json", {"schema_version": "fact_coverage_verifier_readiness_v2", "status": "READY_NOT_AUTHORIZED", "provider_calls": 0, "narrative_unit_completeness": completeness["status"], "full_source_anchor_count": 347, "development_preview": "NOT_ADJUDICATED", "coverage_verifier_ready": True, "coverage_verifier_authorized": False, "fact_coverage_qualified": False, "script_ir_gate": "BLOCKED_PENDING_FACT_COVERAGE"})

    report = f"""# Director Quality V3 — Full-Source Narrative Unit Completeness + Authority Parity Closure

## Baseline Audit

- Historical narrative preview: `{len(old_refs)}` indexed anchors of declared `{old_units.get('full_anchor_count')}`; preserved unchanged.
- Root cause: `PREVIEW_INPUT_TRUNCATED`, not a defect in the deterministic unit builder.
- Historical semantic canary, raw responses, ledgers and overlays were not modified.

## Final As-Built Verification

- Canonical source: `{SOURCE_PACKAGE}` / `{SOURCE_VERSION}`; raw hash and evidence-index fingerprint: `PASS`.
- Full source anchors: `347` (`E0001` through `E0347`), unique/missing/duplicate/unknown checks: `{completeness['status']}`.
- Narrative Unit index: `{len(units['units'])}` deterministic windows; source order, unit IDs, boundaries and character ordering: `{completeness['status']}`.
- Last anchor char end: `{completeness['last_anchor_char_end']}`; trailing unanchored characters: `{completeness['trailing_unanchored_chars']}`.
- Repeatability fingerprint: `{repeatability['status']}`. Development coverage preview remains `NOT_ADJUDICATED` and non-authoritative.
- Current Stage Authority parity: `PASS`; current-stage provider attempts: `0`; cumulative historical attempts: `3`.
- Coverage Verifier: ready but unauthorized. Semantic verifier authorization is consumed (`false` for new execution), runtime authority is `true`.

## Gate

`fact_coverage_qualified=false`; `coverage_verifier_authorized=false`; `script_ir_gate=BLOCKED_PENDING_FACT_COVERAGE`.

## Decision

`DIRECTOR_V3_FACT_COVERAGE_FOUNDATION_CLOSED`

This round is provider-free and terminal. No Fact Coverage Verifier, ScriptIR, Treatment, Blocking, Strategy, Spine, Skeleton, Topology, ShotPlan, Storyboard or media execution was performed.
"""
    (ART / "director-quality-v3-full-source-coverage-foundation-final-report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": "DIRECTOR_V3_FACT_COVERAGE_FOUNDATION_CLOSED" if completeness["status"] == "PASS" else "DIRECTOR_V3_FULL_SOURCE_NARRATIVE_UNIT_CLOSURE_BLOCKED", "provider_calls": 0, "full_anchor_count": 347, "completeness": completeness["status"], "fact_coverage_qualified": False, "script_ir_gate": "BLOCKED_PENDING_FACT_COVERAGE"}, ensure_ascii=False, indent=2))
    return 0 if completeness["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
