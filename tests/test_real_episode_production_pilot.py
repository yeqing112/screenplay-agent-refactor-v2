"""Safety contracts for the real Episode pilot runner."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scripts.run_real_episode_production_pilot as pilot
from models import GenerationExecutionRecord, TaskRun
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "real-episode-pilot-safety.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    return engine, sessionmaker(bind=engine)()


def test_missing_real_gates_are_blocked_without_provider_calls(monkeypatch):
    for name in ("PHASE_F_PROVIDER_CANARY_REAL", "MINIMAX_H3_GRAY_REAL", "MINIMAX_H3_GRAY_CONFIRM", "MINIMAX_H3_GRAY_WHITELIST"):
        monkeypatch.delenv(name, raising=False)
    result = pilot._gate_snapshot(["77:1:101", "77:1:102"])
    assert result["image_canary_enabled"] is False
    assert result["video_gray_enabled"] is False
    assert result["video_confirmation_matches"] is False
    assert result["exact_shots_whitelisted"] is False


def test_exact_shot_allowlist_is_required(monkeypatch):
    monkeypatch.setenv("PHASE_F_PROVIDER_CANARY_REAL", "1")
    monkeypatch.setenv("MINIMAX_H3_GRAY_REAL", "1")
    monkeypatch.setenv("MINIMAX_H3_GRAY_CONFIRM", pilot.MINIMAX_CONFIRMATION_TOKEN)
    monkeypatch.setenv("MINIMAX_H3_GRAY_WHITELIST", "77:1:101,77:1:102")
    assert pilot._gate_snapshot(["77:1:101", "77:1:102"])["exact_shots_whitelisted"] is True
    assert pilot._gate_snapshot(["77:1:101", "77:1:103"])["exact_shots_whitelisted"] is False


def test_profile_contract_rejects_wrong_provider_and_transport():
    profile = {"id": "wrong", "provider": "prototype-task-adapter", "capability": "image", "enabled": True, "transport_binding_id": "prototype-task-adapter.image.v1", "credential_configured": True}
    ok, reason = pilot._profile_ready(profile, provider=pilot.IMAGE_PROVIDER, capability="image", transport=pilot.IMAGE_TRANSPORT)
    assert ok is False
    assert reason == "provider_mismatch"


def test_missing_episode_is_blocked_and_writes_no_production_rows(tmp_path: Path, monkeypatch):
    engine, session = _session(tmp_path)
    try:
        for name in ("PHASE_F_PROVIDER_CANARY_REAL", "MINIMAX_H3_GRAY_REAL", "MINIMAX_H3_GRAY_CONFIRM", "MINIMAX_H3_GRAY_WHITELIST"):
            monkeypatch.delenv(name, raising=False)
        before = (session.query(GenerationExecutionRecord).count(), session.query(TaskRun).count())
        result = pilot.build_preflight(session, episode_id=999999, shot_ids=[101, 102], image_profile_id="local-image-mw4y52", video_profile_id="local-video-7deneh")
        after = (session.query(GenerationExecutionRecord).count(), session.query(TaskRun).count())
        assert result["status"] == "BLOCKED"
        assert result["production_writes"] == 0
        assert before == after == (0, 0)
    finally:
        session.close()
        engine.dispose()


def test_real_execution_requires_explicit_consent(monkeypatch):
    parser = pilot._parser()
    args = parser.parse_args(["--episode-id", "1", "--shot-id", "10", "--shot-id", "11", "--execute"])
    assert args.confirm_real_pilot == ""
    assert pilot.CONSENT_TOKEN not in args.confirm_real_pilot


def test_budget_exhaustion_blocks_before_provider_call(tmp_path: Path, monkeypatch):
    engine, session = _session(tmp_path)
    try:
        monkeypatch.setattr(pilot, "_next_operation", lambda *_args, **_kwargs: {"kind": "IMAGE", "shot_id": 1, "keyframe_id": 1, "profile_id": "local-image-mw4y52"})
        provider_called = False

        def _unexpected_provider(*args, **kwargs):
            nonlocal provider_called
            provider_called = True
            raise AssertionError("provider must not be called after budget exhaustion")

        monkeypatch.setattr(pilot, "produce_keyframe_image", _unexpected_provider)
        result = pilot.execute_one(session, shot_ids=[1, 2], image_profile_id="local-image-mw4y52", video_profile_id="local-video-7deneh", allowed_image_calls=0, allowed_video_calls=2)
        assert result == {"status": "BLOCKED_BUDGET", "blocker": "image_budget_exhausted", "provider_calls": 0}
        assert provider_called is False
    finally:
        session.close()
        engine.dispose()


def test_blocker_serialization_does_not_leak_sql_or_paths():
    message = pilot._short_exception(RuntimeError("secret SQL text /tmp/private"))
    assert message == "RuntimeError"
    assert "/tmp/private" not in message
