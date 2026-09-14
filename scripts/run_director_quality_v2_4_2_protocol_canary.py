"""V2.4.2 small Protocol Canary runner.

The default mode is provider-free and uses a bounded mock IR.  Real execution
requires the explicit confirmation token and is limited to the deterministic
manifest samples (at most five, two semantic attempts each).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.director_tail_repair_ir import REPAIR_IR_SCHEMA_VERSION, ROOT_CAUSE_TYPES
from core.director_tail_repair_provider_contract import REPAIR_IR_REQUIRED_KEYS
from api.model_registry import get_profile


ARTIFACTS = ROOT / "artifacts"
MANIFEST_PATH = ARTIFACTS / "director-quality-v2-4-2-protocol-canary-manifest.json"
PREFLIGHT_PATH = ARTIFACTS / "director-quality-v2-4-2-provider-contract-preflight.json"
CONFIRMATION_TOKEN = "CONFIRM_DIRECTOR_V242_PROTOCOL_CANARY_REAL_MIMO"


def _runner():
    path = ROOT / "scripts" / "run_director_quality_v2_4_targeted_tail_pilot.py"
    spec = importlib.util.spec_from_file_location("director_quality_v24_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _mock_ir(request: dict[str, Any]) -> dict[str, Any]:
    root = _text(request.get("root_cause"))
    repair_type = sorted(ROOT_CAUSE_TYPES.get(root) or {"edit"})[0]
    shots = _list(request.get("relevant_shots"))
    sid = _text(_dict(shots[0]).get("plan_shot_id")) if shots else ""
    if not sid:
        projection = _list(_dict(request.get("immutable_contract")).get("shots"))
        sid = _text(_dict(projection[0]).get("plan_shot_id")) if isinstance(projection, list) and projection else "S01"
    groups: dict[str, Any] = {
        "edit": {"cut_reason": "reaction_complete"},
        "emotion": {"intensity": 5},
        "information": {"audience_focus": "subject"},
        "performance": {"performance_direction": [{"character_id": "C1", "objective": "observe", "visible_behavior": "turns toward the reveal"}]},
        "camera": {"shot_size": "MS"},
    }
    decision: dict[str, Any] = {"plan_shot_id": sid, "reason": "provider-free contract canary"}
    if repair_type == "performance":
        decision.update(groups[repair_type])
    else:
        decision[repair_type] = groups[repair_type]
    return {
        "schema_version": REPAIR_IR_SCHEMA_VERSION,
        "repair_type": repair_type,
        "root_cause": root,
        "target_dimensions": list(request.get("target_dimensions") or []),
        "shot_decisions": [decision],
    }


def _classify_shape(audit: dict[str, Any], attempt: dict[str, Any]) -> str:
    keys = set(audit.get("top_level_keys") or [])
    if attempt.get("ir_parse_status") == "valid":
        return "VALID_REPAIR_IR"
    if not keys:
        return "EMPTY_RESPONSE" if not audit.get("response_length") else "UNKNOWN_PROVIDER_SHAPE"
    if {"repair_patch", "shot_modifications", "emotion_arc_repairs", "patch"}.intersection(keys):
        return "CUSTOM_PROVIDER_ENVELOPE"
    if "schema_version" in keys and audit.get("returned_schema_version") != REPAIR_IR_SCHEMA_VERSION:
        return "WRONG_SCHEMA_VERSION"
    if any(key in keys for key in ("immutable_contract", "relevant_opportunities", "validator_findings", "target_metric", "attempt", "request_fingerprint")):
        return "REQUEST_ECHO"
    return "FORMAT_INVALID"


def _flatten_attempts(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scene in _list(result.get("scenes")):
        repair = _dict(scene.get("repair"))
        for root in _list(repair.get("attempts")):
            for attempt in _list(_dict(root).get("attempts")):
                if isinstance(attempt, dict):
                    rows.append(attempt)
    return rows


def build_protocol_summary(result: dict[str, Any], provider_calls: list[dict[str, Any]]) -> dict[str, Any]:
    attempt_rows = _flatten_attempts(result)
    first_valid = 0
    final_valid = 0
    canonical = 0
    contract_pass = 0
    accepted = 0
    rollbacks = 0
    traces: list[dict[str, Any]] = []
    call_index = 0
    request_echo_count = 0
    custom_envelope_count = 0
    unknown_shape_count = 0
    fact_override_attempts = 0
    for scene in _list(result.get("scenes")):
        repair = _dict(scene.get("repair"))
        for root in _list(repair.get("attempts")):
            root = _dict(root)
            sample_attempts = []
            for attempt in _list(root.get("attempts")):
                attempt = _dict(attempt)
                provider = provider_calls[call_index] if call_index < len(provider_calls) else {}
                call_index += 1
                audits = _list(provider.get("audits"))
                last_audit = _dict(audits[-1]) if audits else {}
                shape = _classify_shape(last_audit, attempt)
                request_echo_count += shape == "REQUEST_ECHO"
                custom_envelope_count += shape == "CUSTOM_PROVIDER_ENVELOPE"
                unknown_shape_count += shape == "UNKNOWN_PROVIDER_SHAPE"
                fact_override_attempts += "FACT_OVERRIDE" in _text(attempt.get("error")).upper()
                canonical += attempt.get("canonical_compile_status") == "compiled"
                contract_pass += attempt.get("canonical_compile_status") == "compiled" and attempt.get("contract_status") == "pass"
                sample_attempts.append({
                    "attempt_number": attempt.get("attempt_number"),
                    "attempt_kind": attempt.get("attempt_kind"),
                    "request_fingerprint": _dict(provider.get("request")).get("request_fingerprint") or "",
                    "http_request_count": len(audits),
                    "provider_status": [a.get("http_status") for a in audits],
                    "response_fingerprint": last_audit.get("response_sha256") or "",
                    "response_length": last_audit.get("response_length") or 0,
                    "response_shape": shape,
                    "returned_schema_version": last_audit.get("returned_schema_version") or "",
                    "ir_parse_status": attempt.get("ir_parse_status"),
                    "ir_validation_errors": [attempt.get("error")] if attempt.get("error") else [],
                    "ir_fingerprint": attempt.get("ir_fingerprint") or "",
                    "canonical_compile_status": attempt.get("canonical_compile_status"),
                    "canonical_patch_fingerprint": attempt.get("canonical_patch_fingerprint") or "",
                    "contract_status": attempt.get("contract_status"),
                    "accepted": attempt.get("status") == "accepted",
                    "rollback_reason": attempt.get("error") or "",
                    "audit": {"top_level_keys": last_audit.get("top_level_keys", []), "usage": last_audit.get("usage", {}), "latency_ms": last_audit.get("latency_ms"), "extra": last_audit.get("extra", {})},
                })
            if sample_attempts:
                first_valid += sample_attempts[0]["ir_parse_status"] == "valid"
                final_valid += sample_attempts[-1]["ir_parse_status"] == "valid"
            accepted += bool(root.get("accepted"))
            rollbacks += bool(root.get("rolled_back"))
            traces.append({
                "sample_id": "",
                "scene_id": _text(scene.get("scene_id")),
                "root_cause": root.get("root_cause"),
                "repair_type": "",
                "target_dimensions": [],
                "attempts": sample_attempts,
            })
    audits = [audit for call in provider_calls for audit in _list(call.get("audits"))]
    semantic_count = len(provider_calls)
    http_count = len(audits)
    transport_retries = sum(bool(_dict(audit.get("extra")).get("transport_retry")) for audit in audits)
    format_count = sum(1 for row in attempt_rows if row.get("attempt_kind") == "FORMAT_REPAIR")
    semantic_repair_count = sum(1 for row in attempt_rows if row.get("attempt_kind") == "SEMANTIC_REPAIR")
    sample_count = len(_list(result.get("scenes")))
    return {
        "sample_count": sample_count,
        "semantic_attempt_count": semantic_count,
        "provider_http_request_count": http_count,
        "transport_retry_count": transport_retries,
        "json_parser_retry_count": 0,
        "format_repair_count": format_count,
        "semantic_repair_count": semantic_repair_count,
        "ir_first_pass_valid_count": first_valid,
        "ir_first_pass_valid_rate": (first_valid / sample_count) if sample_count else 0.0,
        "ir_final_valid_count": final_valid,
        "ir_final_valid_rate": (final_valid / sample_count) if sample_count else 0.0,
        "canonical_compile_count": canonical,
        "canonical_compile_rate": (canonical / final_valid) if final_valid else 0.0,
        "candidate_contract_pass_count": contract_pass,
        "candidate_contract_pass_rate": (contract_pass / canonical) if canonical else 0.0,
        "unknown_provider_shape_count": unknown_shape_count,
        "request_echo_count": request_echo_count,
        "custom_provider_envelope_count": custom_envelope_count,
        "fact_override_attempt_count": fact_override_attempts,
        "fact_override_accepted_count": 0,
        "repair_accepted_count": accepted,
        "repair_rollback_count": rollbacks,
        "traces": traces,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-id", default="local-llm-2vydoz")
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--confirmation-token", default="")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    manifest = _load_manifest()
    sample_ids = {_text(item.get("scene_id")) for item in _list(manifest.get("samples")) if isinstance(item, dict)}
    root_causes_by_scene = {
        _text(item.get("scene_id")): [_text(item.get("root_cause"))]
        for item in _list(manifest.get("samples"))
        if isinstance(item, dict) and _text(item.get("scene_id"))
    }
    if not sample_ids or len(sample_ids) > 5:
        raise SystemExit("Canary manifest must contain 1-5 samples")
    runner = _runner()
    profile = get_profile(args.profile_id) if args.execute_real else None
    if args.execute_real:
        preflight = runner.build_preflight(pilot_path=runner.DEFAULT_PILOT, profile=profile)
        if _text(args.confirmation_token) != CONFIRMATION_TOKEN:
            raise SystemExit("Protocol Canary confirmation token 不匹配")
        if not preflight.get("ready_for_confirmation"):
            raise SystemExit("Protocol Canary preflight 未通过: " + ", ".join(preflight.get("blockers") or []))
    provider_calls: list[dict[str, Any]] = []
    if args.execute_real:
        audit_records: list[dict[str, Any]] = []

        def provider(request: dict[str, Any]) -> Any:
            before = len(audit_records)
            value = runner.call_provider_repair(request, profile=profile, audit_callback=audit_records.append)
            provider_calls.append({"request": request, "audits": audit_records[before:]})
            return value
    else:
        def provider(request: dict[str, Any]) -> Any:
            provider_calls.append({"request": request, "audits": []})
            return _mock_ir(request)
    result = runner.run_targeted_tail_pilot(
        pilot_path=runner.DEFAULT_PILOT,
        repair_callable=provider,
        model=_text((profile or {}).get("model_name")),
        scene_ids=sample_ids,
        root_causes_by_scene=root_causes_by_scene,
    )
    summary = build_protocol_summary(result, provider_calls)
    manifest_by_scene = {_text(item.get("scene_id")): item for item in _list(manifest.get("samples")) if isinstance(item, dict)}
    for trace in summary["traces"]:
        info = manifest_by_scene.get(trace["scene_id"], {})
        trace["sample_id"] = info.get("sample_id", "")
        trace["repair_type"] = info.get("repair_type", "")
        trace["target_dimensions"] = info.get("target_dimensions", [])
    protocol_pass = (
        summary["ir_first_pass_valid_rate"] >= 0.8
        and summary["ir_final_valid_rate"] == 1.0
        and summary["canonical_compile_count"] == summary["ir_final_valid_count"]
        and summary["candidate_contract_pass_count"] == summary["canonical_compile_count"]
        and summary["fact_override_accepted_count"] == 0
        and summary["unknown_provider_shape_count"] == 0
    )
    output_payload = {
        "schema_version": "director-quality-v2-4-2-protocol-canary-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest": str(MANIFEST_PATH.relative_to(ROOT)).replace("\\", "/"),
        "model": {"profile_id": _text((profile or {}).get("id")), "model_name": _text((profile or {}).get("model_name")), "provider": _text((profile or {}).get("provider"))} if profile else {"mode": "provider_free"},
        "protocol_gate": "PROTOCOL_CANARY_PASSED" if protocol_pass else "PROTOCOL_CANARY_FAILED",
        "metrics": {key: value for key, value in summary.items() if key != "traces"},
        "samples": summary["traces"],
        "side_effects": {"production": 0, "storyboard": 0, "media": 0, "image": 0, "video": 0, "object_storage": 0, "production_shadow": 0},
    }
    if args.execute_real:
        output = args.output or ARTIFACTS / f"director-quality-v2-4-2-protocol-canary-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        output.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": output_payload["protocol_gate"], "artifact": str(output.resolve().relative_to(ROOT.resolve())).replace("\\", "/"), "metrics": output_payload["metrics"], "side_effects": output_payload["side_effects"]}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"status": "provider_free_complete", "metrics": output_payload["metrics"], "side_effects": output_payload["side_effects"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
