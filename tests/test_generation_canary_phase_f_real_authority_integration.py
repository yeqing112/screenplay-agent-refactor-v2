from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRACE = ROOT / "artifacts" / "e2e-production-pilot" / "episode_01_phase_f_real_authority_fake_provider_trace.json"


def test_real_authority_fake_provider_trace_is_real_sqlite_and_upstream_immutable():
    trace = json.loads(TRACE.read_text(encoding="utf-8"))
    assert trace["database"] == "REAL_SQLITE"
    assert trace["alembic_head"] == "y8h9i0j1k2l3"
    assert trace["real_persisted_prompt_ir"] is True
    assert trace["resolver_monkeypatched"] is False
    assert trace["asset_resolver_monkeypatched"] is False
    assert trace["storyboard_resolver_monkeypatched"] is False
    assert trace["fake_provider_calls"] == 1
    assert trace["external_provider_calls"] == 0
    assert trace["authority_mutations"] == 0
    assert trace["before_authorities"] == trace["after_authorities"]
    identities = trace["before_authorities"]["identities"]
    for key in ("script_ir", "treatment", "blocking", "shot_plan", "storyboard_shot", "prompt_ir", "prompt_ir_pointer"):
        assert identities[key], key
    assert trace["phase_f_records_before"] == {"generation_execution_records": 0, "media_candidate_records": 0}
    assert trace["phase_f_records_after"] == {"generation_execution_records": 1, "media_candidate_records": 1}
    assert trace["execution"]["status"] == "SUCCEEDED"
    assert trace["candidate"]["width"] == 1
    assert trace["candidate"]["height"] == 1
    assert trace["candidate"]["checksum"]
