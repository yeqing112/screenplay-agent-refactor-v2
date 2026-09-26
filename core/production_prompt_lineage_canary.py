"""Provider-free canary for the complete Prompt -> Asset -> Review trace."""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Mapping

from core.production_asset_graph_canary import build_production_asset_graph_fixture, reconcile_production_asset_graph_canary
from core.production_asset_review import run_review_path, activate_production_asset_version_after_review
from core.production_prompt_lineage import (
    asset_has_prompt_lineage,
    create_production_generation_intent,
    create_production_prompt_lineage,
    create_production_prompt_version,
    create_prompt_change_candidate,
    prompt_fingerprint,
    review_reproducible_generation_context,
    trace_production_asset_version,
)
from models import (
    CharacterAssetVersion,
    ProductionAssetReview,
    ProductionAssetVersionRegistry,
    ProductionGenerationIntent,
    ProductionPromptLineage,
    ProductionPromptVersion,
    SceneAssetVersion,
    StoryboardShot,
)


SCHEMA_VERSION = "production_prompt_lineage_canary_v1"
STAGE = "PHASE_PRODUCTION_PROMPT_LINEAGE_CANARY_COMPLETE"
APPROVAL = "PRODUCTION_PROMPT_LINEAGE_CANARY_APPROVED"


def _source(name: str, revision: int) -> dict[str, Any]:
    return {
        "storage_identity": f"https://assets.example.invalid/prompt-lineage/{name}/v{revision}.png",
        "checksum": f"sha256:prompt-lineage:{name}:{revision}",
        "metadata": {
            "schema_version": "production_asset_media_metadata_v1",
            "source_kind": "production_prompt_lineage_canary",
            "logical_version": f"v{revision}",
            "mime_type": "image/png",
            "width": 2048,
            "height": 2048,
            "provenance": {
                "source_reference": f"fixture://prompt-lineage/{name}/{revision}",
                "provider_response_id": f"prompt-lineage-{name}-{revision}",
                "provider_output_fingerprint": f"sha256:fixture:{name}:{revision}",
                "captured_at": "2026-09-26T00:00:00Z",
                "provider": "fixture-provider",
                "fixture_mode": True,
                "is_mock": False,
            },
        },
    }


def build_production_prompt_lineage_fixture() -> dict[str, Any]:
    graph = build_production_asset_graph_fixture()
    prompt_specs = []
    for shot in range(1, 11):
        prompt_specs.append({"prompt_id": f"shot-{shot:03d}", "prompt_text": f"Production shot {shot}: preserve the declared subject, scene and camera intent."})
    for shot in range(1, 6):
        prompt_specs.append({"prompt_id": f"shot-{shot:03d}", "prompt_text": f"Production shot {shot}: preserve the declared subject, scene, camera and continuity intent v2."})
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "book_id": graph["book_id"],
        "episode": graph["episode"],
        "provider_free": True,
        "provider_calls": 0,
        "graph_fixture": graph,
        "prompt_specs": prompt_specs,
        "prompt_change": {
            "prompt_id": "prompt-change-character-b",
            "prompt_v1": "Character B enters the office and pauses at the evidence wall.",
            "prompt_v2": "Character B enters the office, pauses at the evidence wall, and turns toward the withheld clue.",
            "asset_name": "character-b-prompt-change",
        },
    }


def _entity_for_version(version: Any) -> tuple[str, str]:
    for field, kind in (("character_id", "CHARACTER"), ("scene_id", "SCENE")):
        value = getattr(version, field, None)
        if value:
            return kind, str(value)
    raise ValueError(f"unsupported production version row: {version!r}")


def _asset_versions(session: Any) -> list[Any]:
    return list(session.query(CharacterAssetVersion).order_by(CharacterAssetVersion.id.asc()).all()) + list(session.query(SceneAssetVersion).order_by(SceneAssetVersion.id.asc()).all())


