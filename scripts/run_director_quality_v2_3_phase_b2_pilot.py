"""Guarded Director Quality V2.3 Phase B2 MiMo pilot.

This runner reuses the already-tested Phase B creative-value engine with a
larger, independently frozen evidence pool.  It is artifact-only: the real
provider call is limited to Director Quality / Creative Value planning and
cannot write Production, Storyboard, media, or object-storage state.
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
EVIDENCE_PATH = ARTIFACTS / "director-quality-v2-3-phase-b2-evidence.json"
CONFIRMATION_TOKEN = "CONFIRM_DIRECTOR_V23_PHASE_B2_REAL_MIMO_PILOT"
REQUIRED_SCENE_COUNT = 24


def _text(value: Any) -> str:
    return str(value or "").strip()


def validate_real_authorization(*, execute_real: bool, confirmation_token: str, profile: dict[str, Any] | None) -> dict[str, str]:
    if not execute_real:
        raise PermissionError("真实 B2 Pilot 默认关闭；必须显式提供 --execute-real。")
    if _text(confirmation_token) != CONFIRMATION_TOKEN:
        raise PermissionError("真实 B2 Pilot confirmation token 不匹配。")
    if not isinstance(profile, dict):
        raise ValueError("必须显式指定已保存的 MiMo LLM profile。")
    if _text(profile.get("provider")) != "openai-compatible" or _text(profile.get("capability")) != "llm":
        raise ValueError("B2 Pilot 需要 openai-compatible LLM profile。")
    if not bool(profile.get("enabled", True)):
        raise ValueError("Pilot profile 已禁用。")
    if "mimo" not in _text(profile.get("model_name")).lower():
        raise ValueError("B2 Pilot 只允许显式指定 MiMo 模型 profile。")
    if not _text(profile.get("api_key")) or not _text(profile.get("base_url")):
        raise ValueError("Pilot profile 缺少 API Key 或 base_url。")
    return {"profile_id": _text(profile.get("id")), "provider": _text(profile.get("provider")), "model_name": _text(profile.get("model_name"))}


def _rename_telemetry_stage(telemetry: dict[str, Any]) -> dict[str, Any]:
    """Make the reused engine's stage label explicit in the B2 artifact."""

    value = copy.deepcopy(telemetry) if isinstance(telemetry, dict) else {}
    stages = value.get("stages") if isinstance(value.get("stages"), dict) else {}
    if "director_patch_planner_v23_b1" in stages:
        stage = stages.pop("director_patch_planner_v23_b1")
        stages["director_patch_planner_v23_b2"] = stage
    for record in value.get("records", []) if isinstance(value.get("records"), list) else []:
        if not isinstance(record, dict):
            continue
        extra = record.get("extra") if isinstance(record.get("extra"), dict) else {}
        if extra.get("stage") == "director_patch_planner_v23_b1":
            extra["stage"] = "director_patch_planner_v23_b2"
        if extra.get("pilot_stage") == "director_patch_planner_v23_b1":
            extra["pilot_stage"] = "director_patch_planner_v23_b2"
    return value


def run_authorized_pilot(*, profile: dict[str, Any], evidence_path: Path = EVIDENCE_PATH, scene_limit: int = REQUIRED_SCENE_COUNT, confirmation_token: str = "") -> dict[str, Any]:
    """Run B2 using the tested Phase B engine against frozen evidence."""

    if _text(confirmation_token) != CONFIRMATION_TOKEN:
        raise PermissionError("B2 runner requires the exact confirmation token")
    if not evidence_path.exists():
        raise ValueError(f"B2 evidence bundle is missing: {evidence_path}")
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    scenes = payload.get("scenes") if isinstance(payload, dict) else []
    if not isinstance(scenes, list) or len(scenes) < int(scene_limit):
        raise ValueError(f"B2 evidence bundle has fewer than {scene_limit} scenes")

    # Import only after authorization at the CLI boundary; tests may replace
    # this function with a provider-free stub.
    from scripts.run_director_quality_v2_3_phase_b1_pilot import run_authorized_pilot as run_b1
    from core.director_quality_provenance import build_provenance

    result = run_b1(profile=profile, golden_path=evidence_path, scene_limit=int(scene_limit))
    result = copy.deepcopy(result)
    result["protocol_version"] = "director-quality-v2-3-phase-b2-pilot"
    result["pilot_mode"] = "real_mimo_phase_b2_artifact_only"
    result["phase"] = "B2"
    result["source_evidence"] = {"path": str(evidence_path), "available_scene_count": len(scenes), "selected_scene_count": int(scene_limit)}
    result["telemetry"] = _rename_telemetry_stage(result.get("telemetry"))
    result["production_shadow"] = {"enabled": False}
    result["provenance"] = build_provenance(
        protocol_version="director-quality-v2-3-phase-b2-pilot",
        model=result.get("model"),
        model_profile=profile,
        scenes=result.get("scenes") or [],
        source_artifacts=[evidence_path],
        evidence_path=evidence_path,
        gate_version=str((result.get("shadow_gate") or {}).get("schema_version") or ""),
        metric_schema_version="director-quality-v2-3-phase-b-metrics-v1",
        generated_at=str(result.get("generated_at") or ""),
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guarded Director Quality V2.3 Phase B2 MiMo pilot")
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--confirmation-token", default="")
    parser.add_argument("--profile-id", default="")
    parser.add_argument("--evidence", type=Path, default=EVIDENCE_PATH)
    parser.add_argument("--scene-limit", type=int, default=REQUIRED_SCENE_COUNT)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    from api.model_registry import get_profile

    profile = get_profile(args.profile_id) if args.profile_id else None
    if not args.execute_real:
        print(json.dumps({"status": "preflight_only", "phase": "B2", "confirmation_required": True, "confirmation_token_name": CONFIRMATION_TOKEN, "profile_id": _text((profile or {}).get("id")), "model_name": _text((profile or {}).get("model_name")), "evidence": str(args.evidence), "scene_limit": int(args.scene_limit), "real_mimo_calls": 0}, ensure_ascii=False, indent=2))
        return 0

    safe_model = validate_real_authorization(execute_real=True, confirmation_token=args.confirmation_token, profile=profile)
    result = run_authorized_pilot(profile=profile, evidence_path=args.evidence, scene_limit=max(REQUIRED_SCENE_COUNT, int(args.scene_limit)), confirmation_token=args.confirmation_token)
    output = args.output or (ARTIFACTS / f"director-quality-v2-3-phase-b2-pilot-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(output), "model": safe_model, "phase": "B2", "scene_count": result["scene_count"], "summary": result["summary"], "shadow_gate": result["shadow_gate"], "side_effects": result["side_effects"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
