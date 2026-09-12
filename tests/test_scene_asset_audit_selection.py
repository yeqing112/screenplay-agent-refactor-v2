import importlib.util
import json
from pathlib import Path


_SCRIPT = Path(__file__).parents[1] / "scripts" / "audit-storyboard-scene-asset-readiness.py"
_SPEC = importlib.util.spec_from_file_location("scene_asset_audit", _SCRIPT)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_default_selection_reads_active_registry(monkeypatch, tmp_path):
    monkeypatch.delenv("SCENE_ASSET_AUDIT_BOOK_IDS", raising=False)
    registry = tmp_path / "production-sample-registry.json"
    registry.write_text(json.dumps({"active_book_ids": [990400, 990401], "retired_book_ids": [75]}), encoding="utf-8")
    monkeypatch.setattr(_MODULE, "SAMPLE_REGISTRY_PATH", registry)
    assert _MODULE.parse_book_ids() == [990400, 990401]


def test_explicit_selection_overrides_registry(monkeypatch, tmp_path):
    monkeypatch.setenv("SCENE_ASSET_AUDIT_BOOK_IDS", "7,8")
    monkeypatch.setattr(_MODULE, "SAMPLE_REGISTRY_PATH", tmp_path / "missing.json")
    assert _MODULE.parse_book_ids() == [7, 8]


def test_empty_registry_fails_closed(monkeypatch, tmp_path):
    monkeypatch.delenv("SCENE_ASSET_AUDIT_BOOK_IDS", raising=False)
    registry = tmp_path / "production-sample-registry.json"
    registry.write_text(json.dumps({"active_book_ids": []}), encoding="utf-8")
    monkeypatch.setattr(_MODULE, "SAMPLE_REGISTRY_PATH", registry)
    try:
        _MODULE.parse_book_ids()
    except RuntimeError as exc:
        assert "No active production sample IDs" in str(exc)
    else:
        raise AssertionError("expected empty registry to fail closed")
