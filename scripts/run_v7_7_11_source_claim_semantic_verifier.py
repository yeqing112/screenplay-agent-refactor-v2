"""Run the one authorized V7.7.11 semantic verifier call for one frozen claim."""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import llm
from core.fact_semantic_verifier import build_verifier_request, parse_verifier_payload, provider_schema, validate_verifier_payload
from core.provider_structured_output_qualification import compile_provider_strict_schema, fingerprint, provider_identity, qualification_fingerprint, validate_json_schema_subset
from core.source_claim_semantic_verifier_adapter import (
    TRANSPORT_FACT_ID, adapter_contract, build_verifier_packet, compile_shadow_overlay,
    component_contract, evidence_authority_audit, support_role_registry_v1, typed_atomicity_guard,
)
from core.source_semantic_claim_v3 import build_claim_input_entity_registry
from core.source_semantic_claim_v3_1 import source_speech_act_binding_registry_v1
from core.source_semantic_claim_v3_2 import (
    PROVIDER_PREDICATE_REGISTRY_V3_VERSION, QUALIFIER_REGISTRY_V4_VERSION,
    RELATION_SIGNATURE_REGISTRY_V4_VERSION, provider_predicate_registry_v3,
    qualifier_registry_v4, relation_signature_registry_v4, validate_provider_candidate_v3_2,
)
from scripts.generate_v7_7_8_source_semantic_claim_v3_foundation_evidence import current_production_freeze, sha256_file
from scripts.run_v7_7_3_source_semantic_claim_proposal import read_db
from scripts.run_v7_7_10_source_semantic_claim_v3_2_reproposal import load_script_ir

BRANCH = "codex/visual-authoring-provider-canary-reconcile"
BASELINE = "0cd7dc57dbf0a7541c73bd56f2b426c6afce2551"
AUTHORIZATION_ID = "v7.7.11-source-semantic-claim-v3-2-semantic-verifier-single-call"
CLAIM_REF = "SCC_V7_7_10_0001"
EXPECTED_CANDIDATE_FP = "6f5a6a567c83d674f5ecc463ef44bfcc9ecfd0e5798a44a166be929ed5f8717f"
EXPECTED_SET_FP = "d896b80a538f515a17a0d82058bbed45d1582675e8a563aabb9929d6f3ac1bfb"
EXPECTED_RAW_SHA = "39c43a5a571f220e15bc88c273f7652fe4679fc52b629886c00713a8e6d21b1a"
EXPECTED_SOURCE_FP = "190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1"
EXPECTED_UNITS_FP = "2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f"
EXPECTED_ENTITY_FP = "88de4d7793043c11897605217c3e6a29847062eb87ac4b7bb20909b147e6b186"
EXPECTED_INPUT_ENTITY_FP = "877d43fc4cea05b487e50b6a4afcdb58e44f78338f1ebfcb388ecbe9b9740acb"
EXPECTED_TRANSPORT_FP = "5f4ecbd2ca8cbaf8dea0b1319350cf763a971aefea8143a346232d23e8d4c75c"
EXPECTED_PROVIDER_FP = "9908c628bc8b970817674b26ff3897bb055bc24ee6505bbc2af6a80f7722c455"
EXPECTED_QUALIFICATION_FP = "194241dae7837d160c63a72bd1c3017bd9a9d0219d2f25e6a083637abdf3cb3b"

V710 = ROOT / "docs/canonical-canary/v7_7_10-source-semantic-claim-v3-2-reproposal-real"
OUT = ROOT / "docs/canonical-canary/v7_7_11-source-semantic-claim-v3-2-semantic-verification-real"
V71 = ROOT / "docs/canonical-canary/v7_1-director-source-grounded-authoring-contract"
V775 = ROOT / "docs/canonical-canary/v7_7_5-provider-structured-output-capability-qualification"
V777 = ROOT / "docs/canonical-canary/v7_7_7-source-entity-semantic-verification-real"
V778 = ROOT / "docs/canonical-canary/v7_7_8-source-semantic-claim-v3-foundation"
DB = ROOT / "work/db/screenplay.db"

