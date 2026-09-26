# Asset Promotion Runtime Report

## Result

`ASSET_PROMOTION_RUNTIME_COMPLETE`

- Commit: `f2fb492ce5b24bf8fc0abf46abde078299fef096`
- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Migration head: `c8d9e0f1a2b3`
- Provider contract: `shapi-openai-images.image.v1` via `https://shapi.vip/v1`
- External provider calls in this runtime phase: `0` (deterministic fixture tests); the previously accepted real SHAPI canary remains the provider evidence.

## Delivered

- Added `MediaPromotionRecord` and candidate validation metadata/status fields.
- Validation now creates `REVIEW_REQUIRED` review state while keeping `MediaCandidateRecord.status=MEDIA_CANDIDATE`.
- Explicit `APPROVE` records reviewer and publishes `OfficialMediaVersion`, `OfficialMediaAuthority`, and `OfficialMediaPointer`.
- `REJECT` and `REQUEST_CHANGE` persist the decision and fail closed without official rows.
- Added `/api/assets/candidates` and `/assets/candidates` list, validate, and promote routes.
- Added migration-chain checks for the new schema, secret-free candidate metadata serialization, and provider-response completeness enforcement.

## Verification

| Area | Command / evidence | Result |
|---|---|---|
| Migration chain | `python -m scripts.verify_migration_chain --ci` | PASS; fresh upgrade, repeat upgrade, legacy fixtures, and drift all pass |
| Promotion contract | `pytest -q tests/test_media_validation_promotion_contract.py` | 16 passed |
| Runtime review/API | `pytest -q tests/test_asset_promotion_runtime.py` | 5 passed |
| SHAPI/provider regression | `pytest -q tests/test_real_image_provider_canary.py tests/test_model_adapter_runtime.py tests/test_generation_execution_foundation.py` | 13 passed |
| Schema regression | `pytest -q tests/test_migration_chain_hardening.py tests/test_h2_asset_authority_schema.py` | 11 passed |
| Canonical validator regression | `pytest -q tests/test_phase_j3_canonical_generation.py` | 22 passed |
| Diff hygiene | `git diff --check` | PASS |

## Golden / regression

- Golden: deterministic 1x1 PNG fixture used for validation and promotion contract tests; no provider bytes or credentials are stored in the new reports.
- Regression: existing real-image SHAPI canary and model adapter suites remain green.
- Authority chain: `Provider Response → GenerationExecutionRecord → MediaCandidateRecord → MediaValidationRecord → MediaPromotionRecord → OfficialMediaVersion → OfficialMediaPointer`.

ASSET_PROMOTION_RUNTIME_COMPLETE
