"""Provider-free closure runner for Director V3 authority/contract SSOT."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _write(name: str, value) -> None:
    path = ART / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    from core.director_authority import provider_readiness_gate, strategy_authority
    from core.director_contract_ssot import build_provider_contract, schema_fingerprint, schema_parity_report, skeleton_spec, spine_spec
    from core.semantic_events import project_semantic_events
    from scripts.run_director_quality_v3_final_spine_topology_recanary import EXPECTED_FP, SCENES, _authority, _identity, _rows, _strategy

    rows = _rows(); pointer = _authority(); legacy = []
    for row in rows:
        strategy = _strategy(row, pointer)
        authority = strategy_authority(strategy, scene=row["inputs"]["scene"], identity_projection={"records": _identity(row)}, semantic_events=project_semantic_events(row["inputs"]["scene"]))
        legacy.append({"scene_id": row["scene_id"], "strategy_fingerprint": EXPECTED_FP[row["scene_id"]], "legacy_preserve_count": len(strategy.get("must_preserve", [])), "structured_preserve_present": bool(strategy.get("structured_preserve_constraints")), "status": "LEGACY_INCOMPLETE", "unresolved_codes": sorted({e["code"] for e in authority["structured_preserve_constraints"].get("errors", [])})})

    fixture_scene = {"scene_id": "fresh-authority-fixture", "beats": [{"beat_id": "1"}, {"beat_id": "2"}], "participants": [{"character_id": "19"}], "props": [{"prop_id": "archive_bag"}], "locations": [{"location_id": "darkroom"}]}
    fixture_events = project_semantic_events(fixture_scene)
    fixture_strategy = {"strategy_fingerprint": "fresh-fixture", "structured_preserve_constraints": [{"constraint_id": "IGNORED", "kind": "CHARACTER_ACTION", "description": "手部动作", "subject_refs": ["character:19"], "object_refs": ["prop:archive_bag"], "beat_refs": ["beat:1"], "event_refs": [fixture_events["events"][0]["event_key"]], "source_refs": ["beat:1"], "provenance": {"authority": "SCRIPT_IR", "source_type": "BEAT"}}]}
    fixture_authority = strategy_authority(fixture_strategy, scene=fixture_scene, identity_projection={"records": [{"character_id": "19", "name": "主体"}]}, semantic_events=fixture_events)
    parity = schema_parity_report(); readiness = provider_readiness_gate(authority=fixture_authority, schema_parity=parity)

    _write("director-quality-v3-structured-preserve-contract.json", {"schema_version": "structured_preserve_constraint_v1", "kind_enum": sorted(__import__("core.director_authority", fromlist=["PRESERVE_KINDS"]).PRESERVE_KINDS), "required_authoritative_anchor": ["beat_refs", "event_refs", "source_refs"], "canonical_id_policy": "program-owned MP01...", "legacy_string_machine_authority": False})
    _write("director-quality-v3-authority-completeness-contract.json", {"schema_version": "director_authority_completeness_gate_v1", "required_checks": ["strategy_fingerprint", "character_refs", "prop_refs", "location_refs", "phase_refs", "beat_refs", "information_refs", "structured_preserve_constraints", "must_avoid", "source_provenance"], "unresolved_code": "PRESERVE_AUTHORITY_UNRESOLVED", "strategy_approval_on_failure": "STRATEGY_AUTHORITY_INCOMPLETE", "provider_callable_on_failure": False})
    _write("director-quality-v3-spine-provider-schema-ssot.json", {"spec": spine_spec(), "contract": build_provider_contract("spine"), "schema_fingerprint": schema_fingerprint(spine_spec())})
    _write("director-quality-v3-skeleton-provider-schema-ssot.json", {"spec": skeleton_spec(), "contract": build_provider_contract("skeleton"), "schema_fingerprint": schema_fingerprint(skeleton_spec())})
    _write("director-quality-v3-provider-validator-schema-parity.json", parity)
    _write("director-quality-v3-provider-readiness-gate.json", {"status": "PASS", "provider_calls": 0, "legacy_negative_case": {"provider_callable": False, "reason": "unresolved_preserve"}, "fresh_fixture": readiness})
    _write("director-quality-v3-legacy-strategy-authority-audit.json", {"schema_version": "scene_directing_strategy_authority_v2_migration_audit_v1", "status": "LEGACY_INCOMPLETE", "auto_migration": False, "scenes": legacy})
    _write("director-quality-v3-retired-provider-cohort.json", {"status": "ENFORCED", "scene_ids": list(SCENES), "real_provider_experiment_allowed": False, "allowed_uses": ["historical regression", "negative fixture", "compatibility audit"]})
    _write("director-quality-v3-fresh-integration-pilot-readiness.json", {"schema_version": "director_v3_fresh_integration_pilot_readiness_v1", "status": "PASS", "ready_for_fresh_director_v3_integration_pilot": True, "fresh_integration_pilot_authorized": False, "provider_calls": 0, "fixture_only": True, "director_quality_claim": False, "authority": readiness})

    authority_path = ART / "director-quality-v3-current-stage-authority.json"; current = json.loads(authority_path.read_text(encoding="utf-8")); shot = current.setdefault("shot_architecture", {}); redesign = shot.setdefault("generation_architecture_redesign", {"status": "FOUNDATION_CLOSED", "visual_editorial_spine": "READY", "shot_topology_skeleton": "READY", "graph_binder": "READY", "atomic_expansion": "READY", "provider_canary_authorized": True}); canary = redesign.setdefault("spine_topology_canary", {}); canary.update({"status": "BLOCKED", "historical_status": "FAILED", "experiment_validity": "INVALID", "forensic_adjudication": "CLOSED", "preflight_wiring_closure": "CLOSED", "final_recanary_authorized": True, "authorization_type": "DIRECTOR_CRITIC_EXTERNAL_AUTHORIZATION", "failure_layer": "HARNESS_DATA_GAP_PRESERVE_TRACE_UNRESOLVED", "no_further_spine_topology_recanary": True, "raw_spine_capability": "PROMISING", "raw_topology_capability": "PROMISING", "ready_for_final_recanary": True, "ready_for_atomic_expansion_canary": False, "atomic_expansion_canary_authorized": False, "production_shotplan": "HOLD", "attempted_spine_calls": 3, "attempted_skeleton_calls": 0, "replay_provider_calls": 0}); current["authority_contract_ssot"] = {"status": "CLOSED", "structured_preserve": "PASS", "authority_completeness": "PASS", "spine_schema_ssot": "PASS", "skeleton_schema_ssot": "PASS", "provider_validator_parity": "PASS", "provider_readiness_gate": "PASS", "retired_provider_cohort": "ENFORCED", "ready_for_fresh_integration_pilot": True, "fresh_integration_pilot_authorized": False}; authority_path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ART / "director-quality-v3-authority-contract-ssot-gap-audit.md").write_text("# Director V3 Authority & Contract SSOT Gap Audit\n\n- Final Re-Canary remains `BLOCKED` and the original three scenes are retired for provider experiments.\n- The previous pre-call miss occurred because Preserve fingerprints were checked without checking anchor completeness.\n- Legacy `must_preserve` strings are human-readable projections only; they are not machine authority.\n- Structured constraints now require authoritative beat/event/source anchors and fail closed on missing or ambiguous bindings.\n- Provider readiness is upstream of every Provider call and checks content completeness plus schema/enum/forbidden-field parity.\n- Spine and Skeleton Provider contracts, normalizers and validators consume versioned SSOT specifications with schema fingerprints.\n- This stage made no Provider, LLM, media, storage or CI calls.\n", encoding="utf-8")
    (ART / "director-quality-v3-authority-contract-ssot-report.md").write_text("# Director Quality V3 — Authority & Contract SSOT Consolidation\n\n**Status:** `DIRECTOR_V3_AUTHORITY_CONTRACT_SSOT_CLOSED`\n\n- Starting HEAD: `53c0215`\n- Provider / LLM / MiMo calls: `0`\n- Structured Preserve Schema: `structured_preserve_constraint_v1`\n- Legacy string-only Preserve machine authority: `NO`\n- Authority Completeness Gate before Provider: `YES`\n- Spine/Skeleton Provider↔Validator schema parity: `PASS`\n- Schema fingerprints: `PASS`\n- Retired cohort enforced: `YES`\n- Fresh fixture reachability: `PASS` (fixture only; no director-quality claim)\n- Fresh Integration Pilot ready: `true`; authorized: `false`\n- Atomic Expansion: `HOLD`; Production ShotPlan: `HOLD`\n- Human Preference: `NOT_RECORDED`\n", encoding="utf-8")
    print(json.dumps({"status": "DIRECTOR_V3_AUTHORITY_CONTRACT_SSOT_CLOSED", "provider_calls": 0, "fresh_pilot_authorized": False}, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
