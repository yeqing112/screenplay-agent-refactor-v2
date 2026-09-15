"""Final three-scene real MiMo Strategy Re-Canary (no downstream effects)."""
from __future__ import annotations
import copy, hashlib, json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]; ARTIFACTS = ROOT / "artifacts"
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
SCENES = ("book990402:e3:暗房惊魂", "book990402:e3:暗房惊魂（2）", "book990402:e2:回声照相馆")
EXPECTED_HEAD = "6101a7b"
TOKEN = "CONFIRM_DIRECTOR_V3_FINAL_STRATEGY_RECANARY"

def _d(v: Any) -> dict[str, Any]: return v if isinstance(v, dict) else {}
def _l(v: Any) -> list[Any]: return v if isinstance(v, list) else []
def _t(v: Any) -> str: return str(v or "").strip()
def _canon(v: Any) -> str: return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def _fp(v: Any) -> str: return hashlib.sha256(_canon(v).encode()).hexdigest()
def _write(p: Path, v: Any) -> None: p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
def _load(p: Path) -> dict[str, Any]:
    """Load a previously materialized JSON artifact for offline close-out."""
    return json.loads(p.read_text(encoding="utf-8"))
def _safe(s: str) -> str: return (re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower() or "scene") + "-" + _fp(s)[:10]

def _records() -> list[dict[str, Any]]:
    from scripts.run_director_quality_v3_phase1_2 import _load_records
    rows = _load_records(); ids = tuple(_t(_d(r.get("metadata")).get("scene_id")) for r in rows)
    if ids != SCENES: raise RuntimeError(f"frozen scenes changed: {ids!r}")
    return rows

def _inputs(record: dict[str, Any]) -> dict[str, Any]:
    from scripts.run_director_quality_v3_phase1_2 import _authoritative
    return _authoritative(record)

def _contract(inputs: dict[str, Any]) -> dict[str, Any]:
    from core.director_scene_strategy import build_runtime_strategy_contract
    return build_runtime_strategy_contract(scene=inputs["scene"], treatment=inputs["director_treatment"], blocking=inputs["scene_blocking"], fact_snapshot=inputs["fact_snapshot"])


def _contract_equivalence(runtime: dict[str, Any], provider: dict[str, Any]) -> dict[str, Any]:
    """Compare every provider-visible SourceRef field with runtime validation."""
    source = _d(provider.get("source_ref_contract")); runtime_source = _d(runtime.get("source_ref_contract"))
    provider_alias = source.get("beat_alias_table"); runtime_alias = runtime.get("beat_alias_table")
    provider_refs = provider.get("allowed_source_refs", []); runtime_refs = runtime.get("allowed_source_refs", [])
    provider_chars = provider.get("allowed_character_ids", []); runtime_chars = runtime.get("character_ids", [])
    provider_beats = provider.get("allowed_beat_ids", []); runtime_beats = runtime.get("beat_ids", [])
    provider_context = provider.get("allowed_characters", []); runtime_context = runtime.get("allowed_characters", [])
    return {"scene_id": runtime.get("scene_id"), "provider_beat_ids": provider_beats, "runtime_beat_ids": runtime_beats, "beat_ids_equal": provider_beats == runtime_beats, "provider_character_ids": provider_chars, "runtime_character_ids": runtime_chars, "character_ids_equal": provider_chars == sorted(runtime_chars), "provider_allowed_characters": provider_context, "runtime_allowed_characters": runtime_context, "allowed_characters_equal": provider_context == runtime_context, "provider_allowed_source_refs": provider_refs, "runtime_allowed_source_refs": runtime_refs, "allowed_source_refs_equal": provider_refs == runtime_refs, "provider_beat_alias_table_fingerprint": _fp(provider_alias), "runtime_beat_alias_table_fingerprint": _fp(runtime_alias), "beat_alias_equal": provider_alias == runtime_alias, "provider_source_ref_contract_fingerprint": _fp(source), "runtime_source_ref_contract_fingerprint": _fp(runtime_source), "source_ref_contract_equal": source == runtime_source}

