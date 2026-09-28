"""Three-shot resumable Episode production vertical slice."""

import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.storyboard_materializer as storyboard_materializer
from core.automatic_keyframe_authoring import review_keyframe_plan
from core.automatic_storyboard import (
    approve_storyboard,
    compile_storyboard,
    persist_storyboard,
    storyboard_from_reasoning,
)
from core.director_reasoning import director_reason, persist_reasoning
from core.episode_production import run_episode_production
from core.episode_rendering import create_episode_render_plan
from core.keyframe_image_production import promote_keyframe_image
from core.media_authority import promote_media_candidate
from core.storyboard_production_materialization import materialize_storyboard_plan
from models import (
    AutomaticKeyframePlan,
    EpisodeOutline,
    GenerationExecutionRecord,
    Keyframe,
    KeyframeSequence,
    MediaCandidateRecord,
    MediaValidationRecord,
    OfficialMediaVersion,
    PromptIRAuthority,
    PromptIRVersion,
    StoryboardPlan,
    StoryboardShot,
)
from scripts.verify_migration_chain import _upgrade
from tests.prompt_ir_authority_fixture import resolve_fixture_materialization
from tests.test_j2_3_dual_media_currentness import _install_video_scope


def _session(tmp_path: Path):
    db = tmp_path / "episode-automatic-production-vertical-slice.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    return engine, sessionmaker(bind=engine)()


def _build_episode(session):
    script = {
        "episode_id": "episode-vertical-1",
        "episode": 1,
        "scenes": [{
            "scene_id": "scene-1",
            "scene_name": "Station",
            "participants": ["char-1"],
            "shots": [{"shot_id": "shot-1"}, {"shot_id": "shot-2"}, {"shot_id": "shot-3"}],
        }],
    }
    episode = {
        "episode_id": "episode-vertical-1",
        "book_id": 77,
        "episode": 1,
        "character_profiles": [{"character_id": "char-1"}],
        "visual_style_profiles": [{"visual_style_id": "style-1"}],
    }
    scene = {
        "scenes": script["scenes"],
        "visual_styles": [{"visual_style_id": "style-1"}],
        "beats": [
            {"sequence": 1, "scene_id": "scene-1", "purpose": "arrive", "emotion": "calm", "visual_goal": "establish", "character_refs": ["char-1"], "shot_refs": ["shot-1"]},
            {"sequence": 2, "scene_id": "scene-1", "purpose": "look", "emotion": "alert", "visual_goal": "reaction", "character_refs": ["char-1"], "shot_refs": ["shot-2"]},
            {"sequence": 3, "scene_id": "scene-1", "purpose": "move", "emotion": "resolved", "visual_goal": "exit", "character_refs": ["char-1"], "shot_refs": ["shot-3"]},
        ],
    }
    reasoning = persist_reasoning(session, director_reason(episode, script, scene))
    payload = storyboard_from_reasoning(
        reasoning,
        context={"episode_id": script["episode_id"], "scenes": script["scenes"]},
        director_reasoning_id=reasoning["id"],
        director_reasoning_version=reasoning["version"],
    )
    draft = persist_storyboard(session, payload)
    storyboard = session.query(StoryboardPlan).filter_by(id=draft["id"]).one()
    compile_storyboard(session, storyboard, episode_context=episode, script_ir=script, scene_context=scene, book_id=77, episode_number=1)
    approve_storyboard(session, script["episode_id"], 1, reviewer="human")
    materialize_storyboard_plan(session, episode_id=script["episode_id"], storyboard_plan_id=storyboard.id, storyboard_version=1, book_id=77, episode_number=1)
    shots = session.query(StoryboardShot).order_by(StoryboardShot.shot_id.asc()).all()
    outline = EpisodeOutline(id=50101, book_id=77, episode=1, title="Automatic production vertical slice")
    session.add(outline)
    session.flush()
    render_plan = create_episode_render_plan(
        session,
        episode_id=outline.id,
        items=[{"shot_id": shot.id, "order": index, "dependency": [] if index == 0 else [shots[index - 1].id]}
               for index, shot in enumerate(shots)],
    )
    session.commit()
    return outline.id, render_plan.id, shots


