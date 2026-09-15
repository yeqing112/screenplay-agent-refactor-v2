"""Final three-scene real MiMo Shot Architecture re-canary.

The run is intentionally one-shot-per-scene: requests are frozen before any
provider call, transport/semantic/format retries are disabled, and no repair
or downstream production side effect is allowed.
"""
from __future__ import annotations
import copy, hashlib, json, re, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
OUT = ARTIFACTS / "director-quality-v3-final-shot-architecture-recanary-scenes"
EXPECTED_HEAD = "4e26dc1"
SCENES = ("book990402:e3:暗房惊魂", "book990402:e3:暗房惊魂（2）", "book990402:e2:回声照相馆")
EXPECTED_STRATEGIES = {
    SCENES[0]: "8a98151b7e7e2801b8daa5d576003da529717f61796dce491c2aa791037f3c04",
    SCENES[1]: "95a18cc7b7f9096934bb668f6d3ba81bc7a1ce489d33074734fe9abccef465e2",
    SCENES[2]: "e38dd057db5a7bf53f93e6cc416a7576d0d010b523e9a8971e5dcfdc924ce0b5",
}
SYSTEM_PROMPT = """You are designing the final shot architecture for an already approved scene directing strategy.
Design the scene as a coherent visual and editorial system. Each item in shots[] MUST represent exactly one continuous camera setup/take.
Never bundle shot-reverse-shot coverage, multiple camera angles, multiple cuts, or A/B coverage into one shot object. If another angle or reaction is required, create another shot entry.
You may add, remove, split, merge, or reorder shots, but may not alter story facts, character identities, beat chronology, blocking truth, or approved directing strategy. Do not mechanically map one beat to one shot or default to generic shot-reverse-shot dialogue coverage.
Every shot must have a dramatic, performance, information, spatial, or editorial reason to exist. Use only supplied enum values; shot_size is exactly one enum and camera_movement is exactly one enum.
If primary_function is REACTION, stimulus_ref is required and must reference an already established stimulus. Use the authoritative character identity contract exactly. Return only the required JSON object."""
SHOT_FIELDS = ("phase_id", "beat_refs", "primary_function", "secondary_function", "subject", "shot_size", "camera_position", "camera_movement", "composition_intent", "performance_focus", "information_focus", "prop_focus", "spatial_anchor", "entry_state", "exit_state", "cut_in_motivation", "cut_out_motivation", "hold_logic", "continuity_requirements", "must_preserve_refs", "stimulus_ref", "what_audience_knows_before", "what_this_shot_adds", "what_remains_withheld")
ENUM_SIZES = {"EWS", "WS", "MWS", "MS", "MCU", "CU", "ECU", "INSERT"}
ENUM_MOVES = {"STATIC", "PAN", "TILT", "PUSH_IN", "PULL_OUT", "TRACK", "DOLLY", "HANDHELD_SUBTLE", "REFRAME", "NONE"}
ENUM_FUNCS = {"ESTABLISH", "ORIENT", "OBSERVE", "PRESSURE", "REACTION", "EVIDENCE", "INSERT", "REVEAL", "TURN", "HOLD", "TRANSITION", "RELEASE", "CLOSING"}

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

def _authority_strategy(row):
    pointer = json.loads((ARTIFACTS / "director-quality-v3-current-stage-authority.json").read_text(encoding="utf-8"))
    item = _d(_d(pointer.get("strategy_layer")).get("scenes")).get(row["scene_id"])
    expected = EXPECTED_STRATEGIES[row["scene_id"]]
    if _t(_d(item).get("fingerprint")) != expected or _t(_d(item).get("expected_fingerprint")) != expected:
        raise RuntimeError(f"strategy authority mismatch: {row['scene_id']}")
    path = ROOT / _t(_d(item).get("snapshot_path"))
    strategy = json.loads(path.read_text(encoding="utf-8"))
    if _fp(strategy) != expected: raise RuntimeError(f"strategy snapshot fingerprint mismatch: {row['scene_id']}")
    return strategy

