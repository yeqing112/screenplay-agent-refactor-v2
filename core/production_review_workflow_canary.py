"""Provider-free canary for the human Production Asset Review workflow."""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Mapping

from core.production_asset_authority import bind_shot_assets, resolve_shot_assets
from core.production_asset_graph_canary import (
    BOOK_ID,
    EPISODE,
    build_production_asset_graph_fixture,
    reconcile_production_asset_graph_canary,
    validate_production_asset_graph,
)
from core.production_asset_review import (
    SCHEMA_VERSION as REVIEW_SCHEMA_VERSION,
    ProductionAssetReviewGateError,
    activate_production_asset_version_after_review,
    create_new_version_after_request_change,
    create_production_asset_review,
    review_history,
    run_review_path,
    transition_production_asset_review,
)
from models import (
    CharacterAssetAuthority,
    CharacterAssetVersion,
    ProductionAssetReview,
    ProductionAssetReviewHistory,
    SceneAssetAuthority,
    SceneAssetVersion,
    ShotAssetBinding,
    StoryboardShot,
)


SCHEMA_VERSION = "production_review_workflow_canary_v1"
WORKFLOW_STAGE = "PHASE_PRODUCTION_REVIEW_WORKFLOW_CANARY_COMPLETE"
WORKFLOW_APPROVAL_STATE = "PRODUCTION_REVIEW_CANARY_APPROVED"


def build_production_review_workflow_fixture() -> dict[str, Any]:
    graph = build_production_asset_graph_fixture()
    return {
        "schema_version": SCHEMA_VERSION,
        "book_id": BOOK_ID,
        "episode": EPISODE,
        "provider_free": True,
        "provider_calls": 0,
        "graph_fixture": graph,
        "review_cases": [
            {
                "case_id": "approved_character_a_v3",
                "asset_type": "CHARACTER",
                "asset_id": "CHARACTER_A",
                "logical_version": "v3",
                "reviewer_type": "DIRECTOR",
                "decision": "APPROVE",
                "expected_final_state": "PRODUCTION_READY",
            },
            {
                "case_id": "rejected_character_b_v2",
                "asset_type": "CHARACTER",
                "asset_id": "CHARACTER_B",
                "logical_version": "v2",
                "reviewer_type": "ART_DIRECTOR",
                "decision": "REJECT",
                "expected_final_state": "REJECTED",
            },
            {
                "case_id": "request_change_scene_street_v1",
                "asset_type": "SCENE",
                "asset_id": "SCENE_STREET",
                "logical_version": "v1",
                "reviewer_type": "PRODUCER",
                "decision": "REQUEST_CHANGE",
                "expected_final_state": "ARCHIVED",
            },
        ],
        "request_change_replacement": {
            "asset_type": "SCENE",
            "asset_id": "SCENE_STREET",
            "from_logical_version": "v1",
            "new_logical_version": "v2",
            "storage_identity": "https://assets.example.invalid/production-review/scene/scene-street/v2.png",
            "checksum": "sha256:production-review-scene-street-v2",
            "metadata": {
                "schema_version": "production_asset_media_metadata_v1",
                "source_kind": "production_review_workflow_canary",
                "logical_version": "v2",
                "mime_type": "image/png",
                "width": 2048,
                "height": 2048,
                "provenance": {
                    "source_reference": "provider-response://production-review-workflow-canary/v1/SCENE_STREET/v2",
                    "provider_response_id": "production-review-scene-street-v2",
                    "provider_output_fingerprint": "sha256:production-review-scene-street-v2",
                    "captured_at": "2026-09-26T00:00:00Z",
                    "provider": "fixture-provider",
                    "fixture_mode": True,
                    "is_mock": False,
                },
            },
        },
    }


def _typed_version(session: Any, *, asset_type: str, asset_id: str, revision: int):
    model = CharacterAssetVersion if asset_type == "CHARACTER" else SceneAssetVersion
    field = "character_id" if asset_type == "CHARACTER" else "scene_id"
    return session.query(model).filter_by(**{field: asset_id, "revision": revision}).one()


def _current_asset(session: Any, *, asset_type: str, asset_id: str) -> dict[str, str]:
    model = CharacterAssetAuthority if asset_type == "CHARACTER" else SceneAssetAuthority
    field = "character_id" if asset_type == "CHARACTER" else "scene_id"
    authority = session.query(model).filter_by(**{field: asset_id}).one()
    return {"authority_id": str(authority.authority_id), "version_id": str(authority.current_version_id)}


