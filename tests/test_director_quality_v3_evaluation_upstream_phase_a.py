from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from core.evaluation_upstream_phase_a import (
    EXPECTED_NORMALIZED_HASH,
    EXPECTED_RAW_HASH,
    SOURCE_PACKAGE_ID,
    SOURCE_VERSION_ID,
    build_call_graph,
    build_fact_request,
    build_script_ir_request,
    canonicalize_fact_payload,
    canonicalize_script_payload,
    evaluation_book_id,
    load_and_verify_source,
    phase_a_preflight,
    run_with_provider_calls,
)


def _source() -> dict:
    raw = "程雨说：我看见门外有一把伞。她把纸箱拖到门口。"
    return {
        "status": "PASS",
        "raw_text": raw,
        "raw_hash": hashlib.sha256(raw.encode()).hexdigest(),
        "provenance": {
            "source_package_id": SOURCE_PACKAGE_ID,
            "source_version_id": SOURCE_VERSION_ID,
            "source_class": "EVALUATION_ONLY",
            "source_authorship": "AI_GENERATED",
            "human_authored": False,
            "blind_human_origin_eligible": False,
            "functional_pipeline_evaluation_eligible": True,
            "user_authorized_for_evaluation": True,
            "raw_source_hash": hashlib.sha256(raw.encode()).hexdigest(),
            "normalized_source_hash": EXPECTED_NORMALIZED_HASH,
        },
        "errors": [],
    }


def _facts(raw: str) -> dict:
    return {
        "facts": [
            {"subject_type": "character", "subject_id": "程雨", "predicate": "said", "value": "我看见门外有一把伞。", "authority": "source_text", "status": "confirmed", "evidence": [{"excerpt": "程雨说：我看见门外有一把伞。"}]},
            {"subject_type": "character", "subject_id": "程雨", "predicate": "belief", "value": "某人来过", "authority": "model_observation", "status": "proposed", "evidence": []},
        ]
    }


def _script() -> dict:
    return {"script_ir": {"title": "门外", "scenes": [{"name": "门口", "location_name": "公寓门口", "beats": [{"event": "她把纸箱拖到门口。"}], "dialogues": [{"text": "我看见门外有一把伞。"}]}]}}


def test_eval_phase_a_uses_immutable_source_package():
    result = load_and_verify_source()
    assert result["status"] == "PASS"
    assert result["raw_hash"] == EXPECTED_RAW_HASH
    assert result["package"]["source_package_id"] == SOURCE_PACKAGE_ID


def test_eval_phase_a_rejects_source_hash_mismatch(tmp_path: Path):
    package = Path("work/intake/director_v3/evaluation_packages/SRC79f12d1b7f5eb828.json")
    raw = Path("work/intake/director_v3/evaluation_packages/SRC79f12d1b7f5eb828.raw")
    result = load_and_verify_source(package_path=package, raw_path=raw, expected_raw_hash="0" * 64)
    assert result["status"] == "FAIL"
    assert any(error["code"] == "SOURCE_RAW_HASH_MISMATCH" for error in result["errors"])


def test_eval_phase_a_preserves_ai_generated_provenance():
    source = load_and_verify_source()
    assert source["provenance"]["source_authorship"] == "AI_GENERATED"
    assert source["provenance"]["human_authored"] is False
    assert source["provenance"]["blind_human_origin_eligible"] is False


def test_eval_phase_a_does_not_enter_human_fresh_pool():
    preflight = phase_a_preflight(source=_source(), provider_config={"provider": "openai-compatible", "model": "mimo-v2.5"})
    assert preflight["mutation_plan"]["human_fresh_pool"] == 0
    assert preflight["isolation_plan"]["fresh_pool"] == "forbidden"


def test_eval_phase_a_call_budget_max_two_and_no_retry_policy():
    graph = build_call_graph(provider_config={"provider": "openai-compatible", "model": "mimo-v2.5"})
    assert graph["predicted_provider_calls"] == 2
    assert graph["absolute_max_provider_calls"] == 2
    assert all(value == 0 for value in graph["retry_policy"].values())
    assert "core.fact_snapshot.build_fact_snapshot" in graph["stages"][0]["reusable"]
    assert "agents.reader.ReaderAgent" in graph["excluded_production_paths"]


def test_source_fact_requires_verified_evidence():
    source = _source()
    result = canonicalize_fact_payload({"facts": [{"subject_type": "character", "subject_id": "程雨", "predicate": "saw", "value": "伞", "authority": "source_text", "status": "confirmed", "evidence": [{"excerpt": "不存在"}]}]}, raw_text=source["raw_text"], source_fingerprint=source["raw_hash"], provenance=source["provenance"])
    assert result["report"]["status"] == "FAIL"
    assert result["report"]["evidence_invalid"] == 1


def test_character_claim_not_promoted_to_objective_fact():
    source = _source()
    payload = {"facts": [{"subject_type": "character", "subject_id": "程雨", "predicate": "reported", "value": "有人来过", "authority": "model_observation", "status": "confirmed", "evidence": []}]}
    result = canonicalize_fact_payload(payload, raw_text=source["raw_text"], source_fingerprint=source["raw_hash"], provenance=source["provenance"])
    assert result["report"]["claim_objective_promotion_violations"] == 1
    assert result["snapshot"]["records"][0]["status"] == "proposed"


def test_model_observation_not_auto_confirmed():
    source = _source()
    result = canonicalize_fact_payload({"facts": [{"subject_type": "location", "subject_id": "门口", "predicate": "mood", "value": "压迫", "authority": "model_observation", "status": "proposed", "evidence": []}]}, raw_text=source["raw_text"], source_fingerprint=source["raw_hash"], provenance=source["provenance"])
    assert result["snapshot"]["records"][0]["authority"] == "model_observation"
    assert result["snapshot"]["records"][0]["status"] == "proposed"


