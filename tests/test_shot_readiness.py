from __future__ import annotations

import pytest

from api.generation_adapters import _coerce_75api_minimax_h3_seconds
from core.shot_readiness import ShotPropState, project_provider_duration
from api.generation_adapters import ModelProfileError


@pytest.mark.parametrize("raw, expected, padding", [(5, 5, 0), (5.5, 6, .5), (8.5, 9, .5), (13.5, 14, .5), (15, 15, 0)])
def test_provider_duration_projection_uses_ceil(raw, expected, padding):
    projection = project_provider_duration(raw)
    assert projection.provider_duration_seconds == expected
    assert projection.provider_padding_seconds == padding


def test_provider_duration_projection_blocks_over_max():
    assert project_provider_duration(15.1).status == "BLOCK"
    assert project_provider_duration(15.1).provider_duration_seconds is None


def test_raw_fractional_adapter_input_fails_closed():
    with pytest.raises(ModelProfileError, match="VIDEO_PROVIDER_DURATION_NOT_PROJECTED"):
        _coerce_75api_minimax_h3_seconds(13.5)


def test_shot_prop_state_requires_physical_authority():
    state = ShotPropState("SH_E01_SC002_006", "APPLE", True, "LU_SHU", "RIGHT", "holds", "table edge", "whole", "offered", "DIALOGUE_ACTION_RESOLVED_PROP")
    assert state.validate() == []
    bad = ShotPropState("SH_E01_SC002_002", "HANDBAG", True, "LIN_WAN", "LEFT", "grips", "door", "closed", "carried", "DIRECTOR_HALLUCINATED_PROP")
    assert "UNAUTHORIZED_SHOT_PROP" in bad.validate()
