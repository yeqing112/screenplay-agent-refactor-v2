# Production UI V3 Real Provider Staging Vertical Slice

## Result

**Status: `BLOCKED_REAL_IMAGE_RESPONSE_PROJECTION`**

The non billable SHAPI catalog probe succeeded and confirmed the exact model `grok-imagine-image-quality`. The normal V3 browser path completed canary creation, content readiness, script lock and release, director treatment, runtime ShotPlan approval, storyboard materialization, production asset binding, and IMAGE PromptIR preparation for disposable canary Book `990453`.

The first real IMAGE submission reached SHAPI, but canonical execution rejected the returned media before candidate review because the persisted Provider response projection did not satisfy the complete response identity contract. Three controlled attempts each recorded `provider_calls=1` and were cleaned up as disposable canaries. No Official IMAGE version was created and no VIDEO call was started.

The required two-call initial-plus-regenerate proof therefore remains incomplete. This report records the actual block and does not mark the phase complete.

## Gate and provider facts

- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Baseline remote commit: `7c5f28c13aba50d1bcb4b91f775deaaa8ac1fdad`
- SHAPI profile: `local-image-mw4y52`
- Provider: `shapi-openai-images`
- Model: `grok-imagine-image-quality`
- Base URL: `https://shapi.vip/v1`
- Transport: `shapi-openai-images.image.v1`
- Catalog probe: passed by `GET /v1/models`; exact model present
- Browser direct provider hosts: `0`
- Book `990400` writes: `0`
- Production writes outside disposable canaries: `0`
- VIDEO: not started
- API keys: not written to this report or evidence

## Browser evidence

Final controlled browser artifact: `output/playwright/real-image-staging-final8/summary.json`.

- 16 preparation and cleanup steps passed before the IMAGE submission blocker.
- Disposable canary creation and deletion were performed through the normal UI path.
- Browser external hosts: `0`.
- The only failed business mutation was the canonical `generate-frame` request, HTTP 502.
- The browser surfaced duplicate React keys for built-in mock selector entries; this is recorded as a known UI warning and did not cause the provider call.

## Real provider call accounting

| Attempt | Provider calls | Result | Evidence |
|---|---:|---|---|
| final5 | 1 | blocked by missing response identity projection | `GENERATION_EXECUTION_FAILED` |
| final7 | 1 | blocked by the same projection contract | `GENERATION_EXECUTION_FAILED` |
| final8 | 1 | blocked by the same projection contract | `GENERATION_EXECUTION_FAILED` |

The strict requested budget was two calls for initial generation and regeneration. The observed recovery attempts total three calls, so the phase is explicitly blocked rather than represented as a successful two-call proof.

## Zero-call and configuration fixes delivered

- Delivery readiness now clears stale repair copy when `canExport=true`; blocked readiness retains repair guidance.
- Pilot migration head is `p1q2r3s4t5u6`.
- Model registry API now preserves canonical adapter and credential binding fields.
- SHAPI staging credential reference uses a secret-free runtime environment binding with a secret-free runtime validator.
- SHAPI OpenAI image responses derive a stable secret-free response identity when the upstream omits `id`.
- Provider profile parameters are reduced to the typed execution allowlist.

## Verification

- Web delivery test: 9 passed
- Relevant backend suite: passed before the final staging attempts
- Web production build: passed
- Node syntax check: passed
- Python compileall: passed
- Alembic head: `p1q2r3s4t5u6`
- `git diff --check`: passed

## Next safe action

Resolve the remaining runtime response projection mismatch, then run one fresh canary with the strict two-call budget. Do not treat the current evidence as `REAL_PROVIDER_STAGING_IMAGE_GO` or as phase completion.
