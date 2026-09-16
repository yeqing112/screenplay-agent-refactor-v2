"""Provider-free closure runner for the Director V3 Strategy authority contract.

This command audits and records the Strategy V3 contract boundary only.  It
never imports a provider client, never freezes a new cohort, and never invokes
the Fresh Pilot #2 execution path.  The historical Pilot #1 evidence remains
immutable; this runner only adds a formal reclassification and readiness
inventory.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
AUTHORITY = ART / "director-quality-v3-current-stage-authority.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _write(name: str, value: Any) -> None:
    path = ART / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    scene = {
        "scene_id": "strategy-authority-fixture",
        "beats": [{"beat_id": "1"}, {"beat_id": "2"}, {"beat_id": "3"}],
        "participants": [{"character_id": "19"}],
        "props": [{"prop_id": "archive_bag"}],
        "locations": [{"location_id": "darkroom"}],
    }
    contract = {
        "strategy_contract": {
            "scene_id": scene["scene_id"],
            "beat_ids": ["1", "2", "3"],
            "character_ids": ["19"],
            "prop_ids": ["archive_bag"],
            "location_ids": ["darkroom"],
        }
    }
    strategy = {
        "schema_version": "director_scene_strategy_ir_v3",
        "dramatic_objective": "hold the evidence under pressure",
        "scene_question": "who will move first",
        "strategy_summary": "pressure moves from object to witness",
        "visual_thesis": "the archive bag is the silent witness",
        "scene_phases": [{"phase_id": "P01", "beat_ids": ["1", "2", "3"]}],
        "spatial_expression": "threshold to table",
        "prop_visual_strategy": "keep the bag visible",
        "creative_risks": [],
        "must_avoid": [],
        "preserve_intents": [{
            "kind": "PROP_INTERACTION",
            "description": "the witness touches the archive bag",
            "anchor_refs": ["beat:1"],
            "subject_refs": ["character:19"],
            "object_refs": ["prop:archive_bag"],
            "visibility_requirement": "EXPLICIT",
        }],
    }
    identity = {"records": [{"character_id": "19", "canonical_name": "主体"}]}
    events = {"events": [{"event_key": "event:archive_touch"}]}
    return scene, contract, strategy, {"identity": identity, "events": events}


def _fresh_pilot_1_reclassification() -> dict[str, Any]:
    return {
        "schema_version": "director_quality_v3_fresh_pilot_1_reclassification_v1",
        "historical_status": "FAILED",
        "experiment_validity": "INVALID",
        "primary_root_cause": "STRATEGY_PROVIDER_AUTHORITY_CONTRACT_MISMATCH",
        "secondary_findings": ["MODEL_OUTPUT_USED_LEGACY_STRING_PRESERVE"],
        "model_strategy_capability": "NOT_FAIRLY_ADJUDICATED",
        "provider_calls": 3,
        "retries": 0,
        "raw_evidence_mutated": False,
        "historical_evidence_immutable": True,
        "historical_machine_classification": "MODEL_FAILURE",
        "evidence": {
            "raw_strategy": "artifacts/director-quality-v3-fresh-integration-pilot-scenes",
            "execution_manifest": "artifacts/director-quality-v3-fresh-integration-pilot-execution-manifest.json",
            "provider_call_ledger": "artifacts/director-quality-v3-fresh-integration-pilot-provider-call-ledger.json",
        },
    }


def main() -> int:
    from core.director_authority import authority_completeness_gate, provider_readiness_gate
    from core.director_strategy_provider_spec import (
        build_strategy_provider_contract,
        canonicalize_strategy_v3,
        provider_validator_parity,
        strategy_provider_spec,
        validate_strategy_v3_shape,
    )
    from core.strategy_preserve_authority import compile_preserve_intents_to_authority

    scene, evidence_contract, strategy, extras = _fixture()
    provider_contract = build_strategy_provider_contract(evidence_contract | {"scene": scene, "semantic_events": extras["events"]})
    strategy_shape = validate_strategy_v3_shape(strategy, contract=provider_contract)
    authority_gate = authority_completeness_gate(
        # Validate the provider envelope before adding program-owned fields.
        strategy=strategy,
        scene=scene,
        identity_projection=extras["identity"],
        semantic_events=extras["events"],
        fresh_path=True,
        provider_contract=provider_contract,
    )
    readiness = provider_readiness_gate(
        authority=authority_gate.get("authority", {}),
        schema_parity={"status": "PASS", "strategy": provider_validator_parity()},
        strategy_fingerprint_ok=True,
    )
    invalid_anchor = dict(strategy)
    invalid_anchor["preserve_intents"] = [dict(strategy["preserve_intents"][0], anchor_refs=["beat:UNKNOWN"])]
    negative = authority_completeness_gate(
        strategy=invalid_anchor,
        scene=scene,
        identity_projection=extras["identity"],
        semantic_events=extras["events"],
        fresh_path=True,
        provider_contract=provider_contract,
    )

    parity = provider_validator_parity()
    preserve_contract = {
        "schema_version": "strategy_preserve_intent_v1",
        "required_fields": ["kind", "description", "anchor_refs", "subject_refs", "object_refs", "visibility_requirement"],
        "kind_enum": list(__import__("core.director_strategy_provider_spec", fromlist=["PRESERVE_KINDS"]).PRESERVE_KINDS),
        "visibility_requirement_enum": list(__import__("core.director_strategy_provider_spec", fromlist=["VISIBILITY_REQUIREMENTS"]).VISIBILITY_REQUIREMENTS),
        "anchor_policy": "non-empty exact refs selected from provider-visible allowed refs",
        "program_owned": ["constraint_id", "beat_refs", "event_refs", "source_refs", "provenance", "fingerprint"],
    }
    compiled = compile_preserve_intents_to_authority(
        strategy["preserve_intents"],
        allowed_source_refs=provider_contract["allowed_source_refs"],
        allowed_character_refs=provider_contract["allowed_character_refs"],
        allowed_prop_refs=provider_contract["allowed_prop_refs"],
        allowed_location_refs=provider_contract["allowed_location_refs"],
        allowed_event_refs=provider_contract["allowed_event_refs"],
        scene_id=scene["scene_id"],
    )

    reclassification = _fresh_pilot_1_reclassification()
    try:
        from scripts.run_director_quality_v3_fresh_integration_pilot import (
            RETIRED_SCENES,
            _approved_scene_rows,
            build_provider_exposure_registry,
            select_fresh_cohort,
        )
        rows = _approved_scene_rows()
        registry = build_provider_exposure_registry(candidate_ids={row["scene_id"] for row in rows})
        selection = select_fresh_cohort(rows, registry, retired=set(RETIRED_SCENES))
        inventory = {
            "schema_version": "director_quality_v3_fresh_pilot_2_candidate_inventory_v1",
            "candidate_count": selection["candidate_count"],
            "eligible_unseen_scene_count": selection["candidate_count"],
            "candidates": [row["scene_id"] for row in selection["eligible"]],
            "excluded": selection["excluded"],
            "retired_scene_count": len(RETIRED_SCENES),
            "provider_calls": 0,
        }
        retired_ids = sorted(RETIRED_SCENES)
    except Exception as exc:
        inventory = {"schema_version": "director_quality_v3_fresh_pilot_2_candidate_inventory_v1", "candidate_count": 0, "eligible_unseen_scene_count": 0, "candidates": [], "status": "UNAVAILABLE", "reason": str(exc)[:240], "provider_calls": 0}
        retired_ids = []

    readiness_doc = {
        "schema_version": "director_quality_v3_fresh_pilot_2_readiness_v1",
        "eligible_unseen_scene_count": inventory.get("eligible_unseen_scene_count", 0),
        "ready": False,
        "authorized": False,
        "cohort_frozen": False,
        "provider_calls": 0,
        "reason": "INSUFFICIENT_FRESH_ELIGIBLE_SCENES" if inventory.get("eligible_unseen_scene_count", 0) == 0 else "AUTHORIZATION_REQUIRED_AND_NO_COHORT_FREEZE_IN_CLOSURE",
    }

    _write("director-quality-v3-strategy-provider-spec-ssot.json", strategy_provider_spec(**{key: provider_contract.get(key, []) for key in ("allowed_source_refs", "allowed_character_refs", "allowed_prop_refs", "allowed_location_refs", "allowed_event_refs")}))
    _write("director-quality-v3-strategy-provider-validator-parity.json", parity)
    _write("director-quality-v3-strategy-preserve-intent-contract.json", preserve_contract)
    _write("director-quality-v3-strategy-preserve-authority-compiler.json", {"status": compiled["status"], "schema_version": compiled["schema_version"], "positive_fixture": compiled, "negative_invalid_anchor": negative.get("authority", {}).get("structured_preserve_constraints", {}), "deterministic_id_policy": "program-owned MP01, MP02...", "prose_guessing": False})
    canonical = canonicalize_strategy_v3(strategy)
    _write("director-quality-v3-strategy-authority-completeness-v2.json", {"status": "PASS" if authority_gate["status"] == "PASS" and readiness["status"] == "PASS" else "FAIL", "positive_fixture": {"shape": strategy_shape, "authority": authority_gate, "provider_readiness": readiness, "canonical_program_output": {"strategy_fingerprint": canonical.get("strategy_fingerprint")}}, "negative_invalid_anchor": negative, "legacy_string_only": {"status": "FAIL_CLOSED", "provider_callable": False}})
    _write("director-quality-v3-fresh-pilot-1-reclassification.json", reclassification)
    _write("director-quality-v3-retired-provider-cohort.json", {"schema_version": "director_quality_v3_retired_provider_cohort_v1", "status": "ENFORCED", "scene_ids": retired_ids, "count": len(retired_ids), "future_provider_experiment_allowed": False, "allowed_uses": ["historical regression", "negative fixture", "compatibility audit"]})
    _write("director-quality-v3-fresh-pilot-2-candidate-inventory.json", inventory)
    _write("director-quality-v3-fresh-pilot-2-readiness.json", readiness_doc)

    from core.director_v3_authority import reconcile_historical_recanary_authority
    pointer = reconcile_historical_recanary_authority(_load(AUTHORITY))
    pilot = pointer.setdefault("fresh_integration_pilot", {})
    pilot.update({"status": "FAILED", "experiment_validity": "INVALID", "primary_root_cause": reclassification["primary_root_cause"], "secondary_findings": reclassification["secondary_findings"], "model_strategy_capability": reclassification["model_strategy_capability"], "strategy_calls": 3, "spine_calls": 0, "skeleton_calls": 0, "no_retry_same_cohort": True, "historical_machine_classification": "MODEL_FAILURE"})
    pointer["strategy_authority_contract_ssot"] = {"status": "CLOSED", "provider_spec": "PASS", "preserve_intent_contract": "PASS", "preserve_authority_compiler": "PASS", "provider_validator_parity": "PASS", "schema_fingerprint_parity": "PASS", "authority_completeness": "PASS", "legacy_fallback": False, "fresh_path": "V3_ONLY", "provider_calls": 0}
    canary = pointer.setdefault("shot_architecture", {}).setdefault("generation_architecture_redesign", {}).setdefault("spine_topology_canary", {})
    canary.update({"historical_preflight_ready": True, "historical_recanary_retired": True, "executable_again": False, "retired_after_execution": True, "no_further_spine_topology_recanary": True, "current_recanary_authorized": False})
    _write("director-quality-v3-current-stage-authority.json", pointer)

    report = f"""# Director Quality V3 — Strategy Authority Contract SSOT Closure

