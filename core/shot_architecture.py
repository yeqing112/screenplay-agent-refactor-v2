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

def parse_architecture_envelope(raw: str) -> dict[str, Any]:
    """Parse the outer architecture envelope, never a nested shot object."""
    from core.structured_output import parse_json_object
    required = {"architecture_summary", "shots"}
    parsed = parse_json_object(raw, label="shot_architecture_draft_v1", required_keys=required)
    missing = sorted(required - set(parsed))
    if missing or not isinstance(parsed.get("shots"), list):
        raise ValueError(f"shot_architecture_draft_v1 envelope invalid; required top-level keys={sorted(required)}; missing={missing}")
    return parsed

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
MOVE_ALIASES = {"轻微手持晃动": "HANDHELD_SUBTLE", "轻微手持": "HANDHELD_SUBTLE", "重新构图": "REFRAME", "缓慢下摇": "TILT", "下摇": "TILT", "缓慢上摇": "TILT", "上摇": "TILT", "摇摄": "PAN", "横摇": "PAN", "轻微推进": "PUSH_IN", "推近": "PUSH_IN", "推进": "PUSH_IN", "拉远": "PULL_OUT", "后退": "PULL_OUT", "跟拍": "TRACK", "固定": "STATIC", "静止": "STATIC", "无运动": "NONE", "无": "NONE"}

def _ref(value: Any, prefix: str) -> str:
    raw = _t(value)
    if not raw: return ""
    if raw.startswith(prefix + ":"):
        raw = raw.split(":", 1)[1]
    if prefix == "beat" and re.fullmatch(r"B\d+", raw, re.IGNORECASE):
        raw = raw[1:]
    return prefix + ":" + raw

def _shot_ref(value: Any) -> str:
    """Canonicalize a shot reference without inventing an ordinal mapping."""
    raw = _t(value)
    if not raw:
        return ""
    if raw.lower().startswith("shot:"):
        target = raw.split(":", 1)[1].strip()
        if re.fullmatch(r"\d+", target):
            target = "SA" + target.zfill(2)
        return "shot:" + target.upper()
    if re.fullmatch(r"SA\d+", raw, re.IGNORECASE):
        return "shot:" + raw.upper()
    if re.fullmatch(r"\d+", raw):
        return "shot:SA" + raw.zfill(2)
    # Other SourceRef namespaces (beat:, character:, prop:, event:) are
    # already meaningful and free-form legacy prose must remain visible for
    # contract QA rather than being relabeled as a shot reference.
    if re.match(r"^(?:beat|character|prop|event):", raw, re.IGNORECASE):
        return raw.split(":", 1)[0].lower() + ":" + raw.split(":", 1)[1].strip()
    return raw

def _string_list(value: Any) -> tuple[list[str], str]:
    """Losslessly coerce nullable string/string[] fields to string[]."""
    if value is None:
        return [], "null_to_empty_list"
    if isinstance(value, list):
        return [_t(item) for item in value if _t(item)], "list_preserved"
    text = _t(value)
    return ([text] if text else []), "string_to_singleton_list" if text else "empty_to_empty_list"

def normalize_camera_movement(value: Any) -> tuple[str, dict[str, Any]]:
    """Normalize movement aliases without silently guessing unknown phrases."""
    raw = _t(value)
    if not raw:
        return "", {"raw": raw, "canonical": "", "reason": "missing", "review_required": True}
    upper = raw.upper()
    if upper in MOVEMENTS:
        return upper, {"raw": raw, "canonical": upper, "reason": "already_enum", "review_required": False}
    matches = [(alias, target) for alias, target in sorted(MOVE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True) if alias in raw]
    if not matches:
        return "", {"raw": raw, "canonical": "", "reason": "MOVEMENT_NORMALIZATION_REVIEW_REQUIRED", "review_required": True}
    targets = []
    for _, target in matches:
        if target not in targets:
            targets.append(target)
    canonical = matches[0][1]
    reason = "alias" if len(targets) == 1 else "most_specific_motion_wins:" + ",".join(targets)
    return canonical, {"raw": raw, "canonical": canonical, "reason": reason, "review_required": False}

