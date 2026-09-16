"""Provider-free Fresh Approved Record Pool infrastructure.

This module deliberately treats freshness as a property of the source
material, not of a scene id.  It consumes persisted source records and
deterministic fingerprints only; it never calls a model, creates approvals, or
mutates production state.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "director_v3_fresh_approved_record_pool_v1"
INTAKE_SCHEMA_VERSION = "fresh_approved_record_intake_v1"
RETIRED_SCENES = {
    "book990402:e1:红伞幻影（一）",
    "book990402:e1:红伞幻影（二）",
    "book990402:e2:回声照相馆",
    "book990402:e2:暗房门口的试探",
    "book990402:e3:暗房惊魂",
    "book990402:e3:暗房惊魂（2）",
}


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _t(value: Any) -> str:
    return str(value or "").strip()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_source_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text, flags=re.UNICODE)
    return text.strip()


def source_fingerprints(*, source_records: Iterable[dict[str, Any]], source_text: str, beats: Iterable[Any]) -> dict[str, str]:
    records = [dict(_d(item)) for item in source_records]
    beat_rows = []
    for item in beats:
        row = _d(item)
        beat_rows.append({
            "id": _t(row.get("beat_id") or row.get("id") or row.get("seq")),
            "type": _t(row.get("type")),
            "event": normalize_source_text(row.get("event") or row.get("description")),
        })
    normalized = normalize_source_text(source_text)
    return {
        "source_fingerprint": fingerprint({"records": records, "text": normalized, "beats": beat_rows}),
        "normalized_source_text_hash": fingerprint(normalized),
        "beat_sequence_fingerprint": fingerprint(beat_rows),
    }


def _json(value: Any, default: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _scene_names_from_script(content: str) -> list[dict[str, Any]]:
    """Extract only explicit scene structures; never invent a creative scene."""
    parsed = _json(content, None)
    if isinstance(parsed, dict) and isinstance(parsed.get("scenes"), list):
        result = []
        for index, item in enumerate(parsed["scenes"], 1):
            row = _d(item)
            name = _t(row.get("name") or row.get("scene_name") or row.get("title"))
            if name:
                result.append({"name": name, "payload": row, "text": canonical_json(row), "beats": _l(row.get("beats"))})
        if result:
            return result
    result = []
    # Markdown screenplay imports use explicit scene headings.  The heading
    # itself is source evidence, not a generated scene description.
    heading = re.compile(r"^\s*#{1,6}\s*(?:场景\s*)?\d*\s*[：:]\s*(.+?)\s*$", re.MULTILINE)
    for match in heading.finditer(content or ""):
        raw = _t(match.group(1)).strip("-— ")
        if raw:
            result.append({"name": raw, "payload": {"heading": raw}, "text": raw, "beats": []})
    return result


def _latest(c: sqlite3.Connection, table: str, where: str, params: tuple[Any, ...], status: str | None = None) -> sqlite3.Row | None:
    sql = f"select * from {table} where {where}"
    values = list(params)
    if status is not None:
        sql += " and status=?"
        values.append(status)
    sql += " order by revision desc, id desc limit 1"
    return c.execute(sql, tuple(values)).fetchone()


def _upstream(c: sqlite3.Connection, book_id: int, episode: int, scene_name: str) -> dict[str, Any]:
    ir = _latest(c, "script_ir_versions", "book_id=? and episode=?", (book_id, episode), None)
    qualified = bool(ir and _t(ir["status"]) == "qualified" and _t(ir["validation_status"]) == "qualified")
    fact = None
    if ir and _t(ir["source_fact_snapshot_id"]):
        fact = c.execute("select * from fact_snapshots where id=?", (ir["source_fact_snapshot_id"],)).fetchone()
    treatment = _latest(c, "director_treatments", "book_id=? and episode=? and scene_name=?", (book_id, episode, scene_name), "approved")
    blocking = _latest(c, "scene_blockings", "book_id=? and episode=? and scene_name=?", (book_id, episode, scene_name), "approved")
    fact_confirmed = bool(fact and _t(fact["status"]) == "confirmed")
    identity_valid = False
    beat_valid = False
    if blocking:
        participants = _json(blocking["participants"], [])
        identity_valid = bool(participants) and all(_t(_d(x).get("character_id") or _d(x).get("id")) and _t(_d(x).get("name")) for x in _l(participants))
    return {
        "fact_snapshot": {"status": _t(fact["status"]) if fact else "missing", "id": int(fact["id"]) if fact else None, "payload_hash": _t(fact["payload_hash"]) if fact else ""},
        "script_ir": {"status": _t(ir["status"]) if ir else "missing", "validation_status": _t(ir["validation_status"]) if ir else "missing", "id": int(ir["id"]) if ir else None, "payload_hash": _t(ir["payload_hash"]) if ir else "", "qualified": qualified},
        "director_treatment": {"status": _t(treatment["status"]) if treatment else "missing", "id": int(treatment["id"]) if treatment else None, "source_script_hash": _t(treatment["source_script_hash"]) if treatment else ""},
        "scene_blocking": {"status": _t(blocking["status"]) if blocking else "missing", "id": int(blocking["id"]) if blocking else None, "source_script_hash": _t(blocking["source_script_hash"]) if blocking else "", "identity_valid": identity_valid, "participants": participants if blocking else [], "identity_fingerprint": fingerprint(participants) if blocking else ""},
        "fact_confirmed": fact_confirmed,
        "identity_authority_valid": identity_valid,
        "beat_authority_valid": beat_valid,
    }


def _candidate(*, book_id: int, episode: int, scene_name: str, source_records: list[dict[str, Any]], source_text: str, beats: list[Any], upstream: dict[str, Any]) -> dict[str, Any]:
    scene_id = f"book{book_id}:e{episode}:{scene_name}"
    fps = source_fingerprints(source_records=source_records, source_text=source_text, beats=beats)
    beat_ids = [_t(_d(x).get("beat_id") or _d(x).get("id") or _d(x).get("seq")) for x in beats]
    upstream = dict(upstream)
    upstream["beat_authority_valid"] = bool(beat_ids)
    upstream["identity_authority_valid"] = bool(upstream.get("identity_authority_valid"))
    reasons: list[str] = []
    if not upstream.get("fact_confirmed"): reasons.append("FACT_SNAPSHOT_NOT_CONFIRMED")
    if not upstream.get("script_ir", {}).get("qualified"): reasons.append("SCRIPT_IR_NOT_QUALIFIED")
    if upstream.get("director_treatment", {}).get("status") != "approved": reasons.append("TREATMENT_NOT_APPROVED")
    if upstream.get("scene_blocking", {}).get("status") != "approved": reasons.append("BLOCKING_NOT_APPROVED")
    if not upstream.get("identity_authority_valid"): reasons.append("IDENTITY_AUTHORITY_INVALID")
    if not upstream.get("beat_authority_valid"): reasons.append("BEAT_AUTHORITY_INVALID")
    if not _t(scene_name) or not isinstance(book_id, int) or episode < 1: reasons.append("SCENE_IDENTITY_INVALID")
    return {
        "scene_id": scene_id,
        "book_id": book_id,
        "episode": episode,
        "scene_name": scene_name,
        "source_real": bool(source_records),
        "source_records": source_records,
        "source_text": source_text,
        "beats": beats,
        "fingerprints": fps,
        "upstream": upstream,
        "eligibility_reasons": reasons,
    }


def scan_source_material(db_path: Path) -> list[dict[str, Any]]:
    """Scan persisted DB source records and return deterministic candidates."""
    if not db_path.exists():
        return []
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    merged: dict[tuple[int, int, str], dict[str, Any]] = {}

    def add(book_id: int, episode: int, name: str, record: dict[str, Any], text: str, beats: list[Any]) -> None:
        if not name:
            return
        key = (int(book_id), int(episode), name)
        item = merged.setdefault(key, {"records": [], "texts": [], "beats": []})
        item["records"].append(record); item["texts"].append(text); item["beats"].extend(beats)

    for row in c.execute("select * from script_ir_versions order by book_id, episode, revision, id"):
        payload = _json(row["payload_json"], {})
        for scene in _l(_d(payload).get("scenes")):
            scene = _d(scene); name = _t(scene.get("name") or scene.get("scene_name"))
            add(int(row["book_id"]), int(row["episode"]), name, {"kind": "script_ir", "id": int(row["id"]), "status": _t(row["status"]), "provenance": "database.script_ir_versions"}, canonical_json(scene), _l(scene.get("beats")))

    for row in c.execute("select * from scripts order by book_id, episode, id"):
        for scene in _scene_names_from_script(_t(row["content"])):
            add(int(row["book_id"]), int(row["episode"]), scene["name"], {"kind": "script", "id": int(row["id"]), "status": _t(row["status"]), "provenance": "database.scripts"}, scene["text"], _l(scene.get("beats")))

    for row in c.execute("select * from chapters order by book_id, seq, id"):
        scenes = _json(row["scenes"], [])
        for index, scene in enumerate(_l(scenes), 1):
            scene = _d(scene)
            # Chapter analysis does not provide a creative scene name.  The
            # stable chapter/index identity is retained and marked incomplete;
            # it is never silently joined to an approved record.
            name = f"chapter-{int(row['seq']):02d}-scene-{index:02d}"
            add(int(row["book_id"]), int(row["seq"]), name, {"kind": "chapter", "id": int(row["id"]), "status": _t(row["status"]), "provenance": "database.chapters"}, canonical_json(scene), _l(scene.get("beats")))

    result = []
    for (book_id, episode, name), item in sorted(merged.items()):
        upstream = _upstream(c, book_id, episode, name)
        candidate = _candidate(book_id=book_id, episode=episode, scene_name=name, source_records=item["records"], source_text="\n".join(item["texts"]), beats=item["beats"], upstream=upstream)
        result.append(candidate)
    c.close()
    return result


class FreshApprovedRecordEligibilityGate:
    """Hard gate; every failed requirement is explicit and machine-readable."""

    def evaluate(self, candidate: dict[str, Any], *, exposure_status: str = "NOT_EXPOSED", retired: bool = False, denied_fingerprints: set[str] | None = None) -> dict[str, Any]:
        denied = denied_fingerprints or set()
        reasons = list(candidate.get("eligibility_reasons") or [])
        if not candidate.get("source_real"): reasons.append("SOURCE_NOT_REAL")
        upstream = _d(candidate.get("upstream"))
        if not upstream.get("fact_confirmed"): reasons.append("FACT_SNAPSHOT_NOT_CONFIRMED")
        if not _d(upstream.get("script_ir")).get("qualified"): reasons.append("SCRIPT_IR_NOT_QUALIFIED")
        if _t(_d(upstream.get("director_treatment")).get("status")) != "approved": reasons.append("TREATMENT_NOT_APPROVED")
        if _t(_d(upstream.get("scene_blocking")).get("status")) != "approved": reasons.append("BLOCKING_NOT_APPROVED")
        if exposure_status == "EXPOSED": reasons.append("PROVIDER_EXPOSED")
        elif exposure_status == "EXPOSURE_UNKNOWN": reasons.append("EXPOSURE_UNKNOWN")
        if retired: reasons.append("SCENE_RETIRED")
        fps = _d(candidate.get("fingerprints"))
        if not _t(fps.get("source_fingerprint")): reasons.append("SOURCE_FINGERPRINT_INVALID")
        if any(_t(fps.get(key)) in denied for key in ("source_fingerprint", "normalized_source_text_hash", "beat_sequence_fingerprint")): reasons.append("SOURCE_CONTENT_ALREADY_EXPOSED" if exposure_status != "EXPOSURE_UNKNOWN" else "SOURCE_CONTENT_DENIED")
        if not upstream.get("identity_authority_valid"): reasons.append("IDENTITY_AUTHORITY_INVALID")
        if not upstream.get("beat_authority_valid"): reasons.append("BEAT_AUTHORITY_INVALID")
        if not _t(candidate.get("scene_id")) or int(candidate.get("book_id") or 0) <= 0 or int(candidate.get("episode") or 0) <= 0: reasons.append("SCENE_IDENTITY_INVALID")
        unique = list(dict.fromkeys(reasons))
        return {"status": "FRESH_APPROVED_RECORD_ELIGIBLE" if not unique else "NOT_ELIGIBLE", "eligible": not unique, "reasons": unique}


def classify_candidate(candidate: dict[str, Any], *, exposure_status: str, retired: bool, denied_fingerprints: set[str]) -> dict[str, Any]:
    gate = FreshApprovedRecordEligibilityGate().evaluate(candidate, exposure_status=exposure_status, retired=retired, denied_fingerprints=denied_fingerprints)
    if not candidate.get("source_real"):
        classification = "SYNTHETIC_OR_FIXTURE"
    elif retired:
        classification = "RETIRED"
    elif exposure_status == "EXPOSED":
        classification = "PROVIDER_EXPOSED"
    elif exposure_status == "EXPOSURE_UNKNOWN":
        classification = "EXPOSURE_UNKNOWN"
    elif gate["eligible"]:
        classification = "SOURCE_REAL_READY"
    else:
        classification = "SOURCE_REAL_UPSTREAM_INCOMPLETE"
    return {**candidate, "classification": classification, "exposure_status": exposure_status, "retired": retired, "eligibility": gate}


def build_pool(candidates: list[dict[str, Any]], *, retired_scene_ids: set[str] = RETIRED_SCENES, exposed_scene_ids: set[str] | None = None, exposure_unknown_scene_ids: set[str] | None = None, denied_fingerprints: set[str] | None = None) -> dict[str, Any]:
    exposed = exposed_scene_ids or set(); unknown = exposure_unknown_scene_ids or set(); denied = denied_fingerprints or set(); classified = []
    for candidate in candidates:
        sid = _t(candidate.get("scene_id")); status = "EXPOSED" if sid in exposed else ("EXPOSURE_UNKNOWN" if sid in unknown else "NOT_EXPOSED")
        classified.append(classify_candidate(candidate, exposure_status=status, retired=sid in retired_scene_ids, denied_fingerprints=denied))
    eligible = [row for row in classified if row["eligibility"]["eligible"] and row["classification"] == "SOURCE_REAL_READY"]
    return {"schema_version": SCHEMA_VERSION, "eligible_scene_count": len(eligible), "scenes": eligible, "inventory": classified, "retired_scene_count": sum(x["classification"] == "RETIRED" for x in classified), "exposure_unknown_count": sum(x["classification"] == "EXPOSURE_UNKNOWN" for x in classified), "provider_calls": 0, "synthetic_scenes_created": 0, "approval_fabricated": False, "cohort_frozen": False}


def build_intake(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for candidate in candidates:
        rows.append({"source_scene_id": candidate["scene_id"], "book_id": candidate["book_id"], "episode": candidate["episode"], "scene_name": candidate["scene_name"], "source_fingerprint": _d(candidate.get("fingerprints")).get("source_fingerprint"), "fact_snapshot_status": _d(candidate.get("upstream")).get("fact_snapshot", {}).get("status"), "script_ir_status": "qualified" if _d(candidate.get("upstream")).get("script_ir", {}).get("qualified") else _d(candidate.get("upstream")).get("script_ir", {}).get("status"), "director_treatment_status": _d(candidate.get("upstream")).get("director_treatment", {}).get("status"), "scene_blocking_status": _d(candidate.get("upstream")).get("scene_blocking", {}).get("status"), "provider_exposure_status": candidate.get("exposure_status", "NOT_EXPOSED"), "retirement_status": "RETIRED" if candidate.get("retired") else "ACTIVE", "missing_requirements": list(_d(candidate.get("eligibility")).get("reasons") or candidate.get("eligibility_reasons") or []), "approval_fabricated": False})
    return {"schema_version": INTAKE_SCHEMA_VERSION, "approval_fabricated": False, "provider_calls": 0, "records": rows}


def build_exposure_fingerprint_registry(classified: list[dict[str, Any]], *, retired_scene_ids: set[str] = RETIRED_SCENES, exposed_scene_ids: set[str] | None = None) -> dict[str, Any]:
    exposed_ids = exposed_scene_ids or set(); retired = {}; exposed = {}
    for row in classified:
        sid = _t(row.get("scene_id")); fps = _d(row.get("fingerprints"))
        if sid in retired_scene_ids: retired[sid] = fps
        if sid in exposed_ids: exposed[sid] = fps
    denied = sorted({value for fps in list(retired.values()) + list(exposed.values()) for value in fps.values() if value})
    return {"schema_version": "director_v3_provider_exposed_source_fingerprints_v1", "retired_scene_fingerprints": retired, "exposed_scene_fingerprints": exposed, "denied_fingerprints": denied, "provider_calls": 0}
