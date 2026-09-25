# Director Quality V3 — Authorized Evaluation Source Upstream Phase A

**Status:** `DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_BLOCKED`

## Baseline Audit

- Historical expected HEAD: `63c93d6e1f78a4777fff9c3e329f5eeb723846eb`; resolved execution base: `2c2e3bc4649b2e6d0bb50ac3ed697c73da9bf779` (`REBASELINED`); observed `bd7db4cd4205081090f0d812f669621952152471`.
- Remote `origin/codex/unify-formal-workspace`: `10962c9fd3a0e2dd8445c6fe37f6aa76aaa7e174`.
- Immutable source package: `SRC79f12d1b7f5eb828` / `SRC79f12d1b7f5eb828:V01:d001bab5cc82`.
- Raw hash verification: `PASS`; provenance: `PASS`.
- Working tree dirty entries: `26`; no files were reset, stashed, deleted or overwritten.

## Final As-Built Verification

- Provider/model resolution: `openai-compatible` / `qwen3-max`; secrets omitted.
- Predicted provider calls: `2` (absolute max `2`); actual calls: `0`; retries: `0`.
- Evaluation isolation: production DB `0`, Book/Scene/FactSnapshot/ScriptIR production mutations `0`, Human Fresh Pool `0`.
- FactSnapshot: `NOT_RUN_BLOCKED`; ScriptIR: `NOT_RUN_BLOCKED`. ScriptIR dispatch is outside the Fact Attempt #2 authorization scope.
- Treatment, Blocking, Strategy, Spine, Topology, ShotPlan, Storyboard and media actions: `0`.

## Blocking Reasons

- EVALUATION_PHASE_A_HEAD_MISMATCH
- EVALUATION_PHASE_A_REMOTE_HEAD_UNAVAILABLE_OR_MISMATCH
- WORKTREE_NOT_CLEAN_FOR_REAL_PROVIDER_RUN

## Decision

`DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_BLOCKED`

Lineage is `SOURCE_ACCEPTED`; no Treatment processing is authorized. Human review is `NOT_RECORDED`.
