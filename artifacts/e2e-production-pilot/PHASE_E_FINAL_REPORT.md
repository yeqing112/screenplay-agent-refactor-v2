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
- New Production Boundary Closure suite: **11 passed**.
- Combined focused regression: **104 passed**.
- Deterministic Golden regression: **5/5 passed**.
- Full backend: **1642 passed, 4 historical failures**.

The implementation validation run is **#231** (`35547462913`) for commit
`55a86a4`. Its deterministic production gate job (`106175858642`) failed with
exit code 1. The unauthenticated GitHub UI exposed the generic annotation
(`step:8:37`) plus the Node.js 20 and Ubuntu 26 runner notices; it did not
expose the failing test node IDs. The four historical failures below remain
the local baseline and were not changed in this phase.

The unchanged historical failures are:

1. `test_director_quality_v24_offline_replay`
2. `test_director_quality_v3_final_spine_topology_preflight_wiring`
3. `test_real_llm_gray_selection`
4. `test_targeted_missing_fact_api`

No Phase E induced failure was observed.

## PromptIR Revision Lifecycle

The current PromptIR integrity check is separated from currentness and new
compile intent:

- complete current object plus identical semantic payload and policy: `REUSE`;
- complete stored object plus an explicit changed GenerationPolicy: `REVISION`;
- complete stored object plus a valid upstream VisualAssetVersion activation:
  explicit `REVISION`;
- pointer, payload, envelope, semantic, or asset-lineage tamper: `409` and no
  replacement is created.

The real pilot proves `A → B → B`: Policy A created 15 v2 rows, identical A
reused all 15, Policy B created 15 new v2 versions and authorities while
moving the 15 existing PromptIR pointers, and identical B reused all 15.
The old 15 versions remain immutable apart from stale lifecycle fields.

## VisualAssetPointer Current Authority

`VisualAssetPointer` is part of the authoritative chain. The production asset
resolver validates pointer scope uniqueness, pointer freshness, pointer to
version identity, version freshness and production qualification, payload hash,
and authority status before any PromptIR or adapter binding consumes the
version. Reference resolution runs only after that validation and retains the
current-version fingerprint binding with no latest fallback.

The real pilot also activated a valid scene VisualAssetVersion A → B through
the existing visual-authority API. The pointer moved from version 10 to 12;
the eight Scene 1 PromptIR rows that bound that asset were revisioned while
the seven unaffected Scene 2 rows reused their current versions. Adapter
preview independently returned `409 VISUAL_ASSET_POINTER_TAMPERED` when only
the VisualAssetPointer hash was modified.

Evidence:

- `phase_e_prompt_ir_revision_asset_pointer_audit.json`
- `episode_01_phase_e_trace.json`
- `episode_01_prompt_ir_phase_e.json`
- `episode_01_generation_payload_phase_e.json`

## Migration and provider status

- No database migration was added.
- No LLM, provider, image generation, or video generation was started.
- `PROMPT_IR_QUALIFIED` remains separate from `MODEL_GENERATION_READY`.

## Historical Lineage Integrity Closure

Historical PromptIR validation now reads the exact persisted `MaterializationSet`, `StoryboardShot`, `VisualAssetVersion`, and `ReferenceAuthority` IDs bound by the PromptIR authority envelope. Historical rows may be stale because a newer upstream revision is current, but they must still reproduce their own deterministic compile and pass every persisted fingerprint check.

The provider-free real pilot records:

- clean current PromptIR: `PASS`;
- clean obsolete asset revision: `PASS`;
- clean obsolete Storyboard Set A → B revision: `PASS`;
- semantic tamper plus legitimate VisualAssetVersion A → B: `FAIL_CLOSED`, HTTP `409 PROMPT_IR_HISTORICAL_SEMANTIC_MISMATCH`, zero PromptIR version/authority/pointer writes;
- semantic tamper plus legitimate Storyboard Set A → B: `FAIL_CLOSED`, HTTP `409 PROMPT_IR_HISTORICAL_SEMANTIC_MISMATCH`, zero PromptIR version/authority/pointer writes;
- semantic tamper plus policy revision: `FAIL_CLOSED` with zero writes;
- missing historical asset, asset fingerprint tamper, and Storyboard projection tamper: all `FAIL_CLOSED`;
- historical latest fallback: `false`;
- provider, LLM, image, and video calls: `0 / 0 / 0 / 0`.

Evidence: `phase_e_historical_lineage_integrity_audit.json` and `episode_01_phase_e_trace.json`.

Production episode compilation now validates every still-current PromptIR pointer's historical integrity before matching the current Storyboard shot set. This prevents a new immutable StoryboardShot ID from hiding a tampered old PromptIR object.

## CI Execution Closure

GitHub Actions production regression now installs the pinned test dependency manifest `requirements-test.txt` (`pytest==8.4.2`) before collection. The closure regression is covered by `tests/test_prompt_ir_phase_e_historical_lineage_integrity_closure.py` and verifies that pytest installation is explicit in the workflow.

The first pushed commit triggered Production regression **Run #233** (`35550879680`), job **Deterministic production gate** (`106185271242`); the amended report commit `dbe0fd1` triggered **Run #234** (`35551041694`), job `106185724217`; the previous closure commit `e9aea39` triggered **Run #235** (`35551304302`), job `106186442313`. All three workflows reached the `Run production regression gate` step after installing `requirements-test.txt`, proving pytest is installed and collection/execution is no longer skipped by a missing dependency. All three gates concluded with exit code 1; the public unauthenticated UI exposes only the generic failing step annotation and does not expose exact pytest node IDs. Uploaded evidence artifacts are `production-regression-evidence-35550879680` and `production-regression-evidence-35551041694`; Run #235 has the same public evidence limitation. These are recorded as CI regression results, not as green CI claims.

The final local closure rerun of the four focused Phase E suites passed **41 tests** with one existing Pydantic deprecation warning. A push of this report commit will create the next production regression run; no result from that run is claimed here.

## Review token

`PHASE_E_HISTORICAL_LINEAGE_INTEGRITY_AND_CI_EXECUTION_CLOSURE_READY_FOR_REVIEW`
