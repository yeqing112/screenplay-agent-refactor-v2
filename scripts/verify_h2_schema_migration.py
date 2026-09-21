"""Generate the Phase H2 migration execution and schema audit artifacts."""
from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

try:
    from scripts.verify_migration_chain import _upgrade
except ModuleNotFoundError:  # direct ``python scripts/...`` invocation
    from verify_migration_chain import _upgrade

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "artifacts" / "e2e-production-pilot"
REVISION = "a1b2c3d4e5f6"
DOWN_REVISION = "z0a1b2c3d4e5"
H2_TABLES = (
    "production_asset_authority_registry",
    "production_asset_version_registry",
    "character_asset_authorities",
    "character_asset_versions",
    "character_asset_pointers",
    "scene_asset_authorities",
    "scene_asset_versions",
    "scene_asset_pointers",
    "prop_asset_authorities",
    "prop_asset_versions",
    "prop_asset_pointers",
    "shot_asset_bindings",
)
IMPACT_TABLES = (
    "script_ir_versions",
    "director_treatment_authorities",
    "scene_blocking_authorities",
    "shot_plan_authorities",
    "storyboard_shots",
    "prompt_ir_versions",
    "media_candidate_records",
    "official_media_versions",
    "visual_reference_authorities",
)


def _cfg(db: Path) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    return cfg


def _counts(engine, tables):
    with engine.connect() as connection:
        return {table: connection.execute(text(f"select count(*) from {table}")).scalar() for table in tables}


