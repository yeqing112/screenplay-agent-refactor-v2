"""Single, fail-closed resolver for Director Creative patch paths.

Provider payloads use several wire representations for the same creative
field.  This module is the only place that interprets those representations.
It deliberately performs no fuzzy matching and never chooses a target when a
path is ambiguous.  Contract/validator code remains responsible for applying
the resolved path and for immutable/fact checks.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping


FIELD_ALIASES: dict[str, str] = {
    "shot-size": "shot_size",
    "shotsize": "shot_size",
    "shotSize": "shot_size",
    "cameraMovement": "movement",
    "camera_movement": "movement",
    "cameraSpeed": "speed",
    "cameraSide": "camera_side",
    "cameraAngle": "angle",
    "cutReason": "cut_reason",
    "cut-reason": "cut_reason",
    "holdAfterActionSeconds": "hold_after_action_seconds",
    "hold-after-action-seconds": "hold_after_action_seconds",
    "whyThisShot": "why_this_shot",
    "dramaticFunction": "dramatic_function",
    "visualEmphasis": "visual_emphasis",
    "performanceDirection": "performance_direction",
    "informationStrategy": "information_strategy",
}


class PatchPathResolutionError(ValueError):
    """Raised when a provider path cannot be resolved without guessing."""

    code = "AMBIGUOUS_PATCH_PATH"

    def __init__(self, message: str, *, code: str | None = None, raw_path: str = "") -> None:
        super().__init__(message)
        self.code = code or self.code
        self.raw_path = raw_path


@dataclass(frozen=True)
class ResolvedPatchPath:
    plan_shot_id: str
    path: str
    raw_path: str
    source_format: str
    alias_hit: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan_shot_id": self.plan_shot_id,
            "path": self.path,
            "raw_path": self.raw_path,
            "source_format": self.source_format,
            "alias_hit": self.alias_hit,
        }


_SHOT_ID_RE = re.compile(r"^S\d+$", re.IGNORECASE)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _segment(value: Any) -> tuple[str, bool]:
    token = _text(value)
    if not token:
        return "", False
    mapped = FIELD_ALIASES.get(token)
    if mapped is not None:
        return mapped, mapped != token
    return token, False


def _allowed_relative_paths(allowed_patch_paths: Iterable[str] | None) -> set[str]:
    result: set[str] = set()
    for raw in allowed_patch_paths or ():
        text = _text(raw)
        if not text:
            continue
        parts = [part for part in text.replace(".", "/").split("/") if part]
        if parts and parts[0] == "shots":
            parts = parts[2:]
        normalized: list[str] = []
        for part in parts:
            mapped, _ = _segment(part)
            normalized.append(mapped)
        if normalized:
            result.add(".".join(normalized))
    return result


def _matches_allowed(path: str, allowed: set[str]) -> bool:
    if not allowed:
        return True
    parts = path.split(".")
    for pattern in allowed:
        pattern_parts = pattern.split(".")
        if len(parts) != len(pattern_parts):
            continue
        if all(expected == "*" or expected == actual for actual, expected in zip(parts, pattern_parts)):
            return True
    return False


def resolve_patch_path(
    raw_path: Any,
    *,
    plan_shot_id: str = "",
    known_plan_shot_ids: Iterable[str] | None = None,
    allowed_patch_paths: Iterable[str] | None = None,
) -> ResolvedPatchPath:
    """Resolve one provider path to ``plan_shot_id + relative dotted path``.

    Supported wire forms include JSON pointers, slash/dotted paths, wildcard
    selectors and an explicit ``S03.`` prefix.  A wildcard or numeric selector
    is accepted only when it can be tied to the declared target and known plan
    IDs.  Unknown or ambiguous selectors fail closed.
    """

    declared = _text(plan_shot_id)
    raw = _text(raw_path)
    if not raw:
        raise PatchPathResolutionError("patch path is required", code="DIRECTOR_PATCH_PATH_MISSING", raw_path=raw)
    if "\\" in raw or ".." in raw:
        raise PatchPathResolutionError("patch path contains unsafe traversal", code="DIRECTOR_PATCH_PATH_FORBIDDEN", raw_path=raw)

    # A mapping is accepted for callers that pass the complete target object.
    if isinstance(raw_path, Mapping):
        if raw_path.get("path") is None:
            raise PatchPathResolutionError("path is required", code="DIRECTOR_PATCH_PATH_MISSING", raw_path=raw)
        object_target = _text(raw_path.get("plan_shot_id"))
        if declared and object_target and declared != object_target:
            raise PatchPathResolutionError("declared and embedded plan_shot_id differ", code="AMBIGUOUS_PATCH_PATH", raw_path=raw)
        declared = declared or object_target
        raw = _text(raw_path.get("path"))
        if not raw:
            raise PatchPathResolutionError("path is required", code="DIRECTOR_PATCH_PATH_MISSING", raw_path=raw)

    # Split both slash and dot forms.  Hyphenated leaf aliases are normalized
    # by _segment, never by fuzzy similarity.
    parts_raw = [part for part in re.split(r"[/.]", raw) if _text(part)]
    if not parts_raw:
        raise PatchPathResolutionError("patch path is empty", code="DIRECTOR_PATCH_PATH_MISSING", raw_path=raw)
    parts: list[str] = []
    alias_hit = False
    for part in parts_raw:
        mapped, hit = _segment(part)
        if not mapped:
            raise PatchPathResolutionError("patch path contains an empty segment", code="DIRECTOR_PATCH_PATH_FORBIDDEN", raw_path=raw)
        parts.append(mapped)
        alias_hit = alias_hit or hit

    source_format = "relative"
    selector: str | None = None
    if parts[0] == "shots":
        source_format = "json_pointer" if raw.startswith("/") else "shots_prefix"
        if len(parts) < 3:
            raise PatchPathResolutionError("shot path must address a field", code="DIRECTOR_PATCH_PATH_FORBIDDEN", raw_path=raw)
        selector = parts[1]
        parts = parts[2:]
    else:
        known = {_text(item) for item in (known_plan_shot_ids or ()) if _text(item)}
        if declared and parts[0] == declared:
            selector = parts.pop(0)
            source_format = "shot_prefix"
        elif parts[0] == "*":
            selector = "*"
            parts = parts[1:]
        elif parts[0] in known or _SHOT_ID_RE.match(parts[0] or ""):
            # S03.camera.shot_size is unambiguous as a target-prefixed form;
            # existence is checked downstream against the plan/known IDs.
            selector = parts.pop(0)
            source_format = "shot_prefix"

    known_list = [_text(item) for item in (known_plan_shot_ids or ()) if _text(item)]
    if selector is not None:
        if selector == "*":
            if not declared:
                raise PatchPathResolutionError("wildcard selector requires declared plan_shot_id", code="AMBIGUOUS_PATCH_PATH", raw_path=raw)
        elif selector.isdigit():
            if not known_list:
                # An explicit declared target is sufficient to bind a
                # provider-local numeric selector.  Without that declaration
                # there is no safe way to know which shot index is intended.
                if not declared:
                    raise PatchPathResolutionError("numeric selector requires known plan_shot_ids or declared plan_shot_id", code="AMBIGUOUS_PATCH_PATH", raw_path=raw)
            else:
                index = int(selector)
                if index < 0 or index >= len(known_list):
                    raise PatchPathResolutionError("numeric selector is out of range", code="DIRECTOR_PATCH_TARGET_MISMATCH", raw_path=raw)
                selected = known_list[index]
                if declared and selected != declared:
                    raise PatchPathResolutionError("shot path targets a different plan_shot_id", code="DIRECTOR_PATCH_TARGET_MISMATCH", raw_path=raw)
                declared = selected
        elif declared and selector != declared:
            raise PatchPathResolutionError("shot path targets a different plan_shot_id", code="DIRECTOR_PATCH_TARGET_MISMATCH", raw_path=raw)
        else:
            declared = declared or selector

    if not declared and selector is not None:
        raise PatchPathResolutionError("plan_shot_id is required to resolve a shot-qualified path", code="AMBIGUOUS_PATCH_PATH", raw_path=raw)
    if not parts:
        raise PatchPathResolutionError("patch path must address a field", code="DIRECTOR_PATCH_PATH_FORBIDDEN", raw_path=raw)
    path = ".".join(parts)
    allowed = _allowed_relative_paths(allowed_patch_paths)
    if not _matches_allowed(path, allowed):
        raise PatchPathResolutionError(
            f"resolved path is not in allowed_patch_paths: {path}",
            code="DIRECTOR_PATCH_PATH_FORBIDDEN",
            raw_path=raw,
        )
    return ResolvedPatchPath(plan_shot_id=declared, path=path, raw_path=raw, source_format=source_format, alias_hit=alias_hit)


def canonical_path(
    raw_path: Any,
    *,
    plan_shot_id: str = "",
    known_plan_shot_ids: Iterable[str] | None = None,
    allowed_patch_paths: Iterable[str] | None = None,
) -> str:
    """Convenience wrapper returning only the canonical relative path."""

    return resolve_patch_path(
        raw_path,
        plan_shot_id=plan_shot_id,
        known_plan_shot_ids=known_plan_shot_ids,
        allowed_patch_paths=allowed_patch_paths,
    ).path


__all__ = [
    "FIELD_ALIASES",
    "PatchPathResolutionError",
    "ResolvedPatchPath",
    "resolve_patch_path",
    "canonical_path",
]
