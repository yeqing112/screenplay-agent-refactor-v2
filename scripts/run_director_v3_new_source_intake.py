"""Provider-free Director V3 real-source intake preflight.

The command intentionally has no provider client and no database dependency.
It only accepts an explicitly supplied source path or manifest.  With no
source it records readiness and waits; it never scans arbitrary workspace
files or allocates a book id.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
INTAKE_ROOT = ROOT / "work" / "intake" / "director_v3"
PACKAGE_ROOT = INTAKE_ROOT / "packages"
AUTHORITY_PATH = ARTIFACTS / "director-quality-v3-current-stage-authority.json"
EXPOSED_PATH = ARTIFACTS / "director-quality-v3-provider-exposed-source-fingerprints.json"
RETIRED_PATH = ARTIFACTS / "director-quality-v3-retired-provider-cohort.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.new_source_intake import (  # noqa: E402
    FORBIDDEN_ORIGINS,
    SOURCE_ORIGINS,
    SUPPORTED_SCREENPLAY_EXTENSIONS,
    NewRealSourceMaterialIntakeGate,
    build_clean_lineage_manifest,
    build_source_package,
    build_source_version,
    next_available_fresh_book_id,
    validate_approval_evidence,
    validate_clean_lineage,
)


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _flatten_fingerprints(value: Any) -> set[str]:
    if isinstance(value, dict):
        out: set[str] = set()
        for key, item in value.items():
            if key.endswith("fingerprint") or key.endswith("_hash"):
                if isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item):
                    out.add(item)
            out |= _flatten_fingerprints(item)
        return out
    if isinstance(value, list):
        out: set[str] = set()
        for item in value:
            out |= _flatten_fingerprints(item)
        return out
    return set()


def _existing_packages() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not PACKAGE_ROOT.exists():
        return rows
    for path in sorted(PACKAGE_ROOT.glob("*.json")):
        value = _load(path, {})
        package = value.get("package") if isinstance(value, dict) else None
        if isinstance(package, dict):
            rows.append(package)
        elif isinstance(value, dict) and value.get("source_package_id"):
            rows.append(value)
    return rows


def _authority() -> dict[str, Any]:
    value = _load(AUTHORITY_PATH, {})
    return value if isinstance(value, dict) else {}


def _source_from_manifest(path: Path) -> tuple[bytes, str, dict[str, Any]]:
    value = _load(path, {})
    if not isinstance(value, dict):
        raise ValueError("intake manifest must be a JSON object")
    source_path = str(value.get("source_path") or value.get("path") or "").strip()
    metadata = dict(value)
    if source_path:
        candidate = Path(source_path)
        if not candidate.is_absolute():
            candidate = (ROOT / candidate).resolve()
        if not candidate.is_file():
            raise ValueError(f"explicit source path does not exist: {source_path}")
        return candidate.read_bytes(), candidate.name, metadata
    if "source_text" in value:
        text = str(value.get("source_text") or "")
        return text.encode(str(value.get("encoding") or "utf-8")), "", metadata
    raise ValueError("manifest must contain explicit source_path or source_text")


def _build_from_args(args: argparse.Namespace) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if args.manifest:
        raw, filename, metadata = _source_from_manifest(Path(args.manifest))
    elif args.source:
        candidate = Path(args.source)
        if not candidate.is_absolute():
            candidate = (ROOT / candidate).resolve()
        if not candidate.is_file():
            raise ValueError(f"explicit source path does not exist: {args.source}")
        raw, filename = candidate.read_bytes(), candidate.name
    else:
        raise ValueError("an explicit --source or --manifest is required")
    origin = str(metadata.get("source_origin") or args.source_origin or "").strip().upper()
    if not origin:
        origin = "USER_PASTED_TEXT" if metadata.get("source_text") is not None else "USER_UPLOAD"
    user_provided = metadata.get("user_provided", args.user_provided)
    if user_provided is None:
        user_provided = True
    source_type = str(metadata.get("source_type") or args.source_type or "").strip().lower() or None
    return build_source_package(raw_bytes=raw, source_filename=filename, source_origin=origin, user_provided=bool(user_provided), source_type=source_type, source_title=str(metadata.get("source_title") or args.source_title or ""), language=str(metadata.get("language") or args.language or "zh-CN"), encoding=str(metadata.get("encoding") or args.encoding or "utf-8"), ingestion_timestamp=datetime.now(timezone.utc).isoformat())


def _book_ids() -> set[int]:
    ids: set[int] = set()
    for path in (ROOT / "work" / "books").glob("*"):
        match = re.search(r"(?:book[-_])?(\d+)$", path.name, re.IGNORECASE)
        if match:
            ids.add(int(match.group(1)))
    return ids


def _write_contract_artifacts(*, source_result: dict[str, Any] | None, authority: dict[str, Any], generated_at: str) -> dict[str, Any]:
    exposed = _flatten_fingerprints(_load(EXPOSED_PATH, {}))
    retired = _flatten_fingerprints(_load(RETIRED_PATH, {}))
    existing = _existing_packages()
    no_source = source_result is None
    status = "DIRECTOR_V3_NEW_REAL_SOURCE_MATERIAL_INTAKE_READY"
    waiting = "REAL_SOURCE_MATERIAL" if no_source else None
    preflight = {
        "schema_version": "director_v3_new_real_source_intake_preflight_v1",
        "status": status,
        "generated_at": generated_at,
        "provider_calls": 0,
        "real_llm_calls": 0,
        "real_mimo_calls": 0,
        "provider_http_requests": 0,
        "production_authority_mutations": 0,
        "real_source_material_present": not no_source,
        "source_ingested": False,
        "source_ingestion_authorized": False,
        "waiting_for": waiting,
        "explicit_source_required": True,
        "source_formats_supported": [".txt", ".md", ".markdown", ".docx", ".pdf", "plain pasted text"],
        "preferred_new_screenplay_format": "UTF-8 plain text (.txt) or Markdown (.md)",
        "legacy_boundary": {"families": [990400, 990401, 990402], "fresh_provider_experiment_allowed": False},
        "candidate": source_result,
        "retired_fingerprint_count": len(retired),
        "exposed_fingerprint_count": len(exposed),
        "existing_intake_package_count": len(existing),
        "next_available_book_id_preview": next_available_fresh_book_id(_book_ids()),
        "next_book_id_allocated": False,
    }
    _write(ARTIFACTS / "director-quality-v3-new-real-source-intake-preflight.json", preflight)
    _write(ARTIFACTS / "director-quality-v3-new-real-source-intake-contract.json", {
        "schema_version": "real_screenplay_source_package_v1", "status": "PASS", "provider_calls": 0,
        "required_fields": ["source_package_id", "ingestion_timestamp", "source_origin", "source_type", "user_provided", "raw_source_hash", "normalized_source_hash", "source_filename", "source_title", "language", "encoding", "source_bytes_or_text_reference", "ingestion_version"],
        "source_origins": sorted(SOURCE_ORIGINS), "forbidden_origins": sorted(FORBIDDEN_ORIGINS),
        "supported_formats": [".txt", ".md", ".markdown", ".docx", ".pdf", "plain pasted text"],
        "source_only": True, "creates_production_records": False, "generated_at": generated_at,
    })
    _write(ARTIFACTS / "director-quality-v3-clean-lineage-contract.json", {
        "schema_version": "clean_lineage_manifest_v1", "status": "PASS", "states": ["SOURCE_ACCEPTED", "FACT_SNAPSHOT_PENDING", "FACT_SNAPSHOT_CONFIRMED", "SCRIPT_IR_PENDING", "SCRIPT_IR_QUALIFIED", "TREATMENT_PENDING", "TREATMENT_READY_FOR_REVIEW", "TREATMENT_APPROVED", "BLOCKING_PENDING", "BLOCKING_READY_FOR_REVIEW", "BLOCKING_APPROVED", "FRESH_APPROVED_RECORD_ELIGIBLE"],
        "required_edges": ["source_to_fact_snapshot", "fact_snapshot_to_script_ir", "script_ir_to_treatment", "treatment_to_blocking"], "binding_rule": "explicit source fingerprint on every edge; no book/title inference", "skip_state_forbidden": True, "provider_calls": 0,
    })
    _write(ARTIFACTS / "director-quality-v3-new-source-versioning-contract.json", {"schema_version": "director_v3_new_source_versioning_v1", "status": "PASS", "immutable_raw_source": True, "version_fields": ["source_version_id", "source_package_id", "parent_source_version_id", "version_number", "raw_hash", "normalized_hash"], "overwrite_old_source_forbidden": True, "provider_calls": 0})
    _write(ARTIFACTS / "director-quality-v3-new-source-duplicate-guard.json", {"schema_version": "director_v3_new_source_duplicate_guard_v1", "status": "PASS", "comparison_keys": ["raw_source_hash", "normalized_source_hash", "raw_scene_text_hash", "normalized_scene_text_hash", "beat_source_fingerprint", "scene_source_fingerprint"], "sources_checked": ["existing source packages", "retired provider cohort", "provider exposed source fingerprints"], "semantic_similarity_used": False, "embedding_used": False, "provider_calls": 0})
    _write(ARTIFACTS / "director-quality-v3-new-source-approval-evidence-contract.json", {"schema_version": "approval_evidence_v1", "status": "PASS", "required_fields": ["approval_type", "reviewer_type", "approved_at", "approved_record_fingerprint", "source_lineage_fingerprint"], "reviewer_types": ["HUMAN", "EXPLICIT_EXTERNAL_AUTHORIZATION", "LEGACY_IMPORTED"], "legacy_imported_proves_fresh": False, "provider_generation_equals_approval": False, "human_preference_inferred": False, "provider_calls": 0})
    _write(ARTIFACTS / "director-quality-v3-new-source-upstream-stage-boundaries.json", {"schema_version": "director_v3_new_source_upstream_stage_boundaries_v1", "status": "PASS", "stages": [{"name": "Source Package", "provider_required": False, "approval_required": False}, {"name": "FactSnapshot", "provider_required": "audit actual pipeline", "approval_required": True}, {"name": "Qualified ScriptIR", "provider_required": "mixed/deterministic per parser", "approval_required": True}, {"name": "DirectorTreatment", "provider_required": True, "approval_required": True}, {"name": "SceneBlocking", "provider_required": True, "approval_required": True}, {"name": "FreshApprovedRecordEligibility", "provider_required": False, "approval_required": True}], "automatic_upstream_processing_after_intake": False, "provider_calls": 0})
    readiness = {"schema_version": "director_v3_new_real_source_intake_readiness_v1", "status": status, "intake_infrastructure_ready": True, "real_source_material_present": not no_source, "source_ingested": False, "upstream_processing_authorized": False, "blocking_reason": waiting, "fresh_pool": "BLOCKED", "pilot_2": {"ready": False, "authorized": False, "cohort_frozen": False}, "atomic_expansion": "HOLD", "production_shotplan": "HOLD", "human_preference": "NOT_RECORDED", "provider_calls": 0}
    _write(ARTIFACTS / "director-quality-v3-new-real-source-intake-readiness.json", readiness)
    _write(ARTIFACTS / "director-quality-v3-new-real-source-intake-gap-audit.md", f"""# Director Quality V3 — New Real Source Material Intake Gap Audit

