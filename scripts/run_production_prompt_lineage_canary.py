"""Run the provider-free Production Prompt Lineage canary."""
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

from core.production_prompt_lineage_canary import (  # noqa: E402
    build_production_prompt_lineage_fixture,
    build_prompt_lineage_truth_audit,
    reconcile_production_prompt_lineage_canary,
)
from scripts.verify_migration_chain import _upgrade  # noqa: E402


ARTIFACTS = ROOT / "artifacts" / "e2e-production-pilot"


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _vertical(result: dict, audit: dict) -> dict:
    counts = result.get("counts") or {}
    return {
        "schema_version": "production_prompt_lineage_vertical_slice_v1",
        "stage": audit["stage"],
        "provider_free": True,
        "provider_calls": 0,
        "episode_count": result.get("episode_count", 1),
        "shot_count": counts.get("shot_count", 0),
        "prompt_count": counts.get("prompt_count", 0),
        "prompt_version_count": counts.get("prompt_version_count", 0),
        "generation_intent_count": counts.get("generation_intent_count", 0),
        "asset_count": counts.get("asset_count", 0),
        "review_count": counts.get("review_count", 0),
        "lineage_count": counts.get("lineage_count", 0),
        "fingerprint_validation_result": result.get("fingerprint_checks", {}),
        "traceability_result": bool((audit.get("checks") or {}).get("traceability_result")),
        "prompt_change": result.get("prompt_change", {}),
        "truth_checks": audit.get("checks", {}),
        "scope_boundary": "Provider-free canary; no UI, Source Fact or ScriptIR mutation; Human Review remains the production gate.",
    }


def _report(result: dict, audit: dict, vertical: dict) -> str:
    c = result["counts"]
    checks = audit["checks"]
    return "\n".join([
        "# Production Prompt Lineage Canary Report",
        "",
        f"- Status: `{audit['stage']}`",
        f"- Approval state: `{result['approval_state']}`",
        "- Mode: provider-free frozen fixture",
        f"- Episode count: `{vertical['episode_count']}`; Shot count: `{c['shot_count']}`",
        f"- Prompt count: `{c['prompt_count']}`; Prompt versions: `{c['prompt_version_count']}`",
        f"- Generation intents: `{c['generation_intent_count']}`; Assets: `{c['asset_count']}`; Reviews: `{c['review_count']}`",
        f"- Prompt lineages: `{c['lineage_count']}`; Provider calls: `0`",
        "",
        "## Trace",
        "",
        "`Shot Requirement → Generation Intent → Prompt Version → Asset Version → Human Review`",
        "",
        f"- `asset_has_prompt_lineage`: `{checks['asset_has_prompt_lineage']}`",
        f"- `prompt_version_exists`: `{checks['prompt_version_exists']}`",
        f"- `generation_intent_exists`: `{checks['generation_intent_exists']}`",
        f"- `review_reproducible`: `{checks['review_reproducible']}`",
        f"- `traceability_result`: `{checks['traceability_result']}`",
        "",
        "## Fingerprints",
        "",
        f"- Same prompt / same fingerprint: `{result['fingerprint_checks']['same_prompt_same_fingerprint']}`",
        f"- Changed prompt / different fingerprint: `{result['fingerprint_checks']['different_prompt_different_fingerprint']}`",
        "",
        "## Prompt change",
        "",
        f"- Prompt v1: `{result['prompt_change']['old_prompt_version_id']}` → rejected review `{result['prompt_change']['old_review_id']}`.",
        f"- Prompt v2: `{result['prompt_change']['new_prompt_version_id']}` → new Asset Version `{result['prompt_change']['new_asset_version_id']}` → approved review `{result['prompt_change']['new_review_id']}`.",
        "- Prompt v1 and its review history remain immutable and queryable.",
        "",
        "## Boundary and audit",
        "",
        f"- Prompt history append-only: `{checks['prompt_history_append_only']}`.",
        f"- Source Fact mutations: `{audit['source_fact_mutations']}`; ScriptIR mutations: `{audit['script_ir_mutations']}`.",
        "- No real Provider was called; fixture provenance is not external Provider output.",
        "- This report closes `PHASE_PRODUCTION_PROMPT_LINEAGE_CANARY`; it does not announce `UI_V2_COMPLETE`.",
        "",
    ])


def main() -> int:
    fixture = build_production_prompt_lineage_fixture()
    with TemporaryDirectory(prefix="production-prompt-lineage-") as directory:
        db_path = Path(directory) / "canary.sqlite"
        _upgrade(db_path)
        engine = create_engine(f"sqlite:///{db_path.as_posix()}")
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        session = sessionmaker(bind=engine)()
        try:
            result = reconcile_production_prompt_lineage_canary(session, fixture)
            session.commit()
        finally:
            session.close(); engine.dispose()
    audit = build_prompt_lineage_truth_audit(result)
    vertical = _vertical(result, audit)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    _write(ARTIFACTS / "PRODUCTION_PROMPT_LINEAGE_CANARY_FIXTURE.json", fixture)
    _write(ARTIFACTS / "PRODUCTION_PROMPT_LINEAGE_TRUTH_AUDIT.json", audit)
    _write(ARTIFACTS / "PRODUCTION_PROMPT_LINEAGE_VERTICAL_SLICE.json", vertical)
    (ARTIFACTS / "PRODUCTION_PROMPT_LINEAGE_CANARY_REPORT.md").write_text(_report(result, audit, vertical), encoding="utf-8")
    print(json.dumps({"status": audit["stage"], "approval_state": result["approval_state"], "provider_calls": 0, "artifacts": [str(path.relative_to(ROOT)) for path in (ARTIFACTS / "PRODUCTION_PROMPT_LINEAGE_CANARY_FIXTURE.json", ARTIFACTS / "PRODUCTION_PROMPT_LINEAGE_TRUTH_AUDIT.json", ARTIFACTS / "PRODUCTION_PROMPT_LINEAGE_VERTICAL_SLICE.json", ARTIFACTS / "PRODUCTION_PROMPT_LINEAGE_CANARY_REPORT.md")], "generated_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2))
    return 0 if audit["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
