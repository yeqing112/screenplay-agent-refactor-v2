import pytest

from core.director_patch_path_resolver import (
    PatchPathResolutionError,
    resolve_patch_path,
)
from core.director_patch_normalizer import collect_path_resolution_metrics


ALLOWED = [
    "/shots/*/camera/shot_size",
    "/shots/*/camera/movement",
    "/shots/*/composition/*",
]


@pytest.mark.parametrize(
    "raw,kwargs",
    [
        ("/shots/S03/camera/shot_size", {"plan_shot_id": "S03"}),
        ("/shots/S03/camera/shot-size", {"plan_shot_id": "S03"}),
        ("shots.S03.camera.shot_size", {}),
        ("shots/S03/camera/shot_size", {}),
        ("S03.camera.shot_size", {}),
        ({"plan_shot_id": "S03", "path": "camera.shot_size"}, {}),
    ],
)
def test_resolves_equivalent_provider_paths(raw, kwargs):
    result = resolve_patch_path(raw, allowed_patch_paths=ALLOWED, **kwargs)
    assert result.plan_shot_id == "S03"
    assert result.path == "camera.shot_size"


def test_resolves_numeric_selector_only_when_declared_or_known():
    assert resolve_patch_path("/shots/0/camera/movement", plan_shot_id="S01", allowed_patch_paths=ALLOWED).plan_shot_id == "S01"
    assert resolve_patch_path("/shots/1/camera/movement", known_plan_shot_ids=["S01", "S02"], allowed_patch_paths=ALLOWED).plan_shot_id == "S02"
    with pytest.raises(PatchPathResolutionError) as error:
        resolve_patch_path("/shots/0/camera/movement", allowed_patch_paths=ALLOWED)
    assert error.value.code == "AMBIGUOUS_PATCH_PATH"


def test_rejects_ambiguous_wildcard_without_target():
    with pytest.raises(PatchPathResolutionError) as error:
        resolve_patch_path("/shots/*/camera/shot_size", allowed_patch_paths=ALLOWED)
    assert error.value.code == "AMBIGUOUS_PATCH_PATH"


def test_rejects_cross_target_and_forbidden_path_after_resolution():
    with pytest.raises(PatchPathResolutionError) as error:
        resolve_patch_path("/shots/S02/camera/shot_size", plan_shot_id="S03", allowed_patch_paths=ALLOWED)
    assert error.value.code == "DIRECTOR_PATCH_TARGET_MISMATCH"
    with pytest.raises(PatchPathResolutionError) as error:
        resolve_patch_path("/shots/S03/scene_name", plan_shot_id="S03", allowed_patch_paths=ALLOWED)
    assert error.value.code == "DIRECTOR_PATCH_PATH_FORBIDDEN"


def test_rejects_unsafe_and_unknown_relative_paths_fail_closed():
    with pytest.raises(PatchPathResolutionError) as error:
        resolve_patch_path("S03..camera.shot_size", allowed_patch_paths=ALLOWED)
    assert error.value.code == "DIRECTOR_PATCH_PATH_FORBIDDEN"


def test_collects_path_resolution_metrics_without_applying_patches():
    metrics = collect_path_resolution_metrics(
        {
            "patches": [
                {"plan_shot_id": "S03", "changes": {"camera.shotSize": "CU", "camera.angle": "eye_level"}},
                {"plan_shot_id": "S03", "patch": [{"op": "replace", "path": "/shots/*/camera/movement", "value": "static"}]},
            ]
        },
        known_plan_shot_ids=["S01", "S02", "S03"],
        allowed_patch_paths=ALLOWED,
    )
    assert metrics["path_resolution_attempt_count"] == 3
    assert metrics["path_resolution_success_count"] == 2
    assert metrics["path_resolution_failure_count"] == 1
    assert metrics["forbidden_path_count"] == 1
    assert metrics["path_resolution_success_rate"] == 0.6667
    with pytest.raises(PatchPathResolutionError) as error:
        resolve_patch_path("S03.camera.angle", allowed_patch_paths=ALLOWED)
    assert error.value.code == "DIRECTOR_PATCH_PATH_FORBIDDEN"
