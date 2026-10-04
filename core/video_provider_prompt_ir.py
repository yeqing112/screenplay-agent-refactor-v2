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
    # Compatibility bridge: all prompt text now comes from VideoIntentIR and
    # the selected model compiler.  The legacy return shape remains for older
    # callers while preventing a second provider prompt renderer.
    from core.video_compilers import default_video_compiler_registry
    from core.video_compilers.minimax_h3 import H3_CAPABILITIES
    from core.video_intent_ir import build_video_intent_ir

    intent = build_video_intent_ir(decision, prop_states=prop_states)
    compiled = default_video_compiler_registry().resolve(compiler_id="minimax-h3").compile(intent, H3_CAPABILITIES)
    dialogue = build_dialogue_contract(decision)
    mouth_projection = project_no_dialogue_mouth_state(decision)
    source = decision.get("source_facts") if isinstance(decision.get("source_facts"), dict) else {}
    blocking = tuple(dict(x) for x in (decision.get("blocking") or []) if isinstance(x, dict))
    props = tuple(dict(x) for x in (prop_states or []) if isinstance(x, dict) and x.get("present"))
    projected_beats = mouth_projection.sanitized_performance_beats if dialogue.dialogue_mode == "NONE" else tuple(dict(x) for x in (decision.get("performance_beats") or []) if isinstance(x, dict))
    projected_ending_state = _sanitize_structure(decision.get("ending_state") or {}) if dialogue.dialogue_mode == "NONE" else (decision.get("ending_state") or {})
    validate_no_dialogue_mouth_contract(compiled.prompt, dialogue)
    return VideoProviderPromptIR(
        intent.shot_id,
        {"scene_id": source.get("scene_id"), "location": source.get("location")},
        blocking,
        props,
        projection.as_dict(),
        dialogue,
        projected_beats,
        tuple(dict(x) for x in (decision.get("camera_beats") or []) if isinstance(x, dict)),
        projected_ending_state,
        terminal_hold_text(projection),
        tuple(intent.negative_constraints),
        compiled.prompt,
        compiled.compiled_prompt_sha256,
    )

    # Kept below only as a source-compatible historical reference during the
    # migration; execution never reaches this renderer.
    shot_id = str(decision.get("shot_id") or "")
    source = decision.get("source_facts") if isinstance(decision.get("source_facts"), dict) else {}
    blocking = tuple(dict(x) for x in (decision.get("blocking") or []) if isinstance(x, dict))
    props = tuple(dict(x) for x in (prop_states or []) if isinstance(x, dict) and x.get("present"))
    dialogue = build_dialogue_contract(decision)
    mouth_projection = project_no_dialogue_mouth_state(decision)
    duration = projection.as_dict()
    hold = terminal_hold_text(projection)
    negatives = ["不得新增人物、道具、事件、摄影事件或场景拓扑变化", "不得文生视频，必须使用输入首帧作为第一帧"]
    if dialogue.dialogue_mode == "NONE":
        negatives += ["禁止对白、台词、旁白、语音、人声、歌声和说话口型", "两位角色全程保持沉默，嘴部自然放松，仅允许呼吸、吞咽或极轻微非语言表情"]
    else:
        negatives += ["只有指定 speaker 在 phrase_windows 内做说话口型", f"{dialogue.silent_characters[0] if dialogue.silent_characters else '其他角色'} 全程不说话，不得产生连续说话口型"]
    lines = [
        f"镜头 {shot_id}。", f"场景：{source.get('location') or source.get('scene_id') or 'E01_SC002'}。保持场景身份和空间拓扑。",
        f"导演时长 {projection.director_duration_seconds:g} 秒；Provider 时长 {projection.provider_duration_seconds} 秒。",
    ]
    if dialogue.dialogue_mode == "NONE":
        lines += ["这是一个完全无对白镜头。", "林晚和陆叔全程保持沉默。", "两人都不得说话，不得出现明显的对白式张嘴、闭嘴循环。", "嘴部保持自然放松；仅允许正常呼吸、吞咽或极轻微非语言表情变化。", "人物仅通过眼神、表情、头部运动和身体动作完成表演。"]
    else:
        lines += [f"对白说话人：{dialogue.speaker}。", f"完整权威对白：{dialogue.authoritative_text}", "对白时间轴："]
        for item in dialogue.phrase_windows:
            lines.append(f"[{item.get('start_time')}–{item.get('end_time')}] {dialogue.speaker}：{item.get('text')}")
        if dialogue.silent_characters:
            lines.append(f"{dialogue.silent_characters[0]}全程无对白，只做倾听、眼神、表情和身体反应。")
    lines.append("起始人物状态：")
    for item in blocking:
        identity = item.get("identity") or item.get("character") or "角色"
        lines.append(_human_state(str(identity), {k: item.get(k) for k in ("position", "body_pose", "weight_distribution", "torso_direction", "head_yaw", "head_pitch", "eye_target", "expression", "left_hand", "right_hand", "prop_contact") if item.get(k) is not None}))
    if props:
        lines.append("起始道具状态：" + "；".join(_human_state(str(x.get("prop_id")), x) for x in props))
    else:
        lines.append("起始道具状态：无剧情道具。")
    lines.append("时间化表演动作：")
    projected_beats = mouth_projection.sanitized_performance_beats if dialogue.dialogue_mode == "NONE" else tuple(dict(x) for x in (decision.get("performance_beats") or []) if isinstance(x, dict))
    for beat in projected_beats:
        if isinstance(beat, dict):
            actor = beat.get("actor") or "角色"
            details = "；".join(f"{key}={beat.get(key)}" for key in ("body_action", "hand_action", "head_action", "eye_action", "facial_action", "prop_action", "ending_state") if beat.get(key))
            lines.append(f"[{beat.get('start_time')}–{beat.get('end_time')}] {actor}：{details}")
    lines.append("时间化摄影动作：")
    for beat in (decision.get("camera_beats") or []):
        if isinstance(beat, dict):
            lines.append(f"[{beat.get('start_time')}–{beat.get('end_time')}] {beat.get('movement_type')}；方向={beat.get('direction')}；速度={beat.get('speed')}；目标={beat.get('target')}；起始构图={beat.get('start_framing')}；结束构图={beat.get('end_framing')}；缓动={beat.get('easing')}")
    projected_ending_state = _sanitize_structure(decision.get("ending_state") or {}) if dialogue.dialogue_mode == "NONE" else (decision.get("ending_state") or {})
    lines.append("最终状态：" + _json(projected_ending_state))
    if hold:
        lines.append(hold)
    lines.append("负向时间约束：" + "；".join(negatives))
    if dialogue.dialogue_mode == "NONE":
        lines.insert(5, "嘴部状态合同：CLOSED_RELAXED_STABLE；嘴唇自然闭合，下颌放松，不产生说话运动。")
    rendered = "\n".join(lines)
    validate_no_dialogue_mouth_contract(rendered, dialogue)
    return VideoProviderPromptIR(shot_id, {"scene_id": source.get("scene_id"), "location": source.get("location")}, blocking, props, duration, dialogue, projected_beats, tuple(dict(x) for x in (decision.get("camera_beats") or []) if isinstance(x, dict)), projected_ending_state, hold, tuple(negatives), rendered, hashlib.sha256(rendered.encode("utf-8")).hexdigest())


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
