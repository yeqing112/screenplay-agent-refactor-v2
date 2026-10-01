"""Canonical, provider-free Book and Script lifecycle services.

The lifecycle bootstrap is deliberately small: creating a project or saving a
structured source Script only persists domain rows.  It does not run ingest,
Reader/Bible agents, vector indexing, an LLM, or a media Provider.

Book deletion lives here as an explicit scope plan rather than in the HTTP
route.  The plan is intentionally enumerated so a new book-scoped model cannot
silently escape cleanup: the inventory audit fails closed when a direct
``book_id`` table is added without being reviewed here.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
import shutil
from typing import Any, Iterable, Mapping
from uuid import uuid4

import config
from sqlalchemy import and_, or_

from models import Base, Book, EpisodeOutline, Script, Session


class BookLifecycleError(ValueError):
    """A safe, user-facing lifecycle contract error."""

    def __init__(self, code: str, message: str, *, status_code: int = 422, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = int(status_code)
        self.details = dict(details or {})


# Every table currently carrying a direct book_id.  Keep this list explicit:
# it is both the delete plan and the review surface for future schema changes.
DIRECT_BOOK_SCOPE_TABLES: tuple[str, ...] = (
    "agent_attachments",
    "agent_project_updates",
    "agent_sessions",
    "agent_violation_logs",
    "asset_semantic_governance_records",
    "book_bibles",
    "chapters",
    "character_profiles",
    "character_stages",
    "decision_packet_records",
    "director_benchmark_runs",
    "director_treatment_authorities",
    "director_treatment_pointers",
    "director_treatments",
    "episode_outlines",
    "fact_snapshots",
    "generation_execution_attempt_lineages",
    "generation_execution_records",
    "official_media_pointers",
    "official_media_versions",
    "production_export_records",
    "prompt_ir_authorities",
    "prompt_ir_pointers",
    "prompt_ir_versions",
    "qa_issues",
    "qa_results",
    "repair_attempts",
    "scene_blocking_authorities",
    "scene_blocking_pointers",
    "scene_blockings",
    "scene_characters",
    "scene_props",
    "script_ir_versions",
    "script_versions",
    "scripts",
    "shot_plan_authorities",
    "shot_plan_pointers",
    "shot_plans",
    "shot_style_bindings",
    "storyboard_acceptance_records",
    "storyboard_materialization_pointers",
    "storyboard_materialization_sets",
    "storyboard_prompt_versions",
    "storyboard_shots",
    "storyboard_transition_continuity_reviews",
    "storyboard_transition_contracts",
    "storyboard_transition_frames",
    "storyboard_video_retry_attempts",
    "task_runs",
    "visual_asset_pointers",
    "visual_asset_versions",
    "visual_authoring_decision_requests",
    "visual_authoring_decisions",
    "visual_authoring_proposals",
    "visual_era_specs",
    "visual_locations",
    "visual_makeups",
    "visual_props",
    "visual_reference_assets",
    "visual_style_profiles",
)


def _model_by_table() -> dict[str, Any]:
    return {
        mapper.local_table.name: mapper.class_
        for mapper in Base.registry.mappers
    }


def direct_book_scope_inventory() -> dict[str, Any]:
    """Return the reviewed direct scope inventory and fail closed on drift."""

    tables = Base.metadata.tables
    actual = {
        table.name
        for table in tables.values()
        if "book_id" in table.c and table.name != "books"
    }
    expected = set(DIRECT_BOOK_SCOPE_TABLES)
    missing = sorted(actual - expected)
    stale = sorted(expected - actual)
    return {
        "direct_book_scope_tables": sorted(expected),
        "actual_direct_book_scope_tables": sorted(actual),
        "unreviewed_direct_book_scope_tables": missing,
        "removed_from_schema": stale,
        "complete": not missing,
    }


def _assert_direct_scope_inventory() -> None:
    audit = direct_book_scope_inventory()
    if not audit["complete"]:
        raise BookLifecycleError(
            "BOOK_DELETE_SCOPE_INVENTORY_INCOMPLETE",
            "a new direct book-scoped table must be added to the explicit delete plan",
            status_code=500,
            details=audit,
        )


def _canonical_script_content(content: str | dict[str, Any]) -> tuple[str, int]:
    if isinstance(content, str):
        normalized = content.strip()
        if not normalized:
            raise BookLifecycleError("SCRIPT_CONTENT_REQUIRED", "content must not be empty")
        return normalized, len(normalized)
    if isinstance(content, dict):
        if not content:
            raise BookLifecycleError("SCRIPT_CONTENT_REQUIRED", "content must not be empty")
        normalized = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return normalized, len(normalized)
    raise BookLifecycleError("SCRIPT_CONTENT_INVALID", "content must be a string or JSON object")


def create_book(session: Any, *, title: str) -> Book:
    """Create an empty Book with only server-owned source metadata."""

    normalized = str(title or "").strip()
    if not normalized:
        raise BookLifecycleError("BOOK_TITLE_REQUIRED", "title must not be empty")
    if len(normalized) > 255:
        raise BookLifecycleError("BOOK_TITLE_TOO_LONG", "title must be at most 255 characters")

    book = Book(
        title=normalized,
        filename=f"api-{uuid4().hex}.json",
        chapter_count=0,
        total_words=0,
        status="imported",
    )
    session.add(book)
    session.commit()
    session.refresh(book)
    return book


def create_script(
    session: Any,
    *,
    book_id: int,
    episode: int,
    content: str | dict[str, Any],
    genre: str = "short_drama",
    workflow_profile: str = "creative_draft",
) -> Script:
    """Persist exactly one source Script for a book/episode/genre scope."""

    book = session.get(Book, int(book_id))
    if book is None:
        raise BookLifecycleError("BOOK_NOT_FOUND", "Book not found", status_code=404)
    if int(episode) < 1:
        raise BookLifecycleError("SCRIPT_EPISODE_INVALID", "episode must be at least 1")
    normalized_genre = str(genre or "").strip()
    if not normalized_genre or len(normalized_genre) > 50:
        raise BookLifecycleError("SCRIPT_GENRE_INVALID", "genre must be between 1 and 50 characters")
    normalized_profile = str(workflow_profile or "").strip()
    if normalized_profile not in {"creative_draft", "production"}:
        raise BookLifecycleError("SCRIPT_WORKFLOW_PROFILE_INVALID", "workflowProfile must be creative_draft or production")

    existing = session.query(Script).filter(
        Script.book_id == int(book_id),
        Script.episode == int(episode),
        Script.genre == normalized_genre,
    ).order_by(Script.id.asc()).first()
    if existing is not None:
        raise BookLifecycleError(
            "SCRIPT_ALREADY_EXISTS",
            "an active source Script already exists for this book, episode, and genre",
            status_code=409,
            details={"existing_script_id": int(existing.id)},
        )

    canonical_content, word_count = _canonical_script_content(content)
    row = Script(
        book_id=int(book_id),
        episode=int(episode),
        genre=normalized_genre,
        content=canonical_content,
        word_count=word_count,
        status="draft",
        execution_status="succeeded",
        quality_status="draft",
        production_status="blocked",
        workflow_profile=normalized_profile,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def serialize_book(session: Any, book: Book) -> dict[str, Any]:
    from models import StoryboardShot, Script

    return {
        "id": int(book.id),
        "title": str(book.title or ""),
        "chapters": int(book.chapter_count or 0),
        "words": int(book.total_words or 0),
        "status": str(book.status or "imported"),
        "scripts": int(session.query(Script).filter(Script.book_id == book.id).count()),
        "storyboard_shots": int(session.query(StoryboardShot).filter(StoryboardShot.book_id == book.id).count()),
        "created_at": book.created_at.isoformat() if book.created_at else None,
        "provider_calls": 0,
        "llm_calls": 0,
    }


def _ids(session: Any, model: Any, column: str, values: Iterable[Any]) -> set[Any]:
    values = {value for value in values if value not in {None, ""}}
    if not values or not hasattr(model, column):
        return set()
    return {getattr(row, column) for row in session.query(model).filter(getattr(model, column).in_(values)).all()}


def _json_mentions_book(value: Any, book_id: int) -> bool:
    if not value:
        return False
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if isinstance(parsed, Mapping):
        if parsed.get("book_id") in {book_id, str(book_id)}:
            return True
        return any(_json_mentions_book(item, book_id) for item in parsed.values())
    if isinstance(parsed, list):
        return any(_json_mentions_book(item, book_id) for item in parsed)
    return False


def _lineage_values(value: Any, key: str) -> list[Any]:
    """Collect canonical lineage values without treating episode ids as scope."""

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if isinstance(value, Mapping):
        values: list[Any] = []
        if key in value and value[key] not in {None, ""}:
            values.append(value[key])
        for child in value.values():
            values.extend(_lineage_values(child, key))
        return values
    if isinstance(value, list):
        values: list[Any] = []
        for child in value:
            values.extend(_lineage_values(child, key))
        return values
    return []


def _delete_rows(session: Any, model: Any, criterion: Any) -> int:
    return int(session.query(model).filter(criterion).delete(synchronize_session=False) or 0)


def _remove_scoped_files(book_id: int, title: str, *, has_same_title_neighbor: bool) -> dict[str, Any]:
    """Remove only paths whose scope is unambiguously this Book."""

    removed: list[str] = []
    skipped: list[str] = []
    roots = [
        config.UPLOAD_DIR / "production-assets" / f"book-{int(book_id)}",
        config.UPLOAD_DIR / "agent-attachments" / f"book-{int(book_id)}",
        config.UPLOAD_DIR / "transition-frames" / f"book-{int(book_id)}",
        config.UPLOAD_DIR / "transition-reviews" / f"book-{int(book_id)}",
    ]
    for root in roots:
        resolved_root = root.resolve()
        expected_root = config.UPLOAD_DIR.resolve()
        try:
            resolved_root.relative_to(expected_root)
        except ValueError:
            skipped.append(str(root))
            continue
        if resolved_root.exists():
            shutil.rmtree(resolved_root)
            removed.append(str(resolved_root))

    # Legacy stores are flat and use a book-id prefix.  Only delete exact
    # prefix matches; unrelated projects remain untouched.
    for dirname in ("manual-media", "generated-media"):
        directory = (config.UPLOAD_DIR / dirname).resolve()
        try:
            directory.relative_to(config.UPLOAD_DIR.resolve())
        except ValueError:
            skipped.append(str(directory))
            continue
        if directory.exists():
            prefix = f"book-{int(book_id)}-"
            for path in directory.iterdir():
                if path.is_file() and path.name.startswith(prefix):
                    path.unlink()
                    removed.append(str(path))

    # Ingest uses title directories.  Never remove a shared-title neighbor's
    # directory; API-created Books do not create one in the first place.
    if title and not has_same_title_neighbor:
        ingest_dir = (config.BOOKS_DIR / title).resolve()
        try:
            ingest_dir.relative_to(config.BOOKS_DIR.resolve())
        except ValueError:
            skipped.append(str(ingest_dir))
        else:
            if ingest_dir.exists():
                shutil.rmtree(ingest_dir)
                removed.append(str(ingest_dir))
    elif title:
        skipped.append(f"shared-title:{title}")
    return {"removed": removed, "skipped": skipped}


def _script_ir_hash_books(session: Any) -> dict[str, set[int]]:
    from models import ScriptIRVersion

    result: dict[str, set[int]] = defaultdict(set)
    for row in session.query(ScriptIRVersion).all():
        payload_hash = str(row.payload_hash or "")
        if payload_hash:
            result[payload_hash].add(int(row.book_id))
    return result


def _scope_context(session: Any, book_id: int) -> dict[str, Any]:
    """Collect all explicit IDs needed for indirect child cleanup."""

    from models import (
        CharacterProfile,
        AgentSession,
        FactSnapshot,
        EpisodeOutline,
        GenerationExecutionRecord,
        MediaCandidateRecord,
        OfficialMediaVersion,
        ProductionAssetAuthorityRegistry,
        ProductionAssetVersionRegistry,
        SceneAssetAuthority,
        CharacterAssetAuthority,
        PropAssetAuthority,
        ShotAssetBinding,
        StoryboardShot,
        VisualAssetVersion,
        VisualLocation,
        VisualMakeup,
        VisualProp,
        VisualReferenceAsset,
        VisualStyleProfile,
        PromptIRVersion,
        SceneBlocking,
        DirectorTreatment,
        ShotPlan,
        StoryboardMaterializationSet,
        ScriptIRVersion,
    )

    shots = session.query(StoryboardShot).filter_by(book_id=book_id).all()
    outlines = session.query(EpisodeOutline).filter_by(book_id=book_id).all()
    source_scripts = session.query(Script).filter_by(book_id=book_id).all()
    source_irs = session.query(ScriptIRVersion).filter_by(book_id=book_id).all()
    executions = session.query(GenerationExecutionRecord).filter_by(book_id=book_id).all()
    candidates = session.query(MediaCandidateRecord).filter(
        MediaCandidateRecord.execution_id.in_([row.execution_id for row in executions])
    ).all() if executions else []
    official = session.query(OfficialMediaVersion).filter_by(book_id=book_id).all()
    visual_versions = session.query(VisualAssetVersion).filter_by(book_id=book_id).all()
    visual_refs = session.query(VisualReferenceAsset).filter_by(book_id=book_id).all()
    locations = session.query(VisualLocation).filter_by(book_id=book_id).all()
    makeups = session.query(VisualMakeup).filter_by(book_id=book_id).all()
    props = session.query(VisualProp).filter_by(book_id=book_id).all()
    styles = session.query(VisualStyleProfile).filter_by(book_id=book_id).all()
    characters = session.query(CharacterProfile).filter_by(book_id=book_id).all()
    agent_sessions = session.query(AgentSession).filter_by(book_id=book_id).all()
    fact_snapshots = session.query(FactSnapshot).filter_by(book_id=book_id).all()
    shot_ids = {int(row.id) for row in shots}
    outline_ids = {int(row.id) for row in outlines}
    # Episode values are candidate keys only.  They are never ownership
    # evidence for Director runtime rows; canonical ownership comes from the
    # source IR, lineage, or a canonical parent row.
    episode_numbers = {int(row.episode) for row in outlines}
    episode_numbers.update(int(row.episode) for row in source_scripts)
    episode_keys = {str(value) for value in outline_ids | episode_numbers}
    execution_ids = {str(row.execution_id) for row in executions}
    candidate_ids = {str(row.candidate_id) for row in candidates}
    official_version_ids = {str(row.official_media_version_id) for row in official}
    visual_version_ids = {int(row.id) for row in visual_versions}
    visual_ref_ids = {int(row.id) for row in visual_refs}
    prompt_ir_version_ids = {int(row.id) for row in session.query(PromptIRVersion).filter_by(book_id=book_id).all()}
    materialization_set_ids = {int(row.id) for row in session.query(StoryboardMaterializationSet).filter_by(book_id=book_id).all()}
    treatment_ids = {int(row.id) for row in session.query(DirectorTreatment).filter_by(book_id=book_id).all()}
    blocking_ids = {int(row.id) for row in session.query(SceneBlocking).filter_by(book_id=book_id).all()}
    shot_plan_ids = {int(row.id) for row in session.query(ShotPlan).filter_by(book_id=book_id).all()}

    # Typed production assets are scoped by a fingerprint containing book_id,
    # not by a direct column.  Verify that fingerprint before including them.
    asset_authority_ids: set[str] = set()
    asset_version_ids: set[str] = set()
    asset_entities: dict[str, set[str]] = defaultdict(set)
    for row in characters:
        asset_entities["CHARACTER"].update({str(row.id), str(getattr(row, "name", "") or "")})
    for row in locations:
        asset_entities["SCENE"].update({str(row.id), str(getattr(row, "asset_key", "") or ""), str(getattr(row, "scene_id", "") or "")})
    for row in props:
        asset_entities["PROP"].update({str(row.id), str(getattr(row, "asset_key", "") or ""), str(getattr(row, "name", "") or "")})
    for row in session.query(ShotAssetBinding).filter(ShotAssetBinding.storyboard_shot_id.in_(shot_ids)).all() if shot_ids else []:
        asset_authority_ids.add(str(row.authority_id))
        asset_version_ids.add(str(row.version_id))
    for model in (CharacterAssetAuthority, SceneAssetAuthority, PropAssetAuthority):
        entity_field = {CharacterAssetAuthority: "character_id", SceneAssetAuthority: "scene_id", PropAssetAuthority: "prop_id"}[model]
        for row in session.query(model).all():
            from core.production_asset_authority import _authority_fingerprint
            entity = str(getattr(row, entity_field, "") or "")
            expected = _authority_fingerprint(book_id=book_id, asset_type={CharacterAssetAuthority: "CHARACTER", SceneAssetAuthority: "SCENE", PropAssetAuthority: "PROP"}[model], entity_id=entity, authority_id=str(row.authority_id))
            if str(getattr(row, "fingerprint", "") or "") == expected:
                asset_authority_ids.add(str(row.authority_id))
    if asset_authority_ids:
        asset_version_ids.update(str(row.version_id) for row in session.query(ProductionAssetVersionRegistry).filter(ProductionAssetVersionRegistry.authority_id.in_(asset_authority_ids)).all())

    return {
        "book_id": int(book_id),
        "title": str(session.get(Book, book_id).title or ""),
        "shot_ids": shot_ids,
        "outline_ids": outline_ids,
        "episode_keys": episode_keys,
        "episode_numbers": episode_numbers,
        "source_script_ir_ids": {int(row.id) for row in source_irs},
        "source_script_ir_hashes": {str(row.payload_hash) for row in source_irs if str(row.payload_hash or "")},
        "source_script_ir_hash_books": _script_ir_hash_books(session),
        "execution_ids": execution_ids,
        "candidate_ids": candidate_ids,
        "official_version_ids": official_version_ids,
        "visual_version_ids": visual_version_ids,
        "visual_ref_ids": visual_ref_ids,
        "location_ids": {int(row.id) for row in locations},
        "character_ids": {int(row.id) for row in characters},
        "agent_session_ids": {int(row.id) for row in agent_sessions},
        "fact_snapshot_ids": {int(row.id) for row in fact_snapshots},
        "style_ids": {int(row.id) for row in styles},
        "asset_authority_ids": asset_authority_ids,
        "asset_version_ids": asset_version_ids,
        "prompt_ir_version_ids": prompt_ir_version_ids,
        "materialization_set_ids": materialization_set_ids,
        "treatment_ids": treatment_ids,
        "blocking_ids": blocking_ids,
        "shot_plan_ids": shot_plan_ids,
    }


def _int_values(values: Iterable[Any]) -> set[int]:
    result: set[int] = set()
    for value in values:
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            continue
    return result


def _director_row_scope(
    session: Any,
    row: Any,
    ctx: Mapping[str, Any],
    *,
    table: str,
    parent_scope: str | None = None,
) -> str:
    """Resolve one Director row using canonical evidence only.

    ``episode_id`` is used solely to decide whether an evidence-free legacy
    row could be related to the target.  It never returns ``owned`` by itself.
    """

    if parent_scope in {"owned", "foreign", "ambiguous"}:
        return str(parent_scope)

    target_book_id = int(ctx["book_id"])
    potential = str(getattr(row, "episode_id", "")) in set(ctx.get("episode_keys", set()))
    lineage = getattr(row, "lineage_json", "")
    lineage_books = _int_values(_lineage_values(lineage, "book_id"))
    source_ids = _int_values(
        [getattr(row, "source_script_ir_version_id", None)]
        + _lineage_values(lineage, "source_script_ir_version_id")
    )
    source_hashes = {str(value) for value in _lineage_values(lineage, "source_script_ir_hash") if str(value or "")}
    direct_hash = str(getattr(row, "source_script_ir_hash", "") or "")
    if direct_hash:
        source_hashes.add(direct_hash)

    # An explicit source IR id is first-class evidence.  A dangling id is
    # ambiguous when the raw episode key could point at this Book.
    if source_ids:
        from models import ScriptIRVersion

        ir_rows = session.query(ScriptIRVersion).filter(ScriptIRVersion.id.in_(source_ids)).all()
        known_ids = {int(ir.id) for ir in ir_rows}
        ir_books = {int(ir.book_id) for ir in ir_rows}
        if known_ids != source_ids or len(ir_books) != 1:
            return "ambiguous" if potential else "unrelated"
        source_book = next(iter(ir_books))
        if lineage_books and lineage_books != {source_book}:
            return "ambiguous" if potential else "unrelated"
        if source_book == target_book_id:
            return "owned"
        return "foreign"

    # A canonical book_id in lineage is valid ownership evidence when no
    # contradictory source IR id exists.
    if lineage_books:
        if len(lineage_books) != 1:
            return "ambiguous" if potential else "unrelated"
        return "owned" if target_book_id in lineage_books else "foreign"

    # Hash evidence is valid only when every matching ScriptIR row belongs to
    # this Book.  A shared hash is explicitly ambiguous.
    if source_hashes:
        hash_books: set[int] = set()
        matched = False
        for payload_hash in source_hashes:
            books = set(ctx.get("source_script_ir_hash_books", {}).get(payload_hash, set()))
            if books:
                matched = True
                hash_books.update(books)
        if matched:
            if len(hash_books) == 1 and target_book_id in hash_books:
                return "owned"
            if target_book_id in hash_books or len(hash_books) > 1:
                return "ambiguous" if potential else "unrelated"
            return "foreign"
        return "ambiguous" if potential else "unrelated"

    # Raw episode numbers are deliberately never ownership evidence.
    return "ambiguous" if potential else "unrelated"


def _resolve_director_runtime_scope(session: Any, ctx: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve Director ownership once for delete, audit, and preflight."""

    from models import DirectorPlan, DirectorReasoning, DirectorReasoningGeneration, StoryboardPlan

    plans: dict[int, str] = {}
    reasonings: dict[int, str] = {}
    storyboards: dict[int, str] = {}
    generations: dict[int, str] = {}
    ambiguous_rows: list[dict[str, Any]] = []

    def record(table: str, row: Any, scope: str) -> None:
        if scope == "ambiguous":
            ambiguous_rows.append({
                "table": table,
                "row_id": int(row.id),
                "episode_id": str(getattr(row, "episode_id", "")),
                "reason": "missing canonical Book ownership evidence; raw episode_id is not sufficient",
            })

    for row in session.query(DirectorPlan).all():
        scope = _director_row_scope(session, row, ctx, table="director_plans")
        plans[int(row.id)] = scope
        record("director_plans", row, scope)
    for row in session.query(DirectorReasoning).all():
        scope = _director_row_scope(session, row, ctx, table="director_reasonings")
        reasonings[int(row.id)] = scope
        record("director_reasonings", row, scope)
    for row in session.query(StoryboardPlan).all():
        parent_scope = reasonings.get(int(row.director_reasoning_id)) if row.director_reasoning_id is not None else None
        scope = _director_row_scope(session, row, ctx, table="director_storyboard_plans", parent_scope=parent_scope)
        storyboards[int(row.id)] = scope
        record("director_storyboard_plans", row, scope)
    for row in session.query(DirectorReasoningGeneration).all():
        parent_scope = reasonings.get(int(row.director_reasoning_id)) if row.director_reasoning_id is not None else None
        scope = _director_row_scope(session, row, ctx, table="director_reasoning_generations", parent_scope=parent_scope)
        generations[int(row.id)] = scope
        record("director_reasoning_generations", row, scope)

    return {
        "plan_ids": {row_id for row_id, scope in plans.items() if scope == "owned"},
        "reasoning_ids": {row_id for row_id, scope in reasonings.items() if scope == "owned"},
        "storyboard_plan_ids": {row_id for row_id, scope in storyboards.items() if scope == "owned"},
        "generation_ids": {row_id for row_id, scope in generations.items() if scope == "owned"},
        "plan_scopes": plans,
        "reasoning_scopes": reasonings,
        "storyboard_scopes": storyboards,
        "generation_scopes": generations,
        "ambiguous_rows": ambiguous_rows,
    }


