"""Provider-free contracts for the Episode 13 pilot source fixture."""

from types import SimpleNamespace

from scripts.prepare_real_episode_production_pilot_source import (
    PILOT_MARKER,
    SHOT_IDS,
    _marker,
    _pilot_context,
)


def test_pilot_context_is_explicit_and_preserves_upstream_hashes():
    ir = SimpleNamespace(id=2, revision=2, payload_json='{"scenes": []}', payload_hash="sha256:ir-source")
    facts = SimpleNamespace(id=1, revision=1, payload_hash="sha256:fact-source")
    episode, script, scene = _pilot_context(ir, facts)

    assert script["production_eligible"] is True
    assert script["timeline_origin"] == "EXPLICIT_PILOT_AUTHORING_DECISION"
    assert [item["shot_id"] for item in script["scenes"][0]["shots"]] == list(SHOT_IDS)
    assert [item["sequence"] for item in scene["beats"]] == [1, 2]
    assert episode["source_script_ir_hash"] == "sha256:ir-source"
    assert episode["source_fact_snapshot_hash"] == "sha256:fact-source"
    assert script["source_lineage"]["source_fact_mutated"] is False
    assert script["source_lineage"]["script_ir_mutated"] is False


def test_pilot_marker_is_strict():
    assert _marker({"pilot_marker": PILOT_MARKER}) is True
    assert _marker({"pilot_marker": "other"}) is False
    assert _marker("not-json") is False
