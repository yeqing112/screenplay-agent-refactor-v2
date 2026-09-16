"""Deterministic, byte-accurate source evidence anchors."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SCHEMA_VERSION = "source_evidence_index_v1"


def classify_anchor_surface(text: Any) -> str:
    """Classify presentation form only; unknown inputs fail safe."""
    if not isinstance(text, str) or not text.strip():
        return "UNKNOWN_SURFACE"
    value = text.strip()
    if any(mark in value for mark in ("“", "”", "‘", "’")) or re.match(r"^—{1,2}\s*", value):
        return "QUOTED_TEXT"
    return "NARRATIVE_PROSE"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build_source_evidence_index(
    raw_bytes: bytes,
    *,
    source_package_id: str,
    source_version_id: str,
    source_raw_hash: str | None = None,
) -> dict[str, Any]:
    """Split immutable UTF-8 bytes into maximal non-blank source blocks.

    Offsets use inclusive/exclusive Python semantics.  No newline
    normalization or rewritten text participates in the authority index.
    """
    raw_text = raw_bytes.decode("utf-8")
    raw_hash = source_raw_hash or _sha(raw_bytes)
    anchors: list[dict[str, Any]] = []
    cursor = 0
    block_start: int | None = None
    for line in raw_text.splitlines(keepends=True):
        is_blank = line.strip("\r\n") == ""
        if is_blank:
            if block_start is not None:
                _append_anchor(anchors, raw_text, raw_bytes, block_start, cursor, source_package_id, source_version_id, raw_hash)
                block_start = None
            cursor += len(line)
            continue
        if block_start is None:
            block_start = cursor
        cursor += len(line)
    if block_start is not None:
        _append_anchor(anchors, raw_text, raw_bytes, block_start, cursor, source_package_id, source_version_id, raw_hash)

    projection = [
        {
            "anchor_ref": row["anchor_ref"],
            "char_start": row["char_start"],
            "char_end": row["char_end"],
            "byte_start": row["byte_start"],
            "byte_end": row["byte_end"],
            "exact_text_sha256": row["exact_text_sha256"],
        }
        for row in anchors
    ]
    fingerprint = _sha(_canonical({"schema_version": SCHEMA_VERSION, "source_raw_hash": raw_hash, "anchors": projection}))
    return {
        "schema_version": SCHEMA_VERSION,
        "source_package_id": source_package_id,
        "source_version_id": source_version_id,
        "source_raw_hash": raw_hash,
        "anchors": anchors,
        "anchor_count": len(anchors),
        "evidence_index_fingerprint": fingerprint,
    }


def _append_anchor(anchors: list[dict[str, Any]], text: str, raw_bytes: bytes, start: int, end: int, package_id: str, version_id: str, raw_hash: str) -> None:
    exact = text[start:end]
    byte_start = len(text[:start].encode("utf-8"))
    byte_end = byte_start + len(exact.encode("utf-8"))
    assert raw_bytes[byte_start:byte_end].decode("utf-8") == exact
    ordinal = len(anchors) + 1
    anchors.append({
        "anchor_ref": f"E{ordinal:04d}",
        "ordinal": ordinal,
        "unit_type": "SOURCE_BLOCK",
        "source_package_id": package_id,
        "source_version_id": version_id,
        "source_raw_hash": raw_hash,
        "char_start": start,
        "char_end": end,
        "byte_start": byte_start,
        "byte_end": byte_end,
        "exact_text": exact,
        "exact_text_sha256": _sha(exact.encode("utf-8")),
        "anchor_surface_class": classify_anchor_surface(exact),
    })


def validate_source_evidence_index(index: dict[str, Any], raw_bytes: bytes) -> dict[str, Any]:
    text = raw_bytes.decode("utf-8")
    errors: list[str] = []
    for row in index.get("anchors") or []:
        try:
            exact = text[int(row["char_start"]):int(row["char_end"])]
            byte_exact = raw_bytes[int(row["byte_start"]):int(row["byte_end"])].decode("utf-8")
        except (KeyError, TypeError, ValueError, UnicodeDecodeError):
            errors.append("ANCHOR_OFFSET_INVALID")
            continue
        if exact != row.get("exact_text") or byte_exact != row.get("exact_text"):
            errors.append(f"ANCHOR_EXACT_TEXT_MISMATCH:{row.get('anchor_ref')}")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "anchor_count": len(index.get("anchors") or [])}


__all__ = ["SCHEMA_VERSION", "classify_anchor_surface", "build_source_evidence_index", "validate_source_evidence_index"]