def _bind_current_requirements(session: Any, *, fixture: Mapping[str, Any], shot_raw: Mapping[str, Any], shot: StoryboardShot) -> None:
    character_id = next(item["entity_id"] for item in shot_raw["requirements"] if item["asset_type"] == "CHARACTER")
    scene_id = next(item["entity_id"] for item in shot_raw["requirements"] if item["asset_type"] == "SCENE")
    bind_shot_assets(
        session,
        storyboard_shot_id=int(shot.id),
        characters=[_current_asset(session, asset_type="CHARACTER", asset_id=character_id)],
        scene=_current_asset(session, asset_type="SCENE", asset_id=scene_id),
        props=[],
    )


def _rebind_entity_shots(session: Any, *, fixture: Mapping[str, Any], asset_type: str, asset_id: str) -> None:
    shots = session.query(StoryboardShot).filter_by(book_id=int(fixture["book_id"]), episode=int(fixture["episode"])).order_by(StoryboardShot.shot_id.asc()).all()
    for shot, raw in zip(shots, fixture["graph_fixture"]["shots"]):
        if any(item["asset_type"] == asset_type and item["entity_id"] == asset_id for item in raw["requirements"]):
            _bind_current_requirements(session, fixture=fixture, shot_raw=raw, shot=shot)


def _review_counts(session: Any) -> dict[str, int]:
    reviews = session.query(ProductionAssetReview).all()
    return {
        "review_count": len(reviews),
        "review_history_count": int(session.query(ProductionAssetReviewHistory).count()),
        "approved_asset_count": sum(row.review_state == "PRODUCTION_READY" for row in reviews),
        "rejected_asset_count": sum(row.review_state == "REJECTED" for row in reviews),
        "archived_review_count": sum(row.review_state == "ARCHIVED" for row in reviews),
        "blocked_promotion_count": 0,
    }