def _delete_indirect_scope(session: Any, ctx: dict[str, Any]) -> dict[str, int]:
    """Delete child tables that do not carry book_id, in dependency order."""

    from models import (
        AutomaticKeyframePlan,
        AgentAuditLog,
        AgentMessage,
        AgentPlan,
        CharacterAssetAuthority,
        CharacterAssetPointer,
        CharacterAssetVersion,
        CharacterReferenceAsset,
        DirectorPlan,
        DirectorReasoning,
        DirectorReasoningGeneration,
        EpisodeRenderItem,
        EpisodeRenderPlan,
        GenerationExecutionAttemptLineage,
        Keyframe,
        KeyframeAssetBinding,
        KeyframeSequence,
        MediaCandidateRecord,
        MediaPromotionRecord,
        MediaValidationRecord,
        ProductionAssetAuthorityRegistry,
        ProductionAssetReview,
        ProductionAssetReviewHistory,
        ProductionAssetVersionRegistry,
        ProductionBatch,
        ProductionBatchItem,
        ProductionGenerationIntent,
        ProductionPromptLineage,
        ProductionPromptVersion,
        PropAssetAuthority,
        PropAssetPointer,
        PropAssetVersion,
        SceneAssetAuthority,
        SceneAssetPointer,
        SceneAssetVersion,
        SceneReferenceAsset,
        ShotAssetBinding,
        ShotCharacterBinding,
        ShotDirection,
        ShotSceneBinding,
        ShotStyleBinding,
        StoryboardPlan,
        StoryboardPlanShot,
        ScenePlan,
        StyleReferenceAsset,
        VideoGenerationIntent,
        VisualDecision,
        VisualReferenceAuthority,
        VisualReferenceGenerationRequest,
        VisualReferenceSet,
        StoryBeat,
        FactRecord,
    )

    # The unusual import alias above is replaced at runtime below.  Keeping
    # the actual table names here makes the dependency plan auditable.
    counts: dict[str, int] = {}
    shots = ctx["shot_ids"]
    execution_ids = ctx["execution_ids"]
    candidate_ids = ctx["candidate_ids"]
    official_version_ids = ctx["official_version_ids"]
    asset_authority_ids = ctx["asset_authority_ids"]
    asset_version_ids = ctx["asset_version_ids"]
    agent_session_ids = ctx.get("agent_session_ids", set())
    fact_snapshot_ids = ctx.get("fact_snapshot_ids", set())

    def delete(name: str, model: Any, criterion: Any) -> None:
        count = _delete_rows(session, model, criterion)
        if count:
            counts[name] = counts.get(name, 0) + count

    # Resolve Director ownership once.  Raw episode keys are never enough.
    director_scope = _resolve_director_runtime_scope(session, ctx)
    plan_ids = set(director_scope["plan_ids"])
    reasoning_ids = set(director_scope["reasoning_ids"])
    storyboard_plan_ids = set(director_scope["storyboard_plan_ids"])

    render_plans = session.query(EpisodeRenderPlan).filter(
        or_(
            EpisodeRenderPlan.project_id == ctx["book_id"],
            EpisodeRenderPlan.episode_id.in_(ctx["outline_ids"]) if ctx["outline_ids"] else False,
        )
    ).all()
    render_plan_ids = {int(row.id) for row in render_plans}
    batch_rows = session.query(ProductionBatch).filter(
        or_(ProductionBatch.project_id == ctx["book_id"], ProductionBatch.episode_id.in_(ctx["outline_ids"]) if ctx["outline_ids"] else False)
    ).all()
    batch_ids = {int(row.id) for row in batch_rows}

    # Delete review/lineage/media children first.
    review_rows = session.query(ProductionAssetReview).filter(ProductionAssetReview.asset_version_id.in_(asset_version_ids)).all() if asset_version_ids else []
    review_ids = {str(row.review_id) for row in review_rows}
    delete("production_asset_review_history", ProductionAssetReviewHistory, or_(ProductionAssetReviewHistory.review_id.in_(review_ids), ProductionAssetReviewHistory.asset_version_id.in_(asset_version_ids)) if review_ids or asset_version_ids else False)
    delete("production_asset_reviews", ProductionAssetReview, ProductionAssetReview.asset_version_id.in_(asset_version_ids) if asset_version_ids else False)
    delete("production_prompt_lineages", ProductionPromptLineage, ProductionPromptLineage.shot_id.in_(shots) if shots else False)
    delete("media_promotion_records", MediaPromotionRecord, or_(MediaPromotionRecord.execution_id.in_(execution_ids), MediaPromotionRecord.candidate_id.in_(candidate_ids)) if execution_ids or candidate_ids else False)
    delete("media_validation_records", MediaValidationRecord, or_(MediaValidationRecord.execution_id.in_(execution_ids), MediaValidationRecord.candidate_id.in_(candidate_ids)) if execution_ids or candidate_ids else False)
    delete("media_candidates", MediaCandidateRecord, MediaCandidateRecord.execution_id.in_(execution_ids) if execution_ids else False)
    delete("shot_asset_bindings", ShotAssetBinding, ShotAssetBinding.storyboard_shot_id.in_(shots) if shots else False)
    delete("official_media_authorities", __import__("models").OfficialMediaAuthority, __import__("models").OfficialMediaAuthority.official_media_version_id.in_(official_version_ids) if official_version_ids else False)

    # Shot anchored children.
    delete("keyframe_asset_bindings", KeyframeAssetBinding, KeyframeAssetBinding.storyboard_shot_id.in_(shots) if shots else False)
    keyframe_sequences = session.query(KeyframeSequence).filter(KeyframeSequence.storyboard_shot_id.in_(shots)).all() if shots else []
    keyframe_sequence_ids = {int(row.id) for row in keyframe_sequences}
    keyframe_rows = session.query(Keyframe).filter(Keyframe.keyframe_sequence_id.in_(keyframe_sequence_ids)).all() if keyframe_sequence_ids else []
    keyframe_ids = {int(row.id) for row in keyframe_rows}
    delete("keyframe_asset_bindings", KeyframeAssetBinding, KeyframeAssetBinding.keyframe_id.in_(keyframe_ids) if keyframe_ids else False)
    delete("keyframes", Keyframe, Keyframe.keyframe_sequence_id.in_(keyframe_sequence_ids) if keyframe_sequence_ids else False)
    delete("keyframe_sequences", KeyframeSequence, KeyframeSequence.storyboard_shot_id.in_(shots) if shots else False)
    materialization_set_ids = ctx.get("materialization_set_ids", set())
    delete("automatic_keyframe_plans", AutomaticKeyframePlan, or_(AutomaticKeyframePlan.storyboard_shot_id.in_(shots) if shots else False, AutomaticKeyframePlan.storyboard_materialization_set_id.in_(materialization_set_ids) if materialization_set_ids else False) if shots or materialization_set_ids else False)
    delete("shot_character_bindings", ShotCharacterBinding, ShotCharacterBinding.storyboard_shot_id.in_(shots) if shots else False)
    delete("shot_scene_bindings", ShotSceneBinding, ShotSceneBinding.storyboard_shot_id.in_(shots) if shots else False)
    delete("shot_style_bindings", ShotStyleBinding, ShotStyleBinding.storyboard_shot_id.in_(shots) if shots else False)
    delete("shot_directions", ShotDirection, ShotDirection.storyboard_shot_id.in_(shots) if shots else False)
    delete("video_generation_intents", VideoGenerationIntent, VideoGenerationIntent.storyboard_shot_id.in_(shots) if shots else False)
    delete("production_generation_intents", ProductionGenerationIntent, ProductionGenerationIntent.shot_id.in_(shots) if shots else False)
    delete("production_prompt_versions", ProductionPromptVersion, ProductionPromptVersion.storyboard_plan_id.in_(storyboard_plan_ids) if storyboard_plan_ids else False)
    delete("episode_render_items", EpisodeRenderItem, or_(EpisodeRenderItem.render_plan_id.in_(render_plan_ids), EpisodeRenderItem.shot_id.in_(shots)) if render_plan_ids or shots else False)
    delete("production_batch_items", ProductionBatchItem, or_(ProductionBatchItem.batch_id.in_(batch_ids), ProductionBatchItem.execution_id.in_(execution_ids)) if batch_ids or execution_ids else False)

    # Draft and reasoning graphs.
    delete("director_storyboard_shots", StoryboardPlanShot, StoryboardPlanShot.storyboard_id.in_(storyboard_plan_ids) if storyboard_plan_ids else False)
    delete("director_scene_plans", ScenePlan, ScenePlan.director_plan_id.in_(plan_ids) if plan_ids else False)
    delete("director_story_beats", StoryBeat, StoryBeat.director_reasoning_id.in_(reasoning_ids) if reasoning_ids else False)
    delete("director_visual_decisions", VisualDecision, VisualDecision.director_reasoning_id.in_(reasoning_ids) if reasoning_ids else False)
    delete("director_reasoning_generations", DirectorReasoningGeneration, DirectorReasoningGeneration.id.in_(director_scope["generation_ids"]) if director_scope["generation_ids"] else False)
    delete("director_storyboard_plans", StoryboardPlan, StoryboardPlan.id.in_(storyboard_plan_ids) if storyboard_plan_ids else False)
    delete("director_reasonings", DirectorReasoning, DirectorReasoning.id.in_(reasoning_ids) if reasoning_ids else False)
    delete("director_plans", DirectorPlan, DirectorPlan.id.in_(plan_ids) if plan_ids else False)
    delete("episode_render_plans", EpisodeRenderPlan, EpisodeRenderPlan.id.in_(render_plan_ids) if render_plan_ids else False)
    delete("production_batches", ProductionBatch, ProductionBatch.id.in_(batch_ids) if batch_ids else False)

    # References and typed production assets.
    delete("character_reference_assets", CharacterReferenceAsset, CharacterReferenceAsset.character_id.in_(ctx["character_ids"]) if ctx["character_ids"] else False)
    delete("scene_reference_assets", SceneReferenceAsset, SceneReferenceAsset.scene_id.in_(ctx["location_ids"]) if ctx["location_ids"] else False)
    delete("style_reference_assets", StyleReferenceAsset, StyleReferenceAsset.style_id.in_(ctx["style_ids"]) if ctx["style_ids"] else False)
    delete("visual_reference_authorities", VisualReferenceAuthority, VisualReferenceAuthority.visual_reference_asset_id.in_(ctx["visual_ref_ids"]) if ctx["visual_ref_ids"] else False)
    delete("visual_reference_sets", VisualReferenceSet, VisualReferenceSet.asset_version_id.in_(ctx["visual_version_ids"]) if ctx["visual_version_ids"] else False)
    delete("visual_reference_generation_requests", VisualReferenceGenerationRequest, VisualReferenceGenerationRequest.asset_version_id.in_(ctx["visual_version_ids"]) if ctx["visual_version_ids"] else False)
    delete("character_asset_pointers", CharacterAssetPointer, CharacterAssetPointer.authority_id.in_(asset_authority_ids) if asset_authority_ids else False)
    delete("scene_asset_pointers", SceneAssetPointer, SceneAssetPointer.authority_id.in_(asset_authority_ids) if asset_authority_ids else False)
    delete("prop_asset_pointers", PropAssetPointer, PropAssetPointer.authority_id.in_(asset_authority_ids) if asset_authority_ids else False)
    # Typed authorities point at their current version with RESTRICT. Clear
    # that pointer before removing the version and registry rows.
    if asset_authority_ids:
        session.query(CharacterAssetAuthority).filter(CharacterAssetAuthority.authority_id.in_(asset_authority_ids)).update({CharacterAssetAuthority.current_version_id: None}, synchronize_session=False)
        session.query(SceneAssetAuthority).filter(SceneAssetAuthority.authority_id.in_(asset_authority_ids)).update({SceneAssetAuthority.current_version_id: None}, synchronize_session=False)
        session.query(PropAssetAuthority).filter(PropAssetAuthority.authority_id.in_(asset_authority_ids)).update({PropAssetAuthority.current_version_id: None}, synchronize_session=False)
    delete("character_asset_versions", CharacterAssetVersion, CharacterAssetVersion.authority_id.in_(asset_authority_ids) if asset_authority_ids else False)
    delete("scene_asset_versions", SceneAssetVersion, SceneAssetVersion.authority_id.in_(asset_authority_ids) if asset_authority_ids else False)
    delete("prop_asset_versions", PropAssetVersion, PropAssetVersion.authority_id.in_(asset_authority_ids) if asset_authority_ids else False)
    delete("character_asset_authorities", CharacterAssetAuthority, CharacterAssetAuthority.authority_id.in_(asset_authority_ids) if asset_authority_ids else False)
    delete("scene_asset_authorities", SceneAssetAuthority, SceneAssetAuthority.authority_id.in_(asset_authority_ids) if asset_authority_ids else False)
    delete("prop_asset_authorities", PropAssetAuthority, PropAssetAuthority.authority_id.in_(asset_authority_ids) if asset_authority_ids else False)
    delete("production_asset_version_registry", ProductionAssetVersionRegistry, ProductionAssetVersionRegistry.authority_id.in_(asset_authority_ids) if asset_authority_ids else False)
    delete("production_asset_authority_registry", ProductionAssetAuthorityRegistry, ProductionAssetAuthorityRegistry.authority_id.in_(asset_authority_ids) if asset_authority_ids else False)
    # Agent session children and fact snapshot records have no FK constraints;
    # scope them explicitly before deleting their direct parents.
    delete("agent_audit_logs", AgentAuditLog, AgentAuditLog.session_id.in_(agent_session_ids) if agent_session_ids else False)
    delete("agent_messages", AgentMessage, AgentMessage.session_id.in_(agent_session_ids) if agent_session_ids else False)
    delete("agent_plans", AgentPlan, AgentPlan.session_id.in_(agent_session_ids) if agent_session_ids else False)
    delete("fact_records", FactRecord, FactRecord.snapshot_id.in_(fact_snapshot_ids) if fact_snapshot_ids else False)
    return counts


