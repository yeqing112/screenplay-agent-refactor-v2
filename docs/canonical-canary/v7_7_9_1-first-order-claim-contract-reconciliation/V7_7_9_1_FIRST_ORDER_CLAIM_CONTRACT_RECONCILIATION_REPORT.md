# V7.7.9.1 First-Order Claim Contract Reconciliation

## Reassessment of V7.7.9

- V7.7.9 remains `SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_PARTIAL`; immutable raw SHA256: `44730220ba61ce249d1ebd5b87e3a0373b4cc220e58b7f96eef04a5b06f40585`. The historical raw, candidate set, V2/V3 registries, and V7.7.9 artifacts were not changed.
- Candidate #2's direct validator error remains `SYMBOLIC_TOKEN_INVALID:speaker_binding`. The architecture root cause is `PROVIDER_OWNED_SPEAKER_BINDING_IS_REDUNDANT`, not a Chinese token formatting failure: speaker identity is already the `speech_act.subject_ref`, while the provenance belongs to structured upstream dialogue binding.
- `speaker_binding` semantic owner: grounded ScriptIR / upstream source-structuring program. It is not Provider-writable in V3.1.
- Old candidate #1 is `SUPERSEDED_SIGNATURE_NOT_VERIFIER_ELIGIBLE`: the former `enter_guided` relation omitted the guided participant. Old candidate #2 remains blocked as `BLOCKED_REDUNDANT_PROVIDER_QUALIFIER`. Current V7.7.9 verifier-eligible candidates: `0`.
- Historical replay with frozen V2/V3 registries reproduces `1 PASS / 1 BLOCKED`, including the exact symbolic-token error.

## New ownership and typed relation contracts

- Relation registry: `source_claim_relation_signature_registry_v3`. Qualifier registry: `source_claim_qualifier_registry_v3`. Provider predicate registry: `source_claim_proposal_predicate_registry_v2`.
- Ownership partition: Provider-proposable `5` first-order relations; program-deterministic `speech_act` (`1`); deferred second-order `knows` / `uncertainty` (`2`), pending verified ClaimRefs.
- Current runtime Provider-executable predicates: `enter_guided, left_by, received_by` (3). Dormant: `has_property, state_value` (2). Program-deterministic: `speech_act` (1).
- `speech_act` remains `SOURCE_SPEECH_ACT` / `SPEECH_ACT`, owner `PROGRAM_DETERMINISTIC`; Provider proposal is disabled. The frozen ScriptIR and SourceAuthoringUnit join produced `1` deterministic binding(s), with structured speaker provenance fingerprinted. A wrong subject is blocked with `SPEECH_ACT_SPEAKER_BINDING_MISMATCH`.
- Deterministic `speech_act` proves only that the bound speaker uttered the exact dialogue-content entity. It does not make the dialogue proposition a world fact; proposition truth still requires independent semantic verification.
- `enter_guided` now requires `guided_character: ENTITY_REF` constrained to `CHARACTER`. The destination remains `object_ref`; the duplicate `destination` qualifier is removed. Required qualifier kind availability is included in generic runtime executability derivation.
- New Provider qualifier surface is `guided_character, transfer_source`. `speaker_binding` is not writable; `destination` is not allowed for `enter_guided`.

## Verification and freeze

- Production freeze unchanged: Book 990453, FactSnapshot 49, ScriptIR 52, Packet 64; Director ledger `11` → `11`; active Stage B `attempt-11` → `attempt-11`.
- Provider calls `0`; Claim Verifier `0`; second-order Provider `0`; production writes `0`; Stage A / Attempt-12 / Confirm / IMAGE / VIDEO `0 / 0 / 0 / 0 / 0`.
- Claim V2 remains `LEGACY_BLOCKED_UNION_TYPE`; second-order `knows` / `uncertainty` remains `DEFERRED_NOT_PROVEN`.
- Completeness remains: entity semantics `NOT_PROVEN`, proposal completeness `NOT_PROVEN`, second-order epistemic coverage `DEFERRED_NOT_PROVEN`, Typed Director Requirement Manifest `MISSING`.
- Focused V7.7.2–V7.7.9.1 suites: `158 passed`; `python -m compileall -q core scripts tests`: `PASS`; `git diff --check`: `PASS`.
- No real Provider POST, verifier, re-proposal, promotion, Stage A, Attempt-12, Confirm, PR, or merge was performed.

## State

- Terminal state: `SOURCE_SEMANTIC_CLAIM_V3_CONTRACT_RECONCILED`.
- Next: `SOURCE_SEMANTIC_CLAIM_V3_REPROPOSAL_CANARY_AUTHORIZATION_REQUIRED`. A future proposal requires a new explicit authorization and must use the new frozen ontology.
- Baseline for this reconciliation: `cf3bebc93f94739402888d9f149ea523083bc621`. Final implementation and evidence commit SHAs are reported after pushing.
