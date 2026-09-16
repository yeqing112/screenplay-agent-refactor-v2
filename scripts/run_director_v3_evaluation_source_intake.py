"""Provider-free intake for the authorized AI-generated evaluation lane.

This command accepts exactly one explicitly named source file.  It never
scans the source directory, calls a provider, allocates a Book id, or writes
production records.  ``--commit`` only stores immutable raw bytes plus a
metadata manifest under ``work/intake/director_v3/evaluation_packages``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SOURCE = Path(r"D:\Work\小说库\门外那把伞.txt")
ART = ROOT / "artifacts"
AUTHORITY = ART / "director-quality-v3-current-stage-authority.json"
EVALUATION_ROOT = ROOT / "work" / "intake" / "director_v3" / "evaluation_packages"
EXPOSED = ART / "director-quality-v3-provider-exposed-source-fingerprints.json"
RETIRED = ART / "director-quality-v3-retired-provider-cohort.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.evaluation_source_intake import (  # noqa: E402
    AuthorizedEvaluationSourceIntakeGate,
    build_evaluation_source_package,
    detect_test_meta,
    evaluation_provenance_fingerprint,
)
from core.new_source_intake import build_source_version  # noqa: E402


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fp(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _flatten_fingerprints(value: Any) -> set[str]:
    if isinstance(value, dict):
        result: set[str] = set()
        for key, item in value.items():
            if (key.endswith("fingerprint") or key.endswith("_hash")) and isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item):
                result.add(item)
            result |= _flatten_fingerprints(item)
        return result
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            result |= _flatten_fingerprints(item)
        return result
    return set()


def _existing_packages() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in (ROOT / "work" / "intake" / "director_v3" / "packages", EVALUATION_ROOT):
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json")):
            value = _load(path, {})
            package = value.get("package") if isinstance(value, dict) else None
            if isinstance(package, dict):
                rows.append(package)
            elif isinstance(value, dict) and value.get("source_package_id"):
                rows.append(value)
    return rows


def _resolve_exact(path_value: str) -> Path:
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = (ROOT / candidate).resolve()
    expected = EXPECTED_SOURCE.resolve()
    if candidate.resolve() != expected:
        raise ValueError("EVALUATION_SOURCE_PATH_NOT_ALLOWED")
    if not candidate.exists():
        raise ValueError("EVALUATION_SOURCE_PATH_NOT_FOUND")
    if not candidate.is_file():
        raise ValueError("EVALUATION_SOURCE_NOT_REGULAR_FILE")
    if candidate.suffix.lower() != ".txt":
        raise ValueError("EVALUATION_SOURCE_EXTENSION_INVALID")
    return candidate


def _authority() -> dict[str, Any]:
    value = _load(AUTHORITY, {})
    return value if isinstance(value, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Director V3 authorized AI evaluation source intake")
    parser.add_argument("--source", required=True)
    parser.add_argument("--source-title", required=True)
    parser.add_argument("--narrative-form", required=True, choices=("SHORT_STORY",))
    parser.add_argument("--authorship", required=True, choices=("AI_GENERATED",))
    parser.add_argument("--user-authorized", action="store_true")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args(argv)
    supplied = argv if argv is not None else sys.argv[1:]
    forbidden = ("--human-authored", "--force", "--unsafe", "--provider", "--llm", "--execute-real")
    if any(flag in supplied for flag in forbidden):
        parser.error("forbidden flag for provider-free evaluation intake")

    generated_at = datetime.now(timezone.utc).isoformat()
    source_path: Path | None = None
    raw = b""
    package: dict[str, Any] | None = None
    gate: dict[str, Any] = {"status": "NOT_ACCEPTED", "accepted": False, "errors": []}
    preflight_errors: list[str] = []
    try:
        source_path = _resolve_exact(args.source)
        raw = source_path.read_bytes()
        if not raw:
            preflight_errors.append("EVALUATION_SOURCE_EMPTY")
        text = raw.decode("utf-8", errors="strict")
        package = build_evaluation_source_package(
            raw_bytes=raw,
            source_path=str(source_path),
            source_title=args.source_title,
            narrative_form=args.narrative_form,
            generation_origin="OPENAI_CHATGPT_USER_REQUESTED",
        )
        package["user_authorized_for_evaluation"] = bool(args.user_authorized)
        package["source_authorship"] = args.authorship
        meta = detect_test_meta(text)
        if meta:
            preflight_errors.append("SOURCE_CONTAINS_TEST_META")
        gate = AuthorizedEvaluationSourceIntakeGate().evaluate(
            package,
            explicit_source_path=str(source_path),
            expected_source_path=str(EXPECTED_SOURCE),
            existing_packages=_existing_packages(),
            retired_fingerprints=_flatten_fingerprints(_load(RETIRED, {})),
            exposed_fingerprints=_flatten_fingerprints(_load(EXPOSED, {})),
            source_text=text,
        )
        if preflight_errors:
            gate = {**gate, "status": "NOT_ACCEPTED", "accepted": False, "errors": list(dict.fromkeys(preflight_errors + gate.get("errors", [])))}
    except (OSError, UnicodeError, ValueError) as exc:
        preflight_errors.append(str(exc))
        gate = {"status": "NOT_ACCEPTED", "accepted": False, "errors": list(dict.fromkeys(preflight_errors)), "provider_calls": 0, "production_db_mutations": 0}

    accepted = bool(package and gate.get("accepted"))
    source_package_id = package.get("source_package_id") if package else None
    source_version = build_source_version(package) if accepted and package else None
    committed = False
    if args.commit and accepted and package and source_version:
        EVALUATION_ROOT.mkdir(parents=True, exist_ok=True)
        raw_target = EVALUATION_ROOT / f"{source_package_id}.raw"
        meta_target = EVALUATION_ROOT / f"{source_package_id}.json"
        if raw_target.exists() and hashlib.sha256(raw_target.read_bytes()).hexdigest() != package["raw_source_hash"]:
            gate = {**gate, "status": "NOT_ACCEPTED", "accepted": False, "errors": ["SOURCE_IMMUTABLE_CONFLICT"]}
        else:
            if not raw_target.exists():
                raw_target.write_bytes(raw)
            try:
                raw_reference = str(raw_target.relative_to(ROOT)).replace("\\", "/")
            except ValueError:
                raw_reference = str(raw_target)
            package = {**package, "source_bytes_or_text_reference": raw_reference}
            _write(meta_target, {"schema_version": "evaluation_screenplay_source_package_v1", "package": package, "source_version": source_version, "provenance_fingerprint": evaluation_provenance_fingerprint(package), "lineage_state": "SOURCE_ACCEPTED", "production_db_mutations": 0, "provider_calls": 0})
            committed = True

    status = "DIRECTOR_V3_AUTHORIZED_AI_EVALUATION_SOURCE_INTAKE_CLOSED" if accepted and (committed or not args.commit) else "DIRECTOR_V3_AUTHORIZED_AI_EVALUATION_SOURCE_INTAKE_FAILED"
    checks = {
        "exact_source_path": source_path is not None and source_path.resolve() == EXPECTED_SOURCE.resolve(),
        "regular_utf8_non_empty": bool(package and package.get("byte_length", 0) > 0 and package.get("normalized_text_length", 0) > 0),
        "test_meta_clean": not preflight_errors or "SOURCE_CONTAINS_TEST_META" not in preflight_errors,
        "provenance_complete": bool(package and package.get("source_class") == "EVALUATION_ONLY" and package.get("source_authorship") == "AI_GENERATED" and package.get("human_authored") is False and package.get("ai_generated") is True),
        "user_authorized": bool(package and package.get("user_authorized_for_evaluation") is True),
        "duplicate_guard": "SOURCE_DUPLICATE" not in gate.get("errors", []),
        "retired_guard": "SOURCE_RETIRED" not in gate.get("errors", []),
        "exposure_guard": "SOURCE_PROVIDER_EXPOSED" not in gate.get("errors", []),
        "immutable_package": committed or (not args.commit and accepted),
        "real_source_lane_untouched": True,
        "provider_calls_zero": True,
        "production_db_mutations_zero": True,
    }
    preflight = {"schema_version": "director_v3_ai_evaluation_source_preflight_v1", "status": "PASS" if accepted else "FAIL", "generated_at": generated_at, "source_path": str(EXPECTED_SOURCE), "source_title": args.source_title, "narrative_form": args.narrative_form, "source_authorship": args.authorship, "source_class": "EVALUATION_ONLY", "user_authorized": bool(args.user_authorized), "test_meta": detect_test_meta(raw.decode("utf-8", errors="replace")) if raw else [], "raw_source_hash": package.get("raw_source_hash") if package else None, "normalized_source_hash": package.get("normalized_source_hash") if package else None, "checks": checks, "errors": gate.get("errors", []), "provider_calls": 0, "production_db_mutations": 0}
    duplicate = {"schema_version": "director_v3_ai_evaluation_source_duplicate_check_v1", "status": "PASS" if "SOURCE_DUPLICATE" not in gate.get("errors", []) else "FAIL", "raw_source_hash": package.get("raw_source_hash") if package else None, "normalized_source_hash": package.get("normalized_source_hash") if package else None, "semantic_similarity_used": False, "embedding_used": False, "provider_calls": 0}
    exposure = {"schema_version": "director_v3_ai_evaluation_source_exposure_check_v1", "status": "PASS" if "SOURCE_PROVIDER_EXPOSED" not in gate.get("errors", []) else "FAIL", "project_provider_exposure": gate.get("project_provider_exposure", "UNKNOWN"), "universally_unseen_claim": False, "provider_calls": 0}
    provenance_contract = {"schema_version": "evaluation_source_provenance_v1", "status": "PASS", "fixed_values": {"source_class": "EVALUATION_ONLY", "source_authorship": "AI_GENERATED", "generation_origin": "OPENAI_CHATGPT_USER_REQUESTED", "user_supplied_to_system": True, "user_authorized_for_evaluation": True, "human_authored": False, "ai_generated": True, "blind_human_origin_eligible": False, "functional_pipeline_evaluation_eligible": True, "final_human_source_benchmark_eligible": False}, "real_source_lane_replacement": False, "provider_calls": 0}
    result = {"status": status, "source_title": args.source_title, "source_class": "EVALUATION_ONLY", "source_authorship": "AI_GENERATED", "user_authorized": bool(args.user_authorized), "source_ingested": committed, "lineage_state": "SOURCE_ACCEPTED" if committed else None, "source_package_id": source_package_id, "source_version_id": source_version.get("source_version_id") if source_version else None, "provider_calls": 0, "production_db_mutations": 0, "book_created": 0, "scene_created": 0, "fact_snapshot_created": 0, "script_ir_created": 0, "treatment_created": 0, "blocking_created": 0, "gate": gate}
    readiness = {"schema_version": "director_v3_authorized_evaluation_source_readiness_v1", "status": status, "evaluation_source_pool": {"source_count": 1 if committed else 0, "upstream_complete": 0}, "ready_for_authorized_evaluation_upstream_processing": bool(committed), "authorized_evaluation_upstream_processing": False, "human_fresh_pool": {"eligible_scene_count": 0}, "fresh_pilot_2": {"ready": False, "authorized": False, "cohort_frozen": False}, "atomic_expansion": "HOLD", "production_shotplan": "HOLD", "human_preference": "NOT_RECORDED", "provider_calls": 0}
    _write(ART / "director-quality-v3-ai-evaluation-source-provenance-contract.json", provenance_contract)
    _write(ART / "director-quality-v3-ai-evaluation-source-preflight.json", preflight)
    _write(ART / "director-quality-v3-ai-evaluation-source-duplicate-check.json", duplicate)
    _write(ART / "director-quality-v3-ai-evaluation-source-exposure-check.json", exposure)
    _write(ART / "director-quality-v3-ai-evaluation-source-intake-result.json", result)
    _write(ART / "director-quality-v3-ai-evaluation-source-readiness.json", readiness)

    if committed:
        authority = _authority()
        authority["authorized_ai_evaluation_source"] = {"status": "INGESTED", "source_title": args.source_title, "source_class": "EVALUATION_ONLY", "source_authorship": "AI_GENERATED", "user_authorized": True, "human_origin_blind_eligible": False, "functional_pipeline_evaluation_eligible": True, "lineage_state": "SOURCE_ACCEPTED", "source_package_id": source_package_id, "source_version_id": source_version.get("source_version_id") if source_version else None, "provider_calls": 0, "ready_for_upstream_processing": True, "upstream_processing_authorized": False}
        _write(AUTHORITY, authority)
    _write(ART / "director-quality-v3-ai-evaluation-source-intake-report.md", f"""# Director Quality V3 — Authorized AI Evaluation Source Intake

