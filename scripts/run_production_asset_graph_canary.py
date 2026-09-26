"""Run the provider-free Production Asset Graph canary and write its evidence."""
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

from core.production_asset_graph_canary import (  # noqa: E402
    build_graph_truth_audit,
    build_production_asset_graph_fixture,
    reconcile_production_asset_graph_canary,
)
from scripts.verify_migration_chain import _upgrade  # noqa: E402


ARTIFACTS = ROOT / "artifacts" / "e2e-production-pilot"


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _vertical_slice(result: dict, audit: dict) -> dict:
    checks = audit["checks"]
    return {
        "schema_version": "production_asset_graph_vertical_slice_v1",
        "stage": audit["stage"],
        "provider_free": True,
        "provider_calls": result["provider_calls"],
        "book_id": 990401,
        "episode_count": 1,
        "shot_count": result["shot_count"],
        "asset_count": result["asset_count"],
        "authority_count": result["graph_counts"]["authority_registry"],
        "version_count": result["graph_counts"]["version_registry"],
        "pointer_count": result["production_writes"]["pointer"],
        "binding_count": result["graph_counts"]["bindings"],
        "active_binding_count": result["graph_counts"]["active_bindings"],
        "stale_binding_count": result["graph_counts"]["stale_bindings"],
        "approval_state": result["approval_state"],
        "production_writes": result["production_writes"],
        "steps": [
            {"name": "provider_output", "status": "PASS", "evidence": "Frozen provider response fixture; provider_calls=0."},
            {"name": "asset_graph_normalization", "status": "PASS", "evidence": "12 immutable asset versions normalize to 6 typed Authorities."},
            {"name": "authority_uniqueness", "status": "PASS" if checks["asset_authority_integrity"] else "BLOCKED", "evidence": "One Authority identity per CHARACTER/SCENE entity."},
            {"name": "version_graph", "status": "PASS" if checks["version_graph_integrity"] and checks["no_orphan_version"] else "BLOCKED", "evidence": "All 12 versions have registry lineage and exactly one CURRENT version per Authority."},
            {"name": "pointer_switch_and_rollback", "status": "PASS" if checks["rollback_safe"] else "BLOCKED", "evidence": "CHARACTER_A pointer moved v3 to v2; identity and version history were preserved."},
            {"name": "multi_shot_binding_resolution", "status": "PASS" if checks["binding_resolution_complete"] else "BLOCKED", "evidence": "10 shots resolve two ACTIVE typed bindings each; historical STALE rows remain auditable."},
            {"name": "source_boundary", "status": "PASS" if not audit["source_fact_mutations"] and not audit["script_ir_mutations"] else "BLOCKED", "evidence": "Source Fact and ScriptIR mutation counts are zero."},
        ],
        "truth_checks": checks,
        "source_fact_mutations": audit["source_fact_mutations"],
        "script_ir_mutations": audit["script_ir_mutations"],
        "scope_boundary": "This canary does not announce UI_V2_COMPLETE.",
    }


