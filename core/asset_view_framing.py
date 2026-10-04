"""Semantic view framing and provider aspect-ratio projection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class AssetViewFraming:
    asset_kind: str
    view_id: str
    framing_class: str
    requested_aspect_ratio: str
    provider_aspect_ratio: str
    projection_reason: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


class AssetViewFramingPolicy:
    """Map semantic views to requested framing and legal provider ratios."""

    # The 75api GPT-image transport currently exposes these ratio tokens in
    # the profile contract. Unsupported requests are projected explicitly.
    PROVIDER_RATIOS = ("1:1", "16:9", "9:16")

    @classmethod
    def for_view(cls, asset_kind: str, view_id: str, *, provider_ratios: Iterable[str] | None = None) -> AssetViewFraming:
        kind = str(asset_kind or "").upper()
        view = str(view_id or "").upper()
        if kind == "CHARACTER":
            if view in {"MASTER", "FULL_FRONT", "FULL_SIDE", "FULL_BACK"}:
                requested, framing_class = "2:3", "FULL_BODY"
            elif view in {"FACE_FRONT", "FACE_PROFILE", "FACE_45"}:
                requested, framing_class = "1:1", "FACE"
            else:
                raise ValueError(f"ASSET_VIEW_FRAMING_UNKNOWN:{kind}:{view}")
        elif kind == "PROP":
            requested, framing_class = ("1:1", "DETAIL") if view == "DETAIL" else ("1:1", "OBJECT")
            if view not in {"MASTER", "HERO", "SIDE", "BACK", "DETAIL"}:
                raise ValueError(f"ASSET_VIEW_FRAMING_UNKNOWN:{kind}:{view}")
        elif kind == "SCENE":
            requested, framing_class = "16:9", "SCENE"
        else:
            raise ValueError(f"ASSET_VIEW_FRAMING_UNKNOWN:{kind}:{view}")

        legal = tuple(str(value) for value in (provider_ratios or cls.PROVIDER_RATIOS))
        if requested in legal:
            provider = requested
            reason = "requested_ratio_supported"
        else:
            provider = cls._nearest_ratio(requested, legal)
            reason = "requested_ratio_projected_to_nearest_legal_provider_ratio"
        return AssetViewFraming(kind, view, framing_class, requested, provider, reason)

    @staticmethod
    def _nearest_ratio(requested: str, legal: tuple[str, ...]) -> str:
        def numeric(value: str) -> float:
            width, height = value.split(":", 1)
            return float(width) / float(height)
        target = numeric(requested)
        if not legal:
            raise ValueError("ASPECT_RATIO_CAPABILITY_EMPTY")
        return min(legal, key=lambda value: abs(numeric(value) - target))


__all__ = ["AssetViewFraming", "AssetViewFramingPolicy"]
