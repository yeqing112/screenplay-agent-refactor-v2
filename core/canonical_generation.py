"""Shared production generation contract.

This module owns the media-neutral selection identity used by the canonical
preview/execute API.  IMAGE and VIDEO differ only in target media, profile
capability, adapter binding, and transport behavior; they share the existing
GenerationExecutionRecord and MediaCandidateRecord lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .prompt_ir_phase_e import canonical, canonical_target_media, fingerprint


class CanonicalGenerationContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProductionGenerationSelection:
    book_id: int
    episode: int
    storyboard_shot_id: int
    target_media: str
    model_profile_id: str
    generation_mode: str | None = None

    @classmethod
    def from_request(cls, *, book_id: int, episode: int, storyboard_shot_id: int, target_media: Any, model_profile_id: Any, generation_mode: Any = None) -> "ProductionGenerationSelection":
        if not str(model_profile_id or "").strip():
            raise CanonicalGenerationContractError("PRODUCTION_MODEL_SELECTION_REQUIRED", "Production generation requires an explicit model_profile_id.")
        try:
            media = canonical_target_media(target_media)
        except Exception as exc:
            raise CanonicalGenerationContractError("GENERATION_MEDIA_SCOPE_MISMATCH", "Production generation requires explicit target_media IMAGE or VIDEO.") from exc
        mode = str(generation_mode or "").strip().upper() or None
        return cls(int(book_id), int(episode), int(storyboard_shot_id), media, str(model_profile_id).strip(), mode)

    def as_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "episode": self.episode,
            "storyboard_shot_id": self.storyboard_shot_id,
            "target_media": self.target_media,
            "model_profile_id": self.model_profile_id,
            "generation_mode": self.generation_mode,
        }

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.as_dict())


def canonical_request_fingerprint(*, selection: ProductionGenerationSelection, prompt_ir_payload_hash: str, prompt_ir_version_id: int, generation_payload_fingerprint: str, generation_policy_fingerprint: str, model_profile_fingerprint: str, adapter_id: str, adapter_version: str, reference_bindings_fingerprint: str = "", source_binding: dict[str, Any] | None = None) -> str:
    """Build the secret-free request identity shared by preview and execute."""
    return fingerprint({
        "schema_version": "canonical_generation_request_v1",
        "selection": selection.as_dict(),
        "selection_fingerprint": selection.fingerprint,
        "prompt_ir_payload_hash": prompt_ir_payload_hash,
        "prompt_ir_version_id": int(prompt_ir_version_id),
        "generation_payload_fingerprint": generation_payload_fingerprint,
        "generation_policy_fingerprint": generation_policy_fingerprint,
        "model_profile_fingerprint": model_profile_fingerprint,
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "reference_bindings_fingerprint": reference_bindings_fingerprint,
        "source_binding": source_binding or {},
    })


__all__ = ["CanonicalGenerationContractError", "ProductionGenerationSelection", "canonical_request_fingerprint"]
