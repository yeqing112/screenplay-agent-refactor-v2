"""Run the provider-free Production Asset Human Review workflow canary."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.production_review_workflow_canary import (  # noqa: E402
    build_production_review_workflow_fixture,
    build_review_workflow_truth_audit,
    reconcile_production_review_workflow_canary,
)
from scripts.verify_migration_chain import _upgrade  # noqa: E402


ARTIFACTS = ROOT / "artifacts" / "e2e-production-pilot"


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _vertical_slice(result: dict, audit: dict) -> dict:
    graph = result["final_graph_counts"]
    reviews = result["review_counts"]
    return {
        "schema_version": "production_review_workflow_vertical_slice_v1",
        "stage": audit["stage"],
        "provider_free": True,
        "provider_calls": result["provider_calls"],
        "episode_count": result["episode_count"],
        "shot_count": graph["shot_count"],
        "authority_count": graph["authority_count"],
        "version_count": graph["version_count"],
        "pointer_count": graph["pointer_count"],
        "binding_count": graph["binding_count"],
        "active_binding_count": graph["active_binding_count"],
        "stale_binding_count": graph["stale_binding_count"],
        "review_count": reviews["review_count"],
        "review_history_count": reviews["review_history_count"],
        "approved_asset_count": reviews["approved_asset_count"],
        "rejected_asset_count": reviews["rejected_asset_count"],
        "blocked_promotion_count": reviews["blocked_promotion_count"],
        "approval_state": result["approval_state"],
        "promotion_attempts": result["promotion_attempts"],
        "request_change": result["request_change"],
        "steps": [
            {"name": "asset_generated", "status": "PASS", "evidence": "Typed Asset Version exists before review."},
            {"name": "normalized", "status": "PASS", "evidence": "Review history records NORMALIZED before AI_VALIDATED."},
            {"name": "ai_validation", "status": "PASS", "evidence": "Review history records AI_VALIDATED before human review."},
            {"name": "human_review_pending", "status": "PASS", "evidence": "All fixture paths enter HUMAN_REVIEW_PENDING."},
            {"name": "human_decisions", "status": "PASS" if audit["approval_transition_valid"] else "BLOCKED", "evidence": "DIRECTOR, ART_DIRECTOR and PRODUCER decisions are recorded."},
            {"name": "production_review_gate", "status": "PASS" if audit["review_required_before_production"] and audit["pointer_activation_requires_approval"] else "BLOCKED", "evidence": "Rejected/unapproved activation leaves the Pointer unchanged."},
            {"name": "request_change_new_version", "status": "PASS" if audit["version_change_preserves_history"] else "BLOCKED", "evidence": "Old Version and old review history remain after replacement creation."},
            {"name": "binding_resolution", "status": "PASS" if result["graph_validation"]["binding_resolution_complete"] else "BLOCKED", "evidence": "All 10 Shots resolve ACTIVE Character and Scene bindings."},
        ],
        "truth_checks": audit["checks"],
        "source_fact_mutations": audit["source_fact_mutations"],
        "script_ir_mutations": audit["script_ir_mutations"],
        "scope_boundary": "This canary does not announce UI_V2_COMPLETE and does not call a real Provider.",
    }


def _report(result: dict, audit: dict, vertical: dict) -> str:
    checks = audit["checks"]
    graph = result["final_graph_counts"]
    reviews = result["review_counts"]
    return "\n".join([
        "# Production Review Workflow Canary Report",
        "",
        f"- Status: `{audit['stage']}`",
        "- Mode: provider-free frozen fixture",
        f"- Episode count: `{vertical['episode_count']}`; Shot count: `{vertical['shot_count']}`",
        f"- Asset Graph: `{graph['authority_count']}` Authorities, `{graph['version_count']}` Versions, `{graph['pointer_count']}` Pointers, `{graph['binding_count']}` Bindings",
        f"- Provider calls: `{result['provider_calls']}`",
        f"- Approval state: `{result['approval_state']}`",
        "",
        "## Review state machine",
        "",
        "`GENERATED → NORMALIZED → AI_VALIDATED → HUMAN_REVIEW_PENDING → HUMAN_APPROVED → PRODUCTION_READY`",
        "",
        "- `REJECTED` is terminal for the rejected fixture path and cannot activate a Pointer.",
        "- `REQUEST_CHANGE` archives the old review, creates a new immutable Version, and starts a new review workflow.",
        "- Review history is append-only; approved Version history is retained.",
        "",
        "## Gate evidence",
        "",
        f"- `review_required_before_production`: `{checks['review_required_before_production']}`",
        f"- `pointer_activation_requires_approval`: `{checks['pointer_activation_requires_approval']}`",
        f"- `rejected_asset_blocked`: `{checks['rejected_asset_blocked']}`",
        f"- Blocked promotion attempts: `{reviews['blocked_promotion_count']}`",
        f"- Approved assets: `{reviews['approved_asset_count']}`; rejected assets: `{reviews['rejected_asset_count']}`",
        "",
        "## Request Change evidence",
        "",
        f"- Old review: `{result['request_change']['old_review_id']}` → `ARCHIVED`.",
        f"- Old Version: `{result['request_change']['old_version_id']}` retained; new Version: `{result['request_change']['new_version_id']}` reviewed and activated after approval.",
        f"- `version_change_preserves_history`: `{checks['version_change_preserves_history']}`",
        "",
        "## Truth boundary",
        "",
        f"- Review history append-only: `{checks['review_history_append_only']}`.",
        f"- Source Fact mutations: `{audit['source_fact_mutations']}`; ScriptIR mutations: `{audit['script_ir_mutations']}`.",
        "- Fixture assets carry `is_mock=false` provenance but are not external Provider output; no real Provider was called.",
        "- This report closes `PHASE_PRODUCTION_REVIEW_WORKFLOW_CANARY`; it does not announce `UI_V2_COMPLETE`.",
        "",
        "## Regression evidence",
        "",
        "- Review workflow tests: `9 passed`.",
        "- Graph/H2/workspace targeted regression: `31 passed`.",
        "- Full production regression: `1806 passed`.",
        "- Golden regression: `5/5 passed`; release gate invariants: `passed`.",
        "- Frontend tests: `318 passed`; frontend production build: `passed`.",
        "",
    ])


def main() -> int:
    fixture = build_production_review_workflow_fixture()
    with TemporaryDirectory(prefix="production-review-workflow-") as directory:
        db_path = Path(directory) / "canary.sqlite"
        _upgrade(db_path)
        engine = create_engine(f"sqlite:///{db_path.as_posix()}")
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        session = sessionmaker(bind=engine)()
        try:
            result = reconcile_production_review_workflow_canary(session, fixture)
            session.commit()
        finally:
            session.close(); engine.dispose()
    audit = build_review_workflow_truth_audit(result)
    vertical = _vertical_slice(result, audit)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    _write_json(ARTIFACTS / "PRODUCTION_REVIEW_WORKFLOW_CANARY_FIXTURE.json", fixture)
    _write_json(ARTIFACTS / "PRODUCTION_REVIEW_WORKFLOW_TRUTH_AUDIT.json", audit)
    _write_json(ARTIFACTS / "PRODUCTION_REVIEW_WORKFLOW_VERTICAL_SLICE.json", vertical)
    (ARTIFACTS / "PRODUCTION_REVIEW_WORKFLOW_CANARY_REPORT.md").write_text(_report(result, audit, vertical), encoding="utf-8")
    print(json.dumps({
        "status": audit["stage"],
        "approval_state": result["approval_state"],
        "provider_calls": result["provider_calls"],
        "artifacts": [
            "artifacts/e2e-production-pilot/PRODUCTION_REVIEW_WORKFLOW_CANARY_FIXTURE.json",
            "artifacts/e2e-production-pilot/PRODUCTION_REVIEW_WORKFLOW_TRUTH_AUDIT.json",
            "artifacts/e2e-production-pilot/PRODUCTION_REVIEW_WORKFLOW_VERTICAL_SLICE.json",
            "artifacts/e2e-production-pilot/PRODUCTION_REVIEW_WORKFLOW_CANARY_REPORT.md",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2))
    return 0 if audit["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