def test_fact_ids_deterministic():
    source = _source()
    first = canonicalize_fact_payload(_facts(source["raw_text"]), raw_text=source["raw_text"], source_fingerprint=source["raw_hash"], provenance=source["provenance"])["snapshot"]
    second = canonicalize_fact_payload(_facts(source["raw_text"]), raw_text=source["raw_text"], source_fingerprint=source["raw_hash"], provenance=source["provenance"])["snapshot"]
    assert [row["fact_id"] for row in first["records"]] == ["FACT_0001", "FACT_0002"]
    assert first["payload_hash"] == second["payload_hash"]


def test_fact_snapshot_source_fingerprint_exact():
    source = _source()
    result = canonicalize_fact_payload(_facts(source["raw_text"]), raw_text=source["raw_text"], source_fingerprint=source["raw_hash"], provenance=source["provenance"])
    assert result["report"]["source_fingerprint_exact"] is True


def test_script_ir_requires_fact_snapshot_pass():
    source = _source()
    bad = {"validation": {"status": "needs_review"}}
    result = canonicalize_script_payload(_script(), raw_text=source["raw_text"], fact_snapshot=bad, provenance=source["provenance"])
    assert result["report"]["status"] == "NEEDS_REVIEW"


def test_script_ir_scene_ids_deterministic_unique():
    source = _source()
    snapshot = canonicalize_fact_payload(_facts(source["raw_text"]), raw_text=source["raw_text"], source_fingerprint=source["raw_hash"], provenance=source["provenance"])["snapshot"]
    first = canonicalize_script_payload(_script(), raw_text=source["raw_text"], fact_snapshot=snapshot, provenance=source["provenance"])["script_ir"]
    second = canonicalize_script_payload(_script(), raw_text=source["raw_text"], fact_snapshot=snapshot, provenance=source["provenance"])["script_ir"]
    assert first["scenes"][0]["scene_id"] == second["scenes"][0]["scene_id"]
    assert len({scene["scene_id"] for scene in first["scenes"]}) == len(first["scenes"])


def test_reported_past_does_not_auto_create_flashback_scene():
    source = _source()
    snapshot = {"validation": {"status": "qualified"}}
    payload = {"scenes": [{"name": "回忆", "scene_type": "flashback", "beats": [{"event": "过去发生"}]}]}
    result = canonicalize_script_payload(payload, raw_text=source["raw_text"], fact_snapshot=snapshot, provenance=source["provenance"])
    assert result["report"]["errors"][0]["code"] == "REPORTED_PAST_FLASHBACK_UNGROUNDED"


def test_internal_thought_not_auto_dialogue():
    source = _source()
    result = canonicalize_script_payload({"scenes": [{"name": "门口", "beats": [{"event": "她把纸箱拖到门口。"}], "dialogues": [{"type": "internal_thought", "text": "我不应该开门"}]}]}, raw_text=source["raw_text"], fact_snapshot={"validation": {"status": "qualified"}}, provenance=source["provenance"])
    assert any(error["code"] == "INTERNAL_THOUGHT_AS_DIALOGUE" for error in result["report"]["errors"])


def test_missing_source_dialogue_not_invented():
    source = _source()
    result = canonicalize_script_payload({"scenes": [{"name": "门口", "beats": [{"event": "她把纸箱拖到门口。"}], "dialogues": [{"text": "这是新对白"}]}]}, raw_text=source["raw_text"], fact_snapshot={"validation": {"status": "qualified"}}, provenance=source["provenance"])
    assert result["report"]["invented_dialogues"] == 1


def test_script_ir_does_not_add_directing_fields():
    source = _source()
    result = canonicalize_script_payload({"scenes": [{"name": "门口", "camera": "close-up", "beats": [{"event": "她把纸箱拖到门口。"}]}]}, raw_text=source["raw_text"], fact_snapshot={"validation": {"status": "qualified"}}, provenance=source["provenance"])
    assert result["report"]["director_leakage"] == 1


def test_script_ir_provenance_propagates():
    source = _source()
    result = canonicalize_script_payload(_script(), raw_text=source["raw_text"], fact_snapshot={"validation": {"status": "qualified"}}, provenance=source["provenance"])
    assert result["script_ir"]["provenance"] == source["provenance"]


def test_fact_snapshot_failure_stops_before_script_ir_call():
    source = _source()
    calls = []
    bad_fact = {"facts": [{"subject_type": "character", "subject_id": "程雨", "predicate": "x", "value": "y", "authority": "source_text", "status": "confirmed", "evidence": [{"excerpt": "不存在"}]}]}
    def provider(request):
        calls.append(request["task"])
        return bad_fact
    result = run_with_provider_calls(source=source, provider_config={"provider": "openai-compatible", "model": "mimo-v2.5"}, call_provider=provider)
    assert result["status"].endswith("_FAILED")
    assert result["provider_calls"] == 1
    assert calls == ["extract_source_grounded_facts"]


def test_run_with_provider_calls_has_no_retry_and_max_two_calls():
    source = _source()
    calls = []
    def provider(request):
        calls.append(request["task"])
        return _facts(source["raw_text"]) if len(calls) == 1 else _script()
    result = run_with_provider_calls(source=source, provider_config={"provider": "openai-compatible", "model": "mimo-v2.5"}, call_provider=provider)
    assert result["provider_calls"] == 2
    assert calls == ["extract_source_grounded_facts", "structure_fact_grounded_script_ir"]
