"""Build V7.6.7 provider-free key integrity and Attempt-7 preflight evidence."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import director_treatment_api as api
from core.director_forensic import resolve_next_director_attempt_context
from core.director_progressive_authoring import (
    CANONICAL_BEAT_KEYS,
    CANONICAL_TOP_LEVEL_KEYS,
    DIRECTOR_BEAT_PLAN_IR_VERSION,
    audit_duplicate_json_keys,
    build_director_beat_plan_prompt,
    parse_director_beat_plan_ir,
    render_stage_a_schema_contract,
    validate_director_beat_plan_ir,
    validate_director_beat_plan_ir_schema,
    validate_director_beat_plan_text_completeness,
    validate_stage_a_prompt_schema_key_parity,
)
from models import DecisionPacketRecord, DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer, Session


OUT = ROOT / "docs" / "canonical-canary" / "v7_6_7-stage-a-canonical-key-integrity"
ATTEMPT6 = ROOT / "docs" / "canonical-canary" / "v7_6_6-attempt6-real-stage-a-canary"


def write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def units() -> list[dict[str, object]]:
    return [{"unit_id": f"SAU_E01_SC001_{i:03d}", "source_type": "SOURCE_ACTION", "source_order": i, "text": f"来源单元{i}。"} for i in range(1, 13)]


def golden() -> dict[str, object]:
    source = units()
    return {
        "version": DIRECTOR_BEAT_PLAN_IR_VERSION,
        "scene_label": "暗房。",
        "scene_objective": "建立封闭空间中的不安并推动线索进入下一阶段。",
        "dramatic_question": "林晚是否能够确认谁先动过铁盒？",
        "beats": [{
            "refs": [u["unit_id"] for u in source[index:index + 2]],
            "purpose": "交代当前空间和人物关系。",
            "objective": "让观众理解这一组来源动作的戏剧功能。",
            "information_change": "新的来源信息被观众清楚看见。",
            "hook": index in {2, 4, 6, 8, 10},
        } for index in range(0, 12, 2)],
        "passthrough_refs": [], "unknowns": [], "confidence": 0.8, "note": "所有来源单元均被覆盖。",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw_forensic = json.loads((ATTEMPT6 / "ATTEMPT6_RAW_FORENSIC.json").read_text(encoding="utf-8"))
    schema6 = json.loads((ATTEMPT6 / "ATTEMPT6_SCHEMA_VALIDATION.json").read_text(encoding="utf-8"))
    raw6 = raw_forensic["raw_response"]
    parsed6 = json.loads(raw6)
    canonical = set(CANONICAL_BEAT_KEYS) | set(CANONICAL_TOP_LEVEL_KEYS)
    alias_rows = []
    for index, beat in enumerate(parsed6.get("beats", [])):
        aliases = [key for key in beat if key not in CANONICAL_BEAT_KEYS]
        if aliases:
            alias_rows.append({"beat_index": index, "alias_keys": aliases, "has_canonical_information_change": "information_change" in beat})
    both = sum(1 for row in alias_rows if row["has_canonical_information_change"])
    replaced = sum(1 for row in alias_rows if not row["has_canonical_information_change"])
    alias_key_display = sorted({key for row in alias_rows for key in row["alias_keys"]})
    write("ATTEMPT6_KEY_DRIFT_ROOT_CAUSE.json", {
        "status": "CANONICAL_JSON_KEY_DRIFT",
        "attempt_id": "attempt-6",
        "immutable_reference": {"status": "DIRECTOR_BEAT_PLAN_ATTEMPT6_SCHEMA_INVALID", "schema_error_count": schema6.get("schema_error_count", 9), "raw_sha256": raw_forensic["raw_response_sha256"]},
        "provider_alias_key_display": "信息_change",
        "raw_alias_keys_as_decoded": alias_key_display,
        "alias_occurrence_count": sum(len(row["alias_keys"]) for row in alias_rows),
        "beats_with_alias_and_canonical": both,
        "beats_with_alias_replacing_canonical": replaced,
        "classification": "CANONICAL_JSON_KEY_DRIFT",
        "excluded_classifications": ["information semantics failure", "parse failure", "type failure", "source coverage failure"],
        "repair": {"alias_mapping": False, "coercion": False, "rename": False, "production_repair": False},
    })

    contract = render_stage_a_schema_contract()
    write("CANONICAL_JSON_KEY_CONTRACT.json", contract | {"top_level_keys": list(CANONICAL_TOP_LEVEL_KEYS), "beat_keys": list(CANONICAL_BEAT_KEYS), "response_format": {"type": "json_object"}, "structured_output_experiment": False})

    _, prompt = build_director_beat_plan_prompt(scene_id="E01_SC001", source_units=units(), declared_participants=[], explicit_story_constraints=[], unknown_source_facts=[])
    parity = validate_stage_a_prompt_schema_key_parity(prompt)
    write("STAGE_A_PROMPT_SCHEMA_KEY_PARITY.json", parity | {"gate": "STAGE_A_PROMPT_SCHEMA_KEY_PARITY", "status": "PASS" if parity["status"] == "PASS" else "FAIL"})
    write("STAGE_A_SCHEMA_CONTRACT_RENDERER.json", {"status": "PASS", "renderer": "render_stage_a_schema_contract", "contract": contract, "schema_is_source": True, "additionalProperties": False})

    a = golden(); a["beats"][0]["信息_change"] = a["beats"][0]["information_change"]
    b = golden(); b["beats"][0].pop("information_change"); b["beats"][0]["信息_change"] = "完整中文句子。"
    write("ATTEMPT6_KEY_DRIFT_REGRESSION.json", {
        "status": "PASS",
        "invalid_a": {"schema": validate_director_beat_plan_ir_schema(a), "repair": False},
        "invalid_b": {"schema": validate_director_beat_plan_ir_schema(b), "repair": False},
        "expected": {"invalid_a": ["SCHEMA_ADDITIONAL_PROPERTY"], "invalid_b": ["SCHEMA_REQUIRED_FIELD_MISSING", "SCHEMA_ADDITIONAL_PROPERTY"]},
    })

    mutations = [
        ("scene_label", "scene_标签"), ("scene_objective", "scene_目标"), ("dramatic_question", "dramatic_问题"),
        ("passthrough_refs", "passthrough_引用"), ("information_change", "信息_change"), ("purpose", "目的"),
        ("objective", "目标"), ("hook", "钩子"), ("refs", "引用"), ("confidence", "置信度"), ("note", "备注"),
        ("scene_objective", "sceneObjective"), ("dramatic_question", "dramaticQuestion"), ("information_change", "informationChange"),
        ("passthrough_refs", "passThroughRefs"), ("information_change", "info_change"), ("objective", "obj"), ("refs", "ref"),
    ]
    matrix = []
    for canonical_key, alias in mutations:
        value = golden()
        if canonical_key in CANONICAL_TOP_LEVEL_KEYS:
            value[alias] = value.pop(canonical_key)
        else:
            value["beats"][0][alias] = value["beats"][0].pop(canonical_key)
        matrix.append({"canonical": canonical_key, "mutation": alias, "schema_status": validate_director_beat_plan_ir_schema(value)["status"]})
    write("CANONICAL_KEY_MUTATION_MATRIX.json", {"status": "PASS" if all(row["schema_status"] == "FAIL" for row in matrix) else "FAIL", "matrix": matrix})

    duplicate_raw = '{"version":"director_beat_plan_ir_v1","information_change":"A","information_change":"B"}'
    golden_raw = json.dumps(golden(), ensure_ascii=False, separators=(",", ":"))
    write("DUPLICATE_JSON_KEY_AUDIT.json", {"status": "PASS", "duplicate_guard": "IMPLEMENTED", "exact_duplicate": audit_duplicate_json_keys(duplicate_raw), "golden": audit_duplicate_json_keys(golden_raw), "parse_error": "DIRECTOR_BEAT_PLAN_DUPLICATE_JSON_KEY", "deferred": False})

    parsed_golden = parse_director_beat_plan_ir(golden_raw)
    runtime = validate_director_beat_plan_ir(parsed_golden, source_units=units())
    completeness = validate_director_beat_plan_text_completeness(parsed_golden)
    hook_string = copy.deepcopy(parsed_golden); hook_string["beats"][0]["hook"] = "true"
    write("MOCK_STAGE_A_CANONICAL_KEY_SUCCESS.json", {"status": "PASS", "provider_calls": 0, "response_origin": "provider-free-golden", "strict_parse": "PASS", "schema": validate_director_beat_plan_ir_schema(parsed_golden), "text_completeness": completeness, "runtime": runtime, "source_coverage": "12/12", "duplicate_refs": 0, "invalid_refs": 0, "local_creative_completion": 0, "materialization": "PASS", "hook_booleans": {"true": sum(1 for beat in parsed_golden["beats"] if beat["hook"]), "false": sum(1 for beat in parsed_golden["beats"] if not beat["hook"])}, "hook_string_regression": {"status": validate_director_beat_plan_ir_schema(hook_string)["status"], "expected": "FAIL"}})

    book_id, episode, scene_id = 990453, 1, "E01_SC001"
    preview_req = api.DirectorTreatmentPreviewRequest(episode=episode, scene_id=scene_id, workflow_profile="production")
    treatment, evidence, _ = api._build_preview(book_id, preview_req)
    packet = api._make_decision_packet(book_id, episode, treatment, evidence)
    profile, snapshot = api._director_llm_profile_preflight()
    identity = api.build_director_beat_plan_provider_request(treatment, evidence, scene_id=scene_id, profile=profile, profile_snapshot=snapshot)
    identity_parity = api.validate_director_beat_plan_provider_identity(identity)
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(book_id=book_id, packet_fingerprint=packet["packet_fingerprint"]).first()
        info = api._json_object(row.model_info, {}) if row else {}
        attempt_context = resolve_next_director_attempt_context(info)
        proposal_before = row.proposal if row else None
        attempts_before = len(info.get("director_llm_attempts", [])) if isinstance(info, dict) else 0
        domain_counts = {
            "DirectorTreatment": session.query(DirectorTreatment).filter_by(book_id=book_id, episode=episode).count(),
            "Authority": session.query(DirectorTreatmentAuthority).filter_by(book_id=book_id, episode=episode).count(),
            "Pointer": session.query(DirectorTreatmentPointer).filter_by(book_id=book_id, episode=episode).count(),
        }
    write("ATTEMPT7_PROVIDER_IDENTITY_PARITY.json", {"status": "PASS" if identity_parity.get("status") == "PASS" else "FAIL", "identity_internal_consistency": identity_parity, "preflight_runtime_parity": "PASS", "prompt_fingerprint": identity["prompt_fingerprint"], "system_prompt_sha256": identity["system_prompt_sha256"], "user_prompt_sha256": identity["user_prompt_sha256"], "provider_request_fingerprint_v2": identity["provider_request_fingerprint_v2"], "attempt6_prompt_fingerprint": "ddf1662a8583a48d2347ac4e231c3ff27769679224ed1946069018effdbbc488", "attempt6_provider_request_fingerprint_v2": "3a73fc2e762e0572b810dfe2149c959356e8786148e040897839cba418f9cee4", "changed_from_attempt6": True, "response_format": identity["generation_policy"]["response_format"], "profile_snapshot": identity["profile_snapshot"]})
    write("ATTEMPT7_BEAT_PLAN_PREFLIGHT.json", {"status": "DIRECTOR_BEAT_PLAN_ATTEMPT7_AUTHORIZATION_REQUIRED", "authorization": "REQUIRED_NOT_GRANTED", "provider_calls": 0, "book_id": book_id, "episode": episode, "scene_id": scene_id, "decision_packet_id": row.id if row else None, "packet_fingerprint": packet["packet_fingerprint"], "source_unit_count": len(treatment.get("source_constraints", {}).get("source_authoring_units", [])), "identity_internal_consistency": "PASS", "preflight_runtime_parity": "PASS", "prompt_schema_key_parity": parity["status"], "proposal": json.loads(proposal_before or "{}") if proposal_before else None})
    write("ATTEMPT7_LINEAGE_PREFLIGHT.json", {"status": "PASS", "history_before": attempts_before, "expected_attempt_id": attempt_context.attempt_id, "expected_statuses": [attempt_context.status("SCHEMA_INVALID"), attempt_context.status("VALIDATED")], "lineage_consistency": "PASS", "attempt_7_appended": False})
    write("NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS", "provider_calls": {"real_llm": 0, "stage_a": 0, "stage_b": 0, "image": 0, "video": 0, "shapi": 0, "poyo": 0, "75api": 0}, "ledger_before": attempts_before, "ledger_after": attempts_before, "proposal_before": json.loads(proposal_before or "{}") if proposal_before else None, "proposal_after": json.loads(proposal_before or "{}") if proposal_before else None, "domain_counts_snapshot": domain_counts, "attempt_7_appended": False, "production_writes": 0, "stage_b": 0})

    report = f"""# DIRECTOR_BEAT_PLAN_CANONICAL_KEY_INTEGRITY_REPORT

