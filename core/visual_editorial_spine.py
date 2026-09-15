"""Visual / Editorial Spine IR and deterministic validation.

The spine owns macro visual progression, attention and editorial rhythm.  It
intentionally has no shot-size, lens, camera or shot-id fields.
"""
from __future__ import annotations
import hashlib, json, re
from typing import Any

SPINE_SCHEMA = "visual_editorial_spine_ir_v1"
SPINE_FIELDS = {"schema_version", "scene_id", "strategy_fingerprint", "spine_summary", "segments"}
SEGMENT_FIELDS = {"segment_key", "phase_ids", "beat_refs", "dramatic_function", "audience_attention", "performance_pressure", "information_change", "spatial_focus", "visual_motif", "editorial_rhythm", "entry_condition", "exit_condition"}
FORBIDDEN_FIELDS = {"shot_size", "shot_id", "camera_lens", "lens", "camera_movement", "camera_position", "shot_count", "lighting"}

def _d(v: Any) -> dict[str, Any]: return v if isinstance(v, dict) else {}
def _l(v: Any) -> list[Any]: return v if isinstance(v, list) else []
def _t(v: Any) -> str: return str(v or "").strip()
def _canon(v: Any) -> str: return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def fingerprint(v: Any) -> str: return hashlib.sha256(_canon(v).encode()).hexdigest()
def _ref(v: Any, namespace: str = "beat") -> str:
    text = _t(v)
    if not text: return ""
    if ":" in text: return text
    return f"{namespace}:{text[1:] if namespace == 'beat' and text.upper().startswith('B') else text}"

def normalize_spine(raw: dict[str, Any], *, scene_id: str, strategy_fingerprint: str) -> dict[str, Any]:
    if not isinstance(raw, dict): return {"status": "FAIL", "errors": [{"code": "SPINE_NOT_OBJECT"}], "ir": None}
    errors = [{"code": "UNKNOWN_SPINE_FIELD", "field": k} for k in raw if k not in SPINE_FIELDS]
    segments = []
    for index, value in enumerate(_l(raw.get("segments")), 1):
        row = _d(value); unknown = sorted(k for k in row if k not in SEGMENT_FIELDS)
        errors += [{"code": "UNKNOWN_SPINE_SEGMENT_FIELD", "segment_index": index, "field": k} for k in unknown]
        beat_values = row.get("beat_refs") if "beat_refs" in row else row.get("beats")
        phase_values = row.get("phase_ids") if "phase_ids" in row else row.get("phases")
        segments.append({
            "segment_key": f"SEG{index:02d}",
            "phase_ids": [_t(x) for x in _l(phase_values) if _t(x)],
            "beat_refs": [_ref(x) for x in _l(beat_values) if _t(x)],
            "dramatic_function": _t(row.get("dramatic_function")), "audience_attention": _t(row.get("audience_attention")),
            "performance_pressure": _t(row.get("performance_pressure")), "information_change": _t(row.get("information_change")),
            "spatial_focus": _t(row.get("spatial_focus")), "visual_motif": _t(row.get("visual_motif")),
            "editorial_rhythm": _t(row.get("editorial_rhythm")), "entry_condition": _t(row.get("entry_condition")),
            "exit_condition": _t(row.get("exit_condition")),
        })
    ir = {"schema_version": SPINE_SCHEMA, "scene_id": scene_id, "strategy_fingerprint": strategy_fingerprint, "spine_summary": _t(raw.get("spine_summary") or raw.get("summary")), "segments": segments}
    return {"status": "FAIL" if errors else "PASS", "errors": errors, "ir": ir, "spine_fingerprint": fingerprint(ir)}

_TRACE_UNSET = object()

