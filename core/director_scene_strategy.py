"""V3 SceneDirectingStrategy domain object and deterministic validator.

The strategy is the directing brief for one scene.  It sits between an
approved treatment/blocking package and a draft ShotPlan.  This module is
provider-free: it builds a conservative fixture from supplied evidence and
validates references/consistency, but never calls a model or mutates a plan.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Iterable


SCENE_STRATEGY_SCHEMA_VERSION = "director_scene_strategy_v1"
SOURCE_FACT = "SOURCE_FACT"
TREATMENT_INTENT = "TREATMENT_INTENT"
BLOCKING_FACT = "BLOCKING_FACT"
DIRECTOR_CREATIVE_DECISION = "DIRECTOR_CREATIVE_DECISION"
AUTHORITY_TYPES = {SOURCE_FACT, TREATMENT_INTENT, BLOCKING_FACT, DIRECTOR_CREATIVE_DECISION}

STRATEGY_FIELDS = (
    "schema_version", "scene_id", "strategy_version", "dramatic_objective",
    "scene_question", "audience_experience", "beat_priorities",
    "audience_knowledge_arc", "emotional_arc", "power_arc", "visual_grammar",
    "camera_principles", "composition_principles", "performance_arc", "edit_arc",
    "information_reveal_plan", "spatial_expression", "prop_visual_strategy",
    "shot_architecture_guidance", "must_preserve", "must_avoid", "creative_risks",
    "strategy_summary", "authority", "source_refs", "strategy_fingerprint",
)


class SceneStrategyError(ValueError):
    code = "DIRECTOR_SCENE_STRATEGY_INVALID"

    def __init__(self, message: str, *, code: str | None = None, path: str = "") -> None:
        super().__init__(message)
        self.code = code or self.code
        self.path = path


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def strategy_fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def build_strategy_contract(*, scene: dict[str, Any], treatment: dict[str, Any] | None = None, blocking: dict[str, Any] | None = None, fact_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build only an immutable reference contract from approved evidence."""
    scene_obj, treatment_obj, blocking_obj, facts_obj = map(_dict, (scene, treatment, blocking, fact_snapshot))
    beat_rows = _list(scene_obj.get("beats")) or _list(treatment_obj.get("beat_map"))
    beats: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(beat_rows, 1):
        row = raw if isinstance(raw, dict) else {"event": str(raw)}
        beat_id = _text(row.get("beat_id") or row.get("id") or f"B{index:02d}")
        beats[beat_id] = copy.deepcopy(row)
    character_ids: set[str] = set()
    intents = _dict(treatment_obj.get("character_intents"))
    character_ids.update(_text(key) for key in intents if _text(key))
    for row in _list(blocking_obj.get("participants")):
        if isinstance(row, dict):
            value = row.get("character_id") or row.get("id")
        else:
            value = row
        if _text(value):
            character_ids.add(_text(value))
    for row in _list(scene_obj.get("participants")):
        value = row.get("character_id") if isinstance(row, dict) else row
        if _text(value):
            character_ids.add(_text(value))
    fact_ids: set[str] = set()
    source_facts = _list(scene_obj.get("source_facts")) + _list(blocking_obj.get("source_spatial_facts")) + _list(facts_obj.get("records"))
    for index, row in enumerate(source_facts, 1):
        if isinstance(row, dict):
            fact_id = _text(row.get("fact_id") or row.get("id") or f"FACT_{index:04d}")
            if fact_id:
                fact_ids.add(fact_id)
    scene_id = _text(scene_obj.get("scene_id") or treatment_obj.get("scene_id") or blocking_obj.get("scene_id") or scene_obj.get("name") or treatment_obj.get("scene_name"))
    return {
        "scene_id": scene_id,
        "beat_ids": list(beats),
        "beats": beats,
        "character_ids": sorted(character_ids),
        "fact_ids": sorted(fact_ids),
        "immutable_source_projection": {
            "scene_name": _text(scene_obj.get("name") or treatment_obj.get("scene_name")),
            "event_facts": [_text(row.get("event")) for row in beats.values() if _text(row.get("event"))],
            "source_facts": copy.deepcopy(source_facts),
        },
    }


