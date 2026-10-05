"""Runtime-only resolution of semantic reference bindings to accessible URLs."""
from __future__ import annotations

from typing import Any, Callable

from .video_compilers.base import CompiledVideoRequestIR
from .video_reference_bridge import validate_official_media_video_reference_bridge


def resolve_compiled_references(
    compiled_request: CompiledVideoRequestIR,
    resolver: Callable[[dict[str, Any]], str],
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for binding in compiled_request.reference_bindings:
        item = dict(binding)
        if not item.get("asset_id") or not item.get("authority_fingerprint") or not item.get("media_sha256"):
            raise ValueError("REFERENCE_LINEAGE_INCOMPLETE")
        # Production OfficialMedia projections carry structured canonical
        # lineage. Fixture-only unit bindings remain supported, but a binding
        # that claims OfficialMedia truth must pass the bridge contract before
        # any provider URL is resolved.
        if item.get("official_lineage") is not None or item.get("source_binding") is not None:
            bridge_audit = validate_official_media_video_reference_bridge(item)
            if bridge_audit["status"] != "PASS":
                raise ValueError("OFFICIAL_MEDIA_REFERENCE_LINEAGE_INCOMPLETE")
            if item.get("official_media_current") is False or item.get("official_pointer_current") is False or item.get("prompt_ir_lineage_exact") is False:
                raise ValueError("OFFICIAL_MEDIA_REFERENCE_NOT_CURRENT")
        url = str(resolver(item) or "").strip()
        if not url:
            raise LookupError("REFERENCE_RUNTIME_URL_UNRESOLVED")
        item["url"] = url
        resolved.append(item)
    if compiled_request.reference_mode == "FIRST_FRAME" and not any(x.get("role") == "FIRST_FRAME" for x in resolved):
        raise ValueError("FIRST_FRAME_REFERENCE_MISSING")
    return resolved


__all__ = ["resolve_compiled_references"]