def _contract(row, strategy):
    from core.director_scene_strategy import build_runtime_strategy_contract, canonicalize_allowed_characters
    i = row["inputs"]; runtime = build_runtime_strategy_contract(scene=i["scene"], treatment=i["director_treatment"], blocking=i["scene_blocking"], fact_snapshot=i["fact_snapshot"])
    identity = canonicalize_allowed_characters(runtime["allowed_characters"], book_id=runtime.get("book_id"))
    return runtime, identity

def _request(row):
    strategy = _authority_strategy(row); runtime, identity = _contract(row, strategy); i = row["inputs"]
    approved = {k: copy.deepcopy(v) for k, v in strategy.items() if k not in {"source_trace", "authority_projection", "strategy_fingerprint", "creative_core_fingerprint", "compiler_version", "semantic_spec_version", "strategy_version"}}
    contract = {"schema_version": "shot_architecture_draft_contract_v2", "top_level_required": ["architecture_summary", "shots"], "shot_fields": list(SHOT_FIELDS), "enums": {"primary_function": sorted(ENUM_FUNCS), "secondary_function": sorted(ENUM_FUNCS) + [None], "shot_size": sorted(ENUM_SIZES), "camera_movement": sorted(ENUM_MOVES)}, "atomic_shot_rule": "one continuous camera setup per entry", "reaction_rule": "primary_function=REACTION requires stimulus_ref to an earlier stimulus"}
    return {"task": "final_shot_architecture_recanary", "scene_id": row["scene_id"], "approved_revised_strategy": approved, "scene_blocking": i["scene_blocking"], "authoritative_scene_beats": i["scene"], "fact_snapshot": i["fact_snapshot"], "character_identity_projection": identity, "identity_binding_fingerprint": runtime["identity_binding_fingerprint"], "prop_canonical": i["prop_canonical"], "location_canonical": i["location_canonical"], "must_preserve": strategy.get("must_preserve", []), "must_avoid": strategy.get("must_avoid", []), "director_critic_review_notes": {"scene": {SCENES[0]: "Preserve pressure→body-defense leakage, dossier, T-shirt hem, darkroom; avoid mechanical angle stacking.", SCENES[1]: "Separate P03 primary/secondary expression; reflection suggests but never confirms a third party.", SCENES[2]: "Preserve trace→prop→probe→grey-coat photo→old-photo loop; avoid standard OTS."}[row["scene_id"]]}, "contract_v2": contract}

