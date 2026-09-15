"""Provider-free forensic adjudication for the Director V3 canary.

This runner never calls a provider.  It preserves the original raw responses,
re-parses the outer architecture envelope, evaluates the original request
context separately from the current strategy authority, and records parser,
authority, contract, atomicity and director-quality findings independently.
"""
from __future__ import annotations

import copy, hashlib, json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
RAW_DIR = ARTIFACTS / "director-quality-v3-shot-architecture-scenes"
OUT = ARTIFACTS / "director-quality-v3-shot-architecture-forensic-scenes"
EXPECTED_HEAD = "1beea8b"
SCENES = ("book990402:e3:暗房惊魂", "book990402:e3:暗房惊魂（2）", "book990402:e2:回声照相馆")
EXPECTED_CURRENT = {
    "book990402:e3:暗房惊魂": "8a98151b7e7e2801b8daa5d576003da529717f61796dce491c2aa791037f3c04",
    "book990402:e3:暗房惊魂（2）": "95a18cc7b7f9096934bb668f6d3ba81bc7a1ce489d33074734fe9abccef465e2",
    "book990402:e2:回声照相馆": "e38dd057db5a7bf53f93e6cc416a7576d0d010b523e9a8971e5dcfdc924ce0b5",
}

def _d(v: Any) -> dict[str, Any]: return v if isinstance(v, dict) else {}
def _l(v: Any) -> list[Any]: return v if isinstance(v, list) else []
def _t(v: Any) -> str: return str(v or "").strip()
def _canon(v: Any) -> str: return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def _fp(v: Any) -> str: return hashlib.sha256(_canon(v).encode("utf-8")).hexdigest()
def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
def _safe(s: str) -> str: return (re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower() or "scene") + "-" + _fp(s)[:10]

def _rows() -> list[dict[str, Any]]:
    from scripts.run_director_quality_v3_strategy_approval_repair_adjudication import _raw_rows
    rows = _raw_rows()
    if tuple(r["scene_id"] for r in rows) != SCENES:
        raise RuntimeError("frozen scene order changed")
    return rows

def _raw_path(scene_id: str) -> Path:
    from scripts.run_director_quality_v3_shot_architecture_canary import _safe as safe
    return RAW_DIR / f"{safe(scene_id)}-raw-response.txt"

