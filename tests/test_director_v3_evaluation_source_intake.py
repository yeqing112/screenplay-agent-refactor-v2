from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.evaluation_source_intake import (
    EXPECTED_AUTHORSHIP,
    EXPECTED_EVALUATION_CLASS,
    EXPECTED_GENERATION_ORIGIN,
    AuthorizedEvaluationSourceIntakeGate,
    build_evaluation_source_package,
    evaluation_provenance_fingerprint,
)
from core.new_source_intake import NewRealSourceMaterialIntakeGate


def _package(tmp_path: Path, text: str = "一段没有测试说明的故事正文。") -> tuple[dict, Path]:
    path = tmp_path / "story.txt"
    path.write_text(text, encoding="utf-8")
    package = build_evaluation_source_package(raw_bytes=path.read_bytes(), source_path=str(path), source_title="测试故事")
    return package, path


def test_ai_generated_source_cannot_pass_real_source_gate(tmp_path: Path):
    package, _ = _package(tmp_path)
    result = NewRealSourceMaterialIntakeGate().evaluate(package)
    assert result["accepted"] is False
    assert "SOURCE_PROVENANCE_MISSING" in result["errors"]


def test_authorized_ai_source_passes_only_evaluation_gate(tmp_path: Path):
    package, path = _package(tmp_path)
    result = AuthorizedEvaluationSourceIntakeGate().evaluate(
        package,
        explicit_source_path=str(path),
        expected_source_path=str(path),
        source_text=path.read_text(encoding="utf-8"),
    )
    assert result["status"] == "AUTHORIZED_EVALUATION_SOURCE_ACCEPTED"
    assert result["provider_calls"] == 0
    assert result["production_db_mutations"] == 0


def test_user_supplied_does_not_imply_human_authored(tmp_path: Path):
    package, path = _package(tmp_path)
    assert package["user_supplied_to_system"] is True
    assert package["human_authored"] is False
    altered = dict(package, human_authored=True)
    result = AuthorizedEvaluationSourceIntakeGate().evaluate(altered, explicit_source_path=str(path), expected_source_path=str(path))
    assert "EVALUATION_AUTHORSHIP_CONFLICT" in result["errors"]


def test_evaluation_provenance_is_immutable_and_not_human_benchmark(tmp_path: Path):
    package, _ = _package(tmp_path)
    assert package["source_class"] == EXPECTED_EVALUATION_CLASS
    assert package["source_authorship"] == EXPECTED_AUTHORSHIP
    assert package["generation_origin"] == EXPECTED_GENERATION_ORIGIN
    assert package["blind_human_origin_eligible"] is False
    assert package["final_human_source_benchmark_eligible"] is False
    assert evaluation_provenance_fingerprint(package) == evaluation_provenance_fingerprint(dict(package))


def test_evaluation_source_duplicate_retired_and_exposed_guards(tmp_path: Path):
    package, path = _package(tmp_path)
    kwargs = {"explicit_source_path": str(path), "expected_source_path": str(path)}
    duplicate = AuthorizedEvaluationSourceIntakeGate().evaluate(package, existing_packages=[package], **kwargs)
    assert "SOURCE_DUPLICATE" in duplicate["errors"]
    retired = AuthorizedEvaluationSourceIntakeGate().evaluate(package, retired_fingerprints=[package["raw_source_hash"]], **kwargs)
    assert "SOURCE_RETIRED" in retired["errors"]
    exposed = AuthorizedEvaluationSourceIntakeGate().evaluate(package, exposed_fingerprints=[package["normalized_source_hash"]], **kwargs)
    assert "SOURCE_PROVIDER_EXPOSED" in exposed["errors"]


def test_empty_hash_entries_do_not_create_false_duplicates(tmp_path: Path):
    package, path = _package(tmp_path)
    other = {"raw_source_hash": "", "normalized_source_hash": ""}
    result = AuthorizedEvaluationSourceIntakeGate().evaluate(package, existing_packages=[other], **{"explicit_source_path": str(path), "expected_source_path": str(path)})
    assert "SOURCE_DUPLICATE" not in result["errors"]


