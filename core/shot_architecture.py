"""Shot Architecture Draft IR, canonicalizer and deterministic validators."""
from __future__ import annotations

import hashlib, json, re
from collections import Counter
from typing import Any

PROGRAM_OWNED = {"architecture_fingerprint", "compiler_version", "source_trace", "authority_projection", "qa_metrics"}
REQUIRED_SHOT_FIELDS = ("phase_id", "beat_refs", "function", "subject", "shot_size", "camera_position", "camera_movement", "composition_intent", "performance_focus", "information_focus", "prop_focus", "spatial_anchor", "entry_state", "exit_state", "cut_in_motivation", "cut_out_motivation", "hold_logic", "continuity_requirements", "must_preserve_refs")
FUNCTIONS = {"ESTABLISH", "ORIENT", "OBSERVE", "PRESSURE", "REACTION", "EVIDENCE", "INSERT", "REVEAL", "TURN", "HOLD", "TRANSITION", "RELEASE", "CLOSING"}
MOVEMENTS = {"STATIC", "PAN", "TILT", "PUSH_IN", "PULL_OUT", "TRACK", "DOLLY", "HANDHELD_SUBTLE", "REFRAME", "NONE"}
SIZES = {"EWS", "WS", "MWS", "MS", "MCU", "CU", "ECU", "INSERT"}

def _d(v: Any) -> dict[str, Any]: return v if isinstance(v, dict) else {}
def _l(v: Any) -> list[Any]: return v if isinstance(v, list) else []
def _t(v: Any) -> str: return str(v or "").strip()
def _canon(v: Any) -> str: return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def fingerprint(v: Any) -> str: return hashlib.sha256(_canon(v).encode("utf-8")).hexdigest()

def _alias(v: Any, mapping: dict[str, str], default: str = "") -> str:
    raw = _t(v)
    if raw.upper() in mapping.values():
        return raw.upper()
    exact = mapping.get(raw.upper(), mapping.get(raw, default))
    if exact:
        return exact
    # Providers sometimes return a short Chinese phrase instead of the enum
    # alias (e.g. “从全景开始建立空间”).  Deterministic keyword normalization
    # is safe here because it only maps to the fixed enum vocabulary.
    for alias, target in mapping.items():
        if alias and alias in raw:
            return target
    return default

FUNCTION_ALIASES = {"建立": "ESTABLISH", "建立空间": "ESTABLISH", "定位": "ORIENT", "观察": "OBSERVE", "施压": "PRESSURE", "压力": "PRESSURE", "反应": "REACTION", "证据": "EVIDENCE", "插入": "INSERT", "揭示": "REVEAL", "转折": "TURN", "停顿": "HOLD", "过渡": "TRANSITION", "释放": "RELEASE", "收束": "CLOSING", "结尾": "CLOSING"}
SIZE_ALIASES = {"远景": "EWS", "全景": "WS", "中远景": "MWS", "中景": "MS", "中近景": "MCU", "近景": "CU", "特写": "CU", "大特写": "ECU", "插入特写": "INSERT"}
MOVE_ALIASES = {"固定": "STATIC", "静止": "STATIC", "无": "NONE", "无运动": "NONE", "轻微推进": "PUSH_IN", "推进": "PUSH_IN", "拉远": "PULL_OUT", "横摇": "PAN", "跟拍": "TRACK", "轻微手持": "HANDHELD_SUBTLE", "重新构图": "REFRAME"}

def _ref(value: Any, prefix: str) -> str:
    raw = _t(value)
    if not raw: return ""
    if raw.startswith(prefix + ":"): return raw
    return prefix + ":" + raw

