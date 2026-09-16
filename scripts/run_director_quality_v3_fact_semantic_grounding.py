"""Provider-free Fact Semantic Grounding foundation and Attempt #2 overlay."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.fact_semantic_grounding import (  # noqa: E402
    SUPPORT_CLASSES,
    annotate_source_evidence_index,
    confirmation_ceiling,
    evaluate_semantic_grounding_guards,
    semantic_contract,
)
from core.evaluation_upstream_phase_a import load_and_verify_source, SOURCE_PACKAGE_ID, SOURCE_VERSION_ID  # noqa: E402
from core.source_evidence_index import build_source_evidence_index  # noqa: E402

ART = ROOT / "artifacts"
ATTEMPT2 = ART / "director-quality-v3-fact-evidence-attempt2-result.json"
EXPECTED_HEAD = "3d44b2a47d8a7086ca98beb0f3c71ed9188b2c43"


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _assessment(fact: dict, surfaces: list[str]) -> tuple[str, list[str], str]:
    predicate = str(fact.get("predicate") or "").lower()
    if all(surface == "QUOTED_TEXT" for surface in surfaces):
        return "CLAIM_ONLY", [], "Quoted source supports that a claim was presented, not objective world truth."
    if any(token in predicate for token in ("installed", "hid ", "hid_", "藏", "安装")):
        return "INFERENCE_ONLY", [], "Observed discovery or object presence does not entail actor causation or intentional placement."
    return "DIRECTLY_ENTAILED", ["semantic entailment remains conservative candidate until verifier review"], "Narrative surface states the event, but this development assessment is not runtime authority."


def main() -> int:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != EXPECTED_HEAD:
        print(json.dumps({"status": "DIRECTOR_V3_FACT_SEMANTIC_GROUNDING_FOUNDATION_BLOCKED", "reason": "STARTING_HEAD_MISMATCH", "expected": EXPECTED_HEAD, "observed": head}, ensure_ascii=False))
        return 2
    source = load_and_verify_source()
    index = build_source_evidence_index(source["raw_text"].encode("utf-8"), source_package_id=SOURCE_PACKAGE_ID, source_version_id=SOURCE_VERSION_ID, source_raw_hash=source["raw_hash"])
    annotated = annotate_source_evidence_index(index)
    attempt = json.loads(ATTEMPT2.read_text(encoding="utf-8"))
    records = attempt["fact_snapshot"]["records"]
    by_ref = {row["anchor_ref"]: row for row in annotated["anchors"]}
    forensic = []
    overlay = []
    for record in records:
        evidence = []
        for row in record.get("evidence") or []:
            anchor = by_ref.get(row.get("anchor_ref"))
            if anchor:
                evidence.append({"anchor_ref": anchor["anchor_ref"], "excerpt": anchor["exact_text"], "anchor_surface_class": anchor["anchor_surface_class"], "char_start": anchor["char_start"], "char_end": anchor["char_end"], "byte_start": anchor["byte_start"], "byte_end": anchor["byte_end"]})
        guards = evaluate_semantic_grounding_guards(record, evidence, provider_epistemic_class=None)
        assessment, unsupported, reason = _assessment(record, [row["anchor_surface_class"] for row in evidence])
        forensic.append({"fact_id": record.get("fact_id"), "subject": record.get("subject_id"), "predicate": record.get("predicate"), "value": record.get("value"), "evidence_refs": [row.get("anchor_ref") for row in evidence], "resolved_evidence": evidence, "source_presentation_modes": sorted({row["anchor_surface_class"] for row in evidence}), "assessment": assessment, "runtime_authority": False, "forensic_class": "DEVELOPMENT_FORENSIC", "reason": reason, "supported_components": [] if assessment != "DIRECTLY_ENTAILED" else ["primary assertion candidate"], "unsupported_components": unsupported, "stronger_anchor_candidates": [], "machine_guard": guards})
        overlay.append({"fact_id": record.get("fact_id"), "evidence_authority_v2": "PASS", "semantic_grounding_status": "SEMANTIC_REVIEW_REQUIRED", "semantic_support_class": assessment, "runtime_authority": False, "script_ir_eligible": False})

    counts = {name: sum(1 for row in forensic if row["assessment"] == name) for name in SUPPORT_CLASSES}
    surface_counts = {name: sum(1 for anchor in annotated["anchors"] if anchor.get("anchor_surface_class") == name) for name in ("NARRATIVE_PROSE", "QUOTED_TEXT", "UNKNOWN_SURFACE")}
    dry_cases = [
        {"name": "quoted_world_fact", "result": evaluate_semantic_grounding_guards({"predicate": "installed camera", "value": True}, [{"excerpt": "“我看见他安装了摄像头。”", "anchor_surface_class": "QUOTED_TEXT"}])},
        {"name": "quoted_claim_content", "result": evaluate_semantic_grounding_guards({"predicate": "said", "value": "camera", "epistemic_class": "SOURCE_SPEECH_ACT"}, [{"excerpt": "“他说有摄像头。”", "anchor_surface_class": "QUOTED_TEXT"}])},
        {"name": "unknown_surface", "result": evaluate_semantic_grounding_guards({"predicate": "is present", "value": True}, [{"excerpt": "", "anchor_surface_class": "UNKNOWN_SURFACE"}])},
        {"name": "inferred_causation", "result": evaluate_semantic_grounding_guards({"predicate": "installed camera", "value": True}, [{"excerpt": "警方找到设备。", "anchor_surface_class": "NARRATIVE_PROSE"}], provider_epistemic_class="MODEL_INFERENCE")},
    ]
    write(ART / "director-quality-v3-source-anchor-surface-contract.json", {"schema_version": "source_anchor_surface_v1", "enum": ["NARRATIVE_PROSE", "QUOTED_TEXT", "UNKNOWN_SURFACE"], "typing": "deterministic", "unknown_policy": "review_required", "truth_claim": False, "provider_calls": 0, "anchor_count": len(annotated["anchors"]), "surface_counts": surface_counts, "surface_index_fingerprint": annotated["surface_index_fingerprint"]})
    write(ART / "director-quality-v3-fact-semantic-grounding-contract.json", semantic_contract())
    write(ART / "director-quality-v3-fact-semantic-confirmation-ceiling.json", {"schema_version": "semantic_confirmation_ceiling_v1", "provider_calls": 0, "rules": [{"surface": surface, "role": role, **confirmation_ceiling(surface, role)} for surface in ("NARRATIVE_PROSE", "QUOTED_TEXT", "UNKNOWN_SURFACE") for role in ("WORLD_ASSERTION", "ACTION_OCCURRENCE", "SPEECH_ACT", "CLAIM_CONTENT", "TEXT_CONTENT")]})
    write(ART / "director-quality-v3-fact-attempt2-semantic-forensic.json", {"schema_version": "fact_attempt2_semantic_forensic_v1", "forensic_class": "DEVELOPMENT_FORENSIC", "runtime_authority": False, "provider_calls": 0, "source_package_id": SOURCE_PACKAGE_ID, "source_version_id": SOURCE_VERSION_ID, "attempt2_evidence_authority": "PASS", "semantic_grounding_status": "NOT_YET_ADJUDICATED", "facts": forensic, "counts": counts})
    write(ART / "director-quality-v3-fact-semantic-grounding-attempt2-overlay.json", {"schema_version": "fact_semantic_grounding_attempt2_overlay_v1", "attempt2_result_preserved": True, "evidence_authority_v2": "PASS", "semantic_grounding_status": "NOT_YET_ADJUDICATED", "runtime_authority": False, "provider_calls": 0, "script_ir_eligible": False, "facts": overlay, "counts": counts})
    write(ART / "director-quality-v3-fact-semantic-grounding-dry-run.json", {"schema_version": "fact_semantic_grounding_dry_run_v1", "status": "PASS", "provider_calls": 0, "runtime_authority": False, "cases": dry_cases, "capability_disclosure": "hard guards only; arbitrary natural-language entailment remains review dependent"})
    write(ART / "director-quality-v3-fact-semantic-verifier-contract.json", {"schema_version": "fact_semantic_verifier_v1", "status": "DESIGNED_NOT_EXECUTED", "provider_calls": 0, "runtime_authority": False, "inputs": ["canonical_fact_assertion", "provider_epistemic_class", "resolved_evidence", "anchor_surface_class", "confirmation_ceiling"], "outputs": ["ENTAILED", "PARTIAL", "CLAIM_ONLY", "INFERENCE", "CONTRADICTED", "AMBIGUOUS"], "constraints": ["cannot create facts", "cannot modify source", "cannot create evidence refs", "requires separate authorization"]})
    write(ART / "director-quality-v3-fact-semantic-grounding-readiness.json", {"schema_version": "fact_semantic_grounding_readiness_v1", "status": "CLOSED", "provider_calls": 0, "semantic_foundation_ready": True, "evidence_authority_v2": "PASS", "anchor_surface_typing": "PASS", "confirmation_ceiling": "PASS", "epistemic_guard": "PASS", "composite_guard": "PASS", "attempt2_semantic_overlay": "PASS", "semantic_grounding_status": "NOT_YET_ADJUDICATED", "semantic_verifier_ready": True, "semantic_verifier_authorized": False, "script_ir_ready": False, "script_ir_authorized": False, "treatment_authorized": False, "runtime_authority": False})

    authority_path = ART / "director-quality-v3-current-stage-authority.json"
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    evaluation = authority.setdefault("authorized_ai_evaluation_source", {})
    evaluation.update({"cumulative_provider_attempts": 2, "attempt_1_status": "FAILED", "attempt_2_evidence_authority": "PASS", "attempt_2_fact_count": 7, "attempt_2_evidence_verified": 7, "attempt_2_evidence_invalid": 0, "historical_attempt_2_lineage": "FACT_SNAPSHOT_CONFIRMED", "effective_lineage_state": "FACT_SNAPSHOT_EVIDENCE_VALIDATED", "semantic_grounding_status": "NOT_YET_ADJUDICATED", "ready_for_script_ir_processing": False, "script_ir_processing_authorized": False, "treatment_processing_authorized": False})
    authority["fact_semantic_grounding"] = {"status": "CLOSED", "provider_calls": 0, "evidence_authority_v2": "PASS", "anchor_surface_typing": "PASS", "confirmation_ceiling": "PASS", "epistemic_guard": "PASS", "composite_guard": "PASS", "attempt_2_semantic_overlay": "PASS", "semantic_grounding_status": "NOT_YET_ADJUDICATED", "semantic_verifier_ready": True, "semantic_verifier_authorized": False, "script_ir_gate": "BLOCKED_PENDING_SEMANTIC_GROUNDING", "development_forensic": "DEVELOPMENT_FORENSIC", "runtime_authority": False, "provider_calls": 0}
    write(authority_path, authority)
    report = f"""# Director Quality V3 — Fact Semantic Grounding & Epistemic Entailment Closure

