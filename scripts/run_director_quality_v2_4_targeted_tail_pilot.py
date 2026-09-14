"""Guarded Targeted Tail Repair pilot for Director Quality V2.4.

The default command is a provider-free preflight.  Real MiMo execution is a
separate, explicit authorization path and is only allowed after the local
unit/integration/full-regression gate has passed.
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
DEFAULT_PILOT = ARTIFACTS / "director-quality-v2-3-phase-b2-pilot-20260914T040506Z.json"
CONFIRMATION_TOKEN = "CONFIRM_DIRECTOR_V24_TARGETED_TAIL_REAL_MIMO_PILOT"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _repo_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def select_tail_scenes(pilot: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [item for item in _list(pilot.get("scenes")) if isinstance(item, dict)]
    selected = []
    for row in rows:
        tail = _dict(row.get("tail_repair"))
        if bool(tail.get("triggered")):
            selected.append(copy.deepcopy(row))
    return selected


def build_preflight(*, pilot_path: Path = DEFAULT_PILOT, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
    selected = select_tail_scenes(pilot)
    safe_profile = _dict(profile)
    key_configured = bool(safe_profile.get("key_configured") or _text(safe_profile.get("api_key")))
    profile_valid = (
        _text(safe_profile.get("provider")) == "openai-compatible"
        and _text(safe_profile.get("capability")) == "llm"
        and "mimo" in _text(safe_profile.get("model_name")).lower()
        and bool(safe_profile.get("enabled", True))
        and key_configured
        and bool(_text(safe_profile.get("base_url")))
    )
    source_provenance_present = bool(_text(_dict(pilot.get("provenance")).get("commit_sha")))
    return {
        "protocol_version": "director-quality-v2-4-targeted-tail-preflight",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_artifact": _repo_path(pilot_path),
        "source_commit": _text(_dict(pilot.get("provenance")).get("commit_sha")),
        "selected_scene_count": len(selected),
        "selected_scene_ids": [_text(item.get("scene_id")) for item in selected],
        "profile": {
            "id": _text(safe_profile.get("id")),
            "provider": _text(safe_profile.get("provider")),
            "model_name": _text(safe_profile.get("model_name")),
            "base_url": _text(safe_profile.get("base_url")),
            "key_configured": key_configured,
        },
        "ready_for_confirmation": bool(selected) and profile_valid and source_provenance_present,
        "blockers": ([] if selected else ["NO_TRIGGERED_TAIL_SCENES"])
        + ([] if profile_valid else ["MIMO_PROFILE_KEY_OR_CONFIGURATION_MISSING"])
        + ([] if source_provenance_present else ["SOURCE_PROVENANCE_MISSING"]),
        "real_mimo_calls": 0,
        "side_effects": {"production": 0, "storyboard": 0, "media": 0, "object_storage": 0, "production_shadow": 0},
    }


def validate_authorization(*, confirmation_token: str, profile: dict[str, Any] | None, preflight: dict[str, Any]) -> None:
    if _text(confirmation_token) != CONFIRMATION_TOKEN:
        raise PermissionError("Targeted Tail Pilot confirmation token 不匹配")
    if not preflight.get("ready_for_confirmation"):
        raise PermissionError("Targeted Tail Pilot preflight 未通过: " + ", ".join(preflight.get("blockers") or []))
    if not isinstance(profile, dict):
        raise PermissionError("必须提供已保存的 MiMo profile")


def run_targeted_tail_pilot(
    *,
    pilot_path: Path = DEFAULT_PILOT,
    evidence_path: Path = ARTIFACTS / "director-quality-v2-3-phase-b2-evidence.json",
    repair_callable: Any,
    model: str = "",
) -> dict[str, Any]:
    """Run only triggered tail scenes through the injected repair provider.

    The callable is the sole external boundary.  Supplying a test callable
    keeps this function entirely offline; the guarded CLI supplies a real
    MiMo callable only after the confirmation token and preflight pass.
    """

    from core.director_tail_repair_executor import execute_tail_repair

    pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
    evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence_by_id = {
        _text(_dict(item.get("scene")).get("scene_id")): item
        for item in _list(evidence_payload.get("scenes"))
        if isinstance(item, dict)
    }
    results: list[dict[str, Any]] = []
    for source_row in select_tail_scenes(pilot):
        scene_id = _text(source_row.get("scene_id"))
        frozen = evidence_by_id.get(scene_id, {})
        evidence = _dict(frozen.get("evidence"))
        candidate = _dict(frozen.get("final_candidate")) or _dict(frozen.get("baseline"))
        contract = _dict(frozen.get("contract")) or _dict(evidence.get("contract"))
        if not candidate or not contract:
            results.append({"scene_id": scene_id, "status": "non_repairable", "non_repairable_reason": "FROZEN_CANDIDATE_OR_CONTRACT_MISSING", "attempts": []})
            continue
        record = {
            "scene_id": scene_id,
            "director_quality_score": source_row.get("director_quality_score"),
            "creative_value": source_row.get("creative_value"),
            "eligible_coverage": source_row.get("eligible_coverage") or source_row.get("coverage") or {},
            "quality_issues": _dict(source_row.get("quality")).get("issues") or [],
            "relevant_beats": [],
            "relevant_shots": [],
        }
        repair_result = execute_tail_repair(
            candidate=candidate,
            record=record,
            contract=contract,
            repair_callable=repair_callable,
            treatment=_dict(evidence.get("treatment")),
            blocking=_dict(evidence.get("blocking")),
            opportunities=source_row.get("opportunities") or [],
            strategy=_dict(frozen.get("strategy")) or _dict(evidence.get("strategy")),
            model=model,
        )
        results.append({
            "scene_id": scene_id,
            "before_director_quality": source_row.get("director_quality_score"),
            "after_candidate_fingerprint": repair_result.get("after_fingerprint"),
            "root_causes": repair_result.get("ranked_root_causes"),
            "repair": repair_result,
            "contract_pass": all(bool(item.get("acceptance", {}).get("accepted", True)) for item in _list(repair_result.get("attempts")) if item.get("accepted")),
        })
    attempted = sum(1 for item in results if _dict(item.get("repair")).get("attempts"))
    accepted = sum(1 for item in results if _list(_dict(item.get("repair")).get("accepted")))
    return {
        "protocol_version": "director-quality-v2-4-targeted-tail-pilot",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_artifacts": [_repo_path(pilot_path), _repo_path(evidence_path)],
        "selected_scene_count": len(results),
        "attempted_scene_count": attempted,
        "accepted_scene_count": accepted,
        "execution_coverage": (attempted / len(results)) if results else 0.0,
        "success_rate": (accepted / attempted) if attempted else None,
        "scenes": results,
        "side_effects": {"production": 0, "storyboard": 0, "media": 0, "object_storage": 0, "production_shadow": 0},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guarded V2.4 Targeted Tail Repair MiMo pilot")
    parser.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--profile-id", default="")
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--confirmation-token", default="")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    from api.model_registry import get_profile

    profile = get_profile(args.profile_id) if args.profile_id else None
    preflight = build_preflight(pilot_path=args.pilot, profile=profile)
    if not args.execute_real:
        output = args.output or (ARTIFACTS / "director-quality-v2-4-targeted-tail-preflight.json")
        output.write_text(json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "preflight_only", "artifact": _repo_path(output), **preflight}, ensure_ascii=False, indent=2))
        return 0
    validate_authorization(confirmation_token=args.confirmation_token, profile=profile, preflight=preflight)
    from core.llm import call_llm_json

    def provider_call(request: dict[str, Any]) -> Any:
        return call_llm_json(
            json.dumps(request, ensure_ascii=False, sort_keys=True),
            system="Return only a bounded director_creative_patch_v1 JSON repair patch within the supplied scope.",
            model_profile=profile,
            required_keys={"schema_version", "patches", "auxiliary_shot_proposals"},
            estimated_tokens=1800,
            audit_extra={"stage": "director_quality_v2_4_targeted_tail_repair"},
        )

    result = run_targeted_tail_pilot(repair_callable=provider_call, pilot_path=args.pilot, model=_text(profile.get("model_name")))
    output = args.output or (ARTIFACTS / f"director-quality-v2-4-targeted-tail-pilot-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "targeted_tail_pilot_complete", "artifact": _repo_path(output), "selected_scene_count": result["selected_scene_count"], "execution_coverage": result["execution_coverage"], "success_rate": result["success_rate"], "side_effects": result["side_effects"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
