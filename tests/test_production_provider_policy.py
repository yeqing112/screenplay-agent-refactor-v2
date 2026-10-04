from dataclasses import dataclass

import pytest

from core.production_provider_policy import ProductionProviderPolicy


@dataclass
class Trace:
    provider: str
    model: str


def test_strict_75api_policy_filters_router_fallbacks():
    policy = ProductionProviderPolicy()
    rows = policy.filter_image_candidates([
        Trace("shapi-gemini-image", "nano-banana-2"),
        Trace("75api-image", "gpt-image-2-1k"),
        Trace("poyo-async", "gpt-image-2"),
    ])
    assert [(row.provider, row.model) for row in rows] == [("75api-image", "gpt-image-2-1k")]


def test_strict_75api_policy_rejects_wrong_model():
    policy = ProductionProviderPolicy()
    with pytest.raises(ValueError, match="PRODUCTION_PROVIDER_POLICY_IMAGE_MISMATCH"):
        policy.assert_image_profile({"provider": "75api-image", "model_name": "gpt-image-2-2k"})
