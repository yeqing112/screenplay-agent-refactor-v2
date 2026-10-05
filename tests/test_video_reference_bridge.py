from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.video_reference_bridge import build_official_media_video_reference_bridge, validate_official_media_video_reference_bridge
from core.video_reference_runtime import resolve_compiled_references
from core.video_compilers.base import CompiledVideoRequestIR, PromptComplexityAudit


def _records():
    version = SimpleNamespace(official_media_version_id="omv-1", status="CURRENT", checksum_sha256="sha-image")
    authority = SimpleNamespace(authority_id="oma-1", status="CURRENT", lineage_hash="lineage-1", payload_hash="payload-1")
    pointer = SimpleNamespace(official_media_version_id="omv-1", authority_id="oma-1", fingerprint="ptr-fp")
    validation = SimpleNamespace(validation_id="validation-1")
    promotion = SimpleNamespace(promotion_id="promotion-1")
    candidate = SimpleNamespace(candidate_id="candidate-1", execution_id="exec-1", checksum_sha256="sha-image")
    execution = SimpleNamespace(execution_id="exec-1")
    binding = {"authority_class": "OFFICIAL_MEDIA", "official_media_authority_id": "oma-1", "official_media_version_id": "omv-1", "media_role": "KEYFRAME_START_IMAGE", "checksum_sha256": "sha-image", "source_prompt_ir_version_id": "77", "source_prompt_ir_payload_hash": "prompt-hash"}
    return binding, version, authority, pointer, validation, promotion, candidate, execution


def test_bridge_uses_official_media_ids_and_authority_lineage():
    args = _records()
    bridge = build_official_media_video_reference_bridge(source_binding=args[0], official_media_version=args[1], official_media_authority=args[2], official_media_pointer=args[3], validation=args[4], promotion=args[5], candidate=args[6], execution=args[7])
    assert bridge["asset_id"] == "omv-1"
    assert bridge["authority_fingerprint"] == "lineage-1"
    assert bridge["generation_execution_id"] == "exec-1"
    assert bridge["official_lineage"]["candidate_id"] == "candidate-1"
    assert validate_official_media_video_reference_bridge(bridge)["status"] == "PASS"


def test_bridge_rejects_checksum_only_or_pointer_mismatch():
    args = list(_records())
    args[3] = SimpleNamespace(official_media_version_id="other", authority_id="oma-1", fingerprint="ptr-fp")
    with pytest.raises(ValueError, match="OFFICIAL_MEDIA_POINTER_MISMATCH"):
        build_official_media_video_reference_bridge(source_binding=args[0], official_media_version=args[1], official_media_authority=args[2], official_media_pointer=args[3], validation=args[4], promotion=args[5], candidate=args[6], execution=args[7])


def test_runtime_blocks_incomplete_official_reference_before_url_resolution():
    compiled = CompiledVideoRequestIR("minimax-h3", "v", "minimax-h3", "SH_E01_SC002_002", "source", "prompt", 14, "16:9", "FIRST_FRAME", ({"role": "FIRST_FRAME", "asset_id": "omv-1", "authority_fingerprint": "lineage", "media_sha256": "sha", "generation_execution_id": "exec", "official_lineage": {}},), "NATIVE_AUDIO_EXPECTED", {}, (), "sha-prompt", "fp", PromptComplexityAudit(characters=2, words=10, performance_beats=0, camera_beats=0, dialogue_length=0, timeline_windows=1))
    with pytest.raises(ValueError, match="OFFICIAL_MEDIA_REFERENCE_LINEAGE_INCOMPLETE"):
        resolve_compiled_references(compiled, lambda _: "https://provider.invalid/frame.jpg")


def test_runtime_resolves_url_only_after_complete_official_bridge():
    args = _records()
    bridge = build_official_media_video_reference_bridge(source_binding=args[0], official_media_version=args[1], official_media_authority=args[2], official_media_pointer=args[3], validation=args[4], promotion=args[5], candidate=args[6], execution=args[7])
    bridge.update({"official_media_current": True, "official_pointer_current": True, "prompt_ir_lineage_exact": True})
    compiled = CompiledVideoRequestIR("minimax-h3", "v", "minimax-h3", "SH_E01_SC002_002", "source", "prompt", 14, "16:9", "FIRST_FRAME", (bridge,), "NATIVE_AUDIO_EXPECTED", {}, (), "sha-prompt", "fp", PromptComplexityAudit(characters=2, words=10, performance_beats=0, camera_beats=0, dialogue_length=0, timeline_windows=1))
    resolved = resolve_compiled_references(compiled, lambda _: "https://provider.invalid/frame.jpg")
    assert resolved[0]["url"] == "https://provider.invalid/frame.jpg"
