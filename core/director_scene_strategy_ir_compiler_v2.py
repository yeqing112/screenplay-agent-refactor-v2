"""Deterministic compiler from Strategy IR V2 to Canonical Strategy V3."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.director_scene_strategy_ir_v2 import validate_strategy_ir_v2
from core.director_scene_strategy_semantic_spec_v2 import CANONICAL_SCHEMA_VERSION, COMPILER_VERSION


def _canonical(value: Any) -> str: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def _sha(value: Any) -> str: return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def strategy_fingerprint_v3(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value); payload.pop("strategy_fingerprint", None); return _sha(payload)


def creative_core_fingerprint_v3(value: dict[str, Any]) -> str:
    excluded = {"scene_id", "schema_version", "semantic_spec_version", "compiler_version", "strategy_fingerprint", "creative_core_fingerprint", "source_trace", "authority_projection"}
    return _sha({k: value[k] for k in sorted(value) if k not in excluded})


def compile_ir_v2_to_canonical_v3(*, ir: dict[str, Any], contract: dict[str, Any], authority: dict[str, Any] | None = None) -> dict[str, Any]:
    checked = validate_strategy_ir_v2(ir, contract=contract)
    if not checked["valid"]: raise ValueError(f"{checked['errors'][0].get('code')}: {checked['errors'][0].get('path')}")
    normalized = copy.deepcopy(checked["ir"])
    canonical = {**normalized, "schema_version": CANONICAL_SCHEMA_VERSION, "semantic_spec_version": "director_scene_strategy_semantic_spec_v2", "compiler_version": COMPILER_VERSION, "strategy_version": "v3", "spatial_expression": list(normalized.get("spatial_expression") or []), "prop_visual_strategy": list(normalized.get("prop_visual_strategy") or []), "shot_architecture_guidance": list(normalized.get("shot_architecture_guidance") or []), "must_preserve": list(normalized.get("must_preserve") or []), "must_avoid": list(normalized.get("must_avoid") or []), "creative_risks": list(normalized.get("creative_risks") or [])}
    canonical["authority_projection"] = copy.deepcopy(authority or {"SOURCE_FACT": ["scene identity", "beats", "dialogue", "chronology", "character/asset identity"], "TREATMENT_INTENT": ["dramatic objective", "tone", "intent"], "BLOCKING_FACT": ["spatial truth", "entry/exit", "screen direction"], "DIRECTOR_CREATIVE_DECISION": ["phase staging", "audience/emotion/power", "performance", "edit", "visual"]})
    canonical["source_trace"] = {"contract_scene_id": str(contract.get("scene_id") or ""), "beat_ids": list(contract.get("beat_ids") or []), "character_ids": sorted(contract.get("character_ids") or []), "fact_ids": sorted(contract.get("fact_ids") or []), "phases": [{"phase_id": p.get("phase_id"), "beat_refs": [f"beat:{b}" for b in p.get("beat_ids", [])], "reveal_refs": list(p.get("information", {}).get("reveal_refs", [])), "hint_refs": list(p.get("information", {}).get("hint_refs", [])), "withhold_refs": list(p.get("information", {}).get("withhold_refs", [])), "audience_suspicions": copy.deepcopy(p.get("information", {}).get("audience_suspicions", [])), "director_inferences": copy.deepcopy(p.get("information", {}).get("director_inferences", []))} for p in canonical.get("scene_phases", [])]}
    canonical["creative_core_fingerprint"] = creative_core_fingerprint_v3(canonical); canonical["strategy_fingerprint"] = strategy_fingerprint_v3(canonical)
    return canonical


__all__ = ["compile_ir_v2_to_canonical_v3", "strategy_fingerprint_v3", "creative_core_fingerprint_v3"]
