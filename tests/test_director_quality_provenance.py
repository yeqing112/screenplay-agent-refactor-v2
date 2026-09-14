from pathlib import Path

from core.director_quality_provenance import build_provenance, repo_relative_path, sha256_file


ROOT = Path(__file__).resolve().parents[1]


def test_repo_relative_path_is_portable_posix():
    assert repo_relative_path(ROOT / "artifacts" / "sample.json") == "artifacts/sample.json"


def test_provenance_contains_required_fields_and_redacts_secrets():
    provenance = build_provenance(
        protocol_version="director-quality-v2-4",
        model={"provider": "openai-compatible", "model_name": "mimo-v2.5"},
        model_profile={"id": "profile-1", "api_key": "must-not-leak"},
        scenes=[{"scene": {"scene_id": "S1", "episode": 1, "scene_name": "Test"}}],
        source_artifacts=[ROOT / "artifacts" / "director-quality-v2-3-phase-b2-evidence.json"],
        evidence_path=ROOT / "artifacts" / "director-quality-v2-3-phase-b2-evidence.json",
        gate_version="director_quality_v2_3_shadow_gate_v1",
        metric_schema_version="director-quality-v2-4-metrics-v1",
    )
    required = {"schema_version", "protocol_version", "commit_sha", "branch", "model", "model_profile", "scene_manifest_hash", "evidence_hash", "generated_at", "source_artifacts", "source_artifact_hashes", "gate_version", "metric_schema_version"}
    assert required <= set(provenance)
    assert "api_key" not in provenance["model_profile"]
    assert provenance["source_artifacts"] == ["artifacts/director-quality-v2-3-phase-b2-evidence.json"]
    assert provenance["source_artifact_hashes"][provenance["source_artifacts"][0]] == sha256_file(ROOT / "artifacts" / "director-quality-v2-3-phase-b2-evidence.json")
