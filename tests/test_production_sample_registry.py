import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).parents[1] / "scripts" / "validate-production-sample-registry.py"
_SPEC = importlib.util.spec_from_file_location("validate_production_sample_registry", _SCRIPT)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

_REGISTER_SCRIPT = Path(__file__).parents[1] / "scripts" / "register-production-sample.py"
_REGISTER_SPEC = importlib.util.spec_from_file_location("register_production_sample", _REGISTER_SCRIPT)
assert _REGISTER_SPEC and _REGISTER_SPEC.loader
_REGISTER_MODULE = importlib.util.module_from_spec(_REGISTER_SPEC)
_REGISTER_SPEC.loader.exec_module(_REGISTER_MODULE)

_SCHEDULED_BACKUP_SCRIPT = Path(__file__).parents[1] / "scripts" / "scheduled-database-backup.py"
_SCHEDULED_BACKUP_SPEC = importlib.util.spec_from_file_location("scheduled_database_backup", _SCHEDULED_BACKUP_SCRIPT)
assert _SCHEDULED_BACKUP_SPEC and _SCHEDULED_BACKUP_SPEC.loader
_SCHEDULED_BACKUP_MODULE = importlib.util.module_from_spec(_SCHEDULED_BACKUP_SPEC)
_SCHEDULED_BACKUP_SPEC.loader.exec_module(_SCHEDULED_BACKUP_MODULE)


def test_registry_validation_accepts_existing_project_with_script_and_shots():
    result = _MODULE.validate_registry_payload(
        {"active_book_ids": [990400], "retired_book_ids": []},
        books=[990400],
        scripts_by_book={990400: 1},
        shots_by_book={990400: 3},
    )
    assert result["ok"] is True
    assert result["errors"] == []
    assert result["available_candidates"] == []


def test_registry_validation_reports_unregistered_real_candidates_without_activating_them():
    result = _MODULE.validate_registry_payload(
        {"active_book_ids": [990400], "retired_book_ids": []},
        books=[990400, 990401],
        scripts_by_book={990400: 1, 990401: 1},
        shots_by_book={990400: 3, 990401: 12},
    )
    assert result["ok"] is True
    assert result["active"] == [990400]
    assert result["available_candidates"] == [{"book_id": 990401, "scripts": 1, "shots": 12}]
    assert result["orphan_evidence"] == []


def test_registry_validation_reports_orphan_evidence_without_promoting_it():
    result = _MODULE.validate_registry_payload(
        {"active_book_ids": [990400], "retired_book_ids": []},
        books=[990400],
        scripts_by_book={990400: 1, 991119: 2},
        shots_by_book={990400: 3, 991119: 4},
    )
    assert result["ok"] is True
    assert result["available_candidates"] == []
    assert result["orphan_evidence"] == [991119]
    assert any("orphan evidence book 991119" in warning for warning in result["warnings"])


def test_registry_validation_rejects_missing_evidence_and_active_retired_overlap():
    result = _MODULE.validate_registry_payload(
        {"active_book_ids": [1, 2], "retired_book_ids": [2]},
        books=[1],
        scripts_by_book={1: 0},
        shots_by_book={},
    )
    assert result["ok"] is False
    assert "active and retired sets overlap: [2]" in result["errors"]
    assert "active book 1 has no non-empty Script evidence" in result["errors"]
    assert "active book 1 has no StoryboardShot evidence" in result["errors"]
    assert "active book 2 does not exist in the database" in result["errors"]


def test_registry_validation_rejects_non_array_registry_fields():
    result = _MODULE.validate_registry_payload(
        {"active_book_ids": "990400", "retired_book_ids": []},
        books=[],
        scripts_by_book={},
        shots_by_book={},
    )
    assert result["ok"] is False
    assert result["errors"] == ["active_book_ids and retired_book_ids must be arrays"]


def test_registration_is_dry_run_without_explicit_confirmation():
    result = _REGISTER_MODULE.build_registration_plan(
        {"active_book_ids": [990400], "retired_book_ids": []},
        book_id=990401,
        book_exists=True,
        script_count=1,
        shot_count=12,
        confirmed=False,
    )
    assert result["ok"] is True
    assert result["requires_confirmation"] is True
    assert result["would_write"] is False
    assert result["next_active_book_ids"] == [990400, 990401]


def test_registration_requires_explicit_unretire_for_retired_book():
    result = _REGISTER_MODULE.build_registration_plan(
        {"active_book_ids": [], "retired_book_ids": [990306]},
        book_id=990306,
        book_exists=True,
        script_count=1,
        shot_count=2,
        confirmed=True,
    )
    assert result["ok"] is False
    assert "retired" in result["errors"][0]


def test_registration_rejects_dirty_registry_instead_of_normalizing_it():
    result = _REGISTER_MODULE.build_registration_plan(
        {"active_book_ids": [990400, 990400, "bad"], "retired_book_ids": [990400]},
        book_id=990401,
        book_exists=True,
        script_count=1,
        shot_count=12,
        confirmed=True,
    )
    assert result["ok"] is False
    assert any("duplicate" in error for error in result["errors"])
    assert any("non-positive or non-integer" in error for error in result["errors"])
    assert any("overlap" in error for error in result["errors"])


def test_registration_registry_write_is_atomic(tmp_path):
    registry = tmp_path / "production-sample-registry.json"
    payload = {"schema_version": 1, "active_book_ids": [990400], "retired_book_ids": []}
    _REGISTER_MODULE.atomically_write_registry(registry, payload)
    assert registry.read_text(encoding="utf-8") == '{\n  "schema_version": 1,\n  "active_book_ids": [\n    990400\n  ],\n  "retired_book_ids": []\n}\n'
    assert list(tmp_path.glob("*.tmp")) == []


def test_batch_registration_is_all_or_nothing_when_one_candidate_is_invalid():
    plan = _REGISTER_MODULE.build_batch_registration_plan(
        {"active_book_ids": [990400], "retired_book_ids": []},
        candidates=[
            {"book_id": 990401, "book_exists": True, "script_count": 1, "shot_count": 12},
            {"book_id": 990402, "book_exists": False, "script_count": 0, "shot_count": 0},
        ],
        confirmed=True,
    )
    assert plan["ok"] is False
    assert plan["would_write"] is False
    assert plan["next_active_book_ids"] == [990400, 990401]


def test_batch_registration_requires_one_confirmation_for_all_candidates():
    plan = _REGISTER_MODULE.build_batch_registration_plan(
        {"active_book_ids": [990400], "retired_book_ids": []},
        candidates=[
            {"book_id": 990401, "book_exists": True, "script_count": 1, "shot_count": 12},
            {"book_id": 990402, "book_exists": True, "script_count": 1, "shot_count": 8},
        ],
        confirmed=False,
    )
    assert plan["ok"] is True
    assert plan["requires_confirmation"] is True
    assert plan["would_write"] is False
    assert plan["next_active_book_ids"] == [990400, 990401, 990402]


def test_timestamped_backup_path_is_unique_and_sanitizes_prefix(tmp_path):
    output = _SCHEDULED_BACKUP_MODULE.timestamped_output(tmp_path, prefix="production / backup")
    assert output.parent == tmp_path.resolve()
    assert output.name.startswith("production---backup-")
    assert output.suffix == ".sqlite"
