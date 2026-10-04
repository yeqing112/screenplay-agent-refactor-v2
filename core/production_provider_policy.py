"""Strict provider selection for production visual canaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ProductionProviderPolicy:
    """Production routing contract kept separate from capability discovery."""

    image_provider: str = "75api-image"
    image_model: str = "gpt-image-2-1k"
    video_provider: str = "75api-minimax-h3"
    video_model: str = "minimax_h3_no_audios"
    strict_provider: bool = True

    def allows_image_profile(self, profile: dict[str, Any]) -> bool:
        provider = str(profile.get("provider") or "")
        model = str(profile.get("model_name") or "")
        if self.strict_provider:
            return provider == self.image_provider and model == self.image_model
        return provider == self.image_provider and model == self.image_model

    def filter_image_candidates(self, candidates: Iterable[Any]) -> list[Any]:
        """Filter ranked router traces without changing generic router behavior."""

        if not self.strict_provider:
            return list(candidates)
        return [
            row for row in candidates
            if str(getattr(row, "provider", "")) == self.image_provider
            and str(getattr(row, "model", "")) == self.image_model
        ]

    def assert_image_profile(self, profile: dict[str, Any]) -> None:
        if not self.allows_image_profile(profile):
            raise ValueError(
                "PRODUCTION_PROVIDER_POLICY_IMAGE_MISMATCH: "
                f"expected {self.image_provider}/{self.image_model}, "
                f"got {profile.get('provider')}/{profile.get('model_name')}"
            )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = ["ProductionProviderPolicy"]
