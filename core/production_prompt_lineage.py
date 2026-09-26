"""Provider-free Prompt -> Intent -> Asset -> Review lineage services."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from typing import Any, Mapping

from models import (
    ProductionAssetReview,
    ProductionAssetReviewHistory,
    ProductionAssetVersionRegistry,
    ProductionGenerationIntent,
    ProductionPromptLineage,
    ProductionPromptVersion,
    StoryboardShot,
)

from core.production_asset_authority import (
    ProductionAssetSchemaError,
    _asset_type,
    _typed_config,
    ingest_production_asset,
)


SCHEMA_VERSION = "production_prompt_lineage_v1"


class ProductionPromptLineageError(ProductionAssetSchemaError):
    """Raised when a prompt lineage contract would be violated."""

    status_code = 409
    code = "PRODUCTION_PROMPT_LINEAGE_INVALID"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def prompt_fingerprint(prompt_text: str, prompt_structure: Mapping[str, Any] | None = None) -> str:
    """Return the stable content fingerprint for a prompt version."""
    basis = {"prompt_text": str(prompt_text), "prompt_structure": dict(prompt_structure or {})}
    return "sha256:" + hashlib.sha256(_canonical(basis).encode("utf-8")).hexdigest()


def _token(value: Any, prefix: str) -> str:
    return prefix + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()[:24]


def _json(value: Any) -> str:
    return _canonical(value if isinstance(value, Mapping) else {})


def _load_json(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _prompt_dict(row: ProductionPromptVersion) -> dict[str, Any]:
    return {
        "prompt_version_id": row.prompt_version_id,
        "prompt_id": row.prompt_id,
        "version_number": int(row.version_number),
        "prompt_text": row.prompt_text,
        "prompt_structure": _load_json(row.prompt_structure),
        "prompt_fingerprint": row.prompt_fingerprint,
        "created_from": row.created_from,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _intent_dict(row: ProductionGenerationIntent) -> dict[str, Any]:
    return {
        "generation_intent_id": row.generation_intent_id,
        "shot_id": int(row.shot_id),
        "character_requirements": _load_json(row.character_requirements),
        "scene_requirements": _load_json(row.scene_requirements),
        "camera_requirements": _load_json(row.camera_requirements),
        "style_requirements": _load_json(row.style_requirements),
        "constraint_snapshot": _load_json(row.constraint_snapshot),
        "shot_requirement_snapshot": _load_json(row.shot_requirement_snapshot),
        "shot_requirement_fingerprint": row.shot_requirement_fingerprint,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def create_production_prompt_version(
    session: Any,
    *,
    prompt_id: str,
    prompt_text: str,
    prompt_structure: Mapping[str, Any] | None = None,
    created_from: str = "SHOT_REQUIREMENT",
) -> dict[str, Any]:
    """Append a prompt version; existing versions are never updated."""
    prompt_key = str(prompt_id or "").strip()
    text = str(prompt_text or "")
    if not prompt_key or not text.strip():
        raise ProductionPromptLineageError("prompt_id and prompt_text are required")
    existing = (
        session.query(ProductionPromptVersion)
        .filter_by(prompt_id=prompt_key)
        .order_by(ProductionPromptVersion.version_number.desc())
        .first()
    )
    number = int(existing.version_number) + 1 if existing else 1
    structure = dict(prompt_structure or {})
    fingerprint = prompt_fingerprint(text, structure)
    row = ProductionPromptVersion(
        prompt_version_id=f"ppv_{_token({'prompt_id': prompt_key, 'version_number': number, 'fingerprint': fingerprint}, '')}",
        prompt_id=prompt_key,
        version_number=number,
        prompt_text=text,
        prompt_structure=_json(structure),
        prompt_fingerprint=fingerprint,
        created_from=str(created_from or "SHOT_REQUIREMENT"),
    )
    session.add(row)
    session.flush()
    return _prompt_dict(row)


def get_prompt_version(session: Any, prompt_version_id: str) -> ProductionPromptVersion:
    row = session.query(ProductionPromptVersion).filter_by(prompt_version_id=str(prompt_version_id)).one_or_none()
    if row is None:
        raise ProductionPromptLineageError("prompt_version_id does not exist")
    return row


def update_production_prompt_version(*args: Any, **kwargs: Any) -> None:
    """Explicitly reject mutation of an existing prompt version."""
    raise ProductionPromptLineageError("prompt versions are immutable; create a new version")


def create_production_generation_intent(
    session: Any,
    *,
    shot_id: int,
    shot_requirement: Mapping[str, Any],
    character_requirements: Mapping[str, Any] | None = None,
    scene_requirements: Mapping[str, Any] | None = None,
    camera_requirements: Mapping[str, Any] | None = None,
    style_requirements: Mapping[str, Any] | None = None,
    constraint_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist an intent whose source is an explicit Shot Requirement snapshot."""
    shot = session.query(StoryboardShot).filter_by(id=int(shot_id)).one_or_none()
    if shot is None:
        raise ProductionPromptLineageError("generation intent requires an existing shot")
    if not isinstance(shot_requirement, Mapping) or not shot_requirement:
        raise ProductionPromptLineageError("generation intent must be derived from a non-empty shot requirement")
    snapshot = deepcopy(dict(shot_requirement))
    requirement_fp = "sha256:" + hashlib.sha256(_canonical(snapshot).encode("utf-8")).hexdigest()
    basis = {"shot_id": int(shot_id), "shot_requirement_fingerprint": requirement_fp}
    existing = session.query(ProductionGenerationIntent).filter_by(generation_intent_id=_token(basis, "pgi_")).one_or_none()
    if existing is not None:
        return _intent_dict(existing)
    row = ProductionGenerationIntent(
        generation_intent_id=_token(basis, "pgi_"),
        shot_id=int(shot_id),
        character_requirements=_json(character_requirements),
        scene_requirements=_json(scene_requirements),
        camera_requirements=_json(camera_requirements),
        style_requirements=_json(style_requirements),
        constraint_snapshot=_json(constraint_snapshot),
        shot_requirement_snapshot=_json(snapshot),
        shot_requirement_fingerprint=requirement_fp,
    )
    session.add(row)
    session.flush()
    return _intent_dict(row)


