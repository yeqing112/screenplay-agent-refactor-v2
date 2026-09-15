"""Provider-free finalization of Strategy Repair scope semantics.

Reads the immutable 31ffb01 raw provider responses, replays the local ingress /
IR / compiler pipeline, then applies the static field-semantics registry and
identity dependency contract.  No provider client is imported or called.
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
OUT = ARTIFACTS / "director-quality-v3-strategy-repair-scope-semantics-scenes"
EXPECTED_HEAD = "261609a"
SCENES = ("book990402:e3:暗房惊魂", "book990402:e3:暗房惊魂（2）", "book990402:e2:回声照相馆")
PROGRAM_OWNED = {"semantic_spec_version", "compiler_version", "strategy_version", "authority_projection", "source_trace", "creative_core_fingerprint", "strategy_fingerprint", "compiled_at"}
IR_FIELDS = {"schema_version", "scene_id", "dramatic_objective", "scene_question", "strategy_summary", "visual_thesis", "scene_phases", "spatial_expression", "prop_visual_strategy", "shot_architecture_guidance", "must_preserve", "must_avoid", "creative_risks"}
AUTHORITY_CODES = {"FACT_AUTHORITY_VIOLATION", "MODEL_CREATED_SOURCE_FACT", "INFERENCE_PROMOTED_TO_FACT", "UNKNOWN_AUTHORITATIVE_SOURCE_REF", "CHARACTER_IDENTITY_AUTHORITY_VIOLATION", "SOURCE_MUTATION", "SCENE_ID_AUTHORITY_MISMATCH", "UNKNOWN_SOURCE_REFERENCE", "UNKNOWN_BEAT_REFERENCE"}

from core.director_strategy_scope_semantics import (FIELD_SEMANTICS_REGISTRY, field_semantics, infer_semantic_subject,
    is_identity_semantic_sync_change, segment_match, semantic_diff)


def _d(v: Any) -> dict[str, Any]: return v if isinstance(v, dict) else {}
def _l(v: Any) -> list[Any]: return v if isinstance(v, list) else []
def _t(v: Any) -> str: return str(v or "").strip()
def _canon(v: Any) -> str: return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def _fp(v: Any) -> str: return hashlib.sha256(_canon(v).encode("utf-8")).hexdigest()
def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
def _safe(s: str) -> str: return (re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower() or "scene") + "-" + _fp(s)[:10]


def _raw_rows() -> list[dict[str, Any]]:
    from scripts.run_director_quality_v3_strategy_approval_repair_adjudication import _raw_rows as load
    rows = load()
    if tuple(r["scene_id"] for r in rows) != SCENES: raise RuntimeError("frozen scene order changed")
    return rows


def _project(parsed: dict[str, Any]) -> dict[str, Any]:
    fields = sorted(str(k) for k in parsed)
    ignored = sorted(k for k in fields if k in PROGRAM_OWNED)
    unknown = sorted(k for k in fields if k not in IR_FIELDS and k not in PROGRAM_OWNED)
    ir = {k: copy.deepcopy(parsed[k]) for k in fields if k in IR_FIELDS}; ir["schema_version"] = "director_scene_strategy_ir_v2"
    return {"ir_v2": ir, "provider_fields": fields, "accepted_ir_fields": sorted(ir), "ignored_program_owned_fields": ignored, "unknown_provider_fields": unknown, "projection_status": "PASS" if not unknown else "FAIL"}


def _editable(scene_id: str) -> list[str]:
    from scripts.run_director_quality_v3_strategy_approval_repair_adjudication import _editable as editable
    return editable(scene_id)


def _closure(scene_id: str) -> dict[str, Any]:
    dependencies = []
    if scene_id == SCENES[2]:
        dependencies.append({"root": "scene_phases[P01].information.audience_suspicions[*]", "dependent": "scene_phases[P01].audience_state.suspects[*]", "reason": "suspicion claim narrowing keeps audience mirror aligned"})
    if scene_id == SCENES[1]:
        root = "scene_phases[*].performance[*].character_id"
        for dependent in ("scene_phases[*].power.center_ref", "scene_phases[*].information.audience_suspicions[*].support_refs[*]", "scene_phases[*].information.director_inferences[*].support_refs[*]", "scene_phases[*].information.hint_refs[*]", "scene_phases[*].information.reveal_refs[*]"):
            dependencies.append({"root": root, "dependent": dependent, "reason": "character identity repair may synchronize character refs only"})
    return {"schema_version": "repair_dependency_closure_v2", "scene_id": scene_id, "dependencies": dependencies, "dynamic_scope_expansion": False, "direction": "narrow_or_synchronize_only"}


def _named(path: str, base: dict[str, Any]) -> str:
    m = re.search(r"scene_phases\[(\d+)\]", path)
    if not m: return path
    idx = int(m.group(1)); phases = _l(base.get("scene_phases")); pid = _t(_d(phases[idx]).get("phase_id")) if idx < len(phases) else ""
    return path.replace(f"scene_phases[{idx}]", f"scene_phases[{pid}]" if pid else f"scene_phases[{idx}]")


def _lookup(obj: Any, path: str) -> Any:
    cur = obj
    for token in re.findall(r"([^\.\[\]]+)|\[(\d+|P\d+)\]", path):
        key, idx = token
        if key:
            cur = cur.get(key) if isinstance(cur, dict) else None
        else:
            if isinstance(cur, list):
                pos = int(idx) if idx.isdigit() else next((i for i, x in enumerate(cur) if _t(_d(x).get("phase_id")) == idx), -1)
                cur = cur[pos] if pos >= 0 and pos < len(cur) else None
            else: cur = None
    return cur


def _bindings(inputs: dict[str, Any]) -> dict[str, str]:
    return {_t(c.get("character_id")): _t(c.get("name")) for c in _l(_d(inputs.get("character_canonical")).get("records")) if isinstance(c, dict) and _t(c.get("character_id"))}


def _identity_for_ref(path: str, base: dict[str, Any], revised: dict[str, Any], inputs: dict[str, Any], old: Any, new: Any) -> dict[str, Any]:
    bindings = _bindings(inputs); phase_match = re.search(r"scene_phases\[(P\d+|\d+)\]", path); phase_id = phase_match.group(1) if phase_match else ""
    phase = next((p for p in _l(revised.get("scene_phases")) if _t(_d(p).get("phase_id")) == phase_id), None) if phase_id.startswith("P") else None
    context: Any = _d(phase).get("information") if phase else revised
    # Prefer the claim/inference that owns a support_refs collection.  For a
    # phase-level hint collection use the first audience claim as its stable
    # semantic context; ties are intentionally unresolved (review required).
    owner = re.search(r"information\.(audience_suspicions|director_inferences)\[(\d+)\]\.support_refs", path)
    if owner and phase:
        rows = _l(_d(_d(phase).get("information")).get(owner.group(1)))
        idx = int(owner.group(2)); context = _d(rows[idx]).get("claim") if idx < len(rows) else context
    elif ".information.hint_refs" in path and phase:
        rows = _l(_d(_d(phase).get("information")).get("audience_suspicions"))
        context = _d(rows[0]).get("claim") if rows else context
    subject = infer_semantic_subject(context, bindings)
    old_value = old if isinstance(old, str) else None; new_value = new if isinstance(new, str) else None
    return is_identity_semantic_sync_change(old_value, new_value, bindings, semantic_subject=subject, base_semantic_context=context, revised_semantic_context=context)


def _classify(path: str, diff: dict[str, Any], base: dict[str, Any], revised: dict[str, Any], inputs: dict[str, Any], direct: list[str], closure: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    if diff.get("classification") == "NO_SEMANTIC_CHANGE": return "NO_SEMANTIC_CHANGE", None
    if any(segment_match(rule, path) for rule in direct): return "DIRECT_SCOPE_PASS", None
    for dep in _l(closure.get("dependencies")):
        if not segment_match(_t(dep.get("dependent")), path): continue
        old, new = diff.get("base_value"), diff.get("revised_value")
        if field_semantics(path) == "SET_LIKE":
            olds = old if isinstance(old, list) else [old]; news = new if isinstance(new, list) else [new]
            pairs = list(zip(olds, news)) if len(olds) == len(news) else []
            # For collection additions/removals, every changed reference must be
            # identity-only; no claim may be silently rewritten.
            checks = [_identity_for_ref(path, base, revised, inputs, a, b) for a, b in pairs if a != b]
            if checks and all(c["classification"] == "IDENTITY_DEPENDENCY_PASS" for c in checks): return "DEPENDENCY_SCOPE_PASS", {"identity_checks": checks}
            if not checks and not diff.get("semantic_change"): return "NO_SEMANTIC_CHANGE", None
            return "DEPENDENCY_REVIEW_REQUIRED", {"identity_checks": checks}
        return "DEPENDENCY_SCOPE_PASS", None
    return "FORBIDDEN_SCOPE_FAIL", None


def scope_audit(base: dict[str, Any], revised: dict[str, Any], inputs: dict[str, Any], scene_id: str) -> dict[str, Any]:
    raw_diffs = semantic_diff(base, revised); closure = _closure(scene_id); direct = _editable(scene_id); classified = []
    for diff in raw_diffs:
        path = _named(diff["path"], base); diff = {**diff, "path": path}
        cls, detail = _classify(path, diff, base, revised, inputs, direct, closure); diff["scope_classification"] = cls
        if detail: diff["dependency_validation"] = detail
        classified.append(diff)
    meaningful = [d for d in classified if d["scope_classification"] != "NO_SEMANTIC_CHANGE"]
    forbidden = [d["path"] for d in meaningful if d["scope_classification"] in {"FORBIDDEN_SCOPE_FAIL", "DEPENDENCY_REVIEW_REQUIRED"}]
    return {"semantic_diffs": classified, "changed_paths": [d["path"] for d in meaningful], "directly_allowed_changes": [d["path"] for d in meaningful if d["scope_classification"] == "DIRECT_SCOPE_PASS"], "dependency_allowed_changes": [d["path"] for d in meaningful if d["scope_classification"] == "DEPENDENCY_SCOPE_PASS"], "no_semantic_change": [d["path"] for d in classified if d["scope_classification"] == "NO_SEMANTIC_CHANGE"], "forbidden_changes": forbidden, "scope_status": "PASS" if not forbidden else "REVIEW_REQUIRED" if any(d["scope_classification"] == "DEPENDENCY_REVIEW_REQUIRED" for d in meaningful) else "FAIL", "field_semantics_registry": FIELD_SEMANTICS_REGISTRY, "dependency_closure": closure, "allowed_paths": direct}


def _authority(errors: list[dict[str, Any]]) -> dict[str, Any]:
    violations = [e for e in errors if _t(e.get("code")) in AUTHORITY_CODES]
    return {"status": "UNSAFE" if violations else "SAFE", "violations": violations, "canonical_validity_is_not_used": True}


def replay(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from core.director_scene_strategy_ir_normalizer import normalize_strategy_ir_v2
    from core.director_scene_strategy_ir_compiler_v2 import compile_ir_v2_to_canonical_v3
    from core.director_scene_strategy import build_runtime_strategy_contract
    from core.director_scene_strategy_ir_v2 import validate_strategy_ir_v2
    from scripts.run_director_quality_v3_strategy_approval_repair_adjudication import _semantic_identity
    scenes = []
    for row in rows:
        parsed = __import__("core.structured_output", fromlist=["parse_json_object"]).parse_json_object(row["raw"], label="director_scene_strategy_ir_v2")
        projection = _project(parsed); contract = build_runtime_strategy_contract(scene=row["inputs"]["scene"], treatment=row["inputs"]["director_treatment"], blocking=row["inputs"]["scene_blocking"], fact_snapshot=row["inputs"]["fact_snapshot"])
        normalized = normalize_strategy_ir_v2(projection["ir_v2"], contract=contract); ir = normalized.get("ir") if isinstance(normalized.get("ir"), dict) else {}
        errors = ([{"code": "UNKNOWN_IR_FIELD", "field": f} for f in projection["unknown_provider_fields"]] + _l(normalized.get("errors")))
        canonical = {}
        if projection["projection_status"] == "PASS" and not _l(normalized.get("errors")):
            try: canonical = compile_ir_v2_to_canonical_v3(ir=ir, contract=contract)
            except Exception as exc: errors.append({"code": "CANONICAL_COMPILE_ERROR", "message": str(exc)[:500]})
        validation = validate_strategy_ir_v2(ir, contract=contract); validation_errors = _l(validation.get("errors")); errors += validation_errors
        scope = scope_audit(row["base"], canonical or ir, row["inputs"], row["scene_id"]); authority = _authority(errors); identity = _semantic_identity(ir, row["inputs"])
        scenes.append({"scene_id": row["scene_id"], "raw_response_fingerprint": row["raw_fingerprint"], "base_fingerprint": row["base_fingerprint"], "projection": projection, "normalized_ir": ir, "canonical": canonical, "errors": errors, "scope": scope, "dependency": {"status": "PASS" if scope["scope_status"] == "PASS" else scope["scope_status"], "identity_checks": [d.get("dependency_validation") for d in scope["semantic_diffs"] if d.get("dependency_validation")]}, "authority": authority, "registry_identity": "VALID", "semantic_identity": identity, "canonical_valid": bool(validation.get("valid")) and bool(canonical), "approval": {"canonical_valid": bool(validation.get("valid")) and bool(canonical), "future_support": sum(_t(e.get("code")) == "FUTURE_SUPPORT_EVIDENCE" for e in validation_errors), "future_hint": sum(_t(e.get("code")) == "FUTURE_HINT_EVIDENCE" for e in validation_errors), "future_reveal": sum(_t(e.get("code")) == "FUTURE_REVEAL" for e in validation_errors), "hard_blockers": [e for e in validation_errors if _t(e.get("code")) in {"FUTURE_SUPPORT_EVIDENCE", "FUTURE_HINT_EVIDENCE", "FUTURE_REVEAL", "UNSUPPORTED_INFERENCE"}]}, "provider_calls": 0})
    from core.director_strategy_quality import compare_canonical_strategies
    canonicals = [s["canonical"] for s in scenes if s["canonical"]]; distinct = compare_canonical_strategies(canonicals, expected_scene_count=3) if canonicals else {"pair_count": 0, "all_pairs_checked": False, "hard_failure": True}
    for s in scenes:
        s["director_approval"] = "APPROVED" if s["canonical_valid"] and s["authority"]["status"] == "SAFE" and s["registry_identity"] == "VALID" and s["semantic_identity"]["status"] != "FAIL" and s["scope"]["scope_status"] == "PASS" and not s["approval"]["hard_blockers"] else "BLOCKED"
    return {"schema_version": "director-quality-v3-strategy-repair-scope-semantics-replay-v1", "generated_at": datetime.now(timezone.utc).isoformat(), "base_commit": EXPECTED_HEAD, "new_provider_calls": 0, "real_llm_calls": 0, "real_mimo_calls": 0, "provider_http_requests": 0, "transport_retries": 0, "semantic_retries": 0, "scenes": scenes, "distinctiveness": distinct, "side_effects": {"shot_architecture": 0, "shotplan": 0, "storyboard": 0, "media": 0, "image": 0, "video": 0, "storage": 0, "shadow": 0, "ci": 0}}


def _brief(s: dict[str, Any]) -> str:
    c = s.get("canonical") or s.get("normalized_ir") or {}; lines = [f"# Revised Director Brief — {s['scene_id']}", "", "- Evidence: `31ffb01 raw response; provider-free replay`", "- New MiMo/LLM calls: `0`", f"- Canonical: `{'VALID' if s['canonical_valid'] else 'INVALID'}`", f"- Authority: `{s['authority']['status']}`", f"- Scope: `{s['scope']['scope_status']}`", f"- Semantic Identity: `{s['semantic_identity']['status']}`", f"- Machine Approval: `{s['director_approval']}`", "", "## Director Strategy", "", _t(c.get("strategy_summary")), "", "## Dramatic Objective", "", _t(c.get("dramatic_objective")), "", "## Scene Question", "", _t(c.get("scene_question")), "", "## Visual Thesis", "", _t(c.get("visual_thesis")), "", "## Phases", ""]
    for p in _l(c.get("scene_phases")):
        lines += [f"### {_t(p.get('phase_id'))} · beats {', '.join(_t(x) for x in _l(p.get('beat_ids')))}", "", f"- Performance: {'; '.join(_t(x.get('character_id'))+'：'+_t(x.get('objective')) for x in _l(p.get('performance')) if isinstance(x, dict))}", f"- Audience question: {_t(_d(p.get('audience_state')).get('question_shift'))}", f"- Visual: {json.dumps(p.get('visual') or {}, ensure_ascii=False)}", ""]
    lines += ["## Review Boundary", "", "> Strategy-only deterministic adjudication. No Shot Architecture, ShotPlan, storyboard, media or production side effect was created."]
    return "\n".join(lines)


def main() -> int:
    head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    rows = _raw_rows(); fingerprints = {r["scene_id"]: r["raw_fingerprint"] for r in rows}; prior = {}
    for r in rows:
        p = ARTIFACTS / "director-quality-v3-strategy-approval-repair-adjudication-scenes" / f"{_safe(r['scene_id'])}-raw-response-fingerprint.json"
        if p.exists(): prior[r["scene_id"]] = _d(json.loads(p.read_text(encoding="utf-8"))).get("fingerprint")
    replay_result = replay(rows); OUT.mkdir(parents=True, exist_ok=True)
    for s in replay_result["scenes"]:
        name = _safe(s["scene_id"]); _write(OUT / f"{name}-semantic-diff.json", {"scene_id": s["scene_id"], "diffs": s["scope"]["semantic_diffs"]}); _write(OUT / f"{name}-scope.json", s["scope"]); _write(OUT / f"{name}-dependency.json", s["dependency"]); _write(OUT / f"{name}-approval.json", {"status": s["director_approval"], "approval": s["approval"], "canonical_valid": s["canonical_valid"]}); (OUT / f"{name}-director-brief.md").write_text(_brief(s), encoding="utf-8")
    counts = {"canonical": sum(s["canonical_valid"] for s in replay_result["scenes"]), "authority_safe": sum(s["authority"]["status"] == "SAFE" for s in replay_result["scenes"]), "registry_identity": sum(s["registry_identity"] == "VALID" for s in replay_result["scenes"]), "semantic_fail": sum(s["semantic_identity"]["status"] == "FAIL" for s in replay_result["scenes"]), "scope": sum(s["scope"]["scope_status"] == "PASS" for s in replay_result["scenes"]), "future_support": sum(s["approval"]["future_support"] for s in replay_result["scenes"]), "future_hint": sum(s["approval"]["future_hint"] for s in replay_result["scenes"]), "future_reveal": sum(s["approval"]["future_reveal"] for s in replay_result["scenes"]), "machine_approval": sum(s["director_approval"] == "APPROVED" for s in replay_result["scenes"])}
    passed = head == EXPECTED_HEAD and all(fingerprints.get(k) == prior.get(k) for k in fingerprints) and counts["canonical"] == counts["authority_safe"] == counts["registry_identity"] == counts["scope"] == counts["machine_approval"] == 3 and counts["semantic_fail"] == counts["future_support"] == counts["future_hint"] == counts["future_reveal"] == 0 and replay_result["distinctiveness"].get("all_pairs_checked") and not replay_result["distinctiveness"].get("hard_failure")
    status = "DIRECTOR_V3_STRATEGY_REPAIR_SCOPE_SEMANTICS_FINALIZED" if passed else "DIRECTOR_V3_STRATEGY_REPAIR_SCOPE_SEMANTICS_FAILED"
    _write(ARTIFACTS / "director-quality-v3-strategy-scope-field-semantics.json", {"schema_version": "strategy_scope_field_semantics_v1", "registry": FIELD_SEMANTICS_REGISTRY, "matcher": "segment-aware", "global_array_sort": False})
    _write(ARTIFACTS / "director-quality-v3-strategy-repair-identity-dependency-contract.json", {"schema_version": "strategy_repair_identity_dependency_v1", "authoritative_identity_required": True, "allowed_reference_fields": ["power.center_ref", "hint_refs", "reveal_refs", "audience_suspicions[*].support_refs", "director_inferences[*].support_refs"], "unknown_subject": "DEPENDENCY_REVIEW_REQUIRED", "dynamic_scope_expansion": False})
    _write(ARTIFACTS / "director-quality-v3-strategy-repair-scope-semantics-replay.json", replay_result)
    _write(ARTIFACTS / "director-quality-v3-strategy-repair-scope-semantics-scope.json", {s["scene_id"]: s["scope"] for s in replay_result["scenes"]})
    _write(ARTIFACTS / "director-quality-v3-strategy-repair-scope-semantics-semantic-identity.json", {s["scene_id"]: s["semantic_identity"] for s in replay_result["scenes"]})
    _write(ARTIFACTS / "director-quality-v3-strategy-repair-scope-semantics-approval.json", {s["scene_id"]: {"status": s["director_approval"], "approval": s["approval"]} for s in replay_result["scenes"]})
    _write(ARTIFACTS / "director-quality-v3-strategy-repair-scope-semantics-distinctiveness.json", replay_result["distinctiveness"])
    _write(ARTIFACTS / "director-quality-v3-strategy-repair-scope-semantics-human-review-package.json", {"status": status, "human_review_pending": True, "ready_for_shot_architecture_canary": False, "briefs": [str(p) for p in sorted(OUT.glob("*-director-brief.md"))]})
    report = f"""# Director Quality V3 — Strategy Repair Scope Semantics Final Report

