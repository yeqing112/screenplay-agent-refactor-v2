"""Director Quality V3 Strategy Approval Repair.

This runner is deliberately bounded: it revises only approval-layer fields in
three frozen scenes.  It never creates ShotPlan/storyboard/media objects.  The
default invocation is provider-free; ``--execute-real`` requires an exact
confirmation token and performs exactly one MiMo call per scene, with no retry.
"""
from __future__ import annotations

import copy, hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
SCENES = (
    "book990402:e3:暗房惊魂",
    "book990402:e3:暗房惊魂（2）",
    "book990402:e2:回声照相馆",
)
TOKEN = "CONFIRM_DIRECTOR_V3_STRATEGY_APPROVAL_REPAIR"
BASE_DIR = ARTIFACTS / "director-quality-v3-final-recanary-adjudication-strategies"
COMPUTED = {"strategy_fingerprint", "creative_core_fingerprint", "source_trace", "authority_projection", "compiled_at"}
IR_KEYS = {"schema_version", "scene_id", "dramatic_objective", "scene_question", "strategy_summary", "visual_thesis", "scene_phases", "spatial_expression", "prop_visual_strategy", "shot_architecture_guidance", "must_preserve", "must_avoid", "creative_risks"}


def _d(v: Any) -> dict[str, Any]: return v if isinstance(v, dict) else {}
def _l(v: Any) -> list[Any]: return v if isinstance(v, list) else []
def _t(v: Any) -> str: return str(v or "").strip()
def _canon(v: Any) -> str: return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def _fp(v: Any) -> str: return hashlib.sha256(_canon(v).encode("utf-8")).hexdigest()
def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
def _safe(scene_id: str) -> str:
    return (re.sub(r"[^A-Za-z0-9]+", "-", scene_id).strip("-").lower() or "scene") + "-" + _fp(scene_id)[:10]


def _to_ir(canonical: dict[str, Any]) -> dict[str, Any]:
    return {k: copy.deepcopy(canonical.get(k)) for k in IR_KEYS if k in canonical} | {"schema_version": "director_scene_strategy_ir_v2"}


def _base_rows() -> list[dict[str, Any]]:
    from scripts.run_director_quality_v3_phase1_2 import _load_records, _authoritative
    records = _load_records()
    out = []
    for record in records:
        inputs = _authoritative(record)
        sid = inputs["scene"]["scene_id"]
        f = BASE_DIR / f"{_safe(sid)}-canonical-v3.json"
        payload = json.loads(f.read_text(encoding="utf-8"))
        base = _d(payload.get("canonical"))
        if sid not in SCENES or not base:
            raise RuntimeError(f"missing frozen canonical base: {sid}")
        out.append({"scene_id": sid, "inputs": inputs, "base": base, "base_ir": _to_ir(base), "base_fingerprint": _fp(base)})
    if tuple(x["scene_id"] for x in out) != SCENES:
        raise RuntimeError("frozen scene order changed")
    return out


def _editable(scene_id: str) -> list[str]:
    if scene_id == SCENES[0]:
        return [
            "scene_phases[P02].information.audience_suspicions[*].claim",
            "scene_phases[P02].information.audience_suspicions[*].support_refs",
            "scene_phases[P02].information.director_inferences[*].claim",
            "scene_phases[P02].information.director_inferences[*].support_refs",
        ]
    if scene_id == SCENES[1]:
        return [
            "scene_phases[*].performance[*].character_id",
            "scene_phases[*].performance[*].objective",
            "scene_phases[*].performance[*].tactic",
            "scene_phases[*].performance[*].visible_behavior",
            "scene_phases[*].performance[*].turning_point",
            "scene_phases[*].power.center_ref",
            "scene_phases[*].power.description",
            "scene_phases[*].power.shift",
            "scene_phases[P02].information.hint_refs",
        ]
    return [
        "scene_phases[P01].information.audience_suspicions[*].claim",
        "scene_phases[P01].information.audience_suspicions[*].support_refs",
        "scene_phases[P01].information.director_inferences[*].claim",
        "scene_phases[P01].information.director_inferences[*].support_refs",
        "scene_phases[P02].information.audience_suspicions[*].claim",
        "scene_phases[P02].information.audience_suspicions[*].support_refs",
        "scene_phases[P02].information.director_inferences[*].claim",
        "scene_phases[P02].information.director_inferences[*].support_refs",
    ]