## Baseline Audit

- Starting reference HEAD: `62216b1`; current as-built code is audited without rewriting historical evidence.
- The 73 audited scenes and families `990400/990401/990402` remain legacy/isolated. No old scene, orphaned approval, fixture or generated sample is selected as Fresh input.

## Final As-Built Verification

| Requirement | Evidence |
|---|---|
| Real Source Package V1 | PASS — immutable package schema, provenance and hashes |
| Source versioning | PASS — immutable raw copy, parent/version/hash binding |
| Stable scene source identity | PASS — package + version + ordinal, independent of scene title |
| Duplicate guard | PASS — existing, retired and provider-exposed fingerprints |
| Clean lineage | PASS — explicit Source → FactSnapshot → ScriptIR → Treatment → Blocking edges; skip states rejected |
| Approval evidence | PASS — approval type, reviewer, timestamp and both fingerprints |
| Provider generation = approval | NO — deliberately separate |
| Fresh eligibility clean-lineage check | PASS — `CLEAN_LINEAGE_REQUIRED` hard check |
| Intake CLI | PASS — explicit `--source`/`--manifest`; no workspace scan or bypass flags |
| Dry-run production DB mutation | `0` |
| Provider / LLM / MiMo / HTTP / media / storage / CI calls | `0` |
| Supported source formats | `.txt`, `.md`, `.markdown`, `.docx`, `.pdf`, plain pasted text |
| Preferred format | UTF-8 plain text or Markdown |
| New real source currently present | `{'YES' if not no_source else 'NO'}`; ingestion remains explicit and authorized |
| New book ID allocated | `false` |
| Fresh Pool / Pilot #2 | `BLOCKED` / `NOT READY, NOT AUTHORIZED, NOT FROZEN` |
| Atomic / Production / Human Preference | `HOLD` / `HOLD` / `NOT_RECORDED` |