def normalize_architecture_ir(raw: dict[str, Any], *, scene_id: str, strategy_fingerprint: str) -> dict[str, Any]:
    """Project model-facing output into the small canonical Draft schema."""
    if not isinstance(raw, dict): return {"errors": [{"code": "ARCHITECTURE_NOT_OBJECT"}], "ir": None}
    unknown = sorted(k for k in raw if k not in {"scene_id", "schema_version", "strategy_fingerprint", "architecture_summary", "shots", "shot_count", "notes", "primary_function", "secondary_function", *PROGRAM_OWNED})
    shots = _l(raw.get("shots")); canonical_shots = []; normalization_audit = []
    for i, item in enumerate(shots, 1):
        row = _d(item)
        function_value = row.get("function")
        if function_value is None and row.get("primary_function") is not None:
            function_value = [row.get("primary_function")]
            if row.get("secondary_function") not in (None, ""):
                function_value.append(row.get("secondary_function"))
        functions = _l(function_value) if isinstance(function_value, list) else [_t(function_value)]
        functions = [_alias(x, FUNCTION_ALIASES, "") for x in functions if _alias(x, FUNCTION_ALIASES, "")]
        movement, movement_audit = normalize_camera_movement(row.get("camera_movement") or row.get("movement"))
        continuity_raw = row.get("continuity_requirements") if "continuity_requirements" in row else row.get("continuity")
        preserve_raw = row.get("must_preserve_refs") if "must_preserve_refs" in row else row.get("must_preserve")
        continuity, continuity_reason = _string_list(continuity_raw)
        preserve_refs, preserve_reason = _string_list(preserve_raw)
        normalization_audit.append({"shot_index": i, "camera_movement": movement_audit, "continuity_requirements": {"raw": continuity_raw, "canonical": continuity, "reason": continuity_reason}, "must_preserve_refs": {"raw": preserve_raw, "canonical": preserve_refs, "reason": preserve_reason}, "raw_shot_size": row.get("shot_size") or row.get("size"), "framing_transition_present": bool(re.search(r"正反打|转|先.?再.?切|双机位|多机位|A/B", _t(row.get("shot_size") or row.get("size")) + _t(row.get("composition_intent") or row.get("composition"))))})
        canonical_shots.append({
            "shot_id": f"SA{i:02d}",
            "logical_key": _t(row.get("logical_key") or row.get("ordinal") or f"shot-{i}"),
            "phase_id": _t(row.get("phase_id")),
            "beat_refs": [_ref(x, "beat") for x in _l(row.get("beat_refs") or row.get("beats"))],
            "function": functions or ["OBSERVE"],
            "primary_function": functions[0] if functions else "OBSERVE",
            "secondary_function": functions[1] if len(functions) > 1 else None,
            "subject": _t(row.get("subject")),
            "shot_size": _alias(row.get("shot_size") or row.get("size"), SIZE_ALIASES, ""),
            "camera_position": _t(row.get("camera_position") or row.get("camera")),
            "camera_movement": movement,
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
            "continuity_requirements": continuity,
            "must_preserve_refs": preserve_refs,
            "stimulus_ref": _shot_ref(row.get("stimulus_ref") or row.get("stimulus") or row.get("reaction_to")),
            "what_audience_knows_before": _t(row.get("what_audience_knows_before") or row.get("audience_before")),
            "what_this_shot_adds": _t(row.get("what_this_shot_adds") or row.get("audience_adds")),
            "what_remains_withheld": _t(row.get("what_remains_withheld") or row.get("withheld")),
        })
    ir = {"scene_id": scene_id, "schema_version": "shot_architecture_draft_v1", "strategy_fingerprint": strategy_fingerprint, "architecture_summary": _t(raw.get("architecture_summary") or raw.get("summary")), "shot_count": len(canonical_shots), "shots": canonical_shots, "notes": _l(raw.get("notes")), "compiler_version": "shot_architecture_compiler_v1", "architecture_fingerprint": "", "source_trace": {"strategy_fingerprint": strategy_fingerprint, "provider_shot_ids_ignored": True}}
    ir["architecture_fingerprint"] = fingerprint({k: v for k, v in ir.items() if k not in PROGRAM_OWNED})
    errors = [{"code": "UNKNOWN_CREATIVE_FIELD", "field": x} for x in unknown]
    return {"ir": ir, "errors": errors, "unknown_fields": unknown, "projection_status": "PASS" if not unknown else "FAIL", "normalization_audit": normalization_audit}

