"""Guarded V2.2.2 evidence-driven Recovery Pilot.

The runner uses the same frozen 12-scene benchmark and the same upstream
evidence as the Observability Pilot.  Recovery rules are read from the
explicit registry; an empty registry is a valid result and proves that no
unsupported alias/allow-list expansion was applied.
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
CONFIRMATION_TOKEN = "CONFIRM_DIRECTOR_V22_2_RECOVERY_PILOT"


def _text(value: Any) -> str:
    return str(value or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded Director Quality V2.2.2 evidence-driven Recovery Pilot")
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--confirmation-token", default="")
    parser.add_argument("--profile-id", default="")
    parser.add_argument("--scene-limit", type=int, default=12)
    args = parser.parse_args()
    if not args.execute_real:
        print(json.dumps({"status": "preflight_only", "real_mimo_calls": 0, "confirmation_required": True}, ensure_ascii=False, indent=2))
        return
    if _text(args.confirmation_token) != CONFIRMATION_TOKEN:
        raise PermissionError("真实 V2.2.2 Recovery Pilot confirmation token 不匹配。")

    from api.model_registry import get_profile
    from core.director_patch_recovery_rules import list_recovery_rules
    from scripts.run_director_quality_v2_2_mimo_pilot_authorized import (
        run_authorized_pilot,
        validate_real_authorization,
    )

    profile = get_profile(args.profile_id)
    safe_model = validate_real_authorization(
        execute_real=True,
        confirmation_token=CONFIRMATION_TOKEN,
        expected_token=CONFIRMATION_TOKEN,
        profile=profile,
    )
    rules = list_recovery_rules()
    result = copy.deepcopy(run_authorized_pilot(profile=profile, scene_limit=max(12, int(args.scene_limit))))
    result["protocol_version"] = "director-quality-v2-2-2"
    result["pilot_mode"] = "real_mimo_v2_2_2_recovery"
    result["observability_only"] = False
    result["evidence_analysis_artifact"] = "artifacts/director-quality-v2-2-2-rejection-analysis.md"
    result["recovery_rules_applied"] = [item.get("rule_id") for item in rules if isinstance(item, dict) and item.get("rule_id")]
    result["recovery_rules"] = rules
    result["release_decision"] = "RECOVERY_COMPLETE_SHADOW_PENDING"
    result["production_shadow"] = {"enabled": False}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ARTIFACTS.mkdir(exist_ok=True)
    path = ARTIFACTS / f"director-quality-v2-2-2-recovery-pilot-{stamp}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "artifact": str(path),
        "model": safe_model,
        "scene_count": result.get("scene_count"),
        "recovery_rules_applied": result.get("recovery_rules_applied"),
        "side_effects": result.get("side_effects"),
        "observability": result.get("metrics", {}).get("rejection_observability", {}),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
