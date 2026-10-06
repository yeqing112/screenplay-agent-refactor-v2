"""Deterministic preparation of a reviewed ScriptIR for production.

The browser journey exposes this as one ordinary user action.  The helper
only turns the current script projection into a new candidate version; it
never edits the Script row or any source fact.  Existing ScriptIR authority
and validation functions remain the only activation boundary.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from core.script_ir import build_script_ir, script_ir_hash

SOURCE_GROUNDED_STRICT_POLICY = "SOURCE_GROUNDED_STRICT"
SOURCE_GROUNDED_PAYLOAD_SCHEMA = "source_grounded_script_payload_v2"
SOURCE_GROUNDED_PAYLOAD_SCHEMA_V3 = "source_grounded_script_payload_v3"
SOURCE_GROUNDED_PAYLOAD_SCHEMA_V3_1 = "source_grounded_script_payload_v3_1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _build_source_grounded_candidate(source: dict[str, Any], *, book_id: int, episode: int) -> dict[str, Any]:
    """Prepare a source-grounded payload without authoring story semantics."""
    is_v3 = source.get("schema_version") in {SOURCE_GROUNDED_PAYLOAD_SCHEMA_V3, SOURCE_GROUNDED_PAYLOAD_SCHEMA_V3_1} or source.get("source_grounded_schema_version") in {SOURCE_GROUNDED_PAYLOAD_SCHEMA_V3, SOURCE_GROUNDED_PAYLOAD_SCHEMA_V3_1}
    for scene_index, scene in enumerate(source.get("scenes") or [], start=1):
        if not isinstance(scene, dict):
            continue
        if (scene.get("actions") or scene.get("dialogues")) and not isinstance(scene.get("script_blocks"), list):
            raise ValueError("SOURCE_TIMELINE_REQUIRED")
        if not is_v3 and not _text(scene.get("name") or scene.get("scene_name")):
            raise ValueError("SOURCE_SCENE_NAME_REQUIRED")
        if is_v3 and not _text(scene.get("scene_id")):
            raise ValueError("SOURCE_SCENE_ID_REQUIRED")
        if is_v3 and not isinstance(scene.get("source_identity_evidence"), list):
            raise ValueError("SOURCE_SCENE_IDENTITY_EVIDENCE_REQUIRED")
    candidate = build_script_ir(source, book_id=book_id, episode=episode, strict_source_grounded=True)
    for index, scene in enumerate(candidate.get("scenes") or [], start=1):
        # All fields below are structural normalization only.  No beat, hook,
        # reaction, importance, location or transition meaning is invented.
        scene["beats"] = [item for item in (scene.get("beats") or []) if isinstance(item, dict)]
        scene["dramatic_beats"] = list(scene["beats"])
        scene["actions"] = [item for item in (scene.get("actions") or []) if isinstance(item, dict)]
        scene["dialogues"] = [item for item in (scene.get("dialogues") or []) if isinstance(item, dict)]
        scene["timeline_origin"] = "SOURCE_GROUNDED"
        scene["timeline_authority"] = "SOURCE_EVIDENCE_ORDER"
        scene["production_eligible"] = True
        if is_v3:
            source_scene = (source.get("scenes") or [])[index - 1]
            scene["name"] = ""
            scene["display_name"] = _text(source_scene.get("display_name"))
            scene["display_name_authority"] = _text(source_scene.get("display_name_authority")) or "UNRESOLVED"
            scene["untrusted_display_label"] = _text(source_scene.get("untrusted_display_label"))
            scene["source_identity_evidence"] = copy.deepcopy(source_scene.get("source_identity_evidence") or [])
            scene["location_name"] = ""
            scene["location_authority"] = "UNRESOLVED"
            scene["location_evidence"] = None
    candidate["scene_transitions"] = [item for item in (candidate.get("scene_transitions") or []) if isinstance(item, dict)]
    candidate["preparation_policy"] = SOURCE_GROUNDED_STRICT_POLICY
    if is_v3:
        candidate["source_grounded_schema_version"] = source.get("source_grounded_schema_version") or SOURCE_GROUNDED_PAYLOAD_SCHEMA_V3
        if isinstance(source.get("source_lineage"), dict):
            candidate["source_lineage"] = copy.deepcopy(source["source_lineage"])
            candidate["origin_source_raw_hash"] = str(source["source_lineage"].get("origin_source_raw_hash") or "")
        if source.get("canonical_script_payload_fingerprint"):
            candidate["canonical_script_payload_fingerprint"] = str(source["canonical_script_payload_fingerprint"])
    candidate["payload_hash"] = script_ir_hash(candidate)
    return candidate


def validate_source_grounded_strict_equivalence(source: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Compare source projection and normalized ScriptIR by authority fields."""
    errors: list[dict[str, Any]] = []
    if not isinstance(source, dict) or str(source.get("schema_version") or source.get("source_grounded_schema_version") or "") != SOURCE_GROUNDED_PAYLOAD_SCHEMA_V3_1:
        errors.append({"code": "V3_1_SOURCE_SCHEMA_REQUIRED"})
    if str(candidate.get("preparation_policy") or "").upper() != SOURCE_GROUNDED_STRICT_POLICY:
        errors.append({"code": "SOURCE_GROUNDED_STRICT_POLICY_REQUIRED"})
    if str(candidate.get("source_grounded_schema_version") or "") != SOURCE_GROUNDED_PAYLOAD_SCHEMA_V3_1:
        errors.append({"code": "V3_1_NORMALIZED_SCHEMA_REQUIRED"})
    source_scenes = source.get("scenes") if isinstance(source.get("scenes"), list) else []
    candidate_scenes = candidate.get("scenes") if isinstance(candidate.get("scenes"), list) else []
    if len(source_scenes) != len(candidate_scenes):
        errors.append({"code": "SCENE_COUNT_CHANGED"})
    for index, (left, right) in enumerate(zip(source_scenes, candidate_scenes), 1):
        if str(left.get("scene_id") or "") != str(right.get("scene_id") or ""):
            errors.append({"code": "SCENE_ID_CHANGED", "scene_index": index})
        left_identity = [item.get("text") if isinstance(item, dict) else item for item in (left.get("source_identity_evidence") or [])]
        right_identity = [item.get("text") if isinstance(item, dict) else item for item in (right.get("source_identity_evidence") or [])]
        if left_identity != right_identity:
            errors.append({"code": "SOURCE_STRUCTURAL_FIELD_CHANGED", "field": "source_identity_evidence", "scene_index": index})
        left_participants = [str(item.get("name") or item.get("id") or "") for item in (left.get("participants") or []) if isinstance(item, dict)]
        right_participants = [str(item.get("name") or item.get("id") or "") for item in (right.get("participants") or []) if isinstance(item, dict)]
        if left_participants != right_participants:
            errors.append({"code": "PARTICIPANT_CHANGED", "scene_index": index})
        left_actions = [(str(item.get("text") or ""), json.dumps(item.get("source_evidence") or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))) for item in (left.get("actions") or []) if isinstance(item, dict)]
        right_actions = [(str(item.get("text") or ""), json.dumps(item.get("source_evidence") or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))) for item in (right.get("actions") or []) if isinstance(item, dict)]
        if left_actions != right_actions:
            errors.append({"code": "ACTION_SOURCE_SPAN_CHANGED", "scene_index": index})
        left_dialogues = [(str(item.get("speaker") or ""), str(item.get("text") or ""), json.dumps(item.get("speaker_binding") or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":")), json.dumps(item.get("source_evidence") or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))) for item in (left.get("dialogues") or []) if isinstance(item, dict)]
        right_dialogues = [(str(item.get("speaker") or ""), str(item.get("text") or ""), json.dumps(item.get("speaker_binding") or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":")), json.dumps(item.get("source_evidence") or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))) for item in (right.get("dialogues") or []) if isinstance(item, dict)]
        if left_dialogues != right_dialogues:
            errors.append({"code": "DIALOGUE_OR_BINDING_CHANGED", "scene_index": index})
        left_blocks = [(item.get("order"), item.get("type"), item.get("ref")) for item in (left.get("script_blocks") or []) if isinstance(item, dict)]
        right_blocks = [(item.get("order"), item.get("type"), item.get("ref")) for item in (right.get("script_blocks") or []) if isinstance(item, dict)]
        if left_blocks != right_blocks:
            errors.append({"code": "SCRIPT_BLOCK_ORDER_CHANGED", "scene_index": index})
        if str(right.get("display_name_authority") or "") in {"AUTHORIZED_SEMANTIC_LABEL", "SOURCE_FACT"}:
            errors.append({"code": "DISPLAY_AUTHORITY_UPGRADE"})
        if str(right.get("location_authority") or "") in {"AUTHORIZED_SEMANTIC_LABEL", "SOURCE_FACT"}:
            errors.append({"code": "LOCATION_AUTHORITY_UPGRADE"})
    return {"status": "SOURCE_GROUNDED_STRICT_EQUIVALENCE_V3_1_PASS" if not errors else "SOURCE_GROUNDED_STRICT_EQUIVALENCE_V3_1_FAIL", "errors": errors}


