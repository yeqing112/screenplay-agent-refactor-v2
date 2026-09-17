"""Deterministic ScriptIR normalization, validation and legacy reconstruction."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SCHEMA_VERSION = "script_ir_v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def script_ir_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_script_ir(payload: Any, *, book_id: int, episode: int, fact_snapshot_id: str = "", source_outline_revision: str = "") -> dict[str, Any]:
    """Normalize a structured script payload into ScriptIR v1."""
    source = payload if isinstance(payload, dict) else {}
    raw_scenes = source.get("scenes") if isinstance(source.get("scenes"), list) else []
    scenes: list[dict[str, Any]] = []
    for scene_index, raw_scene in enumerate(raw_scenes, start=1):
        if not isinstance(raw_scene, dict):
            continue
        name = _text(raw_scene.get("name") or raw_scene.get("scene_name")) or f"未命名场景{scene_index}"
        scene_id = _text(raw_scene.get("scene_id")) or f"E{int(episode):02d}_SC{scene_index:03d}"
        raw_beats = raw_scene.get("beats") if isinstance(raw_scene.get("beats"), list) else []
        beats = []
        for beat_index, raw_beat in enumerate(raw_beats, start=1):
            if isinstance(raw_beat, dict):
                beats.append({
                    "beat_id": _text(raw_beat.get("beat_id") or raw_beat.get("id")) or f"{scene_id}_B{beat_index:02d}",
                    "type": _text(raw_beat.get("type")),
                    "event": _text(raw_beat.get("event") or raw_beat.get("description") or raw_beat.get("content")),
                    "dramatic_function": _text(raw_beat.get("dramatic_function")),
                    "information_change": _text(raw_beat.get("information_change")),
                    "emotion_change": _text(raw_beat.get("emotion_change")),
                })
            elif _text(raw_beat):
                beats.append({"beat_id": f"{scene_id}_B{beat_index:02d}", "type": "action", "event": _text(raw_beat), "dramatic_function": "", "information_change": "", "emotion_change": ""})
        scenes.append({
            "scene_id": scene_id,
            "name": name,
            "location_id": _text(raw_scene.get("location_id")),
            "location_name": _text(raw_scene.get("location_name") or name),
            "time_of_day": _text(raw_scene.get("time_of_day")),
            "weather": _text(raw_scene.get("weather")),
            "participants": raw_scene.get("participants") if isinstance(raw_scene.get("participants"), list) else [],
            "beats": beats,
            "actions": raw_scene.get("actions") if isinstance(raw_scene.get("actions"), list) else [],
            "dialogues": raw_scene.get("dialogues") if isinstance(raw_scene.get("dialogues"), list) else [],
            "state_in": raw_scene.get("state_in") if isinstance(raw_scene.get("state_in"), dict) else {},
            "state_out": raw_scene.get("state_out") if isinstance(raw_scene.get("state_out"), dict) else {},
            "required_visual_proofs": raw_scene.get("required_visual_proofs") if isinstance(raw_scene.get("required_visual_proofs"), list) else [],
            "blocking_hints": raw_scene.get("blocking_hints") if isinstance(raw_scene.get("blocking_hints"), list) else [],
            # Keep explicit spatial declarations available to the
            # evidence-first SceneBlocking stage.  Older ScriptIR payloads
            # simply omit these fields; adding them is backwards compatible
            # and prevents a structured build from silently discarding
            # production-critical blocking evidence.
            "character_blocking": raw_scene.get("character_blocking") if isinstance(raw_scene.get("character_blocking"), list) else [],
            "props": raw_scene.get("props") if isinstance(raw_scene.get("props"), list) else [],
            "asset_mentions": raw_scene.get("asset_mentions") if isinstance(raw_scene.get("asset_mentions"), list) else [],
        })
    result = {
        "schema_version": SCHEMA_VERSION,
        "book_id": int(book_id),
        "episode": int(episode),
        "fact_snapshot_id": _text(fact_snapshot_id),
        "title": _text(source.get("title")),
        "episode_objective": _text(source.get("episode_objective")),
        "characters": source.get("characters") if isinstance(source.get("characters"), list) else [],
        "scenes": scenes,
    }
    result["payload_hash"] = script_ir_hash(result)
    return result


def legacy_markdown_to_script_ir(markdown: str, *, book_id: int, episode: int) -> dict[str, Any]:
    """Best-effort one-time reconstruction; callers must mark needs_review."""
    scenes: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in str(markdown or "").splitlines():
        text = line.strip()
        heading = re.match(r"^#{2,4}\s+(.+?)\s*$", text)
        if heading:
            current = {"name": heading.group(1).strip(), "beats": []}
            scenes.append(current)
        elif text and current is not None and not text.startswith("#"):
            current.setdefault("beats", []).append({"type": "action", "event": text})
    return build_script_ir({"scenes": scenes}, book_id=book_id, episode=episode)


def validate_script_ir(payload: Any) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        errors.append({"code": "SCHEMA_VERSION_INVALID", "message": "ScriptIR schema_version must be script_ir_v1."})
        return {"status": "invalid", "errors": errors, "warnings": warnings}
    scenes = payload.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        errors.append({"code": "SCENES_REQUIRED", "message": "ScriptIR must contain at least one scene."})
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for scene in scenes if isinstance(scenes, list) else []:
        if not isinstance(scene, dict):
            errors.append({"code": "SCENE_OBJECT_INVALID", "message": "Each scene must be an object."})
            continue
        scene_id = _text(scene.get("scene_id"))
        name = _text(scene.get("name"))
        if not scene_id or scene_id in seen_ids:
            errors.append({"code": "SCENE_ID_INVALID", "message": "Scene IDs must be present and unique."})
        seen_ids.add(scene_id)
        if not name:
            errors.append({"code": "SCENE_NAME_REQUIRED", "message": f"{scene_id or 'scene'} requires a name."})
        elif name in seen_names:
            errors.append({"code": "SCENE_NAME_DUPLICATE", "message": f"Scene names must be unique: {name}."})
        else:
            seen_names.add(name)
        beats = scene.get("beats")
        if not isinstance(beats, list) or not beats:
            warnings.append({"code": "SCENE_BEATS_EMPTY", "message": f"{scene_id or name} has no beats."})
    return {"status": "qualified" if not errors else "needs_review", "errors": errors, "warnings": warnings}


def resolve_script_payload(session: Any, script_row: Any, *, workflow_profile: str = "creative_draft") -> dict[str, Any]:
    """Resolve the machine source for downstream director stages.

    Production is fail-closed: it may only consume a qualified ScriptIR.  The
    creative-draft compatibility path may still read the legacy Script.content
    payload while migration is in progress.
    """
    from fastapi import HTTPException

    profile = str(workflow_profile or "creative_draft").strip().lower()
    if profile == "production":
        from models import ScriptIRVersion
        from core.fact_coverage import fingerprint
        from core.fact_snapshot import snapshot_hash
        from core.script_ir_authority import validate_authority_envelope, validate_source_anchor_bindings
        from core.source_evidence_index import build_source_evidence_index
        version = None
        current_id = getattr(script_row, "current_script_ir_version_id", None)
        if current_id:
            version = session.query(ScriptIRVersion).filter_by(id=current_id, book_id=script_row.book_id, episode=script_row.episode).first()
        if version is None:
            raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_AUTHORITY_POINTER_MISSING", "message": "Production workflow requires a current ScriptIR authority pointer to a qualified ScriptIR version."})
        if version.status != "production_qualified" or getattr(version, "qualification_state", "") != "PRODUCTION_QUALIFIED":
            raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_NOT_PRODUCTION_QUALIFIED", "message": "Current ScriptIR is not production-qualified."})
        try:
            payload = json.loads(version.payload_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_PAYLOAD_INVALID", "message": "Production ScriptIR payload is invalid."}) from exc
        try:
            envelope = json.loads(version.authority_envelope_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_AUTHORITY_ENVELOPE_INVALID", "message": "Production ScriptIR authority envelope is invalid."}) from exc
        raw_source_bytes = str(script_row.content or "").encode("utf-8")
        expected: dict[str, Any] = {"book_id": script_row.book_id, "episode": script_row.episode, "immutable_source_raw_hash": hashlib.sha256(raw_source_bytes).hexdigest()}
        try:
            source_package_id = str(envelope.get("source_package_id") or "").strip()
            source_version_id = str(envelope.get("source_version_id") or "").strip()
            if not source_package_id or not source_version_id:
                raise HTTPException(status_code=409, detail={"code": "SOURCE_LINEAGE_REQUIRED", "message": "Production ScriptIR authority has incomplete source lineage."})
            current_evidence_index = build_source_evidence_index(raw_source_bytes, source_package_id=source_package_id, source_version_id=source_version_id, source_raw_hash=expected["immutable_source_raw_hash"])
            expected.update({"authority_policy_version": "script_ir_authority_policy_v1", "source_package_id": source_package_id, "source_version_id": source_version_id, "source_evidence_index_fingerprint": current_evidence_index.get("evidence_index_fingerprint")})
        except HTTPException:
            raise
        except (TypeError, UnicodeDecodeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail={"code": "SOURCE_EVIDENCE_INDEX_INVALID", "message": "Production source evidence index cannot be rebuilt."}) from exc
        # Recompute contract and requirement fingerprints so a contract/schema
        # upgrade cannot silently reuse an old production version.
        try:
            from core.script_ir_source_requirements import compile_script_ir_source_requirements, evaluate_script_ir_source_coverage, script_ir_source_requirement_contract
            current_contract = script_ir_source_requirement_contract()
            raw_source = json.loads(script_row.content or "{}") if str(script_row.content or "").lstrip().startswith("{") else payload
            if not isinstance(raw_source, dict):
                raise ValueError("immutable source is not a structured object")
            current_requirements = compile_script_ir_source_requirements(source_structure=raw_source)
            expected.update({"source_requirement_contract_version": current_contract["schema_version"], "source_requirement_contract_fingerprint": current_contract["fingerprint"], "compiled_requirement_set_fingerprint": current_requirements["fingerprint"]})
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_SOURCE_REQUIREMENTS_UNAVAILABLE", "message": "Current source requirements cannot be recomputed."}) from exc
        try:
            from models import FactSnapshot
            snapshot_id = envelope.get("fact_snapshot_id")
            snapshot = session.query(FactSnapshot).filter_by(id=int(snapshot_id)).first() if str(snapshot_id or "").isdigit() else None
            if not snapshot or snapshot.book_id != script_row.book_id or int(snapshot.episode or -1) != int(script_row.episode) or str(snapshot.status).lower() != "confirmed":
                raise HTTPException(status_code=409, detail={"code": "FACT_SNAPSHOT_BINDING_INVALID", "message": "Bound FactSnapshot is missing, stale or mismatched."})
            records = json.loads(snapshot.records_json or "[]")
            if not isinstance(records, list) or snapshot_hash(records) != str(snapshot.payload_hash or ""):
                raise HTTPException(status_code=409, detail={"code": "FACT_SNAPSHOT_PAYLOAD_HASH_MISMATCH", "message": "Bound FactSnapshot payload hash does not match its records."})
            if str(snapshot.source_fingerprint or "").strip() and str(snapshot.source_fingerprint) != str(expected["immutable_source_raw_hash"]):
                raise HTTPException(status_code=409, detail={"code": "FACT_SNAPSHOT_SOURCE_MISMATCH", "message": "Bound FactSnapshot source fingerprint is stale."})
            coverage = evaluate_script_ir_source_coverage(current_requirements, records=records, allow_source_structure_fallback=False)
            if coverage.get("status") != "SCRIPT_IR_SOURCE_CONTRACT_COVERAGE_SUFFICIENT":
                raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_SOURCE_COVERAGE_INSUFFICIENT", "message": "Bound FactSnapshot no longer covers current ScriptIR requirements.", "coverage": coverage})
            expected.update({"fact_snapshot_id": snapshot.id, "fact_snapshot_revision": snapshot.revision, "fact_snapshot_payload_hash": snapshot.payload_hash, "source_coverage_result_fingerprint": fingerprint(coverage)})
            anchor_check = validate_source_anchor_bindings(requirement_set=current_requirements, source_evidence_index=current_evidence_index, bindings=envelope.get("source_anchor_bindings"))
            if anchor_check.get("status") != "PASS":
                raise HTTPException(status_code=409, detail={"code": "SOURCE_EVIDENCE_BINDING_INVALID", "message": "Production ScriptIR authority source anchors are invalid.", "details": anchor_check})
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=409, detail={"code": "FACT_SNAPSHOT_BINDING_INVALID", "message": "Bound FactSnapshot cannot be validated."})
        report = validate_authority_envelope(envelope, payload=payload, expected=expected)
        if report["status"] != "PASS":
            code = "SCRIPT_IR_AUTHORITY_TAMPERED" if any(str(item.get("code")) in {"SCRIPT_IR_AUTHORITY_TAMPERED", "SCRIPT_IR_AUTHORITY_ENVELOPE_TAMPERED"} for item in report.get("errors", [])) else "SCRIPT_IR_AUTHORITY_STALE"
            raise HTTPException(status_code=409, detail={"code": code, "message": "Production ScriptIR authority validation failed.", "errors": report["errors"], "stale_reasons": report.get("stale_reasons", [])})
        return payload if isinstance(payload, dict) else {"scenes": []}
    try:
        parsed = json.loads(script_row.content or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"raw_content": str(script_row.content or "")}
    return parsed if isinstance(parsed, dict) else {"raw_content": str(script_row.content or "")}
