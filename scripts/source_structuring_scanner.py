"""Safe semantic scanner for source-structuring canary dependencies.

It evaluates only constant AST expressions and simple top-level assignments.
It never imports or executes the scanned module.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Iterable

FORBIDDEN_CANARY_TOKENS = (
    "990402",
    "CH03",
    "林晚",
    "顾沉",
    "也许是你自己",
    "第三章 没有底片的暗房",
    "f77d206835ad01882841e6e3c864de7543fbcf478a39cab3ad0bbce90722939a",
    "190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1",
)


class _Unknown:
    pass


UNKNOWN = _Unknown()


def _constant(node: ast.AST, env: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)):
        return node.value
    if isinstance(node, ast.Name):
        return env.get(node.id, UNKNOWN)
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
                continue
            if isinstance(value, ast.FormattedValue):
                rendered = _constant(value.value, env)
                if rendered is UNKNOWN:
                    return UNKNOWN
                if value.format_spec is not None:
                    spec = _constant(value.format_spec, env)
                    if spec is UNKNOWN:
                        return UNKNOWN
                    parts.append(format(rendered, str(spec)))
                else:
                    parts.append(str(rendered))
                continue
            return UNKNOWN
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mult)):
        left, right = _constant(node.left, env), _constant(node.right, env)
        if left is UNKNOWN or right is UNKNOWN:
            return UNKNOWN
        if isinstance(node.op, ast.Add) and type(left) is type(right) and isinstance(left, (str, int, float)):
            return left + right
        if isinstance(node.op, ast.Mult) and ((isinstance(left, str) and isinstance(right, int)) or (isinstance(right, str) and isinstance(left, int))):
            return left * right
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _constant(node.operand, env)
        if value is not UNKNOWN and isinstance(value, (int, float)):
            return +value if isinstance(node.op, ast.UAdd) else -value
    return UNKNOWN


def _iter_statements(nodes: list[ast.stmt]) -> Iterable[ast.AST]:
    """Yield nodes in source order while preserving nested scopes."""
    for statement in nodes:
        yield statement
        for child in ast.iter_child_nodes(statement):
            if isinstance(child, ast.stmt):
                yield from _iter_statements([child])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.If, ast.For, ast.While, ast.Try, ast.With)):
                body = getattr(child, "body", None)
                if isinstance(body, list):
                    yield from _iter_statements(body)


def scan_source_text(source: str, *, path: str = "<memory>", forbidden: tuple[str, ...] = FORBIDDEN_CANARY_TOKENS) -> list[dict[str, Any]]:
    tree = ast.parse(source, filename=path)
    env: dict[str, Any] = {}
    hits: list[dict[str, Any]] = []
    seen: set[tuple[int, str, str]] = set()
    # Evaluate assignments in source order. This catches Unicode escapes,
    # arithmetic and f-string reconstruction without importing or executing.
    ordered = list(_iter_statements(tree.body))
    for node in ordered:
        values_to_scan: list[Any] = []
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            value = _constant(node.value, env)
            values_to_scan.append(value)
            targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            if value is not UNKNOWN:
                for target in targets:
                    if isinstance(target, ast.Name):
                        env[target.id] = value
        values_to_scan.append(_constant(node, env))
        for value in values_to_scan:
            if value is UNKNOWN or not isinstance(value, (str, int, float)):
                continue
            rendered = str(value)
            for token in forbidden:
                if token in rendered:
                    key = (getattr(node, "lineno", 0), token, rendered)
                    if key not in seen:
                        seen.add(key)
                        hits.append({"path": path, "line": getattr(node, "lineno", 0), "token": token, "value": rendered, "detection": "SEMANTIC_CONSTANT"})
    return hits


def scan_paths(paths: Iterable[Path], *, forbidden: tuple[str, ...] = FORBIDDEN_CANARY_TOKENS) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        hits.extend(scan_source_text(text, path=str(path), forbidden=forbidden))
    return hits


__all__ = ["FORBIDDEN_CANARY_TOKENS", "scan_source_text", "scan_paths"]
