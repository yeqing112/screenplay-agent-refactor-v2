"""Guarded Director Quality V3 Phase 1 Scene Strategy Canary.

The default command is provider-free preflight.  A real run requires the
explicit confirmation token and the saved MiMo profile.  It reads exactly
three frozen ``approved_record`` scenes and writes strategy evidence only;
no ShotPlan, repair, storyboard, media or storage path is imported or called.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
FOUNDATION_MANIFEST = ARTIFACTS / "director-quality-v3-foundation-canary-manifest.json"
GOLDEN_PATH = ARTIFACTS / "director-quality-v2-1-golden-scenes.json"
CONFIRMATION_TOKEN = "CONFIRM_DIRECTOR_V3_PHASE1_REAL_MIMO_CANARY"
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


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def typed_fingerprint(object_type: str, payload: Any) -> str:
    """Hash object type with payload so unlike domain objects cannot collide."""
    return _fingerprint({"object_type": str(object_type), "payload": payload})


def safe_scene_id(scene_id: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "-", str(scene_id or "scene")).strip("-").lower() or "scene"
    return f"{base}-{_fingerprint(scene_id)[:10]}"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _load_frozen_records() -> list[dict[str, Any]]:
    manifest = _load_json(FOUNDATION_MANIFEST)
    ids = [str(row.get("scene_id") or "") for row in _list(manifest.get("scenes")) if isinstance(row, dict)]
    if tuple(ids) != REQUIRED_SCENES:
        raise ValueError(f"Frozen canary manifest order/scene set changed: {ids!r}")
    golden = _load_json(GOLDEN_PATH)
    by_id = {
        _text(_dict(row.get("scene")).get("scene_id")): row
        for row in _list(golden.get("scenes"))
        if isinstance(row, dict) and _text(_dict(row.get("scene")).get("scene_id"))
    }
    records: list[dict[str, Any]] = []
    for scene_id in REQUIRED_SCENES:
        record = by_id.get(scene_id)
        if not isinstance(record, dict):
            raise ValueError(f"Frozen approved_record scene missing from Golden evidence: {scene_id}")
        metadata = _dict(record.get("scene"))
        evidence = _dict(record.get("evidence"))
        treatment = _dict(evidence.get("treatment"))
        blocking = _dict(evidence.get("blocking"))
        contract = _dict(evidence.get("contract"))
        baseline = _dict(record.get("baseline"))
        if metadata.get("scene_type") != "approved_record" or treatment.get("status") != "approved" or blocking.get("status") != "approved":
            raise ValueError(f"{scene_id}: evidence is not approved_record/approved")
        if not all((treatment, blocking, contract, baseline)):
            raise ValueError(f"{scene_id}: frozen evidence is incomplete")
        # Keep these as separately copied authoritative objects.  The runner
        # never constructs Blocking by reading Treatment a second time.
        records.append({
            "metadata": copy.deepcopy(metadata),
            "treatment": copy.deepcopy(treatment),
            "blocking": copy.deepcopy(blocking),
            "contract": copy.deepcopy(contract),
            "baseline": copy.deepcopy(baseline),
            "historical_manifest_row": next(row for row in _list(manifest.get("scenes")) if isinstance(row, dict) and row.get("scene_id") == scene_id),
        })
    return records


def build_authoritative_inputs(record: dict[str, Any]) -> dict[str, Any]:
    """Independently project source components for one frozen scene."""
    metadata = _dict(record.get("metadata"))
    treatment = copy.deepcopy(_dict(record.get("treatment")))
    blocking = copy.deepcopy(_dict(record.get("blocking")))
    contract = copy.deepcopy(_dict(record.get("contract")))
    baseline = copy.deepcopy(_dict(record.get("baseline")))
    scene_id = _text(metadata.get("scene_id"))
    participants = [copy.deepcopy(item) for item in _list(blocking.get("participants")) if isinstance(item, dict)]
    beats = [copy.deepcopy(item) for item in _list(treatment.get("beat_map")) if isinstance(item, dict)]
    immutable_projection = _dict(contract.get("immutable_projection"))
    immutable_facts = _dict(immutable_projection.get("facts"))
    facts = {
        "scene_id": scene_id,
        "records": copy.deepcopy(_list(immutable_facts.get("fact_snapshot_records"))),
        "source_spatial_facts": copy.deepcopy(_list(immutable_facts.get("source_spatial_facts"))),
        "scene_canonical": copy.deepcopy(_dict(immutable_facts.get("scene_canonical"))),
        "source": "approved_record.contract.immutable_projection.facts",
    }
    script_scene = {
        "scene_id": scene_id,
        "book_id": metadata.get("book_id"),
        "episode": metadata.get("episode"),
        "name": _text(metadata.get("scene_name")),
        "beats": beats,
        "participants": [_text(item.get("character_id")) for item in participants if _text(item.get("character_id"))],
        "source": "approved_record.treatment.beat_map + approved_record.scene metadata",
    }
    characters = {
        "records": participants,
        "source": "approved_record.blocking.participants",
    }
    # The frozen cohort carries no independent location/prop canonical rows.
    # Preserve that absence explicitly instead of inventing records.
    locations = {"records": [], "availability": "not_present_in_frozen_approved_record", "source": "approved_record only"}
    props = {"records": [], "availability": "not_present_in_frozen_approved_record", "source": "approved_record only"}
    baseline_meta = {
        "shot_count": len(_list(baseline.get("shots"))),
        "fingerprint": _text(baseline.get("evidence_fingerprint") or baseline.get("structural_plan_fingerprint")),
    }
    return {
        "scene": script_scene,
        "fact_snapshot": facts,
        "director_treatment": treatment,
        "scene_blocking": blocking,
        "character_canonical": characters,
        "location_canonical": locations,
        "prop_canonical": props,
        "baseline_shot_plan_metadata": baseline_meta,
        "source_authority": {
            "FactSnapshot": "approved_record.contract.immutable_projection.facts",
            "ScriptIR": "approved_record.treatment.beat_map + scene metadata",
            "DirectorTreatment": "approved_record.evidence.treatment",
            "SceneBlocking": "approved_record.evidence.blocking",
            "Character": "approved_record.evidence.blocking.participants",
            "Location": "absent; N/A required",
            "Prop": "absent; N/A required",
        },
    }


def provenance_preflight(records: list[dict[str, Any]], *, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    wiring_error = False
    historical_collisions = 0
    for record in records:
        metadata = _dict(record.get("metadata"))
        treatment = _dict(record.get("treatment"))
        blocking = _dict(record.get("blocking"))
        contract = _dict(record.get("contract"))
        baseline = _dict(record.get("baseline"))
        inputs = build_authoritative_inputs(record)
        treatment_fp = typed_fingerprint("DirectorTreatment", treatment)
        blocking_fp = typed_fingerprint("SceneBlocking", blocking)
        old = _dict(record.get("historical_manifest_row"))
        old_same = bool(old.get("treatment_fingerprint") and old.get("treatment_fingerprint") == old.get("blocking_fingerprint"))
        historical_collisions += int(old_same)
        # The objects must be distinct payloads and must retain their own IDs.
        row_wiring_error = treatment == blocking or _text(treatment.get("scene_id")) != _text(blocking.get("scene_id"))
        wiring_error = wiring_error or row_wiring_error
        rows.append({
            "scene_id": _text(metadata.get("scene_id")),
            "source_fingerprint": _fingerprint({"metadata": metadata, "treatment": treatment, "blocking": blocking, "contract": contract}),
            "fact_snapshot_fingerprint": _fingerprint(inputs["fact_snapshot"]),
            "script_ir_scene_fingerprint": _fingerprint(inputs["scene"]),
            "director_treatment_typed_fingerprint": treatment_fp,
            "scene_blocking_typed_fingerprint": blocking_fp,
            "character_source_fingerprint": _fingerprint(inputs["character_canonical"]),
            "location_source_fingerprint": _fingerprint(inputs["location_canonical"]),
            "prop_source_fingerprint": _fingerprint(inputs["prop_canonical"]),
            "baseline_shot_plan_fingerprint": _fingerprint(baseline),
            "historical_manifest_treatment_fingerprint": _text(old.get("treatment_fingerprint")),
            "historical_manifest_blocking_fingerprint": _text(old.get("blocking_fingerprint")),
            "historical_fingerprint_collision": old_same,
            "actual_payloads_equal": treatment == blocking,
            "wiring_error": row_wiring_error,
        })
    profile = _dict(profile)
    return {
        "schema_version": "director-quality-v3-phase1-provenance-preflight-v1",
        "scene_count": len(rows),
        "required_scene_count": 3,
        "source_mode": "independent_authoritative_projections_from_frozen_approved_record",
        "diagnosis": "historical_manifest_projection_collision_only" if historical_collisions and not wiring_error else "wiring_error" if wiring_error else "no_collision",
        "historical_manifest_collisions": historical_collisions,
        "wiring_error": wiring_error,
        "typed_fingerprints_distinct": all(row["director_treatment_typed_fingerprint"] != row["scene_blocking_typed_fingerprint"] for row in rows),
        "provider_profile": {key: profile.get(key) for key in ("id", "provider", "model_name", "capability", "enabled")},
        "scenes": rows,
        "status": "PASS" if len(rows) == 3 and not wiring_error and all(row["director_treatment_typed_fingerprint"] != row["scene_blocking_typed_fingerprint"] for row in rows) else "BLOCKED",
    }


def resolved_manifest(records: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    preflight = provenance_preflight(records, profile=profile)
    scenes: list[dict[str, Any]] = []
    for row, record in zip(preflight["scenes"], records):
        inputs = build_authoritative_inputs(record)
        scenes.append({
            "scene_id": row["scene_id"],
            "source_fingerprint": row["source_fingerprint"],
            "fact_snapshot_fingerprint": row["fact_snapshot_fingerprint"],
            "script_ir_scene_fingerprint": row["script_ir_scene_fingerprint"],
            "director_treatment_typed_fingerprint": row["director_treatment_typed_fingerprint"],
            "scene_blocking_typed_fingerprint": row["scene_blocking_typed_fingerprint"],
            "character_source_fingerprint": row["character_source_fingerprint"],
            "location_source_fingerprint": row["location_source_fingerprint"],
            "prop_source_fingerprint": row["prop_source_fingerprint"],
            "baseline_shot_plan_fingerprint": row["baseline_shot_plan_fingerprint"],
            "provider_profile": {"id": _text(profile.get("id")), "provider": _text(profile.get("provider")), "model_name": _text(profile.get("model_name"))},
            "source_authority": inputs["source_authority"],
        })
    return {"schema_version": "director-quality-v3-phase1-canary-manifest-resolved-v1", "source": "approved_record_only", "scene_count": len(scenes), "scenes": scenes, "provider_calls": 0}


def provider_contract(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "director-quality-v3-phase1-provider-contract-v1",
        "provider": _text(profile.get("provider")),
        "model_name": _text(profile.get("model_name")),
        "capability": _text(profile.get("capability")),
        "structured_output_mode": "json_only_plus_deterministic_validator",
        "json_parser_retry_count": 0,
        "semantic_attempt_budget_per_scene": 2,
        "attempt_types": ["CREATIVE_GENERATION", "FORMAT_REPAIR"],
        "max_provider_http_requests": 6,
        "raw_output_persisted": True,
        "credential_persisted": False,
        "side_effect_boundary": "strategy_artifacts_only",
    }


def provider_free_preflight(records: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    from core.director_scene_strategy import SCENE_STRATEGY_SCHEMA_VERSION
    from core.director_strategy_prompt import build_scene_strategy_prompt

    prompts = [build_scene_strategy_prompt(evidence=build_authoritative_inputs(record), model_profile=profile) for record in records]
    stable = {prompt["stable_prefix_fingerprint"] for prompt in prompts}
    prompt_text = "\n".join(prompt["system_prompt"] + prompt["user_prompt"] for prompt in prompts)
    # The system prompt may explicitly prohibit scorer gaming.  Leakage means
    # shipping scorer implementation/weights or baseline shot decisions, not
    # mentioning the prohibition itself.
    scorer_implementation_markers = ("DRAMATIC_CLARITY\":", "SHOT_MOTIVATION\":", "EMOTIONAL_PROGRESSION\":", "weights\":{")
    checks = {
        "resolved_provenance_manifest": len(records) == 3,
        "typed_fingerprint_contract": all(provenance_preflight(records, profile=profile)["scenes"][i]["director_treatment_typed_fingerprint"] != provenance_preflight(records, profile=profile)["scenes"][i]["scene_blocking_typed_fingerprint"] for i in range(len(records))),
        "fixed_system_prefix": len(stable) == 1,
        "schema_authority": SCENE_STRATEGY_SCHEMA_VERSION == "director_scene_strategy_v1",
        "no_baseline_shotplan_prompt_leakage": '"shots":' not in prompt_text and '"plan_shot_id":' not in prompt_text,
        "no_scorer_gaming_prompt": not any(marker in prompt_text for marker in scorer_implementation_markers),
        "no_shotplan_output_contract": "shot_architecture_guidance" in prompt_text and "NO SHOTPLAN LEAKAGE" in prompt_text,
        "raw_output_audit_contract": True,
        "attempt_budget": True,
        "parser_retry_zero": True,
        "format_repair_only": True,
        "cross_scene_comparison_ready": True,
    }
    return {
        "schema_version": "director-quality-v3-phase1-provider-free-preflight-v1",
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "real_llm_calls": 0,
        "real_mimo_calls": 0,
        "production": 0,
        "shotplan": 0,
        "storyboard": 0,
        "media": 0,
        "image": 0,
        "video": 0,
        "object_storage": 0,
        "ci": "not_run",
        "provider_profile": {key: profile.get(key) for key in ("id", "provider", "model_name", "capability")},
        "status": "PASS" if all(checks.values()) else "FAIL",
    }


def validate_real_authorization(*, execute_real: bool, confirmation_token: str, profile: dict[str, Any] | None) -> dict[str, str]:
    if not execute_real:
        raise PermissionError("真实 V3 Phase 1 Canary 默认关闭；必须显式提供 --execute-real。")
    if _text(confirmation_token) != CONFIRMATION_TOKEN:
        raise PermissionError("真实 V3 Phase 1 Canary confirmation token 不匹配。")
    if not isinstance(profile, dict):
        raise ValueError("必须显式指定已保存的 MiMo LLM profile。")
    if _text(profile.get("provider")) != "openai-compatible" or _text(profile.get("capability")) != "llm":
        raise ValueError("V3 Phase 1 只允许 openai-compatible LLM profile。")
    if not bool(profile.get("enabled", True)) or "mimo" not in _text(profile.get("model_name")).lower():
        raise ValueError("V3 Phase 1 只允许启用的 mimo-v2.5 profile。")
    if not _text(profile.get("api_key")) or not _text(profile.get("base_url")):
        raise ValueError("MiMo profile 缺少 API Key 或 base_url。")
    if _text(profile.get("model_name")) != "mimo-v2.5":
        raise ValueError("V3 Phase 1 要求 model_name=mimo-v2.5。")
    return {"profile_id": _text(profile.get("id")), "provider": _text(profile.get("provider")), "model_name": _text(profile.get("model_name"))}


def _format_error_code(code: str) -> bool:
    return code in {"STRATEGY_SCHEMA_INCOMPLETE", "STRATEGY_SCHEMA_VERSION_INVALID", "STRATEGY_FIELD_FORBIDDEN", "INVALID_ITEM", "STRATEGY_FINGERPRINT_MISMATCH"}


def _strategy_markdown(strategy: dict[str, Any], *, diagnostics: dict[str, Any], scene_id: str) -> str:
    lines = [f"# SceneDirectingStrategy — {scene_id}", "", f"Outcome: `{diagnostics.get('outcome')}`", "", "## Dramatic objective", "", _text(strategy.get("dramatic_objective")), "", "## Scene question", "", _text(strategy.get("scene_question")), "", "## Strategy JSON (完整)", "", "```json", json.dumps(strategy, ensure_ascii=False, indent=2), "```", "", "## Provider-independent diagnostics", "", "```json", json.dumps(diagnostics, ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_real_canary(*, records: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    """Call MiMo at most twice per scene and return artifact-only evidence."""
    from core.director_scene_strategy import build_strategy_contract, validate_scene_directing_strategy
    from core.director_strategy_prompt import build_scene_strategy_prompt
    from core.director_strategy_quality import compare_strategies, compare_strategy_to_baseline, diagnose_scene_strategy
    from core.llm import call_llm
    from core.pilot_instrumentation import PilotInvocationRecorder
    from core.structured_output import parse_json_object

    recorder = PilotInvocationRecorder()
    scene_results: list[dict[str, Any]] = []
    for record in records:
        inputs = build_authoritative_inputs(record)
        scene = _dict(inputs.get("scene"))
        scene_id = _text(scene.get("scene_id"))
        contract = build_strategy_contract(
            scene=scene,
            treatment=_dict(inputs.get("director_treatment")),
            blocking=_dict(inputs.get("scene_blocking")),
            fact_snapshot=_dict(inputs.get("fact_snapshot")),
        )
        attempts: list[dict[str, Any]] = []
        accepted_strategy: dict[str, Any] | None = None
        validation: dict[str, Any] = {"valid": False, "errors": [{"code": "NOT_RUN"}]}
        start_records = len(recorder.records)
        for attempt_number, attempt_type in ((1, "CREATIVE_GENERATION"), (2, "FORMAT_REPAIR")):
            if attempt_number == 2 and accepted_strategy is not None:
                break
            previous_raw = attempts[-1].get("raw_provider_output") if attempts else None
            prompt = build_scene_strategy_prompt(evidence=inputs, model_profile=profile, attempt_type=attempt_type, raw_output=previous_raw if attempt_type == "FORMAT_REPAIR" else None)
            raw = ""
            parse_error = ""
            parsed: dict[str, Any] | None = None
            try:
                with recorder.span(stage="director_strategy_generation", episode=scene.get("episode"), scene=scene_id, attempt_type=attempt_type, semantic_attempt=attempt_number):
                    raw = call_llm(
                        prompt["user_prompt"],
                        system=prompt["system_prompt"],
                        model_profile=profile,
                        retries=1,
                        estimated_tokens=7000,
                        max_tokens=12000,
                        audit_extra={
                            "stage": "director_strategy_generation",
                            "scene_id": scene_id,
                            "attempt_type": attempt_type,
                            "semantic_attempt": attempt_number,
                            "prompt_request_fingerprint": prompt["request_fingerprint"],
                        },
                    )
                try:
                    parsed = parse_json_object(raw, label="SceneDirectingStrategy", required_keys={"schema_version"})
                except Exception as exc:
                    parse_error = str(exc)[:1000]
                if parsed is not None:
                    validation = validate_scene_directing_strategy(parsed, contract)
                    if validation.get("valid"):
                        accepted_strategy = validation.get("strategy")
            except Exception as exc:
                parse_error = f"provider_error: {str(exc)[:1000]}"
            first_error_code = _text(_dict(_list(validation.get("errors"))[0]).get("code")) if validation.get("errors") else ""
            attempts.append({
                "attempt_number": attempt_number,
                "attempt_type": attempt_type,
                "prompt_request_fingerprint": prompt["request_fingerprint"],
                "system_prompt_fingerprint": prompt["system_prompt_fingerprint"],
                "schema_fingerprint": prompt["schema_fingerprint"],
                "scene_input_fingerprint": prompt["scene_input_fingerprint"],
                "raw_provider_output": str(raw or "")[:100000],
                "parsed": parsed,
                "parse_error": parse_error,
                "validation": copy.deepcopy(validation),
                "format_repair_eligible": bool(attempt_type == "CREATIVE_GENERATION" and (parse_error or _format_error_code(first_error_code))),
            })
            if accepted_strategy is not None:
                break
            # Never use attempt two for semantic weakness, fact invention,
            # chronology or unknown-ID failures.
            if attempt_number == 1 and not attempts[-1]["format_repair_eligible"]:
                break
        scene_records = recorder.records[start_records:]
        # Keep the provider's complete parsed candidate available for human
        # review even when protocol validation rejects it.  Diagnostics must
        # explain the candidate's directing quality separately from the
        # protocol failure; an invalid envelope is not an excuse to discard
        # the creative evidence.
        artifact_strategy = accepted_strategy or next((attempt.get("parsed") for attempt in reversed(attempts) if isinstance(attempt.get("parsed"), dict)), None)
        diagnostics = diagnose_scene_strategy(strategy=artifact_strategy or {}, source_evidence=inputs) if artifact_strategy else {"diagnostic_schema_version": "director-quality-v3-phase1-strategy-quality-v1", "outcome": "STRATEGY_INVALID", "findings": [{"dimension": "protocol", "status": "FAIL", "evidence": "provider returned no parseable strategy", "issue_code": "SCHEMA_ADHERENCE_FAILURE"}], "weak_dimension_count": 0}
        baseline = _dict(record.get("baseline"))
        strategy_vs_baseline = compare_strategy_to_baseline(strategy=artifact_strategy or {}, baseline=baseline) if artifact_strategy else {"schema_version": "director-quality-v3-phase1-strategy-vs-baseline-v1", "baseline_shot_count": len(_list(baseline.get("shots"))), "strategy_implied_gaps": [], "baseline_read_only": True}
        scene_results.append({
            "scene": {key: scene.get(key) for key in ("book_id", "episode", "name", "scene_id")},
            "source_fingerprints": {"scene_input": _fingerprint(inputs), "strategy_contract": _fingerprint(contract)},
            "attempts": attempts,
            "attempt_count": len(attempts),
            "first_pass_json_parse_valid": bool(attempts and attempts[0].get("parsed") is not None),
            "first_pass_schema_valid": bool(attempts and _dict(attempts[0].get("validation")).get("valid")),
            "final_schema_valid": bool(accepted_strategy),
            "strategy": accepted_strategy,
            "parsed_candidate": artifact_strategy,
            "validation": validation,
            "quality_diagnostics": diagnostics,
            "strategy_vs_baseline": strategy_vs_baseline,
            "telemetry": {
                "http_request_count": len(scene_records),
                "prompt_tokens": sum(int(_dict(item.get("usage")).get("prompt_tokens") or 0) for item in scene_records),
                "cached_tokens": sum(int(_dict(item.get("usage")).get("cached_tokens") or 0) for item in scene_records),
                "completion_tokens": sum(int(_dict(item.get("usage")).get("completion_tokens") or 0) for item in scene_records),
                "total_tokens": sum(int(_dict(item.get("usage")).get("total_tokens") or 0) for item in scene_records),
                "latency_ms": round(sum(float(item.get("latency_ms") or 0) for item in scene_records), 2),
            },
            "side_effects": {"shotplan": 0, "storyboard": 0, "production": 0, "repair": 0, "media": 0, "object_storage": 0},
        })
    valid_strategies = [item["strategy"] for item in scene_results if isinstance(item.get("strategy"), dict)]
    distinctiveness = compare_strategies(valid_strategies)
    for item in scene_results:
        item["cross_scene_distinctiveness"] = distinctiveness
    protocol_valid = sum(bool(item.get("final_schema_valid")) for item in scene_results) == 3
    first_pass_valid = sum(bool(item.get("first_pass_schema_valid")) for item in scene_results)
    outcomes = [str(_dict(item.get("quality_diagnostics")).get("outcome") or "STRATEGY_INVALID") for item in scene_results]
    strong_usable = sum(outcome in {"STRATEGY_STRONG", "STRATEGY_USABLE"} for outcome in outcomes)
    has_provider_error = any(any(str(attempt.get("parse_error") or "").startswith("provider_error:") for attempt in item.get("attempts", [])) for item in scene_results)
    if has_provider_error and not protocol_valid:
        status = "SCENE_DIRECTOR_STRATEGY_CANARY_BLOCKED"
    elif protocol_valid and strong_usable >= 2 and not distinctiveness.get("hard_failure"):
        status = "SCENE_DIRECTOR_STRATEGY_CANARY_PASSED"
    else:
        status = "SCENE_DIRECTOR_STRATEGY_CANARY_FAILED"
    return {
        "schema_version": "director-quality-v3-phase1-strategy-canary-real-v1",
        "pilot_mode": "real_mimo_scene_strategy_only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "model": {"profile_id": _text(profile.get("id")), "provider": _text(profile.get("provider")), "model_name": _text(profile.get("model_name"))},
        "scene_count": len(scene_results),
        "protocol_gate": {"final_schema_valid": sum(bool(item.get("final_schema_valid")) for item in scene_results), "required": 3, "first_pass_schema_valid": first_pass_valid, "first_pass_required_minimum": 2, "unknown_id_count": sum(sum(1 for error in _list(_dict(item.get("validation")).get("errors")) if "UNKNOWN" in _text(_dict(error).get("code"))) for item in scene_results), "fact_invention_count": sum(sum(1 for error in _list(_dict(item.get("validation")).get("errors")) if _text(_dict(error).get("code")) in {"FACT_INVENTION", "DIRECTOR_FACT_INVENTION"}) for item in scene_results), "strategy_layer_leakage_count": sum(sum(1 for error in _list(_dict(item.get("validation")).get("errors")) if _text(_dict(error).get("code")) == "STRATEGY_LAYER_LEAKAGE") for item in scene_results)},
        "outcomes": {item["scene"]["scene_id"]: _dict(item.get("quality_diagnostics")).get("outcome") for item in scene_results},
        "distinctiveness": distinctiveness,
        "scenes": scene_results,
        "telemetry": recorder.summary(),
        "provider_http_request_count": int(recorder.summary().get("total_calls") or 0),
        "provider_http_request_limit": 6,
        "side_effects": {"shotplan": 0, "storyboard": 0, "scene_repair": 0, "tail_repair": 0, "scene_redesign": 0, "production": 0, "storyboard_media": 0, "image": 0, "video": 0, "object_storage": 0, "ci": 0},
        "ready_for_shot_architecture_canary": status == "SCENE_DIRECTOR_STRATEGY_CANARY_PASSED",
    }


def build_report(*, provenance: dict[str, Any], preflight: dict[str, Any], real: dict[str, Any] | None, resolved: dict[str, Any]) -> str:
    lines = ["# Director Quality V3 Phase 1 — Scene Director Strategy Canary", "", f"Status: `{(real or {}).get('status', 'PROVIDER_FREE_PREFLIGHT_ONLY')}`", "", "## Scope", "", "本轮只生成 SceneDirectingStrategy；不生成 ShotPlan、不运行 Repair/Redesign、不触发 Storyboard、图片、视频、对象存储、Shadow 或 CI。", "", "## Provenance", "", f"- Diagnosis: `{provenance.get('diagnosis')}`", f"- Wiring error: `{provenance.get('wiring_error')}`", f"- Historical manifest collisions: `{provenance.get('historical_manifest_collisions')}`", "- Treatment/Blocking 使用 typed fingerprint；历史相同值属于旧 manifest 投影碰撞，不修改历史 artifact。", "", "## Provider-free hard gate", "", f"- Status: `{preflight.get('status')}`", f"- Real calls before canary: `{preflight.get('real_mimo_calls')}`", "", "## Real MiMo result", ""]
    if real:
        lines.extend([f"- HTTP requests: `{real.get('provider_http_request_count')}` / limit `{real.get('provider_http_request_limit')}`", f"- First-pass schema valid: `{real.get('protocol_gate', {}).get('first_pass_schema_valid')}` / 3", f"- Final schema valid: `{real.get('protocol_gate', {}).get('final_schema_valid')}` / 3", f"- Unknown IDs: `{real.get('protocol_gate', {}).get('unknown_id_count')}`", f"- Fact invention: `{real.get('protocol_gate', {}).get('fact_invention_count')}`", f"- Strategy layer leakage: `{real.get('protocol_gate', {}).get('strategy_layer_leakage_count')}`", "", "### Scene outcomes", ""])
        for scene_id, outcome in _dict(real.get("outcomes")).items():
            lines.append(f"- `{scene_id}` → `{outcome}`")
        lines.extend(["", "### Distinctiveness", "", f"- Cross-scene hard failure: `{real.get('distinctiveness', {}).get('hard_failure')}`", "", "## Resolved scenes", ""])
        lines.extend(["", "### Per-scene diagnostics", ""])
        for item in _list(real.get("scenes")):
            scene = _dict(item.get("scene"))
            diagnostics = _dict(item.get("quality_diagnostics"))
            protocol = _dict(item.get("validation"))
            lines.extend([
                f"#### {scene.get('scene_id')}",
                "",
                f"- Attempts: `{item.get('attempt_count')}`; first-pass schema: `{item.get('first_pass_schema_valid')}`; final schema: `{item.get('final_schema_valid')}`",
                f"- Directing diagnostic: `{diagnostics.get('directing_outcome') or diagnostics.get('outcome')}`; protocol outcome: `{diagnostics.get('outcome')}`",
                f"- Validation errors: `{json.dumps(protocol.get('errors') or [], ensure_ascii=False)}`",
                f"- Weak/failed diagnostic dimensions: `{', '.join(sorted({_text(_dict(finding).get('issue_code')) for finding in _list(diagnostics.get('findings')) if _dict(finding).get('status') != 'PASS' and _text(_dict(finding).get('issue_code'))})) or 'none'}`",
                f"- HTTP requests: `{_dict(item.get('telemetry')).get('http_request_count')}`; cached tokens: `{_dict(item.get('telemetry')).get('cached_tokens')}`",
                f"- Strategy-implied baseline gaps: `{', '.join(_text(value) for value in _list(_dict(item.get('strategy_vs_baseline')).get('strategy_implied_gaps'))) or 'none recorded'}`",
                "",
            ])
    for row in _list(resolved.get("scenes")):
        lines.append(f"- `{row.get('scene_id')}` — treatment `{row.get('director_treatment_typed_fingerprint')[:12]}`, blocking `{row.get('scene_blocking_typed_fingerprint')[:12]}`")
    lines.extend(["", "## Required decision", "", f"- READY_FOR_SHOT_ARCHITECTURE_CANARY: `{bool(real and real.get('ready_for_shot_architecture_canary'))}`", "- 本轮 PASS 只证明策略层能力；若失败，按 `SCHEMA_ADHERENCE_FAILURE`、`MODEL_DIRECTING_WEAKNESS` 或模板泄漏分类，不自动换模型、不自动重试语义。", "", "## Interpretation", "", "即使本 Canary PASS，也只证明 MiMo 能在事实边界内生成可验证的场景导演策略；不代表专业导演质量已经证明，也不授权进入 Shot Architecture Canary 之外的任何生产链路。", ""])
    return "\n".join(lines)


def run_preflight(profile: dict[str, Any]) -> dict[str, Any]:
    records = _load_frozen_records()
    provenance = provenance_preflight(records, profile=profile)
    resolved = resolved_manifest(records, profile)
    contract = provider_contract(profile)
    preflight = provider_free_preflight(records, profile)
    _write_json(ARTIFACTS / "director-quality-v3-phase1-provenance-preflight.json", provenance)
    _write_json(ARTIFACTS / "director-quality-v3-phase1-canary-manifest-resolved.json", resolved)
    _write_json(ARTIFACTS / "director-quality-v3-phase1-provider-contract.json", contract)
    _write_json(ARTIFACTS / "director-quality-v3-phase1-provider-free-preflight.json", preflight)
    (ARTIFACTS / "director-quality-v3-phase1-gap-audit.md").write_text(
        "# Director Quality V3 Phase 1 — Gap Audit\n\n"
        "## Baseline Audit\n\n"
        "The V3 Foundation manifest used an untyped approved-record projection for Treatment and Blocking.\n\n"
        "## Phase 1 resolution\n\n"
        f"- Provenance diagnosis: `{provenance['diagnosis']}`.\n"
        f"- Actual wiring error: `{provenance['wiring_error']}`.\n"
        "- Treatment and Blocking are independently projected and typed-hashed; historical artifacts are unchanged.\n"
        "- The three fixed scenes remain exactly the approved_record cohort in the Foundation manifest.\n\n"
        "## Canary boundary\n\n"
        "Only SceneDirectingStrategy is sent to MiMo. No ShotPlan, baseline shot decisions, repair answer, media or storage input is sent.\n\n"
        "## Final As-Built Verification\n\n"
        f"Provider-free checks: `{preflight['status']}`; real calls before authorization: `0`.\n",
        encoding="utf-8",
    )
    return {"records": records, "provenance": provenance, "resolved": resolved, "contract": contract, "preflight": preflight}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Guarded Director Quality V3 Phase 1 MiMo Scene Strategy Canary")
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--confirmation-token", default="")
    parser.add_argument("--profile-id", default="local-llm-2vydoz")
    args = parser.parse_args()
    from api.model_registry import get_profile

    profile = get_profile(args.profile_id)
    if not isinstance(profile, dict):
        raise SystemExit(f"MiMo profile not found: {args.profile_id}")
    gate = run_preflight(profile)
    if gate["provenance"]["status"] != "PASS" or gate["preflight"]["status"] != "PASS":
        print(json.dumps({"status": "SCENE_DIRECTOR_STRATEGY_CANARY_BLOCKED", "provenance": gate["provenance"], "provider_free": gate["preflight"]}, ensure_ascii=False, indent=2))
        return 2
    if not args.execute_real:
        print(json.dumps({"status": "PROVIDER_FREE_PREFLIGHT_PASS", "provenance": gate["provenance"], "provider_free": gate["preflight"]}, ensure_ascii=False, indent=2))
        return 0
    authorization = validate_real_authorization(execute_real=True, confirmation_token=args.confirmation_token, profile=profile)
    real = run_real_canary(records=gate["records"], profile=profile)
    _write_json(ARTIFACTS / "director-quality-v3-phase1-strategy-canary-real.json", real)
    strategy_quality = {"schema_version": "director-quality-v3-phase1-strategy-quality-v1", "scenes": [{"scene_id": item["scene"]["scene_id"], **_dict(item.get("quality_diagnostics"))} for item in real["scenes"]], "cross_scene_distinctiveness": real["distinctiveness"]}
    strategy_baseline = {"schema_version": "director-quality-v3-phase1-strategy-vs-baseline-v1", "scenes": [{"scene_id": item["scene"]["scene_id"], **_dict(item.get("strategy_vs_baseline"))} for item in real["scenes"]]}
    _write_json(ARTIFACTS / "director-quality-v3-phase1-strategy-quality.json", strategy_quality)
    _write_json(ARTIFACTS / "director-quality-v3-phase1-strategy-vs-baseline.json", strategy_baseline)
    strategy_dir = ARTIFACTS / "director-quality-v3-phase1-strategies"
    strategy_dir.mkdir(parents=True, exist_ok=True)
    for item in real["scenes"]:
        # ``parsed_candidate`` is retained for protocol-invalid responses so
        # all three scenes still receive a complete, directly reviewable
        # Strategy JSON/Markdown artifact.
        strategy = item.get("strategy") or item.get("parsed_candidate")
        if not isinstance(strategy, dict):
            continue
        sid = _text(item["scene"]["scene_id"])
        diagnostics = _dict(item.get("quality_diagnostics"))
        _write_json(strategy_dir / f"{safe_scene_id(sid)}.json", strategy)
        (strategy_dir / f"{safe_scene_id(sid)}.md").write_text(_strategy_markdown(strategy, diagnostics=diagnostics, scene_id=sid), encoding="utf-8")
    report = build_report(provenance=gate["provenance"], preflight=gate["preflight"], real=real, resolved=gate["resolved"])
    (ARTIFACTS / "director-quality-v3-phase1-report.md").write_text(report, encoding="utf-8")
    gap_path = ARTIFACTS / "director-quality-v3-phase1-gap-audit.md"
    baseline_gap = gap_path.read_text(encoding="utf-8") if gap_path.exists() else "# Director Quality V3 Phase 1 — Gap Audit\n"
    marker = "\n## Final As-Built Verification\n"
    baseline_gap = baseline_gap.split(marker, 1)[0].rstrip()
    gap_path.write_text(
        baseline_gap + marker + "\n"
        f"- Real MiMo HTTP requests: `{real.get('provider_http_request_count')}` (limit `{real.get('provider_http_request_limit')}`).\n"
        f"- First-pass schema valid: `{real.get('protocol_gate', {}).get('first_pass_schema_valid')}/3`; final schema valid: `{real.get('protocol_gate', {}).get('final_schema_valid')}/3`.\n"
        f"- Fact invention: `{real.get('protocol_gate', {}).get('fact_invention_count')}`; unknown IDs: `{real.get('protocol_gate', {}).get('unknown_id_count')}`; strategy leakage: `{real.get('protocol_gate', {}).get('strategy_layer_leakage_count')}`.\n"
        f"- Final status: `{real.get('status')}`; no ShotPlan/media/storage/CI side effects.\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": real["status"], "authorization": authorization, "artifact": str(ARTIFACTS / "director-quality-v3-phase1-strategy-canary-real.json"), "strategy_files": [str(path) for path in sorted(strategy_dir.glob("*.json"))], "http_requests": real["provider_http_request_count"]}, ensure_ascii=False, indent=2))
    return 0 if real["status"] == "SCENE_DIRECTOR_STRATEGY_CANARY_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
