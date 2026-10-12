# V7.7.7 Source Entity Semantic Verification — Single Real Provider Canary

## Scope and lineage

- Target Book: `990453`; Episode: `1`
- Origin source: Book `990402`, chapter `16`, sequence `3`
- Origin source package: `book:990402`
- Cross-book lineage reconciliation: `PASS`; cross-book source: `True`; differing target/origin IDs alone are not a mismatch.
- Origin raw fingerprint: `190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1`
- Lineage documents: NEW_BOOK / FROZEN_SOURCE_LINEAGE / ORIGIN_SOURCE_REFREEZE / AUTHORITY_ENVELOPE_V2_AUDIT all cross-checked with runtime authority, migration, reconciliation, manifest, and persisted DB snapshot.
- V7.7.6 source fingerprint: `190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1`; source-unit fingerprint: `2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f`; units: `12`.

## Frozen proposal and Provider call

- V7.7.6 raw SHA256: `1fdc30f0bb1aa6aeda4930aee3cefb4e5cf66d1c0b383bd3cd0be9338e41ff27`
- Proposal registry fingerprint: `7e1c7d37f36ae61b04504c107d0f7fc2c4bfc939a1ddfcbeb8badf4d7ff56fb4`
- PEC input count: `15`; registry freeze status: `PASS`
- Provider: `local-llm-2vydoz` / `openai-compatible` / `mimo-v2.5` / `https://api.xiaomimimo.com`
- Qualification fingerprint: `194241dae7837d160c63a72bd1c3017bd9a9d0219d2f25e6a083637abdf3cb3b`; identity freshness: `PASS`
- Verifier POST attempts: `1`; HTTP: `200`; finish_reason: `stop`; latency ms: `22354.73`
- Tokens: `{"cache_hit_rate": null, "cached_tokens": null, "completion_tokens": 648, "completion_tokens_details": {"reasoning_tokens": 0}, "prompt_tokens": 1990, "prompt_tokens_details": {}, "reasoning_tokens": 0, "total_tokens": 2638}`
- Raw response SHA256 / length: `86099972a3bf19dbd5e8047d9653572d5339aa57815f1df7738d037801221711` / `2021`; raw persisted before parsing: `True`
- Strict parse: `PASS`; transport schema validation: `PASS`

## Coverage and verdicts

- PEC coverage: `PASS`; missing / duplicate / unknown PECs: `0` / `0` / `0`
- Evidence scope violations: `0`
- Mention verdicts: `{"AMBIGUOUS": 0, "EXPLICITLY_EVIDENCED": 15, "NOT_EXPLICITLY_EVIDENCED": 0}`
- Kind verdicts: `{"AMBIGUOUS": 0, "SUPPORTED": 15, "UNSUPPORTED": 0}`
- Semantically verified / rejected / review required: `15` / `0` / `0`
- Final state: `SOURCE_ENTITY_SEMANTIC_VERIFICATION_VALIDATED`; next state: `SOURCE_SEMANTIC_CLAIM_V2_TRANSPORT_SCHEMA_BOUNDARY_REQUIRED`
- Verified PECs remain `SEMANTICALLY_VERIFIED_PROPOSAL`, never `CANONICAL_RUNTIME`; canonical promotions: `0`.
- Entity semantic completeness: `NOT_PROVEN`; the verifier did not assess omitted entities or source-unit completeness.

## Production and authority boundary

- Entity re-proposal: `0`; Fact Semantic Verifier: `0`; Source Claim Proposal: `0`
- FactSnapshot / FactRecord / SourceClaim / canonical entity writes: `0`
- FactSnapshot 49 / ScriptIR 52 / Packet 64 unchanged: `True`
- Director ledger: `11 -> 11`; active Stage B: `attempt-11 -> attempt-11`
- Stage A / Attempt-12 / Confirm: `0`; IMAGE / VIDEO: `0 / 0`
- Claim V2 compiler: `BLOCKED`; reason: `UNION_TYPE_UNSUPPORTED:$.properties.claims.items.properties.qualifiers.additionalProperties.type`
- Typed Director Requirement Manifest: `TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING`
- Anti-Heuristic review: `PASS`

## Verification

- V7.7.7 and V7.7.6–V7.7.2 regression suites: `83 passed`.
- Python compileall: `PASS`; `git diff --check`: `PASS`.
- Provider-call implementation commit: `7afef07c5b7ef247601988d269158d0c455da9c9` (pushed before the call).
- Branch: `codex/visual-authoring-provider-canary-reconcile`.
- Evidence publication commit: `12a3d873ffa2e84fced53c90bc0985258027b122`; at publication, local HEAD matched remote HEAD and the working tree was clean.
- SceneBlocking historical baseline remains `29 passed, 3 pre-existing failures`; it was not modified.

The run stops here. No source-entity reproposal, canonical promotion, Claim V2 repair, Claim Proposal, or Fact Semantic Verifier was run.
