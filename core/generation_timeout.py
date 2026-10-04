"""Timeout hierarchy for provider generation requests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import time
from typing import Any

import httpx

from core.provider_execution_profile import provider_timeout_seconds


@dataclass(frozen=True)
class GenerationTimeoutHierarchy:
    provider_timeout_seconds: int
    orchestration_read_timeout_seconds: int
    connect_timeout_seconds: int = 10
    write_timeout_seconds: int = 60
    pool_timeout_seconds: int = 30
    margin_seconds: int = 60

    @classmethod
    def from_profile(cls, profile: dict[str, Any], *, margin_seconds: int = 60) -> "GenerationTimeoutHierarchy":
        provider = provider_timeout_seconds(profile, strict=bool(profile.get("phase_f_strict")))
        margin = max(int(margin_seconds), 30)
        return cls(provider, provider + margin, margin_seconds=margin)

    def httpx_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=float(self.connect_timeout_seconds),
            read=float(self.orchestration_read_timeout_seconds),
            write=float(self.write_timeout_seconds),
            pool=float(self.pool_timeout_seconds),
        )

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def timeout_evidence(
    hierarchy: GenerationTimeoutHierarchy,
    *,
    request_started_at: float,
    request_finished_at: float | None = None,
    timeout_layer: str = "NONE",
) -> dict[str, Any]:
    finished = float(request_finished_at if request_finished_at is not None else time.monotonic())
    return {
        **hierarchy.as_dict(),
        "orchestration_timeout_seconds": hierarchy.orchestration_read_timeout_seconds,
        "request_started_at": request_started_at,
        "request_finished_at": finished,
        "elapsed_seconds": round(max(0.0, finished - request_started_at), 3),
        "timeout_layer": str(timeout_layer),
    }


def classify_timeout_layer(
    exc: BaseException,
    *,
    hierarchy: GenerationTimeoutHierarchy,
    elapsed_seconds: float,
    provider_transport_timeout: bool = False,
) -> tuple[str, str | None]:
    """Classify the layer that timed out and configuration errors."""

    if provider_transport_timeout:
        return "PROVIDER", None
    if isinstance(exc, httpx.TimeoutException):
        if elapsed_seconds < hierarchy.provider_timeout_seconds:
            return "ORCHESTRATION", "ORCHESTRATION_TIMEOUT_CONFIGURATION_ERROR"
        if elapsed_seconds >= hierarchy.orchestration_read_timeout_seconds:
            return "ORCHESTRATION", "ORCHESTRATION_TIMEOUT_CONFIGURATION_ERROR"
        return "NETWORK", None
    return "NONE", None


__all__ = ["GenerationTimeoutHierarchy", "classify_timeout_layer", "timeout_evidence"]
