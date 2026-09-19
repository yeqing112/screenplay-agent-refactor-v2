"""Script Creative Quality Gate.

Phase A of the production quality closure.  This module is a read-only
professional quality gate that runs *before* a ScriptIR candidate becomes
authority.  It never writes versions, moves pointers, or mutates payloads.

It answers:

    "Is this script a professionally shootable, cuttable, logically sound
    piece of work?"  (as opposed to the Authority Gate which answers
    "is this the current authoritative version?")

Hard errors must block production.  Soft diagnostics are advisory and must
not block by themselves.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

# ---------------------------------------------------------------------------
# Canonical beat taxonomy
# ---------------------------------------------------------------------------
BEAT_TYPES = (
    "SETUP",
    "ACTION",
    "QUESTION",
    "REVEAL",
    "REACTION",
    "DECISION",
    "REVERSAL",
    "ESCALATION",
    "TRANSITION",
    "HOOK",
)

BEAT_TYPE_ALIASES = {
    "setup": "SETUP",
    "establish": "SETUP",
    "action": "ACTION",
    "question": "QUESTION",
    "ask": "QUESTION",
    "reveal": "REVEAL",
    "reaction": "REACTION",
    "react": "REACTION",
    "decision": "DECISION",
    "decide": "DECISION",
    "reversal": "REVERSAL",
    "turn": "REVERSAL",
    "escalation": "ESCALATION",
    "escalate": "ESCALATION",
    "transition": "TRANSITION",
    "cut": "TRANSITION",
    "hook": "HOOK",
    "beat_marker": "SETUP",
}

ASSERTION_MODES = (
    "OBJECTIVE_FACT",
    "CHARACTER_BELIEF",
    "DECEPTION",
    "UNCERTAIN_CLAIM",
)

# Camera-direction phrases that must NOT appear in a reader script.
CAMERA_LEAK_PATTERNS = (
    "镜头",
    "推近",
    "拉远",
    "特写",
    "中景",
    "全景",
    "POV",
    "俯拍",
    "仰拍",
    "摇镜",
    "横移",
    "运镜",
    "机位",
    "画面稳定",
    "镜头稳定",
    "主观视角",
    "缓推",
    "快推",
    "切到",
    "切换到",
    "cut to",
    "CUT TO",
)

# Internal engineering markers that must never leak into a reader script.
INTERNAL_LABEL_PATTERNS = (
    "【视觉证明",
    "【隐藏层",
    "【强钩子",
    "【开场",
    "【冲突引入",
    "【场景结束",
    "【场景开始",
    "【重试要求",
    "beat_id",
    "fact_snapshot",
    "prompt_fingerprint",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def normalize_beat_type(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return "ACTION"
    return BEAT_TYPE_ALIASES.get(raw.lower(), raw.upper() if raw.upper() in BEAT_TYPES else "ACTION")


def _flat_text(script_ir: dict[str, Any]) -> str:
    parts: list[str] = []
    for scene in script_ir.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for beat in scene.get("dramatic_beats") or scene.get("beats") or []:
            if isinstance(beat, dict) and _text(beat.get("event")):
                parts.append(_text(beat["event"]))
        for dialogue in scene.get("dialogues") or []:
            if isinstance(dialogue, dict):
                speaker = _text(dialogue.get("speaker"))
                text = _text(dialogue.get("text") or dialogue.get("content"))
                if text:
                    parts.append(f"{speaker}：{text}")
    return "\n".join(parts)


def _scene_order(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in (script_ir.get("scenes") or []) if isinstance(s, dict)]


def _beats_of(scene: dict[str, Any]) -> list[dict[str, Any]]:
    return [b for b in (scene.get("dramatic_beats") or scene.get("beats") or []) if isinstance(b, dict)]


def _dialogues_of(scene: dict[str, Any]) -> list[dict[str, Any]]:
    return [d for d in (scene.get("dialogues") or []) if isinstance(d, dict)]


def _transitions(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    raw = script_ir.get("scene_transitions") or []
    return [t for t in raw if isinstance(t, dict)]


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "severity": "blocked", "target_layer": "SCRIPT", "message": message, **extra}


def _diagnostic(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "severity": "warning", "target_layer": "SCRIPT", "message": message, **extra}


# ---------------------------------------------------------------------------
# Hard gates
# ---------------------------------------------------------------------------

def _gate_scene_transitions(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    scenes = _scene_order(script_ir)
    transitions = {(_text(t.get("from_scene_id")), _text(t.get("to_scene_id"))): t for t in _transitions(script_ir)}
    for index in range(len(scenes) - 1):
        from_scene = scenes[index]
        to_scene = scenes[index + 1]
        from_id = _text(from_scene.get("scene_id")) or f"SC{index + 1:02d}"
        to_id = _text(to_scene.get("scene_id")) or f"SC{index + 2:02d}"
        transition = transitions.get((from_id, to_id))
        if transition is None:
            errors.append(_error(
                "SCENE_TRANSITION_UNRESOLVED",
                f"场景 {from_id} → {to_id} 之间缺少 SceneTransitionContract，无法证明跳转具有因果。",
                from_scene_id=from_id, to_scene_id=to_id,
            ))
            continue
        if _text(transition.get("status")) not in {"RESOLVED", "resolved"}:
            errors.append(_error(
                "SCENE_TRANSITION_UNRESOLVED",
                f"场景 {from_id} → {to_id} 的转场合同未解析（status={_text(transition.get('status'))}）。",
                from_scene_id=from_id, to_scene_id=to_id,
            ))
        if not _text(transition.get("causal_reason")):
            errors.append(_error(
                "SCENE_TRANSITION_UNRESOLVED",
                f"场景 {from_id} → {to_id} 的转场合同缺少 causal_reason。",
                from_scene_id=from_id, to_scene_id=to_id,
            ))
        if not _text(transition.get("transition_event")):
            errors.append(_error(
                "SCENE_TRANSITION_UNRESOLVED",
                f"场景 {from_id} → {to_id} 的转场合同缺少 transition_event。",
                from_scene_id=from_id, to_scene_id=to_id,
            ))
    return errors


def _gate_character_knowledge(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    """Statements that contradict recorded facts must be marked as belief,
    deception or uncertainty.  Unmarked contradictions are continuity bugs.
    """
    errors: list[dict[str, Any]] = []
    for scene in _scene_order(script_ir):
        scene_id = _text(scene.get("scene_id"))
        for dialogue in _dialogues_of(scene):
            text = _text(dialogue.get("text") or dialogue.get("content"))
            if not text:
                continue
            contradicts = dialogue.get("contradicts_fact_refs")
            has_contradiction_refs = isinstance(contradicts, list) and bool(contradicts)
            assertion_mode = _text(dialogue.get("assertion_mode"))
            if has_contradiction_refs and assertion_mode == "OBJECTIVE_FACT":
                # A statement that contradicts a declared fact cannot itself be
                # an objective fact.  The writer must mark it DECEPTION /
                # UNCERTAIN_CLAIM / CHARACTER_BELIEF.  Defaulting to
                # OBJECTIVE_FACT without an explicit mode is the unmarked
                # contradiction bug.
                errors.append(_error(
                    "CHARACTER_STATEMENT_CONTINUITY_CONFLICT",
                    f"对白引用事实 {contradicts} 但 assertion_mode 仍为默认 OBJECTIVE_FACT，系统无法区分人物撒谎与编剧矛盾。",
                    scene_id=scene_id, dialogue_id=_text(dialogue.get("dialogue_id")), speaker=_text(dialogue.get("speaker")),
                ))
            elif has_contradiction_refs and assertion_mode not in ASSERTION_MODES:
                errors.append(_error(
                    "UNMARKED_FACT_CONTRADICTION",
                    f"对白引用事实 {contradicts} 但未标记 assertion_mode，系统无法区分人物撒谎与编剧矛盾。",
                    scene_id=scene_id, dialogue_id=_text(dialogue.get("dialogue_id")), speaker=_text(dialogue.get("speaker")),
                ))
            if assertion_mode == "DECEPTION":
                if not has_contradiction_refs:
                    # A deception that contradicts nothing declared is still a
                    # statement we cannot verify; keep it soft, not hard.
                    pass
                if not dialogue.get("audience_should_notice"):
                    # Deception that the audience cannot notice is a director
                    # choice, not a hard script error.
                    pass
    return errors


def _gate_character_state_discontinuity(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    """Characters whose declared entry state contradicts their previous
    scene's exit state are a hard discontinuity when both are declared.
    """
    errors: list[dict[str, Any]] = []
    previous_exit: dict[str, str] = {}
    for scene in _scene_order(script_ir):
        scene_id = _text(scene.get("scene_id"))
        state_in = scene.get("state_in") if isinstance(scene.get("state_in"), dict) else {}
        state_out = scene.get("state_out") if isinstance(scene.get("state_out"), dict) else {}
        for character_id, entry_value in state_in.items():
            if character_id in previous_exit and _text(previous_exit[character_id]) and _text(entry_value):
                if _text(previous_exit[character_id]) != _text(entry_value):
                    errors.append(_error(
                        "CHARACTER_STATE_DISCONTINUITY",
                        f"角色 {character_id} 在 {scene_id} 的入场状态 {_text(entry_value)} 与上一场离场状态 {_text(previous_exit[character_id])} 冲突。",
                        character_id=character_id, scene_id=scene_id,
                    ))
        for character_id, exit_value in state_out.items():
            previous_exit[character_id] = _text(exit_value)
    return errors


def _gate_prop_state_conflict(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    """Same prop declared with different states across scenes is a conflict
    unless an explicit transition explains the change.
    """
    errors: list[dict[str, Any]] = []
    prop_states: dict[str, list[tuple[str, str]]] = {}
    for scene in _scene_order(script_ir):
        scene_id = _text(scene.get("scene_id"))
        props = scene.get("props") if isinstance(scene.get("props"), list) else []
        for prop in props:
            if not isinstance(prop, dict):
                continue
            prop_id = _text(prop.get("prop_id"))
            if not prop_id:
                continue
            state = _text(prop.get("state") or prop.get("entry_state"))
            if state:
                prop_states.setdefault(prop_id, []).append((scene_id, state))
    for prop_id, states in prop_states.items():
        distinct = {state for _, state in states}
        if len(distinct) > 1:
            errors.append(_error(
                "PROP_STATE_CONFLICT",
                f"道具 {prop_id} 在不同场景状态冲突：{sorted(distinct)}。",
                prop_id=prop_id, states=sorted(distinct),
            ))
    return errors


def _gate_timeline_conflict(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    transitions = _transitions(script_ir)
    scenes = _scene_order(script_ir)
    for transition in transitions:
        time_relation = _text(transition.get("time_relation"))
        if time_relation and time_relation not in {"before", "same_time", "later", "same_time_block", "flashback", "overlap"}:
            errors.append(_error(
                "TIMELINE_CONFLICT",
                f"转场 {_text(transition.get('from_scene_id'))} → {_text(transition.get('to_scene_id'))} 使用非法 time_relation：{time_relation}。",
            ))
    # Detect obviously incompatible scene headings (e.g. 日 → 夜 reversed).
    time_tokens = {
        "凌晨": 0, "夜": 1, "深夜": 1, "傍晚": 2, "黄昏": 2, "上午": 3, "日": 3, "白天": 3, "下午": 4, "正午": 4,
    }
    for index in range(len(scenes) - 1):
        from_time = _text(scenes[index].get("time_of_day"))
        to_time = _text(scenes[index + 1].get("time_of_day"))
        if from_time and to_time:
            from_rank = next((v for k, v in time_tokens.items() if k in from_time), None)
            to_rank = next((v for k, v in time_tokens.items() if k in to_time), None)
            if from_rank is not None and to_rank is not None and from_rank > to_rank:
                # Only flag when both are explicit and the time went backward
                # without a transition contract declaring a flashback.
                transition = next((t for t in transitions if _text(t.get("from_scene_id")) == _text(scenes[index].get("scene_id"))), None)
                if transition and _text(transition.get("time_relation")) != "flashback":
                    errors.append(_error(
                        "TIMELINE_CONFLICT",
                        f"场景时间从 {from_time} 倒退到 {to_time}，且未声明 flashback。",
                        from_scene_id=_text(scenes[index].get("scene_id")), to_scene_id=_text(scenes[index + 1].get("scene_id")),
                    ))
    return errors


def _gate_critical_beat(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    """Production script requires structured dramatic beats and a closing
    hook.  A scene without at least one critical beat is under-specified.
    """
    errors: list[dict[str, Any]] = []
    scenes = _scene_order(script_ir)
    if not scenes:
        return [_error("CRITICAL_BEAT_MISSING", "剧本没有场景，无法验收。")]
    for scene in scenes:
        scene_id = _text(scene.get("scene_id")) or _text(scene.get("name"))
        beats = _beats_of(scene)
        if not beats:
            errors.append(_error("CRITICAL_BEAT_MISSING", f"场景 {scene_id} 没有任何戏剧节拍。", scene_id=scene_id))
            continue
        critical = [b for b in beats if _text(b.get("importance")) == "critical" or _text(b.get("requires_reaction")) == "true"]
        if not critical:
            errors.append(_error(
                "CRITICAL_BEAT_MISSING",
                f"场景 {scene_id} 没有任何 critical 节拍（importance=critical 或 requires_reaction）。",
                scene_id=scene_id,
            ))
    # The episode must end with a hook / escalation beat.
    last_scene = scenes[-1]
    last_beats = _beats_of(last_scene)
    last_type = normalize_beat_type(last_beats[-1].get("type")) if last_beats else ""
    if last_type not in {"HOOK", "ESCALATION", "REVERSAL", "TRANSITION"}:
        errors.append(_error(
            "CRITICAL_BEAT_MISSING",
            f"本集结尾节拍类型为 {last_type or '未知'}，缺少 HOOK/ESCALATION/REVERSAL 作为集尾钩子。",
        ))
    return errors


def run_hard_gates(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    errors.extend(_gate_scene_transitions(script_ir))
    errors.extend(_gate_character_knowledge(script_ir))
    errors.extend(_gate_character_state_discontinuity(script_ir))
    errors.extend(_gate_prop_state_conflict(script_ir))
    errors.extend(_gate_timeline_conflict(script_ir))
    errors.extend(_gate_critical_beat(script_ir))
    return errors


# ---------------------------------------------------------------------------
# Soft diagnostics
# ---------------------------------------------------------------------------

def _soft_repetitive_interrogation(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for scene in _scene_order(script_ir):
        scene_id = _text(scene.get("scene_id"))
        question_texts: list[str] = []
        for dialogue in _dialogues_of(scene):
            text = _text(dialogue.get("text") or dialogue.get("content"))
            if text and ("？" in text or "?" in text):
                question_texts.append(text)
        counter = Counter()
        for text in question_texts:
            for keyword in ("伞", "什么", "谁", "怎么", "哪"):
                if keyword in text:
                    counter[keyword] += 1
        repeated = {kw: count for kw, count in counter.items() if count >= 4}
        if repeated:
            diagnostics.append(_diagnostic(
                "REPETITIVE_INTERROGATION",
                f"场景 {scene_id} 对同一关键词反复质问：{repeated}。",
                scene_id=scene_id, repeated=repeated,
            ))
    return diagnostics


def _soft_exposition_heavy_dialogue(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for scene in _scene_order(script_ir):
        scene_id = _text(scene.get("scene_id"))
        for dialogue in _dialogues_of(scene):
            text = _text(dialogue.get("text") or dialogue.get("content"))
            if len(text) > 80:
                diagnostics.append(_diagnostic(
                    "EXPOSITION_HEAVY_DIALOGUE",
                    f"场景 {scene_id} 出现超长对白（{len(text)} 字），注意避免解说式表达。",
                    scene_id=scene_id, dialogue_id=_text(dialogue.get("dialogue_id")), length=len(text),
                ))
    return diagnostics


def _soft_low_escalation(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    total_beats = 0
    escalation_beats = 0
    for scene in _scene_order(script_ir):
        for beat in _beats_of(scene):
            total_beats += 1
            if normalize_beat_type(beat.get("type")) in {"ESCALATION", "REVERSAL", "REVEAL", "DECISION"}:
                escalation_beats += 1
    if total_beats and (escalation_beats / total_beats) < 0.25:
        diagnostics.append(_diagnostic(
            "LOW_ESCALATION",
            f"全剧戏剧性节拍（ESCALATION/REVERSAL/REVEAL/DECISION）占比过低：{escalation_beats}/{total_beats}。",
            escalation_beats=escalation_beats, total_beats=total_beats,
        ))
    return diagnostics


def _soft_overdirected_script(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    """Reader-script content (scene action lines) must not contain camera
    direction or internal engineering labels.
    """
    diagnostics: list[dict[str, Any]] = []
    for scene in _scene_order(script_ir):
        scene_id = _text(scene.get("scene_id"))
        action_lines: list[str] = []
        for beat in _beats_of(scene):
            event = _text(beat.get("event"))
            if event:
                action_lines.append(event)
        for action in scene.get("actions") or []:
            if _text(action):
                action_lines.append(_text(action))
        for line in action_lines:
            leaked_camera = [pattern for pattern in CAMERA_LEAK_PATTERNS if pattern in line]
            leaked_labels = [pattern for pattern in INTERNAL_LABEL_PATTERNS if pattern in line]
            if leaked_camera:
                diagnostics.append(_diagnostic(
                    "OVERDIRECTED_SCRIPT",
                    f"场景 {scene_id} 动作行含摄影机/导演标记：{leaked_camera}。读者剧本不应指定摄影。",
                    scene_id=scene_id, leaked=leaked_camera,
                ))
            if leaked_labels:
                diagnostics.append(_diagnostic(
                    "INTERNAL_LABEL_LEAK",
                    f"场景 {scene_id} 动作行含内部工程标记：{leaked_labels}。",
                    scene_id=scene_id, leaked=leaked_labels,
                ))
    return diagnostics


def run_soft_diagnostics(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    diagnostics.extend(_soft_repetitive_interrogation(script_ir))
    diagnostics.extend(_soft_exposition_heavy_dialogue(script_ir))
    diagnostics.extend(_soft_low_escalation(script_ir))
    diagnostics.extend(_soft_overdirected_script(script_ir))
    return diagnostics


# ---------------------------------------------------------------------------
# Top-level gate
# ---------------------------------------------------------------------------

def run_script_creative_quality_gate(script_ir: dict[str, Any]) -> dict[str, Any]:
    """Run the full Script Creative Quality Gate.

    Returns a read-only report.  Hard errors (severity=blocked) must fail the
    production gate; soft diagnostics are advisory.
    """
    hard_errors = run_hard_gates(script_ir)
    soft_diagnostics = run_soft_diagnostics(script_ir)
    status = "PRODUCTION_QUALIFIED" if not hard_errors else "CREATIVE_QUALITY_BLOCKED"
    scenes = _scene_order(script_ir)
    beats = sum(len(_beats_of(scene)) for scene in scenes)
    dialogues = sum(len(_dialogues_of(scene)) for scene in scenes)
    return {
        "status": status,
        "qualified": not hard_errors,
        "hard_errors": hard_errors,
        "soft_diagnostics": soft_diagnostics,
        "metrics": {
            "scene_count": len(scenes),
            "beat_count": beats,
            "dialogue_count": dialogues,
            "transition_count": len(_transitions(script_ir)),
        },
    }


def detect_negative_fixture_issues(script_ir: dict[str, Any]) -> dict[str, Any]:
    """Run all gates plus explicit camera/label leak detection for the
    negative fixture.  Returns issues the old broken version must trip.
    """
    report = run_script_creative_quality_gate(script_ir)
    leaked_camera = []
    leaked_labels = []
    for scene in _scene_order(script_ir):
        for beat in _beats_of(scene):
            event = _text(beat.get("event"))
            if event:
                for pattern in CAMERA_LEAK_PATTERNS:
                    if pattern in event:
                        leaked_camera.append(pattern)
                for pattern in INTERNAL_LABEL_PATTERNS:
                    if pattern in event:
                        leaked_labels.append(pattern)
    expected = [
        "SCENE_TRANSITION_UNRESOLVED",
        "CHARACTER_STATEMENT_CONTINUITY_CONFLICT",
        "DIRECTOR_TREATMENT_PLACEHOLDER",
        "BLOCKING_NOT_MATERIALIZED",
        "SHOT_COVERAGE_INCOMPLETE",
        "NON_ATOMIC_SHOT",
        "SHOT_RUNTIME_MISMATCH",
        "CAMERA_MOVEMENT_SEMANTIC_CONFLICT",
    ]
    detected = sorted({item["code"] for item in report["hard_errors"]})
    return {
        "script_gate_status": report["status"],
        "detected_script_issues": detected,
        "leaked_camera_patterns": sorted(set(leaked_camera)),
        "leaked_internal_labels": sorted(set(leaked_labels)),
        "expected_negative_signals": expected,
    }
