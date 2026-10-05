"""Model independent video intent IR.

This layer is the semantic boundary between Director/Shot truth and model
compilers.  It intentionally contains no provider names, HTTP URLs, model
tokens, or transport fields.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from .shot_readiness import ShotPropState, canonical_shot_prop_states


@dataclass(frozen=True)
class CharacterIntent:
    character_id: str
    display_name: str
    start_state: Mapping[str, Any]
    role: str
    silent: bool
    authority_fingerprint: str
    reference_roles: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"start_state": dict(self.start_state), "reference_roles": list(self.reference_roles)}


@dataclass(frozen=True)
class DialogueIntent:
    mode: str
    speaker_character_id: str | None
    authoritative_text: str
    language: str | None
    phrase_windows: tuple[Mapping[str, Any], ...]
    silent_character_ids: tuple[str, ...]
    visual_lipsync_policy: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"phrase_windows": [dict(x) for x in self.phrase_windows], "silent_character_ids": list(self.silent_character_ids)}


@dataclass(frozen=True)
class AudioIntent:
    dialogue_required: bool
    room_tone_allowed: bool
    sound_effects_allowed: bool
    music_allowed: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VideoIntentIR:
    shot_id: str
    source_revision: str
    source_fingerprint: str
    director_duration_seconds: float
    scene: Mapping[str, Any]
    characters: tuple[CharacterIntent, ...]
    props: tuple[Mapping[str, Any], ...]
    dialogue: DialogueIntent
    performance_beats: tuple[Mapping[str, Any], ...]
    camera_beats: tuple[Mapping[str, Any], ...]
    ending_state: Mapping[str, Any]
    reference_requirements: Mapping[str, Any]
    audio_intent: AudioIntent
    negative_constraints: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "source_revision": self.source_revision,
            "source_fingerprint": self.source_fingerprint,
            "director_duration_seconds": self.director_duration_seconds,
            "scene": dict(self.scene),
            "characters": [x.as_dict() for x in self.characters],
            "props": [dict(x) for x in self.props],
            "dialogue": self.dialogue.as_dict(),
            "performance_beats": [dict(x) for x in self.performance_beats],
            "camera_beats": [dict(x) for x in self.camera_beats],
            "ending_state": dict(self.ending_state),
            "reference_requirements": dict(self.reference_requirements),
            "audio_intent": self.audio_intent.as_dict(),
            "negative_constraints": list(self.negative_constraints),
        }


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _language(text: str) -> str | None:
    if not text:
        return None
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh-CN"
    if re.search(r"[A-Za-z]", text):
        return "en"
    return None


def _sanitize_state(state: Mapping[str, Any], allowed_prop_ids: set[str]) -> dict[str, Any]:
    """Reconcile stale Director blocking without mutating the source IR."""
    output = dict(state)
    if not allowed_prop_ids:
        forbidden = ("bag strap", "handbag", "shoulder bag", "bag", "手提包", "肩包", "包带", "苹果", "apple")
        for key in ("left_hand", "right_hand", "prop_contact"):
            value = str(output.get(key) or "")
            if any(token.lower() in value.lower() for token in forbidden):
                output[key] = "自然放松，不接触道具"
    return output


def _sanitize_performance(value: Any, allowed_prop_ids: set[str] | None = None) -> Any:
    if isinstance(value, str):
        replacements = {
            "lips slightly parted": "lips gently closed",
            "mouth starts open": "mouth starts gently closed",
            "mouth opens": "mouth remains gently closed",
            "mouth open": "mouth gently closed",
            "speaking mouth": "relaxed non-speaking mouth",
            "嘴唇微张": "嘴唇自然闭合",
            "嘴部张开": "嘴部自然闭合",
        }
        for source, target in replacements.items():
            value = value.replace(source, target)
        if not allowed_prop_ids:
            for source, target in {
                "bag strap": "hands remain relaxed without prop contact",
                "handbag": "no unauthorized prop",
                "shoulder bag": "no unauthorized prop",
                "手提包": "无未授权道具",
                "包带": "无未授权道具",
            }.items():
                value = value.replace(source, target)
        return value
    if isinstance(value, list):
        return [_sanitize_performance(x, allowed_prop_ids) for x in value]
    if isinstance(value, dict):
        return {key: _sanitize_performance(item, allowed_prop_ids) for key, item in value.items()}
    return value


def build_video_intent_ir(
    decision: Mapping[str, Any],
    *,
    source_revision: str = "DIRECTOR_DECISION_IR",
    prop_states: list[Mapping[str, Any]] | None = None,
    reference_plan: Mapping[str, Any] | None = None,
) -> VideoIntentIR:
    source = decision.get("source_facts") if isinstance(decision.get("source_facts"), Mapping) else {}
    shot_id = str(decision.get("shot_id") or source.get("shot_id") or "")
    director_duration = float(decision.get("duration_seconds") or 0)
    raw_dialogue_beats = [x for x in (decision.get("dialogue_beats") or []) if isinstance(x, Mapping)]
    source_text = str(source.get("dialogue") or "")
    mode = "AUTHORITATIVE" if raw_dialogue_beats and source_text.strip() else "NONE"
    dialogue_beat = raw_dialogue_beats[0] if raw_dialogue_beats else {}
    speaker = str(dialogue_beat.get("speaker") or "") or None
    authoritative_text = str(dialogue_beat.get("authoritative_text") or source_text or "") if mode == "AUTHORITATIVE" else ""
    characters_raw = [x for x in (decision.get("blocking") or []) if isinstance(x, Mapping)]
    canonical_props = canonical_shot_prop_states(decision)
    if prop_states is not None:
        supplied = tuple(dict(x) for x in prop_states if isinstance(x, Mapping) and x.get("present"))
        canonical_keys = {(x.prop_id, x.holder, x.hand) for x in canonical_props}
        supplied_keys = {(str(x.get("prop_id") or x.get("id") or ""), str(x.get("holder") or ""), str(x.get("hand") or "")) for x in supplied}
        if supplied_keys != canonical_keys:
            raise ValueError("VIDEO_INTENT_PROP_HOLDER_CONFLICT")
    effective_props = canonical_props
    allowed_prop_ids = {x.prop_id for x in effective_props if x.present}
    characters: list[CharacterIntent] = []
    for item in characters_raw:
        cid = str(item.get("identity") or item.get("character") or "")
        if not cid:
            continue
        state = _sanitize_state(item, allowed_prop_ids)
        role = "speaker" if mode == "AUTHORITATIVE" and cid == speaker else "listener"
        characters.append(CharacterIntent(cid, cid, state, role, role != "speaker", str(item.get("authority_fingerprint") or _fingerprint(state)), ("CHARACTER_FULL", "CHARACTER_FACE")))
    silent_ids = tuple(x.character_id for x in characters if x.character_id != speaker) if mode == "AUTHORITATIVE" else tuple(x.character_id for x in characters)
    dialogue = DialogueIntent(mode, speaker, authoritative_text, _language(authoritative_text), tuple(dict(x) for x in (dialogue_beat.get("phrase_windows") or [])), silent_ids, "TIMED_SPEAKER_ONLY" if mode == "AUTHORITATIVE" else "NO_SPEAKING_MOTION")
    props = tuple(x.as_dict() for x in effective_props if x.present)
    references = {"mode": "FIRST_FRAME", "bindings": [], "roles": ["SCENE_MASTER", "CHARACTER_FULL", "CHARACTER_FACE"]}
    if reference_plan:
        references["bindings"] = [dict(x) for x in (reference_plan.get("references") or []) if isinstance(x, Mapping)]
        references["roles"] = [str(x.get("role") or "") for x in references["bindings"]]
    audio = AudioIntent(mode == "AUTHORITATIVE", mode == "AUTHORITATIVE", False, False)
    negative = ("no additional characters", "no unauthorized props", "preserve scene topology")
    performance_raw = list(decision.get("performance_beats") or [])
    # Canonical ShotPropState is authoritative even when the caller does not
    # pass an explicit list: an empty authorized set must remove stale bag or
    # strap actions from the projected intent.
    performance_projected = _sanitize_performance(performance_raw, allowed_prop_ids)
    semantic_payload = {
        "shot_id": shot_id, "source_revision": source_revision, "director_duration_seconds": director_duration,
        "scene": {"scene_id": source.get("scene_id"), "location": source.get("location")},
        "characters": [x.as_dict() for x in characters], "props": [dict(x) for x in props],
        "dialogue": dialogue.as_dict(), "performance_beats": performance_projected,
        "camera_beats": list(decision.get("camera_beats") or []), "ending_state": decision.get("ending_state") or {},
        "reference_requirements": references, "audio_intent": audio.as_dict(), "negative_constraints": list(negative),
    }
    ending = _sanitize_performance(decision.get("ending_state") or {}, allowed_prop_ids)
    return VideoIntentIR(shot_id, source_revision, _fingerprint(semantic_payload), director_duration, semantic_payload["scene"], tuple(characters), props, dialogue, tuple(dict(x) for x in performance_projected if isinstance(x, Mapping)), tuple(dict(x) for x in (decision.get("camera_beats") or []) if isinstance(x, Mapping)), ending, references, audio, negative)
