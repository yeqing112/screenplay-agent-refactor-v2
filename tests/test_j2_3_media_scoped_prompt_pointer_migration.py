"""Provider-free J2.3 pointer-scope migration contract tests."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from core.prompt_ir_phase_e import _prompt_ir_payload_basis, fingerprint


ROOT = Path(__file__).resolve().parents[1]
LEGACY_HEAD = "a1b2c3d4e5f6"
J23_HEAD = "b2c3d4e5f6g7"


def _config(db: Path) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    return cfg


def _engine_at(db: Path, revision: str) -> None:
    command.upgrade(_config(db), revision)


def _payload(target: str | None = "IMAGE", *, omit_policy: bool = False) -> tuple[str, str]:
    payload = {"schema_version": "prompt_ir_v2", "storyboard_shot_id": 7, "plan_shot_id": "P7", "prompt": {"text": "fixture"}}
    if not omit_policy:
        payload["generation_policy"] = {"mode": "TEXT_TO_IMAGE", "target_media": target}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return raw, fingerprint(_prompt_ir_payload_basis(payload))


def _insert_legacy(db: Path, *, target: str | None = "IMAGE", omit_policy: bool = False, pointer_id: int = 1, book: int = 1, episode: int = 1, shot: int = 7, version_book: int | None = None, version_episode: int | None = None, version_shot: int | None = None, pointer_hash: str | None = None) -> dict[str, str]:
    raw, payload_hash = _payload(target, omit_policy=omit_policy)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO prompt_ir_versions
            (id, book_id, episode, scene_id, storyboard_shot_id, materialization_set_id, plan_shot_id,
             schema_version, payload_json, payload_hash, compiler_version, compiler_policy_version,
             retention_policy_version, authority_envelope_json, qualification_state, asset_reference_state,
             model_generation_ready, stale_status, stale_reasons)
            VALUES (11, :book, :episode, 'S1', :shot, 1, 'P7', 'prompt_ir_v2', :payload, :hash,
                    'compiler', 'policy', 'retention', '{}', 'PROMPT_IR_QUALIFIED', 'READY', 'true', 'FRESH', '[]')
        """), {"book": version_book if version_book is not None else book, "episode": version_episode if version_episode is not None else episode, "shot": version_shot if version_shot is not None else shot, "payload": raw, "hash": payload_hash})
        conn.execute(text("""
            INSERT INTO prompt_ir_pointers
            (id, book_id, episode, storyboard_shot_id, prompt_ir_version_id, payload_hash, qualification_state)
            VALUES (:id, :book, :episode, :shot, 11, :hash, 'PROMPT_IR_QUALIFIED')
        """), {"id": pointer_id, "book": book, "episode": episode, "shot": shot, "hash": pointer_hash if pointer_hash is not None else payload_hash})
    engine.dispose()
    return {"payload": raw, "payload_hash": payload_hash}


def test_fresh_upgrade_has_media_scope_schema_and_empty_rows(tmp_path):
    db = tmp_path / "fresh.sqlite"
    _engine_at(db, "head")
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    inspector = inspect(engine)
    assert engine.connect().execute(text("select version_num from alembic_version")).scalar() == J23_HEAD
    assert "target_media" in {item["name"] for item in inspector.get_columns("prompt_ir_pointers")}
    assert {item["name"] for item in inspector.get_unique_constraints("prompt_ir_pointers")} == {"uq_prompt_ir_pointer_media_scope"}
    assert engine.connect().execute(text("select count(*) from prompt_ir_pointers")).scalar() == 0
    engine.dispose()