def _approve_image(session, shot_id: int, frame_type: str):
    frame = (
        session.query(Keyframe)
        .join(KeyframeSequence, KeyframeSequence.id == Keyframe.keyframe_sequence_id)
        .filter(KeyframeSequence.storyboard_shot_id == shot_id, Keyframe.frame_type == frame_type.lower())
        .one()
    )
    executions = session.query(GenerationExecutionRecord).filter_by(storyboard_shot_id=shot_id).all()
    execution = next(
        row for row in executions
        if (row.request_payload if isinstance(row.request_payload, dict) else json.loads(row.request_payload or "{}"))
        .get("_keyframe_image_production", {}).get("keyframe_id") == frame.id
    )
    validation = session.query(MediaValidationRecord).filter_by(execution_id=execution.execution_id).one()
    return promote_keyframe_image(session, keyframe_id=frame.id, validation_id=validation.validation_id, reviewer="human")


def _approve_video(session, shot_id: int):
    execution = session.query(GenerationExecutionRecord).filter_by(storyboard_shot_id=shot_id, target_media="VIDEO").order_by(GenerationExecutionRecord.id.desc()).first()
    candidate = session.query(MediaCandidateRecord).filter_by(execution_id=execution.execution_id).one()
    validation = session.query(MediaValidationRecord).filter_by(execution_id=execution.execution_id).one()
    return promote_media_candidate(session, candidate.candidate_id, validation.validation_id, confirmation=True, reviewer="human", decision="APPROVE")


def test_three_shot_episode_resumes_through_review_and_dependency_gates(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(storyboard_materializer, "resolve_current_authoritative_materialization", resolve_fixture_materialization)
    engine, session = _session(tmp_path)
    try:
        episode_id, plan_id, shots = _build_episode(session)
        first = run_episode_production(session, episode_id=episode_id, plan_id=plan_id)
        assert first["state"] == "WAITING_REVIEW"
        assert first["shots"][0]["state"] == "KEYFRAME_PLAN_REVIEW_REQUIRED"
        assert first["shots"][1]["state"] == "BLOCKED_DEPENDENCY"
        replay = run_episode_production(session, episode_id=episode_id, plan_id=plan_id)
        assert replay["actions"] == []

        for index, shot in enumerate(shots):
            plan = session.query(AutomaticKeyframePlan).filter_by(storyboard_shot_id=shot.id).order_by(AutomaticKeyframePlan.version.desc()).first()
            assert plan is not None
            review_keyframe_plan(session, shot_id=shot.id, version=plan.version, decision="APPROVE", reviewer="human")
            session.commit()
            image_run = run_episode_production(session, episode_id=episode_id, plan_id=plan_id)
            assert image_run["shots"][index]["state"] == "KEYFRAME_IMAGE_REVIEW_REQUIRED"
            _approve_image(session, shot.id, "START")
            session.commit()
            second_image_run = run_episode_production(session, episode_id=episode_id, plan_id=plan_id)
            assert second_image_run["shots"][index]["state"] == "KEYFRAME_IMAGE_REVIEW_REQUIRED"
            _approve_image(session, shot.id, "END")
            session.commit()

            image_version = session.query(PromptIRVersion).filter_by(storyboard_shot_id=shot.id).order_by(PromptIRVersion.id.desc()).first()
            image_authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=image_version.id).one()
            _install_video_scope(session, image_version, image_authority)
            session.commit()
            video_run = run_episode_production(session, episode_id=episode_id, plan_id=plan_id)
            assert video_run["shots"][index]["state"] == "VIDEO_REVIEW_REQUIRED"
            assert video_run["provider_calls"]["real_video"] == 0
            _approve_video(session, shot.id)
            session.commit()
            completed = run_episode_production(session, episode_id=episode_id, plan_id=plan_id)
            if index < 2:
                assert completed["shots"][index]["state"] == "COMPLETE"
                assert completed["shots"][index + 1]["state"] == "KEYFRAME_PLAN_REVIEW_REQUIRED"
            else:
                assert completed["state"] == "PRODUCTION_COMPLETE"

        assert session.query(OfficialMediaVersion).filter_by(media_type="VIDEO", media_role="SHOT_PRIMARY_VIDEO", status="CURRENT").count() == 3
        assert session.query(GenerationExecutionRecord).filter_by(target_media="VIDEO").count() == 3
        assert session.query(MediaCandidateRecord).filter_by(media_type="VIDEO").count() == 3
    finally:
        session.close()
        engine.dispose()
