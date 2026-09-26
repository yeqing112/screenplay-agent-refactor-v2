# Production Batch Runtime Report

## PRODUCTION_BATCH_RUNTIME_COMPLETE

- **Commit:** `4a04f1a` (`feat: add production image batch orchestration runtime`)
- **Branch:** `codex/visual-authoring-provider-canary-reconcile`
- **Baseline:** `541aef8`
- **Migration:** `d9e0f1a2b3c4` adds `production_batches` and `production_batch_items`; the migration chain is single headed and repeatable.
- **Provider:** image generation remains bound to the existing SHAPI registry adapter: `shapi-openai-images`, endpoint `https://shapi.vip/v1`.

## Delivered vertical slice

`Episode → ProductionBatch → ProductionBatchItem → GenerationExecution → AssetPromotion review gate`

- Batch creation resolves the episode's current IMAGE PromptIR pointers and creates one durable execution per shot.
- Items run serially by `priority DESC, id ASC` through the existing `GenerationOrchestrator`.
- Existing `TaskRun` is reused for durable task status and progress; no Queue, Worker, Task System, or asset manager was added.
- Provider success creates/uses the existing MediaCandidate validation boundary. The batch does not auto-approve or replace `OfficialMediaPointer`.
- Failed items support bounded `retry_failed` recovery while retaining the same execution identity.
- VIDEO pointers fail closed; this phase is IMAGE-only and uses one fixed model profile per batch.

## Verification

- `pytest -q tests/test_production_batch_runtime.py` — **4 passed**
- `pytest -q tests/test_migration_chain_hardening.py tests/test_h2_asset_authority_schema.py` — **11 passed**
- `pytest -q tests/test_generation_execution_foundation.py` — **4 passed**
- `pytest -q tests/test_real_image_provider_canary.py tests/test_model_adapter_runtime.py` — **9 passed**
- `python -m scripts.verify_migration_chain --ci` — **PASS** (fresh upgrade, repeat upgrade, legacy preservation, drift)
- `git diff --check` — **PASS**

Migration and schema evidence is stored in the existing `artifacts/migration-*` reports in this commit.
