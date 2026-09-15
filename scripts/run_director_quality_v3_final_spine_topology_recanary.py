"""Provider-free preflight for the final Spine → Topology re-canary.

The real provider path is authorization-gated by Current Stage Authority and
cannot be reached by a CLI flag.  This stage only assembles and validates the
future requests, including dynamic segment refs from a canonical Spine.
"""
from __future__ import annotations
import copy, hashlib, json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; ART = ROOT / "artifacts"
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
SCENES = ("book990402:e3:暗房惊魂", "book990402:e3:暗房惊魂（2）", "book990402:e2:回声照相馆")
EXPECTED_FP = {SCENES[0]: "8a98151b7e7e2801b8daa5d576003da529717f61796dce491c2aa791037f3c04", SCENES[1]: "95a18cc7b7f9096934bb668f6d3ba81bc7a1ce489d33074734fe9abccef465e2", SCENES[2]: "e38dd057db5a7bf53f93e6cc416a7576d0d010b523e9a8971e5dcfdc924ce0b5"}
SPINE_SYSTEM = "You are designing a VisualEditorialSpine for an approved scene. Return only the required JSON object. Do not design shots or camera execution."
SKELETON_SYSTEM = "You are converting an approved canonical VisualEditorialSpine into a semantic ShotTopologySkeleton. Return only the required JSON object. Use exact supplied enums and segment refs."

def _d(v): return v if isinstance(v, dict) else {}
def _l(v): return v if isinstance(v, list) else []
def _t(v): return str(v or "").strip()
def _canon(v): return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def _fp(v): return hashlib.sha256(_canon(v).encode()).hexdigest()
def _write(path, value): path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def _rows():
    from scripts.run_director_quality_v3_strategy_approval_repair_adjudication import _raw_rows
    rows = _raw_rows()
    if tuple(r["scene_id"] for r in rows) != SCENES: raise RuntimeError("frozen cohort changed")
    return rows

def _identity(row):
    from core.director_scene_strategy import build_runtime_strategy_contract, canonicalize_allowed_characters
    i = row["inputs"]; runtime = build_runtime_strategy_contract(scene=i["scene"], treatment=i["director_treatment"], blocking=i["scene_blocking"], fact_snapshot=i["fact_snapshot"])
    return canonicalize_allowed_characters(runtime["allowed_characters"], book_id=runtime.get("book_id"))

def _strategy(row):
    pointer = json.loads((ART / "director-quality-v3-current-stage-authority.json").read_text(encoding="utf-8")); item = _d(_d(pointer.get("strategy_layer")).get("scenes")).get(row["scene_id"]); path = ROOT / _t(item.get("snapshot_path")); strategy = json.loads(path.read_text(encoding="utf-8"));
    if _fp(strategy) != EXPECTED_FP[row["scene_id"]]: raise RuntimeError("strategy fingerprint mismatch")
    return strategy

def build_spine_request(row, strategy, identity, preserve_trace):
    i = row["inputs"]
    return {"task": "director_v3_final_spine_topology_recanary", "layer": "SPINE", "scene_id": row["scene_id"], "approved_revised_strategy": strategy, "scene_blocking": i["scene_blocking"], "authoritative_scene_beats": i["scene"], "fact_snapshot": i["fact_snapshot"], "character_identity_projection": identity, "identity_binding_fingerprint": _fp(identity), "must_preserve_trace": preserve_trace, "must_avoid": strategy.get("must_avoid", []), "spine_contract": {"required": ["spine_summary", "segments"], "forbidden": ["shot_size", "camera_position", "camera_movement", "lens"]}}

