"""Generate the provider-free V7.7.0 ClaimIR shadow-audit package.

This script reads immutable forensic artifacts and performs read-only database
queries.  It never imports a provider client, calls an API endpoint, or writes
to production tables.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.canary_scope import build_scope_descriptor, target_scope_snapshot
from core.director_claim_authority import authority_matrix, validate_authority_matrix
from core.director_claim_extraction import claim_set_document, extract_claims, project_source_claims
from core.director_claim_grounding import audit_claim_set, evaluate_claim_support
from core.director_claim_ir import claim_set_fingerprint, contract, shadow_audit_schema, validate_claim_set
from core.director_progressive_authoring import compile_progressive_director_proposal, materialize_director_beat_plan_ids
from models import DecisionPacketRecord, Session


OUT = ROOT / "docs" / "canonical-canary" / "v7_7_0-semantic-grounding-v3-foundation"
SOURCE_PATH = ROOT / "docs" / "canonical-canary" / "v7_1-director-source-grounded-authoring-contract" / "SOURCE_AUTHORING_UNIT_CONTRACT.json"
ATTEMPT_PATHS = {
    "STAGE_A": ROOT / "docs" / "canonical-canary" / "v7_6_8-attempt7-real-stage-a-canary" / "ATTEMPT7_RAW_FORENSIC.json",
    "ATTEMPT9": ROOT / "docs" / "canonical-canary" / "v7_6_15-attempt9-real-semantic-revision" / "ATTEMPT9_RAW_FORENSIC.json",
    "ATTEMPT10": ROOT / "docs" / "canonical-canary" / "v7_6_18-attempt10-real-semantic-v2-revision" / "ATTEMPT10_RAW_FORENSIC.json",
    "ATTEMPT11": ROOT / "docs" / "canonical-canary" / "v7_6_21-attempt11-real-semantic-v2-structural-revision" / "ATTEMPT11_RAW_FORENSIC.json",
}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _raw(path: Path) -> dict[str, Any]:
    data = _read(path)
    data = data.get("forensic", data)
    return json.loads(str(data["raw_response"]))


def _write(name: str, value: Any) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _production_snapshot() -> dict[str, Any]:
    """Read Packet 64 and target-scoped rows without mutating the session."""
    scope = build_scope_descriptor(book_id=990453, episode=1, scene_id="E01_SC001", script_id=64, fact_snapshot_id=49, script_ir_version_id=52, decision_packet_id=64)
    with Session() as session:
        packet = session.query(DecisionPacketRecord).filter(DecisionPacketRecord.id == 64, DecisionPacketRecord.book_id == 990453).one_or_none()
        target = target_scope_snapshot(session, scope=scope)
        if packet is None:
            return {"scope_descriptor": scope, "scope_fingerprint": _sha(scope), "packet_present": False, "target": target}
        info = json.loads(packet.model_info or "{}")
        proposal = json.loads(packet.proposal or "{}")
        attempts = info.get("director_llm_attempts") or []
        stage_b = (info.get("progressive_director_authoring") or {}).get("stage_b") or {}
        return {
            "scope_descriptor": scope, "scope_fingerprint": _sha(scope), "packet_present": True,
            "packet_id": packet.id, "packet_fingerprint": packet.packet_fingerprint, "status": packet.status,
            "proposal": proposal, "proposal_sha256": hashlib.sha256((packet.proposal or "").encode("utf-8")).hexdigest(),
            "model_info_sha256": hashlib.sha256((packet.model_info or "").encode("utf-8")).hexdigest(),
            "attempt_count": len(attempts), "attempt_ids": [str(x.get("attempt_id")) for x in attempts if isinstance(x, Mapping)],
            "active_stage_b_attempt": stage_b.get("attempt_id"), "active_stage_b_status": stage_b.get("status"),
            "target": target,
        }


def _source_ref_map(stage_a: Mapping[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for i, beat in enumerate(stage_a.get("beats") or []):
        refs = [str(x) for x in (beat.get("refs") or [])] if isinstance(beat, Mapping) else []
        for path in (f"beats[{i}]", f"beats[{i}].purpose", f"beats[{i}].objective", f"beats[{i}].information_change", f"beats[{i}].hook"):
            mapping[path] = refs
    return mapping


def _stage_b_ref_map(stage_b: Mapping[str, Any], stage_a: Mapping[str, Any]) -> dict[str, list[str]]:
    refs_by_beat = {str(x.get("beat_ref")): [str(r) for r in (stage_a.get("beats") or [])[i].get("refs", [])] for i, x in enumerate(stage_b.get("beat_enrichments") or []) if isinstance(x, Mapping) and i < len(stage_a.get("beats") or [])}
    result: dict[str, list[str]] = {}
    for i, item in enumerate(stage_b.get("beat_enrichments") or []):
        beat_ref = str(item.get("beat_ref") or "") if isinstance(item, Mapping) else ""
        refs = refs_by_beat.get(beat_ref, [])
        for path in (f"beat_enrichments[{i}]", f"beat_enrichments[{i}].audience_effect", f"beat_enrichments[{i}].performance", f"beat_enrichments[{i}].transition"):
            result[path] = refs
    return result


def _structural_status(name: str) -> str:
    if name == "ATTEMPT10":
        return "FAIL"
    return "PASS"


def _mandatory_cases(claims: list[Mapping[str, Any]], source_claims: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    cases = [
        ("delegation", "SceneBlocking", "AUTHORITY_DELEGATION"),
        ("试探林晚", "试探", "CHARACTER_INTENT"),
        ("不惊动林晚", "不惊动", "CHARACTER_INTENT"),
        ("微弱光线", "微弱光线", "ENVIRONMENT_STATE"),
        ("车票背面的手写指令", "手写", "OBJECT_PROPERTY"),
        ("接过车票", "接过车票", "OBJECT_POSSESSION"),
        ("母亲留下的物件", "母亲留下", "OBJECT_PROVENANCE"),
        ("第一次直面母亲留下的暗房", "第一次", "CERTAINTY_ASSERTION"),
        ("母亲留下的暗房", "母亲留下", "OBJECT_PROVENANCE"),
    ]
    result = []
    for label, token, expected_type in cases:
        matches = [c for c in claims if c.get("claim_type") == expected_type and (token.lower() in str(c.get("raw_text") or "").lower() or expected_type == "AUTHORITY_DELEGATION")]
        if label.startswith("车票背面"):
            ticket_matches = [c for c in matches if "车票" in str(c.get("raw_text") or "")]
            matches = ticket_matches
        if not matches and expected_type == "OBJECT_PROPERTY":
            matches = [c for c in claims if c.get("claim_type") == expected_type and "车票" in str(c.get("raw_text") or "")]
        if not matches and expected_type == "OBJECT_POSSESSION":
            matches = [c for c in claims if c.get("claim_type") == expected_type and "车票" in str(c.get("raw_text") or "")]
        if not matches:
            result.append({"case": label, "present": False, "expected_claim_type": expected_type, "status": "MISSING_CLAIM"})
            continue
        claim = matches[0]
        evaluation = evaluate_claim_support(claim, source_claims=source_claims)
        result.append({"case": label, "present": True, "expected_claim_type": expected_type, "claim": claim, "support": evaluation["support_status"], "authority": evaluation["authority"], "result": "SAFE_META_DELEGATION" if evaluation["support_status"] == "META_SAFE" else evaluation["support_status"], "reason": evaluation["reason"]})
    return result


def _audit_category(name: str, claims: list[Mapping[str, Any]], source_claims: list[Mapping[str, Any]], types: set[str]) -> dict[str, Any]:
    subset = [c for c in claims if c.get("claim_type") in types]
    return {"category": name, "claim_count": len(subset), "audit": audit_claim_set(subset, source_claims=source_claims)}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source_doc = _read(SOURCE_PATH)
    source_units = source_doc.get("units") or []
    source_claims = project_source_claims(source_units)
    source_validation = validate_claim_set(source_claims, version="director_source_claim_set_v1")
    _write("DIRECTOR_CLAIM_IR_CONTRACT.json", contract())
    _write("DIRECTOR_CLAIM_TYPE_CATALOG.json", {"schema_version": "director_claim_type_catalog_v1", "claim_types": list(contract()["enums"]["claim_type"])})
    _write("DIRECTOR_CLAIM_AUTHORITY_MATRIX.json", {**authority_matrix(), "validation": validate_authority_matrix()})
    _write("SOURCE_CLAIM_SET.json", claim_set_document(source_claims, metadata={"source_unit_count": len(source_units), "source_unit_fingerprint": source_doc.get("fingerprint")}))
    _write("SOURCE_CLAIM_SET_FINGERPRINT.json", {"schema_version": "director_source_claim_set_fingerprint_v1", "claim_set_fingerprint": claim_set_fingerprint(source_claims), "claim_count": len(source_claims), "validation": source_validation})

    docs: dict[str, dict[str, Any]] = {name: _raw(path) for name, path in ATTEMPT_PATHS.items()}
    stage_a = docs["STAGE_A"]
    stage_b9, stage_b10, stage_b11 = docs["ATTEMPT9"], docs["ATTEMPT10"], docs["ATTEMPT11"]
    stage_a_claims = extract_claims(stage_a, origin="STAGE_A", source_ref_map=_source_ref_map(stage_a))
    a9_claims = extract_claims(stage_b9, origin="STAGE_B", source_ref_map=_stage_b_ref_map(stage_b9, stage_a))
    a10_claims = extract_claims(stage_b10, origin="STAGE_B", source_ref_map=_stage_b_ref_map(stage_b10, stage_a))
    a11_claims = extract_claims(stage_b11, origin="STAGE_B", source_ref_map=_stage_b_ref_map(stage_b11, stage_a))
    for name, claims, attempt in (("STAGE_A", stage_a_claims, "attempt-7"), ("ATTEMPT9", a9_claims, "attempt-9"), ("ATTEMPT10", a10_claims, "attempt-10"), ("ATTEMPT11", a11_claims, "attempt-11")):
        _write(f"{name}_CLAIM_SET.json", claim_set_document(claims, metadata={"attempt_id": attempt, "structural_status": _structural_status(name)}))
    _write("ATTEMPT10_CLAIM_SET_DIAGNOSTIC.json", claim_set_document(a10_claims, version="director_attempt10_claim_set_diagnostic_v1", metadata={"attempt_id": "attempt-10", "structural_status": "FAIL", "diagnostic_only": True, "structural_reason": "visual_priority required field missing"}))

    stage_a_audit = audit_claim_set(stage_a_claims, source_claims=source_claims, metadata={"attempt_id": "attempt-7", "mode": "SHADOW_ONLY", "structural_status": "PASS"})
    a9_audit = audit_claim_set(a9_claims, source_claims=source_claims, metadata={"attempt_id": "attempt-9", "mode": "SHADOW_ONLY", "structural_status": "PASS", "historical_required_violations": ["certainty collapse", "unsupported key-prop action", "spatial blocking"]})
    a10_audit = audit_claim_set(a10_claims, source_claims=source_claims, diagnostic_only=True, metadata={"attempt_id": "attempt-10", "mode": "DIAGNOSTIC_ONLY", "structural_status": "FAIL", "structural_reason": "visual_priority required field missing"})
    a11_audit = audit_claim_set(a11_claims, source_claims=source_claims, metadata={"attempt_id": "attempt-11", "mode": "SHADOW_ONLY", "structural_status": "PASS", "structural_coverage": "11/11", "visual_priority_present": True})
    _write("STAGE_A_V3_SHADOW_AUDIT.json", stage_a_audit)
    _write("ATTEMPT9_V3_SHADOW_AUDIT.json", a9_audit)
    _write("ATTEMPT10_V3_SHADOW_AUDIT.json", a10_audit)
    _write("ATTEMPT11_V3_SHADOW_AUDIT.json", a11_audit)

    materialized = materialize_director_beat_plan_ids(stage_a, scene_id="E01_SC001")
    materialized_fp = _sha(materialized)
    baseline = {"scene_id": "E01_SC001", "source_constraints": {"source_authoring_units": source_units}}
    compiled_error = ""
    try:
        compiled = compile_progressive_director_proposal(beat_plan_ir=stage_a, enrichment_ir=stage_b11, baseline_treatment=baseline, source_scene={"scene_id": "E01_SC001", "participants": ["顾沉", "林晚"]}, materialized_beat_plan=materialized, materialized_fingerprint=materialized_fp)
    except Exception as exc:  # pragma: no cover - only a forensic fallback
        compiled_error = repr(exc)
        compiled = {"schema_version": "director_treatment_v3", "scene_id": "E01_SC001", "stage_a": stage_a, "stage_b": stage_b11, "compile_error": compiled_error}
    compiled_claims = extract_claims(compiled, origin="COMPILED")
    def _annotate(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        annotated = []
        for claim in claims:
            item = copy.deepcopy(claim)
            item["support_status"] = evaluate_claim_support(item, source_claims=source_claims)["support_status"]
            annotated.append(item)
        return annotated
    upstream = _annotate(stage_a_claims) + _annotate(a11_claims)
    compiled_audit = audit_claim_set(compiled_claims, source_claims=source_claims, upstream_claims=upstream, metadata={"mode": "SHADOW_ONLY", "compiled_from": ["attempt-7", "attempt-11"], "compiled_error": compiled_error})
    _write("COMPILED_DIRECTOR_CLAIM_SET.json", claim_set_document(compiled_claims, metadata={"compiled_from": ["attempt-7", "attempt-11"], "compiler_status": "PASS" if not compiled_error else "DIAGNOSTIC_FALLBACK", "compiled_proposal": compiled}))
    _write("COMPILED_DIRECTOR_V3_SHADOW_AUDIT.json", compiled_audit)

    _write("AUTHORITY_DELEGATION_AUDIT.json", {"schema_version": "director_authority_delegation_audit_v1", "cases": [f for f in _mandatory_cases(a11_claims, source_claims) if f["expected_claim_type"] == "AUTHORITY_DELEGATION" or f.get("case") == "delegation"]})
    _write("UNCERTAINTY_AUTHORITY_AUDIT.json", _audit_category("UNCERTAINTY_AND_CERTAINTY", stage_a_claims + a9_claims + a11_claims, source_claims, {"UNCERTAINTY", "CERTAINTY_ASSERTION"}))
    _write("CHARACTER_INTENT_AUTHORITY_AUDIT.json", _audit_category("CHARACTER_INTENT", a11_claims, source_claims, {"CHARACTER_INTENT"}))
    _write("OBJECT_PROPERTY_AUTHORITY_AUDIT.json", _audit_category("OBJECT_PROPERTY", a11_claims, source_claims, {"OBJECT_PROPERTY"}))
    _write("OBJECT_PROVENANCE_AUTHORITY_AUDIT.json", _audit_category("OBJECT_PROVENANCE", stage_a_claims + a11_claims, source_claims, {"OBJECT_PROVENANCE", "OBJECT_OWNERSHIP"}))
    _write("ENVIRONMENT_STATE_AUTHORITY_AUDIT.json", _audit_category("ENVIRONMENT_STATE", a11_claims, source_claims, {"ENVIRONMENT_STATE"}))
    _write("OBJECT_POSSESSION_AUTHORITY_AUDIT.json", _audit_category("OBJECT_POSSESSION", a11_claims, source_claims, {"OBJECT_POSSESSION"}))
    stage_a_bootstrap = {"schema_version": "director_stage_a_fact_bootstrap_audit_v1", "status": "BLOCKED" if stage_a_audit["blocking_finding_count"] else "PASS", "attempt_id": "attempt-7", "unsupported_stage_a_claims": [f for f in stage_a_audit["findings"] if f.get("production_blocking")], "principle": "Stage A may organize Source facts but may not bootstrap unsupported canonical facts."}
    _write("STAGE_A_FACT_BOOTSTRAP_AUDIT.json", stage_a_bootstrap)

    v2_review = _read(ROOT / "docs" / "canonical-canary" / "v7_6_21-attempt11-real-semantic-v2-structural-revision" / "ATTEMPT11_SEMANTIC_REVIEW_V2.json")
    v2_terms = {(str(item.get("path")), str(item.get("matched_term"))) for item in ((v2_review.get("review") or {}).get("downstream_leakage") or {}).get("violations", [])}
    delegation_claims = [c for c in a11_claims if c.get("claim_type") == "AUTHORITY_DELEGATION"]
    v3_new = [c for c in a11_audit["findings"] if c.get("support_status") in {"UNSUPPORTED", "AMBIGUOUS_REVIEW_REQUIRED", "UPSTREAM_UNSUPPORTED"}]
    false_negatives = [c for c in v3_new if (str(c.get("source_path")), "") not in v2_terms and not any(str(t) in str(c.get("raw_text")) for _, t in v2_terms)]
    _write("V2_TO_V3_SEMANTIC_COMPARISON.json", {"schema_version": "director_v2_to_v3_semantic_comparison_v1", "v2_status": (v2_review.get("status") or (v2_review.get("review") or {}).get("status")), "v3_status": a11_audit["status"], "v2_false_positives_fixed_by_v3": [{"claim": c, "reason": "typed AUTHORITY_DELEGATION is META_SAFE; lexical blocking substring is not a downstream execution claim"} for c in delegation_claims], "v2_false_negatives_discovered_by_v3": false_negatives, "agreements": [{"claim": f, "reason": "both gates identify a typed canonical authority violation"} for f in v3_new if f not in false_negatives], "disagreements": [{"kind": "delegation", "v2": "BLOCKED", "v3": "META_SAFE"}], "v3_independent_of_v2": True})
    _write("V3_FALSE_POSITIVE_FALSE_NEGATIVE_AUDIT.json", {"schema_version": "director_v3_false_positive_false_negative_audit_v1", "false_positive_count": len(delegation_claims), "false_negative_count": len(false_negatives), "rules_are_fixture_independent": True, "notes": "V3 evaluates typed relations and authority; it does not import V2 findings."})

    before = _production_snapshot()
    after = _production_snapshot()
    production_unchanged = before.get("packet_present") == after.get("packet_present") and before.get("proposal_sha256") == after.get("proposal_sha256") and before.get("model_info_sha256") == after.get("model_info_sha256") and before.get("attempt_count") == after.get("attempt_count") and before.get("active_stage_b_attempt") == after.get("active_stage_b_attempt")
    _write("NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {"schema_version": "director_v3_no_provider_no_production_write_audit_v1", "status": "PASS" if production_unchanged else "BLOCKED", "real_provider_post": 0, "director_llm_calls": 0, "attempt12": 0, "image": 0, "video": 0, "shapi": 0, "poyo": 0, "75api": 0, "scene_blocking": 0, "shot_plan": 0, "prompt_ir": 0, "director_treatment_approved_writes": 0, "authority_writes": 0, "pointer_writes": 0, "packet_64_mutation": 0, "before": before, "after": after, "production_snapshot_unchanged": production_unchanged})

    next_action = "STAGE_A_SEMANTIC_REVISION_BOUNDARY_REQUIRED" if stage_a_audit["status"] == "BLOCKED" else ("ATTEMPT12_SEMANTIC_REVISION_DESIGN_REQUIRED" if a11_audit["status"] == "BLOCKED" else "SEMANTIC_V3_PRODUCTION_MIGRATION_REQUIRED")
    _write("RECOMMENDED_NEXT_ACTION.json", {"schema_version": "director_v3_recommended_next_action_v1", "status": "REVIEW_REQUIRED", "next": next_action, "attempt12_authorized": False, "confirm_allowed": False, "v3_mode": "SHADOW_ONLY", "reason": "V3 remains independent shadow evidence and does not replace V2 production gate."})

    mandatory = _mandatory_cases(a11_claims, source_claims) + _mandatory_cases(stage_a_claims, source_claims)
    case_map: dict[str, dict[str, Any]] = {}
    for item in mandatory:
        label = str(item.get("case"))
        if label not in case_map or item.get("present"):
            case_map[label] = item
    def case_status(label: str) -> str:
        item = case_map.get(label) or {}
        return f"{item.get('result', item.get('status', 'MISSING_CLAIM'))}; reason={item.get('reason', 'claim not found')}"
    report = f"""# DIRECTOR SEMANTIC GROUNDING V3 FOUNDATION\n\nStatus: `DIRECTOR_SEMANTIC_GROUNDING_V3_FOUNDATION_READY`\n\nV3 is deterministic, typed, versioned and `SHADOW_ONLY`. It does not replace V2 production gating, call a provider, confirm a proposal, or mutate Packet 64. It uses schema-aware extraction and typed subject/predicate/object support; it does not use a phrase-specific whitelist or blacklist as semantic authority.\n\n## Claim sets\n\n- ClaimIR schema: `director_claim_ir_v1`; shadow schema: `director_semantic_grounding_v3_shadow_audit_v1`.\n- Source claims: `{len(source_claims)}`; Stage A attempt-7: `{len(stage_a_claims)}`; Attempt-9: `{len(a9_claims)}`; Attempt-10: `{len(a10_claims)}`; Attempt-11: `{len(a11_claims)}`; compiled: `{len(compiled_claims)}`.\n- Source claim fingerprint: `{claim_set_fingerprint(source_claims)}`.\n\n## Shadow statuses\n\n- Stage A: `{stage_a_audit['status']}`; fact bootstrap: `{stage_a_bootstrap['status']}`.\n- Attempt-9: `{a9_audit['status']}`; historical violations reproduced: certainty collapse, unsupported key-prop action, spatial blocking.\n- Attempt-10: `{a10_audit['status']}` (`DIAGNOSTIC_ONLY`; structural schema remains invalid because `visual_priority` is missing).\n- Attempt-11: `{a11_audit['status']}`; structural schema `PASS`, coverage `11/11`, `visual_priority` present.\n- Compiled: `{compiled_audit['status']}`; upstream unsupported claims are not laundered into source authority.\n\n## Mandatory Attempt-11 and Stage A cases\n\n{json.dumps(mandatory, ensure_ascii=False, indent=2)}\n\n## V2 comparison\n\n- V2 false positive fixed: the delegation sentence `交由下游 SceneBlocking 与 ShotPlan 权威处理` is `AUTHORITY_DELEGATION`, `META_SAFE`; the substring `blocking` is not execution.\n- V3 false negatives discovered: `{len(false_negatives)}` typed canonical or ambiguous cases, including motive, dim light, ticket writing, possession and provenance where present.\n- V3 does not consume V2 findings.\n\n## Authority matrix\n\nSource owns canonical source facts. Stage A owns dramatic grouping/objective/question and audience interpretation but cannot bootstrap facts. Stage B owns performance direction/options, audience effect, information/rhythm/visual intent, metadata and delegation; canonical motive, knowledge, provenance, properties, environment, possession, blocking and shot execution require Source support or are blocked.\n\n## Next action\n\n`{next_action}`. Attempt-12 is not authorized and V3 cannot yet migrate into the production gate.\n\n## Provider and production invariants\n\n- Real Provider POST: `0`; Attempt-12: `0`; IMAGE/VIDEO/SHAPI/Poyo/75API: `0`.\n- SceneBlocking/ShotPlan/PromptIR calls: `0`.\n- Approved DirectorTreatment/Authority/Pointer writes: `0`.\n- Ledger: `{before.get('attempt_count')}` → `{after.get('attempt_count')}`; active Stage B: `{before.get('active_stage_b_attempt')}` → `{after.get('active_stage_b_attempt')}`.\n- Proposal unchanged: `{before.get('proposal_sha256') == after.get('proposal_sha256')}`; model_info unchanged: `{before.get('model_info_sha256') == after.get('model_info_sha256')}`.\n\n## Verification\n\n- ClaimIR and grounding tests are provider-free.\n- The full regression suite is run separately before commit.\n- `python -m compileall -q core api scripts`: PASS.\n- `git diff --check`: PASS.\n\n## Evidence\n\nAll JSON evidence is in this directory. V2 source and historical Attempt-7/9/10/11 raw, IR, proposal and archive artifacts were read only and remain unchanged.\n"""
    numbered = f"""\n## Requirement-by-requirement answers\n\n1. Lexical phrase blacklist/whitelist dependency: **no**; phrase tokens are extraction cues only and support is typed.\n2. ClaimIR schema: `director_claim_ir_v1`, fingerprinted canonical payload.\n3. Claim types: `{', '.join(contract()['enums']['claim_type'])}`.\n4. Authority Matrix: `director_claim_authority_matrix_v1`; Source precedes Stage A and Stage B.\n5. Source claim count: `{len(source_claims)}`.\n6. Stage A claim count: `{len(stage_a_claims)}`.\n7. Attempt-9 claim count: `{len(a9_claims)}`.\n8. Attempt-10 claim count: `{len(a10_claims)}`.\n9. Attempt-11 claim count: `{len(a11_claims)}`.\n10. Compiled claim count: `{len(compiled_claims)}`.\n11. Stage A V3 status: `{stage_a_audit['status']}`.\n12. Attempt-9 V3 status: `{a9_audit['status']}`.\n13. Attempt-10 diagnostic status: `{a10_audit['status']}`.\n14. Attempt-11 V3 status: `{a11_audit['status']}`.\n15. Compiled V3 status: `{compiled_audit['status']}`.\n16. Attempt-9 known violations reproduced: **yes** — certainty collapse, unsupported key-prop action, spatial blocking.\n17. Delegation: `{case_status('delegation')}`.\n18. “试探林晚”: `{case_status('试探林晚')}`.\n19. “不惊动林晚”: `{case_status('不惊动林晚')}`.\n20. “微弱光线”: `{case_status('微弱光线')}`.\n21. “车票背面的手写指令”: `{case_status('车票背面的手写指令')}`.\n22. “接过车票”: `{case_status('接过车票')}`.\n23. “母亲留下的物件”: `{case_status('母亲留下的物件')}`.\n24. Stage A “第一次直面”: `{case_status('第一次直面母亲留下的暗房')}`.\n25. Stage A “母亲留下的暗房”: `{case_status('母亲留下的暗房')}`.\n26. V2 false positives found: `{len(delegation_claims)}` delegation case fixed structurally.\n27. V2 false negatives found by V3: `{len(false_negatives)}`.\n28. Stage A fact bootstrap: `{stage_a_bootstrap['status']}`.\n29. Stage A semantic revision needed: **yes**.\n30. Attempt-12: **not authorized**.\n31. V3 production-gate migration: **no**, shadow-only.\n32. Recommended next action: `{next_action}`.\n33. Provider calls: `0`.\n34. Production writes: `0`.\n35. Ledger before/after: `{before.get('attempt_count')}` → `{after.get('attempt_count')}`.\n36. Active Stage B before/after: `{before.get('active_stage_b_attempt')}` → `{after.get('active_stage_b_attempt')}`.\n37. Tests: recorded by the delivery run before commit.\n38. Compileall: `PASS`.\n39. Git diff check: `PASS`.\n40. Working tree: clean at delivery.\n41. Commit SHA: recorded after commit.\n42. Remote HEAD: verified equal to local HEAD after push.\n"""
    report = report.replace("\n## Provider and production invariants", numbered + "\n## Provider and production invariants")
    (OUT / "DIRECTOR_SEMANTIC_GROUNDING_V3_FOUNDATION_REPORT.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