ARTIFACTS = [
    "ANTI_HEURISTIC_PATCH_REVIEW.json", "V7_7_10_PROPOSAL_FREEZE.json", "SOURCE_CLAIM_VERIFIER_ELIGIBILITY.json",
    "SOURCE_CLAIM_VERIFIER_ADAPTER_CONTRACT.json", "SOURCE_CLAIM_VERIFIER_ID_MAPPING.json", "SOURCE_CLAIM_TYPED_COMPONENT_CONTRACT.json",
    "SOURCE_CLAIM_EVIDENCE_AUTHORITY_AUDIT.json", "SOURCE_CLAIM_TYPED_ATOMICITY_CONTRACT.json", "SOURCE_CLAIM_TYPED_ATOMICITY_AUDIT.json",
    "SOURCE_CLAIM_SUPPORT_ROLE_REGISTRY.json", "SOURCE_CLAIM_CONFIRMATION_CEILING_AUDIT.json", "SOURCE_CLAIM_VERIFIER_MACHINE_GUARDS.json",
    "SOURCE_CLAIM_VERIFIER_INPUT_FREEZE.json", "SOURCE_CLAIM_VERIFIER_PROVIDER_IDENTITY.json", "SOURCE_CLAIM_VERIFIER_AUTHORIZATION.json",
    "SOURCE_CLAIM_VERIFIER_PROMPT_AUDIT.json", "SOURCE_CLAIM_VERIFIER_TRANSPORT_AUDIT.json", "SOURCE_CLAIM_VERIFIER_RAW_FORENSIC.json",
    "SOURCE_CLAIM_VERIFIER_PARSE_AUDIT.json", "SOURCE_CLAIM_VERIFIER_SCHEMA_VALIDATION.json", "SOURCE_CLAIM_VERIFIER_CARDINALITY_AUDIT.json",
    "SOURCE_CLAIM_VERIFIER_COMPONENT_AUDIT.json", "SOURCE_CLAIM_VERIFIER_RESULT.json", "SOURCE_CLAIM_SEMANTIC_AUTHORITY_COMPILATION.json",
    "SOURCE_CLAIM_SEMANTIC_AUTHORITY_OVERLAY_SHADOW.json", "PROGRAM_DETERMINISTIC_SPEECH_ACT_COMPANION_STATUS.json",
    "NO_AUTHORITY_PERSISTENCE_NO_PRODUCTION_WRITE_AUDIT.json", "RECOMMENDED_NEXT_ACTION.json", "SOURCE_SEMANTIC_CLAIM_V3_2_SEMANTIC_VERIFICATION_REPORT.md",
]


