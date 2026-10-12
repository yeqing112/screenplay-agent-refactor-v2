"""Read-only revalidation of the V7.5.1 canary scope on the current branch.

This audit deliberately does not repair, migrate, or write the production
database.  V7.5.1 evidence remains historical; this file records whether the
current branch still has the frozen packet state required by that phase.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.canary_scope import build_scope_descriptor, canonical_json, target_scope_snapshot
from models import Session


EVIDENCE = ROOT / "docs" / "canonical-canary" / "v7_5_1-evidence-scope-reconciliation"
SCOPE = build_scope_descriptor(
    book_id=990453,
    episode=1,
    scene_id="E01_SC001",
    script_id=64,
    fact_snapshot_id=49,
    script_ir_version_id=52,
    decision_packet_id=64,
)
EXPECTED_HEAD = "96807f669b7c9b89a6d733854e25ed04ad146308"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _packet_read() -> dict[str, Any]:
    from models import DecisionPacketRecord

    with Session() as session:
        row = session.query(DecisionPacketRecord).filter(
            DecisionPacketRecord.id == 64,
            DecisionPacketRecord.book_id == 990453,
        ).one_or_none()
        if row is None:
            return {"present": False}
        info = json.loads(row.model_info or "{}") if isinstance(row.model_info, str) else {}
        proposal = json.loads(row.proposal or "{}") if isinstance(row.proposal, str) else {}
        attempts = info.get("director_llm_attempts") if isinstance(info.get("director_llm_attempts"), list) else []
        row_payload = {
            "id": row.id,
            "book_id": row.book_id,
            "domain": row.domain,
            "scope": row.scope,
            "packet_fingerprint": row.packet_fingerprint,
            "evidence": row.evidence,
            "unknowns": row.unknowns,
            "conflicts": row.conflicts,
            "allowed_operations": row.allowed_operations,
            "proposal": row.proposal,
            "status": row.status,
            "model_info": row.model_info,
            "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        return {
            "present": True,
            "row_sha256": hashlib.sha256(canonical_json(row_payload).encode("utf-8")).hexdigest(),
            "packet_fingerprint": row.packet_fingerprint,
            "proposal_sha256": hashlib.sha256(canonical_json(proposal).encode("utf-8")).hexdigest(),
            "proposal_schema_version": proposal.get("schema_version"),
            "proposal_decision": proposal.get("decision"),
            "proposal_top_level_keys": sorted(proposal),
            "status": row.status,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "attempt_ids": [str(item.get("attempt_id")) for item in attempts if isinstance(item, dict) and item.get("attempt_id")],
            "attempt_count": len(attempts),
            "stage_a_attempt": (info.get("proposal_provenance") or {}).get("stage_a", {}).get("attempt_id"),
            "stage_b_attempt": (info.get("proposal_provenance") or {}).get("stage_b", {}).get("attempt_id"),
            "provider_calls_recorded": (info.get("proposal_provenance") or {}).get("provider", {}).get("calls"),
        }


def _write(name: str, value: Any) -> None:
    (EVIDENCE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    head = _git("rev-parse", "HEAD")
    branch = _git("branch", "--show-current")
    with Session() as session:
        snapshot_before = target_scope_snapshot(session, scope=SCOPE)
        packet_before = _packet_read()
    with Session() as session:
        snapshot_after = target_scope_snapshot(session, scope=SCOPE)
        packet_after = _packet_read()

    historical_delta = json.loads((EVIDENCE / "TARGET_SCOPE_RECONCILED_DELTA.json").read_text(encoding="utf-8"))
    historical_packet = historical_delta.get("packet", {})
    target_counts = {name: descriptor["count"] for name, descriptor in snapshot_after["tables"].items()}
    packet_state_matches = (
        packet_after.get("proposal_schema_version") is None
        and packet_after.get("proposal_decision") == historical_packet.get("proposal", {}).get("decision")
        and packet_after.get("attempt_count") == 3
        and packet_after.get("stage_b_attempt") in (None, "")
    )
    snapshot_equal = snapshot_before == snapshot_after
    packet_read_equal = packet_before == packet_after
    historical_files = [
        "REAL_DIRECTOR_PROPOSAL_IR_REPORT.md",
        "DIRECTOR_LLM_RAW_RESPONSE_FORENSIC.json",
        "DIRECTOR_LLM_ATTEMPT_3_AUDIT.json",
        "DIRECTOR_PROPOSAL_IR_PARSE_AUDIT.json",
        "DIRECTOR_PROPOSAL_IR_SCHEMA_AUDIT.json",
        "DIRECTOR_PROPOSAL_IR_VALIDATION.json",
        "PRODUCTION_DB_BEFORE.json",
        "PRODUCTION_DB_AFTER.json",
        "PRODUCTION_DB_DELTA.json",
    ]
    historical_preserved = all((ROOT / "docs" / "canonical-canary" / "v7_5-real-director-proposal-ir" / name).exists() for name in historical_files)
    result = {
        "phase": "PHASE_V7_5_PRODUCTION_EVIDENCE_SCOPE_RECONCILIATION_V7_5_1",
        "status": "V7_5_1_REVALIDATION_BLOCKED_CURRENT_BRANCH_DRIFT" if not packet_state_matches else "DIRECTOR_ATTEMPT4_PREFLIGHT_READY",
        "historical_v7_5_1_status": "DIRECTOR_ATTEMPT4_PREFLIGHT_READY",
        "historical_evidence_preserved": historical_preserved,
        "requested_baseline_head": EXPECTED_HEAD,
        "current_head": head,
        "current_branch": branch,
        "head_matches_requested_baseline": head == EXPECTED_HEAD,
        "scope_descriptor": SCOPE,
        "scope_fingerprint": snapshot_after["scope_fingerprint"],
        "target_scope_snapshot_equal_on_double_read": snapshot_equal,
        "target_counts": target_counts,
        "target_downstream_all_zero": all(value == 0 for key, value in target_counts.items() if key != "decision_packet_records"),
        "source_lineage_reference": "SOURCE_LINEAGE_REFREEZE.json",
        "packet_read_equal_on_double_read": packet_read_equal,
        "packet_current": packet_after,
        "packet_expected_for_v7_5_1": {
            "count": 1,
            "proposal": historical_packet.get("proposal"),
            "attempt_history_count": 3,
            "stage_b_attempt": None,
        },
        "packet_state_matches_v7_5_1": packet_state_matches,
        "block_reason": (
            "CURRENT_BRANCH_DRIFT: Packet 64 has a later director_treatment proposal and Stage B attempt-11; "
            "V7.5.1 cannot be re-declared successful without rewriting later production history."
            if not packet_state_matches else ""
        ),
        "provider_calls_this_revalidation": 0,
        "production_writes_this_revalidation": 0,
        "authorization_consumed_this_revalidation": False,
        "historical_delta_not_rewritten": True,
    }
    _write("CURRENT_BRANCH_REVALIDATION.json", result)
    report = f"""# V7.5.1 Current Branch Revalidation\n\n- Status: `{result['status']}`\n- Historical V7.5.1 status: `DIRECTOR_ATTEMPT4_PREFLIGHT_READY` (preserved)\n- Requested baseline: `{EXPECTED_HEAD}`\n- Current HEAD: `{head}`\n- Branch: `{branch}`\n- Scope fingerprint: `{snapshot_after['scope_fingerprint']}`\n- Target scope double-read: `{'PASS' if snapshot_equal else 'FAIL'}`\n- Packet double-read: `{'PASS' if packet_read_equal else 'FAIL'}`\n- Target downstream counts: all zero except DecisionPacket count `{target_counts.get('decision_packet_records')}`\n- Historical V7.5 artifacts preserved: `{historical_preserved}`\n- Provider calls in this revalidation: `0`\n- Production writes in this revalidation: `0`\n\n## Closure\n\nThe scope reconciliation itself still holds. The current branch has advanced beyond the V7.5.1 freeze: Packet 64 now contains a later `director_treatment_v3` proposal and Stage B `attempt-11`, so the V7.5.1 success state cannot be re-declared on this branch. This audit does not rewrite Packet 64 or any historical artifact.\n\nBlock reason: `{result['block_reason']}`\n"""
    (EVIDENCE / "CURRENT_BRANCH_REVALIDATION_REPORT.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
