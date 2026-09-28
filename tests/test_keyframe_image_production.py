"""Keyframe image production vertical slice over existing authorities."""
from pathlib import Path
import json

import pytest

import core.storyboard_materializer as storyboard_materializer
from core.automatic_keyframe_authoring import compile_keyframe_plan, plan_keyframes, review_keyframe_plan
from core.keyframe_image_production import KeyframeImageProductionError, produce_keyframe_image, promote_keyframe_image
from core.video_generation_runtime import create_video_generation_intent
from models import Keyframe, KeyframeAssetBinding, KeyframeSequence, MediaCandidateRecord, OfficialMediaVersion, ProductionGenerationIntent
from tests.prompt_ir_authority_fixture import resolve_fixture_materialization
from tests.test_automatic_keyframe_authoring import _db, _materialized


@pytest.fixture()
def prepared(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(storyboard_materializer, "resolve_current_authoritative_materialization", resolve_fixture_materialization)
    engine, factory = _db(tmp_path)
    shot_id = _materialized(factory)
    with factory() as session:
        plan_keyframes(session, shot_id=shot_id)
        review_keyframe_plan(session, shot_id=shot_id, version=1, decision="APPROVE", reviewer="human")
        compile_keyframe_plan(session, shot_id=shot_id, version=1)
        session.commit()
        frame_ids = [row.id for row in session.query(Keyframe).order_by(Keyframe.order_index.asc()).all()]
    yield factory, shot_id, frame_ids
    engine.dispose()


def test_fixture_production_is_idempotent_and_review_gated(prepared):
    factory, _shot_id, frame_ids = prepared
    with factory() as session:
        first = produce_keyframe_image(session, keyframe_id=frame_ids[0])
        replay = produce_keyframe_image(session, keyframe_id=frame_ids[0])
        assert first["candidate"]["validation_status"] == "REVIEW_REQUIRED"
        assert replay["idempotent"] is True
        assert session.query(MediaCandidateRecord).count() == 1
        assert session.query(OfficialMediaVersion).count() == 0


def test_keyframe_request_contains_immutable_frame_prompt_lineage(prepared):
    factory, _shot_id, frame_ids = prepared
    with factory() as session:
        produced = produce_keyframe_image(session, keyframe_id=frame_ids[0])
        request = produced["execution"]["request"]
        keyframe_prompt = request["keyframe_prompt"]
        assert keyframe_prompt["source"] == "ProductionPromptVersion"
        assert keyframe_prompt["prompt_version_id"] == request["prompt_version_id"]
        assert keyframe_prompt["prompt_fingerprint"]
        assert "Frame State:" in keyframe_prompt["prompt_text"]
        assert "Motion Preparation:" in keyframe_prompt["prompt_text"]


def test_approve_creates_official_and_primary_keyframe_binding(prepared):
    factory, _shot_id, frame_ids = prepared
    with factory() as session:
        produced = produce_keyframe_image(session, keyframe_id=frame_ids[0])
        promoted = promote_keyframe_image(session, keyframe_id=frame_ids[0], validation_id=produced["validation_id"], reviewer="human")
        assert promoted["promotion"]["official_media_version_id"]
        binding = session.query(KeyframeAssetBinding).filter_by(keyframe_id=frame_ids[0], status="ACTIVE").one()
        assert binding.is_primary is True
        assert session.query(OfficialMediaVersion).count() == 1


def test_reject_preserves_candidate_and_allows_regeneration(prepared):
    factory, _shot_id, frame_ids = prepared
    with factory() as session:
        first = produce_keyframe_image(session, keyframe_id=frame_ids[1])
        promote_keyframe_image(session, keyframe_id=frame_ids[1], validation_id=first["validation_id"], reviewer="human", decision="REJECT", review_notes="revise")
        second = produce_keyframe_image(session, keyframe_id=frame_ids[1])
        assert second["idempotent"] is False
        assert session.query(MediaCandidateRecord).count() == 2
        assert session.query(OfficialMediaVersion).count() == 0


def test_stale_source_blocks_production(prepared):
    factory, _shot_id, frame_ids = prepared
    with factory() as session:
        row = session.query(Keyframe).filter_by(id=frame_ids[0]).one()
        session.query(KeyframeSequence).filter_by(id=row.keyframe_sequence_id).one().status = "STALE"
        session.commit()
        with pytest.raises(KeyframeImageProductionError) as exc:
            produce_keyframe_image(session, keyframe_id=frame_ids[0])
        assert exc.value.code in {"STALE_SOURCE", "KEYFRAME_SEQUENCE_STALE"}


def test_ineligible_generation_intent_fails_closed(prepared):
    factory, _shot_id, frame_ids = prepared
    with factory() as session:
        intent = session.query(ProductionGenerationIntent).one()
        constraints = json.loads(intent.constraint_snapshot or "{}")
        constraints["production_eligible"] = False
        intent.constraint_snapshot = json.dumps(constraints, ensure_ascii=False, sort_keys=True)
        session.commit()
        with pytest.raises(KeyframeImageProductionError) as exc:
            produce_keyframe_image(session, keyframe_id=frame_ids[0])
        assert exc.value.code in {"STALE_SOURCE", "GENERATION_INTENT_INELIGIBLE"}


def test_stale_after_generation_retains_candidate_and_blocks_promotion(prepared):
    factory, _shot_id, frame_ids = prepared
    with factory() as session:
        produced = produce_keyframe_image(session, keyframe_id=frame_ids[0])
        plan = session.query(__import__("models", fromlist=["AutomaticKeyframePlan"]).AutomaticKeyframePlan).one()
        plan.status = "STALE"
        plan.stale_reasons = json.dumps(["MATERIALIZATION_POINTER_CHANGED"])
        session.commit()
        with pytest.raises(KeyframeImageProductionError) as exc:
            promote_keyframe_image(session, keyframe_id=frame_ids[0], validation_id=produced["validation_id"], reviewer="human")
        assert exc.value.code == "STALE_SOURCE"
        assert session.query(MediaCandidateRecord).count() == 1
        assert session.query(OfficialMediaVersion).count() == 0
        assert session.query(KeyframeAssetBinding).count() == 0


def test_source_revision_after_execution_retains_candidate_and_blocks_promotion(prepared, monkeypatch):
    factory, _shot_id, frame_ids = prepared
    import core.keyframe_image_production as production

    with factory() as session:
        original_guard = production._source_guard
        calls = {"count": 0}

        def guarded(session_arg, frame, sequence, shot):
            calls["count"] += 1
            if calls["count"] == 2:
                plan = session_arg.query(__import__("models", fromlist=["AutomaticKeyframePlan"]).AutomaticKeyframePlan).one()
                plan.status = "STALE"
                plan.stale_reasons = json.dumps(["MATERIALIZATION_POINTER_CHANGED"])
                session_arg.flush()
            return original_guard(session_arg, frame, sequence, shot)

        monkeypatch.setattr(production, "_source_guard", guarded)
        with pytest.raises(KeyframeImageProductionError) as exc:
            produce_keyframe_image(session, keyframe_id=frame_ids[0])
        assert exc.value.code == "STALE_SOURCE"
        assert session.query(MediaCandidateRecord).count() == 1
        assert session.query(OfficialMediaVersion).count() == 0
        assert session.query(KeyframeAssetBinding).count() == 0


def test_atomic_promotion_rolls_back_official_rows_on_binding_failure(prepared, monkeypatch):
    factory, _shot_id, frame_ids = prepared
    with factory() as session:
        produced = produce_keyframe_image(session, keyframe_id=frame_ids[0])
        monkeypatch.setattr("core.keyframe_image_production.bind_keyframe_asset", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("binding failure")))
        with pytest.raises(RuntimeError, match="binding failure"):
            promote_keyframe_image(session, keyframe_id=frame_ids[0], validation_id=produced["validation_id"], reviewer="human")
        assert session.query(OfficialMediaVersion).count() == 0
        assert session.query(KeyframeAssetBinding).count() == 0


