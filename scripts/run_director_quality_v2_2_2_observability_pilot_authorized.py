"""Guarded V2.2.2 observability-only Pilot.

This runner intentionally reuses the V2.2 benchmark pipeline after the raw
RejectionTrace capture was added.  It does not register recovery rules and
does not mutate production, storyboard, media, or storage state.
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
CONFIRMATION_TOKEN = "CONFIRM_DIRECTOR_V22_2_OBSERVABILITY_PILOT"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded Director Quality V2.2.2 observability Pilot")
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--confirmation-token", default="")
    parser.add_argument("--profile-id", default="")
    parser.add_argument("--scene-limit", type=int, default=12)
    args = parser.parse_args()
    if not args.execute_real:
        print(json.dumps({"status": "preflight_only", "real_mimo_calls": 0, "confirmation_required": True}, ensure_ascii=False, indent=2))
        return
    if _text(args.confirmation_token) != CONFIRMATION_TOKEN:
        raise PermissionError("真实 V2.2.2 Observability Pilot confirmation token 不匹配。")

    from api.model_registry import get_profile
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
    result = run_authorized_pilot(profile=profile, scene_limit=max(12, int(args.scene_limit)))
    result = copy.deepcopy(result)
    result["protocol_version"] = "director-quality-v2-2-2"
    result["pilot_mode"] = "real_mimo_v2_2_2_observability_only"
    result["observability_only"] = True
    result["recovery_rules_applied"] = []
    result["release_decision"] = "OBSERVABILITY_COMPLETE_RECOVERY_PENDING"
    result["production_shadow"] = {"enabled": False}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ARTIFACTS.mkdir(exist_ok=True)
    path = ARTIFACTS / f"director-quality-v2-2-2-observability-pilot-{stamp}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(path), "model": safe_model, "scene_count": result.get("scene_count"), "side_effects": result.get("side_effects"), "observability": _dict(_dict(result.get("metrics")).get("rejection_observability"))}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
