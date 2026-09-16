"""Clean-lineage real screenplay intake primitives.

This module handles source packages only.  It never creates a Book, Scene,
FactSnapshot, ScriptIR, Treatment or Blocking record and never calls a
provider.  A later authorized workflow may consume the immutable package.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SOURCE_ORIGINS = {"USER_UPLOAD", "USER_PASTED_TEXT", "USER_PROVIDED_LIBRARY_FILE", "EXTERNAL_AUTHORIZED_IMPORT"}
FORBIDDEN_ORIGINS = {"GENERATED_FOR_TEST", "SYNTHETIC", "FIXTURE", "GOLDEN", "INTERNAL_SAMPLE"}
SUPPORTED_SCREENPLAY_EXTENSIONS = {".txt", ".md", ".markdown", ".docx", ".pdf"}
SUPPORTED_SOURCE_TYPES = {"text", "pasted", "txt", "md", "markdown", "docx", "pdf"}
LINEAGE_STATES = ("SOURCE_ACCEPTED", "FACT_SNAPSHOT_PENDING", "FACT_SNAPSHOT_CONFIRMED", "SCRIPT_IR_PENDING", "SCRIPT_IR_QUALIFIED", "TREATMENT_PENDING", "TREATMENT_READY_FOR_REVIEW", "TREATMENT_APPROVED", "BLOCKING_PENDING", "BLOCKING_READY_FOR_REVIEW", "BLOCKING_APPROVED", "FRESH_APPROVED_RECORD_ELIGIBLE")


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_source_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\r\n", "\n").replace("\r", "\n")).strip()


def extract_source_text(raw_bytes: bytes, *, source_type: str, encoding: str = "utf-8") -> tuple[str, str]:
    """Extract bounded source text using the repository's deterministic parsers.

    This deliberately does not interpret document instructions or call a
    provider.  The returned status is recorded in the immutable package so a
    later upstream stage can distinguish extracted text from an unavailable
    parser.
    """
    kind = str(source_type or "text").strip().lower()
    try:
        if kind in {"text", "pasted", "txt", "md", "markdown"}:
            return raw_bytes.decode(encoding, errors="replace")[:24000], "extracted"
        if kind == "docx":
            with zipfile.ZipFile(BytesIO(raw_bytes)) as archive:
                xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
            text = xml.replace("</w:p>", "\n")
            text = re.sub(r"<[^>]+>", "", text)
            return text[:24000], "extracted"
        if kind == "pdf":
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(raw_bytes))
            return "\n".join((page.extract_text() or "") for page in reader.pages)[:24000], "extracted"
    except Exception:
        return "", "failed"
    return "", "unavailable"


def source_package_id(raw_hash: str, normalized_hash: str) -> str:
    return "SRC" + hashlib.sha256(f"{raw_hash}:{normalized_hash}".encode("ascii")).hexdigest()[:16]


def source_version_id(package_id: str, version_number: int, raw_hash: str) -> str:
    return f"{package_id}:V{int(version_number):02d}:{raw_hash[:12]}"


def stable_scene_source_id(package_id: str, version_id: str, ordinal: int) -> str:
    if int(ordinal) < 1:
        raise ValueError("scene ordinal must be positive")
    return f"{package_id}:{version_id.split(':')[-2] if ':V' in version_id else 'V01'}:SC{int(ordinal):03d}"


def next_available_fresh_book_id(existing_ids: Iterable[int], minimum: int = 990403) -> int:
    used = {int(value) for value in existing_ids if str(value).isdigit()}
    candidate = max(int(minimum), 1)
    while candidate in used:
        candidate += 1
    return candidate


def build_source_package(*, raw_bytes: bytes, source_filename: str = "", source_origin: str, user_provided: bool, source_type: str | None = None, source_title: str = "", language: str = "zh-CN", encoding: str = "utf-8", ingestion_timestamp: str = "", ingestion_version: str = "real_screenplay_source_package_v1") -> dict[str, Any]:
    suffix = Path(source_filename).suffix.lower()
    resolved_type = (source_type or suffix.lstrip(".") or "text").lower()
    text, extraction_status = extract_source_text(raw_bytes, source_type=resolved_type, encoding=encoding)
    raw_hash = sha256_bytes(raw_bytes)
    normalized_hash = sha256_bytes(normalize_source_text(text).encode("utf-8"))
    package_id = source_package_id(raw_hash, normalized_hash)
    return {"schema_version": "real_screenplay_source_package_v1", "source_package_id": package_id, "ingestion_timestamp": ingestion_timestamp, "source_origin": str(source_origin or "").strip().upper(), "source_type": resolved_type, "user_provided": bool(user_provided), "raw_source_hash": raw_hash, "normalized_source_hash": normalized_hash, "source_filename": Path(source_filename).name if source_filename else "", "source_title": str(source_title or "").strip(), "language": language, "encoding": encoding, "source_bytes_or_text_reference": f"intake://{package_id}", "ingestion_version": ingestion_version, "byte_length": len(raw_bytes), "text_extraction_status": extraction_status, "normalized_text_length": len(normalize_source_text(text))}


def build_source_version(package: dict[str, Any], *, version_number: int = 1, parent_source_version_id: str | None = None) -> dict[str, Any]:
    version_id = source_version_id(package["source_package_id"], version_number, package["raw_source_hash"])
    return {"source_version_id": version_id, "source_package_id": package["source_package_id"], "parent_source_version_id": parent_source_version_id, "version_number": int(version_number), "raw_hash": package["raw_source_hash"], "normalized_hash": package["normalized_source_hash"], "immutable": True}


def validate_source_version(version: dict[str, Any], package: dict[str, Any], *, parent: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate a version binding without mutating the prior source."""
    errors: list[str] = []
    if not isinstance(version, dict) or version.get("immutable") is not True: errors.append("SOURCE_VERSION_NOT_IMMUTABLE")
    if str(version.get("source_package_id") or "") != str(package.get("source_package_id") or ""): errors.append("SOURCE_VERSION_PACKAGE_MISMATCH")
    if str(version.get("raw_hash") or "") != str(package.get("raw_source_hash") or ""): errors.append("SOURCE_VERSION_RAW_HASH_MISMATCH")
    if str(version.get("normalized_hash") or "") != str(package.get("normalized_source_hash") or ""): errors.append("SOURCE_VERSION_NORMALIZED_HASH_MISMATCH")
    number = version.get("version_number")
    if not isinstance(number, int) or number < 1: errors.append("SOURCE_VERSION_NUMBER_INVALID")
    if isinstance(number, int) and number > 1:
        if not parent or version.get("parent_source_version_id") != parent.get("source_version_id") or parent.get("version_number") != number - 1: errors.append("SOURCE_VERSION_PARENT_INVALID")
    elif version.get("parent_source_version_id") is not None: errors.append("SOURCE_VERSION_PARENT_UNEXPECTED")
    return {"status": "PASS" if not errors else "FAIL", "errors": list(dict.fromkeys(errors))}


