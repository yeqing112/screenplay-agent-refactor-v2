"""Phase E semantic PromptIR compiler and provider-neutral adapter boundary.

This module consumes only a validated ``StoryboardProductionSnapshot``.  It
does not read ScriptIR, ShotPlan prose, legacy ``visual_prompt_*`` columns or
call a provider.  All values in the PromptIR are projections of structured
Storyboard semantics, explicit asset authority and explicit runtime policy.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


PROMPT_IR_SCHEMA_VERSION = "prompt_ir_v2"
GENERATION_POLICY_SCHEMA_VERSION = "generation_policy_v1"
MODEL_PROFILE_SCHEMA_VERSION = "model_profile_v1"
GENERATION_PAYLOAD_SCHEMA_VERSION = "generation_payload_v1"
PROMPT_IR_COMPILER_VERSION = "prompt_ir_semantic_compiler_v1"
PROMPT_IR_COMPILER_POLICY_VERSION = "prompt_ir_compiler_policy_v1"

SOURCE_SEMANTIC_PROJECTION = "SOURCE_SEMANTIC_PROJECTION"
STORYBOARD_SEMANTIC_PROJECTION = "STORYBOARD_SEMANTIC_PROJECTION"
ASSET_AUTHORITY_BINDING = "ASSET_AUTHORITY_BINDING"
GENERATION_POLICY = "GENERATION_POLICY"
MODEL_AGNOSTIC_PROMPT_SEMANTIC = "MODEL_AGNOSTIC_PROMPT_SEMANTIC"
MODEL_ADAPTER_OUTPUT = "MODEL_ADAPTER_OUTPUT"
MEDIA_REQUEST_METADATA = "MEDIA_REQUEST_METADATA"
UNKNOWN_INVALID = "UNKNOWN_INVALID"


class PromptIRPhaseEError(ValueError):
    def __init__(self, code: str, message: str, *, diagnostics: list[dict[str, Any]] | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.diagnostics = diagnostics or [{"code": code, "message": message, "severity": "blocked"}]


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def canonical_target_media(value: Any, *, required: bool = True) -> str:
    """Return the canonical media scope or fail closed.

    Pointer rows are persisted only as exact ``IMAGE``/``VIDEO`` values.  A
    request boundary may normalize case, but no resolver may infer a scope or
    silently default to IMAGE.
    """
    raw = _text(value)
    if not raw:
        if required:
            raise PromptIRPhaseEError("PROMPT_IR_MEDIA_SCOPE_REQUIRED", "target_media is required for current PromptIR resolution.")
        return ""
    target = raw.upper()
    if target not in {"IMAGE", "VIDEO"}:
        raise PromptIRPhaseEError("PROMPT_IR_MEDIA_SCOPE_INVALID", "target_media must be IMAGE or VIDEO.")
    return target


def build_generation_policy(policy: dict[str, Any] | None = None, *, allow_default: bool = True) -> dict[str, Any]:
    """Normalize a policy.

    Pure compiler fixtures may request the historical deterministic default by
    leaving ``allow_default`` enabled.  Production entry points always pass
    ``allow_default=False`` so an omitted policy cannot silently become a
    TEXT_TO_IMAGE request.
    """
    raw = dict(policy) if isinstance(policy, dict) else {}
    if not allow_default and (not _text(raw.get("mode")) or not _text(raw.get("target_media"))):
        raise PromptIRPhaseEError("GENERATION_POLICY_REQUIRED", "Production PromptIR compilation requires an explicit mode and target_media.")
    mode = _text(raw.get("mode") or "TEXT_TO_IMAGE").upper()
    target = _text(raw.get("target_media") or ("VIDEO" if mode.endswith("VIDEO") else "IMAGE")).upper()
    required = sorted({_text(item).upper() for item in _list(raw.get("required_asset_classes")) if _text(item)})
    optional = sorted({_text(item).upper() for item in _list(raw.get("optional_asset_classes")) if _text(item)})
    result = {
        "schema_version": GENERATION_POLICY_SCHEMA_VERSION,
        "mode": mode,
        "target_media": target,
        "required_asset_classes": required,
        "optional_asset_classes": optional,
        "style_profile_id": _text(raw.get("style_profile_id")),
        "language": _text(raw.get("language")),
        "source": _text(raw.get("source") or "explicit_request"),
    }
    if mode not in {"TEXT_TO_IMAGE", "IMAGE_TO_VIDEO", "TEXT_TO_VIDEO", "IMAGE_EDIT"}:
        raise PromptIRPhaseEError("GENERATION_POLICY_INVALID", f"Unsupported generation policy mode: {mode}.")
    result["fingerprint"] = fingerprint({key: value for key, value in result.items() if key != "fingerprint"})
    return result


def build_model_profile(profile: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = dict(profile) if isinstance(profile, dict) else {}
    family = _text(raw.get("model_family")).upper()
    adapter_id = _text(raw.get("adapter_id") or family.lower())
    capabilities = dict(raw.get("capabilities")) if isinstance(raw.get("capabilities"), dict) else {}
    result = {
        "schema_version": MODEL_PROFILE_SCHEMA_VERSION,
        "model_family": family,
        "adapter_id": adapter_id,
        "capabilities": capabilities,
        "provider_config_ref": _text(raw.get("provider_config_ref")),
    }
    result["fingerprint"] = fingerprint({key: value for key, value in result.items() if key != "fingerprint"})
    return result


def _asset_identity_index(semantic: dict[str, Any]) -> dict[str, dict[str, Any]]:
    bindings = _dict(semantic.get("asset_identity_bindings"))
    canonical_assets = _dict(bindings.get("canonical_asset_identity"))
    result: dict[str, dict[str, Any]] = {}
    for asset_type, key in (("scene", "scene"), ("character", "characters"), ("prop", "props")):
        values = canonical_assets.get(key)
        if not isinstance(values, list):
            values = [values] if values not in (None, "") else []
        for value in values:
            identity = _text(value.get("canonical_id") if isinstance(value, dict) else value)
            if identity:
                result[f"{asset_type}:{identity}"] = {"asset_type": asset_type, "asset_identity_ref": identity}
    return result


def _ordered_asset_identity_refs(semantic: dict[str, Any]) -> list[str]:
    """Return explicit scene/subject/prop order from the semantic handoff."""
    bindings = _dict(semantic.get("asset_identity_bindings"))
    canonical_assets = _dict(bindings.get("canonical_asset_identity"))
    ordered: list[str] = []

    def add(asset_type: str, value: Any) -> None:
        identity = _text(value.get("canonical_id") if isinstance(value, dict) else value)
        token = f"{asset_type}:{identity}" if identity else ""
        if token and token not in ordered:
            ordered.append(token)

    add("scene", canonical_assets.get("scene") or semantic.get("scene_id"))
    character_values = _list(canonical_assets.get("characters")) or _list(semantic.get("subjects"))
    for value in character_values:
        add("character", value)
    prop_values = _list(canonical_assets.get("props")) or _list(_dict(semantic.get("spatial")).get("prop_refs")) or _list(semantic.get("props"))
    for value in prop_values:
        add("prop", value)
    return ordered


def _snapshot_authority(snapshot: dict[str, Any], semantic: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    envelope = _dict(snapshot.get("authority_envelope"))
    shot_plan = _dict(envelope.get("shot_plan"))
    blocking = _dict(envelope.get("scene_blocking") or envelope.get("blocking"))
    authority = _dict(snapshot.get("storyboard_materialization_authority"))
    provenance = _dict(semantic.get("projection_provenance"))
    return {
        "storyboard_materialization_set_id": authority.get("materialization_set_id"),
        "storyboard_set_payload_fingerprint": _text(authority.get("set_payload_fingerprint")),
        "storyboard_projection_fingerprint": _text(row.get("projection_fingerprint")),
        "visual_semantic_handoff_fingerprint": fingerprint({key: value for key, value in semantic.items() if key != "projection_provenance"}),
        "shot_plan_authority_fingerprint": _text(provenance.get("source_shot_plan_authority_fingerprint") or shot_plan.get("authority_fingerprint")),
        "blocking_authority_fingerprint": _text(provenance.get("blocking_authority_fingerprint") or blocking.get("authority_fingerprint")),
    }


def _semantic_prompt_projection(snapshot: dict[str, Any], row: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    semantic = _dict(row.get("visual_semantic_handoff"))
    if not semantic or _text(semantic.get("schema_version")) != "storyboard_visual_semantic_handoff_v1":
        raise PromptIRPhaseEError("PROMPT_IR_SEMANTIC_HANDOFF_MISSING", "StoryboardProductionSnapshot row has no current visual semantic handoff.")
    if _text(snapshot.get("storyboard_materialization_authority", {}).get("stale_status")) != "FRESH":
        raise PromptIRPhaseEError("STORYBOARD_MATERIALIZATION_STALE", "PromptIR compilation requires a fresh StoryboardProductionSnapshot.")
    assets = _asset_identity_index(semantic)
    characters = []
    for subject in _list(semantic.get("subjects")):
        identity = _text(subject)
        characters.append({"subject_ref": identity, "asset_identity_ref": assets.get(f"character:{identity}", {}).get("asset_identity_ref", identity)})
    props = []
    for prop in _list(semantic.get("props")):
        identity = _text(prop)
        props.append({"prop_ref": identity, "asset_identity_ref": assets.get(f"prop:{identity}", {}).get("asset_identity_ref", identity)})
    camera = _dict(semantic.get("camera"))
    continuity = _dict(semantic.get("continuity"))
    temporal = _dict(semantic.get("temporal_intent"))
    projection = _dict(row.get("projection_payload"))
    prompt_handoff = _dict(row.get("prompt_compiler_handoff"))
    duration = projection.get("duration")
    if duration is None:
        duration = projection.get("duration_hint_seconds")
    source_authority = _snapshot_authority(snapshot, semantic, row)
    source_authority["generation_policy_fingerprint"] = _text(policy.get("fingerprint"))
    return {
        "schema_version": PROMPT_IR_SCHEMA_VERSION,
        "authority_classes": {
            "source_authority": SOURCE_SEMANTIC_PROJECTION,
            "storyboard_semantics": STORYBOARD_SEMANTIC_PROJECTION,
            "asset_bindings": ASSET_AUTHORITY_BINDING,
            "generation_policy": GENERATION_POLICY,
            "semantic_payload": MODEL_AGNOSTIC_PROMPT_SEMANTIC,
            "adapter_output": MODEL_ADAPTER_OUTPUT,
            "media_metadata": MEDIA_REQUEST_METADATA,
        },
        "scene_id": _text(semantic.get("scene_id") or snapshot.get("scene_id")),
        "plan_shot_id": _text(semantic.get("plan_shot_id") or row.get("plan_shot_id")),
        "storyboard_shot_id": row.get("storyboard_shot_id"),
        "source_authority": source_authority,
        "semantic_refs": {
            "beat_refs": _list(semantic.get("beat_refs")),
            "director_decision_refs": _list(semantic.get("director_decision_refs")),
            "requirement_refs": _list(semantic.get("requirement_refs")),
            "information_refs": _list(semantic.get("information_refs")),
            "reaction_contract_refs": _list(semantic.get("reaction_contract_refs")),
            "coverage_roles": _list(semantic.get("coverage_roles")),
        },
        "subjects": characters,
        "props": props,
        "environment": {
            "scene_ref": _text(semantic.get("scene_id") or snapshot.get("scene_id")),
            "asset_identity_ref": _dict(semantic.get("asset_identity_bindings")).get("canonical_asset_identity", {}).get("scene"),
        },
        "action": {"action_beats": _list(prompt_handoff.get("action_beats")) or _list(projection.get("action_beats"))},
        "camera": {key: camera.get(key) for key in ("framing_class", "orientation", "support", "movement", "movement_trigger", "movement_target", "movement_end_condition")},
        "continuity": {key: continuity.get(key) for key in ("axis_ref", "axis_refs", "axis_policy", "screen_side_assignments", "look_direction")},
        "spatial": {
            "entry_state_ref": _text(_dict(semantic.get("spatial")).get("entry_state_ref")),
            "exit_state_ref": _text(_dict(semantic.get("spatial")).get("exit_state_ref")),
            "blocking_state_refs": _list(_dict(semantic.get("spatial")).get("blocking_state_refs")),
            "subject_zones": _dict(_dict(semantic.get("spatial")).get("subject_zones")),
            "prop_refs": _list(_dict(semantic.get("spatial")).get("prop_refs")),
        },
        "temporal": {
            "duration_hint_seconds": duration,
            "duration_mode": temporal.get("duration_mode"),
            "cut_trigger": temporal.get("cut_trigger"),
            "continuous_take": continuity.get("continuous_take"),
            "cut_events": _list(continuity.get("cut_events")),
        },
        "information_visibility": semantic.get("information_visibility"),
        "generation_constraints": {
            "must_include_subject_refs": [_text(item.get("subject_ref")) for item in characters if _text(item.get("subject_ref"))],
            "must_include_prop_refs": [_text(item.get("prop_ref")) for item in props if _text(item.get("prop_ref"))],
            "must_preserve_axis": bool(continuity.get("axis_ref") or continuity.get("axis_refs")),
        },
        "asset_authority_bindings": {"identity_refs": _ordered_asset_identity_refs(semantic), "resolved": []},
        "generation_policy": policy,
        "qualification_state": "PROMPT_IR_QUALIFIED",
        "prompt_ir_semantic_ready": True,
        "model_generation_ready": False,
        "compiler_provenance": {"origin": "STORYBOARD_PRODUCTION_SNAPSHOT", "compiler_version": PROMPT_IR_COMPILER_VERSION, "compiler_policy_version": PROMPT_IR_COMPILER_POLICY_VERSION},
    }


def prompt_ir_semantic_projection(prompt_ir: dict[str, Any]) -> dict[str, Any]:
    payload = dict(prompt_ir) if isinstance(prompt_ir, dict) else {}
    # Hashes are transport metadata; all structured authority, including
    # current asset identities and the explicit generation policy, remains in
    # the semantic comparison.  This is what makes subject/prop/asset and
    # policy tampering fail closed.
    for key in ("prompt_ir_payload_fingerprint", "payload_hash", "prompt_ir_semantic_fingerprint"):
        payload.pop(key, None)
    return payload


def _prompt_ir_payload_basis(prompt_ir: dict[str, Any]) -> dict[str, Any]:
    payload = dict(prompt_ir) if isinstance(prompt_ir, dict) else {}
    for key in ("prompt_ir_payload_fingerprint", "payload_hash"):
        payload.pop(key, None)
    return payload


def _diff(expected: Any, actual: Any, path: str = "") -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [{"code": "PROMPT_IR_SEMANTIC_MISMATCH", "path": path or "$", "kind": "changed"}]
        for key in expected:
            if key not in actual:
                errors.append({"code": "PROMPT_IR_SEMANTIC_MISSING", "path": f"{path}.{key}" if path else key})
            else:
                errors.extend(_diff(expected[key], actual[key], f"{path}.{key}" if path else key))
        for key in actual:
            if key not in expected:
                errors.append({"code": "PROMPT_IR_SEMANTIC_EXTRA", "path": f"{path}.{key}" if path else key})
        return errors
    if expected != actual:
        errors.append({"code": "PROMPT_IR_SEMANTIC_MISMATCH", "path": path or "$", "expected": expected, "actual": actual})
    return errors


def compare_prompt_ir_semantics(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    errors = _diff(prompt_ir_semantic_projection(expected), prompt_ir_semantic_projection(actual))
    return {"empty": not errors, "errors": errors, "missing": [item for item in errors if item.get("code") == "PROMPT_IR_SEMANTIC_MISSING"], "extra": [item for item in errors if item.get("code") == "PROMPT_IR_SEMANTIC_EXTRA"]}


def classify_prompt_ir_compile_transition(*, current_payload: dict[str, Any], expected_payload: dict[str, Any]) -> str:
    """Classify a compile intent after the stored current row is trusted."""
    return "REUSE" if _text(current_payload.get("payload_hash") or current_payload.get("prompt_ir_payload_fingerprint")) == _text(expected_payload.get("payload_hash") or expected_payload.get("prompt_ir_payload_fingerprint")) else "REVISION"


def _historical_failure(code: str, message: str, *, diagnostics: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "integrity_valid": False,
        "current_lineage_valid": None,
        "obsolete_due_to_upstream_change": None,
        "tampered": True,
        "code": code,
        "message": message,
        "diagnostics": diagnostics or [{"code": code, "message": message, "severity": "blocked"}],
    }


def _historical_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _historical_asset_payload_hash(payload: dict[str, Any]) -> str:
    """Accept both pilot seed payloads and authority API payloads.

    The authority API stores ``payload_hash`` inside the payload after hashing
    the rest of the spec; early provider-free fixtures hash the whole payload.
    Historical validation supports both representations without consulting a
    current pointer.
    """
    from core.visual_asset_authority import fingerprint as asset_fingerprint

    basis = dict(payload)
    basis.pop("payload_hash", None)
    return asset_fingerprint(basis if "payload_hash" in payload else payload)


def validate_prompt_ir_historical_integrity(session: Any, *, version: Any, authority: Any, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prove a stored PromptIR against its exact historical authorities.

    This validator deliberately does not read a current Storyboard or visual
    asset pointer.  Stale historical rows remain usable as immutable evidence;
    only missing or fingerprint-inconsistent historical objects fail closed.
    """
    from core.storyboard_materializer import (
        _live_row_projection_payload,
        _row_projection_payload,
        build_storyboard_production_snapshot,
        projection_fingerprint,
        authority_envelope_fingerprint,
    )
    from core.visual_asset_authority import build_reference_media_authority
    from models import StoryboardMaterializationSet, StoryboardShot, VisualAssetVersion, VisualReferenceAuthority

    stored = payload if isinstance(payload, dict) else _historical_json(getattr(version, "payload_json", "{}"), {})
    if not isinstance(stored, dict):
        return _historical_failure("PROMPT_IR_HISTORICAL_SEMANTIC_MISMATCH", "Stored PromptIR payload is not an object.")
    envelope = _historical_json(getattr(authority, "envelope_json", "{}"), {})
    source = _dict(stored.get("source_authority"))
    envelope_source = _dict(envelope.get("source_authority"))
    if not isinstance(envelope, dict) or _text(envelope.get("schema_version")) != "prompt_ir_authority_envelope_v2":
        return _historical_failure("PROMPT_IR_HISTORICAL_LINEAGE_MISSING", "PromptIR authority envelope does not declare the v2 historical lineage contract.")
    if _text(envelope.get("envelope_fingerprint")) != fingerprint({key: value for key, value in envelope.items() if key != "envelope_fingerprint"}):
        return _historical_failure("PROMPT_IR_HISTORICAL_AUTHORITY_TAMPERED", "PromptIR authority envelope fingerprint is invalid.")
    if envelope_source != source or envelope.get("generation_policy") != stored.get("generation_policy") or envelope.get("asset_authority_bindings") != stored.get("asset_authority_bindings"):
        return _historical_failure("PROMPT_IR_HISTORICAL_AUTHORITY_TAMPERED", "PromptIR envelope does not bind the stored historical lineage.")

    set_id = source.get("storyboard_materialization_set_id")
    shot_id = stored.get("storyboard_shot_id")
    if set_id in (None, "") or shot_id in (None, ""):
        return _historical_failure("PROMPT_IR_HISTORICAL_LINEAGE_MISSING", "PromptIR payload is missing the historical materialization set or StoryboardShot ID.")
    if str(getattr(version, "storyboard_shot_id", shot_id)) != str(shot_id) or str(getattr(authority, "storyboard_shot_id", shot_id)) != str(shot_id):
        return _historical_failure("PROMPT_IR_HISTORICAL_AUTHORITY_TAMPERED", "PromptIR version and authority do not bind the stored historical StoryboardShot.")
    if getattr(version, "materialization_set_id", None) not in (None, 0, "", int(set_id)):
        return _historical_failure("PROMPT_IR_HISTORICAL_AUTHORITY_TAMPERED", "PromptIR version does not bind the stored historical materialization set.")
    materialization_set = session.query(StoryboardMaterializationSet).filter_by(id=int(set_id), book_id=version.book_id, episode=version.episode).first()
    if materialization_set is None:
        return _historical_failure("PROMPT_IR_HISTORICAL_LINEAGE_MISSING", "Historical StoryboardMaterializationSet is missing.", diagnostics=[{"code": "PROMPT_IR_HISTORICAL_LINEAGE_MISSING", "materialization_set_id": set_id}])
    set_envelope = _historical_json(materialization_set.authority_envelope_json, {})
    if not isinstance(set_envelope, dict) or _text(set_envelope.get("authority_fingerprint")) != authority_envelope_fingerprint(set_envelope):
        return _historical_failure("PROMPT_IR_HISTORICAL_AUTHORITY_TAMPERED", "Historical Storyboard authority envelope fingerprint is invalid.")
    materialization_meta = _dict(set_envelope.get("materialization"))
    if str(materialization_meta.get("id")) != str(materialization_set.id) or _text(materialization_meta.get("fingerprint")) != _text(materialization_set.set_payload_fingerprint):
        return _historical_failure("PROMPT_IR_HISTORICAL_AUTHORITY_TAMPERED", "Historical Storyboard materialization binding does not match the persisted Set.")
    if _text(source.get("storyboard_set_payload_fingerprint")) != _text(materialization_set.set_payload_fingerprint):
        return _historical_failure("PROMPT_IR_HISTORICAL_AUTHORITY_TAMPERED", "PromptIR does not bind the historical Storyboard Set fingerprint.")

    rows = session.query(StoryboardShot).filter_by(book_id=version.book_id, episode=version.episode, materialization_set_id=materialization_set.id).order_by(StoryboardShot.shot_id).all()
    expected_ids = _historical_json(materialization_set.ordered_plan_shot_ids, [])
    if not isinstance(expected_ids, list) or len(rows) != len(expected_ids) or int(materialization_set.expected_shot_count) != len(rows) or int(materialization_set.materialized_shot_count) != len(rows):
        return _historical_failure("PROMPT_IR_HISTORICAL_AUTHORITY_TAMPERED", "Historical Storyboard Set cardinality is inconsistent.")
    historical_shot = next((row for row in rows if int(row.id) == int(shot_id)), None)
    if historical_shot is None:
        return _historical_failure(
            "PROMPT_IR_HISTORICAL_LINEAGE_MISSING",
            "Historical StoryboardShot is missing.",
            diagnostics=[{"code": "PROMPT_IR_HISTORICAL_LINEAGE_MISSING", "storyboard_shot_id": shot_id, "materialization_set_id": materialization_set.id}],
        )
    for row in rows:
        meta = _historical_json(row.meta_info, {})
        stored_projection = meta.get("projection_payload") if isinstance(meta, dict) and isinstance(meta.get("projection_payload"), dict) else None
        if stored_projection is not None:
            live_projection = _live_row_projection_payload(row, meta)
            live_projection.pop("visual_semantic_handoff", None)
            stored_projection_without_semantic = dict(stored_projection)
            stored_projection_without_semantic.pop("visual_semantic_handoff", None)
            if live_projection != stored_projection_without_semantic:
                return _historical_failure("PROMPT_IR_HISTORICAL_AUTHORITY_TAMPERED", "Historical Storyboard projection columns were modified.")
        if not _text(row.projection_fingerprint) or _text(row.projection_fingerprint) != projection_fingerprint(_row_projection_payload(row, meta)):
            return _historical_failure("PROMPT_IR_HISTORICAL_AUTHORITY_TAMPERED", "Historical Storyboard projection fingerprint is invalid.")
        semantic = meta.get("visual_semantic_handoff") if isinstance(meta, dict) and isinstance(meta.get("visual_semantic_handoff"), dict) else {}
        semantic_fp = fingerprint({key: value for key, value in semantic.items() if key != "projection_provenance"})
        if row.id == int(shot_id) and (_text(source.get("storyboard_projection_fingerprint")) != _text(row.projection_fingerprint) or _text(source.get("visual_semantic_handoff_fingerprint")) != semantic_fp):
            return _historical_failure("PROMPT_IR_HISTORICAL_AUTHORITY_TAMPERED", "PromptIR does not bind the exact historical StoryboardShot projection.")

    historical_bindings: list[dict[str, Any]] = []
    resolved = _list(_dict(stored.get("asset_authority_bindings")).get("resolved"))
    for binding in resolved:
        if not isinstance(binding, dict):
            return _historical_failure("PROMPT_IR_HISTORICAL_AUTHORITY_TAMPERED", "Historical asset binding is not an object.")
        version_id = binding.get("asset_version_id")
        asset_version = session.query(VisualAssetVersion).filter_by(id=version_id, book_id=version.book_id).first() if version_id not in (None, "") else None
        if asset_version is None:
            return _historical_failure("PROMPT_IR_HISTORICAL_LINEAGE_MISSING", "Historical VisualAssetVersion is missing.", diagnostics=[{"code": "PROMPT_IR_HISTORICAL_LINEAGE_MISSING", "asset_version_id": version_id}])
        asset_payload = _historical_json(asset_version.payload_json, {})
        if not isinstance(asset_payload, dict) or _text(binding.get("asset_authority_ref")) != _text(asset_version.asset_key) or _text(binding.get("asset_version_fingerprint")) != _text(asset_version.payload_hash) or _historical_asset_payload_hash(asset_payload) != _text(asset_version.payload_hash):
            return _historical_failure("PROMPT_IR_HISTORICAL_AUTHORITY_TAMPERED", "Historical VisualAssetVersion fingerprint or identity is invalid.")
        historical_binding = {"asset_type": asset_version.asset_type, "canonical_asset_id": asset_version.asset_key.rsplit(":", 1)[-1], "asset_key": asset_version.asset_key, "asset_version_id": asset_version.id, "revision": asset_version.revision, "payload": asset_payload, "payload_hash": asset_version.payload_hash, "asset_version_fingerprint": asset_version.payload_hash, "authority_fingerprint": asset_version.payload_hash, "authority_status": asset_version.authority_status, "stale_status": "FRESH"}
        reference_fp = _text(binding.get("reference_authority_fingerprint") or binding.get("reference_authority_ref"))
        if reference_fp:
            reference_row = session.query(VisualReferenceAuthority).filter_by(authority_fingerprint=reference_fp).first()
            if reference_row is None:
                return _historical_failure("PROMPT_IR_HISTORICAL_LINEAGE_MISSING", "Historical ReferenceAuthority is missing.", diagnostics=[{"code": "PROMPT_IR_HISTORICAL_LINEAGE_MISSING", "authority_fingerprint": reference_fp}])
            if str(reference_row.asset_version_id) != str(asset_version.id) or _text(reference_row.asset_version_fingerprint) != _text(asset_version.payload_hash):
                return _historical_failure("PROMPT_IR_HISTORICAL_AUTHORITY_TAMPERED", "Historical ReferenceAuthority is bound to a different asset version.")
            reference_payload = build_reference_media_authority(asset_key=reference_row.asset_key, asset_version_id=reference_row.asset_version_id, asset_version_fingerprint=reference_row.asset_version_fingerprint, reference_scope=_historical_json(reference_row.reference_scope_json, {}), image_identity=reference_row.image_identity, checksum=reference_row.checksum, storage_reference=_historical_json(reference_row.storage_reference_json, {}), generation_provenance=_historical_json(reference_row.generation_provenance_json, {}), reference_token_mapping=_historical_json(reference_row.reference_token_mapping_json, {}), lock_revision=reference_row.lock_revision, status=reference_row.status)
            if _text(reference_payload.get("authority_fingerprint")) != _text(reference_row.authority_fingerprint):
                return _historical_failure("PROMPT_IR_HISTORICAL_AUTHORITY_TAMPERED", "Historical ReferenceAuthority fingerprint is invalid.")
            historical_binding["reference_authority"] = {"status": reference_row.status, "stale_status": "FRESH", "authority_fingerprint": reference_row.authority_fingerprint, "asset_version_id": reference_row.asset_version_id, "asset_version_fingerprint": reference_row.asset_version_fingerprint, "reference_token": _historical_json(reference_row.reference_token_mapping_json, {}).get("token", ""), "reference_name": _historical_json(reference_row.reference_token_mapping_json, {}).get("name", "")}
        historical_bindings.append(historical_binding)

    from copy import deepcopy
    historical_snapshot = build_storyboard_production_snapshot(materialization_set=materialization_set, rows=rows, authority_envelope=set_envelope)
    # Historical rows may be stale because a newer Set is current.  Staleness
    # is currentness metadata, not corruption, so compile a read-only copy.
    historical_snapshot_for_compile = deepcopy(historical_snapshot)
    historical_snapshot_for_compile["storyboard_materialization_authority"]["stale_status"] = "FRESH"
    try:
        expected = next(item for item in compile_storyboard_snapshot_to_prompt_ir(historical_snapshot_for_compile, generation_policy=stored.get("generation_policy"), asset_authority={"bindings": historical_bindings}, allow_default_policy=False) if item.get("storyboard_shot_id") == stored.get("storyboard_shot_id") or item.get("plan_shot_id") == stored.get("plan_shot_id"))
    except (PromptIRPhaseEError, StopIteration) as exc:
        return _historical_failure(exc.code if isinstance(exc, PromptIRPhaseEError) else "PROMPT_IR_HISTORICAL_SEMANTIC_MISMATCH", str(exc))
    diff = compare_prompt_ir_semantics(expected, stored)
    if not diff.get("empty"):
        return _historical_failure("PROMPT_IR_HISTORICAL_SEMANTIC_MISMATCH", "Stored PromptIR does not reproduce its historical deterministic compile.", diagnostics=diff.get("errors", []))
    return {"integrity_valid": True, "current_lineage_valid": None, "obsolete_due_to_upstream_change": None, "tampered": False, "diagnostics": [], "historical_snapshot": historical_snapshot, "historical_asset_authority": {"bindings": historical_bindings}, "expected_payload": expected}