def reconcile_production_review_workflow_canary(session: Any, fixture: Mapping[str, Any] | None = None) -> dict[str, Any]:
    fixture = deepcopy(dict(fixture or build_production_review_workflow_fixture()))
    graph_fixture = fixture["graph_fixture"]
    graph_result = reconcile_production_asset_graph_canary(session, graph_fixture) if session is not None else reconcile_production_asset_graph_canary(None, graph_fixture)
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "stage": "PHASE_PRODUCTION_REVIEW_WORKFLOW_CANARY_BLOCKED",
        "provider_calls": int(fixture.get("provider_calls") or 0),
        "approval_state": "REJECTED",
        "episode_count": 1,
        "shot_count": len(graph_fixture.get("shots") or []),
        "graph_result": graph_result,
        "review_cases": deepcopy(fixture.get("review_cases") or []),
        "review_counts": {},
        "promotion_attempts": [],
    }
    if session is None:
        result["stage"] = "PHASE_PRODUCTION_REVIEW_WORKFLOW_CANARY_RECONCILE_READY"
        result["approval_state"] = "RECONCILE_READY"
        return result

    nested = session.begin_nested()
    try:
        a_v3 = _typed_version(session, asset_type="CHARACTER", asset_id="CHARACTER_A", revision=3)
        b_v2 = _typed_version(session, asset_type="CHARACTER", asset_id="CHARACTER_B", revision=2)
        street_v1 = _typed_version(session, asset_type="SCENE", asset_id="SCENE_STREET", revision=1)

        approved = create_production_asset_review(session, asset_type="CHARACTER", asset_id="CHARACTER_A", asset_version_id=a_v3.version_id)
        run_review_path(session, review_id=approved["review_id"], decision="APPROVE", reviewer_type="DIRECTOR")
        before_a_pointer = _current_asset(session, asset_type="CHARACTER", asset_id="CHARACTER_A")["version_id"]
        activated_approved = activate_production_asset_version_after_review(session, review_id=approved["review_id"], book_id=int(fixture["book_id"]))
        _rebind_entity_shots(session, fixture=fixture, asset_type="CHARACTER", asset_id="CHARACTER_A")

        rejected = create_production_asset_review(session, asset_type="CHARACTER", asset_id="CHARACTER_B", asset_version_id=b_v2.version_id)
        run_review_path(session, review_id=rejected["review_id"], decision="REJECT", reviewer_type="ART_DIRECTOR")
        before_b_pointer = _current_asset(session, asset_type="CHARACTER", asset_id="CHARACTER_B")["version_id"]
        blocked = False
        blocked_detail = ""
        try:
            activate_production_asset_version_after_review(session, review_id=rejected["review_id"], book_id=int(fixture["book_id"]))
        except ProductionAssetReviewGateError as exc:
            blocked = True
            blocked_detail = str(exc)
        after_b_pointer = _current_asset(session, asset_type="CHARACTER", asset_id="CHARACTER_B")["version_id"]

        request_change = create_production_asset_review(session, asset_type="SCENE", asset_id="SCENE_STREET", asset_version_id=street_v1.version_id)
        run_review_path(session, review_id=request_change["review_id"], decision="REQUEST_CHANGE", reviewer_type="PRODUCER")
        old_street_pointer = _current_asset(session, asset_type="SCENE", asset_id="SCENE_STREET")["version_id"]
        replacement = create_new_version_after_request_change(
            session,
            review_id=request_change["review_id"],
            source=fixture["request_change_replacement"],
            book_id=int(fixture["book_id"]),
        )
        replacement_review_id = replacement["replacement_review"]["review_id"]
        replacement_review = run_review_path(session, review_id=replacement_review_id, decision="APPROVE", reviewer_type="PRODUCER")
        candidate_pointer_before = _current_asset(session, asset_type="SCENE", asset_id="SCENE_STREET")["version_id"]
        activated_replacement = activate_production_asset_version_after_review(session, review_id=replacement_review_id, book_id=int(fixture["book_id"]))
        _rebind_entity_shots(session, fixture=fixture, asset_type="SCENE", asset_id="SCENE_STREET")

        session.flush()
        shots = session.query(StoryboardShot).filter_by(book_id=int(fixture["book_id"]), episode=int(fixture["episode"])).order_by(StoryboardShot.shot_id.asc()).all()
        graph_validation = validate_production_asset_graph(
            session,
            shot_rows=shots,
            expected_entities=graph_result["expected_entities"],
        )
        for shot in shots:
            resolve_shot_assets(session, storyboard_shot_id=int(shot.id))
        review_rows = session.query(ProductionAssetReview).order_by(ProductionAssetReview.id.asc()).all()
        all_histories = {row.review_id: review_history(session, row.review_id) for row in review_rows}
        counts = _review_counts(session)
        counts["blocked_promotion_count"] = 1 if blocked else 0
        nested.commit()
    except Exception:
        nested.rollback()
        raise

    approved_history = all_histories[approved["review_id"]]
    rejected_history = all_histories[rejected["review_id"]]
    request_history = all_histories[request_change["review_id"]]
    replacement_history = all_histories[replacement_review_id]
    history_ids = [item["history_id"] for history in all_histories.values() for item in history]
    history_transitions_valid = all(
        item["to"] in {"GENERATED", "NORMALIZED", "AI_VALIDATED", "HUMAN_REVIEW_PENDING", "HUMAN_APPROVED", "PRODUCTION_READY", "REJECTED", "REQUEST_CHANGE", "ARCHIVED"}
        for history in all_histories.values() for item in history
    )
    result.update({
        "stage": WORKFLOW_STAGE if not graph_validation["errors"] and blocked else "PHASE_PRODUCTION_REVIEW_WORKFLOW_CANARY_BLOCKED",
        "approval_state": WORKFLOW_APPROVAL_STATE if not graph_validation["errors"] and blocked else "REJECTED",
        "review_counts": counts,
        "graph_counts": graph_result["graph_counts"],
        "final_graph_counts": {
            "authority_count": graph_result["graph_counts"]["authority_registry"],
            "version_count": int(session.query(CharacterAssetVersion).count() + session.query(SceneAssetVersion).count()),
            "pointer_count": int(session.query(CharacterAssetAuthority).count() + session.query(SceneAssetAuthority).count()),
            "shot_count": len(shots),
            "binding_count": int(session.query(ShotAssetBinding).count()),
            "active_binding_count": int(session.query(ShotAssetBinding).filter(ShotAssetBinding.status == "ACTIVE").count()),
            "stale_binding_count": int(session.query(ShotAssetBinding).filter(ShotAssetBinding.status == "STALE").count()),
        },
        "graph_validation": graph_validation,
        "reviews": [{"review": {**{key: getattr(row, key) for key in ("review_id", "asset_type", "asset_id", "asset_version_id", "review_state", "reviewer_type", "decision")}, "history": all_histories[row.review_id]}} for row in review_rows],
        "promotion_attempts": [
            {"case_id": "approved_character_a_v3", "before_pointer_version_id": before_a_pointer, "after_pointer_version_id": activated_approved["switch"]["version_id"], "allowed": True},
            {"case_id": "rejected_character_b_v2", "before_pointer_version_id": before_b_pointer, "after_pointer_version_id": after_b_pointer, "allowed": False, "blocked_detail": blocked_detail},
            {"case_id": "request_change_scene_street_v1", "before_pointer_version_id": old_street_pointer, "candidate_pointer_before_approval": candidate_pointer_before, "after_pointer_version_id": activated_replacement["switch"]["version_id"], "allowed": True},
        ],
        "request_change": {
            "old_review_id": request_change["review_id"],
            "old_review_final_state": session.query(ProductionAssetReview).filter_by(review_id=request_change["review_id"]).one().review_state,
            "old_version_id": street_v1.version_id,
            "new_version_id": replacement["replacement_version"]["version_id"],
            "new_review_id": replacement_review_id,
            "old_history_count": len(request_history),
            "new_history_count": len(replacement_history),
        },
        "source_fact_mutations": graph_result.get("source_gate_mutations", {}).get("fact_snapshots", 0) + graph_result.get("source_gate_mutations", {}).get("fact_records", 0),
        "script_ir_mutations": graph_result.get("source_gate_mutations", {}).get("script_ir_versions", 0),
        "truth_checks": {
            "review_required_before_production": blocked and before_b_pointer == after_b_pointer,
            "approval_transition_valid": all_histories[approved["review_id"]][-1]["to"] == "PRODUCTION_READY" and all_histories[replacement_review_id][-1]["to"] == "PRODUCTION_READY" and history_transitions_valid,
            "review_history_append_only": len(history_ids) == len(set(history_ids)) and all(len(history) >= 5 for history in all_histories.values()),
            "rejected_asset_blocked": blocked and after_b_pointer == before_b_pointer and session.query(ProductionAssetReview).filter_by(review_id=rejected["review_id"], review_state="REJECTED").count() == 1,
            "version_change_preserves_history": session.query(CharacterAssetVersion).filter_by(version_id=a_v3.version_id).count() == 1 and session.query(SceneAssetVersion).filter_by(version_id=street_v1.version_id).count() == 1 and len(request_history) >= 5,
            "pointer_activation_requires_approval": candidate_pointer_before == old_street_pointer and activated_replacement["switch"]["version_id"] != old_street_pointer,
            "source_fact_mutations": int(result.get("source_fact_mutations") or 0),
            "script_ir_mutations": int(result.get("script_ir_mutations") or 0),
        },
    })
    return result


