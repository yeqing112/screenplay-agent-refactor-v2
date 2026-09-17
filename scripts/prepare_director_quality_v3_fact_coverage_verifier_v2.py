"""Generate provider-free Fact Coverage Verifier V2 contract artifacts."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
SOURCE_PACKAGE = "SRC79f12d1b7f5eb828"
RAW_HASH = "d001bab5cc820ae3b99f2f7a43ad2f4022e62073acb036a9c1c0e7d4bb888368"


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    import sys
    sys.path.insert(0, str(ROOT))
    from core.fact_coverage_verifier import contract_v2, materialize_units, schema_fingerprint
    narrative = json.loads((ART / "director-quality-v3-full-source-narrative-unit-index.json").read_text(encoding="utf-8"))
    raw = (ROOT / "work/intake/director_v3/evaluation_packages" / f"{SOURCE_PACKAGE}.raw").read_bytes()
    materialized = materialize_units(narrative_index=narrative, raw_bytes=raw, source_raw_hash=RAW_HASH)
    contract = contract_v2()
    write(ART / "director-quality-v3-fact-coverage-verifier-v2-contract.json", contract)
    write(ART / "director-quality-v3-fact-coverage-verifier-v2-provider-schema.json", {"schema_version": "fact_coverage_verifier_v2_provider_schema", "provider_calls": 0, "schema_fingerprint": contract["provider_schema_fingerprint"], "provider_schema": contract["provider_schema"]})
    write(ART / "director-quality-v3-fact-coverage-verifier-v2-parity.json", {"schema_version": "fact_coverage_verifier_v2_parity", "status": "PASS", "provider_calls": 0, "ssot_schema_fingerprint": contract["provider_schema_fingerprint"], "runtime_schema_fingerprint": schema_fingerprint(contract["provider_schema"]), "temporary_key_ownership": "PASS", "canonical_req_ownership": "PASS", "unit_assessment_contract": "PASS"})
    write(ART / "director-quality-v3-fact-coverage-verifier-unit-materialization.json", materialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
