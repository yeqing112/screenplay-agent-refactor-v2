from __future__ import annotations

import json
import copy

from datetime import datetime

from core.visual_asset_authority import build_asset_key, fingerprint, scope_key
from models import (
    GenerationExecutionRecord,
    MediaCandidateRecord,
    OfficialMediaAuthority,
    OfficialMediaPointer,
    OfficialMediaVersion,
    PromptIRPointer,
    PromptIRVersion,
    Session,
    ShotPlan,
    StoryboardShot,
    VisualAssetPointer,
    VisualAssetVersion,
)
from tests.phase_b_contract_fixtures import build_phase_b_production_blocking_candidate
from tests.test_scene_blocking_authority_contract import (
    SceneBlockingAuthorityContractTests as _AuthorityFixture,
)

_AuthorityFixture.__test__ = False


def _human_proposal(plan: dict, blocking: dict) -> dict:
    requirements = plan["phase_c_contract"]["requirements"]
    requirement = requirements[0]
    beat_ref = requirement["beat_refs"][0]
    state = next(
        item
        for item in blocking.get("beat_spatial_states", [])
        if str(item.get("beat_ref")) == str(beat_ref)
    )
    subjects = list(requirement.get("required_subjects") or ["SCENE_CAST"])
    subject_zones = {
        str(key): (value.get("zone") if isinstance(value, dict) else value)
        for key, value in (state.get("characters") or {}).items()
    }
    subject_zones.setdefault("SCENE_CAST", "playing_area")
    roles = list(requirement["required_coverages"])
    return {
        "scene_id": plan["scene_id"],
        "scene_name": plan["scene_name"],
        "shots": [
            {
                "plan_shot_id": "S01",
                "scene_id": plan["scene_id"],
                "requirement_refs": [requirement["requirement_id"]],
                "beat_refs": [beat_ref],
                "director_decision_refs": list(requirement.get("director_decision_refs") or []),
                "shot_purpose": "FOLLOW_ACTION",
                "coverage_roles": roles,
                "reaction_contract_refs": list(requirement.get("reaction_contract_refs") or []),
                "subjects": subjects,
                "spatial_binding": {
                    "blocking_state_refs": [beat_ref],
                    "subject_zones": subject_zones,
                    "prop_refs": list(requirement.get("required_prop_refs") or []),
                },
                "camera_state": {
                    "framing_class": "MEDIUM",
                    "orientation": "EYE_LEVEL",
                    "support": "STATIC",
                    "movement": "NONE",
                    "subject_binding": subjects,
                },
                "axis_contract": {
                    "axis_applicability": "NOT_APPLICABLE",
                    "axis_ref": "",
                    "axis_refs": [],
                    "axis_policy": "PRESERVE",
                },
                "information_visibility": "CHARACTER_AND_AUDIENCE",
                "temporal_intent": {
                    "duration_mode": "ACTION_COMPLETION",
                    "cut_trigger": beat_ref,
                },
                "duration_hint_seconds": 3,
                "continuous_take": True,
                "cut_events": [],
                "action_beats": [
                    {
                        "action_id": f"{beat_ref}_A01",
                        "actor": subjects[0] if subjects else "SCENE_CAST",
                        "action": "两人对视",
                        "start_seconds": 0,
                        "end_seconds": 3,
                    }
                ],
                "entry_state": {},
                "exit_state": {},
                "asset_bindings": {
                    "scene": plan["scene_id"],
                    "characters": subjects,
                    "props": list(requirement.get("required_prop_refs") or []),
                },
            }
        ],
        "authoring_provenance": {
            "proposal_origin": "HUMAN_INPUT",
            "authoring": {"human_input": True},
        },
    }


