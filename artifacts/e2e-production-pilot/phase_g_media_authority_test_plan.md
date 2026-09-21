# Phase G Media Authority Migration Test Plan

## Status

Plan only. No Phase G implementation or tests were added in this task. The plan assumes the separately approved four-table migration and service/API implementation.

## Test fixtures and invariants

- Use a persisted Phase A–F chain with one real PromptIR, GenerationPayload, GenerationExecutionRecord, and `MEDIA_CANDIDATE`.
- Use local deterministic bytes; never call an external Provider or LLM.
- Assert Candidate remains immutable and `MEDIA_CANDIDATE` in every test.
- Assert all failed Promotion paths perform zero writes to Version, Authority, and Pointer.

## Candidate and Validation tests

1. valid PNG bytes pass deterministic technical validation;
2. empty file fails;
3. storage path/URL missing fails;
4. storage bytes replaced at the same identity fail;
5. recomputed SHA-256 mismatch fails;
6. invalid image bytes fail;
7. MIME mismatch fails;
8. media type mismatch fails;
9. dimensions missing or inconsistent fail;
10. Candidate execution id, Candidate id, PromptIR id/hash, GenerationPayload fingerprint, model/profile fingerprint, provider request fingerprint, or provider response hash mismatch fails;
11. PromptIR revision makes an otherwise intact historical Candidate `STALE` for promotion;
12. Asset revision makes it stale;
13. Reference Authority revision makes it stale;
14. validation payload/fingerprint tamper fails closed;
15. same Candidate/current lineage reuses the same validation record and does not create duplicates;
16. `AUTO_PROMOTED` is rejected as an invalid validation status.

## Promotion tests

1. valid Candidate + valid deterministic Validation + explicit confirmation creates exactly one Version, Authority, and Pointer;
2. Provider calls and LLM calls remain zero;
3. Validation PASS alone does not create official rows;
4. promotion request cannot carry prompt, style, reference, URL, storage, or checksum overrides;
5. stale confirmation after PromptIR, Asset, Reference, Candidate bytes, Validation, or Pointer change returns `409 MEDIA_PROMOTION_STALE` and performs zero writes;
6. duplicate same-Candidate promotion reuses the exact official revision;
7. different Candidate requires explicit revision and never uses last-writer-wins;
8. failed transaction leaves Version, Authority, and Pointer counts unchanged;
9. Candidate bytes/checksum/storage identity are unchanged by Promotion.

## Resolver tests

1. valid exact current pointer resolves;
2. missing pointer fails closed;
3. pointer to wrong shot/book/episode/role fails;
4. pointer fingerprint mismatch fails;
5. missing or stale Version fails;
6. missing or tampered Authority fails;
7. missing or tampered Validation fails;
8. Candidate lineage or storage checksum change fails;
9. current PromptIR/Asset/Reference drift fails;
10. resolver never falls back to latest Candidate, Validation, Version, or filename.

## Tamper and lifecycle tests

- Candidate DB field tamper;
- Candidate file tamper;
- Execution lineage tamper;
- Validation payload/fingerprint tamper;
- Official Version payload/status/checksum tamper;
- Authority envelope/lineage/promotion fingerprint tamper;
- Pointer scope/version/authority/fingerprint tamper;
- `CURRENT -> SUPERSEDED` revision lifecycle;
- `CURRENT -> STALE` fail-closed lifecycle;
- rejected Candidate remains queryable and immutable.

## Concurrency tests

- two identical promotions: at most one official revision, second reuses or returns deterministic conflict;
- two different Candidates for one shot/role: deterministic explicit-revision conflict, never last-writer-wins;
- pointer uniqueness is enforced under concurrent transactions;
- any loser performs zero Provider/LLM calls and zero partial writes.

## Real persisted pilot assertions

For one shot using the existing fake-provider Phase F Candidate:

```text
A–F authority before == A–F authority after
Validation records: 0 -> 1
OfficialMediaVersions: 0 -> 1
OfficialMediaAuthorities: 0 -> 1
OfficialMediaPointers: 0 -> 1
Provider calls: 0 during validation/promotion
LLM calls: 0
Candidate status: MEDIA_CANDIDATE
Candidate bytes/checksum/storage identity unchanged
```

## Regression and migration gates

- migration chain hardening passes;
- no existing A–F regression;
- Golden and Web suites remain unchanged;
- Alembic diff contains only the formally approved Phase G migration when implementation begins;
- no external Provider or LLM calls;
- no heuristic visual score is used as a Production hard gate;
- full real-E2E trigger is re-evaluated after implementation.