def _asset_version_row(session: Any, *, asset_type: str, asset_id: str, asset_version_id: str):
    kind = _asset_type(asset_type)
    config = _typed_config(kind)
    row = session.query(config["version"]).filter_by(version_id=str(asset_version_id)).one_or_none()
    if row is None or str(getattr(row, config["entity"])) != str(asset_id):
        raise ProductionPromptLineageError("asset version does not match the declared asset identity")
    registry = session.query(ProductionAssetVersionRegistry).filter_by(version_id=str(asset_version_id)).one_or_none()
    if registry is None:
        raise ProductionPromptLineageError("asset version registry row is missing")
    return kind, row


def create_production_prompt_lineage(
    session: Any,
    *,
    asset_type: str,
    asset_id: str,
    asset_version_id: str,
    shot_id: int,
    prompt_version_id: str,
    generation_intent_id: str,
) -> dict[str, Any]:
    """Create one immutable Prompt -> Intent -> Asset lineage edge."""
    kind, _ = _asset_version_row(session, asset_type=asset_type, asset_id=asset_id, asset_version_id=asset_version_id)
    shot = session.query(StoryboardShot).filter_by(id=int(shot_id)).one_or_none()
    if shot is None:
        raise ProductionPromptLineageError("prompt lineage requires an existing shot")
    prompt = get_prompt_version(session, prompt_version_id)
    intent = session.query(ProductionGenerationIntent).filter_by(generation_intent_id=str(generation_intent_id)).one_or_none()
    if intent is None:
        raise ProductionPromptLineageError("generation_intent_id does not exist")
    if int(intent.shot_id) != int(shot_id):
        raise ProductionPromptLineageError("generation intent and prompt lineage shot_id must match")
    existing = session.query(ProductionPromptLineage).filter_by(asset_version_id=str(asset_version_id)).first()
    if existing is not None:
        # Multiple prompt/intent attempts are allowed for a version only when
        # they are an exact replay of the existing edge.
        if (existing.prompt_version_id, existing.generation_intent_id, int(existing.shot_id)) != (str(prompt_version_id), str(generation_intent_id), int(shot_id)):
            raise ProductionPromptLineageError("asset version already has a different prompt lineage")
        return {
            "prompt_lineage_id": existing.prompt_lineage_id,
            "asset_type": kind,
            "asset_id": str(asset_id),
            "asset_version_id": existing.asset_version_id,
            "shot_id": int(existing.shot_id),
            "prompt_version_id": existing.prompt_version_id,
            "generation_intent_id": existing.generation_intent_id,
            "prompt_fingerprint": existing.prompt_fingerprint,
            "created_at": existing.created_at.isoformat() if existing.created_at else None,
        }
    row = ProductionPromptLineage(
        prompt_lineage_id=_token({"asset_version_id": str(asset_version_id), "prompt_version_id": str(prompt_version_id), "generation_intent_id": str(generation_intent_id)}, "ppl_"),
        asset_id=str(asset_id),
        asset_version_id=str(asset_version_id),
        shot_id=int(shot_id),
        prompt_version_id=str(prompt_version_id),
        generation_intent_id=str(generation_intent_id),
        prompt_fingerprint=prompt.prompt_fingerprint,
    )
    session.add(row)
    session.flush()
    return {
        "prompt_lineage_id": row.prompt_lineage_id,
        "asset_type": kind,
        "asset_id": str(asset_id),
        "asset_version_id": row.asset_version_id,
        "shot_id": int(row.shot_id),
        "prompt_version_id": row.prompt_version_id,
        "generation_intent_id": row.generation_intent_id,
        "prompt_fingerprint": row.prompt_fingerprint,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def asset_has_prompt_lineage(session: Any, asset_version_id: str) -> bool:
    return session.query(ProductionPromptLineage).filter_by(asset_version_id=str(asset_version_id)).count() > 0


def trace_production_asset_version(session: Any, asset_version_id: str) -> dict[str, Any]:
    """Return the complete reverse trace from asset version to review history."""
    rows = session.query(ProductionPromptLineage).filter_by(asset_version_id=str(asset_version_id)).order_by(ProductionPromptLineage.id.asc()).all()
    if not rows:
        raise ProductionPromptLineageError("asset version has no prompt lineage")
    traces = []
    for row in rows:
        prompt = get_prompt_version(session, row.prompt_version_id)
        intent = session.query(ProductionGenerationIntent).filter_by(generation_intent_id=row.generation_intent_id).one()
        reviews = session.query(ProductionAssetReview).filter_by(asset_version_id=str(asset_version_id)).order_by(ProductionAssetReview.id.asc()).all()
        history = []
        for review in reviews:
            history.extend(
                {
                    "history_id": item.history_id,
                    "review_id": item.review_id,
                    "from": item.from_state,
                    "to": item.to_state,
                    "actor": item.actor,
                    "decision": item.decision,
                    "comment": item.comment or "",
                }
                for item in session.query(ProductionAssetReviewHistory).filter_by(review_id=review.review_id).order_by(ProductionAssetReviewHistory.id.asc()).all()
            )
        traces.append({
            "prompt_lineage_id": row.prompt_lineage_id,
            "asset_id": row.asset_id,
            "asset_version_id": row.asset_version_id,
            "shot_id": int(row.shot_id),
            "generation_intent": _intent_dict(intent),
            "prompt_version": _prompt_dict(prompt),
            "review_history": history,
        })
    first = traces[0]
    valid = all(
        item["prompt_version"]["prompt_fingerprint"] == lineage.prompt_fingerprint
        and item["generation_intent"]["shot_id"] == item["shot_id"]
        for item, lineage in zip(traces, rows)
    )
    return {
        "asset_version_id": str(asset_version_id),
        "shot_id": first["shot_id"],
        "generation_intent": first["generation_intent"],
        "prompt_version": first["prompt_version"],
        "review_history": first["review_history"],
        "lineages": traces,
        "traceability_valid": valid,
    }


def create_prompt_change_candidate(
    session: Any,
    *,
    old_asset_type: str,
    old_asset_id: str,
    old_asset_version_id: str,
    shot_id: int,
    prompt_id: str,
    prompt_text: str,
    prompt_structure: Mapping[str, Any] | None,
    shot_requirement: Mapping[str, Any],
    source: Mapping[str, Any],
    reviewer_type: str = "SYSTEM",
) -> dict[str, Any]:
    """Create Prompt vN + candidate Asset vN without replacing the Pointer."""
    if not asset_has_prompt_lineage(session, old_asset_version_id):
        raise ProductionPromptLineageError("prompt change requires lineage on the old asset version")
    kind = _asset_type(old_asset_type)
    ingested = ingest_production_asset(
        session,
        entity_type=kind,
        entity_id=str(old_asset_id),
        source=source,
        activate_pointer=False,
    )
    prompt = create_production_prompt_version(
        session,
        prompt_id=prompt_id,
        prompt_text=prompt_text,
        prompt_structure=prompt_structure,
        created_from="PROMPT_CHANGE",
    )
    intent = create_production_generation_intent(
        session,
        shot_id=shot_id,
        shot_requirement=shot_requirement,
    )
    lineage = create_production_prompt_lineage(
        session,
        asset_type=kind,
        asset_id=str(old_asset_id),
        asset_version_id=ingested["version_id"],
        shot_id=shot_id,
        prompt_version_id=prompt["prompt_version_id"],
        generation_intent_id=intent["generation_intent_id"],
    )
    from core.production_asset_review import create_production_asset_review

    review = create_production_asset_review(
        session,
        asset_type=kind,
        asset_id=str(old_asset_id),
        asset_version_id=ingested["version_id"],
        reviewer_type=reviewer_type,
        prompt_lineage_id=lineage["prompt_lineage_id"],
        comment="Prompt change candidate awaits human review.",
    )
    return {"prompt_version": prompt, "generation_intent": intent, "lineage": lineage, "asset": ingested, "review": review}


def review_reproducible_generation_context(session: Any, review_id: str) -> dict[str, Any]:
    review = session.query(ProductionAssetReview).filter_by(review_id=str(review_id)).one_or_none()
    if review is None:
        raise ProductionPromptLineageError("review_id does not exist")
    trace = trace_production_asset_version(session, review.asset_version_id)
    if review.prompt_lineage_id and trace["lineages"][0]["prompt_lineage_id"] != review.prompt_lineage_id:
        raise ProductionPromptLineageError("review prompt lineage does not match the asset trace")
    return {"review_id": str(review_id), "review": {"asset_id": review.asset_id, "asset_version_id": review.asset_version_id, "prompt_lineage_id": review.prompt_lineage_id}, "trace": trace, "reproducible": bool(trace.get("shot_id") and trace.get("prompt_version") and trace.get("generation_intent"))}


# Short aliases keep the layer convenient for callers while the explicit names
# remain the canonical public contract.
create_prompt_version = create_production_prompt_version
create_generation_intent = create_production_generation_intent
create_prompt_lineage = create_production_prompt_lineage
trace_asset_version = trace_production_asset_version
change_prompt = create_prompt_change_candidate


__all__ = [
    "SCHEMA_VERSION",
    "ProductionPromptLineageError",
    "prompt_fingerprint",
    "create_production_prompt_version",
    "get_prompt_version",
    "update_production_prompt_version",
    "create_production_generation_intent",
    "create_production_prompt_lineage",
    "asset_has_prompt_lineage",
    "trace_production_asset_version",
    "create_prompt_change_candidate",
    "review_reproducible_generation_context",
    "create_prompt_version",
    "create_generation_intent",
    "create_prompt_lineage",
    "trace_asset_version",
    "change_prompt",
]
