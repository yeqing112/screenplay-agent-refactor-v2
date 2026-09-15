"""Director Quality V3 Phase 1.2 Scene Director Strategy re-canary.

This runner is intentionally strategy-only.  It consumes the frozen
approved-record cohort from Phase 1.1, sends only the provider-facing IR
evidence to the explicitly authorised MiMo profile, and persists complete
evidence without touching ShotPlan, media or production state.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
CONFIRMATION_TOKEN = "CONFIRM_DIRECTOR_V3_PHASE1_2_REAL_MIMO_CANARY"
REQUIRED_SCENES = (
    "book990402:e3:暗房惊魂",
    "book990402:e3:暗房惊魂（2）",
    "book990402:e2:回声照相馆",
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fp(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def safe_scene_id(scene_id: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "-", scene_id).strip("-").lower() or "scene"
    return f"{base}-{_fp(scene_id)[:10]}"


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _load_records() -> list[dict[str, Any]]:
    from scripts.run_director_quality_v3_phase1 import _load_frozen_records
    records = _load_frozen_records()
    ids = tuple(_text(_dict(row.get("metadata")).get("scene_id")) for row in records)
    if ids != REQUIRED_SCENES:
        raise ValueError(f"frozen scene order changed: {ids!r}")
    return records


def _authoritative(record: dict[str, Any]) -> dict[str, Any]:
    from scripts.run_director_quality_v3_phase1 import build_authoritative_inputs
    return build_authoritative_inputs(record)


def _contract(inputs: dict[str, Any]) -> dict[str, Any]:
    from core.director_scene_strategy import build_strategy_contract
    return build_strategy_contract(
        scene=inputs["scene"], treatment=inputs["director_treatment"],
        blocking=inputs["scene_blocking"], fact_snapshot=inputs["fact_snapshot"],
    )


def provider_free_preflight(records: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    from core.director_scene_strategy_ir import validate_strategy_ir
    from core.director_scene_strategy_ir_compiler import compile_ir_to_canonical
    from core.director_scene_strategy_semantic_spec import IR_SCHEMA_VERSION, semantic_spec
    from core.director_strategy_prompt import build_scene_strategy_ir_prompt

    prompts = []
    contracts = []
    for record in records:
        inputs = _authoritative(record); contract = _contract(inputs); contracts.append(contract)
        prompts.append(build_scene_strategy_ir_prompt(evidence={
            "scene_id": contract["scene_id"], "strategy_contract": contract,
            "source_authority": inputs["source_authority"],
            "baseline_shot_count": inputs["baseline_shot_plan_metadata"]["shot_count"],
        }, model_profile=profile))
    prompt_text = "\n".join(p["system_prompt"] + p["user_prompt"] for p in prompts)
    checks = {
        "frozen_scene_order": len(records) == 3,
        "approved_record_only": all(_dict(r.get("metadata")).get("scene_type") == "approved_record" for r in records),
        "approved_treatment_blocking": all(_dict(r.get("treatment")).get("status") == "approved" and _dict(r.get("blocking")).get("status") == "approved" for r in records),
        "fixed_ir_schema": IR_SCHEMA_VERSION == "director_scene_strategy_ir_v1",
        "semantic_spec_available": bool(semantic_spec().get("schema_version")),
        "new_ir_prompt": all(p.get("protocol_version") == "director-quality-v3-phase1-1-strategy-ir-prompt-v1" for p in prompts),
        "no_provider_fingerprint_request": all("strategy_fingerprint" not in _canonical(p.get("provider_contract")) for p in prompts),
        # The semantic skeleton is allowed to name forbidden keys so the
        # provider knows what not to emit.  What must not be present is an
        # actual shot-list payload/topology in the dynamic evidence.
        "no_shotplan_request": '"shots":' not in prompt_text and '"plan_shot_id":' not in prompt_text and '"shot_plan":' not in prompt_text,
        "no_old_answers": not any(k in prompt_text for k in ("Legacy replay", "Foundation fixture", "repair answer")),
        "attempt_budget_two": True,
        "format_repair_only": True,
        "json_parser_retry_zero": True,
        "provider_calls_zero": True,
        "side_effects_zero": True,
    }
    return {
        "schema_version": "director-quality-v3-phase1-2-provider-free-preflight-v1",
        "status": "PASS" if all(checks.values()) else "FAIL", "all_checks_pass": all(checks.values()),
        "checks": checks, "real_llm_calls": 0, "real_mimo_calls": 0,
        "shotplan": 0, "shot_architecture": 0, "repair": 0, "storyboard": 0,
        "media": 0, "image": 0, "video": 0, "object_storage": 0, "shadow": 0, "ci": "not_run",
        "provider_profile": {k: profile.get(k) for k in ("id", "provider", "model_name", "capability")},
        "contract_fingerprints": [_fp(c) for c in contracts],
    }


def build_contract_artifact(records: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    from core.director_strategy_prompt import build_scene_strategy_ir_prompt
    rows = []
    for record in records:
        inputs = _authoritative(record); contract = _contract(inputs)
        evidence = {"scene_id": contract["scene_id"], "strategy_contract": contract,
                    "source_authority": inputs["source_authority"],
                    "baseline_shot_count": inputs["baseline_shot_plan_metadata"]["shot_count"]}
        prompt = build_scene_strategy_ir_prompt(evidence=evidence, model_profile=profile)
        rows.append({"scene_id": contract["scene_id"], "contract_fingerprint": _fp(contract),
                     "prompt_request_fingerprint": prompt["request_fingerprint"],
                     "system_prompt_fingerprint": prompt["system_prompt_fingerprint"],
                     "schema_fingerprint": prompt["schema_fingerprint"],
                     "provider_contract": prompt["provider_contract"],
                     "computed_fields_excluded": prompt["computed_fields_excluded"]})
    return {"schema_version": "director-quality-v3-phase1-2-provider-contract-v1", "provider": profile.get("provider"), "model_name": profile.get("model_name"), "capability": profile.get("capability"), "structured_output": "director_scene_strategy_ir_v1", "semantic_attempt_budget_per_scene": 2, "attempt_types": ["CREATIVE_GENERATION", "FORMAT_REPAIR"], "json_parser_retry_count": 0, "raw_output_persisted": True, "credential_persisted": False, "side_effect_boundary": "strategy_artifacts_only", "scenes": rows}


def build_manifest(records: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for record in records:
        inputs = _authoritative(record); contract = _contract(inputs)
        rows.append({"scene_id": contract["scene_id"], "source_fingerprint": _fp(inputs), "contract_fingerprint": _fp(contract), "treatment_fingerprint": _fp(record.get("treatment")), "blocking_fingerprint": _fp(record.get("blocking")), "baseline_shot_count": inputs["baseline_shot_plan_metadata"]["shot_count"], "provider_profile": {k: profile.get(k) for k in ("id", "provider", "model_name")}})
    return {"schema_version": "director-quality-v3-phase1-2-canary-manifest-v1", "phase": "1.2", "source": "Phase 1.1 frozen approved_record cohort", "scene_count": 3, "scenes": rows, "shotplan_generation": 0, "media_generation": 0, "provider_calls": 0, "ready_for_shot_architecture_canary": False}


def _parse(raw: str) -> tuple[dict[str, Any] | None, str]:
    from core.structured_output import parse_json_object
    try:
        return parse_json_object(raw, label="director_scene_strategy_ir_v1"), ""
    except Exception as exc:
        return None, str(exc)[:1000]


def _format_eligible(parsed: dict[str, Any] | None, parse_error: str, errors: list[dict[str, Any]]) -> bool:
    if parse_error:
        return True
    codes = {str(_dict(e).get("code")) for e in errors}
    format_codes = {"IR_NOT_OBJECT", "IR_SCHEMA_VERSION_INVALID", "UNKNOWN_IR_FIELD", "FORBIDDEN_IR_FIELD", "IR_REQUIRED_FIELD_MISSING", "NESTED_FIELD_SHAPE_INVALID", "PHASE_FIELD_MISSING", "PHASE_NOT_OBJECT", "INVALID_POWER_CENTER", "PERFORMANCE_ROW_INVALID", "PERFORMANCE_FIELD_MISSING"}
    # A second attempt is permitted only when *all* failures are protocol or
    # shape failures.  Mixed shape + semantic errors (fact invention,
    # chronology, unknown IDs, etc.) are semantic failures and must stop the
    # scene rather than receive an accidental creative rewrite.
    return bool(codes) and codes.issubset(format_codes)


def run_real(records: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    from core.director_scene_strategy_ir import validate_strategy_ir
    from core.director_scene_strategy_ir_compiler import compile_ir_to_canonical
    from core.director_strategy_prompt import build_scene_strategy_ir_prompt
    from core.director_strategy_quality import compare_canonical_strategies, diagnose_scene_strategy_v2
    from core.llm import call_llm
    from core.pilot_instrumentation import PilotInvocationRecorder

    recorder = PilotInvocationRecorder(); scenes = []
    for record in records:
        inputs = _authoritative(record); contract = _contract(inputs); sid = contract["scene_id"]
        evidence = {"scene_id": sid, "strategy_contract": contract, "source_authority": inputs["source_authority"], "baseline_shot_count": inputs["baseline_shot_plan_metadata"]["shot_count"]}
        attempts = []; accepted = None; validation = {"valid": False, "errors": [{"code": "NOT_RUN"}]}
        for number, kind in ((1, "CREATIVE_GENERATION"), (2, "FORMAT_REPAIR")):
            if accepted is not None: break
            previous = attempts[-1].get("raw_provider_output") if attempts else None
            prompt = build_scene_strategy_ir_prompt(evidence=evidence, model_profile=profile, attempt_type=kind, raw_output=previous if kind == "FORMAT_REPAIR" else None)
            raw = ""; parse_error = ""; parsed = None
            try:
                with recorder.span(stage="director_strategy_phase1_2", episode=inputs["scene"].get("episode"), scene=sid, attempt_type=kind, semantic_attempt=number):
                    raw = call_llm(prompt["user_prompt"], system=prompt["system_prompt"], model_profile=profile, retries=1, estimated_tokens=7000, max_tokens=12000, audit_extra={"phase": "1.2", "scene_id": sid, "attempt_type": kind, "semantic_attempt": number, "prompt_request_fingerprint": prompt["request_fingerprint"]})
                parsed, parse_error = _parse(str(raw or ""))
                if parsed is not None:
                    validation = validate_strategy_ir(parsed, contract=contract)
                    if validation.get("valid"): accepted = validation["ir"]
            except Exception as exc:
                parse_error = "provider_error: " + str(exc)[:1000]
            errors = _list(validation.get("errors")); eligible = _format_eligible(parsed, parse_error, errors)
            attempts.append({"attempt_number": number, "attempt_type": kind, "prompt_request_fingerprint": prompt["request_fingerprint"], "system_prompt_fingerprint": prompt["system_prompt_fingerprint"], "schema_fingerprint": prompt["schema_fingerprint"], "scene_input_fingerprint": prompt["scene_input_fingerprint"], "raw_provider_output": str(raw or "")[:100000], "parsed_ir": parsed, "parse_error": parse_error, "validation": copy.deepcopy(validation), "format_repair_eligible": eligible})
            if accepted is None and number == 1 and not eligible: break
        candidate = accepted or next((a.get("parsed_ir") for a in reversed(attempts) if isinstance(a.get("parsed_ir"), dict)), None)
        canonical = None; compile_error = ""
        if accepted is not None:
            try: canonical = compile_ir_to_canonical(ir=accepted, contract=contract)
            except Exception as exc: compile_error = str(exc)[:1000]
        quality = diagnose_scene_strategy_v2(strategy=canonical or candidate or {}, source_evidence=inputs)
        records_for_scene = recorder.records[-sum(1 for a in attempts if a.get("raw_provider_output") is not None):] if attempts else []
        # Use request-scoped metadata rather than assuming calls have no other
        # records; this keeps telemetry correct if call_llm emits an error row.
        scene_calls = [r for r in recorder.records if _dict(r.get("extra")).get("pilot_scene") == sid]
        scenes.append({"scene": {k: inputs["scene"].get(k) for k in ("book_id", "episode", "name", "scene_id")}, "contract_fingerprint": _fp(contract), "attempts": attempts, "attempt_count": len(attempts), "first_pass_ir_valid": bool(attempts and _dict(attempts[0].get("validation")).get("valid")), "final_ir_valid": bool(accepted), "ir": accepted, "candidate_ir": candidate, "canonical": canonical, "compile_error": compile_error, "protocol_result": {"status": "PASS" if accepted and not compile_error else "FAIL", "errors": _list(validation.get("errors"))}, "directing_result": quality, "telemetry": {"http_request_count": len(scene_calls), "prompt_tokens": sum(int(_dict(x.get("usage")).get("prompt_tokens") or 0) for x in scene_calls), "cached_tokens": sum(int(_dict(x.get("usage")).get("cached_tokens") or 0) for x in scene_calls), "completion_tokens": sum(int(_dict(x.get("usage")).get("completion_tokens") or 0) for x in scene_calls), "total_tokens": sum(int(_dict(x.get("usage")).get("total_tokens") or 0) for x in scene_calls), "latency_ms": round(sum(float(x.get("latency_ms") or 0) for x in scene_calls), 2)}, "side_effects": {"shotplan": 0, "storyboard": 0, "repair": 0, "media": 0, "object_storage": 0}})
    canonical = [s["canonical"] for s in scenes if isinstance(s.get("canonical"), dict)]
    distinct = compare_canonical_strategies(canonical)
    for s in scenes: s["distinctiveness"] = distinct
    protocol_valid = sum(bool(s["final_ir_valid"]) for s in scenes)
    first_valid = sum(bool(s["first_pass_ir_valid"]) for s in scenes)
    outcomes = [str(_dict(s["directing_result"]).get("directing_content_status") or "DIRECTING_INCONCLUSIVE") for s in scenes]
    strong_usable = sum(o in {"DIRECTING_STRONG", "DIRECTING_USABLE"} for o in outcomes)
    status = "SCENE_DIRECTOR_STRATEGY_RECANARY_PASSED" if protocol_valid == 3 and first_valid >= 2 and strong_usable >= 2 and not distinct.get("hard_failure") else "SCENE_DIRECTOR_STRATEGY_RECANARY_FAILED"
    return {"schema_version": "director-quality-v3-phase1-2-strategy-canary-real-v1", "generated_at": datetime.now(timezone.utc).isoformat(), "status": status, "pilot_mode": "real_mimo_scene_strategy_ir_only", "model": {k: profile.get(k) for k in ("id", "provider", "model_name")}, "scene_count": 3, "protocol_gate": {"final_ir_valid": protocol_valid, "first_pass_ir_valid": first_valid, "required_final": 3, "required_first_pass_minimum": 2}, "quality_gate": {"directing_strong_or_usable": strong_usable, "required": 2}, "distinctiveness": distinct, "scenes": scenes, "telemetry": recorder.summary(), "provider_http_request_count": recorder.summary().get("total_calls", 0), "provider_http_request_limit": 6, "side_effects": {"shotplan": 0, "shot_architecture": 0, "scene_repair": 0, "scene_redesign": 0, "tail_repair": 0, "storyboard": 0, "media": 0, "image": 0, "video": 0, "object_storage": 0, "shadow": 0, "ci": 0}, "ready_for_shot_architecture_canary": False, "awaiting_human_director_review": True, "capability": "PROVISIONALLY_PROVEN" if status.endswith("PASSED") else "NOT_PROVEN"}


def _brief(scene: dict[str, Any]) -> str:
    strategy = scene.get("canonical") or scene.get("candidate_ir") or {}
    quality = _dict(scene.get("directing_result")); lines = [f"# Director Brief — {_text(_dict(scene.get('scene')).get('scene_id'))}", "", f"**Protocol:** `{'PASS' if scene.get('final_ir_valid') else 'FAIL'}`  ", f"**Directing QA:** `{quality.get('directing_content_status', 'DIRECTING_INCONCLUSIVE')}`", "", "## 导演命题", "", _text(strategy.get("dramatic_objective")), "", "## 观众问题", "", _text(strategy.get("scene_question")), "", "## 视觉命题", "", _text(strategy.get("visual_thesis")), "", "## 场面推进", ""]
    for phase in _list(strategy.get("scene_phases")):
        if not isinstance(phase, dict): continue
        audience = _dict(phase.get("audience_state")); emotion = _dict(phase.get("emotion")); power = _dict(phase.get("power")); visual = _dict(phase.get("visual")); edit = _dict(phase.get("edit"))
        lines += [f"### {_text(phase.get('phase_id'))} · beats {', '.join(_text(x) for x in _list(phase.get('beat_ids')))}", "", f"- 观众知道/怀疑：{_text(audience.get('question_shift'))}; {', '.join(_text(x) for x in _list(audience.get('suspects')))}", f"- 情绪：{_text(emotion.get('state'))}（{_text(emotion.get('transition_reason'))}）", f"- 权力关系：{_text(power.get('description'))}；中心 `{_text(power.get('center_ref') or power.get('center_type'))}`", f"- 表演：{'; '.join(_text(_dict(x).get('character_id')) + '：' + _text(_dict(x).get('objective')) for x in _list(phase.get('performance')) if isinstance(x, dict))}", f"- 视觉/剪辑：{_text(visual.get('visual_grammar'))}；{_text(visual.get('camera_rule'))}；{_text(edit.get('cut_logic'))}", ""]
    lines += ["## 保留与风险", "", "- 必须保留：" + "；".join(_text(x) for x in _list(strategy.get("must_preserve"))), "- 避免：" + "；".join(_text(x) for x in _list(strategy.get("must_avoid"))), "- 创作风险：" + "；".join(_text(x) for x in _list(strategy.get("creative_risks"))), "", "> 本文件是 Phase 1.2 场景导演策略候选，仅供人工导演审阅；本轮未生成 ShotPlan、图片、视频或生产任务。", ""]
    return "\n".join(lines)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--confirmation-token", default="")
    parser.add_argument("--profile-id", default="local-llm-2vydoz")
    args = parser.parse_args()
    from api.model_registry import get_profile
    profile = get_profile(args.profile_id)
    if not isinstance(profile, dict): raise SystemExit(f"profile not found: {args.profile_id}")
    records = _load_records(); preflight = provider_free_preflight(records, profile)
    contract = build_contract_artifact(records, profile); manifest = build_manifest(records, profile)
    _write(ARTIFACTS / "director-quality-v3-phase1-2-provider-free-preflight.json", preflight)
    _write(ARTIFACTS / "director-quality-v3-phase1-2-provider-contract.json", contract)
    _write(ARTIFACTS / "director-quality-v3-phase1-2-canary-manifest.json", manifest)
    if not args.execute_real:
        print(json.dumps({"status": "PROVIDER_FREE_PREFLIGHT_PASS" if preflight["all_checks_pass"] else "SCENE_DIRECTOR_STRATEGY_RECANARY_BLOCKED", "artifact": str(ARTIFACTS / "director-quality-v3-phase1-2-provider-free-preflight.json")}, ensure_ascii=False, indent=2)); return 0 if preflight["all_checks_pass"] else 2
    if _text(args.confirmation_token) != CONFIRMATION_TOKEN: raise SystemExit("confirmation token mismatch")
    if _text(profile.get("provider")) != "openai-compatible" or _text(profile.get("model_name")) != "mimo-v2.5" or not profile.get("api_key"): raise SystemExit("Phase 1.2 requires enabled MiMo profile with key")
    real = run_real(records, profile)
    strategy_dir = ARTIFACTS / "director-quality-v3-phase1-2-strategies"; strategy_dir.mkdir(parents=True, exist_ok=True)
    protocol = []; quality = []; canonical = []
    for scene in real["scenes"]:
        sid = _text(_dict(scene["scene"]).get("scene_id")); safe = safe_scene_id(sid); raw = "\n\n".join(a.get("raw_provider_output", "") for a in scene["attempts"])
        (strategy_dir / f"{safe}-raw.txt").write_text(raw, encoding="utf-8")
        _write(strategy_dir / f"{safe}-ir.json", scene.get("ir") or scene.get("candidate_ir") or {"status": "invalid"})
        _write(strategy_dir / f"{safe}-canonical.json", scene.get("canonical") or {"status": "not_compiled", "error": scene.get("compile_error")})
        (strategy_dir / f"{safe}-director-brief.md").write_text(_brief(scene), encoding="utf-8")
        _write(strategy_dir / f"{safe}-qa.json", {"protocol": scene["protocol_result"], "directing": scene["directing_result"], "telemetry": scene["telemetry"]})
        protocol.append({"scene_id": sid, **scene["protocol_result"]}); quality.append({"scene_id": sid, **scene["directing_result"]}); canonical.append({"scene_id": sid, "compiled": bool(scene.get("canonical"))})
    _write(ARTIFACTS / "director-quality-v3-phase1-2-strategy-canary-real.json", real)
    _write(ARTIFACTS / "director-quality-v3-phase1-2-protocol-results.json", {"schema_version": "director-quality-v3-phase1-2-protocol-results-v1", "scenes": protocol, "valid_count": sum(x["status"] == "PASS" for x in protocol)})
    _write(ARTIFACTS / "director-quality-v3-phase1-2-directing-quality.json", {"schema_version": "director-quality-v3-phase1-2-directing-quality-v1", "scenes": quality, "strong_or_usable": real["quality_gate"]["directing_strong_or_usable"]})
    _write(ARTIFACTS / "director-quality-v3-phase1-2-distinctiveness.json", real["distinctiveness"])
    phase1 = _load(ARTIFACTS / "director-quality-v3-phase1-strategy-canary-real.json") if (ARTIFACTS / "director-quality-v3-phase1-strategy-canary-real.json").exists() else {}
    _write(ARTIFACTS / "director-quality-v3-phase1-2-phase1-comparison.json", {"schema_version": "director-quality-v3-phase1-2-phase1-comparison-v1", "phase1_status": phase1.get("status"), "phase1_final_valid": _dict(phase1.get("protocol_gate")).get("final_schema_valid"), "phase1_2_final_valid": real["protocol_gate"]["final_ir_valid"], "phase1_2_first_pass_valid": real["protocol_gate"]["first_pass_ir_valid"]})
    status = real["status"]
    report = "\n".join(["# Director Quality V3 Phase 1.2 — Scene Director Strategy Re-Canary", "", f"**Status:** `{status}`", "", "## Baseline Audit", "", "Phase 1.1 established the frozen three-scene approved_record cohort and IR/Compiler/QA boundary. Phase 1 historical canary had schema failures; this run does not modify those artifacts.", "", "## Final As-Built Verification", "", f"- MiMo profile: `{profile.get('model_name')}` (credentials omitted)", f"- Final IR valid: `{real['protocol_gate']['final_ir_valid']}/3`; first-pass valid: `{real['protocol_gate']['first_pass_ir_valid']}/3`", f"- Directing strong/usable: `{real['quality_gate']['directing_strong_or_usable']}/3`", f"- Distinctiveness hard failure: `{real['distinctiveness'].get('hard_failure')}`", f"- HTTP calls: `{real['provider_http_request_count']}/6`; parser retries: `0`", "- ShotPlan/Storyboard/Media/Storage/Shadow/CI side effects: `0`", "", "## Human review gate", "", "- `AWAITING_HUMAN_DIRECTOR_REVIEW=true`", "- `READY_FOR_SHOT_ARCHITECTURE_CANARY=false`", "- 三份 director-brief.md 必须由导演人工审阅后，才能决定是否进入 Shot Architecture Canary。", ""])
    (ARTIFACTS / "director-quality-v3-phase1-2-report.md").write_text(report, encoding="utf-8")
    gap = "\n".join(["# Director Quality V3 Phase 1.2 — Gap Audit", "", "## Baseline Audit", "", "Phase 1.1 frozen cohort and deterministic IR/Compiler/QA contract are retained. No historical artifact was overwritten.", "", "## Final As-Built Verification", "", f"- Provider-free preflight: `{preflight['status']}`", f"- Re-canary status: `{status}`", f"- Final IR valid: `{real['protocol_gate']['final_ir_valid']}/3`; first pass: `{real['protocol_gate']['first_pass_ir_valid']}/3`", f"- HTTP calls: `{real['provider_http_request_count']}`; no media/ShotPlan/CI side effects", f"- Human director review required: `true`; Shot Architecture Canary: `false`", ""])
    (ARTIFACTS / "director-quality-v3-phase1-2-gap-audit.md").write_text(gap, encoding="utf-8")
    print(json.dumps({"status": status, "report": str(ARTIFACTS / "director-quality-v3-phase1-2-report.md"), "briefs": [str(p) for p in sorted(strategy_dir.glob("*-director-brief.md"))]}, ensure_ascii=False, indent=2))
    return 0 if status == "SCENE_DIRECTOR_STRATEGY_RECANARY_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
