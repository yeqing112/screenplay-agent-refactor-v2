import copy

import pytest

from core.director_forensic import append_director_attempt, resolve_next_director_attempt_context


def _info(count):
    return {"director_llm_attempts": [{"attempt_id": f"attempt-{i}", "status": "HISTORICAL"} for i in range(1, count + 1)]}


@pytest.mark.parametrize("count,expected", [(0, "attempt-1"), (4, "attempt-5"), (5, "attempt-6"), (6, "attempt-7")])
def test_next_attempt_context_is_derived_from_ledger(count, expected):
    context = resolve_next_director_attempt_context(_info(count))
    assert context.attempt_id == expected
    assert context.history_count == count
    assert context.status("VALIDATED") == f"DIRECTOR_BEAT_PLAN_ATTEMPT{count + 1}_VALIDATED"


@pytest.mark.parametrize("count", [5, 6])
def test_append_uses_frozen_context_for_next_attempt(count):
    info = _info(count)
    context = resolve_next_director_attempt_context(info)
    updated = append_director_attempt(info, request_fingerprint="fp", raw_response_sha256="sha", authorization_id="auth", attempt_context=context)
    assert updated["director_llm_attempts"][-1]["attempt_id"] == context.attempt_id


def test_append_rejects_race_or_stale_context_without_renumbering():
    info = _info(5)
    context = resolve_next_director_attempt_context(info)
    raced = copy.deepcopy(info)
    raced["director_llm_attempts"].append({"attempt_id": "attempt-6", "status": "OTHER_EXECUTION"})
    with pytest.raises(ValueError, match="DIRECTOR_BEAT_PLAN_ATTEMPT_LINEAGE_CONFLICT"):
        append_director_attempt(raced, request_fingerprint="fp", raw_response_sha256="sha", authorization_id="auth", attempt_context=context)
    assert len(raced["director_llm_attempts"]) == 6


@pytest.mark.parametrize("count,outcome,expected", [(5, "SCHEMA_INVALID", "DIRECTOR_BEAT_PLAN_ATTEMPT6_SCHEMA_INVALID"), (5, "VALIDATED", "DIRECTOR_BEAT_PLAN_ATTEMPT6_VALIDATED"), (6, "TEXT_INCOMPLETE", "DIRECTOR_BEAT_PLAN_ATTEMPT7_TEXT_INCOMPLETE")])
def test_dynamic_status_never_references_attempt5(count, outcome, expected):
    context = resolve_next_director_attempt_context(_info(count))
    assert context.status(outcome) == expected
    assert "ATTEMPT5" not in context.status(outcome)


def test_authorization_id_does_not_determine_attempt_number():
    context = resolve_next_director_attempt_context(_info(5))
    updated = append_director_attempt(_info(5), request_fingerprint="fp", raw_response_sha256="sha", authorization_id="v7.6.6-attempt6-stage-a-single-call", attempt_context=context)
    assert updated["director_llm_attempts"][-1]["attempt_id"] == "attempt-6"
