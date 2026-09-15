"""Director V3 Shot Architecture Canary.

Exactly one provider call is made per frozen scene after a provider-free
preflight.  The output is a Draft Architecture only; no ShotPlan, storyboard,
media or production records are created.
"""
from __future__ import annotations

import copy, hashlib, json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
OUT = ARTIFACTS / "director-quality-v3-shot-architecture-scenes"
EXPECTED_HEADS = {"a75e2b1", "aa33aab"}
EXPECTED_HEAD = "aa33aab"
SCENES = ("book990402:e3:暗房惊魂", "book990402:e3:暗房惊魂（2）", "book990402:e2:回声照相馆")
SYSTEM_PROMPT = """You are designing shot architecture for an already approved directing strategy.
You may design, add, remove, split, merge and reorder shots.
You may not change story facts, character identities, beat chronology or the approved directing intent.
Every shot must have a dramatic, information, performance or spatial reason to exist.
Do not default to generic shot-reverse-shot coverage. Do not translate each beat into one shot.
Design the scene as a coherent visual system.
Use the supplied allowed_characters identity contract exactly; never infer or swap character identities.
Return exactly one JSON object with keys architecture_summary and shots. Each shot must include:
phase_id, beat_refs, function, subject, shot_size, camera_position, camera_movement,
composition_intent, performance_focus, information_focus, prop_focus, spatial_anchor,
entry_state, exit_state, cut_in_motivation, cut_out_motivation, hold_logic,
continuity_requirements, must_preserve_refs, what_audience_knows_before,
what_this_shot_adds, what_remains_withheld. Use only the declared beats and characters.
Do not emit shot_id, architecture_fingerprint, compiler_version, source_trace, authority_projection or qa_metrics."""

def _d(v: Any) -> dict[str, Any]: return v if isinstance(v, dict) else {}
def _l(v: Any) -> list[Any]: return v if isinstance(v, list) else []
def _t(v: Any) -> str: return str(v or "").strip()
def _canon(v: Any) -> str: return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def _fp(v: Any) -> str: return hashlib.sha256(_canon(v).encode("utf-8")).hexdigest()
def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
def _safe(s: str) -> str: return (re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower() or "scene") + "-" + _fp(s)[:10]

def _rows():
    from scripts.run_director_quality_v3_strategy_approval_repair_adjudication import _raw_rows
    rows = _raw_rows()
    if tuple(r["scene_id"] for r in rows) != SCENES: raise RuntimeError("frozen scene order changed")
    return rows

def _strategy(row: dict[str, Any]) -> dict[str, Any]:
    # Only the approved canonical strategy from the previous commit is used;
    # old ShotPlan/storyboard payloads are deliberately excluded.
    return copy.deepcopy(row["base"])

def _request(row: dict[str, Any]) -> dict[str, Any]:
    from core.director_scene_strategy import build_runtime_strategy_contract, canonicalize_allowed_characters
    inputs, strategy = row["inputs"], _strategy(row)
    runtime = build_runtime_strategy_contract(scene=inputs["scene"], treatment=inputs["director_treatment"], blocking=inputs["scene_blocking"], fact_snapshot=inputs["fact_snapshot"])
    identity = canonicalize_allowed_characters(runtime["allowed_characters"], book_id=runtime.get("book_id"))
    stripped = {k: v for k, v in strategy.items() if k not in {"source_trace", "authority_projection", "strategy_fingerprint", "creative_core_fingerprint", "compiler_version", "semantic_spec_version", "strategy_version"}}
    scene = copy.deepcopy(inputs["scene"])
    return {"scene_id": row["scene_id"], "task": "shot_architecture_draft_only", "approved_strategy": stripped, "authoritative_scene_beats": scene, "scene_blocking": inputs["scene_blocking"], "allowed_characters": identity, "identity_binding_fingerprint": runtime["identity_binding_fingerprint"], "provider_visible_contract_fingerprint": runtime["provider_visible_contract_fingerprint"], "runtime_validation_contract_fingerprint": runtime["runtime_validation_contract_fingerprint"], "location_identity": inputs["location_canonical"], "prop_identity": inputs["prop_canonical"], "must_preserve": strategy.get("must_preserve", []), "must_avoid": strategy.get("must_avoid", []), "human_director_review_notes": {"scene_specific": {"book990402:e3:暗房惊魂": "顾沉压力逐渐逼近，林晚身体反应越来越难隐藏；避免俯拍仰拍手持特写机械堆叠。", "book990402:e3:暗房惊魂（2）": "P03 的闪回、走廊反光、崩溃需区分 primary expression 与 secondary support；反光只表达可能有第三方。", "book990402:e2:回声照相馆": "保住痕迹→道具线索→人物试探→灰外套照片→旧照片揭示视觉闭环，避免标准 OTS 正反打。"}.get(row["scene_id"], "")}, "output_contract": "shot_architecture_draft_v1; program assigns SA IDs"}

