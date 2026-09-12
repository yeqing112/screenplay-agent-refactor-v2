from core.fact_snapshot import validate_fact_records


def test_locked_fact_must_be_confirmed_and_have_authority():
    report = validate_fact_records([{"fact_id": "f1", "subject_type": "character", "subject_id": "c1", "predicate": "gender", "value": "female", "authority": "locked_fact", "status": "proposed"}])
    assert report["status"] == "needs_review"
    assert any(item["code"] == "LOCKED_FACT_MUST_BE_CONFIRMED" for item in report["errors"])


def test_unknown_authority_is_rejected():
    report = validate_fact_records([{"fact_id": "f1", "subject_type": "scene", "subject_id": "s1", "predicate": "weather", "value": "rain", "authority": "guess", "status": "proposed"}])
    assert any(item["code"] == "FACT_AUTHORITY_INVALID" for item in report["errors"])