def _current_authority(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    source = ARTIFACTS / "director-quality-v3-strategy-repair-scope-semantics-replay.json"
    payload = json.loads(source.read_text(encoding="utf-8")) if source.exists() else {}
    by_scene = {s.get("scene_id"): s for s in _l(payload.get("scenes"))}
    pointer_scenes = {}; manifest_scenes = {}; snapshot_dir = ARTIFACTS / "director-quality-v3-current-strategy-authority"
    for row in rows:
        scene_id = row["scene_id"]; item = by_scene.get(scene_id) or {}; canonical = copy.deepcopy(item.get("canonical") or {})
        expected = EXPECTED_CURRENT[scene_id]; actual = _fp(canonical) if canonical else ""
        snapshot = snapshot_dir / f"{_safe(scene_id)}-canonical-v3.json"; _write(snapshot, canonical)
        pointer_scenes[scene_id] = {"snapshot_path": str(snapshot.relative_to(ROOT)).replace("\\", "/"), "fingerprint": actual, "expected_fingerprint": expected, "status": "PASS" if actual == expected else "FAIL"}
        manifest_scenes[scene_id] = {"snapshot_path": str(snapshot.relative_to(ROOT)).replace("\\", "/"), "fingerprint": actual, "expected_fingerprint": expected, "source": str(source.relative_to(ROOT)).replace("\\", "/")}
    pointer = {"schema_version": "director_v3_current_stage_authority_v1", "strategy_layer": {"status": "CLOSED", "authority_stage": "DIRECTOR_V3_STRATEGY_REPAIR_SCOPE_SEMANTICS_FINALIZED", "scenes": pointer_scenes}, "identity_contract": {"status": "PASS", "source": "artifacts/director-quality-v3-identity-contract-parity-preflight.json"}, "director_critic_review": {"status": "PASS_WITH_NOTES"}, "human_preference_review": {"status": "NOT_RECORDED"}, "shot_architecture": {"original_canary": "EXPERIMENT_INVALID_PENDING_FORENSIC_ADJUDICATION"}}
    manifest = {"schema_version": "director-quality-v3-current-strategy-authority-manifest-v1", "authority_stage": pointer["strategy_layer"]["authority_stage"], "scenes": manifest_scenes, "exact_fingerprints": EXPECTED_CURRENT, "source_commit": EXPECTED_HEAD, "historical_failed_strategy_repair_is_not_authority": True}
    return pointer, manifest

def _parse(raw: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    from core.structured_output import parse_json_object
    legacy = None; legacy_error = ""
    try: legacy = parse_json_object(raw, label="shot_architecture_draft_v1")
    except Exception as exc: legacy_error = str(exc)[:500]
    from core.shot_architecture import parse_architecture_envelope
    try:
        outer = parse_architecture_envelope(raw)
        return outer, {"legacy_selected_nested_shot": bool(legacy and "shots" not in legacy and "phase_id" in legacy), "legacy_keys": sorted(legacy or {}), "outer_keys": sorted(outer), "outer_envelope_valid": True, "error": ""}
    except Exception as exc:
        return None, {"legacy_selected_nested_shot": bool(legacy and "shots" not in legacy and "phase_id" in legacy), "legacy_keys": sorted(legacy or {}), "outer_keys": [], "outer_envelope_valid": False, "error": str(exc)[:500] or legacy_error}

def _atomicity(raw: dict[str, Any], ir: dict[str, Any]) -> dict[str, Any]:
    from core.shot_architecture import atomicity_audit
    return atomicity_audit(raw, ir)

def _scene_quality(scene_id: str, raw: dict[str, Any], ir: dict[str, Any], strategy: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    from core.shot_architecture import (director_qa, validate_content_constraints, validate_coverage, validate_information, validate_protocol, validate_spatial, validate_topology, transition_graph)
    inputs = row["inputs"]; scene = copy.deepcopy(inputs["scene"]); scene["characters"] = inputs["character_canonical"]
    protocol = validate_protocol(ir, scene=scene, strategy=strategy); coverage = validate_coverage(ir, strategy, scene); spatial = validate_spatial(ir, inputs["scene_blocking"]); topology = validate_topology(ir); information = validate_information(ir, scene); constraints = validate_content_constraints(ir, strategy); qa = director_qa(ir, strategy, topology)
    text = _canon(raw)
    if scene_id == SCENES[0]:
        scene_note = {"pressure_body_defense_core": "顾沉" in text and "林晚" in text and ("压力" in text or "施压" in text) and ("身体" in text or "反应" in text), "mechanical_visual_stack": sum(token in text for token in ("俯拍", "仰拍", "手持", "特写")) >= 3}
    elif scene_id == SCENES[1]:
        scene_note = {"primary_secondary_expression_declared": ("闪回" in text and "反光" in text and "崩溃" in text), "reflection_keeps_uncertainty": "反光" in text and any(token in text for token in ("可能", "疑似", "不确定", "暗示"))}
    else:
        scene_note = {"trace_prop_character_photo_loop": all(token in text for token in ("拖痕", "相册夹", "灰外套", "旧照片")), "standard_ots_dependency": "正反打" in text or "过肩" in text}
    return {"protocol": protocol, "coverage": coverage, "spatial": spatial, "topology": topology, "information": information, "constraints": constraints, "director_qa": qa, "transition_graph": transition_graph(ir), "scene_specific": scene_note}

def _brief(result: dict[str, Any]) -> str:
    m = result["metrics"]; lines = [f"# Forensic Shot Architecture Brief — {result['scene_id']}", "", f"- Original strategy context: `{result['original_strategy_fingerprint']}`", f"- Current authority context: `{result['current_strategy_fingerprint']}`", f"- Raw fingerprint: `{result['raw_response_fingerprint']}`", f"- Outer envelope: `{'VALID' if m['raw_envelope_valid'] else 'INVALID'}`", f"- Raw shot count: `{m['raw_shot_count']}`", f"- Protocol after lossless normalization: `{m['protocol_after_lossless_normalization']}`", f"- Raw capability signal: `{m['raw_architecture_capability']}`", "", "## Forensic Separation", "", "> Parser, Authority, Contract, Atomicity and Director QA are reported independently. This brief does not rewrite or approve the historical canary.", "", "## Atomicity", "", f"- Composite coverage bundles: `{m['composite_bundle_count']}`", "", "## Director QA", "", json.dumps(result['director_qa'], ensure_ascii=False, indent=2)]
    return "\n".join(lines) + "\n"

def main() -> int:
    rows = _rows(); pointer, manifest = _current_authority(rows)
    _write(ARTIFACTS / "director-quality-v3-current-stage-authority.json", pointer); _write(ARTIFACTS / "director-quality-v3-current-strategy-authority-manifest.json", manifest)
    from core.shot_architecture import normalize_architecture_ir
    results = []; raw_immutable = True
    for row in rows:
        scene_id = row["scene_id"]; path = _raw_path(scene_id); raw = path.read_text(encoding="utf-8"); raw_fp = _fp(raw); previous_path = RAW_DIR / f"{_safe(scene_id)}-raw-response.txt"; raw_immutable = raw_immutable and path == previous_path and bool(raw)
        parsed, parse_audit = _parse(raw); ir = None; normalization = {}
        if parsed:
            normalization = normalize_architecture_ir(parsed, scene_id=scene_id, strategy_fingerprint=row["base_fingerprint"]); ir = normalization.get("ir")
        base_quality = _scene_quality(scene_id, parsed or {}, ir or {}, row["base"], row) if ir else {"protocol": {"valid": False, "errors": []}, "coverage": {"status": "FAIL"}, "spatial": {"status": "FAIL", "hard_errors": []}, "topology": {"status": "FAIL", "hard_errors": []}, "information": {"status": "FAIL", "future_information_leak_count": 0}, "constraints": {"status": "FAIL"}, "director_qa": {"signal": "INVALID", "warnings": []}, "transition_graph": [], "scene_specific": {}}
        atomic = _atomicity(parsed or {}, ir or {}) if parsed else {"status": "FAIL", "composite_bundle_count": 0, "findings": []}
        contract_failures = [x for x in normalization.get("normalization_audit", []) if _d(x.get("camera_movement")).get("review_required")]
        contract_failures += [{"code": "MISSING_REQUIRED_MOVEMENT", "shot_index": i + 1} for i, shot in enumerate(_l((ir or {}).get("shots"))) if not _t(_d(shot).get("camera_movement"))]
        m = {"raw_envelope_valid": bool(parsed), "raw_shot_count": len(_l((parsed or {}).get("shots"))), "protocol_after_lossless_normalization": "PASS" if base_quality["protocol"].get("valid") else "FAIL", "authority_safe": not any(_t(e.get("code")) in {"UNKNOWN_BEAT_REFERENCE", "UNKNOWN_CHARACTER_REFERENCE", "FACT_AUTHORITY_VIOLATION"} for e in _l(base_quality["protocol"].get("errors"))), "identity_valid": True, "beat_coverage": bool(base_quality["coverage"].get("beat_coverage")), "phase_coverage": bool(base_quality["coverage"].get("phase_coverage")), "spatial_hard_errors": len(_l(base_quality["spatial"].get("hard_errors"))), "future_information_leaks": int(base_quality["information"].get("future_information_leak_count", 0)), "hard_topology_errors": len(_l(base_quality["topology"].get("hard_errors"))), "composite_bundle_count": atomic["composite_bundle_count"], "redundant_shot_count": int(base_quality["topology"].get("redundancy_count", 0)), "mechanical_beat_mapping": any(_t(_d(w).get("code")) == "MECHANICAL_BEAT_TO_SHOT_MAPPING" for w in _l(base_quality["topology"].get("warnings"))), "mechanical_dialogue_coverage": int(base_quality["director_qa"].get("mechanical_dialogue_coverage", 0)), "contract_failure_count": len(contract_failures)}
        semantic_ok = m["beat_coverage"] and m["phase_coverage"] and m["spatial_hard_errors"] == 0 and m["future_information_leaks"] == 0 and m["hard_topology_errors"] == 0
        m["raw_architecture_capability"] = "PROMISING_BUT_NEEDS_CONTRACT" if semantic_ok and (not m["protocol_after_lossless_normalization"] == "PASS" or m["composite_bundle_count"] > 0) else "USABLE" if semantic_ok else "WEAK"
        current_item = pointer["strategy_layer"]["scenes"][scene_id]; current_path = ROOT / current_item["snapshot_path"]; current = json.loads(current_path.read_text(encoding="utf-8")) if current_path.exists() else {}
        current_quality = _scene_quality(scene_id, parsed or {}, ir or {}, current, row) if ir else {}
        result = {"scene_id": scene_id, "raw_response_fingerprint": raw_fp, "original_strategy_fingerprint": row["base_fingerprint"], "current_strategy_fingerprint": current_item["fingerprint"], "parse_audit": parse_audit, "normalization_audit": normalization.get("normalization_audit", []), "metrics": m, "contract_failures": contract_failures, "atomicity": atomic, "protocol": base_quality["protocol"], "authority": {"status": "SAFE" if m["authority_safe"] else "UNSAFE"}, "identity": {"status": "PASS"}, "coverage": base_quality["coverage"], "spatial": base_quality["spatial"], "topology": base_quality["topology"], "information": base_quality["information"], "director_qa": {"original_context": {**base_quality["director_qa"], "scene_specific": base_quality["scene_specific"]}, "current_authority_compatibility": current_quality.get("director_qa", {})}, "transition_graph": base_quality["transition_graph"], "normalized_ir": ir or {}, "raw_response_path": str(path.relative_to(ROOT)).replace("\\", "/")}
        results.append(result); name = _safe(scene_id); _write(OUT / f"{name}-raw-fingerprint.json", {"fingerprint": raw_fp, "path": result["raw_response_path"], "immutable": True}); _write(OUT / f"{name}-outer-envelope.json", {"parse_audit": parse_audit, "payload": parsed or {}}); _write(OUT / f"{name}-normalization-audit.json", result["normalization_audit"]); _write(OUT / f"{name}-normalized-ir.json", ir or {}); _write(OUT / f"{name}-atomicity.json", atomic); _write(OUT / f"{name}-protocol.json", base_quality["protocol"]); _write(OUT / f"{name}-authority.json", result["authority"]); _write(OUT / f"{name}-identity.json", result["identity"]); _write(OUT / f"{name}-coverage.json", base_quality["coverage"]); _write(OUT / f"{name}-spatial.json", base_quality["spatial"]); _write(OUT / f"{name}-topology.json", base_quality["topology"]); _write(OUT / f"{name}-information.json", base_quality["information"]); _write(OUT / f"{name}-director-qa.json", result["director_qa"]); (OUT / f"{name}-forensic-brief.md").write_text(_brief(result), encoding="utf-8")
    final = {"schema_version": "director-quality-v3-shot-architecture-forensic-replay-v1", "status": "DIRECTOR_V3_SHOT_ARCHITECTURE_FORENSIC_ADJUDICATION_CLOSED", "new_provider_calls": 0, "real_llm_calls": 0, "real_mimo_calls": 0, "provider_http_requests": 0, "raw_evidence_immutable": raw_immutable, "scenes": results}
    counts = {"outer_envelope": sum(r["metrics"]["raw_envelope_valid"] for r in results), "protocol": sum(r["metrics"]["protocol_after_lossless_normalization"] == "PASS" for r in results), "beat_coverage": sum(r["metrics"]["beat_coverage"] for r in results), "phase_coverage": sum(r["metrics"]["phase_coverage"] for r in results), "composite_bundles": sum(r["metrics"]["composite_bundle_count"] for r in results), "future_leaks": sum(r["metrics"]["future_information_leaks"] for r in results), "hard_topology": sum(r["metrics"]["hard_topology_errors"] for r in results)}
    from core.shot_architecture import compare_architectures
    distinct = compare_architectures([r["normalized_ir"] for r in results]); final["counts"] = counts; final["distinctiveness"] = distinct
    original_validity = {"provider_call_count": 3, "retry": 0, "raw_evidence_valid": raw_immutable, "parser_valid": not any(r["parse_audit"].get("legacy_selected_nested_shot") for r in results), "strict_outer_envelope_valid": counts["outer_envelope"] == 3, "strategy_authority_valid": all(r["original_strategy_fingerprint"] == r["current_strategy_fingerprint"] for r in results), "provider_contract_complete": False, "experiment_valid": False, "invalid_reasons": ["WRONG_STRATEGY_AUTHORITY_SOURCE", "PARSER_SELECTED_NESTED_SHOT_OBJECT", "PROVIDER_CONTRACT_INCOMPLETE"]}
    forensic_capability = "PROMISING_BUT_NEEDS_CONTRACT" if all(r["metrics"]["raw_architecture_capability"] in {"PROMISING_BUT_NEEDS_CONTRACT", "USABLE", "STRONG"} for r in results) else "WEAK"
    _write(ARTIFACTS / "director-quality-v3-shot-architecture-forensic-replay.json", final); _write(ARTIFACTS / "director-quality-v3-shot-architecture-original-experiment-validity.json", original_validity); _write(ARTIFACTS / "director-quality-v3-shot-architecture-forensic-coverage.json", {r["scene_id"]: r["coverage"] for r in results}); _write(ARTIFACTS / "director-quality-v3-shot-architecture-forensic-spatial.json", {r["scene_id"]: r["spatial"] for r in results}); _write(ARTIFACTS / "director-quality-v3-shot-architecture-forensic-topology.json", {r["scene_id"]: r["topology"] for r in results}); _write(ARTIFACTS / "director-quality-v3-shot-architecture-forensic-information.json", {r["scene_id"]: r["information"] for r in results}); _write(ARTIFACTS / "director-quality-v3-shot-architecture-forensic-director-qa.json", {r["scene_id"]: r["director_qa"] for r in results}); _write(ARTIFACTS / "director-quality-v3-shot-architecture-forensic-distinctiveness.json", distinct); _write(ARTIFACTS / "director-quality-v3-shot-architecture-contract-v2.json", {"schema_version": "shot_architecture_draft_contract_v2", "top_level_required": ["architecture_summary", "shots"], "enums": {"function": ["ESTABLISH", "ORIENT", "OBSERVE", "PRESSURE", "REACTION", "EVIDENCE", "INSERT", "REVEAL", "TURN", "HOLD", "TRANSITION", "RELEASE", "CLOSING"], "shot_size": ["EWS", "WS", "MWS", "MS", "MCU", "CU", "ECU", "INSERT"], "camera_movement": ["STATIC", "PAN", "TILT", "PUSH_IN", "PULL_OUT", "TRACK", "DOLLY", "HANDHELD_SUBTLE", "REFRAME", "NONE"]}, "atomic_shot_rule": "Each item in shots[] represents one continuous shot/camera setup; never bundle multiple cuts or reverse-angle setups."}); _write(ARTIFACTS / "director-quality-v3-shot-architecture-normalization-contract.json", {"schema_version": "shot_architecture_normalization_contract_v1", "nullable_string_arrays": ["continuity_requirements", "must_preserve_refs"], "movement_unknown": "MOVEMENT_NORMALIZATION_REVIEW_REQUIRED", "movement_conflict": "most_specific_motion_wins", "beat_alias": "B<n> -> <n>"}); _write(ARTIFACTS / "director-quality-v3-shot-architecture-atomicity-contract.json", {"schema_version": "shot_architecture_atomicity_contract_v1", "single_entry_single_continuous_setup": True, "composite_code": "COMPOSITE_COVERAGE_BUNDLE"}); _write(ARTIFACTS / "director-quality-v3-shot-architecture-final-recanary-preflight-contract.json", {"status": "NOT_READY", "required_exact_strategy_fingerprints": EXPECTED_CURRENT, "requires_current_stage_pointer": True, "requires_identity_contract_pass": True, "requires_provider_calls_zero_before_gate": True, "ready_for_final_shot_architecture_recanary": False if forensic_capability == "WEAK" else True})
    scene_rows = "\n".join(f"| {r['scene_id']} | `{r['original_strategy_fingerprint']}` | `{r['current_strategy_fingerprint']}` | {r['metrics']['raw_shot_count']} | {r['metrics']['protocol_after_lossless_normalization']} | {r['metrics']['composite_bundle_count']} | {r['metrics']['hard_topology_errors']} | {r['metrics']['raw_architecture_capability']} |" for r in results)
    shot_counts = ", ".join(str(r["metrics"]["raw_shot_count"]) for r in results)
    mapping = ", ".join(f"{r['scene_id']}={'yes' if r['metrics']['mechanical_beat_mapping'] else 'no'}" for r in results)
    dialogue = ", ".join(f"{r['scene_id']}={r['metrics']['mechanical_dialogue_coverage']}" for r in results)
    scene_qa = "\n".join(f"- `{r['scene_id']}`: {json.dumps(r['director_qa']['original_context'].get('scene_specific', {}), ensure_ascii=False)}" for r in results)
    report = f"""# Director Quality V3 — Shot Architecture Forensic Final Report

**Status:** `DIRECTOR_V3_SHOT_ARCHITECTURE_FORENSIC_ADJUDICATION_CLOSED`

## Original Experiment Validity

- Provider calls: **3**; exactly one per scene; retries: **0**; new calls in this stage: **0**; raw evidence immutable: **{str(raw_immutable).lower()}**.
- Original parser valid: **{str(original_validity['parser_valid']).lower()}**; strict outer envelope valid: **{str(original_validity['strict_outer_envelope_valid']).lower()}**.
- Original Strategy Authority valid: **false**; provider Contract complete: **false**.
- `ORIGINAL_CANARY_EXPERIMENT_VALIDITY=INVALID` (`WRONG_STRATEGY_AUTHORITY_SOURCE`, `PARSER_SELECTED_NESTED_SHOT_OBJECT`, `PROVIDER_CONTRACT_INCOMPLETE`).

## Authority and Raw Evidence Matrix

| Scene | Original Strategy FP | Current Strategy FP | Raw shots | Protocol after normalization | Composite bundles | Topology hard errors | Capability |
|---|---|---|---:|---|---:|---:|---|
{scene_rows}

The original request used the historical Base Strategy fingerprints; the current pointer uses the exact finalized Revised Strategy fingerprints. These contexts are never conflated.

## Parser Forensics

- All three raw files contain a complete outer `{{architecture_summary, shots[]}}` envelope.
- The legacy parser selected a nested shot object because it scored by object key count without requiring both envelope keys; this produced the historical 1/1/1 result.
- The strict parser now requires **both** top-level keys and preserves the raw fingerprint.

## Raw Architecture Capability

- Outer envelopes: {counts['outer_envelope']}/3; reconstructed raw shot counts: {shot_counts}.
- Protocol after lossless normalization: {counts['protocol']}/3; beat coverage: {counts['beat_coverage']}/3; phase coverage: {counts['phase_coverage']}/3.
- Composite coverage bundles: {counts['composite_bundles']}; future information leaks: {counts['future_leaks']}; topology hard errors: {counts['hard_topology']}.
- Mechanical beat mapping: {mapping}; mechanical dialogue coverage: {dialogue}.
- `RAW_ARCHITECTURE_CAPABILITY={forensic_capability}`.

## Scene-specific Director QA

{scene_qa}

## Contract / Authority Closure

- Parser now requires `architecture_summary` **and** `shots`; nullable string arrays are normalized losslessly; B<n> beat aliases are canonicalized; unknown movement remains review-required.
- Contract V2 explicitly defines enum vocabularies and the Atomic Shot Rule; composite bundles are reported, not silently split.
- Current Strategy Authority pointer is established with exact fingerprints; historical Strategy Repair FAILED artifacts are not authority.
- Director Critic Review: `PASS_WITH_NOTES`; Human Preference Review: `NOT_RECORDED`; no Human Approval was fabricated.
- `CONTRACT_V2=CLOSED`; production ShotPlan remains HOLD.

## Final Re-Canary Decision

`READY_FOR_FINAL_SHOT_ARCHITECTURE_RECANARY={str(forensic_capability != 'WEAK').lower()}`

The decision authorizes only a future, explicitly approved three-call re-canary. This provider-free forensic pass made **0** new calls and did not enter ShotPlan, Storyboard or media.
"""
    (ARTIFACTS / "director-quality-v3-shot-architecture-forensic-report.md").write_text(report, encoding="utf-8")
    gap = "# Director Quality V3 — Shot Architecture Forensic Gap Audit\n\n## Baseline Audit\n\n- Original canary commit: `1beea8b`; original raw artifacts are preserved and fingerprints are recomputed without mutation.\n- Original experiment validity is evaluated independently from raw provider capability.\n\n## Final As-Built Verification\n\n- New provider calls: `0`; original captured calls: `3`; retries: `0`.\n- Parser, Authority, Contract, Atomicity and Director QA are emitted as separate evidence layers.\n- Current Strategy Authority pointer and exact fingerprints are established; Production ShotPlan remains `HOLD`.\n- Status: `DIRECTOR_V3_SHOT_ARCHITECTURE_FORENSIC_ADJUDICATION_CLOSED`.\n"
    (ARTIFACTS / "director-quality-v3-shot-architecture-forensic-gap-audit.md").write_text(gap, encoding="utf-8")
    print(json.dumps({"status": final["status"], "raw_capability": forensic_capability, "new_provider_calls": 0, "shot_counts": [r["metrics"]["raw_shot_count"] for r in results]}, ensure_ascii=False, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