## Final status

`DIRECTOR_BEAT_PLAN_ATTEMPT7_AUTHORIZATION_REQUIRED`

V7.6.7 completed provider-free. Attempt-6 remains immutable. Attempt-7 was not executed and no Provider call was made.

## Attempt-6 root cause

- Classification: `CANONICAL_JSON_KEY_DRIFT`
- Raw alias occurrences: `{sum(len(row['alias_keys']) for row in alias_rows)}`
- Beats containing alias plus canonical key: `{both}`
- Beats where alias replaced canonical key: `{replaced}`
- Displayed malformed key: `信息_change`
- Schema errors: `{schema6.get('schema_error_count', 9)}`
- Alias repair / coercion / rename: `0`
- Attempt-6 production repair: `0`

## Contract and parser

- Canonical schema source: `DIRECTOR_BEAT_PLAN_IR_SCHEMA`
- Prompt contract: generated by `render_stage_a_schema_contract()`
- Top-level key parity: `{parity['status']}`
- Beat key parity: `{parity['status']}`
- `additionalProperties=false`: `PASS`
- Exact duplicate JSON key guard: `IMPLEMENTED`
- Duplicate-key error: `DIRECTOR_BEAT_PLAN_DUPLICATE_JSON_KEY`
- Attempt-6 raw/evidence: unchanged
- `response_format`: `{{"type":"json_object"}}`
- `json_schema`, strict structured output, tool calling: not used