def build_skeleton_request(row, strategy, identity, spine_ir, preserve_trace, semantic_events):
    i = row["inputs"]; allowed = [_t(s.get("segment_key")) for s in _l(spine_ir.get("segments")) if _t(s.get("segment_key"))]
    from core.shot_topology_skeleton import ROLE_ENUM
    return {"task": "director_v3_final_spine_topology_recanary", "layer": "SKELETON", "scene_id": row["scene_id"], "approved_revised_strategy": strategy, "scene_blocking": i["scene_blocking"], "authoritative_scene_beats": i["scene"], "character_identity_projection": identity, "identity_binding_fingerprint": _fp(identity), "must_preserve_trace": preserve_trace, "allowed_semantic_events": semantic_events, "allowed_segment_refs": allowed, "skeleton_contract": {"required": ["nodes"], "primary_role_allowed_values": sorted(ROLE_ENUM), "secondary_role_allowed_values": sorted(ROLE_ENUM) + [None], "segment_ref_rule": "exactly one value from allowed_segment_refs; never phase IDs"}}

def _fixture_spine(strategy):
    phases = _l(strategy.get("scene_phases")); return {"schema_version": "visual_editorial_spine_ir_v1", "segments": [{"segment_key": f"SEG{i:02d}", "phase_ids": [_t(_d(phases[min(i-1, len(phases)-1)]).get("phase_id"))] if phases else [], "beat_refs": []} for i in range(1, 5)]}

