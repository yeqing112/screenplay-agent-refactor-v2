from __future__ import annotations

import json

import pytest

from core.director_v3_runtime_authorization import authorization_gate, load_runtime_authorization


def _authorization(base: str = "a" * 40) -> dict:
    return {
        "schema_version": "director_v3_phase_a_runtime_authorization_v1",
        "authorization_id": "auth-test-1",
        "scope": "DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A",
        "source_package_id": "SRC79f12d1b7f5eb828",
        "source_version_id": "SRC79f12d1b7f5eb828:V01:d001bab5cc82",
        "authorized_execution_base": base,
        "allowed_stages": ["FACT_EXTRACTION", "SCRIPT_IR"],
        "max_provider_calls": 2,
        "retries": 0,
        "issued_from_external_authorization": True,
    }


def test_runtime_authorization_rejects_wrong_source_and_base(tmp_path):
    path = tmp_path / "authorization.json"
    path.write_text(json.dumps(_authorization()), encoding="utf-8")
    auth = load_runtime_authorization(path)
    ok, reasons = authorization_gate(
        auth,
        head="b" * 40,
        remote_head="b" * 40,
        dirty=[],
        source_package_id="wrong",
        source_version_id=auth["source_version_id"],
        predicted_calls=2,
    )
    assert not ok
    assert "RUNTIME_AUTHORIZATION_EXECUTION_BASE_MISMATCH" in reasons
    assert "RUNTIME_AUTHORIZATION_SOURCE_PACKAGE_MISMATCH" in reasons


def test_runtime_authorization_rejects_budget_above_two(tmp_path):
    payload = _authorization()
    payload["max_provider_calls"] = 3
    path = tmp_path / "authorization.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="call_budget_must_be_two"):
        load_runtime_authorization(path)


def test_dispatch_attempt_is_counted_before_transport_failure(tmp_path, monkeypatch):
    from scripts import run_director_quality_v3_evaluation_upstream_phase_a as runner
    import core.evaluation_upstream_phase_a as phase_a
    import core.llm as llm

    captured = {}

    def fake_run_with_provider_calls(*, source, provider_config, call_provider):
        try:
            call_provider({"task": "fact_extraction", "payload": {"x": 1}})
        except TimeoutError:
            captured["raised"] = True
        return {"status": "FAILED", "provider_calls": 0}

    monkeypatch.setattr(phase_a, "run_with_provider_calls", fake_run_with_provider_calls)
    monkeypatch.setattr(llm, "call_llm", lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("timeout")))
    eval_root = tmp_path / "eval"
    result = runner._execute_authorized_phase_a(
        source={"raw_hash": "h", "provenance": {}},
        provider={"provider": "openai-compatible", "model": "mimo-v2.5"},
        eval_root=eval_root,
        authorization=_authorization(),
    )
    assert captured["raised"] is True
    assert result["attempted_provider_calls"] == 1
    assert result["provider_exposure"] == "EXPOSED"
    ledger = json.loads((eval_root / "dispatch-ledger.json").read_text(encoding="utf-8"))
    assert ledger["entries"][0]["status"] == "TRANSPORT_FAILED"
    assert ledger["entries"][0]["response_received"] is False
