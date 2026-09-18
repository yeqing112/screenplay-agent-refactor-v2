# Visual Authoring Provider Canary Reconciliation

## Baseline Audit

The prior provider canary lived on `codex/unify-formal-workspace` at `10962c9`,
while canonical Production Authority was `5b2a5ae`. The branches were not a
safe linear continuation (`ahead_by=5`, `behind_by=49`). The old branch is
therefore recorded as `NON_CANONICAL_PROVIDER_CANARY_BRANCH`; its simplified
Authority models, mutable row-id asset keys, and replacement migration were
not imported.

## Final As-Built Verification

The canonical branch now has an additive `VisualAuthoringProposal` model,
`x7g8h9i0j1k2` migration, and a no-op compatibility marker for the retired
`p0q1r2s3t4u5` revision. The existing Authority router and models remain
the source of truth. The independent provider router:

- requires an explicit LLM profile and `confirmed_provider_call=true`;
- builds a stable `book:{book_id}:{type}:{canonical_id}` key;
- sends only a deterministic evidence packet and bounded allow-list;
- validates exact `request_id` and `asset_key`, unknowns, source conflicts and
  forbidden authority fields;
- deduplicates an unchanged request fingerprint;
- stores a `REVIEW_REQUIRED` proposal without activating any authority; and
- maps human approval to field-level canonical `VisualAuthoringDecision` rows.

Asset Center now exposes a folded Provider Proposal panel. It only enables the
call when ProductionWorkspace exposes a complete stable asset key, shows the
proposal fields and review state, and supports confirm/reject actions without
clearing the production blocker or creating a version.

Approval does not create a `VisualAssetVersion`, move a `VisualAssetPointer`,
mutate `VisualReferenceAuthority`, or alter PromptIR. Existing user artifacts
were preserved in the pre-reconciliation stash and are not part of this
change.

## Gate status

Deterministic provider contract tests and canonical Authority API regression
tests pass. The canonical real MiMo Provider-only Canary also passed with
`book:987654321:character:char_canary_001`, exact request identity, HTTP 200,
JSON validation, source validation, and final `REVIEW_REQUIRED` status.

The canary made one logical and one transport call against profile
`local-llm-2vydoz` (`mimo-v2.5`). No `VisualAssetVersion`, pointer,
reference-authority, PromptIR stale state, image task, or video task changed.

The runtime database was an old Canary-era database and did not contain the
PromptIR tables; this was recorded as an unchanged absent-table baseline, not
treated as a false-green PromptIR comparison. The runtime database is now at
head `x7g8h9i0j1k2` and old rows remain intact.

The Golden regression passed (`5/5`). The fresh, pre-authority, and historical
Canary-revision migration gates pass with head `x7g8h9i0j1k2`. The aggregate
production release gate was not green in the local workspace because its
unrelated sample/shot-planning subprocesses still expect the old 990400 audit
sample; this is outside the Provider reconciliation and no provider/media call
was made by those subprocesses.

Full backend regression: `1540 passed, 3 unrelated historical failures`.
The failures are the pre-existing historical replay branch assertion, a
retired Director re-canary preflight expectation, and a targeted fact-extract
snapshot expectation; none exercises this Provider reconciliation. Frontend
regression: `301 passed`; production build passed.