def validate_spine(spine: dict[str, Any], *, scene: dict[str, Any], strategy: dict[str, Any], must_preserve_trace: dict[str, Any] | None | object = _TRACE_UNSET) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []; warnings: list[dict[str, Any]] = []
    if _t(spine.get("schema_version")) != SPINE_SCHEMA: errors.append({"code": "SPINE_SCHEMA_INVALID"})
    if _t(spine.get("scene_id")) != _t(scene.get("scene_id")): errors.append({"code": "SPINE_SCENE_MISMATCH"})
    if _t(strategy.get("strategy_fingerprint")) and _t(spine.get("strategy_fingerprint")) != _t(strategy.get("strategy_fingerprint")):
        errors.append({"code": "SPINE_STRATEGY_MISMATCH"})
    beats = [_ref(_d(b).get("beat_id")) for b in _l(scene.get("beats")) if _t(_d(b).get("beat_id"))]
    beat_order = {ref: i for i, ref in enumerate(beats)}; phases = {_t(p.get("phase_id")): {_ref(x) for x in _l(p.get("beat_ids"))} for p in _l(strategy.get("scene_phases")) if isinstance(p, dict)}
    covered = []; previous = -1; previous_phase = -1
    phase_order = {_t(p.get("phase_id")): i for i, p in enumerate(_l(strategy.get("scene_phases"))) if isinstance(p, dict)}
    for segment in _l(spine.get("segments")):
        refs = [_t(x) for x in _l(_d(segment).get("beat_refs"))]
        if not refs: errors.append({"code": "SPINE_SEGMENT_BEATS_EMPTY", "segment_key": _d(segment).get("segment_key")})
        for ref in refs:
            if ref not in beat_order: errors.append({"code": "SPINE_UNKNOWN_BEAT", "segment_key": _d(segment).get("segment_key"), "reference": ref})
            elif beat_order[ref] < previous: errors.append({"code": "SPINE_BEAT_CHRONOLOGY_VIOLATION", "segment_key": _d(segment).get("segment_key"), "reference": ref})
            else: previous = beat_order[ref]
            covered.append(ref)
        for phase in _l(_d(segment).get("phase_ids")):
            if phase not in phases: errors.append({"code": "SPINE_UNKNOWN_PHASE", "segment_key": _d(segment).get("segment_key"), "phase_id": phase})
            elif refs and not set(refs) & phases[phase]: errors.append({"code": "SPINE_PHASE_BEAT_MISMATCH", "segment_key": _d(segment).get("segment_key"), "phase_id": phase})
            elif phase_order.get(phase, -1) < previous_phase:
                errors.append({"code": "SPINE_SEGMENT_CHRONOLOGY_VIOLATION", "segment_key": _d(segment).get("segment_key"), "phase_id": phase})
            else:
                previous_phase = phase_order.get(phase, previous_phase)
        required = ("dramatic_function", "audience_attention", "performance_pressure", "information_change", "spatial_focus", "visual_motif", "editorial_rhythm", "entry_condition", "exit_condition")
        for field in required:
            if not _t(_d(segment).get(field)): errors.append({"code": "SPINE_FIELD_MISSING", "segment_key": _d(segment).get("segment_key"), "field": field})
        forbidden = sorted(set(_d(segment)) & FORBIDDEN_FIELDS)
        errors += [{"code": "FORBIDDEN_LAYER_FIELD", "segment_key": _d(segment).get("segment_key"), "field": field} for field in forbidden]
        # A segment cannot reveal a beat that is not yet in its own temporal
        # scope.  Explicit beat refs in creative prose are checked so future
        # information leaks fail closed without trying to interpret prose.
        max_index = max((beat_order.get(ref, -1) for ref in refs), default=-1)
        prose = " ".join(_t(_d(segment).get(field)) for field in SEGMENT_FIELDS if field not in {"segment_key", "phase_ids", "beat_refs"})
        for leaked in re.findall(r"(?:beat\s*[:#]?\s*)(\w+)", prose, flags=re.IGNORECASE):
            leaked_ref = _ref(leaked)
            if leaked_ref in beat_order and beat_order[leaked_ref] > max_index:
                errors.append({"code": "SPINE_FUTURE_INFORMATION_LEAK", "segment_key": _d(segment).get("segment_key"), "reference": leaked_ref})
    missing = sorted(set(beats) - set(covered)); errors += [{"code": "SPINE_ORPHAN_REQUIRED_BEAT", "reference": x} for x in missing]
    required_phases = set(phases); covered_phases = {p for s in _l(spine.get("segments")) for p in _l(_d(s).get("phase_ids"))}; errors += [{"code": "SPINE_ORPHAN_PHASE", "phase_id": x} for x in sorted(required_phases - covered_phases)]
    # Preserve coverage is authority-trace based.  The omitted argument is
    # retained only for legacy callers; Final Re-Canary passes the trace
    # explicitly and fails closed when it is missing.
    if must_preserve_trace is None:
        errors.append({"code": "PRESERVE_AUTHORITY_MISSING"})
    elif must_preserve_trace is not _TRACE_UNSET:
        for item in _l(_d(must_preserve_trace).get("constraints")):
            refs = {_t(x) for x in _l(_d(item).get("supporting_beat_refs")) if _t(x)}
            if _t(item.get("status")) == "PRESERVE_TRACE_UNRESOLVED":
                errors.append({"code": "PRESERVE_TRACE_UNRESOLVED", "constraint_id": _t(item.get("constraint_id"))})
            elif refs and not refs & set(covered):
                errors.append({"code": "SPINE_MUST_PRESERVE_UNCOVERED", "constraint_id": _t(item.get("constraint_id")), "supporting_beat_refs": sorted(refs)})
    avoid = [_t(x) for x in _l(strategy.get("must_avoid")) if _t(x)]; joined = _canon(spine)
    errors += [{"code": "SPINE_MUST_AVOID_VIOLATION", "constraint": x} for x in avoid if x and x in joined]
    return {"status": "PASS" if not errors else "FAIL", "hard_errors": errors, "warnings": warnings, "covered_beats": sorted(set(covered)), "missing_beats": missing, "covered_phases": sorted(covered_phases), "missing_phases": sorted(required_phases - covered_phases)}

def compile_spine(raw: dict[str, Any], *, scene_id: str, strategy: dict[str, Any]) -> dict[str, Any]:
    result = normalize_spine(raw, scene_id=scene_id, strategy_fingerprint=_t(strategy.get("strategy_fingerprint")))
    if not result.get("ir"): return result
    validation = validate_spine(result["ir"], scene={"scene_id": scene_id, "beats": strategy.get("beats", [])}, strategy=strategy)
    return {**result, "validation": validation, "status": "PASS" if result["status"] == "PASS" and validation["status"] == "PASS" else "FAIL"}
