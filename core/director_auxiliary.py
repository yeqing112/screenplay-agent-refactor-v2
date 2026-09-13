"""Deterministic validation for Director V2.1 auxiliary-shot proposals.

Auxiliary shots are the only mechanism that may expand coverage beyond the
approved structural ShotPlan.  They therefore have a separate authority
boundary from ordinary creative field patches.  This module validates the
proposal metadata without creating or mutating shots; materialization remains
the responsibility of the existing storyboard/shot-plan pipeline.
"""

from __future__ import annotations

import copy
from typing import Any

from core.director_creative_contract import AUXILIARY_SHOT_TYPES, AUXILIARY_SHOT_POLICY


class AuxiliaryShotValidationError(ValueError):
    """Raised when an auxiliary proposal cannot be admitted safely."""

    code = "DIRECTOR_AUXILIARY_INVALID"

    def __init__(self, message: str, *, code: str | None = None, proposal_id: str = "", path: str = "") -> None:
        super().__init__(message)
        self.code = code or self.code
        self.proposal_id = proposal_id
        self.path = path


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _shot_ids(structural_shot_plan: dict[str, Any]) -> set[str]:
    return {
        _text(item.get("plan_shot_id"))
        for item in _list(structural_shot_plan.get("shots"))
        if isinstance(item, dict) and _text(item.get("plan_shot_id"))
    }


def _known_participants(contract: dict[str, Any], structural_shot_plan: dict[str, Any]) -> set[str]:
    known: set[str] = set()
    facts = _dict(_dict(contract).get("immutable_projection")).get("facts")
    for value in _list(_dict(facts).get("participants")):
        if isinstance(value, dict):
            value = value.get("character_id") or value.get("id") or value.get("name")
        if _text(value):
            known.add(_text(value))
    for shot in _list(structural_shot_plan.get("shots")):
        if not isinstance(shot, dict):
            continue
        for value in _list(shot.get("participants")):
            if isinstance(value, dict):
                value = value.get("character_id") or value.get("id") or value.get("name")
            if _text(value):
                known.add(_text(value))
        for value in _list(_dict(shot.get("asset_bindings")).get("character_asset_ids")):
            if isinstance(value, dict):
                value = value.get("character_id") or value.get("id") or value.get("name")
            if _text(value):
                known.add(_text(value))
    return known


def _source_beats(contract: dict[str, Any]) -> dict[str, Any]:
    beats = _dict(contract).get("source_beat_map")
    return beats if isinstance(beats, dict) else {}


