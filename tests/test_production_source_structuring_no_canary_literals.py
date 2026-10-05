"""Static production-core hardcode audit for the generalized source path."""
from __future__ import annotations

import ast
from scripts.source_structuring_scanner import scan_source_text
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ("990402", "CH03", "林晚", "顾沉", "也许是你自己", "第三章 没有底片的暗房", "f77d206835ad01882841e6e3c864de7543fbcf478a39cab3ad0bbce90722939a", "190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1")


def _production_paths() -> list[Path]:
    return sorted((ROOT / "core").rglob("*.py")) + sorted((ROOT / "api").rglob("*.py"))


def test_strict_source_structuring_boundary_has_zero_semantic_canary_hits():
    strict = [
        ROOT / "core" / "source_structuring_v3.py",
        ROOT / "core" / "script_ir.py",
        ROOT / "core" / "script_ir_production_preparation.py",
        ROOT / "core" / "script_ir_source_requirements.py",
        ROOT / "api" / "script_ir_preparation_api.py",
    ]
    hits = [hit for path in strict for hit in scan_source_text(path.read_text(encoding="utf-8"), path=str(path), forbidden=FORBIDDEN)]
    assert hits == [], hits


def test_whole_core_api_scan_is_inventory_only():
    hits = [(str(path), literal) for path in _production_paths() for literal in FORBIDDEN if literal in path.read_text(encoding="utf-8")]
    assert isinstance(hits, list)


def test_source_structuring_ast_has_no_literal_specific_branch():
    violations: list[tuple[str, int, str]] = []
    for path in ROOT.glob("core/source_structuring*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                literals = [part.value for part in [node.left, *node.comparators] if isinstance(part, ast.Constant) and isinstance(part.value, str)]
                if any(value in FORBIDDEN for value in literals):
                    violations.append((str(path), node.lineno, "literal comparison"))
    assert violations == []