def _audit_indirect_scope(session: Any, ctx: dict[str, Any]) -> dict[str, int]:
    """Count known indirect children after a scope mutation."""

    from models import (
        AutomaticKeyframePlan,
        AgentAuditLog,
        AgentMessage,
        AgentPlan,
        CharacterAssetAuthority,
        CharacterAssetPointer,
        CharacterAssetVersion,
        CharacterReferenceAsset,
        DirectorPlan,
        DirectorReasoning,
        DirectorReasoningGeneration,
        EpisodeRenderItem,
        EpisodeRenderPlan,
        Keyframe,
        KeyframeAssetBinding,
        KeyframeSequence,
        MediaCandidateRecord,
        MediaPromotionRecord,
        MediaValidationRecord,
        ProductionAssetAuthorityRegistry,
        ProductionAssetReview,
        ProductionAssetReviewHistory,
        ProductionAssetVersionRegistry,
        ProductionBatch,
        ProductionBatchItem,
        ProductionGenerationIntent,
        ProductionPromptLineage,
        ProductionPromptVersion,
        PropAssetAuthority,
        PropAssetPointer,
        PropAssetVersion,
        SceneAssetAuthority,
        SceneAssetPointer,
        SceneAssetVersion,
        SceneReferenceAsset,
        ScenePlan,
        ShotAssetBinding,
        ShotCharacterBinding,
        ShotDirection,
        ShotSceneBinding,
        ShotStyleBinding,
        StoryBeat,
        StoryboardPlan,
        StoryboardPlanShot,
        StyleReferenceAsset,
        VideoGenerationIntent,
        VisualDecision,
        VisualReferenceAuthority,
        VisualReferenceGenerationRequest,
        VisualReferenceSet,
        FactRecord,
    )
    from models import OfficialMediaAuthority

    rows: dict[str, int] = {}
    shots = ctx["shot_ids"]
    execution_ids = ctx["execution_ids"]
    candidate_ids = ctx["candidate_ids"]
    official_version_ids = ctx["official_version_ids"]
    authority_ids = ctx["asset_authority_ids"]
    version_ids = ctx["asset_version_ids"]
    visual_version_ids = ctx["visual_version_ids"]
    visual_ref_ids = ctx["visual_ref_ids"]
    outline_ids = ctx["outline_ids"]
    plan_ids = ctx.get("shot_plan_ids", set())
    materialization_ids = ctx.get("materialization_set_ids", set())
    episode_keys = ctx["episode_keys"]
    agent_session_ids = ctx.get("agent_session_ids", set())
    fact_snapshot_ids = ctx.get("fact_snapshot_ids", set())
    director_scope = _resolve_director_runtime_scope(session, ctx)
    reasoning_ids = set(director_scope["reasoning_ids"])

    def count(name: str, model: Any, criterion: Any) -> None:
        value = int(session.query(model).filter(criterion).count())
        if value:
            rows[name] = value

    count("keyframe_asset_bindings", KeyframeAssetBinding, KeyframeAssetBinding.storyboard_shot_id.in_(shots) if shots else False)
    sequences = session.query(KeyframeSequence.id).filter(KeyframeSequence.storyboard_shot_id.in_(shots)).all() if shots else []
    sequence_ids = {int(row[0]) for row in sequences}
    count("keyframes", Keyframe, Keyframe.keyframe_sequence_id.in_(sequence_ids) if sequence_ids else False)
    count("keyframe_sequences", KeyframeSequence, KeyframeSequence.id.in_(sequence_ids) if sequence_ids else False)
    count("automatic_keyframe_plans", AutomaticKeyframePlan, or_(AutomaticKeyframePlan.storyboard_shot_id.in_(shots) if shots else False, AutomaticKeyframePlan.storyboard_materialization_set_id.in_(materialization_ids) if materialization_ids else False) if shots or materialization_ids else False)
    count("shot_asset_bindings", ShotAssetBinding, ShotAssetBinding.storyboard_shot_id.in_(shots) if shots else False)
    count("shot_character_bindings", ShotCharacterBinding, ShotCharacterBinding.storyboard_shot_id.in_(shots) if shots else False)
    count("shot_scene_bindings", ShotSceneBinding, ShotSceneBinding.storyboard_shot_id.in_(shots) if shots else False)
    count("shot_style_bindings", ShotStyleBinding, ShotStyleBinding.storyboard_shot_id.in_(shots) if shots else False)
    count("shot_directions", ShotDirection, ShotDirection.storyboard_shot_id.in_(shots) if shots else False)
    count("video_generation_intents", VideoGenerationIntent, VideoGenerationIntent.storyboard_shot_id.in_(shots) if shots else False)
    count("production_generation_intents", ProductionGenerationIntent, ProductionGenerationIntent.shot_id.in_(shots) if shots else False)
    count("production_prompt_lineages", ProductionPromptLineage, ProductionPromptLineage.shot_id.in_(shots) if shots else False)
    count("production_prompt_versions", ProductionPromptVersion, ProductionPromptVersion.storyboard_plan_id.in_(plan_ids) if plan_ids else False)
    count("media_promotions", MediaPromotionRecord, or_(MediaPromotionRecord.execution_id.in_(execution_ids), MediaPromotionRecord.candidate_id.in_(candidate_ids)) if execution_ids or candidate_ids else False)
    count("media_validations", MediaValidationRecord, or_(MediaValidationRecord.execution_id.in_(execution_ids), MediaValidationRecord.candidate_id.in_(candidate_ids)) if execution_ids or candidate_ids else False)
    count("media_candidates", MediaCandidateRecord, MediaCandidateRecord.execution_id.in_(execution_ids) if execution_ids else False)
    count("official_media_authorities", OfficialMediaAuthority, OfficialMediaAuthority.official_media_version_id.in_(official_version_ids) if official_version_ids else False)
    count("episode_render_items", EpisodeRenderItem, EpisodeRenderItem.shot_id.in_(shots) if shots else False)
    count("episode_render_plans", EpisodeRenderPlan, or_(EpisodeRenderPlan.project_id == ctx["book_id"], EpisodeRenderPlan.episode_id.in_(outline_ids) if outline_ids else False))
    count("production_batch_items", ProductionBatchItem, ProductionBatchItem.execution_id.in_(execution_ids) if execution_ids else False)
    count("production_batches", ProductionBatch, or_(ProductionBatch.project_id == ctx["book_id"], ProductionBatch.episode_id.in_(outline_ids) if outline_ids else False))
    count("character_reference_assets", CharacterReferenceAsset, CharacterReferenceAsset.character_id.in_(ctx["character_ids"]) if ctx["character_ids"] else False)
    count("scene_reference_assets", SceneReferenceAsset, SceneReferenceAsset.scene_id.in_(ctx["location_ids"]) if ctx["location_ids"] else False)
    count("style_reference_assets", StyleReferenceAsset, StyleReferenceAsset.style_id.in_(ctx["style_ids"]) if ctx["style_ids"] else False)
    count("visual_reference_authorities", VisualReferenceAuthority, VisualReferenceAuthority.visual_reference_asset_id.in_(visual_ref_ids) if visual_ref_ids else False)
    count("visual_reference_sets", VisualReferenceSet, VisualReferenceSet.asset_version_id.in_(visual_version_ids) if visual_version_ids else False)
    count("visual_reference_generation_requests", VisualReferenceGenerationRequest, VisualReferenceGenerationRequest.asset_version_id.in_(visual_version_ids) if visual_version_ids else False)
    count("production_asset_reviews", ProductionAssetReview, ProductionAssetReview.asset_version_id.in_(version_ids) if version_ids else False)
    count("production_asset_review_history", ProductionAssetReviewHistory, ProductionAssetReviewHistory.asset_version_id.in_(version_ids) if version_ids else False)
    count("director_reasoning_generations", DirectorReasoningGeneration, DirectorReasoningGeneration.id.in_(director_scope["generation_ids"]) if director_scope["generation_ids"] else False)
    for name, model in (("character_asset_authorities", CharacterAssetAuthority), ("scene_asset_authorities", SceneAssetAuthority), ("prop_asset_authorities", PropAssetAuthority), ("character_asset_pointers", CharacterAssetPointer), ("scene_asset_pointers", SceneAssetPointer), ("prop_asset_pointers", PropAssetPointer)):
        count(name, model, model.authority_id.in_(authority_ids) if authority_ids else False)
    for name, model in (("character_asset_versions", CharacterAssetVersion), ("scene_asset_versions", SceneAssetVersion), ("prop_asset_versions", PropAssetVersion)):
        count(name, model, model.authority_id.in_(authority_ids) if authority_ids else False)
    count("production_asset_versions", ProductionAssetVersionRegistry, ProductionAssetVersionRegistry.authority_id.in_(authority_ids) if authority_ids else False)
    count("production_asset_authorities", ProductionAssetAuthorityRegistry, ProductionAssetAuthorityRegistry.authority_id.in_(authority_ids) if authority_ids else False)
    count("agent_audit_logs", AgentAuditLog, AgentAuditLog.session_id.in_(agent_session_ids) if agent_session_ids else False)
    count("agent_messages", AgentMessage, AgentMessage.session_id.in_(agent_session_ids) if agent_session_ids else False)
    count("agent_plans", AgentPlan, AgentPlan.session_id.in_(agent_session_ids) if agent_session_ids else False)
    count("fact_records", FactRecord, FactRecord.snapshot_id.in_(fact_snapshot_ids) if fact_snapshot_ids else False)
    for name, ids in (("director_plans", director_scope["plan_ids"]), ("director_reasonings", director_scope["reasoning_ids"]), ("director_storyboard_plans", director_scope["storyboard_plan_ids"])):
        if ids:
            rows[name] = len(ids)
    if rows:
        rows["total"] = sum(rows.values())
    return rows


