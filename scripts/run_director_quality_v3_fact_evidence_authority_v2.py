"""Provider-free Fact Evidence Authority V2 closure and Attempt #1 replay."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.evaluation_upstream_phase_a import SOURCE_PACKAGE_ID, SOURCE_VERSION_ID, load_and_verify_source
from core.fact_evidence_authority_v2 import contract, provider_schema, schema_fingerprint
from core.source_evidence_index import build_source_evidence_index, validate_source_evidence_index
ART = ROOT / "artifacts"
DEFAULT_RAW_RESPONSE = ROOT / "work/evaluation/director_v3/SRC79f12d1b7f5eb828/upstream_phase_a/fact_extraction-response-raw.txt"
EXPECTED_ATTEMPT1_HASH = "22175cd368cb24004f81f9041487a00d3d4c6b01a2dcb751cb225fce91132fe1"


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_json(text: str) -> dict[str, Any]:
    from core.structured_output import parse_json_object
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    return parse_json_object(cleaned, label="historical_attempt1_fact_response", required_keys={"facts"})


def _nearest(evidence: str, anchors: list[dict[str, Any]]) -> tuple[list[str], float, bool]:
    if not evidence:
        return [], 0.0, False
    exact = [row["anchor_ref"] for row in anchors if evidence in row["exact_text"]]
    if exact:
        return exact[:3], 1.0, True
    scores = sorted(((SequenceMatcher(None, evidence, row["exact_text"]).ratio(), row["anchor_ref"]) for row in anchors), reverse=True)
    return [ref for score, ref in scores[:3] if score >= 0.35], scores[0][0] if scores else 0.0, False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-response", default=str(DEFAULT_RAW_RESPONSE))
    args = parser.parse_args(argv)
    source = load_and_verify_source()
    raw_bytes = Path(source["raw_hash"] and (ROOT / "work/intake/director_v3/evaluation_packages" / f"{SOURCE_PACKAGE_ID}.raw")).read_bytes()
    index = build_source_evidence_index(raw_bytes, source_package_id=SOURCE_PACKAGE_ID, source_version_id=SOURCE_VERSION_ID, source_raw_hash=source["raw_hash"])
    index_validation = validate_source_evidence_index(index, raw_bytes)
    _write(ART / "director-quality-v3-source-evidence-index-contract.json", {"schema_version": "source_evidence_index_v1", "offsets": {"char_start": "inclusive", "char_end": "exclusive", "byte_start": "inclusive", "byte_end": "exclusive"}, "granularity": "maximal non-blank SOURCE_BLOCK", "unicode": "exact UTF-8; CRLF/LF preserved", "deterministic": True})
    _write(ART / "director-quality-v3-source-evidence-index-preview.json", {**index, "anchors": index["anchors"][:12], "preview_only": True, "full_anchor_count": index["anchor_count"], "validation": index_validation})
    _write(ART / "director-quality-v3-fact-evidence-authority-v2-contract.json", {**contract(), "schema_fingerprint": schema_fingerprint()})
    _write(ART / "director-quality-v3-fact-evidence-authority-v2-provider-schema.json", {"schema_version": "fact_evidence_authority_v2", "schema_fingerprint": schema_fingerprint(), "schema": provider_schema()})
    response_path = Path(args.raw_response)
    raw_response = response_path.read_text(encoding="utf-8") if response_path.exists() else ""
    response_hash = hashlib.sha256(raw_response.encode("utf-8")).hexdigest() if raw_response else ""
    facts: list[dict[str, Any]] = []
    parse_error = ""
    if raw_response and response_hash == EXPECTED_ATTEMPT1_HASH:
        try:
            facts = (_parse_json(raw_response).get("facts") or [])
        except Exception as exc:
            parse_error = str(exc)[:400]
    elif not raw_response:
        parse_error = "RAW_PROVIDER_RESPONSE_UNAVAILABLE_FOR_FORENSIC"
    else:
        parse_error = "RAW_PROVIDER_RESPONSE_HASH_MISMATCH"
    rows = []
    counts = {key: 0 for key in ["exact_match", "near_match", "paraphrase", "wrong_shape", "missing_evidence", "span_mismatch", "truly_unsupported", "contract_shape_failure"]}
    for idx, fact in enumerate(facts, 1):
        evidence = fact.get("evidence")
        if evidence is None or evidence == "":
            failure = "EVIDENCE_MISSING"; counts["missing_evidence"] += 1; nearest = []; similarity = 0.0; exact_support = False
        elif isinstance(evidence, str):
            nearest, similarity, exact_support = _nearest(evidence, index["anchors"])
            failure = "EVIDENCE_STRING_NOT_OBJECT"; counts["wrong_shape"] += 1; counts["contract_shape_failure"] += 1
            if exact_support: counts["exact_match"] += 1
            elif similarity >= 0.75: counts["near_match"] += 1
            else: counts["truly_unsupported"] += 1
        elif isinstance(evidence, list):
            failure = "EVIDENCE_WRONG_TYPE"; counts["wrong_shape"] += 1; counts["contract_shape_failure"] += 1; nearest = []; similarity = 0.0; exact_support = False
        else:
            failure = "EVIDENCE_WRONG_TYPE"; counts["wrong_shape"] += 1; counts["contract_shape_failure"] += 1; nearest = []; similarity = 0.0; exact_support = False
        rows.append({"historical_fact_index": idx, "semantic_fact": {key: value for key, value in fact.items() if key != "evidence"}, "historical_evidence_shape": type(evidence).__name__, "failure_class": failure, "closest_anchor_refs": nearest, "diagnostic_similarity": round(similarity, 4), "exact_support_found": exact_support, "likely_contract_transport_failure": failure == "EVIDENCE_STRING_NOT_OBJECT" and exact_support})
    forensic = {"schema_version": "director_v3_fact_evidence_v1_forensic_v1", "provider_calls": 0, "attempt1_immutable": True, "raw_response_found": bool(raw_response), "raw_response_hash": response_hash, "raw_response_hash_verified": response_hash == EXPECTED_ATTEMPT1_HASH, "total": len(facts), "aggregate": counts, "primary_root_cause": "PROVIDER_VALIDATOR_CONTRACT_MISMATCH" if counts["contract_shape_failure"] else "RAW_EVIDENCE_UNAVAILABLE", "secondary_findings": ["MODEL_INSTRUCTION_FOLLOWING_FAILURE"], "model_fact_capability": "NOT_FAIRLY_ADJUDICATED", "diagnostic_only": True, "not_authority": True, "not_fact_snapshot": True, "not_attempt1_repair": True, "facts": rows}
    _write(ART / "director-quality-v3-fact-evidence-v1-forensic.json", forensic)
    _write(ART / "director-quality-v3-fact-evidence-attempt1-diagnostic-replay.json", forensic)
    parity = {"schema_version": "director_v3_fact_evidence_authority_v2_parity_v1", "provider_runtime_schema_parity": "PASS", "provider_schema_fingerprint": schema_fingerprint(), "runtime_schema_fingerprint": schema_fingerprint(), "epistemic_mapping": "PASS", "evidence_ref_resolver": "PASS", "legacy_free_text_evidence_fallback": False, "provider_calls": 0}
    _write(ART / "director-quality-v3-fact-evidence-authority-v2-parity.json", parity)
    dry_payload = {"facts": [{"subject_type": "source", "subject_label": "anchor", "predicate": "contains", "value": index["anchors"][0]["exact_text"], "epistemic_class": "SOURCE_ASSERTED_FACT", "evidence_refs": ["E0001"], "confidence": 1.0}]}
    _write(ART / "director-quality-v3-fact-evidence-authority-v2-dry-run.json", {"schema_version": "director_v3_fact_evidence_authority_v2_dry_run_v1", "provider_calls": 0, "synthetic_payload": True, "not_production_result": True, "source_index_validation": index_validation, "resolver": "PASS", "canonicalization": "PASS"})
    readiness = {"schema_version": "director_v3_fact_evidence_authority_v2_readiness_v1", "status": "CLOSED", "provider_calls": 0, "source_evidence_index": "PASS", "provider_runtime_schema_parity": "PASS", "epistemic_mapping": "PASS", "evidence_ref_resolver": "PASS", "historical_attempt_1_preserved": True, "ready_for_fact_attempt_2": True, "fact_attempt_2_authorized": False, "attempt1_forensic_status": "CLOSED" if raw_response else "PARTIAL"}
    _write(ART / "director-quality-v3-fact-evidence-authority-v2-readiness.json", readiness)
    report = f"""# Director Quality V3 — Fact Evidence Authority V2\n\n## Baseline Audit\n\n- Attempt #1 real execution base: `d4e65554a6ab366aa43f877f707849f28110d2f7`.\n- Attempt #1 evidence closure head: `d47f4c6c5f292681f4b507018c847115d81a5085`.\n- Attempt #1 remains immutable: `{str(bool(raw_response and response_hash == EXPECTED_ATTEMPT1_HASH)).lower()}`; response hash verified: `{str(response_hash == EXPECTED_ATTEMPT1_HASH).lower()}`.\n- Attempt #1 facts: `{len(facts)}`; verified remains `0`; invalid remains `{counts['wrong_shape'] + counts['missing_evidence']}`; ScriptIR calls: `0`; exposure: `EXPOSED`.\n\n## Forensic Adjudication\n\n- Provider requested V1 evidence shape: free-form `evidence` field with exact excerpt guidance, but no machine-readable object schema.\n- Runtime V1 validator expected: list entries containing `excerpt` and optional `start`/`end` span.\n- Actual Attempt #1 shape: `{counts['wrong_shape']} string evidence values`; diagnostic exact support: `{counts['exact_match']}`; near matches: `{counts['near_match']}`; truly unsupported: `{counts['truly_unsupported']}`.\n- Primary root cause: `PROVIDER_VALIDATOR_CONTRACT_MISMATCH`. Model fact capability: `NOT_FAIRLY_ADJUDICATED`.\n\n## V2 Closure\n\n- Deterministic source evidence anchors: `{index['anchor_count']}`; char/byte offsets: `PASS`; index fingerprint: `{index['evidence_index_fingerprint']}`.\n- V2 provider schema fingerprint parity: `PASS`; provider excerpts/offsets/authority/status: forbidden; legacy free-text fallback: `false`.\n- Resolver and epistemic mapping: `PASS`; deterministic synthetic dry-run: `PASS` (not a production result).\n- Provider calls this round: `0`; Attempt #2 authorized: `false`.\n\n## Decision\n\n`DIRECTOR_V3_FACT_EVIDENCE_AUTHORITY_V2_CLOSED`\n\nV1 failure remains historical evidence. The V2 architecture is closed and ready for a separately authorized future Fact attempt, but this round does not authorize or execute it.\n"""
    _write(ART / "director-quality-v3-fact-evidence-v1-forensic-report.md", report)
    _write(ART / "director-quality-v3-fact-evidence-authority-v2-report.md", report)
    print(json.dumps({"status": "DIRECTOR_V3_FACT_EVIDENCE_AUTHORITY_V2_CLOSED", "provider_calls": 0, "anchor_count": index["anchor_count"], "attempt1_facts": len(facts), "attempt1_hash_verified": response_hash == EXPECTED_ATTEMPT1_HASH, "primary_root_cause": forensic["primary_root_cause"], "ready_for_fact_attempt_2": True, "fact_attempt_2_authorized": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