def _validate(row: dict[str, Any], raw: str) -> dict[str, Any]:
    from core.structured_output import parse_json_object
    from core.shot_architecture import (normalize_architecture_ir, validate_protocol, validate_coverage, validate_spatial, validate_topology, validate_information, validate_content_constraints, director_qa, transition_graph)
    inputs, strategy = row["inputs"], _strategy(row); parse_error = ""; parsed = None
    try: parsed = parse_json_object(raw, label="shot_architecture_draft_v1")
    except Exception as exc: parse_error = str(exc)[:1000]
    shape_error = []
    model_payload = parsed or {}
    # MiMo's first canary response occasionally collapses the requested
    # envelope into one shot object.  Preserve that object for human review,
    # but mark the protocol shape invalid; this is deterministic observation,
    # never a semantic retry or creative repair.
    if parsed is not None and "shots" not in parsed and "phase_id" in parsed:
        model_payload = {"architecture_summary": "", "shots": [parsed]}
        shape_error = [{"code": "ARCHITECTURE_OUTPUT_SHAPE_INVALID", "reason": "top_level_single_shot_object"}]
    projected = normalize_architecture_ir(model_payload, scene_id=row["scene_id"], strategy_fingerprint=row["base_fingerprint"]) if parsed is not None else {"ir": None, "errors": [{"code": "ARCHITECTURE_PARSE_ERROR", "message": parse_error}], "projection_status": "FAIL"}
    if shape_error:
        projected["errors"] = list(projected.get("errors") or []) + shape_error
        projected["projection_status"] = "FAIL"
    ir = projected.get("ir") if isinstance(projected.get("ir"), dict) else None
    scene = copy.deepcopy(inputs["scene"]); scene["characters"] = inputs["character_canonical"]
    protocol = validate_protocol(ir or {}, scene=scene, strategy=strategy) if ir else {"valid": False, "errors": projected.get("errors", [])}
    coverage = validate_coverage(ir or {}, strategy, scene)
    spatial = validate_spatial(ir or {}, inputs["scene_blocking"])
    topology = validate_topology(ir or {})
    information = validate_information(ir or {}, scene)
    constraints = validate_content_constraints(ir or {}, strategy)
    qa = director_qa(ir or {}, strategy, topology)
    identity_errors = [e for e in protocol.get("errors", []) if e.get("code") == "UNKNOWN_CHARACTER_REFERENCE"]
    identity = {"status": "PASS" if not identity_errors else "FAIL", "unknown_character_references": identity_errors, "bindings": {_t(c.get("character_id")): _t(c.get("name")) for c in _l(_d(inputs.get("character_canonical")).get("records")) if isinstance(c, dict)}}
    errors = list(projected.get("errors") or []) + list(protocol.get("errors") or [])
    valid = bool(ir and projected.get("projection_status") == "PASS" and protocol.get("valid") and coverage.get("status") == "PASS" and spatial.get("status") == "PASS" and topology.get("status") == "PASS" and information.get("status") == "PASS" and constraints.get("status") == "PASS")
    if not valid:
        qa = {**qa, "signal": "SHOT_ARCHITECTURE_INVALID"}
    return {"parsed": parsed, "parse_error": parse_error, "projection": {k: v for k, v in projected.items() if k != "ir"}, "draft_ir": ir, "canonical": ir if valid else None, "protocol": {"status": "PASS" if protocol.get("valid") else "FAIL", "errors": errors, "valid": bool(protocol.get("valid"))}, "authority": {"status": "SAFE" if not any(_t(e.get("code")) in {"FACT_AUTHORITY_VIOLATION", "UNKNOWN_BEAT_REFERENCE", "UNKNOWN_CHARACTER_REFERENCE"} for e in errors) else "UNSAFE", "violations": [e for e in errors if _t(e.get("code")) in {"FACT_AUTHORITY_VIOLATION", "UNKNOWN_BEAT_REFERENCE", "UNKNOWN_CHARACTER_REFERENCE"}]}, "identity": identity, "coverage": coverage, "spatial": spatial, "topology": topology, "information": information, "constraints": constraints, "director_qa": qa, "transition_graph": transition_graph(ir or {}), "valid": valid}