def scene_fingerprints(*, raw_scene_text: str, normalized_scene_text: str | None = None, beat_sequence: list[Any] | None = None) -> dict[str, str]:
    normalized = normalize_source_text(normalized_scene_text if normalized_scene_text is not None else raw_scene_text)
    beats = beat_sequence or []
    beat_payload = [{"id": str(item.get("id") or item.get("beat_id") or index), "text": normalize_source_text(item.get("event") or item.get("description") or item) if isinstance(item, dict) else normalize_source_text(item)} for index, item in enumerate(beats, 1)]
    return {"raw_scene_text_hash": sha256_bytes(str(raw_scene_text or "").encode("utf-8")), "normalized_scene_text_hash": sha256_bytes(normalized.encode("utf-8")), "beat_source_fingerprint": sha256_bytes(canonical(beat_payload).encode("utf-8")), "scene_source_fingerprint": sha256_bytes(canonical({"scene": normalized, "beats": beat_payload}).encode("utf-8"))}


@dataclass(frozen=True)
class NewRealSourceMaterialIntakeGate:
    """Fail-closed source-only acceptance gate."""

    def evaluate(self, package: dict[str, Any], *, existing_packages: Iterable[dict[str, Any]] = (), retired_fingerprints: Iterable[str] = (), exposed_fingerprints: Iterable[str] = ()) -> dict[str, Any]:
        errors: list[str] = []
        raw_hash, normalized_hash = str(package.get("raw_source_hash") or ""), str(package.get("normalized_source_hash") or "")
        origin = str(package.get("source_origin") or "").upper()
        if not raw_hash or not normalized_hash or int(package.get("byte_length") or 0) <= 0: errors.append("SOURCE_EMPTY")
        if package.get("user_provided") is not True: errors.append("SOURCE_NOT_USER_PROVIDED")
        if not origin: errors.append("SOURCE_PROVENANCE_MISSING")
        if origin in FORBIDDEN_ORIGINS: errors.append("SOURCE_SYNTHETIC_FORBIDDEN" if origin in {"SYNTHETIC", "GENERATED_FOR_TEST"} else "SOURCE_FIXTURE_FORBIDDEN")
        if origin not in SOURCE_ORIGINS and origin not in FORBIDDEN_ORIGINS: errors.append("SOURCE_PROVENANCE_MISSING")
        if not package.get("source_filename") and package.get("source_type") not in {"text", "pasted"}: errors.append("SOURCE_FILENAME_MISSING")
        if package.get("source_type") not in SUPPORTED_SOURCE_TYPES: errors.append("SOURCE_TYPE_UNSUPPORTED")
        if package.get("source_type") in {"docx", "pdf"} and package.get("text_extraction_status") != "extracted": errors.append("SOURCE_TEXT_EXTRACTION_UNAVAILABLE")
        if package.get("source_type") in SUPPORTED_SOURCE_TYPES and int(package.get("normalized_text_length") or 0) <= 0: errors.append("SOURCE_EMPTY")
        if not re.fullmatch(r"[0-9a-f]{64}", raw_hash) or not re.fullmatch(r"[0-9a-f]{64}", normalized_hash): errors.append("SOURCE_VERSION_INVALID")
        fingerprints = {raw_hash, normalized_hash}
        if fingerprints & {str(value) for value in retired_fingerprints}: errors.extend(("SOURCE_RETIRED", "SOURCE_RETIRED_FOR_PROVIDER_EXPERIMENT"))
        if fingerprints & {str(value) for value in exposed_fingerprints}: errors.extend(("SOURCE_PROVIDER_EXPOSED", "SOURCE_ALREADY_PROVIDER_EXPOSED"))
        if any(raw_hash == str(item.get("raw_source_hash")) or normalized_hash == str(item.get("normalized_source_hash")) for item in existing_packages if isinstance(item, dict)): errors.extend(("SOURCE_DUPLICATE", "SOURCE_ALREADY_EXISTS"))
        unique = list(dict.fromkeys(errors))
        return {"status": "NEW_REAL_SOURCE_ACCEPTED" if not unique else "NOT_ACCEPTED", "accepted": not unique, "errors": unique, "source_package_id": package.get("source_package_id"), "provider_calls": 0, "production_authority_mutations": 0}


