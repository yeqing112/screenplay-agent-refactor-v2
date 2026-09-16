from core.director_authority import authority_completeness_gate, normalize_structured_preserve_constraints, provider_readiness_gate, strategy_authority, valid_scene_refs
from core.director_contract_ssot import build_provider_contract, schema_fingerprint, schema_parity_report, skeleton_spec, spine_spec


def _scene():
    return {"scene_id": "fresh-1", "beats": [{"beat_id": "1"}, {"beat_id": "2"}], "participants": [{"character_id": "19"}], "props": [{"prop_id": "archive_bag"}], "locations": [{"location_id": "darkroom"}]}


def _events():
    return {"events": [{"event_key": "EV01", "beat_ref": "beat:1"}]}


def _constraint(**extra):
    return {"kind": "CHARACTER_ACTION", "description": "手部动作", "subject_refs": ["character:19"], "object_refs": ["prop:archive_bag"], "beat_refs": ["beat:1"], "event_refs": ["EV01"], "source_refs": ["beat:1"], "provenance": {"authority": "SCRIPT_IR", "source_type": "BEAT"}, **extra}


def test_preserve_constraint_requires_authoritative_anchor():
    result = normalize_structured_preserve_constraints([{k: v for k, v in _constraint().items() if k not in {"beat_refs", "event_refs", "source_refs"}}], scene=_scene(), semantic_events=_events())
    assert result["status"] == "FAIL"
    assert any(error["code"] == "PRESERVE_AUTHORITY_UNRESOLVED" for error in result["errors"])


def test_preserve_constraint_valid_beat_ref_passes():
    result = normalize_structured_preserve_constraints([_constraint()], scene=_scene(), semantic_events=_events())
    assert result["status"] == "PASS"
    assert result["constraints"][0]["constraint_id"] == "MP01"


def test_preserve_constraint_unknown_refs_and_ambiguous_binding_fail():
    result = normalize_structured_preserve_constraints([_constraint(beat_refs=["beat:999"], binding_candidates=["beat:1", "beat:2"])], scene=_scene(), semantic_events=_events())
    codes = {error["code"] for error in result["errors"]}
    assert "PRESERVE_CONSTRAINT_UNKNOWN_BEAT" in codes
    assert "PRESERVE_BINDING_AMBIGUOUS" in codes


def test_legacy_string_only_preserve_is_incomplete_and_blocks_provider():
    authority = strategy_authority({"must_preserve": ["legacy prose"]}, scene=_scene(), identity_projection={"records": [{"character_id": "19"}]}, semantic_events=_events())
    assert authority["status"] == "STRATEGY_AUTHORITY_INCOMPLETE"
    gate = provider_readiness_gate(authority=authority, schema_parity=schema_parity_report())
    assert gate["provider_callable"] is False


def test_complete_authority_reaches_readiness_without_provider_call():
    authority = strategy_authority({"structured_preserve_constraints": [_constraint()]}, scene=_scene(), identity_projection={"records": [{"character_id": "19"}]}, semantic_events=_events())
    gate = provider_readiness_gate(authority=authority, schema_parity=schema_parity_report())
    assert authority["status"] == "PASS"
    assert gate["status"] == "PASS"
    assert gate["provider_callable"] is True


def test_spine_and_skeleton_specs_have_provider_validator_parity():
    report = schema_parity_report()
    assert report["status"] == "PASS"
    assert report["spine"]["provider_segment_required_fields"] == report["spine"]["validator_segment_required_fields"]
    assert report["skeleton"]["provider_role_enum"] == report["skeleton"]["validator_role_enum"]
    assert report["duplicate_role_enum_authority"] is False
    assert build_provider_contract("spine")["schema_fingerprint"] == schema_fingerprint(spine_spec())
    assert build_provider_contract("skeleton")["schema_fingerprint"] == schema_fingerprint(skeleton_spec())


def test_schema_parity_negative_field_drift_is_detectable():
    report = schema_parity_report()
    report["spine"]["provider_segment_required_fields"] = ["phase_ids"]
    assert report["spine"]["provider_segment_required_fields"] != report["spine"]["validator_segment_required_fields"]


def test_authority_completeness_gate_has_explicit_failure_status():
    result = authority_completeness_gate(strategy={"must_preserve": ["legacy prose"]}, scene=_scene(), identity_projection={"records": [{"character_id": "19"}]}, semantic_events=_events())
    assert result["status"] == "AUTHORITY_COMPLETENESS_FAILED"
    assert result["provider_callable"] is False


def test_canonical_prefixed_beat_ids_are_preserved_in_authority_refs():
    refs = valid_scene_refs({"beats": [{"beat_id": "B12"}]})["beat"]
    assert "beat:B12" in refs
    assert "beat:12" in refs  # compatibility alias, never a replacement
    result = normalize_structured_preserve_constraints(
        [{"kind": "VISUAL_EVENT", "description": "event", "beat_refs": ["beat:B12"], "provenance": {"source": "test"}}],
        scene={"scene_id": "s", "beats": [{"beat_id": "B12"}]},
    )
    assert result["status"] == "PASS"