def atomicity_audit(raw: dict[str, Any], ir: dict[str, Any] | None = None) -> dict[str, Any]:
    """Classify bundled coverage versus a continuous framing evolution.

    A framing transition is not itself a cut: PUSH_IN/PULL_OUT/DOLLY/TRACK,
    PAN/TILT and REFRAME describe one continuous setup.  Reverse angles,
    A/B coverage and explicit cut sequences remain definite composites.  A
    static transition is intentionally left review-required rather than
    silently accepted or split.
    """
    findings = []; classifications = []
    patterns = ("正反打", "先A再切B", "先A再B", "A/B", "双机位", "多机位", "两个机位", "先拍A再切", "切回A", "切回B")
    definite_tokens = ("正反打", "先A再切B", "先A再B", "A/B", "双机位", "多机位", "两个机位", "先拍A再切", "切回A", "切回B")
    continuous_movements = {"PUSH_IN", "PULL_OUT", "DOLLY", "TRACK", "TILT", "PAN", "REFRAME", "HANDHELD_SUBTLE"}
    for index, item in enumerate(_l(_d(raw).get("shots")), 1):
        row = _d(item); text = _canon(row); matched = [pattern for pattern in patterns if pattern in text]
        size = _t(row.get("shot_size") or row.get("size"))
        transition = bool(re.search(r"(?:特写|近景|中近景|中景|全景|远景).*(?:转|切|推|拉|推进|拉远).*(?:特写|近景|中近景|中景|全景|远景)", size))
        if transition:
            matched.append("framing_transition")
        canonical_shot = _l(_d(ir).get("shots"))[index - 1] if ir and index <= len(_l(_d(ir).get("shots"))) else {}
        if matched:
            movement = _t(_d(canonical_shot).get("camera_movement"))
            # A provider may explain that it is *avoiding* reverse-angle
            # coverage in a motivation field.  Only positive inclusion in the
            # shot setup is a composite finding.
            definite = any(token in text and not re.search(r"(?:避免|不要|不使用|不采用|非|禁止).{0,8}" + re.escape(token), text) for token in definite_tokens)
            if definite:
                classification, code = "DEFINITE_COMPOSITE_COVERAGE_BUNDLE", "COMPOSITE_COVERAGE_BUNDLE"
            elif transition and movement in continuous_movements:
                classification, code = "CONTINUOUS_FRAMING_EVOLUTION", "CONTINUOUS_FRAMING_EVOLUTION"
            elif transition:
                classification, code = "ATOMICITY_REVIEW_REQUIRED", "ATOMICITY_REVIEW_REQUIRED"
            else:
                continue
            finding = {"shot_index": index, "shot_id": _d(canonical_shot).get("shot_id") or f"SA{index:02d}", "code": code, "classification": classification, "matched_patterns": sorted(set(matched)), "raw_shot_size": size, "camera_movement": movement or None}
            findings.append(finding); classifications.append(finding)
        else:
            classifications.append({"shot_index": index, "shot_id": _d(canonical_shot).get("shot_id") or f"SA{index:02d}", "classification": "ATOMIC_SHOT_PASS", "matched_patterns": [], "camera_movement": _t(_d(canonical_shot).get("camera_movement")) or None})
    definite_count = sum(f["classification"] == "DEFINITE_COMPOSITE_COVERAGE_BUNDLE" for f in findings)
    continuous_count = sum(f["classification"] == "CONTINUOUS_FRAMING_EVOLUTION" for f in findings)
    review_count = sum(f["classification"] == "ATOMICITY_REVIEW_REQUIRED" for f in findings)
    return {"status": "FAIL" if definite_count else "REVIEW_REQUIRED" if review_count else "PASS", "composite_bundle_count": definite_count, "definite_composite_count": definite_count, "continuous_framing_count": continuous_count, "review_required_count": review_count, "findings": findings, "classifications": classifications, "atomic_pass_count": sum(x["classification"] == "ATOMIC_SHOT_PASS" for x in classifications)}

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
            if field not in shot:
                errors.append({"code": "SHOT_FIELD_MISSING", "shot_id": shot.get("shot_id"), "field": field})
            elif isinstance(shot[field], list):
                # Nullable list fields are canonicalized to [] and may be
                # intentionally empty; the field's presence is the contract.
                if field not in {"continuity_requirements", "must_preserve_refs"} and not shot[field]:
                    errors.append({"code": "SHOT_FIELD_MISSING", "shot_id": shot.get("shot_id"), "field": field})
            elif not _t(shot[field]):
                errors.append({"code": "SHOT_FIELD_MISSING", "shot_id": shot.get("shot_id"), "field": field})
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
    """Validate ordering while treating reaction stimulus as explicit evidence.

    Legacy drafts often omit ``stimulus_ref``.  They are not promoted to a
    hard error merely because the previous shot's function is OBSERVE: prose
    such as “听到顾沉质问后” is deterministic evidence of a stimulus, while
    an undecidable legacy reaction is review-required.  Explicit forward
    references are always invalid.
    """
    shots = _l(ir.get("shots")); errors=[]; warnings=[]; stimulus_evaluations=[]
    for a,b in zip(shots, shots[1:]):
        if (_l(_d(a).get("function")) == _l(_d(b).get("function")) and _t(_d(a).get("subject")) == _t(_d(b).get("subject")) and _t(_d(a).get("information_focus")) == _t(_d(b).get("information_focus")) and _t(_d(a).get("performance_focus")) == _t(_d(b).get("performance_focus"))): errors.append({"code": "REDUNDANT_SHOT", "shot_ids": [_d(a).get("shot_id"), _d(b).get("shot_id")]})
    for index, shot in enumerate(shots):
        funcs = set(_l(_d(shot).get("function")))
        if "REACTION" in funcs:
            shot_id = _t(_d(shot).get("shot_id")) or f"SA{index + 1:02d}"
            ref = _t(_d(shot).get("stimulus_ref"))
            if ref:
                target = ref.split(":", 1)[1] if ":" in ref else ref
                match = re.fullmatch(r"SA(\d+)", target, re.IGNORECASE)
                target_index = int(match.group(1)) if match else None
                if target_index is None:
                    # A malformed/non-canonical reference is a contract
                    # problem, not evidence that the stimulus was forward in
                    # time.  Keep ordering metrics honest.
                    if re.match(r"^(?:beat|character|prop|event):", ref, re.IGNORECASE):
                        stimulus_evaluations.append({"shot_id": shot_id, "classification": "REACTION_STIMULUS_REVIEW_REQUIRED", "stimulus_ref": ref, "reason": "non-shot_ref_requires_source_resolution"})
                        warnings.append({"code": "REACTION_STIMULUS_REVIEW_REQUIRED", "shot_id": shot_id, "reason": "source_ref_resolution_required"})
                    else:
                        errors.append({"code": "INVALID_REACTION_STIMULUS_REF", "shot_id": shot_id, "stimulus_ref": ref, "reason": "non_canonical_reference"})
                        stimulus_evaluations.append({"shot_id": shot_id, "classification": "INVALID_REACTION_STIMULUS_REF", "stimulus_ref": ref})
                elif target_index >= index + 1:
                    errors.append({"code": "INVALID_REACTION_ORDER", "shot_id": shot_id, "stimulus_ref": ref, "reason": "stimulus_must_precede_reaction"})
                    stimulus_evaluations.append({"shot_id": shot_id, "classification": "INVALID_REACTION_ORDER", "stimulus_ref": ref})
                else:
                    stimulus_evaluations.append({"shot_id": shot_id, "classification": "REACTION_STIMULUS_CONFIRMED", "stimulus_ref": ref})
            elif index == 0:
                errors.append({"code": "REACTION_WITHOUT_STIMULUS", "shot_id": shot_id})
                stimulus_evaluations.append({"shot_id": shot_id, "classification": "REACTION_WITHOUT_STIMULUS"})
            else:
                context = " ".join(_t(_d(shot).get(k)) for k in ("performance_focus", "entry_state", "information_focus", "cut_in_motivation", "what_this_shot_adds", "beat_refs"))
                no_stimulus = bool(re.search(r"无(?:外部)?刺激|没有刺激|无刺激来源|不依赖刺激", context))
                cue = bool(re.search(r"听到|听见|质问后|询问后|看到后|看见后|得知后|发现后|回应|受到.{0,8}(?:冲击|质问|威胁)|在.{0,8}之后", context))
                if no_stimulus:
                    errors.append({"code": "REACTION_WITHOUT_STIMULUS", "shot_id": shot_id})
                    stimulus_evaluations.append({"shot_id": shot_id, "classification": "REACTION_WITHOUT_STIMULUS", "evidence": context})
                elif cue:
                    stimulus_evaluations.append({"shot_id": shot_id, "classification": "REACTION_STIMULUS_CONFIRMED", "evidence": context, "legacy_context": True})
                else:
                    warnings.append({"code": "REACTION_STIMULUS_REVIEW_REQUIRED", "shot_id": shot_id, "reason": "legacy_reaction_without_explicit_stimulus_ref"})
                    stimulus_evaluations.append({"shot_id": shot_id, "classification": "REACTION_STIMULUS_REVIEW_REQUIRED", "evidence": context})
        if "EVIDENCE" in funcs and index and "REACTION" in set(_l(_d(shots[index - 1]).get("function"))):
            warnings.append({"code": "EVIDENCE_AFTER_REACTION", "shot_id": _d(shot).get("shot_id")})
        if index and not _t(_d(shot).get("cut_in_motivation")):
            errors.append({"code": "ISOLATED_SHOT", "shot_id": _d(shot).get("shot_id")})
    if shots:
        beat_sets = [_l(_d(s).get("beat_refs")) for s in shots]
        if len(shots) > 1 and all(len(refs) == 1 for refs in beat_sets) and len({refs[0] for refs in beat_sets if refs}) == len(shots):
            warnings.append({"code": "MECHANICAL_BEAT_TO_SHOT_MAPPING"})
    if len(shots) > 30: warnings.append({"code": "SHOT_COUNT_EXTREME"})
    return {"status": "PASS" if not errors else "FAIL", "hard_errors": errors, "warnings": warnings, "redundancy_count": sum(1 for e in errors if e["code"] == "REDUNDANT_SHOT"), "stimulus_evaluations": stimulus_evaluations, "reaction_hard_error_count": sum(e["code"] in {"REACTION_WITHOUT_STIMULUS", "INVALID_REACTION_ORDER"} for e in errors), "reaction_review_required_count": sum(e.get("classification") == "REACTION_STIMULUS_REVIEW_REQUIRED" for e in stimulus_evaluations)}

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
    def signature(value: dict[str, Any]) -> tuple[Any, ...]:
        shots = _l(value.get("shots"))
        functions = [tuple(_l(_d(s).get("function"))) for s in shots]
        phases = [(_t(_d(s).get("phase_id")), tuple(sorted(_l(_d(s).get("beat_refs"))))) for s in shots]
        placements = tuple((name, tuple(i for i, s in enumerate(shots) if name in set(_l(_d(s).get("function"))))) for name in ("REACTION", "INSERT", "EVIDENCE", "REVEAL"))
        transitions = tuple((_t(_d(s).get("cut_in_motivation")), _t(_d(s).get("cut_out_motivation"))) for s in shots)
        return (len(shots), functions, phases, tuple(_t(_d(s).get("shot_size")) for s in shots), tuple(_t(_d(s).get("camera_movement")) for s in shots), placements, transitions)
    for i in range(len(items)):
        for j in range(i+1,len(items)):
            a,b=items[i],items[j]; sig_a=signature(a); sig_b=signature(b); same=sig_a==sig_b and _t(a.get("architecture_summary"))==_t(b.get("architecture_summary")); pairs.append({"left":a.get("scene_id"),"right":b.get("scene_id"),"same_topology":same,"left_signature":sig_a,"right_signature":sig_b}); hard = hard or same
    return {"pair_count":len(pairs),"all_pairs_checked":len(pairs)==3,"pairs":pairs,"hard_template_leakage":hard,"hard_failure":hard}