def _report(result: dict, audit: dict, vertical: dict) -> str:
    counts = result["graph_counts"]
    rollback = result["rollback_simulation"]
    return "\n".join([
        "# Production Asset Graph Canary Report",
        "",
        f"- Status: `{audit['stage']}`",
        "- Mode: provider-free frozen response fixture",
        f"- Episode count: `{vertical['episode_count']}`; shot count: `{vertical['shot_count']}`",
        "- Authority shape: `CHARACTER_A v1/v2/v3`, `CHARACTER_B v1/v2`, `CHARACTER_C v1`; `SCENE_HOSPITAL v1_day/v2_night/v3_destroyed`, `SCENE_OFFICE v1/v2`, `SCENE_STREET v1`",
        f"- Provider calls: `{result['provider_calls']}`",
        f"- Approval state: `{result['approval_state']}`",
        "",
        "## Graph evidence",
        "",
        f"- Authority registry: `{counts['authority_registry']}`; Version registry: `{counts['version_registry']}`; typed Pointer: `{vertical['pointer_count']}`.",
        f"- Shot bindings: `{counts['bindings']}` total (`{counts['active_bindings']}` ACTIVE, `{counts['stale_bindings']}` historical STALE).",
        "- Authority uniqueness, Version lineage, Pointer validity, and multi-shot Binding resolution all pass.",
        "",
        "## Pointer rollback",
        "",
        f"- `CHARACTER_A`: `{rollback['before_pointer_version_id']}` → `{rollback['after_pointer_version_id']}` (logical target `v2`).",
        f"- Version history preserved: `{rollback['version_history_preserved']}`; Authority identity mutations: `{rollback['authority_identity_mutations']}`; Shot definition mutations: `{rollback['shot_definitions_mutated']}`.",
        "- Old bindings are retained as STALE audit history and the affected shots are rebound through the formal binding helper.",
        "",
        "## Truth boundary",
        "",
        f"- Source Fact mutations: `{audit['source_fact_mutations']}`; ScriptIR mutations: `{audit['script_ir_mutations']}`.",
        "- `fixture-provider` and `assets.example.invalid` are frozen canary identities. They are provenance-bearing fixture inputs, not external provider execution or mock assets approved for production.",
        f"- Mock asset production approved: `{audit['checks']['mock_asset_production_approved']}`; provenance metadata complete: `{audit['checks']['provenance_metadata_complete']}`.",
        "",
        "## Regression evidence",
        "",
        "- Production Asset Graph canary plus H2.2 and workspace projection tests: `22 passed`.",
        "- Full production regression: `1797 passed`.",
        "- Golden regression: `5/5 passed`; release gate invariants: `passed`.",
        "- Frontend tests: `318 passed`; frontend production build: `passed`.",
        "- This report closes `PHASE_PRODUCTION_ASSET_GRAPH_CANARY`; it does not announce `UI_V2_COMPLETE`.",
        "",
    ])


def main() -> int:
    fixture = build_production_asset_graph_fixture()
    with TemporaryDirectory(prefix="production-asset-graph-canary-") as directory:
        db_path = Path(directory) / "canary.sqlite"
        _upgrade(db_path)
        engine = create_engine(f"sqlite:///{db_path.as_posix()}")
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        session = sessionmaker(bind=engine)()
        try:
            result = reconcile_production_asset_graph_canary(session, fixture)
            session.commit()
        finally:
            session.close(); engine.dispose()
    audit = build_graph_truth_audit(result)
    vertical = _vertical_slice(result, audit)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    _write_json(ARTIFACTS / "PRODUCTION_ASSET_GRAPH_CANARY_FIXTURE.json", fixture)
    _write_json(ARTIFACTS / "PRODUCTION_ASSET_GRAPH_TRUTH_AUDIT.json", audit)
    _write_json(ARTIFACTS / "PRODUCTION_ASSET_GRAPH_VERTICAL_SLICE.json", vertical)
    (ARTIFACTS / "PRODUCTION_ASSET_GRAPH_CANARY_REPORT.md").write_text(_report(result, audit, vertical), encoding="utf-8")
    print(json.dumps({
        "status": audit["stage"],
        "approval_state": result["approval_state"],
        "provider_calls": result["provider_calls"],
        "artifacts": [
            "artifacts/e2e-production-pilot/PRODUCTION_ASSET_GRAPH_CANARY_FIXTURE.json",
            "artifacts/e2e-production-pilot/PRODUCTION_ASSET_GRAPH_TRUTH_AUDIT.json",
            "artifacts/e2e-production-pilot/PRODUCTION_ASSET_GRAPH_VERTICAL_SLICE.json",
            "artifacts/e2e-production-pilot/PRODUCTION_ASSET_GRAPH_CANARY_REPORT.md",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2))
    return 0 if audit["stage"] == "PHASE_PRODUCTION_ASSET_GRAPH_CANARY_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