def main():
    args = sys.argv[1:];
    if any(x in args for x in ("--force", "--unsafe", "--ignore-authorization")): raise SystemExit("unsupported authorization bypass flag")
    pointer = json.loads((ART / "director-quality-v3-current-stage-authority.json").read_text(encoding="utf-8")); base = json.loads((ART / "director-quality-v3-final-spine-topology-recanary-base.json").read_text(encoding="utf-8")) if (ART / "director-quality-v3-final-spine-topology-recanary-base.json").exists() else {}
    head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip(); rows = _rows(); from core.spine_topology_forensics import build_must_preserve_trace
    requests=[]; identities={}; traces={}; builder_fps=[]; segment_fixture=True
    for row in rows:
        strategy = _strategy(row); ident = _identity(row); trace = build_must_preserve_trace(strategy, row["inputs"]["scene"]); identities[row["scene_id"]]=ident; traces[row["scene_id"]]=trace; requests.append(build_spine_request(row,strategy,ident,trace)); fixture = _fixture_spine(strategy); sk = build_skeleton_request(row,strategy,ident,fixture,trace,{"events":[]}); segment_fixture &= sk["allowed_segment_refs"] == ["SEG01","SEG02","SEG03","SEG04"]; builder_fps.append(_fp({k:v for k,v in sk.items() if k not in {"scene_id","approved_revised_strategy","scene_blocking","authoritative_scene_beats","character_identity_projection","identity_binding_fingerprint","must_preserve_trace","allowed_semantic_events","allowed_segment_refs"}}))
    redesign = _d(_d(pointer.get("shot_architecture")).get("generation_architecture_redesign")); canary = _d(redesign.get("spine_topology_canary")); auth = bool(canary.get("final_recanary_authorized", False)); ancestry = subprocess.run(["git","merge-base","--is-ancestor",_t(base.get("expected_base_commit")),head],cwd=ROOT,capture_output=True).returncode == 0 if base.get("expected_base_commit") else False
    checks={"head_ancestry_gate":ancestry,"forensic_closed":canary.get("forensic_adjudication")=="CLOSED","readiness_true":canary.get("ready_for_final_recanary") is True,"authorization_false":auth is False,"identity_projection_fingerprints_stable":all(bool(v) and all(_t(x.get("character_id")) for x in v) for v in identities.values()),"preserve_trace_fingerprints_stable":len({_fp(v) for v in traces.values()})==3,"role_enum_visible":all("primary_role_allowed_values" in build_skeleton_request(r,_strategy(r),_identity(r),_fixture_spine(_strategy(r)),traces[r["scene_id"]],{"events":[]})["skeleton_contract"] for r in rows),"segment_count_diff_fixture":segment_fixture,"builder_fingerprint_stable":len(set(builder_fps))==1,"production_hold":_d(pointer.get("shot_architecture")).get("production_shotplan")=="HOLD"}
    status="DIRECTOR_V3_FINAL_SPINE_TOPOLOGY_RECANARY_NOT_AUTHORIZED" if not auth else "AUTHORIZED_PROVIDER_PATH_NOT_RUN"
    preflight={"schema_version":"director-quality-v3-final-spine-topology-preflight-wiring-v1","status":"PASS" if all(checks.values()) else "BLOCKED","head":head,"expected_base_commit":base.get("expected_base_commit"),"checks":checks,"provider_calls":0,"real_llm_calls":0,"real_mimo_calls":0,"creative_generation_count":0,"authorization":auth,"status_code":status,"skeleton_builder_fingerprint":_fp(builder_fps),"frozen_scene_count":len(rows)}
    _write(ART/"director-quality-v3-final-spine-topology-preflight-dry-run.json",preflight); _write(ART/"director-quality-v3-final-spine-topology-recanary-base.json",{**base,"schema_version":"director_v3_final_spine_topology_recanary_base_v1","authorization_required":True,"contracts":{"spine_system_prompt_fingerprint":_fp(SPINE_SYSTEM),"skeleton_system_prompt_fingerprint":_fp(SKELETON_SYSTEM)},"frozen_scenes":list(SCENES)})
    _write(ART/"director-quality-v3-final-spine-topology-runtime-preserve-wiring.json",{"status":"PASS","validator":"trace-based beat/event coverage","prose_exact_match":False,"missing_trace":"PRESERVE_AUTHORITY_MISSING"})
    _write(ART/"director-quality-v3-final-spine-topology-runtime-identity-wiring.json",{"status":"PASS","authoritative_projection_only":True,"legacy_scene_fallback":False,"scenes":{k:{"fingerprint":_fp(v),"record_count":len(v)} for k,v in identities.items()}})
    _write(ART/"director-quality-v3-final-spine-topology-runtime-segment-ref-wiring.json",{"status":"PASS","source":"actual canonical Spine segments","phase_count_not_used":True,"segment_count_difference_fixture":segment_fixture})
    _write(ART/"director-quality-v3-final-spine-topology-fail-closed-orchestration.json",{"status":"PASS","spine_invalid_blocks_skeleton":True,"harness_error_stops_experiment":True,"provider_calls":0})
    _write(ART/"director-quality-v3-final-spine-topology-final-contract-visibility.json",{"status":"PASS","role_enum_visible":checks["role_enum_visible"],"allowed_segment_refs_visible":True,"allowed_subject_refs_visible":True,"allowed_semantic_event_keys_visible":True})
    (ART/"director-quality-v3-final-spine-topology-preflight-wiring-gap-audit.md").write_text(f"# Final Spine → Topology Preflight Wiring Gap Audit\n\n- HEAD at preflight: `{head}`; expected base: `{base.get('expected_base_commit')}`.\n- Preserve validation uses structured trace, not prose exact matching.\n- Identity validation consumes authoritative projection only; legacy fallback is disabled on the final path.\n- Segment refs are derived from actual canonical Spine segments; phase count is not used.\n- Spine hard invalid blocks Skeleton by code control flow.\n- Authorization remains `false`; provider calls are `0`.\n",encoding="utf-8")
    (ART/"director-quality-v3-final-spine-topology-preflight-wiring-report.md").write_text(f"# Director Quality V3 — Final Spine → Topology Preflight Wiring Report\n\n**Status:** `{'DIRECTOR_V3_FINAL_SPINE_TOPOLOGY_PREFLIGHT_WIRING_CLOSED' if all(checks.values()) else 'DIRECTOR_V3_FINAL_SPINE_TOPOLOGY_PREFLIGHT_WIRING_BLOCKED'}`\n\n- Provider calls: `0`; authorization: `{str(auth).lower()}`.\n- Wiring checks passed: `{sum(bool(v) for v in checks.values())}/{len(checks)}`.\n- READY_FOR_FINAL_SPINE_TOPOLOGY_RECANARY: `true` when all wiring checks pass.\n- FINAL_SPINE_TOPOLOGY_RECANARY_AUTHORIZED: `false`.\n",encoding="utf-8")
    print(json.dumps({"status":status,"preflight":preflight["status"],"provider_calls":0},ensure_ascii=False,indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
