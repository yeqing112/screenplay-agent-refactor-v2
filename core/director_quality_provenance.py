"""Stable provenance helpers for Director Quality pilot artifacts.

The provenance envelope is deliberately provider-neutral and contains no
credentials or raw model responses.  Paths are normalized to repository-
relative POSIX form so artifacts remain portable across Windows, CI, and
replay environments.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROVENANCE_SCHEMA_VERSION = "director_quality_provenance_v1"
_SECRET_KEYS = {"api_key", "apikey", "secret", "secret_key", "access_token", "authorization"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(_canonical(value).encode("utf-8"))


def repo_relative_path(path: str | Path, *, root: Path | None = None) -> str:
    """Return a stable repository-relative POSIX path."""

    repo_root = (root or Path(__file__).resolve().parents[1]).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    candidate = candidate.resolve()
    try:
        return candidate.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"provenance path is outside repository: {path}") from exc


def sha256_file(path: str | Path) -> str:
    candidate = Path(path)
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_model_profile(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {"profile_id": value}
    if not isinstance(value, dict):
        return {}
    return {
        str(key): value_item
        for key, value_item in value.items()
        if str(key).lower() not in _SECRET_KEYS
        and isinstance(value_item, (str, int, float, bool))
    }


def git_context(*, root: Path | None = None) -> dict[str, str]:
    repo_root = (root or Path(__file__).resolve().parents[1]).resolve()

    def run(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args], cwd=repo_root, check=True, capture_output=True, text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    return {"commit_sha": run("rev-parse", "HEAD"), "branch": run("branch", "--show-current")}


def scene_manifest_hash(scenes: Iterable[dict[str, Any]]) -> str:
    manifest = []
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        metadata = scene.get("scene") if isinstance(scene.get("scene"), dict) else scene
        manifest.append({
            "index": index,
            "scene_id": str(metadata.get("scene_id") or scene.get("scene_id") or ""),
            "episode": metadata.get("episode"),
            "scene_name": str(metadata.get("scene_name") or metadata.get("name") or ""),
        })
    return sha256_json(manifest)


def build_provenance(
    *,
    protocol_version: str,
    model: dict[str, Any] | None,
    model_profile: dict[str, Any] | str | None,
    scenes: Iterable[dict[str, Any]],
    source_artifacts: Iterable[str | Path] = (),
    evidence_path: str | Path | None = None,
    gate_version: str = "",
    metric_schema_version: str = "",
    root: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the required artifact provenance envelope."""

    repo_root = (root or Path(__file__).resolve().parents[1]).resolve()
    normalized_sources: list[str] = []
    source_hashes: dict[str, str] = {}
    for raw_path in source_artifacts:
        relative = repo_relative_path(raw_path, root=repo_root)
        if relative in normalized_sources:
            continue
        normalized_sources.append(relative)
        candidate = repo_root / relative
        if candidate.is_file():
            source_hashes[relative] = sha256_file(candidate)
    evidence_hash = None
    if evidence_path:
        evidence_relative = repo_relative_path(evidence_path, root=repo_root)
        candidate = repo_root / evidence_relative
        if candidate.is_file():
            evidence_hash = sha256_file(candidate)
        if evidence_relative not in normalized_sources:
            normalized_sources.append(evidence_relative)
            if candidate.is_file():
                source_hashes[evidence_relative] = evidence_hash
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "protocol_version": str(protocol_version or ""),
        **git_context(root=repo_root),
        "model": _safe_model_profile(model),
        "model_profile": _safe_model_profile(model_profile),
        "scene_manifest_hash": scene_manifest_hash(scenes),
        "evidence_hash": evidence_hash,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "source_artifacts": normalized_sources,
        "source_artifact_hashes": source_hashes,
        "gate_version": str(gate_version or ""),
        "metric_schema_version": str(metric_schema_version or ""),
    }


__all__ = [
    "PROVENANCE_SCHEMA_VERSION",
    "build_provenance",
    "git_context",
    "repo_relative_path",
    "scene_manifest_hash",
    "sha256_file",
    "sha256_json",
]