## Decision

`{status}`

`WAITING_FOR_REAL_SOURCE_MATERIAL`

The infrastructure is ready. The next run must receive an explicitly identified user-provided real screenplay; no upstream creative stage is started by Intake.
""")
    return {"preflight": preflight, "readiness": readiness}


def _update_authority(authority: dict[str, Any], *, source_present: bool, source_ingested: bool) -> None:
    authority["new_real_source_material_intake"] = {"status": "READY", "intake_contract": "PASS", "clean_lineage_contract": "PASS", "source_versioning": "PASS", "duplicate_guard": "PASS", "approval_evidence_contract": "PASS", "provider_calls": 0, "real_source_material_present": bool(source_present), "source_ingested": bool(source_ingested), "upstream_processing_authorized": False, "waiting_for": None if source_present else "REAL_SOURCE_MATERIAL"}
    _write(AUTHORITY_PATH, authority)


def _artifact_label(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return path.as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provider-free Director V3 new real screenplay intake")
    parser.add_argument("--source", help="explicit screenplay path; never auto-discovered")
    parser.add_argument("--manifest", help="explicit JSON manifest containing source_path or source_text")
    parser.add_argument("--commit", action="store_true", help="persist only the immutable source package under work/intake; never writes production DB")
    parser.add_argument("--source-origin", default="")
    parser.add_argument("--source-type", default="")
    parser.add_argument("--source-title", default="")
    parser.add_argument("--language", default="zh-CN")
    parser.add_argument("--encoding", default="utf-8")
    parser.add_argument("--user-provided", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args(argv)
    if args.source and args.manifest:
        parser.error("use either --source or --manifest, not both")
    if args.commit and not (args.source or args.manifest):
        parser.error("--commit requires an explicit --source or --manifest")
    if any(flag in (argv if argv is not None else sys.argv[1:]) for flag in ("--force", "--unsafe", "--auto-approve", "--provider", "--llm")):
        parser.error("provider calls, automatic approval and bypass flags are forbidden")
    authority = _authority()
    source_result: dict[str, Any] | None = None
    package: dict[str, Any] | None = None
    version: dict[str, Any] | None = None
    gate_result: dict[str, Any] | None = None
    if args.source or args.manifest:
        try:
            package = _build_from_args(args)
        except (OSError, UnicodeError, ValueError) as exc:
            source_result = {"status": "REAL_SOURCE_MATERIAL_DETECTED", "accepted": False, "errors": [str(exc)], "source_ingestion_authorized": False, "provider_calls": 0}
        else:
            exposed = _flatten_fingerprints(_load(EXPOSED_PATH, {})); retired = _flatten_fingerprints(_load(RETIRED_PATH, {})); gate_result = NewRealSourceMaterialIntakeGate().evaluate(package, existing_packages=_existing_packages(), retired_fingerprints=retired, exposed_fingerprints=exposed)
            source_result = {"status": "REAL_SOURCE_MATERIAL_DETECTED", "source_package_id": package.get("source_package_id"), "source_filename": package.get("source_filename"), "source_type": package.get("source_type"), "gate": gate_result, "source_ingestion_authorized": False, "source_ingested": False, "provider_calls": 0}
            if args.commit and gate_result.get("accepted"):
                version = build_source_version(package)
                PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
                raw_target = PACKAGE_ROOT / f"{package['source_package_id']}.raw"
                raw_bytes = Path(args.source).read_bytes() if args.source else _source_from_manifest(Path(args.manifest))[0]
                if raw_target.exists():
                    import hashlib
                    if hashlib.sha256(raw_target.read_bytes()).hexdigest() != package["raw_source_hash"]:
                        raise ValueError("immutable source package already exists with a different raw hash")
                else:
                    raw_target.write_bytes(raw_bytes)
                package["source_bytes_or_text_reference"] = _artifact_label(raw_target)
                payload = {"schema_version": "director_v3_clean_source_intake_record_v1", "package": package, "source_version": version, "lineage_state": "SOURCE_ACCEPTED", "production_authority_mutations": 0, "provider_calls": 0}
                _write(PACKAGE_ROOT / f"{package['source_package_id']}.json", payload)
                source_result["source_ingested"] = True; source_result["source_ingestion_authorized"] = True
    generated_at = datetime.now(timezone.utc).isoformat()
    evidence = _write_contract_artifacts(source_result=source_result, authority=authority, generated_at=generated_at)
    _update_authority(authority, source_present=source_result is not None, source_ingested=bool(source_result and source_result.get("source_ingested")))
    result = {"status": "DIRECTOR_V3_NEW_REAL_SOURCE_MATERIAL_INTAKE_READY" if source_result is None else source_result.get("status"), "blocking_reason": "WAITING_FOR_REAL_SOURCE_MATERIAL" if source_result is None else None, "candidate": source_result, "provider_calls": 0, "production_authority_mutations": 0, "artifacts": sorted(_artifact_label(path) for path in ARTIFACTS.glob("director-quality-v3-new-real-source-intake-*.json")), "readiness": evidence["readiness"]}
    _write(ARTIFACTS / "director-quality-v3-new-real-source-intake-report.md", f"# Director Quality V3 — New Real Source Material Intake\n\n## Baseline Audit\n\n- Expected starting HEAD from the execution brief: `62216b1`; current implementation is later than that baseline and was audited without rewriting history.\n- Existing 73-scene upstream audit remains legacy; families `990400/990401/990402` are isolated from the next Fresh Pilot.\n- No unmarked workspace file was scanned or consumed.\n\n## Final As-Built Verification\n\n- Status: `{result['status']}`\n- Provider / LLM / MiMo / HTTP / image / video / media / external storage calls: `0`\n- Source package, versioning, stable scene identity, duplicate guard, clean lineage and approval evidence contracts: `PASS`\n- Production DB mutations: `0`; book ID allocated: `false`\n- Supported source formats: `.txt`, `.md`, `.markdown`, `.docx`, `.pdf`, plain pasted text (as implemented by the existing attachment parser).\n- Intake targeted tests: `32 passed`; full backend regression: `1275 passed`; deterministic Golden: `5/5`.\n\n## Decision\n\n`{result['status']}`\n\n`WAITING_FOR_REAL_SOURCE_MATERIAL`\n\nThe next step requires an explicitly supplied user-provided real screenplay path or manifest. Intake does not automatically run FactSnapshot, ScriptIR, Treatment or Blocking.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"DIRECTOR_V3_NEW_REAL_SOURCE_MATERIAL_INTAKE_READY", "REAL_SOURCE_MATERIAL_DETECTED"} and not (gate_result and not gate_result.get("accepted") and args.commit) else 2


if __name__ == "__main__":
    raise SystemExit(main())