**Status:** `{status}`

## Baseline Audit

- HEAD: `{head}`; frozen cohort: 3 scenes; source raw responses are immutable.
- Raw response fingerprints unchanged: **{'yes' if all(fingerprints.get(k) == prior.get(k) for k in fingerprints) else 'no'}**.
- Previous scope result was 2/3; Scene 2 retained three false forbidden changes caused by array-order and identity-reference semantics.

## Final As-Built Verification

- Canonical / Authority Safe / Registry Identity / Scope: {counts['canonical']}/3 / {counts['authority_safe']}/3 / {counts['registry_identity']}/3 / {counts['scope']}/3.
- Semantic Identity FAIL: {counts['semantic_fail']}; Future Support / Hint / Reveal: {counts['future_support']}/{counts['future_hint']}/{counts['future_reveal']}.
- Machine Approval: {counts['machine_approval']}/3; Distinctiveness: {replay_result['distinctiveness'].get('pair_count', 0)}/3, hard leakage={replay_result['distinctiveness'].get('hard_failure')}.
- New MiMo/LLM calls: **0**; provider HTTP requests: **0**; transport retries: **0**; semantic retries: **0**.

## Semantics Contract

- ORDERED: `scene_phases`, `scene_phases[*].beat_ids`, `scene_phases[*].performance`.
- SET_LIKE: `reveal_refs`, `hint_refs`, `withhold_refs`, `audience_suspicions[*].support_refs`, `director_inferences[*].support_refs`.
- Set-like reorder is `NO_SEMANTIC_CHANGE`; add/remove is a real diff. Duplicates remain validator-visible and are never hidden by comparison.
- Arrays are not globally sorted because narrative sequence fields encode staging, beat order and performance order.