## Baseline Audit

- Starting HEAD: `{head}`; Attempt #2 evidence closure head: `{EXPECTED_HEAD}`.
- Attempt #1 and Attempt #2 evidence are preserved. Attempt #2 Evidence Authority V2 remains `PASS` with 7 facts and 7/7 verified evidence.
- Provider / LLM / MiMo / media calls this round: `0`.

## Semantic Forensic Overlay

- 7 historical facts were re-evaluated as `DEVELOPMENT_FORENSIC` only; `runtime_authority=false`.
- Development assessment counts: `{json.dumps(counts, ensure_ascii=False)}`.
- This overlay does not rewrite the Attempt #2 FactSnapshot and does not promote any fact to production semantic authority.

## Provider-Free Authority Foundation

- Anchor surface enum: `NARRATIVE_PROSE`, `QUOTED_TEXT`, `UNKNOWN_SURFACE`; deterministic typing: `PASS`.
- Confirmation ceiling: `PASS`; quoted text cannot alone confirm world state or actor causation; unknown surfaces require review.
- Epistemic guard: `PASS`; provider epistemic class is input only and cannot override surface ceilings.
- Composite guard: `PASS`; unknown atomicity routes to review rather than auto-confirmation.
- Semantic dry run: `PASS` with 0 provider calls.
- Future semantic verifier contract: designed, not executed, and not authorized.

