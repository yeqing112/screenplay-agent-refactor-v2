"""Character Consistency Runtime contract tests."""
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from core.character_consistency import (
    CharacterConsistencyError,
    add_character_reference_asset,
    bind_shot_character,
    create_character_identity,
    create_character_constrained_prompt_version,
    inject_character_constraints,
    validate_shot_character_consistency,
)
from models import CharacterIdentity, CharacterReferenceAsset, ShotCharacterBinding, StoryboardShot
from models import ProductionPromptVersion
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "character-consistency.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return engine, sessionmaker(bind=engine)()


def _shot(session, *, shot_id: int = 11):
    row = StoryboardShot(
        book_id=990401,
        episode=1,
        scene_name="office",
        scene_id="scene:office",
        shot_id=shot_id,
        materialization_status="MATERIALIZED",
        execution_status="queued",
        quality_status="draft",
        production_status="blocked",
        workflow_profile="production",
    )
    session.add(row)
    session.flush()
    return row


def test_migration_exposes_identity_extension_and_typed_relations(tmp_path):
    engine, session = _session(tmp_path)
    try:
        columns = {item["name"] for item in inspect(engine).get_columns("character_profiles")}
        assert {"description", "attributes", "appearance_profile"}.issubset(columns)
        assert {"character_reference_assets", "shot_character_bindings"}.issubset(set(inspect(engine).get_table_names()))
        assert CharacterIdentity.__tablename__ == "character_profiles"
    finally:
        session.close(); engine.dispose()


def test_identity_reference_binding_and_prompt_injection_preserve_source_prompt(tmp_path):
    engine, session = _session(tmp_path)
    try:
        identity = create_character_identity(
            session,
            book_id=990401,
            name="顾宁",
            description="冷静的调查记者",
            attributes={"gender": "female", "age_range": "late twenties"},
            appearance_profile={"hair": "shoulder length black hair", "wardrobe": "navy coat"},
        )
        portrait = add_character_reference_asset(session, character_id=identity["id"], asset_id="char-gu-portrait-v1", reference_type="portrait", priority=0)
        full_body = add_character_reference_asset(session, character_id=identity["id"], asset_id="char-gu-full-body-v1", reference_type="full_body", priority=1)
        shot = _shot(session)
        binding = bind_shot_character(session, shot_id=shot.id, character_id=identity["id"], role="lead", reference_asset_ids=[portrait["id"], full_body["asset_id"]], appearance_rules={"expression": "alert"})
        session.commit()

        validation = validate_shot_character_consistency(session, shot_id=shot.id)
        assert validation["status"] == "PASS"
        assert validation["checks"] == {"character_bound": True, "reference_asset_present": True, "constraints_present": True}
        assert binding["role"] == "lead"
        assert session.query(CharacterReferenceAsset).count() == 2
        assert session.query(ShotCharacterBinding).count() == 1

        source = "A medium shot of the office doorway."
        compiled = inject_character_constraints(session, shot_id=shot.id, original_prompt=source)
        assert compiled["original_prompt"] == source
        assert compiled["prompt_was_mutated"] is False
        assert source in compiled["injected_prompt"]
        assert "顾宁" in compiled["injected_prompt"]
        assert "char-gu-portrait-v1" in compiled["injected_prompt"]
        assert "navy coat" in compiled["injected_prompt"]
        prompt_version = create_character_constrained_prompt_version(session, prompt_id="shot-11-character", shot_id=shot.id, original_prompt=source, prompt_structure={"media": "IMAGE"})
        assert prompt_version["prompt_was_mutated"] is False
        persisted = session.query(ProductionPromptVersion).filter_by(prompt_version_id=prompt_version["prompt_version"]["prompt_version_id"]).one()
        assert persisted.created_from == "CHARACTER_CONSISTENCY"
        assert "source_prompt" in persisted.prompt_structure
        assert source in persisted.prompt_structure
    finally:
        session.close(); engine.dispose()


def test_missing_reference_blocks_consistency_and_prompt_injection(tmp_path):
    engine, session = _session(tmp_path)
    try:
        identity = create_character_identity(session, book_id=990401, name="缺图角色", description="needs a reference")
        shot = _shot(session, shot_id=12)
        bind_shot_character(session, shot_id=shot.id, character_id=identity["id"], role="supporting")
        session.commit()
        validation = validate_shot_character_consistency(session, shot_id=shot.id)
        assert validation["status"] == "BLOCKED"
        assert any(item["code"] == "CHARACTER_REFERENCE_ASSET_MISSING" for item in validation["errors"])
        with pytest.raises(CharacterConsistencyError) as exc:
            inject_character_constraints(session, shot_id=shot.id, original_prompt="original")
        assert exc.value.code == "CHARACTER_CONSISTENCY_BLOCKED"
    finally:
        session.close(); engine.dispose()