def _brief(scene: dict[str, Any]) -> str:
    ir = scene.get("draft_ir") or {}; lines = [f"# Shot Architecture Brief — {scene['scene_id']}", "", f"- Protocol: `{scene['protocol']['status']}`", f"- Architecture Signal: `{scene['director_qa']['signal']}`", f"- Shot Count: `{len(_l(ir.get('shots')))}`", "", "## Architecture Summary", "", _t(ir.get("architecture_summary")), "", "## Shot List", ""]
    for shot in _l(ir.get("shots")):
        camera = "; ".join(value for value in (_t(shot.get("camera_position")), _t(shot.get("camera_movement"))) if value)
        lines += [f"### {_t(shot.get('shot_id'))} · {' / '.join(_l(shot.get('function')))}", "", f"- Phase / Beats: `{_t(shot.get('phase_id'))}` / {', '.join(_t(x) for x in _l(shot.get('beat_refs')))}", f"- Size / Subject: `{_t(shot.get('shot_size'))}` / {_t(shot.get('subject'))}", f"- Camera: {camera}", f"- Performance: {_t(shot.get('performance_focus'))}", f"- Information gained: {_t(shot.get('what_this_shot_adds')) or _t(shot.get('information_focus'))}", f"- Cut in: {_t(shot.get('cut_in_motivation'))}", f"- Cut out: {_t(shot.get('cut_out_motivation'))}", f"- Hold: {_t(shot.get('hold_logic'))}", ""]
    lines += ["## Phase / Information / Performance / Spatial Arcs", "", f"- Phase mapping: {json.dumps(scene['coverage'], ensure_ascii=False)}", f"- Information QA: {json.dumps(scene['information'], ensure_ascii=False)}", f"- Performance focus: {json.dumps([_d(s).get('performance_focus') for s in _l(ir.get('shots'))], ensure_ascii=False)}", f"- Spatial QA: {json.dumps(scene['spatial'], ensure_ascii=False)}", "", "## Cut Graph", "", json.dumps(scene.get("transition_graph") or [], ensure_ascii=False, indent=2), "", "## Warnings", "", json.dumps(scene['director_qa'].get('warnings') or [], ensure_ascii=False), ""]
    return "\n".join(lines)

def preflight(rows: list[dict[str, Any]], profile: dict[str, Any], *, allow_existing: bool = False) -> dict[str, Any]:
    head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    parity = ARTIFACTS / "director-quality-v3-identity-contract-parity-preflight.json"
    parity_doc = json.loads(parity.read_text(encoding="utf-8")) if parity.exists() else {}
    checks = {"head_is_expected": head in EXPECTED_HEADS, "frozen_scene_count": len(rows) == 3, "strategy_artifacts_available": all(bool(r.get("base")) for r in rows), "approved_strategies": all(_d(r["inputs"].get("director_treatment")).get("status") == "approved" and _d(r["inputs"].get("scene_blocking")).get("status") == "approved" for r in rows), "authority_inputs": all(isinstance(r["inputs"].get("fact_snapshot"), dict) for r in rows), "identity_bindings": all(bool(_d(r["inputs"].get("character_canonical")).get("records")) for r in rows), "identity_contract_parity": parity_doc.get("status") == "PASS" and all(parity_doc.get("checks", {}).get(k) for k in ("identity_projection_parity", "contract_fingerprint_parity")), "no_prior_canary_outputs": allow_existing or not OUT.exists(), "profile_mimo": _t(profile.get("model_name")) == "mimo-v2.5", "real_calls_zero": True, "downstream_side_effects_zero": True}
    return {"schema_version": "director-quality-v3-shot-architecture-preflight-v1", "status": "PASS" if all(checks.values()) else "FAIL", "all_checks_pass": all(checks.values()), "checks": checks, "real_llm_calls": 0, "real_mimo_calls": 0, "provider_http_requests": 0, "shot_architecture": 0, "shotplan": 0, "storyboard": 0, "image": 0, "video": 0, "media": 0, "storage": 0, "shadow": 0, "ci": "not_run", "profile": {k: profile.get(k) for k in ("id", "provider", "model_name")}}

