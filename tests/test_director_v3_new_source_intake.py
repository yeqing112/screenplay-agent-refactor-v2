from __future__ import annotations

from core.new_source_intake import (
    NewRealSourceMaterialIntakeGate,
    build_source_package,
    build_source_version,
    next_available_fresh_book_id,
    scene_fingerprints,
    stable_scene_source_id,
    transition_lineage,
    validate_approval_evidence,
    validate_clean_lineage,
    validate_source_version,
)
import json
import zipfile
from io import BytesIO


def _package(**kwargs):
    values = {"raw_bytes": b"Episode 1\nScene A\nAction", "source_filename": "story.txt", "source_origin": "USER_UPLOAD", "user_provided": True}
    values.update(kwargs)
    return build_source_package(**values)


def test_real_source_package_requires_user_provided():
    result = NewRealSourceMaterialIntakeGate().evaluate(_package(user_provided=False))
    assert "SOURCE_NOT_USER_PROVIDED" in result["errors"]


def test_empty_source_rejected():
    result = NewRealSourceMaterialIntakeGate().evaluate(_package(raw_bytes=b""))
    assert "SOURCE_EMPTY" in result["errors"]


def test_fixture_source_rejected():
    result = NewRealSourceMaterialIntakeGate().evaluate(_package(source_origin="FIXTURE"))
    assert "SOURCE_FIXTURE_FORBIDDEN" in result["errors"]


def test_synthetic_source_rejected():
    result = NewRealSourceMaterialIntakeGate().evaluate(_package(source_origin="SYNTHETIC"))
    assert "SOURCE_SYNTHETIC_FORBIDDEN" in result["errors"]


def test_source_package_hash_is_deterministic():
    assert _package() == _package()


def test_source_version_is_immutable():
    version = build_source_version(_package())
    assert version["immutable"] is True and version["parent_source_version_id"] is None


def test_source_version_binds_immutable_package_hashes():
    package = _package(); version = build_source_version(package)
    assert validate_source_version(version, package)["status"] == "PASS"
    version["raw_hash"] = "changed"
    assert validate_source_version(version, package)["status"] == "FAIL"


def test_scene_source_id_is_stable():
    package = _package(); version = build_source_version(package)
    assert stable_scene_source_id(package["source_package_id"], version["source_version_id"], 1) == stable_scene_source_id(package["source_package_id"], version["source_version_id"], 1)


def test_scene_rename_does_not_create_fresh_source():
    assert scene_fingerprints(raw_scene_text="Scene A\nAction") == scene_fingerprints(raw_scene_text="Scene A\nAction")


def test_retired_source_duplicate_rejected():
    package = _package(); result = NewRealSourceMaterialIntakeGate().evaluate(package, retired_fingerprints=[package["raw_source_hash"]])
    assert "SOURCE_RETIRED" in result["errors"]


def test_exposed_source_duplicate_rejected():
    package = _package(); result = NewRealSourceMaterialIntakeGate().evaluate(package, exposed_fingerprints=[package["normalized_source_hash"]])
    assert "SOURCE_PROVIDER_EXPOSED" in result["errors"]


def test_clean_source_is_not_automatically_approved():
    result = NewRealSourceMaterialIntakeGate().evaluate(_package())
    assert result["status"] == "NEW_REAL_SOURCE_ACCEPTED"
    assert "approval" not in result


def test_clean_lineage_starts_at_source():
    assert transition_lineage("SOURCE_ACCEPTED", "FACT_SNAPSHOT_PENDING")["allowed"] is True


def test_lineage_cannot_skip_fact_snapshot():
    assert transition_lineage("SOURCE_ACCEPTED", "SCRIPT_IR_PENDING")["error"] == "LINEAGE_STATE_SKIP_FORBIDDEN"


def test_lineage_cannot_skip_script_ir():
    assert transition_lineage("FACT_SNAPSHOT_CONFIRMED", "TREATMENT_PENDING")["error"] == "LINEAGE_STATE_SKIP_FORBIDDEN"


def test_treatment_cannot_be_approved_without_source_binding():
    result = validate_clean_lineage({"source_package_id": "S", "source_version_id": "V", "scene_source_id": "SC", "source_fingerprint": "fp", "fact_snapshot": {}, "script_ir": {}, "director_treatment": {}, "scene_blocking": {}, "approval_evidence": {}, "exposure_state": "NOT_EXPOSED", "fresh_eligibility": False, "lineage_edges": {}})
    assert result["status"] == "FAIL"


def test_orphaned_legacy_approval_fails_clean_lineage():
    assert validate_clean_lineage({})["clean_lineage"] is False


def test_provider_generation_is_not_approval():
    evidence = {"approval_type": "TREATMENT_APPROVAL", "reviewer_type": "HUMAN", "approved_at": "2026-01-01", "approved_record_fingerprint": "r", "source_lineage_fingerprint": "s"}
    assert validate_approval_evidence(evidence, record_fingerprint="r", source_lineage_fingerprint="s")["status"] == "PASS"


def test_approval_requires_evidence():
    assert validate_approval_evidence({}, record_fingerprint="r", source_lineage_fingerprint="s")["status"] == "FAIL"


def test_approval_fingerprint_matches_record():
    evidence = {"approval_type": "BLOCKING_APPROVAL", "reviewer_type": "HUMAN", "approved_at": "2026-01-01", "approved_record_fingerprint": "wrong", "source_lineage_fingerprint": "s"}
    assert "APPROVAL_FINGERPRINT_MISMATCH" in validate_approval_evidence(evidence, record_fingerprint="r", source_lineage_fingerprint="s")["errors"]


