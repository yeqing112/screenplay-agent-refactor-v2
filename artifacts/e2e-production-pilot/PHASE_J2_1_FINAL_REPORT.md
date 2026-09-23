# Phase J2.1 Final Report — PromptIR / Media Policy Cardinality Review

## Final status

```text
PHASE_J2_1_MEDIA_SCOPED_PROMPT_IR_SCHEMA_REQUIRED
```

This is a design Gate only. J3 was not started.

## Baseline

- HEAD: `64692456a44b84377fa1b64d5b4046f778c06ff1`
- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Scope: `PHASE_J2_1_PROMPT_IR_MEDIA_POLICY_CARDINALITY_REVIEW`

## What was verified

The audit confirmed that `PromptIRPointer.storyboard_shot_id` is unique, so the current model has one current PromptIR per shot. `OfficialMediaPointer` is already unique per `(shot, media_role)`, and the shared execution/candidate records carry `target_media` and PromptIR lineage.

A provider-free temporary SQLite reproduction created:

1. IMAGE PromptIR A, IMAGE execution/candidate/validation, and `SHOT_PRIMARY_IMAGE` OfficialMedia A.
2. A strict resolver call that returned `PASS` before any VIDEO PromptIR existed.
3. Legal VIDEO PromptIR B and an advance of the single PromptIR pointer from A to B.
4. A second strict resolver call for the existing IMAGE OfficialMedia, which returned `OFFICIAL_MEDIA_BINDING_INVALID` with cause `MEDIA_OFFICIAL_RESOLUTION_FAILED`.

The historical IMAGE chain remained internally valid: candidate/execution lineage, validation envelope, technical bytes, OfficialMedia lineage hash, payload hash, and PromptIR A payload hash all verified. The failure is current-lineage obsolescence caused by pointer cardinality, not tampering.

See [the reproduction JSON](./phase_j2_1_prompt_media_currentness_reproduction.json) and [the cardinality matrix](./phase_j2_1_media_authority_cardinality_matrix.md).

## Decision

Option B, media-scoped PromptIR pointers, is selected. It preserves the approved J2 rule that `GenerationPolicy` is semantic PromptIR policy while aligning PromptIR currentness with the already media-scoped OfficialMedia roles. Option A would require an authority redesign that reclassifies GenerationPolicy as execution intent and changes Phase E historical semantics. Option C would remove legitimate IMAGE OfficialMedia truth and create a competing reference model.

The required follow-up is a schema/migration and resolver design for a PromptIR pointer scope of `(book, episode, storyboard_shot_id, target_media)`. This Gate intentionally performed no migration or production code change.

See [the policy decision](./phase_j2_1_prompt_media_policy_decision.md) and [the schema decision](./phase_j2_1_schema_decision.json).

## Side-effect accounting

```text
Provider calls: 0
LLM calls: 0
Image calls: 0
Video calls: 0
Database migration performed: false
Production Authority writes: 0
Temporary fixture writes: yes, temporary SQLite only
FULL_REAL_END_TO_END_PRODUCTION_ACCEPTANCE_COMPLETE=false
```

## Stop condition

Do not start J3 implementation from this report. The media-scoped PromptIR pointer contract, backfill rules, API/resolver scope, stale propagation, and `IMAGE_TO_VIDEO` reference authority must be approved first.
