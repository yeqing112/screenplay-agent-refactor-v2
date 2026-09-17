# Director Quality V3 — Targeted Semantic Evidence Resolution

## Baseline / Retrieval

- Required manifest items: `6`; candidate anchor retrieval is scoped per fact and provider-free.
- Retrieval returns immutable exact text, source hash, character/byte offsets, lexical matches and ranking; it never creates facts.

## Resolution

- Resolved: `0`; ambiguous: `0`; conflicted: `0`; unsupported: `6`; remaining unresolved: `6`.
- Exact quote and anchor validation run before any proposal can be converted to a FactSnapshot candidate.
- No provider adapter was supplied; provider calls: `0`.

## Decision

- This stage does not mutate FactSnapshot or alter coverage thresholds.
- Merge: `NO_CHANGE`; coverage recheck: `FACT_COVERAGE_INSUFFICIENT`; ScriptIR gate: `BLOCKED_PENDING_TARGETED_MISSING_FACTS`.
