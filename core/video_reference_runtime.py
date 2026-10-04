"""Runtime-only resolution of semantic reference bindings to accessible URLs."""
from __future__ import annotations

from typing import Any, Callable

from .video_compilers.base import CompiledVideoRequestIR


def resolve_compiled_references(
    compiled_request: CompiledVideoRequestIR,
    resolver: Callable[[dict[str, Any]], str],
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for binding in compiled_request.reference_bindings:
        item = dict(binding)
        if not item.get("asset_id") or not item.get("authority_fingerprint") or not item.get("media_sha256"):
            raise ValueError("REFERENCE_LINEAGE_INCOMPLETE")
        url = str(resolver(item) or "").strip()
        if not url:
            raise LookupError("REFERENCE_RUNTIME_URL_UNRESOLVED")
        item["url"] = url
        resolved.append(item)
    if compiled_request.reference_mode == "FIRST_FRAME" and not any(x.get("role") == "FIRST_FRAME" for x in resolved):
        raise ValueError("FIRST_FRAME_REFERENCE_MISSING")
    return resolved


__all__ = ["resolve_compiled_references"]
