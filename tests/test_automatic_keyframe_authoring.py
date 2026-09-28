"""AutomaticKeyframePlan review, stale, atomic, and lineage contracts."""
from pathlib import Path
import json

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from core.automatic_keyframe_authoring import (
    AutomaticKeyframePlanError,
    compile_keyframe_plan,
    get_keyframe_plan,
    plan_keyframes,
    review_keyframe_plan,
)
from core.automatic_storyboard import compile_storyboard, persist_storyboard, storyboard_from_reasoning, approve_storyboard
from core.director_reasoning import director_reason, persist_reasoning
from core.storyboard_production_materialization import materialize_storyboard_plan
from core.shot_direction import update_shot_direction
from models import (
    AutomaticKeyframePlan,
    Keyframe,
    KeyframeSequence,
    ProductionPromptVersion,
    StoryboardMaterializationPointer,
    StoryboardMaterializationSet,
    StoryboardPlan,
    StoryboardShot,
)
from scripts.verify_migration_chain import _upgrade


def _db(tmp_path: Path):
    path = tmp_path / "automatic-keyframe.sqlite"
    _upgrade(path)
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    return engine, sessionmaker(bind=engine)


def _materialized(factory):
    script = {"episode_id": "akf-ep-1", "episode": 1, "scenes": [{"scene_id": "scene-1", "scene_name": "Station", "participants": ["char-1"], "shots": [{"shot_id": "shot-1"}]}]}
    episode = {"episode_id": "akf-ep-1", "book_id": 77, "episode": 1, "character_profiles": [{"character_id": "char-1"}], "visual_style_profiles": [{"visual_style_id": "style-1"}]}
    scene = {"scenes": script["scenes"], "visual_styles": [{"visual_style_id": "style-1"}]}
    with factory() as session:
        reasoning = persist_reasoning(session, director_reason(episode, script, scene))
        payload = storyboard_from_reasoning(reasoning, context={"episode_id": "akf-ep-1", "scenes": script["scenes"]}, director_reasoning_id=reasoning["id"], director_reasoning_version=reasoning["version"])
        draft = persist_storyboard(session, payload)
        row = session.query(StoryboardPlan).filter_by(id=draft["id"]).one()
        compile_storyboard(session, row, episode_context=episode, script_ir=script, scene_context=scene, book_id=77, episode_number=1)
        session.commit()
        approve_storyboard(session, "akf-ep-1", 1, reviewer="reviewer-1")
        materialize_storyboard_plan(session, episode_id="akf-ep-1", storyboard_plan_id=row.id, storyboard_version=1, book_id=77, episode_number=1)
        session.commit()
        return int(session.query(StoryboardShot).one().id)


def test_plan_review_compile_idempotency_and_prompt_lineage(tmp_path: Path):
    engine, factory = _db(tmp_path)
    try:
        shot_id = _materialized(factory)
        with factory() as session:
            assert inspect(engine).has_table("automatic_keyframe_plans")
            plan = plan_keyframes(session, shot_id=shot_id)
            assert plan["status"] == "REVIEW_REQUIRED"
            assert [item["type"] for item in plan["plan"]["frames"]] == ["start", "middle", "end"]
            assert session.query(KeyframeSequence).count() == 0
            with pytest.raises(AutomaticKeyframePlanError) as blocked:
                compile_keyframe_plan(session, shot_id=shot_id, version=1)
            assert blocked.value.code == "REVIEW_REQUIRED"
            approved = review_keyframe_plan(session, shot_id=shot_id, version=1, decision="APPROVE", reviewer="human-1")
            assert approved["status"] == "APPROVED"
            compiled = compile_keyframe_plan(session, shot_id=shot_id, version=1)
            session.commit()
            assert compiled["plan"]["status"] == "COMPILED"
            assert [item["type"] for item in compiled["sequence"]["frames"]] == ["start", "middle", "end"]
            assert session.query(Keyframe).count() == 3
            assert session.query(ProductionPromptVersion).count() == 4
            replay = compile_keyframe_plan(session, shot_id=shot_id, version=1)
            assert replay["idempotent"] is True
            assert replay["sequence"]["id"] == compiled["sequence"]["id"]
            lineage_rows = [row for row in session.query(ProductionPromptVersion).all() if "AUTOMATIC_KEYFRAME_PLAN" in row.created_from]
            assert len(lineage_rows) == 3
            assert all(json.loads(row.prompt_structure)["automatic_keyframe_plan"]["id"] == 1 for row in lineage_rows)
    finally:
        engine.dispose()