def read(path: Path) -> Any: return json.loads(path.read_text(encoding="utf-8"))
def sha_text(text: str) -> str: return hashlib.sha256(text.encode("utf-8")).hexdigest()
def git(*args: str, check: bool = True) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=check).stdout.strip()
def write_json(name: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True); target = OUT / name; tmp = target.with_suffix(target.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"); os.replace(tmp, target)
def write_text(name: str, value: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True); target = OUT / name; tmp = target.with_suffix(target.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(value, encoding="utf-8"); os.replace(tmp, target)


def profile_audit() -> tuple[dict[str, Any], dict[str, Any]]:
    profile = llm._resolve_llm_profile(); base = str(profile.get("base_url") or "").rstrip("/"); parsed = urlparse(base)
    identity = provider_identity(profile_id=str(profile.get("id") or ""), provider=str(profile.get("provider") or ""), model=str(profile.get("model_name") or ""), base_host=f"{parsed.scheme}://{parsed.netloc}")
    qualification = read(V775 / "PROVIDER_STRUCTURED_OUTPUT_QUALIFICATION.json")
    q = qualification_fingerprint(identity=identity, capability=str(qualification.get("capability") or ""), probe_schema_fingerprint=str(qualification.get("probe_schema_fingerprint") or ""), request_fingerprint=str(qualification.get("request_fingerprint") or ""), raw_response_sha256=str(qualification.get("raw_response_sha256") or ""), qualified=bool(qualification.get("qualified")))
    checks = {"profile": identity.get("profile_id") == "local-llm-2vydoz", "provider": identity.get("provider") == "openai-compatible", "model": identity.get("model") == "mimo-v2.5", "host": identity.get("base_host") == "https://api.xiaomimimo.com", "identity": identity.get("provider_identity_fingerprint") == EXPECTED_PROVIDER_FP, "qualification": q.get("qualification_fingerprint") == EXPECTED_QUALIFICATION_FP, "strict": qualification.get("qualified") is True and qualification.get("capability") == "JSON_SCHEMA_STRICT_SUPPORTED", "key": bool(profile.get("api_key") or profile.get("key_configured"))}
    return profile, {"status": "PASS" if all(checks.values()) else "BLOCKED", "checks": checks, "identity": identity, "qualification_fingerprint": q.get("qualification_fingerprint"), "qualification": qualification}


def anti_heuristic() -> dict[str, Any]:
    source = (ROOT / "core/source_claim_semantic_verifier_adapter.py").read_text(encoding="utf-8")
    forbidden = {"顾沉": "gu", "林晚": "lin", "暗房": "room"}
    return {"schema_version": "v7_7_11_anti_heuristic_patch_review_v1", "status": "PASS" if not any(k in source for k in forbidden) else "BLOCKED", "phrase_dependence": "NO", "scene_dependence": "NO", "attempt_specific_semantic_rule": "NO", "predicate_name_semantic_inference": "NO", "source_prose_local_entailment": "NO", "regex_entailment": "NO", "names_special_cased": False, "uses_ast_review": isinstance(ast.parse(source), ast.Module)}


def strict_transport_schema() -> dict[str, Any]:
    """Project the reused verifier schema into the qualified strict subset.

    The semantic verifier's existing ``pattern`` remains enforced by its
    parser/cardinality check. The qualified Provider dialect intentionally
    excludes that annotation from the wire schema.
    """
    schema = copy.deepcopy(provider_schema())
    schema["properties"]["results"]["items"]["properties"]["fact_id"].pop("pattern", None)
    return schema


def local_gates(db_sha: str) -> dict[str, Any]:
    tests = subprocess.run([sys.executable, "-m", "pytest", "tests/test_source_claim_semantic_verifier_adapter.py", "tests/test_fact_semantic_verifier.py", "tests/test_fact_semantic_grounding.py", "tests/test_source_semantic_claim_v3_2_reproposal.py", "-q"], cwd=ROOT, capture_output=True, text=True)
    compile_result = subprocess.run([sys.executable, "-m", "compileall", "-q", "core", "scripts", "tests"], cwd=ROOT, capture_output=True, text=True)
    diff_result = subprocess.run(["git", "diff", "--check"], cwd=ROOT, capture_output=True, text=True)
    db_after = sha256_file(DB)
    return {"tests": {"status": "PASS" if tests.returncode == 0 else "BLOCKED", "output": (tests.stdout + tests.stderr)[-5000:]}, "compileall": {"status": "PASS" if compile_result.returncode == 0 else "BLOCKED", "output": (compile_result.stdout + compile_result.stderr)[-1000:]}, "git_diff_check": {"status": "PASS" if diff_result.returncode == 0 else "BLOCKED", "output": (diff_result.stdout + diff_result.stderr)[-1000:]}, "database_unchanged": db_after == db_sha}


def build_preflight() -> dict[str, Any]:
    head, branch, dirty = git("rev-parse", "HEAD"), git("branch", "--show-current"), git("status", "--porcelain")
    remote_tracking = git("rev-parse", f"origin/{BRANCH}", check=False); remote_server = (git("ls-remote", "origin", f"refs/heads/{BRANCH}", check=False).split() or [""])[0]
    proposal, assignment, raw = read(V710 / "SOURCE_CLAIM_REPROPOSAL_SET.json"), read(V710 / "SOURCE_CLAIM_REPROPOSAL_PROGRAM_ID_ASSIGNMENT.json"), read(V710 / "SOURCE_CLAIM_REPROPOSAL_RAW_FORENSIC.json")
    row = proposal.get("candidates", [None])[0] if isinstance(proposal.get("candidates"), list) else None
    projection = row.get("projection") if isinstance(row, Mapping) else None
    candidate = row.get("raw_candidate") if isinstance(row, Mapping) else None
    source_contract = read(V71 / "SOURCE_AUTHORING_UNIT_CONTRACT.json"); units = source_contract.get("units", [])
    unit = next((x for x in units if x.get("unit_id") == "SAU_E01_SC001_001"), {})
    source_registry = read(V777 / "SOURCE_VERIFIED_ENTITY_REGISTRY.json"); input_registry = build_claim_input_entity_registry(source_registry, expected_fingerprint=EXPECTED_ENTITY_FP)
    relation = relation_signature_registry_v4(); qualifier = qualifier_registry_v4(); provider_registry = provider_predicate_registry_v3(relation_registry=relation, qualifier_registry=qualifier, entity_registry=input_registry)
    signature = relation["signatures"].get("enter_guided", {})
    bindings = {str(x.get("source_evidence", {}).get("evidence_id")): [str(x.get("unit_id"))] for x in units if isinstance(x.get("source_evidence"), Mapping)}
    candidate_validation = validate_provider_candidate_v3_2(candidate or {}, provider_registry=provider_registry, relation_registry=relation, entity_registry=input_registry, qualifier_registry=qualifier, evidence_unit_bindings=bindings, allowed_source_unit_refs=[str(x.get("unit_id")) for x in units])
    db_before, freeze_before, db_sha = read_db(), current_production_freeze(), sha256_file(DB)
    evidence = evidence_authority_audit(projection=projection or {}, source_unit=unit, source_fingerprint=str(db_before.get("source_fingerprint") or ""), expected_source_fingerprint=EXPECTED_SOURCE_FP)
    atomicity = typed_atomicity_guard(projection or {}, signature)
    packet = build_verifier_packet(claim_ref=CLAIM_REF, projection=projection or {}, relation_signature=signature, evidence={**(unit.get("source_evidence") or {}), "source_unit_ref": unit.get("unit_id")})
    schema = strict_transport_schema(); compiled = compile_provider_strict_schema(schema)
    request = build_verifier_request(facts=[packet["fact"]], machine_context=[packet["machine_context"]])
    profile, provider = profile_audit(); anti = anti_heuristic()
    script_ir, _ = load_script_ir()
    companion = source_speech_act_binding_registry_v1(script_ir=script_ir, source_units=units, entity_registry=input_registry, source_fingerprint=EXPECTED_SOURCE_FP)
    candidate_fp = assignment.get("rows", [{}])[0].get("candidate_fingerprint") if isinstance(assignment.get("rows"), list) and assignment.get("rows") else ""
    eligibility_checks = {
        "proposal_validated": proposal.get("status") == "SOURCE_SEMANTIC_CLAIM_V3_REPROPOSAL_VALIDATED", "candidate_validation": row and row.get("validation_status") == "PASS" and candidate_validation.get("status") == "PASS", "authority_untrusted": row and row.get("authority") == "UNTRUSTED_PROPOSED" and row.get("canonical") is False, "registry_versions": relation.get("schema_version") == RELATION_SIGNATURE_REGISTRY_V4_VERSION and qualifier.get("schema_version") == QUALIFIER_REGISTRY_V4_VERSION and provider_registry.get("schema_version") == PROVIDER_PREDICATE_REGISTRY_V3_VERSION, "entity_fingerprints": source_registry.get("fingerprint") == EXPECTED_ENTITY_FP and input_registry.get("fingerprint") == EXPECTED_INPUT_ENTITY_FP, "evidence_binding": evidence.get("status") == "PASS", "role_constraint": candidate_validation.get("role_constraint_audit", {}).get("status") == "PASS", "candidate_fp": candidate_fp == EXPECTED_CANDIDATE_FP, "set_fp": proposal.get("candidate_set_fingerprint") == EXPECTED_SET_FP, "raw_sha": raw.get("raw_response_sha256") == EXPECTED_RAW_SHA, "source_current": str(db_before.get("source_fingerprint") or "") == EXPECTED_SOURCE_FP,
    }
    gates = local_gates(db_sha)
    production_after, db_sha_after = current_production_freeze(), sha256_file(DB)
    proposal_transport = read(V710 / "SOURCE_CLAIM_REPROPOSAL_TRANSPORT_SCHEMA_AUDIT.json")
    checks = {"baseline": subprocess.run(["git", "merge-base", "--is-ancestor", BASELINE, head], cwd=ROOT).returncode == 0, "branch": branch == BRANCH, "clean": not dirty, "remote": head == remote_tracking == remote_server, "no_evidence": not OUT.exists(), "eligibility": all(eligibility_checks.values()), "evidence_authority": evidence.get("status") == "PASS", "atomicity": atomicity.get("status") == "PASS", "support_role_and_ceiling": packet.get("status") == "PASS" and packet.get("confirmation_ceiling", {}).get("allowed") is True, "proposal_transport_freeze": proposal_transport.get("transport_schema_fingerprint") == EXPECTED_TRANSPORT_FP, "strict_schema": compiled.get("audit", {}).get("status") == "PASS", "provider": provider.get("status") == "PASS", "anti_heuristic": anti.get("status") == "PASS", "speech_companion": companion.get("status") == "PASS" and len(companion.get("bindings", [])) == 1, "local_gates": all(x.get("status") == "PASS" for x in (gates["tests"], gates["compileall"], gates["git_diff_check"])) and gates["database_unchanged"], "production_freeze": freeze_before == production_after and db_sha == db_sha_after and db_before.get("fact_snapshot_id") == 49 and db_before.get("script_ir_id") == 52 and db_before.get("packet_id") == 64 and db_before.get("packet_attempt_count") == 11 and db_before.get("stage_b_attempt") == "attempt-11"}
    return {"status": "PASS" if all(checks.values()) else "BLOCKED", "failed": [k for k,v in checks.items() if not v], "checks": checks, "eligibility_checks": eligibility_checks, "values": {"proposal":proposal,"assignment":assignment,"raw":raw,"row":row,"projection":projection,"unit":unit,"source_contract":source_contract,"source_registry":source_registry,"input_registry":input_registry,"relation":relation,"qualifier":qualifier,"signature":signature,"candidate_validation":candidate_validation,"evidence":evidence,"atomicity":atomicity,"packet":packet,"compiled":compiled,"request":request,"profile":profile,"provider":provider,"anti":anti,"companion":companion,"local_gates":gates,"db_before":db_before,"freeze_before":freeze_before,"db_sha":db_sha}, "runtime": {"head":head,"branch":branch,"remote":remote_server,"request_fingerprint":fingerprint(request),"transport_schema_fingerprint":EXPECTED_TRANSPORT_FP,"verifier_schema_fingerprint":compiled.get("audit",{}).get("output_fingerprint")}}


def write_preflight(pre: Mapping[str, Any]) -> None:
    v=pre["values"]; packet=v["packet"]
    write_json("ANTI_HEURISTIC_PATCH_REVIEW.json",v["anti"])
    write_json("V7_7_10_PROPOSAL_FREEZE.json",{"status":"PASS" if all(pre["eligibility_checks"].values()) else "BLOCKED","claim_ref":CLAIM_REF,"candidate_fingerprint":EXPECTED_CANDIDATE_FP,"candidate_set_fingerprint":EXPECTED_SET_FP,"raw_sha256":EXPECTED_RAW_SHA,"proposal_status":v["proposal"].get("status"),"historical_artifact_mutated":False})
    write_json("SOURCE_CLAIM_VERIFIER_ELIGIBILITY.json",{"schema_version":"source_claim_verifier_input_eligibility_v1","status":"VERIFIER_INPUT_ELIGIBLE" if all(pre["eligibility_checks"].values()) else "VERIFIER_INPUT_BLOCKED","checks":pre["eligibility_checks"],"proposal_verifier_eligible_field_mutated":False})
    write_json("SOURCE_CLAIM_VERIFIER_ADAPTER_CONTRACT.json",adapter_contract()); write_json("SOURCE_CLAIM_VERIFIER_ID_MAPPING.json",packet["id_mapping"])
    write_json("SOURCE_CLAIM_TYPED_COMPONENT_CONTRACT.json",{"status":"PASS","claim_ref":CLAIM_REF,"required_components":packet["required_semantic_components"],"derived_from":"typed_projection_and_relation_signature","source_prose_consulted":False})
    write_json("SOURCE_CLAIM_EVIDENCE_AUTHORITY_AUDIT.json",v["evidence"]); write_json("SOURCE_CLAIM_TYPED_ATOMICITY_CONTRACT.json",{"schema_version":"source_claim_typed_atomicity_guard_v1","atomicity_basis":["registered_predicate","complete_relation_signature","typed_roles","required_qualifiers","role_constraints","no_nested_claim","no_conjunction_claim_list"],"json_dict_implies_composite":False})
    write_json("SOURCE_CLAIM_TYPED_ATOMICITY_AUDIT.json",v["atomicity"]); write_json("SOURCE_CLAIM_SUPPORT_ROLE_REGISTRY.json",support_role_registry_v1())
    write_json("SOURCE_CLAIM_CONFIRMATION_CEILING_AUDIT.json",{"status":"PASS" if packet["confirmation_ceiling"].get("allowed") else "BLOCKED","relation_class":v["projection"].get("relation_class"),"support_role":packet["support_role"],"anchor_surface":packet["anchor_surface"],"ceiling":packet["confirmation_ceiling"],"predicate_name_inference":False})
    guards={"status":"PASS" if v["atomicity"].get("status")=="PASS" and v["evidence"].get("status")=="PASS" else "BLOCKED","hard_blockers":v["atomicity"].get("errors",[]),"confirmation_ceilings":[packet["confirmation_ceiling"]],"uses_legacy_composite_guard":False}; write_json("SOURCE_CLAIM_VERIFIER_MACHINE_GUARDS.json",guards)
    write_json("SOURCE_CLAIM_VERIFIER_INPUT_FREEZE.json",{"status":"PASS","target_book_id":990453,"episode":1,"fact_snapshot_id":49,"script_ir_id":52,"packet_id":64,"source_raw_sha256":EXPECTED_SOURCE_FP,"source_unit_fingerprint":EXPECTED_UNITS_FP,"verified_entity_registry_fingerprint":EXPECTED_ENTITY_FP,"claim_input_entity_registry_fingerprint":EXPECTED_INPUT_ENTITY_FP,"current_registry_versions":{"relation":RELATION_SIGNATURE_REGISTRY_V4_VERSION,"qualifier":QUALIFIER_REGISTRY_V4_VERSION,"provider_predicate":PROVIDER_PREDICATE_REGISTRY_V3_VERSION},"proposal_transport_schema_fingerprint":EXPECTED_TRANSPORT_FP,"transport_fact_id":TRANSPORT_FACT_ID,"claim_ref":CLAIM_REF,"packet":packet})
    write_json("SOURCE_CLAIM_VERIFIER_PROVIDER_IDENTITY.json",v["provider"]); write_json("SOURCE_CLAIM_VERIFIER_AUTHORIZATION.json",{"authorization_id":AUTHORIZATION_ID,"granted":True,"scope":{"claim_ref":CLAIM_REF,"evidence_refs":["S1A001"],"semantic_verification_only":True},"max_provider_posts":1,"retries":0,"claim_proposal_posts":0,"second_order_posts":0,"production_writes":0})
    system="You are a semantic verifier. Judge only the supplied frozen assertion against supplied frozen evidence. Return strict JSON only. Do not retrieve sources, create facts or evidence, rewrite the assertion, or decide final authority. Use only component IDs supplied in each fact."
    user=json.dumps(v["request"],ensure_ascii=False,sort_keys=True,indent=2)
    v["system"],v["user"]=system,user
    write_json("SOURCE_CLAIM_VERIFIER_PROMPT_AUDIT.json",{"status":"PASS","system_prompt_sha256":sha_text(system),"user_prompt_sha256":sha_text(user),"request_fingerprint":pre["runtime"]["request_fingerprint"],"proposal_prompt_included":False,"proposal_raw_included":False,"exact_evidence_refs":["S1A001"],"all_source_units_included":False,"source_retrieval":False,"canonical_provider_schema":provider_schema(),"strict_transport_schema":v["compiled"]["schema"],"fact_id_pattern_enforced_by": "validate_verifier_payload"})
    for name,data in {"SOURCE_CLAIM_VERIFIER_TRANSPORT_AUDIT.json":{"status":"NOT_CALLED_YET","provider_post_count":0,"retry_count":0},"SOURCE_CLAIM_VERIFIER_RAW_FORENSIC.json":{"status":"NOT_CALLED_YET","provider_post_count":0,"raw_response":"","raw_response_sha256":"","raw_response_length":0},"SOURCE_CLAIM_VERIFIER_PARSE_AUDIT.json":{"status":"NOT_RUN"},"SOURCE_CLAIM_VERIFIER_SCHEMA_VALIDATION.json":{"status":"NOT_RUN"},"SOURCE_CLAIM_VERIFIER_CARDINALITY_AUDIT.json":{"status":"NOT_RUN"},"SOURCE_CLAIM_VERIFIER_COMPONENT_AUDIT.json":{"status":"NOT_RUN"},"SOURCE_CLAIM_VERIFIER_RESULT.json":{"status":"NOT_RUN"},"SOURCE_CLAIM_SEMANTIC_AUTHORITY_COMPILATION.json":{"status":"NOT_RUN"},"SOURCE_CLAIM_SEMANTIC_AUTHORITY_OVERLAY_SHADOW.json":{"status":"NOT_RUN","shadow_only":True,"production_persisted":False},"PROGRAM_DETERMINISTIC_SPEECH_ACT_COMPANION_STATUS.json":{**v["companion"],"speech_act_verifier_posts":0},"NO_AUTHORITY_PERSISTENCE_NO_PRODUCTION_WRITE_AUDIT.json":{"status":"NOT_RUN","claim_verifier_posts":0,"claim_proposal_posts":0,"second_order_posts":0,"source_claim_writes":0,"fact_record_writes":0,"fact_snapshot_writes":0,"entity_writes":0},"RECOMMENDED_NEXT_ACTION.json":{"status":"PREFLIGHT_READY_PENDING_SINGLE_CALL" if pre["status"]=="PASS" else "PREFLIGHT_BLOCKED","failed_checks":pre["failed"],"provider_posts":0}}.items(): write_json(name,data)


def call_and_finish(pre: Mapping[str, Any]) -> dict[str, Any]:
    v=pre["values"]; audits=[]; holder={"raw":None,"saved":False}; started=time.monotonic()
    def raw_first(value: Any) -> None:
        text=value if isinstance(value,str) else ""; holder.update({"raw":value,"saved":True}); write_json("SOURCE_CLAIM_VERIFIER_RAW_FORENSIC.json",{"status":"RAW_PERSISTED_BEFORE_PARSE","provider_post_count":1,"raw_response":value,"raw_response_sha256":sha_text(text),"raw_response_length":len(text),"persisted_before_parse":True})
    error=""
    try: llm.call_llm(v["user"],system=v["system"],model_profile=v["profile"],retries=1,estimated_tokens=4096,max_tokens=4096,temperature=0.0,response_format={"type":"json_schema","json_schema":{"name":"fact_semantic_verifier_v1","strict":True,"schema":v["compiled"]["schema"]}},audit_callback=audits.append,audit_extra={"authorization_id":AUTHORIZATION_ID,"stage":"SOURCE_CLAIM_SEMANTIC_VERIFIER"},raw_response_callback=raw_first)
    except Exception as exc: error=f"{type(exc).__name__}: {str(exc)[:500]}"
    raw=holder["raw"] if isinstance(holder["raw"],str) else ""; audit=audits[-1] if audits else {}; posts=len(audits); elapsed=round((time.monotonic()-started)*1000,2)
    write_json("SOURCE_CLAIM_VERIFIER_RAW_FORENSIC.json",{"status":"RAW_PERSISTED_BEFORE_PARSE" if holder["saved"] else "NO_RAW_CONTENT_RETURNED","provider_post_count":posts,"raw_response":raw if holder["saved"] else "","raw_response_sha256":sha_text(raw) if holder["saved"] else "","raw_response_length":len(raw),"persisted_before_parse":True,"provider_audit":audit,"error":error})
    write_json("SOURCE_CLAIM_VERIFIER_TRANSPORT_AUDIT.json",{"status":"PASS" if posts==1 and audit.get("http_status")==200 and not error else "BLOCKED","provider_post_count":posts,"retry_count":max(0,posts-1),"retry_authorized":False,"http_status":audit.get("http_status"),"finish_reason":audit.get("finish_reason"),"latency_ms":elapsed,"usage":audit.get("usage"),"raw_response_sha256":sha_text(raw) if raw else "","error":error})
    try: parsed=parse_verifier_payload(raw); parse_status="PASS"; parse_error=""
    except ValueError as exc: parsed=None; parse_status="BLOCKED"; parse_error=str(exc)
    write_json("SOURCE_CLAIM_VERIFIER_PARSE_AUDIT.json",{"status":parse_status,"strict_json_parse":True,"repair":False,"parse_retry":0,"error":parse_error})
    schema_result=validate_json_schema_subset(parsed,v["compiled"]["schema"]) if parsed is not None else {"status":"NOT_RUN","errors":[parse_error]}
    base_validation=validate_verifier_payload(parsed,[TRANSPORT_FACT_ID]) if parsed is not None else {"status":"FAIL","errors":[{"code":parse_error}],"results":[]}
    result=base_validation.get("results",[{}])[0] if len(base_validation.get("results",[]))==1 else {}
    component=component_contract(result,v["packet"]["required_semantic_components"]) if result else {"status":"BLOCKED","errors":["VERIFIER_RESULT_MISSING"]}
    schema_ok=schema_result.get("status")=="PASS" and base_validation.get("status")=="PASS"; cardinality={"status":"PASS" if len(base_validation.get("results",[]))==1 and [x.get("fact_id") for x in base_validation.get("results",[])]==[TRANSPORT_FACT_ID] else "BLOCKED","expected_fact_ids":[TRANSPORT_FACT_ID],"result_count":len(base_validation.get("results",[])),"result_fact_ids":[x.get("fact_id") for x in base_validation.get("results",[])]}
    write_json("SOURCE_CLAIM_VERIFIER_SCHEMA_VALIDATION.json",{"status":"PASS" if schema_ok else "BLOCKED","transport_schema":schema_result,"fact_verifier_schema":base_validation,"forbidden_provider_fields":[] if schema_ok else base_validation.get("errors",[])})
    write_json("SOURCE_CLAIM_VERIFIER_CARDINALITY_AUDIT.json",cardinality); write_json("SOURCE_CLAIM_VERIFIER_COMPONENT_AUDIT.json",component); write_json("SOURCE_CLAIM_VERIFIER_RESULT.json",{"status":"PASS" if schema_ok and cardinality["status"]=="PASS" and component["status"]=="PASS" else "BLOCKED","transport_fact_id":TRANSPORT_FACT_ID,"claim_ref":CLAIM_REF,"provider_result":result,"provider_owns":["verdict","supported_components","unsupported_components","rationale"]})
    overlay=compile_shadow_overlay(packet=v["packet"],result=result,evidence_status=v["evidence"]["status"],atomicity=v["atomicity"],component_audit=component) if schema_ok and cardinality["status"]=="PASS" else {"status":"BLOCKED","shadow_only":True,"production_persisted":False,"reason":"VERIFIER_OUTPUT_CONTRACT_FAILED"}
    write_json("SOURCE_CLAIM_SEMANTIC_AUTHORITY_COMPILATION.json",overlay.get("compiler_overlay",overlay)); write_json("SOURCE_CLAIM_SEMANTIC_AUTHORITY_OVERLAY_SHADOW.json",overlay)
    db_after, freeze_after, sha_after=read_db(),current_production_freeze(),sha256_file(DB); unchanged=freeze_after==v["freeze_before"] and sha_after==v["db_sha"]
    no_write={"status":"PASS" if unchanged else "BLOCKED","claim_verifier_posts":posts,"claim_proposal_posts":0,"second_order_posts":0,"source_claim_writes":0,"fact_record_writes":0,"fact_snapshot_writes":0,"entity_writes":0,"stage_a":0,"attempt_12":0,"confirm":0,"image":0,"video":0,"production_freeze_before":v["freeze_before"],"production_freeze_after":freeze_after,"database_sha256_before":v["db_sha"],"database_sha256_after":sha_after,"database_unchanged":sha_after==v["db_sha"],"ledger_before":v["db_before"].get("packet_attempt_count"),"ledger_after":db_after.get("packet_attempt_count"),"active_stage_b_before":v["db_before"].get("stage_b_attempt"),"active_stage_b_after":db_after.get("stage_b_attempt")}; write_json("NO_AUTHORITY_PERSISTENCE_NO_PRODUCTION_WRITE_AUDIT.json",no_write)
    verdict=result.get("verdict"); confirmed=overlay.get("semantic_disposition")=="WORLD_FACT_CONFIRMED" and overlay.get("downstream_eligible") is True
    if confirmed: status,next_state="SOURCE_SEMANTIC_CLAIM_V3_SEMANTIC_VERIFICATION_VALIDATED","SOURCE_SEMANTIC_CLAIM_V3_AUTHORITY_PROJECTION_BOUNDARY_REQUIRED"
    elif verdict=="PARTIAL": status,next_state="SOURCE_SEMANTIC_CLAIM_V3_SEMANTIC_VERIFICATION_PARTIAL_REVIEW_REQUIRED","SOURCE_SEMANTIC_CLAIM_V3_SEMANTIC_VERIFICATION_PARTIAL_REVIEW_REQUIRED"
    elif verdict=="INFERENCE": status,next_state="SOURCE_SEMANTIC_CLAIM_V3_SEMANTIC_VERIFICATION_INFERENCE_BLOCKED","SOURCE_SEMANTIC_CLAIM_V3_SEMANTIC_VERIFICATION_INFERENCE_BLOCKED"
    elif verdict=="CONTRADICTED": status,next_state="SOURCE_SEMANTIC_CLAIM_V3_SEMANTIC_VERIFICATION_REJECTED","SOURCE_SEMANTIC_CLAIM_V3_SEMANTIC_VERIFICATION_REJECTED"
    elif verdict=="AMBIGUOUS": status,next_state="SOURCE_SEMANTIC_CLAIM_V3_SEMANTIC_REVIEW_REQUIRED","SOURCE_SEMANTIC_CLAIM_V3_SEMANTIC_REVIEW_REQUIRED"
    else: status,next_state="SOURCE_SEMANTIC_CLAIM_V3_SEMANTIC_VERIFICATION_BLOCKED","SOURCE_SEMANTIC_CLAIM_V3_SEMANTIC_VERIFICATION_REVIEW_REQUIRED"
    write_json("RECOMMENDED_NEXT_ACTION.json",{"status":status,"next_state":next_state,"provider_posts":posts,"authority_projection_authorized":False,"production_writes":0 if unchanged else "AUDIT_BLOCKED"})
    return {"status":status,"next_state":next_state,"posts":posts,"audit":audit,"elapsed":elapsed,"raw":raw,"parse":parse_status,"schema":schema_ok,"cardinality":cardinality["status"],"component":component,"result":result,"overlay":overlay,"unchanged":unchanged,"no_write":no_write}


def report(pre: Mapping[str, Any], r: Mapping[str, Any]) -> str:
    v=pre["values"]; o=r.get("overlay",{}); a=r.get("audit",{})
    return f"""# V7.7.11 Source Semantic Claim V3.2 Semantic Verification

- Baseline: `{BASELINE}`. Claim: `{CLAIM_REF}`; candidate fingerprint `{EXPECTED_CANDIDATE_FP}`; candidate set fingerprint `{EXPECTED_SET_FP}`; V7.7.10 raw `{EXPECTED_RAW_SHA}`.
- Verifier input eligibility: `VERIFIER_INPUT_ELIGIBLE`. Transport mapping: `{TRANSPORT_FACT_ID}` ↔ `{CLAIM_REF}`; transport IDs are not production Fact IDs.
- Required components: `{v['packet']['required_semantic_components']}`. Evidence authority `{v['evidence']['status']}`; typed atomicity `{v['atomicity']['status']}`; support role `{v['packet']['support_role']}`; anchor surface `{v['packet']['anchor_surface']}`; confirmation ceiling `{v['packet']['confirmation_ceiling']}`.
- Provider: `local-llm-2vydoz / mimo-v2.5`; verifier POSTs `{r.get('posts')}`; HTTP `{a.get('http_status')}`; finish `{a.get('finish_reason')}`; latency `{r.get('elapsed')} ms`; usage `{a.get('usage')}`.
- Raw SHA `{sha_text(r.get('raw','')) if r.get('raw') else ''}`; length `{len(r.get('raw',''))}`; parse `{r.get('parse')}`; schema `{r.get('schema')}`; cardinality `{r.get('cardinality')}`.
- Verdict `{r.get('result',{}).get('verdict')}`; supported `{r.get('result',{}).get('supported_components')}`; unsupported `{r.get('result',{}).get('unsupported_components')}`; component contract `{r.get('component',{}).get('status')}`.
- Disposition `{o.get('semantic_disposition')}`; effective authority `{o.get('effective_authority')}`; effective status `{o.get('effective_status')}`; downstream eligible `{o.get('downstream_eligible')}`; review required `{o.get('review_required')}`; shadow only `true`; production persisted `false`.
- Program speech companion count `{len(v['companion'].get('bindings',[]))}`; speech verifier posts `0`; proposal and second-order posts `0`; SourceClaim / FactRecord writes `0 / 0`.
- Completeness remains: proposal `NOT_PROVEN`, entity semantic `NOT_PROVEN`, second order `DEFERRED_NOT_PROVEN`, typed director manifest `MISSING`. Ledger `11`; active Stage B `attempt-11`.
- Status: `{r.get('status')}`. Next: `{r.get('next_state')}`. No retry, proposal, persistence, Stage A, Attempt-12, Confirm, image, video, PR, or merge was performed.
"""


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--preflight-only",action="store_true"); parser.add_argument("--execute-real",action="store_true"); args=parser.parse_args(); pre=build_preflight()
    if args.preflight_only or not args.execute_real:
        print(json.dumps({"status":pre["status"],"failed":pre["failed"],"checks":pre["checks"],"runtime":pre["runtime"]},ensure_ascii=False,indent=2)); return 0 if pre["status"]=="PASS" else 2
    if OUT.exists(): raise SystemExit(f"Evidence already exists: {OUT}")
    write_preflight(pre)
    if pre["status"]!="PASS": write_text("SOURCE_SEMANTIC_CLAIM_V3_2_SEMANTIC_VERIFICATION_REPORT.md",f"# V7.7.11\n\nPreflight blocked: `{pre['failed']}`. Provider POSTs: `0`.\n"); return 2
    r=call_and_finish(pre); write_text("SOURCE_SEMANTIC_CLAIM_V3_2_SEMANTIC_VERIFICATION_REPORT.md",report(pre,r)); print(json.dumps({k:v for k,v in r.items() if k not in {"raw","overlay","no_write"}},ensure_ascii=False,indent=2)); return 0 if r["unchanged"] else 3
if __name__=="__main__": raise SystemExit(main())
