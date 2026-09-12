"""Small, auditable responsibility-layer repairs for qualification."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def apply_local_repair(candidate: dict[str, Any], issue: dict[str, Any]) -> dict[str, Any]:
    """Apply only an explicit JSON-like patch within the routed layer."""
    before = fingerprint(candidate)
    updated = copy.deepcopy(candidate)
    patch = issue.get("patch") if isinstance(issue.get("patch"), list) else []
    for operation in patch:
        if not isinstance(operation, dict) or operation.get("op") not in {"add", "replace", "remove"}:
            raise ValueError("repair patch contains unsupported operation")
        path = [part for part in str(operation.get("path") or "").split("/") if part]
        if not path:
            raise ValueError("repair patch path is required")
        target: Any = updated
        for part in path[:-1]:
            if isinstance(target, list):
                target = target[int(part)]
            elif isinstance(target, dict):
                target = target[part]
            else:
                raise ValueError("repair patch path is invalid")
        key = path[-1]
        if isinstance(target, list):
            index = int(key)
            if operation["op"] == "remove": target.pop(index)
            elif operation["op"] == "replace": target[index] = operation.get("value")
            else: target.insert(index, operation.get("value"))
        elif isinstance(target, dict):
            if operation["op"] == "remove": target.pop(key, None)
            else: target[key] = operation.get("value")
        else:
            raise ValueError("repair patch target is invalid")
    after = fingerprint(updated)
    return {
        "issue_code": str(issue.get("code") or issue.get("issue_code") or ""),
        "target_id": str(issue.get("target_id") or issue.get("target_shot_id") or ""),
        "patch": copy.deepcopy(patch),
        "candidate": updated,
        # Keep the complete pre-image so a caller can restore it without
        # reconstructing an inverse JSON patch.
        "rollback_candidate": copy.deepcopy(candidate),
        "before_fingerprint": before,
        "after_fingerprint": after,
        "changed": before != after,
        "target_layer": str(issue.get("target_layer") or ""),
    }


def rollback_local_repair(repair: dict[str, Any], *, expected_fingerprint: str | None = None) -> dict[str, Any]:
    """Restore a repair pre-image, optionally guarding against stale state."""
    if not isinstance(repair, dict) or not isinstance(repair.get("rollback_candidate"), dict):
        raise ValueError("repair rollback snapshot is missing")
    current = repair.get("candidate")
    if expected_fingerprint and fingerprint(current) != expected_fingerprint:
        raise ValueError("repair rollback fingerprint mismatch")
    restored = copy.deepcopy(repair["rollback_candidate"])
    return {"candidate": restored, "fingerprint": fingerprint(restored), "target_layer": str(repair.get("target_layer") or "")}
