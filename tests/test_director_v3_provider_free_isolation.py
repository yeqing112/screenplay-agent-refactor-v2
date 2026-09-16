from __future__ import annotations

import json


def test_model_registry_resolves_non_secret_env_snapshot_without_kv(monkeypatch):
    import api.model_registry as registry

    profile = {
        "id": "audit-mimo",
        "name": "MiMo audit",
        "capability": "llm",
        "provider": "openai-compatible",
        "base_url": "https://api.xiaomimimo.com/v1",
        "model_name": "mimo-v2.5",
        "default_params": {"thinking": {"type": "disabled"}},
        "enabled": True,
    }
    monkeypatch.setattr(registry, "get_kv", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("kv unavailable")))
    import config
    monkeypatch.setattr(config, "MODEL_REGISTRY_PROFILES_JSON", json.dumps([profile]))
    monkeypatch.setattr(config, "MODEL_REGISTRY_DEFAULTS_JSON", json.dumps({"llm": "audit-mimo"}))

    resolved = registry.get_default_profile("llm")
    assert resolved is not None
    assert resolved["model_name"] == "mimo-v2.5"
    assert resolved["provider"] == "openai-compatible"
    assert not resolved.get("api_key")


def test_phase_a_read_only_option_is_exposed():
    from scripts import run_director_quality_v3_evaluation_upstream_phase_a as runner

    # argparse acceptance is enough here; the normal provider-free path still
    # blocks on the intentionally dirty development tree and performs no call.
    assert runner.main(["--read-only"]) in {0, 2}