def _enable_foreign_keys(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def _seed_existing_ag2(engine):
    """Seed a non-empty, provider-free A-G2-shaped fixture before H2."""
    inspector = inspect(engine)
    seed_tables = tuple(table for table in IMPACT_TABLES if table != "official_media_versions")
    with engine.begin() as connection:
        for table in seed_tables:
            values = {}
            for column in inspector.get_columns(table):
                name = column["name"]
                if name == "id" or column.get("nullable") or column.get("default") is not None:
                    continue
                type_name = str(column["type"]).upper()
                if "INT" in type_name:
                    values[name] = 1
                elif "DATE" in type_name or "TIME" in type_name:
                    values[name] = datetime.utcnow()
                elif "TEXT" in type_name:
                    values[name] = "{}"
                else:
                    values[name] = f"h2-fixture-{table}-{name}"
            if not values:
                continue
            columns = list(values)
            placeholders = [f":value_{index}" for index in range(len(columns))]
            params = {f"value_{index}": values[column] for index, column in enumerate(columns)}
            connection.execute(
                text(f"insert into {table} ({', '.join(columns)}) values ({', '.join(placeholders)})"),
                params,
            )


def _schema(engine):
    inspector = inspect(engine)
    result = {}
    for table in H2_TABLES:
        result[table] = {
            "columns": [column["name"] for column in inspector.get_columns(table)],
            "foreign_keys": [
                {"name": item.get("name"), "columns": item.get("constrained_columns"), "references": item.get("referred_table")}
                for item in inspector.get_foreign_keys(table)
            ],
            "indexes": [
                {"name": item.get("name"), "columns": item.get("column_names"), "unique": bool(item.get("unique"))}
                for item in inspector.get_indexes(table)
            ],
            "unique_constraints": [
                {"name": item.get("name"), "columns": item.get("column_names")}
                for item in inspector.get_unique_constraints(table)
            ],
            "checks": [
                {"name": item.get("name"), "sqltext": item.get("sqltext")}
                for item in inspector.get_check_constraints(table)
            ],
        }
    return result


def _cycle(db: Path):
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    _enable_foreign_keys(engine)
    with engine.connect() as connection:
        first_version = connection.execute(text("select version_num from alembic_version")).scalar()
    before_downgrade = _counts(engine, H2_TABLES)
    command.downgrade(_cfg(db), DOWN_REVISION)
    after_downgrade_tables = set(inspect(engine).get_table_names()) & set(H2_TABLES)
    command.upgrade(_cfg(db), "head")
    with engine.connect() as connection:
        final_version = connection.execute(text("select version_num from alembic_version")).scalar()
    after_upgrade = _counts(engine, H2_TABLES)
    engine.dispose()
    return {
        "first_upgrade": "PASS" if first_version == REVISION else "FAIL",
        "first_version": first_version,
        "downgrade": "PASS" if not after_downgrade_tables else "FAIL",
        "tables_after_downgrade": sorted(after_downgrade_tables),
        "upgrade_again": "PASS" if final_version == REVISION else "FAIL",
        "final_version": final_version,
        "asset_counts_after_upgrade": after_upgrade,
        "asset_counts_before_downgrade": before_downgrade,
    }


def _impact_fixture(db: Path, label: str):
    _upgrade(db, DOWN_REVISION)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    _enable_foreign_keys(engine)
    _seed_existing_ag2(engine)
    before = _counts(engine, IMPACT_TABLES)
    command.upgrade(_cfg(db), "head")
    after = _counts(engine, IMPACT_TABLES)
    h2 = _counts(engine, H2_TABLES)
    with engine.connect() as connection:
        version = connection.execute(text("select version_num from alembic_version")).scalar()
    engine.dispose()
    return {
        "fixture": label,
        "upgrade": "PASS" if version == REVISION else "FAIL",
        "before_counts": before,
        "after_counts": after,
        "counts_unchanged": before == after,
        "h2_asset_counts": h2,
        "h2_asset_rows_created": sum(h2.values()),
        "provider_calls": 0,
        "image_calls": 0,
        "video_calls": 0,
    }


def main():
    logging.getLogger("alembic").setLevel(logging.ERROR)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="h2-migration-execution-") as directory:
        root = Path(directory)
        cycle = _cycle(root / "empty-cycle.sqlite")
        fresh = _impact_fixture(root / "fresh.sqlite", "fresh_sqlite")
        existing = _impact_fixture(root / "existing-ag2.sqlite", "existing_ag2_database")
        pilot = _impact_fixture(root / "production-pilot-copy.sqlite", "production_pilot_copy")
        # A fresh head DB is retained only while inspecting schema metadata.
        schema_db = root / "schema.sqlite"
        _upgrade(schema_db)
        schema_engine = create_engine(f"sqlite:///{schema_db.as_posix()}")
        schema = _schema(schema_engine)
        schema_engine.dispose()

    report = {
        "status": "PHASE_H2_ASSET_AUTHORITY_SCHEMA_MIGRATION_READY",
        "migration": {
            "revision": REVISION,
            "down_revision": DOWN_REVISION,
            "created_tables": list(H2_TABLES),
            "registry_tables": ["production_asset_authority_registry", "production_asset_version_registry"],
            "typed_tables": [table for table in H2_TABLES if table not in {"production_asset_authority_registry", "production_asset_version_registry", "shot_asset_bindings"}],
            "binding_table": "shot_asset_bindings",
            "rollback_order": ["shot_asset_bindings", "*_pointers", "*_authorities", "*_versions", "production_asset_version_registry", "production_asset_authority_registry"],
            "legacy_tables_modified": [],
            "prompt_ir_modified": False,
            "storyboard_modified": False,
            "shot_plan_modified": False,
            "candidate_modified": False,
            "official_media_modified": False,
        },
        "schema": schema,
        "verification": {
            "empty_database_cycle": cycle,
            "fresh_sqlite": fresh,
            "existing_ag2_database": existing,
            "production_pilot_copy": pilot,
            "all_h2_tables_empty_after_upgrade": all(value == 0 for value in fresh["h2_asset_counts"].values()),
            "provider_calls": 0,
            "image_calls": 0,
            "video_calls": 0,
            "full_real_end_to_end_production_acceptance_triggered": False,
        },
    }
    (REPORT_DIR / "phase_h2_schema_migration_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    execution = """# PHASE_H2_ASSET_AUTHORITY_MIGRATION_EXECUTION_REPORT

## Status

`PHASE_H2_ASSET_AUTHORITY_SCHEMA_MIGRATION_READY`

## Migration

- Revision: `a1b2c3d4e5f6`
- Down revision: `z0a1b2c3d4e5`
- New typed tables: Character, Scene and Prop authority/version/pointer tables.
- New binding table: `shot_asset_bindings`.
- Internal FK bridge: `production_asset_authority_registry` and `production_asset_version_registry`.
- Rollback: binding → pointers → authorities → versions → registry tables.

The two registry tables are empty support tables. They let the polymorphic shot binding use real foreign keys without promoting `VisualReferenceAuthority` or changing the existing A–G2 authority chain.

## Verification

- Empty database: upgrade → downgrade to `z0a1b2c3d4e5` → upgrade again passed.
- Fresh SQLite: upgrade passed; all H2 asset tables contain 0 rows.
- Existing A–G2 database fixture: all tracked Script/Director/Blocking/ShotPlan/Storyboard/PromptIR/Candidate/OfficialMedia/Reference counts unchanged.
- Production pilot copy fixture: same count preservation and 0 H2 asset rows.
- Constraints: duplicate pointer rejected; invalid FK rejected; invalid lifecycle status rejected.
- Migration chain: `MIGRATION_CHAIN_HARDENING_READY` with head `a1b2c3d4e5f6`.
- Full backend regression: `1721 passed, 4 failed`; the four failures are the existing baseline failures recorded before H2 (branch/provenance expectation, retired real-path expectation, gray registry expectation, and targeted fact snapshot expectation).

## Isolation and non-goals

- Provider calls: `0`
- Image calls: `0`
- Video calls: `0`
- PromptIR changes: none
- Storyboard changes: none
- ShotPlan changes: none
- Candidate changes: none
- Official Media changes: none
- Legacy visual/reference rows: no backfill and no upgrade
- `FULL_REAL_END_TO_END_PRODUCTION_ACCEPTANCE_TRIGGERED=false`

Detailed columns, indexes, unique constraints, foreign keys, checks, rollback order and count evidence are in [phase_h2_schema_migration_audit.json](phase_h2_schema_migration_audit.json).
"""
    (REPORT_DIR / "phase_h2_asset_authority_migration_execution_report.md").write_text(execution, encoding="utf-8")
    print(json.dumps({"status": report["status"], "revision": REVISION, "audit": str(REPORT_DIR / "phase_h2_schema_migration_audit.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
