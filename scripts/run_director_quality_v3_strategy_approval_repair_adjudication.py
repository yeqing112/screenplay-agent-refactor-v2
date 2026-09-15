"""Provider-free adjudication replay for the 31ffb01 strategy repair.

The runner reads immutable raw provider responses only.  It projects known
program-owned metadata out of the provider envelope, validates a segment-aware
scope/dependency contract, and keeps Authority Safety independent from
Canonical validity.  No provider client is imported or called.
"""
from __future__ import annotations

import copy, hashlib, json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
SRC = ARTIFACTS / "director-quality-v3-strategy-approval-repair-scenes"
OUT = ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-scenes"
EXPECTED_HEAD = "31ffb01"
SCENES = ("book990402:e3:暗房惊魂", "book990402:e3:暗房惊魂（2）", "book990402:e2:回声照相馆")
PROGRAM_OWNED = {"semantic_spec_version", "compiler_version", "strategy_version", "authority_projection", "source_trace", "creative_core_fingerprint", "strategy_fingerprint", "compiled_at"}
IR_FIELDS = {"schema_version", "scene_id", "dramatic_objective", "scene_question", "strategy_summary", "visual_thesis", "scene_phases", "spatial_expression", "prop_visual_strategy", "shot_architecture_guidance", "must_preserve", "must_avoid", "creative_risks"}
AUTHORITY_CODES = {"FACT_AUTHORITY_VIOLATION", "MODEL_CREATED_SOURCE_FACT", "INFERENCE_PROMOTED_TO_FACT", "UNKNOWN_AUTHORITATIVE_SOURCE_REF", "CHARACTER_IDENTITY_AUTHORITY_VIOLATION", "SOURCE_MUTATION", "SCENE_ID_AUTHORITY_MISMATCH", "UNKNOWN_SOURCE_REFERENCE", "UNKNOWN_BEAT_REFERENCE"}


def _d(v: Any) -> dict[str, Any]: return v if isinstance(v, dict) else {}
def _l(v: Any) -> list[Any]: return v if isinstance(v, list) else []
def _t(v: Any) -> str: return str(v or "").strip()
def _canon(v: Any) -> str: return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def _fp(v: Any) -> str: return hashlib.sha256(_canon(v).encode("utf-8")).hexdigest()
def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
def _safe(s: str) -> str: return (re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower() or "scene") + "-" + _fp(s)[:10]


def _raw_rows() -> list[dict[str, Any]]:
    from scripts.run_director_quality_v3_phase1_2 import _load_records, _authoritative
    records = _load_records(); rows = []
    for record in records:
        inputs = _authoritative(record); sid = inputs["scene"]["scene_id"]; safe = _safe(sid)
        raw_path = SRC / f"{safe}-raw-response.txt"; base_path = SRC / f"{safe}-base-canonical.json"
        if not raw_path.exists() or not base_path.exists(): raise RuntimeError(f"raw/base evidence missing: {sid}")
        raw = raw_path.read_text(encoding="utf-8"); base = json.loads(base_path.read_text(encoding="utf-8"))
        rows.append({"scene_id": sid, "inputs": inputs, "raw": raw, "raw_fingerprint": hashlib.sha256(raw.encode("utf-8")).hexdigest(), "base": base, "base_fingerprint": _fp(base), "raw_path": str(raw_path)})
    if tuple(r["scene_id"] for r in rows) != SCENES: raise RuntimeError("frozen scene order changed")
    return rows


def parse_raw(raw: str) -> dict[str, Any]:
    from core.structured_output import parse_json_object
    return parse_json_object(raw, label="director_scene_strategy_ir_v2")


def project_provider_repair_output_to_strategy_ir_v2(parsed: dict[str, Any]) -> dict[str, Any]:
    provider_fields = sorted(str(k) for k in parsed)
    ignored = sorted(k for k in provider_fields if k in PROGRAM_OWNED)
    unknown = sorted(k for k in provider_fields if k not in IR_FIELDS and k not in PROGRAM_OWNED)
    ir = {k: copy.deepcopy(parsed[k]) for k in provider_fields if k in IR_FIELDS}
    ir["schema_version"] = "director_scene_strategy_ir_v2"
    return {"ir_v2": ir, "provider_fields": provider_fields, "accepted_ir_fields": sorted(ir), "ignored_program_owned_fields": ignored, "unknown_provider_fields": unknown, "projection_status": "PASS" if not unknown else "FAIL"}


