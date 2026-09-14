from pathlib import Path

from scripts.run_director_quality_v2_4_offline_replay import build_offline_replay
from scripts.run_director_quality_v2_4_targeted_tail_pilot import build_preflight
from scripts.freeze_director_quality_v2_4_b2 import freeze_b2
from scripts.run_director_quality_v2_4_targeted_tail_pilot import run_targeted_tail_pilot


ROOT = Path(__file__).resolve().parents[1]


def test_offline_replay_emits_provenance_reports_and_nonempty_gate_reasons():
    result = build_offline_replay(
        pilot_path=ROOT / "artifacts" / "director-quality-v2-3-phase-b2-pilot-20260914T040506Z.json",
        evidence_path=ROOT / "artifacts" / "director-quality-v2-3-phase-b2-evidence.json",
    )

    provenance = result["provenance"]
    assert provenance["commit_sha"]
    assert provenance["branch"] == "codex/unify-formal-workspace"
    assert provenance["source_artifacts"]
    assert all("\\" not in path and ":" not in path for path in provenance["source_artifacts"])
    assert result["scene_count"] == 24
    assert result["gate"]["status"] == "NOT_READY"
    assert result["gate"]["reasons"]
    assert result["side_effects"] == {
        "production": 0,
        "storyboard": 0,
        "media": 0,
        "object_storage": 0,
        "production_shadow": 0,
    }
    # The historical B2 artifact has only rejection counts for the three
    # failing scenes.  The replay must surface this as unknown taxonomy data,
    # never silently call it a known failure or fabricate a path.
    assert result["contract_failures"]["counts"].get("UNKNOWN_CONTRACT_FAILURE") == 20


def test_targeted_tail_preflight_selects_only_triggered_scenes_and_fails_closed_without_key():
    preflight = build_preflight(
        pilot_path=ROOT / "artifacts" / "director-quality-v2-3-phase-b2-pilot-20260914T040506Z.json",
        profile={
            "id": "mimo-test",
            "provider": "openai-compatible",
            "capability": "llm",
            "model_name": "mimo-v2.5",
            "base_url": "https://api.xiaomimimo.com/v1",
            "enabled": True,
            "key_configured": False,
        },
    )
    assert preflight["selected_scene_count"] == 15
    assert preflight["ready_for_confirmation"] is False
    assert "MIMO_PROFILE_KEY_OR_CONFIGURATION_MISSING" in preflight["blockers"]
    assert "SOURCE_PROVENANCE_MISSING" in preflight["blockers"]
    assert preflight["real_mimo_calls"] == 0


def test_targeted_tail_preflight_defaults_to_provenance_bearing_b2_freeze():
    """The real-call gate must start from the immutable V2.4 freeze."""
    from scripts import run_director_quality_v2_4_targeted_tail_pilot as module

    preflight = module.build_preflight(
        profile={
            "id": "mimo-test",
            "provider": "openai-compatible",
            "capability": "llm",
            "model_name": "mimo-v2.5",
            "base_url": "https://api.xiaomimimo.com/v1",
            "enabled": True,
            "key_configured": False,
        },
    )
    assert preflight["source_artifact"] == "artifacts/director-quality-v2-4-b2-freeze.json"
    assert preflight["source_commit"]
    assert preflight["selected_scene_count"] == 15
    assert "SOURCE_PROVENANCE_MISSING" not in preflight["blockers"]
    assert "MIMO_PROFILE_KEY_OR_CONFIGURATION_MISSING" in preflight["blockers"]
    assert preflight["ready_for_confirmation"] is False


def test_b2_freeze_adds_portable_provenance_without_changing_scene_count():
    frozen = freeze_b2(
        pilot_path=ROOT / "artifacts" / "director-quality-v2-3-phase-b2-pilot-20260914T040506Z.json",
        evidence_path=ROOT / "artifacts" / "director-quality-v2-3-phase-b2-evidence.json",
    )
    assert frozen["frozen"] is True
    assert len(frozen["scenes"]) == 24
    provenance = frozen["provenance"]
    assert provenance["commit_sha"]
    assert all("\\" not in path and ":" not in path for path in provenance["source_artifacts"])


def test_targeted_tail_runner_uses_frozen_evidence_and_keeps_side_effects_zero():
    """The mocked integration path exercises all selected tails offline."""
    calls = []

    result = run_targeted_tail_pilot(
        pilot_path=ROOT / "artifacts" / "director-quality-v2-4-b2-freeze.json",
        evidence_path=ROOT / "artifacts" / "director-quality-v2-3-phase-b2-evidence.json",
        repair_callable=lambda request: (
            calls.append(request)
            or {
                "schema_version": "director_creative_patch_v1",
                "patches": [],
                "auxiliary_shot_proposals": [],
            }
        ),
        model="mimo-v2.5",
    )

    assert result["selected_scene_count"] == 15
    assert result["attempted_scene_count"] == 15
    assert result["execution_coverage"] == 1.0
    assert len(calls) > 0
    assert result["side_effects"] == {
        "production": 0,
        "storyboard": 0,
        "media": 0,
        "object_storage": 0,
        "production_shadow": 0,
    }