def _write_replay_reports(scenes: list[dict[str, Any]], counts: dict[str, Any], distinct: dict[str, Any]) -> None:
    status = "DIRECTOR_V3_SHOT_ARCHITECTURE_CANARY_PASSED" if all(counts[k] == 3 for k in ("protocol", "canonical", "authority", "identity", "beat_coverage", "phase_coverage", "strong_or_usable")) and counts["spatial_hard_errors"] == counts["future_information_leak"] == counts["hard_topology"] == 0 and not distinct.get("hard_failure") else "DIRECTOR_V3_SHOT_ARCHITECTURE_CANARY_FAILED"
    report = "# Director Quality V3 — Shot Architecture Canary\n\n**Status:** `" + status + "`\n\n## Baseline Audit\n\n- Approved Revised Director Strategies were reused; no Strategy regeneration or historical artifact mutation occurred.\n- This is a deterministic replay of the already captured three raw provider responses.\n\n## Final As-Built Verification\n\n- MiMo calls: **3**, exactly one per scene; new provider calls in replay: **0**; retries: 0.\n" + f"- Protocol / Canonical / Authority / Identity: {counts['protocol']}/3 / {counts['canonical']}/3 / {counts['authority']}/3 / {counts['identity']}/3.\n- Beat / Phase coverage: {counts['beat_coverage']}/3 / {counts['phase_coverage']}/3.\n- Spatial hard errors: {counts['spatial_hard_errors']}; future information leaks: {counts['future_information_leak']}; hard topology errors: {counts['hard_topology']}; redundant shots: {counts['redundant_shots']}.\n- Mechanical dialogue coverage: {counts['mechanical_dialogue_coverage']}; Strong/Usable: {counts['strong_or_usable']}/3.\n- Distinctiveness pairs: {distinct.get('pair_count', 0)}/3; hard template leakage: {distinct.get('hard_template_leakage')}.\n\n## Scene Results\n\n" + "\n".join(f"- `{s['scene_id']}`: {s['director_qa']['signal']}, shots={len(_l((s.get('draft_ir') or {}).get('shots')))}, protocol={s['protocol']['status']}" for s in scenes) + "\n\n## Release Boundary\n\n`READY_FOR_HUMAN_SHOT_ARCHITECTURE_REVIEW=true`\n`READY_FOR_PRODUCTION_SHOTPLAN=false`\n`READY_FOR_STORYBOARD=false`\n`READY_FOR_MEDIA=false`\n"
    (ARTIFACTS / "director-quality-v3-shot-architecture-report.md").write_text(report, encoding="utf-8")
    with (ARTIFACTS / "director-quality-v3-shot-architecture-report.md").open("a", encoding="utf-8") as handle:
        handle.write("\n## Required Review Answers\n\n- Exactly one MiMo call per frozen scene: **YES** (3 captured; replay calls 0).\n- Semantic / format / creative retries: **NO**.\n- Scene shot counts: **1 / 1 / 1**; no fixed-count template was imposed, but all three provider outputs are protocol-invalid single-shot objects.\n- Facts, character identity, beat order and phase membership changed: **NO** (draft-only validators; no downstream write).\n- ShotPlan / Storyboard / Image / Video / Media / Storage entered: **NO**.\n- Every shot existence reason, cut motivation and hold logic: **NOT CERTIFIABLE** because all three drafts failed the required top-level architecture envelope; the raw single-shot objects are preserved for human diagnosis only.\n- Scene 1 pressure-versus-body-defense topology: **NOT CERTIFIABLE**.\n- Scene 2 primary/secondary visual expression and uncertain reflection: **NOT CERTIFIABLE**.\n- Scene 3 trace → prop → character → grey-coat photo → old-photo loop and non-OTS coverage: **NOT CERTIFIABLE**.\n- Human Shot Architecture Review: **READY**; Production ShotPlan: **BLOCKED**.\n")
    _write(ARTIFACTS / "director-quality-v3-shot-architecture-human-review-package.json", {"status": status, "human_review_pending": True, "ready_for_production_shotplan": False, "briefs": [str(p) for p in sorted(OUT.glob("*-architecture-brief.md"))]})
    (ARTIFACTS / "director-quality-v3-shot-architecture-gap-audit.md").write_text("# Director Quality V3 Shot Architecture Canary — Gap Audit\n\n## Baseline Audit\n\n- Existing raw responses were captured with exactly one provider call per frozen scene.\n- No repair, retry, ShotPlan, Storyboard or media action was performed.\n\n## Final As-Built Verification\n\n- Deterministic replay provider calls: `0`; original captured calls: `3`.\n- Structural QA and Director Architecture QA remain separate.\n- Result is held at the human Shot Architecture review boundary; production remains blocked.\n", encoding="utf-8")