def validate_auxiliary_shot_proposal(
    proposal: dict[str, Any],
    structural_shot_plan: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Validate one proposal against immutable source evidence.

    The returned proposal is a deep copy and can be safely attached to a
    candidate.  No ShotPlan mutation or creative inference occurs here.
    """

    if not isinstance(proposal, dict):
        raise AuxiliaryShotValidationError("auxiliary proposal must be an object")
    proposal_id = _text(proposal.get("proposal_id"))
    proposal_type = _text(proposal.get("proposal_type")).lower()
    source_beat_id = _text(proposal.get("source_beat_id"))
    anchor = _text(proposal.get("insert_after_plan_shot_id"))
    if not proposal_id:
        raise AuxiliaryShotValidationError("proposal_id is required", code="DIRECTOR_AUXILIARY_SCHEMA_INVALID", path="proposal_id")
    if proposal_type not in set(AUXILIARY_SHOT_TYPES):
        raise AuxiliaryShotValidationError(
            f"unsupported auxiliary proposal_type: {proposal_type}",
            code="INVALID_AUXILIARY_TYPE",
            proposal_id=proposal_id,
            path="proposal_type",
        )
    beats = _source_beats(contract)
    if not source_beat_id or source_beat_id not in beats:
        raise AuxiliaryShotValidationError(
            f"source beat is not bound: {source_beat_id or '<missing>'}",
            code="AUXILIARY_SHOT_UNBOUND_BEAT",
            proposal_id=proposal_id,
            path="source_beat_id",
        )
    if anchor not in _shot_ids(structural_shot_plan):
        raise AuxiliaryShotValidationError(
            f"insert anchor is unknown: {anchor or '<missing>'}",
            code="UNKNOWN_PLAN_SHOT_ID",
            proposal_id=proposal_id,
            path="insert_after_plan_shot_id",
        )
    if not _text(proposal.get("purpose")) or not _text(proposal.get("why_needed")):
        raise AuxiliaryShotValidationError(
            "purpose and why_needed are required",
            code="DIRECTOR_AUXILIARY_MOTIVATION_REQUIRED",
            proposal_id=proposal_id,
            path="why_needed",
        )
    participants = proposal.get("participants")
    if not isinstance(participants, list) or not participants or any(not _text(value) for value in participants):
        raise AuxiliaryShotValidationError(
            "participants must be a non-empty list of character IDs",
            code="INVALID_CHARACTER_REFERENCE",
            proposal_id=proposal_id,
            path="participants",
        )
    known = _known_participants(contract, structural_shot_plan)
    unknown = [_text(value) for value in participants if _text(value) not in known]
    if unknown:
        raise AuxiliaryShotValidationError(
            f"participants are not bound by approved evidence: {', '.join(unknown)}",
            code="INVALID_CHARACTER_REFERENCE",
            proposal_id=proposal_id,
            path="participants",
        )
    camera = proposal.get("camera")
    if not isinstance(camera, dict) or not camera:
        raise AuxiliaryShotValidationError(
            "camera is required",
            code="DIRECTOR_AUXILIARY_SCHEMA_INVALID",
            proposal_id=proposal_id,
            path="camera",
        )
    duration = proposal.get("estimated_duration_seconds")
    if duration is not None and (isinstance(duration, bool) or not isinstance(duration, (int, float)) or float(duration) <= 0):
        raise AuxiliaryShotValidationError(
            "estimated_duration_seconds must be positive",
            code="DIRECTOR_AUXILIARY_SCHEMA_INVALID",
            proposal_id=proposal_id,
            path="estimated_duration_seconds",
        )
    return copy.deepcopy(proposal)


def validate_auxiliary_shot_proposals(
    proposals: Any,
    structural_shot_plan: dict[str, Any],
    contract: dict[str, Any],
    *,
    allow_partial: bool = False,
) -> dict[str, Any]:
    """Validate all proposals and optionally retain valid ones.

    ``allow_partial=False`` is fail-closed for callers that require an
    all-or-nothing proposal set.  ``allow_partial=True`` is the explicit hook
    for the later Partial Acceptance stage and never turns an invalid proposal
    into an admitted shot.
    """

    if not isinstance(proposals, list):
        raise AuxiliaryShotValidationError("auxiliary proposals must be a list", code="DIRECTOR_AUXILIARY_SCHEMA_INVALID")
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    counts: dict[str, int] = {}
    limit = int(AUXILIARY_SHOT_POLICY.get("max_per_source_beat", 2))
    for index, proposal in enumerate(proposals):
        proposal_id = _text(proposal.get("proposal_id")) if isinstance(proposal, dict) else ""
        try:
            if proposal_id and proposal_id in seen_ids:
                raise AuxiliaryShotValidationError(
                    f"duplicate proposal_id: {proposal_id}",
                    code="DIRECTOR_AUXILIARY_DUPLICATE_ID",
                    proposal_id=proposal_id,
                )
            validated = validate_auxiliary_shot_proposal(proposal, structural_shot_plan, contract)
            source_beat_id = _text(validated.get("source_beat_id"))
            counts[source_beat_id] = counts.get(source_beat_id, 0) + 1
            if counts[source_beat_id] > limit:
                raise AuxiliaryShotValidationError(
                    f"source beat {source_beat_id} exceeds auxiliary budget {limit}",
                    code="AUXILIARY_SHOT_BUDGET_EXCEEDED",
                    proposal_id=_text(validated.get("proposal_id")),
                    path="source_beat_id",
                )
            seen_ids.add(_text(validated.get("proposal_id")))
            accepted.append(validated)
        except AuxiliaryShotValidationError as exc:
            rejected.append(
                {
                    "index": index,
                    "proposal_id": proposal_id or exc.proposal_id,
                    "code": exc.code,
                    "path": exc.path,
                    "message": str(exc),
                }
            )
            if not allow_partial:
                raise
    return {
        "status": "valid" if not rejected else "partial",
        "accepted": accepted,
        "rejected": rejected,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "partial_acceptance": bool(rejected),
    }


# Friendly aliases for integration callers.
validate_auxiliary_proposals = validate_auxiliary_shot_proposals
validate_auxiliary_proposal = validate_auxiliary_shot_proposal


__all__ = [
    "AuxiliaryShotValidationError",
    "validate_auxiliary_shot_proposal",
    "validate_auxiliary_shot_proposals",
    "validate_auxiliary_proposal",
    "validate_auxiliary_proposals",
]