def build_review_workflow_truth_audit(result: Mapping[str, Any]) -> dict[str, Any]:
    checks = dict(result.get("truth_checks") or {})
    required = (
        "review_required_before_production",
        "approval_transition_valid",
        "review_history_append_only",
        "rejected_asset_blocked",
        "version_change_preserves_history",
        "pointer_activation_requires_approval",
    )
    complete = all(bool(checks.get(key)) for key in required) and int(checks.get("source_fact_mutations", 0)) == 0 and int(checks.get("script_ir_mutations", 0)) == 0
    return {
        "schema_version": "production_review_workflow_truth_audit_v1",
        "stage": result.get("stage"),
        "provider_calls": int(result.get("provider_calls") or 0),
        "approval_state": result.get("approval_state"),
        "checks": checks,
        "review_required_before_production": bool(checks.get("review_required_before_production")),
        "approval_transition_valid": bool(checks.get("approval_transition_valid")),
        "review_history_append_only": bool(checks.get("review_history_append_only")),
        "rejected_asset_blocked": bool(checks.get("rejected_asset_blocked")),
        "version_change_preserves_history": bool(checks.get("version_change_preserves_history")),
        "pointer_activation_requires_approval": bool(checks.get("pointer_activation_requires_approval")),
        "source_fact_mutations": int(checks.get("source_fact_mutations", 0)),
        "script_ir_mutations": int(checks.get("script_ir_mutations", 0)),
        "review_counts": result.get("review_counts") or {},
        "graph_counts": result.get("final_graph_counts") or {},
        "complete": complete,
    }


__all__ = [
    "SCHEMA_VERSION",
    "WORKFLOW_STAGE",
    "WORKFLOW_APPROVAL_STATE",
    "build_production_review_workflow_fixture",
    "reconcile_production_review_workflow_canary",
    "build_review_workflow_truth_audit",
]
