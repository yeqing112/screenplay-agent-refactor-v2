# Phase E PromptIR semantic compilation and model adapter gap audit

## Scope

Phase E closes the production boundary from the current
`StoryboardProductionSnapshot` to structured PromptIR v2 and provider-neutral
model generation payloads. The compiler is deterministic, provider-free, and
never treats legacy `visual_prompt_static`, `visual_prompt_motion`, or
`visual_prompt_final` as semantic authority.

## Authority and readiness audit

| Boundary | Result | Evidence |
| --- | --- | --- |
| Current Storyboard authority | PASS | Current materialization pointer/set/rows are resolved before compile; stale materialization invalidates downstream PromptIR |
| PromptIR activation | PASS | 15 versions, 15 authorities, and 15 pointers activated atomically for 15 current shots |
| Compiler handoff | PASS | Structured prompt compiler handoff, visual semantic handoff, and immutable projection payload are carried by the snapshot |
| Legacy prompt bypass | PASS | Legacy visual prompt columns are not read by Phase E semantic compilation or adapter projection |
| Semantic qualification | PASS | `prompt_ir_semantic_ready` is true for all 15 resolver-positive rows |
| Model readiness separation | PASS | Adapter readiness remains false with `PROVIDER_CONFIG_MISSING`; no provider call is attempted |
| Asset authority | PASS | Current scene and `prop:TICKET` bindings resolve through explicit Visual Asset Authority pointers |
| Current-only rule | PASS | Resolver rejects stale/tampered pointers and does not use newest/max historical rows |
| Adapter projection | PASS | 15 `image_generic_adapter_v1` payloads preserve structured sections and add no cinematic, lens, lighting, quality, or other unauthorized facts |
| Atomic failure behavior | PASS | Required-asset failure returned without changing counts or pointer hashes |
| Idempotency | PASS | Repeated identical compile reused current payloads with unchanged counts |
| Stale propagation | PASS | Storyboard stale marked 8 PromptIR rows stale; Visual Asset stale marked 8 PromptIR rows stale |
| Tamper validation | PASS | Pointer, authority envelope, and payload tamper cases each failed closed with HTTP 409 |
| Provider activity | PASS | Provider, LLM, image, and video calls were all zero |

## Persisted pilot evidence

- `episode_01_phase_e_trace.json` is the real temporary SQLite/Alembic trace.
- `episode_01_prompt_ir_phase_e.json` contains 15 persisted PromptIR payloads.
- `episode_01_generation_payload_phase_e.json` contains 15 persisted adapter previews.
- `episode_01_prompt_ir_phase_e.md` lists each current `plan_shot_id` and its structured semantic fields.

## Semantic fields carried

PromptIR v2 preserves subjects, props, information references, reaction
contracts, coverage roles, camera framing/orientation/support and movement
trigger/target/end condition, temporal intent, visibility, axis, spatial
references, and explicit asset bindings. The adapter serializes those sections
without inventing visual style or cinematography facts.

## Verification

- Phase E semantic closure: 15 passed.
- Combined Phase E/Authority/Visual Asset/Phase D regression: 48 passed.
- Deterministic Golden regression: 5/5 passed.
- Full suite baseline: 1624 passed, with the four pre-existing failures listed in `PHASE_E_FINAL_REPORT.md`.
- No migration was added.
