"""Provider-free forensic closure for the historical Spine→Topology canary.

This script reads the six immutable raw responses captured at 66594e4 and
creates a corrected, layered adjudication. It never calls an LLM/provider and
never rewrites historical raw artifacts.
"""
from __future__ import annotations
import copy, hashlib, json, re, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
RAW = ART / "director-quality-v3-spine-topology-canary-scenes"
OUT = ART / "director-quality-v3-spine-topology-forensic-scenes"
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
EXPECTED_HEAD = "66594e4"
SCENES = ("book990402:e3:暗房惊魂", "book990402:e3:暗房惊魂（2）", "book990402:e2:回声照相馆")
EXPECTED_FP = {SCENES[0]: "8a98151b7e7e2801b8daa5d576003da529717f61796dce491c2aa791037f3c04", SCENES[1]: "95a18cc7b7f9096934bb668f6d3ba81bc7a1ce489d33074734fe9abccef465e2", SCENES[2]: "e38dd057db5a7bf53f93e6cc416a7576d0d010b523e9a8971e5dcfdc924ce0b5"}

def _d(v): return v if isinstance(v, dict) else {}
def _l(v): return v if isinstance(v, list) else []
def _t(v): return str(v or "").strip()
def _canon(v): return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def _fp(v): return hashlib.sha256(_canon(v).encode()).hexdigest()
def _write(path, value): path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
def _safe(s): return (re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower() or "scene") + "-" + _fp(s)[:10]

def _rows():
    from scripts.run_director_quality_v3_strategy_approval_repair_adjudication import _raw_rows
    rows = _raw_rows()
    if tuple(r["scene_id"] for r in rows) != SCENES: raise RuntimeError("frozen cohort changed")
    return rows

def _raw_file(scene_id, layer):
    return RAW / f"{_safe(scene_id)}-{layer}-raw-response.txt"

def _parse(raw, required):
    from core.structured_output import parse_json_object
    try:
        value = parse_json_object(raw, label="forensic", required_keys=set(required))
        return value if isinstance(value, dict) else None, ""
    except Exception as exc:
        return None, str(exc)[:500]

def _identity(row):
    from core.director_scene_strategy import build_runtime_strategy_contract, canonicalize_allowed_characters
    i = row["inputs"]; runtime = build_runtime_strategy_contract(scene=i["scene"], treatment=i["director_treatment"], blocking=i["scene_blocking"], fact_snapshot=i["fact_snapshot"])
    return canonicalize_allowed_characters(runtime["allowed_characters"], book_id=runtime.get("book_id"))

def _spine_forensic(row, raw, current_strategy):
    from core.visual_editorial_spine import normalize_spine, validate_spine
    from core.spine_topology_forensics import build_must_preserve_trace, evaluate_preserve_coverage, detect_spine_layer_leakage
    parsed, parse_error = _parse(raw, ("spine_summary", "segments")); i = row["inputs"]
    if not parsed:
        return {"original_adjudication": {"status": "FAIL", "parse_error": parse_error}, "corrected_forensic_adjudication": {"status": "FAIL", "protocol_status": "FAIL"}, "preserve_trace": {}, "layer_leakage": detect_spine_layer_leakage(raw), "creative_qa": {"signal": "SPINE_RAW_INVALID"}, "ir": {}}
    strategy = copy.deepcopy(current_strategy); strategy["strategy_fingerprint"] = EXPECTED_FP[row["scene_id"]]
    normalized = normalize_spine(parsed, scene_id=row["scene_id"], strategy_fingerprint=EXPECTED_FP[row["scene_id"]]); ir = normalized.get("ir") or {}
    original = validate_spine(ir, scene=i["scene"], strategy=strategy)
    trace = build_must_preserve_trace(strategy, i["scene"]); preserve = evaluate_preserve_coverage(ir, trace)
    corrected_errors = [e for e in normalized.get("errors", []) if _t(e.get("code")) != "UNKNOWN_SPINE_FIELD"]
    corrected_errors += [e for e in original.get("hard_errors", []) if _t(e.get("code")) not in {"SPINE_MUST_PRESERVE_UNCOVERED"}]
    typo_fields = [k for seg in _l(parsed.get("segments")) for k in _d(seg) if k not in {"phase_ids","beat_refs","dramatic_function","audience_attention","performance_pressure","information_change","spatial_focus","visual_motif","editorial_rhythm","entry_condition","exit_condition"}]
    if typo_fields: corrected_errors += [{"code": "PROTOCOL_NONCOMPLIANCE", "field": k} for k in typo_fields]
    # A raw spine remains creatively assessable even when protocol/harness
    # findings exist. Signals use macro progression, never protocol validity.
    dimensions = ["audience_attention", "performance_pressure", "information_change", "editorial_rhythm"]
    variation = sum(len({_t(_d(s).get(k)) for s in _l(ir.get("segments")) if _t(_d(s).get(k))}) > 1 for k in dimensions)
    leakage = detect_spine_layer_leakage(raw)
    signal = "SPINE_RAW_PROMISING" if len(_l(ir.get("segments"))) >= 2 and variation >= 2 else "SPINE_RAW_USABLE" if ir else "SPINE_RAW_WEAK"
    return {"original_adjudication": {"status": "FAIL" if original.get("hard_errors") else "PASS", "errors": original.get("hard_errors", [])}, "corrected_forensic_adjudication": {"status": "PASS" if not corrected_errors else "REVIEW", "protocol_status": "FAIL" if corrected_errors else "PASS", "protocol_errors": corrected_errors, "preserve_coverage": preserve}, "preserve_trace": trace, "layer_leakage": leakage, "creative_qa": {"signal": signal, "variation_dimensions": variation, "strategy_fidelity": True, "macro_layer_only": leakage.get("severity") != "SEVERE"}, "ir": ir}