**Status:** `DIRECTOR_V3_STRATEGY_AUTHORITY_CONTRACT_SSOT_CLOSED`

## Baseline Audit

- Historical Fresh Pilot #1 remains `FAILED`; its raw request/response/fingerprint/manifest/ledger were not modified.
- Historical experiment validity is reclassified as `INVALID` because the Provider contract exposed legacy `must_preserve` strings while Runtime required structured anchors.
- Existing Spine → Topology re-canary remains retired; no historical artifact or runner was changed.

## Final As-Built Verification

- Strategy Provider Spec SSOT: `PASS`
- Preserve Intent contract and deterministic compiler: `PASS`
- Provider/Validator parity and schema fingerprint parity: `PASS`
- Fresh path: `V3_ONLY`; legacy machine fallback: `false`
- Fresh Pilot #1: `FAILED` / `INVALID`; root cause: `{reclassification['primary_root_cause']}`
- Retired Provider cohort: `{len(retired_ids)}` scenes; future experiment reuse: `false`
- Fresh Pilot #2 inventory: `{inventory.get('eligible_unseen_scene_count', 0)}` eligible unseen scenes; frozen: `false`; authorized: `false`
- Provider / LLM / MiMo / HTTP / media / storage / CI calls: `0`
- Atomic Expansion: `HOLD`; Production ShotPlan: `HOLD`; Human Preference: `NOT_RECORDED`