def _install_visual_assets(book_id: int) -> None:
    now = datetime.now()
    with Session() as session:
        for asset_type, canonical_id in (("scene", "E01_SC001"), ("character", "SCENE_CAST")):
            key = build_asset_key(book_id=book_id, asset_type=asset_type, canonical_id=canonical_id)
            payload = {
                "schema_version": "visual_asset_authority_contract_v1",
                "asset_key": key,
                "asset_type": asset_type,
                "canonical_identity": {"id": canonical_id},
                "scope": {},
                "canonical_spec": {"identity": canonical_id},
                "authoring_spec": {},
                "variant_spec": {},
            }
            payload_hash = fingerprint(payload)
            version = VisualAssetVersion(
                book_id=book_id,
                asset_key=key,
                asset_type=asset_type,
                canonical_id=canonical_id,
                canonical_identity_json=json.dumps(payload["canonical_identity"]),
                scope_json="{}",
                revision=1,
                payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
                payload_hash=payload_hash,
                source_constraints_json="[]",
                authoring_decisions_json="[]",
                variant_binding_json="{}",
                source_constraint_fingerprint=fingerprint([]),
                authoring_decision_fingerprint=fingerprint({}),
                variant_fingerprint=fingerprint({}),
                authority_status="PRODUCTION_READY",
                stale_status="FRESH",
                stale_reasons="[]",
                created_at=now,
                updated_at=now,
            )
            session.add(version)
            session.flush()
            session.add(
                VisualAssetPointer(
                    book_id=book_id,
                    asset_key=key,
                    asset_type=asset_type,
                    scope_key=scope_key(asset_key=key, scope={}),
                    current_version_id=version.id,
                    payload_hash=payload_hash,
                    authority_status="PRODUCTION_READY",
                    stale_status="FRESH",
                    stale_reasons="[]",
                    created_at=now,
                    updated_at=now,
                )
            )
        session.commit()


def _expand_proposal(proposal: dict) -> dict:
    base = proposal["shots"][0]
    shots = []
    for index in range(1, 4):
        shot = copy.deepcopy(base)
        shot["plan_shot_id"] = f"S0{index}"
        shot["action_beats"][0]["action_id"] = f"B01_A0{index}"
        if index > 1:
            shot["axis_contract"]["axis_policy"] = "MOTIVATED_CROSS"
        shots.append(shot)
    return {**proposal, "shots": shots}


def _execute_public(client, *, book_id: int, shot_id: int, target_media: str, generation_mode: str):
    profile_id = "builtin-mock-image" if target_media == "IMAGE" else "builtin-mock-video"
    preview = client.post(
        f"/api/books/{book_id}/episodes/1/shots/{shot_id}/generation/preview",
        json={
            "model_profile_id": profile_id,
            "target_media": target_media,
            "generation_mode": generation_mode,
        },
    )
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    execute_payload = {
        "execute": True,
        "confirmation_token": preview_body["confirmation_token"],
        "preview_execution_id": preview_body["execution"]["execution_id"],
    }
    executed = client.post(
        f"/api/books/{book_id}/episodes/1/shots/{shot_id}/generation/execute",
        json=execute_payload,
    )
    assert executed.status_code == 200, executed.text
    replay = client.post(
        f"/api/books/{book_id}/episodes/1/shots/{shot_id}/generation/execute",
        json=execute_payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json().get("reused") is True
    assert replay.json().get("provider_calls") == 0
    return preview_body, executed.json(), replay.json(), execute_payload


def _persist_official_image(
    book_id: int,
    shot_id: int,
    *,
    execution_id: str,
    revision: int = 1,
) -> None:
    now = datetime.now()
    with Session() as session:
        execution = session.query(GenerationExecutionRecord).filter_by(execution_id=execution_id).one_or_none()
        assert execution is not None
        assert execution.book_id == book_id
        assert execution.episode == 1
        assert execution.storyboard_shot_id == shot_id
        assert execution.target_media == "IMAGE"
        assert execution.status in {"SUCCEEDED", "REUSED"}
        candidate = session.query(MediaCandidateRecord).filter_by(execution_id=execution.execution_id).one()
        prompt_pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=1, storyboard_shot_id=shot_id, target_media="IMAGE").one()
        prompt_version = session.query(PromptIRVersion).filter_by(id=prompt_pointer.prompt_ir_version_id).one()
        official_version_id = f"pilot-official-image-{book_id}-{shot_id}-v{revision}"
        authority_id = f"pilot-oma-image-{book_id}-{shot_id}-v{revision}"
        official = OfficialMediaVersion(
            official_media_version_id=official_version_id,
            book_id=book_id,
            episode=1,
            storyboard_shot_id=shot_id,
            plan_shot_id="",
            media_role="SHOT_PRIMARY_IMAGE",
            media_type="IMAGE",
            candidate_id=candidate.candidate_id,
            candidate_fingerprint=fingerprint({"candidate_id": candidate.candidate_id, "execution_id": execution.execution_id}),
            storage_identity=candidate.storage_identity,
            checksum_sha256=candidate.checksum_sha256,
            mime_type=candidate.mime_type,
            byte_size=candidate.byte_size,
            width=candidate.width,
            height=candidate.height,
            duration_ms=candidate.duration_ms,
            prompt_ir_version_id=prompt_version.id,
            prompt_ir_payload_hash=prompt_version.payload_hash,
            generation_payload_fingerprint=execution.generation_payload_fingerprint,
            provider_request_fingerprint=execution.provider_request_fingerprint,
            provider_response_hash=execution.provider_response_hash,
            validation_id=f"pilot-validation-{book_id}-{shot_id}-v{revision}",
            validation_fingerprint=fingerprint({"candidate_id": candidate.candidate_id, "revision": revision}),
            revision=revision,
            status="CURRENT",
            payload_hash=fingerprint({"official_media_version_id": official_version_id, "candidate_id": candidate.candidate_id, "revision": revision}),
            created_at=now,
        )
        session.add(official)
        session.flush()
        session.add(
            OfficialMediaAuthority(
                authority_id=authority_id,
                official_media_version_id=official_version_id,
                authority_envelope_json="{}",
                payload_hash=official.payload_hash,
                lineage_hash=fingerprint({"official_media_version_id": official_version_id}),
                validation_fingerprint=official.validation_fingerprint,
                promotion_fingerprint=fingerprint({"authority_id": authority_id}),
                status="CURRENT",
                created_at=now,
            )
        )
        pointer = session.query(OfficialMediaPointer).filter_by(book_id=book_id, episode=1, storyboard_shot_id=shot_id, media_role="SHOT_PRIMARY_IMAGE").first()
        if pointer is None:
            pointer = OfficialMediaPointer(
                book_id=book_id,
                episode=1,
                storyboard_shot_id=shot_id,
                media_role="SHOT_PRIMARY_IMAGE",
                official_media_version_id=official_version_id,
                authority_id=authority_id,
                fingerprint=fingerprint({"official_media_version_id": official_version_id, "authority_id": authority_id}),
                created_at=now,
                updated_at=now,
            )
            session.add(pointer)
        else:
            pointer.official_media_version_id = official_version_id
            pointer.authority_id = authority_id
            pointer.fingerprint = fingerprint({"official_media_version_id": official_version_id, "authority_id": authority_id})
            pointer.updated_at = now
        session.commit()


