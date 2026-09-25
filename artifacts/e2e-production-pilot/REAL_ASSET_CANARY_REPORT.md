# Real Asset Canary Report

- Status: `PHASE_UI_V2_REAL_ASSET_CANARY_COMPLETE`
- Mode: provider-free frozen response fixture
- Episode count: `1`
- Shot count: `3`
- Asset count: `2` (one CHARACTER, one SCENE)
- Provider calls: `0`
- Approval state: `CANARY_APPROVED`

## Reconcile pipeline

`provider_output → asset_normalization → constraint_check → reconcile → approval_state`

- Provider output is a frozen fixture; the runner performs no provider or object-storage calls.
- Normalization requires canonical asset identity, media identity and complete provenance metadata.
- Constraint checks require a source reference, exact shot requirement coverage, readable media identity and `is_mock=false`.
- Production writes: `True` and only after reconcile: `True`.

## Truth audit

- `asset_has_source_reference`: `True`
- `asset_matches_shot_requirement`: `True`
- `asset_state_transition_valid`: `True`
- Mock asset production approved: `False`
- Provenance metadata required: `True`
- Source Fact mutations: `0`
- ScriptIR mutations: `0`

## Regression protection

- Existing production regression baseline: `1787 passed`.
- Current production regression: `1790 passed` (`1787` existing + `3` canary tests); existing regression remains unchanged.
- Golden regression: `5/5 passed`.
- Release-gate invariants: `passed`.

## Persistence evidence

- Authority rows: `2`
- Version rows: `2`
- Pointer rows: `2`
- Shot rows: `3`
- Binding rows: `6`
- All three shots resolve through typed Production Asset Authority/Pointer/Version and exact active bindings.
- No VisualReferenceAuthority or legacy adopted row participates in approval.

## Scope boundary

This canary proves the provider-free reconcile contract and does not announce `UI_V2_COMPLETE`. Real external provider execution remains outside this fixture run.
