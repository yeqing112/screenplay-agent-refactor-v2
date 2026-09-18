"""Production PromptIR authority contract and deterministic adapter boundary.

PromptIR is structured authority.  Human-readable prompt strings are derived
serialization and never become a source of facts.  This module consumes only
the versioned ``storyboard_prompt_handoff_v1`` produced by the Materializer.
It performs no provider calls.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


PROMPT_IR_SCHEMA_VERSION = "prompt_ir_authority_v1"
PROMPT_IR_AUTHORITY_ENVELOPE_VERSION = "prompt_ir_authority_envelope_v1"
PROMPT_IR_COMPILER_VERSION = "prompt_ir_compiler_v2"
PROMPT_IR_COMPILER_POLICY_VERSION = "prompt_ir_compiler_policy_v1"
RETENTION_POLICY_VERSION = "retention_policy_v1"
HANDOFF_SCHEMA_VERSION = "storyboard_prompt_handoff_v1"

STORYBOARD_CONSTRAINT = "STORYBOARD_CONSTRAINT"
VISUAL_ASSET_CONSTRAINT = "VISUAL_ASSET_CONSTRAINT"
COMPILER_POLICY = "COMPILER_POLICY"
MODEL_ADAPTER_POLICY = "MODEL_ADAPTER_POLICY"
MEDIA_PENDING = "MEDIA_PENDING"
UNKNOWN_INVALID = "UNKNOWN_INVALID"

QUALIFICATION_STATES = (
    "STRUCTURALLY_VALID",
    "STORYBOARD_AUTHORITY_BOUND",
    "ASSET_IDENTITY_BOUND",
    "COMPILER_POLICY_APPLIED",
    "PROMPT_IR_QUALIFIED",
)


class PromptIRAuthorityError(ValueError):
    def __init__(self, code: str, message: str, *, diagnostics: list[dict[str, Any]] | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.diagnostics = diagnostics or [{"code": code, "message": message, "severity": "blocked"}]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def prompt_ir_authority_contract() -> dict[str, Any]:
    fields = [
        ("scene_id", "stable scene identity", STORYBOARD_CONSTRAINT, "string", True, True, True, "immutable", "StoryboardMaterializationSet"),
        ("storyboard_shot_id", "authoritative StoryboardShot database identity", STORYBOARD_CONSTRAINT, "integer", True, True, True, "immutable", "StoryboardMaterializationPointer"),
        ("materialization_set_id", "authoritative storyboard projection set", STORYBOARD_CONSTRAINT, "integer", True, True, True, "immutable", "StoryboardMaterializationPointer"),
        ("plan_shot_id", "ShotPlan semantic shot identity", STORYBOARD_CONSTRAINT, "string", True, True, True, "immutable", "ShotPlan authority"),
        ("beat_id", "upstream beat binding", STORYBOARD_CONSTRAINT, "string", True, True, True, "immutable", "ShotPlan authority"),
        ("duration", "authoritative shot duration", STORYBOARD_CONSTRAINT, "positive number", True, True, True, "immutable", "Storyboard projection"),
        ("camera", "authoritative camera decision", STORYBOARD_CONSTRAINT, "object", True, True, True, "immutable", "Storyboard projection"),
        ("action_beats", "declared timed action units", STORYBOARD_CONSTRAINT, "object[]", True, True, True, "immutable", "Storyboard projection"),
        ("entry_state", "continuity entry state", STORYBOARD_CONSTRAINT, "object|string", True, True, True, "immutable", "Storyboard projection"),
        ("exit_state", "continuity exit state", STORYBOARD_CONSTRAINT, "object|string", True, True, True, "immutable", "Storyboard projection"),
        ("continuity_contract", "screen direction and transition constraints", STORYBOARD_CONSTRAINT, "object", True, True, True, "immutable", "Storyboard projection"),
        ("asset_bindings", "canonical asset identities and readiness", VISUAL_ASSET_CONSTRAINT, "object", True, True, True, "identity-preserving", "Asset authority"),
        ("retention_policy", "serialization retention policy", COMPILER_POLICY, "object", True, False, True, "policy-versioned", "Compiler policy"),
        ("static_prompt", "derived image serialization", MODEL_ADAPTER_POLICY, "string", False, False, False, "derived-only", "Adapter"),
        ("motion_prompt", "derived motion serialization", MODEL_ADAPTER_POLICY, "string", False, False, False, "derived-only", "Adapter"),
        ("negative_prompt", "derived negative serialization", MODEL_ADAPTER_POLICY, "string", False, False, False, "derived-only", "Adapter"),
    ]
    result = []
    for field, meaning, authority, schema, required, compile_blocking, model_blocking, mutation, provenance in fields:
        result.append({"field": field, "semantic_definition": meaning, "authority_class": authority, "value_schema": schema, "required": required, "compile_blocking": compile_blocking, "model_ready_blocking": model_blocking, "mutation_policy": mutation, "provenance_requirement": provenance, "storyboard_dependency": authority == STORYBOARD_CONSTRAINT, "asset_dependency": authority == VISUAL_ASSET_CONSTRAINT, "continuity_dependency": field in {"entry_state", "exit_state", "continuity_contract"}, "adapter_dependency": authority == MODEL_ADAPTER_POLICY, "stale_dependency": ["storyboard", "asset", "compiler_policy"] if authority != MODEL_ADAPTER_POLICY else ["adapter"]})
    return {"schema_version": PROMPT_IR_SCHEMA_VERSION, "authority_envelope_version": PROMPT_IR_AUTHORITY_ENVELOPE_VERSION, "fields": result, "qualification_states": list(QUALIFICATION_STATES), "model_generation_ready_is_distinct": True, "prompt_text_is_derived": True}


def contract_fingerprint() -> str:
    return fingerprint(prompt_ir_authority_contract())


def prompt_ir_payload_hash(prompt_ir: dict[str, Any]) -> str:
    """Hash structured authority only; derived prompt text is excluded."""
    payload = dict(prompt_ir) if isinstance(prompt_ir, dict) else {}
    payload.pop("serialization", None)
    payload.pop("payload_hash", None)
    return fingerprint(payload)


def _asset_authority_index(asset_authority: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    raw = _dict(asset_authority)
    items = raw.get("bindings") if isinstance(raw.get("bindings"), list) else []
    if not items:
        for role in ("scene", "characters", "props"):
            group = raw.get(role)
            group = group if isinstance(group, list) else ([group] if isinstance(group, dict) else [])
            items.extend({"asset_type": "character" if role == "characters" else ("prop" if role == "props" else "scene"), **item} for item in group if isinstance(item, dict))
    for item in items:
        asset_id = _text(item.get("canonical_asset_id") or item.get("asset_id") or item.get("id"))
        if asset_id:
            index[f"{_text(item.get('asset_type') or 'asset')}:{asset_id}"] = item
    return index


def _normalize_asset_bindings(raw_bindings: dict[str, Any], asset_authority: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw = _dict(raw_bindings)
    canonical = _dict(raw.get("canonical_asset_identity"))
    pending = _list(raw.get("media_asset_pending"))
    locked_refs = _list(raw.get("locked_visual_references"))
    authority_index = _asset_authority_index(asset_authority)
    entries: list[dict[str, Any]] = []

    def add(role: str, asset_id: Any, name: Any = ""):
        normalized_id = _text(asset_id)
        if not normalized_id:
            return
        authority = authority_index.get(f"{role}:{normalized_id}", {})
        locked = bool(authority.get("locked_reference") or authority.get("reference_status") in {"locked", "ready", "REFERENCE_READY"})
        ref_token = _text(authority.get("reference_token") or authority.get("reference_name")) if locked else ""
        visual_facts = authority.get("visual_facts") if isinstance(authority.get("visual_facts"), list) else []
        canonical_facts = [item for item in visual_facts if isinstance(item, dict) and _text(item.get("fact_key") or item.get("fact"))]
        status = _text(authority.get("authority_status") or "IDENTITY_BOUND")
        if status not in {"PRODUCTION_AUTHORITATIVE", "LOCKED", "QUALIFIED"}:
            status = "IDENTITY_BOUND"
        if not canonical_facts and status == "PRODUCTION_AUTHORITATIVE":
            status = "IDENTITY_BOUND"
        item = {"asset_type": role, "canonical_asset_id": normalized_id, "asset_revision": authority.get("asset_revision"), "asset_name": _text(name or authority.get("asset_name")), "authority_status": status, "variant_scope": _text(authority.get("variant_scope")), "variant_id": _text(authority.get("variant_id")), "reference_status": "REFERENCE_READY" if locked and ref_token else "REFERENCE_PENDING", "reference_token": ref_token, "authority_fingerprint": _text(authority.get("authority_fingerprint") or fingerprint(authority)) if authority else "", "visual_facts": canonical_facts, "media_readiness": "READY" if locked else "PENDING"}
        entries.append(item)

    add("scene", canonical.get("scene") or raw.get("scene_asset_id"), raw.get("scene_name"))
    chars = canonical.get("characters") if isinstance(canonical.get("characters"), list) else raw.get("character_asset_ids", [])
    for value in chars if isinstance(chars, list) else []:
        add("character", value)
    props = canonical.get("props") if isinstance(canonical.get("props"), list) else raw.get("prop_asset_ids", [])
    for value in props if isinstance(props, list) else []:
        add("prop", value)
    ready_ids = {item["canonical_asset_id"] for item in entries if item["reference_status"] == "REFERENCE_READY"}
    pending_requirements = [{"asset_id": _text(item.get("asset_id") if isinstance(item, dict) else item), "reason": "ASSET_AUTHORING_PENDING"} for item in pending if _text(item.get("asset_id") if isinstance(item, dict) else item) not in ready_ids]
    for item in entries:
        if item["reference_status"] == "REFERENCE_PENDING":
            pending_requirements.append({"asset_type": item["asset_type"], "asset_id": item["canonical_asset_id"], "reason": "REFERENCE_PENDING"})
    return entries, pending_requirements


def _require_handoff(handoff: dict[str, Any]) -> None:
    if not isinstance(handoff, dict) or _text(handoff.get("schema_version")) != HANDOFF_SCHEMA_VERSION:
        raise PromptIRAuthorityError("STORYBOARD_HANDOFF_INVALID", "PromptIR production compilation only accepts storyboard_prompt_handoff_v1.")
    required = ("materialization_set_id", "storyboard_shot_id", "plan_shot_id", "beat_id", "scene_id", "shot_plan_id", "shot_plan_authority_fingerprint", "storyboard_projection_fingerprint", "camera", "duration", "action_beats", "entry_state", "exit_state", "continuity_contract", "asset_identity_bindings")
    missing = [field for field in required if field not in handoff or handoff.get(field) in (None, "")]
    if missing:
        raise PromptIRAuthorityError("STORYBOARD_HANDOFF_INCOMPLETE", "Storyboard handoff is missing authoritative fields.", diagnostics=[{"code": "STORYBOARD_HANDOFF_FIELD_MISSING", "field": field, "severity": "blocked"} for field in missing])
    camera = _dict(handoff.get("camera"))
    for key in ("shot_size", "angle", "movement", "speed"):
        if not _text(camera.get(key)):
            raise PromptIRAuthorityError("STORYBOARD_CAMERA_REQUIRED", f"Storyboard handoff camera.{key} is missing.")
    if not isinstance(handoff.get("action_beats"), list):
        raise PromptIRAuthorityError("STORYBOARD_ACTION_CONTRACT_INVALID", "Storyboard handoff action_beats must be an array.")
    if not isinstance(handoff.get("asset_identity_bindings"), dict):
        raise PromptIRAuthorityError("ASSET_BINDING_CONTRACT_INVALID", "Storyboard handoff asset_identity_bindings must be an object.")


def compile_prompt_ir_from_handoff(handoff: dict[str, Any], *, asset_authority: dict[str, Any] | None = None, retention_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compile structured PromptIR from one authoritative handoff only."""
    _require_handoff(handoff)
    assets, pending = _normalize_asset_bindings(handoff["asset_identity_bindings"], _dict(asset_authority))
    policy = {"schema_version": RETENTION_POLICY_VERSION, "version": RETENTION_POLICY_VERSION, "face": "fully_preserved", "hair": "fully_preserved", "costume": "fully_preserved", "background": "mostly_preserved", "composition": "free", "origin": "compiler_policy", "provenance": "compiler_policy_default"}
    if isinstance(retention_policy, dict):
        policy.update(retention_policy)
        policy["origin"] = "compiler_policy"
        policy["version"] = _text(retention_policy.get("version") or RETENTION_POLICY_VERSION)
    transition = _text(handoff.get("transition")) or "cut"
    policy_defaults = []
    if not _text(handoff.get("transition")):
        policy_defaults.append({"field": "transition", "value": transition, "code": "COMPILER_POLICY_DEFAULT", "policy_version": PROMPT_IR_COMPILER_POLICY_VERSION})
    storyboard = {key: handoff.get(key) for key in ("scene_id", "storyboard_shot_id", "materialization_set_id", "plan_shot_id", "beat_id", "shot_plan_id", "shot_plan_revision", "shot_plan_authority_fingerprint", "storyboard_projection_fingerprint", "duration", "camera", "action_beats", "entry_state", "exit_state", "continuity_contract", "shot_purpose", "transition")}
    prompt_ir = {
        "schema_version": PROMPT_IR_SCHEMA_VERSION,
        "authority_classes": {"storyboard": STORYBOARD_CONSTRAINT, "assets": VISUAL_ASSET_CONSTRAINT, "compiler": COMPILER_POLICY, "adapter": MODEL_ADAPTER_POLICY, "pending": MEDIA_PENDING},
        "storyboard": storyboard,
        "assets": {"bindings": assets, "pending_requirements": pending, "authority_fingerprint": _text(_dict(asset_authority).get("authority_fingerprint") or fingerprint(asset_authority or {}))},
        "compiler_policy": {"compiler_version": PROMPT_IR_COMPILER_VERSION, "compiler_policy_version": PROMPT_IR_COMPILER_POLICY_VERSION, "defaults": policy_defaults, "prompt_text_is_derived": True},
        "retention_policy": policy,
        "serialization": {"static_prompt": "", "motion_prompt": "", "negative_prompt": "", "status": "NOT_SERIALIZED"},
        "qualification_state": "PROMPT_IR_QUALIFIED",
        "asset_reference_state": "ASSET_REFERENCE_READY" if not pending else "ASSET_REFERENCE_PENDING",
        "model_generation_ready": not bool(pending),
        "diagnostics": {"status": "pass", "errors": [], "warnings": [], "pending": pending, "policy_defaults": policy_defaults},
    }
    if not assets:
        prompt_ir["qualification_state"] = "PROMPT_IR_QUALIFIED"
    ir_fingerprint_basis = {"handoff": handoff, "assets": prompt_ir["assets"], "compiler_policy": prompt_ir["compiler_policy"], "retention_policy": policy, "schema_version": PROMPT_IR_SCHEMA_VERSION}
    prompt_ir["authority_fingerprint"] = fingerprint(ir_fingerprint_basis)
    prompt_ir["payload_hash"] = prompt_ir_payload_hash(prompt_ir)
    return prompt_ir


