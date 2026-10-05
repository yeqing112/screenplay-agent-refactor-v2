"""Provider-free source structuring contract v2.

The LLM-facing object contains semantic selections only.  All source
locations, byte ranges, hashes and lineage are computed locally after the
response is received.  This module has no provider or database side effects.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

SCHEMA_VERSION = "source_grounded_screenplay_structuring_candidate_v2"
GROUNDED_VERSION = "grounded_source_screenplay_structuring_candidate_v2"
FORBIDDEN_LLM_FIELDS = {"start", "end", "byte_offset", "byte_start", "byte_end", "char_start", "char_end", "sha256"}
ALLOWLIST = ("林晚", "顾沉")


class SourceEvidenceError(ValueError):
    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.details = details


def _sha(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _occurrences(raw: str, needle: str) -> list[int]:
    positions: list[int] = []
    cursor = 0
    while needle and cursor <= len(raw):
        found = raw.find(needle, cursor)
        if found < 0:
            break
        positions.append(found)
        cursor = found + 1
    return positions


def resolve_exact_source_evidence(raw_source: str, evidence_text: str) -> dict[str, Any]:
    """Resolve one exact source excerpt without choosing an ambiguous match."""
    raw = str(raw_source or "")
    text = str(evidence_text or "")
    if not text:
        raise SourceEvidenceError("SOURCE_EVIDENCE_NOT_FOUND", "source evidence must not be empty")
    positions = _occurrences(raw, text)
    if not positions:
        raise SourceEvidenceError("SOURCE_EVIDENCE_NOT_FOUND", "exact source evidence was not found", evidence_text=text)
    if len(positions) != 1:
        raise SourceEvidenceError("SOURCE_EVIDENCE_AMBIGUOUS", "exact source evidence occurs more than once", evidence_text=text, occurrence_count=len(positions))
    start = positions[0]
    end = start + len(text)
    byte_start = len(raw[:start].encode("utf-8"))
    byte_end = len(raw[:end].encode("utf-8"))
    return {"text": text, "char_start": start, "char_end": end, "byte_start": byte_start, "byte_end": byte_end, "sha256": _sha(text), "occurrence_count": 1}


def _walk_forbidden(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key) in FORBIDDEN_LLM_FIELDS:
                found.append(f"{path}.{key}")
            found.extend(_walk_forbidden(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk_forbidden(child, f"{path}[{index}]"))
    return found


def _exact_evidence_list(raw: str, values: Any, *, field: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(values, list) or not values:
        return [], [{"code": "SOURCE_EVIDENCE_REQUIRED", "field": field}]
    grounded: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for value in values:
        try:
            grounded.append(resolve_exact_source_evidence(raw, str(value)))
        except SourceEvidenceError as exc:
            errors.append({"code": exc.code, "field": field, **exc.details})
    return grounded, errors


def _label_evidence(items: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    return [{**item, "evidence_id": f"{prefix}{index:03d}"} for index, item in enumerate(items, start=1)]


def _is_direct_quote(raw: str, text: str) -> bool:
    pairs = (("“", "”"), ("\"", "\""), ("「", "」"), ("『", "』"), ("‘", "’"))
    return any(f"{left}{text}{right}" in raw for left, right in pairs)


def _reported_speech_like(text: str) -> bool:
    markers = ("说", "回答", "问", "告诉", "表示")
    return any(marker in text for marker in markers)


def _reported_speech_in_source(raw: str, text: str) -> bool:
    return any(f"{marker}{text}" in raw for marker in ("说", "回答", "问", "告诉", "表示"))


def ground_candidate_v2(raw_source: str, candidate: Any, *, source_fingerprint: str | None = None, expected_source_fingerprint: str | None = None, allowlist: tuple[str, ...] = ALLOWLIST) -> dict[str, Any]:
    """Enrich and validate a semantic V2 candidate with local evidence."""
    raw = str(raw_source or "")
    errors: list[dict[str, Any]] = []
    raw_fingerprint = _sha(raw)
    if expected_source_fingerprint is not None and str(expected_source_fingerprint) != raw_fingerprint:
        errors.append({"code": "AUTHORIZED_SOURCE_CHANGED", "expected": str(expected_source_fingerprint), "actual": raw_fingerprint})
    if not isinstance(candidate, dict):
        return {"status": "FAIL", "errors": [{"code": "CANDIDATE_NOT_OBJECT"}]}
    if candidate.get("schema_version") != SCHEMA_VERSION:
        errors.append({"code": "SCHEMA_VERSION_INVALID"})
    forbidden = _walk_forbidden(candidate)
    if forbidden:
        errors.append({"code": "LLM_MUST_NOT_PROVIDE_LOCAL_OFFSETS_OR_HASHES", "paths": forbidden})
    if candidate.get("historical_source") or candidate.get("source_layer") == "historical_script_ir":
        errors.append({"code": "HISTORICAL_DERIVED_EVIDENCE_FORBIDDEN"})
    scenes = candidate.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        errors.append({"code": "SCENES_REQUIRED"})
        return {"status": "FAIL", "errors": errors}
    grounded_scenes: list[dict[str, Any]] = []
    seen_dialogue_text: set[str] = set()
    for scene_index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            errors.append({"code": "SCENE_INVALID", "scene_index": scene_index}); continue
        scene_label = str(scene.get("scene_label") or "").strip()
        if not scene_label:
            errors.append({"code": "SCENE_LABEL_REQUIRED", "scene_index": scene_index})
        scene_ev, scene_errors = _exact_evidence_list(raw, scene.get("scene_evidence"), field=f"scenes[{scene_index}].scene_evidence")
        errors.extend(scene_errors)
        grounded_participants: list[dict[str, Any]] = []
        participants = scene.get("participants") if isinstance(scene.get("participants"), list) else []
        for participant_index, participant in enumerate(participants):
            if not isinstance(participant, dict):
                errors.append({"code": "PARTICIPANT_INVALID", "scene_index": scene_index}); continue
            name = str(participant.get("name") or "").strip()
            if name not in allowlist:
                errors.append({"code": "PARTICIPANT_NOT_ALLOWLISTED", "name": name})
            evidence, participant_errors = _exact_evidence_list(raw, participant.get("evidence"), field=f"participant:{name}")
            errors.extend(participant_errors)
            grounded_participants.append({"name": name, "evidence": _label_evidence(evidence, f"S{scene_index}P{participant_index + 1}E")})
        grounded_actions: list[dict[str, Any]] = []
        for action_index, action in enumerate(scene.get("actions") or []):
            if not isinstance(action, dict) or not str(action.get("source_text") or ""):
                errors.append({"code": "ACTION_SOURCE_TEXT_REQUIRED", "scene_index": scene_index}); continue
            try:
                evidence = resolve_exact_source_evidence(raw, str(action["source_text"]))
                grounded_actions.append({"source_evidence": {**evidence, "evidence_id": f"S{scene_index}A{action_index + 1:03d}"}})
            except SourceEvidenceError as exc:
                errors.append({"code": exc.code, "field": f"action:{action_index}", **exc.details})
        grounded_dialogues: list[dict[str, Any]] = []
        for dialogue_index, dialogue in enumerate(scene.get("dialogues") or []):
            if not isinstance(dialogue, dict):
                errors.append({"code": "DIALOGUE_INVALID", "scene_index": scene_index}); continue
            speaker = str(dialogue.get("speaker") or "").strip()
            text = str(dialogue.get("text") or "")
            if speaker not in allowlist:
                errors.append({"code": "SPEAKER_NOT_ALLOWLISTED", "speaker": speaker})
            if not text:
                errors.append({"code": "DIALOGUE_TEXT_REQUIRED"})
            try:
                utterance = resolve_exact_source_evidence(raw, text)
            except SourceEvidenceError as exc:
                errors.append({"code": exc.code, "field": f"dialogue:{dialogue_index}", **exc.details})
                utterance = None
            if text in seen_dialogue_text:
                errors.append({"code": "DIALOGUE_DUPLICATED", "text": text})
            seen_dialogue_text.add(text)
            if text and not _is_direct_quote(raw, text):
                errors.append({"code": "DIALOGUE_NOT_DIRECT_QUOTE", "text": text})
                if _reported_speech_like(text) or _reported_speech_in_source(raw, text):
                    errors.append({"code": "REPORTED_SPEECH_PROMOTED", "text": text})
            identity, identity_errors = _exact_evidence_list(raw, dialogue.get("speaker_identity_evidence"), field=f"dialogue:{dialogue_index}.speaker_identity_evidence")
            utterance_context, utterance_errors = _exact_evidence_list(raw, dialogue.get("utterance_evidence"), field=f"dialogue:{dialogue_index}.utterance_evidence")
            errors.extend(identity_errors); errors.extend(utterance_errors)
            binding_type = str(dialogue.get("binding_type") or "").strip()
            if not binding_type:
                errors.append({"code": "BINDING_TYPE_REQUIRED", "speaker": speaker})
            literal = any(speaker in item["text"] for item in utterance_context)
            classification = "SOURCE_LITERAL_BINDING" if literal else "AUTHORIZED_SEMANTIC_BINDING"
            if not literal and binding_type != "COREFERENCE_RESOLUTION":
                errors.append({"code": "SEMANTIC_BINDING_TYPE_REQUIRED", "speaker": speaker})
            if identity and utterance_context and min(item["char_start"] for item in identity) > min(item["char_start"] for item in utterance_context):
                errors.append({"code": "SPEAKER_EVIDENCE_ORDER_INVALID", "speaker": speaker})
            if utterance and text:
                grounded_dialogues.append({"speaker": speaker, "text": text, "utterance_evidence": _label_evidence(utterance_context, f"S{scene_index}D{dialogue_index + 1}U"), "speaker_identity_evidence": _label_evidence(identity, f"S{scene_index}D{dialogue_index + 1}I"), "utterance": {**utterance, "evidence_id": f"S{scene_index}D{dialogue_index + 1:03d}"}, "binding_type": binding_type, "binding_classification": classification})
        grounded_scenes.append({"scene_label": scene_label, "scene_evidence": _label_evidence(scene_ev, f"S{scene_index}E"), "participants": grounded_participants, "actions": grounded_actions, "dialogues": grounded_dialogues})
    grounded = {"schema_version": GROUNDED_VERSION, "source_fingerprint": raw_fingerprint, "source_length": len(raw.encode("utf-8")), "scenes": grounded_scenes, "unknowns": candidate.get("unknowns") if isinstance(candidate.get("unknowns"), list) else [], "validation_status": "PASS" if not errors else "FAIL", "errors": errors}
    return {"status": grounded["validation_status"], "errors": errors, "grounded_candidate": grounded}


def canonical_script_payload_v2(grounded: Any) -> dict[str, Any]:
    if not isinstance(grounded, dict) or grounded.get("schema_version") != GROUNDED_VERSION or grounded.get("validation_status") != "PASS":
        raise ValueError("GROUNDED_CANDIDATE_REQUIRED")
    scenes = []
    for index, scene in enumerate(grounded.get("scenes") or [], start=1):
        scene_id = f"CH03_SC{index:02d}"
        participants = [{"id": p["name"], "character_id": p["name"], "name": p["name"]} for p in scene.get("participants") or []]
        actions = [{"action_id": f"{scene_id}_A{n:03d}", "text": item["source_evidence"]["text"], "source_evidence": item["source_evidence"]} for n, item in enumerate(scene.get("actions") or [], start=1)]
        dialogues = [{"dialogue_id": f"{scene_id}_D{n:03d}", "speaker": item["speaker"], "text": item["text"], "source_evidence": item["utterance"], "speaker_binding": {"classification": item["binding_classification"], "binding_type": item["binding_type"], "identity_evidence": item["speaker_identity_evidence"], "utterance_evidence": item["utterance_evidence"]}} for n, item in enumerate(scene.get("dialogues") or [], start=1)]
        scenes.append({"scene_id": scene_id, "name": scene["scene_label"], "participants": participants, "actions": actions, "dialogues": dialogues, "scene_evidence": scene.get("scene_evidence") or []})
    return {"schema_version": "source_grounded_script_payload_v2", "source_fingerprint": grounded["source_fingerprint"], "scenes": scenes}


def retain_forensic_response(*, run_id: str, response: Any, provider: str, model: str, provider_request_id: str = "") -> dict[str, Any]:
    serialized = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    text = str(serialized)
    safe = {"run_id": run_id, "received": True, "response_sha256": _sha(text), "response_length": len(text), "provider": provider, "model": model, "provider_request_id": str(provider_request_id or "")[:200], "validation_not_yet_run": True, "secret_fields_persisted": False}
    def sanitize(value: Any) -> Any:
        if isinstance(value, Mapping):
            clean = {}
            for key, child in value.items():
                key_text = str(key).lower()
                if any(marker in key_text for marker in ("api_key", "authorization", "credential", "secret", "token")):
                    clean[str(key)] = "[REDACTED]"
                else:
                    clean[str(key)] = sanitize(child)
            return clean
        if isinstance(value, list):
            return [sanitize(child) for child in value]
        return value
    if isinstance(response, (dict, list)):
        safe["parsed_json"] = sanitize(response)
    else:
        safe["raw_response_excerpt"] = text[:2000]
    return safe


def transport_attempt_budget(retries: int | None) -> int:
    return max(1, int(retries or 0))


def json_parse_attempt_budget(json_parse_retries: int | None) -> int:
    return max(1, int(json_parse_retries or 0) + 1)


__all__ = ["SCHEMA_VERSION", "GROUNDED_VERSION", "ALLOWLIST", "SourceEvidenceError", "resolve_exact_source_evidence", "ground_candidate_v2", "canonical_script_payload_v2", "retain_forensic_response", "transport_attempt_budget", "json_parse_attempt_budget"]
