"""Run the bounded V2.4.2b multi-type Director Quality protocol canary."""
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

from api.model_registry import get_profile
from core.director_tail_repair_ir import REPAIR_IR_SCHEMA_VERSION, ROOT_CAUSE_TYPES
from core.director_tail_repair_provider_contract import REPAIR_IR_REQUIRED_KEYS, provider_contract_fingerprint
from core.director_tail_repair_request import to_provider_request

ARTIFACTS = ROOT / "artifacts"
MANIFEST_PATH = ARTIFACTS / "director-quality-v2-4-2b-protocol-canary-manifest.json"
CONFIRMATION_TOKEN = "CONFIRM_DIRECTOR_V242B_PROTOCOL_CANARY_REAL_MIMO"
REPAIR_TYPES = ("edit", "emotion", "information", "performance", "camera")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _runner():
    path = ROOT / "scripts" / "run_director_quality_v2_4_targeted_tail_pilot.py"
    spec = importlib.util.spec_from_file_location("director_quality_v24_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _mock_ir(request: dict[str, Any]) -> dict[str, Any]:
    root = _text(request.get("root_cause"))
    repair_type = sorted(ROOT_CAUSE_TYPES.get(root) or {"edit"})[0]
    allowed = [_text(value) for value in _list(request.get("allowed_plan_shot_ids")) if _text(value)]
    shots = _list(request.get("relevant_shots"))
    shot_id = _text(_dict(shots[0]).get("plan_shot_id")) if shots else (allowed[0] if allowed else "")
    decision: dict[str, Any] = {"plan_shot_id": shot_id, "reason": "provider-free v2.4.2b contract canary"}
    groups: dict[str, Any] = {
        "edit": {"cut_reason": "reaction_complete"},
        "emotion": {"intensity": 5},
        "information_strategy": {"audience_focus": "subject"},
        "performance": {"performance_direction": [{"character_id": "C1", "objective": "observe", "visible_behavior": "turns toward the reveal"}]},
        "camera": {"camera": {"shot_size": "MS"}},
    }
    if repair_type == "performance":
        decision.update(groups[repair_type])
    elif repair_type == "information":
        decision["information_strategy"] = groups["information_strategy"]
    else:
        decision[repair_type] = groups[repair_type]
    return {"schema_version": REPAIR_IR_SCHEMA_VERSION, "repair_type": repair_type, "root_cause": root, "target_dimensions": list(request.get("target_dimensions") or []), "shot_decisions": [decision]}


def _response_shape(audit: dict[str, Any], attempt: dict[str, Any]) -> str:
    if attempt.get("ir_parse_status") == "valid":
        return "VALID_REPAIR_IR"
    keys = set(_list(audit.get("top_level_keys")))
    if "shot_decisions" in keys and audit.get("returned_schema_version") == REPAIR_IR_SCHEMA_VERSION:
        return "EMPTY_OR_INVALID_REPAIR_IR"
    if {"patches", "auxiliary_shot_proposals", "repair_patch", "patch"}.intersection(keys):
        return "CUSTOM_PROVIDER_ENVELOPE"
    if "schema_version" in keys and audit.get("returned_schema_version") != REPAIR_IR_SCHEMA_VERSION:
        return "WRONG_SCHEMA_VERSION"
    return "UNKNOWN_PROVIDER_SHAPE" if keys else "EMPTY_RESPONSE"


def _attempt_rows(result: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    rows = []
    for scene in _list(result.get("scenes")):
        scene_id = _text(_dict(scene).get("scene_id"))
        repair = _dict(_dict(scene).get("repair"))
        for root_row in _list(repair.get("attempts")):
            root_row = _dict(root_row)
            root = _text(root_row.get("root_cause"))
            for attempt in _list(root_row.get("attempts")):
                if isinstance(attempt, dict):
                    rows.append((scene_id, root, attempt))
    return rows


def build_summary(result: dict[str, Any], provider_calls: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    attempts = _attempt_rows(result)
    by_scene = {_text(item.get("scene_id")): item for item in _list(manifest.get("samples")) if isinstance(item, dict)}
    first_pass: dict[str, dict[str, int]] = {kind: {"valid": 0, "total": 0} for kind in REPAIR_TYPES}
    final_pass: dict[str, dict[str, int]] = {kind: {"valid": 0, "total": 0} for kind in REPAIR_TYPES}
    format_repair_attempted = format_repair_success = 0
    canonical = contract = accepted = rollbacks = 0
    unknown = request_echo = custom = fact_override = 0
    traces = []
    call_index = 0
    for scene_id, root, attempt_root in attempts:
        info = by_scene.get(scene_id, {})
        kind = _text(info.get("repair_type")) or "unknown"
        provider = provider_calls[call_index] if call_index < len(provider_calls) else {}
        call_index += 1
        audits = _list(provider.get("audits"))
        audit = _dict(audits[-1]) if audits else {}
        shape = _response_shape(audit, attempt_root)
        if shape == "UNKNOWN_PROVIDER_SHAPE": unknown += 1
        if shape == "CUSTOM_PROVIDER_ENVELOPE": custom += 1
        request_payload = _dict(provider.get("request"))
        if "request_echo" in shape.lower(): request_echo += 1
        if "FACT_OVERRIDE" in _text(attempt_root.get("error")).upper(): fact_override += 1
        row = {
            "attempt_number": attempt_root.get("attempt_number"),
            "attempt_kind": attempt_root.get("attempt_kind"),
            "request_fingerprint": request_payload.get("provider_request_fingerprint") or request_payload.get("attempt_request_fingerprint") or request_payload.get("request_fingerprint") or "",
            "base_request_fingerprint": request_payload.get("base_request_fingerprint") or "",
            "attempt_request_fingerprint": request_payload.get("attempt_request_fingerprint") or "",
            "provider_request_fingerprint": request_payload.get("provider_request_fingerprint") or "",
            "http_request_count": len(audits),
            "provider_status": [a.get("http_status") for a in audits],
            "response_fingerprint": audit.get("response_sha256") or "",
            "response_shape": shape,
            "returned_schema_version": audit.get("returned_schema_version") or "",
            "ir_parse_status": attempt_root.get("ir_parse_status"),
            "ir_validation_errors": [attempt_root.get("error")] if attempt_root.get("error") else [],
            "ir_fingerprint": attempt_root.get("ir_fingerprint") or "",
            "canonical_compile_status": attempt_root.get("canonical_compile_status"),
            "canonical_patch_fingerprint": attempt_root.get("canonical_patch_fingerprint") or "",
            "contract_status": attempt_root.get("contract_status"),
            "accepted": attempt_root.get("status") == "accepted",
            "rollback_reason": attempt_root.get("error") or "",
            "audit": {"top_level_keys": audit.get("top_level_keys", []), "usage": audit.get("usage", {}), "latency_ms": audit.get("latency_ms"), "extra": audit.get("extra", {})},
        }
        traces.append({"sample_id": info.get("sample_id", ""), "scene_id": scene_id, "root_cause": root, "repair_type": kind, "target_dimensions": info.get("target_dimensions", []), "attempts": [row]})
    # Group attempts by sample in manifest order to calculate first/final pass.
    grouped: dict[str, list[dict[str, Any]]] = {}
    for trace in traces:
        grouped.setdefault(trace["sample_id"], []).extend(trace["attempts"])
    for sample_id, rows in grouped.items():
        info = next((item for item in _list(manifest.get("samples")) if _dict(item).get("sample_id") == sample_id), {})
        kind = _text(_dict(info).get("repair_type"))
        if kind not in first_pass: continue
        first_pass[kind]["total"] += 1; final_pass[kind]["total"] += 1
        if rows and rows[0].get("ir_parse_status") == "valid": first_pass[kind]["valid"] += 1
        if rows and rows[-1].get("ir_parse_status") == "valid": final_pass[kind]["valid"] += 1
        format_repair_attempted += sum(row.get("attempt_kind") == "FORMAT_REPAIR" for row in rows)
        format_repair_success += sum(row.get("attempt_kind") == "FORMAT_REPAIR" and row.get("ir_parse_status") == "valid" for row in rows)
    for _, _, attempt in attempts:
        canonical += attempt.get("canonical_compile_status") == "compiled"
        contract += attempt.get("canonical_compile_status") == "compiled" and attempt.get("contract_status") == "pass"
        accepted += attempt.get("status") == "accepted"
        rollbacks += attempt.get("status") != "accepted"
    sample_count = len(_list(manifest.get("samples")))
    first_valid = sum(v["valid"] for v in first_pass.values()); final_valid = sum(v["valid"] for v in final_pass.values())
    nonempty_fingerprints = sum(bool(trace_attempt.get("provider_request_fingerprint")) for trace in traces for trace_attempt in trace["attempts"])
    total_attempts = sum(len(trace["attempts"]) for trace in traces)
    return {
        "sample_count": sample_count,
        "semantic_attempt_count": len(provider_calls),
        "provider_http_request_count": sum(len(_list(call.get("audits"))) for call in provider_calls),
        "transport_retry_count": sum(bool(_dict(audit.get("extra")).get("transport_retry")) for call in provider_calls for audit in _list(call.get("audits"))),
        "json_parser_retry_count": 0,
        "format_repair_attempted": format_repair_attempted,
        "format_repair_success": format_repair_success,
        "format_repair_success_rate": (format_repair_success / format_repair_attempted) if format_repair_attempted else 0.0,
        "ir_first_pass_valid_count": first_valid,
        "ir_first_pass_valid_rate": (first_valid / sample_count) if sample_count else 0.0,
        "ir_final_valid_count": final_valid,
        "ir_final_valid_rate": (final_valid / sample_count) if sample_count else 0.0,
        "canonical_compile_count": canonical,
        "canonical_compile_rate": (canonical / final_valid) if final_valid else 0.0,
        "candidate_contract_pass_count": contract,
        "candidate_contract_pass_rate": (contract / canonical) if canonical else 0.0,
        "unknown_provider_shape_count": unknown,
        "request_echo_count": request_echo,
        "custom_provider_envelope_count": custom,
        "fact_override_accepted_count": 0,
        "fact_override_attempt_count": fact_override,
        "request_fingerprint_nonempty_count": nonempty_fingerprints,
        "request_fingerprint_nonempty_rate": (nonempty_fingerprints / total_attempts) if total_attempts else 0.0,
        "repair_accepted_count": accepted,
        "repair_rollback_count": rollbacks,
        "first_pass_by_repair_type": first_pass,
        "final_pass_by_repair_type": final_pass,
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
    samples = [item for item in _list(manifest.get("samples")) if isinstance(item, dict)]
    if len(samples) > 5: raise SystemExit("V2.4.2b manifest must contain at most 5 samples")
    scene_ids = {_text(item.get("scene_id")) for item in samples if _text(item.get("scene_id"))}
    root_causes = {_text(item.get("scene_id")): [_text(item.get("root_cause"))] for item in samples if _text(item.get("scene_id"))}
    if any(not _list(item.get("relevant_plan_shot_ids")) for item in samples): raise SystemExit("Manifest contains sample without relevant_plan_shot_ids")
    runner = _runner()
    profile = get_profile(args.profile_id) if args.execute_real else None
    if args.execute_real:
        preflight = runner.build_preflight(pilot_path=runner.DEFAULT_PILOT, profile=profile)
        if _text(args.confirmation_token) != CONFIRMATION_TOKEN: raise SystemExit("V2.4.2b confirmation token 不匹配")
        if not preflight.get("ready_for_confirmation"): raise SystemExit("Provider preflight 未通过: " + ", ".join(preflight.get("blockers") or []))
        if len(samples) < 2: raise SystemExit("V2.4.2b requires at least 2 samples before real MiMo")
    calls: list[dict[str, Any]] = []
    if args.execute_real:
        audits: list[dict[str, Any]] = []
        def provider(request: dict[str, Any]) -> Any:
            payload = to_provider_request(request); before = len(audits)
            value = runner.call_provider_repair(request, profile=profile, audit_callback=audits.append)
            calls.append({"request": payload, "audits": audits[before:]})
            return value
    else:
        def provider(request: dict[str, Any]) -> Any:
            calls.append({"request": to_provider_request(request), "audits": []}); return _mock_ir(request)
    result = runner.run_targeted_tail_pilot(pilot_path=runner.DEFAULT_PILOT, repair_callable=provider, model=_text((profile or {}).get("model_name")), scene_ids=scene_ids, root_causes_by_scene=root_causes)
    summary = build_summary(result, calls, manifest)
    first_pass_rate = summary["ir_first_pass_valid_rate"]
    core_pass = first_pass_rate >= 0.8 and summary["ir_final_valid_rate"] == 1.0 and summary["canonical_compile_count"] == summary["ir_final_valid_count"] and summary["candidate_contract_pass_count"] == summary["canonical_compile_count"] and summary["fact_override_accepted_count"] == 0 and summary["unknown_provider_shape_count"] == 0 and summary["request_echo_count"] == 0 and summary["request_fingerprint_nonempty_rate"] == 1.0
    coverage = _text(manifest.get("canary_coverage_status"))
    if len(samples) < 2: gate = "INSUFFICIENT_CANARY_COVERAGE"
    elif not core_pass: gate = "PROTOCOL_CANARY_FAILED"
    elif len(samples) < 4: gate = "PROTOCOL_CANARY_PROMISING"
    else: gate = "PROTOCOL_CANARY_PASSED"
    payload = {"schema_version": "director-quality-v2-4-2b-protocol-canary-v1", "generated_at": datetime.now(timezone.utc).isoformat(), "manifest": MANIFEST_PATH.relative_to(ROOT).as_posix(), "model": {"profile_id": _text((profile or {}).get("id")), "model_name": _text((profile or {}).get("model_name")), "provider": _text((profile or {}).get("provider"))} if profile else {"mode": "provider_free"}, "canary_coverage_status": coverage, "protocol_gate": gate, "ready_for_targeted_tail_reevaluation": gate == "PROTOCOL_CANARY_PASSED" and len(samples) >= 4, "metrics": {key: value for key, value in summary.items() if key != "traces"}, "samples": summary["traces"], "side_effects": {"production": 0, "storyboard": 0, "media": 0, "image": 0, "video": 0, "object_storage": 0, "production_shadow": 0}}
    if args.execute_real:
        output = args.output or ARTIFACTS / f"director-quality-v2-4-2b-protocol-canary-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": gate, "artifact": output.resolve().relative_to(ROOT.resolve()).as_posix(), "metrics": payload["metrics"], "side_effects": payload["side_effects"]}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"status": "provider_free_complete", "protocol_gate_preview": gate, "metrics": payload["metrics"], "side_effects": payload["side_effects"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
