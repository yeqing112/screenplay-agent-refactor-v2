# PHASE J2.4 Final Report

## Status

`PRODUCTION_REGRESSION_GATE_CONVERGENCE_IN_PROGRESS`

This commit packages the J2.4 regression evidence and the environment fixes needed to make CI deterministic. J3 remains blocked and was not started.

## Changes included

- Pinned `pytest-asyncio==1.1.0` so the three Phase F async transport contract cases execute in CI.
- Added `.gitattributes` for immutable raw evaluation sources and restored the declared raw source blob hash across Windows and Linux checkouts.
- Added a committed deterministic approved-scene fixture and made the fresh integration pilot use it by default; explicit database paths remain available for audit tooling.
- Added the machine-readable CI failure inventory, local/CI parity record, and Phase F transport evidence.

## Verification

- Targeted J2.4 repair and transport/storage wiring tests: **52 passed**.
- Local remaining baseline failures: **3** (offline replay historical branch context, retired recanary assertion precedence, and active registry scope).
- Prior CI run `35902213060` / job `107311920540`: **1751 passed, 13 failed** before this repair set.
- Provider / LLM / Image / Video calls: **0 / 0 / 0 / 0**.
- Migration and web/build evidence remains as recorded in `PHASE_J2_3_FINAL_REPORT.md`; no production migration was run and J3 was not started.

## Remaining closure work

The next CI run must confirm the cross-platform raw-source fix, deterministic fresh integration cohort, async transport dependency, SVG rasterization path, provider-free preflight, and targeted missing-fact API. The three local baseline failures remain explicitly open in `phase_j2_4_ci_failure_inventory.json`; no skips, xfails, failure allowlists, or CI-only bypasses were added.

## Artifacts

- `phase_j2_4_ci_failure_inventory.json`
- `phase_j2_4_local_ci_parity.json`
- `phase_j2_4_phase_f_async_transport_evidence.json`
