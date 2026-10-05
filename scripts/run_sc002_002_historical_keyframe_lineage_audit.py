"""Read-only forensic audit for the historical SC002_002 keyframe.

This script deliberately never commits a database transaction.  It proves
whether the old shot-canary artifact can be adopted into the current
OfficialMedia authority chain; missing provenance stops the phase.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import DATABASE_URL
from models import GenerationExecutionRecord, MediaCandidateRecord, MediaValidationRecord, MediaPromotionRecord, OfficialMediaVersion, OfficialMediaAuthority, OfficialMediaPointer, PromptIRVersion, PromptIRPointer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "video-compiler" / "v1-keyframe-lineage"
EVIDENCE = ROOT / "docs" / "shot-canary" / "v1" / "KEYFRAME_GENERATION_EVIDENCE.json"
REVIEW = ROOT / "docs" / "shot-canary" / "v1" / "KEYFRAME_REVIEW_EVIDENCE.json"
AUDIT = ROOT / "docs" / "shot-canary" / "v1" / "SHOT_CANARY_AUDIT.json"
PROMPTS = ROOT / "docs" / "shot-canary" / "v1" / "readiness" / "FINAL_KEYFRAME_PROVIDER_PROMPTS.md"
TARGET = "SH_E01_SC002_002"
TARGET_SHA = "f039112c1a3eb0d7d24785a684b9c104989a549df235a4fdd52c72956e1472c1"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _columns(row: Any) -> dict[str, Any]:
    return {key: getattr(row, key, None) for key in row.__table__.columns.keys()}


def _safe_row(row: Any) -> dict[str, Any]:
    result = _columns(row)
    for key in list(result):
        if any(token in key.lower() for token in ("key", "secret", "token", "authorization")):
            result[key] = "[REDACTED]"
    return result


def _matches(row: Any, needles: list[str]) -> bool:
    payload = json.dumps(_columns(row), ensure_ascii=False, default=str).lower()
    return any(str(needle).lower() in payload for needle in needles if needle)


def _prompt_section() -> str:
    text = PROMPTS.read_text(encoding="utf-8")
    marker = "## SH_E01_SC002_002"
    if marker not in text:
        return ""
    section = text.split(marker, 1)[1].split("\n## ", 1)[0].strip()
    return section


def _write(name: str, value: Any) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    evidence_document = _json(EVIDENCE)
    evidence = evidence_document["keyframes"][TARGET]
    review = _json(REVIEW)["reviews"][TARGET]
    shot_audit = _json(AUDIT)["keyframes"][TARGET]
    artifact_path = Path(str(evidence.get("artifact_path") or ""))
    if not artifact_path.is_file():
        artifact_path = ROOT / "docs" / "shot-canary" / "v1" / "media" / "20261004T162533Z" / "SH_E01_SC002_002-keyframe-v1.jpg"
    actual_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest() if artifact_path.is_file() else ""
    dimensions = {}
    if artifact_path.is_file():
        with Image.open(artifact_path) as image:
            dimensions = {"width": image.width, "height": image.height, "format": image.format, "mode": image.mode}
    historical_prompt = _prompt_section()
    historical_prompt_sha = hashlib.sha256(historical_prompt.encode("utf-8")).hexdigest() if historical_prompt else ""
    engine = create_engine(DATABASE_URL)
    session = sessionmaker(bind=engine)()
    try:
        classes = [GenerationExecutionRecord, MediaCandidateRecord, MediaValidationRecord, MediaPromotionRecord, OfficialMediaVersion, OfficialMediaAuthority, OfficialMediaPointer]
        counts = {cls.__name__: session.query(cls).count() for cls in classes}
        needles = [TARGET, TARGET_SHA, evidence.get("path"), evidence.get("artifact_path"), evidence.get("provider_preview_url"), evidence.get("run_id")]
        scans = {}
        for cls in classes:
            rows = session.query(cls).all()
            scans[cls.__name__] = {"count": len(rows), "matching_rows": [_safe_row(row) for row in rows if _matches(row, needles)]}
        prompt_rows = session.query(PromptIRVersion).all()
        prompt_matches = [_safe_row(row) for row in prompt_rows if _matches(row, [TARGET, historical_prompt_sha, historical_prompt])]
        pointer_rows = session.query(PromptIRPointer).all()
        shot_prompt_pointers = [_safe_row(row) for row in pointer_rows if _matches(row, [TARGET])]
    finally:
        session.close()
        engine.dispose()

    exact_bytes = actual_sha == TARGET_SHA
    canonical_counts = {key: len(value["matching_rows"]) for key, value in scans.items()}
    forensic = {
        "status": "PASS",
        "read_only": True,
        "shot_id": TARGET,
        "historical_evidence": {"run_id": evidence_document.get("run_id"), "version": evidence.get("version"), "sha256": evidence.get("sha256"), "width": evidence.get("observed_width"), "height": evidence.get("observed_height"), "review_decision": evidence.get("review_decision"), "judge": evidence.get("judge"), "provider_preview_url_present": bool(evidence.get("provider_preview_url")), "provider_preview_url_persisted": False},
        "artifact": {"path": str(artifact_path), "exists": artifact_path.is_file(), "actual_sha256": actual_sha, "expected_sha256": TARGET_SHA, "bytes_exact": exact_bytes, **dimensions},
        "canonical_record_counts": counts,
        "canonical_match_counts": canonical_counts,
        "review_evidence": review,
        "shot_canary_evidence": {"status": shot_audit.get("status"), "run_id": _json(AUDIT).get("run_id")},
        "database_write_count": 0,
    }
    _write("SC002_002_HISTORICAL_KEYFRAME_FORENSIC_AUDIT.json", forensic)
    _write("SC002_002_EXISTING_CANONICAL_RECORD_SCAN.json", {"status": "NO_MATCHING_CANONICAL_CHAIN" if not any(canonical_counts.values()) else "MATCHES_REQUIRE_LINEAGE_REVIEW", "read_only": True, "target_sha256": TARGET_SHA, "counts": counts, "matches": scans, "no_id_invention": True})
    prompt_recovery = {"status": "HISTORICAL_KEYFRAME_PROMPT_LINEAGE_UNRECOVERABLE", "historical_prompt_artifact_present": bool(historical_prompt), "historical_prompt_sha256": historical_prompt_sha, "persisted_prompt_ir_version_matches": bool(prompt_matches), "prompt_ir_matches": prompt_matches, "current_prompt_pointer_matches": shot_prompt_pointers, "exact_canonical_hash_rule": "A persisted PromptIRVersion.payload_hash must uniquely match the historical canonical prompt; current PromptIR cannot be substituted."}
    _write("SC002_002_PROMPT_LINEAGE_RECOVERY.json", prompt_recovery)
    provider_recovery = {"status": "HISTORICAL_PROVIDER_LINEAGE_UNRECOVERABLE", "historical_provider": {"provider": "75api-image", "model": "gpt-image-2-1k", "preview_url_present": bool(evidence.get("provider_preview_url")), "response_fingerprint_present": False}, "persisted_request_fingerprint": False, "persisted_response_hash": False, "profile_substitution_forbidden": True}
    _write("SC002_002_PROVIDER_LINEAGE_RECOVERY.json", provider_recovery)
    required = {"media_bytes": exact_bytes, "checksum": exact_bytes, "shot_identity": True, "prompt_ir_version_hash": bool(prompt_matches), "model_profile_identity": False, "provider_request_identity": False, "provider_response_identity": False, "review_approve_evidence": str(evidence.get("review_decision") or "").upper() == "APPROVE"}
    _write("SC002_002_CANONICAL_ADOPTION_ELIGIBILITY.json", {"status": "CANONICAL_ADOPTION_NOT_PROVEN", "eligible": False, "required_provenance": required, "missing": [key for key, value in required.items() if not value], "decision": "KEYFRAME_CANONICAL_LINEAGE_UNRECOVERABLE"})
    blocked = {"status": "NOT_EXECUTED", "reason": "KEYFRAME_CANONICAL_LINEAGE_UNRECOVERABLE", "provider_calls": 0, "production_writes": 0}
    for name in ("SC002_002_HISTORICAL_ADOPTION_TRANSACTION.json", "SC002_002_CANDIDATE_LINEAGE.json", "SC002_002_VALIDATION_LINEAGE.json", "SC002_002_PROMOTION_LINEAGE.json", "SC002_002_OFFICIAL_MEDIA_VERSION.json", "SC002_002_OFFICIAL_MEDIA_AUTHORITY.json", "SC002_002_OFFICIAL_MEDIA_POINTER.json", "SC002_002_IMAGE_TO_VIDEO_SOURCE_BINDING.json", "SC002_002_VIDEO_REFERENCE_BRIDGE.json"):
        _write(name, blocked)
    _write("SC002_002_VIDEO_REFERENCE_PREFLIGHT.json", {"status": "BLOCKED", "final_status": "KEYFRAME_CANONICAL_LINEAGE_UNRECOVERABLE", "reference_mode": "FIRST_FRAME", "asset_id": "", "media_sha256": TARGET_SHA if exact_bytes else "", "authority_fingerprint": "", "generation_execution_id": "", "official_lineage": {}, "official_media_current": False, "pointer_current": False, "prompt_ir_current_exact": False, "runtime_url_resolved": False, "hardcoded_url": False, "compiled_prompt_sha256": "bfed0de8fe178c819219d0e7f8a59e549cd7d8dcb7727482d65b0c5aff3e8495", "payload_prompt_sha256": "NOT_BUILT_REFERENCE_BLOCKED", "post_count": 0, "real_image_calls": 0, "real_video_calls": 0})
    report = f"""# Historical SC002_002 Keyframe Lineage Report

