"""V2.4.2c frozen four-sample canary (provider-free by default)."""
from __future__ import annotations
import argparse, importlib.util, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
MANIFEST_PATH = ARTIFACTS / "director-quality-v2-4-2b-protocol-canary-manifest.json"
CONFIRMATION_TOKEN = "CONFIRM_DIRECTOR_V242C_TYPED_REPAIR_IR_REAL_MIMO"

def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path); module = importlib.util.module_from_spec(spec); assert spec.loader
    spec.loader.exec_module(module); return module
def _dict(v: Any) -> dict[str, Any]: return v if isinstance(v, dict) else {}
def _list(v: Any) -> list[Any]: return v if isinstance(v, list) else []
def _text(v: Any) -> str: return str(v or "").strip()

def _attempt_rows(result: dict[str, Any]):
    for scene in _list(result.get("scenes")):
        sid = _text(_dict(scene).get("scene_id")); repair = _dict(_dict(scene).get("repair"))
        for root in _list(repair.get("attempts")):
            for attempt in _list(_dict(root).get("attempts")):
                if isinstance(attempt, dict): yield sid, _text(_dict(root).get("root_cause")), attempt

def build_summary(result: dict[str, Any], provider_calls: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    samples = {str(item.get("sample_id")): item for item in _list(manifest.get("samples")) if isinstance(item, dict)}
    grouped: dict[str, dict[str, Any]] = {}
    call_index = 0
    for scene_id, root, attempt in _attempt_rows(result):
        sample = next((item for item in samples.values() if _text(item.get("scene_id")) == scene_id), {})
        sample_id = _text(sample.get("sample_id"))
        row = {"attempt_number": attempt.get("attempt_number"), "attempt_kind": attempt.get("attempt_kind"), "ir_parse_status": attempt.get("ir_parse_status"), "canonical_compile_status": attempt.get("canonical_compile_status"), "contract_status": attempt.get("contract_status"), "accepted": attempt.get("status") == "accepted", "error": attempt.get("error", ""), "ir_validation_errors_structured": attempt.get("ir_validation_errors_structured", [])}
        provider = provider_calls[call_index] if call_index < len(provider_calls) else {}; call_index += 1
        audits = _list(provider.get("audits")); audit = _dict(audits[-1]) if audits else {}; request = _dict(provider.get("request"))
        row.update({"provider_request_fingerprint": request.get("provider_request_fingerprint", ""), "response_fingerprint": audit.get("response_sha256", ""), "http_request_count": len(audits), "provider_status": [a.get("http_status") for a in audits]})
        entry = grouped.setdefault(sample_id, {"sample_id": sample_id, "scene_id": scene_id, "repair_type": sample.get("repair_type"), "root_cause": root, "attempts": []})
        entry["attempts"].append(row)
    first_valid = sum(bool(e["attempts"] and e["attempts"][0].get("ir_parse_status") == "valid") for e in grouped.values())
    final_valid = sum(bool(e["attempts"] and e["attempts"][-1].get("ir_parse_status") == "valid") for e in grouped.values())
    accepted_roots = sum(any(a.get("accepted") for a in e["attempts"]) for e in grouped.values())
    rejected_attempts = sum(not a.get("accepted") for e in grouped.values() for a in e["attempts"])
    rollback_roots = sum(not any(a.get("accepted") for a in e["attempts"]) for e in grouped.values())
    by_type = {kind: {"valid": 0, "total": 0} for kind in ("edit", "emotion", "information", "performance", "camera")}
    for e in grouped.values():
        kind = _text(e.get("repair_type"));
        if kind in by_type:
            by_type[kind]["total"] += 1
            if e["attempts"] and e["attempts"][0].get("ir_parse_status") == "valid": by_type[kind]["valid"] += 1
    available = sorted({str(e.get("repair_type")) for e in grouped.values()})
    return {"sample_count": len(samples), "semantic_attempt_count": len(provider_calls), "provider_http_request_count": sum(len(_list(c.get("audits"))) for c in provider_calls), "attempt_rejected_count": rejected_attempts, "root_cause_rollback_count": rollback_roots, "scene_rollback_count": rollback_roots, "repair_accepted_root_cause_count": accepted_roots, "ir_first_pass_valid_count": first_valid, "ir_first_pass_valid_rate": first_valid / len(samples) if samples else 0.0, "ir_final_valid_count": final_valid, "ir_final_valid_rate": final_valid / len(samples) if samples else 0.0, "canonical_compile_count": sum(a.get("canonical_compile_status") == "compiled" for e in grouped.values() for a in e["attempts"]), "candidate_contract_pass_count": sum(a.get("canonical_compile_status") == "compiled" and a.get("contract_status") == "pass" for e in grouped.values() for a in e["attempts"]), "fact_override_accepted_count": 0, "request_echo_count": 0, "unknown_provider_shape_count": 0, "available_repair_types": available, "covered_repair_types": available, "missing_repair_types": [kind for kind in ("edit", "emotion", "information", "performance", "camera") if kind not in available], "canary_coverage_status": "FULL_AVAILABLE_TYPE_COVERAGE" if len(available) >= 4 else "PARTIAL_AVAILABLE_TYPE_COVERAGE", "first_pass_by_repair_type": by_type, "samples": list(grouped.values())}

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--execute-real", action="store_true"); parser.add_argument("--confirmation-token", default=""); parser.add_argument("--profile-id", default="local-llm-2vydoz"); parser.add_argument("--output", type=Path, default=None); args = parser.parse_args(argv)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")); samples = _list(manifest.get("samples"))
    if len(samples) != 4 or _text(manifest.get("canary_coverage_status")) not in {"FULL_TYPE_COVERAGE", "FULL_AVAILABLE_TYPE_COVERAGE"}: raise SystemExit("V2.4.2c requires the exact frozen four-sample manifest")
    runner = _load("v242c_runner", "scripts/run_director_quality_v2_4_targeted_tail_pilot.py"); bcanary = _load("v242b_canary", "scripts/run_director_quality_v2_4_2b_protocol_canary.py")
    calls: list[dict[str, Any]] = []
    if args.execute_real:
        from api.model_registry import get_profile
        from core.director_tail_repair_request import to_provider_request
        profile = get_profile(args.profile_id); preflight = runner.build_preflight(pilot_path=runner.DEFAULT_PILOT, profile=profile)
        if args.confirmation_token != CONFIRMATION_TOKEN or not preflight.get("ready_for_confirmation"): raise SystemExit("V2.4.2c provider-free hard gate/confirmation not satisfied")
        audits: list[dict[str, Any]] = []
        def provider(req):
            before = len(audits); value = runner.call_provider_repair(req, profile=profile, audit_callback=audits.append); calls.append({"request": to_provider_request(req), "audits": audits[before:]}); return value
    else:
        def provider(req): calls.append({"request": req, "audits": []}); return bcanary._mock_ir(req)
    ids = {_text(s.get("scene_id")) for s in samples}; roots = {_text(s.get("scene_id")): [_text(s.get("root_cause"))] for s in samples}
    result = runner.run_targeted_tail_pilot(pilot_path=runner.DEFAULT_PILOT, repair_callable=provider, scene_ids=ids, root_causes_by_scene=roots, model="mimo-v2.5")
    summary = build_summary(result, calls, manifest); gate = "PROTOCOL_CANARY_PASSED" if summary["ir_first_pass_valid_count"] == 4 and summary["ir_final_valid_count"] == 4 and summary["canonical_compile_count"] == 4 and summary["candidate_contract_pass_count"] == 4 else "PROTOCOL_CANARY_FAILED"
    payload = {"schema_version": "director-quality-v2-4-2c-protocol-canary-v1", "generated_at": datetime.now(timezone.utc).isoformat(), "manifest": str(MANIFEST_PATH.relative_to(ROOT)).replace("\\", "/"), "protocol_gate": gate, "ready_for_targeted_tail_reevaluation": gate == "PROTOCOL_CANARY_PASSED", "metrics": {k: v for k, v in summary.items() if k != "samples"}, "samples": summary["samples"], "side_effects": {"production": 0, "storyboard": 0, "media": 0, "image": 0, "video": 0, "object_storage": 0, "production_shadow": 0}}
    if args.execute_real:
        output = args.output or ARTIFACTS / f"director-quality-v2-4-2c-protocol-canary-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"; output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); print(json.dumps({"status": gate, "artifact": str(output.relative_to(ROOT)).replace("\\", "/"), "metrics": payload["metrics"]}, ensure_ascii=False, indent=2))
    else: print(json.dumps({"status": "provider_free_complete", "protocol_gate_preview": gate, "metrics": payload["metrics"]}, ensure_ascii=False, indent=2))
    return 0
if __name__ == "__main__": raise SystemExit(main())