def _strict_validate(row, raw):
    from core.shot_architecture import parse_architecture_envelope, normalize_architecture_ir, validate_protocol, validate_coverage, validate_spatial, validate_topology, validate_information, validate_content_constraints, director_qa, transition_graph, atomicity_audit
    parsed = None; parse_error = ""
    try: parsed = parse_architecture_envelope(raw)
    except Exception as exc: parse_error = str(exc)[:1000]
    if not parsed: return _invalid(row, parse_error or "empty envelope")
    errors = []; top_unknown = sorted(k for k in parsed if k not in {"architecture_summary", "shots"})
    if top_unknown: errors += [{"code": "UNKNOWN_CREATIVE_FIELD", "field": x} for x in top_unknown]
    for n, shot in enumerate(_l(parsed.get("shots")), 1):
        unknown = sorted(k for k in _d(shot) if k not in set(SHOT_FIELDS))
        errors += [{"code": "UNKNOWN_CREATIVE_FIELD", "shot_index": n, "field": x} for x in unknown]
        missing = [f for f in SHOT_FIELDS if f not in shot]
        errors += [{"code": "SHOT_FIELD_MISSING", "shot_index": n, "field": f} for f in missing]
        if _t(_d(shot).get("primary_function")) not in ENUM_FUNCS: errors.append({"code": "PRIMARY_FUNCTION_INVALID", "shot_index": n})
        secondary = _d(shot).get("secondary_function")
        if secondary is not None and _t(secondary) not in ENUM_FUNCS: errors.append({"code": "SECONDARY_FUNCTION_INVALID", "shot_index": n})
        if _t(_d(shot).get("shot_size")) not in ENUM_SIZES: errors.append({"code": "SHOT_SIZE_INVALID", "shot_index": n})
        if _t(_d(shot).get("camera_movement")) not in ENUM_MOVES: errors.append({"code": "CAMERA_MOVEMENT_INVALID", "shot_index": n})
        if _t(_d(shot).get("primary_function")) == "REACTION" and not _t(_d(shot).get("stimulus_ref")): errors.append({"code": "REACTION_MISSING_STIMULUS", "shot_index": n})
    # Explicitly reject old function[] output and framing transitions in the
    # provider payload, even if normalization could alias them.
    for n, shot in enumerate(_l(parsed.get("shots")), 1):
        if "function" in _d(shot): errors.append({"code": "LEGACY_FUNCTION_FIELD", "shot_index": n})
        if re.search(r"(?:特写|近景|中近景|中景|全景|远景).*(?:转|切).*(?:特写|近景|中近景|中景|全景|远景)", _t(_d(shot).get("shot_size"))): errors.append({"code": "SHOT_SIZE_NOT_SINGLE_ENUM", "shot_index": n})
    projected = normalize_architecture_ir(parsed, scene_id=row["scene_id"], strategy_fingerprint=EXPECTED_STRATEGIES[row["scene_id"]]); ir = projected.get("ir") or {}
    i = row["inputs"]; scene = copy.deepcopy(i["scene"]); scene["characters"] = i["character_canonical"]; strategy = _authority_strategy(row)
    protocol = validate_protocol(ir, scene=scene, strategy=strategy); coverage = validate_coverage(ir, strategy, scene); spatial = validate_spatial(ir, i["scene_blocking"]); topology = validate_topology(ir); information = validate_information(ir, scene); constraints = validate_content_constraints(ir, strategy); qa = director_qa(ir, strategy, topology); atomic = atomicity_audit(parsed, ir)
    errors += list(projected.get("errors") or []) + list(protocol.get("errors") or [])
    identity = {"status": "PASS" if not any(_t(e.get("code")) == "UNKNOWN_CHARACTER_REFERENCE" for e in protocol.get("errors", [])) else "FAIL", "bindings": {_t(c.get("character_id")): _t(c.get("name")) for c in _l(_d(i.get("character_canonical")).get("records")) if isinstance(c, dict)}}
    authority = {"status": "SAFE" if not any(_t(e.get("code")) in {"UNKNOWN_BEAT_REFERENCE", "UNKNOWN_CHARACTER_REFERENCE", "FACT_AUTHORITY_VIOLATION"} for e in errors) else "UNSAFE", "violations": [e for e in errors if _t(e.get("code")) in {"UNKNOWN_BEAT_REFERENCE", "UNKNOWN_CHARACTER_REFERENCE", "FACT_AUTHORITY_VIOLATION"}]}
    valid = not errors and bool(ir) and bool(protocol.get("valid")) and coverage.get("status") == "PASS" and spatial.get("status") == "PASS" and topology.get("status") == "PASS" and information.get("status") == "PASS" and constraints.get("status") == "PASS" and not atomic.get("definite_composite_count")
    if not valid: qa = {**qa, "signal": "SHOT_ARCHITECTURE_INVALID"}
    return {"parsed_envelope": parsed, "parse_error": "", "normalized_ir": ir, "canonical": ir if valid else None, "protocol": {"status": "PASS" if protocol.get("valid") and not errors else "FAIL", "valid": bool(protocol.get("valid") and not errors), "errors": errors}, "authority": authority, "identity": identity, "coverage": coverage, "spatial": spatial, "information": information, "reaction": {"hard_errors": [e for e in topology.get("hard_errors", []) if _t(e.get("code")) in {"REACTION_WITHOUT_STIMULUS", "INVALID_REACTION_ORDER", "REACTION_MISSING_STIMULUS"}], "missing_stimulus": sum(_t(e.get("code")) == "REACTION_MISSING_STIMULUS" for e in errors), "invalid_order": sum(_t(e.get("code")) == "INVALID_REACTION_ORDER" for e in topology.get("hard_errors", [])), "evaluations": topology.get("stimulus_evaluations", [])}, "atomicity": atomic, "topology": topology, "director_qa": qa, "constraints": constraints, "transition_graph": transition_graph(ir), "valid": valid}

