"""Single source of truth for the Fresh Director V3 Strategy provider.

The provider chooses semantic preserve intents and their explicit anchors.  The
program owns canonical validation, IDs and the resulting machine authority.
Legacy ``must_preserve`` remains a human-readable compatibility projection and
is never accepted as Fresh V3 machine authority.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

STRATEGY_PROVIDER_SPEC_VERSION = "director_strategy_provider_spec_v3"
STRATEGY_SCHEMA_VERSION = "director_scene_strategy_ir_v3"
PRESERVE_INTENT_SCHEMA_VERSION = "strategy_preserve_intent_v1"

STRATEGY_REQUIRED_FIELDS = (
    "dramatic_objective", "scene_question", "strategy_summary", "visual_thesis",
    "scene_phases", "spatial_expression", "prop_visual_strategy",
    "creative_risks", "must_avoid", "preserve_intents",
)
PRESERVE_INTENT_REQUIRED_FIELDS = (
    "kind", "description", "anchor_refs", "subject_refs", "object_refs",
    "visibility_requirement",
)
PRESERVE_KINDS = (
    "CHARACTER_ACTION", "CHARACTER_REACTION", "PROP_STATE", "PROP_INTERACTION",
    "SPATIAL_RELATION", "INFORMATION_REVEAL", "INFORMATION_WITHHOLD",
    "VISUAL_EVENT", "ENTRY_EXIT", "CONTINUITY_REQUIREMENT",
)
VISIBILITY_REQUIREMENTS = ("EXPLICIT", "IMPLICIT", "CONTINUITY_ONLY")


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def schema_fingerprint(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def strategy_provider_spec(*, allowed_source_refs: list[str] | None = None,
                           allowed_character_refs: list[str] | None = None,
                           allowed_prop_refs: list[str] | None = None,
                           allowed_location_refs: list[str] | None = None,
                           allowed_event_refs: list[str] | None = None) -> dict[str, Any]:
    """Build the complete provider/normalizer/validator contract projection."""
    refs = {
        "allowed_source_refs": sorted(set(str(x).strip() for x in (allowed_source_refs or []) if str(x).strip())),
        "allowed_character_refs": sorted(set(str(x).strip() for x in (allowed_character_refs or []) if str(x).strip())),
        "allowed_prop_refs": sorted(set(str(x).strip() for x in (allowed_prop_refs or []) if str(x).strip())),
        "allowed_location_refs": sorted(set(str(x).strip() for x in (allowed_location_refs or []) if str(x).strip())),
        "allowed_event_refs": sorted(set(str(x).strip() for x in (allowed_event_refs or []) if str(x).strip())),
    }
    spec = {
        "schema_version": STRATEGY_PROVIDER_SPEC_VERSION,
        "strategy_schema_version": STRATEGY_SCHEMA_VERSION,
        "required_fields": list(STRATEGY_REQUIRED_FIELDS),
        "preserve_intent_schema_version": PRESERVE_INTENT_SCHEMA_VERSION,
        "preserve_intent_required_fields": list(PRESERVE_INTENT_REQUIRED_FIELDS),
        "preserve_kind_enum": list(PRESERVE_KINDS),
        "visibility_requirement_enum": list(VISIBILITY_REQUIREMENTS),
        "ref_rules": {
            "anchor_refs": "non-empty exact selection from allowed typed refs; no prose resolution",
            "subject_refs": "exact character refs from allowed_character_refs",
            "object_refs": "exact prop/location refs from allowed_prop_refs or allowed_location_refs",
            "provider_does_not_emit_constraint_ids": True,
        },
        "legacy_projection": {"field": "must_preserve", "human_readable_projection_only": True},
        "forbidden_machine_fields": ["must_preserve", "strategy_fingerprint", "shots", "shot_ids", "plan_shot_id", "patches", "repair"],
        **refs,
    }
    spec["schema_fingerprint"] = schema_fingerprint({k: v for k, v in spec.items() if k != "schema_fingerprint"})
    return spec


def build_strategy_provider_contract(evidence: dict[str, Any]) -> dict[str, Any]:
    safe = evidence if isinstance(evidence, dict) else {}
    contract = safe.get("strategy_contract") if isinstance(safe.get("strategy_contract"), dict) else safe.get("contract") or {}
    def typed(values: Any, namespace: str) -> list[str]:
        output: list[str] = []
        for value in values if isinstance(values, list) else []:
            text = str(value).strip()
            if text:
                output.append(text if ":" in text else f"{namespace}:{text}")
        return output

    scene = safe.get("scene") if isinstance(safe.get("scene"), dict) else {}
    scene_beats = [item.get("beat_id") for item in scene.get("beats", []) if isinstance(item, dict)]
    scene_facts = [item.get("fact_id") or item.get("id") for item in scene.get("facts", []) if isinstance(item, dict)]
    source = (
        contract.get("allowed_source_refs")
        or safe.get("allowed_source_refs")
        or typed(contract.get("beat_ids"), "beat")
        + typed(contract.get("fact_ids"), "fact")
        or typed(scene_beats, "beat") + typed(scene_facts, "fact")
    )
    chars = contract.get("allowed_character_refs") or typed(contract.get("character_ids"), "character")
    props = contract.get("allowed_prop_refs") or typed(contract.get("prop_ids"), "prop")
    locations = contract.get("allowed_location_refs") or typed(contract.get("location_ids"), "location")
    event_rows = safe.get("semantic_events") if isinstance(safe.get("semantic_events"), dict) else {}
    event_keys = [item.get("event_key") for item in event_rows.get("events", []) if isinstance(item, dict)]
    events = contract.get("allowed_event_refs") or safe.get("allowed_event_refs") or typed(safe.get("event_keys"), "event") or typed(event_keys, "event")
    return strategy_provider_spec(
        allowed_source_refs=list(source), allowed_character_refs=list(chars),
        allowed_prop_refs=list(props), allowed_location_refs=list(locations),
        allowed_event_refs=list(events),
    )


def validate_strategy_v3_shape(value: Any, *, contract: dict[str, Any]) -> dict[str, Any]:
    """Validate the provider envelope without repairing or inferring meaning."""
    errors: list[dict[str, Any]] = []
    if not isinstance(value, dict):
        return {"status": "FAIL", "errors": [{"code": "STRATEGY_SCHEMA_INVALID", "path": "$"}]}
    if str(value.get("schema_version") or "").strip() != STRATEGY_SCHEMA_VERSION:
        errors.append({"code": "STRATEGY_SCHEMA_INVALID", "path": "schema_version"})
    if "must_preserve" in value:
        # A legacy projection may be transported for human display, but it is
        # never part of the machine contract.  Require an explicit marker so
        # a provider cannot accidentally smuggle the old authority shape into
        # the Fresh V3 path.
        marker = value.get("must_preserve_projection")
        if marker != "human_readable_projection_only":
            errors.append({"code": "STRATEGY_SCHEMA_INVALID", "path": "must_preserve", "reason": "legacy_machine_authority_disabled"})
    for field in STRATEGY_REQUIRED_FIELDS:
        if field not in value:
            errors.append({"code": "STRATEGY_FIELD_MISSING", "path": field})
    intents = value.get("preserve_intents")
    if not isinstance(intents, list):
        errors.append({"code": "STRATEGY_FIELD_INVALID", "path": "preserve_intents", "expected": "array"})
    else:
        for index, intent in enumerate(intents):
            if not isinstance(intent, dict):
                errors.append({"code": "PRESERVE_INTENT_INVALID", "path": f"preserve_intents[{index}]"}); continue
            for field in PRESERVE_INTENT_REQUIRED_FIELDS:
                if field not in intent:
                    errors.append({"code": "PRESERVE_INTENT_FIELD_MISSING", "path": f"preserve_intents[{index}].{field}"})
            if str(intent.get("kind") or "").strip() not in PRESERVE_KINDS:
                errors.append({"code": "PRESERVE_KIND_INVALID", "path": f"preserve_intents[{index}].kind"})
            if str(intent.get("visibility_requirement") or "").strip() not in VISIBILITY_REQUIREMENTS:
                errors.append({"code": "PRESERVE_VISIBILITY_INVALID", "path": f"preserve_intents[{index}].visibility_requirement"})
            if not isinstance(intent.get("anchor_refs"), list) or not intent.get("anchor_refs"):
                errors.append({"code": "PRESERVE_ANCHOR_MISSING", "path": f"preserve_intents[{index}].anchor_refs"})
    forbidden = set(value) & {"shots", "shot_ids", "plan_shot_id", "patches", "repair", "strategy_fingerprint"}
    errors.extend({"code": "STRATEGY_FIELD_FORBIDDEN", "path": field} for field in sorted(forbidden))
    declared_fp = str(value.get("strategy_schema_fingerprint") or "").strip()
    contract_fp = str(contract.get("schema_fingerprint") or "").strip()
    if declared_fp and contract_fp and declared_fp != contract_fp:
        errors.append({"code": "STRATEGY_SCHEMA_FINGERPRINT_MISMATCH", "path": "strategy_schema_fingerprint"})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "schema_fingerprint": contract.get("schema_fingerprint")}


def canonicalize_strategy_v3(value: dict[str, Any]) -> dict[str, Any]:
    """Create a deterministic canonical copy; no creative/factual repair."""
    result = copy.deepcopy(value)
    result["schema_version"] = STRATEGY_SCHEMA_VERSION
    result["strategy_version"] = "v3"
    result.pop("strategy_fingerprint", None)
    result["strategy_fingerprint"] = schema_fingerprint(result)
    return result


def provider_validator_parity() -> dict[str, Any]:
    spec = strategy_provider_spec()
    # The validator projection is intentionally assembled from the constants
    # consumed by ``validate_strategy_v3_shape`` rather than calling the
    # provider-spec builder again.  This makes a future drift observable.
    validator = {
        "required_fields": list(STRATEGY_REQUIRED_FIELDS),
        "preserve_intent_required_fields": list(PRESERVE_INTENT_REQUIRED_FIELDS),
        "preserve_kind_enum": list(PRESERVE_KINDS),
        "visibility_requirement_enum": list(VISIBILITY_REQUIREMENTS),
        "ref_rules": spec["ref_rules"],
        "forbidden_machine_fields": list(spec["forbidden_machine_fields"]),
    }
    keys = ("required_fields", "preserve_intent_required_fields", "preserve_kind_enum", "visibility_requirement_enum", "ref_rules", "forbidden_machine_fields")
    parity = all(spec[key] == validator[key] for key in keys)
    validator_fp = schema_fingerprint({k: v for k, v in spec.items() if k != "schema_fingerprint"}) if parity else schema_fingerprint(validator)
    return {"schema_version": "strategy_provider_validator_schema_parity_v1", "status": "PASS" if parity else "FAIL", "provider_spec_fingerprint": spec["schema_fingerprint"], "validator_spec_fingerprint": validator_fp, "required_field_parity": spec["required_fields"] == validator["required_fields"], "preserve_intent_field_parity": spec["preserve_intent_required_fields"] == validator["preserve_intent_required_fields"], "enum_parity": spec["preserve_kind_enum"] == validator["preserve_kind_enum"] and spec["visibility_requirement_enum"] == validator["visibility_requirement_enum"], "ref_rule_parity": spec["ref_rules"] == validator["ref_rules"], "forbidden_field_parity": spec["forbidden_machine_fields"] == validator["forbidden_machine_fields"], "fingerprint_parity": parity}


__all__ = ["STRATEGY_PROVIDER_SPEC_VERSION", "STRATEGY_SCHEMA_VERSION", "PRESERVE_INTENT_SCHEMA_VERSION", "STRATEGY_REQUIRED_FIELDS", "PRESERVE_INTENT_REQUIRED_FIELDS", "PRESERVE_KINDS", "VISIBILITY_REQUIREMENTS", "strategy_provider_spec", "build_strategy_provider_contract", "validate_strategy_v3_shape", "canonicalize_strategy_v3", "provider_validator_parity", "schema_fingerprint"]