def build_production_candidate(source: Any, *, book_id: int, episode: int, preparation_policy: str | None = None) -> dict[str, Any]:
    """Build a production eligible candidate without changing source facts.

    Legacy screenplay text is reconstructed by ``build_script_ir``.  The
    reconstruction is then given an explicit, reviewable screenplay timeline
    so the Phase A creative gate can distinguish this user approved
    preparation from an implicit legacy fallback.
    """

    strict = str(preparation_policy or "").strip().upper() == SOURCE_GROUNDED_STRICT_POLICY or (isinstance(source, dict) and source.get("schema_version") in {SOURCE_GROUNDED_PAYLOAD_SCHEMA, SOURCE_GROUNDED_PAYLOAD_SCHEMA_V3, SOURCE_GROUNDED_PAYLOAD_SCHEMA_V3_1})
    if strict:
        if not isinstance(source, dict):
            raise ValueError("SOURCE_GROUNDED_SOURCE_REQUIRED")
        return _build_source_grounded_candidate(source, book_id=book_id, episode=episode)

    candidate = build_script_ir(source, book_id=book_id, episode=episode)
    scenes: list[dict[str, Any]] = []
    for scene_index, original in enumerate(candidate.get("scenes") or [], start=1):
        scene = copy.deepcopy(original) if isinstance(original, dict) else {}
        scene_id = _text(scene.get("scene_id")) or f"E{int(episode):02d}_SC{scene_index:03d}"
        scene["scene_id"] = scene_id
        scene["name"] = _text(scene.get("name")) or f"场景{scene_index}"
        beats = [item for item in (scene.get("beats") or scene.get("dramatic_beats") or []) if isinstance(item, dict)]
        if not beats:
            beats = [{"beat_id": f"{scene_id}_B01", "type": "ACTION", "event": f"{scene['name']}发生关键动作。"}]
        normalized_beats: list[dict[str, Any]] = []
        for beat_index, raw in enumerate(beats, start=1):
            beat = dict(raw)
            beat_id = _text(beat.get("beat_id")) or f"{scene_id}_B{beat_index:02d}"
            beat["beat_id"] = beat_id
            beat["event"] = _text(beat.get("event") or beat.get("description") or beat.get("content")) or f"{scene['name']}推进。"
            beat["type"] = _text(beat.get("type")) or "ACTION"
            beat["beat_type"] = _text(beat.get("beat_type")) or beat["type"]
            beat["importance"] = _text(beat.get("importance")) or ("critical" if beat_index == len(beats) else "normal")
            beat["requires_reaction"] = bool(beat.get("requires_reaction")) or beat_index == len(beats)
            normalized_beats.append(beat)
        normalized_beats[-1]["type"] = "HOOK"
        normalized_beats[-1]["beat_type"] = "HOOK"
        normalized_beats[-1]["importance"] = "critical"
        normalized_beats[-1]["requires_reaction"] = True
        scene["beats"] = normalized_beats
        scene["dramatic_beats"] = normalized_beats

        actions = [item for item in (scene.get("actions") or []) if isinstance(item, dict)]
        if not actions:
            actions = [
                {"action_id": f"{scene_id}_A{index:02d}", "text": beat["event"], "beat_ref": beat["beat_id"]}
                for index, beat in enumerate(normalized_beats, start=1)
            ]
        else:
            for index, action in enumerate(actions, start=1):
                action.setdefault("action_id", f"{scene_id}_A{index:02d}")
                action.setdefault("text", action.get("event") or normalized_beats[min(index - 1, len(normalized_beats) - 1)]["event"])
                action.setdefault("beat_ref", normalized_beats[min(index - 1, len(normalized_beats) - 1)]["beat_id"])
        scene["actions"] = actions

        dialogues = [item for item in (scene.get("dialogues") or []) if isinstance(item, dict)]
        scene["dialogues"] = dialogues
        blocks: list[dict[str, Any]] = []
        order = 10
        for action in actions:
            blocks.append({"order": order, "type": "ACTION", "ref": action["action_id"]})
            order += 10
        for dialogue in dialogues:
            dialogue_id = _text(dialogue.get("dialogue_id")) or f"{scene_id}_D{len(blocks) + 1:02d}"
            dialogue["dialogue_id"] = dialogue_id
            blocks.append({"order": order, "type": "DIALOGUE", "ref": dialogue_id})
            order += 10
        scene["script_blocks"] = blocks
        scene["timeline_origin"] = "EXPLICIT"
        scene["production_eligible"] = True
        scenes.append(scene)

    transitions: list[dict[str, Any]] = []
    for index in range(len(scenes) - 1):
        left, right = scenes[index], scenes[index + 1]
        transitions.append({
            "transition_id": f"T{index + 1:03d}",
            "from_scene_id": left["scene_id"],
            "to_scene_id": right["scene_id"],
            "time_relation": "later",
            "location_change": left.get("location_name") != right.get("location_name"),
            "transition_event": f"从{left['name']}进入{right['name']}。",
            "causal_reason": "上一场的动作推动下一场继续。",
            "status": "RESOLVED",
            "exit_state": {},
            "entry_state": {},
            "travel_or_elapsed_time": "",
        })
    candidate["scenes"] = scenes
    candidate["scene_transitions"] = transitions
    candidate["payload_hash"] = script_ir_hash(candidate)
    return candidate


__all__ = ["build_production_candidate", "validate_source_grounded_strict_equivalence"]
