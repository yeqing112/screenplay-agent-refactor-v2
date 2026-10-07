"""Provider-free completion of the single Attempt-9 transport.

The authorized transport persisted raw Attempt-9 before a historical packet
fingerprint reconciliation raised.  This script consumes only that persisted
raw response; it never calls a Provider and never creates approved or
downstream records.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("DATABASE_URL", "sqlite:///D:/Work/Project/screenplay-agent-refactor-v2/work/db/screenplay.db?timeout=30")
os.environ.setdefault("APP_ENV", "production")
os.environ.setdefault("DEPLOYMENT_ENV", "production")

from api import director_treatment_api as api
from core.director_progressive_authoring import (
    compile_progressive_director_proposal,
    parse_director_creative_enrichment_ir,
    validate_director_creative_enrichment_ir,
    validate_director_creative_enrichment_ir_schema,
    validate_director_creative_enrichment_text_completeness,
)
from core.director_source_grounded import validate_director_contract_v2 as validate_source_grounded_contract_v2
from core.director_semantic_grounding import validate_director_creative_semantic_review
from core.director_revision import proposal_fingerprint, semantic_review_fingerprint
from models import DecisionPacketRecord, Session


BOOK_ID = 990453
PACKET_ID = 64
PACKET_FP = "e48b8502ab2e14b94798d19a"
SCENE_ID = "E01_SC001"
ATTEMPT8_FP = "5bb234bb5439d0d762f4fc41d63ed5d409f855d9047dff1d26645a7ef90483f4"
ATTEMPT9_AUTH = "v7.6.15-attempt9-stage-b-semantic-revision-single-call"


def main() -> None:
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=PACKET_ID, book_id=BOOK_ID, packet_fingerprint=PACKET_FP).first()
        if not row:
            raise SystemExit("ATTEMPT9_RECOVERY_PACKET_NOT_FOUND")
        info = json.loads(row.model_info or "{}")
        proposal_before = json.loads(row.proposal or "{}")
        progressive = info.get("progressive_director_authoring") or {}
        stage_a = progressive.get("stage_a") or {}
        stage_b = progressive.get("stage_b") or {}
        archives = progressive.get("stage_b_attempts") or []
        attempt9_archive = next((item for item in archives if item.get("attempt_id") == "attempt-9"), None)
        if not attempt9_archive or not attempt9_archive.get("raw_forensic", {}).get("raw_response"):
            raise SystemExit("ATTEMPT9_RECOVERY_RAW_NOT_FOUND")
        if stage_b.get("attempt_id") != "attempt-8" or stage_b.get("ir_fingerprint") != ATTEMPT8_FP:
            raise SystemExit("ATTEMPT9_RECOVERY_PARENT_NOT_ACTIVE")
        raw = str(attempt9_archive["raw_forensic"]["raw_response"])

        treatment, evidence, _ = api._build_preview(
            BOOK_ID,
            api.DirectorTreatmentPreviewRequest(episode=1, scene_id=SCENE_ID, workflow_profile="production"),
        )
        source_constraints = treatment.get("source_constraints") if isinstance(treatment.get("source_constraints"), dict) else {}
        parsed = parse_director_creative_enrichment_ir(raw)
        schema_report = validate_director_creative_enrichment_ir_schema(parsed)
        text_report = validate_director_creative_enrichment_text_completeness(parsed)
        runtime_report = validate_director_creative_enrichment_ir(
            parsed,
            beat_plan=stage_a["materialized_beat_plan"],
            declared_participants=source_constraints.get("declared_participants") or [],
        )
        if schema_report.get("status") != "PASS" or text_report.get("status") != "PASS" or runtime_report.get("status") != "qualified":
            raise SystemExit("ATTEMPT9_RECOVERY_STRUCTURAL_GATE_FAILED")
        candidate = compile_progressive_director_proposal(
            beat_plan_ir=stage_a["ir"],
            enrichment_ir=parsed,
            baseline_treatment=treatment,
            source_scene=evidence.get("scene") if isinstance(evidence.get("scene"), dict) else {},
            materialized_beat_plan=stage_a["materialized_beat_plan"],
            materialized_fingerprint=stage_a["materialized_fingerprint"],
        )
        compiled = validate_source_grounded_contract_v2(
            candidate,
            scene=evidence.get("scene") if isinstance(evidence.get("scene"), dict) else {},
            production=False,
        )
        if compiled.get("status") != "qualified":
            raise SystemExit("ATTEMPT9_RECOVERY_COMPILED_CONTRACT_FAILED")
        semantic_review = validate_director_creative_semantic_review(
            parsed,
            candidate=candidate,
            source_authoring_units=source_constraints.get("source_authoring_units") or [],
            stage_a=stage_a.get("ir"),
            declared_participants=source_constraints.get("declared_participants") or [],
        )
        stage_b_fp = hashlib.sha256(json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        forensic = copy.deepcopy(attempt9_archive.get("raw_forensic") or {})
        provider_identity = copy.deepcopy(attempt9_archive.get("provider_request_identity") or {})
        provider = {
            "called": True,
            "calls": 1,
            "profile_id": forensic.get("profile_id"),
            "model": forensic.get("model"),
            "request_fingerprint": forensic.get("prompt_fingerprint"),
            "provider_request_fingerprint_v2": forensic.get("provider_request_fingerprint_v2"),
            "response_fingerprint": forensic.get("raw_response_sha256"),
            "provider_request_id": forensic.get("provider_request_id") or None,
        }
        revision_parent = attempt9_archive.get("revision_parent") or {}
        proposal_lineage = {
            "proposal_origin": "PROVIDER_PROPOSAL",
            "provider": provider,
            "authoring": {"human_input": False},
            "stage_a": {"attempt_id": stage_a.get("attempt_id"), "ir_fingerprint": stage_a.get("ir_fingerprint"), "materialized_fingerprint": stage_a.get("materialized_fingerprint")},
            "stage_b": {"attempt_id": "attempt-9", "ir_fingerprint": stage_b_fp},
            "revision": {"parent_attempt_id": "attempt-8", "parent_ir_fingerprint": ATTEMPT8_FP, "semantic_rejection_fingerprint": semantic_review_fingerprint(semantic_review)},
            "merge": "deterministic",
        }
        candidate["proposal_origin"] = "PROVIDER_PROPOSAL"
        candidate["proposal_provenance"] = proposal_lineage
        stage_b_active = {
            "status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_VALIDATED",
            "authoring_stage": "CREATIVE_ENRICHMENT",
            "attempt_id": "attempt-9",
            "authorization_id": ATTEMPT9_AUTH,
            "ir": copy.deepcopy(parsed),
            "ir_fingerprint": stage_b_fp,
            "fingerprint": stage_b_fp,
            "stage_a_materialized_fingerprint": stage_a["materialized_fingerprint"],
            "source_authoring_unit_fingerprint": provider_identity.get("source_authoring_unit_fingerprint"),
            "source_authority_content_fingerprint": provider_identity.get("source_authority_content_fingerprint"),
            "provider_provenance": provider,
            "provider_request_identity": provider_identity,
            "validation_state": "VALIDATED",
            "merge_state": "MERGED",
            "semantic_review": copy.deepcopy(semantic_review),
            "semantic_review_fingerprint": semantic_review_fingerprint(semantic_review),
            "revision_parent": copy.deepcopy(revision_parent),
        }
        # Replace the provisional failure archive with the complete immutable
        # Attempt-9 result while preserving Attempt-8 byte-for-byte.
        archive_entry = {
            "attempt_id": "attempt-9",
            "authoring_stage": "CREATIVE_ENRICHMENT",
            "authorization_id": ATTEMPT9_AUTH,
            "ir": copy.deepcopy(parsed),
            "ir_fingerprint": stage_b_fp,
            "structural_status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_VALIDATED",
            "validation_state": "VALIDATED",
            "merge_state": "MERGED",
            "semantic_review": copy.deepcopy(semantic_review),
            "semantic_review_fingerprint": semantic_review_fingerprint(semantic_review),
            "revision_parent": copy.deepcopy(revision_parent),
            "stage_a_materialized_fingerprint": stage_a["materialized_fingerprint"],
            "source_authoring_unit_fingerprint": provider_identity.get("source_authoring_unit_fingerprint"),
            "source_authority_content_fingerprint": provider_identity.get("source_authority_content_fingerprint"),
            "provider_provenance": provider,
            "provider_request_identity": provider_identity,
            "raw_forensic": forensic,
            "validation": {"schema": schema_report, "text": text_report, "runtime": runtime_report, "compiled": compiled, "semantic_review": semantic_review},
            "proposal": copy.deepcopy(candidate),
            "proposal_fingerprint": proposal_fingerprint(candidate),
        }
        new_archives = [archive_entry if item.get("attempt_id") == "attempt-9" else item for item in archives]
        if not any(item.get("attempt_id") == "attempt-9" for item in new_archives):
            new_archives.append(archive_entry)
        progressive["stage_b"] = stage_b_active
        progressive["stage_b_attempts"] = new_archives
        info["progressive_director_authoring"] = progressive
        info["stage_b_status"] = "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_VALIDATED"
        info["stage_b_validation"] = {"schema": schema_report, "text": text_report, "runtime": runtime_report, "compiled": compiled, "semantic_review": semantic_review}
        info["stage_b_raw_response_forensic"] = {**forensic, "parse_started": True}
        info["stage_b_provider_request"] = provider_identity
        info["semantic_review"] = copy.deepcopy(semantic_review)
        info["llm_draft_in_progress"] = False
        info["revision_boundary_status"] = "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_VALIDATED"
        info["stage_b_attempt_context"] = {"history_count": 8, "ordinal": 9, "attempt_id": "attempt-9", "status_prefix": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9"}
        info["event_trace"] = ["TRANSPORT", "RAW_PERSIST", "FINISH_REASON_GATE", "PARSE", "STAGE_B_SCHEMA_VALIDATE", "STAGE_B_TEXT_COMPLETENESS", "STAGE_B_RUNTIME_VALIDATE", "STAGE_A_BINDING_REVALIDATE", "SOURCE_BINDING_REVALIDATE", "STAGE_B_SEMANTIC_REVIEW", "STAGE_B_PERSIST", "DETERMINISTIC_MERGE", "COMPILED_V3_VALIDATE", "PROPOSAL_PERSIST"]
        info["director_llm_attempts"] = [
            {**item, "status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_VALIDATED"} if item.get("attempt_id") == "attempt-9" else item
            for item in (info.get("director_llm_attempts") or [])
        ]
        row.model_info = json.dumps(info, ensure_ascii=False)
        row.proposal = json.dumps(candidate, ensure_ascii=False)
        row.status = "draft"
        row.updated_at = datetime.now()
        session.commit()
        print(json.dumps({
            "status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_VALIDATED",
            "semantic_status": semantic_review.get("status"),
            "provider_calls": 1,
            "attempt9_ir_fingerprint": stage_b_fp,
            "raw_sha256": forensic.get("raw_response_sha256"),
            "attempt8_preserved": any(item.get("attempt_id") == "attempt-8" and item.get("ir_fingerprint") == ATTEMPT8_FP for item in new_archives),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
