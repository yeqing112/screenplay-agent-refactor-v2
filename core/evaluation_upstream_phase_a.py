"""Provider-boundary adapter for Director V3 Evaluation Upstream Phase A.

The production FactSnapshot and ScriptIR modules intentionally accept already
structured payloads.  This adapter is the narrow evaluation-only boundary
between an immutable short-story package and those deterministic authorities.
It never persists to the production database, never invents canonical IDs, and
never treats a model observation as a confirmed source fact.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from core.fact_snapshot import build_fact_snapshot, validate_fact_records
from core.script_ir import build_script_ir, validate_script_ir

SOURCE_PACKAGE_ID = "SRC79f12d1b7f5eb828"
SOURCE_VERSION_ID = "SRC79f12d1b7f5eb828:V01:d001bab5cc82"
EXPECTED_RAW_HASH = "d001bab5cc820ae3b99f2f7a43ad2f4022e62073acb036a9c1c0e7d4bb888368"
EXPECTED_NORMALIZED_HASH = "48abfc0416698f580499dc728514003664cc3497eb092aa4803fd08cf8873d9f"
PACKAGE_DIR = Path("work/intake/director_v3/evaluation_packages")
PACKAGE_PATH = PACKAGE_DIR / f"{SOURCE_PACKAGE_ID}.json"
RAW_PATH = PACKAGE_DIR / f"{SOURCE_PACKAGE_ID}.raw"

PROVENANCE_KEYS = (
    "source_package_id", "source_version_id", "source_class", "source_authorship",
    "human_authored", "blind_human_origin_eligible",
    "functional_pipeline_evaluation_eligible", "user_authorized_for_evaluation",
    "raw_source_hash", "normalized_source_hash",
)

DIRECTING_KEYS = {
    "camera", "camera_position", "camera_movement", "shot_size", "lens",
    "framing", "composition_intent", "lighting_design", "director_note",
    "visual_grammar", "shot_plan", "storyboard", "prompt", "negative_prompt",
}


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _t(value: Any) -> str:
    return str(value or "").strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _payload_object(value: Any, *, label: str, required_keys: set[str] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Parse one provider response without performing retries or repair calls."""
    if isinstance(value, dict):
        return value, []
    try:
        from core.structured_output import parse_json_object
        parsed = parse_json_object(str(value or ""), label=label, required_keys=required_keys)
        return parsed, []
    except Exception as exc:
        return {}, [{"code": "PROVIDER_OUTPUT_PARSE_ERROR", "label": label, "message": str(exc)[:400]}]


def evaluation_book_id(package_id: str = SOURCE_PACKAGE_ID) -> int:
    """Return a stable logical integer ID, never a production Book row."""
    digest = hashlib.sha256(_t(package_id).encode("utf-8")).hexdigest()
    return 900_000_000 + int(digest[:8], 16) % 99_000_000


def load_and_verify_source(
    *,
    package_path: Path = PACKAGE_PATH,
    raw_path: Path = RAW_PATH,
    expected_package_id: str = SOURCE_PACKAGE_ID,
    expected_version_id: str = SOURCE_VERSION_ID,
    expected_raw_hash: str = EXPECTED_RAW_HASH,
    expected_normalized_hash: str = EXPECTED_NORMALIZED_HASH,
) -> dict[str, Any]:
    """Load the immutable package and verify both hashes/provenance metadata."""
    manifest = json.loads(package_path.read_text(encoding="utf-8"))
    package = _d(manifest.get("package"))
    # Hash the immutable bytes exactly as stored.  ``Path.read_text`` performs
    # universal-newline conversion on Windows, which would change the digest
    # of a CRLF source package even though its content is untouched.
    raw_bytes = raw_path.read_bytes()
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    raw = raw_bytes.decode("utf-8")
    errors: list[dict[str, Any]] = []
    if _t(package.get("source_package_id")) != expected_package_id:
        errors.append({"code": "SOURCE_PACKAGE_ID_MISMATCH"})
    if _t(package.get("source_version_id")) != expected_version_id:
        errors.append({"code": "SOURCE_VERSION_ID_MISMATCH"})
    if raw_hash != expected_raw_hash or _t(package.get("raw_source_hash")) != expected_raw_hash:
        errors.append({"code": "SOURCE_RAW_HASH_MISMATCH", "actual": raw_hash})
    if _t(package.get("normalized_source_hash")) != expected_normalized_hash:
        errors.append({"code": "SOURCE_NORMALIZED_HASH_MISMATCH"})
    required_provenance = {
        "source_class": "EVALUATION_ONLY",
        "source_authorship": "AI_GENERATED",
        "human_authored": False,
        "blind_human_origin_eligible": False,
        "functional_pipeline_evaluation_eligible": True,
        "user_authorized_for_evaluation": True,
    }
    provenance = {
        "source_package_id": _t(package.get("source_package_id")),
        "source_version_id": _t(package.get("source_version_id")),
        "source_class": package.get("source_class"),
        "source_authorship": package.get("source_authorship"),
        "human_authored": package.get("human_authored"),
        "blind_human_origin_eligible": package.get("blind_human_origin_eligible"),
        "functional_pipeline_evaluation_eligible": package.get("functional_pipeline_evaluation_eligible"),
        "user_authorized_for_evaluation": package.get("user_authorized_for_evaluation"),
        "raw_source_hash": expected_raw_hash,
        "normalized_source_hash": expected_normalized_hash,
    }
    for key, expected in required_provenance.items():
        if package.get(key) != expected:
            errors.append({"code": "SOURCE_PROVENANCE_MISMATCH", "field": key})
    return {
        "status": "PASS" if not errors else "FAIL",
        "manifest": manifest,
        "package": package,
        "raw_text": raw,
        "raw_hash": raw_hash,
        "normalized_hash": _t(package.get("normalized_source_hash")),
        "provenance": provenance,
        "errors": errors,
    }


