"""Provider-neutral schema/interface for the future Director Critic."""
from __future__ import annotations

from typing import Any, Protocol


CREATIVE_CRITIC_SCHEMA_VERSION = "director_creative_critic_v1"
CRITIC_FIELDS = ("overall_assessment", "dramatic_effectiveness", "visual_coherence", "emotional_effectiveness", "information_control", "performance_direction_quality", "editing_rhythm_quality", "originality", "over_directing_risk", "professional_usability", "major_problems", "redesign_recommendation", "confidence")


class DirectorCriticAdapter(Protocol):
    def evaluate(self, *, strategy: dict[str, Any], shot_plan: dict[str, Any], qa_findings: list[dict[str, Any]]) -> dict[str, Any]: ...


def validate_director_critic_result(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"valid": False, "errors": ["critic result must be an object"]}
    errors = [f"missing {field}" for field in CRITIC_FIELDS if field not in raw]
    for field in ("overall_assessment", "redesign_recommendation"):
        if field in raw and not isinstance(raw[field], str): errors.append(f"{field} must be text")
    for field in ("dramatic_effectiveness", "visual_coherence", "emotional_effectiveness", "information_control", "performance_direction_quality", "editing_rhythm_quality", "originality", "over_directing_risk", "professional_usability", "confidence"):
        if field in raw and (isinstance(raw[field], bool) or not isinstance(raw[field], (int, float)) or not 0 <= float(raw[field]) <= 10): errors.append(f"{field} must be between 0 and 10")
    if "major_problems" in raw and (not isinstance(raw["major_problems"], list) or any(not isinstance(item, str) for item in raw["major_problems"])): errors.append("major_problems must be a list of strings")
    return {"valid": not errors, "errors": errors}


class ProviderFreeCriticAdapter:
    """Deterministic mock; intentionally never calls a provider."""
    def evaluate(self, *, strategy: dict[str, Any], shot_plan: dict[str, Any], qa_findings: list[dict[str, Any]]) -> dict[str, Any]:
        blocked = bool(qa_findings)
        return {"schema_version": CREATIVE_CRITIC_SCHEMA_VERSION, "overall_assessment": "需要修订" if blocked else "策略与镜头结构一致", "dramatic_effectiveness": 6 if blocked else 8, "visual_coherence": 6 if blocked else 8, "emotional_effectiveness": 6 if blocked else 8, "information_control": 6 if blocked else 8, "performance_direction_quality": 6 if blocked else 8, "editing_rhythm_quality": 6 if blocked else 8, "originality": 5 if blocked else 7, "over_directing_risk": 5 if blocked else 2, "professional_usability": 5 if blocked else 8, "major_problems": [str(row.get("issue_code")) for row in qa_findings[:5]], "redesign_recommendation": "进入对应 QA 路由" if blocked else "可进入人工审美选择", "confidence": 0.5 if blocked else 0.8, "adapter_mode": "provider_free_mock", "provider_calls": 0}


__all__ = ["CREATIVE_CRITIC_SCHEMA_VERSION", "CRITIC_FIELDS", "DirectorCriticAdapter", "validate_director_critic_result", "ProviderFreeCriticAdapter"]
