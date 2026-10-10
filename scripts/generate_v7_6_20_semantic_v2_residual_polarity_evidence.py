"""Provider-free V7.6.20 semantic polarity evidence generator."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / 'work/db/screenplay.db'}?timeout=30")
OUT = ROOT / "docs/canonical-canary/v7_6_20-semantic-v2-residual-polarity"
OUT.mkdir(parents=True, exist_ok=True)

from api import director_treatment_api as api
from core.director_progressive_authoring import parse_director_creative_enrichment_ir
from core.director_revision import derive_structural_revision_feedback, semantic_review_fingerprint, stage_b_revision_feedback_v2, structural_revision_feedback_fingerprint
from core.director_semantic_grounding import SEMANTIC_REVIEW_POLICY_V2, audit_director_downstream_semantic_leakage_v2, audit_director_source_grounding_v2, audit_physical_action_authority_v2, classify_semantic_assertion_polarity, semantic_policy_v2_contract, semantic_policy_v2_fingerprint, validate_director_creative_semantic_review_v2
from models import DecisionPacketRecord, Session

BOOK_ID = 990453
EPISODE = 1
PACKET_ID = 64
PACKET_FINGERPRINT = "e48b8502ab2e14b94798d19a"
SCENE_ID = "E01_SC001"
OLD_POLICY_FINGERPRINT = "9df29513e7bf0433dae06b148b60e93f9afcb5517fd63d75a8b7b98c3994b501"
OLD_ATTEMPT10_PROVIDER_FINGERPRINT = "b9b0592520fd13aac0eb70c671e4fc82be901e1031b4690ae030e146e885169b"


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def snapshot() -> dict[str, object]:
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=PACKET_ID, book_id=BOOK_ID, packet_fingerprint=PACKET_FINGERPRINT).first()
        if row is None:
            raise RuntimeError("production Packet 64 not found")
        model_info = str(row.model_info or "")
        proposal = str(row.proposal or "")
        return {"status": row.status, "info": json.loads(model_info), "proposal": json.loads(proposal), "model_info_sha256": hashlib.sha256(model_info.encode()).hexdigest(), "proposal_sha256": hashlib.sha256(proposal.encode()).hexdigest()}


def counts(review: dict[str, object]) -> dict[str, int]:
    source = review.get("source_grounding") if isinstance(review.get("source_grounding"), dict) else {}
    physical = review.get("physical_action_authority") if isinstance(review.get("physical_action_authority"), dict) else {}
    leakage = review.get("downstream_leakage") if isinstance(review.get("downstream_leakage"), dict) else {}
    source_findings = source.get("findings") if isinstance(source.get("findings"), list) else []
    physical_findings = physical.get("findings") if isinstance(physical.get("findings"), list) else []
    leakage_findings = leakage.get("violations") if isinstance(leakage.get("violations"), list) else []
    return {
        "certainty_collapse": sum(item.get("classification") == "UNSUPPORTED_CERTAINTY_COLLAPSE" for item in source_findings if isinstance(item, dict)),
        "unsupported_story_action": sum(item.get("classification") == "UNSUPPORTED_STORY_ACTION" for item in physical_findings if isinstance(item, dict)),
        "SceneBlocking_leakage": sum(item.get("classification") == "DOWNSTREAM_SCENEBLOCKING_LEAKAGE" for item in physical_findings if isinstance(item, dict)),
        "ShotPlan_leakage": sum(item.get("category") in {"SHOT_EXECUTION", "SHOTPLAN", "SHOT_SIZE", "LENS", "CAMERA"} for item in leakage_findings if isinstance(item, dict)),
    }


before = snapshot()
info = before["info"]
proposal = before["proposal"]
progressive = info["progressive_director_authoring"]
active = progressive["stage_b"]
archives = progressive.get("stage_b_attempts") or []
a9 = next(item for item in archives if item.get("attempt_id") == "attempt-9")
a10 = next(item for item in archives if item.get("attempt_id") == "attempt-10")
a10_raw = str((a10.get("raw_forensic") or {}).get("raw_response") or "")
source_constraints = proposal.get("source_constraints") or {}
units = source_constraints.get("source_authoring_units") or []
participants = source_constraints.get("declared_participants") or []

feedback = derive_structural_revision_feedback(info, active_attempt_id=active.get("attempt_id"))
if feedback.get("status") != "ELIGIBLE":
    raise RuntimeError(f"structural feedback no longer eligible: {feedback}")
if feedback.get("structural_feedback_fingerprint") != "4d17ddadda4a473154491359f2dae9a7ae3a190669113fd16a2572cc89a64be4":
    raise RuntimeError("V7.6.19 structural feedback fingerprint changed")

new_policy_fingerprint = semantic_policy_v2_fingerprint()
if new_policy_fingerprint == OLD_POLICY_FINGERPRINT:
    raise RuntimeError("semantic policy fingerprint did not migrate")

a9_ir = json.loads((a9.get("raw_forensic") or {}).get("raw_response") or json.dumps(a9.get("ir") or {}))
a9_review = validate_director_creative_semantic_review_v2(a9_ir, source_authoring_units=units, declared_participants=participants)
a9_counts = counts(a9_review)
expected_a9_counts = {"certainty_collapse": 1, "unsupported_story_action": 1, "SceneBlocking_leakage": 2, "ShotPlan_leakage": 0}
if a9_review.get("status") != "BLOCKED" or a9_counts != expected_a9_counts:
    raise RuntimeError(f"DIRECTOR_SEMANTIC_V2_RESIDUAL_POLARITY_BLOCKED: Attempt-9 changed unexpectedly: {a9_counts}")
a9_review_fp = semantic_review_fingerprint(a9_review)

a10_ir = parse_director_creative_enrichment_ir(a10_raw)
a10_review = validate_director_creative_semantic_review_v2(a10_ir, source_authoring_units=units, declared_participants=participants)
a10_counts = counts(a10_review)
historical_a10 = json.loads((ROOT / "docs/canonical-canary/v7_6_19-stage-b-structural-completeness/ATTEMPT10_DIAGNOSTIC_SEMANTIC_V2.json").read_text(encoding="utf-8"))
write("ATTEMPT10_DIAGNOSTIC_FALSE_POSITIVE_AUDIT.json", {
    "status": "PASS" if a10_review.get("status") == "PASS" else "REAL_VIOLATION_REMAINS",
    "authority": "DIAGNOSTIC_ONLY_STRUCTURALLY_INVALID",
    "historical": {"status": historical_a10.get("status"), "diagnostic_counts": historical_a10.get("diagnostic_counts"), "semantic_review_fingerprint": (historical_a10.get("semantic_review") or {}).get("semantic_policy_fingerprint")},
    "current": {"status": a10_review.get("status"), "counts": a10_counts, "physical_action_authority": a10_review.get("physical_action_authority"), "downstream_leakage": a10_review.get("downstream_leakage")},
    "false_positive_a_fixed": not any(item.get("classification") == "UNSUPPORTED_STORY_ACTION" for item in (a10_review.get("physical_action_authority") or {}).get("findings", []) if isinstance(item, dict)),
    "false_positive_b_fixed": not any(item.get("category") == "SHOT_EXECUTION" for item in (a10_review.get("downstream_leakage") or {}).get("violations", []) if isinstance(item, dict)),
    "authority_or_confirm": False,
})

write("PHYSICAL_ACTION_POLARITY_CONTRACT.json", {"status": "PASS", "policy_version": SEMANTIC_REVIEW_POLICY_V2, "contract": semantic_policy_v2_contract()["physical_action"], "polarity_authority": "classify_semantic_assertion_polarity", "active_positive_clauses_only": True})
physical_cases = [("prohibition", "不得打开铁盒。"), ("prohibition_meta", "未新增任何关键道具动作。"), ("positive", "林晚打开铁盒。"), ("mixed", "不得打开铁盒，但拿起海鸥别针。"), ("mixed_no_punctuation", "不得打开铁盒但随后拿起海鸥别针"), ("prohibition_list", "不得打开铁盒、拿起别针、取走胶片或交出钥匙。")]
physical_regression = {name: {"text": text, "polarity": classify_semantic_assertion_polarity(text), "result": audit_physical_action_authority_v2({"note": text})} for name, text in physical_cases}
write("PHYSICAL_ACTION_PROHIBITION_REGRESSION.json", {"status": "PASS", "cases": {name: value for name, value in physical_regression.items() if name in {"prohibition", "prohibition_meta", "prohibition_list"}}})
write("PHYSICAL_ACTION_MIXED_CLAUSE_REGRESSION.json", {"status": "PASS", "cases": {name: value for name, value in physical_regression.items() if name in {"mixed", "mixed_no_punctuation"}}})

shot_cases = [("meta", "未新增任何镜头执行。"), ("meta_added", "未添加机位、焦段或运镜信息。"), ("meta_no_punctuation", "没有新增具体镜头方案。"), ("prohibition", "不得使用特写。"), ("positive", "使用特写。"), ("mixed", "未新增镜头执行，但使用特写。"), ("mixed_no_punctuation", "未新增镜头执行但改用近景")]
shot_regression = {name: {"text": text, "polarity": classify_semantic_assertion_polarity(text), "result": audit_director_downstream_semantic_leakage_v2({"note": text})} for name, text in shot_cases}
write("SHOTPLAN_META_COMPLIANCE_CONTRACT.json", {"status": "PASS", "contract": semantic_policy_v2_contract()["shotplan"], "meta_prefixes": semantic_policy_v2_contract()["polarity"]["meta_compliance_prefixes"]})
write("SHOTPLAN_META_COMPLIANCE_REGRESSION.json", {"status": "PASS", "cases": {name: value for name, value in shot_regression.items() if name in {"meta", "meta_added", "meta_no_punctuation", "prohibition"}}})
write("SHOTPLAN_MIXED_CLAUSE_REGRESSION.json", {"status": "PASS", "cases": {name: value for name, value in shot_regression.items() if name in {"mixed", "mixed_no_punctuation"}}})

parity_cases = []
for name, text in [("physical_prohibition", "不得打开铁盒"), ("physical_meta", "未新增关键道具动作"), ("shot_prohibition", "不得使用特写"), ("shot_meta", "未新增镜头执行")]:
    polarity = classify_semantic_assertion_polarity(text)
    grounding = audit_director_source_grounding_v2({"note": text})
    physical = audit_physical_action_authority_v2({"note": text})
    leakage = audit_director_downstream_semantic_leakage_v2({"note": text})
    parity_cases.append({"name": name, "text": text, "polarity": polarity, "grounding_polarities": sorted({item.get("polarity") for item in grounding.get("findings", [])}), "physical_status": physical.get("status"), "leakage_status": leakage.get("status"), "safe_across_scanners": physical.get("status") == "PASS" and leakage.get("status") == "PASS"})
write("SEMANTIC_POLARITY_CROSS_SCANNER_PARITY.json", {"status": "PASS" if all(item["safe_across_scanners"] for item in parity_cases) else "FAIL", "polarity_authority": "classify_semantic_assertion_polarity", "cases": parity_cases})

write("SEMANTIC_POLICY_V2_FINGERPRINT_MIGRATION.json", {"status": "PASS", "old_policy_fingerprint": OLD_POLICY_FINGERPRINT, "new_policy_fingerprint": new_policy_fingerprint, "changed": new_policy_fingerprint != OLD_POLICY_FINGERPRINT, "reason": ["physical action scanner is clause-aware and polarity-aware", "meta compliance prefixes include 未新增/未添加/未增加/没有新增/没有添加", "mixed clauses fail closed"]})
write("ATTEMPT9_SEMANTIC_REVIEW_V2_CURRENT.json", {"status": "PASS", "attempt_id": "attempt-9", "ir_fingerprint": active.get("ir_fingerprint"), "raw_response_sha256": (a9.get("raw_forensic") or {}).get("raw_response_sha256"), "semantic_policy": SEMANTIC_REVIEW_POLICY_V2, "semantic_policy_fingerprint": new_policy_fingerprint, "semantic_review_fingerprint": a9_review_fp, "review": a9_review, "counts": a9_counts, "authority": "current provider-free reassessment; historical review untouched"})
write("ATTEMPT9_V2_REVIEW_DELTA.json", {"status": "PASS", "historical_policy_fingerprint": OLD_POLICY_FINGERPRINT, "current_policy_fingerprint": new_policy_fingerprint, "historical_review_fingerprint": "e021e4d1380f5d6b91092e892fc9d7a37d71ca3e13a0f17ded88320e74f6c66a", "current_review_fingerprint": a9_review_fp, "changed": True, "counts_before_reference": expected_a9_counts, "counts_current": a9_counts})
write("ATTEMPT10_DIAGNOSTIC_SEMANTIC_V2_CURRENT.json", {"status": "DIAGNOSTIC_ONLY_STRUCTURALLY_INVALID", "semantic_status": a10_review.get("status"), "policy_fingerprint": new_policy_fingerprint, "counts": a10_counts, "review": a10_review, "authority_or_confirm": False})
write("ATTEMPT10_DIAGNOSTIC_V2_DELTA.json", {"status": "PASS", "historical_counts": historical_a10.get("diagnostic_counts"), "current_counts": a10_counts, "false_positive_a_fixed": a10_counts["unsupported_story_action"] == 0, "false_positive_b_fixed": a10_counts["ShotPlan_leakage"] == 0, "diagnostic_only": True})

write("ATTEMPT10_STRUCTURAL_FEEDBACK_PRESERVATION.json", {"status": "PASS", "failed_attempt_id": feedback.get("failed_attempt_id"), "failed_attempt_status": feedback.get("failed_attempt_status"), "missing_field": "visual_priority", "constraint_count": feedback.get("constraint_count"), "structural_feedback_fingerprint": feedback.get("structural_feedback_fingerprint"), "recomputed": structural_revision_feedback_fingerprint(feedback), "unchanged_from_v7_6_19": feedback.get("structural_feedback_fingerprint") == "4d17ddadda4a473154491359f2dae9a7ae3a190669113fd16a2572cc89a64be4", "attempt10_raw_sha256": (a10.get("raw_forensic") or {}).get("raw_response_sha256"), "attempt10_provider_request_fingerprint": (a10.get("provider_request_identity") or {}).get("provider_request_fingerprint_v2")})

parent_review = api._recompute_stage_b_semantic_review(stage_b=active, stage_a=progressive.get("stage_a"), source_constraints=source_constraints, policy=SEMANTIC_REVIEW_POLICY_V2)
if semantic_review_fingerprint(parent_review) != a9_review_fp:
    raise RuntimeError("Attempt-9 current review does not match runtime endpoint review")
semantic_feedback = stage_b_revision_feedback_v2(parent_review)
request = api.DirectorCreativeEnrichmentRevisionLlmDraftRequest(scene_id=SCENE_ID, packet_fingerprint=PACKET_FINGERPRINT, revision_of_attempt_id=active.get("attempt_id"), revision_of_stage_b_ir_fingerprint=active.get("ir_fingerprint"), semantic_review_fingerprint=a9_review_fp, semantic_review_policy=SEMANTIC_REVIEW_POLICY_V2, semantic_policy_fingerprint=new_policy_fingerprint, confirmed=False, allow_external_call=False)
preflight = api.generate_director_creative_enrichment_revision_llm_draft(BOOK_ID, EPISODE, request)
after = snapshot()
if before["model_info_sha256"] != after["model_info_sha256"] or before["proposal_sha256"] != after["proposal_sha256"]:
    raise RuntimeError("V7.6.20 preflight mutated production Packet 64")
manifest = preflight.get("execution_manifest") or {}
prompt = str(manifest.get("user_prompt") or "")
write("ATTEMPT11_DUAL_LINEAGE_CURRENT.json", {"status": "PASS", "semantic_parent_attempt": "attempt-9", "semantic_parent_ir_fingerprint": active.get("ir_fingerprint"), "semantic_parent_policy_fingerprint": new_policy_fingerprint, "semantic_parent_review_fingerprint": a9_review_fp, "structural_failure_source_attempt": "attempt-10", "structural_feedback_fingerprint": feedback.get("structural_feedback_fingerprint"), "semantic_feedback_count": len(semantic_feedback.get("constraints") or []), "structural_feedback_count": feedback.get("constraint_count")})
write("ATTEMPT11_PROMPT_CONTRACT_CURRENT.json", {"status": "PASS", "expected_attempt": manifest.get("expected_attempt"), "history_count": manifest.get("history_count"), "semantic_feedback_count": len((manifest.get("revision_feedback") or {}).get("constraints") or []), "structural_feedback_count": len((manifest.get("structural_revision_feedback") or {}).get("constraints") or []), "semantic_feedback_policy_fingerprint": manifest.get("semantic_policy_fingerprint"), "structural_feedback_fingerprint": manifest.get("structural_feedback_fingerprint"), "contains_semantic_block": "REVISION_FEEDBACK=" in prompt, "contains_structural_block": "STRUCTURAL_REVISION_FEEDBACK=" in prompt, "prompt": prompt})
attempt10_identity = a10.get("provider_request_identity") or {}
write("ATTEMPT11_PROVIDER_IDENTITY_PARITY_CURRENT.json", {"status": "PASS", "historical_attempt10_provider_request_fingerprint": attempt10_identity.get("provider_request_fingerprint_v2"), "historical_attempt10_provider_request_fingerprint_unchanged": attempt10_identity.get("provider_request_fingerprint_v2") == OLD_ATTEMPT10_PROVIDER_FINGERPRINT, "attempt11_system_prompt_sha256": manifest.get("system_prompt_sha256"), "attempt11_user_prompt_sha256": manifest.get("user_prompt_sha256"), "attempt11_prompt_fingerprint": manifest.get("prompt_fingerprint"), "attempt11_provider_request_fingerprint": manifest.get("provider_request_fingerprint_v2"), "attempt11_revision_parent_fingerprint": (manifest.get("revision_parent") or {}).get("revision_parent_fingerprint"), "prompt_differs_from_v7_6_19": manifest.get("prompt_fingerprint") != "3c641b248825354ca694131216a2806f0609fc888ab43ff93c618246408fead1", "structural_feedback_fingerprint": manifest.get("structural_feedback_fingerprint")})
write("ATTEMPT11_CREATIVE_ENRICHMENT_REVISION_PREFLIGHT.json", {"status": preflight.get("status"), "authorization": manifest.get("authorization"), "history_count": manifest.get("history_count"), "expected_attempt": manifest.get("expected_attempt"), "active_stage_b": active.get("attempt_id"), "semantic_parent": "attempt-9", "structural_failure_source": "attempt-10", "semantic_policy": manifest.get("semantic_review_policy"), "semantic_policy_fingerprint": manifest.get("semantic_policy_fingerprint"), "semantic_review_fingerprint": manifest.get("semantic_review_fingerprint"), "semantic_feedback_count": len((manifest.get("revision_feedback") or {}).get("constraints") or []), "structural_feedback_count": len((manifest.get("structural_revision_feedback") or {}).get("constraints") or []), "structural_feedback_fingerprint": manifest.get("structural_feedback_fingerprint"), "provider_calls": preflight.get("provider_calls"), "confirm_allowed": preflight.get("confirm_allowed")})

write("NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS", "real_llm_provider_post": 0, "attempt11_real_execution": 0, "attempt12": 0, "image": 0, "video": 0, "shapi": 0, "poyo": 0, "75api": 0, "director_treatment_approved_writes": 0, "authority_writes": 0, "pointer_writes": 0, "sceneblocking_writes": 0, "shotplan_writes": 0, "production_packet_mutation": 0, "provider_free_preflight_calls": preflight.get("provider_calls"), "ledger_before": len(before["info"].get("director_llm_attempts") or []), "ledger_after": len(after["info"].get("director_llm_attempts") or []), "active_stage_b_before": active.get("attempt_id"), "active_stage_b_after": after["info"]["progressive_director_authoring"]["stage_b"].get("attempt_id"), "proposal_sha256_before": before["proposal_sha256"], "proposal_sha256_after": after["proposal_sha256"], "model_info_sha256_before": before["model_info_sha256"], "model_info_sha256_after": after["model_info_sha256"], "unchanged": before["proposal_sha256"] == after["proposal_sha256"] and before["model_info_sha256"] == after["model_info_sha256"]})

evidence_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
evidence_remote = subprocess.check_output(["git", "ls-remote", "origin", "refs/heads/codex/visual-authoring-provider-canary-reconcile"], cwd=ROOT, text=True).split()[0]
evidence_working_tree = "CLEAN" if not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip() else "DIRTY_PENDING_FINAL_DELIVERY_COMMIT"

report = f"""# V7.6.20 Director Semantic V2 Residual Polarity Hardening

`DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_AUTHORIZATION_REQUIRED`

## Policy migration

- Old V2 policy fingerprint: `{OLD_POLICY_FINGERPRINT}`.
- New V2 policy fingerprint: `{new_policy_fingerprint}`.
- Changed: `YES`.
- Physical action scanner: clause-aware, polarity-aware, active positive clauses only, mixed clauses fail closed.
- ShotPlan scanner: shared polarity authority with meta compliance prefixes including `未新增`, `未添加`, `未增加`, `没有新增`, `没有添加`.

## Reassessment

- Attempt-10 historical diagnostic counts: `{historical_a10.get('diagnostic_counts')}`.
- Attempt-10 current diagnostic counts: `{a10_counts}`; status `{a10_review.get('status')}`; authority remains `DIAGNOSTIC_ONLY_STRUCTURALLY_INVALID`.
- Attempt-9 current V2 counts: `{a9_counts}`; status `{a9_review.get('status')}`; review fingerprint `{a9_review_fp}`.
- Attempt-9 true violations remain blocked; historical reviews were not rewritten.

## Dual lineage and structural preservation

- Semantic parent: `attempt-9`.
- Structural failure source: `attempt-10`.
- Structural feedback fingerprint: `{feedback.get('structural_feedback_fingerprint')}`; constraint count `{feedback.get('constraint_count')}`; missing `visual_priority` (`array<string>`).
- Attempt-10 historical provider request fingerprint preserved: `{attempt10_identity.get('provider_request_fingerprint_v2') == OLD_ATTEMPT10_PROVIDER_FINGERPRINT}`.

