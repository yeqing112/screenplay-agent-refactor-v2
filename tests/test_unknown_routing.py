from core.fact_snapshot import classify_unknown


def test_production_critical_unknown_blocks():
    assert classify_unknown(subject_type="character", predicate="gender", production_critical=True) == "blocking_unknown"


def test_creative_unknown_does_not_become_blocker():
    assert classify_unknown(subject_type="shot", predicate="camera_side", creative=True) == "creative_unknown"
    assert classify_unknown(subject_type="scene", predicate="decor") == "assumable_unknown"

