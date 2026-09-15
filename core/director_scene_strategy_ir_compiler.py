"""Deterministic compiler from Strategy IR to canonical Strategy V2.

No creative prose is generated here.  The compiler only normalizes IDs,
projects authority and computes program-owned fingerprints.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.director_scene_strategy_ir import validate_strategy_ir
from core.director_scene_strategy_semantic_spec import (
    CANONICAL_SCHEMA_VERSION,
    COMPILER_VERSION,
    IR_SCHEMA_VERSION,
    build_beat_alias_table,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _creative_projection(value: dict[str, Any]) -> dict[str, Any]:
    """Strip identity/provenance/derived metadata for content comparison."""
    excluded = {
        "scene_id", "strategy_fingerprint", "creative_core_fingerprint", "source_trace",
        "authority_projection", "source_refs", "semantic_spec_version", "compiler_version",
        "schema_version", "strategy_version", "metadata", "timestamps", "created_at",
    }
    return {key: value[key] for key in sorted(value) if key not in excluded}


def strategy_fingerprint(value: dict[str, Any]) -> str:
    """Hash canonical strategy including identity, excluding only derived hash."""
    payload = dict(value)
    payload.pop("strategy_fingerprint", None)
    return _sha(payload)


def creative_core_fingerprint(value: dict[str, Any]) -> str:
    return _sha(_creative_projection(value))


def compile_ir_to_canonical(*, ir: dict[str, Any], contract: dict[str, Any], authority: dict[str, Any] | None = None) -> dict[str, Any]:
    checked = validate_strategy_ir(ir, contract=contract)
    if not checked["valid"]:
        first = checked["errors"][0]
        raise ValueError(f"{first.get('code')}: {first.get('path')}")
    normalized = copy.deepcopy(checked["ir"])
    phases = normalized.get("scene_phases", [])
    # Canonical phase ordering is source order; no phase content is invented.
    for index, phase in enumerate(phases, 1):
        phase["phase_index"] = index
        phase["phase_id"] = _text(phase.get("phase_id")) or f"P{index:02d}"
        phase["beat_ids"] = [_text(value) for value in _list(phase.get("beat_ids"))]
        for row in _list(phase.get("performance")):
            if isinstance(row, dict):
                row["character_id"] = _text(row.get("character_id"))
        power = _dict(phase.get("power"))
        power["center_type"] = _text(power.get("center_type")).upper()
        power["center_ref"] = _text(power.get("center_ref")) or None
        phase["power"] = power
    canonical = {
        **normalized,
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "strategy_version": "v2",
        "semantic_spec_version": "director_scene_strategy_semantic_spec_v1",
        "compiler_version": COMPILER_VERSION,
        "normalized_beat_ids": [beat for phase in phases for beat in _list(phase.get("beat_ids"))],
        "canonical_character_ids": sorted({
            _text(row.get("character_id"))
            for phase in phases for row in _list(phase.get("performance")) if isinstance(row, dict) and _text(row.get("character_id"))
        }),
        "authority_projection": copy.deepcopy(authority or {
            "SOURCE_FACT": ["scene identity", "beats", "chronology", "dialogue", "character identity", "asset identity"],
            "TREATMENT_INTENT": ["dramatic objective", "tone", "intent"],
            "BLOCKING_FACT": ["spatial truth", "entry/exit", "screen direction", "continuity"],
            "DIRECTOR_CREATIVE_DECISION": ["scene phases", "audience state", "emotion", "power", "performance", "edit", "visual"],
        }),
        "source_trace": {
            "contract_scene_id": _text(_dict(contract).get("scene_id")),
            "beat_ids": [_text(item) for item in _list(_dict(contract).get("beat_ids"))],
            "character_ids": sorted({_text(item) for item in _list(_dict(contract).get("character_ids")) if _text(item)}),
            "fact_ids": sorted({_text(item) for item in _list(_dict(contract).get("fact_ids")) if _text(item)}),
        },
    }
    canonical["creative_core_fingerprint"] = creative_core_fingerprint(canonical)
    canonical["strategy_fingerprint"] = strategy_fingerprint(canonical)
    return canonical


def legacy_v1_to_ir(*, raw: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """Normalize historical V1/provider shapes without changing their prose.

    This adapter is replay-only.  It maps names and containers, marks absent
    semantics as N/A, and never creates facts, beats or directing decisions.
    """
    def text(value: Any) -> str:
        return _text(value)

    beat_ids = [_text(item) for item in _list(_dict(contract).get("beat_ids")) if _text(item)]
    chars = sorted({_text(item) for item in _list(_dict(contract).get("character_ids")) if _text(item)})
    alias = build_beat_alias_table(beat_ids)
    by_beat: dict[str, dict[str, Any]] = {}
    experience = _list(raw.get("audience_experience"))
    for idx, row in enumerate(experience):
        row = _dict(row)
        bid = row.get("beat_id") or (beat_ids[idx] if idx < len(beat_ids) else None)
        canonical = alias.get("aliases", {}).get(text(bid)) or text(bid)
        by_beat.setdefault(canonical, {})["experience"] = text(row.get("experience"))
    # Legacy outputs vary in beat-keyed fields.  Keep only source-bound rows.
    def rows_by_beat(field: str, names: tuple[str, ...]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for idx, row in enumerate(_list(raw.get(field))):
            row = _dict(row)
            bid = row.get("beat_id") or row.get("id") or (beat_ids[idx] if idx < len(beat_ids) else None)
            bid = alias.get("aliases", {}).get(text(bid)) or text(bid)
            out[bid] = {name: row.get(name) for name in names if row.get(name) not in (None, "")}
        return out
    knowledge = rows_by_beat("audience_knowledge_arc", ("knowledge_state", "knowledge", "does_not_know_yet", "suspects", "withholds", "transition_trigger"))
    emotion = rows_by_beat("emotional_arc", ("emotion", "emotion_state", "trigger", "transition_reason", "intensity_hint"))
    power = rows_by_beat("power_arc", ("power_holder", "power_dynamic", "power_dynamics", "dynamic", "controller", "shift", "description"))
    info = rows_by_beat("information_reveal_plan", ("reveal", "hint", "withhold", "source_refs", "source_fact_refs"))
    phases: list[dict[str, Any]] = []
    # Group consecutive beats into 3-5 phases where possible, preserving order.
    n = len(beat_ids)
    target = max(2, min(5, n)) if n else 2
    chunk = max(1, (n + target - 1) // target)
    for start in range(0, n, chunk):
        ids = beat_ids[start:start + chunk]
        if not ids:
            continue
        first = ids[0]
        k = knowledge.get(first, {})
        e = emotion.get(first, {})
        p = power.get(first, {})
        center_type = "NONE"
        center_ref = None
        holder = text(p.get("controller") or p.get("power_holder"))
        if holder and holder in chars:
            center_type, center_ref = "CHARACTER", holder
        elif holder:
            center_type = "INFORMATION"
        perf: list[dict[str, Any]] = []
        legacy_perf = raw.get("performance_arc")
        if isinstance(legacy_perf, dict):
            iterable = [(key, value) for key, value in legacy_perf.items()]
        else:
            iterable = [(text(_dict(row).get("character_id")), row) for row in _list(legacy_perf)]
        for char, value in iterable:
            if char not in chars:
                continue
            value = _dict(value)
            perf.append({
                "character_id": char,
                "objective": text(value.get("objective")) or "N/A",
                "tactic": text(value.get("tactic") or value.get("tactic_progression")) or "N/A",
                "visible_behavior": text(value.get("visible_behavior") or value.get("visible_behavior_progression")) or "N/A",
                "turning_point": value.get("turning_point") or False,
            })
        if not perf:
            perf = [{"character_id": char, "objective": "N/A", "tactic": "N/A", "visible_behavior": "N/A", "turning_point": False} for char in chars]
        phases.append({
            "phase_id": f"P{len(phases)+1:02d}", "beat_ids": ids,
            "dramatic_function": text(by_beat.get(first, {}).get("experience")) or "N/A",
            "audience_state": {
                "knows": [text(k.get("knowledge_state") or k.get("knowledge"))] if text(k.get("knowledge_state") or k.get("knowledge")) else [],
                "suspects": [text(x) for x in _list(k.get("suspects")) if text(x)],
                "withholds": [text(x) for x in _list(k.get("withholds")) if text(x)],
                "question_shift": text(k.get("transition_trigger")) or "N/A",
            },
            "emotion": {
                "state": text(e.get("emotion_state") or e.get("emotion")) or "N/A",
                "trigger": text(e.get("trigger")) or "N/A",
                "transition_reason": text(e.get("transition_reason")) or "N/A",
                "intensity_hint": e.get("intensity_hint"),
            },
            "power": {"center_type": center_type, "center_ref": center_ref, "description": text(p.get("power_dynamic") or p.get("power_dynamics") or p.get("dynamic")) or "N/A", "shift": text(p.get("shift")) or "N/A"},
            "performance": perf,
            "edit": {"tempo": "N/A", "hold_logic": "N/A", "cut_logic": text(raw.get("edit_arc")) or "N/A", "transition_motivation": "N/A"},
            "visual": {"visual_grammar": text(raw.get("visual_grammar")) or "N/A", "camera_rule": text(raw.get("camera_principles")) or "N/A", "composition_rule": text(raw.get("composition_principles")) or "N/A", "movement_condition": "N/A"},
            "information": {"reveal": [text(x) for x in _list(info.get(first, {}).get("reveal")) if text(x)], "hint": [text(x) for x in _list(info.get(first, {}).get("hint")) if text(x)], "withhold": [text(x) for x in _list(info.get(first, {}).get("withhold")) if text(x)], "source_refs": [text(x) for x in _list(info.get(first, {}).get("source_refs") or info.get(first, {}).get("source_fact_refs")) if text(x) and text(x) in set(_dict(contract).get("fact_ids") or [])]},
        })
    return {
        "schema_version": IR_SCHEMA_VERSION, "scene_id": _text(raw.get("scene_id") or _dict(contract).get("scene_id")),
        "dramatic_objective": text(raw.get("dramatic_objective")) or "N/A", "scene_question": text(raw.get("scene_question")) or "N/A", "strategy_summary": text(raw.get("strategy_summary")) or "N/A", "visual_thesis": text(raw.get("visual_grammar")) or "N/A", "scene_phases": phases,
        "spatial_expression": _list(raw.get("spatial_expression")) or ["N/A"], "prop_visual_strategy": _list(raw.get("prop_visual_strategy")) or ["N/A"], "shot_architecture_guidance": _dict(raw.get("shot_architecture_guidance")) or {"status": "N/A"}, "must_preserve": _list(raw.get("must_preserve")) or ["N/A"], "must_avoid": _list(raw.get("must_avoid")) or ["N/A"], "creative_risks": _list(raw.get("creative_risks")) or ["N/A"],
    }


__all__ = ["compile_ir_to_canonical", "validate_strategy_ir", "legacy_v1_to_ir", "strategy_fingerprint", "creative_core_fingerprint"]
