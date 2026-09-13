"""Offline Director Quality V2.2 benchmark/replay runner.

The default command replays frozen V2.1 evidence and candidate patch
documents through the provider-neutral V2.2 pipeline.  It is deliberately
offline: no provider client is imported, no database/media/storage side effect
is possible, and no production object is written.  A future real MiMo pilot
must use a separate, explicit runner/authorization path.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"
GOLDEN_PATH = ARTIFACTS / "director-quality-v2-1-golden-scenes.json"
V21_REPLAY_PATH = ARTIFACTS / "director-quality-v2-1-mimo-pilot-20260913T093747Z.json"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取 benchmark evidence：{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"benchmark evidence 必须是 JSON object：{path}")
    return value


def _scene_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(_dict(item.get("scene")).get("scene_id")): item
        for item in (payload.get("scenes") or [])
        if isinstance(item, dict) and str(_dict(item.get("scene")).get("scene_id") or "").strip()
    }


def _empty_counts() -> dict[str, int]:
    return {
        "raw_parse_pass": 0,
        "normalized_parse_pass": 0,
        "first_pass_schema_pass": 0,
        "first_pass_contract_pass": 0,
        "post_normalization_contract_pass": 0,
        "post_deterministic_repair_pass": 0,
        "post_llm_repair_pass": 0,
        "final_contract_pass": 0,
        "total_scenes": 0,
        "evaluated_patch_count": 0,
        "fallback_patch_count": 0,
    }


def _empty_cost() -> dict[str, Any]:
    return {
        "normalization_events": 0,
        "deterministic_repair_events": 0,
        "llm_repair_calls": 0,
        "repair_token_cost": 0,
        "repair_latency_ms": 0,
        "fallback_after_repair_count": 0,
    }


def run_offline_replay(
    *,
    golden_path: Path = GOLDEN_PATH,
    replay_path: Path = V21_REPLAY_PATH,
    scene_limit: int = 12,
) -> dict[str, Any]:
    """Replay frozen V2.1 candidate documents through the V2.2 pipeline."""

    from core.director_quality_metrics import build_director_quality_metrics, build_director_quality_v22_metrics
    from core.director_quality_v22 import process_patch_pipeline

    golden = _load_json(golden_path)
    replay = _load_json(replay_path)
    golden_by_id = _scene_index(golden)
    replay_by_id = _scene_index(replay)
    ordered = [
        item for item in (golden.get("scenes") or [])
        if isinstance(item, dict) and str(_dict(item.get("scene")).get("scene_id") or "") in replay_by_id
    ][: max(0, int(scene_limit))]
    if len(ordered) < scene_limit:
        raise ValueError(f"可回放场景不足：{len(ordered)} < {scene_limit}")

    aggregate_counts = _empty_counts()
    aggregate_cost = _empty_cost()
    scenes: list[dict[str, Any]] = []
    total_creative = 0
    retained_creative = 0
    fallback_free = 0

    for golden_scene in ordered:
        scene_meta = _dict(golden_scene.get("scene"))
        scene_id = str(scene_meta.get("scene_id") or "")
        evidence = _dict(golden_scene.get("evidence"))
        baseline = copy.deepcopy(_dict(golden_scene.get("baseline")))
        replay_scene = replay_by_id[scene_id]
        candidate = _dict(replay_scene.get("candidate"))
        raw_document = copy.deepcopy(_dict(candidate.get("patch_document")))
        treatment = copy.deepcopy(_dict(evidence.get("treatment")))
        blocking = copy.deepcopy(_dict(evidence.get("blocking")))
        contract = copy.deepcopy(_dict(evidence.get("contract")))
        strategy = copy.deepcopy(_dict(evidence.get("strategy")))
        if not all((baseline, raw_document, treatment, blocking, contract, strategy)):
            raise ValueError(f"{scene_id}: frozen replay evidence incomplete")

        result = process_patch_pipeline(
            structural_shot_plan=baseline,
            contract=contract,
            strategy=strategy,
            treatment=treatment,
            blocking=blocking,
            raw_output=raw_document,
            # Offline replay intentionally has no Level 2 callable.  Any
            # creative Level 2 issue is recorded as a bounded fallback.
            llm_repair_callable=None,
        )
        result_metrics = _dict(result.get("metrics"))
        stage_counts = _dict(result_metrics.get("stage_counts"))
        for key in _empty_counts():
            if key in {"total_scenes", "evaluated_patch_count", "fallback_patch_count"}:
                continue
            aggregate_counts[key] += int(stage_counts.get(key) or 0)
        patch_count = len(raw_document.get("patches") or [])
        fallback_count = len(result.get("fallbacks") or [])
        aggregate_counts["total_scenes"] += 1
        aggregate_counts["evaluated_patch_count"] += patch_count + fallback_count
        aggregate_counts["fallback_patch_count"] += fallback_count

        result_cost = _dict(result_metrics.get("repair_cost"))
        for key in aggregate_cost:
            aggregate_cost[key] += int(result_cost.get(key) or 0)
        # The pipeline's partial-acceptance metadata is authoritative for
        # retention; it is kept separate from stage counters so patch counts
        # cannot be mistaken for scene counts.
        accepted_meta = _dict(result.get("partial_acceptance"))
        accepted_count = int(accepted_meta.get("accepted_patch_count") or 0)
        total_creative += patch_count + fallback_count
        retained_creative += accepted_count
        if not result.get("fallbacks"):
            fallback_free += 1

        quality = build_director_quality_metrics(
            baseline=baseline,
            first_candidate=result.get("candidate"),
            final_candidate=result.get("candidate"),
            treatment=treatment,
            blocking=blocking,
            partial_acceptance=accepted_meta,
        )
        scenes.append({
            "scene": scene_meta,
            "input": {"source": "frozen_v2_1_candidate_patch_document", "scene_id": scene_id},
            "status": result.get("status"),
            "stage_counts": copy.deepcopy(result.get("stage_counts") or {}),
            "repair_cost": result_cost,
            "fallbacks": copy.deepcopy(result.get("fallbacks") or []),
            "candidate": copy.deepcopy(result.get("candidate") or baseline),
            "validation": copy.deepcopy(result.get("validation") or {}),
            "quality": quality,
            "side_effects": copy.deepcopy(result.get("side_effects") or {}),
        })

    v22_metrics = build_director_quality_v22_metrics(
        stage_counts=aggregate_counts,
        repair_cost=aggregate_cost,
        creative_patch_count=total_creative,
        retained_creative_patch_count=retained_creative,
        fallback_free_scene_count=fallback_free,
        scene_count=aggregate_counts["total_scenes"],
    )
    return {
        "protocol_version": "director-quality-v2-2",
        "benchmark_mode": "offline_replay",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scene_count": len(scenes),
        "source_artifacts": {
            "golden": str(golden_path.relative_to(ROOT)),
            "v21_replay": str(replay_path.relative_to(ROOT)),
        },
        "metrics": v22_metrics,
        "scenes": scenes,
        "side_effects": {
            "production_rows_written": 0,
            "storyboard_shots_created": 0,
            "media_calls": 0,
            "object_storage_calls": 0,
            "llm_provider_calls": 0,
        },
        "real_pilot": {"executed": False, "reason": "offline replay only"},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline Director Quality V2.2 replay benchmark")
    parser.add_argument("--golden", type=Path, default=GOLDEN_PATH)
    parser.add_argument("--replay", type=Path, default=V21_REPLAY_PATH)
    parser.add_argument("--scene-limit", type=int, default=12)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    result = run_offline_replay(golden_path=args.golden, replay_path=args.replay, scene_limit=args.scene_limit)
    output = args.output or (ARTIFACTS / f"director-quality-v2-2-offline-replay-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "metrics": result["metrics"], "side_effects": result["side_effects"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
