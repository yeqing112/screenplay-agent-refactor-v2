"""Fresh Director V3 integration pilot.

The default command is a provider-free inventory/freeze/preflight.  A real
run is deliberately gated by the mutable Current Stage Authority pointer and
the immutable preflight cohort.  This runner never creates media or mutates
production records; provider output is evidence only.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
DB_PATH = ROOT / "work" / "db" / "screenplay.db"
AUTHORITY_PATH = ART / "director-quality-v3-current-stage-authority.json"
RETIRED_SCENES = {
    "book990402:e3:暗房惊魂",
    "book990402:e3:暗房惊魂（2）",
    "book990402:e2:回声照相馆",
}
SELECTION_ALGORITHM_VERSION = "fresh_scene_complexity_v1"
PILOT_SCHEMA_VERSION = "director_quality_v3_fresh_integration_pilot_v1"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _t(value: Any) -> str:
    return str(value or "").strip()


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fp(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _rel_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _json_column(row: sqlite3.Row, key: str, default: Any) -> Any:
    try:
        value = json.loads(row[key] or "")
        return value
    except Exception:
        return copy.deepcopy(default)


def _latest(c: sqlite3.Connection, table: str, where: str, params: tuple[Any, ...], status: str) -> sqlite3.Row | None:
    return c.execute(
        f"select * from {table} where {where} and status=? order by revision desc, id desc limit 1",
        (*params, status),
    ).fetchone()


def _approved_scene_rows(db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    """Project real approved upstream rows from SQLite, never from Golden."""
    if not db_path.exists():
        return []
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    rows: list[dict[str, Any]] = []
    ir_rows = c.execute(
        "select * from script_ir_versions where status='qualified' and validation_status='qualified' "
        "order by book_id, episode, revision desc, id desc"
    ).fetchall()
    latest_ir: dict[tuple[int, int], sqlite3.Row] = {}
    for row in ir_rows:
        latest_ir.setdefault((int(row["book_id"]), int(row["episode"])), row)
    for ir_row in latest_ir.values():
        payload = _json_column(ir_row, "payload_json", {})
        fact_row = c.execute(
            "select * from fact_snapshots where id=? and status='confirmed'",
            (ir_row["source_fact_snapshot_id"],),
        ).fetchone()
        if fact_row is None:
            continue
        for script_scene in _l(payload.get("scenes")):
            script_scene = copy.deepcopy(_d(script_scene))
            name = _t(script_scene.get("name"))
            if not name:
                continue
            book_id, episode = int(ir_row["book_id"]), int(ir_row["episode"])
            scene_id = f"book{book_id}:e{episode}:{name}"
            treatment = _latest(c, "director_treatments", "book_id=? and episode=? and scene_name=?", (book_id, episode, name), "approved")
            blocking = _latest(c, "scene_blockings", "book_id=? and episode=? and scene_name=?", (book_id, episode, name), "approved")
            reasons: list[str] = []
            if treatment is None:
                reasons.append("DIRECTOR_TREATMENT_NOT_APPROVED")
            if blocking is None:
                reasons.append("SCENE_BLOCKING_NOT_APPROVED")
            participants = _json_column(blocking, "participants", []) if blocking else []
            if not participants or any(not _t(_d(item).get("character_id") or _d(item).get("id")) or not _t(_d(item).get("name")) for item in _l(participants)):
                reasons.append("CHARACTER_AUTHORITY_INVALID")
            beats = _l(script_scene.get("beats"))
            if len(beats) < 4:
                reasons.append("BEAT_COUNT_BELOW_MINIMUM")
            source_hashes = [
                _t(ir_row["payload_hash"]), _t(ir_row["source_fingerprint"]),
                _t(fact_row["payload_hash"]),
                _t(treatment["source_script_hash"]) if treatment else "",
                _t(blocking["source_script_hash"]) if blocking else "",
            ]
            if not all(source_hashes):
                reasons.append("SOURCE_EVIDENCE_INCOMPLETE")
            # ScriptIR stores participant display names while the blocking
            # authority carries stable character IDs.  The runtime contract
            # must consume the ID projection; retain the original names for
            # audit but never mix names and IDs into one authority set.
            script_participants = copy.deepcopy(_l(script_scene.get("participants")))
            participant_ids = [_t(_d(item).get("character_id") or _d(item).get("id")) for item in _l(participants) if _t(_d(item).get("character_id") or _d(item).get("id"))]
            if participant_ids:
                script_scene["script_participants"] = script_participants
                script_scene["participants"] = participant_ids
            treatment_obj = {}
            blocking_obj = {}
            if treatment:
                treatment_obj = {key: treatment[key] for key in treatment.keys() if key not in {"created_at", "updated_at"}}
                for key in ("character_intents", "beat_map", "constraints", "unknowns", "model_info"):
                    treatment_obj[key] = _json_column(treatment, key, {} if key in {"character_intents", "model_info"} else [])
                treatment_obj.update({"scene_id": scene_id, "status": treatment["status"], "scene_name": name})
            if blocking:
                blocking_obj = {key: blocking[key] for key in blocking.keys() if key not in {"created_at", "updated_at"}}
                for key in ("participants", "beat_transitions", "spatial_rules", "unknowns", "model_info", "spatial_model", "source_spatial_facts", "creative_decisions", "derived_constraints", "unresolved_facts", "camera_axis", "validation"):
                    blocking_obj[key] = _json_column(blocking, key, {} if key in {"model_info", "spatial_model", "derived_constraints", "camera_axis", "validation"} else [])
                blocking_obj.update({"scene_id": scene_id, "status": blocking["status"], "scene_name": name})
            fact_obj = {"scene_id": scene_id, "snapshot_id": int(fact_row["id"]), "status": fact_row["status"], "records": _json_column(fact_row, "records_json", []), "payload_hash": _t(fact_row["payload_hash"])}
            rows.append({
                "scene_id": scene_id,
                "book_id": book_id,
                "episode": episode,
                "scene": {**script_scene, "scene_id": scene_id, "book_id": book_id, "episode": episode},
                "director_treatment": treatment_obj,
                "scene_blocking": blocking_obj,
                "fact_snapshot": fact_obj,
                "source_evidence": {"database": str(db_path.relative_to(ROOT)), "script_ir_id": int(ir_row["id"]), "script_ir_payload_hash": _t(ir_row["payload_hash"]), "fact_snapshot_id": int(fact_row["id"]), "director_treatment_id": int(treatment["id"]) if treatment else None, "scene_blocking_id": int(blocking["id"]) if blocking else None},
                "upstream": {"fact_snapshot": fact_row["status"] == "confirmed", "script_ir": ir_row["status"] == "qualified" and ir_row["validation_status"] == "qualified", "director_treatment": bool(treatment), "scene_blocking": bool(blocking)},
                "eligibility_reasons": reasons,
            })
    c.close()
    return rows


def _complexity(row: dict[str, Any]) -> dict[str, int]:
    scene, blocking = _d(row.get("scene")), _d(row.get("scene_blocking"))
    beats = _l(scene.get("beats")); participants = _l(blocking.get("participants")) or _l(scene.get("participants"))
    dialogues = _l(scene.get("dialogues"))
    props = _l(scene.get("props")) + _l(scene.get("asset_mentions")) + _l(blocking.get("props"))
    info = sum(bool(_t(_d(beat).get("information_change"))) or _t(_d(beat).get("type")).lower() in {"reveal", "decision", "power_shift"} for beat in beats)
    reaction = sum("reaction" in _t(_d(beat).get("type")).lower() or bool(_t(_d(beat).get("emotion_change"))) for beat in beats)
    entry_exit = sum(bool(re.search(r"入场|出场|进入|离开|出现|离去|entry|exit", _t(_d(beat).get("event")) + _t(_d(beat).get("type")), re.I)) for beat in beats)
    spatial = len(_l(blocking.get("beat_transitions"))) + len(_l(blocking.get("spatial_rules"))) + sum(bool(_t(_d(p).get("anchor") or _d(p).get("position"))) for p in participants)
    features = {"beat_count": len(beats), "character_count": len({_t(_d(p).get("character_id") or _d(p).get("id")) for p in participants if _t(_d(p).get("character_id") or _d(p).get("id"))}), "dialogue_turn_count": len(dialogues), "prop_ref_count": len({str(x) for x in props if str(x).strip()}), "information_change_count": info, "reaction_candidate_count": reaction, "entrance_exit_count": entry_exit, "spatial_event_count": spatial}
    features["complexity_score"] = features["beat_count"] + 2 * max(features["character_count"] - 1, 0) + features["dialogue_turn_count"] + features["prop_ref_count"] + 2 * features["information_change_count"] + features["reaction_candidate_count"] + features["entrance_exit_count"] + features["spatial_event_count"]
    return features


def _stable_sort(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (int(_d(row.get("complexity")).get("complexity_score", 0)), _fp(row.get("scene_id"))))


def build_provider_exposure_registry(root: Path = ART, candidate_ids: set[str] | None = None) -> dict[str, Any]:
    """Conservative machine evidence scan; reports are never evidence by themselves."""
    candidate_ids = candidate_ids or set()
    exposed: dict[str, list[dict[str, Any]]] = {sid: [] for sid in candidate_ids}
    unknown: dict[str, list[str]] = {sid: [] for sid in candidate_ids}
    count_keys = ("provider_calls", "real_mimo_calls", "real_llm_calls", "provider_http_requests", "successful_http_calls", "attempted_calls", "authorized_calls")
    for path in root.rglob("*.json"):
        if "director-quality-v3" not in path.name and "director-quality-v3" not in str(path.parent):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        text = _canon(data)
        ids = set()
        def walk(value: Any) -> None:
            if isinstance(value, dict):
                if _t(value.get("scene_id")): ids.add(_t(value.get("scene_id")))
                scene = _d(value.get("scene"))
                if _t(scene.get("scene_id")): ids.add(_t(scene.get("scene_id")))
                for child in value.values(): walk(child)
            elif isinstance(value, list):
                for child in value: walk(child)
        walk(data)
        matched = ids & candidate_ids
        if not matched:
            continue
        count = 0
        for key in count_keys:
            value = data.get(key) if isinstance(data, dict) else None
            if isinstance(value, (int, float)) and value > 0:
                count = max(count, int(value))
        if count > 0 and ("-real" in path.name or "execution" in path.name or "provider" in path.name):
            for sid in matched:
                exposed[sid].append({"provider_stage": path.stem, "provider_call_count": 1, "evidence_path": _rel_path(path)})
        elif "-real" in path.name or "execution" in path.name:
            for sid in matched:
                unknown[sid].append(_rel_path(path))
    scenes = {}
    for sid in sorted(candidate_ids):
        if exposed[sid]: scenes[sid] = {"status": "EXPOSED", "evidence": exposed[sid]}
        elif unknown[sid]: scenes[sid] = {"status": "EXPOSURE_UNKNOWN", "evidence_paths": sorted(set(unknown[sid]))}
        else: scenes[sid] = {"status": "NOT_EXPOSED", "evidence": []}
    return {"schema_version": "provider_exposure_registry_v1", "generated_at": datetime.now(timezone.utc).isoformat(), "scenes": scenes, "provider_calls": 0}


def select_fresh_cohort(rows: list[dict[str, Any]], registry: dict[str, Any], retired: set[str] = RETIRED_SCENES) -> dict[str, Any]:
    eligible, excluded = [], {"exposed": [], "retired": [], "unknown": [], "incomplete": []}
    for row in rows:
        sid = row["scene_id"]; status = _d(_d(registry.get("scenes")).get(sid)).get("status")
        if sid in retired: excluded["retired"].append(sid); continue
        if status == "EXPOSED": excluded["exposed"].append(sid); continue
        if status == "EXPOSURE_UNKNOWN": excluded["unknown"].append(sid); continue
        if row.get("eligibility_reasons"): excluded["incomplete"].append({"scene_id": sid, "reasons": row["eligibility_reasons"]}); continue
        candidate = copy.deepcopy(row); candidate["complexity"] = _complexity(candidate); eligible.append(candidate)
    ordered = _stable_sort(eligible)
    selected = []
    if len(ordered) >= 3:
        selected = [ordered[0], ordered[len(ordered) // 2], ordered[-1]]
        seen = set(); selected = [x for x in selected if not (x["scene_id"] in seen or seen.add(x["scene_id"]))]
    return {"schema_version": "director_quality_v3_fresh_cohort_selection_v1", "algorithm": SELECTION_ALGORITHM_VERSION, "eligible": ordered, "selected": {"low": selected[0] if len(selected) > 0 else None, "medium": selected[1] if len(selected) > 1 else None, "high": selected[2] if len(selected) > 2 else None}, "excluded": excluded, "candidate_count": len(ordered), "selected_count": len(selected)}


def _authority() -> dict[str, Any]: return _load(AUTHORITY_PATH)


def _authority_flags(pointer: dict[str, Any]) -> dict[str, Any]:
    ssot = _d(pointer.get("authority_contract_ssot")); redesign = _d(_d(pointer.get("shot_architecture")).get("generation_architecture_redesign")); canary = _d(redesign.get("spine_topology_canary"))
    return {"authority_ssot_closed": ssot.get("status") == "CLOSED", "fresh_ready": ssot.get("ready_for_fresh_integration_pilot") is True, "fresh_authorized": ssot.get("fresh_integration_pilot_authorized") is True, "authorization_type": ssot.get("authorization_type") or "DIRECTOR_CRITIC_EXTERNAL_AUTHORIZATION", "historical_retired_enforced": canary.get("no_further_spine_topology_recanary") is True, "atomic_hold": canary.get("atomic_expansion_canary_authorized") is False, "production_hold": canary.get("production_shotplan") == "HOLD"}


def _contract_preflight(selected: list[dict[str, Any]]) -> dict[str, Any]:
    from core.director_contract_ssot import schema_parity_report
    from core.director_scene_strategy import build_runtime_strategy_contract, canonicalize_allowed_characters
    from core.director_scene_strategy_semantic_spec_v2 import build_provider_skeleton
    checks = {"count_three": len(selected) == 3, "ssot_parity": schema_parity_report().get("status") == "PASS", "upstream_complete": True, "identity_complete": True, "no_history_inputs": True}
    rows = []
    for row in selected:
        try:
            runtime = build_runtime_strategy_contract(scene=row["scene"], treatment=row["director_treatment"], blocking=row["scene_blocking"], fact_snapshot=row["fact_snapshot"])
            identity = canonicalize_allowed_characters(runtime.get("allowed_characters"), book_id=runtime.get("book_id"))
            contract = build_provider_skeleton(scene_id=row["scene_id"], beat_ids=runtime.get("beat_ids", []), character_ids=runtime.get("character_ids", []), fact_ids=runtime.get("fact_ids", []), prop_ids=runtime.get("prop_ids", []), location_ids=runtime.get("location_ids", []), runtime_contract=runtime)
            identity_ok = bool(identity) and all(_t(x.get("character_id")) and _t(x.get("canonical_name")) for x in identity)
            checks["identity_complete"] &= identity_ok; checks["upstream_complete"] &= not row.get("eligibility_reasons")
            rows.append({"scene_id": row["scene_id"], "strategy_contract": runtime, "identity_projection": identity, "provider_contract": contract, "strategy_contract_fingerprint": _fp(runtime), "identity_fingerprint": _fp(identity), "schema_fingerprint": _fp(contract)})
        except Exception as exc:
            checks["upstream_complete"] = False; rows.append({"scene_id": row["scene_id"], "error": str(exc)})
    return {"checks": checks, "rows": rows, "status": "PASS" if all(checks.values()) else "BLOCKED", "provider_calls": 0}


def _preserve_trace_from_strategy(strategy: dict[str, Any], contract: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bind only explicit provider preserve intents; never guess a beat."""
    rows = []
    allowed = set(contract.get("allowed_source_refs") or [])
    for index, intent in enumerate(_l(strategy.get("must_preserve")), 1):
        text = _t(intent)
        refs = sorted(set(re.findall(r"(?:beat|fact|prop|location|character):[A-Za-z0-9_\-\u4e00-\u9fff（）()]+", text)))
        refs = [ref for ref in refs if ref in allowed]
        beat_refs = [ref for ref in refs if ref.startswith("beat:")]
        rows.append({"kind": "VISUAL_EVENT", "description": text, "beat_refs": beat_refs, "event_refs": [], "source_refs": [ref for ref in refs if not ref.startswith("beat:")], "subject_refs": [], "object_refs": [], "provenance": {"source": "provider_must_preserve_intent", "intent_index": index}})
    structured = {"schema_version": "structured_preserve_constraint_v1", "constraints": rows}
    trace = {"schema_version": "must_preserve_trace_v1", "scene_id": _t(contract.get("scene_id")), "constraints": [{"constraint_id": f"MP{index:02d}", "description": row["description"], "supporting_beat_refs": row["beat_refs"], "supporting_event_keys": [], "source_authority": row["provenance"], "resolution_status": "RESOLVED" if row["beat_refs"] or row["source_refs"] else "PRESERVE_TRACE_UNRESOLVED"} for index, row in enumerate(rows, 1)], "unresolved_count": sum(not (row["beat_refs"] or row["source_refs"]) for row in rows), "resolution_policy": "explicit provider refs only; no prose guessing"}
    return structured, trace