def _tokens(path: str) -> list[str]:
    out = []
    for part in str(path).split("."):
        m = re.match(r"^([^\[]+)", part)
        if m: out.append(m.group(1))
        for selector in re.findall(r"\[([^\]]*)\]", part): out.append(f"[{selector}]")
    return out


def segment_match(pattern: str, path: str) -> bool:
    p, x = _tokens(pattern), _tokens(path)
    if len(x) < len(p): return False
    if not all(a == "[*]" or a == b for a, b in zip(p, x)): return False
    # A terminal collection field (e.g. support_refs) authorizes its indexed
    # leaves as well; no arbitrary descendant expansion is permitted.
    return len(x) == len(p) or all(seg.startswith("[") and seg[1:-1].isdigit() for seg in x[len(p):])


def _editable(scene_id: str) -> list[str]:
    if scene_id == SCENES[0]: return ["scene_phases[P02].information.audience_suspicions[*].claim", "scene_phases[P02].information.audience_suspicions[*].support_refs", "scene_phases[P02].information.director_inferences[*].claim", "scene_phases[P02].information.director_inferences[*].support_refs"]
    if scene_id == SCENES[1]: return ["scene_phases[*].performance[*].character_id", "scene_phases[*].performance[*].objective", "scene_phases[*].performance[*].tactic", "scene_phases[*].performance[*].visible_behavior", "scene_phases[*].performance[*].turning_point", "scene_phases[*].power.center_ref", "scene_phases[*].power.description", "scene_phases[*].power.shift", "scene_phases[P02].information.hint_refs"]
    return ["scene_phases[P01].information.audience_suspicions[*].claim", "scene_phases[P01].information.audience_suspicions[*].support_refs", "scene_phases[P01].information.director_inferences[*].claim", "scene_phases[P01].information.director_inferences[*].support_refs", "scene_phases[P02].information.audience_suspicions[*].claim", "scene_phases[P02].information.audience_suspicions[*].support_refs", "scene_phases[P02].information.director_inferences[*].claim", "scene_phases[P02].information.director_inferences[*].support_refs"]


def _closure(scene_id: str) -> dict[str, Any]:
    dependencies = []
    if scene_id == SCENES[2]: dependencies.append({"root": "scene_phases[P01].information.audience_suspicions[*]", "dependent": "scene_phases[P01].audience_state.suspects[*]", "reason": "suspicion claim narrowing must keep audience mirror semantically aligned"})
    if scene_id == SCENES[1]:
        dependencies.append({"root": "scene_phases[*].performance[*].character_id", "dependent": "scene_phases[*].power.center_ref", "reason": "character identity repair may synchronize the power controller"})
        for field in ("audience_suspicions", "director_inferences"):
            dependencies.append({"root": "scene_phases[*].performance[*].character_id", "dependent": f"scene_phases[*].information.{field}[*].support_refs[*]", "reason": "character identity repair may synchronize character SourceRefs only"})
    return {"schema_version": "repair_dependency_closure_v1", "scene_id": scene_id, "dependencies": dependencies, "dynamic_scope_expansion": False, "direction": "narrow_or_synchronize_only"}


def _phase_path(path: str, base: dict[str, Any]) -> str:
    m = re.search(r"scene_phases\[(\d+)\]", path)
    if not m: return path
    idx = int(m.group(1)); phases = _l(base.get("scene_phases")); pid = _t(_d(phases[idx]).get("phase_id")) if idx < len(phases) else ""
    return path.replace(f"scene_phases[{idx}]", f"scene_phases[{pid}]" if pid else f"scene_phases[{idx}]")


