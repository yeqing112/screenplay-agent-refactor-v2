"""Small identity boundary separating benchmark fixtures from production shots."""

from __future__ import annotations

from typing import Any

from core.sc002_002_upstream_recovery import resolve_exact_canonical_identity


BENCHMARK_FIXTURE_IDENTITIES = frozenset({
    "SH_E01_SC002_002",
    "SH_E01_SC002_006",
    "SH_E01_SC002_007",
})


class CanaryIdentityError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def classify_canary_identity(identity: str) -> dict[str, Any]:
    value = str(identity or "").strip()
    if value in BENCHMARK_FIXTURE_IDENTITIES:
        return {
            "identity": value,
            "identity_class": "BENCHMARK_FIXTURE",
            "production_canonical_identity": False,
            "historical_media_authority": False,
            "allowed_usage": ["PROMPT_COMPILER_GOLDEN", "VIDEO_COMPILER_GOLDEN", "SEMANTIC_REGRESSION", "TEMPORAL_REGRESSION", "MEDIA_QUALITY_BENCHMARK"],
            "forbidden_usage": ["PRODUCTION_SHOT_AUTHORITY", "PRODUCTION_MEDIA_AUTHORITY", "OFFICIAL_MEDIA_LINEAGE_SOURCE"],
        }
    return {
        "identity": value,
        "identity_class": "UNCLASSIFIED",
        "production_canonical_identity": False,
        "historical_media_authority": False,
        "allowed_usage": [],
        "forbidden_usage": ["PRODUCTION_SHOT_AUTHORITY_UNTIL_CANONICAL_BINDING"],
    }


def require_production_canonical_identity(session: Any, identity: str) -> dict[str, Any]:
    classification = classify_canary_identity(identity)
    if classification["identity_class"] == "BENCHMARK_FIXTURE":
        raise CanaryIdentityError("BENCHMARK_IDENTITY_NOT_PRODUCTION_CANONICAL", "Benchmark fixture identity has no explicit production canonical binding.")
    resolution = resolve_exact_canonical_identity(session, identity)
    if resolution.get("status") != "EXACT_ONE":
        raise CanaryIdentityError("CANONICAL_SHOT_IDENTITY_NOT_RESOLVED", "Production canary identity is not bound to exactly one current ShotPlan authority.")
    production = dict(classification)
    production.update({"identity_class": "PRODUCTION_CANONICAL", "production_canonical_identity": True})
    return {"classification": production, "resolution": resolution}


__all__ = ["BENCHMARK_FIXTURE_IDENTITIES", "CanaryIdentityError", "classify_canary_identity", "require_production_canonical_identity"]
