# ScriptIR Source Requirement Contract Recanary

## Baseline Audit

- Previous baseline used historical `MissingFactManifest` reclassification.
- That baseline reported zero ScriptIR requirements, but did not prove that the ScriptIR consumer has no source inputs.
- Historical downstream backlog remains preserved: `6` items.

## Final As-Built Verification

- Consumer audit: `SCRIPT_IR_CONSUMER_AUDIT` (see `director-quality-v3-script-ir-consumer-audit.json`).
- Source input: `tests\fixtures\golden\dialogue_power_shift\script.json` (structured payload only; no production entity was persisted).
- Contract: `script_ir_source_requirement_contract_v1` (see `director-quality-v3-script-ir-source-requirement-contract.json`).
- Formal requirement set: `4` total; blocking `2`; optional `2`; derived `0`.
- Coverage: covered `2`; derived-covered `0`; missing `0`; ambiguous `0`; conflicted `0`; invalid `0`.
- Status: `SCRIPT_IR_SOURCE_CONTRACT_COVERAGE_SUFFICIENT`; authority readiness: `SCRIPT_IR_AUTHORITY_ACTIVATION_READY`.
- `source_fact_only_missing_manifest`: `0`.
- Structural metadata is separate from FactSnapshot story facts; no visual identity, geometry, camera, lighting, blocking or shot-design requirement was promoted.

## Safety Boundary

- Provider calls: `0`; production writes: `0`.
- No ScriptIR, FactSnapshot, DirectorTreatment, SceneBlocking, ShotPlan or media record was created or modified.
- Next stage only when separately authorized: `SCRIPT_IR_AUTHORITY_ACTIVATION`.
