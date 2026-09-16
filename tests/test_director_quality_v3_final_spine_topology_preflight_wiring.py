from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from core.shot_topology_skeleton import normalize_skeleton, validate_skeleton
from core.visual_editorial_spine import validate_spine
from scripts import run_director_quality_v3_final_spine_topology_recanary as runner


def _valid_spine() -> dict:
    return {
        "schema_version": "visual_editorial_spine_ir_v1",
        "scene_id": "s1",
        "strategy_fingerprint": "fp",
        "segments": [
            {
                "segment_key": "SEG01",
                "phase_ids": ["P01"],
                "beat_refs": ["beat:1"],
                "dramatic_function": "orient",
                "audience_attention": "door",
                "performance_pressure": "low",
                "information_change": "none",
                "spatial_focus": "entry",
                "visual_motif": "threshold",
                "editorial_rhythm": "hold",
                "entry_condition": "start",
                "exit_condition": "watch",
            }
        ],
    }


def test_missing_preserve_trace_is_explicit_fail_closed():
    result = validate_spine(
        _valid_spine(),
        scene={"scene_id": "s1", "beats": [{"beat_id": "1"}]},
        strategy={"strategy_fingerprint": "fp", "scene_phases": [{"phase_id": "P01", "beat_ids": ["1"]}], "must_avoid": []},
        must_preserve_trace=None,
    )
    assert result["status"] == "FAIL"
    assert any(error["code"] == "PRESERVE_AUTHORITY_MISSING" for error in result["hard_errors"])


def test_authoritative_identity_is_required_even_when_legacy_scene_records_exist():
    skeleton = normalize_skeleton(
        {"nodes": []}, scene_id="s1", spine_fingerprint="fp"
    )["ir"]
    result = validate_skeleton(
        skeleton,
        spine={"segments": []},
        scene={"scene_id": "s1", "characters": {"records": [{"character_id": "19"}]}},
        strategy={"scene_phases": []},
        require_authority=True,
    )
    assert any(error["code"] == "IDENTITY_AUTHORITY_MISSING" for error in result["hard_errors"])


def test_invalid_spine_is_a_code_level_skeleton_provider_barrier():
    assert runner._runtime_preflight  # guard the final runner import surface
    from core.spine_topology_forensics import skeleton_callable_after_spine

    assert skeleton_callable_after_spine(False)["skeleton_provider_callable"] is False


def test_unauthorized_real_path_returns_before_provider_import_or_call(monkeypatch: pytest.MonkeyPatch):
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("provider must not be reached")

    monkeypatch.setattr(runner, "_code_changes_present", lambda: [])
    preflight = {"status": "BLOCKED", "authorization": False}
    assert runner._run_real(preflight, "mimo-v2.5")["provider_calls"] == 0
    assert called is False


def test_authorization_false_blocks_even_when_preflight_is_otherwise_pass(monkeypatch: pytest.MonkeyPatch):
    # The guard must run before importing the provider client.  A PASS
    # preflight does not grant permission by itself.
    monkeypatch.setattr(runner, "_code_changes_present", lambda: [])
    result = runner._run_real({"status": "PASS", "authorization": False}, "mimo-v2.5")
    assert result["provider_calls"] == 0
    assert result["status"] == "DIRECTOR_V3_FINAL_SPINE_TOPOLOGY_RECANARY_BLOCKED"


def test_authorized_real_path_requires_entire_worktree_clean(monkeypatch: pytest.MonkeyPatch):
    """Artifacts/config drift must block the provider before import/call."""
    monkeypatch.setattr(runner, "_working_tree_dirty_paths", lambda: ["artifacts/pending.json"])
    monkeypatch.setattr(runner, "_code_changes_present", lambda: [])
    result = runner._run_real({"status": "PASS", "authorization": True}, "mimo-v2.5")
    assert result["provider_calls"] == 0
    assert result["reason"] == "WORKTREE_NOT_CLEAN_FOR_REAL_PROVIDER_RUN"
    assert result["dirty_paths"] == ["artifacts/pending.json"]


def test_cli_rejects_authorization_bypass_flags():
    script = Path(runner.__file__).resolve()
    result = subprocess.run(
        [sys.executable, str(script), "--force"],
        cwd=script.parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "--force" in (result.stdout + result.stderr)
