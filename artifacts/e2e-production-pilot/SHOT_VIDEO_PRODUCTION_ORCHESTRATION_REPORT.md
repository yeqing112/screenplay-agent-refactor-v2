# Shot Video Production Orchestration Report

## Phase

`PHASE_SHOT_VIDEO_PRODUCTION_ORCHESTRATION` — `SHOT_VIDEO_PRODUCTION_ORCHESTRATION_COMPLETE`

- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Remote: [screenplay-agent-refactor-v2](https://github.com/yeqing112/screenplay-agent-refactor-v2)
- Implementation commit: `95750d9`
- Report commit: `abef362`
- Migration head: `m4h5i6j7k8l9`
- Runtime guard follow-up commit: `921b5132108001fb0083526345b74fe6ed7baa2b`
- Remote HEAD verified before report commit: `921b5132108001fb0083526345b74fe6ed7baa2b`
- Working tree state before report commit: clean

## Delivered

- Added a thin shot-scoped orchestration boundary over the existing `VideoGenerationIntent`, `GenerationExecutionRecord`, `TaskRun`, `MediaCandidateRecord`, validation, review, and OfficialMedia authorities.
- Requires current materialization, ShotDirection, compiled AutomaticKeyframePlan, VIDEO PromptIR, and approved Official START/END keyframe assets.
- Stabilized source fingerprints by resolving the same Model Registry profile used by execution; the default mock path now fingerprints `builtin-mock-video` consistently.
- Carries an explicit OfficialMedia image-to-video source binding for keyframe roles and revalidates it before technical validation and promotion.
- Preserves candidate history on stale source changes and blocks publication until a current source is reconciled.
- API: `POST /shots/{id}/video-production`, `GET /shots/{id}/video-production`, `POST /shots/{id}/video-production/reconcile`.

## Vertical slice evidence

The deterministic fixture completed:

`Official START/END Keyframes → VideoGenerationIntent → GenerationExecution/TaskRun → existing provider adapter boundary → VIDEO MediaCandidate → technical validation → REVIEW_REQUIRED → human APPROVE → OfficialMediaVersion/Pointer`.

Counts: 1 VideoGenerationIntent, 1 GenerationExecution, 1 VIDEO candidate, 1 validated candidate, 1 approved video, 1 OfficialMediaVersion, and 1 `SHOT_PRIMARY_VIDEO` pointer. Real MiniMax H3 calls: `0`; real image calls: `0`.

## Verification

| Check | Result |
|---|---:|
| Shot video production tests | 4 passed |
| Focused runtime regression | 30 passed |
| Full regression | 1929 passed |
| Golden fixtures | 5/5 |
| Migration CI | PASS: fresh/repeat/legacy/drift; head `m4h5i6j7k8l9` |
| Compileall | PASS |
| `git diff --check` | PASS |
| Idempotency | PASS; same source reuses intent/execution |
| Stale promotion guard | PASS; stale candidate retained, promotion blocked |
| Atomic promotion | PASS |
| Episode runtime compatibility | PASS |

## Guardrails

- Existing MiniMax H3 async adapter and generation execution runtime are reused; no second video system, provider manager, asset manager, or review workflow was created.
- Source Fact and ScriptIR mutations: `0`.
- Human approval remains mandatory before OfficialMedia publication.
- Image generation remains configured for SHAPI at [https://www.shapi.vip/](https://www.shapi.vip/); this phase made no external image request.
- Default real MiniMax H3 calls remain `0`.

## MiniMax H3 gray gate

- `MINIMAX_H3_GRAY_REAL`: unset (`real calls blocked`)
- `MINIMAX_H3_GRAY_CONFIRM`: unset (`submission confirmation absent`)
- `MINIMAX_H3_GRAY_WHITELIST`: unset (`no shot whitelist supplied`)

See the machine-readable [Truth Audit](SHOT_VIDEO_PRODUCTION_ORCHESTRATION_TRUTH_AUDIT.json) and [Vertical Slice](SHOT_VIDEO_PRODUCTION_ORCHESTRATION_VERTICAL_SLICE.json).