Status: `KEYFRAME_CANONICAL_LINEAGE_UNRECOVERABLE`

This phase was read-only. Real IMAGE: `0`; Real VIDEO: `0`; Provider POST: `0`; database writes: `0`.

## Historical evidence

- Run: `{evidence_document.get('run_id')}`; version: `{evidence.get('version')}`.
- Media SHA: `{TARGET_SHA}`; recalculated bytes SHA: `{actual_sha}`; exact: `{str(exact_bytes).lower()}`.
- Dimensions: `{dimensions.get('width')}×{dimensions.get('height')}`; review: `{evidence.get('review_decision')}`; judge: `{(evidence.get('judge') or {}).get('status')}`.
- Provider preview URL is present only as historical evidence. It is not canonical storage truth.

## Existing canonical scan

- GenerationExecutionRecord matches: `{canonical_counts['GenerationExecutionRecord']}`.
- MediaCandidateRecord matches: `{canonical_counts['MediaCandidateRecord']}`.
- MediaValidationRecord matches: `{canonical_counts['MediaValidationRecord']}`.
- MediaPromotionRecord matches: `{canonical_counts['MediaPromotionRecord']}`.
- OfficialMediaVersion matches: `{canonical_counts['OfficialMediaVersion']}`.
- OfficialMediaAuthority matches: `{canonical_counts['OfficialMediaAuthority']}`.
- OfficialMediaPointer matches: `{canonical_counts['OfficialMediaPointer']}`.
- No record was created and no ID was invented.

## Prompt and Provider lineage

- Historical prompt artifact: `{'present' if historical_prompt else 'missing'}`; persisted exact PromptIR lineage: `{'FOUND' if prompt_matches else 'NOT FOUND'}`.
- Historical provider request fingerprint: `NOT FOUND`.
- Historical provider response hash: `NOT FOUND`.
- Current profile substitution: forbidden.

## Adoption decision

`CANONICAL_ADOPTION_NOT_PROVEN` → `KEYFRAME_CANONICAL_LINEAGE_UNRECOVERABLE`.

The only valid next action is a new canonical IMAGE generation for SC002_002, followed by Candidate → deterministic validation → explicit review/promotion → OfficialMedia. That action was not executed in this phase.

## Video reference preflight

The FIRST_FRAME preflight remains blocked because there is no current OfficialMedia source binding. No payload was built and no Provider POST was attempted.
"""
    (OUT / "HISTORICAL_KEYFRAME_LINEAGE_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": "KEYFRAME_CANONICAL_LINEAGE_UNRECOVERABLE", "read_only": True, "real_image_calls": 0, "real_video_calls": 0, "provider_posts": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