def _invalid(row, message):
    return {"parsed_envelope": None, "parse_error": message, "normalized_ir": {}, "canonical": None, "protocol": {"status": "FAIL", "valid": False, "errors": [{"code": "ARCHITECTURE_PARSE_ERROR", "message": message}]}, "authority": {"status": "REVIEW_REQUIRED", "violations": []}, "identity": {"status": "REVIEW_REQUIRED", "bindings": {}}, "coverage": {"status": "FAIL"}, "spatial": {"status": "FAIL"}, "information": {"status": "FAIL"}, "reaction": {"hard_errors": [], "missing_stimulus": 0, "invalid_order": 0, "evaluations": []}, "atomicity": {"status": "FAIL", "definite_composite_count": 0, "continuous_framing_count": 0, "review_required_count": 0, "findings": []}, "topology": {"status": "FAIL", "hard_errors": [], "warnings": []}, "director_qa": {"signal": "SHOT_ARCHITECTURE_INVALID", "warnings": []}, "constraints": {"status": "FAIL"}, "transition_graph": [], "valid": False}

def _compare(old, final):
    om = old.get("metrics", {}); fm = final.get("metrics", {})
    return {"old_shot_count": om.get("raw_shot_count", len(_l((old.get("normalized_ir") or {}).get("shots")))), "new_shot_count": fm.get("raw_shot_count", len(_l((final.get("normalized_ir") or {}).get("shots")))), "old_definite_composite": om.get("composite_bundle_count", 0), "new_definite_composite": fm.get("definite_composite_count", 0), "old_reaction_issue": om.get("hard_topology_errors", 0), "new_reaction_issue": fm.get("reaction_hard_error_count", 0), "old_director_signal": old.get("director_qa", {}).get("original_context", {}).get("signal"), "new_director_signal": final.get("director_qa", {}).get("signal"), "old_mechanical_dialogue": om.get("mechanical_dialogue_coverage", 0), "new_mechanical_dialogue": fm.get("mechanical_dialogue_coverage", 0), "old_template_findings": om.get("composite_bundle_count", 0), "new_template_findings": fm.get("template_finding_count", 0)}

