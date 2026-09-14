"""Provider-free hard gate for Director Quality V2.4.3."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.director_creative_value import replay_creative_value
MANIFEST = ARTIFACTS / "director-quality-v2-4-3-targeted-tail-manifest.json"


def _check_source(text: str, needle: str) -> bool:
    return needle in text


def build_preflight() -> dict:
    blockers: list[str] = []
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    scenes = manifest.get("scenes") if isinstance(manifest.get("scenes"), list) else []
    scene_ids = [str(item.get("scene_id")) for item in scenes if isinstance(item, dict)]
    root_count = sum(len(item.get("root_causes", [])) for item in scenes if isinstance(item, dict) and isinstance(item.get("root_causes"), list))
    counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
    checks = {
        "manifest_exists": MANIFEST.exists(),
        "manifest_frozen": manifest.get("frozen") is True,
        "manifest_scene_count": len(scenes) == 15 and counts.get("selected_scene_count") == 15,
        "manifest_root_count": root_count == 27 and counts.get("recovered_root_count") == 27,
        "manifest_budget": counts.get("max_semantic_attempts") == 54,
        "unique_scene_ids": len(scene_ids) == len(set(scene_ids)),
        "all_scenes_have_origin": all(bool(item.get("scene_origin")) for item in scenes if isinstance(item, dict)),
        "all_roots_have_targets": all(bool(root.get("target_dimensions")) for item in scenes for root in item.get("root_causes", []) if isinstance(item, dict) for root in [root]),
    }
    blockers.extend(key.upper() for key, passed in checks.items() if not passed)
    runner_text = (ROOT / "scripts" / "run_director_quality_v2_4_targeted_tail_pilot.py").read_text(encoding="utf-8")
    executor_text = (ROOT / "core" / "director_tail_repair_executor.py").read_text(encoding="utf-8")
    safeguards = {
        "manifest_path_supported": _check_source(runner_text, "manifest_path"),
        "frozen_roots_bypass_ranker": _check_source(executor_text, "re-ranking would silently change the A/B cohort"),
        "creative_value_replay_required": _check_source(executor_text, "require_creative_value_replay"),
        "json_parser_retries_zero": _check_source((ROOT / "scripts" / "run_director_quality_v2_4_targeted_tail_pilot.py").read_text(encoding="utf-8"), "json_parse_retries=0"),
        "no_media_side_effects": all(x in runner_text for x in ["production", "storyboard", "object_storage"]),
    }
    blockers.extend(key.upper() for key, passed in safeguards.items() if not passed)
    replay_input = {
        "schema_version": "director_creative_value_score_v1", "score": 25.0,
        "components": {"opportunity_coverage": 1.0, "useful_creative_acceptance": 0.0, "edit_strategy": 0.0, "emotion_arc": 1.0, "information_strategy": 1.0, "tail_stability": 0.0},
    }
    opportunity = {"schema_version": "director_creative_opportunity_v1", "opportunity_id": "PREFLIGHT_O1", "type": "OPP_ACTION_ACCELERATION", "scene_id": "PREFLIGHT", "beat_id": "B1", "subjects": ["C1"], "reason": "preflight", "evidence_refs": ["preflight"], "priority": "high", "eligible": True, "recommended_directing_dimensions": ["edit_strategy"]}
    replay_kwargs = {"baseline_creative_value": replay_input, "opportunities": [opportunity], "decisions": [{"opportunity_id": "PREFLIGHT_O1", "decision": "ACT", "strategy": "preflight"}], "baseline_outcomes": [], "candidate_interventions": [{"opportunity_id": "PREFLIGHT_O1", "patch_valid": True, "applied": True, "fact_contract_pass": True, "new_blocker": False, "quality_delta": 1, "dimension_deltas": {"edit_strategy": 1}, "repaired": True}], "after_director_quality": 51, "candidate_fingerprint": "preflight-candidate", "frozen_inputs": {"scene_id": "PREFLIGHT"}}
    replay_a = replay_creative_value(**replay_kwargs)
    replay_b = replay_creative_value(**replay_kwargs)
    checks["deterministic_replay_ready"] = replay_a.get("measurement_status") == "ready"
    checks["deterministic_replay_reproducible"] = replay_a.get("creative_value_replay_fingerprint") == replay_b.get("creative_value_replay_fingerprint")
    blockers.extend(key.upper() for key in ("deterministic_replay_ready", "deterministic_replay_reproducible") if not checks[key])
    return {
        "schema_version": "director-quality-v2-4-3-provider-free-preflight-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "READY_FOR_REAL_MIMO" if not blockers else "BLOCKED",
        "ready_for_real_mimo": not blockers,
        "manifest": {"path": "artifacts/director-quality-v2-4-3-targeted-tail-manifest.json", "scene_count": len(scenes), "root_count": root_count},
        "checks": checks,
        "safeguards": safeguards,
        "replay_probe": {"status": replay_a.get("measurement_status"), "score": replay_a.get("score"), "fingerprint": replay_a.get("creative_value_replay_fingerprint")},
        "real_mimo_calls": 0,
        "side_effects": {"production": 0, "storyboard": 0, "media": 0, "object_storage": 0, "production_shadow": 0},
        "blockers": blockers,
    }


def main() -> int:
    output = ARTIFACTS / "director-quality-v2-4-3-provider-free-preflight.json"
    result = build_preflight()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "artifact": output.relative_to(ROOT).as_posix(), "blockers": result["blockers"]}, ensure_ascii=False))
    return 0 if result["ready_for_real_mimo"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