def normalize_architecture_ir(raw: dict[str, Any], *, scene_id: str, strategy_fingerprint: str) -> dict[str, Any]:
    """Project model-facing output into the small canonical Draft schema."""
    if not isinstance(raw, dict): return {"errors": [{"code": "ARCHITECTURE_NOT_OBJECT"}], "ir": None}
    unknown = sorted(k for k in raw if k not in {"scene_id", "schema_version", "strategy_fingerprint", "architecture_summary", "shots", "shot_count", "notes", *PROGRAM_OWNED})
    shots = _l(raw.get("shots")); canonical_shots = []
    for i, item in enumerate(shots, 1):
        row = _d(item)
        functions = _l(row.get("function")) if isinstance(row.get("function"), list) else [_t(row.get("function"))]
        functions = [_alias(x, FUNCTION_ALIASES, "") for x in functions if _alias(x, FUNCTION_ALIASES, "")]
        canonical_shots.append({
            "shot_id": f"SA{i:02d}",
            "logical_key": _t(row.get("logical_key") or row.get("ordinal") or f"shot-{i}"),
            "phase_id": _t(row.get("phase_id")),
            "beat_refs": [_ref(x, "beat") for x in _l(row.get("beat_refs") or row.get("beats"))],
            "function": functions or ["OBSERVE"],
            "subject": _t(row.get("subject")),
            "shot_size": _alias(row.get("shot_size") or row.get("size"), SIZE_ALIASES, ""),
            "camera_position": _t(row.get("camera_position") or row.get("camera")),
            "camera_movement": _alias(row.get("camera_movement") or row.get("movement"), MOVE_ALIASES, ""),
            "composition_intent": _t(row.get("composition_intent") or row.get("composition")),
            "performance_focus": _t(row.get("performance_focus") or row.get("performance")),
            "information_focus": _t(row.get("information_focus") or row.get("information")),
            "prop_focus": _t(row.get("prop_focus") or row.get("props") or "none"),
            "spatial_anchor": _t(row.get("spatial_anchor") or row.get("anchor")),
            "entry_state": _t(row.get("entry_state") or row.get("entry")),
            "exit_state": _t(row.get("exit_state") or row.get("exit")),
            "cut_in_motivation": _t(row.get("cut_in_motivation") or row.get("cut_in")),
            "cut_out_motivation": _t(row.get("cut_out_motivation") or row.get("cut_out")),
            "hold_logic": _t(row.get("hold_logic") or row.get("hold")),
            "continuity_requirements": _l(row.get("continuity_requirements") or row.get("continuity")),
            "must_preserve_refs": _l(row.get("must_preserve_refs") or row.get("must_preserve")),
            "what_audience_knows_before": _t(row.get("what_audience_knows_before") or row.get("audience_before")),
            "what_this_shot_adds": _t(row.get("what_this_shot_adds") or row.get("audience_adds")),
            "what_remains_withheld": _t(row.get("what_remains_withheld") or row.get("withheld")),
        })
    ir = {"scene_id": scene_id, "schema_version": "shot_architecture_draft_v1", "strategy_fingerprint": strategy_fingerprint, "architecture_summary": _t(raw.get("architecture_summary") or raw.get("summary")), "shot_count": len(canonical_shots), "shots": canonical_shots, "notes": _l(raw.get("notes")), "compiler_version": "shot_architecture_compiler_v1", "architecture_fingerprint": "", "source_trace": {"strategy_fingerprint": strategy_fingerprint, "provider_shot_ids_ignored": True}}
    ir["architecture_fingerprint"] = fingerprint({k: v for k, v in ir.items() if k not in PROGRAM_OWNED})
    errors = [{"code": "UNKNOWN_CREATIVE_FIELD", "field": x} for x in unknown]
    return {"ir": ir, "errors": errors, "unknown_fields": unknown, "projection_status": "PASS" if not unknown else "FAIL"}

