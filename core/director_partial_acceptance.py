"""Partial acceptance orchestration for Director Creative patches."""

from __future__ import annotations

import copy
from typing import Any

from core.director_patch_compiler import compile_creative_patches
from core.director_patch_validator import validate_compiled_patch_result


def apply_partial_acceptance(
    structural_shot_plan: dict[str, Any],
    patch_document: dict[str, Any],
    contract: dict[str, Any],
    *,
    treatment: dict[str, Any] | None = None,
    blocking: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply all safe patches and retain baseline values for failed patches.

    This function deliberately uses the compiler's explicit ``allow_partial``
    switch.  It never fabricates a replacement for a rejected patch and never
    mutates the structural plan supplied by the caller.
    """

    compilation = compile_creative_patches(structural_shot_plan, patch_document, contract, allow_partial=True)
    validation = validate_compiled_patch_result(compilation, structural_shot_plan, contract, treatment=treatment, blocking=blocking)
    metrics = copy.deepcopy(compilation.get("partial_acceptance") or {})
    metrics.setdefault("accepted_patch_count", int(compilation.get("accepted_patch_count") or 0))
    metrics.setdefault("rejected_patch_count", int(compilation.get("rejected_patch_count") or 0))
    metrics.setdefault("repaired_patch_count", 0)
    metrics.setdefault("fallback_patch_count", metrics["rejected_patch_count"])
    accepted = metrics["accepted_patch_count"]
    rejected = metrics["rejected_patch_count"]
    mode = "partial_creative_planner" if accepted and rejected else ("creative_planner" if accepted else "deterministic_fallback")
    return {
        "status": "partial" if rejected else "accepted",
        "director_mode": mode,
        "candidate": compilation["candidate"],
        "compilation": compilation,
        "validation": validation,
        "partial_acceptance": metrics,
        "rejected_patches": copy.deepcopy(compilation.get("rejected_patches") or []),
    }


accept_creative_patches = apply_partial_acceptance


__all__ = ["apply_partial_acceptance", "accept_creative_patches"]
