# MiniMax H3 Video Provider Canary Report

## PHASE_MINIMAX_H3_VIDEO_PROVIDER_CANARY

- **Implementation commit:** `7e326f614725c6c2c781acb86b90a01a4294e302`.
- **Branch:** `codex/visual-authoring-provider-canary-reconcile`.
- **Scope:** one Episode, one Shot, one Character, one Scene, one Video.
- **Image model:** SHAPI ([shapi.vip](https://www.shapi.vip/)), profile/provider `shapi-openai-images`, transport `shapi-openai-images.image.v1`, base URL `https://shapi.vip/v1`.
- **Video model:** MiniMax H3, registry provider `minimax-h3-async`, transport `minimax-h3-async.video.v1`, endpoint host `https://metaso.cn/api/minimax`.
- **Real paid provider call:** **not run**. The required `MINIMAX_H3_GRAY_REAL`, `MINIMAX_H3_GRAY_CONFIRM`, and exact shot whitelist were absent, so the existing gray gate was preserved.
- **Mocked canary:** passed with a deterministic transport fixture; no network request was made.

## Delivered

- Added `MinimaxH3VideoProvider` in `core/video_provider_adapter.py`. It consumes an already resolved Model Registry profile, validates the MiniMax H3 capability/provider/model/endpoint contract, calls the existing async generation adapter, and returns a normalized `VideoProviderResult`.
- `execute_video_generation()` now accepts `model_profile_id`, resolves real video profiles through `api.model_registry`, records `VIDEO_PROVIDER_CANARY`, profile fingerprint, adapter/version, request/task IDs, response hash, and secret-free request/response projections.
- First frame URL is resolved from the current Keyframe Asset binding and Production Asset Version. Motion profile is carried from the Video Generation Intent into the provider request projection.
- First and last frame URLs are carried as authoritative `first_frame` / `last_frame` payload parts when present. Real provider execution also requires a valid current Shot Direction; its fingerprint and profiles are recorded in the request projection, and the provider motion profile is derived from that direction.
- The adapter retains no Model Registry profile, endpoint, model name, or API key. Each call receives and validates a short-lived runtime Model Registry profile; the credential is used only for that transport call and is absent from snapshots.
- Added `GET /video-generation/{intent_id}` for read-only intent, execution, candidate, validation, and promotion status.
- The existing lineage remains intact: `GenerationExecutionRecord` → `MediaCandidateRecord` → `MediaValidationRecord` → pending `MediaPromotionRecord`; OfficialMedia is created only after the existing review approval gate.

## Verification

- `pytest -q tests/test_minimax_h3_video_provider_canary.py` — **10 passed**.
- `pytest -q` — **1880 passed, 0 failed**.
- `npm run test:golden` — **5/5 passed**.
- `python -m scripts.verify_migration_chain` — **PASS**, migration head `f7a8b9c0d1e2`.
- `git diff --check` — **PASS**.

## Truth boundary

The Provider Response evidence in this phase is a mocked fixture, not a real MiniMax response. No production API key is included in execution snapshots, reports, or committed artifacts; tests use only an explicit dummy credential. A real single-shot canary can be executed only after the explicit gray-gate variables and exact whitelist are supplied.