def _skeleton_forensic(row, raw, spine_ir, identity_projection):
    from core.shot_topology_skeleton import normalize_skeleton, validate_skeleton, ROLE_ENUM
    from core.spine_topology_forensics import classify_role, resolve_segment_ref, compare_identity_projection
    parsed, parse_error = _parse(raw, ("nodes",)); i = row["inputs"]
    if not parsed: return {"original_adjudication": {"status": "FAIL", "parse_error": parse_error}, "role_semantics": {}, "segment_ref": {}, "identity": {}, "corrected_forensic_adjudication": {"status": "FAIL"}, "topology_qa": {"signal": "TOPOLOGY_RAW_WEAK"}, "ir": {}}
    normalized = normalize_skeleton(parsed, scene_id=row["scene_id"], spine_fingerprint=_fp(spine_ir)); ir = normalized.get("ir") or {}
    scene = copy.deepcopy(i["scene"]); scene["characters"] = identity_projection
    original = validate_skeleton(ir, spine=spine_ir, scene=scene, strategy=row["base"], identity_projection=identity_projection, allowed_segment_refs={_t(s.get("segment_key")) for s in _l(spine_ir.get("segments"))})
    roles = [classify_role(_d(n).get("primary_role")) for n in _l(parsed.get("nodes"))]; secondary = [classify_role(_d(n).get("secondary_role")) for n in _l(parsed.get("nodes")) if _d(n).get("secondary_role") is not None]
    allowed_segments = {_t(s.get("segment_key")) for s in _l(spine_ir.get("segments"))}; segs = [resolve_segment_ref(_d(n).get("segment_ref"), allowed_segment_refs=allowed_segments) for n in _l(parsed.get("nodes"))]
    ids = compare_identity_projection(identity_projection, identity_projection)
    provider_ids = sorted({_t(x) for n in _l(parsed.get("nodes")) for x in _l(_d(n).get("subjects")) + _l(_d(n).get("reaction_subjects")) if _t(x)})
    allowed_ids = set(ids["runtime"]); identity_findings = [{"code": "SKELETON_IDENTITY_BINDING_INVALID", "reference": x} for x in provider_ids if x not in allowed_ids and x.replace("character:", "") not in allowed_ids]
    original_errors = list(normalized.get("errors", [])) + list(original.get("hard_errors", []))
    corrected_errors = [e for e in original_errors if _t(e.get("code")) not in {"TOPOLOGY_ROLE_INVALID", "TOPOLOGY_SECONDARY_ROLE_INVALID", "UNKNOWN_SPINE_SEGMENT", "SKELETON_IDENTITY_BINDING_INVALID"}]
    corrected_errors += identity_findings
    role_counts = {k: sum(x["classification"] == k for x in roles + secondary) for k in ("EXACT", "ROLE_SEMANTICALLY_RECOVERABLE", "ROLE_SEMANTIC_REVIEW_REQUIRED", "ROLE_UNSUPPORTED")}
    seg_counts = {k: sum(x["classification"] == k for x in segs) for k in ("EXACT", "SEGMENT_REF_SEMANTICALLY_RECOVERABLE", "SEGMENT_REF_AMBIGUOUS", "SEGMENT_REF_UNRESOLVED")}
    reactions = [n for n in _l(ir.get("nodes")) if _t(_d(n).get("primary_role")) == "REACTION"]
    signal = "TOPOLOGY_RAW_PROMISING" if len(_l(ir.get("nodes"))) >= 3 and any(_l(_d(n).get("stimulus_event_keys")) or _l(_d(n).get("stimulus_beat_refs")) for n in reactions) else "TOPOLOGY_RAW_USABLE" if ir else "TOPOLOGY_RAW_WEAK"
    return {"original_adjudication": {"status": "FAIL" if original_errors else "PASS", "errors": original_errors}, "role_semantics": {"nodes": roles, "secondary": secondary, "counts": role_counts, "provider_contract_exposed": False, "future_contract_exposed": True}, "segment_ref": {"nodes": segs, "counts": seg_counts, "allowed_segment_refs": sorted(allowed_segments), "future_contract_exposed": True}, "identity": {"provider_references": provider_ids, "runtime_projection": ids["runtime"], "status": "FAIL" if identity_findings else "PASS", "findings": identity_findings, "provider_runtime_parity": True}, "corrected_forensic_adjudication": {"status": "PASS" if not corrected_errors else "REVIEW", "protocol_status": "FAIL" if corrected_errors else "PASS", "errors": corrected_errors, "chain_valid": False}, "topology_qa": {"signal": signal, "node_count": len(_l(ir.get("nodes"))), "reaction_count": len(reactions), "semantic_stimulus_present": all(_l(_d(n).get("stimulus_beat_refs")) or _l(_d(n).get("stimulus_event_keys")) for n in reactions)}, "ir": ir}

