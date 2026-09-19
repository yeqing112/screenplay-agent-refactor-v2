"""Phase A: Script Creative Quality Gate tests."""
import json

import pytest
from fastapi.testclient import TestClient

from api.server import app
from core.script_creative_quality import (
    detect_negative_fixture_issues,
    run_script_creative_quality_gate,
)
from core.script_ir import build_script_ir
from core.script_renderer import render_reader_script, render_technical_script_view
from models import Book, Script, ScriptIRVersion, Session, init_db


def _fixed_ir():
    payload = {
        "title": "测试集",
        "episode_objective": "角色主动试探并逼近真相。",
        "characters": ["甲", "乙"],
        "scenes": [
            {
                "scene_id": "SC01",
                "name": "门厅",
                "location_name": "门厅",
                "time_of_day": "日",
                "participants": ["甲", "乙"],
                "state_in": {"甲": "平静"},
                "state_out": {"甲": "警惕"},
                "beats": [
                    {"beat_id": "SC01-B01", "type": "REVEAL", "beat_type": "REVEAL", "event": "甲看见一把红伞。", "requires_reaction": True, "importance": "critical"},
                    {"beat_id": "SC01-B02", "type": "DECISION", "beat_type": "DECISION", "event": "甲决定留下试探。", "requires_reaction": True, "importance": "critical"},
                    {"beat_id": "SC01-B03", "type": "HOOK", "beat_type": "HOOK", "event": "乙的手停在半空。", "requires_reaction": True, "importance": "critical"},
                ],
                "dialogues": [
                    {"dialogue_id": "D001", "speaker": "乙", "text": "我们一直在一起，你忘了？", "assertion_mode": "DECEPTION", "contradicts_fact_refs": ["SC01-B01"], "audience_should_notice": True},
                ],
                "actions": ["甲看见一把红伞。"],
            },
        ],
        "scene_transitions": [],
    }
    return build_script_ir(payload, book_id=1, episode=1)


def _broken_ir():
    payload = {
        "title": "负面样例",
        "scenes": [
            {
                "scene_id": "SC01", "name": "车站", "time_of_day": "日",
                "participants": ["甲"],
                "beats": [
                    {"beat_id": "SC01-B01", "type": "ACTION", "event": "镜头推近甲的脸。"},
                    {"beat_id": "SC01-B02", "type": "ACTION", "event": "【视觉证明1】甲看向红伞。"},
                ],
                "dialogues": [{"dialogue_id": "D001", "speaker": "乙", "text": "我们一直在一起。", "contradicts_fact_refs": ["SC01-B01"]}],
                "actions": ["镜头推近"],
            },
            {"scene_id": "SC02", "name": "公寓", "time_of_day": "夜", "participants": ["甲"], "beats": [{"beat_id": "SC02-B01", "type": "ACTION", "event": "切到公寓。"}]},
        ],
        "scene_transitions": [],
    }
    return build_script_ir(payload, book_id=1, episode=1)


def test_fixed_ir_passes_gate():
    report = run_script_creative_quality_gate(_fixed_ir())
    assert report["qualified"] is True
    assert report["status"] == "PRODUCTION_QUALIFIED"


def test_broken_ir_fails_gate_with_expected_signals():
    result = detect_negative_fixture_issues(_broken_ir())
    assert result["script_gate_status"] == "CREATIVE_QUALITY_BLOCKED"
    assert "SCENE_TRANSITION_UNRESOLVED" in result["detected_script_issues"]
    assert "CHARACTER_STATEMENT_CONTINUITY_CONFLICT" in result["detected_script_issues"]
    assert "CRITICAL_BEAT_MISSING" in result["detected_script_issues"]
    assert result["leaked_camera_patterns"]
    assert result["leaked_internal_labels"]


def test_reader_script_has_no_camera_or_internal_labels():
    reader = render_reader_script(_fixed_ir())
    assert "镜头" not in reader
    assert "beat_id" not in reader
    assert "【视觉证明" not in reader
    assert "甲看见一把红伞。" in reader


def test_technical_view_contains_beat_and_fact_refs():
    tech = render_technical_script_view(_fixed_ir())
    assert "SC01-B01" in tech
    assert "DECEPTION" in tech
    assert "contradicts=" in tech


def test_creative_quality_endpoint_is_readonly_and_blocks_broken():
    init_db()
    client = TestClient(app)
    with Session() as session:
        book = Book(title="cq-test", filename="cq.txt", status="imported")
        session.add(book); session.flush()
        session.add(Script(book_id=book.id, episode=1, content=json.dumps(_broken_ir(), ensure_ascii=False)))
        session.commit(); book_id = book.id
    try:
        # Read-only endpoint evaluates a broken payload and reports blocked
        resp = client.post(f"/api/books/{book_id}/episodes/1/script-ir/creative-quality", json={"payload": _broken_ir()})
        assert resp.status_code == 200
        body = resp.json()
        assert body["mutated"] is False
        assert body["creative_quality"]["status"] == "CREATIVE_QUALITY_BLOCKED"
        # Confirm with enforceCreativeQuality blocks a broken candidate
        draft = client.post(f"/api/books/{book_id}/episodes/1/script-ir/build", json={"persist": True}).json()
        blocked = client.post(f"/api/books/{book_id}/episodes/1/script-ir/confirm", json={"versionId": draft["persisted_draft_id"], "confirmed": True, "enforceCreativeQuality": True})
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "SCRIPT_CREATIVE_QUALITY_BLOCKED"
    finally:
        with Session() as session:
            session.query(ScriptIRVersion).filter_by(book_id=book_id).delete()
            session.query(Script).filter_by(book_id=book_id).delete()
            session.query(Book).filter_by(id=book_id).delete(); session.commit()
