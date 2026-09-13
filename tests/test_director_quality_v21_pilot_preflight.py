import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_director_quality_v2_1_mimo_pilot.py"
SPEC = importlib.util.spec_from_file_location("director_quality_v21_mimo_pilot_preflight", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _scene(scene_type: str, index: int) -> dict:
    stages = {stage: {} for stage in MODULE.REQUIRED_STAGES}
    dimensions = {
        stage: {dimension: 0 for dimension in MODULE.REQUIRED_DIMENSIONS}
        for stage in MODULE.REQUIRED_STAGES
    }
    return {
        "scene": {"scene_id": f"FIXTURE_{index:02d}", "scene_type": scene_type},
        "evidence": {
            "treatment": {"scene_id": f"FIXTURE_{index:02d}"},
            "blocking": {"scene_id": f"FIXTURE_{index:02d}"},
            "contract": {"contract_fingerprint": f"contract-{index}"},
            "strategy": {"strategy_fingerprint": f"strategy-{index}"},
        },
        "contract": {"fingerprint": f"contract-{index}"},
        "strategy": {"fingerprint": f"strategy-{index}"},
        "baseline": {},
        "first_candidate": {},
        "final_candidate": {},
        "metrics": {
            "scores": stages,
            "dimensions": dimensions,
            "contract_reliability": {
                "schema_pass": True,
                "patch_path_pass": True,
                "auxiliary_binding_pass": True,
                "parse_success": True,
            },
        },
    }


def _write_evidence(path: Path, scene_types: list[str]) -> None:
    path.write_text(
        json.dumps({"protocol_version": "director-quality-v2-1", "scenes": [_scene(kind, i) for i, kind in enumerate(scene_types)]}),
        encoding="utf-8",
    )


def test_preflight_requires_all_twelve_scene_challenge_types(tmp_path, monkeypatch):
    scene_types = sorted(MODULE.REQUIRED_SCENE_TYPES)
    evidence = tmp_path / "golden.json"
    _write_evidence(evidence, scene_types)
    monkeypatch.setattr(MODULE, "GOLDEN_PATH", evidence)

    result = MODULE.build_preflight()

    assert result["status"] == "ready_for_authorized_real_pilot"
    assert result["evidence"]["scene_count"] == 12
    assert result["checks"]["required_scene_coverage"] is True
    assert result["telemetry"]["real_mimo_calls"] == 0


def test_preflight_blocks_missing_scene_challenge_type(tmp_path, monkeypatch):
    scene_types = sorted(MODULE.REQUIRED_SCENE_TYPES)[:-1]
    evidence = tmp_path / "golden.json"
    _write_evidence(evidence, scene_types)
    monkeypatch.setattr(MODULE, "GOLDEN_PATH", evidence)

    result = MODULE.build_preflight()

    assert result["status"] == "blocked"
    assert result["evidence"]["missing_scene_types"]
    assert result["checks"]["required_scene_coverage"] is False


def test_preflight_blocks_missing_frozen_evidence(tmp_path, monkeypatch):
    scene_types = sorted(MODULE.REQUIRED_SCENE_TYPES)
    evidence = tmp_path / "golden.json"
    payload = {"protocol_version": "director-quality-v2-1", "scenes": [_scene(kind, i) for i, kind in enumerate(scene_types)]}
    payload["scenes"][0].pop("evidence")
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(MODULE, "GOLDEN_PATH", evidence)

    result = MODULE.build_preflight()

    assert result["status"] == "blocked"
    assert any("missing frozen evidence" in error for error in result["errors"])
