"""Semantic grounding and downstream-boundary checks for Director Stage B.

Stage B is allowed to propose performance and presentation intent.  It is not
allowed to invent source facts or cross into shot execution.  The helpers in
this module are deterministic and provider-free so they can be used both by
runtime gates and by forensic audits of an already persisted proposal.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Iterable, Mapping


SHOTPLAN_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("SHOT_SIZE", "shot_size", ("大特写", "特写", "近景", "中景", "全景", "远景", "半身")),
    ("CAMERA_ANGLE", "camera_angle", ("机位", "俯拍", "仰拍", "平视", "鸟瞰", "高角度", "低角度")),
    ("CAMERA_MOVEMENT", "camera_movement", ("推拉摇移", "推镜", "拉镜", "摇镜", "移镜", "跟拍", "横移", "环绕镜头")),
    ("LENS", "lens", ("焦段", "广角镜头", "长焦镜头", "鱼眼", "24mm", "35mm", "50mm", "85mm")),
    ("FRAME", "frame", ("第一帧", "最后一帧", "最后画面", "首帧", "尾帧")),
    ("SHOT_NUMBER", "shot_number", ("镜头编号", "镜头1", "镜头2", "第1镜", "第2镜", "shot 1", "shot 2")),
    ("SHOT_TRANSITION_EXECUTION", "shot_transition_execution", ("硬切", "跳切", "溶解", "淡入", "淡出", "切到", "转场")),
    ("KEYFRAME", "keyframe", ("关键帧", "keyframe")),
    ("SCENEBLOCKING", "scene_blocking", ("场面调度坐标", "blocking", "scene blocking", "走位图", "站位图", "位置坐标", "调度路径")),
)
_GENERIC_CAMERA_TERMS = ("镜头", "camera")

_KNOWLEDGE_PATTERNS = (
    "他知道", "她知道", "顾沉知道", "林晚知道", "他认识", "她认识", "他早就知道", "她早就知道",
    "他经历过", "她经历过", "他不是第一次", "她不是第一次", "他曾经", "她曾经", "他训练过", "她训练过",
    "并不陌生", "知道门外的人是谁", "不是第一次威胁",
)
_BACKSTORY_PATTERNS = ("训练出来", "更深牵连", "过往", "童年与暗房", "背后的秘密", "真实的过去", "曾经", "早就")
_EMOTIONAL_FACT_PATTERNS = ("怨恨", "憎恨", "爱恋", "嫉妒", "内疚", "依恋", "复杂的情感", "渴望、怨恨、恐惧")
_SENSORY_INVENTION_PATTERNS = ("空气里药水味", "空气中药水味", "药水味", "刺鼻的气味", "闻到", "气味")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _flatten(value: Any, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            yield from _flatten(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _flatten(item, f"{path}[{index}]")
    elif isinstance(value, str) and value.strip():
        yield path or "$", value.strip()


def _source_texts(source_authoring_units: Iterable[Any] | None) -> list[str]:
    texts: list[str] = []
    for unit in source_authoring_units or []:
        if isinstance(unit, Mapping):
            text = _text(unit.get("text") or unit.get("source_text"))
            if text:
                texts.append(text)
        elif _text(unit):
            texts.append(_text(unit))
    return texts


def audit_director_downstream_semantic_leakage(value: Any) -> dict[str, Any]:
    """Scan all textual leaves for concrete shot execution language.

    Generic presentation words such as ``视觉重点`` and ``节奏`` are not
    violations.  A violation always includes its semantic category, path and
    exact matched term for auditability.
    """
    violations: list[dict[str, Any]] = []
    for path, text in _flatten(value):
        lowered = text.lower()
        for category, label, terms in SHOTPLAN_PATTERNS:
            matched = next((term for term in terms if term.lower() in lowered), None)
            if matched:
                violations.append({"category": category, "path": path, "matched_term": matched, "text": text})
        # ``镜头`` by itself is execution language, except in the common
        # phrase ``视觉重点`` where it is not present anyway.  Keep this
        # explicit to avoid accidental false positives from ordinary prose.
        if "镜头" in text and not any(v["path"] == path and v["matched_term"] in text for v in violations):
            violations.append({"category": "SHOT_EXECUTION", "path": path, "matched_term": "镜头", "text": text})
        elif "camera" in lowered and not any(v["path"] == path and v["matched_term"].lower() == "camera" for v in violations):
            violations.append({"category": "SHOT_EXECUTION", "path": path, "matched_term": "camera", "text": text})
    # Stable order and de-duplication make evidence reproducible.
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in violations:
        key = (item["path"], item["category"], item["matched_term"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return {"status": "BLOCKED" if unique else "PASS", "violations": unique, "violation_count": len(unique)}


def build_semantic_claim_inventory(enrichment_ir: Mapping[str, Any] | None) -> dict[str, Any]:
    ir = enrichment_ir if isinstance(enrichment_ir, Mapping) else {}
    fields = (
        "beat_enrichments", "character_directions", "performance_arc", "information_strategy",
        "rhythm_strategy", "visual_priority", "scene_exit_intent", "prohibited_interpretations",
    )
    claims = []
    for path, value in _flatten({field: ir.get(field) for field in fields if field in ir}):
        if path.rsplit(".", 1)[-1] in {"character_ref", "beat_ref", "beat_id", "schema_version"}:
            continue
        claims.append({"path": path, "claim": value, "claim_kind": path.split(".")[0]})
    return {
        "schema_version": "director_semantic_claim_inventory_v1",
        "status": "PASS" if claims else "REVIEW_REQUIRED",
        "claim_count": len(claims),
        "claims": claims,
        "covered_fields": fields,
    }


def _contains_any(text: str, patterns: Iterable[str]) -> str | None:
    return next((pattern for pattern in patterns if pattern in text), None)


def audit_director_source_grounding(
    enrichment_ir: Mapping[str, Any] | None,
    *,
    source_authoring_units: Iterable[Any] | None = None,
    stage_a: Mapping[str, Any] | None = None,
    declared_participants: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Classify Stage B text against source facts and safe direction rules."""
    source_text = "\n".join(_source_texts(source_authoring_units))
    inventory = build_semantic_claim_inventory(enrichment_ir)
    if not inventory["claims"] and isinstance(enrichment_ir, Mapping):
        inventory = {**inventory, "claims": [{"path": path, "claim": value, "claim_kind": path.split(".")[0]} for path, value in _flatten(enrichment_ir)], "claim_count": sum(1 for _ in _flatten(enrichment_ir))}
    findings: list[dict[str, Any]] = []
    participants = {
        _text(item.get("id") or item.get("name") or item.get("character_ref") if isinstance(item, Mapping) else item)
        for item in (declared_participants or [])
    }
    participants.discard("")
    for claim in inventory["claims"]:
        text = claim["claim"]
        category = "SAFE_CREATIVE_DIRECTION"
        matched = None
        if text in source_text or (len(text) >= 8 and text in source_text):
            category = "SOURCE_EXPLICIT"
        elif _contains_any(text, _SENSORY_INVENTION_PATTERNS):
            # A source ``药水柜`` does not ground ``药水味``.
            if "药水味" in text and "药水味" not in source_text:
                category, matched = "UNSUPPORTED_FACT_ASSERTION", "药水味"
            else:
                category, matched = "UNSUPPORTED_FACT_ASSERTION", _contains_any(text, _SENSORY_INVENTION_PATTERNS)
        elif _contains_any(text, _KNOWLEDGE_PATTERNS):
            category, matched = "UNSUPPORTED_CHARACTER_KNOWLEDGE", _contains_any(text, _KNOWLEDGE_PATTERNS)
        elif _contains_any(text, _BACKSTORY_PATTERNS):
            category, matched = "UNSUPPORTED_BACKSTORY", _contains_any(text, _BACKSTORY_PATTERNS)
        elif _contains_any(text, _EMOTIONAL_FACT_PATTERNS):
            category, matched = "UNSUPPORTED_EMOTIONAL_FACT", _contains_any(text, _EMOTIONAL_FACT_PATTERNS)
        # The scanner is authoritative for downstream leakage.  It is run
        # separately below, but annotate claims here for a single report.
        findings.append({**claim, "classification": category, **({"matched_term": matched} if matched else {})})
    leakage = audit_director_downstream_semantic_leakage(enrichment_ir)
    for violation in leakage["violations"]:
        findings.append({
            "path": violation["path"], "claim": violation["text"],
            "classification": "DOWNSTREAM_SHOTPLAN_LEAKAGE",
            "matched_term": violation["matched_term"], "category": violation["category"],
        })
    counts: dict[str, int] = {}
    for item in findings:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1
    blocked_categories = {
        "UNSUPPORTED_FACT_ASSERTION", "UNSUPPORTED_CHARACTER_KNOWLEDGE", "UNSUPPORTED_BACKSTORY",
        "UNSUPPORTED_EMOTIONAL_FACT", "DOWNSTREAM_SHOTPLAN_LEAKAGE", "DOWNSTREAM_SCENEBLOCKING_LEAKAGE",
    }
    return {
        "schema_version": "director_source_grounding_audit_v1",
        "status": "BLOCKED" if any(item["classification"] in blocked_categories for item in findings) else "PASS",
        "findings": findings,
        "classification_counts": counts,
        "source_authority": "SourceAuthoringUnits",
        "stage_a_authority": "DERIVED_STRUCTURE",
        "stage_b_authority": "CREATIVE_PROPOSAL",
        "participant_grounding": "PASS" if all(not participants or _text(item.get("character_ref")) in participants for item in (enrichment_ir or {}).get("character_directions", []) if isinstance(item, Mapping)) else "BLOCKED",
        "stage_a_immutable": True,
    }


