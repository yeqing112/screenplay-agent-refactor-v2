"""Generic dual-source lineage primitives for source-grounded production.

This module is intentionally provider-free.  It knows how to hash canonical
JSON and how to resolve an immutable origin record from a caller supplied
locator; it contains no canary identifiers.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def reconciliation_fingerprint(*, policy_version: str, transformations: list[dict[str, Any]], input_candidate_fingerprint: str, output_candidate_fingerprint: str) -> str:
    if not isinstance(transformations, list):
        raise ValueError("RECONCILIATION_JOURNAL_REQUIRED")
    return canonical_json_sha256({"policy_version": str(policy_version or ""), "transformations": transformations, "input_candidate_fingerprint": str(input_candidate_fingerprint or ""), "output_candidate_fingerprint": str(output_candidate_fingerprint or "")})


@dataclass(frozen=True)
class SourceLineageContext:
    origin_source_kind: str
    origin_source_package_id: str
    origin_source_version_id: str
    origin_source_locator: Mapping[str, Any] = field(default_factory=dict)
    origin_source_raw_hash: str = ""
    structuring_response_fingerprint: str = ""
    reconciliation_policy_version: str = ""
    reconciliation_fingerprint: str = ""
    migration_fingerprint: str = ""
    canonical_projection_version: str = ""
    canonical_script_content_hash: str = ""
    canonical_script_payload_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not str(self.origin_source_kind or "").strip():
            raise ValueError("ORIGIN_SOURCE_KIND_REQUIRED")
        if not str(self.origin_source_package_id or "").strip():
            raise ValueError("ORIGIN_SOURCE_PACKAGE_REQUIRED")
        if not str(self.origin_source_version_id or "").strip():
            raise ValueError("ORIGIN_SOURCE_VERSION_REQUIRED")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SourceLineageContext":
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{key: value[key] for key in allowed if key in value})


def _origin_row(session: Any, context: SourceLineageContext) -> Any:
    from models import Chapter

    locator = dict(context.origin_source_locator or {})
    query = session.query(Chapter)
    if query is None:
        return None
    chapter_id = locator.get("chapter_id")
    if chapter_id is not None:
        row = query.filter_by(id=int(chapter_id)).first()
    else:
        book_id = locator.get("book_id")
        seq = locator.get("chapter_seq", locator.get("episode"))
        if book_id is None or seq is None:
            row = None
        else:
            row = query.filter_by(book_id=int(book_id), seq=int(seq)).first()
    return row


def resolve_origin_source(session: Any, context: SourceLineageContext) -> dict[str, Any]:
    if context.origin_source_kind != "BOOK_CHAPTER":
        raise ValueError("ORIGIN_SOURCE_KIND_UNSUPPORTED")
    row = _origin_row(session, context)
    if row is None:
        raise ValueError("ORIGIN_SOURCE_NOT_FOUND")
    raw_bytes = str(getattr(row, "content", "") or "").encode("utf-8")
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    if context.origin_source_raw_hash and raw_hash != context.origin_source_raw_hash:
        raise ValueError("ORIGIN_SOURCE_CHANGED")
    package_id = context.origin_source_package_id
    version_id = context.origin_source_version_id
    return {"raw_bytes": raw_bytes, "source_package_id": package_id, "source_version_id": version_id, "raw_sha256": raw_hash, "origin_row_id": getattr(row, "id", None)}


__all__ = ["SourceLineageContext", "canonical_json_bytes", "canonical_json_sha256", "reconciliation_fingerprint", "resolve_origin_source"]
