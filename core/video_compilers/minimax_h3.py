"""Deterministic MiniMax H3 V1 compiler."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from core.shot_readiness import project_provider_duration
from core.video_intent_ir import VideoIntentIR
from .base import CompiledVideoRequestIR, CompilerSupportResult, PromptComplexityAudit, VideoModelCapabilities


H3_CAPABILITIES = VideoModelCapabilities(
    model_family="minimax-h3",
    supports_text_to_video=False,
    supports_first_frame=True,
    supports_reference_images=True,
    supports_native_dialogue=True,
    supports_native_audio=True,
    supports_first_last_frame=False,
    min_duration=5,
    max_duration=15,
    allowed_aspect_ratios=("16:9", "9:16"),
    max_reference_images=8,
)


class CompilerPromptComplexityError(ValueError):
    pass


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _natural_state(state: dict[str, Any]) -> str:
    ignored = {"identity", "reference_identity", "screen_x", "depth_zone", "authority_fingerprint"}
    parts = [f"{key.replace('_', ' ')} {value}" for key, value in state.items() if key not in ignored and value not in (None, "")]
    return "; ".join(parts)


def _language_label(language: str | None) -> str:
    return {"zh-CN": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean"}.get(str(language or ""), "")


class MiniMaxH3Compiler:
    compiler_id = "minimax-h3"
    compiler_version = "1"
    model_family = "minimax-h3"

    def supports(self, intent: VideoIntentIR, capabilities: VideoModelCapabilities) -> CompilerSupportResult:
        if capabilities.model_family != self.model_family:
            return CompilerSupportResult(False, "MODEL_FAMILY_MISMATCH")
        if intent.reference_requirements.get("mode") == "FIRST_FRAME" and not capabilities.supports_first_frame:
            return CompilerSupportResult(False, "FIRST_FRAME_UNSUPPORTED")
        if intent.dialogue.mode == "AUTHORITATIVE" and not capabilities.supports_native_dialogue:
            return CompilerSupportResult(False, "NATIVE_DIALOGUE_UNSUPPORTED")
        if intent.director_duration_seconds <= 0:
            return CompilerSupportResult(False, "DIRECTOR_DURATION_INVALID")
        return CompilerSupportResult(True)

    def compile(self, intent: VideoIntentIR, target: VideoModelCapabilities = H3_CAPABILITIES) -> CompiledVideoRequestIR:
        support = self.supports(intent, target)
        if not support.supported:
            raise ValueError(support.code or "VIDEO_COMPILER_UNSUPPORTED")
        projection = project_provider_duration(intent.director_duration_seconds)
        if projection.status != "PASS" or projection.provider_duration_seconds is None:
            raise ValueError("VIDEO_MODEL_DURATION_UNSUPPORTED")
        if target.min_duration > projection.provider_duration_seconds or target.max_duration < projection.provider_duration_seconds:
            raise ValueError("VIDEO_MODEL_DURATION_UNSUPPORTED")
        speaker_ids = {character.character_id: f"S{index}" for index, character in enumerate(intent.characters, 1)}
        lines = [
            "integrated_multimodal_description:",
            f"Cinematic single-take shot {intent.shot_id}. Preserve scene topology: {intent.scene.get('location') or intent.scene.get('scene_id') or 'the established scene'}.",
            "Characters:",
        ]
        for character in intent.characters:
            lines.append(f"{speaker_ids[character.character_id]}: {character.display_name}; role {character.role}; start state {_natural_state(dict(character.start_state))}.")
        if intent.props:
            lines.append("Props: " + "; ".join(f"{item.get('prop_id') or item.get('id')}: {_natural_state(dict(item))}" for item in intent.props))
        else:
            lines.append("Props: none.")
        lines.append("Performance timeline:")
        for beat in intent.performance_beats:
            actor = str(beat.get("actor") or "character")
            details = [str(beat.get(key)) for key in ("body_action", "hand_action", "head_action", "eye_action", "facial_action", "prop_action", "ending_state") if beat.get(key)]
            lines.append(f"Temporal window [{beat.get('start_time')}–{beat.get('end_time')}]")
            lines.append(f"{beat.get('start_time')}–{beat.get('end_time')}s: {actor} {'; '.join(details)}")
        lines.append("Camera timeline:")
        for beat in intent.camera_beats:
            lines.append(f"{beat.get('start_time')}–{beat.get('end_time')}s: {beat.get('movement_type')} {beat.get('direction')}; target {beat.get('target')}; from {beat.get('start_framing')} to {beat.get('end_framing')}.")
        if intent.dialogue.mode == "AUTHORITATIVE":
            language = _language_label(intent.dialogue.language)
            if not language:
                raise ValueError("UNKNOWN_DIALOGUE_LANGUAGE")
            lines.append("Dialogue:")
            lines.append(f"Authoritative dialogue text (byte exact): {intent.dialogue.authoritative_text}")
            for phrase in intent.dialogue.phrase_windows or ({"start_time": 0.0, "end_time": intent.director_duration_seconds, "text": intent.dialogue.authoritative_text},):
                sid = speaker_ids[intent.dialogue.speaker_character_id or ""]
                lines.append(f"{phrase.get('start_time')}–{phrase.get('end_time')}s: ({sid}) <d>[{language}] {phrase.get('text')}</d>")
            for silent_id in intent.dialogue.silent_character_ids:
                lines.append(f"{speaker_ids[silent_id]} remains silent and does not perform speaking-like lip motion.")
            lines.append("overall_soundscape:\nNatural room tone. Speaker dialogue clear and foregrounded. No additional voices.")
        else:
            lines += ["Dialogue: none.", "完全无对白镜头。", "两位角色全程保持沉默，不得出现明显的对白式张嘴、闭嘴循环。", "All characters remain silent. No dialogue markup block, no speaker dialogue token, and no speaking-like lip motion.", "overall_soundscape:\nN/A"]
        lines.append("non_diegetic_music:\nN/A")
        lines.append(f"Duration: {projection.provider_duration_seconds}s total; director intent {intent.director_duration_seconds:g}s; terminal hold {projection.provider_padding_seconds:g}s.")
        lines.append("Negative constraints: " + "; ".join(intent.negative_constraints) + ".")
        prompt = "\n".join(lines)
        # NONE projection safety: source DirectorDecisionIR remains untouched.
        if intent.dialogue.mode == "NONE" and any(token in prompt.lower() for token in ("lips slightly parted", "mouth opens", "mouth open", "speaking mouth", "嘴唇微张", "嘴部张开")):
            raise ValueError("NO_DIALOGUE_MOUTH_STATE_CONFLICT")
        words = len(re.findall(r"\S+", prompt))
        complexity = PromptComplexityAudit(len(intent.characters), words, len(intent.performance_beats), len(intent.camera_beats), len(intent.dialogue.authoritative_text))
        if words > 3000:
            complexity = PromptComplexityAudit(complexity.characters, words, complexity.performance_beats, complexity.camera_beats, complexity.dialogue_length, True, "COMPILER_PROMPT_COMPLEXITY_BLOCKED")
            raise CompilerPromptComplexityError("COMPILER_PROMPT_COMPLEXITY_BLOCKED")
        references = tuple({"role": str(role), "asset_id": ""} for role in intent.reference_requirements.get("roles") or [])
        audio_mode = "NATIVE_AUDIO_EXPECTED" if intent.dialogue.mode == "AUTHORITATIVE" else "SILENCE_REQUESTED"
        request_basis = {"compiler_id": self.compiler_id, "compiler_version": self.compiler_version, "model_family": self.model_family, "shot_id": intent.shot_id, "source": intent.source_fingerprint, "prompt": prompt, "duration": projection.provider_duration_seconds, "aspect_ratio": "16:9", "reference_mode": intent.reference_requirements.get("mode"), "audio_generation_mode": audio_mode}
        return CompiledVideoRequestIR(self.compiler_id, self.compiler_version, self.model_family, intent.shot_id, intent.source_fingerprint, prompt, int(projection.provider_duration_seconds), "16:9", str(intent.reference_requirements.get("mode") or "FIRST_FRAME"), references, audio_mode, {"supports_native_audio": target.supports_native_audio, "supports_first_frame": target.supports_first_frame}, support.warnings, _sha(prompt), _sha(json.dumps(request_basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))), complexity)