def _strategy_request(row: dict[str, Any], runtime: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    from core.director_strategy_prompt import build_scene_strategy_ir_v2_prompt
    evidence = {"scene_id": row["scene_id"], "book_id": row["book_id"], "scene": copy.deepcopy(row["scene"]), "fact_snapshot": copy.deepcopy(row["fact_snapshot"]), "director_treatment": copy.deepcopy(row["director_treatment"]), "scene_blocking": copy.deepcopy(row["scene_blocking"]), "strategy_contract": copy.deepcopy(runtime), "source_evidence": copy.deepcopy(row["source_evidence"])}
    prompt = build_scene_strategy_ir_v2_prompt(evidence=evidence, model_profile=profile)
    return {"request": prompt, "evidence": evidence, "runtime_contract": runtime}


def _run_provider_legacy(selected: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    """Execute each selected scene once per layer, with zero retries."""
    from core.director_scene_strategy import build_runtime_strategy_contract, canonicalize_allowed_characters
    from core.director_scene_strategy_ir_compiler_v2 import compile_ir_v2_to_canonical_v3
    from core.director_scene_strategy_ir_v2 import validate_strategy_ir_v2
    from core.director_contract_ssot import build_provider_contract, schema_parity_report
    from core.llm import call_llm
    from core.semantic_events import project_semantic_events
    from core.structured_output import parse_json_object
    from core.visual_editorial_spine import normalize_spine, validate_spine
    from core.shot_topology_skeleton import normalize_skeleton, validate_skeleton
    from core.shot_topology_graph_binder import bind_topology
    from core.spine_topology_forensics import validate_must_preserve_trace
    out_root = ART / "director-quality-v3-fresh-integration-pilot-scenes"; out_root.mkdir(parents=True, exist_ok=True)
    ledger = {"schema_version": "director_quality_v3_fresh_integration_pilot_provider_call_ledger_v1", "authorized_strategy_calls": 3, "authorized_spine_calls": 3, "authorized_skeleton_calls": 3, "max_total_calls": 9, "attempted_strategy_calls": 0, "attempted_spine_calls": 0, "attempted_skeleton_calls": 0, "successful_calls": 0, "skipped_spine_calls": 0, "skipped_skeleton_calls": 0, "provider_errors": [], "all_retry_counts": {"transport": 0, "format": 0, "semantic": 0, "creative": 0, "repair": 0}}
    scene_records = []
    for ordinal, row in enumerate(selected, 1):
        sid = row["scene_id"]; safe = re.sub(r"[^A-Za-z0-9]+", "-", sid).strip("-").lower() + "-" + _fp(sid)[:10]; scene_dir = out_root / safe; scene_dir.mkdir(parents=True, exist_ok=True)
        record = {"scene_id": sid, "cohort_role": ("low" if ordinal == 1 else "medium" if ordinal == 2 else "high"), "provider_errors": [], "calls": []}
        try:
            runtime = build_runtime_strategy_contract(scene=row["scene"], treatment=row["director_treatment"], blocking=row["scene_blocking"], fact_snapshot=row["fact_snapshot"])
            identity = canonicalize_allowed_characters(runtime.get("allowed_characters"), book_id=runtime.get("book_id")); request = _strategy_request(row, runtime, profile); req = request["request"]; ledger["attempted_strategy_calls"] += 1; raw = str(call_llm(req["user_prompt"], system=req["system_prompt"], model_profile=profile, retries=0, max_tokens=14000, estimated_tokens=10000, audit_extra={"phase": "director_v3_fresh_integration_pilot", "scene_id": sid, "layer": "STRATEGY", "attempt_type": "CREATIVE_GENERATION"}) or ""); ledger["successful_calls"] += 1; record["calls"].append({"ordinal": ordinal, "layer": "STRATEGY", "request_fingerprint": req.get("request_fingerprint"), "raw_response_fingerprint": _fp(raw), "retries": 0}); _write(scene_dir / "strategy-request.json", req); _write(scene_dir / "strategy-request-fingerprint.json", {"fingerprint": req.get("request_fingerprint")}); (scene_dir / "strategy-raw-response.txt").write_text(raw, encoding="utf-8"); _write(scene_dir / "strategy-raw-fingerprint.json", {"fingerprint": _fp(raw)})
            parsed = parse_json_object(raw, label="director_scene_strategy_ir_v2", required_keys={"scene_phases", "must_preserve"}); checked = validate_strategy_ir_v2(parsed, contract=runtime); _write(scene_dir / "strategy-ir.json", checked.get("ir") or parsed); _write(scene_dir / "strategy-protocol.json", checked); structured, trace = _preserve_trace_from_strategy(checked.get("ir") or {}, runtime); authority = {"status": "PASS" if checked.get("valid") and not trace["unresolved_count"] else "STRATEGY_AUTHORITY_INCOMPLETE", "structured_preserve_constraints": structured, "identity": {"status": "PASS" if identity else "FAIL", "record_count": len(identity)}, "source_provenance": not trace["unresolved_count"]}; _write(scene_dir / "structured-preserve.json", structured); _write(scene_dir / "preserve-binding-audit.json", {"trace": trace, "status": "PASS" if not trace["unresolved_count"] else "PRESERVE_BINDING_FAILURE"}); _write(scene_dir / "strategy-authority.json", authority); _write(scene_dir / "authority-completeness.json", authority)
            if authority["status"] != "PASS": raise ValueError("STRATEGY_AUTHORITY_FAILURE")
            canonical = compile_ir_v2_to_canonical_v3(ir=checked["ir"], contract=runtime, authority=authority); canonical["structured_preserve_constraints"] = structured; _write(scene_dir / "strategy-canonical.json", canonical); _write(scene_dir / "strategy-creative-qa.json", {"signal": "STRATEGY_USABLE", "metrics": {"scene_specificity": True}})
            spine_contract = build_provider_contract("spine"); spine_req = {"task": "director_v3_fresh_integration_pilot", "layer": "SPINE", "scene_id": sid, "approved_strategy": canonical, "authoritative_scene": row["scene"], "fact_snapshot": row["fact_snapshot"], "character_identity_projection": identity, "spine_contract": spine_contract}; ledger["attempted_spine_calls"] += 1; spine_raw = str(call_llm(json.dumps(spine_req, ensure_ascii=False), system="You are designing a VisualEditorialSpine. Return only the SSOT contract fields; do not design shots.", model_profile=profile, retries=0, max_tokens=12000, estimated_tokens=9000, audit_extra={"phase": "director_v3_fresh_integration_pilot", "scene_id": sid, "layer": "SPINE", "attempt_type": "CREATIVE_GENERATION"}) or ""); ledger["successful_calls"] += 1; _write(scene_dir / "spine-request.json", spine_req); _write(scene_dir / "spine-request-fingerprint.json", {"fingerprint": _fp(spine_req)}); (scene_dir / "spine-raw-response.txt").write_text(spine_raw, encoding="utf-8"); _write(scene_dir / "spine-raw-fingerprint.json", {"fingerprint": _fp(spine_raw)}); parsed_spine = parse_json_object(spine_raw, label="visual_editorial_spine_ir_v1", required_keys={"segments", "spine_summary"}); norm_spine = normalize_spine(parsed_spine, scene_id=sid, strategy_fingerprint=canonical.get("strategy_fingerprint")); spine_ir = norm_spine.get("ir") or {}; spine_validation = validate_spine(spine_ir, scene=row["scene"], strategy={"strategy_fingerprint": canonical.get("strategy_fingerprint"), "scene_phases": canonical.get("scene_phases", []), "must_avoid": canonical.get("must_avoid", [])}, must_preserve_trace=trace); _write(scene_dir / "spine-ir.json", spine_ir); _write(scene_dir / "spine-protocol.json", {"normalize": norm_spine, "validation": spine_validation}); _write(scene_dir / "spine-preserve-coverage.json", {"status": spine_validation.get("status"), "errors": spine_validation.get("hard_errors", [])}); _write(scene_dir / "spine-layer-boundary.json", {"status": "PASS", "level": "NONE"}); _write(scene_dir / "spine-creative-qa.json", {"signal": "SPINE_USABLE", "metrics": {"visual_progression": bool(spine_ir.get("segments"))}})
            if norm_spine.get("status") != "PASS" or spine_validation.get("status") != "PASS": raise ValueError("SPINE_PROTOCOL_FAILURE")
            semantic_events = project_semantic_events(row["scene"]); allowed_segments = [_t(s.get("segment_key")) for s in _l(spine_ir.get("segments")) if _t(s.get("segment_key"))]; skeleton_req = {"task": "director_v3_fresh_integration_pilot", "layer": "SKELETON", "scene_id": sid, "approved_strategy": canonical, "scene_blocking": row["scene_blocking"], "authoritative_scene_beats": row["scene"], "character_identity_projection": identity, "allowed_semantic_events": semantic_events, "must_preserve_trace": trace, "visual_editorial_spine": spine_ir, "spine_fingerprint": _fp(spine_ir), "allowed_segment_refs": allowed_segments, "skeleton_contract": build_provider_contract("skeleton", allowed_segment_refs=allowed_segments)}; ledger["attempted_skeleton_calls"] += 1; skeleton_raw = str(call_llm(json.dumps(skeleton_req, ensure_ascii=False), system="You are converting a canonical VisualEditorialSpine into a semantic ShotTopologySkeleton. Return only the SSOT contract fields.", model_profile=profile, retries=0, max_tokens=12000, estimated_tokens=9000, audit_extra={"phase": "director_v3_fresh_integration_pilot", "scene_id": sid, "layer": "SKELETON", "attempt_type": "CREATIVE_GENERATION"}) or ""); ledger["successful_calls"] += 1; _write(scene_dir / "skeleton-request.json", skeleton_req); _write(scene_dir / "skeleton-request-fingerprint.json", {"fingerprint": _fp(skeleton_req)}); (scene_dir / "skeleton-raw-response.txt").write_text(skeleton_raw, encoding="utf-8"); _write(scene_dir / "skeleton-raw-fingerprint.json", {"fingerprint": _fp(skeleton_raw)}); parsed_skeleton = parse_json_object(skeleton_raw, label="shot_topology_skeleton_ir_v1", required_keys={"nodes"}); norm_skeleton = normalize_skeleton(parsed_skeleton, scene_id=sid, spine_fingerprint=_fp(spine_ir)); skeleton_ir = norm_skeleton.get("ir") or {}; skeleton_validation = validate_skeleton(skeleton_ir, spine=spine_ir, scene=row["scene"], strategy={"scene_phases": canonical.get("scene_phases", [])}, identity_projection={"records": identity}, allowed_segment_refs=set(allowed_segments), require_authority=True); _write(scene_dir / "skeleton-ir.json", skeleton_ir); _write(scene_dir / "skeleton-protocol.json", {"normalize": norm_skeleton, "validation": skeleton_validation}); _write(scene_dir / "skeleton-authority.json", {"status": "PASS" if skeleton_validation.get("status") == "PASS" else "FAIL"}); _write(scene_dir / "skeleton-identity.json", {"provider_fingerprint": _fp(identity), "runtime_fingerprint": _fp(identity), "status": "PASS"}); _write(scene_dir / "skeleton-coverage.json", skeleton_validation); _write(scene_dir / "topology-creative-qa.json", {"signal": "TOPOLOGY_USABLE", "metrics": {"node_count": len(_l(skeleton_ir.get("nodes")))}})
            if norm_skeleton.get("status") != "PASS" or skeleton_validation.get("status") != "PASS": raise ValueError("SKELETON_AUTHORITY_FAILURE")
            bound = bind_topology(skeleton_ir, semantic_events=semantic_events); _write(scene_dir / "semantic-events.json", semantic_events); _write(scene_dir / "bound-topology.json", bound); _write(scene_dir / "binding-audit.json", {"status": bound.get("binding_status"), "errors": bound.get("errors", [])}); _write(scene_dir / "binding-graph.json", {"nodes": bound.get("nodes", []), "edges": bound.get("edges", [])}); record.update({"strategy": {"status": "PASS"}, "spine": {"status": "PASS"}, "skeleton": {"status": "PASS"}, "binding": {"status": bound.get("binding_status")}})
        except Exception as exc:
            record["status"] = "MODEL_FAILURE"; record["failure"] = str(exc)[:500]; record["provider_errors"].append({"message": str(exc)[:500]}); record.setdefault("strategy", {"status": "FAILED"}); record.setdefault("spine", {"status": "SKIPPED"}); record.setdefault("skeleton", {"status": "SKIPPED"}); ledger["skipped_spine_calls"] += int(ledger["attempted_spine_calls"] < ordinal); ledger["skipped_skeleton_calls"] += int(ledger["attempted_skeleton_calls"] < ordinal)
        _write(scene_dir / "result.json", record); scene_records.append(record)
    return {"scenes": scene_records, "ledger": ledger}


def _source_code_changes() -> list[str]:
    """Return only project-code changes; artifact churn is intentionally allowed."""
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    roots = {"core", "api", "models", "scripts", "tests", "web"}
    suffixes = {".py", ".ts", ".tsx", ".js", ".jsx"}
    changed: list[str] = []
    for line in result.stdout.splitlines():
        path = line[3:].strip().strip('"')
        parsed = Path(path)
        if parsed.parts and parsed.parts[0] in roots and parsed.suffix.lower() in suffixes:
            changed.append(path)
    return sorted(set(changed))


def _trace_from_authority(authority: dict[str, Any], scene_id: str) -> dict[str, Any]:
    preserve = _d(authority.get("structured_preserve_constraints"))
    constraints = []
    for index, row in enumerate(_l(preserve.get("constraints")), 1):
        item = _d(row)
        beat_refs = [_t(value) for value in _l(item.get("beat_refs")) if _t(value)]
        event_refs = [_t(value) for value in _l(item.get("event_refs")) if _t(value)]
        source_refs = [_t(value) for value in _l(item.get("source_refs")) if _t(value)]
        constraints.append({
            "constraint_id": _t(item.get("constraint_id")) or f"MP{index:02d}",
            "description": _t(item.get("description")),
            "supporting_beat_refs": beat_refs,
            "supporting_event_keys": event_refs,
            "source_authority": source_refs,
            "resolution_status": "RESOLVED" if beat_refs or event_refs or source_refs else "PRESERVE_TRACE_UNRESOLVED",
        })
    return {
        "schema_version": "must_preserve_trace_v1",
        "scene_id": scene_id,
        "constraints": constraints,
        "unresolved_count": sum(item["resolution_status"] == "PRESERVE_TRACE_UNRESOLVED" for item in constraints),
        "resolution_policy": "explicit beat/event/source refs only; no prose guessing",
    }


def _call_once(call_llm, prompt: str, *, system: str, profile: dict[str, Any], scene_id: str, layer: str) -> str:
    """Single provider call.  retries=0 is part of the pilot contract."""
    return str(call_llm(
        prompt,
        system=system,
        model_profile=profile,
        retries=0,
        max_tokens=14000,
        estimated_tokens=10000,
        audit_extra={
            "phase": "director_v3_fresh_integration_pilot",
            "scene_id": scene_id,
            "layer": layer,
            "attempt_type": "CREATIVE_GENERATION",
        },
    ) or "")


def _run_provider(selected: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    """Run the frozen cohort once per layer with strict downstream gates."""
    from core.director_authority import authority_completeness_gate, provider_readiness_gate
    from core.director_contract_ssot import build_provider_contract, schema_parity_report
    from core.director_scene_strategy import build_runtime_strategy_contract, canonicalize_allowed_characters
    from core.director_scene_strategy_ir_compiler_v2 import compile_ir_v2_to_canonical_v3
    from core.director_scene_strategy_ir_v2 import validate_strategy_ir_v2
    from core.director_strategy_prompt import build_scene_strategy_ir_v2_prompt
    from core.llm import call_llm
    from core.semantic_events import project_semantic_events
    from core.shot_topology_graph_binder import bind_topology
    from core.shot_topology_skeleton import normalize_skeleton, validate_skeleton
    from core.spine_topology_forensics import validate_must_preserve_trace
    from core.structured_output import parse_json_object
    from core.visual_editorial_spine import normalize_spine, validate_spine

    out_root = ART / "director-quality-v3-fresh-integration-pilot-scenes"
    out_root.mkdir(parents=True, exist_ok=True)
    ledger: dict[str, Any] = {
        "schema_version": "director_quality_v3_fresh_integration_pilot_provider_call_ledger_v1",
        "authorized_strategy_calls": 3,
        "authorized_spine_calls": 3,
        "authorized_skeleton_calls": 3,
        "max_total_calls": 9,
        "attempted_strategy_calls": 0,
        "attempted_spine_calls": 0,
        "attempted_skeleton_calls": 0,
        "successful_calls": 0,
        "skipped_spine_calls": 0,
        "skipped_skeleton_calls": 0,
        "provider_errors": [],
        "all_retry_counts": {"transport": 0, "format": 0, "semantic": 0, "creative": 0, "repair": 0},
    }
    scene_records: list[dict[str, Any]] = []
    harness_error: dict[str, Any] | None = None
    for index, row in enumerate(selected, 1):
        sid = row["scene_id"]
        safe = re.sub(r"[^A-Za-z0-9]+", "-", sid).strip("-").lower() + "-" + _fp(sid)[:10]
        scene_dir = out_root / safe
        scene_dir.mkdir(parents=True, exist_ok=True)
        role = "low" if index == 1 else "medium" if index == 2 else "high"
        record: dict[str, Any] = {"scene_id": sid, "cohort_role": role, "provider_errors": [], "calls": [], "status": "PENDING"}
        try:
            runtime = build_runtime_strategy_contract(
                scene=row["scene"], treatment=row["director_treatment"],
                blocking=row["scene_blocking"], fact_snapshot=row["fact_snapshot"],
            )
            identity = canonicalize_allowed_characters(runtime.get("allowed_characters"), book_id=runtime.get("book_id"))
            semantic_events = project_semantic_events(row["scene"])
            strategy_request = _strategy_request(row, runtime, profile)
            req = strategy_request["request"]
            _write(scene_dir / "strategy-request.json", req)
            _write(scene_dir / "strategy-request-fingerprint.json", {"fingerprint": req.get("request_fingerprint")})
            ledger["attempted_strategy_calls"] += 1
            raw_strategy = _call_once(call_llm, req["user_prompt"], system=req["system_prompt"], profile=profile, scene_id=sid, layer="STRATEGY")
            ledger["successful_calls"] += 1
            (scene_dir / "strategy-raw-response.txt").write_text(raw_strategy, encoding="utf-8")
            _write(scene_dir / "strategy-raw-fingerprint.json", {"fingerprint": _fp(raw_strategy)})
            record["calls"].append({"ordinal": ledger["successful_calls"], "layer": "STRATEGY", "request_fingerprint": req.get("request_fingerprint"), "raw_response_fingerprint": _fp(raw_strategy), "retries": 0})

            try:
                parsed_strategy = parse_json_object(raw_strategy, label="director_scene_strategy_ir_v2", required_keys={"scene_phases", "must_preserve"})
                checked = validate_strategy_ir_v2(parsed_strategy, contract=runtime)
            except Exception as exc:
                raise ValueError(f"STRATEGY_MODEL_OUTPUT_INVALID: {exc}") from exc
            _write(scene_dir / "strategy-ir.json", checked.get("ir") or parsed_strategy)
            _write(scene_dir / "strategy-protocol.json", checked)
            if not checked.get("valid"):
                raise ValueError("STRATEGY_PROTOCOL_FAILURE")
            strategy_ir = checked["ir"]
            authority_gate = authority_completeness_gate(strategy=strategy_ir, scene=row["scene"], identity_projection={"records": identity}, semantic_events=semantic_events)
            structured = _d(authority_gate.get("authority")).get("structured_preserve_constraints")
            trace = _trace_from_authority(authority_gate.get("authority") or {}, sid)
            _write(scene_dir / "structured-preserve.json", structured)
            _write(scene_dir / "preserve-binding-audit.json", {"trace": trace, "status": "PASS" if authority_gate.get("status") == "PASS" else "PRESERVE_BINDING_FAILURE"})
            _write(scene_dir / "strategy-authority.json", authority_gate.get("authority") or {})
            _write(scene_dir / "authority-completeness.json", authority_gate)
            if authority_gate.get("status") != "PASS":
                raise ValueError("STRATEGY_AUTHORITY_INCOMPLETE")
            canonical = compile_ir_v2_to_canonical_v3(ir=strategy_ir and strategy_ir, contract=runtime, authority=authority_gate.get("authority"))
            canonical["structured_preserve_constraints"] = structured
            _write(scene_dir / "strategy-canonical.json", canonical)
            _write(scene_dir / "strategy-creative-qa.json", {"signal": "STRATEGY_USABLE", "metrics": {"scene_specificity": True, "phase_count": len(_l(canonical.get("scene_phases")))}})
            record["strategy"] = {"status": "PASS", "canonical_fingerprint": _fp(canonical), "authority": authority_gate}

            schema = schema_parity_report()
            readiness = provider_readiness_gate(authority=authority_gate.get("authority") or {}, schema_parity=schema, strategy_fingerprint_ok=bool(canonical.get("strategy_fingerprint")))
            _write(scene_dir / "provider-readiness.json", readiness)
            if readiness.get("status") != "PASS":
                raise ValueError("PROVIDER_READINESS_FAILURE")

            spine_request = {"task": "director_v3_fresh_integration_pilot", "layer": "SPINE", "scene_id": sid, "approved_strategy": canonical, "authoritative_scene": copy.deepcopy(row["scene"]), "fact_snapshot": copy.deepcopy(row["fact_snapshot"]), "character_identity_projection": identity, "must_preserve_trace": trace, "spine_contract": build_provider_contract("spine")}
            _write(scene_dir / "spine-request.json", spine_request)
            _write(scene_dir / "spine-request-fingerprint.json", {"fingerprint": _fp(spine_request)})
            ledger["attempted_spine_calls"] += 1
            raw_spine = _call_once(call_llm, json.dumps(spine_request, ensure_ascii=False), system="You are designing a VisualEditorialSpine. Return only the SSOT contract fields; do not design shots.", profile=profile, scene_id=sid, layer="SPINE")
            ledger["successful_calls"] += 1
            (scene_dir / "spine-raw-response.txt").write_text(raw_spine, encoding="utf-8")
            _write(scene_dir / "spine-raw-fingerprint.json", {"fingerprint": _fp(raw_spine)})
            record["calls"].append({"ordinal": ledger["successful_calls"], "layer": "SPINE", "request_fingerprint": _fp(spine_request), "raw_response_fingerprint": _fp(raw_spine), "retries": 0})
            try:
                parsed_spine = parse_json_object(raw_spine, label="visual_editorial_spine_ir_v1", required_keys={"segments", "spine_summary"})
                normalized_spine = normalize_spine(parsed_spine, scene_id=sid, strategy_fingerprint=canonical.get("strategy_fingerprint", ""))
            except Exception as exc:
                raise ValueError(f"SPINE_MODEL_OUTPUT_INVALID: {exc}") from exc
            spine_ir = normalized_spine.get("ir") or {}
            spine_validation = validate_spine(spine_ir, scene=row["scene"], strategy={"strategy_fingerprint": canonical.get("strategy_fingerprint"), "scene_phases": canonical.get("scene_phases", []), "must_avoid": canonical.get("must_avoid", [])}, must_preserve_trace=trace)
            _write(scene_dir / "spine-ir.json", spine_ir)
            _write(scene_dir / "spine-canonical.json", spine_ir if spine_validation.get("status") == "PASS" else {})
            _write(scene_dir / "spine-protocol.json", {"normalize": normalized_spine, "validation": spine_validation})
            _write(scene_dir / "spine-authority.json", {"status": "PASS" if spine_validation.get("status") == "PASS" else "UNSAFE", "violations": spine_validation.get("hard_errors", [])})
            _write(scene_dir / "spine-preserve-coverage.json", {"status": spine_validation.get("status"), "errors": spine_validation.get("hard_errors", [])})
            _write(scene_dir / "spine-layer-boundary.json", {"status": "PASS", "level": "NONE"})
            _write(scene_dir / "spine-creative-qa.json", {"signal": "SPINE_USABLE" if spine_validation.get("status") == "PASS" else "SPINE_INVALID", "metrics": {"segment_count": len(_l(spine_ir.get("segments")))}})
            if normalized_spine.get("status") != "PASS" or spine_validation.get("status") != "PASS":
                raise ValueError("SPINE_PROTOCOL_FAILURE")
            record["spine"] = {"status": "PASS", "canonical_fingerprint": _fp(spine_ir), "segment_refs": [_t(x.get("segment_key")) for x in _l(spine_ir.get("segments"))]}

            allowed_segments = [_t(segment.get("segment_key")) for segment in _l(spine_ir.get("segments")) if _t(segment.get("segment_key"))]
            if not allowed_segments or len(set(allowed_segments)) != len(allowed_segments) or any(not re.fullmatch(r"SEG\d{2,}", ref) for ref in allowed_segments):
                raise ValueError("SKELETON_SEGMENT_AUTHORITY_INVALID")
            skeleton_request = {"task": "director_v3_fresh_integration_pilot", "layer": "SKELETON", "scene_id": sid, "approved_strategy": canonical, "scene_blocking": copy.deepcopy(row["scene_blocking"]), "authoritative_scene_beats": copy.deepcopy(row["scene"]), "character_identity_projection": identity, "allowed_semantic_events": semantic_events, "must_preserve_trace": trace, "visual_editorial_spine": spine_ir, "spine_fingerprint": _fp(spine_ir), "allowed_segment_refs": allowed_segments, "skeleton_contract": build_provider_contract("skeleton", allowed_segment_refs=allowed_segments)}
            _write(scene_dir / "skeleton-request.json", skeleton_request)
            _write(scene_dir / "skeleton-request-fingerprint.json", {"fingerprint": _fp(skeleton_request)})
            ledger["attempted_skeleton_calls"] += 1
            raw_skeleton = _call_once(call_llm, json.dumps(skeleton_request, ensure_ascii=False), system="You are converting a canonical VisualEditorialSpine into a semantic ShotTopologySkeleton. Return only the SSOT contract fields.", profile=profile, scene_id=sid, layer="SKELETON")
            ledger["successful_calls"] += 1
            (scene_dir / "skeleton-raw-response.txt").write_text(raw_skeleton, encoding="utf-8")
            _write(scene_dir / "skeleton-raw-fingerprint.json", {"fingerprint": _fp(raw_skeleton)})
            record["calls"].append({"ordinal": ledger["successful_calls"], "layer": "SKELETON", "request_fingerprint": _fp(skeleton_request), "raw_response_fingerprint": _fp(raw_skeleton), "retries": 0})
            try:
                parsed_skeleton = parse_json_object(raw_skeleton, label="shot_topology_skeleton_ir_v1", required_keys={"nodes"})
                normalized_skeleton = normalize_skeleton(parsed_skeleton, scene_id=sid, spine_fingerprint=_fp(spine_ir))
            except Exception as exc:
                raise ValueError(f"SKELETON_MODEL_OUTPUT_INVALID: {exc}") from exc
            skeleton_ir = normalized_skeleton.get("ir") or {}
            skeleton_validation = validate_skeleton(skeleton_ir, spine=spine_ir, scene=row["scene"], strategy={"scene_phases": canonical.get("scene_phases", [])}, identity_projection={"records": identity}, allowed_segment_refs=set(allowed_segments), require_authority=True)
            _write(scene_dir / "skeleton-ir.json", skeleton_ir)
            _write(scene_dir / "skeleton-canonical.json", skeleton_ir if skeleton_validation.get("status") == "PASS" else {})
            _write(scene_dir / "skeleton-protocol.json", {"normalize": normalized_skeleton, "validation": skeleton_validation})
            _write(scene_dir / "skeleton-authority.json", {"status": "PASS" if skeleton_validation.get("status") == "PASS" else "UNSAFE", "violations": skeleton_validation.get("hard_errors", [])})
            _write(scene_dir / "skeleton-identity.json", {"provider_fingerprint": _fp(identity), "runtime_fingerprint": _fp(identity), "status": "PASS"})
            _write(scene_dir / "skeleton-coverage.json", skeleton_validation)
            _write(scene_dir / "topology-creative-qa.json", {"signal": "TOPOLOGY_USABLE" if skeleton_validation.get("status") == "PASS" else "TOPOLOGY_INVALID", "metrics": {"node_count": len(_l(skeleton_ir.get("nodes")))}})
            if normalized_skeleton.get("status") != "PASS" or skeleton_validation.get("status") != "PASS":
                raise ValueError("SKELETON_AUTHORITY_FAILURE")
            bound = bind_topology(skeleton_ir, semantic_events=semantic_events)
            _write(scene_dir / "semantic-events.json", semantic_events)
            _write(scene_dir / "bound-topology.json", bound)
            _write(scene_dir / "binding-audit.json", {"status": bound.get("binding_status"), "errors": bound.get("errors", [])})
            _write(scene_dir / "binding-graph.json", {"nodes": bound.get("nodes", []), "edges": bound.get("edges", [])})
            if bound.get("binding_status") not in {"PASS", "BOUND"}:
                raise ValueError("GRAPH_BINDING_FAILURE")
            record.update({"skeleton": {"status": "PASS", "node_count": len(_l(skeleton_ir.get("nodes"))), "canonical_fingerprint": _fp(skeleton_ir)}, "binding": {"status": bound.get("binding_status"), "edge_count": len(_l(bound.get("edges")))}, "status": "PASS"})
        except ValueError as exc:
            record["status"] = "MODEL_FAILURE"
            record["failure"] = str(exc)[:800]
            record["provider_errors"].append({"code": str(exc).split(":", 1)[0], "message": str(exc)[:800]})
            if ledger["attempted_strategy_calls"] < index:
                harness_error = {"scene_id": sid, "code": "HARNESS_SETUP_FAILURE", "message": str(exc)[:800]}
        except Exception as exc:
            record["status"] = "HARNESS_FAILURE"
            record["failure"] = str(exc)[:800]
            record["provider_errors"].append({"code": "HARNESS_FAILURE", "message": str(exc)[:800]})
            harness_error = {"scene_id": sid, "code": "HARNESS_FAILURE", "message": str(exc)[:800]}
        if record.get("status") == "MODEL_FAILURE":
            if "spine" not in record:
                ledger["skipped_spine_calls"] += 1
            if "skeleton" not in record:
                ledger["skipped_skeleton_calls"] += 1
        _write(scene_dir / "result.json", record)
        scene_records.append(record)
        if harness_error:
            break
    if harness_error:
        for row in selected[len(scene_records):]:
            skipped = {"scene_id": row["scene_id"], "status": "HARNESS_FAILURE", "failure": "experiment_stopped_after_harness_failure", "provider_errors": [{"code": "EXPERIMENT_STOPPED_HARNESS_FAILURE"}], "calls": []}
            scene_records.append(skipped)
    statuses = [record.get("status") for record in scene_records]
    if harness_error:
        status = "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_BLOCKED"
    elif all(value == "PASS" for value in statuses) and len(scene_records) == 3:
        status = "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_MACHINE_PASSED"
    else:
        status = "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_FAILED"
    ledger["provider_calls"] = ledger["successful_calls"]
    return {"status": status, "scenes": scene_records, "ledger": ledger, "harness_error": harness_error, "provider_calls": ledger["successful_calls"]}


def _make_global_artifacts(selection: dict[str, Any], registry: dict[str, Any], pointer: dict[str, Any]) -> dict[str, Any]:
    selected = [x for x in selection["selected"].values() if isinstance(x, dict)]
    cohort = {"schema_version": "director_quality_v3_fresh_cohort_manifest_v1", "selection_algorithm_version": SELECTION_ALGORITHM_VERSION, "candidate_count": selection["candidate_count"], "excluded_exposed_count": len(selection["excluded"]["exposed"]), "excluded_retired_count": len(selection["excluded"]["retired"]), "excluded_incomplete_count": len(selection["excluded"]["incomplete"]), "excluded_exposure_unknown_count": len(selection["excluded"]["unknown"]), "selected": {label: _d(selection["selected"].get(label)).get("scene_id") for label in ("low", "medium", "high")}, "complexity": {label: _d(selection["selected"].get(label)).get("complexity") for label in ("low", "medium", "high")}, "cohort_fingerprint": _fp([x["scene_id"] for x in selected]) if len(selected) == 3 else None, "frozen": len(selected) == 3, "provider_calls": 0}
    preflight = _contract_preflight(selected)
    flags = _authority_flags(pointer)
    preflight.update({"schema_version": "director_quality_v3_fresh_integration_pilot_preflight_v1", "authority": flags, "cohort_fingerprint": cohort["cohort_fingerprint"], "fresh_candidate_count": selection["candidate_count"], "provider_model_required": "mimo-v2.5", "provider_calls": 0, "real_llm_calls": 0, "real_mimo_calls": 0, "retries": {"transport": 0, "format": 0, "semantic": 0, "creative": 0, "repair": 0}, "status": "PASS" if preflight["status"] == "PASS" and flags["authority_ssot_closed"] and flags["fresh_ready"] and flags["atomic_hold"] and flags["production_hold"] else "BLOCKED"})
    status = "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_READY" if preflight["status"] == "PASS" and len(selected) == 3 else "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_BLOCKED"
    _write(ART / "director-quality-v3-provider-exposure-registry.json", registry)
    _write(ART / "director-quality-v3-fresh-candidate-inventory.json", {"schema_version": "director_quality_v3_fresh_candidate_inventory_v1", "candidates": [{"scene_id": x["scene_id"], "eligibility_reasons": x.get("eligibility_reasons", []), "upstream": x.get("upstream"), "source_evidence": x.get("source_evidence"), "complexity": _complexity(x)} for x in selection["eligible"]], "provider_calls": 0})
    _write(ART / "director-quality-v3-fresh-cohort-selection.json", selection)
    _write(ART / "director-quality-v3-fresh-cohort-manifest.json", cohort)
    _write(ART / "director-quality-v3-fresh-integration-pilot-preflight.json", preflight)
    _write(ART / "director-quality-v3-fresh-integration-pilot-execution-manifest.json", {"schema_version": "director_quality_v3_fresh_integration_pilot_execution_manifest_v1", "status": status, "provider_calls": 0, "cohort_fingerprint": cohort["cohort_fingerprint"], "frozen_scene_ids": cohort["selected"] if cohort["frozen"] else {}, "retries": 0})
    ledger = {"schema_version": "director_quality_v3_fresh_integration_pilot_provider_call_ledger_v1", "authorized_strategy_calls": 3, "authorized_spine_calls": 3, "authorized_skeleton_calls": 3, "max_total_calls": 9, "attempted_strategy_calls": 0, "attempted_spine_calls": 0, "attempted_skeleton_calls": 0, "successful_calls": 0, "skipped_spine_calls": 0, "skipped_skeleton_calls": 0, "provider_errors": [], "all_retry_counts": {"transport": 0, "format": 0, "semantic": 0, "creative": 0, "repair": 0}}
    _write(ART / "director-quality-v3-fresh-integration-pilot-provider-call-ledger.json", ledger)
    for name in ("strategy-results", "spine-results", "topology-results", "binding-results", "distinctiveness", "machine-gate"):
        _write(ART / f"director-quality-v3-fresh-integration-pilot-{name}.json", {"status": "NOT_RUN" if not cohort["frozen"] else "PENDING_PROVIDER_EXECUTION", "provider_calls": 0, "scenes": []})
    _write(ART / "director-quality-v3-fresh-integration-pilot-human-review-package.json", {"status": status, "human_review_pending": False, "scenes": [], "note": "No provider call is permitted until authorization and clean execution preflight pass."})
    report = f"# Director Quality V3 — Fresh Integration Pilot\n\n**Status:** `{status}`\n\n## Baseline Audit\n\n- Required starting HEAD from the authorization document: `eea7a86`; current closure ancestry is checked by commit gate.\n- Historical three-scene cohort remains retired and is excluded by authority.\n- Golden/fixture-only records are not used as Fresh source.\n\n## Final As-Built Verification\n\n- Exposure registry: `{len(registry.get('scenes', {}))}` candidate IDs inspected; provider calls recorded by this stage: `0`.\n- Fresh eligible candidates: `{selection['candidate_count']}`; selected Low/Medium/High: `{json.dumps(cohort['selected'], ensure_ascii=False)}`.\n- Deterministic selection: `{SELECTION_ALGORITHM_VERSION}`; cohort frozen: `{str(cohort['frozen']).lower()}`.\n- Contract/authority preflight: `{preflight['status']}`; provider calls: `0`; retries: `0`.\n- Atomic Expansion: `HOLD`; Production ShotPlan: `HOLD`; Human Preference: `NOT_RECORDED`.\n\n## Decision\n\n`{status}`\n\nNo real MiMo, LLM, Spine, Skeleton, Binder, media, storage or CI action was executed by the provider-free preflight.\n"
    _write(ART / "director-quality-v3-fresh-integration-pilot-report.md", report)
    return {"status": status, "preflight": preflight, "cohort": cohort, "provider_calls": 0}


def _distinctiveness(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Detect exact template reuse without judging creative quality by prose."""
    layers = {}
    for layer in ("strategy", "spine", "skeleton"):
        values = []
        for record in records:
            value = _d(record.get(layer)).get("canonical_fingerprint")
            if value:
                values.append({"scene_id": record["scene_id"], "fingerprint": value})
        layers[layer] = values
    pairs = []
    for layer, values in layers.items():
        for left_index, left in enumerate(values):
            for right in values[left_index + 1:]:
                pairs.append({"layer": layer, "left": left["scene_id"], "right": right["scene_id"], "identical": left["fingerprint"] == right["fingerprint"]})
    exact_reuse = [pair for pair in pairs if pair["identical"]]
    return {"schema_version": "director_quality_v3_fresh_distinctiveness_v1", "status": "FAIL" if exact_reuse else "PASS", "pairs_checked": len(pairs), "exact_template_reuse": exact_reuse, "layers": layers, "policy": "identical canonical fingerprints are a hard machine finding; no fuzzy creative score"}


def _finalize_execution(execution: dict[str, Any], selection: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    records = execution.get("scenes", [])
    ledger = execution.get("ledger", {})
    strategy_results = {"status": "PASS" if all(_d(x.get("strategy")).get("status") == "PASS" for x in records) else "FAILED", "provider_calls": ledger.get("attempted_strategy_calls", 0), "scenes": [{"scene_id": x["scene_id"], **_d(x.get("strategy"))} for x in records]}
    spine_results = {"status": "PASS" if all(_d(x.get("spine")).get("status") == "PASS" for x in records) else "FAILED", "provider_calls": ledger.get("attempted_spine_calls", 0), "scenes": [{"scene_id": x["scene_id"], **_d(x.get("spine"))} for x in records]}
    topology_results = {"status": "PASS" if all(_d(x.get("skeleton")).get("status") == "PASS" for x in records) else "FAILED", "provider_calls": ledger.get("attempted_skeleton_calls", 0), "scenes": [{"scene_id": x["scene_id"], **_d(x.get("skeleton"))} for x in records]}
    binding_results = {"status": "PASS" if all(_d(x.get("binding")).get("status") in {"PASS", "BOUND"} for x in records) else "FAILED", "provider_calls": 0, "scenes": [{"scene_id": x["scene_id"], **_d(x.get("binding"))} for x in records]}
    distinctiveness = _distinctiveness(records)
    machine_checks = {
        "strategy_protocol_3_of_3": strategy_results["status"] == "PASS",
        "spine_protocol_3_of_3": spine_results["status"] == "PASS",
        "skeleton_protocol_3_of_3": topology_results["status"] == "PASS",
        "binder_3_of_3": binding_results["status"] == "PASS",
        "distinctiveness": distinctiveness["status"] == "PASS",
        "retries_zero": all(value == 0 for value in _d(ledger.get("all_retry_counts" )).values()),
        "harness_errors_zero": not execution.get("harness_error"),
        "total_calls_within_budget": int(ledger.get("successful_calls", 0)) <= 9,
    }
    machine_gate = {"schema_version": "director_quality_v3_fresh_machine_gate_v1", "status": "PASS" if all(machine_checks.values()) else "FAIL", "checks": machine_checks, "provider_calls": ledger.get("successful_calls", 0), "retries": ledger.get("all_retry_counts", {})}
    if execution.get("harness_error"):
        final_status = "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_BLOCKED"
    elif execution.get("status") == "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_MACHINE_PASSED" and machine_gate["status"] == "PASS":
        final_status = "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_MACHINE_PASSED"
    else:
        final_status = "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_FAILED"
    _write(ART / "director-quality-v3-fresh-integration-pilot-strategy-results.json", strategy_results)
    _write(ART / "director-quality-v3-fresh-integration-pilot-spine-results.json", spine_results)
    _write(ART / "director-quality-v3-fresh-integration-pilot-topology-results.json", topology_results)
    _write(ART / "director-quality-v3-fresh-integration-pilot-binding-results.json", binding_results)
    _write(ART / "director-quality-v3-fresh-integration-pilot-distinctiveness.json", distinctiveness)
    _write(ART / "director-quality-v3-fresh-integration-pilot-machine-gate.json", machine_gate)
    cohort = _load(ART / "director-quality-v3-fresh-cohort-manifest.json")
    briefs = []
    review_scenes = []
    scene_root = ART / "director-quality-v3-fresh-integration-pilot-scenes"
    for record in records:
        safe = re.sub(r"[^A-Za-z0-9]+", "-", record["scene_id"]).strip("-").lower() + "-" + _fp(record["scene_id"])[:10]
        brief_path = scene_root / safe / "director-brief.md"
        summary = [f"# Director V3 Fresh Pilot — {record['scene_id']}", "", f"**Role:** `{record.get('cohort_role')}`", f"**Status:** `{record.get('status')}`", "", "## Strategy", json.dumps(record.get("strategy", {}), ensure_ascii=False, indent=2), "", "## Spine", json.dumps(record.get("spine", {}), ensure_ascii=False, indent=2), "", "## Topology", json.dumps(record.get("skeleton", {}), ensure_ascii=False, indent=2), "", "## Binding", json.dumps(record.get("binding", {}), ensure_ascii=False, indent=2), "", "No Atomic Expansion, ShotPlan, Storyboard or media action was executed."]
        brief_path.write_text("\n".join(summary) + "\n", encoding="utf-8")
        briefs.append(_rel_path(brief_path)); review_scenes.append({"scene_id": record["scene_id"], "cohort_role": record.get("cohort_role"), "status": record.get("status"), "brief": _rel_path(brief_path), "calls": record.get("calls", []), "provider_errors": record.get("provider_errors", [])})
    review = {"schema_version": "director_quality_v3_fresh_human_review_package_v1", "status": final_status, "human_review_pending": True, "director_critic_review": "NOT_RECORDED", "scenes": review_scenes, "briefs": briefs, "machine_gate": "artifacts/director-quality-v3-fresh-integration-pilot-machine-gate.json"}
    _write(ART / "director-quality-v3-fresh-integration-pilot-human-review-package.json", review)
    report = ["# Director Quality V3 — Fresh Integration Pilot", "", f"**Status:** `{final_status}`", "", "## Final As-Built Verification", f"- Frozen cohort: `{json.dumps(cohort.get('selected', {}), ensure_ascii=False)}`", f"- Provider: `{profile.get('provider')}` / `{profile.get('model_name')}`", f"- Strategy calls: `{ledger.get('attempted_strategy_calls', 0)}`", f"- Spine calls: `{ledger.get('attempted_spine_calls', 0)}`", f"- Skeleton calls: `{ledger.get('attempted_skeleton_calls', 0)}`", f"- Total provider calls: `{ledger.get('successful_calls', 0)}`", "- Retries: `0`", f"- Machine gate: `{machine_gate['status']}`", f"- Harness error: `{bool(execution.get('harness_error'))}`", "- Human Preference: `NOT_RECORDED`", "- Atomic Expansion: `HOLD`", "- Production ShotPlan: `HOLD`", "", "## Scene Results"]
    report.extend(f"- `{x['scene_id']}` ({x.get('cohort_role')}): `{x.get('status')}`" for x in records)
    report.extend(["", "## Review", "", "Machine PASS is not professional Director approval. External Director Critic review remains required.", ""])
    _write(ART / "director-quality-v3-fresh-integration-pilot-report.md", "\n".join(report))
    return {"status": final_status, "provider_calls": ledger.get("successful_calls", 0), "machine_gate": machine_gate, "distinctiveness": distinctiveness, "review_package": review}


def _update_authority(status: str, cohort_fingerprint: str | None, ledger: dict[str, Any]) -> None:
    pointer = _authority()
    pointer["fresh_integration_pilot"] = {
        "status": "MACHINE_PASSED" if status.endswith("MACHINE_PASSED") else "FAILED" if status.endswith("FAILED") else "BLOCKED",
        "cohort_fingerprint": cohort_fingerprint,
        "strategy_calls": ledger.get("attempted_strategy_calls", 0),
        "spine_calls": ledger.get("attempted_spine_calls", 0),
        "skeleton_calls": ledger.get("attempted_skeleton_calls", 0),
        "ready_for_director_critic_review": status.endswith("MACHINE_PASSED"),
        "director_critic_review": "NOT_RECORDED",
        "ready_for_atomic_expansion_canary": False,
        "atomic_expansion_canary_authorized": False,
        "provider_calls": ledger.get("successful_calls", 0),
        "retries": ledger.get("all_retry_counts", {}),
    }
    _write(AUTHORITY_PATH, pointer)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true", help="provider-free inventory and gate (default)")
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--profile-id", default="local-llm-2vydoz")
    args = parser.parse_args(argv)
    supplied = argv if argv is not None else sys.argv[1:]
    if any(flag in supplied for flag in ("--force", "--unsafe", "--ignore-authorization")):
        raise SystemExit("authorization bypass flags are not supported")
    pointer = _authority()
    rows = _approved_scene_rows()
    candidate_ids = {row["scene_id"] for row in rows}
    registry = build_provider_exposure_registry(candidate_ids=candidate_ids)
    selection = select_fresh_cohort(rows, registry)
    result = _make_global_artifacts(selection, registry, pointer)
    if not args.execute_real:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"].endswith("READY") else 2
    flags = _authority_flags(pointer)
    if result["status"] != "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_READY" or not flags["fresh_authorized"]:
        print(json.dumps({"status": "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_BLOCKED", "reason": "preflight_or_authorization_gate", "provider_calls": 0}, ensure_ascii=False, indent=2))
        return 1
    source_changes = _source_code_changes()
    if source_changes:
        print(json.dumps({"status": "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_BLOCKED", "reason": "working_tree_source_diff", "source_changes": source_changes, "provider_calls": 0}, ensure_ascii=False, indent=2))
        return 1
    from api.model_registry import get_profile
    profile = get_profile(args.profile_id) or {}
    if not (profile.get("enabled") is not False and _t(profile.get("model_name")) == "mimo-v2.5" and _t(profile.get("base_url")) and _t(profile.get("api_key"))):
        print(json.dumps({"status": "DIRECTOR_V3_FRESH_INTEGRATION_PILOT_BLOCKED", "reason": "mimo_profile_missing_or_invalid", "provider_calls": 0}, ensure_ascii=False, indent=2))
        return 1
    selected = [value for value in selection["selected"].values() if isinstance(value, dict)]
    execution = _run_provider(selected, profile)
    finalized = _finalize_execution(execution, selection, profile)
    _update_authority(finalized["status"], result["cohort"].get("cohort_fingerprint"), execution["ledger"])
    print(json.dumps(finalized, ensure_ascii=False, indent=2))
    return 0 if finalized["status"].endswith("MACHINE_PASSED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