def _shot_for_entity(fixture: Mapping[str, Any], *, asset_type: str, asset_id: str) -> Mapping[str, Any]:
    for shot in fixture["graph_fixture"]["shots"]:
        if any(item["asset_type"] == asset_type and item["entity_id"] == asset_id for item in shot["requirements"]):
            return shot
    raise ValueError(f"no shot requirement for {asset_type}/{asset_id}")


def _intent_by_shot(session: Any, fixture: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    result = {}
    for raw in fixture["graph_fixture"]["shots"]:
        shot = session.query(StoryboardShot).filter_by(shot_id=int(raw["shot_id"])).one()
        requirement = {"shot_id": int(raw["shot_id"]), "plan_shot_id": raw["plan_shot_id"], "requirements": raw["requirements"]}
        result[int(raw["shot_id"])] = create_production_generation_intent(
            session,
            shot_id=int(shot.id),
            shot_requirement=requirement,
            character_requirements={"required": [item["entity_id"] for item in raw["requirements"] if item["asset_type"] == "CHARACTER"]},
            scene_requirements={"required": [item["entity_id"] for item in raw["requirements"] if item["asset_type"] == "SCENE"]},
            camera_requirements={"shot_size": "MS", "movement": "static"},
            style_requirements={"continuity": "preserve declared shot requirement"},
            constraint_snapshot={"source": "SHOT_REQUIREMENT", "provider_calls": 0},
        )
    return result


def reconcile_production_prompt_lineage_canary(session: Any, fixture: Mapping[str, Any] | None = None) -> dict[str, Any]:
    fixture = deepcopy(dict(fixture or build_production_prompt_lineage_fixture()))
    graph = reconcile_production_asset_graph_canary(session, fixture["graph_fixture"])
    result: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "stage": "PHASE_PRODUCTION_PROMPT_LINEAGE_CANARY_BLOCKED", "approval_state": "REJECTED", "provider_calls": 0, "graph_result": graph}
    if session is None:
        result["stage"] = "PHASE_PRODUCTION_PROMPT_LINEAGE_CANARY_RECONCILE_READY"
        result["approval_state"] = "RECONCILE_READY"
        return result

    intents = _intent_by_shot(session, fixture)
    prompt_rows = []
    for spec in fixture["prompt_specs"]:
        prompt_rows.append(create_production_prompt_version(session, prompt_id=spec["prompt_id"], prompt_text=spec["prompt_text"], prompt_structure={"media": "IMAGE", "shot_requirement": spec["prompt_id"]}))
    same_a = create_production_prompt_version(session, prompt_id="fingerprint-check", prompt_text="same deterministic prompt", prompt_structure={"camera": "MS"})
    same_b = create_production_prompt_version(session, prompt_id="fingerprint-check", prompt_text="same deterministic prompt", prompt_structure={"camera": "MS"})
    changed = create_production_prompt_version(session, prompt_id="fingerprint-check", prompt_text="changed deterministic prompt", prompt_structure={"camera": "MS"})

    lineages = []
    for version in _asset_versions(session):
        asset_type, asset_id = _entity_for_version(version)
        if asset_type == "CHARACTER" and asset_id == "CHARACTER_B" and int(version.revision) == 1:
            # This version is the rejected Prompt v1 branch below.
            continue
        shot = _shot_for_entity(fixture, asset_type=asset_type, asset_id=asset_id)
        shot_row = session.query(StoryboardShot).filter_by(shot_id=int(shot["shot_id"])).one()
        prompt = session.query(ProductionPromptVersion).filter_by(prompt_id=f"shot-{int(shot['shot_id']):03d}").order_by(ProductionPromptVersion.version_number.asc()).first()
        lineages.append(create_production_prompt_lineage(session, asset_type=asset_type, asset_id=asset_id, asset_version_id=version.version_id, shot_id=int(shot_row.id), prompt_version_id=prompt.prompt_version_id, generation_intent_id=intents[int(shot["shot_id"])] ["generation_intent_id"]))

    # Every pre-existing asset version has a review record tied to its lineage.
    review_rows = []
    for lineage in lineages:
        review = __import__("core.production_asset_review", fromlist=["create_production_asset_review"]).create_production_asset_review(
            session,
            asset_type=lineage["asset_type"],
            asset_id=lineage["asset_id"],
            asset_version_id=lineage["asset_version_id"],
            prompt_lineage_id=lineage["prompt_lineage_id"],
        )
        run_review_path(session, review_id=review["review_id"], decision="APPROVE", reviewer_type="DIRECTOR")
        review_rows.append(review["review_id"])

    change_entity = "CHARACTER_B"
    old_version = session.query(CharacterAssetVersion).filter_by(character_id=change_entity, revision=1).one()
    change_shot = _shot_for_entity(fixture, asset_type="CHARACTER", asset_id=change_entity)
    change_shot_row = session.query(StoryboardShot).filter_by(shot_id=int(change_shot["shot_id"])).one()
    old_prompt = create_production_prompt_version(session, prompt_id=fixture["prompt_change"]["prompt_id"], prompt_text=fixture["prompt_change"]["prompt_v1"], prompt_structure={"case": "PROMPT_CHANGE"})
    old_intent = intents[int(change_shot["shot_id"])]
    old_lineage = create_production_prompt_lineage(session, asset_type="CHARACTER", asset_id=change_entity, asset_version_id=old_version.version_id, shot_id=int(change_shot_row.id), prompt_version_id=old_prompt["prompt_version_id"], generation_intent_id=old_intent["generation_intent_id"])
    old_review = __import__("core.production_asset_review", fromlist=["create_production_asset_review"]).create_production_asset_review(session, asset_type="CHARACTER", asset_id=change_entity, asset_version_id=old_version.version_id, prompt_lineage_id=old_lineage["prompt_lineage_id"])
    run_review_path(session, review_id=old_review["review_id"], decision="REJECT", reviewer_type="ART_DIRECTOR")
    candidate = create_prompt_change_candidate(session, old_asset_type="CHARACTER", old_asset_id=change_entity, old_asset_version_id=old_version.version_id, shot_id=int(change_shot_row.id), prompt_id=fixture["prompt_change"]["prompt_id"], prompt_text=fixture["prompt_change"]["prompt_v2"], prompt_structure={"case": "PROMPT_CHANGE", "revision": 2}, shot_requirement={"shot_id": int(change_shot["shot_id"]), "requirements": change_shot["requirements"]}, source=_source(fixture["prompt_change"]["asset_name"], 2))
    run_review_path(session, review_id=candidate["review"]["review_id"], decision="APPROVE", reviewer_type="DIRECTOR")
    activated = activate_production_asset_version_after_review(session, review_id=candidate["review"]["review_id"])

    session.flush()
    all_versions = _asset_versions(session)
    trace_rows = [trace_production_asset_version(session, row.version_id) for row in all_versions]
    reproducible = [review_reproducible_generation_context(session, review_id) for review_id in review_rows + [old_review["review_id"], candidate["review"]["review_id"]]]
    lineage_rows = session.query(ProductionPromptLineage).all()
    fingerprint_valid = all(row.prompt_fingerprint == session.query(ProductionPromptVersion).filter_by(prompt_version_id=row.prompt_version_id).one().prompt_fingerprint for row in lineage_rows)
    all_lineaged = all(asset_has_prompt_lineage(session, row.version_id) for row in all_versions)
    review_ids = [item.review_id for item in session.query(ProductionAssetReview).order_by(ProductionAssetReview.id).all()]
    result.update({
        "stage": STAGE,
        "approval_state": APPROVAL,
        "episode_count": 1,
        "shot_count": session.query(StoryboardShot).filter_by(book_id=int(fixture["book_id"]), episode=int(fixture["episode"])).count(),
        "counts": {
            "prompt_count": session.query(ProductionPromptVersion.prompt_id).distinct().count(),
            "prompt_version_count": session.query(ProductionPromptVersion).count(),
            "generation_intent_count": session.query(ProductionGenerationIntent).count(),
            "asset_count": len(all_versions),
            "shot_count": session.query(StoryboardShot).filter_by(book_id=int(fixture["book_id"]), episode=int(fixture["episode"])).count(),
            "review_count": session.query(ProductionAssetReview).count(),
            "lineage_count": len(lineage_rows),
        },
        "fingerprint_checks": {"same_prompt_same_fingerprint": prompt_fingerprint("same deterministic prompt", {"camera": "MS"}) == same_a["prompt_fingerprint"] == same_b["prompt_fingerprint"], "different_prompt_different_fingerprint": same_a["prompt_fingerprint"] != changed["prompt_fingerprint"]},
        "prompt_change": {"old_prompt_version_id": old_prompt["prompt_version_id"], "new_prompt_version_id": candidate["prompt_version"]["prompt_version_id"], "old_asset_version_id": old_version.version_id, "new_asset_version_id": candidate["asset"]["version_id"], "old_review_id": old_review["review_id"], "new_review_id": candidate["review"]["review_id"], "old_review_state": session.query(ProductionAssetReview).filter_by(review_id=old_review["review_id"]).one().review_state, "new_pointer_version_id": activated["switch"]["version_id"]},
        "trace_samples": trace_rows[:3],
        "review_reproduction": reproducible,
        "truth_checks": {
            "asset_has_prompt_lineage": all_lineaged,
            "prompt_version_exists": all(bool(trace["prompt_version"]) for trace in trace_rows),
            "generation_intent_exists": all(bool(trace["generation_intent"]) for trace in trace_rows),
            "prompt_fingerprint_valid": fingerprint_valid,
            "review_reproducible": all(item["reproducible"] for item in reproducible),
            "prompt_history_append_only": [int(row.version_number) for row in session.query(ProductionPromptVersion).filter_by(prompt_id=fixture["prompt_change"]["prompt_id"]).order_by(ProductionPromptVersion.version_number).all()] == [1, 2] and len(review_ids) == len(set(review_ids)),
            "traceability_result": len(trace_rows) == len(all_versions) and all(item["traceability_valid"] for item in trace_rows),
            "source_fact_mutations": int(graph.get("source_gate_mutations", {}).get("fact_snapshots", 0)) + int(graph.get("source_gate_mutations", {}).get("fact_records", 0)),
            "script_ir_mutations": int(graph.get("source_gate_mutations", {}).get("script_ir_versions", 0)),
        },
    })
    return result


