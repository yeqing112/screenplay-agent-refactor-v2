"""Deterministic MiniMax H3 compiler with single-emission dialogue realism."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from core.shot_readiness import project_video_model_duration
from core.video_dialogue_coverage import audit_dialogue_phrase_coverage, audit_provider_dialogue_occurrences
from core.video_intent_ir import VideoIntentIR
from core.video_intent_semantic_consistency import audit_video_intent_semantics
from .base import CompiledVideoRequestIR, CompilerSupportResult, PromptComplexityAudit, VideoModelCapabilities

H3_CAPABILITIES = VideoModelCapabilities(
    model_family="minimax-h3", supports_text_to_video=False, supports_first_frame=True,
    supports_reference_images=True, supports_native_dialogue=True, supports_native_audio=True,
    supports_first_last_frame=False, min_duration=5, max_duration=15,
    allowed_aspect_ratios=("16:9", "9:16"), max_reference_images=8,
)


class CompilerPromptComplexityError(ValueError):
    pass


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _natural_state(state: dict[str, Any]) -> str:
    ignored = {"identity", "reference_identity", "screen_x", "depth_zone", "authority_fingerprint"}
    forbidden = ("mouth", "lips", "bag", "handbag", "shoulder bag", "crossbody", "apple", "包", "嘴", "唇")
    parts = []
    for key, value in state.items():
        if key in ignored or value in (None, ""):
            continue
        text = str(value)
        if any(token in f"{key} {text}".lower() for token in forbidden):
            continue
        parts.append(f"{key.replace('_', ' ')} {text}")
    return "; ".join(parts)


def _language_label(language: str | None) -> str:
    return {"zh-CN": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean"}.get(str(language or ""), "")


def _number(value: Any) -> float:
    return float(value or 0.0)


def _boundaries(intent: VideoIntentIR, terminal: float) -> tuple[float, ...]:
    values = {0.0, float(intent.director_duration_seconds), float(terminal)}
    for collection in (intent.performance_beats, intent.camera_beats, intent.dialogue.phrase_windows):
        for beat in collection:
            values.add(_number(beat.get("start_time")))
            values.add(_number(beat.get("end_time")))
    return tuple(sorted(x for x in values if 0 <= x <= terminal))


def _active(collection: Iterable[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    return [dict(x) for x in collection if _number(x.get("start_time")) < end and _number(x.get("end_time")) > start]


def _clean_detail(value: Any) -> str:
    text = str(value or "")
    if re.search(r"mouth|lips|speaking|嘴|唇", text, flags=re.IGNORECASE):
        return ""
    return text.replace("approximately ", "about ").strip()


def _actor_label(intent: VideoIntentIR, actor: str) -> str:
    for character in intent.characters:
        if character.character_id == actor:
            return character.display_name or actor
    return actor or "the character"


def _primary_and_micro(intent: VideoIntentIR, start: float, end: float) -> tuple[str, list[str]]:
    beats = _active(intent.performance_beats, start, end)
    if not beats:
        return "maintains the established pose", []
    primary = _clean_detail(beats[0].get("body_action")) or "maintains the established pose"
    micros: list[str] = []
    for key in ("hand_action", "eye_action", "facial_action"):
        detail = _clean_detail(beats[0].get(key))
        if detail and detail not in micros:
            micros.append(detail)
    return primary, micros[:3]


def _camera_line(beat: dict[str, Any] | None, index: int) -> tuple[str, int]:
    if not beat:
        return "The restrained handheld framing holds with barely perceptible micro-drift.", 1
    movement = str(beat.get("movement_type") or "holds")
    direction = str(beat.get("direction") or "")
    target = str(beat.get("target") or "the two characters")
    primary = f"The camera uses a {movement} toward {target}"
    if direction and direction != "none":
        primary += f", {direction}"
    primary += "."
    modifiers = ["barely perceptible micro-drift"]
    if index % 3 == 1:
        modifiers.append("a tiny corrective adjustment follows with subtle reaction lag")
    elif index % 3 == 2:
        modifiers.append("the movement eases into a natural settling")
    else:
        modifiers.append("operator breathing remains subtle")
    return primary + " " + "; ".join(modifiers) + ".", len(modifiers)


def _listener_line(intent: VideoIntentIR, index: int) -> str:
    listeners = [x for x in intent.characters if x.role == "listener"]
    if not listeners:
        return ""
    listener = _actor_label(intent, listeners[0].character_id)
    variants = (
        f"{listener} remains silent and does not react immediately; after a brief 0.2–0.6 second hesitation, the gaze dips before returning to the speaker.",
        f"{listener} stays quiet, with a small breath and a slight shoulder settling before attention returns to the speaker.",
        f"{listener} remains guarded but receptive; a restrained weight shift and a slow blink arrive after the speaker's cue.",
    )
    return variants[index % len(variants)]


class MiniMaxH3Compiler:
    compiler_id = "minimax-h3"
    compiler_version = "2-dialogue-realism"
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
        semantic = audit_video_intent_semantics(intent)
        if semantic.status != "PASS":
            return CompilerSupportResult(False, semantic.conflicts[0] if semantic.conflicts else "VIDEO_INTENT_SEMANTIC_CONSISTENCY_FAILED")
        return CompilerSupportResult(True)

    def compile(self, intent: VideoIntentIR, target: VideoModelCapabilities = H3_CAPABILITIES) -> CompiledVideoRequestIR:
        support = self.supports(intent, target)
        if not support.supported:
            raise ValueError(support.code or "VIDEO_COMPILER_UNSUPPORTED")
        projection = project_video_model_duration(intent.director_duration_seconds)
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
        lines.append("Props: none." if not intent.props else "Props: " + "; ".join(f"{x.get('prop_id') or x.get('id')}: {_natural_state(dict(x))}" for x in intent.props))
        dialogue_count = primary_count = micro_count = camera_modifier_count = 0
        if intent.dialogue.mode == "AUTHORITATIVE":
            language = _language_label(intent.dialogue.language)
            if not language:
                raise ValueError("UNKNOWN_DIALOGUE_LANGUAGE")
            audit_dialogue_phrase_coverage(intent.dialogue.authoritative_text, intent.dialogue.phrase_windows)
            lines.extend([
                "Performance direction: grounded human acting; Lu Shu is concerned, caring, slightly anxious and gentle without melodrama; Lin Wan is tired, guarded, slightly hesitant and quietly receptive.",
                "Realism direction: subtle breathing, micro-expressions, responsive gaze, natural weight shift, occasional secondary motion and imperfect gestures; keep performance intensity restrained.",
                "Emotional arc: concern and guardedness gradually soften into a warmer, reassuring exchange without overt sentimentality.",
                "H3 temporal event stream:",
            ])
            terminal = float(projection.provider_duration_seconds)
            boundaries = _boundaries(intent, terminal)
            for index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
                if end <= start:
                    continue
                if start >= intent.director_duration_seconds:
                    lines.append(f"{start:g}–{end:g}s: Final pose, gaze, expression and framing settle naturally. No new dialogue, mouth articulation, body action, prop interaction or camera event; only subtle breathing and natural stillness remain.")
                    continue
                primary, micros = _primary_and_micro(intent, start, end)
                active_perf = _active(intent.performance_beats, start, end)
                actor = _actor_label(intent, str(active_perf[0].get("actor")) if active_perf else "")
                primary_count += 1
                micro_count += len(micros)
                sentence = f"{start:g}–{end:g}s: {actor} {primary}."
                if micros:
                    sentence += " " + " ".join(micros) + "."
                listener = _listener_line(intent, index)
                if listener:
                    sentence += " " + listener
                camera = _active(intent.camera_beats, start, end)
                camera_text, modifiers = _camera_line(camera[0] if camera else None, index)
                camera_modifier_count += modifiers
                sentence += " " + camera_text
                phrase = next((dict(x) for x in intent.dialogue.phrase_windows if abs(_number(x.get("start_time")) - start) < 1e-6), None)
                if phrase:
                    sid = speaker_ids[intent.dialogue.speaker_character_id or ""]
                    sentence += f" ({sid}) <d>[{language}] {phrase.get('text')}</d>"
                    dialogue_count += 1
                lines.append(sentence)
            lines.extend(["overall_soundscape:", "Quiet natural indoor room tone.", "The authorized speaker's Mandarin dialogue is clear and foregrounded.", "No additional voices.", "No invented dialogue."])
            boundaries_count = len(boundaries) - 1
        else:
            lines += ["Performance direction: grounded natural movement with restrained intensity.", "H3 temporal event stream:", f"0–{intent.director_duration_seconds:g}s: All characters remain silent and maintain the established scene without speaking-like motion.", "overall_soundscape:\nN/A"]
            boundaries_count = 1
        lines += [
            "non_diegetic_music:\nN/A",
            f"Duration: {projection.provider_duration_seconds}s total; director intent {intent.director_duration_seconds:g}s; terminal hold {projection.provider_padding_seconds:g}s.",
            "Negative constraints: no additional characters; no unauthorized props; preserve scene topology; Lin Wan carries no handbag, no shoulder bag, no crossbody bag, and no bag strap is visible; both hands remain free of story props.",
        ]
        prompt = "\n".join(lines)
        if intent.dialogue.mode == "AUTHORITATIVE":
            occurrence = audit_provider_dialogue_occurrences(prompt, intent.dialogue.authoritative_text, intent.dialogue.phrase_windows)
        else:
            occurrence = {"phrase_occurrences": [], "plain_full_authoritative_occurrence": 0, "d_block_count": 0, "status": "PASS", "errors": []}
        words = len(re.findall(r"\S+", prompt))
        complexity = PromptComplexityAudit(len(intent.characters), words, len(intent.performance_beats), len(intent.camera_beats), len(intent.dialogue.authoritative_text), False, None, boundaries_count, primary_count, micro_count, camera_modifier_count, occurrence["d_block_count"])
        if words > 3000:
            raise CompilerPromptComplexityError("COMPILER_PROMPT_COMPLEXITY_BLOCKED")
        references = tuple(dict(item) for item in (intent.reference_requirements.get("bindings") or []) if isinstance(item, dict))
        if not references:
            references = tuple({"role": str(role), "asset_id": "", "authority_fingerprint": "", "media_sha256": ""} for role in intent.reference_requirements.get("roles") or [])
        audio_mode = "NATIVE_AUDIO_EXPECTED" if intent.audio_intent.dialogue_required and target.supports_native_dialogue and target.supports_native_audio else "SILENCE_REQUESTED"
        request_basis = {"compiler_id": self.compiler_id, "compiler_version": self.compiler_version, "model_family": self.model_family, "shot_id": intent.shot_id, "source": intent.source_fingerprint, "prompt": prompt, "duration": projection.provider_duration_seconds, "aspect_ratio": "16:9", "reference_mode": intent.reference_requirements.get("mode"), "audio_generation_mode": audio_mode}
        return CompiledVideoRequestIR(self.compiler_id, self.compiler_version, self.model_family, intent.shot_id, intent.source_fingerprint, prompt, int(projection.provider_duration_seconds), "16:9", str(intent.reference_requirements.get("mode") or "FIRST_FRAME"), references, audio_mode, {"supports_native_audio": target.supports_native_audio, "supports_first_frame": target.supports_first_frame, "dialogue_occurrence_audit": occurrence}, support.warnings, _sha(prompt), _sha(json.dumps(request_basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))), complexity)
