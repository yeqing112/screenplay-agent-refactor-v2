# PRODUCTION UI V3 Browser User Journey Mock Vertical Slice Report

## Phase

`PHASE_PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_VERTICAL_SLICE`

## Result

`PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_VERTICAL_SLICE_COMPLETE`

The ordinary-user journey passed twice consecutively from project list through UI creation, content entry, Production Skill and adaptation locking, script generation/release, production ScriptIR preparation, Director Treatment, Scene Blocking, ShotPlan, V3 Storyboard Materialization, Production Asset authority, PromptIR, IMAGE and VIDEO candidate review/Official, QA, Delivery export, return to project list, and UI deletion.

## Verification

- Primary viewport: 1440x900.
- Responsive smoke: 1280x900 and 1920x1080 on both runs.
- Reload checks: project creation, production preparation, and video running state.
- localStorage compatibility state was cleared after adaptation lock; the server-backed lock remained.
- Browser mutations: visible UI only; no database seed, route mocking, fixture, or Legacy query bypass.
- External hosts: 0. Real LLM/Image/Video/SHAPI/MiniMax calls: 0.
- Mock ledger snapshot: LLM 661, IMAGE 33, VIDEO 21.
- Canonical mock-provider gate: `APP_ENV=production` rejects IMAGE/VIDEO mock execution with `MOCK_RUNTIME_DISABLED_IN_PRODUCTION`; test runtime allows the deterministic adapters.
- Protected Book 990400 writes: 0. Book 998755 was not restored.
- Delete response: HTTP 200, orphan_rows=0, ambiguous_rows=0 on both runs.
- Console errors and HTTP errors: 0 on both final runs.

## Checks

- Web: 63 files / 445 tests passed.
- Backend relevant contract suite: 85 passed.
- Canonical generation / mock-runtime gate tests: 60 passed.
- Frontend build: passed.
- Python compileall: passed.
- Alembic head: p1q2r3s4t5u6.
- git diff --check: passed.

## Evidence

- Browser evidence: output/playwright/user-journey-final30/
- Truth audit: PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_VERTICAL_SLICE_TRUTH_AUDIT.json
- Browser QA: PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_BROWSER_QA.json
- Network audit: PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_NETWORK_AUDIT.json
- UX friction: PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_UX_FRICTION.json

## Recommended next phase

PHASE_PRODUCTION_UI_V3_REAL_PROVIDER_STAGING_VERTICAL_SLICE

## Commit

65f8ea32713788d5458704aa073cc61b5cd77d65
