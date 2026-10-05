from __future__ import annotations

import json
from types import SimpleNamespace

from core.sc002_002_upstream_recovery import exact_shot_plan_payload_matches, resolve_exact_canonical_identity


def _plan(plan_id: int, target: str):
    return SimpleNamespace(
        id=plan_id,
        book_id=100,
        episode=1,
        scene_id="E01_SC002",
        scene_name="厨房",
        revision=1,
        status="approved",
        production_status="qualified",
        qualification_state="PRODUCTION_QUALIFIED",
        stale_status="FRESH",
        payload_hash=f"payload-{plan_id}",
        schema_version="shot_plan_v2",
        model_info=json.dumps({"phase_c_contract": {"contract_version": "v1"}, "phase_c_semantic_ready": True, "shot_design_status": "CANONICAL_CONFIRMED"}),
        shots=json.dumps([{"plan_shot_id": target, "camera": {}}]),
    )


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter_by(self, **kwargs):
        return _Query([row for row in self.rows if all(getattr(row, key, None) == value for key, value in kwargs.items())])

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class _Session:
    def __init__(self, plans, pointers=(), authorities=()):
        from models import ShotPlan, ShotPlanAuthority, ShotPlanPointer
        self.data = {ShotPlan: plans, ShotPlanPointer: pointers, ShotPlanAuthority: authorities}

    def query(self, cls):
        return _Query(self.data.get(cls, []))


def test_exact_plan_shot_id_does_not_match_substrings():
    rows = [_plan(1, "SH_E01_SC002_002_EXTRA"), _plan(2, "SH_E01_SC002_002")]
    matches = exact_shot_plan_payload_matches(rows)
    assert [item["row"].id for item in matches] == [2]


def test_zero_exact_match_fails_closed():
    result = resolve_exact_canonical_identity(_Session([_plan(1, "SH_E01_SC002_003")]))
    assert result["status"] == "ZERO"


def test_multiple_authoritative_exact_matches_are_ambiguous():
    plans = [_plan(1, "SH_E01_SC002_002"), _plan(2, "SH_E01_SC002_002")]
    pointers = [SimpleNamespace(book_id=100, episode=1, scene_id="E01_SC002", shot_plan_id=1, plan_revision=1, authority_envelope_fingerprint="auth-1", qualification_state="PRODUCTION_QUALIFIED"), SimpleNamespace(book_id=100, episode=1, scene_id="E01_SC002", shot_plan_id=2, plan_revision=1, authority_envelope_fingerprint="auth-2", qualification_state="PRODUCTION_QUALIFIED")]
    authorities = [SimpleNamespace(shot_plan_id=1, payload_hash="payload-1", envelope_fingerprint="auth-1", qualification_state="AUTHORITY_BOUND", stale_status="FRESH"), SimpleNamespace(shot_plan_id=2, payload_hash="payload-2", envelope_fingerprint="auth-2", qualification_state="AUTHORITY_BOUND", stale_status="FRESH")]
    result = resolve_exact_canonical_identity(_Session(plans, pointers, authorities))
    assert result["status"] == "AMBIGUOUS"


def test_identity_requires_pointer_and_authority_join():
    plan = _plan(1, "SH_E01_SC002_002")
    pointer = SimpleNamespace(book_id=100, episode=1, scene_id="E01_SC002", shot_plan_id=99, plan_revision=1, authority_envelope_fingerprint="auth-1", qualification_state="PRODUCTION_QUALIFIED")
    authority = SimpleNamespace(shot_plan_id=1, payload_hash="payload-1", envelope_fingerprint="auth-1", qualification_state="AUTHORITY_BOUND", stale_status="FRESH")
    result = resolve_exact_canonical_identity(_Session([plan], [pointer], [authority]))
    assert result["status"] == "ZERO"