def build_call_graph(*, provider_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Describe the two-call maximum without importing or contacting a client."""
    config = _d(provider_config)
    return {
        "schema_version": "director_v3_evaluation_upstream_phase_a_callgraph_v1",
        "source": "immutable short-story raw text",
        "stages": [
            {"name": "fact_extraction", "input": "raw_source", "output": "provider_fact_payload", "max_calls": 1, "retries": 0, "formal_implementation": "EvaluationUpstreamPhaseAAdapter.build_fact_request → canonicalize_fact_payload → core.fact_snapshot.build_fact_snapshot → validate_fact_records", "reusable": ["core.fact_snapshot.build_fact_snapshot", "core.fact_snapshot.validate_fact_records"]},
            {"name": "script_ir_structuring", "input": "verified_fact_snapshot + raw_source", "output": "provider_script_ir_payload", "max_calls": 1, "retries": 0, "formal_implementation": "EvaluationUpstreamPhaseAAdapter.build_script_ir_request → canonicalize_script_payload → core.script_ir.build_script_ir → validate_script_ir", "reusable": ["core.script_ir.build_script_ir", "core.script_ir.validate_script_ir"]},
        ],
        "predicted_provider_calls": 2,
        "absolute_max_provider_calls": 2,
        "retry_policy": {"transport": 0, "format": 0, "repair": 0, "fallback": 0, "critic": 0, "judge": 0},
        "provider": _t(config.get("provider")),
        "model": _t(config.get("model")),
        "endpoint_class": _t(config.get("endpoint_class")),
        "production_db_mutations": 0,
        "excluded_production_paths": ["core.ingest", "agents.reader.ReaderAgent", "api.fact_snapshot_api", "api.script_ir_api"],
        "evaluation_namespace": f"work/evaluation/director_v3/{SOURCE_PACKAGE_ID}/upstream_phase_a",
    }


def build_fact_request(*, raw_text: str, provider_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a neutral request; only source text and machine contract are exposed."""
    config = _d(provider_config)
    return {
        "task": "extract_source_grounded_facts",
        "source_text": str(raw_text),
        "contract": {
            "records_key": "facts",
            "required_fields": ["subject_type", "subject_id", "predicate", "value", "authority", "status", "evidence"],
            "allowed_authority": ["source_text", "model_observation"],
            "allowed_status": ["confirmed", "proposed", "conflict", "unknown"],
            "epistemic_rule": "a character claim is not objective truth; model_observation must remain proposed",
            "evidence_rule": "source_text confirmed facts require an exact bounded excerpt from source_text",
            "canonical_ids": "return semantic labels; program assigns FACT_NNNN",
        },
        "provider": _t(config.get("provider")),
        "model": _t(config.get("model")),
    }


def build_script_ir_request(*, raw_text: str, fact_snapshot: dict[str, Any], provider_config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = _d(provider_config)
    return {
        "task": "structure_fact_grounded_script_ir",
        "source_text": str(raw_text),
        "fact_snapshot": copy.deepcopy(fact_snapshot),
        "contract": {
            "output_key": "script_ir",
            "required_scene_fields": ["name", "location_name", "beats"],
            "no_directing_fields": sorted(DIRECTING_KEYS),
            "evidence_rule": "every confirmed source dialogue/event must cite an exact source excerpt",
            "temporal_rule": "reported past does not create a flashback unless source explicitly stages it",
            "canonical_ids": "program assigns deterministic scene and beat IDs",
        },
        "provider": _t(config.get("provider")),
        "model": _t(config.get("model")),
    }


def _evidence_matches(evidence: Any, raw_text: str) -> tuple[bool, list[dict[str, Any]]]:
    rows = _l(evidence)
    checked: list[dict[str, Any]] = []
    if not rows:
        return False, checked
    valid = True
    for item in rows:
        row = _d(item)
        excerpt = _t(row.get("excerpt") or row.get("text") or row.get("quote"))
        start = row.get("start")
        end = row.get("end")
        exact = bool(excerpt and excerpt in raw_text)
        span_ok = True
        if isinstance(start, int) and isinstance(end, int):
            span_ok = 0 <= start <= end <= len(raw_text) and raw_text[start:end] == excerpt
        if not exact or not span_ok:
            valid = False
        checked.append({"excerpt": excerpt, "start": start, "end": end, "verified": bool(exact and span_ok)})
    return valid, checked


def _fact_rows(payload: Any) -> list[dict[str, Any]]:
    source = _d(payload)
    rows = source.get("facts") if isinstance(source.get("facts"), list) else source.get("records")
    return [_d(item) for item in _l(rows)]


def canonicalize_fact_payload(payload: Any, *, raw_text: str, source_fingerprint: str, provenance: dict[str, Any]) -> dict[str, Any]:
    """Verify evidence and epistemic status before calling build_fact_snapshot."""
    payload_object, parse_errors = _payload_object(payload, label="evaluation_fact_payload", required_keys={"facts", "records"})
    errors: list[dict[str, Any]] = list(parse_errors)
    normalized: list[dict[str, Any]] = []
    evidence_verified = 0
    evidence_invalid = 0
    promotion_violations = 0
    for index, raw in enumerate(_fact_rows(payload_object), 1):
        row = {
            "subject_type": _t(raw.get("subject_type")),
            "subject_id": _t(raw.get("subject_id") or raw.get("subject_label")),
            "predicate": _t(raw.get("predicate")),
            "value": raw.get("value"),
            "scope": _t(raw.get("scope")) or "global",
            "authority": _t(raw.get("authority")).lower() or "model_observation",
            "status": _t(raw.get("status")).lower() or "proposed",
            "confidence": raw.get("confidence", 0.0),
            "evidence": _l(raw.get("evidence")),
            "conflict_group": raw.get("conflict_group"),
        }
        valid_evidence, checked = _evidence_matches(row["evidence"], raw_text)
        row["evidence"] = checked
        if valid_evidence:
            evidence_verified += 1
        elif row["authority"] == "source_text" and row["status"] == "confirmed":
            evidence_invalid += 1
            errors.append({"code": "SOURCE_FACT_EVIDENCE_INVALID", "index": index})
        if row["authority"] == "model_observation" and row["status"] == "confirmed":
            promotion_violations += 1
            errors.append({"code": "EPISTEMIC_PROMOTION_VIOLATION", "index": index})
        if row["authority"] == "source_text" and row["status"] == "confirmed" and not valid_evidence:
            row["status"] = "unknown"
        if row["authority"] == "model_observation":
            row["status"] = "proposed"
        normalized.append(row)
    # Program-owned deterministic ordering and IDs; provider IDs are ignored.
    normalized.sort(key=lambda row: (_t(row.get("subject_type")), _t(row.get("subject_id")), _t(row.get("predicate")), _canonical(row.get("value"))))
    for index, row in enumerate(normalized, 1):
        row["fact_id"] = f"FACT_{index:04d}"
    snapshot = build_fact_snapshot(normalized, book_id=evaluation_book_id(), episode=1, source_fingerprint=source_fingerprint)
    snapshot["provenance"] = copy.deepcopy(provenance)
    report = {
        "status": "PASS" if not errors and snapshot["validation"]["status"] == "qualified" else "FAIL",
        "errors": errors,
        "total_facts": len(normalized),
        "confirmed": sum(row["status"] == "confirmed" for row in normalized),
        "proposed": sum(row["status"] == "proposed" for row in normalized),
        "conflict": sum(row["status"] == "conflict" for row in normalized),
        "unknown": sum(row["status"] == "unknown" for row in normalized),
        "source_text_authority": sum(row["authority"] == "source_text" for row in normalized),
        "model_observation": sum(row["authority"] == "model_observation" for row in normalized),
        "evidence_verified": evidence_verified,
        "evidence_invalid": evidence_invalid,
        "claim_objective_promotion_violations": promotion_violations,
        "validation": snapshot["validation"],
        "source_fingerprint_exact": bool(snapshot.get("source_fingerprint") == source_fingerprint),
    }
    return {"snapshot": snapshot, "report": report}


def _contains_directing_key(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = _t(key).lower()
            if key_text in {item.lower() for item in DIRECTING_KEYS}:
                found.append(f"{path}.{key}" if path else str(key))
            found.extend(_contains_directing_key(item, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_contains_directing_key(item, f"{path}[{index}]"))
    return found


def _script_rows(payload: Any) -> dict[str, Any]:
    source = _d(payload)
    if isinstance(source.get("script_ir"), dict):
        return _d(source.get("script_ir"))
    return source


def _prop_ref(value: Any) -> str:
    if isinstance(value, dict):
        return _t(value.get("prop_id") or value.get("id") or value.get("name"))
    return _t(value)


def canonicalize_script_payload(payload: Any, *, raw_text: str, fact_snapshot: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    """Ground and deterministically build a qualified ScriptIR candidate."""
    payload_object, parse_errors = _payload_object(payload, label="evaluation_script_ir_payload", required_keys={"scenes", "script_ir"})
    source = _script_rows(payload_object)
    errors: list[dict[str, Any]] = list(parse_errors)
    directing_fields = _contains_directing_key(source)
    if directing_fields:
        errors.extend({"code": "SCRIPT_IR_DIRECTOR_LEAKAGE", "field": field} for field in directing_fields)
    scenes = _l(source.get("scenes"))
    invented_dialogues = 0
    invented_events = 0
    flashback_without_source = 0
    internal_thought_dialogues = 0
    canonical_scenes: list[dict[str, Any]] = []
    for scene_index, raw_scene in enumerate(scenes, 1):
        scene = _d(raw_scene)
        if scene.get("flashback") is True or _t(scene.get("scene_type")).lower() == "flashback":
            if not _evidence_matches(scene.get("evidence"), raw_text)[0]:
                flashback_without_source += 1
                errors.append({"code": "REPORTED_PAST_FLASHBACK_UNGROUNDED", "scene_index": scene_index})
        dialogues = []
        for dialogue in _l(scene.get("dialogues")):
            row = _d(dialogue)
            text = _t(row.get("text") or row.get("content") or row.get("line"))
            if _t(row.get("type")).lower() in {"internal_thought", "thought", "inner_monologue"}:
                internal_thought_dialogues += 1
                errors.append({"code": "INTERNAL_THOUGHT_AS_DIALOGUE", "scene_index": scene_index})
            if text and text not in raw_text:
                invented_dialogues += 1
                errors.append({"code": "INVENTED_DIALOGUE", "scene_index": scene_index})
            dialogues.append(row)
        for beat in _l(scene.get("beats")):
            row = _d(beat)
            event = _t(row.get("event") or row.get("description") or row.get("content"))
            evidence_ok = _evidence_matches(row.get("evidence"), raw_text)[0]
            if event and event not in raw_text and not evidence_ok:
                invented_events += 1
                errors.append({"code": "INVENTED_HARD_EVENT", "scene_index": scene_index})
        # Preserve source-oriented fields only; program later assigns IDs.
        canonical_scenes.append({
            "name": _t(scene.get("name") or scene.get("scene_name")),
            "location_id": _t(scene.get("location_id")),
            "location_name": _t(scene.get("location_name") or scene.get("location") or scene.get("name")),
            "time_of_day": _t(scene.get("time_of_day") or scene.get("time")),
            "weather": _t(scene.get("weather")),
            "participants": _l(scene.get("participants")),
            "beats": _l(scene.get("beats")),
            "actions": _l(scene.get("actions")),
            "dialogues": dialogues,
            "state_in": _d(scene.get("state_in")),
            "state_out": _d(scene.get("state_out")),
            "required_visual_proofs": _l(scene.get("required_visual_proofs")),
            "character_blocking": _l(scene.get("character_blocking")),
            "props": _l(scene.get("props")),
            "asset_mentions": _l(scene.get("asset_mentions")),
        })
    ir = build_script_ir({"title": _t(source.get("title")), "episode_objective": _t(source.get("episode_objective")), "scenes": canonical_scenes}, book_id=evaluation_book_id(), episode=1, fact_snapshot_id=f"EVAL:{SOURCE_PACKAGE_ID}:FACT_SNAPSHOT")
    ir["provenance"] = copy.deepcopy(provenance)
    validation = validate_script_ir(ir)
    report = {
        "status": "QUALIFIED" if not errors and validation["status"] == "qualified" and fact_snapshot.get("validation", {}).get("status") == "qualified" else "NEEDS_REVIEW",
        "errors": errors,
        "validation": validation,
        "scene_count": len(ir.get("scenes", [])),
        "beat_count": sum(len(_l(scene.get("beats"))) for scene in ir.get("scenes", [])),
        "character_count": len(_l(ir.get("characters"))),
        "location_count": len({(_t(scene.get("location_id")), _t(scene.get("location_name"))) for scene in ir.get("scenes", []) if _t(scene.get("location_name"))}),
        "prop_refs": sorted({_prop_ref(prop) for scene in ir.get("scenes", []) for prop in _l(scene.get("props")) if _prop_ref(prop)}),
        "dialogue_count": sum(len(_l(scene.get("dialogues"))) for scene in ir.get("scenes", [])),
        "invented_hard_events": invented_events,
        "invented_dialogues": invented_dialogues,
        "dangling_refs": [],
        "director_leakage": len(directing_fields),
        "reported_past_flashback_count": flashback_without_source,
        "internal_thought_dialogue_count": internal_thought_dialogues,
        "provenance_status": "PASS" if ir.get("provenance") == provenance else "FAIL",
    }
    return {"script_ir": ir, "report": report}


def phase_a_preflight(*, source: dict[str, Any], provider_config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = _d(provider_config)
    call_graph = build_call_graph(provider_config=config)
    errors = list(source.get("errors") or [])
    if not source.get("provenance", {}).get("functional_pipeline_evaluation_eligible"):
        errors.append({"code": "SOURCE_NOT_EVALUATION_ELIGIBLE"})
    return {
        "schema_version": "director_v3_evaluation_upstream_phase_a_preflight_v1",
        "status": "PASS" if not errors else "BLOCKED",
        "source_package_verification": source.get("status"),
        "provenance_verification": "PASS" if not errors else "FAIL",
        "call_graph": call_graph,
        "predicted_provider_calls": call_graph["predicted_provider_calls"],
        "provider_call_budget": call_graph["absolute_max_provider_calls"],
        "mutation_plan": {"production_db": 0, "book": 0, "scene": 0, "fact_snapshot": 0, "script_ir": 0, "human_fresh_pool": 0},
        "isolation_plan": {"namespace": f"work/evaluation/director_v3/{SOURCE_PACKAGE_ID}/upstream_phase_a", "production_db": "forbidden", "fresh_pool": "forbidden"},
        "output_schemas": ["fact_snapshot_v1", "script_ir_v1"],
        "validators": ["core.fact_snapshot.build_fact_snapshot", "core.fact_snapshot.validate_fact_records", "core.script_ir.build_script_ir", "core.script_ir.validate_script_ir"],
        "failure_routing": "FactSnapshot failure stops before ScriptIR; no retry or repair provider",
        "errors": errors,
    }


def run_with_provider_calls(*, source: dict[str, Any], provider_config: dict[str, Any], call_provider: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    """Execute at most one fact and one ScriptIR call when the caller has passed all gates.

    The callback is injected by a runner, which makes this function easy to
    test without importing a provider.  It is deliberately not a retry loop.
    """
    preflight = phase_a_preflight(source=source, provider_config=provider_config)
    if preflight["status"] != "PASS":
        return {"status": "DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_BLOCKED", "provider_calls": 0, "preflight": preflight}
    raw_hash = source["raw_hash"]
    provenance = source["provenance"]
    fact_response = call_provider(build_fact_request(raw_text=source["raw_text"], provider_config=provider_config))
    fact = canonicalize_fact_payload(fact_response, raw_text=source["raw_text"], source_fingerprint=raw_hash, provenance=provenance)
    if fact["report"]["status"] != "PASS":
        return {"status": "DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_FAILED", "provider_calls": 1, "fact": fact, "preflight": preflight}
    script_response = call_provider(build_script_ir_request(raw_text=source["raw_text"], fact_snapshot=fact["snapshot"], provider_config=provider_config))
    script = canonicalize_script_payload(script_response, raw_text=source["raw_text"], fact_snapshot=fact["snapshot"], provenance=provenance)
    status = "DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_CLOSED" if script["report"]["status"] == "QUALIFIED" else "DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_FAILED"
    return {"status": status, "provider_calls": 2, "fact": fact, "script": script, "preflight": preflight}