def build_prompt_ir_authority_envelope(*, prompt_ir: dict[str, Any], handoff: dict[str, Any], validation: dict[str, Any] | None = None, stale_status: str = "FRESH", stale_reasons: list[str] | None = None) -> dict[str, Any]:
    envelope = {"schema_version": PROMPT_IR_AUTHORITY_ENVELOPE_VERSION, "storyboard": {key: handoff.get(key) for key in ("materialization_set_id", "storyboard_shot_id", "storyboard_projection_fingerprint", "scene_id", "plan_shot_id")}, "shot_plan": {"id": handoff.get("shot_plan_id"), "revision": handoff.get("shot_plan_revision"), "authority_fingerprint": handoff.get("shot_plan_authority_fingerprint")}, "asset_authority": prompt_ir.get("assets", {}), "compiler": prompt_ir.get("compiler_policy", {}), "retention_policy": prompt_ir.get("retention_policy", {}), "validation": validation or prompt_ir.get("diagnostics", {}), "qualification_state": prompt_ir.get("qualification_state"), "asset_reference_state": prompt_ir.get("asset_reference_state"), "model_generation_ready": bool(prompt_ir.get("model_generation_ready")), "stale_status": stale_status, "stale_reasons": sorted(set(stale_reasons or [])), "contract_fingerprint": contract_fingerprint()}
    envelope["envelope_fingerprint"] = fingerprint(envelope)
    return envelope


