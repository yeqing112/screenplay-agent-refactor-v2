# PHASE_E_PRODUCTION_BOUNDARY_AUTHORITY_AND_REUSE_CLOSURE

## Production Boundary Closure

Phase E now has one Production spine:

`Current Storyboard Authority → explicit GenerationPolicy → internally resolved Visual Asset Authority → PromptIR v2 compile → PromptIR v2 Authority/Pointer → current v2 resolver → Model Adapter preview`.

- Legacy V1 single-shot compile returns `409 PROMPT_IR_LEGACY_PRODUCTION_DISABLED` and cannot mutate the Production pointer.
- Production adapter preview returns `409 PROMPT_IR_V2_REQUIRED` for a V1 current pointer and never calls the legacy serializer.
- Episode compile requires explicit `generation_policy.mode` and `target_media`; missing policy returns `409 GENERATION_POLICY_REQUIRED`.
- Request-supplied `asset_authority` is not part of the Production request model and is ignored when sent as an extra field. Authority is resolved from current `VisualAssetPointer` rows.
- PromptIR reuse calls the shared current-authority validator. It validates pointer/version/authority, schema, hashes, envelope, current Storyboard lineage, semantic recompilation, policy fingerprint, and asset lineage before `reused=true`.
- Visual Reference Authority has no latest-row fallback. Matching references must be unambiguous, `LOCKED`/`REFERENCE_LOCKED`, `FRESH`, and bound to the current asset version fingerprint.
- `*_REFERENCE` policy classes require a concrete current reference authority. Asset identity classes remain separate from concrete reference media requirements.
- Legacy serializer and V1 models remain available for read/audit compatibility only.

## Real pilot evidence

The provider-free real temporary SQLite/Alembic pilot persisted current rows for:

| Check | Result |
| --- | --- |
| Storyboard snapshots | Scene 1: 8; Scene 2: 7 |
| PromptIR v2 compile | 15 versions, 15 authorities, 15 pointers |
| Exact shot mapping | 15/15 `plan_shot_id` one-to-one |
| Clean reuse | 15/15 reused; counts unchanged |
| Missing GenerationPolicy | HTTP 409 `GENERATION_POLICY_REQUIRED` |
| Fake request asset authority | Not present in any persisted payload |
| Legacy V1 compile / adapter | Both HTTP 409 `PROMPT_IR_V2_REQUIRED` |
| Required reference missing | HTTP 409 `PROMPT_IR_REQUIRED_REFERENCE_AUTHORITY_MISSING` |
| Pointer/envelope/payload/semantic tamper compile-again | All HTTP 409 |
| Storyboard stale propagation | 8 PromptIR rows stale |
| Visual Asset stale propagation | 8 PromptIR rows stale |
| Adapter previews | 15 deterministic v2 payloads |
| Provider / LLM / image / video calls | 0 / 0 / 0 / 0 |
| DB migrations added | 0 |

Evidence files:

- `phase_e_production_boundary_audit.json`
- `episode_01_phase_e_trace.json`
- `episode_01_prompt_ir_phase_e.json`
- `episode_01_generation_payload_phase_e.json`

## Verification

- Phase E semantic and authority regressions: **48 passed**.
- New Production Boundary Closure suite: **7 passed**.
- Combined focused regression: **55 passed**.
- Deterministic Golden regression: **5/5 passed**.
- Full backend: **1631 passed, 4 historical failures**.

The unchanged historical failures are:

1. `test_director_quality_v24_offline_replay`
2. `test_director_quality_v3_final_spine_topology_preflight_wiring`
3. `test_real_llm_gray_selection`
4. `test_targeted_missing_fact_api`

No Phase E induced failure was observed.

## Migration and provider status

- No database migration was added.
- No LLM, provider, image generation, or video generation was started.
- `PROMPT_IR_QUALIFIED` remains separate from `MODEL_GENERATION_READY`.

## Review token

`PHASE_E_PRODUCTION_BOUNDARY_AUTHORITY_AND_REUSE_CLOSURE_READY_FOR_REVIEW`
