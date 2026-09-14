"""Provider-free preflight for the Director Quality V2.3 Phase B1 pilot.

Phase B1 is deliberately separated from the Phase A runner.  This command
only reads the frozen Golden evidence and runs deterministic detector,
strategy, and scoring code.  It never imports a provider client and cannot
write production/storyboard/media/storage state.  A subsequent real runner
must require the confirmation token emitted here.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"
GOLDEN_PATH = ARTIFACTS / "director-quality-v2-1-golden-scenes.json"
OFFLINE_PATH = ARTIFACTS / "director-quality-v2-3-offline-benchmark-current.json"
CONFIRMATION_TOKEN_NAME = "CONFIRM_DIRECTOR_V23_PHASE_B1_REAL_MIMO_PILOT"
REQUIRED_SCENE_COUNT = 12


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"evidence must be a JSON object: {path}")
    return payload


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


def _profile_ready(profile: dict[str, Any] | None) -> bool:
    value = profile if isinstance(profile, dict) else {}
    return bool(
        _text(value.get("id"))
        and _text(value.get("provider")) == "openai-compatible"
        and _text(value.get("capability")) == "llm"
        and "mimo" in _text(value.get("model_name")).lower()
        and bool(value.get("enabled", True))
        and bool(value.get("key_configured") or _text(value.get("api_key")))
        and _text(value.get("base_url"))
    )


def build_preflight(
    *,
    profile: dict[str, Any] | None,
    golden_path: Path = GOLDEN_PATH,
    offline_path: Path = OFFLINE_PATH,
    scene_limit: int = REQUIRED_SCENE_COUNT,
) -> dict[str, Any]:
    """Build a non-secret B1 readiness packet without provider calls."""

    from core.director_creative_contract import build_director_creative_contract
    from core.director_quality_metrics import build_director_quality_v23_coverage_metrics
    from core.director_quality_validator import score_director_quality
    from core.director_opportunity_detector import detect_creative_opportunities
    from core.director_opportunity_evaluation import build_eligibility_metrics
    from core.scene_directing_strategy import build_scene_directing_strategy_v2

    payload = _load(golden_path) if golden_path.exists() else {}
    source_scenes = [item for item in _list(payload.get("scenes")) if isinstance(item, dict)]
    limit = max(0, int(scene_limit))
    scenes = source_scenes[:limit]
    rows: list[dict[str, Any]] = []
    type_counts: Counter[str] = Counter()
    errors: list[dict[str, str]] = []

    for index, item in enumerate(scenes):
        metadata = _dict(item.get("scene"))
        evidence = _dict(item.get("evidence"))
        treatment = copy.deepcopy(_dict(evidence.get("treatment")))
        blocking = copy.deepcopy(_dict(evidence.get("blocking")))
        contract = copy.deepcopy(_dict(evidence.get("contract")))
        baseline = copy.deepcopy(_dict(item.get("baseline")))
        scene_id = _text(metadata.get("scene_id"))
        row: dict[str, Any] = {
            "index": index,
            "scene": metadata,
            "scene_id": scene_id,
            "evidence": {
                "treatment": bool(treatment),
                "blocking": bool(blocking),
                "contract": bool(contract),
                "baseline": bool(baseline),
            },
            "status": "ready",
            "errors": [],
            "side_effects": {"production": 0, "storyboard": 0, "media": 0, "object_storage": 0},
        }
        if not scene_id or not all((treatment, blocking, contract, baseline)):
            row["status"] = "blocked"
            row["errors"].append("frozen evidence is incomplete")
            errors.append({"scene_id": scene_id or f"scene-{index}", "message": "frozen evidence is incomplete"})
            rows.append(row)
            continue
        try:
            opportunities = detect_creative_opportunities(
                script_scene=treatment,
                treatment=treatment,
                blocking=blocking,
                structural_shot_plan=baseline,
                fact_snapshot=_dict(evidence.get("fact_snapshot")),
                scene_canonical=_dict(evidence.get("scene_canonical")),
                previous_scene_continuity=_dict(evidence.get("previous_scene_continuity")),
            )
            eligibility = build_eligibility_metrics(opportunities)
            strategy = build_scene_directing_strategy_v2(treatment=treatment, contract=contract, structural_shot_plan=baseline)
            score = score_director_quality(baseline, treatment=treatment, blocking=blocking)
            coverage = build_director_quality_v23_coverage_metrics(candidate=baseline, strategy=strategy, treatment=treatment)
            for opportunity in opportunities:
                type_counts[_text(opportunity.get("type"))] += 1
            row.update({
                "opportunity_count": len(opportunities),
                "eligible_opportunity_count": int(eligibility.get("eligible_opportunity_count") or 0),
                "non_applicable_opportunity_count": int(eligibility.get("non_applicable_opportunity_count") or 0),
                "opportunity_type_counts": dict(Counter(_text(item.get("type")) for item in opportunities)),
                "strategy_fingerprint": _text(strategy.get("strategy_fingerprint")),
                "contract_fingerprint": _text(contract.get("contract_fingerprint")),
                "baseline_director_quality": score.get("director_quality_score"),
                "baseline_coverage": coverage,
            })
            if not opportunities:
                row["status"] = "ready_no_opportunity"
        except Exception as exc:  # deterministic evidence failure; keep report complete
            row["status"] = "blocked"
            row["errors"].append(str(exc)[:300])
            errors.append({"scene_id": scene_id, "message": str(exc)[:300]})
        rows.append(row)

    offline_available = offline_path.exists()
    ready = bool(
        len(scenes) >= limit
        and limit >= REQUIRED_SCENE_COUNT
        and not errors
        and offline_available
        and _profile_ready(profile)
    )
    return {
        "protocol_version": "director-quality-v2-3-phase-b1-preflight",
        "phase": "B1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scene_count": len(rows),
        "required_scene_count": REQUIRED_SCENE_COUNT,
        "real_mimo_calls": 0,
        "confirmation_required": True,
        "confirmation_token_name": CONFIRMATION_TOKEN_NAME,
        "profile": _profile_snapshot(profile),
        "frozen_evidence": {
            "golden_path": str(golden_path),
            "scene_count": len(source_scenes),
            "selected_scene_count": len(scenes),
            "required_scene_count": REQUIRED_SCENE_COUNT,
            "ready": len(scenes) >= limit >= REQUIRED_SCENE_COUNT and not errors,
        },
        "offline_gate": {"artifact": str(offline_path), "available": offline_available},
        "opportunity_summary": {
            "total_count": sum(type_counts.values()),
            "type_counts": dict(sorted(type_counts.items())),
            "scenes_with_opportunities": sum(1 for row in rows if int(row.get("opportunity_count") or 0) > 0),
            "scenes_without_opportunities": sum(1 for row in rows if row.get("status") == "ready_no_opportunity"),
        },
        "scenes": rows,
        "errors": errors,
        "safety": {"production": 0, "storyboard": 0, "media": 0, "object_storage": 0},
        "ready_for_confirmation": ready,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provider-free Director Quality V2.3 Phase B1 preflight")
    parser.add_argument("--profile-id", default="")
    parser.add_argument("--golden", type=Path, default=GOLDEN_PATH)
    parser.add_argument("--offline", type=Path, default=OFFLINE_PATH)
    parser.add_argument("--scene-limit", type=int, default=REQUIRED_SCENE_COUNT)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    profile = None
    if args.profile_id:
        from api.model_registry import get_profile

        profile = get_profile(args.profile_id)
    result = build_preflight(profile=profile, golden_path=args.golden, offline_path=args.offline, scene_limit=args.scene_limit)
    output = args.output or (ARTIFACTS / f"director-quality-v2-3-phase-b1-preflight-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["artifact"] = str(output)
    print(json.dumps({key: result[key] for key in ("protocol_version", "phase", "scene_count", "real_mimo_calls", "profile", "opportunity_summary", "safety", "ready_for_confirmation", "artifact")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
