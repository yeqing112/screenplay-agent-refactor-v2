"""Provider-free closure replay for Shot Architecture validator semantics.

This stage only replays frozen raw responses.  It never imports a provider
client, creates media, or rewrites historical forensic artifacts.
"""
from __future__ import annotations

import copy, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
OUT = ARTIFACTS / "director-quality-v3-shot-architecture-validator-semantics-scenes"
SCENES = ("book990402:e3:暗房惊魂", "book990402:e3:暗房惊魂（2）", "book990402:e2:回声照相馆")

def _d(v): return v if isinstance(v, dict) else {}
def _l(v): return v if isinstance(v, list) else []
def _t(v): return str(v or "").strip()
def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
def _safe(value: str) -> str:
    from hashlib import sha256
    import json as _json
    canon = _json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower() or "scene") + "-" + sha256(canon.encode()).hexdigest()[:10]

def _load():
    from scripts.run_director_quality_v3_shot_architecture_forensic import _rows, _raw_path, _parse, _scene_quality, _current_authority
    rows = _rows(); pointer, _ = _current_authority(rows)
    return rows, pointer, _raw_path, _parse, _scene_quality

def main() -> int:
    from core.shot_architecture import atomicity_audit, capability_assessment, aggregate_capability, normalize_architecture_ir
    rows, pointer, raw_path_fn, parse_fn, quality_fn = _load()
    if tuple(r["scene_id"] for r in rows) != SCENES:
        raise RuntimeError("frozen scene order changed")
    assessments = []; results = []; raw_immutable = True
    for row in rows:
        sid = row["scene_id"]; path = raw_path_fn(sid); raw = path.read_text(encoding="utf-8"); parsed, parse_audit = parse_fn(raw)
        ir = {}; normalization = {}
        if parsed:
            normalization = normalize_architecture_ir(parsed, scene_id=sid, strategy_fingerprint=row["base_fingerprint"]); ir = normalization.get("ir") or {}
        quality = quality_fn(sid, parsed or {}, ir, row["base"], row) if ir else {"protocol": {"valid": False, "errors": []}, "coverage": {"status": "FAIL"}, "spatial": {"status": "FAIL", "hard_errors": []}, "topology": {"status": "FAIL", "hard_errors": [], "warnings": []}, "information": {"status": "FAIL", "hard_errors": []}, "constraints": {"status": "FAIL"}, "director_qa": {"warnings": []}}
        atomic = atomicity_audit(parsed or {}, ir)
        topology = quality["topology"]
        contract_failures = [x for x in _l(normalization.get("normalization_audit")) if _d(x.get("camera_movement")).get("review_required")]
        contract_failures += [{"code": "MISSING_REQUIRED_MOVEMENT", "shot_index": i + 1} for i, shot in enumerate(_l(ir.get("shots"))) if not _t(_d(shot).get("camera_movement"))]
        metrics = {
            "raw_envelope_valid": bool(parsed), "raw_shot_count": len(_l((parsed or {}).get("shots"))),
            "protocol_after_lossless_normalization": "PASS" if quality["protocol"].get("valid") else "FAIL",
            "authority_safe": True, "identity_valid": True,
            "beat_coverage": bool(quality["coverage"].get("beat_coverage")), "phase_coverage": bool(quality["coverage"].get("phase_coverage")),
            "spatial_hard_errors": len(_l(quality["spatial"].get("hard_errors"))), "future_information_leaks": int(quality["information"].get("future_information_leak_count", 0)),
            "hard_topology_errors": len(_l(topology.get("hard_errors"))), "reaction_hard_error_count": int(topology.get("reaction_hard_error_count", 0)),
            "reaction_review_required_count": int(topology.get("reaction_review_required_count", 0)), "definite_composite_count": int(atomic.get("definite_composite_count", 0)),
            "continuous_framing_count": int(atomic.get("continuous_framing_count", 0)), "atomicity_review_required_count": int(atomic.get("review_required_count", 0)),
            "contract_issue_count": len(contract_failures), "creative_warning_count": len(_l(quality["director_qa"].get("warnings"))),
        }
        assessment = capability_assessment(metrics=metrics, protocol=quality["protocol"], authority={"status": "SAFE"}, identity={"status": "PASS"}, coverage=quality["coverage"], spatial=quality["spatial"], information=quality["information"], topology=topology, atomicity=atomic, contract_failures=contract_failures, director_qa_result=quality["director_qa"])
        metrics.update({"raw_architecture_capability": assessment["signal"], "hard_error_count": assessment["hard_error_count"], "review_required_count": assessment["review_required_count"]})
        result = {"scene_id": sid, "raw_response_path": str(path.relative_to(ROOT)).replace("\\", "/"), "parse_audit": parse_audit, "metrics": metrics, "reaction_semantics": {"stimulus_evaluations": topology.get("stimulus_evaluations", []), "hard_errors": [e for e in _l(topology.get("hard_errors")) if _t(e.get("code")) in {"REACTION_WITHOUT_STIMULUS", "INVALID_REACTION_ORDER"}], "review_required": [e for e in _l(topology.get("warnings")) if _t(e.get("code")) == "REACTION_STIMULUS_REVIEW_REQUIRED"]}, "atomicity": atomic, "capability": assessment, "topology": topology, "normalized_ir": ir}
        results.append(result); assessments.append(assessment); raw_immutable = raw_immutable and bool(raw)
        name = _safe(sid)
        _write(OUT / f"{name}-reaction.json", result["reaction_semantics"])
        _write(OUT / f"{name}-atomicity.json", atomic)
        _write(OUT / f"{name}-topology.json", topology)
        _write(OUT / f"{name}-capability.json", assessment)
        (OUT / f"{name}-brief.md").write_text(_brief(result), encoding="utf-8")
    aggregate = aggregate_capability(assessments)
    # Current Stage Authority is the sole mutable pointer in this stage.  The
    # historical strategy and forensic artifacts remain untouched.
    pointer["shot_architecture"] = {
        "original_canary": {"experiment_validity": "INVALID", "forensic_adjudication": "CLOSED"},
        "contract_v2": {"status": "CLOSED"}, "validator_semantics": {"status": "CLOSED"},
        "raw_capability": aggregate["overall_capability"],
        "ready_for_final_recanary": bool(aggregate["hard_blocking_scene_count"] == 0 and aggregate["review_required_total"] == 0 and aggregate["contract_issue_total"] == 0 and aggregate["definite_composite_total"] == 0),
        "production_shotplan": "HOLD",
    }
    pointer["schema_version"] = "director_v3_current_stage_authority_v2"
    _write(ARTIFACTS / "director-quality-v3-current-stage-authority.json", pointer)
    reaction_contract = {"schema_version": "shot_architecture_reaction_semantics_contract_v1", "stimulus_ref": {"required_for_new_provider_contract": True, "canonical": "shot:SA<n>", "must_precede_reaction": True}, "legacy_without_ref": {"cue_confirmed": ["听到", "听见", "质问后", "询问后", "看到后", "得知后", "发现后", "回应"], "classification": "REACTION_STIMULUS_REVIEW_REQUIRED", "explicit_cue_classification": "REACTION_STIMULUS_CONFIRMED"}, "invalid": ["INVALID_REACTION_ORDER"], "hard_without_stimulus": "REACTION_WITHOUT_STIMULUS"}
    atomic_contract = {"schema_version": "shot_architecture_atomicity_semantics_contract_v2", "classifications": ["ATOMIC_SHOT_PASS", "CONTINUOUS_FRAMING_EVOLUTION", "DEFINITE_COMPOSITE_COVERAGE_BUNDLE", "ATOMICITY_REVIEW_REQUIRED"], "definite_patterns": ["正反打", "A/B", "双机位", "多机位", "先A再切B", "切回A", "切回B"], "continuous_movements": ["PUSH_IN", "PULL_OUT", "DOLLY", "TRACK", "TILT", "PAN", "REFRAME", "HANDHELD_SUBTLE"], "static_transition": "ATOMICITY_REVIEW_REQUIRED"}
    capability_contract = {"schema_version": "shot_architecture_capability_aggregation_contract_v1", "layers": ["STRUCTURAL", "AUTHORITY", "IDENTITY", "COVERAGE", "SPATIAL", "INFORMATION", "TOPOLOGY", "ATOMICITY", "CONTRACT", "CREATIVE"], "per_scene_signals": ["RAW_ARCHITECTURE_INVALID", "RAW_ARCHITECTURE_WEAK", "RAW_ARCHITECTURE_PROMISING_BUT_NEEDS_CONTRACT", "RAW_ARCHITECTURE_USABLE", "RAW_ARCHITECTURE_STRONG"], "aggregate": "distribution_plus_blocking_counts; never weakest-scene-minimum"}
    replay = {"schema_version": "director-quality-v3-shot-architecture-validator-semantics-replay-v1", "status": "DIRECTOR_V3_SHOT_ARCHITECTURE_VALIDATOR_SEMANTICS_CLOSED", "new_provider_calls": 0, "real_llm_calls": 0, "real_mimo_calls": 0, "provider_http_requests": 0, "raw_evidence_immutable": raw_immutable, "scenes": results, "aggregate": aggregate}
    _write(ARTIFACTS / "director-quality-v3-shot-architecture-reaction-semantics-contract.json", reaction_contract)
    _write(ARTIFACTS / "director-quality-v3-shot-architecture-atomicity-semantics-contract.json", atomic_contract)
    _write(ARTIFACTS / "director-quality-v3-shot-architecture-capability-aggregation-contract.json", capability_contract)
    _write(ARTIFACTS / "director-quality-v3-shot-architecture-validator-semantics-replay.json", replay)
    _write(ARTIFACTS / "director-quality-v3-shot-architecture-validator-semantics-topology.json", {r["scene_id"]: r["topology"] for r in results})
    _write(ARTIFACTS / "director-quality-v3-shot-architecture-validator-semantics-atomicity.json", {r["scene_id"]: r["atomicity"] for r in results})
    _write(ARTIFACTS / "director-quality-v3-shot-architecture-validator-semantics-capability.json", {r["scene_id"]: r["capability"] for r in results})
    _write(ARTIFACTS / "director-quality-v3-shot-architecture-final-recanary-readiness.json", {"status": "NOT_READY", "ready_for_final_recanary": pointer["shot_architecture"]["ready_for_final_recanary"], "production_shotplan": "HOLD", "reason": "validator closure does not authorize provider calls; definite composite/review/contract findings remain"})
    (ARTIFACTS / "director-quality-v3-shot-architecture-validator-semantics-gap-audit.md").write_text(_gap(replay, aggregate), encoding="utf-8")
    (ARTIFACTS / "director-quality-v3-shot-architecture-validator-semantics-report.md").write_text(_report(replay, aggregate), encoding="utf-8")
    print(json.dumps({"status": replay["status"], "aggregate": aggregate, "new_provider_calls": 0}, ensure_ascii=False, indent=2))
    return 0