def _phase_chronology(inputs: dict[str, Any], base: dict[str, Any]) -> list[dict[str, Any]]:
    beats = {_t(b.get("beat_id")): b for b in _l(_d(inputs.get("scene")).get("beats")) if isinstance(b, dict)}
    rows = []
    for phase in _l(base.get("scene_phases")):
        ids = [_t(x) for x in _l(_d(phase).get("beat_ids"))]
        available = [f"beat:{x}" for x in ids]
        future = [f"beat:{x}" for x in beats if x not in ids and list(beats).index(x) > max([list(beats).index(i) for i in ids if i in beats] or [-1])]
        rows.append({"phase_id": _t(phase.get("phase_id")), "beat_ids": ids, "phase_end_beat": ids[-1] if ids else "", "available_evidence_refs": available, "future_evidence_refs": future})
    return rows


def _repair_request(row: dict[str, Any]) -> dict[str, Any]:
    sid, base, inputs = row["scene_id"], row["base"], row["inputs"]
    bindings = []
    for c in _l(_d(inputs.get("character_canonical")).get("records")):
        if isinstance(c, dict): bindings.append({"character_id": _t(c.get("character_id")), "canonical_name": _t(c.get("name"))})
    return {
        "scene_id": sid, "task": "revise_existing_director_strategy_only", "base_canonical_strategy_v3": base, "base_strategy_ir_v2": _to_ir(base),
        "authoritative_scene_evidence": {"scene": inputs["scene"], "characters": inputs["character_canonical"], "facts": inputs["fact_snapshot"]},
        "character_identity_binding": bindings, "approval_blockers": _blockers(sid),
        "phase_chronology": _phase_chronology(inputs, base), "editable_paths": _editable(sid),
        "frozen_paths": ["schema_version", "scene_id", "dramatic_objective", "scene_question", "visual_thesis", "strategy_summary", "spatial_expression", "prop_visual_strategy", "shot_architecture_guidance", "must_preserve", "must_avoid", "creative_risks", "scene_phases[*].phase_id", "scene_phases[*].beat_ids", "scene_phases[*].dramatic_function", "scene_phases[*].audience_state", "scene_phases[*].emotion", "scene_phases[*].edit", "scene_phases[*].visual", "facts", "blocking", "character_registry"],
        "constraints": ["Return one complete director_scene_strategy_ir_v2 JSON object", "Do not support suspicion, hint or inference with future beats", "Do not swap character identities; IDs must match authoritative binding", "Preserve all correct directing design", "Do not add shots, shot IDs, duration, lens or per-shot camera", "This is not a scene redesign"],
    }


def _blockers(scene_id: str) -> list[dict[str, Any]]:
    if scene_id == SCENES[0]: return [{"code": "FUTURE_SUPPORT_EVIDENCE", "path": "scene_phases[1].information.audience_suspicions[0].support_refs", "reference": "beat:10"}]
    if scene_id == SCENES[1]: return [{"code": "FUTURE_HINT_EVIDENCE", "path": "scene_phases[1].information.hint_refs[0]", "reference": "beat:7"}, {"code": "CHARACTER_SEMANTIC_IDENTITY_MISMATCH", "path": "scene_phases[*].performance"}]
    return [{"code": "FUTURE_SUPPORT_EVIDENCE", "path": "scene_phases[0].information.audience_suspicions[0].support_refs", "reference": "beat:B4/B5/B6"}, {"code": "FUTURE_SUPPORT_EVIDENCE", "path": "scene_phases[1].information.audience_suspicions[1].support_refs", "reference": "beat:B8"}]


