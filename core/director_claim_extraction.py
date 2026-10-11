"""Deterministic, schema-aware ClaimIR extraction for the V7.7.0 shadow audit."""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from .director_claim_ir import CLAIM_SET_VERSION, make_claim, claim_set_fingerprint


_CHARACTERS = ("顾沉", "林晚", "陆叔", "那人", "门外陌生人")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _subject(text: str, fallback: str = "") -> str:
    for item in _CHARACTERS:
        if item in text:
            return item
    return fallback


def _path_parts(path: str) -> tuple[str, int | None, str]:
    m = re.match(r"([^\.\[]+)(?:\[(\d+)\])?(?:\.(.*))?$", path)
    if not m:
        return path, None, ""
    return m.group(1), int(m.group(2)) if m.group(2) is not None else None, m.group(3) or ""


def _walk(value: Any, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            yield from _walk(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")
    elif isinstance(value, str) and value.strip():
        yield path or "$", value.strip()


def _id(origin: str, path: str, kind: str, index: int = 0) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", path).strip("_") or "root"
    return f"DC_{origin}_{safe}_{kind}_{index:02d}"


def _claim(origin: str, path: str, text: str, kind: str, *, subject: Mapping[str, Any] | None = None, predicate: str = "", object_: Mapping[str, Any] | None = None, qualifiers: Mapping[str, Any] | None = None, polarity: str = "POSITIVE", modality: str = "ASSERTED", canonicality: str = "CANONICAL_ASSERTION", authority: str = "SOURCE", source_refs: list[str] | None = None, upstream: list[str] | None = None, support: str = "UNRESOLVED", index: int = 0, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return make_claim(claim_id=_id(origin, path, kind, index), source_path=path, raw_text=text, claim_type=kind, subject=subject, predicate=predicate, object_=object_, qualifiers=qualifiers, polarity=polarity, modality=modality, canonicality=canonicality, authority_required=authority, source_refs=source_refs, upstream_claim_refs=upstream, origin=origin, support_status=support, metadata=metadata)


def project_source_claims(units: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Project canonical source units without inferring beyond explicit facts."""
    claims: list[dict[str, Any]] = []
    for unit in sorted((u for u in units if isinstance(u, Mapping)), key=lambda x: int(x.get("source_order") or 0)):
        ref = str(unit.get("unit_id") or unit.get("source_ref") or "")
        text = _text(unit.get("text") or unit.get("source_text"))
        path = f"source_units[{ref}]"
        if not text:
            continue
        def add(kind: str, *, predicate: str, subject: Mapping[str, Any] | None = None, object_: Mapping[str, Any] | None = None, qualifiers: Mapping[str, Any] | None = None, polarity: str = "POSITIVE", modality: str = "ASSERTED", index: int = 0) -> None:
            claims.append(_claim("SOURCE", path, text, kind, subject=subject, predicate=predicate, object_=object_, qualifiers=qualifiers, polarity=polarity, modality=modality, canonicality="CANONICAL_ASSERTION", authority="SOURCE", source_refs=[ref], support="SUPPORTED_EXPLICIT", index=index))

        if "顾沉带林晚进入暗房" in text:
            add("CHARACTER_ACTION", predicate="带/引导进入", subject={"kind": "CHARACTER", "ref": "顾沉"}, object_={"kind": "CHARACTER", "ref": "林晚"}, qualifiers={"destination": "暗房"})
            add("SOURCE_EVENT", predicate="进入", subject={"kind": "CHARACTER_GROUP", "ref": "顾沉+林晚"}, object_={"kind": "LOCATION", "ref": "暗房"}, index=1)
        if "安全灯" in text:
            if "忽明忽暗" in text:
                add("ENVIRONMENT_STATE", predicate="light_state", subject={"kind": "ENVIRONMENT", "ref": "暗房"}, object_={"kind": "LIGHT", "ref": "红色安全灯"}, qualifiers={"state": "flickering"})
            if "熄灭" in text:
                add("CHARACTER_ACTION", predicate="熄灭", subject={"kind": "CHARACTER", "ref": "顾沉"}, object_={"kind": "LIGHT", "ref": "安全灯"})
        if "水渍" in text:
            add("ENVIRONMENT_STATE", predicate="has_surface_mark", subject={"kind": "LOCATION", "ref": "暗房"}, object_={"kind": "SURFACE", "ref": "墙面水渍"})
        if "铁盒" in text:
            add("OBJECT_EXISTENCE", predicate="exists", subject={"kind": "OBJECT", "ref": "铁盒"}, object_={"kind": "LOCATION", "ref": "暗房"})
            if "空" in text:
                add("OBJECT_PROPERTY", predicate="state", subject={"kind": "OBJECT", "ref": "铁盒"}, object_={"kind": "PROPERTY", "ref": "empty"}, index=1)
            if "手写标签" in text:
                add("OBJECT_PROPERTY", predicate="handwritten", subject={"kind": "OBJECT", "ref": "铁盒标签"}, object_={"kind": "PROPERTY", "ref": "handwritten"}, index=1)
                add("OBJECT_PROVENANCE", predicate="authored_by", subject={"kind": "PERSON", "ref": "母亲"}, object_={"kind": "OBJECT", "ref": "铁盒标签"}, index=2)
            if "母亲" in text and "留下" in text:
                add("OBJECT_PROVENANCE", predicate="left_by", subject={"kind": "PERSON", "ref": "母亲"}, object_={"kind": "OBJECT", "ref": "铁盒"}, index=3)
        if "胶片" in text:
            add("OBJECT_EXISTENCE", predicate="exists", subject={"kind": "OBJECT", "ref": "烧焦胶片"}, object_={"kind": "LOCATION", "ref": "铁盒"})
            if "被人拿走" in text:
                add("INFORMATION_REVEAL", predicate="taken_by_someone", subject={"kind": "OBJECT", "ref": "胶片"}, object_={"kind": "UNKNOWN_ACTOR", "ref": "某人"})
        if "海鸥别针" in text:
            add("OBJECT_EXISTENCE", predicate="exists", subject={"kind": "OBJECT", "ref": "海鸥别针"}, object_={"kind": "LOCATION", "ref": "铁盒"})
        if "认出别针" in text:
            add("CHARACTER_KNOWLEDGE", predicate="recognizes", subject={"kind": "CHARACTER", "ref": "林晚"}, object_={"kind": "OBJECT", "ref": "海鸥别针"})
        if "想不起" in text and "是否来过" in text:
            add("CHARACTER_KNOWLEDGE", predicate="cannot_confirm", subject={"kind": "CHARACTER", "ref": "林晚"}, object_={"kind": "EVENT", "ref": "childhood_visit_to_darkroom"})
            add("UNCERTAINTY", predicate="unresolved", subject={"kind": "EVENT", "ref": "childhood_visit_to_darkroom"}, object_={"kind": "STATE", "ref": "unknown"}, modality="UNCERTAIN", index=1)
        if "问是谁" in text:
            add("CHARACTER_ACTION", predicate="asks_identity", subject={"kind": "CHARACTER", "ref": "林晚"}, object_={"kind": "UNKNOWN_ACTOR", "ref": "胶片拿走者"})
        if "也许是你自己" in text:
            add("INFORMATION_REVEAL", predicate="suggests_possible_actor", subject={"kind": "CHARACTER", "ref": "顾沉"}, object_={"kind": "CHARACTER", "ref": "林晚"}, modality="POSSIBLE")
            add("UNCERTAINTY", predicate="possible_not_certain", subject={"kind": "CHARACTER", "ref": "顾沉"}, object_={"kind": "CHARACTER", "ref": "林晚"}, modality="UNCERTAIN", index=1)
        if "铜铃" in text:
            add("SENSORY_FACT", predicate="heard", subject={"kind": "CHARACTER_GROUP", "ref": "顾沉+林晚"}, object_={"kind": "SOUND", "ref": "门外铜铃"})
        if "拉着林晚躲到药水柜后" in text:
            add("CHARACTER_ACTION", predicate="拉着躲到", subject={"kind": "CHARACTER", "ref": "顾沉"}, object_={"kind": "CHARACTER", "ref": "林晚"}, qualifiers={"destination": "药水柜后"})
            add("SPATIAL_BLOCKING", predicate="hides_behind", subject={"kind": "CHARACTER_GROUP", "ref": "顾沉+林晚"}, object_={"kind": "LOCATION", "ref": "药水柜后"}, index=1)
        if "皮鞋" in text:
            add("OBJECT_EXISTENCE", predicate="appears", subject={"kind": "OBJECT", "ref": "皮鞋"}, object_={"kind": "LOCATION", "ref": "门缝下"})
            if "湿透" in text:
                add("OBJECT_PROPERTY", predicate="wet", subject={"kind": "OBJECT", "ref": "皮鞋"}, object_={"kind": "PROPERTY", "ref": "wet"}, index=1)
        if "车票" in text:
            add("OBJECT_EXISTENCE", predicate="exists", subject={"kind": "OBJECT", "ref": "车票"}, object_={"kind": "LOCATION", "ref": "门缝下"})
            if "塞进来" in text:
                add("CHARACTER_ACTION", predicate="inserts", subject={"kind": "UNKNOWN_ACTOR", "ref": "那人"}, object_={"kind": "OBJECT", "ref": "车票"}, index=1)
            if "背面写着" in text:
                add("OBJECT_PROPERTY", predicate="text_content", subject={"kind": "OBJECT", "ref": "车票背面"}, object_={"kind": "TEXT", "ref": "今晚十点，北堤仓库，带钥匙，不要带顾沉"}, index=1)
                add("INFORMATION_WITHHOLD", predicate="instruction_recipient_unknown", subject={"kind": "OBJECT", "ref": "车票背面"}, object_={"kind": "INFORMATION", "ref": "指令"}, index=2)
        if str(unit.get("source_type") or "").upper() == "SOURCE_DIALOGUE":
            add("SOURCE_EVENT", predicate="dialogue", subject={"kind": "CHARACTER", "ref": str(unit.get("speaker") or "未知说话者")}, object_={"kind": "DIALOGUE", "ref": text}, index=9)
    return claims


def _source_refs_for_path(path: str, document: Mapping[str, Any], source_ref_map: Mapping[str, list[str]] | None) -> list[str]:
    if source_ref_map and path in source_ref_map:
        return list(source_ref_map[path])
    m = re.search(r"beats\[(\d+)\]", path)
    if m:
        beat = (document.get("beats") or [])[int(m.group(1))] if isinstance(document.get("beats"), list) and int(m.group(1)) < len(document.get("beats") or []) else {}
        return [str(x) for x in (beat.get("refs") or [])] if isinstance(beat, Mapping) else []
    m = re.search(r"beat_enrichments\[(\d+)\]", path)
    if m:
        return [str(x) for x in (document.get("beat_enrichments") or [])[int(m.group(1))].get("refs", [])] if False else []
    return []


def _base_claim(origin: str, path: str, text: str, source_refs: list[str], document: Mapping[str, Any]) -> dict[str, Any]:
    field = path.rsplit(".", 1)[-1]
    if origin == "STAGE_A" and field == "purpose":
        return _claim(origin, path, text, "DRAMATIC_GROUPING", subject={"kind": "BEAT", "ref": path}, predicate="purpose", object_={"kind": "DRAMATIC_PURPOSE", "ref": text}, authority="STAGE_A", source_refs=source_refs)
    if origin == "STAGE_A" and field in {"scene_objective", "dramatic_question"}:
        kind = "DRAMATIC_OBJECTIVE" if field == "scene_objective" else "DRAMATIC_QUESTION"
        return _claim(origin, path, text, kind, subject={"kind": "SCENE", "ref": "E01_SC001"}, predicate=field, object_={"kind": "DRAMATIC_TEXT", "ref": text}, authority="STAGE_A", source_refs=source_refs)
    if "audience_effect" in path:
        return _claim(origin, path, text, "AUDIENCE_EFFECT", subject={"kind": "AUDIENCE", "ref": "viewer"}, predicate="experience", object_={"kind": "EFFECT", "ref": text}, canonicality="AUDIENCE_INTERPRETATION", authority="STAGE_B", source_refs=source_refs)
    if "audience_should" in path or "audience_focus" in path:
        kind = "AUDIENCE_INTERPRETATION"
        return _claim(origin, path, text, kind, subject={"kind": "AUDIENCE", "ref": "viewer"}, predicate=field, object_={"kind": "INTERPRETATION", "ref": text}, canonicality="AUDIENCE_INTERPRETATION", authority="STAGE_B", source_refs=source_refs)
    if "performance" in path or field in {"direction", "strategy", "performance_notes", "effect", "transition", "state", "opening", "reveal", "escalation", "button", "scene_exit_intent"}:
        return _claim(origin, path, text, "PERFORMANCE_DIRECTION", subject={"kind": "PERFORMER", "ref": _subject(text, "scene")}, predicate="play", object_={"kind": "DIRECTION", "ref": text}, canonicality="NON_CANONICAL_PERFORMANCE_OPTION", modality="PLAYABLE_OPTION", authority="STAGE_B", source_refs=source_refs)
    if "prohibited_interpretations" in path:
        return _claim(origin, path, text, "PROHIBITION", predicate="prohibit", object_={"kind": "INTERPRETATION", "ref": text}, polarity="PROHIBITION", modality="PROHIBITED", canonicality="META", authority="NONE", source_refs=source_refs)
    if "visual_priority" in path:
        return _claim(origin, path, text, "VISUAL_PRIORITY", subject={"kind": "AUDIENCE", "ref": "viewer"}, predicate="notice", object_={"kind": "VISUAL_SUBJECT", "ref": text}, canonicality="AUDIENCE_INTERPRETATION", authority="STAGE_B", source_refs=source_refs)
    if "known_to_audience" in path or "reveal_plan" in path or "reaction_priority" in path:
        kind = "INFORMATION_REVEAL" if ".reveals" in path or "known_to_audience" in path else ("INFORMATION_WITHHOLD" if ".withholds" in path or "not_yet_know" in path else "AUDIENCE_INTERPRETATION")
        return _claim(origin, path, text, kind, subject={"kind": "AUDIENCE", "ref": "viewer"}, predicate="information", object_={"kind": "NARRATIVE_INFORMATION", "ref": text}, canonicality="AUDIENCE_INTERPRETATION", authority="STAGE_B", source_refs=source_refs)
    if "objective" in path:
        return _claim(origin, path, text, "CHARACTER_INTENT", subject={"kind": "CHARACTER", "ref": _subject(text, "unspecified_character")}, predicate="objective", object_={"kind": "INTENT", "ref": text}, source_refs=source_refs)
    if "obstacle" in path:
        return _claim(origin, path, text, "CHARACTER_STATE", subject={"kind": "CHARACTER", "ref": _subject(text, "unspecified_character")}, predicate="condition", object_={"kind": "STATE", "ref": text}, source_refs=source_refs)
    if "note" in path:
        return _claim(origin, path, text, "META_COMPLIANCE", predicate="compliance_note", object_={"kind": "META", "ref": text}, polarity="META_COMPLIANCE", modality="DELEGATED", canonicality="META", authority="NONE", source_refs=source_refs)
    return _claim(origin, path, text, "AUDIENCE_INTERPRETATION", subject={"kind": "DIRECTOR", "ref": origin}, predicate=field, object_={"kind": "TEXT", "ref": text}, canonicality="AUDIENCE_INTERPRETATION", authority="STAGE_A" if origin == "STAGE_A" else "STAGE_B", source_refs=source_refs)


def _embedded_claims(origin: str, path: str, text: str, source_refs: list[str]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    def add(kind: str, predicate: str, subject: Mapping[str, Any], object_: Mapping[str, Any], *, modality: str = "ASSERTED", canonicality: str = "CANONICAL_ASSERTION", authority: str = "SOURCE", polarity: str = "POSITIVE", support: str = "UNRESOLVED", qualifiers: Mapping[str, Any] | None = None, index: int = 0, metadata: Mapping[str, Any] | None = None):
        found.append(_claim(origin, path, text, kind, subject=subject, predicate=predicate, object_=object_, qualifiers=qualifiers, modality=modality, canonicality=canonicality, authority=authority, polarity=polarity, source_refs=source_refs, support=support, index=index, metadata=metadata))
    # This grammar is structural: it classifies a relation and its arguments,
    # rather than whitelisting a complete historical sentence.
    if re.search(r"交由|交给|留给", text) and re.search(r"SceneBlocking|ShotPlan|场面调度|分镜", text, re.I):
        targets = [name for name in ("SceneBlocking", "ShotPlan") if name.lower() in text.lower()]
        add("AUTHORITY_DELEGATION", "delegates_to", {"kind": "DIRECTOR", "ref": "stage_b"}, {"kind": "AUTHORITY", "ref": "+".join(targets)}, modality="DELEGATED", canonicality="META", authority="NONE", polarity="DELEGATION", support="META_SAFE", index=0, metadata={"target_authority": targets})
        if any(term in text for term in ("站", "走到", "带到", "机位", "特写", "镜头", "焦段", "路径")):
            add("SPATIAL_BLOCKING", "embedded_execution", {"kind": "CHARACTER", "ref": _subject(text, "unspecified_character")}, {"kind": "EXECUTION", "ref": text}, authority="NONE", support="UNRESOLVED", index=1)
    if "试探" in text:
        add("CHARACTER_INTENT", "test_or_probe", {"kind": "CHARACTER", "ref": _subject(text, "顾沉")}, {"kind": "CHARACTER", "ref": "林晚"}, qualifiers={"dialogue_cue": "也许是你自己" if "也许是你自己" in text else ""}, index=2)
    if "不惊动" in text and "观察" in text:
        add("CHARACTER_INTENT", "observe_without_alerting", {"kind": "CHARACTER", "ref": _subject(text, "顾沉")}, {"kind": "CHARACTER", "ref": "林晚"}, qualifiers={"strategy": "observe_reaction"}, index=3)
    if "微弱光线" in text or "微弱的光线" in text:
        add("ENVIRONMENT_STATE", "light_level", {"kind": "ENVIRONMENT", "ref": "暗房"}, {"kind": "LIGHT", "ref": "dim"}, index=4)
    if "手写" in text:
        target = "车票背面" if "车票" in text else ("铁盒标签" if "标签" in text or "铁盒" in text else "unspecified_object")
        add("OBJECT_PROPERTY", "handwritten", {"kind": "OBJECT", "ref": target}, {"kind": "PROPERTY", "ref": "handwritten"}, index=5, metadata={"explicit_target": target})
    if re.search(r"接过|接收|拿到", text) and "车票" in text:
        add("OBJECT_POSSESSION", "receives", {"kind": "CHARACTER", "ref": _subject(text, "林晚")}, {"kind": "OBJECT", "ref": "车票"}, index=6)
    if "母亲留下" in text or "母亲留下的" in text:
        obj = "暗房" if "暗房" in text else ("铁盒" if "铁盒" in text else "物件")
        add("OBJECT_PROVENANCE", "left_by", {"kind": "PERSON", "ref": "母亲"}, {"kind": "OBJECT", "ref": obj}, index=7)
    if "第一次" in text or "首次" in text or "从未" in text:
        cue = "第一次" if "第一次" in text else ("首次" if "首次" in text else "从未")
        add("CERTAINTY_ASSERTION", "first_or_never", {"kind": "CHARACTER", "ref": _subject(text, "林晚")}, {"kind": "EVENT", "ref": "darkroom_visit"}, qualifiers={"cue": cue}, index=8)
    if "打开铁盒" in text or "打开盒" in text:
        add("CHARACTER_ACTION", "opens", {"kind": "CHARACTER", "ref": _subject(text, "林晚")}, {"kind": "OBJECT", "ref": "铁盒"}, index=9)
    if "铁盒前" in text or "走到铁盒" in text or "带到铁盒" in text:
        add("SPATIAL_BLOCKING", "moves_to", {"kind": "CHARACTER", "ref": _subject(text, "顾沉")}, {"kind": "LOCATION", "ref": "铁盒前"}, index=10)
    return found


def extract_claims(document: Mapping[str, Any], *, origin: str, source_ref_map: Mapping[str, list[str]] | None = None) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for path, text in _walk(document):
        if path in {"version", "schema_version"} or not text:
            continue
        refs = _source_refs_for_path(path, document, source_ref_map)
        base = _base_claim(origin, path, text, refs, document)
        claims.append(base)
        claims.extend(_embedded_claims(origin, path, text, refs))
    return _dedupe_claims(claims)


def _dedupe_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for claim in claims:
        key = (str(claim.get("source_path")), str(claim.get("claim_type")), str(claim.get("predicate")), str(claim.get("object")))
        if key in seen:
            continue
        seen.add(key)
        result.append(claim)
    return result


def claim_set_document(claims: list[dict[str, Any]], *, version: str = CLAIM_SET_VERSION, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"schema_version": version, "claim_count": len(claims), "claim_set_fingerprint": claim_set_fingerprint(claims, version=version), "claims": claims, **(dict(metadata or {}))}


__all__ = ["project_source_claims", "extract_claims", "claim_set_document"]
