"""Human review workflow and production gate for typed asset versions.

The review layer is deliberately separate from the Asset Authority graph.  A
Version can be normalized and AI validated without becoming a Pointer target;
only :func:`activate_production_asset_version_after_review` can move the
Pointer after a recorded human approval.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Mapping

from models import (
    CharacterAssetVersion,
    ProductionAssetReview,
    ProductionAssetReviewHistory,
    SceneAssetVersion,
    PropAssetVersion,
    ProductionPromptLineage,
)

from core.production_asset_authority import (
    AssetBindingInvalid,
    ProductionAssetSchemaError,
    _asset_type,
    _typed_config,
    bind_shot_assets,
    ingest_production_asset,
    _switch_current_production_asset_version,
)


SCHEMA_VERSION = "production_asset_review_workflow_v1"
REVIEW_STATES = (
    "GENERATED",
    "NORMALIZED",
    "AI_VALIDATED",
    "HUMAN_REVIEW_PENDING",
    "HUMAN_APPROVED",
    "PRODUCTION_READY",
    "ARCHIVED",
    "REJECTED",
    "REQUEST_CHANGE",
)
REVIEWER_TYPES = ("DIRECTOR", "ART_DIRECTOR", "PRODUCER", "SYSTEM")
HUMAN_REVIEWERS = ("DIRECTOR", "ART_DIRECTOR", "PRODUCER")
REVIEW_DECISIONS = ("APPROVE", "REJECT", "REQUEST_CHANGE")

_ALLOWED_TRANSITIONS: dict[str | None, set[str]] = {
    None: {"GENERATED"},
    "GENERATED": {"NORMALIZED"},
    "NORMALIZED": {"AI_VALIDATED"},
    "AI_VALIDATED": {"HUMAN_REVIEW_PENDING"},
    "HUMAN_REVIEW_PENDING": {"HUMAN_APPROVED", "REJECTED", "REQUEST_CHANGE"},
    "HUMAN_APPROVED": {"PRODUCTION_READY"},
    "PRODUCTION_READY": {"ARCHIVED"},
    "REJECTED": {"ARCHIVED"},
    "REQUEST_CHANGE": {"ARCHIVED"},
    "ARCHIVED": set(),
}


class ProductionAssetReviewError(ProductionAssetSchemaError):
    """Raised when a review transition or gate is invalid."""

    status_code = 409
    code = "PRODUCTION_ASSET_REVIEW_INVALID"

    def __init__(self, message: str, *, diagnostics: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics or []


class ProductionAssetReviewGateError(ProductionAssetReviewError):
    code = "PRODUCTION_REVIEW_REQUIRED"

    def __init__(self, report: Mapping[str, Any]):
        self.report = dict(report)
        failed = ", ".join(report.get("failed_checks") or []) or "review gate failed"
        super().__init__(f"production review gate blocked: {failed}", diagnostics=[dict(report)])


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _token(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()[:24]


def _version_model(asset_type: str):
    return {"CHARACTER": CharacterAssetVersion, "SCENE": SceneAssetVersion, "PROP": PropAssetVersion}[_asset_type(asset_type)]


def _version_row(session: Any, *, asset_type: str, asset_id: str, asset_version_id: str):
    kind = _asset_type(asset_type)
    config = _typed_config(kind)
    model = _version_model(kind)
    row = session.query(model).filter_by(version_id=str(asset_version_id), **{config["entity"]: str(asset_id)}).one_or_none()
    if row is None:
        raise ProductionAssetReviewError(
            "asset version does not exist for the declared identity",
            diagnostics=[{"asset_type": kind, "asset_id": asset_id, "asset_version_id": asset_version_id}],
        )
    return kind, config, row


def _review_id(session: Any, *, asset_type: str, asset_id: str, asset_version_id: str) -> str:
    base = _token({"asset_type": asset_type, "asset_id": asset_id, "asset_version_id": asset_version_id})
    ordinal = session.query(ProductionAssetReview).filter_by(asset_version_id=asset_version_id).count() + 1
    return f"par_{base}_{ordinal:02d}"


def _history_id(session: Any, *, review_id: str, from_state: str | None, to_state: str, ordinal: int) -> str:
    return f"parh_{_token({'review_id': review_id, 'from': from_state, 'to': to_state, 'ordinal': ordinal})}"


def _as_dict(row: ProductionAssetReview) -> dict[str, Any]:
    return {
        "review_id": row.review_id,
        "asset_type": row.asset_type,
        "asset_id": row.asset_id,
        "asset_version_id": row.asset_version_id,
        "prompt_lineage_id": row.prompt_lineage_id,
        "review_state": row.review_state,
        "reviewer_type": row.reviewer_type,
        "decision": row.decision,
        "comment": row.comment or "",
        "version_fingerprint": row.version_fingerprint,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def review_history(session: Any, review_id: str) -> list[dict[str, Any]]:
    rows = session.query(ProductionAssetReviewHistory).filter_by(review_id=review_id).order_by(ProductionAssetReviewHistory.id.asc()).all()
    return [
        {
            "history_id": row.history_id,
            "review_id": row.review_id,
            "asset_version_id": row.asset_version_id,
            "from": row.from_state,
            "to": row.to_state,
            "actor": row.actor,
            "decision": row.decision,
            "comment": row.comment or "",
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def create_production_asset_review(
    session: Any,
    *,
    asset_type: str,
    asset_id: str,
    asset_version_id: str,
    reviewer_type: str = "SYSTEM",
    comment: str = "",
    prompt_lineage_id: str | None = None,
) -> dict[str, Any]:
    """Create an immutable review workflow at ``GENERATED``."""
    kind, _, version = _version_row(session, asset_type=asset_type, asset_id=asset_id, asset_version_id=asset_version_id)
    if prompt_lineage_id:
        lineage = session.query(ProductionPromptLineage).filter_by(prompt_lineage_id=str(prompt_lineage_id)).one_or_none()
        if lineage is None or str(lineage.asset_version_id) != str(asset_version_id) or int(lineage.shot_id) <= 0:
            raise ProductionAssetReviewError("prompt_lineage_id does not match the reviewed asset version")
    actor = str(reviewer_type or "SYSTEM").upper()
    if actor not in REVIEWER_TYPES:
        raise ProductionAssetReviewError(f"unsupported reviewer_type: {actor}")
    if actor != "SYSTEM":
        raise ProductionAssetReviewError("a new generated asset review must start with SYSTEM")
    review = ProductionAssetReview(
        review_id=_review_id(session, asset_type=kind, asset_id=asset_id, asset_version_id=asset_version_id),
        asset_type=kind,
        asset_id=str(asset_id),
        asset_version_id=str(asset_version_id),
        prompt_lineage_id=str(prompt_lineage_id) if prompt_lineage_id else None,
        review_state="GENERATED",
        reviewer_type=actor,
        decision=None,
        comment=str(comment or ""),
        version_fingerprint=_version_fingerprint(version),
    )
    session.add(review)
    session.flush()
    history = ProductionAssetReviewHistory(
        history_id=_history_id(session, review_id=review.review_id, from_state=None, to_state="GENERATED", ordinal=1),
        review_id=review.review_id,
        asset_version_id=review.asset_version_id,
        from_state=None,
        to_state="GENERATED",
        actor="SYSTEM",
        decision=None,
        comment=str(comment or ""),
    )
    session.add(history)
    session.flush()
    return _as_dict(review)


def _version_fingerprint(version: Any) -> str:
    return _token({
        "authority_id": version.authority_id,
        "version_id": version.version_id,
        "revision": int(version.revision or 0),
        "storage_identity": version.storage_identity,
        "checksum": version.checksum,
        "metadata_hash": version.metadata_hash,
    })


def _validate_transition(*, current: str, target: str, actor: str, decision: str | None, internal_activation: bool) -> None:
    if target not in REVIEW_STATES:
        raise ProductionAssetReviewError(f"unsupported review_state: {target}")
    if target not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise ProductionAssetReviewError(f"invalid review transition {current} -> {target}")
    if target == "PRODUCTION_READY" and not internal_activation:
        raise ProductionAssetReviewError("PRODUCTION_READY requires the pointer activation gate")
    if target in {"NORMALIZED", "AI_VALIDATED", "HUMAN_REVIEW_PENDING"} and actor != "SYSTEM":
        raise ProductionAssetReviewError(f"{target} is a system transition")
    if target in {"HUMAN_APPROVED", "REJECTED", "REQUEST_CHANGE"}:
        if actor not in HUMAN_REVIEWERS:
            raise ProductionAssetReviewError("human review decision requires a human reviewer")
        expected = {"HUMAN_APPROVED": "APPROVE", "REJECTED": "REJECT", "REQUEST_CHANGE": "REQUEST_CHANGE"}[target]
        if decision != expected:
            raise ProductionAssetReviewError(f"{target} requires decision={expected}")
    if target == "ARCHIVED" and actor not in REVIEWER_TYPES:
        raise ProductionAssetReviewError("archiving requires a known actor")


def transition_production_asset_review(
    session: Any,
    *,
    review_id: str,
    to_state: str,
    reviewer_type: str,
    decision: str | None = None,
    comment: str = "",
    _internal_activation: bool = False,
) -> dict[str, Any]:
    """Append one legal state transition and update only the current snapshot."""
    actor = str(reviewer_type or "").upper()
    target = str(to_state or "").upper()
    decision_value = str(decision).upper() if decision else None
    if actor not in REVIEWER_TYPES:
        raise ProductionAssetReviewError(f"unsupported reviewer_type: {actor}")
    if decision_value is not None and decision_value not in REVIEW_DECISIONS:
        raise ProductionAssetReviewError(f"unsupported decision: {decision_value}")
    review = session.query(ProductionAssetReview).filter_by(review_id=str(review_id)).one_or_none()
    if review is None:
        raise ProductionAssetReviewError("review_id does not exist")
    current = str(review.review_state)
    _validate_transition(current=current, target=target, actor=actor, decision=decision_value, internal_activation=_internal_activation)
    ordinal = session.query(ProductionAssetReviewHistory).filter_by(review_id=review.review_id).count() + 1
    session.add(ProductionAssetReviewHistory(
        history_id=_history_id(session, review_id=review.review_id, from_state=current, to_state=target, ordinal=ordinal),
        review_id=review.review_id,
        asset_version_id=review.asset_version_id,
        from_state=current,
        to_state=target,
        actor=actor,
        decision=decision_value,
        comment=str(comment or ""),
    ))
    review.review_state = target
    review.reviewer_type = actor
    if decision_value is not None:
        review.decision = decision_value
    review.comment = str(comment or "")
    review.updated_at = datetime.utcnow()
    session.flush()
    return _as_dict(review)


def production_review_gate(
    session: Any,
    *,
    asset_type: str,
    asset_id: str,
    asset_version_id: str,
) -> dict[str, Any]:
    """Evaluate the exact gate required before a Pointer may activate."""
    try:
        kind, _, version = _version_row(session, asset_type=asset_type, asset_id=asset_id, asset_version_id=asset_version_id)
    except ProductionAssetReviewError:
        kind = _asset_type(asset_type)
        return {
            "schema_version": SCHEMA_VERSION,
            "asset_type": kind,
            "asset_id": str(asset_id),
            "asset_version_id": str(asset_version_id),
            "allowed": False,
            "checks": {"asset_exists": False, "asset_normalized": False, "ai_validation_passed": False, "human_review_exists": False, "human_decision_approve": False},
            "failed_checks": ["asset_exists", "asset_normalized", "ai_validation_passed", "human_review_exists", "human_decision_approve"],
            "review_id": None,
            "review_state": None,
            "history_count": 0,
        }
    reviews = session.query(ProductionAssetReview).filter_by(asset_type=kind, asset_id=str(asset_id), asset_version_id=str(asset_version_id)).order_by(ProductionAssetReview.id.desc()).all()
    latest = reviews[0] if reviews else None
    history = review_history(session, latest.review_id) if latest else []
    has_transition = lambda state: any(item["to"] == state for item in history)
    human_approval = any(item["to"] == "HUMAN_APPROVED" and item["actor"] in HUMAN_REVIEWERS and item["decision"] == "APPROVE" for item in history)
    checks = {
        "asset_exists": version is not None,
        "asset_normalized": bool(version.storage_identity and version.checksum and version.metadata_hash),
        "ai_validation_passed": has_transition("AI_VALIDATED"),
        "human_review_exists": human_approval,
        "human_decision_approve": bool(latest and latest.decision == "APPROVE" and latest.review_state == "HUMAN_APPROVED"),
    }
    failed = [key for key, value in checks.items() if not value]
    return {
        "schema_version": SCHEMA_VERSION,
        "asset_type": kind,
        "asset_id": str(asset_id),
        "asset_version_id": str(asset_version_id),
        "allowed": not failed,
        "checks": checks,
        "failed_checks": failed,
        "review_id": latest.review_id if latest else None,
        "review_state": latest.review_state if latest else None,
        "history_count": len(history),
    }


def activate_production_asset_version_after_review(
    session: Any,
    *,
    review_id: str,
    book_id: int = 990401,
) -> dict[str, Any]:
    """Pass the review gate, activate the Pointer, then mark the review ready."""
    review = session.query(ProductionAssetReview).filter_by(review_id=str(review_id)).one_or_none()
    if review is None:
        raise ProductionAssetReviewError("review_id does not exist")
    gate = production_review_gate(
        session,
        asset_type=review.asset_type,
        asset_id=review.asset_id,
        asset_version_id=review.asset_version_id,
    )
    if not gate["allowed"]:
        raise ProductionAssetReviewGateError(gate)
    nested = session.begin_nested()
    try:
        switched = _switch_current_production_asset_version(
            session,
            entity_type=review.asset_type,
            entity_id=review.asset_id,
            version_id=review.asset_version_id,
            book_id=book_id,
        )
        ready = transition_production_asset_review(
            session,
            review_id=review.review_id,
            to_state="PRODUCTION_READY",
            reviewer_type="SYSTEM",
            decision="APPROVE",
            comment="Pointer activated after human approval.",
            _internal_activation=True,
        )
        nested.commit()
    except Exception:
        nested.rollback()
        raise
    return {"gate": gate, "switch": switched, "review": ready}


def create_new_version_after_request_change(
    session: Any,
    *,
    review_id: str,
    source: Mapping[str, Any],
    book_id: int = 990401,
) -> dict[str, Any]:
    """Retire a request-change review and ingest a new, non-pointer version."""
    review = session.query(ProductionAssetReview).filter_by(review_id=str(review_id)).one_or_none()
    if review is None or review.review_state != "REQUEST_CHANGE":
        raise ProductionAssetReviewError("request-change review is required before creating a new version")
    transition_production_asset_review(
        session,
        review_id=review.review_id,
        to_state="ARCHIVED",
        reviewer_type="SYSTEM",
        comment="Archived after request change; replacement version created.",
    )
    ingested = ingest_production_asset(
        session,
        entity_type=review.asset_type,
        entity_id=review.asset_id,
        source=source,
        book_id=book_id,
        activate_pointer=False,
    )
    replacement = create_production_asset_review(
        session,
        asset_type=review.asset_type,
        asset_id=review.asset_id,
        asset_version_id=ingested["version_id"],
        comment="Replacement version created after REQUEST_CHANGE.",
    )
    return {"previous_review_id": review.review_id, "replacement_version": ingested, "replacement_review": replacement}


def run_review_path(session: Any, *, review_id: str, decision: str | None = None, reviewer_type: str = "DIRECTOR") -> dict[str, Any]:
    """Advance the deterministic fixture through its system and human steps."""
    for state in ("NORMALIZED", "AI_VALIDATED", "HUMAN_REVIEW_PENDING"):
        transition_production_asset_review(session, review_id=review_id, to_state=state, reviewer_type="SYSTEM")
    if decision == "APPROVE":
        return transition_production_asset_review(session, review_id=review_id, to_state="HUMAN_APPROVED", reviewer_type=reviewer_type, decision="APPROVE")
    if decision == "REJECT":
        return transition_production_asset_review(session, review_id=review_id, to_state="REJECTED", reviewer_type=reviewer_type, decision="REJECT")
    if decision == "REQUEST_CHANGE":
        return transition_production_asset_review(session, review_id=review_id, to_state="REQUEST_CHANGE", reviewer_type=reviewer_type, decision="REQUEST_CHANGE")
    raise ProductionAssetReviewError("fixture decision is required")


__all__ = [
    "SCHEMA_VERSION",
    "REVIEW_STATES",
    "REVIEWER_TYPES",
    "HUMAN_REVIEWERS",
    "REVIEW_DECISIONS",
    "ProductionAssetReviewError",
    "ProductionAssetReviewGateError",
    "create_production_asset_review",
    "transition_production_asset_review",
    "review_history",
    "production_review_gate",
    "activate_production_asset_version_after_review",
    "create_new_version_after_request_change",
    "run_review_path",
]