def test_atomic_compile_failure_leaves_no_production_rows(tmp_path: Path):
    engine, factory = _db(tmp_path)
    try:
        shot_id = _materialized(factory)
        with factory() as session:
            plan_keyframes(session, shot_id=shot_id)
            review_keyframe_plan(session, shot_id=shot_id, version=1, decision="APPROVE", reviewer="human-1")
            row = session.query(AutomaticKeyframePlan).one()
            payload = json.loads(row.plan_json)
            payload["frames"][1]["type"] = "invalid"
            row.plan_json = json.dumps(payload, ensure_ascii=False)
            with pytest.raises(AutomaticKeyframePlanError):
                compile_keyframe_plan(session, shot_id=shot_id, version=1)
            assert session.query(KeyframeSequence).count() == 0
            assert session.query(Keyframe).count() == 0
            assert session.query(ProductionPromptVersion).count() == 1
    finally:
        engine.dispose()


def test_materialization_switch_marks_old_plan_stale_and_rollback_rechecks_source(tmp_path: Path):
    engine, factory = _db(tmp_path)
    try:
        shot_id = _materialized(factory)
        with factory() as session:
            plan_keyframes(session, shot_id=shot_id)
            shot = session.query(StoryboardShot).one()
            pointer = session.query(StoryboardMaterializationPointer).one()
            old_set = session.query(StoryboardMaterializationSet).one()
            new_set = StoryboardMaterializationSet(
                book_id=old_set.book_id, episode=old_set.episode, scene_id=old_set.scene_id, shot_plan_id=old_set.shot_plan_id,
                shot_plan_revision=old_set.shot_plan_revision, shot_plan_payload_hash=old_set.shot_plan_payload_hash,
                shot_plan_authority_fingerprint=old_set.shot_plan_authority_fingerprint, expected_shot_count=old_set.expected_shot_count,
                materialized_shot_count=old_set.materialized_shot_count, ordered_plan_shot_ids=old_set.ordered_plan_shot_ids,
                set_payload_fingerprint="sha256:new-materialization-set", materializer_version=old_set.materializer_version,
                materializer_policy_version=old_set.materializer_policy_version, authority_envelope_json=old_set.authority_envelope_json,
                status="MATERIALIZED", stale_status="FRESH",
            )
            session.add(new_set)
            session.flush()
            pointer.materialization_set_id = new_set.id
            pointer.set_payload_fingerprint = new_set.set_payload_fingerprint
            session.flush()
            stale = get_keyframe_plan(session, shot_id=shot_id, version=1)
            assert stale["status"] == "STALE"
            assert "MATERIALIZATION_POINTER_CHANGED" in stale["stale_reasons"]
            # Restore the pointer.  The exact original authority fingerprint is
            # required before the historical plan can be reviewed again.
            pointer.materialization_set_id = old_set.id
            pointer.set_payload_fingerprint = old_set.set_payload_fingerprint
            restored = get_keyframe_plan(session, shot_id=shot_id, version=1)
            assert restored["status"] == "STALE"  # history stays stale until a new human approval
            approved = review_keyframe_plan(session, shot_id=shot_id, version=1, decision="APPROVE", reviewer="rollback-review")
            assert approved["status"] == "APPROVED"
            assert shot.materialization_set_id == old_set.id
            shot.source_shot_plan_revision = int(old_set.shot_plan_revision) + 1
            changed_revision = get_keyframe_plan(session, shot_id=shot_id, version=1)
            assert changed_revision["status"] == "STALE"
            assert "SHOT_PLAN_REVISION_CHANGED" in changed_revision["stale_reasons"]
    finally:
        engine.dispose()


def test_direction_revision_creates_plan_and_sequence_v2_without_deleting_v1(tmp_path: Path):
    engine, factory = _db(tmp_path)
    try:
        shot_id = _materialized(factory)
        with factory() as session:
            plan_v1 = plan_keyframes(session, shot_id=shot_id)
            review_keyframe_plan(session, shot_id=shot_id, version=1, decision="APPROVE", reviewer="human-1")
            compiled_v1 = compile_keyframe_plan(session, shot_id=shot_id, version=1)
            session.commit()
            update_shot_direction(session, shot_id=shot_id, camera_profile={"lens": "50mm", "angle": "low_angle", "distance": "close_up", "movement": "slow push in", "speed": "slow"})
            session.commit()
            plan_v2 = plan_keyframes(session, shot_id=shot_id)
            assert plan_v2["version"] == 2
            assert plan_v2["status"] == "REVIEW_REQUIRED"
            review_keyframe_plan(session, shot_id=shot_id, version=2, decision="APPROVE", reviewer="human-2")
            compiled_v2 = compile_keyframe_plan(session, shot_id=shot_id, version=2)
            session.commit()
            assert compiled_v2["sequence"]["revision"] == 2
            assert session.query(AutomaticKeyframePlan).count() == 2
            assert session.query(KeyframeSequence).count() == 2
            assert session.query(KeyframeSequence).filter_by(revision=1).one().status == "STALE"
            assert plan_v1["id"] != plan_v2["id"]
            assert compiled_v1["sequence"]["id"] != compiled_v2["sequence"]["id"]
    finally:
        engine.dispose()