def delete_book_scope(session: Any, *, book_id: int) -> dict[str, Any]:
    """Delete a Book and its canonical graph in one transaction."""

    _assert_direct_scope_inventory()
    book = session.get(Book, int(book_id))
    if book is None:
        raise BookLifecycleError("BOOK_NOT_FOUND", "Book not found", status_code=404)
    title = str(book.title or "")
    ctx = _scope_context(session, int(book_id))
    director_scope = _resolve_director_runtime_scope(session, ctx)
    if director_scope["ambiguous_rows"]:
        raise BookLifecycleError(
            "BOOK_DELETE_DIRECTOR_SCOPE_AMBIGUOUS",
            "Director runtime ownership is ambiguous; no rows were deleted",
            status_code=409,
            details={"rows": director_scope["ambiguous_rows"], "ambiguous_rows": len(director_scope["ambiguous_rows"])},
        )
    counts = _delete_indirect_scope(session, ctx)

    models = _model_by_table()
    # Parent direct rows are removed after all explicitly known children.
    direct_order = [
        "agent_attachments", "agent_project_updates", "agent_sessions", "agent_violation_logs",
        "asset_semantic_governance_records", "production_export_records", "director_benchmark_runs",
        "decision_packet_records", "qa_issues", "qa_results", "repair_attempts", "task_runs",
        "storyboard_transition_continuity_reviews", "storyboard_transition_contracts", "storyboard_transition_frames",
        "storyboard_video_retry_attempts", "storyboard_acceptance_records", "storyboard_prompt_versions",
        "prompt_ir_authorities", "prompt_ir_pointers", "prompt_ir_versions",
        "storyboard_materialization_pointers", "storyboard_materialization_sets",
        "shot_plan_authorities", "shot_plan_pointers", "shot_plans",
        "shot_style_bindings",
        "scene_blocking_authorities", "scene_blocking_pointers", "scene_blockings",
        "director_treatment_authorities", "director_treatment_pointers", "director_treatments",
        "generation_execution_attempt_lineages", "generation_execution_records",
        "official_media_pointers", "official_media_versions",
        "script_versions", "script_ir_versions", "scripts", "episode_outlines",
        "scene_characters", "scene_props", "storyboard_shots",
        "character_stages", "character_profiles", "visual_reference_assets",
        "visual_asset_pointers", "visual_asset_versions", "visual_authoring_decision_requests",
        "visual_authoring_decisions", "visual_authoring_proposals", "visual_era_specs",
        "visual_locations", "visual_makeups", "visual_props", "visual_style_profiles",
        "fact_snapshots",
        "chapters", "book_bibles",
    ]
    for table_name in direct_order:
        model = models.get(table_name)
        if model is None or not hasattr(model, "book_id"):
            continue
        count = _delete_rows(session, model, model.book_id == int(book_id))
        if count:
            counts[table_name] = counts.get(table_name, 0) + count
    session.delete(book)
    session.commit()

    with Session() as verify:
        has_neighbor = verify.query(Book).filter(Book.title == title, Book.id != int(book_id)).first() is not None
    filesystem = _remove_scoped_files(int(book_id), title, has_same_title_neighbor=has_neighbor)
    with Session() as verify:
        remaining = audit_book_scope(verify, int(book_id))
        indirect_remaining = _audit_indirect_scope(verify, ctx)
    remaining["indirect_rows"] = indirect_remaining
    remaining["orphan_rows"] = int(remaining.get("total_rows", 0)) + int(indirect_remaining.get("total", 0))
    return {
        "ok": True,
        "deleted": title,
        "book_id": int(book_id),
        "deleted_rows": counts,
        "filesystem": filesystem,
        "orphan_rows": int(remaining.get("orphan_rows", 0)),
        "ambiguous_rows": 0,
        "orphan_audit": remaining,
    }


def audit_book_scope(session_or_factory: Any, book_id: int) -> dict[str, Any]:
    """Count remaining rows for a deleted scope, including direct inventory."""

    close = False
    session = session_or_factory
    if not hasattr(session, "query"):
        session = session_or_factory()
        close = True
    try:
        models = _model_by_table()
        rows: dict[str, int] = {}
        for table_name in DIRECT_BOOK_SCOPE_TABLES:
            model = models.get(table_name)
            if model is not None and hasattr(model, "book_id"):
                count = int(session.query(model).filter(model.book_id == int(book_id)).count())
                if count:
                    rows[table_name] = count
        rows["books"] = int(session.query(Book).filter(Book.id == int(book_id)).count())
        return {"book_id": int(book_id), "rows": rows, "total_rows": sum(rows.values()), "direct_inventory": direct_book_scope_inventory(), "orphan_rows": sum(rows.values())}
    finally:
        if close:
            session.close()


__all__ = [
    "BookLifecycleError",
    "DIRECT_BOOK_SCOPE_TABLES",
    "direct_book_scope_inventory",
    "create_book",
    "create_script",
    "serialize_book",
    "delete_book_scope",
    "audit_book_scope",
]