def test_public_pilot_reaches_materialization_and_phase_e_without_resolver_monkeypatch():
    _AuthorityFixture.setUpClass()
    fixture = _AuthorityFixture("test_contract_classifies_authority_layers")
    fixture.setUp()
    client = fixture.client
    try:
        blocking_preview = client.post(
            f"/api/books/{fixture.book_id}/episodes/1/scene-blocking/preview",
            json={"persist": True, "workflowProfile": "production", "sceneId": "E01_SC001"},
        )
        assert blocking_preview.status_code == 200, blocking_preview.text
        blocking_body = blocking_preview.json()
        blocking_confirm = client.post(
            f"/api/books/{fixture.book_id}/episodes/1/scene-blocking/confirm",
            json={
                "blockingId": blocking_body["persisted_draft_id"],
                "evidenceFingerprint": blocking_body["blocking"]["evidence_fingerprint"],
                "confirmed": True,
                "workflowProfile": "production",
                "schemaVersion": "scene_blocking_v2",
                "blocking": build_phase_b_production_blocking_candidate(blocking_body["blocking"]),
            },
        )
        assert blocking_confirm.status_code == 200, blocking_confirm.text

        plan_preview = client.post(
            f"/api/books/{fixture.book_id}/episodes/1/shot-plan/preview",
            json={"persist": True, "workflowProfile": "production", "sceneId": "E01_SC001"},
        )
        assert plan_preview.status_code == 200, plan_preview.text
        plan_body = plan_preview.json()
        plan = plan_body["plan"]
        with Session() as session:
            draft = session.query(ShotPlan).filter_by(id=plan_body["persisted_draft_id"], book_id=fixture.book_id).one()
            model_info = json.loads(draft.model_info or "{}")
            model_info["shot_design_status"] = "AUTHORING_REQUIRED"
            draft.model_info = json.dumps(model_info, ensure_ascii=False)
            session.commit()

        proposal = _expand_proposal(_human_proposal(plan, blocking_body["blocking"]))
        plan_confirm = client.post(
            f"/api/books/{fixture.book_id}/episodes/1/shot-plan/confirm",
            json={
                "planId": plan_body["persisted_draft_id"],
                "evidenceFingerprint": plan["evidence_fingerprint"],
                "confirmed": True,
                "workflowProfile": "production",
                "shotDesignProposal": proposal,
                "proposalProvenance": proposal["authoring_provenance"],
            },
        )
        assert plan_confirm.status_code == 200, json.dumps(plan_confirm.json(), ensure_ascii=False, indent=2)
        assert plan_confirm.json()["shot_plan"]["model_info"]["phase_c_semantic_ready"] is True

        materialized = client.post(
            f"/api/books/{fixture.book_id}/episodes/1/storyboard/materialize",
            json={"confirmed": True},
        )
        assert materialized.status_code == 200, materialized.text
        assert materialized.json()["materialized_count"] == 3
        _install_visual_assets(fixture.book_id)
        with Session() as session:
            shot_ids = {
                row.plan_shot_id: row.id
                for row in session.query(StoryboardShot).filter_by(book_id=fixture.book_id, episode=1).all()
            }
        assert set(shot_ids) == {"S01", "S02", "S03"}

        compiled = client.post(
            f"/api/books/{fixture.book_id}/episodes/1/prompt-ir/compile",
            json={"generation_policy": {"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE"}},
        )
        assert compiled.status_code == 200, compiled.text
        assert compiled.json()["compiled_count"] == 3

        image_preview, image_result, image_replay, _ = _execute_public(
            client,
            book_id=fixture.book_id,
            shot_id=shot_ids["S01"],
            target_media="IMAGE",
            generation_mode="TEXT_TO_IMAGE",
        )
        assert image_result.get("provider_calls") == 1
        assert image_result["candidate"]["media_type"] == "IMAGE"
        print("IMAGE_RESULT", json.dumps(image_result, ensure_ascii=False))
        _persist_official_image(
            fixture.book_id,
            shot_ids["S01"],
            execution_id=image_result["execution"]["execution_id"],
        )

        compiled_video = client.post(
            f"/api/books/{fixture.book_id}/episodes/1/prompt-ir/compile",
            json={"generation_policy": {"mode": "TEXT_TO_VIDEO", "target_media": "VIDEO", "duration_seconds": 1}},
        )
        assert compiled_video.status_code == 200, compiled_video.text
        assert compiled_video.json()["compiled_count"] == 3
        video_preview, video_result, video_replay, _ = _execute_public(
            client,
            book_id=fixture.book_id,
            shot_id=shot_ids["S02"],
            target_media="VIDEO",
            generation_mode="TEXT_TO_VIDEO",
        )
        assert video_result.get("provider_calls") == 1
        assert video_result["candidate"]["media_type"] == "VIDEO"

        compiled_image_to_video = client.post(
            f"/api/books/{fixture.book_id}/episodes/1/prompt-ir/compile",
            json={"generation_policy": {"mode": "IMAGE_TO_VIDEO", "target_media": "VIDEO", "duration_seconds": 1}},
        )
        assert compiled_image_to_video.status_code == 200, compiled_image_to_video.text
        itv_preview, itv_result, itv_replay, _ = _execute_public(
            client,
            book_id=fixture.book_id,
            shot_id=shot_ids["S01"],
            target_media="VIDEO",
            generation_mode="IMAGE_TO_VIDEO",
        )
        assert itv_preview["authority_fingerprints"]["source_binding"]["media_role"] == "SHOT_PRIMARY_IMAGE"
        assert itv_result.get("provider_calls") == 1
        assert itv_result["candidate"]["media_type"] == "VIDEO"

        with Session() as session:
            terminal = (
                session.query(GenerationExecutionRecord)
                .filter(
                    GenerationExecutionRecord.book_id == fixture.book_id,
                    GenerationExecutionRecord.episode == 1,
                    GenerationExecutionRecord.status.in_(["SUCCEEDED", "REUSED"]),
                )
                .all()
            )
            candidates = session.query(MediaCandidateRecord).filter_by().all()
            official = session.query(OfficialMediaPointer).filter_by(book_id=fixture.book_id, episode=1).all()
        assert len(terminal) == 3
        assert len([row for row in candidates if row.execution_id in {item["execution"]["execution_id"] for item in (image_result, video_result, itv_result)}]) == 3
        assert len(official) == 1
    finally:
        fixture.tearDown()
