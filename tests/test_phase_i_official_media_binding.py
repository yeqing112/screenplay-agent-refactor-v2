"""Phase I OfficialMedia binding and drift evidence."""
from __future__ import annotations

import json

from scripts.run_phase_i_official_media_binding_pilot import run


def test_phase_i_fixture_pilot_resolves_all_shots_and_blocks_real_gate(tmp_path):
    audit = run(tmp_path)
    matrix = json.loads((tmp_path / "phase_i_visual_truth_matrix.json").read_text(encoding="utf-8"))
    assert audit["status"] == "PHASE_I_FULL_E2E_GATE_BLOCKED"
    assert audit["official_media_resolved"] == 15
    assert audit["asset_binding_resolved"] == 15
    assert audit["prompt_ir_resolved"] == 15
    assert audit["generation_execution_resolved"] == 15
    assert audit["legacy_chain_unchanged"] is True
    assert audit["provider_calls"] == audit["image_calls"] == audit["video_calls"] == 0
    assert audit["dual_media_probe"]["image_official_after_video_pointer"] == "PASS"
    assert audit["dual_media_probe"]["video_pointer_created"]["target_media"] == "VIDEO"
    assert matrix["shots_passed"] == 15
    assert {item["error_code"] for item in audit["drift_tests"].values()} == {"OFFICIAL_MEDIA_BINDING_INVALID"}
    assert {item["status_code"] for item in audit["drift_tests"].values()} == {409}