def validate_director_creative_semantic_review(
    enrichment_ir: Mapping[str, Any] | None = None,
    *,
    candidate: Mapping[str, Any] | None = None,
    source_authoring_units: Iterable[Any] | None = None,
    stage_a: Mapping[str, Any] | None = None,
    declared_participants: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Aggregate semantic gates without changing the candidate."""
    ir = enrichment_ir if isinstance(enrichment_ir, Mapping) else {}
    if not ir and isinstance(candidate, Mapping):
        projection = candidate.get("creative_projection") if isinstance(candidate.get("creative_projection"), Mapping) else {}
        ir = projection
    grounding = audit_director_source_grounding(ir, source_authoring_units=source_authoring_units, stage_a=stage_a, declared_participants=declared_participants)
    leakage = audit_director_downstream_semantic_leakage(ir)
    reasons = []
    stage_a_leaks = []
    if isinstance(ir, Mapping):
        stage_a_leaks.extend(sorted(set(ir).intersection({"scene_objective", "dramatic_question", "purpose", "objective", "information_change", "hook", "refs", "beat_plan", "beat_plan_ir"})))
        for path, value in _flatten(ir):
            if path.endswith(".refs") or path.endswith(".purpose") or path.endswith(".objective") or path.endswith(".information_change") or path.endswith(".hook"):
                stage_a_leaks.append(path)
    if stage_a_leaks:
        reasons.append("STAGE_A_IMMUTABILITY_VIOLATION")
    if grounding.get("status") == "BLOCKED":
        reasons.append("SOURCE_GROUNDING_BLOCKED")
    if leakage.get("status") == "BLOCKED":
        reasons.append("DOWNSTREAM_SHOTPLAN_LEAKAGE")
        if any(item.get("category") == "SCENEBLOCKING" for item in leakage.get("violations", [])):
            reasons.append("DOWNSTREAM_SCENEBLOCKING_LEAKAGE")
    if grounding.get("participant_grounding") != "PASS":
        reasons.append("PARTICIPANT_GROUNDING_BLOCKED")
    return {
        "schema_version": "director_creative_semantic_review_v1",
        "status": "BLOCKED" if reasons else "PASS",
        "decision": "SEMANTIC_REVIEW_BLOCKED" if reasons else "SEMANTIC_REVIEW_PASS",
        "reasons": reasons,
        "source_grounding": grounding,
        "downstream_leakage": leakage,
        "stage_a_immutable": not stage_a_leaks,
        "stage_a_immutability_violations": sorted(set(stage_a_leaks)),
        "production_writes_allowed": not reasons,
    }


def build_creative_enrichment_revision_preflight(*, history_count: int, authorization_granted: bool = False, provider_calls: int = 0) -> dict[str, Any]:
    """Provider-free append-only boundary for a future explicit revision."""
    expected = int(history_count) + 1
    return {
        "schema_version": "director_creative_enrichment_revision_preflight_v1",
        "status": "READY" if authorization_granted else "AUTHORIZATION_REQUIRED",
        "history_count": int(history_count), "expected_attempt": f"attempt-{expected}",
        "authoring_stage": "CREATIVE_ENRICHMENT", "authorization": "GRANTED" if authorization_granted else "NOT_GRANTED",
        "provider_calls": int(provider_calls), "append_only": True, "production_mutation": False,
    }


__all__ = [
    "audit_director_downstream_semantic_leakage", "build_semantic_claim_inventory",
    "audit_director_source_grounding", "validate_director_creative_semantic_review",
    "build_creative_enrichment_revision_preflight",
    "audit_source_grounding", "scan_director_downstream_semantic_leakage",
]

# Short aliases keep the audit helpers convenient for CLI/evidence scripts.
audit_source_grounding = audit_director_source_grounding
scan_director_downstream_semantic_leakage = audit_director_downstream_semantic_leakage
