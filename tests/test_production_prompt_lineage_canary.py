"""Contract tests for the provider-free Production Prompt Lineage layer."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.production_asset_authority import ingest_production_asset
from core.production_asset_review import create_production_asset_review, run_review_path
from core.production_prompt_lineage import (
    ProductionPromptLineageError,
    asset_has_prompt_lineage,
    create_production_generation_intent,
    create_production_prompt_lineage,
    create_production_prompt_version,
    create_prompt_change_candidate,
    prompt_fingerprint,
    review_reproducible_generation_context,
    trace_production_asset_version,
    update_production_prompt_version,
)
from core.production_prompt_lineage_canary import (
    build_production_prompt_lineage_fixture,
    build_prompt_lineage_truth_audit,
    reconcile_production_prompt_lineage_canary,
)
from models import ProductionPromptVersion, StoryboardShot
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "production-prompt-lineage.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return engine, sessionmaker(bind=engine)()


def _source(name: str, revision: int = 1) -> dict:
    return {
        "storage_identity": f"https://assets.example.invalid/test/{name}/v{revision}.png",
        "checksum": f"sha256:test:{name}:{revision}",
        "metadata": {
            "schema_version": "production_asset_media_metadata_v1",
            "source_kind": "production_prompt_lineage_test",
            "mime_type": "image/png",
            "width": 1024,
            "height": 1024,
            "provenance": {"source_reference": f"fixture://{name}/{revision}", "is_mock": False},
        },
    }


def _fixture_rows(tmp_path: Path):
    engine, session = _session(tmp_path)
    asset = ingest_production_asset(session, entity_type="CHARACTER", entity_id="LINEAGE_CHARACTER", source=_source("character"))
    shot = StoryboardShot(book_id=990401, episode=1, scene_name="TEST_SCENE", scene_id="TEST_SCENE", plan_shot_id="TEST_SHOT_001", shot_id=1, production_status="ready", quality_status="qualified", workflow_profile="production")
    session.add(shot)
    session.flush()
    requirement = {"shot_id": 1, "requirements": [{"asset_type": "CHARACTER", "entity_id": "LINEAGE_CHARACTER"}]}
    return engine, session, asset, shot, requirement


def _lineage(session, asset, shot, requirement, prompt_id="test-prompt"):
    prompt = create_production_prompt_version(session, prompt_id=prompt_id, prompt_text="A consistent production frame.", prompt_structure={"camera": "MS"})
    intent = create_production_generation_intent(session, shot_id=shot.id, shot_requirement=requirement)
    lineage = create_production_prompt_lineage(session, asset_type="CHARACTER", asset_id="LINEAGE_CHARACTER", asset_version_id=asset["version_id"], shot_id=shot.id, prompt_version_id=prompt["prompt_version_id"], generation_intent_id=intent["generation_intent_id"])
    return prompt, intent, lineage


def test_asset_requires_prompt_lineage(tmp_path: Path):
    engine, session, asset, shot, requirement = _fixture_rows(tmp_path)
    try:
        assert asset_has_prompt_lineage(session, asset["version_id"]) is False
        _lineage(session, asset, shot, requirement)
        assert asset_has_prompt_lineage(session, asset["version_id"]) is True
    finally:
        session.close(); engine.dispose()


def test_prompt_version_is_immutable_and_new_version_is_appended(tmp_path: Path):
    engine, session, *_ = _fixture_rows(tmp_path)
    try:
        first = create_production_prompt_version(session, prompt_id="immutable", prompt_text="v1")
        with pytest.raises(ProductionPromptLineageError):
            update_production_prompt_version(session, prompt_version_id=first["prompt_version_id"], prompt_text="mutated")
        second = create_production_prompt_version(session, prompt_id="immutable", prompt_text="v2")
        assert first["version_number"] == 1 and second["version_number"] == 2
        assert session.query(ProductionPromptVersion).filter_by(prompt_id="immutable").count() == 2
    finally:
        session.close(); engine.dispose()


def test_prompt_fingerprint_is_deterministic_and_sensitive():
    a = prompt_fingerprint("same", {"camera": "MS"})
    b = prompt_fingerprint("same", {"camera": "MS"})
    c = prompt_fingerprint("changed", {"camera": "MS"})
    assert a == b
    assert a != c


def test_generation_intent_requires_shot_requirement(tmp_path: Path):
    engine, session, *_ = _fixture_rows(tmp_path)
    try:
        with pytest.raises(ProductionPromptLineageError):
            create_production_generation_intent(session, shot_id=1, shot_requirement={})
    finally:
        session.close(); engine.dispose()


def test_asset_traces_back_to_shot_prompt_and_intent(tmp_path: Path):
    engine, session, asset, shot, requirement = _fixture_rows(tmp_path)
    try:
        prompt, intent, lineage = _lineage(session, asset, shot, requirement)
        trace = trace_production_asset_version(session, asset["version_id"])
        assert trace["shot_id"] == shot.id
        assert trace["prompt_version"]["prompt_version_id"] == prompt["prompt_version_id"]
        assert trace["generation_intent"]["generation_intent_id"] == intent["generation_intent_id"]
        assert trace["lineages"][0]["prompt_lineage_id"] == lineage["prompt_lineage_id"]
    finally:
        session.close(); engine.dispose()


def test_review_reproduces_generation_context(tmp_path: Path):
    engine, session, asset, shot, requirement = _fixture_rows(tmp_path)
    try:
        _, _, lineage = _lineage(session, asset, shot, requirement)
        review = create_production_asset_review(session, asset_type="CHARACTER", asset_id="LINEAGE_CHARACTER", asset_version_id=asset["version_id"], prompt_lineage_id=lineage["prompt_lineage_id"])
        run_review_path(session, review_id=review["review_id"], decision="APPROVE")
        context = review_reproducible_generation_context(session, review["review_id"])
        assert context["reproducible"] is True
        assert context["trace"]["lineages"][0]["prompt_lineage_id"] == lineage["prompt_lineage_id"]
    finally:
        session.close(); engine.dispose()


def test_prompt_change_creates_new_prompt_and_asset_version(tmp_path: Path):
    engine, session, asset, shot, requirement = _fixture_rows(tmp_path)
    try:
        old_prompt, _, old_lineage = _lineage(session, asset, shot, requirement, prompt_id="change")
        candidate = create_prompt_change_candidate(session, old_asset_type="CHARACTER", old_asset_id="LINEAGE_CHARACTER", old_asset_version_id=asset["version_id"], shot_id=shot.id, prompt_id="change", prompt_text="A revised production frame.", prompt_structure={"revision": 2}, shot_requirement=requirement, source=_source("character", 2))
        assert candidate["prompt_version"]["version_number"] == 2
        assert candidate["asset"]["version_id"] != asset["version_id"]
        assert candidate["lineage"]["prompt_lineage_id"] != old_lineage["prompt_lineage_id"]
        assert old_prompt["version_number"] == 1
    finally:
        session.close(); engine.dispose()


def test_old_prompt_history_is_preserved_after_change(tmp_path: Path):
    engine, session, asset, shot, requirement = _fixture_rows(tmp_path)
    try:
        old_prompt, _, old_lineage = _lineage(session, asset, shot, requirement, prompt_id="history")
        candidate = create_prompt_change_candidate(session, old_asset_type="CHARACTER", old_asset_id="LINEAGE_CHARACTER", old_asset_version_id=asset["version_id"], shot_id=shot.id, prompt_id="history", prompt_text="new history prompt", prompt_structure={}, shot_requirement=requirement, source=_source("character", 2))
        assert session.query(ProductionPromptVersion).filter_by(prompt_version_id=old_prompt["prompt_version_id"]).one().prompt_text == "A consistent production frame."
        assert candidate["prompt_version"]["version_number"] == 2
        assert session.query(ProductionPromptVersion).filter_by(prompt_id="history").count() == 2
    finally:
        session.close(); engine.dispose()


def test_canary_truth_audit_covers_full_fixture(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        result = reconcile_production_prompt_lineage_canary(session, build_production_prompt_lineage_fixture())
        audit = build_prompt_lineage_truth_audit(result)
        assert result["stage"] == "PHASE_PRODUCTION_PROMPT_LINEAGE_CANARY_COMPLETE"
        assert result["counts"]["shot_count"] == 10
        assert result["counts"]["prompt_version_count"] >= 15
        assert audit["complete"] is True
    finally:
        session.close(); engine.dispose()


def test_lineage_rejects_intent_from_another_shot(tmp_path: Path):
    engine, session, asset, shot, requirement = _fixture_rows(tmp_path)
    try:
        prompt = create_production_prompt_version(session, prompt_id="mismatch", prompt_text="prompt")
        other_shot = StoryboardShot(book_id=990401, episode=1, scene_name="OTHER", scene_id="OTHER", plan_shot_id="OTHER", shot_id=2, production_status="ready", quality_status="qualified", workflow_profile="production")
        session.add(other_shot); session.flush()
        intent = create_production_generation_intent(session, shot_id=other_shot.id, shot_requirement={"shot_id": 2, "requirements": []})
        with pytest.raises(ProductionPromptLineageError):
            create_production_prompt_lineage(session, asset_type="CHARACTER", asset_id="LINEAGE_CHARACTER", asset_version_id=asset["version_id"], shot_id=shot.id, prompt_version_id=prompt["prompt_version_id"], generation_intent_id=intent["generation_intent_id"])
    finally:
        session.close(); engine.dispose()
