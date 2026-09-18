# Visual Authoring Provider Canary Reconciliation

## Baseline Audit

The prior provider canary lived on `codex/unify-formal-workspace` at `10962c9`,
while canonical Production Authority was `5b2a5ae`. The branches were not a
safe linear continuation (`ahead_by=5`, `behind_by=49`). The old branch is
therefore recorded as `NON_CANONICAL_PROVIDER_CANARY_BRANCH`; its simplified
Authority models, mutable row-id asset keys, and replacement migration were
not imported.

## Final As-Built Verification

The canonical branch now has an additive `VisualAuthoringProposal` model and
`x7g8h9i0j1k2` migration only. The existing Authority router and models remain
the source of truth. The independent provider router:

- requires an explicit LLM profile and `confirmed_provider_call=true`;
- builds a stable `book:{book_id}:{type}:{canonical_id}` key;
- sends only a deterministic evidence packet and bounded allow-list;
- validates exact `request_id` and `asset_key`, unknowns, source conflicts and
  forbidden authority fields;
- deduplicates an unchanged request fingerprint;
- stores a `REVIEW_REQUIRED` proposal without activating any authority; and
- maps human approval to field-level canonical `VisualAuthoringDecision` rows.

Approval does not create a `VisualAssetVersion`, move a `VisualAssetPointer`,
mutate `VisualReferenceAuthority`, or alter PromptIR. Existing user artifacts
were preserved in the pre-reconciliation stash and are not part of this
change.

## Gate status

Deterministic provider contract tests and canonical Authority API regression
tests pass. A real MiMo canary was intentionally not run in this turn; the
provider-only canary remains explicitly gated for the next authorization.

The Golden regression passed (`5/5`). The aggregate production release gate
was not green in this local workspace because its unrelated sample/shot
planning subprocesses still point at a historical database revision
`p0q1r2s3t4u5` that is absent from this canonical checkout, and the expected
990400 audit sample is not present. The fresh and legacy migration gate for
this reconciliation itself passed with head `x7g8h9i0j1k2`.