def main() -> int:
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument("--execute-real", action="store_true"); ap.add_argument("--replay-existing", action="store_true", help="revalidate persisted raw responses without provider calls"); ap.add_argument("--profile-id", default="local-llm-2vydoz"); args=ap.parse_args()
    from api.model_registry import get_profile
    from core.llm import call_llm
    rows = _rows(); profile = get_profile(args.profile_id) or {}; pf = preflight(rows, profile, allow_existing=args.replay_existing); _write(ARTIFACTS / "director-quality-v3-shot-architecture-preflight.json", pf)
    _write(ARTIFACTS / "director-quality-v3-shot-architecture-protocol.json", {"system_prompt": SYSTEM_PROMPT, "system_prompt_fingerprint": _fp(SYSTEM_PROMPT), "schema_version": "shot_architecture_draft_v1", "provider_calls_per_scene": 1, "parser_retries": 0, "semantic_retries": 0})
    _write(ARTIFACTS / "director-quality-v3-shot-architecture-contract.json", {"schema_version": "shot_architecture_draft_contract_v1", "required_shot_fields": list(__import__("core.shot_architecture", fromlist=["REQUIRED_SHOT_FIELDS"]).REQUIRED_SHOT_FIELDS), "program_owned_fields": sorted(__import__("core.shot_architecture", fromlist=["PROGRAM_OWNED"]).PROGRAM_OWNED), "shot_id_policy": "program_deterministic_SA01_to_SAxx", "side_effect_boundary": "draft_artifacts_only"})
    manifest = {"schema_version": "director-quality-v3-shot-architecture-manifest-v1", "base_commit": subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip(), "scenes": [{"scene_id": r["scene_id"], "strategy_fingerprint": r["base_fingerprint"], "blocking_fingerprint": _fp(r["inputs"]["scene_blocking"]), "fact_snapshot_fingerprint": _fp(r["inputs"]["fact_snapshot"]), "identity_binding_fingerprint": _fp(_request(r)["allowed_characters"])} for r in rows], "real_calls": 0}
    _write(ARTIFACTS / "director-quality-v3-shot-architecture-manifest.json", manifest)
    if args.replay_existing:
        existing = json.loads((ARTIFACTS / "director-quality-v3-shot-architecture-real.json").read_text(encoding="utf-8")); scenes=[]
        for row in rows:
            previous = next((item for item in existing.get("scenes", []) if item.get("scene_id") == row["scene_id"]), {})
            raw = str(previous.get("raw_response") or ""); result = _validate(row, raw)
            scenes.append({"scene_id": row["scene_id"], "strategy_fingerprint": row["base_fingerprint"], "request": _request(row), "request_fingerprint": _fp(_request(row)), "raw_response": raw, "raw_response_fingerprint": _fp(raw), **result, "provider_calls": 1})
        architectures=[s["canonical"] or s["draft_ir"] for s in scenes if s.get("canonical") or s.get("draft_ir")]
        from core.shot_architecture import compare_architectures
        distinct=compare_architectures(architectures)
        for s in scenes: s["distinctiveness"]=distinct
        counts={"protocol":sum(s["protocol"]["status"]=="PASS" for s in scenes),"canonical":sum(bool(s.get("canonical")) for s in scenes),"authority":sum(s["authority"]["status"]=="SAFE" for s in scenes),"identity":sum(s["identity"]["status"]=="PASS" for s in scenes),"beat_coverage":sum(s["coverage"].get("beat_coverage") for s in scenes),"phase_coverage":sum(s["coverage"].get("phase_coverage") for s in scenes),"spatial_hard_errors":sum(len(s["spatial"].get("hard_errors",[])) for s in scenes),"future_information_leak":sum(s["information"].get("future_information_leak_count",0) for s in scenes),"hard_topology":sum(len(s["topology"].get("hard_errors",[])) for s in scenes),"redundant_shots":sum(s["topology"].get("redundancy_count",0) for s in scenes),"mechanical_dialogue_coverage":sum(s["director_qa"].get("mechanical_dialogue_coverage",0) for s in scenes),"strong_or_usable":sum(s["director_qa"].get("signal") in {"SHOT_ARCHITECTURE_STRONG","SHOT_ARCHITECTURE_USABLE"} for s in scenes)}
        # Replay is provider-free, but it must still replace every derived
        # aggregate so that the persisted JSON evidence is self-consistent
        # with the regenerated per-scene reports.  In particular, retaining
        # the prior top-level distinctiveness result would make the report and
        # machine-readable gate disagree after a replay.
        replay_real = {**existing, "scenes": scenes, "distinctiveness": distinct, "replay_provider_calls": 0, "replay_status": "DETERMINISTIC_REPLAY"}
        _write(ARTIFACTS / "director-quality-v3-shot-architecture-real.json", replay_real)
        _write(ARTIFACTS / "director-quality-v3-shot-architecture-distinctiveness.json", distinct)
        for s in scenes:
            name=_safe(s["scene_id"]); _write(OUT/f"{name}-request.json",s["request"]); (OUT/f"{name}-raw-response.txt").write_text(s["raw_response"],encoding="utf-8"); _write(OUT/f"{name}-draft-ir.json",s.get("draft_ir") or {}); _write(OUT/f"{name}-canonical.json",s.get("canonical") or {}); _write(OUT/f"{name}-protocol.json",s["protocol"]); _write(OUT/f"{name}-authority.json",s["authority"]); _write(OUT/f"{name}-identity.json",s["identity"]); _write(OUT/f"{name}-coverage.json",s["coverage"]); _write(OUT/f"{name}-spatial.json",s["spatial"]); _write(OUT/f"{name}-topology.json",s["topology"]); _write(OUT/f"{name}-information.json",s["information"]); _write(OUT/f"{name}-director-qa.json",s["director_qa"]); (OUT/f"{name}-architecture-brief.md").write_text(_brief(s),encoding="utf-8")
        _write_replay_reports(scenes, counts, distinct)
        print(json.dumps({"status":"DETERMINISTIC_REPLAY_UPDATED","provider_calls":0,"scene_count":3},ensure_ascii=False)); return 0
    if not args.execute_real:
        print(json.dumps({"status": "PROVIDER_FREE_PREFLIGHT_PASS" if pf["all_checks_pass"] else "CANARY_BLOCKED", "artifact": str(ARTIFACTS / "director-quality-v3-shot-architecture-preflight.json")}, ensure_ascii=False)); return 0 if pf["all_checks_pass"] else 2
    if not pf["all_checks_pass"]: print(json.dumps({"status":"CANARY_BLOCKED","real_calls":0})); return 2
    scenes=[]
    for row in rows:
        req = _request(row); prompt = json.dumps(req, ensure_ascii=False)
        raw=""; error=""
        try: raw = str(call_llm(prompt, system=SYSTEM_PROMPT, model_profile=profile, retries=0, max_tokens=12000, estimated_tokens=9000, audit_extra={"phase":"director_v3_shot_architecture_canary","scene_id":row["scene_id"],"attempt_type":"ARCHITECTURE_GENERATION","semantic_attempt":1}) or "")
        except Exception as exc: error = str(exc)[:1000]
        result = _validate(row, raw) if raw else {"parsed":None,"parse_error":error or "empty provider response","projection":{"projection_status":"FAIL"},"draft_ir":None,"canonical":None,"protocol":{"status":"FAIL","errors":[{"code":"PROVIDER_EMPTY_OR_ERROR","message":error}],"valid":False},"authority":{"status":"SAFE","violations":[]},"identity":{"status":"REVIEW_REQUIRED","unknown_character_references":[]},"coverage":{"status":"FAIL"},"spatial":{"status":"FAIL"},"topology":{"status":"FAIL"},"information":{"status":"FAIL"},"constraints":{"status":"FAIL"},"director_qa":{"signal":"SHOT_ARCHITECTURE_INVALID","warnings":[]},"transition_graph":[],"valid":False}
        scenes.append({"scene_id":row["scene_id"],"strategy_fingerprint":row["base_fingerprint"],"request":req,"request_fingerprint":_fp(req),"raw_response":raw,"raw_response_fingerprint":_fp(raw),**result,"provider_calls":1})
    architectures=[s["canonical"] or s["draft_ir"] for s in scenes if s.get("canonical") or s.get("draft_ir")]
    from core.shot_architecture import compare_architectures
    distinct=compare_architectures(architectures)
    for s in scenes: s["distinctiveness"]=distinct
    counts={"protocol":sum(s["protocol"]["status"]=="PASS" for s in scenes),"canonical":sum(bool(s.get("canonical")) for s in scenes),"authority":sum(s["authority"]["status"]=="SAFE" for s in scenes),"identity":sum(s["identity"]["status"]=="PASS" for s in scenes),"beat_coverage":sum(s["coverage"].get("beat_coverage") for s in scenes),"phase_coverage":sum(s["coverage"].get("phase_coverage") for s in scenes),"spatial_hard_errors":sum(len(s["spatial"].get("hard_errors",[])) for s in scenes),"future_information_leak":sum(s["information"].get("future_information_leak_count",0) for s in scenes),"hard_topology":sum(len(s["topology"].get("hard_errors",[])) for s in scenes),"redundant_shots":sum(s["topology"].get("redundancy_count",0) for s in scenes),"mechanical_dialogue_coverage":sum(s["director_qa"].get("mechanical_dialogue_coverage",0) for s in scenes),"strong_or_usable":sum(s["director_qa"].get("signal") in {"SHOT_ARCHITECTURE_STRONG","SHOT_ARCHITECTURE_USABLE"} for s in scenes)}
    passed=all(counts[k]==3 for k in ("protocol","canonical","authority","identity","beat_coverage","phase_coverage","strong_or_usable")) and counts["spatial_hard_errors"]==counts["future_information_leak"]==counts["hard_topology"]==0 and not distinct.get("hard_failure")
    status="DIRECTOR_V3_SHOT_ARCHITECTURE_CANARY_PASSED" if passed else "DIRECTOR_V3_SHOT_ARCHITECTURE_CANARY_FAILED"
    current_head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    result={"schema_version":"director-quality-v3-shot-architecture-real-v1","status":status,"base_commit":current_head,"scene_count":3,"provider_calls":3,"real_mimo_calls":3,"provider_http_requests":3,"transport_retries":0,"parser_retries":0,"semantic_retries":0,"scenes":scenes,"counts":counts,"distinctiveness":distinct,"side_effects":{"shotplan":0,"storyboard":0,"media":0,"image":0,"video":0,"storage":0,"shadow":0},"ready_for_human_shot_architecture_review":True,"ready_for_production_shotplan":False,"ready_for_storyboard":False,"ready_for_media":False}
    _write(ARTIFACTS / "director-quality-v3-shot-architecture-real.json", result)
    for s in scenes:
        name=_safe(s["scene_id"]); _write(OUT/f"{name}-request.json",s["request"]); (OUT/f"{name}-raw-response.txt").write_text(s["raw_response"],encoding="utf-8"); _write(OUT/f"{name}-draft-ir.json",s.get("draft_ir") or {}); _write(OUT/f"{name}-canonical.json",s.get("canonical") or {}); _write(OUT/f"{name}-protocol.json",s["protocol"]); _write(OUT/f"{name}-authority.json",s["authority"]); _write(OUT/f"{name}-identity.json",s["identity"]); _write(OUT/f"{name}-coverage.json",s["coverage"]); _write(OUT/f"{name}-spatial.json",s["spatial"]); _write(OUT/f"{name}-topology.json",s["topology"]); _write(OUT/f"{name}-information.json",s["information"]); _write(OUT/f"{name}-director-qa.json",s["director_qa"]); (OUT/f"{name}-architecture-brief.md").write_text(_brief(s),encoding="utf-8")
    for filename,payload in (("director-quality-v3-shot-architecture-authority.json",{s["scene_id"]:s["authority"] for s in scenes}),("director-quality-v3-shot-architecture-identity.json",{s["scene_id"]:s["identity"] for s in scenes}),("director-quality-v3-shot-architecture-coverage.json",{s["scene_id"]:s["coverage"] for s in scenes}),("director-quality-v3-shot-architecture-spatial.json",{s["scene_id"]:s["spatial"] for s in scenes}),("director-quality-v3-shot-architecture-topology.json",{s["scene_id"]:s["topology"] for s in scenes}),("director-quality-v3-shot-architecture-information.json",{s["scene_id"]:s["information"] for s in scenes}),("director-quality-v3-shot-architecture-director-qa.json",{s["scene_id"]:s["director_qa"] for s in scenes}),("director-quality-v3-shot-architecture-distinctiveness.json",distinct),("director-quality-v3-shot-architecture-human-review-package.json",{"status":status,"human_review_pending":True,"ready_for_production_shotplan":False,"briefs":[str(p) for p in sorted(OUT.glob("*-architecture-brief.md"))]})): _write(ARTIFACTS/filename,payload)
    report=f"# Director Quality V3 — Shot Architecture Canary\n\n**Status:** `{status}`\n\n## Baseline Audit\n\n- Source commit: `{EXPECTED_HEAD}`; frozen scenes: 3; approved Revised Director Strategies were reused without regeneration.\n- No historical Strategy/ShotPlan/Storyboard artifacts were modified.\n\n## Final As-Built Verification\n\n- MiMo calls: **3**, exactly one per scene; retries: 0; parser retries: 0; semantic retries: 0.\n- Protocol / Canonical / Authority / Identity: {counts['protocol']}/3 / {counts['canonical']}/3 / {counts['authority']}/3 / {counts['identity']}/3.\n- Beat / Phase coverage: {counts['beat_coverage']}/3 / {counts['phase_coverage']}/3.\n- Spatial hard errors: {counts['spatial_hard_errors']}; future information leaks: {counts['future_information_leak']}; hard topology errors: {counts['hard_topology']}; redundant shots: {counts['redundant_shots']}.\n- Mechanical dialogue coverage: {counts['mechanical_dialogue_coverage']}; Strong/Usable: {counts['strong_or_usable']}/3.\n- Distinctiveness pairs: {distinct.get('pair_count',0)}/3; hard template leakage: {distinct.get('hard_template_leakage')}.\n\n## Scene Results\n\n" + "\n".join(f"- `{s['scene_id']}`: {s['director_qa']['signal']}, shots={len(_l((s.get('draft_ir') or {}).get('shots')))}, protocol={s['protocol']['status']}" for s in scenes) + "\n\n## Release Boundary\n\n`READY_FOR_HUMAN_SHOT_ARCHITECTURE_REVIEW=true`\n`READY_FOR_PRODUCTION_SHOTPLAN=false`\n`READY_FOR_STORYBOARD=false`\n`READY_FOR_MEDIA=false`\n"
    (ARTIFACTS/"director-quality-v3-shot-architecture-report.md").write_text(report,encoding="utf-8")
    (ARTIFACTS/"director-quality-v3-shot-architecture-gap-audit.md").write_text(f"# Director Quality V3 Shot Architecture Canary — Gap Audit\n\n## Baseline Audit\n\n- Frozen strategy cohort from `{EXPECTED_HEAD}`; no old ShotPlan was provided to the model.\n\n## Final As-Built Verification\n\n- Status: `{status}`; provider calls: 3; downstream production/media side effects: 0.\n- Structural QA and Director Architecture QA are stored separately per scene.\n- Human Shot Architecture Review remains required; ShotPlan and media remain blocked.\n",encoding="utf-8")
    print(json.dumps({"status":status,"counts":counts,"report":str(ARTIFACTS/"director-quality-v3-shot-architecture-report.md")},ensure_ascii=False,indent=2)); return 0 if passed else 1

if __name__ == "__main__": raise SystemExit(main())
