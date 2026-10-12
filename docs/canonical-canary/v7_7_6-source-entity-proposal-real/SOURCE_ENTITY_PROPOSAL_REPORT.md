# V7.7.6 Source Entity Proposal Single Real Provider Canary

## Result

- Status: `SOURCE_ENTITY_PROPOSAL_VALIDATED`
- Next state: `SOURCE_ENTITY_SEMANTIC_VERIFICATION_BOUNDARY_REQUIRED`
- Preflight: `PASS`; all freshness, production freeze, schema, evidence, and anti-heuristic gates passed.
- Authorization: `v7.7.6-source-entity-proposal-single-call`
- Scope: Book `990453`, Episode `1`; runtime origin source package: `book:990402`
- Provider POST attempts: `1`; HTTP-confirmed: `1`; retry/fallback: `0`
- Provider: `local-llm-2vydoz` / `openai-compatible` / `mimo-v2.5` / `https://api.xiaomimimo.com`
- Provider identity fingerprint: `9908c628bc8b970817674b26ff3897bb055bc24ee6505bbc2af6a80f7722c455`
- V7.7.5 qualification fingerprint: `194241dae7837d160c63a72bd1c3017bd9a9d0219d2f25e6a083637abdf3cb3b`; current identity match: `PASS`
- HTTP / finish reason: `200` / `stop`; latency: `32513.23 ms`
- Usage: 1,190 prompt tokens; 816 completion tokens; 2,006 total tokens
- Raw response SHA256 / length: `1fdc30f0bb1aa6aeda4930aee3cefb4e5cf66d1c0b383bd3cd0be9338e41ff27` / `2414`; persisted before parsing.

## Schema and candidate audit

- Entity transport schema compiler: `PASS`
- Transport schema fingerprint: `f4cf9b6c0ed32fb4024dc277f30e1905192ef8014c96775a8c862e7133a16263`
- Request used `json_schema` with `strict=true`; the resolved sent response format matched the compiled schema.
- Strict parse / transport schema validation: `PASS` / `PASS`; JSON repair, markdown stripping, substring extraction, and coercion: `NO`
- Candidates: `15`; schema-valid: `15`; evidence-valid: `15`; source-unit-valid: `15`; surface-valid: `15`
- Already canonical: `0`; exact proposal duplicates: `0`; blocked: `0`
- Program-owned PECs: `15`; proposal registry entries: `15`; `UNKNOWN_ENTITY`: `1`
- Source units referenced: `9 / 12`; unreferenced: `3` (`SAU_E01_SC001_006`, `_007`, `_008`)
- Entity proposal coverage is recorded only; entity semantic completeness: `NOT_PROVEN`.
- Registry keeps runtime canonical entities under `CANONICAL_RUNTIME` and PECs under `UNTRUSTED_PROPOSED`. No candidate was promoted.

## Authority and production freeze

- Entity Semantic Verifier calls: `0`
- Source Claim Proposal calls: `0`; Semantic Verifier calls: `0`
- Canonical entity promotions: `0`; FactSnapshot / FactRecord / SourceClaim / canonical entity production writes: `0`
- FactSnapshot 49, ScriptIR 52, and Packet 64: unchanged
- Director ledger: `11 → 11`; active Stage B: `attempt-11 → attempt-11`; Stage A / Attempt-12 / Confirm: `0`
- Real IMAGE / VIDEO: `0 / 0`
- Claim V2 compiler: `BLOCKED`, reason `UNION_TYPE_UNSUPPORTED:$.properties.claims.items.properties.qualifiers.additionalProperties.type`
- Typed Director Requirement Manifest: remains `TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING`.
- Anti-Heuristic review: `PASS`; phrase, scene, attempt, story-specific registration, local NLP, noun dictionary, and regex entity extraction dependence: `NO`.

## Verification and Git

- V7.7.6, V7.7.5, V7.7.4, V7.7.3, V7.7.2 focused regressions: `73 passed`
- SceneBlocking historical baseline: `29 passed, 3 pre-existing failures`; unchanged and not modified in this phase.
- Python `compileall`: passed
- `git diff --check`: passed
- Implementation commit already pushed before the canary: `54444d9a5772a8552cff32e592d1dfbb3d22d3ec`
- Evidence commit and final remote HEAD are recorded in the final task delivery.

The single-call phase ends at the untrusted proposal entity registry. Do not run entity verification, entity promotion, Claim Proposal V2, or Semantic Verifier as part of this result.