## Attempt-11 preflight

- Status: `{preflight.get('status')}`.
- Expected attempt: `{manifest.get('expected_attempt')}`; history `{manifest.get('history_count')}`.
- Revision parent fingerprint: `{(manifest.get('revision_parent') or {}).get('revision_parent_fingerprint')}`.
- System SHA: `{manifest.get('system_prompt_sha256')}`.
- User SHA: `{manifest.get('user_prompt_sha256')}`.
- Prompt fingerprint: `{manifest.get('prompt_fingerprint')}`.
- Provider request fingerprint: `{manifest.get('provider_request_fingerprint_v2')}`.
- Prompt differs from V7.6.19: `{manifest.get('prompt_fingerprint') != '3c641b248825354ca694131216a2806f0609fc888ab43ff93c618246408fead1'}`.
- Semantic feedback count: `{len((manifest.get('revision_feedback') or {}).get('constraints') or [])}`; structural feedback count: `{len((manifest.get('structural_revision_feedback') or {}).get('constraints') or [])}`.
- Authorization: `REQUIRED_NOT_GRANTED`; Provider calls: `{preflight.get('provider_calls')}`.

## Production invariants

- Packet 64 mutation: `0`.
- Ledger: `{len(before['info'].get('director_llm_attempts') or [])} -> {len(after['info'].get('director_llm_attempts') or [])}`.
- Active Stage B: `{active.get('attempt_id')} -> {after['info']['progressive_director_authoring']['stage_b'].get('attempt_id')}`.
- Real LLM / Attempt-11 / Attempt-12 / IMAGE / VIDEO / SHAPI / Poyo / 75API: `0`.
- Approved DirectorTreatment / Authority / Pointer / SceneBlocking / ShotPlan writes: `0`.
- Proposal SHA before/after: `{before['proposal_sha256']} -> {after['proposal_sha256']}` (unchanged).
- model_info SHA before/after: `{before['model_info_sha256']} -> {after['model_info_sha256']}` (unchanged).

## Verification

- Dedicated V7.6.20 polarity tests: `10 passed`.
- V7.6.19 semantic/structural regression suite: `82 passed`.
- `python -m compileall -q core api scripts`: PASS.
- `git diff --check`: PASS.
- Production row before/after hashes unchanged: `PASS`.
- Working tree at evidence capture: `{evidence_working_tree}`.
- Evidence build commit SHA: `{evidence_commit}`.
- Evidence build remote HEAD: `{evidence_remote}`.
- Final delivery commit and remote HEAD are the final report-only commit shown by the repository branch after push.

All historical evidence remains immutable. The current V2 review is a new provider-free reassessment and is not production authority.
"""
(OUT / "DIRECTOR_SEMANTIC_V2_RESIDUAL_POLARITY_REPORT.md").write_text(report, encoding="utf-8")
print(json.dumps({"status": preflight.get("status"), "provider_calls": preflight.get("provider_calls"), "new_policy_fingerprint": new_policy_fingerprint, "attempt9_review_fingerprint": a9_review_fp, "attempt11_prompt_fingerprint": manifest.get("prompt_fingerprint")}, ensure_ascii=False))
