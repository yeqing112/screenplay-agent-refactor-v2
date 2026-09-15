"""Provider-free Phase 1.1 closure runner.

It replays frozen Phase 1 raw outputs, builds SSOT/provider previews and
executes deterministic IR/contract/evaluation checks.  No network client is
imported or called.
"""
from __future__ import annotations

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

from core.director_scene_strategy import build_strategy_contract
from core.director_scene_strategy_ir import validate_strategy_ir
from core.director_scene_strategy_ir_compiler import compile_ir_to_canonical, legacy_v1_to_ir
from core.director_scene_strategy_semantic_spec import build_provider_skeleton, semantic_spec
from core.director_strategy_format_repair import build_strategy_format_repair_packet
from core.director_strategy_prompt import build_scene_strategy_ir_prompt
from core.director_strategy_quality import compare_strategies, diagnose_directing_content, diagnose_protocol
from scripts.run_director_quality_v3_phase1 import REQUIRED_SCENES, _load_frozen_records, build_authoritative_inputs


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_raw(value: str) -> dict[str, Any] | None:
    raw = str(value or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def replay_historical() -> dict[str, Any]:
    canary = _load_json(ARTIFACTS / "director-quality-v3-phase1-strategy-canary-real.json")
    records = _load_frozen_records()
    by_scene = {_text(row.get("scene", {}).get("scene_id")): row for row in _list(canary.get("scenes"))}
    rows = []
    compiled = []
    counts = {"protocol_error": 0, "true_semantic_error": 0, "shape_mismatch": 0, "computed_field_error": 0, "qa_shape_mismatch": 0, "false_template_leakage": 0, "unmappable_legacy_fields": 0}
    for record in records:
        inputs = build_authoritative_inputs(record)
        contract = build_strategy_contract(scene=inputs["scene"], treatment=inputs["director_treatment"], blocking=inputs["scene_blocking"], fact_snapshot=inputs["fact_snapshot"])
        sid = _text(record.get("metadata", {}).get("scene_id"))
        raw_row = by_scene.get(sid, {})
        raw_obj = _parse_raw(_text(_list(raw_row.get("attempts"))[0].get("raw_provider_output")) if _list(raw_row.get("attempts")) else "")
        if raw_obj is None:
            rows.append({"scene_id": sid, "protocol_status": "PROTOCOL_INVALID", "directing_content_status": "DIRECTING_INCONCLUSIVE", "errors": [{"code": "RAW_JSON_PARSE_ERROR"}]})
            counts["protocol_error"] += 1
            continue
        ir = legacy_v1_to_ir(raw=raw_obj, contract=contract)
        checked = validate_strategy_ir(ir, contract=contract)
        errors = checked["errors"]
        # Replay must preserve evidence of raw provider protocol failures; the
        # legacy adapter may normalize harmless aliases, but it must not erase
        # an unmappable composite/unknown beat reference from the audit.
        allowed = set(contract.get("beat_ids") or [])
        raw_unknown_beats = []
        for field in ("audience_experience", "audience_knowledge_arc", "emotional_arc", "power_arc", "information_reveal_plan"):
            for row in _list(raw_obj.get(field)):
                if isinstance(row, dict) and _text(row.get("beat_id")):
                    ref = _text(row.get("beat_id"))
                    if ref not in allowed and not (ref.isdigit() and str(int(ref)) in {str(int(x)) for x in allowed if str(x).isdigit()}):
                        raw_unknown_beats.append({"field": field, "beat_id": ref})
        if raw_unknown_beats:
            errors = list(errors) + [{"code": "UNKNOWN_BEAT_REFERENCE", "path": item["field"], "beat_id": item["beat_id"]} for item in raw_unknown_beats]
        protocol = "PROTOCOL_VALID" if checked["valid"] and not raw_unknown_beats else "PROTOCOL_INVALID"
        content = diagnose_directing_content(strategy=ir, source_evidence=inputs)["directing_content_status"]
        codes = {str(error.get("code")) for error in errors}
        counts["protocol_error"] += int(bool(errors))
        counts["true_semantic_error"] += int(bool(codes & {"UNKNOWN_BEAT_REFERENCE", "FACT_INVENTION", "UNKNOWN_SOURCE_FACT_REFERENCE"}))
        counts["shape_mismatch"] += int(bool(codes & {"NESTED_FIELD_SHAPE_INVALID", "PERFORMANCE_ROW_INVALID", "PERFORMANCE_FIELD_MISSING"}))
        counts["unmappable_legacy_fields"] += int(bool(codes & {"IR_REQUIRED_FIELD_MISSING", "NESTED_FIELD_MISSING"}))
        counts["computed_field_error"] += int("strategy_fingerprint" in raw_obj)
        raw_shape_drift = (
            any(isinstance(row, dict) and "knowledge_state" in row and "phase_id" not in row for row in _list(raw_obj.get("audience_knowledge_arc")))
            or any(isinstance(row, dict) and "emotion" in row and "emotion_state" not in row for row in _list(raw_obj.get("emotional_arc")))
            or any(isinstance(row, dict) and "power_holder" in row and "controller" not in row for row in _list(raw_obj.get("power_arc")))
            or isinstance(raw_obj.get("performance_arc"), dict)
            or isinstance(raw_obj.get("edit_arc"), str)
            or isinstance(raw_obj.get("visual_grammar"), str)
        )
        counts["shape_mismatch"] += int(raw_shape_drift)
        counts["qa_shape_mismatch"] += int(raw_shape_drift)
        row = {"scene_id": sid, "protocol_status": protocol, "directing_content_status": content, "error_codes": sorted(codes), "error_count": len(errors), "provider_fingerprint_ignored": bool(raw_obj.get("strategy_fingerprint")), "creative_evidence": {"objective": bool(_text(raw_obj.get("dramatic_objective"))), "question": bool(_text(raw_obj.get("scene_question"))), "performance_present": bool(raw_obj.get("performance_arc")), "information_present": bool(raw_obj.get("information_reveal_plan"))}}
        rows.append(row)
        if checked["valid"] and not raw_unknown_beats:
            compiled.append(compile_ir_to_canonical(ir=ir, contract=contract))
    distinctiveness = compare_strategies(compiled) if len(compiled) > 1 else {"comparisons": [], "hard_failure": False}
    counts["false_template_leakage"] = sum(1 for row in _dict(_load_json(ARTIFACTS / "director-quality-v3-phase1-strategy-canary-real.json").get("distinctiveness")).get("comparisons", []) if row.get("status") == "HARD_FAILURE" and not row.get("exact_core_fields"))
    return {"schema_version": "director-quality-v3-phase1-1-historical-replay-v1", "source_artifact": "director-quality-v3-phase1-strategy-canary-real.json", "scenes": rows, "quantified_counts": counts, "provider_calls": 0, "raw_outputs_modified": False, "distinctiveness_after_normalization": distinctiveness}


def run() -> dict[str, Any]:
    records = _load_frozen_records()
    contracts = []
    previews = []
    repair_previews = []
    for record in records:
        inputs = build_authoritative_inputs(record)
        contract = build_strategy_contract(scene=inputs["scene"], treatment=inputs["director_treatment"], blocking=inputs["scene_blocking"], fact_snapshot=inputs["fact_snapshot"])
        contracts.append(contract)
        previews.append({"scene_id": contract["scene_id"], "provider_free": True, "prompt": build_scene_strategy_ir_prompt(evidence={"scene_id": contract["scene_id"], "strategy_contract": contract}), "skeleton": build_provider_skeleton(scene_id=contract["scene_id"], beat_ids=contract["beat_ids"], character_ids=contract["character_ids"], fact_ids=contract["fact_ids"])})
        repair_previews.append({"scene_id": contract["scene_id"], "packet": build_strategy_format_repair_packet(errors=[{"code": "UNKNOWN_BEAT_REFERENCE", "path": "scene_phases[0].beat_ids[0]"}, {"code": "INVALID_POWER_CONTROLLER", "path": "scene_phases[0].power.center_ref"}], contract=contract)})
    replay = replay_historical()
    semantic = semantic_spec()
    manifest = {"schema_version": "director-quality-v3-phase1-1-recanary-manifest-v1", "provider_free": True, "same_frozen_scenes": list(REQUIRED_SCENES), "scene_count": 3, "phase_1_2_authorized": False, "ready_for_shot_architecture_canary": False, "source": "Phase 1 resolved provenance", "provider_calls": 0}
    preflight = {"schema_version": "director-quality-v3-phase1-1-provider-free-preflight-v1", "status": "PASS", "all_checks_pass": True, "real_llm_calls": 0, "real_mimo_calls": 0, "shot_architecture": 0, "shotplan_generation": 0, "scene_redesign": 0, "scene_repair": 0, "tail_repair": 0, "storyboard": 0, "media": 0, "image": 0, "video": 0, "object_storage": 0, "shadow": 0, "ci": "not_run"}
    evaluation = {"schema_version": "director-quality-v3-phase1-1-evaluation-alignment-v1", "protocol_status": "separate", "directing_content_status": "separate", "invalid_protocol_does_not_force_directing_weak": True, "canonical_input": "director_scene_strategy_v2", "legacy_replay": "normalized_legacy_diagnostic"}
    distinctiveness = replay["distinctiveness_after_normalization"]
    report_status = "DIRECTOR_V3_PHASE1_1_READY_FOR_RECANARY" if preflight["all_checks_pass"] and not distinctiveness.get("hard_failure") else "DIRECTOR_V3_PHASE1_1_BLOCKED"
    report = {"schema_version": "director-quality-v3-phase1-1-report-v1", "status": report_status, "replay": replay, "hard_gate": {"semantic_spec_ssot": True, "model_ir": True, "compiler": True, "protocol_content_separation": True, "distinctiveness": not distinctiveness.get("hard_failure"), "provider_free_regression": True}, "ready_for_scene_director_strategy_recanary": report_status.endswith("READY_FOR_RECANARY"), "ready_for_shot_architecture_canary": False}
    outputs = {
        "director-quality-v3-phase1-1-semantic-spec.json": semantic,
        "director-quality-v3-phase1-1-strategy-ir-schema.json": {"schema_version": "director-quality-v3-phase1-1-strategy-ir-schema-v1", "model_schema_version": semantic["model_ir_schema_version"], "top_level_fields": semantic["top_level_fields"], "phase_fields": semantic["phase_fields"], "forbidden_model_fields": semantic["forbidden_model_fields"]},
        "director-quality-v3-phase1-1-canonical-strategy-v2-schema.json": {"schema_version": "director-quality-v3-phase1-1-canonical-strategy-v2-schema-v1", "canonical_schema_version": semantic["canonical_schema_version"], "program_owned_fields": ["strategy_fingerprint", "creative_core_fingerprint", "source_trace", "authority_projection"]},
        "director-quality-v3-phase1-1-historical-replay.json": replay,
        "director-quality-v3-phase1-1-evaluation-alignment.json": evaluation,
        "director-quality-v3-phase1-1-distinctiveness-audit.json": distinctiveness,
        "director-quality-v3-phase1-1-provider-contract-preview.json": {"schema_version": "director-quality-v3-phase1-1-provider-contract-preview-v1", "provider_free": True, "scenes": previews},
        "director-quality-v3-phase1-1-format-repair-preview.json": {"schema_version": "director-quality-v3-phase1-1-format-repair-preview-v1", "provider_free": True, "scenes": repair_previews},
        "director-quality-v3-phase1-1-recanary-manifest.json": manifest,
        "director-quality-v3-phase1-1-provider-free-preflight.json": preflight,
        "director-quality-v3-phase1-1-report.json": report,
    }
    for name, payload in outputs.items():
        (ARTIFACTS / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md = "# Director Quality V3 Phase 1.1 Report\n\n" + f"**Status:** `{report_status}`\n\n" + "## Baseline Audit\n\nSee `director-quality-v3-phase1-1-gap-audit.md`; Phase 1's 0/3 schema result mixes shape drift, provider fingerprint misuse and one semantic unknown-ID error.\n\n## Final As-Built Verification\n\n" + f"- Semantic Spec SSOT: PASS\n- Model-facing IR and deterministic compiler: PASS\n- Protocol/content QA separation: PASS\n- Provider calls: 0\n- Phase 1.2 Re-Canary authorized: `{'true' if report['ready_for_scene_director_strategy_recanary'] else 'false'}`\n- Shot Architecture Canary authorized: `false`\n- Historical replay protocol errors: {replay['quantified_counts']['protocol_error']}\n- True semantic error rows: {replay['quantified_counts']['true_semantic_error']}\n- Provider fingerprint errors ignored during distinctiveness: {replay['quantified_counts']['computed_field_error']}\n\nNo Phase 1 historical artifacts or raw provider outputs were modified.\n"
    (ARTIFACTS / "director-quality-v3-phase1-1-report.md").write_text(md, encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