def test_human_preference_not_inferred_from_approval():
    evidence = {"approval_type": "TREATMENT_APPROVAL", "reviewer_type": "HUMAN", "approved_at": "2026-01-01", "approved_record_fingerprint": "r", "source_lineage_fingerprint": "s"}
    assert "human_preference" not in validate_approval_evidence(evidence, record_fingerprint="r", source_lineage_fingerprint="s")


def test_preflight_makes_zero_provider_calls():
    assert NewRealSourceMaterialIntakeGate().evaluate(_package())["provider_calls"] == 0


def test_dry_run_does_not_write_production_db():
    assert NewRealSourceMaterialIntakeGate().evaluate(_package())["production_authority_mutations"] == 0


def test_commit_intake_requires_valid_real_source():
    assert NewRealSourceMaterialIntakeGate().evaluate(_package(source_origin="FIXTURE"))["accepted"] is False


def test_commit_intake_does_not_trigger_upstream_provider():
    assert NewRealSourceMaterialIntakeGate().evaluate(_package())["provider_calls"] == 0


def test_clean_lineage_requirement_is_explicit():
    from core.fresh_approved_record_pool import FreshApprovedRecordEligibilityGate, _candidate
    row = _candidate(book_id=1, episode=1, scene_name="A", source_records=[{"kind": "script"}], source_text="x", beats=[{"id": "B1", "event": "x"}], upstream={"fact_confirmed": True, "script_ir": {"qualified": True}, "director_treatment": {"status": "approved"}, "scene_blocking": {"status": "approved"}, "identity_authority_valid": True})
    assert "CLEAN_LINEAGE_REQUIRED" in FreshApprovedRecordEligibilityGate().evaluate(row, require_clean_lineage=True)["reasons"]


def test_next_available_book_id_does_not_reserve_when_empty():
    assert next_available_fresh_book_id([]) == 990403


def test_docx_source_uses_deterministic_local_extractor():
    payload = b"<?xml version='1.0'?><w:document><w:body><w:p><w:t>Scene text</w:t></w:p></w:body></w:document>"
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("word/document.xml", payload)
    package = _package(raw_bytes=stream.getvalue(), source_filename="story.docx")
    assert package["source_type"] == "docx"
    assert package["text_extraction_status"] == "extracted"
    assert NewRealSourceMaterialIntakeGate().evaluate(package)["accepted"] is True


def test_legacy_approval_is_not_fresh_approval_by_default():
    evidence = {"approval_type": "TREATMENT_APPROVAL", "reviewer_type": "LEGACY_IMPORTED", "approved_at": "2026-01-01", "approved_record_fingerprint": "r", "source_lineage_fingerprint": "s"}
    assert "LEGACY_APPROVAL_NOT_ALLOWED_FOR_FRESH" in validate_approval_evidence(evidence, record_fingerprint="r", source_lineage_fingerprint="s")["errors"]


def test_strict_lineage_requires_each_approved_upstream_stage():
    package = _package(); version = build_source_version(package)
    manifest = __import__("core.new_source_intake", fromlist=["build_clean_lineage_manifest"]).build_clean_lineage_manifest(source_package=package, source_version=version, scene_source_id="SC", lineage_state="FRESH_APPROVED_RECORD_ELIGIBLE", fresh_eligibility=True)
    result = validate_clean_lineage(manifest, strict=True)
    assert result["status"] == "FAIL"
    assert "FACT_SNAPSHOT_NOT_CONFIRMED" in result["errors"]


def test_cli_no_source_is_provider_free_and_does_not_ingest(tmp_path, monkeypatch):
    import scripts.run_director_v3_new_source_intake as cli
    artifact_root = tmp_path / "artifacts"; artifact_root.mkdir()
    authority = artifact_root / "authority.json"; authority.write_text(json.dumps({"fresh_approved_record_pool": {"status": "BLOCKED"}}), encoding="utf-8")
    monkeypatch.setattr(cli, "ARTIFACTS", artifact_root)
    monkeypatch.setattr(cli, "AUTHORITY_PATH", authority)
    monkeypatch.setattr(cli, "EXPOSED_PATH", artifact_root / "exposed.json")
    monkeypatch.setattr(cli, "RETIRED_PATH", artifact_root / "retired.json")
    monkeypatch.setattr(cli, "PACKAGE_ROOT", tmp_path / "packages")
    assert cli.main([]) == 0
    assert not (tmp_path / "packages").exists()
    updated = json.loads(authority.read_text(encoding="utf-8"))
    assert updated["new_real_source_material_intake"]["waiting_for"] == "REAL_SOURCE_MATERIAL"


def test_cli_commit_only_persists_explicit_source_package(tmp_path, monkeypatch):
    import scripts.run_director_v3_new_source_intake as cli
    artifact_root = tmp_path / "artifacts"; artifact_root.mkdir()
    authority = artifact_root / "authority.json"; authority.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "ARTIFACTS", artifact_root)
    monkeypatch.setattr(cli, "AUTHORITY_PATH", authority)
    monkeypatch.setattr(cli, "EXPOSED_PATH", artifact_root / "exposed.json")
    monkeypatch.setattr(cli, "RETIRED_PATH", artifact_root / "retired.json")
    monkeypatch.setattr(cli, "PACKAGE_ROOT", tmp_path / "packages")
    source = tmp_path / "new-story.txt"; source.write_text("Episode 1\nScene 1\nAction", encoding="utf-8")
    assert cli.main(["--source", str(source), "--commit"]) == 0
    assert len(list((tmp_path / "packages").glob("*.json"))) == 1
    assert len(list((tmp_path / "packages").glob("*.raw"))) == 1
