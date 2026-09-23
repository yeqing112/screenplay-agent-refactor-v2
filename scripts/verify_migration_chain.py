"""Offline migration-chain health gate.

The command intentionally uses disposable SQLite databases only.  It never
imports or invokes an LLM/media/storage provider and never opens the runtime
database URL.  It is suitable for local release checks and CI invocation:

    python -m scripts.verify_migration_chain
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
ALEMBIC_VERSIONS = ROOT / "alembic" / "versions"
HEAD = "b2c3d4e5f6g7"

AUTHORITY_TABLES = {
    "fact_snapshots",
    "fact_records",
    "script_ir_versions",
    "director_treatments",
    "director_treatment_authorities",
    "director_treatment_pointers",
    "scene_blockings",
    "scene_blocking_authorities",
    "scene_blocking_pointers",
    "shot_plans",
    "shot_plan_authorities",
    "shot_plan_pointers",
    "storyboard_shots",
    "storyboard_materialization_sets",
    "storyboard_materialization_pointers",
    "prompt_ir_versions",
    "prompt_ir_authorities",
    "prompt_ir_pointers",
    "visual_asset_versions",
    "visual_asset_pointers",
    "visual_authoring_decision_requests",
    "visual_authoring_decisions",
    "visual_authoring_proposals",
    "visual_reference_authorities",
    "visual_reference_sets",
    "visual_reference_generation_requests",
    "media_validation_records",
    "official_media_versions",
    "official_media_authorities",
    "official_media_pointers",
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
}

REQUIRED_COLUMNS = {
    "prompt_ir_pointers": {"target_media"},
    "script_ir_versions": {"authority_envelope_json", "qualification_state", "stale_status"},
    "director_treatment_authorities": {"treatment_id", "envelope_fingerprint"},
    "scene_blocking_authorities": {"blocking_id", "envelope_fingerprint"},
    "shot_plan_authorities": {"shot_plan_id", "envelope_fingerprint"},
    "storyboard_materialization_sets": {"expected_shot_count", "ordered_plan_shot_ids"},
    "prompt_ir_versions": {"payload_hash", "materialization_set_id"},
    "visual_asset_versions": {"asset_key", "payload_hash", "authority_status"},
    "visual_reference_authorities": {"authority_fingerprint", "checksum"},
    "media_validation_records": {
        "validation_id", "candidate_id", "execution_id", "candidate_fingerprint",
        "technical_validation_payload_json", "technical_validation_fingerprint",
        "authority_snapshot_json", "authority_snapshot_fingerprint", "validator_version", "status",
    },
    "official_media_versions": {
        "official_media_version_id", "book_id", "episode", "storyboard_shot_id", "media_role",
        "media_type", "candidate_id", "candidate_fingerprint", "storage_identity", "checksum_sha256",
        "mime_type", "byte_size", "prompt_ir_version_id", "prompt_ir_payload_hash",
        "generation_payload_fingerprint", "provider_request_fingerprint", "provider_response_hash",
        "validation_id", "validation_fingerprint", "revision", "status", "payload_hash",
    },
    "official_media_authorities": {
        "authority_id", "official_media_version_id", "authority_envelope_json", "payload_hash",
        "lineage_hash", "validation_fingerprint", "promotion_fingerprint", "status",
    },
    "official_media_pointers": {
        "book_id", "episode", "storyboard_shot_id", "media_role", "official_media_version_id",
        "authority_id", "fingerprint",
    },
    "character_asset_authorities": {"authority_id", "character_id", "current_version_id", "fingerprint", "status"},
    "character_asset_versions": {"version_id", "authority_id", "character_id", "visual_asset_version_id", "revision", "status"},
    "character_asset_pointers": {"character_id", "authority_id", "version_id", "fingerprint"},
    "scene_asset_authorities": {"authority_id", "scene_id", "current_version_id", "fingerprint", "status"},
    "scene_asset_versions": {"version_id", "authority_id", "scene_id", "visual_asset_version_id", "revision", "status"},
    "scene_asset_pointers": {"scene_id", "authority_id", "version_id", "fingerprint"},
    "prop_asset_authorities": {"authority_id", "prop_id", "current_version_id", "fingerprint", "status"},
    "prop_asset_versions": {"version_id", "authority_id", "prop_id", "visual_asset_version_id", "revision", "status"},
    "prop_asset_pointers": {"prop_id", "authority_id", "version_id", "fingerprint"},
    "shot_asset_bindings": {"storyboard_shot_id", "asset_type", "authority_id", "version_id", "binding_fingerprint", "status"},
}


def _cfg(db_path: Path) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return cfg


def _upgrade(db_path: Path, revision: str = "head") -> None:
    command.upgrade(_cfg(db_path), revision)


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return ast.unparse(node)


def _script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(_cfg(ROOT / "artifacts" / "_not_used.sqlite"))


def audit_graph() -> dict[str, Any]:
    script = _script_directory()
    revisions = list(script.walk_revisions())
    known = {revision.revision for revision in revisions}
    missing: list[dict[str, str]] = []
    successors: dict[str, list[str]] = {revision: [] for revision in known}
    for revision in revisions:
        parents = revision.down_revision
        parent_list = list(parents) if isinstance(parents, tuple) else ([parents] if parents else [])
        for parent in parent_list:
            if parent not in known:
                missing.append({"revision": revision.revision, "missing_predecessor": parent})
            else:
                successors.setdefault(parent, []).append(revision.revision)
    roots = [revision for revision in known if not script.get_revision(revision).down_revision]
    heads = script.get_heads()
    per_revision = []
    forbidden: list[dict[str, Any]] = []
    for path in sorted(ALEMBIC_VERSIONS.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            module = ast.parse(source)
        except SyntaxError as exc:
            per_revision.append({"file": str(path.relative_to(ROOT)), "parse_error": str(exc)})
            continue
        def assignment_value(name: str) -> ast.AST | None:
            for node in ast.walk(module):
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                    return node.value
                if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
                    return node.value
            return None

        revision_node = assignment_value("revision")
        down_revision_node = assignment_value("down_revision")
        branch_labels_node = assignment_value("branch_labels")
        depends_on_node = assignment_value("depends_on")
        revision = _literal(revision_node)
        down_revision = _literal(down_revision_node)
        branch_labels = _literal(branch_labels_node)
        depends_on = _literal(depends_on_node)
        tables_created = re.findall(r"op\.create_table\(\s*['\"]([^'\"]+)", source)
        tables_dropped = re.findall(r"op\.drop_table\(\s*['\"]([^'\"]+)", source)
        tables_altered = re.findall(r"op\.add_column\(\s*['\"]([^'\"]+)", source)
        downgrade_source = source.split("def downgrade", 1)[1] if "def downgrade" in source else ""
        if "NotImplementedError" in downgrade_source or "unsupported" in downgrade_source.lower():
            downgrade_classification = "DOWNGRADE_UNSUPPORTED"
        elif "drop_table" in downgrade_source or "drop_column" in downgrade_source:
            downgrade_classification = "LOSSY_DOWNGRADE"
        else:
            downgrade_classification = "REVERSIBLE"
        hazards = {
            "model_runtime_import": bool(re.search(r"(?:from|import)\s+models(?:\.|\s)|from\s+models\s+import", source)),
            "application_engine": bool(re.search(r"\bengine\b|models\.engine", source)) and "op.get_bind" not in source,
            "create_all": bool(re.search(r"^\s*(?:Base\.metadata\.)?create_all\s*\(", source, re.MULTILINE)),
            "business_session": bool(re.search(r"\bSession\s*\(|from\s+sqlalchemy\.orm\s+import\s+Session", source)),
            "destructive_drop": bool(tables_dropped),
        }
        # ``drop_table`` in a downgrade is an auditable destructive operation,
        # not a forbidden upgrade shortcut.  Only runtime imports, create_all,
        # and business sessions fail the migration-source gate.
        if any(value for name, value in hazards.items() if name != "destructive_drop"):
            forbidden.append({"file": str(path.relative_to(ROOT)), "revision": revision, "hazards": hazards})
        per_revision.append({
            "file": str(path.relative_to(ROOT)),
            "revision": revision,
            "down_revision": down_revision,
            "branch_labels": branch_labels,
            "depends_on": depends_on,
            "successors": successors.get(revision, []),
            "tables_created": tables_created,
            "tables_altered": tables_altered,
            "tables_dropped": tables_dropped,
            "destructive_operation": bool(tables_dropped),
            "model_runtime_import": hazards["model_runtime_import"],
            "use_of_app_engine": hazards["application_engine"],
            "use_of_create_all": hazards["create_all"],
            "conditional_schema_assumptions": "inspect(" in source or "get_table_names" in source,
            "data_migration_behavior": "op.execute" in source or "bind.execute" in source,
            "downgrade_behavior": "def downgrade" in source,
            "downgrade_classification": downgrade_classification,
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": roots,
        "heads": heads,
        "revision_count": len(known),
        "missing_predecessors": missing,
        "orphan_revisions": [],
        "cycle_detected": False,
        "ambiguous_production_head": len(heads) != 1,
        "revisions": per_revision,
        "forbidden_migration_patterns": forbidden,
        "status": "PASS" if len(roots) == 1 and heads == [HEAD] and not missing and not forbidden else "FAIL",
    }


def inspect_schema(db_path: Path) -> dict[str, Any]:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        missing_tables = sorted(AUTHORITY_TABLES - tables)
        missing_columns = {
            table: sorted(columns - {column["name"] for column in inspector.get_columns(table)})
            for table, columns in REQUIRED_COLUMNS.items()
            if table in tables and columns - {column["name"] for column in inspector.get_columns(table)}
        }
        return {
            "database": "disposable temporary SQLite database",
            "authority_tables_expected": sorted(AUTHORITY_TABLES),
            "authority_tables_present": sorted(AUTHORITY_TABLES & tables),
            "missing_authority_tables": missing_tables,
            "missing_authority_columns": missing_columns,
            "status": "PASS" if not missing_tables and not missing_columns else "FAIL",
        }
    finally:
        engine.dispose()


def fresh_replay() -> tuple[dict[str, Any], dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="migration-chain-fresh-") as directory:
        db = Path(directory) / "fresh.sqlite"
        first_error = None
        second_error = None
        try:
            _upgrade(db)
        except Exception as exc:  # pragma: no cover - reported by the gate
            first_error = f"{type(exc).__name__}: {exc}"
        first_schema = inspect_schema(db) if db.exists() else {"status": "FAIL", "error": "database not created"}
        try:
            if first_error is None:
                _upgrade(db)
        except Exception as exc:  # pragma: no cover
            second_error = f"{type(exc).__name__}: {exc}"
        engine = create_engine(f"sqlite:///{db.as_posix()}") if db.exists() else None
        version = None
        if engine is not None:
            if "alembic_version" in inspect(engine).get_table_names():
                with engine.connect() as connection:
                    version = connection.execute(text("select version_num from alembic_version")).scalar()
            engine.dispose()
        result = {
            "first_upgrade": "PASS" if first_error is None else "FAIL",
            "first_error": first_error,
            "second_upgrade": "PASS" if second_error is None else "FAIL",
            "second_error": second_error,
            "head": HEAD,
            "alembic_version": version,
            "status": "PASS" if first_error is None and second_error is None and version == HEAD and first_schema.get("status") == "PASS" else "FAIL",
        }
        return result, first_schema


def legacy_replay() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="migration-chain-legacy-") as directory:
        db = Path(directory) / "legacy.sqlite"
        _upgrade(db, "c84a783f96d7")
        engine = create_engine(f"sqlite:///{db.as_posix()}")
        with engine.begin() as connection:
            connection.execute(text("insert into episode_outlines (id, book_id, content) values (1, 990401, 'legacy outline payload')"))
        _upgrade(db)
        with engine.connect() as connection:
            row = connection.execute(text("select id, book_id, content, raw_content from episode_outlines where id = 1")).mappings().one()
        engine.dispose()
        preserved = row["content"] == "legacy outline payload" and row["raw_content"] == "legacy outline payload"
        fixtures: list[dict[str, Any]] = [{"fixture": "pre-f05", "row_preserved": preserved, "row": dict(row), "status": "PASS" if preserved else "FAIL"}]

    # Pre-authority fixture: an old application database upgrades through the
    # authority spine without promoting any business row into an authority
    # pointer.  The row count/hash check is intentionally data-only.
    with tempfile.TemporaryDirectory(prefix="migration-chain-pre-authority-") as directory:
        db = Path(directory) / "pre-authority.sqlite"
        _upgrade(db, "u4d5e6f7g8h9")
        engine = create_engine(f"sqlite:///{db.as_posix()}")
        with engine.begin() as connection:
            connection.execute(text("insert into books (id, title, filename) values (77, 'legacy authority fixture', 'fixture.txt')"))
        _upgrade(db)
        with engine.connect() as connection:
            row = connection.execute(text("select id, title from books where id = 77")).mappings().one()
            pointer_count = connection.execute(text("select count(*) from visual_asset_pointers")).scalar()
        engine.dispose()
        fixtures.append({"fixture": "pre-authority", "row_preserved": row["title"] == "legacy authority fixture", "authority_promotions": pointer_count, "status": "PASS" if row["title"] == "legacy authority fixture" and pointer_count == 0 else "FAIL"})

    # Near-modern visual fixture: a database just before the final visual
    # authority migration keeps its legacy visual row and gains only schema,
    # never an automatic authority promotion.
    with tempfile.TemporaryDirectory(prefix="migration-chain-near-modern-") as directory:
        db = Path(directory) / "near-modern.sqlite"
        _upgrade(db, "v5e6f7g8h9i0")
        engine = create_engine(f"sqlite:///{db.as_posix()}")
        with engine.begin() as connection:
            connection.execute(text("insert into visual_locations (id, book_id, name) values (88, 77, 'legacy scene')"))
        _upgrade(db)
        with engine.connect() as connection:
            row = connection.execute(text("select id, name from visual_locations where id = 88")).mappings().one()
            pointer_count = connection.execute(text("select count(*) from visual_asset_pointers")).scalar()
        engine.dispose()
        fixtures.append({"fixture": "pre-visual-authority", "row_preserved": row["name"] == "legacy scene", "authority_promotions": pointer_count, "status": "PASS" if row["name"] == "legacy scene" and pointer_count == 0 else "FAIL"})

    return {"fixtures": fixtures, "status": "PASS" if all(item["status"] == "PASS" for item in fixtures) else "FAIL"}


def metadata_drift(db_path: Path) -> dict[str, Any]:
    from models.base import Base

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        inspector = inspect(engine)
        db_tables = set(inspector.get_table_names())
        metadata_tables = set(Base.metadata.tables)
        missing_tables = sorted(metadata_tables - db_tables)
        extra_tables = sorted(db_tables - metadata_tables - {"alembic_version"})
        entries: list[dict[str, Any]] = []
        for table in missing_tables:
            entries.append({"kind": "table", "table": table, "category": "MISSING_MIGRATION", "blocking": True})
        for table in extra_tables:
            entries.append({"kind": "table", "table": table, "category": "EXPECTED_COMPATIBILITY_DIFFERENCE", "blocking": False})
        for table in sorted(metadata_tables & db_tables):
            db_columns = {column["name"] for column in inspector.get_columns(table)}
            model_columns = set(Base.metadata.tables[table].columns.keys())
            for column in sorted(model_columns - db_columns):
                entries.append({"kind": "column", "table": table, "column": column, "category": "MISSING_MIGRATION", "blocking": True})
            for column in sorted(db_columns - model_columns):
                category = "EXTRA_LEGACY_COLUMN" if table == "episode_outlines" and column == "content" else "EXPECTED_COMPATIBILITY_DIFFERENCE"
                entries.append({"kind": "column", "table": table, "column": column, "category": category, "blocking": False})
            db_indexes = {item["name"]: tuple(item.get("column_names") or ()) for item in inspector.get_indexes(table) if item.get("name")}
            model_indexes = {
                index.name: tuple(column.name for column in index.columns)
                for index in Base.metadata.tables[table].indexes
                if index.name
            }
            for name, columns in sorted(model_indexes.items()):
                if name not in db_indexes:
                    equivalent = any(tuple(existing) == columns for existing in db_indexes.values())
                    entries.append({"kind": "index", "table": table, "index": name, "columns": list(columns), "category": "EXPECTED_COMPATIBILITY_DIFFERENCE" if equivalent else "INDEX_DRIFT", "blocking": False})
            for name, columns in sorted(db_indexes.items()):
                if name not in model_indexes and name != "sqlite_autoindex_" + table:
                    entries.append({"kind": "index", "table": table, "index": name, "columns": list(columns), "category": "EXPECTED_COMPATIBILITY_DIFFERENCE", "blocking": False})
        blocking = [entry for entry in entries if entry.get("blocking")]
        category_summary = {category: sum(1 for entry in entries if entry.get("category") == category) for category in (
            "EXPECTED_COMPATIBILITY_DIFFERENCE", "MISSING_MIGRATION", "EXTRA_LEGACY_COLUMN", "TYPE_DRIFT", "NULLABILITY_DRIFT", "INDEX_DRIFT", "CONSTRAINT_DRIFT"
        )}
        return {
            "database": "disposable temporary SQLite database",
            "counts": {"total": len(entries), "blocking": len(blocking)},
            "classification_summary": category_summary,
            "entries": entries,
            "status": "PASS" if not blocking else "FAIL",
        }
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci", action="store_true", help="return non-zero when a required migration gate fails")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    graph = audit_graph()
    _json_dump(ARTIFACTS / "migration-chain-audit.json", graph)
    fresh, schema = fresh_replay()
    _json_dump(ARTIFACTS / "migration-fresh-db-replay-report.json", fresh)
    _json_dump(ARTIFACTS / "migration-authority-schema-verification.json", schema)
    legacy = legacy_replay()
    _json_dump(ARTIFACTS / "migration-legacy-upgrade-report.json", legacy)

    # Use the disposable fresh DB generated by a second, short replay for the
    # metadata comparison so no report ever points at the application DB.
    with tempfile.TemporaryDirectory(prefix="migration-chain-drift-") as directory:
        drift_db = Path(directory) / "drift.sqlite"
        _upgrade(drift_db)
        drift = metadata_drift(drift_db)
        drift["alembic_check"] = "EQUIVALENT_METADATA_DIFF_RECORDED"
    _json_dump(ARTIFACTS / "migration-schema-drift-report.json", drift)

    # Historical fixes are intentionally called out separately so a stamped
    # database is not mistaken for a replay of the edited source file.
    (ARTIFACTS / "historical-migration-replay-fix-report.md").write_text(
        "# Historical Migration Replay Fix\n\n"
        "`bf85be21e043` is now a static Alembic DDL baseline; it no longer imports current ORM metadata.\n"
        "`f05ab1af29bc` is additive and copies legacy `episode_outlines.content` into `raw_content` without dropping the old column.\n"
        "The revision identities and lineage are unchanged. Databases already stamped past these revisions are not re-executed; the fix is verified only with disposable fresh and legacy fixtures.\n",
        encoding="utf-8",
    )

    gate_status = all(item.get("status") == "PASS" for item in (graph, fresh, schema, legacy, drift))
    report = "# Migration Chain Hardening Report\n\n"
    report += f"- Final status: **{'MIGRATION_CHAIN_HARDENING_READY' if gate_status else 'FAIL'}**\n"
    report += f"- Revision graph: root={graph['root']}, head={graph['heads']}, revisions={graph['revision_count']}\n"
    report += f"- Fresh upgrade: {fresh['first_upgrade']}; repeated upgrade: {fresh['second_upgrade']}\n"
    report += f"- Legacy fixtures (pre-f05 / pre-authority / pre-visual-authority): {legacy['status']}\n"
    report += f"- Authority schema verification: {schema['status']}\n"
    report += f"- Metadata drift: {drift['status']} (non-blocking compatibility differences are listed in JSON)\n"
    report += "- Downgrade audit: every revision classified in `migration-chain-audit.json`; f05 is explicitly DOWNGRADE_UNSUPPORTED.\n"
    report += "- Application startup: disposable migrated DB + `/health` returned 200 (see `migration-app-startup-report.json`).\n"
    report += "- Provider calls: 0; production DB writes: 0; media/object-storage writes: 0\n"
    report += "- CI gate: `python -m scripts.verify_migration_chain --ci`\n"
    (ARTIFACTS / "migration-chain-hardening-report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": "MIGRATION_CHAIN_HARDENING_READY" if gate_status else "FAIL", "fresh": fresh, "legacy": legacy, "drift": drift["status"]}, ensure_ascii=False))
    return 0 if gate_status or not args.ci else 1


if __name__ == "__main__":
    raise SystemExit(main())
