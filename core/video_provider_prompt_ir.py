"""Canonical VideoProviderPromptIR and provider truth-chain helpers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping

from core.shot_readiness import ProviderDurationProjection, ShotPropState, terminal_hold_text


POSITIVE_DIALOGUE_LEAK_TOKENS = (
    "按照对白执行", "对白时间", "说台词", "lip sync", "对白口型", "连续说话口型",
)

NO_DIALOGUE_MOUTH_CONFLICT_TOKENS = (
    "lips slightly parted", "mouth opens", "mouth open", "speaking mouth",
    "mouth movement", "inviting mouth shape", "嘴唇微张", "嘴部张开", "明显张嘴",
    "说话口型", "嘴部运动", "开口说话",
)


class NoDialogueMouthStateConflict(ValueError):
    """Raised when a NONE dialogue projection still contains a positive mouth beat."""


@dataclass(frozen=True)
class NoDialogueMouthStateProjection:
    mouth_state_contract: str
    sanitized_performance_beats: tuple[Mapping[str, Any], ...]
    conflict_tokens: tuple[str, ...]
    source_conflict_count: int
    prompt_conflict_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "mouth_state_contract": self.mouth_state_contract,
            "sanitized_performance_beats": [dict(x) for x in self.sanitized_performance_beats],
            "conflict_tokens": list(self.conflict_tokens),
            "source_conflict_count": self.source_conflict_count,
            "prompt_conflict_count": self.prompt_conflict_count,
        }


@dataclass(frozen=True)
class DialogueContract:
    dialogue_mode: str
    speaker: str | None
    authoritative_text: str
    phrase_windows: tuple[dict[str, Any], ...]
    silent_characters: tuple[str, ...]
    visual_lipsync_required: bool
    audio_generation_allowed: bool
    mouth_motion_outside_dialogue_allowed: bool
    mouth_state_contract: str = "DIALOGUE_TIMED"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"phrase_windows": [dict(x) for x in self.phrase_windows], "silent_characters": list(self.silent_characters)}


@dataclass(frozen=True)
class VideoProviderPromptIR:
    shot_id: str
    scene_state: Mapping[str, Any]
    character_start_states: tuple[Mapping[str, Any], ...]
    prop_start_states: tuple[Mapping[str, Any], ...]
    duration_projection: Mapping[str, Any]
    dialogue_contract: DialogueContract
    performance_beats: tuple[Mapping[str, Any], ...]
    camera_beats: tuple[Mapping[str, Any], ...]
    ending_state: Mapping[str, Any]
    terminal_hold: str
    negative_temporal_constraints: tuple[str, ...]
    rendered_prompt: str
    prompt_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "scene_state": dict(self.scene_state),
            "character_start_states": [dict(x) for x in self.character_start_states],
            "prop_start_states": [dict(x) for x in self.prop_start_states],
            "duration_projection": dict(self.duration_projection),
            "dialogue_contract": self.dialogue_contract.as_dict(),
            "performance_beats": [dict(x) for x in self.performance_beats],
            "camera_beats": [dict(x) for x in self.camera_beats],
            "ending_state": dict(self.ending_state),
            "terminal_hold": self.terminal_hold,
            "negative_temporal_constraints": list(self.negative_temporal_constraints),
            "rendered_prompt": self.rendered_prompt,
            "prompt_sha256": self.prompt_sha256,
        }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _human_state(label: str, value: Any) -> str:
    if isinstance(value, dict):
        return f"{label}：" + "；".join(f"{k}={v}" for k, v in value.items())
    return f"{label}：{value}"


def build_dialogue_contract(decision: Mapping[str, Any]) -> DialogueContract:
    characters = tuple(str(x) for x in (decision.get("source_facts", {}).get("character_ids") or []))
    beats = [x for x in (decision.get("dialogue_beats") or []) if isinstance(x, dict)]
    if not beats or not str(decision.get("source_facts", {}).get("dialogue") or "").strip():
        return DialogueContract("NONE", None, "", (), characters, False, False, False, "CLOSED_RELAXED_STABLE")
    first = beats[0]
    speaker = str(first.get("speaker") or "") or None
    silent = tuple(x for x in characters if x != speaker)
    return DialogueContract(
        "AUTHORITATIVE",
        speaker,
        str(first.get("authoritative_text") or decision.get("source_facts", {}).get("dialogue") or ""),
        tuple(dict(x) for x in (first.get("phrase_windows") or [])),
        silent,
        True,
        False,
        False,
        "DIALOGUE_TIMED",
    )


def _replace_mouth_language(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    replacements = (
        ("lips slightly parted", "lips gently closed"),
        ("mouth starts open", "mouth starts gently closed"),
        ("mouth opens", "mouth remains gently closed"),
        ("mouth open", "mouth gently closed"),
        ("speaking mouth", "relaxed non-speaking mouth"),
        ("mouth movement", "no speaking movement"),
        ("inviting mouth shape", "relaxed closed mouth shape"),
        ("嘴唇微张", "嘴唇自然闭合"),
        ("嘴部张开", "嘴部自然闭合"),
        ("明显张嘴", "嘴部自然闭合"),
        ("说话口型", "非说话口型"),
        ("嘴部运动", "嘴部保持稳定"),
        ("开口说话", "保持闭嘴静止"),
    )
    result = value
    for source, target in replacements:
        result = result.replace(source, target)
    return result


def _sanitize_structure(value: Any) -> Any:
    if isinstance(value, str):
        return _replace_mouth_language(value)
    if isinstance(value, list):
        return [_sanitize_structure(x) for x in value]
    if isinstance(value, dict):
        return {key: _sanitize_structure(item) for key, item in value.items()}
    return value


def _contains_positive_mouth_language(value: Any) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    return tuple(token for token in NO_DIALOGUE_MOUTH_CONFLICT_TOKENS if token in value)


def project_no_dialogue_mouth_state(decision: Mapping[str, Any]) -> NoDialogueMouthStateProjection:
    """Project NONE dialogue beats without mutating DirectorDecisionIR."""
    contract = build_dialogue_contract(decision)
    beats = tuple(dict(x) for x in (decision.get("performance_beats") or []) if isinstance(x, dict))
    if contract.dialogue_mode != "NONE":
        return NoDialogueMouthStateProjection("DIALOGUE_TIMED", beats, (), 0, 0)
    source_tokens: list[str] = []
    sanitized: list[dict[str, Any]] = []
    for beat in beats:
        item = {}
        for key, value in beat.items():
            if isinstance(value, str):
                source_tokens.extend(_contains_positive_mouth_language(value))
                item[key] = _replace_mouth_language(value)
            else:
                item[key] = value
        sanitized.append(item)
    return NoDialogueMouthStateProjection(
        "CLOSED_RELAXED_STABLE",
        tuple(sanitized),
        tuple(dict.fromkeys(source_tokens)),
        len(tuple(dict.fromkeys(source_tokens))),
        0,
    )


def find_no_dialogue_mouth_conflicts(prompt: str) -> tuple[str, ...]:
    """Find positive mouth descriptions while ignoring explicit negative constraints."""
    tokens: list[str] = []
    for line in str(prompt or "").splitlines():
        if any(marker in line for marker in ("禁止", "不得", "仅允许", "不产生")):
            continue
        tokens.extend(_contains_positive_mouth_language(line))
    return tuple(dict.fromkeys(tokens))


def validate_no_dialogue_mouth_contract(prompt: str, dialogue_contract: DialogueContract) -> dict[str, Any]:
    conflicts = find_no_dialogue_mouth_conflicts(prompt) if dialogue_contract.dialogue_mode == "NONE" else ()
    result = {
        "status": "PASS" if not conflicts else "NO_DIALOGUE_MOUTH_STATE_CONFLICT",
        "dialogue_mode": dialogue_contract.dialogue_mode,
        "mouth_state_contract": dialogue_contract.mouth_state_contract,
        "prompt_conflict_count": len(conflicts),
        "conflict_tokens": list(conflicts),
    }
    if conflicts:
        raise NoDialogueMouthStateConflict(json.dumps(result, ensure_ascii=False))
    return result


def build_video_provider_prompt_ir(decision: Mapping[str, Any], projection: ProviderDurationProjection, prop_states: list[Mapping[str, Any]] | None = None) -> VideoProviderPromptIR:
    """DEPRECATED_COMPATIBILITY_BRIDGE; production runtime must use a persisted profile."""
    from core.video_compilers import default_video_compiler_registry
    from core.video_intent_ir import build_video_intent_ir
    from core.video_compilers.minimax_h3 import H3_CAPABILITIES
    intent = build_video_intent_ir(decision, prop_states=prop_states)
    compiled = default_video_compiler_registry().resolve(compiler_id='minimax-h3').compile(intent, H3_CAPABILITIES)
    dialogue = build_dialogue_contract(decision)
    mouth_projection = project_no_dialogue_mouth_state(decision)
    source = decision.get('source_facts') if isinstance(decision.get('source_facts'), dict) else {}
    blocking = tuple(dict(x) for x in (decision.get('blocking') or []) if isinstance(x, dict))
    props = tuple(dict(x) for x in (intent.props or ()))
    projected_beats = mouth_projection.sanitized_performance_beats if dialogue.dialogue_mode == 'NONE' else tuple(dict(x) for x in (decision.get('performance_beats') or []) if isinstance(x, dict))
    projected_ending_state = _sanitize_structure(decision.get('ending_state') or {}) if dialogue.dialogue_mode == 'NONE' else (decision.get('ending_state') or {})
    validate_no_dialogue_mouth_contract(compiled.prompt, dialogue)
    return VideoProviderPromptIR(intent.shot_id, {'scene_id': source.get('scene_id'), 'location': source.get('location')}, blocking, props, projection.as_dict(), dialogue, projected_beats, tuple(dict(x) for x in (decision.get('camera_beats') or []) if isinstance(x, dict)), projected_ending_state, terminal_hold_text(projection), tuple(intent.negative_constraints), compiled.prompt, compiled.compiled_prompt_sha256)

def build_prompt_truth_chain(canonical_prompt: str, submission_prompt: str, provider_recorded_prompt: str | None) -> dict[str, Any]:
    def digest(value: str | None) -> str:
        return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()
    canonical_sha, submission_sha, provider_sha = digest(canonical_prompt), digest(submission_prompt), digest(provider_recorded_prompt)
    return {"canonical_prompt_sha256": canonical_sha, "submission_prompt_sha256": submission_sha, "provider_recorded_prompt_sha256": provider_sha, "canonical_equals_submission": canonical_sha == submission_sha, "submission_equals_provider": bool(provider_recorded_prompt is not None and submission_sha == provider_sha), "status": "PASS" if canonical_sha == submission_sha and provider_recorded_prompt is not None and submission_sha == provider_sha else "VIDEO_PROMPT_TRUTH_CHAIN_BROKEN"}


def extract_provider_truth(provider_response: Mapping[str, Any]) -> dict[str, Any]:
    properties = provider_response.get("properties") if isinstance(provider_response, Mapping) else None
    if not isinstance(properties, Mapping) and isinstance(provider_response.get("data"), Mapping):
        properties = provider_response["data"].get("properties")
    properties = properties if isinstance(properties, Mapping) else {}
    raw_input = properties.get("input")
    if isinstance(raw_input, Mapping):
        raw_input = raw_input.get("prompt") or raw_input.get("text") or ""
    return {"properties_input": str(raw_input or ""), "origin_model_name": provider_response.get("origin_model_name") or properties.get("origin_model_name"), "upstream_model_name": provider_response.get("upstream_model_name") or properties.get("upstream_model_name"), "reported_completion_model": provider_response.get("model") or provider_response.get("completion_model") or provider_response.get("data", {}).get("model") if isinstance(provider_response.get("data"), Mapping) else provider_response.get("model")}