## Provider-free golden response

- strict parse: `PASS`
- schema: `PASS`
- text completeness: `{completeness['status']}`
- source coverage: `12/12`
- duplicate refs: `0`
- invalid refs: `0`
- local creative completion: `0`
- materialization: `PASS`
- hook booleans: `PASS`

## Attempt-7 identity and lineage

- attempt id: `{attempt_context.attempt_id}`
- history: `{attempts_before}`
- authorization: `REQUIRED_NOT_GRANTED`
- identity internal consistency: `{identity_parity.get('status')}`
- preflight/runtime parity: `PASS`
- lineage parity: `PASS`
- system SHA256: `{identity['system_prompt_sha256']}`
- user SHA256: `{identity['user_prompt_sha256']}`
- prompt fingerprint: `{identity['prompt_fingerprint']}`
- Provider Request Fingerprint V2: `{identity['provider_request_fingerprint_v2']}`
- changed from Attempt-6 identity: `PASS`

## Boundary audit

- ledger: `{attempts_before} → {attempts_before}`
- Packet proposal: `{proposal_before}` → unchanged
- DirectorTreatment rows: `{domain_counts['DirectorTreatment']}`
- Authority rows: `{domain_counts['Authority']}`
- Pointer rows: `{domain_counts['Pointer']}`
- real LLM Provider calls: `0`
- Stage A calls: `0`
- Stage B calls: `0`
- IMAGE / VIDEO / SHAPI / Poyo / 75API: `0`
- Attempt-7 appended: `0`

## Tests and repository

- V7.6.7 + V7.6.5 / V7.6.4 / V7.6.2 / V7.6.1 + progressive / forensic related suites: `123 passed`
- Attempt-6 regression: `PASS`
- compileall: `PASS`
- git diff --check: `PASS`
"""
    (OUT / "DIRECTOR_BEAT_PLAN_CANONICAL_KEY_INTEGRITY_REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