def _beat_rows(contract: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [(str(key), value if isinstance(value, dict) else {}) for key, value in _dict(contract).get("beats", {}).items()]


def build_scene_directing_strategy(*, scene: dict[str, Any], treatment: dict[str, Any] | None = None, blocking: dict[str, Any] | None = None, fact_snapshot: dict[str, Any] | None = None, strategy_version: str = "v3-foundation-shadow") -> dict[str, Any]:
    """Create a provider-free strategy from declared evidence only.

    The output is intentionally a directing strategy, not a ShotPlan: it
    contains phase principles and arcs but no final shot topology.
    """
    scene_obj, treatment_obj = _dict(scene), _dict(treatment)
    contract = build_strategy_contract(scene=scene_obj, treatment=treatment_obj, blocking=blocking, fact_snapshot=fact_snapshot)
    rows = _beat_rows(contract)
    if not rows:
        raise SceneStrategyError("SceneDirectingStrategy requires at least one source beat", code="MISSING_SOURCE_BEATS")
    beat_ids = [key for key, _ in rows]
    character_ids = contract["character_ids"]
    default_character = character_ids[0] if character_ids else "shared"
    first_event = _text(rows[0][1].get("event")) or "当前场景冲突"
    last_event = _text(rows[-1][1].get("event")) or "场景转折"
    objective = _text(treatment_obj.get("dramatic_objective") or treatment_obj.get("scene_objective")) or f"让观众从“{first_event}”的预期走向“{last_event}”后的新判断。"
    question = _text(treatment_obj.get("audience_question") or treatment_obj.get("scene_question")) or "这一场戏结束时，观众会重新判断什么？"
    phases = []
    knowledge = []
    emotional = []
    power = []
    reveals = []
    for index, (beat_id, beat) in enumerate(rows, 1):
        phase_id = f"P{index:02d}"
        event = _text(beat.get("event")) or f"beat {beat_id}"
        beat_type = _text(beat.get("type")).lower()
        is_reveal = beat_type in {"reveal", "decision", "power_shift"} or bool(_text(beat.get("information_change")))
        experience = "建立预期" if index == 1 else ("确认变化" if is_reveal else "增加压力")
        phases.append({"phase_id": phase_id, "beat_ids": [beat_id], "experience": experience, "rationale": f"服务 {event} 的观众体验变化"})
        knowledge.append({"phase_id": phase_id, "beat_id": beat_id, "knows": [event] if index == 1 else [], "does_not_know_yet": ["下一阶段的后果"], "suspects": ["人物真实意图"], "reveal": [event] if is_reveal else [], "withhold": ["尚未发生的后果"]})
        intensity = min(9, 3 + index + (2 if is_reveal else 0))
        emotional.append({"phase": phase_id, "beat_ids": [beat_id], "trigger": event, "emotion_state": "不安" if is_reveal else ("期待" if index == 1 else "压力上升"), "intensity_hint": intensity, "transition_reason": "由当前节拍的可见变化推动"})
        controller = default_character
        power.append({"phase": phase_id, "beat_id": beat_id, "controller": controller, "shift": "信息或行动改变控制感" if is_reveal else "维持既有控制关系", "expression": "通过构图关系、反应与镜头距离表现，不改变事实"})
        reveals.append({"beat_id": beat_id, "source_fact_refs": [f for f in contract["fact_ids"] if f], "reveal": [event] if is_reveal else [], "withhold": ["尚未发生的剧情结果"], "hint": ["人物反应或空间细节"]})
    performance = []
    for character_id in character_ids or [default_character]:
        intent = _dict(_dict(treatment_obj.get("character_intents")).get(character_id))
        performance.append({"character_id": character_id, "beat_ids": beat_ids, "objective": _text(intent.get("goal")) or "推进当前场景目标", "tactic_progression": ["观察", "试探", "施压或回应"], "visible_behavior_progression": ["保持初始姿态", "出现可见反应", "在转折处改变行动"], "turning_point": beat_ids[-1]})
    strategy = {
        "schema_version": SCENE_STRATEGY_SCHEMA_VERSION,
        "scene_id": contract["scene_id"],
        "strategy_version": strategy_version,
        "dramatic_objective": objective,
        "scene_question": question,
        "audience_experience": phases,
        "beat_priorities": [{"beat_id": beat_id, "priority": "primary" if index in {1, len(rows)} else "supporting", "dramatic_function": _text(beat.get("dramatic_function")) or "推进当前场景变化"} for index, (beat_id, beat) in enumerate(rows, 1)],
        "audience_knowledge_arc": knowledge,
        "emotional_arc": emotional,
        "power_arc": power,
        "visual_grammar": {"overall": "先建立可读的空间关系，再以隔离、反应和信息焦点表现认知变化。", "phases": [{"phase_id": p["phase_id"], "beat_ids": p["beat_ids"], "grammar": "客观关系" if i == 0 else "逐步收紧并保留反应"} for i, p in enumerate(phases)]},
        "camera_principles": ["信息未确认前保持客观机位。", "只有角色认知或权力关系发生可见变化时才推进、转向或切入近景。", "每次运动必须能回答它服务哪一个节拍。"],
        "composition_principles": ["先让人物关系可读，再用隔离、负空间或视线关系表现变化。", "关键道具只在已声明信息需要强调时进入视觉中心。"],
        "performance_arc": performance,
        "edit_arc": {"tempo_progression": "从建立预期到压力上升，转折处短暂保留反应，结尾留余波。", "hold_points": ["转折后的反应", "新信息被理解的瞬间"], "cut_motivations": ["beat change", "action completion", "reaction completion", "reveal control"], "reveal_timing": "按 beat 顺序揭示，不提前泄露结果"},
        "information_reveal_plan": reveals,
        "spatial_expression": ["沿用 Blocking 的入口、锚点、屏幕方向和出入状态；只改变呈现方式。"],
        "prop_visual_strategy": ["只强调来源事实中已绑定且对当前 beat 有作用的道具。"],
        "shot_architecture_guidance": {"required_functions": ["establishing", "relationship", "action_or_reveal", "reaction"], "phase_mapping": [{"phase_id": p["phase_id"], "beat_ids": p["beat_ids"], "functions": ["relationship"] if i == 0 else ["action_or_reveal", "reaction"]} for i, p in enumerate(phases)], "topology_status": "not_defined_by_strategy"},
        "must_preserve": ["scene identity", "declared event and dialogue facts", "character and asset identity", "blocking source truth", "chronology"],
        "must_avoid": ["每个镜头都移动相机", "为多样性随机换景别", "每句对白都切镜头", "情绪强度机械锯齿", "提前 reveal", "缺少 reaction", "机械 shot/reverse-shot"],
        "creative_risks": ["如果 ShotPlan 未覆盖 phase 或 reaction，必须进入 QA 修复或重导。"],
        "strategy_summary": f"以“{objective}”为核心，沿 beat 顺序控制观众知识、情绪、权力和视觉语法。",
        "authority": {SOURCE_FACT: ["scene identity", "event facts", "dialogue facts", "character identity", "asset identity", "chronology"], TREATMENT_INTENT: ["dramatic objective", "tone and intent"], BLOCKING_FACT: ["spatial source truth", "entry/exit state", "screen direction"], DIRECTOR_CREATIVE_DECISION: ["audience experience", "arcs", "visual grammar", "camera/composition principles", "edit strategy", "shot architecture guidance"]},
        "source_refs": {"contract_scene_id": contract["scene_id"], "beat_ids": beat_ids, "character_ids": character_ids, "fact_ids": contract["fact_ids"]},
    }
    strategy["strategy_fingerprint"] = strategy_fingerprint(strategy)
    return strategy


def _validate_refs(strategy: dict[str, Any], contract: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    known_beats = set(_dict(contract).get("beat_ids") or _dict(_dict(contract).get("beats")).keys())
    known_chars = set(_dict(contract).get("character_ids") or [])
    known_facts = set(_dict(contract).get("fact_ids") or [])
    for path, rows in (("beat_priorities", strategy.get("beat_priorities")), ("audience_knowledge_arc", strategy.get("audience_knowledge_arc")), ("emotional_arc", strategy.get("emotional_arc")), ("power_arc", strategy.get("power_arc")), ("information_reveal_plan", strategy.get("information_reveal_plan"))):
        for index, row in enumerate(_list(rows)):
            if not isinstance(row, dict):
                errors.append({"code": "INVALID_ITEM", "path": f"{path}[{index}]"}); continue
            refs = _list(row.get("beat_ids")) or ([_text(row.get("beat_id"))] if _text(row.get("beat_id")) else [])
            for beat_id in refs:
                if beat_id not in known_beats:
                    errors.append({"code": "UNKNOWN_BEAT_REFERENCE", "path": f"{path}[{index}]", "beat_id": beat_id})
            for fact_id in _list(row.get("source_fact_refs")):
                if known_facts and fact_id not in known_facts:
                    errors.append({"code": "UNKNOWN_SOURCE_FACT_REFERENCE", "path": f"{path}[{index}]", "fact_id": fact_id})
    for index, row in enumerate(_list(strategy.get("performance_arc"))):
        if isinstance(row, dict) and known_chars and _text(row.get("character_id")) not in known_chars:
            errors.append({"code": "UNKNOWN_CHARACTER_REFERENCE", "path": f"performance_arc[{index}].character_id"})
    for index, row in enumerate(_list(strategy.get("power_arc"))):
        if isinstance(row, dict) and known_chars and _text(row.get("controller")) not in known_chars | {"shared", "none"}:
            errors.append({"code": "INVALID_POWER_CONTROLLER", "path": f"power_arc[{index}].controller"})


def parse_scene_directing_strategy(raw: Any, contract: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SceneStrategyError("strategy must be an object")
    unknown = sorted(set(raw) - set(STRATEGY_FIELDS))
    if unknown:
        raise SceneStrategyError(f"strategy contains forbidden fields: {', '.join(unknown)}", code="STRATEGY_FIELD_FORBIDDEN")
    missing = [field for field in STRATEGY_FIELDS if field not in {"strategy_fingerprint", "authority", "source_refs"} and not raw.get(field)]
    if missing:
        raise SceneStrategyError(f"strategy missing required fields: {', '.join(missing)}", code="STRATEGY_SCHEMA_INCOMPLETE")
    if _text(raw.get("schema_version")) != SCENE_STRATEGY_SCHEMA_VERSION:
        raise SceneStrategyError(f"schema_version must be {SCENE_STRATEGY_SCHEMA_VERSION}", code="STRATEGY_SCHEMA_VERSION_INVALID")
    normalized = copy.deepcopy(raw)
    errors: list[dict[str, Any]] = []
    _validate_refs(normalized, _dict(contract), errors)
    beat_ids = list(_dict(contract).get("beat_ids") or [])
    for required_name in ("audience_knowledge_arc", "emotional_arc", "power_arc"):
        refs = []
        for row in _list(normalized.get(required_name)):
            if not isinstance(row, dict):
                continue
            refs.extend(_list(row.get("beat_ids")) or ([_text(row.get("beat_id"))] if _text(row.get("beat_id")) else []))
        if beat_ids and set(refs) != set(beat_ids):
            errors.append({"code": "STRATEGY_COVERAGE_GAP", "field": required_name, "missing": sorted(set(beat_ids) - set(refs))})
    source_refs = _dict(normalized.get("source_refs"))
    if beat_ids and set(_list(source_refs.get("beat_ids"))) != set(beat_ids):
        errors.append({"code": "SOURCE_BEAT_COVERAGE_GAP"})
    info_rows = _list(normalized.get("information_reveal_plan"))
    info_order = [_text(row.get("beat_id")) for row in info_rows if isinstance(row, dict)]
    if beat_ids and info_order != beat_ids:
        errors.append({"code": "REVEAL_CHRONOLOGY_INVALID", "expected": beat_ids, "actual": info_order})
    source_events = {_text(row.get("event")) for row in _dict(contract).get("beats", {}).values() if isinstance(row, dict) and _text(row.get("event"))}
    for index, row in enumerate(info_rows):
        if not isinstance(row, dict):
            continue
        reveal_values = {_text(value) for value in _list(row.get("reveal")) if _text(value)}
        if source_events and not reveal_values.issubset(source_events):
            errors.append({"code": "FACT_INVENTION", "path": f"information_reveal_plan[{index}].reveal", "values": sorted(reveal_values - source_events)})
        if reveal_values.intersection({_text(value) for value in _list(row.get("withhold")) if _text(value)}):
            errors.append({"code": "STRATEGY_INTERNAL_CONTRADICTION", "path": f"information_reveal_plan[{index}]"})
    if errors:
        first = errors[0]
        raise SceneStrategyError(first.get("code", "strategy validation failed"), code=first.get("code", "DIRECTOR_SCENE_STRATEGY_INVALID"), path=first.get("path", ""))
    supplied = _text(normalized.get("strategy_fingerprint"))
    normalized.pop("strategy_fingerprint", None)
    expected = strategy_fingerprint(normalized)
    if supplied and supplied != expected:
        raise SceneStrategyError("strategy_fingerprint does not match normalized strategy", code="STRATEGY_FINGERPRINT_MISMATCH")
    normalized["strategy_fingerprint"] = expected
    return normalized


def validate_scene_directing_strategy(raw: Any, contract: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        normalized = parse_scene_directing_strategy(raw, contract)
        return {"valid": True, "strategy": normalized, "errors": []}
    except SceneStrategyError as exc:
        return {"valid": False, "strategy": None, "errors": [{"code": exc.code, "path": exc.path, "message": str(exc)}]}


__all__ = ["SCENE_STRATEGY_SCHEMA_VERSION", "SOURCE_FACT", "TREATMENT_INTENT", "BLOCKING_FACT", "DIRECTOR_CREATIVE_DECISION", "SceneStrategyError", "build_strategy_contract", "build_scene_directing_strategy", "parse_scene_directing_strategy", "validate_scene_directing_strategy", "strategy_fingerprint"]