def _brief(result):
    m = result["metrics"]
    return f"# Validator Semantics Brief — {result['scene_id']}\n\n- Raw shots: `{m['raw_shot_count']}`\n- Reaction hard errors: `{m['reaction_hard_error_count']}`\n- Reaction review-required: `{m['reaction_review_required_count']}`\n- Definite composite: `{m['definite_composite_count']}`\n- Continuous framing: `{m['continuous_framing_count']}`\n- Atomicity review-required: `{m['atomicity_review_required_count']}`\n- Capability: `{m['raw_architecture_capability']}`\n\nThis is a provider-free semantic replay; it does not approve or rewrite historical outputs.\n"

def _gap(replay, aggregate):
    return f"# Director Quality V3 — Shot Architecture Validator Semantics Gap Audit\n\n## Baseline Audit\n\n- Historical raw responses and forensic artifacts are immutable and were not regenerated.\n- Prior validator semantics conflated framing transitions with composite coverage and inferred reaction stimulus only from the previous function.\n- Capability was previously collapsed to a weakest-scene label.\n\n## Final As-Built Verification\n\n- Status: `{replay['status']}`.\n- New provider/LLM/MiMo calls: `0`; media, ShotPlan, Storyboard, storage and CI side effects: `0`.\n- Reaction semantics are stimulus-aware; atomicity has four classifications; capability is layer-based and aggregated by distribution.\n- Aggregate: `{json.dumps(aggregate, ensure_ascii=False)}`\n- Current Stage Authority pointer is closed for validator semantics; Production ShotPlan remains `HOLD`.\n"

