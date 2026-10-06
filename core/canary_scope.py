"""Canonical canary scope descriptors and target-scoped DB snapshots.

The production database contains historical books and downstream artifacts.
Canary evidence must therefore describe its scope and query path explicitly;
global table counts are never valid inputs to a target delta.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from sqlalchemy.orm import Session as SQLAlchemySession


CANARY_SCOPE_KIND = "CANONICAL_CANARY_TARGET"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def build_scope_descriptor(*, book_id: int, episode: int, scene_id: str, script_id: int, fact_snapshot_id: int, script_ir_version_id: int, decision_packet_id: int) -> dict[str, Any]:
    descriptor = {
        "kind": CANARY_SCOPE_KIND,
        "book_id": int(book_id),
        "episode": int(episode),
        "scene_id": str(scene_id),
        "script_id": int(script_id),
        "fact_snapshot_id": int(fact_snapshot_id),
        "script_ir_version_id": int(script_ir_version_id),
        "decision_packet_id": int(decision_packet_id),
    }
    return descriptor


def scope_fingerprint(scope_descriptor: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(dict(scope_descriptor)).encode("utf-8")).hexdigest()


def _row_identity(row: Any, fields: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in fields:
        value = getattr(row, field, None)
        result[field] = value.isoformat() if hasattr(value, "isoformat") else value
    return result


def row_identity_hash(rows: list[Any], fields: list[str]) -> str:
    identities = [_row_identity(row, fields) for row in rows]
    identities.sort(key=lambda item: canonical_json(item))
    return hashlib.sha256(canonical_json(identities).encode("utf-8")).hexdigest()


def describe_rows(*, table: str, rows: list[Any], scope_mode: str, query_predicates: list[str], lineage_join_path: list[str], identity_fields: list[str]) -> dict[str, Any]:
    return {
        "table": table,
        "scope_mode": scope_mode,
        "query_predicates": list(query_predicates),
        "lineage_join_path": list(lineage_join_path),
        "count": len(rows),
        "row_identity_fields": list(identity_fields),
        "row_identity_hash": row_identity_hash(rows, identity_fields),
    }


def assert_matching_scope(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    before_fp = str(before.get("scope_fingerprint") or "")
    after_fp = str(after.get("scope_fingerprint") or "")
    if not before_fp or before_fp != after_fp:
        raise ValueError("DB_SNAPSHOT_SCOPE_MISMATCH")
    return {"status": "PASS", "scope_fingerprint": before_fp}


def target_scope_snapshot(session: SQLAlchemySession, *, scope: Mapping[str, Any]) -> dict[str, Any]:
    """Return only rows derived from the canonical target scene.

    The function imports models lazily so it remains usable by provider-free
    tests and does not create or mutate any database rows.
    """
    from models import (
        DecisionPacketRecord, DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer,
        SceneBlocking, ShotPlan, StoryboardShot, StoryboardPromptVersion, PromptIRVersion,
        GenerationExecutionRecord, MediaCandidateRecord, OfficialMediaVersion,
    )

    book_id = int(scope["book_id"]); episode = int(scope["episode"]); scene_id = str(scope["scene_id"])
    packet_id = int(scope["decision_packet_id"])
    descriptors: dict[str, dict[str, Any]] = {}

    def direct(name: str, model: Any, *, identity_fields: list[str], extra_filters: Mapping[str, Any] | None = None) -> None:
        query = session.query(model).filter(model.book_id == book_id)
        predicates = [f"{name}.book_id = {book_id}"]
        if hasattr(model, "episode"):
            query = query.filter(model.episode == episode); predicates.append(f"{name}.episode = {episode}")
        if hasattr(model, "scene_id"):
            query = query.filter(model.scene_id == scene_id); predicates.append(f"{name}.scene_id = {scene_id}")
        for field, value in (extra_filters or {}).items():
            query = query.filter(getattr(model, field) == value); predicates.append(f"{name}.{field} = {value}")
        rows = query.order_by(model.id).all()
        descriptors[name] = describe_rows(table=name, rows=rows, scope_mode="DIRECT_FILTER", query_predicates=predicates, lineage_join_path=[], identity_fields=identity_fields)

    packet_rows = session.query(DecisionPacketRecord).filter(DecisionPacketRecord.id == packet_id, DecisionPacketRecord.book_id == book_id).order_by(DecisionPacketRecord.id).all()
    descriptors["decision_packet_records"] = describe_rows(
        table="decision_packet_records", rows=packet_rows, scope_mode="DIRECT_FILTER",
        query_predicates=[f"decision_packet_records.id = {packet_id}", f"decision_packet_records.book_id = {book_id}"],
        lineage_join_path=[], identity_fields=["id", "book_id", "packet_fingerprint", "domain", "status"],
    )
    direct("director_treatments", DirectorTreatment, identity_fields=["id", "book_id", "episode", "scene_id", "revision", "status"])
    direct("director_treatment_authorities", DirectorTreatmentAuthority, identity_fields=["id", "book_id", "episode", "scene_id", "treatment_id", "treatment_revision"])
    direct("director_treatment_pointers", DirectorTreatmentPointer, identity_fields=["id", "book_id", "episode", "scene_id", "treatment_id", "treatment_revision"])
    direct("scene_blockings", SceneBlocking, identity_fields=["id", "book_id", "episode", "scene_id", "revision", "status"])
    direct("shot_plans", ShotPlan, identity_fields=["id", "book_id", "episode", "scene_id", "revision", "status"])
    direct("storyboard_shots", StoryboardShot, identity_fields=["id", "book_id", "episode", "scene_id", "shot_id", "materialization_status"])
    direct("prompt_ir_versions", PromptIRVersion, identity_fields=["id", "book_id", "episode", "scene_id", "storyboard_shot_id", "materialization_set_id"])

    prompt_rows = (session.query(StoryboardPromptVersion)
                   .join(StoryboardShot, StoryboardShot.shot_id == StoryboardPromptVersion.shot_id)
                   .filter(StoryboardPromptVersion.book_id == book_id, StoryboardPromptVersion.episode == episode, StoryboardShot.book_id == book_id, StoryboardShot.episode == episode, StoryboardShot.scene_id == scene_id)
                   .order_by(StoryboardPromptVersion.id).all())
    descriptors["storyboard_prompt_versions"] = describe_rows(
        table="storyboard_prompt_versions", rows=prompt_rows, scope_mode="LINEAGE_JOIN",
        query_predicates=[f"storyboard_prompt_versions.book_id = {book_id}", f"storyboard_prompt_versions.episode = {episode}", f"StoryboardShot.scene_id = {scene_id}"],
        lineage_join_path=["StoryboardPromptVersion.shot_id = StoryboardShot.shot_id", "StoryboardShot.book_id/episode/scene_id -> target scope"],
        identity_fields=["id", "book_id", "episode", "shot_id", "version"],
    )
    execution_rows = (session.query(GenerationExecutionRecord)
                      .join(StoryboardShot, StoryboardShot.id == GenerationExecutionRecord.storyboard_shot_id)
                      .filter(GenerationExecutionRecord.book_id == book_id, GenerationExecutionRecord.episode == episode, StoryboardShot.book_id == book_id, StoryboardShot.episode == episode, StoryboardShot.scene_id == scene_id)
                      .order_by(GenerationExecutionRecord.id).all())
    descriptors["generation_execution_records"] = describe_rows(
        table="generation_execution_records", rows=execution_rows, scope_mode="LINEAGE_JOIN",
        query_predicates=[f"generation_execution_records.book_id = {book_id}", f"generation_execution_records.episode = {episode}", f"StoryboardShot.scene_id = {scene_id}"],
        lineage_join_path=["GenerationExecutionRecord.storyboard_shot_id = StoryboardShot.id", "StoryboardShot.book_id/episode/scene_id -> target scope"],
        identity_fields=["id", "execution_id", "book_id", "episode", "storyboard_shot_id", "target_media"],
    )
    candidate_rows = (session.query(MediaCandidateRecord)
                      .join(GenerationExecutionRecord, GenerationExecutionRecord.execution_id == MediaCandidateRecord.execution_id)
                      .join(StoryboardShot, StoryboardShot.id == GenerationExecutionRecord.storyboard_shot_id)
                      .filter(GenerationExecutionRecord.book_id == book_id, GenerationExecutionRecord.episode == episode, StoryboardShot.book_id == book_id, StoryboardShot.episode == episode, StoryboardShot.scene_id == scene_id)
                      .order_by(MediaCandidateRecord.id).all())
    descriptors["media_candidate_records"] = describe_rows(
        table="media_candidate_records", rows=candidate_rows, scope_mode="LINEAGE_JOIN",
        query_predicates=[f"GenerationExecutionRecord.book_id = {book_id}", f"GenerationExecutionRecord.episode = {episode}", f"StoryboardShot.scene_id = {scene_id}"],
        lineage_join_path=["MediaCandidateRecord.execution_id = GenerationExecutionRecord.execution_id", "GenerationExecutionRecord.storyboard_shot_id = StoryboardShot.id", "StoryboardShot scene scope"],
        identity_fields=["id", "candidate_id", "execution_id", "prompt_ir_version_id"],
    )
    official_rows = (session.query(OfficialMediaVersion)
                     .join(StoryboardShot, StoryboardShot.id == OfficialMediaVersion.storyboard_shot_id)
                     .filter(OfficialMediaVersion.book_id == book_id, OfficialMediaVersion.episode == episode, StoryboardShot.book_id == book_id, StoryboardShot.episode == episode, StoryboardShot.scene_id == scene_id)
                     .order_by(OfficialMediaVersion.id).all())
    descriptors["official_media_versions"] = describe_rows(
        table="official_media_versions", rows=official_rows, scope_mode="LINEAGE_JOIN",
        query_predicates=[f"official_media_versions.book_id = {book_id}", f"official_media_versions.episode = {episode}", f"StoryboardShot.scene_id = {scene_id}"],
        lineage_join_path=["OfficialMediaVersion.storyboard_shot_id = StoryboardShot.id", "StoryboardShot scene scope"],
        identity_fields=["id", "official_media_version_id", "book_id", "episode", "storyboard_shot_id", "media_role", "revision"],
    )
    return {"scope_descriptor": dict(scope), "scope_fingerprint": scope_fingerprint(scope), "tables": descriptors}


__all__ = ["CANARY_SCOPE_KIND", "canonical_json", "build_scope_descriptor", "scope_fingerprint", "row_identity_hash", "describe_rows", "assert_matching_scope", "target_scope_snapshot"]
