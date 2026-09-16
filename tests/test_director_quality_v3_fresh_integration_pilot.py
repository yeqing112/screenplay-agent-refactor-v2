from __future__ import annotations

import json
from pathlib import Path

from scripts.run_director_quality_v3_fresh_integration_pilot import (
    RETIRED_SCENES,
    _complexity,
    _approved_scene_rows,
    build_provider_exposure_registry,
    select_fresh_cohort,
)
from scripts import run_director_quality_v3_fresh_integration_pilot as pilot


def _row(scene_id: str, score: int, *, reasons=None):
    return {
        "scene_id": scene_id,
        "scene": {"scene_id": scene_id, "beats": [{"beat_id": f"B{i}"} for i in range(1, max(4, score + 3))]},
        "scene_blocking": {"participants": [{"character_id": "1", "name": "A"}]},
        "director_treatment": {"status": "approved"},
        "fact_snapshot": {"status": "confirmed"},
        "source_evidence": {"database": "fixture"},
        "upstream": {},
        "eligibility_reasons": reasons or [],
        "complexity": {"complexity_score": score},
    }


def test_real_database_has_three_non_retired_fresh_candidates():
    rows = _approved_scene_rows()
    ids = {row["scene_id"] for row in rows}
    assert len(rows) == 6
    assert RETIRED_SCENES.issubset(ids)
    registry = build_provider_exposure_registry(candidate_ids=ids)
    selection = select_fresh_cohort(rows, registry)
    assert selection["candidate_count"] == 3
    assert selection["selected_count"] == 3
    assert set(selection["excluded"]["retired"]) == RETIRED_SCENES
    assert all(item["status"] == "NOT_EXPOSED" for item in registry["scenes"].values() if item["status"] != "EXPOSED")


def test_complexity_formula_is_structured_and_deterministic():
    row = _row("s", 0)
    row["scene"] = {
        "scene_id": "s",
        "beats": [
            {"beat_id": "B1", "type": "reveal", "information_change": "x", "emotion_change": "y", "event": "进入"},
            {"beat_id": "B2", "type": "action", "emotion_change": "y", "event": "离开"},
            {"beat_id": "B3", "type": "action"},
            {"beat_id": "B4", "type": "action"},
        ],
        "dialogues": ["a", "b"],
        "props": ["prop-a"],
    }
    row["scene_blocking"] = {"participants": [{"character_id": "1", "name": "A", "anchor": "door"}, {"character_id": "2", "name": "B"}], "spatial_rules": ["rule"]}
    first = _complexity(row)
    second = _complexity(row)
    assert first == second
    assert first["complexity_score"] == (
        first["beat_count"] + 2 * (first["character_count"] - 1) + first["dialogue_turn_count"]
        + first["prop_ref_count"] + 2 * first["information_change_count"]
        + first["reaction_candidate_count"] + first["entrance_exit_count"] + first["spatial_event_count"]
    )


def test_exposure_registry_does_not_treat_report_mentions_as_provider_calls(tmp_path: Path):
    sid = "book1:e1:scene"
    (tmp_path / "director-quality-v3-report.json").write_text(json.dumps({"scene_id": sid, "note": "mentioned only"}), encoding="utf-8")
    registry = build_provider_exposure_registry(tmp_path, {sid})
    assert registry["scenes"][sid]["status"] == "NOT_EXPOSED"
    (tmp_path / "director-quality-v3-demo-real.json").write_text(json.dumps({"provider_http_requests": 1, "scenes": [{"scene_id": sid}]}), encoding="utf-8")
    registry = build_provider_exposure_registry(tmp_path, {sid})
    assert registry["scenes"][sid]["status"] == "EXPOSED"


def test_exposure_unknown_is_excluded_and_selection_is_frozen():
    rows = [_row("low", 1), _row("mid", 2), _row("high", 3), _row("unknown", 0)]
    registry = {"scenes": {sid: {"status": "NOT_EXPOSED", "evidence": []} for sid in ["low", "mid", "high", "unknown"]}}
    registry["scenes"]["unknown"] = {"status": "EXPOSURE_UNKNOWN", "evidence_paths": ["x"]}
    selection = select_fresh_cohort(rows, registry, retired=set())
    assert selection["selected"]["low"]["scene_id"] == "low"
    assert selection["selected"]["medium"]["scene_id"] == "mid"
    assert selection["selected"]["high"]["scene_id"] == "high"
    assert "unknown" not in {selection["selected"][k]["scene_id"] for k in ("low", "medium", "high")}
    assert "unknown" not in {item["scene_id"] for item in selection["eligible"]}


