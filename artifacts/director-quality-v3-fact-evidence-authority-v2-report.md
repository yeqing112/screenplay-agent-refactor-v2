# Director Quality V3 — Fact Evidence Authority V2

## Baseline Audit

- Attempt #1 real execution base: `d4e65554a6ab366aa43f877f707849f28110d2f7`.
- Attempt #1 evidence closure head: `d47f4c6c5f292681f4b507018c847115d81a5085`.
- Attempt #1 remains immutable: `true`; response hash verified: `true`.
- Attempt #1 facts: `36`; verified remains `0`; invalid remains `36`; ScriptIR calls: `0`; exposure: `EXPOSED`.

## Forensic Adjudication

- Provider requested V1 evidence shape: free-form `evidence` field with exact excerpt guidance, but no machine-readable object schema.
- Runtime V1 validator expected: list entries containing `excerpt` and optional `start`/`end` span.
- Actual Attempt #1 shape: `36 string evidence values`; diagnostic exact support: `19`; near matches: `4`; truly unsupported: `13`.
- Primary root cause: `PROVIDER_VALIDATOR_CONTRACT_MISMATCH`. Model fact capability: `NOT_FAIRLY_ADJUDICATED`.

## V2 Closure

- Deterministic source evidence anchors: `347`; char/byte offsets: `PASS`; index fingerprint: `4697f3069bb34c9650d97b7e2c788d5b9db36034a39fedf77a0756e7a7bf5295`.
- V2 provider schema fingerprint parity: `PASS`; provider excerpts/offsets/authority/status: forbidden; legacy free-text fallback: `false`.
- Resolver and epistemic mapping: `PASS`; deterministic synthetic dry-run: `PASS` (not a production result).
- Provider calls this round: `0`; Attempt #2 authorized: `false`.

## Decision

`DIRECTOR_V3_FACT_EVIDENCE_AUTHORITY_V2_CLOSED`

V1 failure remains historical evidence. The V2 architecture is closed and ready for a separately authorized future Fact attempt, but this round does not authorize or execute it.