def validate_protocol(ir: dict[str, Any], *, scene: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if not isinstance(ir, dict): return {"valid": False, "errors": [{"code": "ARCHITECTURE_NOT_OBJECT"}]}
    if _t(ir.get("scene_id")) != _t(scene.get("scene_id")): errors.append({"code": "SCENE_ID_MISMATCH"})
    if _t(ir.get("schema_version")) != "shot_architecture_draft_v1": errors.append({"code": "SCHEMA_VERSION_INVALID"})
    shots = _l(ir.get("shots")); ids = [_t(x.get("shot_id")) for x in shots if isinstance(x, dict)]
    if not shots: errors.append({"code": "SHOT_LIST_EMPTY"})
    if len(ids) != len(set(ids)): errors.append({"code": "DUPLICATE_SHOT_ID"})
    allowed_beats = {_ref(_d(b).get("beat_id"), "beat") for b in _l(scene.get("beats")) if _t(_d(b).get("beat_id"))}
    allowed_chars = {_t(_d(c).get("character_id")) for c in _l(_d(scene.get("characters")).get("records")) if _t(_d(c).get("character_id"))}
    allowed_chars |= {_t(_d(c).get("character_id")) for c in _l(_d(strategy.get("character_registry")).get("records")) if _t(_d(c).get("character_id"))}
    phases = {_t(p.get("phase_id")): {_ref(x, "beat") for x in _l(p.get("beat_ids"))} for p in _l(strategy.get("scene_phases")) if isinstance(p, dict)}
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict): errors.append({"code": "SHOT_NOT_OBJECT", "index": i}); continue
        for field in REQUIRED_SHOT_FIELDS:
            if field not in shot or (not _l(shot[field]) and not _t(shot[field])): errors.append({"code": "SHOT_FIELD_MISSING", "shot_id": shot.get("shot_id"), "field": field})
        refs = set(_t(x) for x in _l(shot.get("beat_refs")))
        for ref in refs - allowed_beats: errors.append({"code": "UNKNOWN_BEAT_REFERENCE", "shot_id": shot.get("shot_id"), "reference": ref})
        phase = _t(shot.get("phase_id"))
        if phase and phase not in phases: errors.append({"code": "UNKNOWN_PHASE", "shot_id": shot.get("shot_id"), "phase_id": phase})
        if phase in phases and not (refs & phases[phase]): errors.append({"code": "PHASE_BEAT_MISMATCH", "shot_id": shot.get("shot_id"), "phase_id": phase})
        for match in re.findall(r"character:(\w+)", _canon(shot)):
            if match not in allowed_chars: errors.append({"code": "UNKNOWN_CHARACTER_REFERENCE", "shot_id": shot.get("shot_id"), "reference": f"character:{match}"})
        if _t(shot.get("shot_size")) not in SIZES: errors.append({"code": "SHOT_SIZE_INVALID", "shot_id": shot.get("shot_id")})
        if not all(_t(x) in FUNCTIONS for x in _l(shot.get("function"))): errors.append({"code": "SHOT_FUNCTION_INVALID", "shot_id": shot.get("shot_id")})
        if _t(shot.get("camera_movement")) not in MOVEMENTS: errors.append({"code": "CAMERA_MOVEMENT_INVALID", "shot_id": shot.get("shot_id")})
    return {"valid": not errors, "errors": errors, "allowed_beats": sorted(allowed_beats), "allowed_characters": sorted(allowed_chars)}

def validate_coverage(ir: dict[str, Any], strategy: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any]:
    shots = _l(ir.get("shots")); covered = {_t(x) for s in shots for x in _l(_d(s).get("beat_refs"))}; all_beats = {_ref(_d(b).get("beat_id"), "beat") for b in _l(scene.get("beats")) if _t(_d(b).get("beat_id"))}; phases = {_t(p.get("phase_id")) for p in _l(strategy.get("scene_phases")) if isinstance(p, dict)}; covered_phases = {_t(_d(s).get("phase_id")) for s in shots}
    return {"beat_coverage": len(covered & all_beats) == len(all_beats), "phase_coverage": phases <= covered_phases, "covered_beats": sorted(covered), "missing_beats": sorted(all_beats - covered), "covered_phases": sorted(covered_phases), "missing_phases": sorted(phases - covered_phases), "status": "PASS" if all_beats <= covered and phases <= covered_phases else "FAIL"}

def validate_spatial(ir: dict[str, Any], blocking: dict[str, Any]) -> dict[str, Any]:
    anchors = {_t(p.get("anchor")) for p in _l(blocking.get("participants")) if _t(_d(p).get("anchor"))}; errors = []
    for s in _l(ir.get("shots")):
        anchor = _t(_d(s).get("spatial_anchor")); low = anchor.lower()
        if not anchor or low in {"unknown", "tbd", "n/a"}: errors.append({"code": "SPATIAL_ANCHOR_UNKNOWN", "shot_id": _d(s).get("shot_id")})
    return {"status": "PASS" if not errors else "FAIL", "hard_errors": errors, "known_blocking_anchors": sorted(anchors)}

