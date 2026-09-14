import json
from pathlib import Path

from core.director_creative_value import replay_creative_value
from core.director_tail_repair_acceptance import evaluate_repair_acceptance


ROOT = Path(__file__).resolve().parents[1]


def _baseline_value():
    return {
        "schema_version": "director_creative_value_score_v1",
        "status": "ready",
        "score": 25.0,
        "components": {
            "opportunity_coverage": 1.0,
            "useful_creative_acceptance": 0.0,
            "edit_strategy": 0.0,
            "emotion_arc": 1.0,
            "information_strategy": 1.0,
            "tail_stability": 0.0,
        },
    }


def test_replay_uses_authoritative_scorer_and_is_reproducible():
    kwargs = {
        "baseline_creative_value": _baseline_value(),
        "opportunities": [{
            "schema_version": "director_creative_opportunity_v1",
            "opportunity_id": "O1",
            "type": "OPP_ACTION_ACCELERATION",
            "scene_id": "S1",
            "beat_id": "B1",
            "subjects": ["C1"],
            "reason": "test",
            "evidence_refs": ["test"],
            "priority": "high",
            "eligible": True,
            "recommended_directing_dimensions": ["edit_strategy"],
        }],
        "decisions": [{"opportunity_id": "O1", "decision": "ACT", "strategy": "tighten cut"}],
        "baseline_outcomes": [{
            "opportunity_id": "O1",
            "final_status": "FALLBACK_BASELINE",
            "quality_delta": 0,
            "dimension_deltas": {},
        }],
        "candidate_interventions": [{
            "opportunity_id": "O1",
            "patch_valid": True,
            "applied": True,
            "fact_contract_pass": True,
            "new_blocker": False,
            "quality_delta": 4,
            "dimension_deltas": {"edit_strategy": 2},
            "repaired": True,
        }],
        "after_director_quality": 54.0,
        "candidate_fingerprint": "candidate-1",
        "frozen_inputs": {"scene_id": "S1", "opportunity_ids": ["O1"]},
    }
    first = replay_creative_value(**kwargs)
    second = replay_creative_value(**kwargs)
    assert first["measurement_status"] == "ready"
    assert first["score"] > kwargs["baseline_creative_value"]["score"]
    assert first["creative_value_replay_fingerprint"] == second["creative_value_replay_fingerprint"]
    assert first["score"] == second["score"]


def test_changed_candidate_without_replay_is_measurement_blocked():
    before = {"director_quality_score": 50, "dimensions": {"EDIT_RHYTHM": 2}}
    after = {"director_quality_score": 60, "dimensions": {"EDIT_RHYTHM": 4}}
    result = evaluate_repair_acceptance(
        before_quality=before,
        after_quality=after,
        target_dimensions=["EDIT_RHYTHM"],
        contract_pass=True,
        creative_value_required=True,
        creative_value_measurement_status="blocked",
    )
    assert result["accepted"] is False
    assert "MEASUREMENT_BLOCKED" in result["reasons"]


def test_v243_manifest_runner_does_not_rerank(monkeypatch):
    from scripts import run_director_quality_v2_4_targeted_tail_pilot as runner

    manifest = json.loads((ROOT / "artifacts" / "director-quality-v2-4-3-targeted-tail-manifest.json").read_text(encoding="utf-8"))
    scene_id = manifest["scenes"][0]["scene_id"]

    def forbidden_ranker(*args, **kwargs):
        raise AssertionError("V2.4.3 must use frozen root causes")

    monkeypatch.setattr("core.director_tail_repair_executor.rank_tail_root_causes_v2", forbidden_ranker)

    def repair(request):
        shot_id = request["relevant_shots"][0]["plan_shot_id"]
        return {
            "schema_version": "director_tail_repair_ir_v1",
            "repair_type": "edit",
            "root_cause": request["root_cause"],
            "target_dimensions": request["target_dimensions"],
            "shot_decisions": [{"plan_shot_id": shot_id, "edit": {"cut_reason": "reaction_complete"}}],
        }

    result = runner.run_targeted_tail_pilot(
        pilot_path=ROOT / "artifacts" / "director-quality-v2-4-b2-freeze.json",
        evidence_path=ROOT / "artifacts" / "director-quality-v2-3-phase-b2-evidence.json",
        repair_callable=repair,
        model="mimo-v2.5",
        scene_ids={scene_id},
        manifest_path=ROOT / "artifacts" / "director-quality-v2-4-3-targeted-tail-manifest.json",
    )
    row = result["scenes"][0]
    assert row["creative_value_measurement_status"] == "ready"
    assert row["creative_value_replay"]["creative_value_replay_fingerprint"]
    assert result["frozen_manifest"] == "artifacts/director-quality-v2-4-3-targeted-tail-manifest.json"