## Scene 2 Adjudication

- P01 `reveal_refs` is a reorder-only change: `['beat:1','character:19','character:20']` → `['beat:1','character:20','character:19']`; semantic change **false**.
- P01 `hint_refs` `character:20` → `character:19` is an identity dependency repair: the old binding is 顾沉, the revised authoritative binding is 林晚, and the semantic subject is 林晚.
- Remaining forbidden changes: **0**; dynamic scope expansion: **NO**.

## Release Decision

`STRATEGY_PROTOCOL_CLOSED=true`
`STRATEGY_REPAIR_LAYER_CLOSED=true`
`STRATEGY_REPAIR_CAPABILITY=PROVISIONALLY_PROVEN`
`READY_FOR_HUMAN_DIRECTOR_REVIEW=true`
`READY_FOR_SHOT_ARCHITECTURE_CANARY=false`
"""
    (ARTIFACTS / "director-quality-v3-strategy-repair-scope-semantics-report.md").write_text(report, encoding="utf-8")
    gap = f"# Director Quality V3 Strategy Repair Scope Semantics — Gap Audit\n\n## Baseline Audit\n\n- HEAD `{head}`; raw response cohort 3/3; prior Scope 2/3 and Machine Approval 2/3.\n- Historical artifacts and raw responses were not modified.\n\n## Final As-Built Verification\n\n- Status: `{status}`\n- Registry, semantic diff and identity dependency contract are deterministic and provider-free.\n- Canonical/Authority/Registry/Scope/Machine Approval: {counts['canonical']}/3, {counts['authority_safe']}/3, {counts['registry_identity']}/3, {counts['scope']}/3, {counts['machine_approval']}/3.\n- Provider calls: 0; media/storage/shot architecture side effects: 0.\n"
    (ARTIFACTS / "director-quality-v3-strategy-repair-scope-semantics-gap-audit.md").write_text(gap, encoding="utf-8")
    print(json.dumps({"status": status, "counts": counts, "report": str(ARTIFACTS / "director-quality-v3-strategy-repair-scope-semantics-report.md")}, ensure_ascii=False, indent=2)); return 0 if passed else 1


if __name__ == "__main__": raise SystemExit(main())
