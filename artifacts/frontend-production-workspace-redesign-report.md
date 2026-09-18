# Frontend Production Workspace Redesign Report

## Status

The first production-workspace slice is implemented on top of the existing
`ProductWorkspace` shell. It is an information-architecture and state-contract
upgrade, not a parallel application.

## Completed in this slice

1. Completed the source audit in `frontend-production-workspace-audit.json`.
2. Added a read-only backend projection at
   `GET /api/books/{book_id}/production-workspace`.
3. Added strict frontend domain types and a single fetch service/hook.
4. Added the Production Spine to the Dashboard.
5. Added authority-aware status/blocker banners to Shot Workspace and Asset
   Center.
6. Added authority blockers to Task Center as Workflow Actions while keeping
   runtime/recovery tasks separate.
7. Added human-readable state mapping and preserved legacy/creative-draft
   compatibility.
8. Added backend projection tests and frontend contract tests.

## Deliberate non-goals

- No new authority tables or cached frontend truth.
- No provider, LLM, image, video, embedding, or object-storage calls.
- No deletion of legacy sections, Canvas, Model Registry, or mature modals.
- No GitHub Actions or remote CI work.
- No 3D blocking editor.

## Verification

- Frontend dependencies restored with `npm ci`.
- Frontend tests: 50 files / 295 tests passed.
- Frontend build: passed.
- Projection + production readiness + production storyboard gate: 14 tests passed.
- Projection endpoint is read-only and reports `provider_calls=0`.
- Browser visual regression completed against the current local build using the
  Codex in-app browser. Accepted evidence is under
  `artifacts/frontend-production-workspace-screenshots/`:
  - `07-dashboard-mobile-fixed-390x844.png`: mobile dashboard after the
    responsive fix; the desktop sidebar is replaced by an accessible page
    selector and the content is no longer clipped.
  - `08-dashboard-final-1440x900.png`: desktop dashboard; Production Spine,
    current blocker state, and next action are visible in the first viewport.
  - `09-content-preparation-final-1440x900.png`: content preparation entry
    point with long-form and short-form import paths and current skill/model
    context.
  - `10-task-center-final-1440x900.png`: task center showing workflow actions,
    runtime task separation, upstream blocking, and the next-action CTA.
  - `11-dashboard-final-1024x800.png`: tablet/compact desktop width; the
    sidebar remains usable and the production spine stays within the viewport.
  - `12-dashboard-final-1920x1080.png`: wide desktop; the content column remains
    readable without layout overflow while preserving the existing dark shell.
  - Pre-fix captures from the same run are retained as rejected diagnostic
    evidence and are not used for acceptance.
- Browser interaction check: the Task Center `立即继续` action navigated to
  `内容准备`; locked downstream sections remained visibly disabled in the
  empty-project state. Shot Workspace and Asset Center therefore have a named
  blocker rather than a false empty production screen in this fixture.
- Golden regression: 5/5 deterministic fixtures passed via
  `python scripts/run-golden-regression.py`.
- Full backend suite: 1,534 passed / 5 failed in the direct run. The five
  failures are historical director-quality/fact-coverage expectations already
  present on this branch; no projection or frontend-workspace test failed.
- Production release gate ran fail-closed and remained blocked by the existing
  empty/retired sample registry (active book 990400 absent), zero active shots
  for the shot-planning gate, missing audit samples, the same historical
  deterministic failures, and an unavailable optional Playwright dependency.
  It produced a fresh gate report, but no provider or media call was made.

## Scope and limits

- The current local fixture is an empty project (`深夜便利店`, 0 chapters,
  0 shots, 0 assets). It is sufficient to verify fail-closed navigation and
  authority projection, but it cannot prove populated Shot Workspace or Asset
  Center rendering without creating business data.
- Visual acceptance is screenshot-based and does not claim full accessibility
  compliance; keyboard/screen-reader behavior beyond the observed ARIA tree
  still needs a dedicated accessibility pass.
- No real LLM, MiMo, image, video, embedding, object-storage, or external
  provider call was made in this slice.

## Readiness conclusion

`FRONTEND_PRODUCTION_WORKSPACE_REDESIGN_READY` for the read-only,
authority-driven workspace slice. The release gate for the overall product
remains separately blocked by the pre-existing sample-data and historical
quality-gate conditions listed above.