def validate_topology(ir: dict[str, Any]) -> dict[str, Any]:
    shots = _l(ir.get("shots")); errors=[]; warnings=[]
    for a,b in zip(shots, shots[1:]):
        if (_l(_d(a).get("function")) == _l(_d(b).get("function")) and _t(_d(a).get("subject")) == _t(_d(b).get("subject")) and _t(_d(a).get("information_focus")) == _t(_d(b).get("information_focus")) and _t(_d(a).get("performance_focus")) == _t(_d(b).get("performance_focus"))): errors.append({"code": "REDUNDANT_SHOT", "shot_ids": [_d(a).get("shot_id"), _d(b).get("shot_id")]})
    for index, shot in enumerate(shots):
        funcs = set(_l(_d(shot).get("function")))
        if "REACTION" in funcs and (index == 0 or not (set(_l(_d(shots[index - 1]).get("function"))) & {"EVIDENCE", "REVEAL", "PRESSURE", "TURN"})):
            errors.append({"code": "REACTION_WITHOUT_STIMULUS", "shot_id": _d(shot).get("shot_id")})
        if "EVIDENCE" in funcs and index and "REACTION" in set(_l(_d(shots[index - 1]).get("function"))):
            warnings.append({"code": "EVIDENCE_AFTER_REACTION", "shot_id": _d(shot).get("shot_id")})
        if index and not _t(_d(shot).get("cut_in_motivation")):
            errors.append({"code": "ISOLATED_SHOT", "shot_id": _d(shot).get("shot_id")})
    if shots:
        beat_sets = [_l(_d(s).get("beat_refs")) for s in shots]
        if len(shots) > 1 and all(len(refs) == 1 for refs in beat_sets) and len({refs[0] for refs in beat_sets if refs}) == len(shots):
            warnings.append({"code": "MECHANICAL_BEAT_TO_SHOT_MAPPING"})
    if len(shots) > 30: warnings.append({"code": "SHOT_COUNT_EXTREME"})
    return {"status": "PASS" if not errors else "FAIL", "hard_errors": errors, "warnings": warnings, "redundancy_count": sum(1 for e in errors if e["code"] == "REDUNDANT_SHOT")}

def validate_information(ir: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any]:
    order = {_ref(_d(b).get("beat_id"), "beat"): i for i,b in enumerate(_l(scene.get("beats"))) if _t(_d(b).get("beat_id"))}; leaks=[]
    for s in _l(ir.get("shots")):
        refs=[r for r in _l(_d(s).get("beat_refs")) if r in order]
        if refs != sorted(refs, key=lambda r: order[r]): leaks.append({"code": "BEAT_ORDER_VIOLATION", "shot_id": _d(s).get("shot_id")})
        text = _canon(s)
        if "确认第三方" in text or "确定第三方存在" in text: leaks.append({"code": "FUTURE_INFORMATION_LEAK", "shot_id": _d(s).get("shot_id")})
    return {"status": "PASS" if not leaks else "FAIL", "future_information_leak_count": sum(e["code"] == "FUTURE_INFORMATION_LEAK" for e in leaks), "hard_errors": leaks}

