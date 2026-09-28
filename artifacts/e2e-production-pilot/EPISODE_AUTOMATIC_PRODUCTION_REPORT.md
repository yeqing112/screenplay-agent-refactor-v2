# Episode Automatic Production Orchestration Report

Status: **EPISODE_AUTOMATIC_PRODUCTION_COMPLETE**

This phase adds a resumable Episode coordinator over the existing rendering, keyframe, image, video, execution, candidate, review, promotion, and official media runtimes. It does not add a second queue, worker, task system, review system, or asset manager. Episode completion means every required Shot has a current, human approved `SHOT_PRIMARY_VIDEO`; it does not mean timeline assembly or a final combined MP4.

## Implementation

- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Remote HEAD at audit start: `48bd16f4c411d49f421e367518ac0213afd64d04`
- Implementation Commit: `fa03f10`
- Report Commit: `db62d49` (report artifact commit; final metadata fix follows)
- Migration Head: `m4h5i6j7k8l9` (no new migration)
- APIs: `POST /episodes/{id}/production/run`, `GET /episodes/{id}/production-status`
- Resume: repeated `run` re-resolves live authorities and acts as resume

## Vertical slice

The deterministic fixture covers one Episode and three Shots:

`Shot 1 → Shot 2 → Shot 3`, with Shot 2 depending on Shot 1 and Shot 3 depending on Shot 2.

- Keyframe plans created: 3
- Keyframe image executions: 6 (START/END for each Shot)
- Video executions: 3
- Review pauses: 12
- Resume count: 12
- Official current Shot videos: 3
- Duplicate executions/candidates/assets: 0 / 0 / 0
- Stale blocks: 0 in the happy path; stale projection and promotion blocking remain covered by existing media currentness regressions
- Retry result: missing VIDEO PromptIR is reported as `NOT_READY` and does not become a provider failure; the next run resumes after the VIDEO authority is installed
- Dry run: PASS, zero production writes

The full run history is in [EPISODE_AUTOMATIC_PRODUCTION_VERTICAL_SLICE.json](EPISODE_AUTOMATIC_PRODUCTION_VERTICAL_SLICE.json). The constraint audit is in [EPISODE_AUTOMATIC_PRODUCTION_TRUTH_AUDIT.json](EPISODE_AUTOMATIC_PRODUCTION_TRUTH_AUDIT.json).

## Safety and lineage

- Human approval remains required for keyframe plans, START/END image candidates, and video candidates.
- Source materialization, ShotDirection, keyframe, PromptIR, execution, candidate, validation, promotion, and OfficialMedia lineage is re-resolved on each run.
- Source revisions fail closed as `STALE`; historical candidates and OfficialMedia versions are retained.
- Real LLM, SHAPI image, and MiniMax H3 calls: **0 / 0 / 0**.
- No ScriptIR or source fact mutation.
- No timeline, audio, subtitle, publishing, or final MP4 assembly.

## Verification

- Episode-focused regression: **89 passed**
- Full regression: **1933 passed**
- Golden regression: **5/5**
- Migration CI (fresh, repeat, legacy, drift): **PASS**
- `python -m compileall -q core api models scripts tests`: **PASS**
- `git diff --check`: **PASS**
- Working tree: clean after the report commit
