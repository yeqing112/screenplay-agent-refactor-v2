from __future__ import annotations

import json
from pathlib import Path

from core.video_reference_bridge import build_official_media_video_reference_bridge


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/video-compiler/v1-keyframe-lineage"
SHA = "f039112c1a3eb0d7d24785a684b9c104989a549df235a4fdd52c72956e1472c1"


def _read(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_historical_scan_is_deterministic_and_read_only():
    audit = _read("SC002_002_HISTORICAL_KEYFRAME_FORENSIC_AUDIT.json")
    assert audit["read_only"] is True
    assert audit["artifact"]["actual_sha256"] == SHA
    assert audit["artifact"]["bytes_exact"] is True
    assert audit["database_write_count"] == 0
    assert all(value == 0 for value in audit["canonical_match_counts"].values())


def test_checksum_match_alone_does_not_establish_canonical_lineage():
    eligibility = _read("SC002_002_CANONICAL_ADOPTION_ELIGIBILITY.json")
    assert eligibility["eligible"] is False
    assert eligibility["status"] == "CANONICAL_ADOPTION_NOT_PROVEN"
    assert "prompt_ir_version_hash" in eligibility["missing"]


def test_prompt_and_provider_lineage_fail_closed_without_invented_ids():
    prompt = _read("SC002_002_PROMPT_LINEAGE_RECOVERY.json")
    provider = _read("SC002_002_PROVIDER_LINEAGE_RECOVERY.json")
    assert prompt["status"] == "HISTORICAL_KEYFRAME_PROMPT_LINEAGE_UNRECOVERABLE"
    assert provider["status"] == "HISTORICAL_PROVIDER_LINEAGE_UNRECOVERABLE"
    assert provider["persisted_request_fingerprint"] is False


def test_historical_adoption_outputs_are_blocked_and_zero_call():
    transaction = _read("SC002_002_HISTORICAL_ADOPTION_TRANSACTION.json")
    preflight = _read("SC002_002_VIDEO_REFERENCE_PREFLIGHT.json")
    assert transaction["status"] == "NOT_EXECUTED"
    assert transaction["provider_calls"] == 0
    assert preflight["status"] == "BLOCKED"
    assert preflight["post_count"] == 0
    assert preflight["hardcoded_url"] is False


def test_official_media_bridge_rejects_fixture_asset_id_and_url_only():
    assert "candidate_id" not in _read("SC002_002_VIDEO_REFERENCE_BRIDGE.json")
    assert _read("SC002_002_VIDEO_REFERENCE_BRIDGE.json")["status"] == "NOT_EXECUTED"