@pytest.mark.parametrize("target", ["IMAGE", "VIDEO"])
def test_legacy_pointer_backfills_exact_payload_media_and_preserves_version(tmp_path, target):
    db = tmp_path / f"legacy-{target}.sqlite"
    _engine_at(db, LEGACY_HEAD)
    original = _insert_legacy(db, target=target)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    before = engine.connect().execute(text("select id, book_id, episode, storyboard_shot_id, prompt_ir_version_id, payload_hash, qualification_state from prompt_ir_pointers")).one()
    version_before = engine.connect().execute(text("select payload_json, payload_hash, schema_version, compiler_version, authority_envelope_json from prompt_ir_versions where id=11")).one()
    engine.dispose()
    command.upgrade(_config(db), "head")
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    row = engine.connect().execute(text("select id, book_id, episode, storyboard_shot_id, target_media, prompt_ir_version_id, payload_hash, qualification_state from prompt_ir_pointers")).one()
    version_after = engine.connect().execute(text("select payload_json, payload_hash, schema_version, compiler_version, authority_envelope_json from prompt_ir_versions where id=11")).one()
    assert tuple(row[:4]) == tuple(before[:4])
    assert row[4] == target
    assert tuple(row[5:]) == tuple(before[4:])
    assert tuple(version_after) == tuple(version_before)
    assert json.loads(version_after[0]) == json.loads(original["payload"])
    engine.dispose()


@pytest.mark.parametrize("target", [None, "image", "AUTO", ""])
def test_missing_or_noncanonical_media_blocks_before_schema_mutation(tmp_path, target):
    db = tmp_path / "blocked.sqlite"
    _engine_at(db, LEGACY_HEAD)
    _insert_legacy(db, target=target, omit_policy=target is None)
    with pytest.raises(RuntimeError, match="PROMPT_IR_POINTER_MIGRATION_BLOCKED"):
        command.upgrade(_config(db), "head")
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    assert "target_media" not in {item["name"] for item in inspect(engine).get_columns("prompt_ir_pointers")}
    assert engine.connect().execute(text("select count(*) from prompt_ir_pointers")).scalar() == 1
    engine.dispose()


@pytest.mark.parametrize("kwargs", [
    {"version_book": 2}, {"version_episode": 2}, {"version_shot": 8}, {"pointer_hash": "wrong"},
])
def test_pointer_version_identity_or_hash_mismatch_blocks(tmp_path, kwargs):
    db = tmp_path / "mismatch.sqlite"
    _engine_at(db, LEGACY_HEAD)
    _insert_legacy(db, **kwargs)
    with pytest.raises(RuntimeError, match="PROMPT_IR_POINTER_MIGRATION_BLOCKED"):
        command.upgrade(_config(db), "head")
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    assert "target_media" not in {item["name"] for item in inspect(engine).get_columns("prompt_ir_pointers")}
    engine.dispose()


def test_invalid_payload_hash_blocks_even_when_pointer_and_version_hash_match(tmp_path):
    db = tmp_path / "payload-hash.sqlite"
    _engine_at(db, LEGACY_HEAD)
    raw, valid_hash = _payload("IMAGE")
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as conn:
        conn.execute(text("insert into prompt_ir_versions (id, book_id, episode, scene_id, storyboard_shot_id, materialization_set_id, plan_shot_id, schema_version, payload_json, payload_hash, compiler_version, compiler_policy_version, retention_policy_version, authority_envelope_json, qualification_state, asset_reference_state, model_generation_ready, stale_status, stale_reasons) values (11,1,1,'S1',7,1,'P7','prompt_ir_v2',:payload,:hash,'c','p','r','{}','PROMPT_IR_QUALIFIED','READY','true','FRESH','[]')"), {"payload": raw.replace("fixture", "tampered"), "hash": valid_hash})
        conn.execute(text("insert into prompt_ir_pointers (id, book_id, episode, storyboard_shot_id, prompt_ir_version_id, payload_hash, qualification_state) values (1,1,1,7,11,:hash,'PROMPT_IR_QUALIFIED')"), {"hash": valid_hash})
    engine.dispose()
    with pytest.raises(RuntimeError, match="PROMPT_IR_POINTER_MIGRATION_BLOCKED"):
        command.upgrade(_config(db), "head")