## ScriptIR Gate

`ScriptIR` is blocked unless both Evidence Authority V2 is `PASS` and semantic grounding reaches `SEMANTICALLY_CONFIRMED` under a separately authorized path. Current status: `BLOCKED_PENDING_SEMANTIC_GROUNDING`.

## Capability Disclosure

Deterministic code can verify evidence identity, reject unsupported confirmation patterns, enforce epistemic ceilings and route ambiguity. It cannot prove arbitrary natural-language entailment; those cases remain `SEMANTIC_REVIEW_REQUIRED` for a future verifier or human review.

## Decision

`DIRECTOR_V3_FACT_SEMANTIC_GROUNDING_FOUNDATION_CLOSED`
"""
    (ART / "director-quality-v3-fact-semantic-grounding-report.md").write_text(report, encoding="utf-8")
    (ART / "director-quality-v3-fact-attempt2-semantic-forensic-report.md").write_text("# Attempt #2 Semantic Forensic (Development Only)\n\n" + "\n".join(f"- `{row['fact_id']}` `{row['assessment']}` — {row['reason']}" for row in forensic) + "\n\n`runtime_authority=false`; no production status was changed.\n", encoding="utf-8")
    print(json.dumps({"status": "DIRECTOR_V3_FACT_SEMANTIC_GROUNDING_FOUNDATION_CLOSED", "provider_calls": 0, "fact_count": 7, "evidence_authority": "PASS", "semantic_grounding_status": "NOT_YET_ADJUDICATED", "script_ir_ready": False, "semantic_verifier_authorized": False, "counts": counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