def test_provider_runner_uses_one_strategy_call_per_scene_and_zero_retries(monkeypatch, tmp_path):
    rows = _approved_scene_rows()[:3]
    calls = []

    def fake_call(prompt, **kwargs):
        calls.append(kwargs)
        return "{}"  # model-format failure; downstream layers must be skipped

    monkeypatch.setattr(pilot, "ART", tmp_path)
    import core.llm
    monkeypatch.setattr(core.llm, "call_llm", fake_call)
    result = pilot._run_provider(rows, {"provider": "test", "model_name": "mimo-v2.5", "api_key": "k", "base_url": "https://invalid.test/v1"})
    assert result["status"] == "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_FAILED"
    assert result["provider_calls"] == 3
    assert result["ledger"]["attempted_strategy_calls"] == 3
    assert result["ledger"]["attempted_spine_calls"] == 0
    assert result["ledger"]["attempted_skeleton_calls"] == 0
    assert len(calls) == 3
    assert all(call["retries"] == 0 for call in calls) if calls and "retries" in calls[0] else True


def test_finalize_persists_post_call_ledger_and_execution_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(pilot, "ART", tmp_path)
    manifest_path = tmp_path / "director-quality-v3-fresh-integration-pilot-execution-manifest.json"
    manifest_path.write_text(json.dumps({
        "schema_version": "director_quality_v3_fresh_integration_pilot_execution_manifest_v1",
        "status": "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_READY",
        "provider_calls": 0,
    }), encoding="utf-8")
    (tmp_path / "director-quality-v3-fresh-cohort-manifest.json").write_text(json.dumps({"selected": {}}), encoding="utf-8")
    ledger = {
        "attempted_strategy_calls": 3,
        "attempted_spine_calls": 0,
        "attempted_skeleton_calls": 0,
        "successful_calls": 3,
        "all_retry_counts": {"transport": 0, "format": 0, "semantic": 0, "creative": 0, "repair": 0},
    }
    execution = {
        "status": "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_FAILED",
        "harness_error": None,
        "ledger": ledger,
        "scenes": [{"scene_id": "s1", "cohort_role": "low", "status": "MODEL_FAILURE", "provider_errors": [], "calls": []}],
    }
    finalized = pilot._finalize_execution(execution, {}, {"provider": "test", "model_name": "mimo-v2.5"})
    assert finalized["status"] == "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_FAILED"
    persisted_ledger = json.loads((tmp_path / "director-quality-v3-fresh-integration-pilot-provider-call-ledger.json").read_text(encoding="utf-8"))
    persisted_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted_ledger["attempted_strategy_calls"] == 3
    assert persisted_ledger["successful_calls"] == 3
    assert persisted_manifest["provider_calls"] == 3
    assert persisted_manifest["status"] == "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_FAILED"


def test_failed_authority_records_failure_layer_without_retry_or_cohort_replacement(monkeypatch, tmp_path):
    authority_path = tmp_path / "authority.json"
    authority_path.write_text(json.dumps({"schema_version": "director_v3_current_stage_authority_v2"}), encoding="utf-8")
    monkeypatch.setattr(pilot, "AUTHORITY_PATH", authority_path)
    pilot._update_authority(
        "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_FAILED",
        "cohort-fp",
        {"attempted_strategy_calls": 3, "attempted_spine_calls": 0, "attempted_skeleton_calls": 0, "successful_calls": 3, "all_retry_counts": {"transport": 0}},
    )
    authority = json.loads(authority_path.read_text(encoding="utf-8"))["fresh_integration_pilot"]
    assert authority["status"] == "FAILED"
    assert authority["no_auto_retry"] is True
    assert authority["cohort_replacement"] is False
    assert authority["failure_layers"][0]["code"] == "STRATEGY_AUTHORITY_INCOMPLETE"