def _record_fingerprint(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return ""
    explicit = str(value.get("fingerprint") or value.get("source_fingerprint") or "").strip()
    return explicit or hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def build_clean_lineage_manifest(*, source_package: dict[str, Any], source_version: dict[str, Any], scene_source_id: str, fact_snapshot: dict[str, Any] | None = None, script_ir: dict[str, Any] | None = None, director_treatment: dict[str, Any] | None = None, scene_blocking: dict[str, Any] | None = None, approval_evidence: list[dict[str, Any]] | dict[str, Any] | None = None, exposure_state: str = "NOT_EXPOSED", fresh_eligibility: bool = False, lineage_state: str = "SOURCE_ACCEPTED") -> dict[str, Any]:
    """Create an explicit, auditable lineage envelope without approving it."""
    source_fp = str(source_package.get("normalized_source_hash") or source_package.get("raw_source_hash") or "").strip()
    package_id = str(source_package.get("source_package_id") or "").strip()
    version_id = str(source_version.get("source_version_id") or "").strip()
    def edge(name: str, target: Any) -> dict[str, str]:
        target_fp = _record_fingerprint(target)
        return {"edge": name, "source_fingerprint": source_fp, "target_source_fingerprint": source_fp, "target_record_fingerprint": target_fp}
    return {
        "schema_version": "clean_lineage_manifest_v1", "source_package_id": package_id, "source_version_id": version_id,
        "scene_source_id": str(scene_source_id or "").strip(), "source_fingerprint": source_fp,
        "fact_snapshot": fact_snapshot or {}, "script_ir": script_ir or {}, "director_treatment": director_treatment or {}, "scene_blocking": scene_blocking or {},
        "approval_evidence": approval_evidence or [], "exposure_state": exposure_state, "fresh_eligibility": bool(fresh_eligibility), "lineage_state": lineage_state,
        "lineage_edges": {"source_to_fact_snapshot": edge("source_to_fact_snapshot", fact_snapshot), "fact_snapshot_to_script_ir": edge("fact_snapshot_to_script_ir", script_ir), "script_ir_to_treatment": edge("script_ir_to_treatment", director_treatment), "treatment_to_blocking": edge("treatment_to_blocking", scene_blocking)},
    }


def validate_clean_lineage(manifest: dict[str, Any], *, strict: bool = False) -> dict[str, Any]:
    required = ("source_package_id", "source_version_id", "scene_source_id", "source_fingerprint", "fact_snapshot", "script_ir", "director_treatment", "scene_blocking", "approval_evidence", "exposure_state", "fresh_eligibility")
    errors = [f"MISSING_{key.upper()}" for key in required if key not in manifest]
    if manifest.get("schema_version") not in {None, "clean_lineage_manifest_v1"}: errors.append("LINEAGE_SCHEMA_INVALID")
    for key in ("source_package_id", "source_version_id", "scene_source_id", "source_fingerprint"):
        if key in manifest and not str(manifest.get(key) or "").strip(): errors.append(f"EMPTY_{key.upper()}")
    for edge in ("source_to_fact_snapshot", "fact_snapshot_to_script_ir", "script_ir_to_treatment", "treatment_to_blocking"):
        value = manifest.get("lineage_edges", {}).get(edge)
        if not isinstance(value, dict) or not value.get("source_fingerprint") or not value.get("target_source_fingerprint") or value.get("source_fingerprint") != value.get("target_source_fingerprint"):
            errors.append(f"LINEAGE_EDGE_INVALID:{edge}")
    state = manifest.get("lineage_state")
    if state is not None and state not in LINEAGE_STATES: errors.append("LINEAGE_STATE_INVALID")
    if strict or state == "FRESH_APPROVED_RECORD_ELIGIBLE":
        fact = manifest.get("fact_snapshot") if isinstance(manifest.get("fact_snapshot"), dict) else {}
        script = manifest.get("script_ir") if isinstance(manifest.get("script_ir"), dict) else {}
        treatment = manifest.get("director_treatment") if isinstance(manifest.get("director_treatment"), dict) else {}
        blocking = manifest.get("scene_blocking") if isinstance(manifest.get("scene_blocking"), dict) else {}
        if str(fact.get("status") or "").lower() not in {"confirmed", "fact_snapshot_confirmed"}: errors.append("FACT_SNAPSHOT_NOT_CONFIRMED")
        if script.get("qualified") is not True and str(script.get("status") or "").lower() not in {"qualified", "script_ir_qualified"}: errors.append("SCRIPT_IR_NOT_QUALIFIED")
        if str(treatment.get("status") or "").lower() != "approved": errors.append("TREATMENT_NOT_APPROVED")
        if str(blocking.get("status") or "").lower() != "approved": errors.append("BLOCKING_NOT_APPROVED")
        approvals = manifest.get("approval_evidence")
        if not approvals or (isinstance(approvals, list) and not approvals): errors.append("APPROVAL_EVIDENCE_MISSING")
        approval_rows = approvals if isinstance(approvals, list) else [approvals] if isinstance(approvals, dict) else []
        if any(str(row.get("reviewer_type") or "").upper() == "LEGACY_IMPORTED" for row in approval_rows if isinstance(row, dict)): errors.append("LEGACY_APPROVAL_NOT_ALLOWED_FOR_FRESH")
        if manifest.get("exposure_state") != "NOT_EXPOSED": errors.append("EXPOSURE_NOT_CLEAN")
        if manifest.get("fresh_eligibility") is not True: errors.append("FRESH_ELIGIBILITY_NOT_CONFIRMED")
    return {"status": "PASS" if not errors else "FAIL", "clean_lineage": not errors, "errors": list(dict.fromkeys(errors))}


def validate_approval_evidence(evidence: dict[str, Any], *, record_fingerprint: str, source_lineage_fingerprint: str, allow_legacy: bool = False) -> dict[str, Any]:
    errors = []
    if evidence.get("approval_type") not in {"TREATMENT_APPROVAL", "BLOCKING_APPROVAL"}: errors.append("APPROVAL_TYPE_INVALID")
    if evidence.get("reviewer_type") not in {"HUMAN", "EXPLICIT_EXTERNAL_AUTHORIZATION", "LEGACY_IMPORTED"}: errors.append("REVIEWER_TYPE_INVALID")
    if evidence.get("reviewer_type") == "LEGACY_IMPORTED" and not allow_legacy: errors.append("LEGACY_APPROVAL_NOT_ALLOWED_FOR_FRESH")
    if not evidence.get("approved_at"): errors.append("APPROVED_AT_MISSING")
    if evidence.get("approved_record_fingerprint") != record_fingerprint: errors.append("APPROVAL_FINGERPRINT_MISMATCH")
    if evidence.get("source_lineage_fingerprint") != source_lineage_fingerprint: errors.append("APPROVAL_LINEAGE_FINGERPRINT_MISMATCH")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


def transition_lineage(current: str, target: str) -> dict[str, Any]:
    if current not in LINEAGE_STATES or target not in LINEAGE_STATES:
        return {"allowed": False, "error": "LINEAGE_STATE_INVALID"}
    if LINEAGE_STATES.index(target) != LINEAGE_STATES.index(current) + 1:
        return {"allowed": False, "error": "LINEAGE_STATE_SKIP_FORBIDDEN"}
    return {"allowed": True, "from": current, "to": target}
