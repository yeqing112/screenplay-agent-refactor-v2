from __future__ import annotations

import hashlib

from core.director_scene_strategy import build_runtime_strategy_contract
from core.director_scene_strategy_ir_normalizer import normalize_source_ref
from core.director_scene_strategy_semantic_spec_v2 import build_source_ref_contract
from core.director_strategy_prompt import build_scene_strategy_ir_v2_prompt
from core.director_strategy_quality import compare_canonical_strategies
from scripts.run_director_quality_v3_final_adjudication import RAW_ARTIFACT, _contract, _equivalence, _records, run
from scripts.run_director_quality_v3_phase1_2 import _authoritative


def _runtime_first():
    inputs = _authoritative(_records()[0])
    return inputs, build_runtime_strategy_contract(scene=inputs["scene"], treatment=inputs["director_treatment"], blocking=inputs["scene_blocking"], fact_snapshot=inputs["fact_snapshot"])


def test_provider_runtime_contract_equivalence():
    inputs, runtime = _runtime_first()
    prompt = build_scene_strategy_ir_v2_prompt(evidence={"scene_id": runtime["scene_id"], "strategy_contract": runtime}, model_profile={"model_name": "mimo-v2.5"})
    result = _equivalence(runtime, prompt["provider_contract"])
    assert all(result[key] for key in ("beat_ids_equal", "character_ids_equal", "allowed_source_refs_equal", "beat_alias_equal", "source_ref_contract_equal"))


def test_provider_beat_ref_valid_at_runtime():
    _, runtime = _runtime_first()
    assert normalize_source_ref("beat:1", contract=runtime) == ("beat:1", None)


def test_provider_character_ref_valid_at_runtime():
    _, runtime = _runtime_first()
    assert normalize_source_ref("character:19", contract=runtime) == ("character:19", None)


def test_unknown_ref_still_rejected():
    contract = build_source_ref_contract(beat_ids=["1"], character_ids=["19"])
    assert normalize_source_ref("beat:999", contract=contract)[1]["code"] == "UNKNOWN_SOURCE_REFERENCE"
    assert normalize_source_ref("character:999", contract=contract)[1]["code"] == "UNKNOWN_SOURCE_REFERENCE"


def test_alias_contract_equivalence():
    contract = build_source_ref_contract(beat_ids=["B1", "B2"], character_ids=["19"])
    assert normalize_source_ref("beat:1", contract=contract) == ("beat:B1", None)


def test_adjudication_uses_raw_output_without_provider_call(monkeypatch):
    import core.llm
    monkeypatch.setattr(core.llm, "call_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("provider call")))
    result = run()
    assert result["real_mimo_calls"] == 0
    assert result["provider_http_requests"] == 0


def test_original_artifacts_unchanged():
    before = hashlib.sha256(RAW_ARTIFACT.read_bytes()).hexdigest()
    run()
    assert hashlib.sha256(RAW_ARTIFACT.read_bytes()).hexdigest() == before


def test_candidate_signal_not_mislabeled_as_canonical():
    result = run()
    assert result["canonical_strategy_v3_count"] < 3
    assert all(scene["directing_signal"].startswith("CANDIDATE_AUTOMATED_DIRECTING_SIGNAL_") for scene in result["scenes"])


def test_distinctiveness_requires_three_canonical_scenes():
    result = compare_canonical_strategies([])
    assert result["expected_pair_count"] == 3
    assert result["all_pairs_checked"] is False
