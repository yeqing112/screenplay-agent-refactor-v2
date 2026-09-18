"""Compatibility import surface for visual authority artifacts."""

from .visual_authority_models import (  # noqa: F401
    VisualAssetPointer,
    VisualAssetVersion,
    VisualAuthoringDecision,
    VisualAuthoringDecisionRequest,
    VisualAuthoringProposal,
    VisualReferenceAuthority,
)

__all__ = [
    "VisualAuthoringDecisionRequest", "VisualAuthoringDecision", "VisualAuthoringProposal",
    "VisualAssetVersion", "VisualAssetPointer", "VisualReferenceAuthority",
]