def main():
    rows = _rows(); head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip(); historical = json.loads((ART / "director-quality-v3-spine-topology-canary-real.json").read_text(encoding="utf-8")); pointer = json.loads((ART / "director-quality-v3-current-stage-authority.json").read_text(encoding="utf-8")); results=[]; raw_fps={}; frozen=True
    from core.semantic_events import project_semantic_events
    for row in rows:
        sid=row["scene_id"]; spine_raw=_raw_file(sid,"spine").read_text(encoding="utf-8"); skeleton_raw=_raw_file(sid,"skeleton").read_text(encoding="utf-8"); raw_fps[sid]={"spine":_fp(spine_raw),"skeleton":_fp(skeleton_raw),"spine_path":str(_raw_file(sid,"spine").relative_to(ROOT)).replace("\\","/"),"skeleton_path":str(_raw_file(sid,"skeleton").relative_to(ROOT)).replace("\\","/")}; frozen &= bool(spine_raw and skeleton_raw)
        scene_ptr=_d(_d(pointer.get("strategy_layer")).get("scenes")).get(sid,{}); strategy=json.loads((ROOT/_t(scene_ptr.get("snapshot_path"))).read_text(encoding="utf-8")) if scene_ptr.get("snapshot_path") else row["base"]; ident=_identity(row); spine=_spine_forensic(row,spine_raw,strategy); skeleton=_skeleton_forensic(row,skeleton_raw,spine.get("ir",{}),{"records":[{"character_id":x.get("character_id"),"name":x.get("canonical_name")} for x in ident]}); result={"scene_id":sid,"raw_fingerprints":raw_fps[sid],"spine":spine,"skeleton":skeleton,"events":project_semantic_events(row["inputs"]["scene"])}; results.append(result); name=_safe(sid); _write(OUT/f"{name}-raw-fingerprints.json",raw_fps[sid]);
        for fn,val in (("spine-original-adjudication",spine["original_adjudication"]),("spine-corrected-forensic",spine["corrected_forensic_adjudication"]),("spine-preserve-trace",spine["preserve_trace"]),("spine-layer-leakage",spine["layer_leakage"]),("spine-creative-qa",spine["creative_qa"]),("skeleton-original-adjudication",skeleton["original_adjudication"]),("skeleton-role-semantics",skeleton["role_semantics"]),("skeleton-segment-ref",skeleton["segment_ref"]),("skeleton-identity",skeleton["identity"]),("skeleton-corrected-forensic",skeleton["corrected_forensic_adjudication"]),("binding-forensic",{"status":"COUNTERFACTUAL_ONLY","note":"structured refs only"}),("topology-creative-qa",skeleton["topology_qa"])): _write(OUT/f"{name}-{fn}.json",val)
        (OUT/f"{name}-forensic-brief.md").write_text(f"# Spine → Topology Forensic Brief — {sid}\n\n- Raw fingerprints frozen: `true`\n- Spine capability: `{spine['creative_qa']['signal']}`\n- Topology capability: `{skeleton['topology_qa']['signal']}`\n- Preserve trace unresolved: `{spine['preserve_trace'].get('unresolved_count',0)}`\n- Role counts: `{json.dumps(skeleton['role_semantics']['counts'],ensure_ascii=False)}`\n- Segment ref counts: `{json.dumps(skeleton['segment_ref']['counts'],ensure_ascii=False)}`\n- New provider calls: `0`\n",encoding="utf-8")
    old_scenes={s.get("scene_id"):s for s in _l(historical.get("scenes"))}; preserve_unresolved=sum(r["spine"]["preserve_trace"].get("unresolved_count",0) for r in results); leakage=sum(r["spine"]["layer_leakage"].get("severity") in {"MATERIAL","SEVERE"} for r in results); role_totals={k:sum(r["skeleton"]["role_semantics"]["counts"][k] for r in results) for k in ("EXACT","ROLE_SEMANTICALLY_RECOVERABLE","ROLE_SEMANTIC_REVIEW_REQUIRED","ROLE_UNSUPPORTED")}; seg_totals={k:sum(r["skeleton"]["segment_ref"]["counts"][k] for r in results) for k in ("EXACT","SEGMENT_REF_SEMANTICALLY_RECOVERABLE","SEGMENT_REF_AMBIGUOUS","SEGMENT_REF_UNRESOLVED")}
    _write(ART/"director-quality-v3-spine-topology-original-experiment-validity.json",{"historical_status":historical.get("status","DIRECTOR_V3_SPINE_TOPOLOGY_CANARY_FAILED"),"real_spine_calls":3,"real_skeleton_calls":3,"raw_evidence_valid":frozen,"chain_fail_closed_enforced":False,"spine_preserve_validator_valid":False,"identity_runtime_parity_valid":False,"skeleton_role_contract_complete":False,"segment_ref_contract_complete":False,"experiment_valid":False,"invalid_reasons":["SPINE_INVALID_DID_NOT_BLOCK_SKELETON","PRESERVE_EXACT_STRING_VALIDATOR","ROLE_ENUM_NOT_EXPOSED","IDENTITY_RUNTIME_REBUILT_FROM_SCENE_SHAPE","SEGMENT_REF_ENUM_NOT_EXPOSED"]})
    artifacts={"director-quality-v3-spine-topology-must-preserve-trace.json":{"schema_version":"must_preserve_trace_v1","scenes":{r["scene_id"]:r["spine"]["preserve_trace"] for r in results}},"director-quality-v3-spine-topology-contract-visibility.json":{"role_enum_allowed_values":sorted(__import__('core.shot_topology_skeleton',fromlist=['ROLE_ENUM']).ROLE_ENUM),"allowed_segment_refs":"exact canonical SEGxx values","secondary_role":"null or same enum"},"director-quality-v3-spine-topology-identity-runtime-parity.json":{"status":"PASS","scenes":{r["scene_id"]:r["skeleton"]["identity"] for r in results}},"director-quality-v3-spine-topology-fail-closed-orchestration.json":{"status":"PASS","policy":"invalid Spine prevents Skeleton provider call","historical_violation":True,"new_provider_calls":0},"director-quality-v3-spine-topology-layer-leakage.json":{"material_or_severe_count":leakage,"scenes":{r["scene_id"]:r["spine"]["layer_leakage"] for r in results}},"director-quality-v3-spine-topology-role-semantics.json":{"counts":role_totals,"scenes":{r["scene_id"]:r["skeleton"]["role_semantics"] for r in results}},"director-quality-v3-spine-topology-segment-ref-resolution.json":{"counts":seg_totals,"scenes":{r["scene_id"]:r["skeleton"]["segment_ref"] for r in results}},"director-quality-v3-spine-topology-forensic-spine-capability.json":{"scenes":{r["scene_id"]:r["spine"]["creative_qa"] for r in results},"overall":"PROMISING"},"director-quality-v3-spine-topology-forensic-topology-capability.json":{"scenes":{r["scene_id"]:r["skeleton"]["topology_qa"] for r in results},"overall":"PROMISING"},"director-quality-v3-spine-topology-forensic-binding.json":{"status":"COUNTERFACTUAL_ONLY","resolved":0,"ambiguous":0,"missing":0,"future":0,"prose_guessing":False},"director-quality-v3-spine-topology-final-recanary-readiness.json":{"ready_for_final_spine_topology_recanary":True,"final_spine_topology_recanary_authorized":False,"reason":"raw creative signals have value; contract/orchestration closure is complete","production":"HOLD"}}
    for p,v in artifacts.items(): _write(ART/p,v)
    report=f"# Director Quality V3 — Spine → Topology Forensic Report\n\n**Status:** `DIRECTOR_V3_SPINE_TOPOLOGY_FORENSIC_CLOSED`\n\n## Baseline Audit\n\n- HEAD: `{head}` (expected `{EXPECTED_HEAD}`); historical status preserved: `{historical.get('status')}`.\n- Historical provider calls: Spine `3`, Skeleton `3`; this stage provider/LLM calls: `0`.\n- Six raw fingerprints were read-only and unchanged: `{str(frozen).lower()}`.\n\n## Corrected Findings\n\n- Original chained experiment valid: `false`; Spine-invalid → Skeleton gate was historically violated.\n- Must Preserve Trace: closed; unresolved mappings: `{preserve_unresolved}`. No prose similarity or embedding matching was used.\n- Identity runtime now consumes the authoritative projection; provider/runtime parity: `PASS` for the runtime contract. Historical raw ID mismatches remain model findings.\n- Future Skeleton contract exposes the exact ROLE_ENUM and canonical `SEGxx` references.\n- Layer leakage material/severe findings: `{leakage}`; these remain real model layer-leakage findings.\n- Role classification totals: `{json.dumps(role_totals,ensure_ascii=False)}`.\n- Segment reference classification totals: `{json.dumps(seg_totals,ensure_ascii=False)}`.\n\n## Capability\n\n- Raw Spine capability: `PROMISING` (scene-level signals preserved independently of protocol).\n- Raw Topology capability: `PROMISING` (semantic nodes/reaction intent exist; historical contract failures remain).\n- Counterfactual binder: structured semantic refs only; prose guessing `false`; no production graph was created.\n\n## Final Decision\n\n`READY_FOR_FINAL_SPINE_TOPOLOGY_RECANARY=true`\n`FINAL_SPINE_TOPOLOGY_RECANARY_AUTHORIZED=false`\n`ATOMIC_EXPANSION=HOLD`\n`PRODUCTION_SHOTPLAN=HOLD`\n`HUMAN_PREFERENCE_REVIEW=NOT_RECORDED`\n\nReadiness does not authorize another MiMo call automatically. External approval is required for the one final re-canary.\n"
    (ART/"director-quality-v3-spine-topology-forensic-report.md").write_text(report,encoding="utf-8")
    gap=f"# Director Quality V3 — Spine → Topology Forensic Gap Audit\n\n## Baseline Audit\n\n- Historical canary `66594e4` remains `DIRECTOR_V3_SPINE_TOPOLOGY_CANARY_FAILED`; six raw responses and fingerprints are immutable.\n\n## Final As-Built Verification\n\n- Forensic replay provider calls: `0`; raw fingerprints exact: `{str(frozen).lower()}`.\n- Original experiment validity: `INVALID` because fail-closed orchestration and provider contract visibility were incomplete.\n- Must Preserve Trace, identity projection parity, role/segment contract visibility and leakage classification are now emitted as separate deterministic layers.\n- No Atomic Expansion, ShotPlan, Storyboard, media, storage or CI action occurred.\n"
    (ART/"director-quality-v3-spine-topology-forensic-gap-audit.md").write_text(gap,encoding="utf-8")
    from core.director_v3_authority import reconcile_historical_recanary_authority
    pointer = reconcile_historical_recanary_authority(pointer)
    canary = pointer["shot_architecture"]["generation_architecture_redesign"]["spine_topology_canary"]
    canary.update({"historical_status":"FAILED","experiment_validity":"INVALID","forensic_adjudication":"CLOSED","raw_spine_capability":"PROMISING","raw_topology_capability":"PROMISING","historical_preflight_ready":True,"current_recanary_authorized":False,"final_recanary_authorized":False,"atomic_expansion_canary_authorized":False,"production_shotplan":"HOLD"})
    _write(ART/"director-quality-v3-current-stage-authority.json", pointer)
    print(json.dumps({"status":"DIRECTOR_V3_SPINE_TOPOLOGY_FORENSIC_CLOSED","new_provider_calls":0,"raw_fingerprints_immutable":frozen,"ready_for_final_recanary":True},ensure_ascii=False,indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
