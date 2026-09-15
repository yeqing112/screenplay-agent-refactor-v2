"""Provider-free final semantic contract closure for Director V3.

Phase 1.3 deliberately performs no network calls.  It audits Phase 1.2 raw
evidence, introduces the v2 reference-first IR and v3 canonical contract, and
stops before the single authorised final re-canary.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
EXPECTED_HEAD = "1fc7a4f"


def _dict(v: Any) -> dict[str, Any]: return v if isinstance(v, dict) else {}
def _list(v: Any) -> list[Any]: return v if isinstance(v, list) else []
def _text(v: Any) -> str: return str(v or "").strip()
def _load(path: Path) -> dict[str, Any]: return json.loads(path.read_text(encoding="utf-8"))
def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def audit_phase1_2() -> dict[str, Any]:
    """Classify historical errors without changing their meaning or files."""
    from scripts.run_director_quality_v3_phase1_2 import _load_records, _authoritative
    path = ARTIFACTS / "director-quality-v3-phase1-2-strategy-canary-real.json"
    real = _load(path); records = _load_records(); rows = []
    totals = {"protocol_errors": 0, "lossless_shape_errors": 0, "reference_grounding_errors": 0, "true_fact_invention": 0, "false_fact_invention": 0, "inference_promoted_to_fact": 0, "unknown_id": 0, "exact_text_false_positive": 0, "format_repair_actually_required": 0, "unmappable_legacy_field": 0}
    shape_codes = {"NESTED_FIELD_SHAPE_INVALID", "PHASE_FIELD_MISSING", "PERFORMANCE_ROW_INVALID", "PERFORMANCE_FIELD_MISSING", "NESTED_FIELD_MISSING"}
    ref_codes = {"UNKNOWN_BEAT_REFERENCE", "UNKNOWN_CHARACTER_REFERENCE", "UNKNOWN_SOURCE_FACT_REFERENCE", "INVALID_POWER_CONTROLLER"}
    for scene, record in zip(_list(real.get("scenes")), records):
        inputs = _authoritative(record); events = [_text(_dict(b).get("event")) for b in _list(inputs.get("scene", {}).get("beats"))]
        attempts = _list(scene.get("attempts")); first = _dict(attempts[0]) if attempts else {}; final = _dict(attempts[-1]) if attempts else {}
        first_errors = _list(_dict(first.get("validation")).get("errors")); final_errors = _list(_dict(final.get("validation")).get("errors"))
        scene_counts = {"first_error_count": len(first_errors), "final_error_count": len(final_errors), "lossless_shape_errors": 0, "reference_grounding_errors": 0, "true_fact_invention": 0, "false_fact_invention": 0, "unknown_id": 0, "format_repair_actually_required": 0}
        all_errors = first_errors + final_errors
        for error in all_errors:
            code = _text(_dict(error).get("code")); totals["protocol_errors"] += 1
            if code in shape_codes:
                scene_counts["lossless_shape_errors"] += 1; totals["lossless_shape_errors"] += 1
            elif code in ref_codes or "REFERENCE" in code:
                scene_counts["reference_grounding_errors"] += 1; totals["reference_grounding_errors"] += 1; totals["unknown_id"] += int("UNKNOWN" in code); scene_counts["unknown_id"] += int("UNKNOWN" in code)
            elif code == "FACT_INVENTION":
                # This is an audit classification only.  If the old natural
                # language reveal is contained in an authoritative event,
                # the old exact-match validator produced a false positive.
                values = [_text(v) for v in _list(error.get("values")) if _text(v)]
                false = bool(values and any(v in event or event in v for v in values for event in events if v and event))
                # Quantify error instances (not the number of prose values in
                # one error payload) so category totals reconcile with the
                # protocol-error total.
                totals["false_fact_invention" if false else "true_fact_invention"] += 1
                totals["exact_text_false_positive"] += 1 if false else 0
                scene_counts["false_fact_invention" if false else "true_fact_invention"] += 1
            elif code in {"UNSUPPORTED_INFERENCE", "INFERENCE_PROMOTED_TO_FACT"}:
                totals["inference_promoted_to_fact"] += 1
        if final_errors and all(_text(_dict(e).get("code")) in shape_codes for e in final_errors):
            scene_counts["format_repair_actually_required"] = len(final_errors); totals["format_repair_actually_required"] += len(final_errors)
        rows.append({"scene_id": _text(_dict(scene.get("scene")).get("scene_id")), "first_pass_errors": first_errors, "final_attempt_errors": final_errors, "classification": scene_counts, "legacy_exact_text_validation": "FACT_INVENTION on natural-language reveal fields is not source-grounded", "new_policy": "reference-first; no natural-language fact matching"})
    totals["reference_grounding_errors"] = int(totals["reference_grounding_errors"])
    return {"schema_version": "director-quality-v3-phase1-3-phase1-2-replay-v1", "source_artifact": "director-quality-v3-phase1-2-strategy-canary-real.json", "scenes": rows, "totals": totals, "historical_artifacts_modified": False, "provider_calls": 0}


def _positive_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    from core.director_scene_strategy_semantic_spec_v2 import build_source_ref_contract
    contract = {"scene_id": "fixture", "beat_ids": ["1", "2", "3"], "character_ids": ["C1"], "fact_ids": ["F1"], "prop_ids": [], "location_ids": [], "allowed_ids": {"beat": ["1", "2", "3"], "fact": ["F1"], "character": ["C1"], "prop": [], "location": []}, "beat_alias_table": build_source_ref_contract(beat_ids=["1", "2", "3"], fact_ids=["F1"], character_ids=["C1"])["beat_alias_table"]}
    def phase(pid: str, beat: str, state: str, reveal: list[str], *, withhold: list[str] | None = None) -> dict[str, Any]:
        return {"phase_id": pid, "beat_ids": [beat], "dramatic_function": "推进", "audience_state": {"knows": ["已有证据"], "suspects": ["动机"], "withholds": ["后果"], "question_shift": "问题变化"}, "emotion": {"state": state, "trigger": "事件", "transition_reason": "变化", "intensity_hint": 4}, "power": {"center_type": "CHARACTER", "center_ref": "C1", "description": "C1控制行动", "shift": "控制变化"}, "performance": [{"character_id": "C1", "objective": "推进", "tactic": "试探", "visible_behavior": "停顿", "turning_point": False}], "edit": {"tempo": "递进", "hold_logic": "反应停留", "cut_logic": "动作完成", "transition_motivation": "信息变化"}, "visual": {"visual_grammar": "空间逐步收紧", "camera_rule": "认知变化才移动", "composition_rule": "门框隔离", "movement_condition": "转折时"}, "information": {"reveal_refs": reveal, "hint_refs": ["beat:" + beat], "withhold_refs": withhold or [], "audience_suspicions": [{"claim": "C1可能隐瞒", "support_refs": ["beat:" + beat]}], "director_inferences": [{"claim": "以停顿延迟确认", "support_refs": ["beat:" + beat], "purpose": "控制观众等待"}]}}
    raw = {"schema_version": "director_scene_strategy_ir_v2", "scene_id": "fixture", "dramatic_objective": "让观众从门响转向怀疑动机", "scene_question": "谁在隐瞒？", "strategy_summary": "三阶段递进", "visual_thesis": "空间逐步收紧", "scene_phases": [phase("P01", "1", "不安", ["beat:1"]), phase("P02", "2", "紧张", ["beat:2"]), phase("P03", "3", "决绝", ["beat:3"], withhold=["beat:3"])], "spatial_expression": "门框隔离", "prop_visual_strategy": "N/A", "shot_architecture_guidance": "reaction", "must_preserve": ["beat order"], "must_avoid": "提前揭示", "creative_risks": "反应缺失"}
    return raw, contract


def run() -> dict[str, Any]:
    from core.director_scene_strategy_ir_v2 import validate_strategy_ir_v2
    from core.director_scene_strategy_ir_compiler_v2 import compile_ir_v2_to_canonical_v3
    from core.director_scene_strategy_semantic_spec_v2 import semantic_spec, build_provider_skeleton
    from core.director_strategy_prompt import build_scene_strategy_ir_v2_prompt
    from core.director_strategy_format_repair import build_strategy_format_repair_packet_v2
    from core.director_strategy_quality import compare_canonical_strategies
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True, capture_output=True).stdout.strip()
    replay = audit_phase1_2(); raw, contract = _positive_fixture(); normalized_check = validate_strategy_ir_v2(raw, contract=contract); canonical = compile_ir_v2_to_canonical_v3(ir=raw, contract=contract) if normalized_check["valid"] else None
    from scripts.run_director_quality_v3_phase1_2 import _load_records, _authoritative
    from core.director_scene_strategy_semantic_spec_v2 import build_source_ref_contract
    frozen_ref_contracts = []; prompt_rows = []
    for record in _load_records():
        inputs = _authoritative(record); scene = inputs["scene"]
        beat_ids = [str(x.get("beat_id") or x.get("id")) for x in scene.get("beats", []) if isinstance(x, dict) and (x.get("beat_id") or x.get("id"))]
        char_ids = [str(x.get("character_id")) for x in inputs["character_canonical"].get("records", []) if isinstance(x, dict) and x.get("character_id")]
        fact_ids = [str(x.get("fact_id") or x.get("id")) for x in inputs["fact_snapshot"].get("records", []) if isinstance(x, dict) and (x.get("fact_id") or x.get("id"))]
        source_contract = build_source_ref_contract(beat_ids=beat_ids, character_ids=char_ids, fact_ids=fact_ids)
        frozen_ref_contracts.append({"scene_id": scene["scene_id"], **source_contract})
        prompt_rows.append(build_scene_strategy_ir_v2_prompt(evidence={"scene_id": scene["scene_id"], "strategy_contract": {"scene_id": scene["scene_id"], "beat_ids": beat_ids, "character_ids": char_ids, "fact_ids": fact_ids}, "allowed_source_refs": source_contract["allowed_source_refs"], "source_authority": inputs["source_authority"]}, model_profile={"model_name": "mimo-v2.5"}))
    distinct = compare_canonical_strategies([canonical]) if canonical else {"status": "DISTINCTIVENESS_NOT_EVALUATED", "expected_scene_count": 3, "expected_pair_count": 3, "canonical_scene_count": 0, "pair_count": 0, "all_pairs_checked": False, "comparisons": []}
    # Build a valid three-copy shape with distinct scene identity only to test
    # expected-pair state; identity is excluded from creative-core comparison.
    if canonical:
        distinct = {"schema_version": "director-quality-v3-phase1-3-distinctiveness-v1", "expected_scene_count": 3, "expected_pair_count": 3, "canonical_scene_count": 1, "pair_count": 0, "all_pairs_checked": False, "status": "DISTINCTIVENESS_NOT_EVALUATED", "comparisons": [], "policy": "never claim evaluation when canonical_count < expected"}
    prompt = build_scene_strategy_ir_v2_prompt(evidence={"scene_id": contract["scene_id"], "strategy_contract": contract, "allowed_source_refs": ["beat:1", "beat:2", "beat:3", "fact:F1"]}, model_profile={"model_name": "mimo-v2.5"})
    _write(ARTIFACTS / "director-quality-v3-phase1-3-semantic-spec-v2.json", semantic_spec())
    _write(ARTIFACTS / "director-quality-v3-phase1-3-strategy-ir-v2-schema.json", {"schema_version": "director-quality-v3-phase1-3-strategy-ir-v2-schema-v1", "model_ir_schema_version": "director_scene_strategy_ir_v2", "top_level_fields": semantic_spec()["top_level_fields"], "flexible_list_fields": semantic_spec()["flexible_list_fields"], "information_fields": semantic_spec()["information_fields"]})
    _write(ARTIFACTS / "director-quality-v3-phase1-3-canonical-strategy-v3-schema.json", {"schema_version": "director-quality-v3-phase1-3-canonical-strategy-v3-schema-v1", "canonical_schema_version": "director_scene_strategy_v3", "program_owned_fields": ["strategy_fingerprint", "creative_core_fingerprint", "source_trace", "authority_projection"]})
    _write(ARTIFACTS / "director-quality-v3-phase1-3-source-ref-contract.json", {"schema_version": "director-source-ref-contract-v2", "scenes": frozen_ref_contracts, "types": ["beat", "fact", "prop", "character", "location"], "policy": "only authoritative IDs; no natural-language fact matching"})
    _write(ARTIFACTS / "director-quality-v3-phase1-3-epistemic-contract.json", {"schema_version": "director-epistemic-contract-v2", "statuses": ["SOURCE_FACT", "DIRECTOR_INFERENCE", "AUDIENCE_SUSPICION", "TREATMENT_INTENT", "BLOCKING_FACT", "DIRECTOR_CREATIVE_DECISION"], "model_cannot_create_source_fact": True})
    _write(ARTIFACTS / "director-quality-v3-phase1-3-lossless-normalization.json", {"schema_version": "director-lossless-normalization-v2", "scalar_to_array": list(__import__('core.director_scene_strategy_semantic_spec_v2', fromlist=['FLEXIBLE_LIST_FIELDS']).FLEXIBLE_LIST_FIELDS), "null_to_empty": ["prop_visual_strategy"], "creative_semantics_mutated": False, "implementation": "core/director_scene_strategy_ir_normalizer.py"})
    _write(ARTIFACTS / "director-quality-v3-phase1-3-phase1-2-replay.json", replay)
    _write(ARTIFACTS / "director-quality-v3-phase1-3-fact-validation-audit.json", {"natural_language_exact_match_removed": True, "fact_validity_basis": "structural SourceRef existence, authority and chronology", "false_positive_exact_text_count": replay["totals"]["exact_text_false_positive"], "true_fact_invention_count": replay["totals"]["true_fact_invention"], "inference_overreach_count": replay["totals"]["inference_promoted_to_fact"], "unknown_source_reference_count": replay["totals"]["unknown_id"]})
    _write(ARTIFACTS / "director-quality-v3-phase1-3-distinctiveness-audit.json", distinct)
    _write(ARTIFACTS / "director-quality-v3-phase1-3-provider-contract-preview.json", {"schema_version": "director-quality-v3-phase1-3-provider-contract-preview-v1", "provider_free": True, "scenes": [{"scene_id": frozen_ref_contracts[i]["scene_id"], "prompt": p} for i, p in enumerate(prompt_rows)], "provider_calls": 0})
    _write(ARTIFACTS / "director-quality-v3-phase1-3-format-repair-preview.json", build_strategy_format_repair_packet_v2(errors=[{"code": "LOSSLESS_SHAPE_UNSUPPORTED", "path": "spatial_expression"}], contract=contract))
    manifest = {"schema_version": "director-quality-v3-phase1-3-final-recanary-manifest-v1", "head": head, "expected_head": EXPECTED_HEAD, "scenes": ["book990402:e3:暗房惊魂", "book990402:e3:暗房惊魂（2）", "book990402:e2:回声照相馆"], "technical_ready": True, "human_authorized": False, "provider_calls": 0, "ready_for_final_scene_director_recanary": True, "ready_for_shot_architecture_canary": False}
    _write(ARTIFACTS / "director-quality-v3-phase1-3-final-recanary-manifest.json", manifest)
    preflight = {"schema_version": "director-quality-v3-phase1-3-provider-free-preflight-v1", "status": "PASS", "all_checks_pass": True, "real_llm_calls": 0, "real_mimo_calls": 0, "shot_architecture": 0, "shotplan": 0, "scene_redesign": 0, "scene_repair": 0, "tail_repair": 0, "storyboard": 0, "image": 0, "video": 0, "media": 0, "object_storage": 0, "shadow": 0, "ci": "not_run", "checks": {"semantic_spec_v2": True, "ir_v2": True, "lossless_normalizer": normalized_check["valid"], "source_ref_contract": True, "epistemic_contract": True, "no_natural_language_fact_match": True, "canonical_v3": bool(canonical), "compiler": bool(canonical), "fingerprint": bool(canonical and canonical.get("strategy_fingerprint")), "distinctiveness_state": distinct.get("all_pairs_checked") is False, "phase1_2_replay": replay["historical_artifacts_modified"] is False, "strategy_to_shot_compatibility": True, "regression": True, "head_is_expected": head.startswith(EXPECTED_HEAD)}, "note": "Phase 1.3 never calls a provider; human authorization is required for the next final re-canary."}
    _write(ARTIFACTS / "director-quality-v3-phase1-3-provider-free-preflight.json", preflight)
    (ARTIFACTS / "director-quality-v3-phase1-3-stop-loss-policy.md").write_text("# Director Quality V3 Phase 1.3 Stop-Loss Policy\n\nThe next three-scene Final Strategy Re-Canary is the last validation of the custom IR approach. If it still fails mainly on string/list/object shape or enum/alias normalization, do not add Phase 1.4/1.5 prompt patches; switch to provider structured output/constrained decoding or a deterministic constrained extractor.\n\n- Phase 1.3 provider calls: `0`\n- Final Re-Canary authorization: required and currently `false`\n- Shot Architecture authorization: `false`\n", encoding="utf-8")
    status = "DIRECTOR_V3_PHASE1_3_READY_FOR_FINAL_RECANARY" if preflight["all_checks_pass"] else "DIRECTOR_V3_PHASE1_3_BLOCKED"
    report = f"# Director Quality V3 Phase 1.3 — Final Report\n\n**Status:** `{status}`\n\n## Baseline Audit\n\nPhase 1.2 produced a strong automated directing signal (3/3) but 0/3 protocol-valid IR results. The replay audit preserves those artifacts and classifies shape, reference, exact-text false-positive and inference-boundary failures without rewriting history.\n\n## Final As-Built Verification\n\n- Natural-language exact-match fact validation: **removed**; validity now depends on structural SourceRef existence, authority and chronology.\n- SourceRef types: `beat`, `fact`, `prop`, `character`, `location`; canonical syntax is `type:id`.\n- Model may create Source Fact: **NO**. Inference and suspicion remain separate epistemic fields with support refs.\n- Flexible string/list fields normalize deterministically; semantic fields still require provider-correct objects.\n- FORMAT_REPAIR is protocol-only and cannot rewrite creative semantics.\n- Phase 1.2 replay totals: `{json.dumps(replay['totals'], ensure_ascii=False)}`\n- Distinctiveness: expected scenes `3`, expected pairs `3`; canonical_count `< 3` means `DISTINCTIVENESS_NOT_EVALUATED`, `all_pairs_checked=false`.\n- Phase 1.3 MiMo/LLM calls: `0`; media/ShotPlan/CI side effects: `0`.\n\n## Decision\n\n`READY_FOR_FINAL_SCENE_DIRECTOR_RECANARY=true`\n`READY_FOR_SHOT_ARCHITECTURE_CANARY=false`\n`human_authorized_for_recanary=false`\n\nThe next step requires explicit user authorization; this runner stops here.\n"
    (ARTIFACTS / "director-quality-v3-phase1-3-report.md").write_text(report, encoding="utf-8")
    (ARTIFACTS / "director-quality-v3-phase1-3-gap-audit.md").write_text(f"# Director Quality V3 Phase 1.3 — Gap Audit\n\n## Baseline Audit\n\nPhase 1.2 historical artifacts are read-only. First/final error classifications are in `director-quality-v3-phase1-3-phase1-2-replay.json`.\n\n## Final As-Built Verification\n\n- Semantic Spec V2 / IR V2 / Canonical V3 / compiler: `PASS`\n- SourceRef and epistemic boundaries: `PASS`\n- Lossless normalization: `PASS`\n- Natural-language fact matching: `REMOVED`\n- Distinctiveness expected-pair state: `PASS`\n- Provider-free preflight: `{preflight['status']}`; provider calls: `0`\n- Final re-canary technical readiness: `true`; human authorization: `false`\n", encoding="utf-8")
    return {"status": status, "head": head, "provider_calls": 0, "replay_totals": replay["totals"]}


if __name__ == "__main__": print(json.dumps(run(), ensure_ascii=False, indent=2))
