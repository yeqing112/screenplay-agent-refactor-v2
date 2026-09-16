"""Deterministic compiler for Strategy V3 preserve intents."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.director_strategy_provider_spec import PRESERVE_INTENT_SCHEMA_VERSION, PRESERVE_KINDS, VISIBILITY_REQUIREMENTS


def _d(value: Any) -> dict[str, Any]: return value if isinstance(value, dict) else {}
def _l(value: Any) -> list[Any]: return value if isinstance(value, list) else []
def _t(value: Any) -> str: return str(value or "").strip()
def _canon(value: Any) -> str: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def _fp(value: Any) -> str: return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _allowed_refs(*, allowed_source_refs: list[str] | None, allowed_character_refs: list[str] | None, allowed_prop_refs: list[str] | None, allowed_location_refs: list[str] | None, allowed_event_refs: list[str] | None) -> dict[str, set[str]]:
    return {
        "source": {_t(x) for x in (allowed_source_refs or []) if _t(x)},
        "character": {_t(x) for x in (allowed_character_refs or []) if _t(x)},
        "prop": {_t(x) for x in (allowed_prop_refs or []) if _t(x)},
        "location": {_t(x) for x in (allowed_location_refs or []) if _t(x)},
        "event": {_t(x) for x in (allowed_event_refs or []) if _t(x)},
    }


def compile_preserve_intents_to_authority(
    preserve_intents: Any,
    *,
    allowed_source_refs: list[str] | None = None,
    allowed_character_refs: list[str] | None = None,
    allowed_prop_refs: list[str] | None = None,
    allowed_location_refs: list[str] | None = None,
    allowed_event_refs: list[str] | None = None,
    scene_id: str | None = None,
) -> dict[str, Any]:
    """Compile exact typed references; never infer refs from descriptions."""
    allowed = _allowed_refs(allowed_source_refs=allowed_source_refs, allowed_character_refs=allowed_character_refs, allowed_prop_refs=allowed_prop_refs, allowed_location_refs=allowed_location_refs, allowed_event_refs=allowed_event_refs)
    rows = _l(preserve_intents); constraints: list[dict[str, Any]] = []; errors: list[dict[str, Any]] = []
    for index, raw in enumerate(rows, 1):
        intent = _d(raw); cid = f"MP{index:02d}"; path = f"preserve_intents[{index - 1}]"
        kind = _t(intent.get("kind")); description = _t(intent.get("description")); anchors = [_t(x) for x in _l(intent.get("anchor_refs")) if _t(x)]
        subjects = [_t(x) for x in _l(intent.get("subject_refs")) if _t(x)]; objects = [_t(x) for x in _l(intent.get("object_refs")) if _t(x)]
        visibility = _t(intent.get("visibility_requirement"))
        if kind not in PRESERVE_KINDS: errors.append({"code": "PRESERVE_KIND_INVALID", "constraint_id": cid, "path": f"{path}.kind"})
        if not description: errors.append({"code": "PRESERVE_INTENT_FIELD_MISSING", "constraint_id": cid, "path": f"{path}.description"})
        if not anchors: errors.append({"code": "PRESERVE_ANCHOR_MISSING", "constraint_id": cid, "path": f"{path}.anchor_refs"})
        if visibility not in VISIBILITY_REQUIREMENTS: errors.append({"code": "PRESERVE_VISIBILITY_INVALID", "constraint_id": cid, "path": f"{path}.visibility_requirement"})
        beat_refs: list[str] = []; event_refs: list[str] = []; source_refs: list[str] = []
        for ref in anchors:
            if ref.startswith("beat:"):
                if ref not in allowed["source"]: errors.append({"code": "PRESERVE_ANCHOR_INVALID", "constraint_id": cid, "reference": ref})
                else: beat_refs.append(ref)
            elif ref.startswith("event:"):
                if ref not in allowed["event"]: errors.append({"code": "PRESERVE_ANCHOR_INVALID", "constraint_id": cid, "reference": ref})
                else: event_refs.append(ref)
            elif ref not in allowed["source"]:
                errors.append({"code": "PRESERVE_ANCHOR_INVALID", "constraint_id": cid, "reference": ref})
            else:
                source_refs.append(ref)
        for ref in subjects:
            if ref not in allowed["character"]: errors.append({"code": "PRESERVE_SUBJECT_INVALID", "constraint_id": cid, "reference": ref})
        for ref in objects:
            if ref not in allowed["prop"] and ref not in allowed["location"]: errors.append({"code": "PRESERVE_OBJECT_INVALID", "constraint_id": cid, "reference": ref})
        constraints.append({"constraint_id": cid, "kind": kind, "description": description, "subject_refs": subjects, "object_refs": objects, "beat_refs": beat_refs, "event_refs": event_refs, "source_refs": source_refs, "visibility_requirement": visibility, "preservation_scope": "SCENE", "provenance": {"authority": "STRATEGY_PROVIDER_INTENT", "source_intent_index": index}})
    result = {"schema_version": "structured_preserve_constraint_v1", "intent_schema_version": PRESERVE_INTENT_SCHEMA_VERSION, "scene_id": _t(scene_id), "constraints": constraints, "errors": errors, "status": "PASS" if not errors else "FAIL"}
    result["fingerprint"] = _fp({k: v for k, v in result.items() if k not in {"fingerprint", "errors", "status"}})
    return result


def preserve_authority_from_strategy(strategy: dict[str, Any], *, contract: dict[str, Any], scene_id: str | None = None) -> dict[str, Any]:
    """Convenience adapter consuming only the V3 provider contract refs."""
    return compile_preserve_intents_to_authority(
        strategy.get("preserve_intents") if isinstance(strategy, dict) else None,
        allowed_source_refs=contract.get("allowed_source_refs"),
        allowed_character_refs=contract.get("allowed_character_refs"),
        allowed_prop_refs=contract.get("allowed_prop_refs"),
        allowed_location_refs=contract.get("allowed_location_refs"),
        allowed_event_refs=contract.get("allowed_event_refs"),
        scene_id=scene_id or _t(strategy.get("scene_id")) if isinstance(strategy, dict) else None,
    )


__all__ = ["compile_preserve_intents_to_authority", "preserve_authority_from_strategy"]