def test_evaluation_source_requires_explicit_authorization(tmp_path: Path):
    package, path = _package(tmp_path)
    package["user_authorized_for_evaluation"] = False
    result = AuthorizedEvaluationSourceIntakeGate().evaluate(package, explicit_source_path=str(path), expected_source_path=str(path))
    assert "USER_EVALUATION_AUTHORIZATION_MISSING" in result["errors"]


def test_test_meta_contamination_fails_closed(tmp_path: Path):
    package, path = _package(tmp_path, "正文\n这个故事为什么适合后续测试\n后续内容")
    result = AuthorizedEvaluationSourceIntakeGate().evaluate(package, explicit_source_path=str(path), expected_source_path=str(path), source_text=path.read_text(encoding="utf-8"))
    assert result["accepted"] is False
    assert "SOURCE_CONTAINS_TEST_META" in result["errors"]


def test_cli_dry_run_does_not_write_package_or_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import scripts.run_director_v3_evaluation_source_intake as cli

    source = tmp_path / "story.txt"
    source.write_text("纯故事正文。", encoding="utf-8")
    monkeypatch.setattr(cli, "EXPECTED_SOURCE", source)
    monkeypatch.setattr(cli, "ART", tmp_path / "artifacts")
    monkeypatch.setattr(cli, "AUTHORITY", tmp_path / "authority.json")
    monkeypatch.setattr(cli, "EVALUATION_ROOT", tmp_path / "evaluation_packages")
    monkeypatch.setattr(cli, "EXPOSED", tmp_path / "exposed.json")
    monkeypatch.setattr(cli, "RETIRED", tmp_path / "retired.json")
    cli.AUTHORITY.write_text(json.dumps({"new_real_source_material_intake": {"status": "READY"}}), encoding="utf-8")
    before = cli.AUTHORITY.read_bytes()
    assert cli.main(["--source", str(source), "--source-title", "测试故事", "--narrative-form", "SHORT_STORY", "--authorship", "AI_GENERATED", "--user-authorized"]) == 0
    assert not cli.EVALUATION_ROOT.exists()
    assert cli.AUTHORITY.read_bytes() == before


def test_cli_commit_is_source_only_and_records_lineage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import scripts.run_director_v3_evaluation_source_intake as cli

    source = tmp_path / "story.txt"
    source.write_text("纯故事正文。", encoding="utf-8")
    monkeypatch.setattr(cli, "EXPECTED_SOURCE", source)
    monkeypatch.setattr(cli, "ART", tmp_path / "artifacts")
    monkeypatch.setattr(cli, "AUTHORITY", tmp_path / "authority.json")
    monkeypatch.setattr(cli, "EVALUATION_ROOT", tmp_path / "evaluation_packages")
    monkeypatch.setattr(cli, "EXPOSED", tmp_path / "exposed.json")
    monkeypatch.setattr(cli, "RETIRED", tmp_path / "retired.json")
    cli.AUTHORITY.write_text(json.dumps({"new_real_source_material_intake": {"status": "READY"}}), encoding="utf-8")
    assert cli.main(["--source", str(source), "--source-title", "测试故事", "--narrative-form", "SHORT_STORY", "--authorship", "AI_GENERATED", "--user-authorized", "--commit"]) == 0
    manifests = list(cli.EVALUATION_ROOT.glob("*.json"))
    raws = list(cli.EVALUATION_ROOT.glob("*.raw"))
    assert len(manifests) == 1 and len(raws) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["lineage_state"] == "SOURCE_ACCEPTED"
    assert manifest["package"]["source_class"] == "EVALUATION_ONLY"
    assert manifest["package"]["human_authored"] is False
    assert manifest["production_db_mutations"] == 0
    authority = json.loads(cli.AUTHORITY.read_text(encoding="utf-8"))
    assert authority["authorized_ai_evaluation_source"]["status"] == "INGESTED"
    assert authority["authorized_ai_evaluation_source"]["upstream_processing_authorized"] is False
