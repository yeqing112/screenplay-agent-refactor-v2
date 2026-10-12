"""Provider-neutral strict structured-output qualification helpers.

This module contains no network transport. It defines a minimal capability
probe, a conservative provider-schema compiler, structural validation, and
profile-scoped qualification classification.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


PROBE_SCHEMA_VERSION = "provider_structured_output_probe_v1"
QUALIFICATION_VERSION = "provider_structured_output_qualification_v1"
STRUCTURAL_KEYWORDS = {
    "type", "properties", "required", "additionalProperties", "items",
    "enum", "const", "minLength", "minItems", "uniqueItems",
}
ANNOTATION_KEYWORDS = {
    "$schema", "$id", "title", "description", "default", "examples",
    "deprecated", "readOnly", "writeOnly", "trust", "authority",
    "schema_version", "provider_may_not_supply", "surface_form_semantics", "notes",
}
FORBIDDEN_DIALECT_KEYWORDS = {"$ref", "$defs", "definitions", "patternProperties", "oneOf", "anyOf", "allOf", "not", "if", "then", "else"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def minimal_probe_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["probe", "ordinal"],
        "properties": {
            "probe": {"type": "string", "enum": ["STRICT_SCHEMA_OK"]},
            "ordinal": {"type": "integer", "enum": [7]},
        },
    }


def strict_probe_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": PROBE_SCHEMA_VERSION,
            "strict": True,
            "schema": minimal_probe_schema(),
        },
    }


def provider_identity(*, profile_id: str, provider: str, model: str, base_host: str) -> dict[str, str]:
    identity = {"profile_id": str(profile_id), "provider": str(provider), "model": str(model), "base_host": str(base_host)}
    return {**identity, "provider_identity_fingerprint": fingerprint(identity)}


def compile_provider_strict_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Keep machine-enforceable supported keywords and remove annotations.

    External or unresolved refs are rejected. Unknown keywords are treated as
    internal annotations and stripped; callers can inspect the audit to see
    every removed key. A list of types is rejected because it is a union.
    """
    before = fingerprint(schema)
    removed: list[str] = []
    errors: list[str] = []

    def compile_node(node: Any, path: str) -> Any:
        if isinstance(node, bool):
            return node
        if not isinstance(node, Mapping):
            errors.append(f"SCHEMA_NODE_NOT_OBJECT:{path}")
            return {}
        output: dict[str, Any] = {}
        for raw_key, value in node.items():
            key = str(raw_key)
            here = f"{path}.{key}"
            if key in FORBIDDEN_DIALECT_KEYWORDS:
                errors.append(f"UNSUPPORTED_SCHEMA_KEYWORD:{here}")
                continue
            if key not in STRUCTURAL_KEYWORDS:
                if key in ANNOTATION_KEYWORDS:
                    removed.append(here)
                else:
                    errors.append(f"UNSUPPORTED_SCHEMA_KEYWORD:{here}")
                continue
            if key == "type":
                if isinstance(value, list):
                    errors.append(f"UNION_TYPE_UNSUPPORTED:{here}")
                elif value not in {"object", "array", "string", "integer", "number", "boolean", "null"}:
                    errors.append(f"JSON_SCHEMA_TYPE_INVALID:{here}")
                else:
                    output[key] = value
            elif key == "properties":
                if not isinstance(value, Mapping):
                    errors.append(f"PROPERTIES_MUST_BE_OBJECT:{here}")
                    output[key] = {}
                else:
                    output[key] = {str(name): compile_node(child, f"{here}.{name}") for name, child in sorted(value.items(), key=lambda item: str(item[0]))}
            elif key == "items":
                output[key] = compile_node(value, here)
            elif key == "additionalProperties" and isinstance(value, Mapping):
                output[key] = compile_node(value, here)
            else:
                output[key] = value
        return output

    compiled = compile_node(schema, "$" )
    has_errors = bool(errors)
    audit = {
        "status": "PASS" if not errors else "BLOCKED",
        "removed_annotation_paths": sorted(set(removed)),
        "errors": sorted(set(errors)),
        "input_fingerprint": before,
        "output_fingerprint": fingerprint(compiled) if not has_errors else None,
        "diagnostic_partial_output_fingerprint": fingerprint(compiled) if has_errors else None,
        "input_unchanged": fingerprint(schema) == before,
        "deterministic": True,
        "structural_keywords": sorted(STRUCTURAL_KEYWORDS),
        "annotation_keywords": sorted(ANNOTATION_KEYWORDS),
    }
    return {"schema": compiled if not has_errors else None, "diagnostic_partial_schema": compiled if has_errors else None, "audit": audit}