CAPABILITY_LAYERS = ("STRUCTURAL", "AUTHORITY", "IDENTITY", "COVERAGE", "SPATIAL", "INFORMATION", "TOPOLOGY", "ATOMICITY", "CONTRACT", "CREATIVE")

def capability_assessment(*, metrics: dict[str, Any], protocol: dict[str, Any], authority: dict[str, Any], identity: dict[str, Any], coverage: dict[str, Any], spatial: dict[str, Any], information: dict[str, Any], topology: dict[str, Any], atomicity: dict[str, Any], contract_failures: list[Any] | None = None, director_qa_result: dict[str, Any] | None = None) -> dict[str, Any]:
    """Produce a layered, non-minimum capability assessment for one scene."""
    contract_failures = contract_failures or []
    director_qa_result = director_qa_result or {}
    layer_counts = {layer: {"hard_error_count": 0, "review_required_count": 0, "contract_issue_count": 0, "creative_warning_count": 0} for layer in CAPABILITY_LAYERS}
    # A malformed outer envelope is structural; a normalized draft that only
    # misses a contract field is not a hard semantic failure and is counted
    # under CONTRACT below.
    layer_counts["STRUCTURAL"]["hard_error_count"] = int(not metrics.get("raw_envelope_valid", False))
    layer_counts["AUTHORITY"]["hard_error_count"] = int(_t(authority.get("status")) in {"UNSAFE", "FAIL"})
    layer_counts["IDENTITY"]["hard_error_count"] = int(_t(identity.get("status")) in {"UNSAFE", "FAIL"})
    layer_counts["COVERAGE"]["hard_error_count"] = int(_t(coverage.get("status")) == "FAIL")
    layer_counts["SPATIAL"]["hard_error_count"] = len(_l(spatial.get("hard_errors")))
    layer_counts["INFORMATION"]["hard_error_count"] = len(_l(information.get("hard_errors")))
    layer_counts["TOPOLOGY"]["hard_error_count"] = len(_l(topology.get("hard_errors")))
    layer_counts["TOPOLOGY"]["review_required_count"] = sum(_t(_d(x).get("code")) == "REACTION_STIMULUS_REVIEW_REQUIRED" for x in _l(topology.get("warnings")))
    layer_counts["ATOMICITY"]["contract_issue_count"] = int(atomicity.get("definite_composite_count", atomicity.get("composite_bundle_count", 0)) or 0)
    layer_counts["ATOMICITY"]["review_required_count"] = int(atomicity.get("review_required_count", 0) or 0)
    layer_counts["CONTRACT"]["contract_issue_count"] = len(contract_failures) + int(not protocol.get("valid", False))
    layer_counts["CREATIVE"]["creative_warning_count"] = len(_l(director_qa_result.get("warnings")))
    hard_total = sum(v["hard_error_count"] for v in layer_counts.values())
    review_total = sum(v["review_required_count"] for v in layer_counts.values())
    contract_total = sum(v["contract_issue_count"] for v in layer_counts.values())
    creative_total = sum(v["creative_warning_count"] for v in layer_counts.values())
    if layer_counts["STRUCTURAL"]["hard_error_count"] or layer_counts["AUTHORITY"]["hard_error_count"] or layer_counts["IDENTITY"]["hard_error_count"]:
        signal = "RAW_ARCHITECTURE_INVALID"
    elif hard_total:
        signal = "RAW_ARCHITECTURE_WEAK"
    elif contract_total or review_total or int(atomicity.get("definite_composite_count", 0) or 0):
        signal = "RAW_ARCHITECTURE_PROMISING_BUT_NEEDS_CONTRACT"
    elif creative_total:
        signal = "RAW_ARCHITECTURE_USABLE"
    else:
        signal = "RAW_ARCHITECTURE_STRONG"
    return {"signal": signal, "layer_counts": layer_counts, "hard_error_count": hard_total, "review_required_count": review_total, "contract_issue_count": contract_total, "creative_warning_count": creative_total, "definite_composite_count": int(atomicity.get("definite_composite_count", atomicity.get("composite_bundle_count", 0)) or 0), "continuous_framing_count": int(atomicity.get("continuous_framing_count", 0) or 0), "reaction_hard_error_count": int(topology.get("reaction_hard_error_count", 0) or 0), "reaction_review_required_count": int(topology.get("reaction_review_required_count", 0) or 0)}