def compare_prompt_ir_lineage_to_current(*, stored_payload: dict[str, Any], current_snapshot: dict[str, Any], asset_authority: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compare only historical and current authority lineage.

    Semantic integrity is proven separately by
    :func:`validate_prompt_ir_historical_integrity`; this function must never
    infer tamper from a current semantic diff.
    """
    stored = _dict(stored_payload)
    policy = _dict(stored.get("generation_policy"))
    try:
        expected = next(
            item for item in compile_storyboard_snapshot_to_prompt_ir(
                current_snapshot,
                generation_policy=policy,
                asset_authority=asset_authority,
                allow_default_policy=False,
            )
            if item.get("storyboard_shot_id") == stored.get("storyboard_shot_id") or item.get("plan_shot_id") == stored.get("plan_shot_id")
        )
    except (PromptIRPhaseEError, StopIteration) as exc:
        return {
            "current_lineage_valid": False,
            "obsolete_due_to_upstream_change": False,
            "tampered": False,
            "diagnostics": [{"code": exc.code, "message": exc.message}] if isinstance(exc, PromptIRPhaseEError) else [{"code": "PROMPT_IR_LINEAGE_MISSING"}],
        }
    source_changed = expected.get("source_authority") != stored.get("source_authority")
    assets_changed = expected.get("asset_authority_bindings") != stored.get("asset_authority_bindings")
    if not source_changed and not assets_changed:
        return {"current_lineage_valid": True, "obsolete_due_to_upstream_change": False, "tampered": False, "diagnostics": [], "expected_payload": expected}
    return {
        "current_lineage_valid": False,
        "obsolete_due_to_upstream_change": True,
        "tampered": False,
        "diagnostics": [{"code": "PROMPT_IR_UPSTREAM_LINEAGE_CHANGED", "source_changed": source_changed, "assets_changed": assets_changed}],
        "expected_payload": expected,
    }


def compile_storyboard_snapshot_to_prompt_ir(snapshot: dict[str, Any], *, generation_policy: dict[str, Any] | None = None, asset_authority: dict[str, Any] | None = None, allow_default_policy: bool = True) -> list[dict[str, Any]]:
    policy = build_generation_policy(generation_policy, allow_default=allow_default_policy)
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != "storyboard_production_snapshot_v1":
        raise PromptIRPhaseEError("STORYBOARD_SNAPSHOT_INVALID", "PromptIR compilation requires storyboard_production_snapshot_v1.")
    if snapshot.get("prompt_prose") is not False or snapshot.get("media_state") != "NOT_GENERATED":
        raise PromptIRPhaseEError("STORYBOARD_SNAPSHOT_NOT_PRODUCTION_SAFE", "Snapshot contains prompt prose or generated media state.")
    if snapshot.get("storyboard_semantic_ready") is not True:
        raise PromptIRPhaseEError("STORYBOARD_SEMANTIC_NOT_READY", "PromptIR compilation requires storyboard_semantic_ready=true.")
    rows = _list(snapshot.get("ordered_shots"))
    if not rows:
        raise PromptIRPhaseEError("STORYBOARD_SNAPSHOT_EMPTY", "Snapshot contains no ordered StoryboardShots.")
    result: list[dict[str, Any]] = []
    for row in rows:
        ir = _semantic_prompt_projection(snapshot, row, policy)
        # Asset authority binds concrete current identities without changing
        # the semantic subject/prop lists.  Unknown identities are a hard
        # error only when the policy explicitly requires that asset class.
        authority = _dict(asset_authority)
        bindings = _list(authority.get("bindings"))
        resolved = {f"{_text(item.get('asset_type')).lower()}:{_text(item.get('canonical_asset_id') or item.get('asset_id') or item.get('id'))}": item for item in bindings if isinstance(item, dict)}
        required = set(policy.get("required_asset_classes", []))
        for identity_key in ir["asset_authority_bindings"]["identity_refs"]:
            identity = identity_key.split(":", 1)[1] if ":" in identity_key else identity_key
            asset_type = identity_key.split(":", 1)[0].upper() if ":" in identity_key else ""
            reference_required = f"{asset_type}_REFERENCE" in required
            requires_authority = asset_type in required or reference_required
            if requires_authority and identity_key not in resolved:
                raise PromptIRPhaseEError("PROMPT_IR_REQUIRED_ASSET_AUTHORITY_MISSING", f"Required current asset authority is missing: {identity_key}.")
            if identity_key in resolved:
                item = resolved[identity_key]
                stale_status = _text(item.get("stale_status") or "FRESH").upper()
                if stale_status != "FRESH":
                    raise PromptIRPhaseEError("PROMPT_IR_ASSET_AUTHORITY_STALE", f"Current asset authority is stale: {identity_key}.")
                if requires_authority and _text(item.get("authority_status")).upper() not in {"SPEC_APPROVED", "PRODUCTION_READY", "LOCKED", "QUALIFIED", "PRODUCTION_AUTHORITATIVE"}:
                    raise PromptIRPhaseEError("PROMPT_IR_REQUIRED_ASSET_AUTHORITY_MISSING", f"Required asset authority is not production qualified: {identity_key}.")
                if reference_required:
                    reference = item.get("reference_authority") if isinstance(item.get("reference_authority"), dict) else {}
                    if not reference:
                        raise PromptIRPhaseEError("PROMPT_IR_REQUIRED_REFERENCE_AUTHORITY_MISSING", f"Required current reference authority is missing: {identity_key}.")
                    ref_status = _text(reference.get("status")).upper()
                    ref_stale = _text(reference.get("stale_status") or "FRESH").upper()
                    if ref_status not in {"LOCKED", "REFERENCE_LOCKED"} or ref_stale != "FRESH":
                        raise PromptIRPhaseEError("VISUAL_REFERENCE_AUTHORITY_STALE", f"Required reference authority is not LOCKED and FRESH: {identity_key}.")
                    current_version_fp = _text(item.get("asset_version_fingerprint") or item.get("payload_hash") or item.get("authority_fingerprint"))
                    ref_version_fp = _text(reference.get("asset_version_fingerprint"))
                    if not ref_version_fp or ref_version_fp != current_version_fp:
                        raise PromptIRPhaseEError("VISUAL_REFERENCE_AUTHORITY_STALE", f"Reference authority is bound to a different asset version: {identity_key}.")
                resolved_binding = {"identity_ref": identity_key, "asset_authority_ref": _text(item.get("asset_key") or item.get("canonical_asset_id") or identity), "authority_fingerprint": _text(item.get("authority_fingerprint") or item.get("payload_hash")), "asset_version_id": item.get("asset_version_id"), "asset_version_fingerprint": _text(item.get("asset_version_fingerprint") or item.get("payload_hash")), "stale_status": _text(item.get("stale_status") or "FRESH")}
                if reference_required:
                    reference = item.get("reference_authority")
                    resolved_binding["reference_authority_ref"] = reference.get("authority_fingerprint")
                    resolved_binding["reference_authority_fingerprint"] = reference.get("authority_fingerprint")
                    resolved_binding["reference_asset_version_fingerprint"] = reference.get("asset_version_fingerprint")
                    resolved_binding["reference_token"] = reference.get("reference_token", "")
                ir["asset_authority_bindings"]["resolved"].append(resolved_binding)
        order = {identity: index for index, identity in enumerate(ir["asset_authority_bindings"]["identity_refs"])}
        ir["asset_authority_bindings"]["resolved"] = sorted(ir["asset_authority_bindings"]["resolved"], key=lambda item: order.get(item["identity_ref"], 10**9))
        ir["prompt_ir_semantic_fingerprint"] = fingerprint(prompt_ir_semantic_projection(ir))
        ir["prompt_ir_payload_fingerprint"] = fingerprint(_prompt_ir_payload_basis(ir))
        ir["payload_hash"] = ir["prompt_ir_payload_fingerprint"]
        result.append(ir)
    return result


def validate_prompt_ir_against_snapshot(snapshot: dict[str, Any], prompt_ir: dict[str, Any], *, generation_policy: dict[str, Any] | None = None, asset_authority: dict[str, Any] | None = None) -> dict[str, Any]:
    expected_list = compile_storyboard_snapshot_to_prompt_ir(snapshot, generation_policy=generation_policy or prompt_ir.get("generation_policy"), asset_authority=asset_authority)
    expected = next((item for item in expected_list if item.get("plan_shot_id") == prompt_ir.get("plan_shot_id")), None)
    if expected is None:
        return {"valid": False, "errors": [{"code": "PROMPT_IR_SHOT_NOT_IN_SNAPSHOT"}], "semantic_diff": {"empty": False}}
    diff = compare_prompt_ir_semantics(expected, prompt_ir)
    actual_fp = fingerprint(_prompt_ir_payload_basis(prompt_ir))
    stored_fp = _text(prompt_ir.get("prompt_ir_payload_fingerprint") or prompt_ir.get("payload_hash"))
    if stored_fp and stored_fp != actual_fp:
        diff["errors"].append({"code": "PROMPT_IR_FINGERPRINT_TAMPERED"})
    diff["valid"] = not diff["errors"]
    return diff


MODEL_ADAPTER_REGISTRY = {
    "flux": {"adapter_id": "flux", "adapter_version": "flux_adapter_v1", "model_family": "FLUX", "supports_reference_images": True, "supports_negative_prompt": False},
    "image_generic": {"adapter_id": "image_generic", "adapter_version": "image_generic_adapter_v1", "model_family": "GENERIC_IMAGE", "supports_reference_images": True, "supports_negative_prompt": False},
    "video_generic": {"adapter_id": "video_generic", "adapter_version": "video_generic_adapter_v1", "model_family": "GENERIC_VIDEO", "supports_reference_images": True, "supports_negative_prompt": False},
}


def evaluate_model_generation_readiness(prompt_ir: dict[str, Any], *, generation_policy: dict[str, Any] | None = None, model_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Recompute runtime readiness; stored PromptIR booleans are advisory."""
    policy = build_generation_policy(generation_policy or prompt_ir.get("generation_policy"))
    profile = build_model_profile(model_profile)
    adapter = MODEL_ADAPTER_REGISTRY.get(profile.get("adapter_id"))
    reasons: list[str] = []
    if not adapter:
        reasons.append("MODEL_ADAPTER_NOT_REGISTERED")
    refs = _list(_dict(prompt_ir.get("asset_authority_bindings")).get("resolved"))
    required = set(policy.get("required_asset_classes", []))
    for asset_class in required:
        if not any(_text(item.get("identity_ref")).split(":", 1)[0].upper() == asset_class or _text(item.get("identity_ref")).split(":", 1)[0].upper() + "_REFERENCE" == asset_class for item in refs if isinstance(item, dict)):
            reasons.append(f"REQUIRED_ASSET_MISSING:{asset_class}")
    reference_required = any(_text(item).upper().endswith("_REFERENCE") for item in required)
    if required and adapter and not profile.get("capabilities", {}).get("supports_reference_images", adapter.get("supports_reference_images", False)):
        reasons.append("MODEL_ADAPTER_UNSUPPORTED_CAPABILITY:REFERENCE_IMAGES")
    if not profile.get("provider_config_ref"):
        reasons.append("PROVIDER_CONFIG_MISSING")
    return {"ready": not reasons, "reasons": sorted(set(reasons)), "adapter_registered": bool(adapter), "policy_fingerprint": policy.get("fingerprint"), "model_profile_fingerprint": profile.get("fingerprint")}


def _adapter_sections(prompt_ir: dict[str, Any]) -> dict[str, Any]:
    """Deterministic semantic sections; no style or visual facts are added."""
    subjects = [item.get("subject_ref") for item in _list(prompt_ir.get("subjects"))]
    props = [item.get("prop_ref") for item in _list(prompt_ir.get("props"))]
    camera = _dict(prompt_ir.get("camera"))
    action = _dict(prompt_ir.get("action"))
    return {
        "SUBJECT": subjects,
        "ENVIRONMENT": prompt_ir.get("environment", {}),
        "PROPS": props,
        "ACTION": action.get("action_beats", []),
        "CAMERA": camera,
        "CONTINUITY": prompt_ir.get("continuity", {}),
        "TEMPORAL": prompt_ir.get("temporal", {}),
        "VISIBILITY": prompt_ir.get("information_visibility"),
        "CONSTRAINTS": prompt_ir.get("generation_constraints", {}),
    }


def render_prompt_surface(prompt_ir: dict[str, Any], *, surface: str = "static") -> dict[str, Any]:
    sections = _adapter_sections(prompt_ir)
    ordered = ["SUBJECT", "ENVIRONMENT", "PROPS", "ACTION", "CAMERA", "CONTINUITY", "TEMPORAL", "VISIBILITY", "CONSTRAINTS"]
    text = "\n".join(f"{key}: {canonical(sections[key])}" for key in ordered if sections[key] not in (None, [], {}, ""))
    return {"surface": surface, "renderer_version": "prompt_surface_renderer_v1", "text": text, "render_fingerprint": fingerprint({"surface": surface, "sections": sections})}


def compare_prompt_ir_adapter_payload_semantics(prompt_ir: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    projection = payload.get("semantic_projection") if isinstance(payload.get("semantic_projection"), dict) else {}
    expected = _adapter_sections(prompt_ir)
    return {"empty": expected == projection, "expected": expected, "actual": projection, "unsupported": payload.get("unsupported", [])}


def adapt_prompt_ir_to_generation_payload(prompt_ir: dict[str, Any], *, generation_policy: dict[str, Any] | None = None, model_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = build_generation_policy(generation_policy or prompt_ir.get("generation_policy"))
    profile = build_model_profile(model_profile)
    adapter = MODEL_ADAPTER_REGISTRY.get(profile.get("adapter_id"))
    if not adapter:
        raise PromptIRPhaseEError("MODEL_ADAPTER_NOT_REGISTERED", f"No deterministic adapter is registered for {profile.get('adapter_id')}.")
    refs = _list(prompt_ir.get("asset_authority_bindings", {}).get("resolved"))
    requires_refs = any(_text(item).upper().endswith("_REFERENCE") for item in policy.get("required_asset_classes", []))
    if policy.get("required_asset_classes") and not profile.get("capabilities", {}).get("supports_reference_images", adapter.get("supports_reference_images", False)):
        raise PromptIRPhaseEError("MODEL_ADAPTER_CAPABILITY_UNSUPPORTED", "ModelProfile cannot represent required reference images.")
    required_identity_types = set(policy.get("required_asset_classes", []))
    missing = [kind for kind in required_identity_types if not any(_text(item.get("identity_ref")).split(":", 1)[0].upper() == kind or _text(item.get("identity_ref")).split(":", 1)[0].upper() + "_REFERENCE" == kind for item in refs)]
    if missing:
        reference_missing = [item for item in missing if item.endswith("_REFERENCE")]
        code = "PROMPT_IR_REQUIRED_REFERENCE_AUTHORITY_MISSING" if reference_missing else "MODEL_ADAPTER_REQUIRED_ASSET_MISSING"
        raise PromptIRPhaseEError(code, "Required authority bindings are missing.", diagnostics=[{"code": code, "asset_class": item} for item in missing])
    for asset_class in required_identity_types:
        if asset_class.endswith("_REFERENCE"):
            base = asset_class.removesuffix("_REFERENCE")
            for item in refs:
                identity_type = _text(item.get("identity_ref")).split(":", 1)[0].upper()
                if identity_type == base and not item.get("reference_authority_fingerprint"):
                    raise PromptIRPhaseEError("PROMPT_IR_REQUIRED_REFERENCE_AUTHORITY_MISSING", f"Required reference authority is not bound: {item.get('identity_ref')}")
    static_surface = render_prompt_surface(prompt_ir, surface="static")
    motion_surface = render_prompt_surface(prompt_ir, surface="motion")
    reference_bindings = []
    for ref in refs:
        identity_ref = _text(ref.get("identity_ref"))
        asset_type = identity_ref.split(":", 1)[0].upper() if ":" in identity_ref else "ASSET"
        role = {"SCENE": "SCENE_REFERENCE", "CHARACTER": "SUBJECT_REFERENCE", "PROP": "PROP_REFERENCE"}.get(asset_type, f"{asset_type}_REFERENCE")
        reference_bindings.append({"role": role, "identity_ref": identity_ref, "asset_authority_ref": _text(ref.get("asset_authority_ref")), "authority_fingerprint": _text(ref.get("authority_fingerprint")), "reference_authority_ref": _text(ref.get("reference_authority_ref")), "reference_authority_fingerprint": _text(ref.get("reference_authority_fingerprint")), "reference_token": _text(ref.get("reference_token"))})
    request: dict[str, Any] = {"prompt": static_surface["text"], "motion_prompt": motion_surface["text"], "reference_bindings": reference_bindings}
    if profile.get("capabilities", {}).get("supports_negative_prompt", adapter.get("supports_negative_prompt", False)):
        request["negative_prompt"] = ""
    readiness = evaluate_model_generation_readiness(prompt_ir, generation_policy=policy, model_profile=profile)
    payload = {
        "schema_version": GENERATION_PAYLOAD_SCHEMA_VERSION,
        "model_family": profile.get("model_family"),
        "prompt_ir_ref": {"storyboard_shot_id": prompt_ir.get("storyboard_shot_id"), "plan_shot_id": prompt_ir.get("plan_shot_id"), "fingerprint": prompt_ir.get("prompt_ir_payload_fingerprint") or prompt_ir.get("payload_hash")},
        "generation_policy": policy,
        "model_profile": profile,
        "request": request,
        "adapter": {"adapter_id": adapter["adapter_id"], "adapter_version": adapter["adapter_version"]},
        "semantic_projection": _adapter_sections(prompt_ir),
        "unsupported": [],
        "readiness": readiness,
        "provider_calls": 0,
    }
    payload["generation_payload_fingerprint"] = fingerprint(payload)
    return payload


def _mark_phase_e_prompt_stale(session: Any, version: Any, authority: Any, reasons: list[str]) -> None:
    normalized = sorted({_text(reason) for reason in reasons if _text(reason)})
    version.stale_status = "STALE"
    version.stale_reasons = json.dumps(normalized, ensure_ascii=False)
    if authority is not None:
        authority.stale_status = "STALE"
        authority.stale_reasons = json.dumps(normalized, ensure_ascii=False)


def validate_prompt_ir_integrity(session: Any, *, book_id: int, episode: int, storyboard_shot_id: int, target_media: str, allow_stale: bool = False) -> dict[str, Any]:
    """Validate stored PromptIR truth without judging whether it is current."""
    from fastapi import HTTPException
    from models import PromptIRAuthority, PromptIRPointer, PromptIRVersion

    if target_media not in {"IMAGE", "VIDEO"}:
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_MEDIA_SCOPE_INVALID", "message": "Current PromptIR resolution requires exact target_media IMAGE or VIDEO."})
    pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=storyboard_shot_id, target_media=target_media).first()
    if pointer is None:
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_POINTER_MISSING", "message": "No current PromptIR pointer exists for the requested media scope."})
    version = session.query(PromptIRVersion).filter_by(id=pointer.prompt_ir_version_id, book_id=book_id, episode=episode, storyboard_shot_id=storyboard_shot_id).first()
    authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=pointer.prompt_ir_version_id, book_id=book_id, episode=episode, storyboard_shot_id=storyboard_shot_id).first()
    if version is None or authority is None:
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_POINTER_TAMPERED", "message": "Current PromptIR pointer does not resolve to one matching version and authority."})
    if version.schema_version != PROMPT_IR_SCHEMA_VERSION:
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_V2_REQUIRED", "message": "Production PromptIR authority must resolve to prompt_ir_v2."})
    if not allow_stale and (version.stale_status != "FRESH" or authority.stale_status != "FRESH"):
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_STALE", "message": "Current PromptIR version or authority is stale."})
    if _text(pointer.qualification_state) != _text(version.qualification_state) or _text(authority.qualification_state) != _text(version.qualification_state):
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_CURRENT_INTEGRITY_INVALID", "message": "PromptIR qualification states disagree."})
    if _text(pointer.payload_hash) != _text(version.payload_hash):
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_POINTER_TAMPERED", "message": "PromptIR pointer payload hash does not match the current version."})
    try:
        payload = json.loads(version.payload_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_TAMPERED", "message": "PromptIR payload is not valid JSON."})
    if not isinstance(payload, dict) or fingerprint(_prompt_ir_payload_basis(payload)) != _text(version.payload_hash):
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_TAMPERED", "message": "PromptIR payload fingerprint is invalid."})
    stored_target = payload.get("generation_policy", {}).get("target_media") if isinstance(payload.get("generation_policy"), dict) else None
    if stored_target != target_media or pointer.target_media != stored_target:
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_POINTER_MEDIA_SCOPE_MISMATCH", "message": "PromptIR pointer scope does not match the stored GenerationPolicy target_media."})
    try:
        envelope = json.loads(authority.envelope_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_AUTHORITY_ENVELOPE_TAMPERED", "message": "PromptIR authority envelope is not valid JSON."})
    if not isinstance(envelope, dict) or _text(authority.envelope_fingerprint) != fingerprint({key: value for key, value in envelope.items() if key != "envelope_fingerprint"}) or _text(envelope.get("envelope_fingerprint")) != _text(authority.envelope_fingerprint):
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_AUTHORITY_ENVELOPE_TAMPERED", "message": "PromptIR authority envelope fingerprint is invalid."})
    if _text(envelope.get("prompt_ir_payload_hash")) != _text(version.payload_hash) or envelope.get("generation_policy") != payload.get("generation_policy") or envelope.get("asset_authority_bindings") != payload.get("asset_authority_bindings"):
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_AUTHORITY_ENVELOPE_TAMPERED", "message": "PromptIR authority envelope does not bind the current payload lineage."})
    return {"integrity_valid": True, "current_lineage_valid": None, "obsolete_due_to_upstream_change": None, "tampered": False, "pointer": pointer, "version": version, "authority": authority, "payload": payload, "authority_envelope": envelope}


def validate_prompt_ir_current_scope(session: Any, *, book_id: int, episode: int, storyboard_shot_id: int, target_media: str) -> dict[str, Any]:
    """Validate stored integrity and the live Storyboard lineage for one scope.

    ``stale_status`` is persisted lifecycle metadata; it is not an authority
    oracle.  A PromptIR can remain historically intact and ``FRESH`` while its
    current materialization has advanced, so this wrapper always performs the
    read-only lineage comparison used by the Phase E resolver.
    """
    result = validate_prompt_ir_integrity(
        session,
        book_id=book_id,
        episode=episode,
        storyboard_shot_id=storyboard_shot_id,
        target_media=target_media,
        allow_stale=False,
    )
    lineage = _validate_prompt_ir_live_lineage(session, integrity=result)
    result.update({key: value for key, value in lineage.items() if key not in {"pointer", "version", "authority", "payload"}})
    result["current_lineage_valid"] = bool(lineage.get("current_lineage_valid"))
    return result


def build_current_prompt_ir_asset_authority(session: Any, *, book_id: int, prompt_payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve PromptIR asset bindings through the canonical asset contract.

    This is the one current asset truth consumed by PromptIR lineage and Media
    Authority.  It validates the formal VisualAssetPointer/Version chain and,
    when a stored binding names a reference authority, validates that the
    reference remains locked, fresh, and bound to the same current version.
    """
    from core.visual_asset_authority import VisualAssetAuthorityError, resolve_current_visual_asset_authority
    from models import VisualAssetPointer, VisualReferenceAuthority

    payload = _dict(prompt_payload)
    stored = _dict(payload.get("asset_authority_bindings"))
    policy = _dict(payload.get("generation_policy"))
    required = {str(item).upper() for item in _list(policy.get("required_asset_classes"))}
    current: list[dict[str, Any]] = []
    for binding in _list(stored.get("resolved")):
        if not isinstance(binding, dict):
            continue
        item = dict(binding)
        identity_ref = _text(item.get("identity_ref"))
        if identity_ref and ":" in identity_ref:
            asset_type, canonical_id = identity_ref.split(":", 1)
            item.setdefault("asset_type", asset_type)
            item.setdefault("canonical_asset_id", canonical_id)
        asset_key = _text(item.get("asset_authority_ref") or item.get("asset_key") or item.get("identity_ref"))
        inferred_asset_type = identity_ref.split(":", 1)[0] if ":" in identity_ref else ""
        asset_type = _text(item.get("asset_type") or inferred_asset_type)
        scope_key = _text(item.get("scope_key"))
        expected_version = item.get("asset_version_id")
        expected_hash = _text(item.get("asset_version_fingerprint"))
        expected_authority = _text(item.get("authority_fingerprint"))
        if not _dict(payload.get("source_authority")):
            # Pre-Phase-E fixtures have no declared Storyboard lineage and
            # therefore cannot satisfy the full production asset contract.
            # Keep their pointer drift observable for Media Authority while
            # preserving the legacy fixture shape.
            query = session.query(VisualAssetPointer).filter_by(book_id=book_id, asset_key=asset_key)
            if scope_key:
                query = query.filter_by(scope_key=scope_key)
            pointer = query.first()
            item["asset_version_id"] = getattr(pointer, "current_version_id", None) if pointer else None
            item["asset_version_fingerprint"] = _text(getattr(pointer, "payload_hash", "")) if pointer else ""
            item["authority_fingerprint"] = _text(getattr(pointer, "payload_hash", "")) if pointer else ""
            item["authority_status"] = _text(getattr(pointer, "authority_status", "")) if pointer else ""
            item["stale_status"] = _text(getattr(pointer, "stale_status", "STALE")) if pointer else "STALE"
            item["pointer_matches"] = bool(pointer and (expected_version is None or int(pointer.current_version_id or 0) == int(expected_version)) and (not expected_hash or _text(pointer.payload_hash) == expected_hash) and (not expected_authority or _text(pointer.payload_hash) == expected_authority) and _text(pointer.stale_status or "FRESH").upper() == "FRESH")
            current.append(item)
            continue
        try:
            resolved = resolve_current_visual_asset_authority(
                session,
                book_id=book_id,
                asset_key=asset_key,
                expected_asset_type=asset_type,
                expected_scope_key=scope_key,
            )
            pointer = resolved["pointer"]
            version = resolved["version"]
            item["asset_version_id"] = version.id
            item["asset_version_fingerprint"] = _text(version.payload_hash)
            item["authority_fingerprint"] = _text(version.payload_hash)
            item["authority_status"] = _text(version.authority_status)
            item["stale_status"] = _text(version.stale_status or getattr(pointer, "stale_status", "FRESH")) or "FRESH"
            item["scope_key"] = _text(pointer.scope_key)
            item["pointer_matches"] = bool(
                (expected_version is None or int(pointer.current_version_id or 0) == int(expected_version))
                and (not expected_hash or _text(pointer.payload_hash) == expected_hash)
                and (not expected_authority or _text(pointer.payload_hash) == expected_authority)
                and _text(pointer.stale_status or "FRESH").upper() == "FRESH"
            )
            reference_fp = _text(item.get("reference_authority_fingerprint") or item.get("reference_authority_ref"))
            reference_required = f"{asset_type.upper()}_REFERENCE" in required
            if reference_fp or reference_required:
                reference = session.query(VisualReferenceAuthority).filter_by(authority_fingerprint=reference_fp).first() if reference_fp else None
                if reference is None or int(reference.asset_version_id or 0) != int(version.id) or _text(reference.asset_version_fingerprint) != _text(version.payload_hash) or _text(reference.status).upper() not in {"LOCKED", "REFERENCE_LOCKED"} or _text(reference.stale_status or "FRESH").upper() != "FRESH":
                    item["stale_status"] = "STALE"
                    item["authority_status"] = "STALE"
                elif reference is not None:
                    item["reference_authority"] = {"authority_fingerprint": reference.authority_fingerprint, "asset_version_id": reference.asset_version_id, "asset_version_fingerprint": reference.asset_version_fingerprint, "status": reference.status, "stale_status": reference.stale_status, "reference_token": _json(reference.reference_token_mapping_json, {}).get("token", "")}
        except VisualAssetAuthorityError:
            item["stale_status"] = "STALE"
            item["authority_status"] = "STALE"
            item["pointer_matches"] = False
        item.setdefault("pointer_matches", False)
        current.append(item)
    return {"declared": bool(current), "bindings": current, "fingerprint": fingerprint(current)}


def _validate_prompt_ir_live_lineage(session: Any, *, integrity: dict[str, Any]) -> dict[str, Any]:
    """Pure current-lineage validator shared by Media Authority and Phase E."""
    from fastapi import HTTPException
    from core.storyboard_materializer import build_storyboard_production_snapshot, resolve_current_authoritative_materialization
    from models import StoryboardShot

    payload = _dict(integrity.get("payload"))
    shot_id = int(getattr(integrity.get("version"), "storyboard_shot_id", 0) or 0)
    book_id = int(getattr(integrity.get("version"), "book_id", 0) or 0)
    episode = int(getattr(integrity.get("version"), "episode", 0) or 0)
    # Legacy deterministic fixtures that predate the persisted Phase D
    # materialization authority do not declare a source lineage. They remain
    # covered by historical integrity and are outside the live-lineage path.
    if not _dict(payload.get("source_authority")):
        return {"current_lineage_valid": True, "obsolete_due_to_upstream_change": False, "tampered": False, "diagnostics": [{"code": "PROMPT_IR_LIVE_LINEAGE_NOT_DECLARED"}]}
    row = session.query(StoryboardShot).filter_by(id=shot_id, book_id=book_id, episode=episode).first()
    if row is None or not _text(getattr(row, "scene_id", "")):
        return {"current_lineage_valid": False, "obsolete_due_to_upstream_change": True, "tampered": False, "diagnostics": [{"code": "PROMPT_IR_LIVE_LINEAGE_MISSING"}]}
    try:
        materialization_set, rows, set_envelope = resolve_current_authoritative_materialization(
            session,
            book_id=book_id,
            episode=episode,
            scene_id=_text(row.scene_id),
        )
        current_snapshot = build_storyboard_production_snapshot(
            materialization_set=materialization_set,
            rows=rows,
            authority_envelope=set_envelope,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return {"current_lineage_valid": False, "obsolete_due_to_upstream_change": True, "tampered": False, "diagnostics": [{"code": detail.get("code", "PROMPT_IR_LIVE_LINEAGE_INVALID"), "message": detail.get("message", str(exc))}]}
    current_assets = build_current_prompt_ir_asset_authority(session, book_id=book_id, prompt_payload=payload)
    lineage = compare_prompt_ir_lineage_to_current(
        stored_payload=payload,
        current_snapshot=current_snapshot,
        asset_authority=current_assets,
    )
    lineage["live_snapshot"] = current_snapshot
    lineage["current_materialization_set_id"] = getattr(materialization_set, "id", None)
    return lineage


def resolve_current_authoritative_prompt_ir(session: Any, *, book_id: int, episode: int, storyboard_shot_id: int, target_media: str, generation_policy: dict[str, Any] | None = None, asset_authority: dict[str, Any] | None = None, model_profile: dict[str, Any] | None = None):
    """Resolve one v2 PromptIR through its current pointer and live lineage.

    Stored qualification/readiness flags are never trusted without rechecking
    payload, authority envelope, current Storyboard materialization and the
    semantic projection.
    """
    from fastapi import HTTPException
    from models import PromptIRAuthority, PromptIRPointer, PromptIRVersion

    if target_media not in {"IMAGE", "VIDEO"}:
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_MEDIA_SCOPE_INVALID", "message": "Current PromptIR resolution requires exact target_media IMAGE or VIDEO."})

    def fail(code: str, message: str, *, version: Any = None, authority: Any = None):
        if version is not None:
            _mark_phase_e_prompt_stale(session, version, authority, [code])
            session.commit()
        raise HTTPException(status_code=409, detail={"code": code, "message": message})

    pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=storyboard_shot_id, target_media=target_media).first()
    if pointer is None:
        fail("PROMPT_IR_POINTER_MISSING", "No current PromptIR pointer exists for the requested media scope.")
    version = session.query(PromptIRVersion).filter_by(id=pointer.prompt_ir_version_id, book_id=book_id, episode=episode, storyboard_shot_id=storyboard_shot_id).first()
    authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=pointer.prompt_ir_version_id, book_id=book_id, episode=episode, storyboard_shot_id=storyboard_shot_id).first()
    if version is None or authority is None:
        fail("PROMPT_IR_POINTER_TAMPERED", "Current PromptIR pointer does not resolve to one matching version and authority.", version=version, authority=authority)
    if version.schema_version != PROMPT_IR_SCHEMA_VERSION:
        fail("PROMPT_IR_V2_REQUIRED", "Production PromptIR authority must resolve to prompt_ir_v2.", version=version, authority=authority)
    if version.stale_status != "FRESH" or authority.stale_status != "FRESH":
        fail("PROMPT_IR_STALE", "Current PromptIR version or authority is stale.", version=version, authority=authority)
    if _text(pointer.qualification_state) != _text(version.qualification_state) or _text(authority.qualification_state) != _text(version.qualification_state):
        fail("PROMPT_IR_CURRENT_AUTHORITY_INVALID", "PromptIR pointer, version, and authority qualification states disagree.", version=version, authority=authority)
    if _text(pointer.payload_hash) != _text(version.payload_hash):
        fail("PROMPT_IR_POINTER_TAMPERED", "PromptIR pointer payload hash does not match the current version.", version=version, authority=authority)
    try:
        payload = json.loads(version.payload_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        fail("PROMPT_IR_TAMPERED", "PromptIR payload is not valid JSON.", version=version, authority=authority)
    if not isinstance(payload, dict) or fingerprint(_prompt_ir_payload_basis(payload)) != _text(version.payload_hash):
        fail("PROMPT_IR_TAMPERED", "PromptIR payload fingerprint is invalid.", version=version, authority=authority)
    stored_target = payload.get("generation_policy", {}).get("target_media") if isinstance(payload.get("generation_policy"), dict) else None
    if pointer.target_media != target_media or stored_target != target_media:
        fail("PROMPT_IR_POINTER_MEDIA_SCOPE_MISMATCH", "PromptIR pointer scope does not match the stored GenerationPolicy target_media.", version=version, authority=authority)
    try:
        envelope = json.loads(authority.envelope_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        fail("PROMPT_IR_AUTHORITY_ENVELOPE_TAMPERED", "PromptIR authority envelope is not valid JSON.", version=version, authority=authority)
    if not isinstance(envelope, dict) or _text(authority.envelope_fingerprint) != fingerprint({key: value for key, value in envelope.items() if key != "envelope_fingerprint"}) or _text(envelope.get("envelope_fingerprint")) != _text(authority.envelope_fingerprint):
        fail("PROMPT_IR_AUTHORITY_ENVELOPE_TAMPERED", "PromptIR authority envelope fingerprint is invalid.", version=version, authority=authority)
    if _text(envelope.get("prompt_ir_payload_hash")) != _text(version.payload_hash):
        fail("PROMPT_IR_AUTHORITY_ENVELOPE_TAMPERED", "PromptIR authority envelope does not bind the current payload hash.", version=version, authority=authority)
    if envelope.get("generation_policy") != payload.get("generation_policy") or envelope.get("asset_authority_bindings") != payload.get("asset_authority_bindings"):
        fail("PROMPT_IR_AUTHORITY_ENVELOPE_TAMPERED", "PromptIR authority envelope does not bind the current policy and asset lineage.", version=version, authority=authority)
    historical = validate_prompt_ir_historical_integrity(session, version=version, authority=authority, payload=payload)
    if not historical.get("integrity_valid"):
        fail(historical.get("code") or "PROMPT_IR_HISTORICAL_SEMANTIC_MISMATCH", historical.get("message") or "Historical PromptIR integrity validation failed.", version=version, authority=authority)
    lineage = _validate_prompt_ir_live_lineage(session, integrity={"version": version, "authority": authority, "payload": payload})
    if not lineage.get("current_lineage_valid"):
        diagnostic = (lineage.get("diagnostics") or [{}])[0]
        code = diagnostic.get("code") or "PROMPT_IR_STALE"
        fail(code, "PromptIR no longer matches the current authoritative Storyboard lineage.", version=version, authority=authority)
    snapshot = lineage.get("live_snapshot")
    if generation_policy is not None and canonical_target_media(build_generation_policy(generation_policy).get("target_media")) != target_media:
        fail("PROMPT_IR_POINTER_MEDIA_SCOPE_MISMATCH", "Requested GenerationPolicy target_media does not match the resolver scope.", version=version, authority=authority)
    if generation_policy is not None and payload.get("generation_policy", {}).get("fingerprint") != build_generation_policy(generation_policy).get("fingerprint"):
        fail("PROMPT_IR_GENERATION_POLICY_CHANGED", "GenerationPolicy changed; PromptIR must be recompiled.", version=version, authority=authority)
    readiness = evaluate_model_generation_readiness(payload, generation_policy=payload.get("generation_policy"), model_profile=model_profile) if model_profile is not None else {"ready": False, "reasons": ["MODEL_PROFILE_NOT_SUPPLIED"]}
    return {"version": version, "authority": authority, "pointer": pointer, "payload": payload, "snapshot": snapshot, "authority_envelope": envelope, "model_generation_ready": bool(readiness.get("ready")), "readiness": readiness}


def validate_current_prompt_ir_authority(session: Any, *, book_id: int, episode: int, storyboard_shot_id: int, target_media: str, expected_prompt_ir: dict[str, Any] | None = None, generation_policy: dict[str, Any] | None = None, asset_authority: dict[str, Any] | None = None, model_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Canonical current-authority validator used by resolver and reuse."""
    resolved = resolve_current_authoritative_prompt_ir(session, book_id=book_id, episode=episode, storyboard_shot_id=storyboard_shot_id, target_media=target_media, generation_policy=generation_policy, asset_authority=asset_authority, model_profile=model_profile)
    if expected_prompt_ir is not None:
        diff = compare_prompt_ir_semantics(expected_prompt_ir, resolved["payload"])
        if not diff.get("empty"):
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_CURRENT_AUTHORITY_INVALID", "message": "Current PromptIR does not equal the newly compiled semantic payload.", "diagnostics": diff.get("errors", [])})
        if _text(expected_prompt_ir.get("payload_hash") or expected_prompt_ir.get("prompt_ir_payload_fingerprint")) != _text(resolved["version"].payload_hash):
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_CURRENT_AUTHORITY_INVALID", "message": "Current PromptIR payload hash differs from the newly compiled payload."})
    return {"valid": True, "reusable": True, **resolved}


__all__ = [
    "PROMPT_IR_SCHEMA_VERSION", "GENERATION_POLICY_SCHEMA_VERSION", "MODEL_PROFILE_SCHEMA_VERSION", "GENERATION_PAYLOAD_SCHEMA_VERSION", "PROMPT_IR_COMPILER_VERSION", "SOURCE_SEMANTIC_PROJECTION", "STORYBOARD_SEMANTIC_PROJECTION", "ASSET_AUTHORITY_BINDING", "GENERATION_POLICY", "MODEL_AGNOSTIC_PROMPT_SEMANTIC", "MODEL_ADAPTER_OUTPUT", "MEDIA_REQUEST_METADATA", "UNKNOWN_INVALID", "PromptIRPhaseEError", "canonical", "fingerprint", "build_generation_policy", "build_model_profile", "compile_storyboard_snapshot_to_prompt_ir", "prompt_ir_semantic_projection", "compare_prompt_ir_semantics", "classify_prompt_ir_compile_transition", "validate_prompt_ir_historical_integrity", "compare_prompt_ir_lineage_to_current", "validate_prompt_ir_against_snapshot", "MODEL_ADAPTER_REGISTRY", "evaluate_model_generation_readiness", "render_prompt_surface", "compare_prompt_ir_adapter_payload_semantics", "adapt_prompt_ir_to_generation_payload", "validate_prompt_ir_integrity", "build_current_prompt_ir_asset_authority", "validate_prompt_ir_current_scope", "resolve_current_authoritative_prompt_ir", "validate_current_prompt_ir_authority",
]