def main():
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--execute-real", action="store_true"); ap.add_argument("--profile-id", default="local-llm-2vydoz"); args = ap.parse_args()
    head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    from api.model_registry import get_profile
    profile = get_profile(args.profile_id) or {}
    rows = _rows(); pointer = json.loads((ARTIFACTS / "director-quality-v3-current-stage-authority.json").read_text(encoding="utf-8")); parity = json.loads((ARTIFACTS / "director-quality-v3-identity-contract-parity-preflight.json").read_text(encoding="utf-8"))
    pre_checks = {"head_is_expected": head == EXPECTED_HEAD, "frozen_scene_count": len(rows) == 3, "authority_pointer_present": bool(pointer), "strategy_fingerprints_exact": True, "identity_contract_pass": parity.get("status") == "PASS", "profile_mimo": _t(profile.get("model_name")) == "mimo-v2.5", "contract_v2": True, "atomic_shot_rule": True, "previous_final_output_absent": not OUT.exists()}
    requests = [_request(r) for r in rows]
    pre_checks["request_fingerprints_frozen"] = len({_fp(x) for x in requests}) == 3
    preflight = {"schema_version": "director-quality-v3-final-shot-architecture-recanary-preflight-v1", "status": "PASS" if all(pre_checks.values()) else "BLOCKED", "checks": pre_checks, "expected_head": EXPECTED_HEAD, "system_prompt_fingerprint": _fp(SYSTEM_PROMPT), "contract_fingerprint": _fp(requests[0]["contract_v2"]), "authorized_calls": 3, "real_calls": 0, "semantic_retry": 0, "format_retry": 0, "repair_retry": 0, "transport_retry": 0}
    _write(ARTIFACTS / "director-quality-v3-final-shot-architecture-recanary-preflight.json", preflight)
    _write(ARTIFACTS / "director-quality-v3-final-shot-architecture-recanary-manifest.json", {"schema_version": "director-quality-v3-final-shot-architecture-recanary-manifest-v1", "head": head, "system_prompt_fingerprint": _fp(SYSTEM_PROMPT), "contract_fingerprint": _fp(requests[0]["contract_v2"]), "requests": [{"scene_id": r["scene_id"], "request_fingerprint": _fp(req)} for r, req in zip(rows, requests)], "frozen_before_provider_calls": True})
    _write(ARTIFACTS / "director-quality-v3-final-shot-architecture-recanary-contract.json", requests[0]["contract_v2"])
    if not preflight["status"] == "PASS" or not args.execute_real:
        print(json.dumps({"status": "PREFLIGHT_" + preflight["status"], "real_calls": 0, "checks": pre_checks}, ensure_ascii=False)); return 0 if preflight["status"] == "PASS" else 2
    from core.llm import call_llm
    scenes = []
    for row, req in zip(rows, requests):
        raw = ""; error = ""
        try: raw = str(call_llm(json.dumps(req, ensure_ascii=False), system=SYSTEM_PROMPT, model_profile=profile, retries=0, max_tokens=16000, estimated_tokens=12000, audit_extra={"phase": "director_v3_final_shot_architecture_recanary", "scene_id": row["scene_id"], "attempt_type": "ARCHITECTURE_GENERATION", "semantic_attempt": 1}) or "")
        except Exception as exc: error = str(exc)[:1000]
        result = _strict_validate(row, raw) if raw else _invalid(row, error or "empty provider response")
        scenes.append({"scene_id": row["scene_id"], "request_fingerprint": _fp(req), "raw_response": raw, "raw_response_fingerprint": _fp(raw), "provider_calls": 1, **result})
    from core.shot_architecture import compare_architectures
    architectures = [s["canonical"] or s["normalized_ir"] for s in scenes]
    distinct = compare_architectures(architectures)
    for s in scenes: s["distinctiveness"] = distinct
    counts = {"protocol": sum(s["protocol"]["status"] == "PASS" for s in scenes), "canonical": sum(bool(s.get("canonical")) for s in scenes), "authority": sum(s["authority"]["status"] == "SAFE" for s in scenes), "identity": sum(s["identity"]["status"] == "PASS" for s in scenes), "beat_coverage": sum(s["coverage"].get("beat_coverage", False) for s in scenes), "phase_coverage": sum(s["coverage"].get("phase_coverage", False) for s in scenes), "future_information_leak": sum(s["information"].get("future_information_leak_count", 0) for s in scenes), "structural_hard_error": sum(len(s["protocol"].get("errors", [])) for s in scenes), "reaction_hard_error": sum(len(s["reaction"].get("hard_errors", [])) for s in scenes), "reaction_missing_stimulus": sum(s["reaction"].get("missing_stimulus", 0) for s in scenes), "invalid_reaction_order": sum(s["reaction"].get("invalid_order", 0) for s in scenes), "definite_composite": sum(s["atomicity"].get("definite_composite_count", 0) for s in scenes), "continuous_framing": sum(s["atomicity"].get("continuous_framing_count", 0) for s in scenes), "atomicity_review_required": sum(s["atomicity"].get("review_required_count", 0) for s in scenes), "hard_topology": sum(len(s["topology"].get("hard_errors", [])) for s in scenes), "redundant_shots": sum(s["topology"].get("redundancy_count", 0) for s in scenes), "mechanical_dialogue_coverage": sum(s["director_qa"].get("mechanical_dialogue_coverage", 0) for s in scenes), "strong_or_usable": sum(s["director_qa"].get("signal") in {"SHOT_ARCHITECTURE_STRONG", "SHOT_ARCHITECTURE_USABLE"} for s in scenes)}
    technical = all(counts[k] == 3 for k in ("protocol", "canonical", "authority", "identity", "beat_coverage", "phase_coverage")) and all(counts[k] == 0 for k in ("future_information_leak", "structural_hard_error", "reaction_hard_error", "reaction_missing_stimulus", "invalid_reaction_order", "definite_composite", "hard_topology"))
    creative = counts["strong_or_usable"] == 3 and not distinct.get("hard_template_leakage") and counts["mechanical_dialogue_coverage"] == 0
    status = "DIRECTOR_V3_FINAL_SHOT_ARCHITECTURE_RECANARY_PASSED" if technical and creative else "DIRECTOR_V3_FINAL_SHOT_ARCHITECTURE_RECANARY_FAILED"
    result = {"schema_version": "director-quality-v3-final-shot-architecture-recanary-real-v1", "status": status, "head": head, "authorized_calls": 3, "attempted_calls": 3, "successful_http_calls": sum(bool(s["raw_response"]) for s in scenes), "creative_generation_count": 3, "transport_retry_count": 0, "semantic_retry_count": 0, "format_retry_count": 0, "repair_retry_count": 0, "scenes": scenes, "counts": counts, "distinctiveness": distinct, "side_effects": {"shotplan": 0, "storyboard": 0, "media": 0, "storage": 0, "shadow": 0, "ci": 0}, "ready_for_final_shot_architecture_review": status.endswith("PASSED"), "ready_for_production_shotplan": False, "ready_for_storyboard": False, "ready_for_media": False, "human_preference_review": "NOT_RECORDED"}
    _write(ARTIFACTS / "director-quality-v3-final-shot-architecture-recanary-real.json", result)
    for row, scene in zip(rows, scenes):
        name = _safe(row["scene_id"]); base = OUT / name; base.mkdir(parents=True, exist_ok=True)
        _write(base / "request.json", next(req for req in requests if req["scene_id"] == row["scene_id"]))
        (base / "raw-response.txt").write_text(scene["raw_response"], encoding="utf-8")
        _write(base / "raw-fingerprint.json", {"fingerprint": scene["raw_response_fingerprint"], "immutable": True})
        for suffix, value in (("parsed-envelope", scene.get("parsed_envelope")), ("normalized-ir", scene.get("normalized_ir")), ("canonical", scene.get("canonical") or {}), ("protocol", scene["protocol"]), ("authority", scene["authority"]), ("identity", scene["identity"]), ("coverage", scene["coverage"]), ("spatial", scene["spatial"]), ("information", scene["information"]), ("reaction", scene["reaction"]), ("atomicity", scene["atomicity"]), ("topology", scene["topology"]), ("director-qa", scene["director_qa"])): _write(base / f"{suffix}.json", value or {})
        (base / "architecture-brief.md").write_text(_brief(scene), encoding="utf-8")
    old = json.loads((ARTIFACTS / "director-quality-v3-shot-architecture-forensic-replay.json").read_text(encoding="utf-8"))
    comparisons = {s["scene_id"]: _compare(old["scenes"][i], s) for i, s in enumerate(scenes)}
    for s in scenes: s["old_vs_final"] = comparisons[s["scene_id"]]
    for filename, payload in (("protocol", {s["scene_id"]: s["protocol"] for s in scenes}), ("authority", {s["scene_id"]: s["authority"] for s in scenes}), ("identity", {s["scene_id"]: s["identity"] for s in scenes}), ("coverage", {s["scene_id"]: s["coverage"] for s in scenes}), ("spatial", {s["scene_id"]: s["spatial"] for s in scenes}), ("information", {s["scene_id"]: s["information"] for s in scenes}), ("reaction", {s["scene_id"]: s["reaction"] for s in scenes}), ("atomicity", {s["scene_id"]: s["atomicity"] for s in scenes}), ("topology", {s["scene_id"]: s["topology"] for s in scenes}), ("director-qa", {s["scene_id"]: s["director_qa"] for s in scenes}), ("comparison", comparisons)): _write(ARTIFACTS / f"director-quality-v3-final-shot-architecture-recanary-{filename}.json", payload)
    _write(ARTIFACTS / "director-quality-v3-final-shot-architecture-recanary-human-review-package.json", {"status": status, "human_preference_review": "NOT_RECORDED", "ready_for_production_shotplan": False, "briefs": [str(p.relative_to(ROOT)).replace("\\", "/") for p in OUT.glob("*/architecture-brief.md")]})
    (ARTIFACTS / "director-quality-v3-final-shot-architecture-recanary-report.md").write_text(_report(result, comparisons), encoding="utf-8")
    print(json.dumps({"status": status, "counts": counts, "real_calls": 3}, ensure_ascii=False, indent=2)); return 0 if status.endswith("PASSED") else 1

