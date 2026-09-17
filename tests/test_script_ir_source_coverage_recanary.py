from scripts.run_director_quality_v3_script_ir_source_coverage_recanary import run


def test_recanary_moves_production_only_gaps_to_backlog_and_keeps_source_gate_empty():
    manifest = {"items": [
        {"fact_key": "character|A|visual_identity|global", "semantic_type": "character", "entity": "A", "required": True},
        {"fact_key": "character|A|current_state|global", "semantic_type": "character", "entity": "A", "required": True},
        {"fact_key": "scene|S|geometry|global", "semantic_type": "scene", "entity": "S", "required": True},
        {"fact_key": "prop|P|state|global", "semantic_type": "prop", "entity": "P", "required": True},
    ]}
    result = run(manifest=manifest, snapshot_payload={"fact_snapshot": {"records": []}})
    assert result["status"] == "SCRIPT_IR_SOURCE_COVERAGE_SUFFICIENT"
    assert result["script_ir_required_source_facts"]["total"] == 0
    assert result["source_fact_only_missing_manifest"]["items"] == []
    assert result["downstream_requirement_backlog_count"] == 4
    assert result["provider_calls"] == 0


def test_recanary_keeps_explicit_source_fact_missing_as_script_ir_blocker():
    manifest = {"items": [{"fact_key": "character|A|gender|global", "semantic_type": "character", "entity": "A", "required": True, "source_required": True}]}
    result = run(manifest=manifest, snapshot_payload={"fact_snapshot": {"records": []}})
    assert result["status"] == "SCRIPT_IR_SOURCE_COVERAGE_INSUFFICIENT"
    assert result["script_ir_required_source_facts"]["missing"] == 1
    assert result["source_fact_only_missing_manifest"]["count"] == 1
    assert result["downstream_requirement_backlog_count"] == 0