ADAPTER_CONTRACTS = {
    "kling": {"adapter_id": "kling", "adapter_version": "kling_adapter_v1", "required_fields": ["scene_id", "camera", "duration", "action_beats"]},
    "seedance": {"adapter_id": "seedance", "adapter_version": "seedance_adapter_v1", "required_fields": ["scene_id", "camera", "duration", "action_beats"]},
    "veo": {"adapter_id": "veo", "adapter_version": "veo_adapter_v1", "required_fields": ["scene_id", "camera", "duration", "action_beats"]},
    "jimeng": {"adapter_id": "jimeng", "adapter_version": "jimeng_adapter_v1", "required_fields": ["scene_id", "camera", "duration", "action_beats"]},
    "flux": {"adapter_id": "flux", "adapter_version": "flux_adapter_v1", "required_fields": ["scene_id", "camera", "duration"]},
    "sd": {"adapter_id": "sd", "adapter_version": "sd_adapter_v1", "required_fields": ["scene_id", "camera", "duration"]},
}


def serialize_prompt_ir_to_adapter(prompt_ir: dict[str, Any], adapter_id: str, *, capability_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    adapter_key = _text(adapter_id).lower() or "kling"
    contract = ADAPTER_CONTRACTS.get(adapter_key)
    if not contract:
        return {"status": "blocked", "diagnostics": [{"code": "ADAPTER_UNSUPPORTED", "adapter_id": adapter_key, "severity": "blocked"}], "provider_calls": 0}
    storyboard = _dict(prompt_ir.get("storyboard"))
    missing = [field for field in contract["required_fields"] if field not in storyboard or storyboard.get(field) in (None, "", [])]
    if missing:
        return {"status": "blocked", "diagnostics": [{"code": "ADAPTER_REQUIRED_INPUT_MISSING", "field": field, "severity": "blocked"} for field in missing], "provider_calls": 0, "adapter_id": adapter_key, "adapter_version": contract["adapter_version"]}
    bindings = _dict(prompt_ir.get("assets")).get("bindings", [])
    labels = []
    refs = []
    facts = []
    for binding in bindings if isinstance(bindings, list) else []:
        label = _text(binding.get("asset_name") or binding.get("canonical_asset_id"))
        if not label:
            continue
        if _text(binding.get("reference_status")) == "REFERENCE_READY" and _text(binding.get("reference_token")):
            refs.append(_text(binding.get("reference_token")))
        labels.append(f"{binding.get('asset_type')}:{label}")
        for fact in _list(binding.get("visual_facts")):
            if isinstance(fact, dict) and _text(fact.get("value") or fact.get("fact")):
                facts.append(_text(fact.get("value") or fact.get("fact")))
    camera = _dict(storyboard.get("camera"))
    static = f"场景 {storyboard.get('scene_id')}；镜头 {camera.get('shot_size')}、{camera.get('angle')}、{camera.get('movement')}、{camera.get('speed')}；资产身份：{'、'.join(labels) if labels else '仅按权威身份'}。"
    if refs:
        static += f"锁定参考：{'、'.join(refs)}。"
    if facts:
        static += f"已授权视觉事实：{'；'.join(facts)}。"
    motion = f"{storyboard.get('duration')}秒内，按已声明动作节拍执行：" + "；".join(_text(item.get("description") or item.get("action")) for item in _list(storyboard.get("action_beats")) if isinstance(item, dict))
    negative = "不得新增人物、道具、场景或未授权外观；不得改变镜头、时长、动作与连续性约束；不得出现文字、水印或身份漂移。"
    output = {"status": "ready" if prompt_ir.get("model_generation_ready") else "blocked", "adapter_id": contract["adapter_id"], "adapter_version": contract["adapter_version"], "capability_profile": capability_profile or {}, "static_prompt": static, "motion_prompt": motion, "negative_prompt": negative, "references": refs, "authority_projection": {"scene_id": storyboard.get("scene_id"), "camera": camera, "duration": storyboard.get("duration"), "action_beats": storyboard.get("action_beats"), "entry_state": storyboard.get("entry_state"), "exit_state": storyboard.get("exit_state"), "continuity_contract": storyboard.get("continuity_contract"), "asset_bindings": bindings}, "serialization_status": "DERIVED_SERIALIZATION_OUTPUT", "provider_calls": 0}
    output["output_fingerprint"] = fingerprint({"prompt_ir_fingerprint": prompt_ir.get("payload_hash"), "adapter_id": contract["adapter_id"], "adapter_version": contract["adapter_version"], "capability_profile": capability_profile or {}, "authority_projection": output["authority_projection"]})
    return output


def mark_prompt_ir_stale(session: Any, version: Any, reasons: list[str]) -> None:
    normalized = sorted({_text(item) for item in reasons if _text(item)})
    version.stale_status = "STALE"
    version.stale_reasons = json.dumps(normalized, ensure_ascii=False)
    version.updated_at = datetime.now()
    authority = session.query(__import__("models", fromlist=["PromptIRAuthority"]).PromptIRAuthority).filter_by(prompt_ir_version_id=version.id).first()
    if authority:
        authority.stale_status = "STALE"
        authority.stale_reasons = json.dumps(normalized, ensure_ascii=False)
        authority.updated_at = datetime.now()


def resolve_current_prompt_ir(session: Any, *, book_id: int, episode: int, storyboard_shot_id: int):
    """Resolve the current PromptIR pointer and fail closed on stale lineage."""
    from fastapi import HTTPException
    from models import PromptIRAuthority, PromptIRPointer, PromptIRVersion, StoryboardShot
    from core.storyboard_materializer import resolve_current_authoritative_materialization

    pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=storyboard_shot_id).first()
    if not pointer:
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_POINTER_MISSING", "message": "No current PromptIR pointer exists."})
    version = session.query(PromptIRVersion).filter_by(id=pointer.prompt_ir_version_id, book_id=book_id, episode=episode, storyboard_shot_id=storyboard_shot_id).first()
    authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=pointer.prompt_ir_version_id).first()
    row = session.query(StoryboardShot).filter_by(id=storyboard_shot_id, book_id=book_id, episode=episode).first()
    if not version or not authority or not row or version.stale_status != "FRESH" or authority.stale_status != "FRESH" or pointer.payload_hash != version.payload_hash:
        if version:
            mark_prompt_ir_stale(session, version, ["PROMPT_IR_POINTER_OR_PAYLOAD_INVALID"])
            session.commit()
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_STALE", "message": "Current PromptIR pointer or payload is invalid."})
    try:
        materialization_set, _rows, _envelope = resolve_current_authoritative_materialization(session, book_id=book_id, episode=episode, scene_id=str(row.scene_id or ""))
    except HTTPException:
        mark_prompt_ir_stale(session, version, ["STORYBOARD_MATERIALIZATION_CHANGED"])
        session.commit()
        raise
    if int(version.materialization_set_id) != int(materialization_set.id) or int(row.id) != int(version.storyboard_shot_id):
        mark_prompt_ir_stale(session, version, ["STORYBOARD_MATERIALIZATION_CHANGED"])
        session.commit()
        raise HTTPException(status_code=409, detail={"code": "PROMPT_IR_STALE", "message": "Storyboard materialization changed; PromptIR must be recompiled."})
    return version, authority


__all__ = ["PROMPT_IR_SCHEMA_VERSION", "PROMPT_IR_AUTHORITY_ENVELOPE_VERSION", "PROMPT_IR_COMPILER_VERSION", "PROMPT_IR_COMPILER_POLICY_VERSION", "RETENTION_POLICY_VERSION", "STORYBOARD_CONSTRAINT", "VISUAL_ASSET_CONSTRAINT", "COMPILER_POLICY", "MODEL_ADAPTER_POLICY", "MEDIA_PENDING", "UNKNOWN_INVALID", "PromptIRAuthorityError", "prompt_ir_authority_contract", "contract_fingerprint", "prompt_ir_payload_hash", "compile_prompt_ir_from_handoff", "build_prompt_ir_authority_envelope", "ADAPTER_CONTRACTS", "serialize_prompt_ir_to_adapter", "mark_prompt_ir_stale", "resolve_current_prompt_ir", "fingerprint"]