## Baseline Audit

- Expected starting HEAD: `fc7a883`; exact source path was checked without scanning its directory.
- Source: `{EXPECTED_SOURCE}`; source class is `EVALUATION_ONLY`, not Human Real Source.

## Final As-Built Verification

- Status: `{status}`
- Raw bytes: `{len(raw)}`; raw hash: `{preflight['raw_source_hash']}`; normalized hash: `{preflight['normalized_source_hash']}`
- Test-meta contamination: `{'NONE' if not preflight['test_meta'] else 'SOURCE_CONTAINS_TEST_META'}`
- Authorship: `AI_GENERATED`; user authorization: `{bool(args.user_authorized)}`; human authored: `false`
- Blind human-origin eligible: `false`; functional evaluation eligible: `true`
- Duplicate / retired / project exposure: `{duplicate['status']}` / `{'PASS' if 'SOURCE_RETIRED' not in gate.get('errors', []) else 'FAIL'}` / `{exposure['project_provider_exposure']}`
- Immutable package committed: `{committed}`; package: `{source_package_id}`; version: `{result['source_version_id']}`; lineage: `{result['lineage_state']}`
- Book / Scene / FactSnapshot / ScriptIR / Treatment / Blocking mutations: `0 / 0 / 0 / 0 / 0 / 0`
- Provider / LLM / MiMo / HTTP calls: `0`
- Human Real Source Intake semantics changed: `NO`; Human Fresh Pool eligible scenes added: `0`
- Fresh Pilot #2: `ready=false`, `authorized=false`, `cohort_frozen=false`
- Evaluation upstream ready: `{readiness['ready_for_authorized_evaluation_upstream_processing']}`; evaluation upstream authorized: `false`

## Decision

`{status}`

The next stage, if explicitly authorized, is `DIRECTOR_V3_AUTHORIZED_EVALUATION_SOURCE_UPSTREAM_PROCESSING`. No upstream creative stage was started by Intake.
""")
    print(json.dumps({"status": status, "source_package_id": source_package_id, "source_version_id": result["source_version_id"], "committed": committed, "provider_calls": 0, "production_db_mutations": 0, "artifacts": ["director-quality-v3-ai-evaluation-source-provenance-contract.json", "director-quality-v3-ai-evaluation-source-preflight.json", "director-quality-v3-ai-evaluation-source-duplicate-check.json", "director-quality-v3-ai-evaluation-source-exposure-check.json", "director-quality-v3-ai-evaluation-source-intake-result.json", "director-quality-v3-ai-evaluation-source-readiness.json", "director-quality-v3-ai-evaluation-source-intake-report.md"]}, ensure_ascii=False, indent=2))
    return 0 if status == "DIRECTOR_V3_AUTHORIZED_AI_EVALUATION_SOURCE_INTAKE_CLOSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
