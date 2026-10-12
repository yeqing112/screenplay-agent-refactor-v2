# V7.7.4 Source Entity Proposal + Structured Output Contract Boundary

## Status

`PROVIDER_STRUCTURED_OUTPUT_CAPABILITY_QUALIFICATION_REQUIRED`

V7.7.3 remains historical and immutable. Its raw SHA is
`c16ec191df55d937effa7246bcdb520bc573ecc6f2c1db8d08e15aa44bd46688` and the
freeze check passed. No V1 artifact was repaired, normalized, coerced, renamed,
or migrated; `CAND_` is not accepted as an alias.

## Root cause reassessment

- Semantic failure: `NOT_DETERMINABLE_BEFORE_VERIFIER`
- Structural contract failure: `YES`
- Entity authority gap: `YES`
- Semantic verification: `NOT_REACHED`
- Formal classes: `STRUCTURAL_OUTPUT_CONTRACT_FAILURE`, `ENTITY_AUTHORITY_GAP`, `SEMANTIC_VERIFICATION_NOT_REACHED`

## Entity and claim contracts

- Current canonical entity registry: `4` entries (`SCENE`, two `CHARACTER`, one `DIALOGUE_CONTENT`). Generic `OBJECT`, `LOCATION`, `ENVIRONMENT`, text, property, and state entities are absent.
- `SourceEntityCandidate`: `source_entity_candidate_v1`, generic kind enum, exact `surface_form` evidence anchoring, evidence and source-unit refs, `UNTRUSTED_PROPOSED`.
- `surface_form` is never canonical identity or semantic authority.
- Provider entity IDs are forbidden. The program assigns `PEC_0001` after schema and evidence validation.
- Claim V2: `source_semantic_claim_candidate_v2`; provider payload has no `candidate_id`; subject/object must be `{kind, ref}` and refs must belong to the canonical or validated proposal registry.
- Free-text refs, unknown refs, and provider ID injection are blocked. The program assigns `SCC_0001` after validation.
- V1 historical candidates are not migrated to V2.

## Structured output

- Provider profile: `local-llm-2vydoz` / `openai-compatible` / `mimo-v2.5`
- Capability state: `UNKNOWN`; profile declaration: `False`
- Historical V7.7.3 observed transport format: `{"type":"json_object"}`; this does not qualify strict JSON Schema support.
- `JSON_OBJECT_ONLY`: fail-closed
- `JSON_SCHEMA_SUPPORTED`: fail-closed for this strict boundary
- `JSON_SCHEMA_STRICT_SUPPORTED`: required for authorization
- Self-contained JSON schemas: `PASS`; dangling `$ref`: `0`
- Response format preview uses `json_schema` with `strict=true`.
- Prompt remains semantic guidance; response schema is the structural enforcement boundary.

## Anti-heuristic audit

- Candidate ID alias: `NO`
- Free-text subject/object compatibility: `NO`
- Current story entity registration: `NO`
- Story-specific predicate mapping: `NO`
- Phrase, scene, or attempt dependence: `NO`
- Local NLP / noun detection: `NO`
- Same typed input with different display prose: deterministic result unchanged

## Completeness and authorization

- Entity proposal: `CONTRACT_READY_NOT_EXECUTED`
- Proposal entity registry: `READY_AS_NON_CANONICAL_BOUNDARY`
- Claim proposal: `BLOCKED_BY_CAPABILITY_AND_ENTITY_PHASE`
- Director semantic completeness: `NOT_PROVEN`
- Typed requirement manifest: `TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING`
- Source Entity Proposal authorization: `NO`
- Claim Proposal retry: `NO`
- Semantic Verifier: `NO`

## Calls and writes

- Real Provider: `0`
- Semantic Verifier: `0`
- Stage A / Attempt-12 / Confirm: `0`
- IMAGE / VIDEO: `0`
- Production writes: `0`
- FactSnapshot 49, ScriptIR 52, Packet 64: unchanged
- Director ledger: `11`
- Active Stage B: `attempt-11`

## Verification

- V7.7.4 + V7.7.3 + V7.7.2 focused tests: `40 passed`
- V7.7.4 test module alone: `18 passed`
- Compileall: passed
- `git diff --check`: passed
- SceneBlocking baseline: `29 passed, 3 pre-existing failures`; unchanged and out of scope
- Required artifacts: `26 JSON + 1 Markdown`, all parse successfully

Implementation commit and final remote HEAD are recorded in the final Git update.
