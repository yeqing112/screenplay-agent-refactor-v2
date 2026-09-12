"""Selection guardrails for the real storyboard LLM gray runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "validate-storyboard-real-llm-gray.py"
SPEC = importlib.util.spec_from_file_location("storyboard_real_llm_gray", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_default_scope_uses_active_registry(monkeypatch):
    monkeypatch.delenv("STORYBOARD_REAL_LLM_GRAY_BOOK_IDS", raising=False)
    assert MODULE.parse_book_ids() == [990400]


def test_explicit_scope_remains_operator_controlled(monkeypatch):
    monkeypatch.setenv("STORYBOARD_REAL_LLM_GRAY_BOOK_IDS", "42, 43, 42")
    assert MODULE.parse_book_ids() == [42, 43, 42]
