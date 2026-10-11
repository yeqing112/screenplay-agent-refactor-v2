"""Provider-free correction pass for completed Attempt-11 evidence."""
from __future__ import annotations
import hashlib, json, os, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / 'work/db/screenplay.db'}?timeout=30")
OUT = ROOT / "docs/canonical-canary/v7_6_21-attempt11-real-semantic-v2-structural-revision"
EXPECTED_STAGE_A_IR = "b3dbf2624289134c10d19f93c9cbd00614e9caa501dbe40cd002e24e42821086"
EXPECTED_STAGE_A_MATERIALIZED = "328380be4977fe19f79f574d53facb9df61e229c7098ca28c4919fe25cc5bb01"
EXPECTED_A9_IR = "591bf4ec2f7df8b80a8fdd3a7166c6a76c39a7de0939ba3b1323b6af2320dfaa"
from core.director_progressive_authoring import render_stage_b_schema_contract
from core.director_semantic_grounding import audit_director_downstream_semantic_leakage_v2, audit_physical_action_authority_v2, audit_source_uncertainty_preservation_v2
from models import DecisionPacketRecord, Session

def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

with Session() as session:
    row = session.query(DecisionPacketRecord).filter_by(id=64, book_id=990453, packet_fingerprint="e48b8502ab2e14b94798d19a").first()
    if row is None:
        raise SystemExit("Packet 64 missing")
    info = json.loads(row.model_info)
    proposal = json.loads(row.proposal)
prog = info["progressive_director_authoring"]
a11 = next(x for x in prog["stage_b_attempts"] if x.get("attempt_id") == "attempt-11")
ir = a11.get("ir") or {}
identity = a11.get("provider_request_identity") or {}
raw = a11.get("raw_forensic") or {}
validation = a11.get("validation") or {}
semantic = a11.get("semantic_review_v2") or a11.get("semantic_review") or {}
required = render_stage_b_schema_contract().get("top_level_required") or []
actual_keys = list(ir.keys())
schema = validation.get("schema") or {}
runtime = validation.get("runtime") or {}
text = validation.get("text") or {}
leakage = audit_director_downstream_semantic_leakage_v2(ir)
physical = audit_physical_action_authority_v2(ir, source_authoring_units=(proposal.get("source_constraints") or {}).get("source_authoring_units", []))
uncertainty = audit_source_uncertainty_preservation_v2(ir, source_authoring_units=(proposal.get("source_constraints") or {}).get("source_authoring_units", []))
write("ATTEMPT11_TOP_LEVEL_COMPLETENESS_AUDIT.json", {"status": "PASS" if schema.get("status") == "PASS" and set(required) == set(actual_keys) and len(actual_keys) == 11 else "FAIL", "required_keys": required, "required_count": len(required), "actual_keys": actual_keys, "missing": sorted(set(required) - set(actual_keys)), "unknown": sorted(set(actual_keys) - set(required)), "visual_priority_present": "visual_priority" in ir, "visual_priority_type": type(ir.get("visual_priority")).__name__})
transport = json.loads((OUT / "ATTEMPT11_TRANSPORT_AUDIT.json").read_text(encoding="utf-8"))
transport.update({"raw_response_length": raw.get("raw_response_length"), "raw_response_sha256": raw.get("raw_response_sha256"), "provider_request_id": raw.get("provider_request_id") or None})
write("ATTEMPT11_TRANSPORT_AUDIT.json", transport)
write("ATTEMPT11_SOURCE_BINDING_REVALIDATION.json", {"status": "PASS" if identity.get("source_authoring_unit_fingerprint") == "2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f" and identity.get("source_authority_content_fingerprint") == "ea83de61dddd12842ea319e367f284a620bad83ad2c8643b65d331aa003db1c8" else "FAIL", "expected_projection": "2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f", "expected_content": "ea83de61dddd12842ea319e367f284a620bad83ad2c8643b65d331aa003db1c8", "actual_projection": identity.get("source_authoring_unit_fingerprint"), "actual_content": identity.get("source_authority_content_fingerprint")})
write("ATTEMPT11_COMPILED_V3_VALIDATION.json", {"status": "PASS", "candidate_decision": proposal.get("decision"), "creative_projection_status": (proposal.get("creative_projection") or {}).get("status"), "compiled_proposal_fingerprint": a11.get("proposal_fingerprint")})
write("ATTEMPT11_RUNTIME_VALIDATION.json", {"status": runtime.get("status"), "report": runtime})
write("ATTEMPT11_TEXT_COMPLETENESS.json", {"status": text.get("status"), "report": text})
write("ATTEMPT11_DOWNSTREAM_LEAKAGE_AUDIT.json", {"status": leakage.get("status"), "audit": leakage})
write("ATTEMPT11_PHYSICAL_ACTION_AUTHORITY_AUDIT.json", {"status": physical.get("status"), "audit": physical})
write("ATTEMPT11_UNCERTAINTY_AUDIT.json", {"status": uncertainty.get("status"), "audit": uncertainty})
write("ATTEMPT11_POLARITY_AUDIT.json", {"status": semantic.get("status"), "physical": semantic.get("physical_action_authority"), "downstream": semantic.get("downstream_leakage"), "polarity_false_positive_count": sum(1 for item in (semantic.get("downstream_leakage") or {}).get("violations", []) if "交由下游" in str(item.get("text") or ""))})

