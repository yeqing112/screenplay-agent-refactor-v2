# Canonical Canary Target Selection V1

Status: `CANONICAL_CANARY_TARGET_AMBIGUOUS`  
Run: `20261005T070217Z`

Identity boundary status: `BENCHMARK_PRODUCTION_IDENTITY_SEPARATED`

## Identity boundary

- Benchmark fixtures: `SH_E01_SC002_002, SH_E01_SC002_006, SH_E01_SC002_007`.
- `production_canonical_identity`: `false` for all benchmark fixtures.
- `historical_media_authority`: `false` for all benchmark fixtures.
- Benchmark boundary audit: `PASS`; all three attempts return `BENCHMARK_IDENTITY_NOT_PRODUCTION_CANONICAL`.
- Historical documents remain retained as forensic / regression evidence. They are forbidden as production shot authority, production media authority, or official media lineage sources.

## Current canonical inventory

- ShotPlanPointer rows scanned: `20` materialized shot projections.
- Hard-gate pass: `12`; hard-gate blocked: `8`.
- Complete chain required: current Script → production-qualified ScriptIR → current Treatment → current SceneBlocking → current ShotPlan → current materialization → StoryboardShot → production asset authority → current IMAGE/VIDEO PromptIR.
- Blocker counts: `PROMPT_IR_VIDEO_NOT_CURRENT`=8.

## Deterministic selection

- Selected target: none.
- Ranking is deterministic: score descending, then book, episode, exact `plan_shot_id`, storyboard id.
- Selection rule: a score tie is rejected as `CANONICAL_CANARY_TARGET_AMBIGUOUS`; no candidate is auto-promoted.

## Runtime safety

- IMAGE profile: `75api-image` / `gpt-image-2-1k`.
- VIDEO profile: `75api-minimax-h3` / `minimax_h3`.
- Real IMAGE calls: `0`.
- Real VIDEO calls: `0`.
- External LLM calls: `0`.
- SHAPI/Poyo calls: `0`.
- Production database/media writes: `0`.

The phase stops at target selection. No provider request, prompt compilation mutation, materialization mutation, media generation, or authority promotion was executed.