def aggregate_capability(scene_assessments: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate scenes without collapsing to the weakest scene."""
    distribution = Counter(_t(x.get("signal")) for x in scene_assessments)
    order = {"RAW_ARCHITECTURE_INVALID": 0, "RAW_ARCHITECTURE_WEAK": 1, "RAW_ARCHITECTURE_PROMISING_BUT_NEEDS_CONTRACT": 2, "RAW_ARCHITECTURE_USABLE": 3, "RAW_ARCHITECTURE_STRONG": 4}
    overall = min((x.get("signal") for x in scene_assessments), key=lambda x: order.get(x, -1), default="RAW_ARCHITECTURE_INVALID")
    if scene_assessments and all(order.get(x.get("signal"), -1) >= order["RAW_ARCHITECTURE_USABLE"] for x in scene_assessments):
        overall = "RAW_ARCHITECTURE_USABLE" if any(x.get("signal") != "RAW_ARCHITECTURE_STRONG" for x in scene_assessments) else "RAW_ARCHITECTURE_STRONG"
    return {"scene_signal_distribution": dict(sorted(distribution.items())), "overall_capability": overall, "hard_blocking_scene_count": sum(x.get("hard_error_count", 0) > 0 for x in scene_assessments), "usable_or_better_count": sum(order.get(x.get("signal"), -1) >= order["RAW_ARCHITECTURE_USABLE"] for x in scene_assessments), "promising_or_better_count": sum(order.get(x.get("signal"), -1) >= order["RAW_ARCHITECTURE_PROMISING_BUT_NEEDS_CONTRACT"] for x in scene_assessments), "definite_composite_total": sum(x.get("definite_composite_count", 0) for x in scene_assessments), "continuous_framing_total": sum(x.get("continuous_framing_count", 0) for x in scene_assessments), "review_required_total": sum(x.get("review_required_count", 0) for x in scene_assessments), "contract_issue_total": sum(x.get("contract_issue_count", 0) for x in scene_assessments)}