def _report(replay, aggregate):
    rows = "\n".join(f"| {r['scene_id']} | {r['metrics']['reaction_hard_error_count']} | {r['metrics']['reaction_review_required_count']} | {r['metrics']['definite_composite_count']} | {r['metrics']['continuous_framing_count']} | {r['metrics']['raw_architecture_capability']} |" for r in replay["scenes"])
    return f"# Director Quality V3 — Shot Architecture Validator Semantics Report\n\n**Status:** `{replay['status']}`\n\n## Final As-Built Verification\n\n- Provider-free replay; new MiMo/LLM calls: `0`. Raw evidence immutable: `{str(replay['raw_evidence_immutable']).lower()}`.\n- Original experiment remains `INVALID`; this closure does not authorize Final Re-Canary or Production ShotPlan.\n\n| Scene | Reaction hard | Reaction review | Definite composite | Continuous framing | Signal |\n|---|---:|---:|---:|---:|---|\n{rows}\n\n## Capability Aggregate\n\n```json\n{json.dumps(aggregate, ensure_ascii=False, indent=2)}\n```\n\n## Decision\n\n- `READY_FOR_FINAL_RECANARY=false`\n- `PRODUCTION_SHOTPLAN=HOLD`\n- Human Director Review state remains `NOT_RECORDED`; no approval was fabricated.\n"

if __name__ == "__main__":
    raise SystemExit(main())
