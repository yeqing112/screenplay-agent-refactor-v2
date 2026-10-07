# DIRECTOR_CREATIVE_ENRICHMENT_REVISION_BOUNDARY_REPORT

## Status

DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_AUTHORIZATION_REQUIRED

V7.6.14 reconciles the V7.6.13 source projection drift and adds an explicit append-only Stage B semantic revision boundary. Attempt-8 remains immutable and active until a separately authorized revision succeeds.

## Source lineage

- Production canonical projection fingerprint: 2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f
- V7.6.13 evidence projection fingerprint: af3a206709921b6c068096d13c3c3d4903178f46768ab3f4408462fcf50f90c8
- Stable source_authority_content_fingerprint_v1: ea83de61dddd12842ea319e367f284a620bad83ad2c8643b65d331aa003db1c8
- V7.6.13 raw candidate content fingerprint: 0595fb5077b1a8db5ba34de97ae3be89a45e084da61da06013bc0e55ee6a47d5
- Reconciliation: PASS / SOURCE_PROJECTION_VERSION_DRIFT
- Finding: projection drift only; source content is equal and timeline order is recovered from canonical authority.
- True source text/type/speaker mutation fails closed with DIRECTOR_STAGE_A_SOURCE_AUTHORITY_STALE.

## Revision boundary

The initial Stage B endpoint keeps its completed/idempotency guard. The new endpoint requires the exact parent Attempt-8 ID, Attempt-8 IR fingerprint, semantic review fingerprint, packet fingerprint, production profile, explicit confirmation, external-call opt-in, and a new authorization ID.

The prompt carries compact semantic constraints and parent bindings. It does not carry the raw rejected Attempt-8 response. Revision attempts are dynamically numbered from the ledger (attempt-9, then attempt-10, then attempt-11).

## Archive and active state

progressive_director_authoring.stage_b_attempts[] stores immutable per-attempt evidence. The active stage_b pointer can move to Attempt-9 only after structural validation, deterministic merge, and proposal persistence. A structural failure archives Attempt-9 while restoring Attempt-8 as the active stage and proposal.

## Mock paths

- Mock success: one isolated mock call; Attempt-9 active; semantic PASS; confirm gate remains human controlled.
- Mock semantic blocked: one isolated mock call; Attempt-9 structurally valid but confirm blocked; next preflight is Attempt-10 authorization required.
- Mock structural failure: one isolated mock call; Attempt-9 schema-invalid archive; Attempt-8 active and proposal unchanged.

## Hard freeze

- Real external LLM: 0
- Real IMAGE: 0
- Real VIDEO: 0
- SHAPI / Poyo / 75API: 0
- Production Packet/DirectorTreatment/Authority/Pointer/SceneBlocking/ShotPlan/Storyboard writes: 0
- Attempt-8 raw/IR/evidence: unchanged

## Verification

- Combined Stage B revision/semantic/execution/provider suite: 55 passed
- tests/test_director_revision_boundary_v7_6_14.py: 11 passed
- V7.5.1 scope/IR/integrity regression suite: 46 passed
- python -m compileall -q core api: PASS
- git diff --check: PASS

## Final state

DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_AUTHORIZATION_REQUIRED

Semantic review fingerprint: c078b4f6dfda1549a54090ddff9d9d38432e26597aba42fd4c9c71e475eb4dcc\n\nNo real Provider authorization was created or consumed in this phase.