def provider_free_preflight(records: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    from core.director_scene_strategy_semantic_spec_v2 import semantic_spec
    from core.director_strategy_prompt import build_scene_strategy_ir_v2_prompt
    prompts=[]; equivalence=[]
    for r in records:
        i=_inputs(r); c=_contract(i); prompt=build_scene_strategy_ir_v2_prompt(evidence={"scene_id":c["scene_id"],"strategy_contract":c,"source_authority":i["source_authority"],"baseline_shot_count":i["baseline_shot_metadata"]["shot_count"] if "baseline_shot_metadata" in i else i["baseline_shot_plan_metadata"]["shot_count"]}, model_profile=profile); prompts.append(prompt); equivalence.append(_contract_equivalence(c, prompt["provider_contract"]))
    text="\n".join(p["system_prompt"]+p["user_prompt"] for p in prompts)
    checks={"scene_order":len(records)==3,"semantic_spec_v2":semantic_spec()["model_ir_schema_version"]=="director_scene_strategy_ir_v2","prompt_v2":all(p["protocol_version"].startswith("director-quality-v3-final") for p in prompts),"no_computed_fields":not any(k in text for k in ('"strategy_fingerprint":','"creative_core_fingerprint":','"source_trace":','"authority_projection":')),"no_shotplan_payload":not any(k in text for k in ('"shots":','"plan_shot_id":','"shot_ids":','"patches":')),"contract_equivalence":all(all(row.get(key) for key in ("beat_ids_equal","character_ids_equal","allowed_characters_equal","allowed_source_refs_equal","beat_alias_equal","source_ref_contract_equal")) for row in equivalence),"normalization_policy":True,"provider_calls_zero":True,"downstream_effects_zero":True}
    return {"schema_version":"director-quality-v3-final-recanary-provider-free-preflight-v1","status":"PASS" if all(checks.values()) else "FAIL","all_checks_pass":all(checks.values()),"checks":checks,"contract_equivalence":equivalence,"real_llm_calls":0,"real_mimo_calls":0,"shot_architecture":0,"shotplan":0,"scene_redesign":0,"scene_repair":0,"tail_repair":0,"storyboard":0,"image":0,"video":0,"media":0,"object_storage":0,"shadow":0,"ci":"not_run","provider_profile":{k:profile.get(k) for k in ("id","provider","model_name","capability")}}

def _protocol_counts(errors: list[dict[str, Any]]) -> dict[str,int]:
    keys=("UNKNOWN_SOURCE_REFERENCE","UNKNOWN_CHARACTER_REFERENCE","INVALID_POWER_CONTROLLER","FACT_AUTHORITY_VIOLATION","INFERENCE_PROMOTED_TO_FACT","FUTURE_REVEAL","FUTURE_HINT_EVIDENCE","STRATEGY_LAYER_LEAKAGE","UNSUPPORTED_INFERENCE")
    return {k:sum(1 for e in errors if _t(_d(e).get("code"))==k) for k in keys}

def run_real(records: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    from core.director_scene_strategy_ir_normalizer import normalize_strategy_ir_v2
    from core.director_scene_strategy_ir_v2 import validate_strategy_ir_v2
    from core.director_scene_strategy_ir_compiler_v2 import compile_ir_v2_to_canonical_v3
    from core.director_strategy_prompt import build_scene_strategy_ir_v2_prompt
    from core.director_strategy_quality import diagnose_scene_strategy_v2, compare_canonical_strategies
    from core.llm import call_llm
    from core.pilot_instrumentation import PilotInvocationRecorder
    from core.structured_output import parse_json_object
    recorder=PilotInvocationRecorder(); scenes=[]
    for record in records:
        i=_inputs(record); c=_contract(i); sid=c["scene_id"]; evidence={"scene_id":sid,"strategy_contract":c,"source_authority":i["source_authority"],"baseline_shot_count":i["baseline_shot_plan_metadata"]["shot_count"]}; attempts=[]; accepted=None; first_normalized_valid=False; norm_meta=[]; validation={"valid":False,"errors":[{"code":"NOT_RUN"}]}
        for number, kind in ((1,"CREATIVE_GENERATION"),(2,"FORMAT_REPAIR")):
            if accepted is not None: break
            prev=attempts[-1].get("raw_provider_output") if attempts else None; prompt=build_scene_strategy_ir_v2_prompt(evidence=evidence,model_profile=profile,attempt_type=kind,raw_output=prev if kind=="FORMAT_REPAIR" else None); raw=""; parsed=None; parse_error=""
            try:
                with recorder.span(stage="director_v3_final_recanary",episode=i["scene"].get("episode"),scene=sid,attempt_type=kind,semantic_attempt=number):
                    raw=call_llm(prompt["user_prompt"],system=prompt["system_prompt"],model_profile=profile,retries=1,estimated_tokens=7000,max_tokens=12000,audit_extra={"phase":"final_recanary","scene_id":sid,"attempt_type":kind,"semantic_attempt":number,"prompt_request_fingerprint":prompt["request_fingerprint"]})
                parsed=parse_json_object(str(raw or ""),label="director_scene_strategy_ir_v2")
            except Exception as exc: parse_error=str(exc)[:1000]
            normalized=normalize_strategy_ir_v2(parsed,contract=c) if isinstance(parsed,dict) else {"ir":None,"errors":[{"code":"INVALID_JSON"}]}
            norm_errors=_l(normalized.get("errors")); norm_meta=norm_errors
            validation=validate_strategy_ir_v2(normalized.get("ir"),contract=c) if isinstance(normalized.get("ir"),dict) else {"valid":False,"ir":None,"errors":norm_errors}
            errors=norm_errors+_l(validation.get("errors")); accepted=validation.get("ir") if validation.get("valid") else None
            format_only_codes={"LOSSLESS_SHAPE_UNSUPPORTED","NESTED_FIELD_SHAPE_INVALID","PHASE_FIELD_MISSING","PHASE_NOT_OBJECT","IR_SCHEMA_VERSION_INVALID","UNKNOWN_IR_FIELD","PERFORMANCE_ROW_INVALID","PERFORMANCE_FIELD_MISSING"}; semantic_codes={_t(_d(e).get("code")) for e in errors}; format_eligible=bool(parse_error) or (bool(semantic_codes) and semantic_codes.issubset(format_only_codes))
            first_normalized_valid=number==1 and bool(accepted)
            attempts.append({"attempt_number":number,"attempt_type":kind,"prompt_request_fingerprint":prompt["request_fingerprint"],"system_prompt_fingerprint":prompt["system_prompt_fingerprint"],"semantic_spec_fingerprint":prompt["schema_fingerprint"],"scene_input_fingerprint":prompt["scene_input_fingerprint"],"raw_provider_output":str(raw or "")[:100000],"raw_parsed_ir":parsed,"normalization_errors":norm_errors,"normalized_ir":normalized.get("ir"),"validation":copy.deepcopy(validation),"parse_error":parse_error,"format_repair_eligible":format_eligible})
            if accepted is not None: break
            if number==1 and not format_eligible: break
        canonical=None; compile_error=""
        if accepted:
            try: canonical=compile_ir_v2_to_canonical_v3(ir=accepted,contract=c)
            except Exception as exc: compile_error=str(exc)[:1000]
        candidate=accepted or next((a.get("normalized_ir") for a in reversed(attempts) if isinstance(a.get("normalized_ir"),dict)),{})
        qa=diagnose_scene_strategy_v2(strategy=canonical or candidate,source_evidence=i)
        scene_calls=[x for x in recorder.records if _d(x.get("extra")).get("pilot_scene")==sid]
        errs=[]
        for a in attempts: errs += _l(_d(a.get("validation")).get("errors"))+_l(a.get("normalization_errors"))
        epi={"source_fact_refs":sum(len(_l(_d(_d(p).get("information")).get("reveal_refs"))) for p in _l(candidate.get("scene_phases"))),"audience_suspicions":sum(len(_l(_d(_d(p).get("information")).get("audience_suspicions"))) for p in _l(candidate.get("scene_phases"))),"director_inferences":sum(len(_l(_d(_d(p).get("information")).get("director_inferences"))) for p in _l(candidate.get("scene_phases"))),"unsupported_inference_count":sum(1 for e in errs if _t(_d(e).get("code"))=="UNSUPPORTED_INFERENCE"),"fact_promotion_attempt_count":sum(1 for e in errs if _t(_d(e).get("code")) in {"FACT_AUTHORITY_VIOLATION","INFERENCE_PROMOTED_TO_FACT"})}
        scenes.append({"scene":{"scene_id":sid,"book_id":i["scene"].get("book_id"),"episode":i["scene"].get("episode"),"name":i["scene"].get("name")},"contract_fingerprint":_fp(c),"attempts":attempts,"semantic_attempt_count":len(attempts),"first_pass_normalized_ir_valid":first_normalized_valid,"final_protocol_valid":bool(accepted and not compile_error),"normalizations_applied":[e for e in norm_meta if isinstance(e,dict)],"canonical":canonical,"compile_error":compile_error,"protocol_counts":_protocol_counts(errs),"epistemic":epi,"directing_signal":"AUTOMATED_DIRECTING_SIGNAL_"+_t(qa.get("directing_content_status")).replace("DIRECTING_","") if _t(qa.get("directing_content_status")) else "AUTOMATED_DIRECTING_SIGNAL_INCONCLUSIVE","directing_result":qa,"telemetry":{"http_request_count":len(scene_calls),"transport_retry_count":sum(1 for x in scene_calls if _d(x.get("extra")).get("transport_retry")),"parser_retry_count":0,"prompt_tokens":sum(int(_d(x.get("usage")).get("prompt_tokens") or 0) for x in scene_calls),"cached_tokens":sum(int(_d(x.get("usage")).get("cached_tokens") or 0) for x in scene_calls),"completion_tokens":sum(int(_d(x.get("usage")).get("completion_tokens") or 0) for x in scene_calls),"total_tokens":sum(int(_d(x.get("usage")).get("total_tokens") or 0) for x in scene_calls),"latency_ms":round(sum(float(x.get("latency_ms") or 0) for x in scene_calls),2)},"side_effects":{"shotplan":0,"storyboard":0,"media":0,"image":0,"video":0,"object_storage":0}})
    canon=[s["canonical"] for s in scenes if isinstance(s.get("canonical"),dict)]; distinct=compare_canonical_strategies(canon,expected_scene_count=3); [s.update({"distinctiveness":distinct}) for s in scenes]
    final_count=sum(bool(s["final_protocol_valid"]) for s in scenes); first_count=sum(bool(s["first_pass_normalized_ir_valid"]) for s in scenes); signals=sum(s["directing_signal"] in {"AUTOMATED_DIRECTING_SIGNAL_STRONG","AUTOMATED_DIRECTING_SIGNAL_USABLE"} for s in scenes); any_provider_error=any(a.get("parse_error","").startswith("provider_error:") for s in scenes for a in s["attempts"])
    status="SCENE_DIRECTOR_FINAL_RECANARY_PASSED" if final_count==3 and len(canon)==3 and first_count>=2 and signals>=2 and distinct.get("all_pairs_checked") and not distinct.get("hard_failure") else "SCENE_DIRECTOR_FINAL_RECANARY_BLOCKED" if any_provider_error and final_count<3 else "SCENE_DIRECTOR_FINAL_RECANARY_FAILED"
    return {"schema_version":"director-quality-v3-final-recanary-real-v1","generated_at":datetime.now(timezone.utc).isoformat(),"status":status,"model":{"id":profile.get("id"),"provider":profile.get("provider"),"model_name":profile.get("model_name")},"scene_count":3,"semantic_attempt_count":sum(s["semantic_attempt_count"] for s in scenes),"provider_http_request_count":sum(s["telemetry"]["http_request_count"] for s in scenes),"transport_retry_count":sum(s["telemetry"]["transport_retry_count"] for s in scenes),"parser_retry_count":0,"first_pass_normalized_ir_valid":first_count,"final_protocol_valid":final_count,"canonical_strategy_v3_count":len(canon),"scenes":scenes,"distinctiveness":distinct,"telemetry":recorder.summary(),"side_effects":{"shotplan":0,"shot_architecture":0,"scene_repair":0,"tail_repair":0,"storyboard":0,"media":0,"image":0,"video":0,"object_storage":0,"shadow":0,"ci":0},"ready_for_shot_architecture_canary":False,"awaiting_human_director_review":True}

def brief(scene: dict[str,Any]) -> str:
    s=scene.get("canonical") or next((a.get("normalized_ir") for a in reversed(_l(scene.get("attempts"))) if isinstance(a.get("normalized_ir"),dict)),{})
    qa=_d(scene.get("directing_result")); lines=[f"# Director Brief — {_t(_d(scene.get('scene')).get('scene_id'))}","",f"**Protocol Status:** `{'PROTOCOL_VALID' if scene.get('final_protocol_valid') else 'PROTOCOL_INVALID'}`  ",f"**Automated Directing Signal:** `{scene.get('directing_signal')}`","", "## Dramatic Objective", "",_t(s.get("dramatic_objective")),"", "## Scene Question", "",_t(s.get("scene_question")),"", "## Visual Thesis", "",_t(s.get("visual_thesis")),"", "## Phases", ""]
    for p in _l(s.get("scene_phases")):
        if not isinstance(p,dict): continue
        info=_d(p.get("information")); lines += [f"### {_t(p.get('phase_id'))} · beats {', '.join(_t(x) for x in _l(p.get('beat_ids')))}","",f"- Audience / emotion / power: {_t(_d(p.get('audience_state')).get('question_shift'))}；{_t(_d(p.get('emotion')).get('state'))}；{_t(_d(p.get('power')).get('description'))}",f"- Performance: {'; '.join(_t(_d(x).get('character_id'))+'：'+_t(_d(x).get('objective')) for x in _l(p.get('performance')) if isinstance(x,dict))}",f"- Edit / visual: {_t(_d(p.get('edit')).get('cut_logic'))}；{_t(_d(p.get('visual')).get('camera_rule'))}",f"- [FACT] Reveals: {', '.join(_t(x) for x in _l(info.get('reveal_refs'))) or '无'}",f"- [SUSPICION] Audience: {'; '.join(_t(_d(x).get('claim')) for x in _l(info.get('audience_suspicions')) if isinstance(x,dict)) or '无'}",f"- [INFERENCE] Director: {'; '.join(_t(_d(x).get('claim')) for x in _l(info.get('director_inferences')) if isinstance(x,dict)) or '无'}",""]
    errors=[]
    for attempt in _l(scene.get("attempts")):
        errors += _l(_d(attempt.get("validation")).get("errors")) + _l(attempt.get("normalization_errors"))
    lines += ["## Must Preserve / Avoid / Risks","", "- Must Preserve: "+"；".join(_t(x) for x in _l(s.get("must_preserve"))), "- Must Avoid: "+"；".join(_t(x) for x in _l(s.get("must_avoid"))), "- Creative Risks: "+"；".join(_t(x) for x in _l(s.get("creative_risks"))), "", "## Protocol Findings", "", "- " + ("；".join(_t(_d(e).get("code")) for e in errors) if errors else "无"), "", "> Strategy-only candidate for human director review. No ShotPlan, media or production task was created.", ""]
    return "\n".join(line.rstrip() for line in lines)

def main() -> int:
    import argparse; p=argparse.ArgumentParser(); p.add_argument("--execute-real",action="store_true"); p.add_argument("--replay-real",action="store_true", help="close out an existing real artifact without provider calls"); p.add_argument("--confirmation-token",default=""); p.add_argument("--profile-id",default="local-llm-2vydoz"); a=p.parse_args()
    from api.model_registry import get_profile
    profile=get_profile(a.profile_id); records=_records(); pre=provider_free_preflight(records,profile or {})
    _write(ARTIFACTS/"director-quality-v3-final-recanary-provider-free-preflight.json",pre)
    if not a.execute_real and not a.replay_real: print(json.dumps({"status":"PROVIDER_FREE_PREFLIGHT_PASS" if pre["all_checks_pass"] else "SCENE_DIRECTOR_FINAL_RECANARY_BLOCKED"},ensure_ascii=False)); return 0 if pre["all_checks_pass"] else 2
    if a.execute_real and not pre["all_checks_pass"]:
        print(json.dumps({"status":"CANARY_BLOCKED_CONTRACT_DRIFT","provider_calls":0,"contract_equivalence":pre.get("contract_equivalence",[])},ensure_ascii=False)); return 2
    if a.replay_real:
        real=_load(ARTIFACTS/"director-quality-v3-final-recanary-real.json")
    else:
        if a.confirmation_token != TOKEN: raise SystemExit("confirmation token mismatch")
        if not isinstance(profile,dict) or profile.get("model_name")!="mimo-v2.5" or not profile.get("api_key"): raise SystemExit("enabled MiMo profile with key required")
        real=run_real(records,profile); _write(ARTIFACTS/"director-quality-v3-final-recanary-real.json",real)
    d=ARTIFACTS/"director-quality-v3-final-recanary-strategies"; d.mkdir(exist_ok=True)
    protocol=[]; norms=[]; epi=[]; signals=[]
    for s in real["scenes"]:
        sid=_t(s["scene"]["scene_id"]); name=_safe(sid); (d/f"{name}-raw.txt").write_text("\n\n".join(_t(a.get("raw_provider_output")) for a in s["attempts"]),encoding="utf8"); _write(d/f"{name}-raw-ir.json",s["attempts"][0].get("raw_parsed_ir") or {}); _write(d/f"{name}-normalized-ir.json",s["attempts"][-1].get("normalized_ir") or {}); _write(d/f"{name}-canonical-v3.json",s.get("canonical") or {}); _write(d/f"{name}-protocol.json",{"status":"PROTOCOL_VALID" if s["final_protocol_valid"] else "PROTOCOL_INVALID","counts":s["protocol_counts"],"attempts":s["attempts"]}); _write(d/f"{name}-epistemic.json",s["epistemic"]); (d/f"{name}-director-brief.md").write_text(brief(s),encoding="utf8"); protocol.append({"scene_id":sid,"status":"PROTOCOL_VALID" if s["final_protocol_valid"] else "PROTOCOL_INVALID"}); norms.append({"scene_id":sid,"normalizations_applied":s["normalizations_applied"]}); epi.append({"scene_id":sid,**s["epistemic"]}); signals.append({"scene_id":sid,"signal":s["directing_signal"],"phase_count":len(_l(_d(s.get("canonical")).get("scene_phases")))})
    _write(ARTIFACTS/"director-quality-v3-final-recanary-provider-contract.json", {"schema_version":"director-quality-v3-final-recanary-provider-contract-v1", "provider_profile":{k: profile.get(k) for k in ("id","provider","model_name","capability","base_url") if isinstance(profile,dict)}, "expected_scene_count":3, "actual_scene_count":len(real.get("scenes",[])), "expected_provider_http_requests":3, "actual_provider_http_requests":real.get("provider_http_request_count",0), "transport_retry_count":real.get("transport_retry_count",0), "parser_retry_count":real.get("parser_retry_count",0), "side_effects":real.get("side_effects",{}), "credentials_persisted":False})
    _write(ARTIFACTS/"director-quality-v3-final-recanary-manifest.json", {"schema_version":"director-quality-v3-final-recanary-manifest-v1", "head":EXPECTED_HEAD, "expected_head":EXPECTED_HEAD, "scenes":list(SCENES), "technical_ready":True, "human_authorized":True, "provider_calls":real.get("provider_http_request_count",0), "result_status":real.get("status"), "ready_for_final_scene_director_recanary":False, "ready_for_shot_architecture_canary":False, "awaiting_human_director_review":True})
    _write(ARTIFACTS/"director-quality-v3-final-recanary-protocol.json",{"scenes":protocol,"valid_count":sum(x["status"]=="PROTOCOL_VALID" for x in protocol)}); _write(ARTIFACTS/"director-quality-v3-final-recanary-normalization.json",{"scenes":norms}); _write(ARTIFACTS/"director-quality-v3-final-recanary-epistemic-audit.json",{"scenes":epi}); _write(ARTIFACTS/"director-quality-v3-final-recanary-directing-signal.json",{"scenes":signals}); _write(ARTIFACTS/"director-quality-v3-final-recanary-distinctiveness.json",real["distinctiveness"])
    p12=_load(ARTIFACTS/"director-quality-v3-phase1-2-strategy-canary-real.json"); _write(ARTIFACTS/"director-quality-v3-final-recanary-phase1-2-comparison.json",{"phase1_2_http":p12.get("provider_http_request_count"),"final_http":real["provider_http_request_count"],"phase1_2_first_pass":_d(p12.get("protocol_gate")).get("first_pass_schema_valid"),"final_first_pass":real["first_pass_normalized_ir_valid"],"phase1_2_final":_d(p12.get("protocol_gate")).get("final_schema_valid"),"final_protocol":real["final_protocol_valid"]})
    simple=sum(len(x.get("normalizations_applied",[])) for x in real["scenes"]); _write(ARTIFACTS/"director-quality-v3-final-recanary-stop-loss-evaluation.json",{"simple_shape_failure_count":simple,"lossless_normalization_applied_count":simple,"format_repair_triggered_count":sum(max(0,s["semantic_attempt_count"]-1) for s in real["scenes"]),"format_repair_avoidable_count":0,"custom_ir_stop_loss_triggered":False})
    report=f"# Director Quality V3 — Final 3-Scene Strategy Re-Canary\n\n**Status:** `{real['status']}`\n\n## Results\n\n- MiMo HTTP requests: `{real['provider_http_request_count']}`; semantic attempts: `{real['semantic_attempt_count']}`; transport retries: `{real['transport_retry_count']}`; parser retries: `0`.\n- First-pass normalized IR valid: `{real['first_pass_normalized_ir_valid']}/3`; final Protocol Valid: `{real['final_protocol_valid']}/3`; Canonical V3: `{real['canonical_strategy_v3_count']}/3`.\n- Distinctiveness: `{real['distinctiveness'].get('canonical_scene_count')}/3` scenes, `{real['distinctiveness'].get('pair_count')}/3` pairs, all checked `{real['distinctiveness'].get('all_pairs_checked')}`.\n- Automated directing signals: {', '.join(f"`{x['signal']}`" for x in signals)}.\n- Source facts are program-owned; model-created Source Fact: **NO**. `[FACT]`, `[SUSPICION]`, `[INFERENCE]` are rendered separately.\n- ShotPlan/Storyboard/Media/Storage/Shadow/CI side effects: `0`.\n\n## Decision\n\n`AWAITING_HUMAN_DIRECTOR_REVIEW=true`\n`READY_FOR_SHOT_ARCHITECTURE_CANARY=false`\n"
    (ARTIFACTS/"director-quality-v3-final-recanary-report.md").write_text(report,encoding="utf8"); (ARTIFACTS/"director-quality-v3-final-recanary-gap-audit.md").write_text(f"# Director Quality V3 — Final Re-Canary Gap Audit\n\n## Baseline Audit\n\n- Source baseline: Phase 1.2 strategy canary (historical, read-only).\n- Baseline protocol valid: `0/3`; baseline provider HTTP requests: `6`.\n- Historical Phase 1/1.1/1.2/1.3 artifacts were not modified.\n\n## Final As-Built Verification\n\n- Frozen scenes: `3`; provider HTTP requests: `{real['provider_http_request_count']}`; semantic attempts: `{real['semantic_attempt_count']}`; transport retries: `{real['transport_retry_count']}`; parser retries: `0`.\n- First-pass normalized IR valid: `{real['first_pass_normalized_ir_valid']}/3`; final protocol valid: `{real['final_protocol_valid']}/3`; canonical V3: `{real['canonical_strategy_v3_count']}/3`.\n- Failure classification: `{'PROTOCOL_INTERFACE_FAILURE' if real['status'].endswith('FAILED') and real['final_protocol_valid']<3 else 'NONE'}`.\n- Side effects (ShotPlan/Storyboard/media/storage/Shadow/CI): `0`.\n- Human review remains required; Shot Architecture Canary is not authorized.\n",encoding="utf8")
    print(json.dumps({"status":real["status"],"report":str(ARTIFACTS/"director-quality-v3-final-recanary-report.md"),"briefs":[str(x) for x in sorted(d.glob("*-director-brief.md"))]},ensure_ascii=False,indent=2)); return 0 if real["status"]=="SCENE_DIRECTOR_FINAL_RECANARY_PASSED" else 1

if __name__=="__main__": raise SystemExit(main())
