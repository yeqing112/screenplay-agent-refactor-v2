"""Deterministic PromptIR authority spine used by provider-free tests.

The helper persists the same materialization objects consumed by Production
PromptIR validation.  Tests may replace the upstream resolver with
``resolve_fixture_materialization`` so the fixture remains self-contained,
while the persisted source authority is produced from the canonical Phase D
snapshot and never hand-written as a compatibility marker.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime
from types import SimpleNamespace

from core.prompt_ir_phase_e import compile_storyboard_snapshot_to_prompt_ir, fingerprint
from core.storyboard_materializer import authority_envelope_fingerprint, build_storyboard_production_snapshot
from models import StoryboardMaterializationPointer, StoryboardMaterializationSet, StoryboardShot


def canonical_snapshot() -> dict:
    from tests.test_prompt_ir_phase_e_semantic_closure import _snapshots

    return copy.deepcopy(_snapshots()[0])


def source_authority_for_row(*, snapshot: dict, row: dict, set_id: int = 1, set_fingerprint: str = "set-1", policy_fingerprint: str) -> dict:
    semantic = row.get("visual_semantic_handoff") or {}
    provenance = semantic.get("projection_provenance") if isinstance(semantic.get("projection_provenance"), dict) else {}
    envelope = snapshot.get("authority_envelope") if isinstance(snapshot.get("authority_envelope"), dict) else {}
    shot_plan = envelope.get("shot_plan") if isinstance(envelope.get("shot_plan"), dict) else {}
    blocking = envelope.get("scene_blocking") or envelope.get("blocking") or {}
    return {
        "storyboard_materialization_set_id": set_id,
        "storyboard_set_payload_fingerprint": set_fingerprint,
        "storyboard_projection_fingerprint": row.get("projection_fingerprint", ""),
        "visual_semantic_handoff_fingerprint": fingerprint({key: value for key, value in semantic.items() if key != "projection_provenance"}),
        "shot_plan_authority_fingerprint": provenance.get("source_shot_plan_authority_fingerprint") or shot_plan.get("authority_fingerprint", ""),
        "blocking_authority_fingerprint": provenance.get("blocking_authority_fingerprint") or blocking.get("authority_fingerprint", ""),
        "generation_policy_fingerprint": policy_fingerprint,
    }


def install_authority_spine(session, *, book_id: int, episode: int, shot_id: int, snapshot: dict | None = None, plan_shot_id: str | None = None, set_id: int = 1) -> tuple[StoryboardShot, dict, dict]:
    """Persist one real materialization set/pointer/shot spine and return it."""
    snapshot = copy.deepcopy(snapshot or canonical_snapshot())
    source_row = next(row for row in snapshot["ordered_shots"] if plan_shot_id is None or row.get("plan_shot_id") == plan_shot_id)
    plan_shot_id = str(source_row.get("plan_shot_id") or plan_shot_id or "fixture-shot")
    existing_set = session.query(StoryboardMaterializationSet).filter_by(book_id=book_id, episode=episode, scene_id=str(snapshot.get("scene_id") or "fixture")).first()
    if existing_set is not None:
        existing_shot = session.query(StoryboardShot).filter_by(book_id=book_id, episode=episode, scene_id=existing_set.scene_id, materialization_set_id=existing_set.id, plan_shot_id=plan_shot_id).first()
        if existing_shot is not None:
            return existing_shot, source_row, json.loads(existing_set.authority_envelope_json or "{}")
    projection = copy.deepcopy(source_row.get("projection_payload") or {})
    semantic = copy.deepcopy(source_row.get("visual_semantic_handoff") or {})
    meta = {
        "visual_semantic_handoff": semantic,
        "projection_payload": projection,
        "prompt_compiler_handoff": copy.deepcopy(source_row.get("prompt_compiler_handoff") or {}),
    }
    now = datetime.now()
    shot = StoryboardShot(
        book_id=book_id, episode=episode, scene_name=str(snapshot.get("scene_id") or "fixture"), scene_id=str(snapshot.get("scene_id") or "fixture"),
        plan_shot_id=plan_shot_id, materialization_set_id=set_id, source_shot_plan_id=1, source_shot_plan_revision=1,
        source_shot_plan_authority_fingerprint=str((semantic.get("projection_provenance") or {}).get("source_shot_plan_authority_fingerprint") or ""),
        projection_fingerprint=str(source_row.get("projection_fingerprint") or ""), materialization_status="MATERIALIZED", shot_id=shot_id,
        duration=projection.get("duration", 3), camera_angle=projection.get("camera_angle", "MS"), camera_movement=projection.get("camera_movement", "static"),
        camera_speed=projection.get("camera_speed", "slow"), shot_purpose=projection.get("shot_purpose", "emotion"), transition=projection.get("transition", "cut"),
        lighting=projection.get("lighting", ""), start_state=json.dumps(projection.get("start_state", ""), ensure_ascii=False) if isinstance(projection.get("start_state"), (dict, list)) else projection.get("start_state", ""), action_process=json.dumps(projection.get("action_process", ""), ensure_ascii=False) if isinstance(projection.get("action_process"), (dict, list)) else projection.get("action_process", ""), end_state=json.dumps(projection.get("end_state", ""), ensure_ascii=False) if isinstance(projection.get("end_state"), (dict, list)) else projection.get("end_state", ""),
        asset_links="{}", meta_info=json.dumps(meta, ensure_ascii=False, sort_keys=True), created_at=now, updated_at=now,
    )
    session.add(shot)
    session.flush()
    authority = copy.deepcopy(snapshot.get("authority_envelope") or {})
    authority["materialization"] = {"id": set_id, "fingerprint": "set-1"}
    authority["authority_fingerprint"] = authority_envelope_fingerprint(authority)
    set_row = StoryboardMaterializationSet(
        id=set_id, book_id=book_id, episode=episode, scene_id=shot.scene_id, shot_plan_id=1, shot_plan_revision=1,
        shot_plan_payload_hash="fixture-shot-plan", shot_plan_authority_fingerprint="", expected_shot_count=1, materialized_shot_count=1,
        ordered_plan_shot_ids=json.dumps([plan_shot_id]), set_payload_fingerprint="set-1", materializer_version="fixture", materializer_policy_version="fixture",
        authority_envelope_json=json.dumps(authority, ensure_ascii=False, sort_keys=True), status="MATERIALIZED", stale_status="FRESH", stale_reasons="[]", created_at=now, activated_at=now, updated_at=now,
    )
    session.add(set_row)
    session.add(StoryboardMaterializationPointer(book_id=book_id, episode=episode, scene_id=shot.scene_id, materialization_set_id=set_id, shot_plan_id=1, shot_plan_revision=1, set_payload_fingerprint="set-1", qualification_state="MATERIALIZED", created_at=now, updated_at=now))
    session.flush()
    return shot, source_row, authority


def resolve_fixture_materialization(session, *, book_id: int, episode: int, scene_id: str, **_kwargs):
    set_row = session.query(StoryboardMaterializationSet).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
    if set_row is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail={"code": "STORYBOARD_MATERIALIZATION_POINTER_MISSING", "message": "Fixture materialization pointer is missing."})
    rows = session.query(StoryboardShot).filter_by(book_id=book_id, episode=episode, scene_id=scene_id, materialization_set_id=set_row.id).order_by(StoryboardShot.shot_id).all()
    envelope = json.loads(set_row.authority_envelope_json or "{}")
    return set_row, rows, envelope


def compile_fixture_prompt(*, snapshot: dict, source_row: dict, storyboard_shot_id: int, target_media: str = "IMAGE", policy: dict | None = None) -> dict:
    policy = dict(policy or {"mode": "TEXT_TO_IMAGE", "target_media": target_media})
    policy["target_media"] = target_media
    compiled = compile_storyboard_snapshot_to_prompt_ir(snapshot, generation_policy=policy, allow_default_policy=True)
    ir = next(item for item in compiled if item.get("plan_shot_id") == source_row.get("plan_shot_id"))
    ir = copy.deepcopy(ir)
    ir["storyboard_shot_id"] = storyboard_shot_id
    ir["source_authority"]["storyboard_materialization_set_id"] = 1
    ir["source_authority"]["storyboard_set_payload_fingerprint"] = "set-1"
    ir["generation_policy"]["target_media"] = target_media
    payload_hash = fingerprint({key: value for key, value in ir.items() if key not in {"prompt_ir_payload_fingerprint", "payload_hash"}})
    ir["prompt_ir_payload_fingerprint"] = payload_hash
    ir["payload_hash"] = payload_hash
    return ir


def build_snapshot_from_fixture(session, *, shot: StoryboardShot, authority: dict) -> dict:
    set_row = session.query(StoryboardMaterializationSet).filter_by(id=shot.materialization_set_id).one()
    rows = session.query(StoryboardShot).filter_by(materialization_set_id=set_row.id, book_id=shot.book_id, episode=shot.episode).order_by(StoryboardShot.shot_id).all()
    return build_storyboard_production_snapshot(materialization_set=set_row, rows=rows, authority_envelope=authority)
