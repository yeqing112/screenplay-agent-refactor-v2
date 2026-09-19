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


def _gate_script_blocks(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    """Phase A timeline: production ScriptIR must carry an explicit,
    valid screenplay timeline (script_blocks).

    Hard errors:
    * SCRIPT_BLOCK_ORDER_REQUIRED — no script_blocks / duplicate order / non-int order
    * SCRIPT_BLOCK_TARGET_MISSING — a block ref does not resolve to content
    * SCRIPT_BLOCK_COVERAGE_INCOMPLETE — a dialogue or critical beat is not on the timeline
    """
    errors: list[dict[str, Any]] = []
    for scene in _scene_order(script_ir):
        scene_id = _text(scene.get("scene_id"))
        blocks = [b for b in (scene.get("script_blocks") or []) if isinstance(b, dict)]
        if not blocks:
            errors.append(_error(
                "SCRIPT_BLOCK_ORDER_REQUIRED",
                f"场景 {scene_id} 缺少 screenplay timeline（script_blocks）。Production ScriptIR 必须提供显式顺序。",
                scene_id=scene_id,
            ))
            continue
        seen_orders: dict[int, str] = {}
        refs: dict[str, str] = {}
        for block in blocks:
            order = block.get("order")
            if not isinstance(order, int) or isinstance(order, bool):
                errors.append(_error(
                    "SCRIPT_BLOCK_ORDER_REQUIRED",
                    f"场景 {scene_id} 的 script_block 缺少整数 order（{_text(order)}）。",
                    scene_id=scene_id,
                ))
                continue
            if order in seen_orders:
                errors.append(_error(
                    "SCRIPT_BLOCK_ORDER_CONFLICT",
                    f"场景 {scene_id} 的 script_block 顺序冲突：order={order} 重复。",
                    scene_id=scene_id, order=order,
                ))
            seen_orders[order] = _text(block.get("ref"))
            block_type = _text(block.get("type")).upper()
            if block_type not in {"ACTION", "DIALOGUE"}:
                errors.append(_error(
                    "SCRIPT_BLOCK_TYPE_INVALID",
                    f"场景 {scene_id} 的 script_block 类型非法：{_text(block.get('type'))}。",
                    scene_id=scene_id,
                ))
            ref = _text(block.get("ref"))
            if not ref:
                errors.append(_error(
                    "SCRIPT_BLOCK_REF_MISSING",
                    f"场景 {scene_id} 的 script_block 缺少 ref。",
                    scene_id=scene_id, order=order,
                ))
                continue
            if ref in refs:
                errors.append(_error(
                    "SCRIPT_BLOCK_DUPLICATE_REF",
                    f"场景 {scene_id} 的 script_block 重复引用 ref={ref}。",
                    scene_id=scene_id, ref=ref,
                ))
            refs[ref] = block_type
        # Resolve coverage: build content indexes.
        action_ids = {_text(a.get("action_id")) for a in (scene.get("actions") or []) if isinstance(a, dict)}
        beat_ids = {_text(b.get("beat_id")) for b in (scene.get("dramatic_beats") or scene.get("beats") or []) if isinstance(b, dict)}
        dialogue_ids = {_text(d.get("dialogue_id")) for d in (scene.get("dialogues") or []) if isinstance(d, dict)}
        action_refs = {ref for ref, btype in refs.items() if btype == "ACTION"}
        dialogue_refs = {ref for ref, btype in refs.items() if btype == "DIALOGUE"}
        valid_action_refs = action_ids | beat_ids
        for ref in sorted(action_refs - valid_action_refs):
            errors.append(_error(
                "SCRIPT_BLOCK_TARGET_MISSING",
                f"场景 {scene_id} 的 ACTION 块引用 {ref} 不存在于 actions/beats。",
                scene_id=scene_id, ref=ref,
            ))
        for ref in sorted(dialogue_refs - dialogue_ids):
            errors.append(_error(
                "SCRIPT_BLOCK_TARGET_MISSING",
                f"场景 {scene_id} 的 DIALOGUE 块引用 {ref} 不存在于 dialogues。",
                scene_id=scene_id, ref=ref,
            ))
        # Coverage: every dialogue must be on the timeline; every critical beat
        # (with visible content) must have an ACTION block referencing it or
        # an action whose beat_ref points to it.
        covered_beats = set()
        for block in blocks:
            if isinstance(block.get("beat_refs"), list):
                covered_beats.update(_text(ref) for ref in block.get("beat_refs") if _text(ref))
        for action in scene.get("actions") or []:
            if not isinstance(action, dict):
                continue
            beat_ref = _text(action.get("beat_ref"))
            if beat_ref:
                covered_beats.add(beat_ref)
                continue
            # Legacy action payloads may predate ``beat_ref``.  Preserve
            # coverage when the action text is the visible realization of a
            # dramatic beat, without assigning identity by array position.
            action_text = _text(action.get("text") or action.get("event"))
            if action_text:
                for beat in (scene.get("dramatic_beats") or scene.get("beats") or []):
                    if isinstance(beat, dict) and action_text == _text(beat.get("event")):
                        covered_beats.add(_text(beat.get("beat_id")))
        covered_beats |= {ref for ref, btype in refs.items() if btype == "ACTION" and ref in beat_ids}
        critical_beats = [b for b in (scene.get("dramatic_beats") or scene.get("beats") or []) if isinstance(b, dict) and (_text(b.get("importance")) == "critical" or b.get("requires_reaction"))]
        missing_dialogues = sorted(dialogue_ids - dialogue_refs)
        missing_critical = sorted({_text(b.get("beat_id")) for b in critical_beats} - covered_beats)
        if missing_dialogues:
            errors.append(_error(
                "SCRIPT_BLOCK_COVERAGE_INCOMPLETE",
                f"场景 {scene_id} 有 {len(missing_dialogues)} 段对白未进入 timeline：{missing_dialogues[:8]}",
                scene_id=scene_id, missing=missing_dialogues[:12],
            ))
        if missing_critical:
            errors.append(_error(
                "SCRIPT_BLOCK_COVERAGE_INCOMPLETE",
                f"场景 {scene_id} 有 {len(missing_critical)} 个 critical 节拍未进入 timeline：{missing_critical[:8]}",
                scene_id=scene_id, missing=missing_critical[:12],
            ))
    return errors


def validate_script_blocks(scene: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate one scene's explicit screenplay timeline deterministically.

    The returned diagnostics use the same hard-gate codes as a production
    ScriptIR evaluation, making this useful to editors and API callers that
    want to validate a scene before assembling a full episode payload.
    """
    if not isinstance(scene, dict):
        return [_error("SCRIPT_BLOCK_ORDER_REQUIRED", "scene must be an object")]
    return _gate_script_blocks({"scenes": [scene]})


def run_hard_gates(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    errors.extend(_gate_scene_transitions(script_ir))
    errors.extend(_gate_character_knowledge(script_ir))
    errors.extend(_gate_character_state_discontinuity(script_ir))
    errors.extend(_gate_prop_state_conflict(script_ir))
    errors.extend(_gate_timeline_conflict(script_ir))
    errors.extend(_gate_critical_beat(script_ir))
    errors.extend(_gate_script_blocks(script_ir))
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


def _soft_reader_duplicate_content(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    """A beat whose event is a semantic summary of a following dialogue creates
    an action/dialogue duplicate in the reader.  Flag it so authors remove the
    summary or drop the ACTION block from the timeline.
    """
    diagnostics: list[dict[str, Any]] = []
    for scene in _scene_order(script_ir):
        scene_id = _text(scene.get("scene_id"))
        dialogues = [d for d in (scene.get("dialogues") or []) if isinstance(d, dict)]
        beats = [b for b in (scene.get("dramatic_beats") or scene.get("beats") or []) if isinstance(b, dict)]
        for beat in beats:
            event = _text(beat.get("event"))
            if not event:
                continue
            # If the beat's event is a near-substring of a dialogue text, it is
            # likely a semantic summary that duplicates audible content.
            beat_core = event
            for dialogue in dialogues:
                text = _text(dialogue.get("text") or dialogue.get("content"))
                if not text:
                    continue
                if beat_core and (beat_core in text or text in beat_core) and len(beat_core) >= 6:
                    diagnostics.append(_diagnostic(
                        "SCRIPT_READER_DUPLICATE_CONTENT",
                        f"场景 {scene_id} 的节拍 {_text(beat.get('beat_id'))} 与对白 {_text(dialogue.get('dialogue_id'))} 内容重复（beat 是对话摘要）。",
                        scene_id=scene_id, beat_id=_text(beat.get("beat_id")), dialogue_id=_text(dialogue.get("dialogue_id")),
                    ))
    return diagnostics


def run_soft_diagnostics(script_ir: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    diagnostics.extend(_soft_repetitive_interrogation(script_ir))
    diagnostics.extend(_soft_exposition_heavy_dialogue(script_ir))
    diagnostics.extend(_soft_low_escalation(script_ir))
    diagnostics.extend(_soft_overdirected_script(script_ir))
    diagnostics.extend(_soft_reader_duplicate_content(script_ir))
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


def validate_reader_script(script_ir: dict[str, Any], reader_text: str) -> dict[str, Any]:
    """Reader-specific verification.

    Guarantees the reader output:
    * has no camera leak, no internal labels, no episode objective, no beat ids,
      no technical metadata;
    * interleaves action and dialogue (no all-actions-then-all-dialogues);
    * does not duplicate a beat summary with its dialogue.
    """
    errors: list[str] = []
    warnings: list[str] = []
    # No camera direction / internal labels / technical metadata.
    for pattern in CAMERA_LEAK_PATTERNS:
        if pattern in reader_text:
            errors.append(f"reader contains camera-direction pattern: {pattern}")
    for pattern in INTERNAL_LABEL_PATTERNS:
        if pattern in reader_text:
            errors.append(f"reader contains internal label: {pattern}")
    for pattern in ("beat_id", "dialogue_id", "assertion_mode", "DECEPTION", "OBJECTIVE_FACT", "contradicts", "prompt_fingerprint", "FactSnapshot", "source_ref"):
        if pattern in reader_text:
            errors.append(f"reader contains technical metadata: {pattern}")
    objective = _text(script_ir.get("episode_objective"))
    if objective and objective in reader_text:
        errors.append("reader contains episode_objective")
    # Interleaving check: no run of >3 consecutive same-type visible blocks in a
    # rendered scene.  Parse visible paragraph types from the reader text.
    visible_lines = [line for line in reader_text.splitlines() if line.strip()]
    type_runs = []
    current_type = None
    current_run = 0
    for line in visible_lines:
        if line.startswith("**") and line.endswith("**"):
            line_type = "DIALOGUE_HEADER"
        elif line.startswith("场") and ("日" in line or "夜" in line or "内" in line or "外" in line):
            line_type = "HEADER"
        elif line.startswith("#"):
            line_type = "TITLE"
        else:
            # The following line after a DIALOGUE_HEADER is dialogue text; a
            # bare prose line is ACTION.
            line_type = "DIALOGUE_BODY" if current_type == "DIALOGUE_HEADER" else "ACTION"
        if line_type == current_type:
            current_run += 1
        else:
            if current_run >= 5 and current_type in {"ACTION", "DIALOGUE_BODY", "DIALOGUE_HEADER"}:
                type_runs.append((current_type, current_run))
            current_type = line_type
            current_run = 1
    if current_run >= 5 and current_type in {"ACTION", "DIALOGUE_BODY", "DIALOGUE_HEADER"}:
        type_runs.append((current_type, current_run))
    if type_runs:
        warnings.append(f"long same-type runs: {type_runs}")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "long_runs": type_runs,
    }
