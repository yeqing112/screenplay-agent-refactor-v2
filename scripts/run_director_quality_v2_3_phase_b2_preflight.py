"""Provider-free readiness check for the Director Quality V2.3 B2 pilot."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
EVIDENCE_PATH = ARTIFACTS / "director-quality-v2-3-phase-b2-evidence.json"
OFFLINE_PATH = ARTIFACTS / "director-quality-v2-3-offline-benchmark-current.json"
CONFIRMATION_TOKEN_NAME = "CONFIRM_DIRECTOR_V23_PHASE_B2_REAL_MIMO_PILOT"
REQUIRED_SCENE_COUNT = 24


def _text(value: Any) -> str:
    return str(value or "").strip()


def _profile_snapshot(profile: dict[str, Any] | None) -> dict[str, Any]:
    value = profile if isinstance(profile, dict) else {}
    return {
        "id": _text(value.get("id")),
        "provider": _text(value.get("provider")),
        "model_name": _text(value.get("model_name")),
        "capability": _text(value.get("capability")),
        "enabled": bool(value.get("enabled", True)),
        "key_configured": bool(value.get("key_configured") or _text(value.get("api_key"))),
    }


def _stats(values: list[float]) -> dict[str, float | None]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {key: None for key in ("min", "p10", "p25", "median", "p75", "p90", "max")}

    def nearest(percentile: float) -> float:
        index = max(0, min(len(ordered) - 1, int(math.ceil(percentile * len(ordered))) - 1))
        return round(ordered[index], 4)

    return {
        "min": round(ordered[0], 4),
        "p10": nearest(0.10),
        "p25": nearest(0.25),
        "median": round(ordered[len(ordered) // 2], 4) if len(ordered) % 2 else round((ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]) / 2, 4),
        "p75": nearest(0.75),
        "p90": nearest(0.90),
        "max": round(ordered[-1], 4),
    }


def build_preflight(*, profile: dict[str, Any] | None, evidence_path: Path = EVIDENCE_PATH, offline_path: Path = OFFLINE_PATH) -> dict[str, Any]:
    """Build B2 readiness without importing or calling a provider client."""

    if not evidence_path.exists():
        return {
            "protocol_version": "director-quality-v2-3-phase-b2-preflight",
            "phase": "B2",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scene_count": 0,
            "required_scene_count": REQUIRED_SCENE_COUNT,
            "real_mimo_calls": 0,
            "confirmation_required": True,
            "confirmation_token_name": CONFIRMATION_TOKEN_NAME,
            "profile": _profile_snapshot(profile),
            "frozen_evidence": {"path": str(evidence_path), "scene_count": 0, "ready": False},
            "offline_gate": {"artifact": str(offline_path), "available": offline_path.exists()},
            "safety": {"production": 0, "storyboard": 0, "media": 0, "object_storage": 0},
            "ready_for_confirmation": False,
            "errors": ["B2 evidence bundle is missing"],
        }

    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    scenes = payload.get("scenes") if isinstance(payload, dict) else []
    scene_count = len(scenes) if isinstance(scenes, list) else 0
    errors: list[str] = []
    opportunity_type_counts: Counter[str] = Counter()
    scenes_with_opportunities = 0
    baseline_scores: list[float] = []
    if not isinstance(scenes, list):
        errors.append("evidence bundle scenes must be a list")
        scenes = []
    else:
        # Exercise the deterministic evidence path for every selected scene.
        # This catches malformed adapters before a paid call is authorized.
        from core.director_opportunity_detector import detect_creative_opportunities
        from core.director_quality_validator import score_director_quality
        from core.scene_directing_strategy import build_scene_directing_strategy_v2

        seen_ids: set[str] = set()
        for index, item in enumerate(scenes[:REQUIRED_SCENE_COUNT]):
            if not isinstance(item, dict):
                errors.append(f"scene[{index}] is not an object")
                continue
            metadata = item.get("scene") if isinstance(item.get("scene"), dict) else {}
            scene_id = _text(metadata.get("scene_id"))
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            if not scene_id:
                errors.append(f"scene[{index}] missing scene_id")
                continue
            if scene_id in seen_ids:
                errors.append(f"duplicate scene_id: {scene_id}")
            seen_ids.add(scene_id)
            missing = [key for key in ("treatment", "blocking", "contract", "structural_shot_plan") if not isinstance(evidence.get(key), dict) or not evidence.get(key)]
            if missing:
                errors.append(f"{scene_id}: missing evidence: {','.join(missing)}")
                continue
            try:
                opportunities = detect_creative_opportunities(
                    script_scene=evidence["treatment"],
                    treatment=evidence["treatment"],
                    blocking=evidence["blocking"],
                    structural_shot_plan=evidence["structural_shot_plan"],
                    fact_snapshot=evidence.get("fact_snapshot") if isinstance(evidence.get("fact_snapshot"), dict) else {},
                    scene_canonical=evidence.get("scene_canonical") if isinstance(evidence.get("scene_canonical"), dict) else {},
                    previous_scene_continuity=evidence.get("previous_scene_continuity") if isinstance(evidence.get("previous_scene_continuity"), dict) else {},
                )
                if opportunities:
                    scenes_with_opportunities += 1
                opportunity_type_counts.update(_text(opportunity.get("type")) for opportunity in opportunities)
                strategy = build_scene_directing_strategy_v2(
                    treatment=evidence["treatment"],
                    contract=evidence["contract"],
                    structural_shot_plan=evidence["structural_shot_plan"],
                )
                score = score_director_quality(evidence["structural_shot_plan"], treatment=evidence["treatment"], blocking=evidence["blocking"])
                if isinstance(score.get("director_quality_score"), (int, float)):
                    baseline_scores.append(float(score["director_quality_score"]))
            except Exception as exc:
                errors.append(f"{scene_id}: opportunity detection failed: {str(exc)[:240]}")
    profile_obj = profile if isinstance(profile, dict) else {}
    profile_ready = bool(
        _text(profile_obj.get("id"))
        and _text(profile_obj.get("provider")) == "openai-compatible"
        and _text(profile_obj.get("capability")) == "llm"
        and "mimo" in _text(profile_obj.get("model_name")).lower()
        and bool(profile_obj.get("enabled", True))
        and bool(profile_obj.get("key_configured") or _text(profile_obj.get("api_key")))
        and _text(profile_obj.get("base_url"))
    )
    if scene_count < REQUIRED_SCENE_COUNT:
        errors.append(f"evidence bundle has {scene_count} scenes; minimum is {REQUIRED_SCENE_COUNT}")
    if not offline_path.exists():
        errors.append("offline benchmark artifact is missing")
    if not profile_ready:
        errors.append("saved MiMo profile is not ready")
    return {
        "protocol_version": "director-quality-v2-3-phase-b2-preflight",
        "phase": "B2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scene_count": scene_count,
        "required_scene_count": REQUIRED_SCENE_COUNT,
        "real_mimo_calls": 0,
        "confirmation_required": True,
        "confirmation_token_name": CONFIRMATION_TOKEN_NAME,
        "profile": _profile_snapshot(profile),
        "frozen_evidence": {"path": str(evidence_path), "scene_count": scene_count, "ready": scene_count >= REQUIRED_SCENE_COUNT},
        "offline_gate": {"artifact": str(offline_path), "available": offline_path.exists()},
        "opportunity_summary": {
            "selected_scene_count": min(scene_count, REQUIRED_SCENE_COUNT),
            "scenes_with_opportunities": scenes_with_opportunities,
            "scenes_without_opportunities": max(0, min(scene_count, REQUIRED_SCENE_COUNT) - scenes_with_opportunities),
            "type_counts": dict(sorted(opportunity_type_counts.items())),
        },
        "baseline_quality": {
            "scene_scores": baseline_scores,
            "distribution": _stats(baseline_scores),
            "scenes_below_60": sum(1 for score in baseline_scores if score < 60),
            "scenes_below_70": sum(1 for score in baseline_scores if score < 70),
        },
        "safety": {"production": 0, "storyboard": 0, "media": 0, "object_storage": 0},
        "ready_for_confirmation": not errors,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provider-free Director Quality V2.3 B2 preflight")
    parser.add_argument("--profile-id", default="")
    parser.add_argument("--evidence", type=Path, default=EVIDENCE_PATH)
    parser.add_argument("--offline", type=Path, default=OFFLINE_PATH)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    profile = None
    if args.profile_id:
        from api.model_registry import get_profile

        profile = get_profile(args.profile_id)
    result = build_preflight(profile=profile, evidence_path=args.evidence, offline_path=args.offline)
    output = args.output or (ARTIFACTS / f"director-quality-v2-3-phase-b2-preflight-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**{key: result[key] for key in ("protocol_version", "phase", "scene_count", "required_scene_count", "real_mimo_calls", "profile", "safety", "ready_for_confirmation")}, "artifact": str(output), "errors": result["errors"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
