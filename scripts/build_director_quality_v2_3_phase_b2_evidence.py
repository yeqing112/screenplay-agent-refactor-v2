"""Build a provider-free, deduplicated evidence pool for Phase B2.

Phase B2 must use evidence already present in the repository.  This helper
combines the existing V2.1 frozen scenes, the older V2 golden fixtures, and
the checked-in golden test fixtures.  Fixture scenes are adapted through the
same deterministic SceneBlocking/ShotPlan/Contract builders used by the
application; no LLM, media provider, database, or object storage is touched.

The output is an evidence bundle only.  It is intentionally separate from
the B1 runner so a B2 real pilot cannot accidentally overwrite a B1 artifact.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
BASE_GOLDEN = ARTIFACTS / "director-quality-v2-1-golden-scenes.json"
SUPPLEMENTAL_GOLDEN = ARTIFACTS / "director-quality-v2-golden-scenes.json"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "golden"
DEFAULT_OUTPUT = ARTIFACTS / "director-quality-v2-3-phase-b2-evidence.json"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"evidence source must be an object: {path}")
    return payload


def _existing_scenes(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = _load_json(path)
    scenes = [copy.deepcopy(item) for item in _list(payload.get("scenes")) if isinstance(item, dict)]
    for scene in scenes:
        if isinstance(scene.get("evidence"), dict):
            evidence = scene["evidence"]
            # Phase A evidence called this field ``baseline`` at the scene
            # level.  Normalize the alias so every B2 consumer sees one
            # stable structural-shot-plan key.
            if not isinstance(evidence.get("structural_shot_plan"), dict) and isinstance(scene.get("baseline"), dict):
                evidence["structural_shot_plan"] = copy.deepcopy(scene["baseline"])
            evidence.setdefault("fact_snapshot", {})
            evidence.setdefault("scene_canonical", {})
            evidence.setdefault("previous_scene_continuity", {})
            continue
        # The older V2 golden artifact predates the nested evidence envelope,
        # but still contains a deterministic baseline.  Reconstruct the
        # envelope from that baseline rather than silently dropping valid
        # existing scenes from the B2 pool.
        metadata = _dict(scene.get("scene"))
        baseline = _dict(scene.get("baseline"))
        scene_id = _text(metadata.get("scene_id"))
        scene_name = _text(metadata.get("scene_name")) or _text(baseline.get("scene_name")) or scene_id
        shots = [item for item in _list(baseline.get("shots")) if isinstance(item, dict)]
        beat_map = []
        for shot in shots:
            beat_id = _text(shot.get("beat_id"))
            if not beat_id:
                continue
            beat_map.append({
                "beat_id": beat_id,
                "type": _text(shot.get("purpose")) or "coverage",
                "event": _text(shot.get("event")),
                "participants": copy.deepcopy(_list(shot.get("participants"))),
            })
        participants = sorted({
            _text(value)
            for shot in shots
            for value in _list(shot.get("participants"))
            if _text(value)
        })
        treatment = {
            "schema_version": "director_treatment_legacy_adapter_v1",
            "scene_id": scene_id,
            "scene_name": scene_name,
            "episode": metadata.get("episode") or 1,
            "beat_map": beat_map,
            "participants": participants,
            "state_out": {"legacy_fixture_completed": True},
            "source": "existing_golden_artifact",
        }
        blocking = {
            "schema_version": "scene_blocking_legacy_adapter_v1",
            "scene_id": scene_id,
            "scene_name": scene_name,
            "participants": [{"character_id": value, "name": value, "position": "declared_by_fixture"} for value in participants],
            "unknowns": [],
            "conflicts": [],
            "source_spatial_facts": [],
            "status": "qualified",
        }
        from core.director_creative_contract import build_director_creative_contract

        contract = build_director_creative_contract(
            script_scene={"scene_id": scene_id, "scene_name": scene_name, "episode": metadata.get("episode") or 1, "beat_map": beat_map},
            treatment=treatment,
            blocking=blocking,
            structural_shot_plan=baseline,
        )
        scene["evidence"] = {
            "treatment": treatment,
            "blocking": blocking,
            "contract": contract,
            "structural_shot_plan": baseline,
            "fact_snapshot": {},
            "scene_canonical": {},
            "previous_scene_continuity": {},
        }
    return scenes


def _fixture_scene(directory: Path) -> dict[str, Any] | None:
    """Adapt one checked-in golden fixture into frozen director evidence."""

    script_path = directory / "script.json"
    if not script_path.exists():
        return None
    payload = _load_json(script_path)
    assets_payload = _load_json(directory / "assets.json") if (directory / "assets.json").exists() else {}
    source_scene = next((item for item in _list(payload.get("scenes")) if isinstance(item, dict)), None)
    if not source_scene:
        return None
    fixture_key = directory.name
    scene_name = _text(source_scene.get("name")) or fixture_key
    scene_id = f"fixture:{fixture_key}"
    episode = payload.get("episode") or 1
    beats: list[dict[str, Any]] = []
    for index, raw in enumerate(_list(source_scene.get("beats")), start=1):
        if not isinstance(raw, dict):
            continue
        beat = copy.deepcopy(raw)
        beat["beat_id"] = _text(raw.get("beat_id") or raw.get("id")) or f"B{index:02d}"
        beat.pop("id", None)
        beats.append(beat)
    if not beats:
        return None

    characters = [item for item in _list(assets_payload.get("characters")) if isinstance(item, dict)]
    participant_ids = [_text(item.get("id")) for item in characters if _text(item.get("id"))]
    props = [item for item in _list(assets_payload.get("props")) if isinstance(item, dict)]
    prop_ids = [_text(item.get("id")) for item in props if _text(item.get("id"))]
    # The fixture scripts intentionally omit per-beat cast bindings.  The
    # checked-in assets manifest is the authoritative fixture evidence, so
    # bind its characters to each beat without inventing new identities.
    for beat in beats:
        if not _list(beat.get("participants")):
            beat["participants"] = copy.deepcopy(participant_ids)

    treatment = {
        "schema_version": "director_treatment_fixture_adapter_v1",
        "scene_id": scene_id,
        "scene_name": scene_name,
        "episode": episode,
        "beat_map": beats,
        "participants": participant_ids,
        "props": prop_ids,
        "state_out": {"fixture_completed": True},
        "source": "existing_test_fixture",
    }
    scene = {"scene_id": scene_id, "name": scene_name, "episode": episode}

    # These builders are deterministic and preserve the same evidence shape
    # consumed by the Phase B detector and planner.
    from core.director_creative_contract import build_director_creative_contract
    from core.scene_blocking import build_scene_blocking_v2
    from core.shot_plan import build_shot_plan

    blocking = build_scene_blocking_v2(scene=scene, treatment=treatment, source_script_hash=_digest(payload))
    blocking["participants"] = [{"character_id": value, "name": value, "position": "declared_by_fixture"} for value in participant_ids]
    blocking["props"] = [{"prop_id": value, "name": value, "source": "existing_test_fixture"} for value in prop_ids]
    baseline = build_shot_plan(treatment=treatment, blocking=blocking)
    contract = build_director_creative_contract(
        script_scene={**scene, "beat_map": beats},
        treatment=treatment,
        blocking=blocking,
        structural_shot_plan=baseline,
    )
    return {
        "scene": {
            "book_id": f"fixture:{fixture_key}",
            "episode": episode,
            "scene_name": scene_name,
            "scene_id": scene_id,
            "scene_type": "fixture_adapter",
            "source": "existing_test_fixture",
            "fixture_path": str(directory.relative_to(ROOT)),
        },
        "evidence": {
            "treatment": treatment,
            "blocking": blocking,
            "contract": contract,
            "structural_shot_plan": baseline,
            "fact_snapshot": {},
            "scene_canonical": {},
            "previous_scene_continuity": {},
        },
        "baseline": copy.deepcopy(baseline),
    }


def build_evidence_pool(*, minimum_scenes: int = 24) -> dict[str, Any]:
    """Build a deduplicated pool and fail closed if it cannot reach minimum."""

    by_id: dict[str, dict[str, Any]] = {}
    sources: list[dict[str, Any]] = []

    for path in (BASE_GOLDEN, SUPPLEMENTAL_GOLDEN):
        for scene in _existing_scenes(path):
            metadata = _dict(scene.get("scene"))
            scene_id = _text(metadata.get("scene_id"))
            if scene_id and scene_id not in by_id:
                by_id[scene_id] = scene
                sources.append({"path": str(path), "kind": "frozen_golden", "scene_id": scene_id})

    for directory in sorted(FIXTURE_ROOT.iterdir()) if FIXTURE_ROOT.exists() else []:
        if not directory.is_dir():
            continue
        scene = _fixture_scene(directory)
        if not scene:
            continue
        scene_id = _text(_dict(scene.get("scene")).get("scene_id"))
        if scene_id and scene_id not in by_id:
            by_id[scene_id] = scene
            sources.append({"path": str(directory), "kind": "existing_test_fixture", "scene_id": scene_id})

    scenes = list(by_id.values())
    if len(scenes) < int(minimum_scenes):
        raise ValueError(f"B2 evidence pool has {len(scenes)} unique scenes; minimum is {minimum_scenes}")
    return {
        "protocol_version": "director-quality-v2-3-phase-b2-evidence-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scene_count": len(scenes),
        "required_scene_count": int(minimum_scenes),
        "deduplication": {"key": "scene.scene_id", "unique_scene_count": len(scenes)},
        "sources": sources,
        "scenes": scenes,
        "safety": {"llm_provider_calls": 0, "media_calls": 0, "object_storage_calls": 0, "production_writes": 0, "storyboard_writes": 0},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build provider-free Director Quality V2.3 Phase B2 evidence")
    parser.add_argument("--minimum-scenes", type=int, default=24)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    result = build_evidence_pool(minimum_scenes=max(1, int(args.minimum_scenes)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(args.output), "scene_count": result["scene_count"], "required_scene_count": result["required_scene_count"], "safety": result["safety"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