def _brief(scene):
    ir = scene.get("normalized_ir") or {}; return f"# Final Shot Architecture Brief — {scene['scene_id']}\n\n- Protocol: `{scene['protocol']['status']}`\n- Director signal: `{scene['director_qa'].get('signal')}`\n- Shot count: `{len(_l(ir.get('shots')))}`\n- Reaction hard errors: `{len(scene['reaction'].get('hard_errors', []))}`\n- Definite composite: `{scene['atomicity'].get('definite_composite_count', 0)}`\n- Continuous framing: `{scene['atomicity'].get('continuous_framing_count', 0)}`\n\n```json\n{json.dumps(ir, ensure_ascii=False, indent=2)}\n```\n"
def _report(result, comparisons):
    c = result["counts"]; rows = "\n".join(f"| {s['scene_id']} | {len(_l((s.get('normalized_ir') or {}).get('shots')))} | {s['protocol']['status']} | {s['reaction'].get('missing_stimulus',0)} | {s['atomicity'].get('definite_composite_count',0)} | {s['atomicity'].get('continuous_framing_count',0)} | {s['director_qa'].get('signal')} |" for s in result["scenes"])
    return f"# Director Quality V3 — Final Shot Architecture Re-Canary\n\n**Status:** `{result['status']}`\n\n## Baseline Audit\n\n- Expected HEAD: `{EXPECTED_HEAD}`; frozen cohort: 3 scenes; current Strategy Authority and Identity Contract were validated before calls.\n- This was the final authorized real-provider canary. No repair, retry, ShotPlan, Storyboard or media action was executed.\n\n## Final As-Built Verification\n\n- Authorized/attempted/successful calls: `{result['authorized_calls']}/{result['attempted_calls']}/{result['successful_http_calls']}`; semantic/format/repair/transport retries: `0/0/0/0`.\n- Protocol / Canonical / Authority / Identity: `{c['protocol']}/3 / {c['canonical']}/3 / {c['authority']}/3 / {c['identity']}/3`.\n- Beat / Phase coverage: `{c['beat_coverage']}/3 / {c['phase_coverage']}/3`; future leak: `{c['future_information_leak']}`.\n- Reaction hard/missing stimulus/invalid order: `{c['reaction_hard_error']}/{c['reaction_missing_stimulus']}/{c['invalid_reaction_order']}`.\n- Definite composite / continuous framing / atomicity review: `{c['definite_composite']}/{c['continuous_framing']}/{c['atomicity_review_required']}`.\n- Hard topology: `{c['hard_topology']}`; redundant shots: `{c['redundant_shots']}`; mechanical dialogue: `{c['mechanical_dialogue_coverage']}`.\n\n| Scene | Shots | Protocol | Missing stimulus | Definite composite | Continuous framing | Director signal |\n|---|---:|---|---:|---:|---:|---|\n{rows}\n\n## Old vs Final\n\n```json\n{json.dumps(comparisons, ensure_ascii=False, indent=2)}\n```\n\n## Decision\n\n- `READY_FOR_FINAL_SHOT_ARCHITECTURE_REVIEW={str(result['ready_for_final_shot_architecture_review']).lower()}`\n- `READY_FOR_PRODUCTION_SHOTPLAN=false`\n- `READY_FOR_STORYBOARD=false`\n- `READY_FOR_MEDIA=false`\n- `HUMAN_PREFERENCE_REVIEW=NOT_RECORDED`\n"

if __name__ == "__main__": raise SystemExit(main())
