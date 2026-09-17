# Director Quality V3 — Targeted Missing Fact Extraction

## Baseline Audit

- Source evidence is immutable and provider-free; requirements: `6`; missing manifest items: `6`.
- Existing FactSnapshot records are read-only input; provider calls: `0`.

## Targeted Extraction

- Candidates validated: `0`; unresolved: `6`.
- Only explicit `FACT:` declarations are eligible; natural-language guesses are unresolved.
- Evidence locators, exact excerpts, source hashes, value support, scope and authoritative conflicts are validated.

## Merge and Coverage Recheck

- Merge: `NO_CHANGE`; conflicts: `0`; unresolved: `0`.
- Coverage after recheck: `FACT_COVERAGE_INSUFFICIENT`.
- ScriptIR gate: `BLOCKED_PENDING_TARGETED_MISSING_FACTS`.
- No threshold was lowered and no unresolved/conflicted fact was promoted.

## Decision

`BLOCKED_PENDING_TARGETED_MISSING_FACTS`
