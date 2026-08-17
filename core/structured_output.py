"""Helpers for resilient structured LLM output parsing and debug capture."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def strip_code_fences(raw: str) -> str:
    text = str(raw or "").strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _extract_balanced_json_object_fragments(text: str, *, limit: int = 12) -> list[str]:
    source = str(text or "")
    fragments: list[str] = []
    start_positions = [index for index, char in enumerate(source) if char == "{"]
    for start in start_positions:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(source)):
            char = source[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                depth += 1
                continue
            if char == "}":
                depth -= 1
                if depth == 0:
                    fragment = source[start:index + 1].strip()
                    if fragment:
                        fragments.append(fragment)
                        if len(fragments) >= limit:
                            return fragments
                        break
        # keep searching later starts if this one never closed
    return fragments


def _candidate_score(payload: dict[str, Any], candidate: str, required_keys: set[str]) -> tuple[int, int, int]:
    payload_keys = {key for key in payload.keys() if isinstance(key, str)}
    required_hits = len(payload_keys & required_keys)
    return (
        required_hits,
        len(payload_keys),
        len(candidate),
    )

def parse_json_object(
    raw: str,
    *,
    label: str = "structured payload",
    required_keys: set[str] | None = None,
) -> dict[str, Any]:
    text = strip_code_fences(raw)
    if not text:
        raise ValueError(f"{label} is empty.")

    candidates = [text]
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        fragment = text[start:end].strip()
        if fragment and fragment not in candidates:
            candidates.append(fragment)
    for fragment in _extract_balanced_json_object_fragments(text):
        if fragment not in candidates:
            candidates.append(fragment)

    last_error: Exception | None = None
    required = {key for key in (required_keys or set()) if isinstance(key, str) and key}
    parsed_candidates: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except Exception as exc:
            last_error = exc
            continue
        if not isinstance(payload, dict):
            last_error = ValueError(f"{label} is not a JSON object.")
            continue
        parsed_candidates.append((_candidate_score(payload, candidate, required), payload))

    if parsed_candidates:
        parsed_candidates.sort(key=lambda item: item[0], reverse=True)
        best_payload = parsed_candidates[0][1]
        if required and not (set(best_payload.keys()) & required):
            preview = text[:500]
            raise ValueError(
                f"Failed to parse {label}: no candidate contained required keys {sorted(required)}. "
                f"Preview: {preview}"
            ) from last_error
        return best_payload

    preview = text[:500]
    raise ValueError(f"Failed to parse {label}: {preview}") from last_error


def write_debug_output(path: str | Path, raw: str) -> None:
    file_path = Path(path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(str(raw or ""), encoding="utf-8")
    except OSError as exc:  # pragma: no cover - best effort debug path
        logger.warning("Failed to write debug output %s: %s", file_path, exc)