def build_prompt_lineage_truth_audit(result: Mapping[str, Any]) -> dict[str, Any]:
    checks = dict(result.get("truth_checks") or {})
    complete = all(bool(checks.get(key)) for key in ("asset_has_prompt_lineage", "prompt_version_exists", "generation_intent_exists", "prompt_fingerprint_valid", "review_reproducible", "prompt_history_append_only", "traceability_result")) and checks.get("source_fact_mutations") == 0 and checks.get("script_ir_mutations") == 0
    return {"schema_version": "production_prompt_lineage_truth_audit_v1", "stage": result.get("stage"), "approval_state": result.get("approval_state"), "provider_calls": 0, "checks": checks, "complete": complete, "asset_has_prompt_lineage": bool(checks.get("asset_has_prompt_lineage")), "prompt_version_exists": bool(checks.get("prompt_version_exists")), "generation_intent_exists": bool(checks.get("generation_intent_exists")), "prompt_fingerprint_valid": bool(checks.get("prompt_fingerprint_valid")), "review_reproducible": bool(checks.get("review_reproducible")), "prompt_history_append_only": bool(checks.get("prompt_history_append_only")), "source_fact_mutations": int(checks.get("source_fact_mutations", 0)), "script_ir_mutations": int(checks.get("script_ir_mutations", 0))}


__all__ = ["SCHEMA_VERSION", "STAGE", "APPROVAL", "build_production_prompt_lineage_fixture", "reconcile_production_prompt_lineage_canary", "build_prompt_lineage_truth_audit"]
