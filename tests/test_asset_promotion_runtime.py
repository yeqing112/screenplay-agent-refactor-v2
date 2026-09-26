from __future__ import annotations

import pytest

from api.asset_promotion_api import PromoteCandidateRequest, router
from core.media_authority import MediaAuthorityError, promote_media_candidate, validate_media_candidate
from models import MediaPromotionRecord, Session, OfficialMediaVersion
from tests.prompt_ir_authority_fixture import resolve_fixture_materialization
from tests.test_media_validation_promotion_contract import _fixture


@pytest.fixture(autouse=True)
def _fixture_authority_resolver(monkeypatch):
    monkeypatch.setattr("core.storyboard_materializer.resolve_current_authoritative_materialization", resolve_fixture_materialization)


def test_validation_creates_review_required_promotion_record():
    candidate_id, _execution_id, _path, _shot_id = _fixture()
    with Session() as session:
        result = validate_media_candidate(session, candidate_id)
        review = session.query(MediaPromotionRecord).filter_by(candidate_id=candidate_id).one()
        assert result["promotion"].promotion_id == review.promotion_id
        assert review.review_status == "REVIEW_REQUIRED"
        assert review.decision is None
        assert session.query(OfficialMediaVersion).filter_by(candidate_id=candidate_id).count() == 0


def test_reject_and_request_change_fail_closed_without_official_rows():
    for decision in ("REJECT", "REQUEST_CHANGE"):
        candidate_id, _execution_id, _path, _shot_id = _fixture()
        with Session() as session:
            validation = validate_media_candidate(session, candidate_id)
            with pytest.raises(MediaAuthorityError) as exc:
                promote_media_candidate(
                    session,
                    candidate_id,
                    validation["validation_id"],
                    confirmation=True,
                    reviewer="qa-reviewer",
                    decision=decision,
                    review_notes="needs another review",
                )
            assert exc.value.code == "MEDIA_PROMOTION_REVIEW_REQUIRED"
            review = session.query(MediaPromotionRecord).filter_by(candidate_id=candidate_id).one()
            assert review.review_status == ("REJECTED" if decision == "REJECT" else "REQUEST_CHANGE")
            assert review.reviewer == "qa-reviewer"
            assert session.query(OfficialMediaVersion).filter_by(candidate_id=candidate_id).count() == 0


def test_explicit_approval_records_reviewer_and_promotes_once():
    candidate_id, _execution_id, _path, _shot_id = _fixture()
    with Session() as session:
        validation = validate_media_candidate(session, candidate_id)
        result = promote_media_candidate(
            session,
            candidate_id,
            validation["validation_id"],
            confirmation=True,
            reviewer="human-reviewer",
            decision="APPROVE",
            review_notes="approved for production",
        )
        review = session.query(MediaPromotionRecord).filter_by(candidate_id=candidate_id).one()
        assert review.review_status == "APPROVED"
        assert review.decision == "APPROVE"
        assert review.reviewer == "human-reviewer"
        assert review.official_media_version_id == result["version"].official_media_version_id
        assert session.query(OfficialMediaVersion).filter_by(candidate_id=candidate_id).count() == 1


def test_asset_promotion_router_exposes_api_and_forbids_unknown_review_fields():
    paths = {route.path for route in router.routes}
    assert "/assets/candidates" in paths
    assert "/assets/candidates/{candidate_id}/validate" in paths
    assert "/assets/candidates/{candidate_id}/promote" in paths
    with pytest.raises(ValueError):
        PromoteCandidateRequest(validation_id="v", reviewer="r", extra_field="blocked")
