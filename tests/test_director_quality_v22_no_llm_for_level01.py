import core.llm as llm_module

from scripts.run_director_quality_v2_1_mimo_pilot_authorized import run_authorized_pilot


def test_equivalent_provider_patch_never_enters_repair_stage(monkeypatch):
    calls = []

    def fake_call(user_prompt, *, system=None, model_profile=None, **kwargs):
        calls.append(kwargs.get("audit_extra", {}).get("stage"))
        return {
            "schema_version": "director_creative_patch_v1",
            "patches": [
                {
                    "plan_shot_id": "S01",
                    "patch": [{"op": "replace", "path": "/shots/*/camera/shot_size", "value": "close-up"}],
                }
            ],
            "auxiliary_shot_proposals": [],
        }

    monkeypatch.setattr(llm_module, "call_llm_json", fake_call)
    result = run_authorized_pilot(
        profile={
            "id": "offline-v22-test",
            "provider": "openai-compatible",
            "model_name": "mimo-v2.5",
            "capability": "llm",
            "enabled": True,
            "api_key": "offline-only",
            "base_url": "https://offline.invalid/v1",
        },
        scene_limit=12,
    )
    assert len(calls) == 12
    assert set(calls) == {"director_patch_planner"}
    assert "director_patch_repair" not in result["telemetry"]["stages"]
