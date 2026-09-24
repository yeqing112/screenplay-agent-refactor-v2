# PHASE J2.4 Final Report

## Status

`PHASE_J2_4_PRODUCTION_REGRESSION_GATE_READY_FOR_REVIEW` — local and required GitHub Actions gates are converged.

J3 remains blocked and was not started. Provider / LLM / Image / Video external calls remained `0 / 0 / 0 / 0`.

## Changes included

- Pinned `pytest-asyncio==1.1.0` for the three Phase F async transport contract cases.
- Declared `cairosvg==2.9.0` for SVG-to-PNG public asset storage.
- Added `.gitattributes` for immutable raw evaluation sources and restored the declared raw source blob hash across Windows and Linux checkouts.
- Added a committed deterministic approved-scene fixture for the fresh integration pilot.
- Made historical offline replay provenance use an explicit historical source branch context.
- Corrected the retired re-canary test fixture to reach the dirty-worktree assertion without changing production gate order.
- Removed the negative E2E sample from the default production gray registry.
- Added test isolation cleanup for orphan FactSnapshot rows and explicit cleanup for the synthetic wrong-book fixture.
- Configured the required production workflow with `fetch-depth: 0` so frozen provenance commits are available to CI base-commit and provider-free ancestry gates.
- Serialized concurrent media promotions so the same candidate and validation produce one official version/pointer chain under concurrent requests.

## Verification

- `npm run check:production`: **1764 passed, 0 failed**; Golden **5/5**; runtime configuration **PASS**; release gate **PASS**; frontend build **PASS**.
- J2.3 authority/media regression set: **51 passed**.
- Migration: `MIGRATION_CHAIN_HARDENING_READY`; `migration_application_runtime_imports = 0`.
- Web: **51 files / 301 tests passed**; build **PASS**.
- Phase F transport cases for `openai-compatible`, `shapi-openai-images`, and `shapi-gemini-image`: executed and passed; mocked transport only; external calls **0**.

## Required CI

Run `35936589757` / job `107434875476` on commit `6c2c7afb50aa234b455a061bc27809a62ac6fe43` completed with conclusion **success**: **1764 passed, 0 failed**. The prior shallow-checkout and concurrent-promotion failures were resolved in the workflow and promotion path; no test exclusions or bypasses were added.

## Artifacts

- `phase_j2_4_ci_failure_inventory.json`
- `phase_j2_4_local_ci_parity.json`
- `phase_j2_4_phase_f_async_transport_evidence.json`