def validate_json_schema_subset(value: Any, schema: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []

    def validate(item: Any, node: Any, path: str) -> None:
        if isinstance(node, bool):
            if not node:
                errors.append(f"FALSE_SCHEMA:{path}")
            return
        if not isinstance(node, Mapping):
            errors.append(f"SCHEMA_NODE_INVALID:{path}")
            return
        expected = node.get("type")
        type_ok = {
            "object": isinstance(item, dict),
            "array": isinstance(item, list),
            "string": isinstance(item, str),
            "integer": isinstance(item, int) and not isinstance(item, bool),
            "number": isinstance(item, (int, float)) and not isinstance(item, bool),
            "boolean": isinstance(item, bool),
            "null": item is None,
            None: True,
        }.get(expected, False)
        if not type_ok:
            errors.append(f"TYPE_MISMATCH:{path}:{expected}")
            return
        if "const" in node and item != node["const"]:
            errors.append(f"CONST_MISMATCH:{path}")
        if "enum" in node and item not in node["enum"]:
            errors.append(f"ENUM_MISMATCH:{path}")
        if isinstance(item, str) and len(item) < int(node.get("minLength", 0)):
            errors.append(f"MIN_LENGTH:{path}")
        if isinstance(item, list):
            if len(item) < int(node.get("minItems", 0)):
                errors.append(f"MIN_ITEMS:{path}")
            if node.get("uniqueItems") is True and len({canonical_json(v) for v in item}) != len(item):
                errors.append(f"DUPLICATE_ITEMS:{path}")
            if isinstance(node.get("items"), Mapping):
                for index, child in enumerate(item):
                    validate(child, node["items"], f"{path}[{index}]")
        if isinstance(item, dict):
            required = node.get("required", [])
            for key in required if isinstance(required, list) else []:
                if key not in item:
                    errors.append(f"REQUIRED_MISSING:{path}.{key}")
            properties = node.get("properties", {}) if isinstance(node.get("properties"), Mapping) else {}
            for key, child in item.items():
                if key in properties:
                    validate(child, properties[key], f"{path}.{key}")
                elif node.get("additionalProperties") is False:
                    errors.append(f"ADDITIONAL_PROPERTY:{path}.{key}")
                elif isinstance(node.get("additionalProperties"), Mapping):
                    validate(child, node["additionalProperties"], f"{path}.{key}")

    validate(value, schema, "$" )
    return {"status": "PASS" if not errors else "BLOCKED", "errors": sorted(set(errors))}


def classify_probe(*, http_status: int | None, finish_reason: str = "", raw: str = "", transport_error: str = "", response_format_rejected: bool = False) -> dict[str, Any]:
    if transport_error and not http_status:
        return {"capability": "AMBIGUOUS", "status": "PROVIDER_STRUCTURED_OUTPUT_QUALIFICATION_SUBMISSION_AMBIGUOUS", "strict_proven": False}
    if response_format_rejected:
        return {"capability": "JSON_OBJECT_ONLY", "status": "PROVIDER_STRUCTURED_OUTPUT_CAPABILITY_QUALIFIED", "strict_proven": False}
    if int(http_status or 0) != 200:
        return {"capability": "UNKNOWN", "status": "PROVIDER_STRUCTURED_OUTPUT_QUALIFICATION_SUBMISSION_AMBIGUOUS", "strict_proven": False}
    try:
        value = json.loads(raw)
        parse_ok = isinstance(value, dict)
    except (TypeError, ValueError, json.JSONDecodeError):
        value = None
        parse_ok = False
    exact_keys = sorted(value) == ["ordinal", "probe"] if isinstance(value, dict) else False
    schema_result = validate_json_schema_subset(value, minimal_probe_schema()) if parse_ok else {"status": "BLOCKED", "errors": ["STRICT_JSON_PARSE_FAILED"]}
    normal_finish = str(finish_reason).lower() in {"stop", "completed", "complete", "end_turn", "stop_sequence"}
    passed = parse_ok and normal_finish and exact_keys and schema_result["status"] == "PASS" and "forbidden_extra" not in value
    return {
        "capability": "JSON_SCHEMA_STRICT_SUPPORTED" if passed else "JSON_SCHEMA_SUPPORTED",
        "status": "PROVIDER_STRUCTURED_OUTPUT_CAPABILITY_QUALIFIED" if passed else "PROVIDER_JSON_SCHEMA_STRICT_CAPABILITY_NOT_PROVEN",
        "strict_proven": passed,
        "parse_ok": parse_ok,
        "normal_finish": normal_finish,
        "exact_keys": exact_keys,
        "schema_validation": schema_result,
        "forbidden_extra_present": isinstance(value, dict) and "forbidden_extra" in value,
    }


def is_explicit_schema_rejection(http_status: int | None, error_text: str) -> bool:
    if int(http_status or 0) not in {400, 415, 422, 501}:
        return False
    text = str(error_text or "").lower()
    markers = ("unsupported response_format", "unsupported json_schema", "invalid response_format", "json_schema is not supported", "response_format.type is not supported", "unknown response_format type")
    return any(marker in text for marker in markers)


def qualification_fingerprint(*, identity: Mapping[str, Any], capability: str, probe_schema_fingerprint: str, request_fingerprint: str, raw_response_sha256: str, qualified: bool) -> dict[str, Any]:
    record = {
        "schema_version": QUALIFICATION_VERSION,
        **{key: identity.get(key) for key in ("profile_id", "provider", "model", "base_host", "provider_identity_fingerprint")},
        "capability": capability,
        "probe_schema_fingerprint": probe_schema_fingerprint,
        "request_fingerprint": request_fingerprint,
        "raw_response_sha256": raw_response_sha256,
        "qualified": bool(qualified),
    }
    record["qualification_fingerprint"] = fingerprint(record)
    return record


__all__ = [
    "PROBE_SCHEMA_VERSION", "QUALIFICATION_VERSION", "STRUCTURAL_KEYWORDS", "ANNOTATION_KEYWORDS", "minimal_probe_schema", "strict_probe_response_format", "provider_identity", "compile_provider_strict_schema", "validate_json_schema_subset", "classify_probe", "is_explicit_schema_rejection", "qualification_fingerprint", "fingerprint",
]
