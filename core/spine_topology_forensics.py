"""Deterministic forensic helpers for the Director V3 spine/topology layers.

These helpers deliberately do not infer creative meaning from prose.  They
only consume structured authority traces, exact enums and explicit references;
unknown mappings remain review-required.
"""
from __future__ import annotations

import re
from typing import Any

ROLE_ENUM = {
    "ORIENT", "ESTABLISH", "OBSERVE", "PRESSURE", "REACTION", "EVIDENCE",
    "INSERT", "REVEAL", "TURN", "HOLD", "TRANSITION", "RELEASE", "CLOSING",
}

ROLE_ALIASES = {
    "ESTABLISHING": "ESTABLISH", "ESTABLISHMENT": "ESTABLISH",
    "ORIENTATION": "ORIENT", "OBSERVATION": "OBSERVE",
    "PRESSURE_BUILD": "PRESSURE", "REVEALING": "REVEAL",
    "INSERT_DETAIL": "INSERT", "TRANSITIONAL": "TRANSITION",
    "CLOSURE": "CLOSING",
}
ROLE_AMBIGUOUS = {"DISCOVERY", "INVESTIGATION", "CHARACTER_ACTION", "HIDDEN_LEAK", "DIALOGUE_CONFLICT", "POWER_SHIFT", "PROP_FOCUS", "ENTRANCE", "SCENE_END", "CLIMAX"}


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _t(value: Any) -> str:
    return str(value or "").strip()


def build_must_preserve_trace(strategy: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any]:
    """Build a trace from explicit authority metadata only.

    A strategy may provide ``must_preserve_trace`` directly.  Otherwise the
    existing source-trace support refs are used only when they explicitly name
    a constraint/claim.  No keyword or embedding matching is performed.
    """
    explicit = _l(strategy.get("must_preserve_trace"))
    preserve = [_t(x) for x in _l(strategy.get("must_preserve")) if _t(x)]
    source = _d(strategy.get("source_trace"))
    claims: list[dict[str, Any]] = []
    for phase in _l(source.get("phases")):
        for key in ("audience_suspicions", "director_inferences"):
            for item in _l(_d(phase).get(key)):
                row = _d(item)
                claims.append({"claim": _t(row.get("claim")), "support_refs": [_t(x) for x in _l(row.get("support_refs")) if _t(x)]})
    trace: list[dict[str, Any]] = []
    for index, constraint in enumerate(preserve, 1):
        row = next((_d(x) for x in explicit if _t(_d(x).get("constraint")) == constraint), None)
        if row:
            refs = [_t(x) for x in _l(row.get("supporting_beat_refs")) if _t(x)]
            trace.append({"constraint_id": _t(row.get("constraint_id")) or f"MP{index:02d}", "description": constraint, "supporting_beat_refs": refs, "supporting_event_keys": [_t(x) for x in _l(row.get("supporting_event_keys")) if _t(x)], "source": "explicit", "status": "RESOLVED" if refs or row.get("supporting_event_keys") else "PRESERVE_TRACE_UNRESOLVED"})
            continue
        match = next((c for c in claims if c["claim"] and c["claim"] == constraint), None)
        if match:
            trace.append({"constraint_id": f"MP{index:02d}", "description": constraint, "supporting_beat_refs": match["support_refs"], "supporting_event_keys": [], "source": "source_trace_claim", "status": "RESOLVED" if match["support_refs"] else "PRESERVE_TRACE_UNRESOLVED"})
        else:
            trace.append({"constraint_id": f"MP{index:02d}", "description": constraint, "supporting_beat_refs": [], "supporting_event_keys": [], "source": "authority_only_no_explicit_binding", "status": "PRESERVE_TRACE_UNRESOLVED"})
    return {"schema_version": "must_preserve_trace_v1", "scene_id": _t(scene.get("scene_id")), "constraints": trace, "unresolved_count": sum(x["status"] == "PRESERVE_TRACE_UNRESOLVED" for x in trace), "resolution_policy": "structured beat/event refs only; no prose similarity"}


