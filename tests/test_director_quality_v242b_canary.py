import importlib.util
from pathlib import Path

from core.director_tail_repair_context import resolve_tail_repair_context
from core.director_tail_repair_request import build_repair_request, to_provider_request, with_attempt

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_real_frozen_manifest_uses_authoritative_ranking_and_reports_coverage():
    builder = _load("v242b_manifest", "scripts/build_director_quality_v2_4_2b_canary_manifest.py")
    payload = builder.build_manifest()
    assert payload["available_repair_types"] == ["edit", "emotion", "information", "performance"]
    assert payload["selected_repair_types"] == ["edit", "emotion", "information", "performance"]
    assert payload["missing_repair_types"] == ["camera"]
    assert payload["canary_coverage_status"] == "FULL_TYPE_COVERAGE"
    assert payload["sample_count"] == 4
    for sample in payload["samples"]:
        assert sample["relevant_plan_shot_ids"]
        assert sample["root_cause_rank"] >= 1
        assert sample["root_cause_score"] >= 0


def test_context_resolver_binds_opportunity_beat_to_matching_shot_and_is_bounded():
    context = resolve_tail_repair_context(
        root_cause="WEAK_INFORMATION_STRATEGY",
        opportunities=[
            {"opportunity_id": "O2", "beat_id": "B02", "priority": "high", "eligible": True, "recommended_directing_dimensions": ["information_strategy"]},
            {"opportunity_id": "O1", "beat_id": "B01", "priority": "low", "eligible": True, "recommended_directing_dimensions": ["information_strategy"]},
        ],
        treatment={"beat_map": [{"beat_id": "B01", "event": "setup"}, {"beat_id": "B02", "event": "reveal"}]},
        structural_candidate={"shots": [{"plan_shot_id": "S01", "beat_id": "B01"}, {"plan_shot_id": "S02", "beat_id": "B02"}]},
    )
    assert context["relevant_beat_ids"] == ["B02", "B01"]
    assert context["relevant_plan_shot_ids"] == ["S02", "S01"]
    assert context["allowed_plan_shot_ids"] == ["S02", "S01"]
    assert len(context["relevant_opportunities"]) <= 5
    assert len(context["relevant_beats"]) <= 3
    assert len(context["relevant_shots"]) <= 4


def test_context_fallback_is_deterministic_for_missing_opportunity_binding():
    kwargs = {
        "root_cause": "WEAK_EDIT_STRATEGY",
        "opportunities": [],
        "treatment": {"beat_map": [{"beat_id": "B01", "event": "one"}, {"beat_id": "B02", "event": "two"}]},
        "structural_candidate": {"shots": [{"plan_shot_id": "S01", "beat_id": "B01"}, {"plan_shot_id": "S02", "beat_id": "B02"}]},
    }
    first = resolve_tail_repair_context(**kwargs)
    second = resolve_tail_repair_context(**kwargs)
    assert first == second
    assert first["allowed_plan_shot_ids"] == ["S01", "S02"]
    assert first["fallback_reason"]


def test_provider_projection_removes_legacy_retry_fields_and_keeps_fingerprints():
    base = build_repair_request(
        root_cause="WEAK_EDIT_STRATEGY",
        target_dimensions=["EDIT_RHYTHM"],
        relevant_beats=[{"beat_id": "B01"}],
        relevant_shots=[{"plan_shot_id": "S01", "beat_id": "B01"}],
        allowed_plan_shot_ids=["S01"],
    )
    attempt = with_attempt(base, {"number": 1, "kind": "CREATIVE_GENERATION"})
    assert "base_request_fingerprint" in base
    assert "attempt_request_fingerprint" in attempt
    assert attempt["attempt_request_fingerprint"] != base["base_request_fingerprint"]
    provider = to_provider_request(attempt)
    assert provider["provider_request_fingerprint"]
    assert "request_fingerprint" not in provider
    assert "attempt_kind" not in provider
    assert "previous_raw_output" not in provider
    assert "previous_validation_errors" not in provider
    assert provider["allowed_plan_shot_ids"] == ["S01"]


def test_first_attempt_context_is_non_empty_for_every_selected_sample():
    manifest = _load("v242b_manifest_for_context", "scripts/build_director_quality_v2_4_2b_canary_manifest.py").build_manifest()
    runner = _load("v242_runner_for_context", "scripts/run_director_quality_v2_4_targeted_tail_pilot.py")
    canary = _load("v242b_canary_for_context", "scripts/run_director_quality_v2_4_2b_protocol_canary.py")
    calls = []
    def provider(request):
        calls.append(request)
        return canary._mock_ir(request)
    ids = {sample["scene_id"] for sample in manifest["samples"]}
    roots = {sample["scene_id"]: [sample["root_cause"]] for sample in manifest["samples"]}
    runner.run_targeted_tail_pilot(pilot_path=runner.DEFAULT_PILOT, repair_callable=provider, scene_ids=ids, root_causes_by_scene=roots)
    assert len(calls) == len(manifest["samples"])
    assert all(request["relevant_shots"] for request in calls)
    assert all(request["allowed_plan_shot_ids"] for request in calls)
    for request in calls:
        structural_ids = {shot.get("plan_shot_id") for shot in request["relevant_shots"]}
        assert set(request["allowed_plan_shot_ids"]).issubset(structural_ids)
