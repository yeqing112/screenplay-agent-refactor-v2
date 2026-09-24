# Phase J3.1 Boundary Closure — Final Report

Date: 2026-09-24  
Branch: `codex/visual-authoring-provider-canary-reconcile`

## Scope

This round closes the production generation boundary around the canonical image/video path. Legacy storyboard aliases now fail closed unless an explicit `model_profile_id` is supplied. Runtime credentials require an explicit resolver and validator binding, and secrets remain runtime-only. Image and video execution are dispatched through the exact provider transport registry.

## Implemented

- Legacy `generate-frame` / `generate-video` requests without a model profile return HTTP 409 `PRODUCTION_MODEL_SELECTION_REQUIRED` before provider, task, execution, candidate, or storyboard-media writes.
- Added formal `RuntimeCredentialBinding` resolver/validator registration. Missing or false validation returns `RUNTIME_CREDENTIAL_NOT_VALIDATED`.
- Added transport binding IDs to model profiles and canonical provider execution profiles.
- Added `core/provider_transport_registry.py` to route IMAGE and VIDEO through exact submit/poll adapters, including Poyo, MiniMax H3, 75API MiniMax H3, and deterministic mock transports.
- Added boundary and regression coverage for fail-closed legacy aliases, credential validation, provider-free replay, source drift, and official image-to-video source binding.
- Added a public temporary-DB pilot that confirms SceneBlocking → Phase C ShotPlan authoring → Storyboard materialization → media-scoped PromptIR → IMAGE / TEXT_TO_VIDEO / IMAGE_TO_VIDEO preview and execute paths without resolver monkeypatching.

## Evidence

- Focused J3/J3.1 boundary, canonical, and public-pilot tests: **28 passed**.
- Artifact evidence:
  - `phase_j3_1_legacy_generation_shutdown_audit.json`
  - `phase_j3_1_runtime_credential_validation_audit.json`
  - `phase_j3_1_provider_transport_matrix.json`
  - `phase_j3_1_full_canonical_provider_free_pilot.json`
- Director Quality artifact regression checks after restoring their baseline fixtures: **12 passed**.
- Full repository run observed **1785 passed, 6 failed**. The six failures were fixture-order mutations in unrelated Director Quality artifact tests; restoring those non-J3 artifacts returns that subset to green. No J3/J3.1 test failed.

## Provider and authorization status

All evidence paths remain provider-free: provider/image/video/paid-LLM calls are `0 / 0 / 0 / 0`. The public temporary-DB pilot reaches all three canonical media paths with `canonical_input_resolver_monkeypatched: false`; replay performs zero provider calls, and official media is created only by the explicit pilot authority step. Real-provider execution is intentionally not claimed because external credentials and human authorization are unavailable.

## Files

- Runtime and API changes: `api/server.py`, `api/model_registry.py`, `core/runtime_credentials.py`, `core/provider_execution_profile.py`, `core/provider_transport_registry.py`
- Tests: `tests/test_phase_j3_1_boundary_closure.py`, `tests/test_phase_j3_canonical_generation.py`, and `tests/test_phase_j3_1_public_pilot.py`
- Evidence and topology: the four JSON artifacts listed above and `phase_j3_canonical_generation_topology.md`
