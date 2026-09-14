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

from core.director_tail_repair_ir import REPAIR_IR_SCHEMA_VERSION
from core.director_tail_repair_provider_contract import (
    REPAIR_IR_REQUIRED_KEYS,
    build_provider_system_prompt,
    provider_contract_fingerprint,
)
from core.director_tail_repair_request import REPAIR_REQUEST_SCHEMA_VERSION
# Targeted repair must consume the immutable, provenance-bearing B2 freeze.
# The historical V2.3 pilot remains available through --pilot for audit/replay,
# but must not be the default input for a V2.4 real-call gate.
DEFAULT_PILOT = ARTIFACTS / "director-quality-v2-4-b2-freeze.json"
CONFIRMATION_TOKEN = "CONFIRM_DIRECTOR_V24_TARGETED_TAIL_REAL_MIMO_PILOT"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _creative_value_score(value: Any) -> float | None:
    if isinstance(value, dict):
        return _number(value.get("score"))
    return _number(value)


def _repo_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def build_provider_contract_alignment(
    *,
    provider_system_prompt: str | None = None,
    provider_required_keys: Any = None,
    executor_required_schema: str = REPAIR_IR_SCHEMA_VERSION,
    executor_require_repair_ir: bool = True,
    request_schema: str = REPAIR_REQUEST_SCHEMA_VERSION,
    json_parse_retries: int = 0,
    canonical_paths_requested: bool = False,
) -> dict[str, Any]:
    """Validate the provider/executor handshake without contacting a provider."""

    system_prompt = build_provider_system_prompt() if provider_system_prompt is None else str(provider_system_prompt)
    required = set(REPAIR_IR_REQUIRED_KEYS if provider_required_keys is None else provider_required_keys)
    expected = set(REPAIR_IR_REQUIRED_KEYS)
    blockers: list[str] = []
    if REPAIR_IR_SCHEMA_VERSION not in system_prompt or "director_creative_patch_v1" in system_prompt:
        blockers.append("REPAIR_PROVIDER_SYSTEM_PROMPT_MISMATCH")
    if required != expected:
        blockers.append("REPAIR_PROVIDER_REQUIRED_KEYS_MISMATCH")
    if str(executor_required_schema) != REPAIR_IR_SCHEMA_VERSION:
        blockers.append("REPAIR_PROVIDER_OUTPUT_SCHEMA_MISMATCH")
    if not executor_require_repair_ir:
        blockers.append("REPAIR_PROVIDER_OUTPUT_SCHEMA_MISMATCH")
    if str(request_schema) != REPAIR_REQUEST_SCHEMA_VERSION:
        blockers.append("REPAIR_REQUEST_SCHEMA_MISMATCH")
    if int(json_parse_retries or 0) != 0:
        blockers.append("NESTED_JSON_RETRY_ENABLED")
    if canonical_paths_requested:
        blockers.append("CANONICAL_PATCH_OUTPUT_REQUESTED")
    import hashlib
    return {
        "provider_output_schema": REPAIR_IR_SCHEMA_VERSION,
        "executor_required_output_schema": str(executor_required_schema),
        "executor_require_repair_ir": bool(executor_require_repair_ir),
        "request_schema": str(request_schema),
        "provider_required_keys": sorted(required),
        "ir_required_keys": sorted(expected),
        "provider_system_prompt_fingerprint": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        "provider_contract_fingerprint": provider_contract_fingerprint(),
        "canonical_paths_requested": bool(canonical_paths_requested),
        "json_parse_retries": int(json_parse_retries or 0),
        "nested_json_retry_enabled": int(json_parse_retries or 0) != 0,
        "aligned": not blockers,
        "blockers": blockers,
    }


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
    configured_contract = _dict(safe_profile.get("provider_contract"))
    alignment = build_provider_contract_alignment(
        provider_system_prompt=configured_contract.get("system_prompt") if "system_prompt" in configured_contract else None,
        provider_required_keys=configured_contract.get("required_keys") if "required_keys" in configured_contract else None,
        executor_required_schema=_text(configured_contract.get("executor_required_output_schema")) or REPAIR_IR_SCHEMA_VERSION,
        executor_require_repair_ir=bool(configured_contract.get("executor_require_repair_ir", True)),
        request_schema=_text(configured_contract.get("request_schema")) or REPAIR_REQUEST_SCHEMA_VERSION,
        json_parse_retries=configured_contract.get("json_parse_retries", 0),
        canonical_paths_requested=bool(configured_contract.get("canonical_paths_requested", False)),
    )
    source_provenance_present = bool(_text(_dict(pilot.get("provenance")).get("commit_sha")))
    return {
        "protocol_version": "director-quality-v2-4-2-provider-contract-preflight",
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
        "provider_contract_alignment": alignment,
        "ready_for_confirmation": bool(selected) and profile_valid and source_provenance_present and bool(alignment["aligned"]),
        "blockers": ([] if selected else ["NO_TRIGGERED_TAIL_SCENES"])
        + ([] if profile_valid else ["MIMO_PROFILE_KEY_OR_CONFIGURATION_MISSING"])
        + ([] if source_provenance_present else ["SOURCE_PROVENANCE_MISSING"])
        + list(alignment["blockers"]),
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


def call_provider_repair(request: dict[str, Any], *, profile: dict[str, Any], audit_callback=None) -> Any:
    """Call the configured provider using the authoritative Repair IR contract."""

    from core.llm import call_llm_json

    return call_llm_json(
        json.dumps(request, ensure_ascii=False, sort_keys=True),
        system=build_provider_system_prompt(),
        model_profile=profile,
        required_keys=set(REPAIR_IR_REQUIRED_KEYS),
        json_parse_retries=0,
        retries=3,
        estimated_tokens=1800,
        audit_callback=audit_callback,
        audit_extra={
            "stage": "director_quality_v2_4_targeted_tail_repair",
            "output_contract_version": REPAIR_IR_SCHEMA_VERSION,
            "provider_contract_fingerprint": provider_contract_fingerprint(),
        },
        audit_repair_request=request,
    )


def run_targeted_tail_pilot(
    *,
    pilot_path: Path = DEFAULT_PILOT,
    evidence_path: Path = ARTIFACTS / "director-quality-v2-3-phase-b2-evidence.json",
    repair_callable: Any,
    model: str = "",
    audit_records: list[dict[str, Any]] | None = None,
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
        before_candidate = copy.deepcopy(candidate)
        from core.director_patch_compiler import compile_creative_patches
        from core.director_patch_validator import validate_compiled_patch_result
        from core.director_quality_validator import score_director_quality

        before_quality = score_director_quality(
            before_candidate,
            treatment=_dict(evidence.get("treatment")),
            blocking=_dict(evidence.get("blocking")),
        )
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
            require_repair_ir=True,
        )
        after_candidate = _dict(repair_result.get("candidate")) or before_candidate
        after_quality = score_director_quality(
            after_candidate,
            treatment=_dict(evidence.get("treatment")),
            blocking=_dict(evidence.get("blocking")),
        )
        empty_document = {
            "schema_version": "director_creative_patch_v1",
            "patches": [],
            "auxiliary_shot_proposals": [],
        }
        final_compilation = compile_creative_patches(
            after_candidate,
            empty_document,
            contract,
            allow_partial=False,
        )
        final_validation = validate_compiled_patch_result(
            final_compilation,
            after_candidate,
            contract,
            treatment=_dict(evidence.get("treatment")),
            blocking=_dict(evidence.get("blocking")),
        )
        before_dq = _number(source_row.get("director_quality_score"))
        if before_dq is None:
            before_dq = _number(before_quality.get("director_quality_score"))
        after_dq = _number(after_quality.get("director_quality_score"))
        before_cv = _creative_value_score(source_row.get("creative_value"))
        # Tail repair changes the candidate, not the opportunity planner.  Do
        # not invent a post-repair Creative Value score without replaying that
        # planner; expose the measurement boundary explicitly instead.
        after_cv = before_cv
        target_before: dict[str, float] = {}
        target_delta: dict[str, float] = {}
        for root_row in _list(repair_result.get("attempts")):
            context = _dict(root_row.get("minimal_context"))
            for dimension, value in _dict(context.get("target_metric")).items():
                numeric = _number(value)
                if numeric is not None:
                    target_before.setdefault(str(dimension), numeric)
            acceptance = _dict(
                _dict(root_row.get("attempts", [{}])[-1] if _list(root_row.get("attempts")) else {}).get("acceptance")
            )
            for dimension, value in _dict(acceptance.get("target_dimension_deltas")).items():
                numeric = _number(value)
                if numeric is not None:
                    target_delta[str(dimension)] = round(target_delta.get(str(dimension), 0.0) + numeric, 4)
        target_after = {
            dimension: round(value + target_delta.get(dimension, 0.0), 4)
            for dimension, value in target_before.items()
        }
        results.append({
            "scene_id": scene_id,
            "before_director_quality": before_dq,
            "after_director_quality": after_dq,
            "director_quality_delta": round((after_dq - before_dq), 4) if before_dq is not None and after_dq is not None else None,
            "before_creative_value": before_cv,
            "after_creative_value": after_cv,
            "creative_value_delta": 0.0 if before_cv is not None else None,
            "creative_value_measurement_status": "not_replayed_after_tail_repair",
            "target_dimensions_before": target_before,
            "target_dimensions_after": target_after,
            "target_dimension_deltas": target_delta,
            "after_candidate_fingerprint": repair_result.get("after_fingerprint"),
            "root_causes": repair_result.get("ranked_root_causes"),
            "repair": repair_result,
            "contract_pass": bool(final_validation.get("contract_pass")),
            "contract_validation_errors": _list(final_validation.get("errors")),
            "accepted": _list(repair_result.get("accepted")),
            "rolled_back": _list(repair_result.get("rolled_back")),
        })
    attempted = sum(1 for item in results if _dict(item.get("repair")).get("attempts"))
    accepted = sum(1 for item in results if _list(_dict(item.get("repair")).get("accepted")))
    root_rows = [
        root
        for item in results
        for root in _list(_dict(item.get("repair")).get("attempts"))
        if isinstance(root, dict)
    ]
    semantic_attempt_count = sum(len(_list(root.get("attempts"))) for root in root_rows)
    attempt_kinds = [
        attempt.get("attempt_kind")
        for root in root_rows
        for attempt in _list(root.get("attempts"))
        if isinstance(attempt, dict)
    ]
    selected_root_count = sum(len(_dict(item.get("root_causes")).get("ranked_root_causes") or []) for item in results)
    attempted_root_count = len(root_rows)
    accepted_root_count = sum(bool(root.get("accepted")) for root in root_rows)
    accepted_scene_count = sum(bool(_list(_dict(item.get("repair")).get("accepted"))) for item in results)
    audit_items = [item for item in (audit_records or []) if isinstance(item, dict)] if audit_records is not None else []
    observed_http_count = len(audit_items) if audit_records is not None else None
    transport_retry_count = sum(bool(_dict(item.get("extra")).get("transport_retry")) for item in audit_items) if audit_records is not None else None
    return {
        "protocol_version": "director-quality-v2-4-2-targeted-tail-pilot",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_artifacts": [_repo_path(pilot_path), _repo_path(evidence_path)],
        "selected_scene_count": len(results),
        "attempted_scene_count": attempted,
        "accepted_scene_count": accepted,
        "execution_coverage": (attempted / len(results)) if results else 0.0,
        "success_rate": (accepted / attempted) if attempted else None,
        "scene_execution_coverage": (attempted / len(results)) if results else 0.0,
        "root_cause_attempt_coverage": (attempted_root_count / selected_root_count) if selected_root_count else 0.0,
        "repair_acceptance_rate": (accepted_root_count / attempted_root_count) if attempted_root_count else 0.0,
        "scene_repair_success_rate": (accepted_scene_count / attempted) if attempted else 0.0,
        "metrics": {
            "semantic_attempt_count": semantic_attempt_count,
            "provider_http_request_count": observed_http_count,
            "provider_http_request_count_status": "observed" if audit_records is not None else "not_collected",
            "transport_retry_count": transport_retry_count,
            "json_parser_retry_count": 0,
            "format_repair_count": attempt_kinds.count("FORMAT_REPAIR"),
            "semantic_repair_count": attempt_kinds.count("SEMANTIC_REPAIR"),
            "creative_generation_count": attempt_kinds.count("CREATIVE_GENERATION"),
        },
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
    audit_records: list[dict[str, Any]] = []

    def provider_call(request: dict[str, Any]) -> Any:
        return call_provider_repair(request, profile=profile, audit_callback=audit_records.append)

    result = run_targeted_tail_pilot(
        repair_callable=provider_call,
        pilot_path=args.pilot,
        model=_text(profile.get("model_name")),
        audit_records=audit_records,
    )
    output = args.output or (ARTIFACTS / f"director-quality-v2-4-targeted-tail-pilot-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "targeted_tail_pilot_complete", "artifact": _repo_path(output), "selected_scene_count": result["selected_scene_count"], "execution_coverage": result["execution_coverage"], "success_rate": result["success_rate"], "side_effects": result["side_effects"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