def test_malformed_payload_json_blocks_before_schema_mutation(tmp_path):
    db = tmp_path / "malformed-payload.sqlite"
    _engine_at(db, LEGACY_HEAD)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as conn:
        values = {"payload": "{not-json", "hash": "same-hash"}
        conn.execute(text("insert into prompt_ir_versions (id, book_id, episode, scene_id, storyboard_shot_id, materialization_set_id, plan_shot_id, schema_version, payload_json, payload_hash, compiler_version, compiler_policy_version, retention_policy_version, authority_envelope_json, qualification_state, asset_reference_state, model_generation_ready, stale_status, stale_reasons) values (11,1,1,'S1',7,1,'P7','prompt_ir_v2',:payload,:hash,'c','p','r','{}','PROMPT_IR_QUALIFIED','READY','true','FRESH','[]')"), values)
        conn.execute(text("insert into prompt_ir_pointers (id, book_id, episode, storyboard_shot_id, prompt_ir_version_id, payload_hash, qualification_state) values (1,1,1,7,11,:hash,'PROMPT_IR_QUALIFIED')"), {"hash": values["hash"]})
    engine.dispose()
    with pytest.raises(RuntimeError, match="PROMPT_IR_POINTER_MIGRATION_BLOCKED"):
        command.upgrade(_config(db), "head")


def test_single_scope_downgrade_and_upgrade_round_trip(tmp_path):
    db = tmp_path / "downgrade-single.sqlite"
    _engine_at(db, LEGACY_HEAD)
    _insert_legacy(db, target="IMAGE")
    command.upgrade(_config(db), "head")
    command.downgrade(_config(db), LEGACY_HEAD)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    assert "target_media" not in {item["name"] for item in inspect(engine).get_columns("prompt_ir_pointers")}
    assert engine.connect().execute(text("select count(*) from prompt_ir_pointers")).scalar() == 1
    engine.dispose()
    command.upgrade(_config(db), "head")
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    assert engine.connect().execute(text("select target_media from prompt_ir_pointers")).scalar() == "IMAGE"
    engine.dispose()


def test_dual_scope_downgrade_fails_before_schema_or_row_mutation(tmp_path):
    db = tmp_path / "downgrade-dual.sqlite"
    _engine_at(db, LEGACY_HEAD)
    _insert_legacy(db, target="IMAGE")
    command.upgrade(_config(db), "head")
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as conn:
        conn.execute(text("insert into prompt_ir_pointers (id, book_id, episode, storyboard_shot_id, target_media, prompt_ir_version_id, payload_hash, qualification_state) values (2,1,1,7,'VIDEO',11,(select payload_hash from prompt_ir_versions where id=11),'PROMPT_IR_QUALIFIED')"))
    engine.dispose()
    with pytest.raises(RuntimeError, match="PROMPT_IR_POINTER_DOWNGRADE_CARDINALITY_CONFLICT"):
        command.downgrade(_config(db), LEGACY_HEAD)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    assert "target_media" in {item["name"] for item in inspect(engine).get_columns("prompt_ir_pointers")}
    assert engine.connect().execute(text("select count(*) from prompt_ir_pointers")).scalar() == 2
    engine.dispose()


def test_same_scope_unique_conflict_and_cross_scope_retention(tmp_path):
    db = tmp_path / "scope-unique.sqlite"
    _engine_at(db, "head")
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as conn:
        for row_id, media in ((1, "IMAGE"), (2, "VIDEO")):
            conn.execute(text("insert into prompt_ir_pointers (id, book_id, episode, storyboard_shot_id, target_media, prompt_ir_version_id, payload_hash, qualification_state) values (:id,1,1,7,:media,11,'hash','PROMPT_IR_QUALIFIED')"), {"id": row_id, "media": media})
        with pytest.raises(IntegrityError):
            conn.execute(text("insert into prompt_ir_pointers (id, book_id, episode, storyboard_shot_id, target_media, prompt_ir_version_id, payload_hash, qualification_state) values (3,1,1,7,'IMAGE',11,'hash','PROMPT_IR_QUALIFIED')"))
    assert engine.connect().execute(text("select count(*) from prompt_ir_pointers where storyboard_shot_id=7")).scalar() == 2
    engine.dispose()