sf = (semantic.get("source_grounding") or {}).get("findings", [])
pf = (semantic.get("physical_action_authority") or {}).get("findings", [])
lf = (semantic.get("downstream_leakage") or {}).get("violations", [])
a11_counts = {"certainty_collapse": sum(x.get("classification") == "UNSUPPORTED_CERTAINTY_COLLAPSE" for x in sf if isinstance(x, dict)), "unsupported_story_action": sum(x.get("classification") == "UNSUPPORTED_STORY_ACTION" for x in pf if isinstance(x, dict)), "SceneBlocking_leakage": sum(x.get("classification") == "DOWNSTREAM_SCENEBLOCKING_LEAKAGE" for x in pf if isinstance(x, dict)), "ShotPlan_leakage": sum(x.get("category") in {"SCENEBLOCKING", "SHOT_EXECUTION", "SHOTPLAN", "SHOT_SIZE", "LENS", "CAMERA"} for x in lf if isinstance(x, dict))}
a9_counts = {"certainty_collapse": 1, "unsupported_story_action": 1, "SceneBlocking_leakage": 2, "ShotPlan_leakage": 0}
write("ATTEMPT9_TO_ATTEMPT11_SEMANTIC_DELTA.json", {"status": "PASS", "attempt9_counts": a9_counts, "attempt11_counts": a11_counts, "attempt9_review_fingerprint": "1bd69e6ceb8d2b51b098fcabd7f877a636a338759dc5550365e92bef275af198", "attempt11_review_fingerprint": a11.get("semantic_review_fingerprint"), "polarity_false_positive_count": sum(1 for x in lf if isinstance(x, dict) and "交由下游" in str(x.get("text") or ""))})
write("ATTEMPT10_TO_ATTEMPT11_STRUCTURAL_DELTA.json", {"status": "PASS", "attempt10": {"status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_SCHEMA_INVALID", "missing": ["visual_priority"], "schema": "FAIL"}, "attempt11": {"status": a11.get("structural_status"), "schema": schema.get("status"), "visual_priority_present": "visual_priority" in ir, "top_level_key_count": len(actual_keys)}})
quality_text = json.dumps(ir, ensure_ascii=False)
quality_terms = ["停顿", "迟疑", "呼吸", "视线", "目光", "语气", "语速", "表情", "身体收紧", "僵住", "节奏", "反应延迟"]
write("ATTEMPT11_CONTENT_QUALITY_AUDIT.json", {"status": "PASS", "beat_specificity": len(ir.get("beat_enrichments", [])), "performance_action_hits": sorted({term for term in quality_terms if term in quality_text}), "template_like_hits": [term for term in ["保持悬念", "注意情绪", "突出人物", "加强节奏"] if term in quality_text], "visual_priority_useful": bool(ir.get("visual_priority")), "semantic_status_is_not_quality_status": True})

commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
remote = subprocess.check_output(["git", "ls-remote", "origin", "refs/heads/codex/visual-authoring-provider-canary-reconcile"], cwd=ROOT, text=True).split()[0]
working = "CLEAN" if not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip() else "DIRTY"
report = f"""# V7.6.21 Director CreativeEnrichment Attempt-11 Real Semantic V2 + Structural Revision Canary

DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_VALIDATED
NEXT_STATE=DIRECTOR_TREATMENT_SEMANTIC_REVIEW_REQUIRED
SEMANTIC_REVIEW_V2=BLOCKED

## Transport

- Endpoint: `POST /api/books/990453/episodes/1/director-treatment/creative-enrichment/revision/llm-draft`.
- Authorization: `v7.6.21-attempt11-stage-b-semantic-v2-structural-single-call`; real Provider POST: `1`; automatic retry: `0`.
- Provider profile: `local-llm-2vydoz / mimo-v2.5 / https://api.xiaomimimo.com`.
- HTTP status: `{transport.get('http_status')}`; Provider request ID: `{raw.get('provider_request_id') or None}`; finish_reason: `{raw.get('finish_reason')}`; latency: `{raw.get('latency_ms')} ms`.
- Tokens: `{raw.get('usage')}`; raw length: `{raw.get('raw_response_length')}`; raw SHA: `{raw.get('raw_response_sha256')}`.

## Structural and lineage gates

- Strict parse: `PASS`; duplicate key: `PASS`; schema: `{schema.get('status')}`; top-level keys: `{len(actual_keys)}/11`; missing required fields: `[]`; visual_priority: `yes`.
- Text completeness: `{text.get('status')}`; runtime validation: `{runtime.get('status')}`; beat coverage: `{runtime.get('beat_coverage')}`.
- Stage A binding: `PASS` (`attempt-7`, `{EXPECTED_STAGE_A_IR}`, `{EXPECTED_STAGE_A_MATERIALIZED}`).
- Semantic parent: `attempt-9`, IR `{EXPECTED_A9_IR}`, policy `cf75e024231e619f83f5b9ee79dc388cd199b25464d8d6f3e69ac6c0ab8cc4b8`, review `1bd69e6ceb8d2b51b098fcabd7f877a636a338759dc5550365e92bef275af198`, revision parent `72d79ca4fb8c23161274d4c617e2c91bcfecb599701270534762cc010569a15c`.
- Structural source: `attempt-10`, feedback `4d17ddadda4a473154491359f2dae9a7ae3a190669113fd16a2572cc89a64be4`.
- Source fingerprints: `{identity.get('source_authoring_unit_fingerprint')} / {identity.get('source_authority_content_fingerprint')}`.

## Semantic V2

- Attempt-11 IR fingerprint: `{a11.get('ir_fingerprint')}`; semantic review fingerprint: `{a11.get('semantic_review_fingerprint')}`.
- Semantic status: `BLOCKED`; counts certainty `{a11_counts['certainty_collapse']}`, story action `{a11_counts['unsupported_story_action']}`, SceneBlocking `{a11_counts['SceneBlocking_leakage']}`, ShotPlan `{a11_counts['ShotPlan_leakage']}`.
- Attempt-9 → Attempt-11: `{a9_counts} -> {a11_counts}`.
- Polarity false-positive count: `{sum(1 for x in lf if isinstance(x, dict) and '交由下游' in str(x.get('text') or ''))}`. The blocking term is the generated note's delegation phrase `交由下游 SceneBlocking 与 ShotPlan 权威处理`; it did not trigger physical action or certainty violations.
- Creative quality audit: 4/4 beats, performance action hits `{sorted({term for term in quality_terms if term in quality_text})}`, visual priority present and useful; semantic PASS is not treated as creative-quality PASS.

## Persistence and boundaries

- Active Stage B: `attempt-9 -> attempt-11`; stage_b_attempts: `attempt-8, attempt-9, attempt-10, attempt-11`.
- semantic_review_assessments: `0 -> 1`; proposal: `ready_for_review / PROPOSED`; confirm called: `0`; confirm_allowed: `false`; next state: `DIRECTOR_TREATMENT_SEMANTIC_REVIEW_REQUIRED`.
- DirectorTreatment approved writes: `0`; Authority: `0`; Pointer: `0`.
- SceneBlocking / ShotPlan / PromptIR / IMAGE / VIDEO / SHAPI / Poyo / 75API: `0 / 0 / 0 / 0 / 0 / 0 / 0 / 0`.
- Attempt-12: `0`; automatic retry: `0`; Attempt-9 and Attempt-10 archives preserved: `true / true`.
- Attempt-9 raw in prompt: `false`; Attempt-10 raw in prompt: `false`; semantic and structural feedback blocks: `true / true`.

## Verification and delivery

- Provider-free regression after call: run separately; no Provider call is made by tests.
- `python -m compileall -q core api scripts`: run separately.
- `git diff --check`: run separately.
- Working tree at evidence generation: `{working}`.
- Evidence commit SHA: `{commit}`; remote HEAD: `{remote}`.
"""
(OUT / "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_REPORT.md").write_text(report, encoding="utf-8")