def test_approved_start_and_end_assets_are_video_intent_compatible(prepared):
    factory, shot_id, frame_ids = prepared
    with factory() as session:
        produced = {}
        for frame_id in (frame_ids[0], frame_ids[-1]):
            frame = session.query(Keyframe).filter_by(id=frame_id).one()
            produced[frame.frame_type] = produce_keyframe_image(session, keyframe_id=frame_id)
            promote_keyframe_image(session, keyframe_id=frame_id, validation_id=produced[frame.frame_type]["validation_id"], reviewer="human")
        start = session.query(Keyframe).filter_by(id=frame_ids[0]).one()
        end = session.query(Keyframe).filter_by(id=frame_ids[-1]).one()
        start_prompt = next(row for row in session.query(__import__("models", fromlist=["ProductionPromptVersion"]).ProductionPromptVersion).all() if int(__import__("json").loads(row.prompt_structure).get("keyframe", {}).get("keyframe_id", -1)) == int(start.id))
        intent = create_video_generation_intent(session, shot_id=shot_id, duration=3, aspect_ratio="16:9", motion_profile={"camera_motion": "static", "subject_motion": "still", "environment_motion": "static", "emotion_transition": "stable"}, first_frame_asset={"keyframe_id": start.id}, last_frame_asset={"keyframe_id": end.id}, prompt_version=start_prompt.prompt_version_id)
        assert intent["first_frame_asset"]["keyframe_id"] == start.id
        assert intent["last_frame_asset"]["keyframe_id"] == end.id


def test_keyframe_image_real_provider_canary_is_gate_skipped_by_default(prepared, monkeypatch):
    monkeypatch.delenv("PHASE_F_PROVIDER_CANARY_REAL", raising=False)
    factory, _shot_id, frame_ids = prepared
    with factory() as session:
        with pytest.raises(KeyframeImageProductionError) as exc:
            produce_keyframe_image(session, keyframe_id=frame_ids[0], fixture=False)
        assert exc.value.code == "REAL_PROVIDER_CANARY_SKIPPED_BY_GATE"


def test_middle_frame_can_be_optional(prepared):
    factory, _shot_id, frame_ids = prepared
    with factory() as session:
        middle = session.query(Keyframe).filter_by(id=frame_ids[1], frame_type="middle").one()
        result = produce_keyframe_image(session, keyframe_id=middle.id, production_required=False)
        assert result["skipped"] is True
        assert result["reason"] == "MIDDLE_FRAME_OPTIONAL"
