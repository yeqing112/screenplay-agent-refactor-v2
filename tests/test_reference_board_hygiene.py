import json

from PIL import Image
import pytest

import scripts.run_autonomous_visual_asset_pipeline_v4 as runner


def _authority(paths):
    return {
        "status": "READY",
        "primary_sha256": runner._sha(paths["MASTER"]),
        "primary_execution_id": "exec-master",
        "derived_shas": {key: runner._sha(path) for key, path in paths.items() if key != "MASTER"},
        "derived_execution_ids": {key: f"exec-{key.lower()}" for key in paths if key != "MASTER"},
        "profile_fingerprint": "profile-fp",
        "prompt_fingerprint": "prompt-fp",
    }


def _images(tmp_path):
    paths = {}
    for key, size in {
        "MASTER": (300, 500),
        "FACE_FRONT": (500, 500),
        "FACE_PROFILE": (700, 500),
        "FACE_45": (500, 700),
        "FULL_SIDE": (300, 500),
        "FULL_BACK": (500, 900),
    }.items():
        path = tmp_path / f"{key}.jpg"
        Image.new("RGB", size, (120, 150, 160)).save(path)
        paths[key] = path
    return paths


def test_partial_authority_cannot_create_board(tmp_path):
    paths = _images(tmp_path)
    with pytest.raises(ValueError, match="REFERENCE_BOARD_REQUIRES_READY_AUTHORITY"):
        runner._board(paths, tmp_path / "board.png", ["FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_FRONT", "FULL_SIDE", "FULL_BACK"], 3, run_id="run-1", authority={"status": "FAILED"})
    assert not (tmp_path / "board.png").exists()


def test_board_provenance_binds_run_authority_and_source_shas(tmp_path):
    paths = _images(tmp_path)
    authority = _authority(paths)
    board = runner._board(paths, tmp_path / "board.png", ["FACE_FRONT", "FACE_PROFILE", "FACE_45", "FULL_FRONT", "FULL_SIDE", "FULL_BACK"], 3, run_id="run-1", authority=authority)
    provenance = json.loads((tmp_path / "board.provenance.json").read_text(encoding="utf-8"))
    assert board["board_run_id"] == "run-1"
    assert provenance["authority_fingerprint"]
    assert provenance["source_view_sha256"][3]["view_id"] == "FULL_FRONT"
    final = tmp_path / "published.png"
    runner._atomic_publish_board(tmp_path / "board.png", final)
    assert final.exists()
    assert final.with_suffix(".provenance.json").exists()


def test_stale_board_is_archived_before_new_run(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    stale = out / "lin-wan-reference-board.png"
    stale.write_bytes(b"stale")
    monkeypatch.setattr(runner, "OUT", out)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    staging = runner._prepare_run_output("run-2")
    assert staging == tmp_path / "work" / "run-2" / "publish-staging"
    assert not stale.exists()
    assert (out / "historical-invalid-artifacts" / "run-2" / stale.name).exists()