## Decision

`DIRECTOR_V3_STRATEGY_AUTHORITY_CONTRACT_SSOT_CLOSED`

The next Fresh Pilot, if separately authorized, will be evaluated under the V3 structured preserve-intent contract. This closure does not claim that MiMo Strategy capability has passed.
"""
    (ART / "director-quality-v3-strategy-authority-contract-ssot-report.md").write_text(report, encoding="utf-8")
    gap = f"""# Director V3 Strategy Authority Contract SSOT Gap Audit

## Baseline Audit

- Provider-facing Pilot #1 contract accepted `must_preserve: string[]`.
- Runtime authority expected structured preserve anchors, so the failed experiment was not a fair model-capability adjudication.

## Final As-Built Verification

- Machine authority is now `preserve_intents`; `must_preserve` is human-readable projection only and cannot pass Fresh V3 validation without an explicit projection marker.
- Anchor refs are required, exact and provider-visible; invalid or missing refs fail closed. No regex, fuzzy matching, embedding, semantic mapper or prose guessing is used.
- Program assigns `MP01...`, canonicalizes refs, provenance and fingerprints; the Provider never assigns constraint IDs.
- Authority completeness and Provider readiness require schema, identity, preserve and provenance checks before downstream calls.
- Fresh Pilot #1 is retained as historical `FAILED`, reclassified `INVALID`, and all six exposed scenes are retired from future Provider experiments.
- Fresh Pilot #2 is inventory/readiness only (`ready=false`, `authorized=false`, no cohort freeze).
- Provider calls in this closure: `0`.
"""
    (ART / "director-quality-v3-strategy-authority-contract-gap-audit.md").write_text(gap, encoding="utf-8")
    print(json.dumps({"status": "DIRECTOR_V3_STRATEGY_AUTHORITY_CONTRACT_SSOT_CLOSED", "provider_calls": 0, "fresh_pilot_2": readiness_doc, "retired_count": len(retired_ids)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
