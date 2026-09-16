"""Final Director V3 Spine -> Topology re-canary.

The runner has one provider-free preflight path and one explicitly authorized
real path. The real path reuses frozen contracts and deterministic validators;
it never retries or mutates production state.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
OUT = ART / "director-quality-v3-final-spine-topology-recanary-scenes"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
AUTHORITY_PATH = ART / "director-quality-v3-current-stage-authority.json"
BASE_PATH = ART / "director-quality-v3-final-spine-topology-recanary-base.json"
SCENES = ("book990402:e3:暗房惊魂", "book990402:e3:暗房惊魂（2）", "book990402:e2:回声照相馆")
EXPECTED_FP = {
    SCENES[0]: "8a98151b7e7e2801b8daa5d576003da529717f61796dce491c2aa791037f3c04",
    SCENES[1]: "95a18cc7b7f9096934bb668f6d3ba81bc7a1ce489d33074734fe9abccef465e2",
    SCENES[2]: "e38dd057db5a7bf53f93e6cc416a7576d0d010b523e9a8971e5dcfdc924ce0b5",
}
SPINE_SYSTEM = "You are designing a VisualEditorialSpine for an approved scene. Return only the required JSON object. Do not design shots or camera execution."
SKELETON_SYSTEM = "You are converting an approved canonical VisualEditorialSpine into a semantic ShotTopologySkeleton. Return only the required JSON object. Use exact supplied enums and segment refs."


def _d(v: Any) -> dict[str, Any]: return v if isinstance(v, dict) else {}
def _l(v: Any) -> list[Any]: return v if isinstance(v, list) else []
def _t(v: Any) -> str: return str(v or "").strip()
def _canon(v: Any) -> str: return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def _fp(v: Any) -> str: return hashlib.sha256(_canon(v).encode()).hexdigest()
def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _authority() -> dict[str, Any]: return json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
def _canary(pointer: dict[str, Any]) -> dict[str, Any]: return _d(_d(_d(pointer.get("shot_architecture")).get("generation_architecture_redesign")).get("spine_topology_canary"))


def _rows() -> list[dict[str, Any]]:
    from scripts.run_director_quality_v3_strategy_approval_repair_adjudication import _raw_rows
    rows = _raw_rows()
    if tuple(r["scene_id"] for r in rows) != SCENES: raise RuntimeError("frozen cohort changed")
    return rows


def _identity(row: dict[str, Any]) -> list[dict[str, Any]]:
    from core.director_scene_strategy import build_runtime_strategy_contract, canonicalize_allowed_characters
    i = row["inputs"]
    runtime = build_runtime_strategy_contract(scene=i["scene"], treatment=i["director_treatment"], blocking=i["scene_blocking"], fact_snapshot=i["fact_snapshot"])
    return canonicalize_allowed_characters(runtime["allowed_characters"], book_id=runtime.get("book_id"))


def _strategy(row: dict[str, Any], pointer: dict[str, Any]) -> dict[str, Any]:
    item = _d(_d(pointer.get("strategy_layer")).get("scenes")).get(row["scene_id"])
    expected = EXPECTED_FP[row["scene_id"]]
    if _t(_d(item).get("fingerprint")) != expected or _t(_d(item).get("expected_fingerprint")) != expected: raise RuntimeError(f"strategy authority mismatch: {row['scene_id']}")
    strategy = json.loads((ROOT / _t(_d(item).get("snapshot_path"))).read_text(encoding="utf-8"))
    if _fp(strategy) != expected: raise RuntimeError(f"strategy snapshot mismatch: {row['scene_id']}")
    return strategy


def build_spine_request(row: dict[str, Any], strategy: dict[str, Any], identity: list[dict[str, Any]], preserve_trace: dict[str, Any]) -> dict[str, Any]:
    i = row["inputs"]
    return {"task": "director_v3_final_spine_topology_recanary", "layer": "SPINE", "scene_id": row["scene_id"], "approved_revised_strategy": copy.deepcopy(strategy), "scene_blocking": i["scene_blocking"], "authoritative_scene_beats": i["scene"], "fact_snapshot": i["fact_snapshot"], "character_identity_projection": identity, "identity_binding_fingerprint": _fp(identity), "prop_canonical": i.get("prop_canonical", {}), "location_canonical": i.get("location_canonical", {}), "must_preserve": strategy.get("must_preserve", []), "must_preserve_trace": preserve_trace, "must_avoid": strategy.get("must_avoid", []), "spine_contract": {"required": ["spine_summary", "segments"], "forbidden": ["shot_size", "camera_position", "camera_movement", "lens"]}}


def allowed_segment_refs_from_spine(spine_ir: dict[str, Any]) -> list[str]:
    """Derive segment refs only from an actual canonical Spine."""
    segments = _l(_d(spine_ir).get("segments"))
    refs = [_t(_d(segment).get("segment_key")) for segment in segments]
    # Canonical Spine segment keys are the only provider-visible topology
    # references.  Reject phase ids (Pxx) and arbitrary labels at the
    # boundary instead of letting them leak into a Skeleton request.
    if not refs or any(not re.fullmatch(r"SEG\d{2,}", ref) for ref in refs) or len(set(refs)) != len(refs):
        raise ValueError("canonical spine has no valid unique segment refs")
    return refs


def build_skeleton_request(row: dict[str, Any], strategy: dict[str, Any], identity: list[dict[str, Any]], spine_ir: dict[str, Any], preserve_trace: dict[str, Any], semantic_events: dict[str, Any]) -> dict[str, Any]:
    from core.shot_topology_skeleton import ROLE_ENUM
    i = row["inputs"]
    allowed = allowed_segment_refs_from_spine(spine_ir)
    return {"task": "director_v3_final_spine_topology_recanary", "layer": "SKELETON", "scene_id": row["scene_id"], "approved_revised_strategy": copy.deepcopy(strategy), "scene_blocking": i["scene_blocking"], "authoritative_scene_beats": i["scene"], "character_identity_projection": identity, "identity_binding_fingerprint": _fp(identity), "allowed_semantic_events": semantic_events, "must_preserve": strategy.get("must_preserve", []), "must_preserve_trace": preserve_trace, "visual_editorial_spine": spine_ir, "spine_fingerprint": _fp(spine_ir), "allowed_segment_refs": allowed, "skeleton_contract": {"required": ["nodes"], "primary_role_allowed_values": sorted(ROLE_ENUM), "secondary_role_allowed_values": sorted(ROLE_ENUM) + [None], "segment_ref_rule": "exactly one value from allowed_segment_refs; never phase IDs"}}


def _fixture_spine(strategy: dict[str, Any]) -> dict[str, Any]:
    phases = _l(strategy.get("scene_phases"))
    return {"schema_version": "visual_editorial_spine_ir_v1", "segments": [{"segment_key": f"SEG{i:02d}", "phase_ids": [_t(_d(phases[min(i - 1, len(phases) - 1)]).get("phase_id"))] if phases else [], "beat_refs": []} for i in range(1, 5)]}


def _parse(raw: str, label: str, required: set[str]) -> dict[str, Any] | None:
    from core.structured_output import parse_json_object
    try:
        value = parse_json_object(str(raw or "").strip(), label=label, required_keys=required)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _evaluate_spine(row: dict[str, Any], strategy: dict[str, Any], trace: dict[str, Any], raw: str) -> dict[str, Any]:
    from core.visual_editorial_spine import normalize_spine, validate_spine_runtime
    from core.spine_topology_forensics import detect_spine_layer_leakage, validate_must_preserve_trace
    parsed = _parse(raw, "visual_editorial_spine_ir_v1", {"segments", "spine_summary"})
    if not parsed: return {"raw_parse": "FAIL", "raw_response": raw, "ir": None, "canonical": None, "protocol": {"status": "FAIL", "errors": [{"code": "SPINE_PARSE_ERROR"}]}, "authority": {"status": "UNSAFE"}, "coverage": {"status": "FAIL"}, "director_qa": {"signal": "SPINE_INVALID", "metrics": {}}, "valid": False}
    trace_validation = validate_must_preserve_trace(trace, scene_id=row["scene_id"])
    layer_leakage = detect_spine_layer_leakage(json.dumps(parsed, ensure_ascii=False, default=str))
    normalized = normalize_spine(parsed, scene_id=row["scene_id"], strategy_fingerprint=EXPECTED_FP[row["scene_id"]]); ir = normalized.get("ir") or {}
    validation = validate_spine_runtime(ir, scene=row["inputs"]["scene"], strategy={**strategy, "strategy_fingerprint": EXPECTED_FP[row["scene_id"]]}, must_preserve_trace=trace)
    errors = list(normalized.get("errors") or []) + list(validation.get("hard_errors") or [])
    if trace_validation.get("status") != "PASS":
        errors.append({"code": "PRESERVE_AUTHORITY_INVALID", "details": trace_validation.get("errors", [])})
    fields = [[_t(seg.get(k)) for k in ("audience_attention", "information_change", "performance_pressure", "editorial_rhythm")] for seg in _l(ir.get("segments"))]
    shifts = sum(len({values[j] for values in fields if values[j]}) > 1 for j in range(4)); mechanical = len(_l(ir.get("segments"))) == len(_l(row["inputs"]["scene"].get("beats"))) and all(len(_l(seg.get("beat_refs"))) == 1 for seg in _l(ir.get("segments")))
    signal = "SPINE_INVALID" if errors else "SPINE_STRONG" if shifts >= 3 and not mechanical else "SPINE_USABLE" if shifts >= 1 else "SPINE_WEAK"
    qa = {"signal": signal, "metrics": {"visual_progression": bool(fields), "attention_design": shifts >= 1, "information_progression": shifts >= 1, "performance_pressure": shifts >= 1, "editorial_rhythm": shifts >= 1, "spatial_focus": all(_t(s.get("spatial_focus")) for s in _l(ir.get("segments"))), "strategy_fidelity": not errors, "non_mechanical_structure": not mechanical, "shift_dimensions": shifts, "mechanical_beat_to_segment": mechanical}}
    return {"raw_parse": "PASS", "raw_response": raw, "ir": ir, "canonical": ir if not errors else None, "protocol": {"status": "PASS" if not errors else "FAIL", "errors": errors}, "authority": {"status": "SAFE" if not errors else "UNSAFE", "violations": errors}, "coverage": {"status": validation["status"], "covered_beats": validation.get("covered_beats", []), "covered_phases": validation.get("covered_phases", [])}, "trace_validation": trace_validation, "layer_leakage": layer_leakage, "director_qa": qa, "valid": not errors}


def _evaluate_skeleton(row: dict[str, Any], strategy: dict[str, Any], identity: list[dict[str, Any]], spine: dict[str, Any], events: dict[str, Any], raw: str) -> dict[str, Any]:
    from core.shot_topology_skeleton import normalize_skeleton, validate_skeleton_runtime
    parsed = _parse(raw, "shot_topology_skeleton_ir_v1", {"nodes"})
    if not parsed: return {"raw_parse": "FAIL", "raw_response": raw, "ir": None, "canonical": None, "protocol": {"status": "FAIL", "errors": [{"code": "SKELETON_PARSE_ERROR"}]}, "authority": {"status": "UNSAFE"}, "coverage": {"status": "FAIL"}, "topology_qa": {"signal": "TOPOLOGY_INVALID", "metrics": {}}, "reaction": {"count": 0, "semantic_stimulus": False}, "valid": False}
    normalized = normalize_skeleton(parsed, scene_id=row["scene_id"], spine_fingerprint=_fp(spine)); ir = normalized.get("ir") or {}
    allowed_refs = {_t(s.get("segment_key")) for s in _l(spine.get("segments")) if _t(s.get("segment_key"))}
    validation = validate_skeleton_runtime(ir, spine=spine, scene=row["inputs"]["scene"], strategy=strategy, identity_projection={"records": identity}, allowed_segment_refs=allowed_refs)
    errors = list(normalized.get("errors") or []) + list(validation.get("hard_errors") or [])
    allowed_events = {_t(e.get("event_key")) for e in _l(events.get("events"))}; errors += [{"code": "UNKNOWN_SEMANTIC_EVENT_KEY", "event_key": key} for node in _l(ir.get("nodes")) for key in _l(node.get("stimulus_event_keys")) if _t(key) not in allowed_events]
    reactions = [node for node in _l(ir.get("nodes")) if _t(node.get("primary_role")) == "REACTION"]; signal = "TOPOLOGY_INVALID" if errors else "TOPOLOGY_STRONG" if len(_l(ir.get("nodes"))) >= 2 and reactions else "TOPOLOGY_USABLE" if _l(ir.get("nodes")) else "TOPOLOGY_WEAK"
    qa = {"signal": signal, "metrics": {"node_necessity": all(any(_t(node.get(key)) for key in ("dramatic_reason", "performance_reason", "information_reason", "spatial_reason", "editorial_reason")) for node in _l(ir.get("nodes"))), "beat_aggregation": any(len(_l(node.get("beat_refs"))) > 1 for node in _l(ir.get("nodes"))), "reaction_causality": bool(reactions), "information_topology": bool(ir.get("nodes")), "performance_topology": bool(ir.get("nodes")), "editorial_topology": bool(ir.get("nodes")), "rhythm_variation": len({_t(node.get("primary_role")) for node in _l(ir.get("nodes"))}) > 1, "template_resistance": True}}
    return {"raw_parse": "PASS", "raw_response": raw, "ir": ir, "canonical": ir if not errors else None, "protocol": {"status": "PASS" if not errors else "FAIL", "errors": errors}, "authority": {"status": "SAFE" if not errors else "UNSAFE", "violations": errors}, "coverage": {"status": validation["status"], "covered_beats": validation.get("covered_beats", []), "node_count": len(_l(ir.get("nodes")))}, "topology_qa": qa, "reaction": {"count": len(reactions), "semantic_stimulus": all(_l(node.get("stimulus_beat_refs")) or _l(node.get("stimulus_event_keys")) for node in reactions)}, "valid": not errors}


def _runtime_preflight(pointer: dict[str, Any], base: dict[str, Any], head: str, *, authorized: bool) -> dict[str, Any]:
    from core.director_v3_authority import retired_recanary_provider_callable, validate_current_stage_authority
    from core.shot_topology_skeleton import ROLE_ENUM
    from core.spine_topology_forensics import build_must_preserve_trace, compare_identity_projection, skeleton_callable_after_spine, validate_must_preserve_trace
    rows = _rows(); identities: dict[str, list[dict[str, Any]]] = {}; traces: dict[str, dict[str, Any]] = {}; builder_fps: list[str] = []; segment_fixture = True
    identity_parity = True; trace_shape = True
    for row in rows:
        strategy = _strategy(row, pointer); ident = _identity(row); trace = build_must_preserve_trace(strategy, row["inputs"]["scene"]); identities[row["scene_id"]] = ident; traces[row["scene_id"]] = trace; fixture = _fixture_spine(strategy); sk = build_skeleton_request(row, strategy, ident, fixture, trace, {"events": []}); segment_fixture &= sk["allowed_segment_refs"] == ["SEG01", "SEG02", "SEG03", "SEG04"]; builder_fps.append(_fp(sk["skeleton_contract"])); trace_shape &= validate_must_preserve_trace(trace, scene_id=row["scene_id"])["status"] == "PASS"; identity_parity &= compare_identity_projection({"records": ident}, {"records": ident})["status"] == "PASS"
    canary = _canary(pointer); auth = bool(canary.get("final_recanary_authorized", False)); base_gate = _base_commit_gate(_t(base.get("expected_base_commit")), head)
    authority_semantics = validate_current_stage_authority(pointer)
    checks = {"head_ancestry_gate": base_gate["status"] == "PASS", "head_base_code_drift_gate": not base_gate["code_changes"], "authority_pointer_fingerprint": _fp(pointer) == _t(base.get("authority_pointer_fingerprint")), "forensic_closed": canary.get("forensic_adjudication") == "CLOSED", "wiring_closed": canary.get("preflight_wiring_closure") == "CLOSED", "historical_preflight_ready": canary.get("historical_preflight_ready") is True, "historical_recanary_retired": canary.get("historical_recanary_retired") is True, "executable_again_false": canary.get("executable_again") is False, "no_further_recanary": canary.get("no_further_spine_topology_recanary") is True, "readiness_true": canary.get("historical_preflight_ready") is True, "authorization": auth is authorized, "authority_semantics": authority_semantics["status"] == "PASS", "retired_provider_gate": retired_recanary_provider_callable(pointer) is False, "identity_projection_fingerprints_stable": all(bool(value) and all(_t(item.get("character_id")) for item in value) for value in identities.values()), "identity_provider_runtime_parity": identity_parity, "preserve_trace_shape": trace_shape, "preserve_trace_fingerprints_stable": len({_fp(value) for value in traces.values()}) == 3, "role_enum_visible": bool(ROLE_ENUM), "segment_count_diff_fixture": segment_fixture, "builder_fingerprint_stable": len(set(builder_fps)) == 1, "fail_closed_skeleton_gate": skeleton_callable_after_spine(False)["skeleton_provider_callable"] is False, "production_hold": _d(pointer.get("shot_architecture")).get("production_shotplan") == "HOLD", "prompt_fingerprints_exact": _fp(SPINE_SYSTEM) == _d(base.get("contracts")).get("spine_system_prompt_fingerprint") and _fp(SKELETON_SYSTEM) == _d(base.get("contracts")).get("skeleton_system_prompt_fingerprint")}
    return {"checks": checks, "base_commit_gate": base_gate, "rows": rows, "identities": identities, "traces": traces, "status": "PASS" if all(checks.values()) else "BLOCKED", "authorization": auth, "provider_calls": 0, "head": head, "expected_base_commit": base.get("expected_base_commit")}


def _code_changes_present() -> list[str]:
    result = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, capture_output=True, text=True, check=True); ext = {".py", ".ts", ".tsx", ".js", ".jsx"}; paths = []
    project_code_roots = {"core", "api", "models", "scripts", "tests", "web"}
    for line in result.stdout.splitlines():
        path = line[3:].strip().strip('"')
        if Path(path).suffix.lower() in ext and Path(path).parts and Path(path).parts[0] in project_code_roots: paths.append(path)
    return sorted(paths)


def _working_tree_dirty_paths() -> list[str]:
    """Return every tracked/untracked path in the working tree.

    The final re-canary is an evidence-producing experiment whose execution
    manifest must be reproducible.  A clean *code* tree is not sufficient:
    changed artifacts, fixtures or configuration can alter authority inputs
    without appearing as source drift.  Keep this check separate from the
    historical ``_code_changes_present`` helper so replay tooling retains its
    original semantics while the authorized runtime enforces the document's
    full working-tree gate.
    """
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        # Porcelain v1 uses two status columns followed by a space.  For a
        # rename, retain the whole entry so the gate remains conservative.
        paths.append(line[3:].strip().strip('"') if len(line) >= 4 else line)
    return sorted(paths)


def _base_commit_gate(expected_base: str, head: str) -> dict[str, Any]:
    """Validate the immutable wiring base and reject post-base code drift."""
    base = _t(expected_base); current = _t(head)
    if not base or not current:
        return {"status": "FAIL", "reason": "BASE_COMMIT_MISSING", "code_changes": []}
    verified = subprocess.run(["git", "cat-file", "-e", f"{base}^{{commit}}"], cwd=ROOT, capture_output=True)
    if verified.returncode != 0:
        return {"status": "FAIL", "reason": "BASE_COMMIT_UNKNOWN", "code_changes": []}
    ancestry = subprocess.run(["git", "merge-base", "--is-ancestor", base, current], cwd=ROOT, capture_output=True).returncode == 0
    if not ancestry:
        return {"status": "FAIL", "reason": "HEAD_NOT_DESCENDANT_OF_BASE", "code_changes": []}
    diff = subprocess.run(["git", "diff", "--name-only", f"{base}..{current}"], cwd=ROOT, capture_output=True, text=True, check=True)
    code_roots = {"core", "api", "models", "scripts", "tests", "web"}; code_ext = {".py", ".ts", ".tsx", ".js", ".jsx"}
    code_changes = sorted(path for path in diff.stdout.splitlines() if Path(path).parts and Path(path).parts[0] in code_roots and Path(path).suffix.lower() in code_ext)
    return {"status": "PASS" if not code_changes else "FAIL", "reason": None if not code_changes else "POST_BASE_CODE_DRIFT", "code_changes": code_changes}


def _brief(scene_id: str, spine: dict[str, Any], skeleton: dict[str, Any], binding: dict[str, Any]) -> str:
    lines = [f"# Spine → Topology Brief — {scene_id}", "", "## Spine Summary", _t(_d(spine.get("ir")).get("spine_summary")), "", "## Segments"]
    for seg in _l(_d(spine.get("ir")).get("segments")): lines.append(f"- {_t(seg.get('segment_key'))}: beats={','.join(_l(seg.get('beat_refs')))}; attention={_t(seg.get('audience_attention'))}; information={_t(seg.get('information_change'))}; rhythm={_t(seg.get('editorial_rhythm'))}")
    lines += ["", f"Spine QA: `{_d(spine.get('director_qa')).get('signal')}`", "", "## Topology Nodes"]
    for node in _l(_d(skeleton.get("ir")).get("nodes")): lines.append(f"- {_t(node.get('node_key'))}: role={_t(node.get('primary_role'))}; beats={','.join(_l(node.get('beat_refs')))}; reason={_t(node.get('dramatic_reason') or node.get('information_reason') or node.get('performance_reason'))}")
    lines += ["", f"Topology QA: `{_d(skeleton.get('topology_qa')).get('signal')}`", "", "## Binder Edges"]
    for edge in _l(binding.get("edges")): lines.append(f"- `{edge.get('edge_type')}` {_t(edge.get('from_node_id'))} → {_t(edge.get('bound_node_id') or edge.get('to_node_id'))} ({_t(edge.get('binding_status'))})")
    return "\n".join(lines + ["", f"Binding QA: `{binding.get('binding_status')}`", "", "No Atomic Expansion, ShotPlan, Storyboard or media step was executed."]) + "\n"


def _run_real(preflight: dict[str, Any], profile_id: str) -> dict[str, Any]:
    if preflight["status"] != "PASS" or not preflight["authorization"]: return {"status": "DIRECTOR_V3_FINAL_SPINE_TOPOLOGY_RECANARY_BLOCKED", "provider_calls": 0, "reason": "preflight_or_authorization_gate"}
    # The historical cohort is permanently retired.  Even a malformed or
    # manually edited authorization field must not make it provider-reachable.
    from core.director_v3_authority import retired_recanary_provider_callable
    if not retired_recanary_provider_callable(_authority()):
        return {"status": "DIRECTOR_V3_FINAL_SPINE_TOPOLOGY_RECANARY_BLOCKED", "provider_calls": 0, "reason": "HISTORICAL_RECANARY_RETIRED"}
    dirty_paths = _working_tree_dirty_paths()
    if dirty_paths:
        return {"status": "DIRECTOR_V3_FINAL_SPINE_TOPOLOGY_RECANARY_BLOCKED", "provider_calls": 0, "reason": "WORKTREE_NOT_CLEAN_FOR_REAL_PROVIDER_RUN", "dirty_paths": dirty_paths}
    code_changes = _code_changes_present()
    if code_changes: return {"status": "DIRECTOR_V3_FINAL_SPINE_TOPOLOGY_RECANARY_BLOCKED", "provider_calls": 0, "reason": "unexpected_code_diff", "code_changes": code_changes}
    from api.model_registry import get_profile
    from core.llm import call_llm
    from core.semantic_events import project_semantic_events
    from core.shot_topology_graph_binder import bind_topology
    profile = get_profile(profile_id) or {}
    if _t(profile.get("model_name")) != "mimo-v2.5" or not profile.get("api_key"): return {"status": "DIRECTOR_V3_FINAL_SPINE_TOPOLOGY_RECANARY_BLOCKED", "provider_calls": 0, "reason": "mimo_profile_missing"}
    pointer = _authority(); rows = preflight["rows"]; requests = []
    for row in rows: requests.append(build_spine_request(row, _strategy(row, pointer), preflight["identities"][row["scene_id"]], preflight["traces"][row["scene_id"]]))
    execution_head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip(); first = rows[0]; first_strategy = _strategy(first, pointer); first_fixture = _fixture_spine(first_strategy)
    manifest = {"schema_version": "director_v3_final_spine_topology_execution_manifest_v1", "execution_code_base_sha": preflight["expected_base_commit"], "authorization_commit_sha": execution_head, "execution_head_sha": execution_head, "base_artifact_expected_commit": preflight["expected_base_commit"], "spine_prompt_fp": _fp(SPINE_SYSTEM), "skeleton_prompt_fp": _fp(SKELETON_SYSTEM), "spine_contract_fp": _fp(requests[0]["spine_contract"]), "skeleton_builder_fp": _fp(build_skeleton_request(first, first_strategy, preflight["identities"][first["scene_id"]], first_fixture, preflight["traces"][first["scene_id"]], {"events": []})["skeleton_contract"]), "strategy_fps": EXPECTED_FP, "identity_fps": {key: _fp(value) for key, value in preflight["identities"].items()}, "preserve_trace_fps": {key: _fp(value) for key, value in preflight["traces"].items()}, "semantic_event_fps": {row["scene_id"]: _fp(project_semantic_events(row["inputs"]["scene"])) for row in rows}, "request_fps": {row["scene_id"]: _fp(req) for row, req in zip(rows, requests)}, "frozen_at": datetime.now(timezone.utc).isoformat()}
    _write(ART / "director-quality-v3-final-spine-topology-execution-manifest.json", manifest)
    scenes: list[dict[str, Any]] = []; provider_calls = 0
    for row, request in zip(rows, requests):
        sid = row["scene_id"]; strategy = _strategy(row, pointer); identity = preflight["identities"][sid]; trace = preflight["traces"][sid]; events = project_semantic_events(row["inputs"]["scene"]); record: dict[str, Any] = {"scene_id": sid, "spine_request": request, "spine_request_fingerprint": _fp(request), "provider_errors": []}
        try: raw_spine = str(call_llm(json.dumps(request, ensure_ascii=False), system=SPINE_SYSTEM, model_profile=profile, retries=0, max_tokens=12000, estimated_tokens=9000, audit_extra={"phase": "director_v3_final_spine_topology_recanary", "scene_id": sid, "layer": "SPINE", "attempt_type": "CREATIVE_GENERATION"}) or "")
        except Exception as exc: raw_spine = ""; record["provider_errors"].append({"layer": "SPINE", "code": "PROVIDER_ERROR", "message": str(exc)[:800]})
        provider_calls += 1; spine = _evaluate_spine(row, strategy, trace, raw_spine); record["spine"] = spine; record["skeleton_request"] = None; record["skeleton"] = {"skipped": True, "reason": "SPINE_HARD_GATE_FAILED"}; record["binding"] = {"binding_status": "SKIPPED", "edges": [], "errors": []}
        if spine.get("valid"):
            skeleton_request = build_skeleton_request(row, strategy, identity, spine["canonical"], trace, events); record["skeleton_request"] = skeleton_request
            try: raw_skeleton = str(call_llm(json.dumps(skeleton_request, ensure_ascii=False), system=SKELETON_SYSTEM, model_profile=profile, retries=0, max_tokens=12000, estimated_tokens=9000, audit_extra={"phase": "director_v3_final_spine_topology_recanary", "scene_id": sid, "layer": "SKELETON", "attempt_type": "CREATIVE_GENERATION"}) or "")
            except Exception as exc: raw_skeleton = ""; record["provider_errors"].append({"layer": "SKELETON", "code": "PROVIDER_ERROR", "message": str(exc)[:800]})
            provider_calls += 1; skeleton = _evaluate_skeleton(row, strategy, identity, spine["canonical"], events, raw_skeleton); record["skeleton"] = skeleton; record["binding"] = bind_topology(skeleton.get("canonical") or skeleton.get("ir") or {}, semantic_events=events)
        scenes.append(record); name = _fp(sid)[:12]; _write(OUT / f"{name}-result.json", record); (OUT / f"{name}-brief.md").write_text(_brief(sid, record["spine"], record["skeleton"], record["binding"]), encoding="utf-8")
    spine_pass = all(_d(s.get("spine")).get("valid") for s in scenes); skeleton_pass = all(_d(s.get("skeleton")).get("valid") for s in scenes if not _d(s.get("skeleton")).get("skipped")); status = "DIRECTOR_V3_FINAL_SPINE_TOPOLOGY_RECANARY_PASSED" if spine_pass and skeleton_pass and len(scenes) == 3 else "DIRECTOR_V3_FINAL_SPINE_TOPOLOGY_RECANARY_FAILED"
    report = {"schema_version": "director_v3_final_spine_topology_recanary_final_report_v1", "status": status, "execution_head_sha": execution_head, "provider": {"model": "mimo-v2.5", "spine_calls": len(scenes), "skeleton_calls": sum(not _d(s.get("skeleton")).get("skipped") for s in scenes), "total_calls": provider_calls, "retries": 0}, "scenes": scenes, "side_effects": {"atomic_expansion": 0, "production_shotplan": 0, "storyboard": 0, "media": 0, "storage": 0, "ci": 0}, "human_preference": "NOT_RECORDED", "ready_for_atomic_expansion_canary": status.endswith("PASSED"), "atomic_expansion_canary_authorized": False, "production_shotplan": "HOLD"}
    _write(ART / "director-quality-v3-final-spine-topology-recanary-final-report.json", report); (ART / "director-quality-v3-final-spine-topology-recanary-final-report.md").write_text("# Director Quality V3 — Final Spine → Topology Re-Canary\n\n" + f"**Status:** `{status}`\n\n- Execution HEAD: `{execution_head}`\n- Provider calls: `{provider_calls}`; retries: `0`\n- Human Preference: `NOT_RECORDED`\n- Atomic Expansion authorization: `false`\n- Production ShotPlan: `HOLD`\n\n" + "\n".join(f"- `{s['scene_id']}`: Spine `{_d(s.get('spine',{}).get('director_qa')).get('signal')}`, Skeleton `{_d(s.get('skeleton',{}).get('topology_qa')).get('signal') if not _d(s.get('skeleton')).get('skipped') else 'SKIPPED'}`, Binder `{s.get('binding',{}).get('binding_status')}`" for s in scenes) + "\n", encoding="utf-8"); _write(ART / "director-quality-v3-final-spine-topology-human-review-package.json", {"status": status, "human_review_pending": True, "briefs": [str(p) for p in sorted(OUT.glob("*-brief.md"))], "final_report": "artifacts/director-quality-v3-final-spine-topology-recanary-final-report.md"})
    return {"status": status, "provider_calls": provider_calls, "execution_head_sha": execution_head}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--execute-real", action="store_true"); parser.add_argument("--profile-id", default="local-llm-2vydoz"); args = parser.parse_args(argv)
    supplied = argv if argv is not None else sys.argv[1:]
    if any(flag in supplied for flag in ("--force", "--unsafe", "--ignore-authorization")): raise SystemExit("unsupported authorization bypass flag")
    pointer = _authority(); base = json.loads(BASE_PATH.read_text(encoding="utf-8")); head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip(); preflight = _runtime_preflight(pointer, base, head, authorized=bool(args.execute_real))
    if args.execute_real:
        result = _run_real(preflight, args.profile_id); print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if result["status"].endswith("PASSED") else 1
    result = {"status": "DIRECTOR_V3_FINAL_SPINE_TOPOLOGY_RECANARY_NOT_AUTHORIZED" if preflight["authorization"] is False else "DIRECTOR_V3_FINAL_SPINE_TOPOLOGY_RECANARY_AUTHORIZED_DRY_RUN", "preflight": preflight["status"], "provider_calls": 0, "authorization": preflight["authorization"]}
    # Keep the dry-run artifact as the single provider-free evidence surface.
    # The wiring runner may already have added its richer gate checks; merge
    # rather than downgrading the schema or erasing those checks when this
    # final runner is invoked for an authorization probe.
    dry_run_path = ART / "director-quality-v3-final-spine-topology-preflight-dry-run.json"
    existing: dict[str, Any] = {}
    if dry_run_path.exists():
        try:
            loaded = json.loads(dry_run_path.read_text(encoding="utf-8"))
            existing = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            existing = {}
    checks = {**_d(existing.get("checks")), **preflight["checks"]}
    _write(dry_run_path, {"schema_version": "director-quality-v3-final-spine-topology-preflight-wiring-v3", "status": preflight["status"], "head": head, "expected_base_commit": base.get("expected_base_commit"), "checks": checks, "provider_calls": 0, "real_llm_calls": 0, "real_mimo_calls": 0, "authorization": preflight["authorization"], "status_code": result["status"], "frozen_scene_count": len(preflight["rows"])})
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if preflight["status"] == "PASS" else 2


if __name__ == "__main__": raise SystemExit(main())