def validate_content_constraints(ir: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    preserve = [_t(x) for x in _l(strategy.get("must_preserve")) if _t(x)]
    avoid = [_t(x) for x in _l(strategy.get("must_avoid")) if _t(x)]
    joined = _canon(ir)
    covered = [item for item in preserve if any(item in _canon(_d(s).get("must_preserve_refs")) or item in _canon(s) for s in _l(ir.get("shots")))]
    violations = [{"code": "MUST_AVOID_VIOLATION", "constraint": item} for item in avoid if item and item in joined]
    missing = [item for item in preserve if item not in covered]
    errors = violations + ([{"code": "MUST_PRESERVE_UNCOVERED", "constraint": item} for item in missing])
    return {"status": "PASS" if not errors else "FAIL", "must_preserve_total": len(preserve), "must_preserve_covered": len(covered), "missing_must_preserve": missing, "must_avoid_violations": violations, "hard_errors": errors}

def director_qa(ir: dict[str, Any], strategy: dict[str, Any], topology: dict[str, Any]) -> dict[str, Any]:
    shots=_l(ir.get("shots")); warnings=[]; scores=[]
    if not _t(ir.get("architecture_summary")) or not (3 <= len(_t(ir.get("architecture_summary")).split("。") ) <= 10): warnings.append({"code":"ARCHITECTURE_SUMMARY_WEAK"})
    if all(len(_l(_d(s).get("function"))) == 1 for s in shots) and len({tuple(_l(_d(s).get("function"))) for s in shots}) <= 2: warnings.append({"code":"MECHANICAL_DIALOGUE_COVERAGE"})
    if topology.get("redundancy_count"): warnings.append({"code":"REDUNDANT_SHOT"})
    warnings.extend(w for w in _l(topology.get("warnings")) if _t(_d(w).get("code")) in {"MECHANICAL_BEAT_TO_SHOT_MAPPING", "EVIDENCE_AFTER_REACTION"})
    for s in shots:
        if not _t(_d(s).get("cut_in_motivation")) or not _t(_d(s).get("cut_out_motivation")): warnings.append({"code":"CUT_MOTIVATION_MISSING","shot_id":_d(s).get("shot_id")})
        if not _t(_d(s).get("hold_logic")): warnings.append({"code":"HOLD_LOGIC_MISSING","shot_id":_d(s).get("shot_id")})
    # Strong/usable is an architecture signal, not the legacy DQ score.
    required_ok = sum(bool(_t(_d(s).get("cut_in_motivation"))) and bool(_t(_d(s).get("hold_logic"))) for s in shots)
    signal = "SHOT_ARCHITECTURE_STRONG" if shots and required_ok == len(shots) and not warnings else "SHOT_ARCHITECTURE_USABLE" if shots and required_ok >= max(1, len(shots)//2) else "SHOT_ARCHITECTURE_WEAK"
    return {"signal": signal, "warnings": warnings, "mechanical_dialogue_coverage": sum(w["code"] == "MECHANICAL_DIALOGUE_COVERAGE" for w in warnings), "visual_overload": 0}

def transition_graph(ir: dict[str, Any]) -> list[dict[str, Any]]:
    shots=_l(ir.get("shots")); return [{"from_shot":_d(a).get("shot_id"),"to_shot":_d(b).get("shot_id"),"transition_reason":_t(_d(b).get("cut_in_motivation"))} for a,b in zip(shots,shots[1:])]

def compare_architectures(items: list[dict[str, Any]]) -> dict[str, Any]:
    pairs=[]; hard=False
    for i in range(len(items)):
        for j in range(i+1,len(items)):
            a,b=items[i],items[j]; sa=[tuple(_l(_d(s).get("function"))) for s in _l(a.get("shots"))]; sb=[tuple(_l(_d(s).get("function"))) for s in _l(b.get("shots"))]; sig_a=(len(sa),sa,[_t(_d(s).get("shot_size")) for s in _l(a.get("shots"))],[_t(_d(s).get("camera_movement")) for s in _l(a.get("shots"))]); sig_b=(len(sb),sb,[_t(_d(s).get("shot_size")) for s in _l(b.get("shots"))],[_t(_d(s).get("camera_movement")) for s in _l(b.get("shots"))]); same=sig_a==sig_b and _t(a.get("architecture_summary"))==_t(b.get("architecture_summary")); pairs.append({"left":a.get("scene_id"),"right":b.get("scene_id"),"same_topology":same,"left_signature":sig_a,"right_signature":sig_b}); hard = hard or same
    return {"pair_count":len(pairs),"all_pairs_checked":len(pairs)==3,"pairs":pairs,"hard_template_leakage":hard,"hard_failure":hard}