def evaluate_preserve_coverage(spine: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    segments = _l(spine.get("segments")); covered = []
    for item in _l(trace.get("constraints")):
        refs = set(_t(x) for x in _l(item.get("supporting_beat_refs")) if _t(x))
        segment_refs = { _t(x) for seg in segments for x in _l(_d(seg).get("beat_refs")) if _t(x) }
        if item.get("status") == "PRESERVE_TRACE_UNRESOLVED":
            status = "PRESERVE_TRACE_UNRESOLVED"
        else:
            status = "COVERED" if refs & segment_refs else "UNCOVERED"
        covered.append({"constraint_id": item.get("constraint_id"), "status": status, "supporting_beat_refs": sorted(refs), "matched_segment_count": sum(bool(refs & {_t(x) for x in _l(_d(seg).get("beat_refs"))}) for seg in segments)})
    return {"schema_version": "must_preserve_coverage_v1", "status": "PASS" if all(x["status"] in {"COVERED", "PRESERVE_TRACE_UNRESOLVED"} for x in covered) else "FAIL", "constraints": covered, "unresolved_count": sum(x["status"] == "PRESERVE_TRACE_UNRESOLVED" for x in covered)}


def classify_role(value: Any) -> dict[str, Any]:
    raw = _t(value); upper = raw.upper()
    if upper in ROLE_ENUM:
        return {"raw": raw, "classification": "EXACT", "canonical": upper}
    alias = ROLE_ALIASES.get(upper)
    if alias:
        return {"raw": raw, "classification": "ROLE_SEMANTICALLY_RECOVERABLE", "canonical": alias}
    if upper in ROLE_AMBIGUOUS:
        return {"raw": raw, "classification": "ROLE_SEMANTIC_REVIEW_REQUIRED", "canonical": None, "reason": "ambiguous"}
    if not raw:
        return {"raw": raw, "classification": "ROLE_UNSUPPORTED", "canonical": None}
    return {"raw": raw, "classification": "ROLE_UNSUPPORTED", "canonical": None}


def resolve_segment_ref(value: Any, *, allowed_segment_refs: set[str], phase_ids: set[str] | None = None) -> dict[str, Any]:
    raw = _t(value); allowed = set(allowed_segment_refs)
    if raw in allowed:
        return {"raw": raw, "classification": "EXACT", "canonical": raw}
    match = re.fullmatch(r"(?:P|PHASE[_-]?|SEGMENT[_-]?)(\d+)", raw.upper())
    if match:
        candidate = f"SEG{int(match.group(1)):02d}"
        if candidate in allowed and (not phase_ids or raw.upper().startswith("P")):
            return {"raw": raw, "classification": "SEGMENT_REF_SEMANTICALLY_RECOVERABLE", "canonical": candidate}
    return {"raw": raw, "classification": "SEGMENT_REF_AMBIGUOUS" if raw else "SEGMENT_REF_UNRESOLVED", "canonical": None}


def compare_identity_projection(provider: Any, runtime: Any) -> dict[str, Any]:
    def records(value: Any) -> dict[str, str]:
        source = _d(value); rows = _l(source.get("records")) if "records" in source else _l(value)
        return {_t(_d(x).get("character_id")): _t(_d(x).get("name")) for x in rows if _t(_d(x).get("character_id"))}
    left, right = records(provider), records(runtime)
    return {"status": "PASS" if left == right else "FAIL", "provider": left, "runtime": right, "mismatches": sorted(set(left) ^ set(right) | {k for k in set(left) & set(right) if left[k] != right[k]})}


def detect_spine_layer_leakage(raw_text: str) -> dict[str, Any]:
    text = _t(raw_text)
    material_terms = ("特写", "全景", "固定镜头", "推近", "正反打", "过肩", "close-up", "wide shot", "shot-reverse-shot")
    severe_terms = ("50mm", "机位序列", "镜头1", "镜头2", "逐镜头")
    material = sorted({term for term in material_terms if term.lower() in text.lower()})
    severe = sorted({term for term in severe_terms if term.lower() in text.lower()})
    if severe:
        severity = "SEVERE"
    elif material:
        severity = "MATERIAL"
    elif any(term in text for term in ("聚焦", "停留", "凝视")):
        severity = "MINOR"
    else:
        severity = "NONE"
    return {"schema_version": "spine_layer_leakage_v1", "status": "PASS" if severity in {"NONE", "MINOR"} else "REVIEW", "severity": severity, "material_terms": material, "severe_terms": severe, "finding_code": "SPINE_LAYER_LEAKAGE_EXECUTION_LANGUAGE" if severity != "NONE" else None}


def skeleton_callable_after_spine(spine_protocol_valid: bool) -> dict[str, Any]:
    return {"spine_protocol_valid": bool(spine_protocol_valid), "skeleton_provider_callable": bool(spine_protocol_valid), "policy": "Spine hard invalid blocks Skeleton provider call"}
