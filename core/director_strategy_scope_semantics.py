"""Deterministic semantic policy for Director Strategy repair scope.

Scope comparison must respect the meaning of a field.  Narrative arrays are
ordered, while reference collections are set-like and may be reordered without
changing the strategy.  This module is intentionally provider-free and has no
book/scene-specific rules.
"""
from __future__ import annotations

from collections import Counter
from typing import Any
import re


FIELD_SEMANTICS_REGISTRY: dict[str, str] = {
    "scene_phases": "ORDERED",
    "scene_phases[*].beat_ids": "ORDERED",
    "scene_phases[*].performance": "ORDERED",
    "scene_phases[*].information.reveal_refs": "SET_LIKE",
    "scene_phases[*].information.hint_refs": "SET_LIKE",
    "scene_phases[*].information.withhold_refs": "SET_LIKE",
    "scene_phases[*].information.audience_suspicions[*].support_refs": "SET_LIKE",
    "scene_phases[*].information.director_inferences[*].support_refs": "SET_LIKE",
}


def _tokens(path: str) -> list[str]:
    out: list[str] = []
    for part in str(path).split("."):
        m = re.match(r"^([^\[]+)", part)
        if m:
            out.append(m.group(1))
        for selector in re.findall(r"\[([^\]]*)\]", part):
            out.append(f"[{selector}]")
    return out


def segment_match(pattern: str, path: str) -> bool:
    """Match path segments, not substrings.

    ``[*]`` matches one selector (numeric, named phase or any other explicit
    selector).  A terminal collection pattern also matches its numeric leaves,
    but never arbitrary descendants.
    """
    p, x = _tokens(pattern), _tokens(path)
    if len(x) < len(p):
        # A collection-level diff is represented at the field itself while a
        # dependency rule may be declared for each member (`refs[*]`).
        if not (p and p[-1] == "[*]" and len(x) == len(p) - 1):
            return False
        return all(a == "[*]" or a == b for a, b in zip(p[:-1], x))
    if not all(a == "[*]" or a == b for a, b in zip(p, x)):
        return False
    if len(x) == len(p):
        return True
    return all(seg.startswith("[") and seg[1:-1].isdigit() for seg in x[len(p) :])


def field_semantics(path: str) -> str:
    """Return the most specific registered semantics for a concrete path."""
    matches = [pattern for pattern in FIELD_SEMANTICS_REGISTRY if segment_match(pattern, path)]
    if not matches:
        return "UNKNOWN"
    return FIELD_SEMANTICS_REGISTRY[max(matches, key=lambda p: len(_tokens(p)))]