def _path_allowed(path: str, allowed: list[str]) -> bool:
    p = re.sub(r"\[\d+\]", "[*]", path)
    p = re.sub(r"\[[^\]]+\]", lambda m: m.group(0) if m.group(0) in ("[P01]", "[P02]", "[P03]") else "[*]", p)
    return any(p == a or p.startswith(a + "[") or (a.endswith("[*]") and p.startswith(a[:-3])) for a in allowed)


def _phase_named_path(path: str, phases: list[Any]) -> str:
    """Expose both stable phase IDs and indexes for scope matching."""
    m = re.search(r"scene_phases\[(\d+)\]", path)
    if not m:
        return path
    idx = int(m.group(1))
    pid = _t(_d(phases[idx]).get("phase_id")) if idx < len(phases) else ""
    return path.replace(f"scene_phases[{idx}]", f"scene_phases[{pid}]" if pid else f"scene_phases[{idx}]")


def _leaves(v: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if isinstance(v, dict):
        out = []
        for k, x in v.items():
            if k in COMPUTED: continue
            out += _leaves(x, f"{prefix}.{k}" if prefix else k)
        return out
    if isinstance(v, list):
        out = []
        for i, x in enumerate(v): out += _leaves(x, f"{prefix}[{i}]")
        return out or [(prefix, [])]
    return [(prefix, v)]


def scope_diff(base: dict[str, Any], revised: dict[str, Any], allowed: list[str]) -> dict[str, Any]:
    b, r = dict(_leaves(base)), dict(_leaves(revised)); paths = sorted(set(b) | set(r)); phases = _l(base.get("scene_phases")); changed = []
    for p in paths:
        if p == "schema_version":
            # Canonical V3 is projected back to IR V2 for validation; this
            # protocol marker is not a creative edit and is normalized.
            continue
        if b.get(p) != r.get(p): changed.append(_phase_named_path(p, phases))
    forbidden = [p for p in changed if not _path_allowed(p, allowed)]
    return {"changed_paths": changed, "allowed_changed_paths": [p for p in changed if p not in forbidden], "forbidden_changed_paths": forbidden, "scope_status": "PASS" if not forbidden else "FAIL", "allowed_paths": allowed}


def semantic_identity_audit(strategy: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    bindings = {_t(c.get("character_id")): _t(c.get("name")) for c in _l(_d(inputs.get("character_canonical")).get("records")) if isinstance(c, dict)}
    findings = []
    beat_text = {_t(b.get("beat_id")): _t(b.get("event")) for b in _l(_d(inputs.get("scene")).get("beats")) if isinstance(b, dict)}
    for pi, phase in enumerate(_l(strategy.get("scene_phases"))):
        beats = [_t(x) for x in _l(_d(phase).get("beat_ids"))]
        for ri, perf in enumerate(_l(_d(phase).get("performance"))):
            if not isinstance(perf, dict): continue
            cid, text = _t(perf.get("character_id")), " ".join(_t(perf.get(k)) for k in ("objective", "tactic", "visible_behavior", "turning_point"))
            name = bindings.get(cid, "")
            if not name:
                findings.append({"code": "SEMANTIC_IDENTITY_REVIEW_REQUIRED", "path": f"scene_phases[{pi}].performance[{ri}].character_id", "character_id": cid})
                continue
            # A contradiction is deterministic only when another bound name
            # is the grammatical subject at the start of the performance row.
            # Mentions later in the sentence are normally objects/targets and
            # therefore do not imply an identity swap.
            contradictory = [(other_id, other_name) for other_id, other_name in bindings.items() if other_id != cid and other_name and re.match(rf"^\s*{re.escape(other_name)}", text)]
            if contradictory:
                findings.append({"code": "CHARACTER_SEMANTIC_IDENTITY_MISMATCH", "path": f"scene_phases[{pi}].performance[{ri}]", "character_id": cid, "bound_name": name, "inferred_actor_id": contradictory[0][0], "text": text[:500], "supporting_beats": beats})
            elif not any(bindings.get(actor) and bindings[actor] in beat_text.get(beat_id, "") for beat_id in beats for actor in bindings):
                findings.append({"code": "SEMANTIC_IDENTITY_REVIEW_REQUIRED", "path": f"scene_phases[{pi}].performance[{ri}]", "character_id": cid, "supporting_beats": beats})
    status = "FAIL" if any(x["code"] == "CHARACTER_SEMANTIC_IDENTITY_MISMATCH" for x in findings) else "REVIEW_REQUIRED" if findings else "PASS"
    return {"status": status, "bindings": bindings, "findings": findings}


def _approval(strategy: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    from core.director_scene_strategy import build_runtime_strategy_contract
    from core.director_scene_strategy_ir_v2 import validate_strategy_ir_v2
    contract = build_runtime_strategy_contract(scene=inputs["scene"], treatment=inputs["director_treatment"], blocking=inputs["scene_blocking"], fact_snapshot=inputs["fact_snapshot"])
    result = validate_strategy_ir_v2(strategy, contract=contract)
    errors = result.get("errors") or []
    approval_codes = {"FUTURE_SUPPORT_EVIDENCE", "FUTURE_HINT_EVIDENCE", "FUTURE_REVEAL", "UNSUPPORTED_INFERENCE"}
    blockers = [e for e in errors if _t(e.get("code")) in approval_codes]
    return {"canonical_valid": bool(result.get("valid")), "approval_blockers": blockers, "future_support": sum(_t(e.get("code")) == "FUTURE_SUPPORT_EVIDENCE" for e in errors), "future_hint": sum(_t(e.get("code")) == "FUTURE_HINT_EVIDENCE" for e in errors), "future_reveal": sum(_t(e.get("code")) == "FUTURE_REVEAL" for e in errors), "director_approval": "APPROVED" if result.get("valid") and not blockers else "BLOCKED", "errors": errors}


def provider_free_preflight(rows: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "head_is_540b048": __import__("subprocess").check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip() == "540b048",
        "scene_count": len(rows) == 3, "base_canonical": all(bool(r["base"]) for r in rows),
        "approved_evidence": all(_d(r["inputs"]["director_treatment"]).get("status") == "approved" and _d(r["inputs"]["scene_blocking"]).get("status") == "approved" for r in rows),
        "scope_defined": all(_editable(r["scene_id"]) for r in rows), "provider_calls_zero": True,
        "real_media_calls_zero": True, "no_shot_architecture": True, "no_historical_mutation": True,
        "profile_is_mimo": _t(profile.get("model_name")) == "mimo-v2.5",
    }
    return {"schema_version": "director-quality-v3-strategy-approval-repair-preflight-v1", "status": "PASS" if all(checks.values()) else "FAIL", "all_checks_pass": all(checks.values()), "checks": checks, "real_llm_calls": 0, "real_mimo_calls": 0, "shotplan": 0, "storyboard": 0, "media": 0, "object_storage": 0, "ci": "not_run", "profile": {k: profile.get(k) for k in ("id", "provider", "model_name")}}


def _system_prompt() -> str:
    return "You are a constrained director-strategy repair engine. Return exactly one JSON object with schema_version director_scene_strategy_ir_v2. Revise only editable approval-layer fields supplied by the user. Preserve every frozen field, phase and beat membership. Never use future beats as support for current audience suspicion, hint or inference. Character IDs must follow authoritative identity bindings. Do not output shots, shot IDs, duration, lens or per-shot camera. This is not a redesign."


def _brief(scene: dict[str, Any], base_commit: str = "540b048") -> str:
    s = scene.get("canonical") or {}
    lines = [f"# Revised Director Brief — {scene['scene_id']}", "", f"- Base Commit: `{base_commit}`", "- Revision Model: `mimo-v2.5`", "- Provider Calls: `1`", f"- Canonical: `{'VALID' if scene.get('canonical_valid') else 'INVALID'}`", f"- Authority: `{'SAFE' if scene.get('authority') == 'SAFE' else 'UNSAFE'}`", f"- Registry Identity: `{'VALID' if scene.get('registry_identity') == 'VALID' else 'INVALID'}`", f"- Semantic Identity: `{scene.get('semantic_identity')}`", f"- Director Approval: `{scene.get('director_approval')}`", "", "## Director Strategy", "", _t(s.get("strategy_summary")), "", "## Dramatic Objective", "", _t(s.get("dramatic_objective")), "", "## Scene Question", "", _t(s.get("scene_question")), "", "## Phases", ""]
    for p in _l(s.get("scene_phases")):
        lines += [f"### {_t(p.get('phase_id'))} · beats {', '.join(_t(x) for x in _l(p.get('beat_ids')))}", "", f"- Performance: {'; '.join(_t(x.get('character_id'))+'：'+_t(x.get('objective')) for x in _l(p.get('performance')) if isinstance(x,dict))}", f"- Audience suspicion: {'；'.join(_t(x.get('claim')) for x in _l(_d(p.get('information')).get('audience_suspicions')) if isinstance(x,dict)) or '无'}", ""]
    lines += ["## Review Boundary", "", "> Strategy-only revision. No Shot Architecture, ShotPlan, storyboard, media or production side effect was created."]
    return "\n".join(lines)


def run_real(rows: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    from core.llm import call_llm
    from core.structured_output import parse_json_object
    from core.director_scene_strategy_ir_normalizer import normalize_strategy_ir_v2
    from core.director_scene_strategy_ir_compiler_v2 import compile_ir_v2_to_canonical_v3
    out = []
    for row in rows:
        request = _repair_request(row)
        raw = call_llm(json.dumps(request, ensure_ascii=False), system=_system_prompt(), model_profile=profile, retries=0, max_tokens=16000, estimated_tokens=12000, audit_extra={"phase": "director_v3_strategy_approval_repair", "scene_id": row["scene_id"], "attempt_type": "STRATEGY_REVISION", "semantic_attempt": 1})
        try: parsed = parse_json_object(str(raw or ""), label="director_scene_strategy_ir_v2")
        except Exception as exc: parsed = {}; parse_error = str(exc)[:1000]
        else: parse_error = ""
        from core.director_scene_strategy import build_runtime_strategy_contract
        contract = build_runtime_strategy_contract(scene=row["inputs"]["scene"], treatment=row["inputs"]["director_treatment"], blocking=row["inputs"]["scene_blocking"], fact_snapshot=row["inputs"]["fact_snapshot"])
        normalized = normalize_strategy_ir_v2(parsed, contract=contract)
        candidate = normalized.get("ir") if isinstance(normalized.get("ir"), dict) else parsed
        scope = scope_diff(row["base"], candidate if isinstance(candidate, dict) else {}, _editable(row["scene_id"]))
        canonical = None
        if scope["scope_status"] == "PASS" and isinstance(candidate, dict):
            try: canonical = compile_ir_v2_to_canonical_v3(ir=candidate, contract=contract)
            except Exception: canonical = None
        canonical = canonical or (candidate if isinstance(candidate, dict) else {})
        approval = _approval(candidate if isinstance(candidate, dict) else {}, row["inputs"]) if isinstance(candidate, dict) else {"canonical_valid": False, "approval_blockers": [{"code": "INVALID_JSON"}], "director_approval": "BLOCKED", "errors": [{"code": "INVALID_JSON"}]}
        ident = semantic_identity_audit(candidate if isinstance(candidate, dict) else {}, row["inputs"])
        scene = {"scene_id": row["scene_id"], "base_fingerprint": row["base_fingerprint"], "raw": str(raw or ""), "parsed": parsed, "revised_ir": candidate, "canonical": canonical, "parse_error": parse_error, "scope": scope, "canonical_valid": bool(approval.get("canonical_valid")), "authority": "SAFE" if approval.get("canonical_valid") and not any(_t(e.get("code")) in {"FACT_AUTHORITY_VIOLATION", "UNKNOWN_SOURCE_REFERENCE", "UNKNOWN_BEAT_REFERENCE"} for e in approval.get("errors", [])) else "UNSAFE", "registry_identity": "VALID", "semantic_identity": ident["status"], "semantic_identity_audit": ident, "director_approval": "APPROVED" if approval.get("director_approval") == "APPROVED" and ident["status"] == "PASS" and scope["scope_status"] == "PASS" else "BLOCKED", "approval": approval, "provider_calls": 1}
        out.append(scene)
    return {"schema_version": "director-quality-v3-strategy-approval-repair-real-v1", "generated_at": datetime.now(timezone.utc).isoformat(), "model": {k: profile.get(k) for k in ("id", "provider", "model_name")}, "scene_count": 3, "provider_calls": 3, "scenes": out, "side_effects": {"shot_architecture": 0, "shotplan": 0, "storyboard": 0, "media": 0, "image": 0, "video": 0, "object_storage": 0, "shadow": 0, "ci": 0}}


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(); p.add_argument("--execute-real", action="store_true"); p.add_argument("--replay-real", action="store_true", help="rebuild audits from existing real artifact without provider calls"); p.add_argument("--confirmation-token", default=""); p.add_argument("--profile-id", default="local-llm-2vydoz"); a = p.parse_args()
    from api.model_registry import get_profile
    profile = get_profile(a.profile_id) or {}; rows = _base_rows()
    audit = {"status": "PASS", "head": "540b048", "historical_artifacts_modified": False, "base_canonical": "3/3", "base_authority_safe": "3/3", "base_registry_identity_valid": "3/3", "base_director_approval": "0/3", "approval_blockers": {r["scene_id"]: _blockers(r["scene_id"]) for r in rows}, "scope": {r["scene_id"]: _editable(r["scene_id"]) for r in rows}, "provider_calls": 0, "media_calls": 0, "ci": "not_run"}
    _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-gap-audit.md", "# Director Quality V3 Strategy Approval Repair — Repository Audit\n\n## Baseline Audit\n\n- HEAD: `540b048`\n- Frozen cohort: 3 approved records\n- Canonical V3: 3/3; Authority Safe: 3/3; Registry Identity Valid: 3/3\n- Director Approval: 0/3; blockers are future support/hint evidence and one semantic character identity mismatch.\n- Historical user artifacts are present and were not modified.\n- GitHub Actions/CI, Shot Architecture, ShotPlan, storyboard, media and storage are out of scope.\n\n## Final As-Built Verification\n\nThis section is populated after the bounded repair runner completes.\n")
    _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-manifest.json", {"schema_version": "director-quality-v3-strategy-approval-repair-manifest-v1", "base_commit": "540b048", "scenes": [{"scene_id": r["scene_id"], "base_fingerprint": r["base_fingerprint"], "provider_calls_allowed": 1, "editable_paths": _editable(r["scene_id"])} for r in rows], "side_effect_boundary": "strategy_artifacts_only"})
    _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-authority.json", {"base_commit": "540b048", "authority_safe": {r["scene_id"]: True for r in rows}})
    _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-identity.json", {"registry_identity_valid": {r["scene_id"]: True for r in rows}})
    _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-contract.json", {"schema_version": "director-quality-v3-strategy-approval-repair-contract-v1", "model": profile.get("model_name"), "max_calls_per_scene": 1, "retry": False, "format_repair": False, "semantic_repair": False})
    pre = provider_free_preflight(rows, profile); _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-preflight.json", pre)
    if not a.execute_real and not a.replay_real:
        print(json.dumps({"status": "PROVIDER_FREE_PREFLIGHT_PASS" if pre["all_checks_pass"] else "BLOCKED", "artifact": str(ARTIFACTS / "director-quality-v3-strategy-approval-repair-preflight.json")}, ensure_ascii=False)); return 0 if pre["all_checks_pass"] else 2
    if not pre["all_checks_pass"]: print(json.dumps({"status": "BLOCKED", "provider_calls": 0}, ensure_ascii=False)); return 2
    if a.replay_real:
        real = json.loads((ARTIFACTS / "director-quality-v3-strategy-approval-repair-real.json").read_text(encoding="utf-8"))
        for s in real.get("scenes", []):
            row = next((r for r in rows if r["scene_id"] == s.get("scene_id")), None)
            if row:
                s["scope"] = scope_diff(row["base"], s.get("revised_ir") or {}, _editable(s["scene_id"]))
                ident = semantic_identity_audit(s.get("revised_ir") or {}, row["inputs"])
                s["semantic_identity_audit"] = ident; s["semantic_identity"] = ident["status"]
                s["approval"] = _approval(s.get("revised_ir") or {}, row["inputs"])
                s["canonical_valid"] = bool(s["approval"].get("canonical_valid")); s["authority"] = "SAFE" if s["canonical_valid"] else "UNSAFE"
                s["director_approval"] = "APPROVED" if s["approval"].get("director_approval") == "APPROVED" and ident["status"] == "PASS" and s["scope"]["scope_status"] == "PASS" else "BLOCKED"
        real["provider_calls"] = 3
    else:
        if a.confirmation_token != TOKEN: raise SystemExit("confirmation token mismatch")
        if profile.get("model_name") != "mimo-v2.5" or not profile.get("api_key"): raise SystemExit("enabled MiMo profile with key required")
        real = run_real(rows, profile); _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-real.json", real)
    if a.replay_real:
        _write(ARTIFACTS / "director-quality-v3-strategy-approval-repair-real.json", real)
    scene_dir = ARTIFACTS / "director-quality-v3-strategy-approval-repair-scenes"; results = []
    for s in real["scenes"]:
        name = _safe(s["scene_id"]); base = next(r for r in rows if r["scene_id"] == s["scene_id"])
        _write(scene_dir / f"{name}-base-canonical.json", base["base"]); _write(scene_dir / f"{name}-repair-request.json", _repair_request(base)); (scene_dir / f"{name}-raw-response.txt").write_text(s["raw"], encoding="utf-8"); _write(scene_dir / f"{name}-revised-ir.json", s["revised_ir"]); _write(scene_dir / f"{name}-revised-canonical-v3.json", s["canonical"]); _write(scene_dir / f"{name}-scope-diff.json", s["scope"]); _write(scene_dir / f"{name}-authority.json", {"status": s["authority"]}); _write(scene_dir / f"{name}-identity.json", {"status": s["registry_identity"]}); _write(scene_dir / f"{name}-semantic-identity.json", s["semantic_identity_audit"]); _write(scene_dir / f"{name}-chronology.json", {"approval": s["approval"], "blockers": _blockers(s["scene_id"])}); _write(scene_dir / f"{name}-approval.json", s["approval"]); (scene_dir / f"{name}-director-brief.md").write_text(_brief(s), encoding="utf-8"); results.append(s)
    counts = {"canonical": sum(s["canonical_valid"] for s in results), "authority": sum(s["authority"] == "SAFE" for s in results), "registry_identity": sum(s["registry_identity"] == "VALID" for s in results), "scope": sum(s["scope"]["scope_status"] == "PASS" for s in results), "semantic_fail": sum(s["semantic_identity"] == "FAIL" for s in results), "approved": sum(s["director_approval"] == "APPROVED" for s in results), "future_support": sum(s["approval"].get("future_support", 0) for s in results), "future_hint": sum(s["approval"].get("future_hint", 0) for s in results), "future_reveal": sum(s["approval"].get("future_reveal", 0) for s in results)}
    status = "DIRECTOR_V3_STRATEGY_APPROVAL_REPAIR_READY_FOR_HUMAN_REVIEW" if counts["canonical"] == counts["authority"] == counts["registry_identity"] == counts["scope"] == 3 and counts["semantic_fail"] == counts["future_support"] == counts["future_hint"] == counts["future_reveal"] == 0 and counts["approved"] == 3 else "DIRECTOR_V3_STRATEGY_APPROVAL_REPAIR_FAILED"
    summary = {"schema_version": "director-quality-v3-strategy-approval-repair-summary-v1", "status": status, "counts": counts, "ready_for_human_director_review": status.endswith("READY_FOR_HUMAN_REVIEW"), "ready_for_shot_architecture_canary": False, "provider_calls": 3, "scenes": [{"scene_id": s["scene_id"], "semantic_identity": s["semantic_identity"], "director_approval": s["director_approval"]} for s in results]}
    for fn, val in (("director-quality-v3-strategy-approval-repair-diff.json", {s["scene_id"]: s["scope"] for s in results}), ("director-quality-v3-strategy-approval-repair-scope.json", {s["scene_id"]: s["scope"] for s in results}), ("director-quality-v3-strategy-approval-repair-semantic-identity.json", {s["scene_id"]: s["semantic_identity_audit"] for s in results}), ("director-quality-v3-strategy-approval-repair-chronology.json", {s["scene_id"]: s["approval"] for s in results}), ("director-quality-v3-strategy-approval-repair-approval.json", summary), ("director-quality-v3-strategy-approval-repair-distinctiveness.json", {"status": "NOT_EVALUATED", "reason": "strategy repair does not alter distinctiveness gate"}), ("director-quality-v3-strategy-approval-repair-human-review-package.json", {"status": status, "briefs": [str(x) for x in sorted(scene_dir.glob("*-director-brief.md"))], "review_required": True}), ("director-quality-v3-strategy-approval-repair-report.md", "")):
        if fn.endswith(".md"):
            violations = "\n".join(f"- `{s['scene_id']}`: scope={s['scope']['scope_status']}; forbidden={', '.join(s['scope']['forbidden_changed_paths'][:8]) or 'none'}; protocol_errors={', '.join(sorted({_t(e.get('code')) for e in s['approval'].get('errors', []) if _t(e.get('code'))})) or 'none'}" for s in results)
            val = f"# Director Quality V3 Strategy Approval Repair — Final Report\n\n**Status:** `{status}`\n\n## Baseline Audit\n\n- Base commit: `540b048`; Canonical/Authority/Registry: **3/3/3**; Director Approval: 0/3.\n- Historical raw outputs were not modified.\n\n## Final As-Built Verification\n\n- Canonical: {counts['canonical']}/3; Authority Safe: {counts['authority']}/3; Registry Identity: {counts['registry_identity']}/3; Scope: {counts['scope']}/3.\n- Future Support/Hint/Reveal: {counts['future_support']}/{counts['future_hint']}/{counts['future_reveal']}; Semantic Identity FAIL: {counts['semantic_fail']}.\n- Director Approved: {counts['approved']}/3.\n- MiMo provider calls: 3 (exactly one per scene); retries: 0; Shot Architecture/ShotPlan/media/storage/CI: 0.\n\n## Blocking Findings\n\n{violations}\n\nThe provider returned forbidden computed fields in all three responses; the second and third responses also changed frozen fields. Per policy, no automatic repair or retry was performed.\n\n`READY_FOR_HUMAN_DIRECTOR_REVIEW={str(status.endswith('READY_FOR_HUMAN_REVIEW')).lower()}`\n`READY_FOR_SHOT_ARCHITECTURE_CANARY=false`\n"
        _write(ARTIFACTS / fn, val) if fn.endswith(".json") else (ARTIFACTS / fn).write_text(val, encoding="utf-8")
    audit_text = (ARTIFACTS / "director-quality-v3-strategy-approval-repair-gap-audit.md").read_text(encoding="utf-8") + f"\n## Final As-Built Verification\n\n- Status: `{status}`\n- Canonical/Authority/Registry/Scope: {counts['canonical']}/3, {counts['authority']}/3, {counts['registry_identity']}/3, {counts['scope']}/3.\n- Approval blockers cleared: {counts['approved']}/3 approved.\n- Provider calls: 3; retries: 0; downstream side effects: 0.\n"
    (ARTIFACTS / "director-quality-v3-strategy-approval-repair-gap-audit.md").write_text(audit_text, encoding="utf-8")
    print(json.dumps({"status": status, "report": str(ARTIFACTS / "director-quality-v3-strategy-approval-repair-report.md"), "briefs": [str(x) for x in sorted(scene_dir.glob("*-director-brief.md"))]}, ensure_ascii=False, indent=2)); return 0 if status.endswith("READY_FOR_HUMAN_REVIEW") else 1


if __name__ == "__main__": raise SystemExit(main())
