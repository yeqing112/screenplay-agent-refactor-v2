"""V6.3 authority versus creative-readiness separation contracts."""
from __future__ import annotations

import copy
import json

from core.script_creative_quality import (
    build_creative_readiness_backlog,
    run_script_creative_quality_gate,
    run_source_grounded_authority_quality_gate,
)
from core.script_ir import build_script_ir
from core.source_authority import canonical_json_sha256
from tests.script_fixtures import build_explicit_production_script_payload


def _source_payload(*, scene_count: int = 1) -> dict:
    scenes = []
    for index in range(scene_count):
        scene_id = f"E90_SC{index + 1:03d}"
        scenes.append({
            "scene_id": scene_id,
            "source_identity_evidence": [{"text": f"Source scene {index + 1}."}],
            "participants": [],
            "actions": [{"action_id": f"{scene_id}_A01", "text": f"Source action {index + 1}.", "source_evidence": f"Source scene {index + 1}."}],
            "dialogues": [{"dialogue_id": f"{scene_id}_D01", "speaker": "MAYA", "text": "Wait.", "source_evidence": "MAYA: Wait."}],
            "script_blocks": [
                {"order": 10, "type": "ACTION", "ref": f"{scene_id}_A01"},
                {"order": 20, "type": "DIALOGUE", "ref": f"{scene_id}_D01"},
            ],
            "timeline_origin": "SOURCE_GROUNDED",
            "timeline_authority": "SOURCE_EVIDENCE_ORDER",
            "production_eligible": True,
        })
    payload = {
        "schema_version": "source_grounded_script_payload_v3_1",
        "source_grounded_schema_version": "source_grounded_script_payload_v3_1",
        "preparation_policy": "SOURCE_GROUNDED_STRICT",
        "scenes": scenes,
        "scene_transitions": [],
    }
    payload["canonical_script_payload_fingerprint"] = canonical_json_sha256({key: value for key, value in payload.items() if key != "preparation_policy"})
    payload["source_lineage"] = {
        "origin_source_kind": "BOOK_CHAPTER", "origin_source_package_id": "book:fixture", "origin_source_version_id": "chapter:fixture:v1", "origin_source_locator": {"book_id": 90, "chapter_seq": 1}, "origin_source_raw_hash": "a" * 64, "structuring_response_fingerprint": "b" * 64, "reconciliation_policy_version": "reconciliation_v1", "reconciliation_fingerprint": "c" * 64, "migration_fingerprint": "d" * 64,
    }
    return payload


def test_pure_v31_source_payload_has_zero_beats_and_transitions():
    payload = _source_payload()
    assert sum(len(scene.get("beats", [])) for scene in payload["scenes"]) == 0
    assert payload["scene_transitions"] == []


def test_source_authority_gate_passes_without_creative_beats_or_transitions():
    report = run_source_grounded_authority_quality_gate(_source_payload())
    assert report["status"] == "SOURCE_AUTHORITY_GATE_PASS", report
    assert report["qualified"] is True


def test_source_creative_readiness_is_deterministic_and_diagnostic():
    first = build_creative_readiness_backlog(_source_payload(scene_count=2))
    second = build_creative_readiness_backlog(json.loads(json.dumps(_source_payload(scene_count=2))))
    assert first == second
    assert first["creative_readiness_state"] == "AUTHORING_REQUIRED"
    assert "DRAMATIC_BEATS_REQUIRED" in first["backlog"]
    assert "SCENE_TRANSITIONS_REQUIRED" in first["backlog"]
    assert len(first["creative_readiness_fingerprint"]) == 64


def test_source_authority_gate_never_materializes_creative_backlog_as_facts():
    payload = _source_payload()
    before = copy.deepcopy(payload)
    report = run_source_grounded_authority_quality_gate(payload)
    assert report["creative_readiness"]["backlog"]
    assert payload == before
    assert all("creative_readiness" not in str(value) for value in payload.values())


def test_authored_valid_fixture_keeps_blocking_creative_gate_semantics():
    authored = build_explicit_production_script_payload({
        "scenes": [{"name": "Hall", "beats": [{"beat_id": "B1", "type": "HOOK", "event": "A turn.", "importance": "critical", "requires_reaction": True}]}],
    })
    report = run_script_creative_quality_gate(build_script_ir(authored, book_id=1, episode=1), production=True)
    assert report["status"] == "PRODUCTION_QUALIFIED"


def test_authored_missing_hook_still_blocks_creative_gate():
    authored = build_explicit_production_script_payload({
        "scenes": [{"name": "Hall", "beats": [{"beat_id": "B1", "type": "ACTION", "event": "A turn.", "importance": "critical", "requires_reaction": True}]}],
    })
    authored["scenes"][0]["beats"][-1]["type"] = "ACTION"
    ir = build_script_ir(authored, book_id=1, episode=1)
    report = run_script_creative_quality_gate(ir, production=True)
    assert report["status"] == "CREATIVE_QUALITY_BLOCKED"
    assert any(item["code"] == "CRITICAL_BEAT_MISSING" for item in report["hard_errors"])


def test_readiness_metadata_cannot_be_used_to_claim_source_authority():
    from core.script_ir_authority import build_authority_envelope_v2, validate_authority_envelope_v2
    from core.source_authority import SourceLineageContext
    lineage = SourceLineageContext(
        origin_source_kind="BOOK_CHAPTER", origin_source_package_id="book:fixture", origin_source_version_id="chapter:fixture:v1", origin_source_locator={"book_id": 90, "chapter_seq": 1}, origin_source_raw_hash="a" * 64, structuring_response_fingerprint="b" * 64, reconciliation_policy_version="r", reconciliation_fingerprint="c" * 64, migration_fingerprint="d" * 64, canonical_projection_version="source_grounded_script_payload_v3_1", canonical_script_payload_fingerprint="e" * 64,
    )
    envelope = build_authority_envelope_v2(book_id=90, episode=1, script_ir_payload={"schema_version": "script_ir_v1", "scenes": []}, lineage=lineage, fact_snapshot={"id": 1, "revision": 1, "payload_hash": "f" * 64}, source_evidence_index={"evidence_index_fingerprint": "g" * 64}, requirement_set={"fingerprint": "h" * 64}, coverage_result={"fingerprint": "i" * 64}, source_anchor_bindings={}, canonical_script_content_hash="j" * 64)
    envelope["creative_readiness_state"] = "READY"
    report = validate_authority_envelope_v2(envelope, payload={"schema_version": "script_ir_v1", "scenes": []}, lineage=lineage, source_evidence_index={"evidence_index_fingerprint": "g" * 64}, canonical_script_content_hash="j" * 64, origin_raw_hash="a" * 64)
    assert report["status"] == "FAIL"
    assert any(item["code"] in {"SCRIPT_IR_AUTHORITY_ENVELOPE_TAMPERED", "CREATIVE_READINESS_CHANGED"} for item in report["errors"])