def _canonical_set(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return sorted({str(v) for v in values})


def _duplicate_refs(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return sorted([key for key, count in Counter(str(v) for v in values).items() if count > 1])


def compare_set_like(base_value: Any, revised_value: Any) -> dict[str, Any]:
    """Compare a reference collection without globally sorting source JSON."""
    base_values = [str(v) for v in base_value] if isinstance(base_value, list) else []
    revised_values = [str(v) for v in revised_value] if isinstance(revised_value, list) else []
    base_set, revised_set = set(base_values), set(revised_values)
    same_order = base_values == revised_values
    same_refs_reordered = base_set == revised_set and not same_order
    base_dupes, revised_dupes = _duplicate_refs(base_values), _duplicate_refs(revised_values)
    duplicate_change = base_dupes != revised_dupes or Counter(base_values) != Counter(revised_values) and base_set == revised_set
    return {
        "added_refs": sorted(revised_set - base_set),
        "removed_refs": sorted(base_set - revised_set),
        "same_refs_reordered": same_refs_reordered,
        "base_duplicates": base_dupes,
        "revised_duplicates": revised_dupes,
        "duplicate_change": duplicate_change,
        "semantic_change": bool(base_set != revised_set or duplicate_change),
    }


def semantic_diff(base: Any, revised: Any, *, path: str = "") -> list[dict[str, Any]]:
    """Return semantic field diffs; set-like reorder is an explicit no-op."""
    semantics = field_semantics(path) if path else "UNKNOWN"
    if isinstance(base, list) or isinstance(revised, list):
        if path == "scene_phases" and isinstance(base, list) and isinstance(revised, list):
            # Phase order itself is semantic, but equal phase IDs should be
            # descended into so that P01/P02 fields receive their own policy.
            base_ids = [str(x.get("phase_id")) if isinstance(x, dict) else "" for x in base]
            revised_ids = [str(x.get("phase_id")) if isinstance(x, dict) else "" for x in revised]
            if base_ids != revised_ids:
                return [{"path": path, "field_semantics": "ORDERED", "base_value": base, "revised_value": revised, "added_items": [], "removed_items": [], "same_refs_reordered": False, "reordered_only": True, "semantic_change": True, "classification": "ORDERED_CHANGE"}]
            out: list[dict[str, Any]] = []
            for i, (left, right) in enumerate(zip(base, revised)):
                out.extend(semantic_diff(left, right, path=f"scene_phases[{base_ids[i]}]"))
            return out
        if semantics == "SET_LIKE":
            result = compare_set_like(base, revised)
            if result["semantic_change"] or result["same_refs_reordered"]:
                return [{"path": path, "field_semantics": semantics, "base_value": base, "revised_value": revised, **result, "reordered_only": result["same_refs_reordered"] and not result["semantic_change"], "classification": "NO_SEMANTIC_CHANGE" if not result["semantic_change"] else "SET_LIKE_CHANGE"}]
            return []
        if semantics == "ORDERED":
            if isinstance(base, list) and isinstance(revised, list) and base and revised and all(isinstance(x, dict) for x in [*base, *revised]):
                # Preserve ordered semantics by comparing each row at its
                # stable index.  This exposes an identity-only row repair at
                # character_id instead of collapsing it into an unscoped list
                # replacement, while any row movement still yields changes.
                out: list[dict[str, Any]] = []
                for i in range(max(len(base), len(revised))):
                    left = base[i] if i < len(base) else None
                    right = revised[i] if i < len(revised) else None
                    out.extend(semantic_diff(left, right, path=f"{path}[{i}]"))
                return out
            if base == revised:
                return []
            return [{"path": path, "field_semantics": semantics, "base_value": base, "revised_value": revised, "added_items": [], "removed_items": [], "same_refs_reordered": False, "reordered_only": True, "semantic_change": True, "classification": "ORDERED_CHANGE"}]
        if semantics == "UNKNOWN" and isinstance(base, list) and isinstance(revised, list):
            out: list[dict[str, Any]] = []
            for i in range(max(len(base), len(revised))):
                left = base[i] if i < len(base) else None
                right = revised[i] if i < len(revised) else None
                out.extend(semantic_diff(left, right, path=f"{path}[{i}]"))
            return out
    if isinstance(base, dict) or isinstance(revised, dict):
        b, r = base if isinstance(base, dict) else {}, revised if isinstance(revised, dict) else {}
        out: list[dict[str, Any]] = []
        for key in sorted(set(b) | set(r)):
            if key in {"semantic_spec_version", "compiler_version", "strategy_version", "authority_projection", "source_trace", "creative_core_fingerprint", "strategy_fingerprint", "compiled_at"}:
                continue
            child = f"{path}.{key}" if path else key
            out.extend(semantic_diff(b.get(key), r.get(key), path=child))
        return out
    if base != revised:
        return [{"path": path, "field_semantics": semantics, "base_value": base, "revised_value": revised, "added_items": [], "removed_items": [], "same_refs_reordered": False, "reordered_only": False, "semantic_change": True, "classification": "SCALAR_CHANGE"}]
    return []


def is_identity_semantic_sync_change(
    base_ref: Any,
    revised_ref: Any,
    authoritative_bindings: dict[str, str],
    semantic_subject: str | None = None,
    base_semantic_context: Any = None,
    revised_semantic_context: Any = None,
) -> dict[str, Any]:
    """Validate a character reference correction without changing meaning."""
    old, new = str(base_ref or ""), str(revised_ref or "")
    result = {"base_ref": old, "revised_ref": new, "classification": "DEPENDENCY_REVIEW_REQUIRED", "reason": "insufficient_identity_evidence"}
    if not (old.startswith("character:") and new.startswith("character:")):
        result.update(classification="REJECT", reason="refs_must_both_be_character_refs")
        return result
    old_id, new_id = old.split(":", 1)[1], new.split(":", 1)[1]
    old_name, new_name = authoritative_bindings.get(old_id, ""), authoritative_bindings.get(new_id, "")
    result.update(base_bound_name=old_name, revised_bound_name=new_name)
    if not old_name or not new_name or old_id == new_id:
        result.update(classification="REJECT", reason="unknown_or_unchanged_identity")
        return result
    subject = str(semantic_subject or "").strip()
    if not subject:
        result.update(classification="DEPENDENCY_REVIEW_REQUIRED", reason="semantic_subject_unresolved")
        return result
    result["semantic_subject"] = subject
    if new_name == subject and old_name != subject:
        result.update(classification="IDENTITY_DEPENDENCY_PASS", reason="revised_ref_restores_authoritative_identity")
    else:
        result.update(classification="REJECT", reason="revised_ref_changes_semantic_subject")
    return result


def infer_semantic_subject(context: Any, bindings: dict[str, str]) -> str | None:
    """Infer a subject only when one name has a strict textual majority."""
    if not isinstance(context, (dict, list, str)):
        return None
    text = str(context) if isinstance(context, str) else _flatten_text(context)
    leading = [name for name in bindings.values() if name and re.match(rf"^\s*{re.escape(name)}", text)]
    if len(set(leading)) == 1:
        return leading[0]
    counts = {name: len(re.findall(re.escape(name), text)) for name in bindings.values() if name}
    if not counts:
        return None
    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    if ordered[0][1] <= 0 or (len(ordered) > 1 and ordered[0][1] == ordered[1][1]):
        return None
    return ordered[0][0]


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(v) for v in value)
    return str(value or "")


__all__ = ["FIELD_SEMANTICS_REGISTRY", "segment_match", "field_semantics", "compare_set_like", "semantic_diff", "is_identity_semantic_sync_change", "infer_semantic_subject"]