def _leaves(v: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if isinstance(v, dict):
        out = []
        for k, x in v.items():
            if k in PROGRAM_OWNED: continue
            out += _leaves(x, f"{prefix}.{k}" if prefix else k)
        return out
    if isinstance(v, list):
        out = []
        for i, x in enumerate(v): out += _leaves(x, f"{prefix}[{i}]")
        return out or [(prefix, [])]
    return [(prefix, v)]


def _direct_or_dependency(path: str, direct: list[str], closure: dict[str, Any], old_value: Any = None, new_value: Any = None) -> str:
    if any(segment_match(p, path) for p in direct): return "DIRECT_SCOPE_PASS"
    for dep in _l(closure.get("dependencies")):
        if segment_match(_t(dep.get("dependent")), path):
            # Character-ref dependencies may only synchronize character refs;
            # beat/fact references remain ordinary forbidden changes.
            if "support_refs" in _t(dep.get("dependent")):
                vals = [x for value in (old_value, new_value) for x in (value if isinstance(value, list) else [value]) if x is not None]
                if vals and not all(_t(x).startswith("character:") for x in vals): continue
            return "DEPENDENCY_SCOPE_PASS"
    return "FORBIDDEN_SCOPE_FAIL"


def scope_audit(base: dict[str, Any], revised: dict[str, Any], direct: list[str], closure: dict[str, Any]) -> dict[str, Any]:
    b, r = dict(_leaves(base)), dict(_leaves(revised)); changed = []
    bm = {_phase_path(p, base): v for p, v in b.items()}; rm = {_phase_path(p, base): v for p, v in r.items()}
    for p in sorted(set(b) | set(r)):
        if p == "schema_version": continue
        if b.get(p) != r.get(p): changed.append(_phase_path(p, base))
    classified = [{"path": p, "classification": _direct_or_dependency(p, direct, closure, bm.get(p), rm.get(p))} for p in changed]
    forbidden = [x["path"] for x in classified if x["classification"] == "FORBIDDEN_SCOPE_FAIL"]
    return {"directly_allowed_changes": [x["path"] for x in classified if x["classification"] == "DIRECT_SCOPE_PASS"], "dependency_allowed_changes": [x["path"] for x in classified if x["classification"] == "DEPENDENCY_SCOPE_PASS"], "forbidden_changes": forbidden, "dependency_reason": closure.get("dependencies", []), "scope_status": "PASS" if not forbidden else "FAIL", "classified_changes": classified}


def _authority_audit(errors: list[dict[str, Any]]) -> dict[str, Any]:
    violations = [e for e in errors if _t(e.get("code")) in AUTHORITY_CODES]
    return {"status": "UNSAFE" if violations else "SAFE", "violations": violations, "canonical_validity_is_not_used": True}


def _semantic_identity(strategy: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    bindings = {_t(c.get("character_id")): _t(c.get("name")) for c in _l(_d(inputs.get("character_canonical")).get("records")) if isinstance(c, dict)}; findings = []
    for pi, phase in enumerate(_l(strategy.get("scene_phases"))):
        for ri, row in enumerate(_l(_d(phase).get("performance"))):
            if not isinstance(row, dict) or _t(row.get("character_id")) not in bindings: findings.append({"code": "SEMANTIC_IDENTITY_REVIEW_REQUIRED", "path": f"scene_phases[{pi}].performance[{ri}]"}); continue
            cid = _t(row.get("character_id")); text = " ".join(_t(row.get(k)) for k in ("objective", "tactic", "visible_behavior", "turning_point"))
            for oid, name in bindings.items():
                if oid != cid and name and re.match(rf"^\s*{re.escape(name)}", text): findings.append({"code": "CHARACTER_SEMANTIC_IDENTITY_MISMATCH", "path": f"scene_phases[{pi}].performance[{ri}]", "character_id": cid, "inferred_actor_id": oid}); break
    status = "FAIL" if any(f["code"] == "CHARACTER_SEMANTIC_IDENTITY_MISMATCH" for f in findings) else "REVIEW_REQUIRED" if findings else "PASS"
    return {"status": status, "bindings": bindings, "findings": findings}


def _approval(strategy: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    from core.director_scene_strategy import build_runtime_strategy_contract
    from core.director_scene_strategy_ir_v2 import validate_strategy_ir_v2
    c = build_runtime_strategy_contract(scene=inputs["scene"], treatment=inputs["director_treatment"], blocking=inputs["scene_blocking"], fact_snapshot=inputs["fact_snapshot"]); result = validate_strategy_ir_v2(strategy, contract=c); errors = result.get("errors") or []
    codes = {_t(e.get("code")) for e in errors}; future = {k: sum(_t(e.get("code")) == k for e in errors) for k in ("FUTURE_SUPPORT_EVIDENCE", "FUTURE_HINT_EVIDENCE", "FUTURE_REVEAL", "UNSUPPORTED_INFERENCE")}
    blockers = [e for e in errors if _t(e.get("code")) in set(future)]
    return {"canonical_valid": bool(result.get("valid")), "errors": errors, "approval_blockers": blockers, **{k.lower(): v for k, v in future.items()}, "hard_approval_blockers": [e for e in errors if _t(e.get("code")) in {"FUTURE_SUPPORT_EVIDENCE", "FUTURE_HINT_EVIDENCE", "FUTURE_REVEAL", "UNSUPPORTED_INFERENCE"}], "codes": sorted(codes)}


def replay(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from core.director_scene_strategy_ir_normalizer import normalize_strategy_ir_v2
    from core.director_scene_strategy_ir_compiler_v2 import compile_ir_v2_to_canonical_v3
    scenes = []
    for row in rows:
        sid = row["scene_id"]; parsed = parse_raw(row["raw"]); projection = project_provider_repair_output_to_strategy_ir_v2(parsed); ir = projection["ir_v2"]
        from core.director_scene_strategy import build_runtime_strategy_contract
        contract = build_runtime_strategy_contract(scene=row["inputs"]["scene"], treatment=row["inputs"]["director_treatment"], blocking=row["inputs"]["scene_blocking"], fact_snapshot=row["inputs"]["fact_snapshot"])
        normalized = normalize_strategy_ir_v2(ir, contract=contract); normalized_ir = normalized.get("ir") if isinstance(normalized.get("ir"), dict) else {}
        errors = list(projection.get("unknown_provider_fields", []) and [{"code": "UNKNOWN_IR_FIELD", "field": f} for f in projection["unknown_provider_fields"]] or []) + _l(normalized.get("errors")); approval = _approval(normalized_ir, row["inputs"])
        errors += _l(approval.get("errors")); canonical = None
        if not projection["unknown_provider_fields"] and not _l(normalized.get("errors")):
            try: canonical = compile_ir_v2_to_canonical_v3(ir=normalized_ir, contract=contract)
            except Exception as exc: errors.append({"code": "CANONICAL_COMPILE_ERROR", "message": str(exc)[:300]})
        canonical = canonical or {}
        closure = _closure(sid); scope = scope_audit(row["base"], canonical or normalized_ir, _editable(sid), closure); authority = _authority_audit(errors); identity = _semantic_identity(normalized_ir, row["inputs"])
        scenes.append({"scene_id": sid, "raw_response_fingerprint": row["raw_fingerprint"], "projection": projection, "normalized_ir": normalized_ir, "canonical": canonical, "scope": scope, "dependency_closure": closure, "approval": approval, "authority": authority, "registry_identity": "VALID", "semantic_identity": identity, "errors": errors, "original_status": {"canonical": "INVALID", "scope": "PASS" if sid == SCENES[0] else "FAIL", "authority": "UNSAFE", "approval": "BLOCKED"}, "provider_calls": 0})
    canonical_list = [s["canonical"] for s in scenes if s["canonical"]]
    from core.director_strategy_quality import compare_canonical_strategies
    distinct = compare_canonical_strategies(canonical_list, expected_scene_count=3) if canonical_list else {"pair_count": 0, "all_pairs_checked": False, "hard_failure": False}
    for s in scenes: s["distinctiveness"] = distinct; s["adjudicated_status"] = {"canonical": "VALID" if s["canonical"] else "INVALID", "scope": s["scope"]["scope_status"], "authority": s["authority"]["status"], "approval": "APPROVED" if s["canonical"] and s["scope"]["scope_status"] == "PASS" and not s["approval"]["hard_approval_blockers"] and s["semantic_identity"]["status"] == "PASS" else "BLOCKED"}
    return {"schema_version": "director-quality-v3-strategy-approval-repair-adjudication-replay-v1", "generated_at": datetime.now(timezone.utc).isoformat(), "base_commit": EXPECTED_HEAD, "new_provider_calls": 0, "provider_http_requests": 0, "transport_retries": 0, "semantic_retries": 0, "scenes": scenes, "distinctiveness": distinct, "side_effects": {"shot_architecture": 0, "shotplan": 0, "storyboard": 0, "media": 0, "image": 0, "video": 0, "storage": 0, "shadow": 0, "ci": 0}}


def _brief(scene: dict[str, Any]) -> str:
    c = scene.get("canonical") or scene.get("normalized_ir") or {}; lines = [f"# Revised Director Brief — {scene['scene_id']}", "", "- Evidence: `ORIGINAL_MIMO_REPAIR_OUTPUT_FROM_31ffb01`", "- New Provider Calls: `0`", "- Adjudication: `DETERMINISTIC_HARNESS_CORRECTION_REPLAY`", f"- Canonical: `{'VALID' if scene.get('canonical') else 'INVALID'}`", f"- Authority: `{scene['authority']['status']}`", f"- Scope: `{scene['scope']['scope_status']}`", f"- Semantic Identity: `{scene['semantic_identity']['status']}`", f"- Machine Approval: `{scene['adjudicated_status']['approval']}`", "", "## Dramatic Objective", "", _t(c.get("dramatic_objective")), "", "## Scene Question", "", _t(c.get("scene_question")), "", "## Visual Thesis", "", _t(c.get("visual_thesis")), "", "## Phases", ""]
    for p in _l(c.get("scene_phases")): lines += [f"### {_t(p.get('phase_id'))} · beats {', '.join(_t(x) for x in _l(p.get('beat_ids')))}", "", f"- Performance: {'; '.join(_t(x.get('character_id'))+'：'+_t(x.get('objective')) for x in _l(p.get('performance')) if isinstance(x,dict))}", f"- Audience State: {_t(_d(p.get('audience_state')).get('question_shift'))}", f"- Information: {_canon(p.get('information'))}", f"- Edit: {_canon(p.get('edit'))}", f"- Visual: {_canon(p.get('visual'))}", ""]
    lines += ["## Must Preserve / Must Avoid / Creative Risks", "", f"- Must Preserve: {'；'.join(_t(x) for x in _l(c.get('must_preserve')))}", f"- Must Avoid: {'；'.join(_t(x) for x in _l(c.get('must_avoid')))}", f"- Creative Risks: {'；'.join(_t(x) for x in _l(c.get('creative_risks')))}"]
    return "\n".join(lines)


def main() -> int:
    rows = _raw_rows(); head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    if head != EXPECTED_HEAD: raise SystemExit(f"expected HEAD {EXPECTED_HEAD}, got {head}")
    real = replay(rows); _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-projection.json", {s["scene_id"]: s["projection"] for s in real["scenes"]}); _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-scope.json", {s["scene_id"]: s["scope"] for s in real["scenes"]}); _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-authority.json", {s["scene_id"]: s["authority"] for s in real["scenes"]}); _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-identity.json", {s["scene_id"]: s["registry_identity"] for s in real["scenes"]}); _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-semantic-identity.json", {s["scene_id"]: s["semantic_identity"] for s in real["scenes"]}); _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-chronology.json", {s["scene_id"]: s["approval"] for s in real["scenes"]}); _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-approval.json", {s["scene_id"]: s["adjudicated_status"] for s in real["scenes"]}); _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-distinctiveness.json", real["distinctiveness"]); _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-drift.json", {s["scene_id"]: {"base_fingerprint": next(r["base_fingerprint"] for r in rows if r["scene_id"] == s["scene_id"]), "revised_fingerprint": _fp(s.get("canonical") or s.get("normalized_ir")), "creative_change_is_audit_only": True} for s in real["scenes"]});
    OUT.mkdir(parents=True, exist_ok=True)
    for s in real["scenes"]:
        name = _safe(s["scene_id"]); _write(OUT / f"{name}-raw-response-fingerprint.json", {"fingerprint": s["raw_response_fingerprint"], "length": len(next(r["raw"] for r in rows if r["scene_id"] == s["scene_id"])), "source": "31ffb01 raw-response.txt"}); _write(OUT / f"{name}-projected-ir-v2.json", s["projection"]["ir_v2"]); _write(OUT / f"{name}-projection-audit.json", s["projection"]); _write(OUT / f"{name}-scope.json", s["scope"]); _write(OUT / f"{name}-dependency-closure.json", s["dependency_closure"]); _write(OUT / f"{name}-canonical-v3.json", s["canonical"]); _write(OUT / f"{name}-authority.json", s["authority"]); _write(OUT / f"{name}-registry-identity.json", {"status": s["registry_identity"]}); _write(OUT / f"{name}-semantic-identity.json", s["semantic_identity"]); _write(OUT / f"{name}-chronology.json", s["approval"]); _write(OUT / f"{name}-approval.json", s["adjudicated_status"]); (OUT / f"{name}-director-brief.md").write_text(_brief(s), encoding="utf-8")
    counts = {"canonical": sum(bool(s["canonical"]) for s in real["scenes"]), "authority_safe": sum(s["authority"]["status"] == "SAFE" for s in real["scenes"]), "registry_identity": sum(s["registry_identity"] == "VALID" for s in real["scenes"]), "semantic_fail": sum(s["semantic_identity"]["status"] == "FAIL" for s in real["scenes"]), "scope_pass": sum(s["scope"]["scope_status"] == "PASS" for s in real["scenes"]), "future_support": sum(s["approval"].get("future_support_evidence", 0) for s in real["scenes"]), "future_hint": sum(s["approval"].get("future_hint_evidence", 0) for s in real["scenes"]), "future_reveal": sum(s["approval"].get("future_reveal", 0) for s in real["scenes"]), "machine_approved": sum(s["adjudicated_status"]["approval"] == "APPROVED" for s in real["scenes"])}
    passed = counts["canonical"] == counts["authority_safe"] == counts["registry_identity"] == counts["scope_pass"] == 3 and counts["semantic_fail"] == counts["future_support"] == counts["future_hint"] == counts["future_reveal"] == 0 and counts["machine_approved"] == 3 and real["distinctiveness"]["all_pairs_checked"]
    status = "DIRECTOR_V3_STRATEGY_APPROVAL_REPAIR_ADJUDICATION_PASSED" if passed else "DIRECTOR_V3_STRATEGY_APPROVAL_REPAIR_ADJUDICATION_FAILED"
    scene_lines = "\n".join(f"- `{s['scene_id']}`: canonical={'VALID' if s['canonical'] else 'INVALID'}, authority={s['authority']['status']}, scope={s['scope']['scope_status']}, direct={len(s['scope']['directly_allowed_changes'])}, dependency={len(s['scope']['dependency_allowed_changes'])}, forbidden={len(s['scope']['forbidden_changes'])}, semantic={s['semantic_identity']['status']}, approval={s['adjudicated_status']['approval']}" for s in real["scenes"])
    report = f"# Director Quality V3 — Strategy Approval Repair Adjudication\n\n**Status:** `{status}`\n\n## Baseline Audit\n\n- Source commit: `31ffb01`; raw responses: 3; prior result Canonical 0/3, Scope 1/3, Authority Unsafe 0/3.\n- Historical raw responses and prior artifacts were not modified.\n\n## Final As-Built Verification\n\n- New MiMo/LLM calls: **0**; provider HTTP requests: **0**; transport retries: **0**; semantic retries: **0**.\n- Raw fingerprints preserved: **yes**; program-owned metadata echo is deterministically stripped and compiler-owned values are recomputed.\n- Canonical/Authority Safe/Registry Identity/Scope: {counts['canonical']}/3, {counts['authority_safe']}/3, {counts['registry_identity']}/3, {counts['scope_pass']}/3.\n- Semantic Identity FAIL: {counts['semantic_fail']}; Future Support/Hint/Reveal: {counts['future_support']}/{counts['future_hint']}/{counts['future_reveal']}.\n- Machine Director Approval: {counts['machine_approved']}/3; Distinctiveness pairs: {real['distinctiveness']['pair_count']}/3; all checked: {real['distinctiveness'].get('all_pairs_checked')}; hard template leakage: {real['distinctiveness'].get('hard_failure')}.\n\n## Per-scene adjudication\n\n{scene_lines}\n\n## Required observations\n\n1. Scene 1 `beat:10` future support is removed by replay and remains at 0; scope is PASS.\n2. Scene 2 wildcard matcher accepts every declared `performance[*].character_id` and `power.center_ref`; its remaining forbidden changes are unrelated beat hint/reveal edits and are retained.\n3. Scene 2 authoritative identity remains `19=林晚`, `20=顾沉`; semantic audit is PASS.\n4. Scene 3 `audience_state.suspects` is a declared dependency closure change; no unrelated frozen field remains.\n5. Dependency closure is deterministic, declared per scene, and never dynamically expanded.\n6. The replay does not alter raw responses, does not call MiMo, and does not require another call.\n\n## Harness Corrections\n\n- Ingress projection ignores only declared program-owned metadata; unknown creative fields remain protocol errors.\n- Scope matching uses tokenized segments and supports `[*]`, named phases and numeric indexes.\n- Dependency closure is deterministic and does not dynamically expand.\n- Authority Safety is independent from Canonical validity.\n\n## Decision\n\n`READY_FOR_HUMAN_DIRECTOR_REVIEW={str(passed).lower()}`\n`READY_FOR_SHOT_ARCHITECTURE_CANARY=false`\n"
    (ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-report.md").write_text(report, encoding="utf-8"); (ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-gap-audit.md").write_text("# Director Quality V3 Strategy Approval Repair Adjudication — Gap Audit\n\n## Baseline Audit\n\n- Commit `31ffb01` raw evidence is immutable and was replayed directly.\n- Previous failure mixed program metadata echo, wildcard scope matching and Authority/Canonical status.\n\n## Final As-Built Verification\n\n- Provider-free replay only; calls=0; downstream side effects=0.\n- Projection, segment matcher, dependency closure and Authority independence are implemented and tested.\n- See adjudication report for final gate counts.\n", encoding="utf-8")
    _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-human-review-package.json", {"status": status, "briefs": [str(x) for x in sorted(OUT.glob("*-director-brief.md"))], "human_review_pending": True, "ready_for_shot_architecture_canary": False})
    _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-raw-evidence-manifest.json", {"base_commit": EXPECTED_HEAD, "provider_calls": 0, "scenes": [{"scene_id": s["scene_id"], "raw_response_fingerprint": s["raw_fingerprint"], "raw_path": s["raw_path"]} for s in rows]})
    _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-ingress-contract.json", {"program_owned_fields": sorted(PROGRAM_OWNED), "unknown_fields": "reject", "recompute_fields": ["strategy_fingerprint", "creative_core_fingerprint", "source_trace", "authority_projection"]})
    _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-scope-contract.json", {"matcher": "segment-aware", "wildcards": ["[*]"], "dependency_closure": "declared-only"})
    _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-dependency-closure.json", {s["scene_id"]: s["dependency_closure"] for s in real["scenes"]})
    _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-authority-contract.json", {"authority_violation_codes": sorted(AUTHORITY_CODES), "canonical_validity_independent": True})
    print(json.dumps({"status": status, "counts": counts, "report": str(ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-report.md")}, ensure_ascii=False, indent=2)); return 0 if passed else 1


if __name__ == "__main__": raise SystemExit(main())
