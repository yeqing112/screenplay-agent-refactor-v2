# PromptIR Authority Activation Report

Stage: `PROMPT_IR_AUTHORITY_CONTRACT`
Provider policy: **0 external calls**
Branch: `codex/shot-plan-authority-contract`

## Baseline Audit

The legacy PromptIR path used a `ShotIR` dataclass whose defaults could turn
missing production facts into `duration=3`, `MS`, `static`, `slow`, `cut`,
`emotion`, `default` style and default retention. `compile_phase_a()` accepted
loose context assembled from StoryboardShot/scene-name data, while Model Adapter
serialization could fall back to `authority_prompt_raw` and state that assets
should follow reference images even when no authoritative reference existed.
Prompt text and compiler state were persisted on StoryboardShot; no current
PromptIR version/pointer separated authority from serialization.

## Final As-Built Verification

- Production PromptIR accepts only `storyboard_prompt_handoff_v1` from the
  current StoryboardMaterialization pointer. The legacy direct prompt compile
  endpoints now fail closed for `workflow_profile=production`.
- `PromptIRVersion`, `PromptIRAuthority` and `PromptIRPointer` are versioned
  persistence artifacts. Recompilation stales the previous version; model
  adapter preview requires the current qualified pointer.
- `prompt_ir_authority_v1` separates storyboard constraints, visual asset
  constraints, compiler policy, adapter policy, media-pending requirements and
  invalid/unknown inputs.
- Camera, duration, action beats, continuity, beat identity, materialization
  identity and ShotPlan fingerprints are immutable handoff facts. Missing
  production facts fail closed; no compiler default can hide them.
- Transition fallback is explicitly recorded as `COMPILER_POLICY_DEFAULT` with
  policy version. Retention is explicitly `COMPILER_POLICY`, never Story Fact.
- Asset bindings distinguish canonical identity, asset revision, authority
  status, variant scope, reference status/token, structured visual facts and
  media readiness. `authority_prompt_raw` is advisory/legacy only and cannot
  create hard visual constraints.
- Identity-only or reference-pending assets produce `ASSET_REFERENCE_PENDING`
  and `MODEL_GENERATION_READY=false`; no hairstyle, costume, face or reference
  claim is invented. Fully authoritative locked references can pass the model
  readiness structure gate.
- PromptIR payload hash excludes derived natural-language serialization.
  Static/motion/negative prompt changes cannot mutate PromptIR authority.
- Deterministic adapters are versioned for Kling, Seedance, Veo, Jimeng,
  Flux and SD. They return `AdapterOutput` with authority projection and
  fingerprint, and cannot alter camera, duration, action, identity,
  continuity or asset bindings. Missing adapter inputs are diagnostics only.
- `MODEL_GENERATION_READY` remains independent from `PROMPT_IR_QUALIFIED`.
  No media request or provider execution is created in this stage.

## Verification

- PromptIR authority/adapter suite: **13 passed**.
- Materializer + production gate regression: **24 passed**.
- Existing Model Adapter / legacy Prompt Compiler / storyboard generation
  regression: **18 passed**.
- Full backend baseline from the previous stage: **1515 passed, 5 known
  historical baseline failures**; no new PromptIR-related failure is accepted.
- Golden regression: **5/5**.
- Frontend: `FRONTEND_NOT_TOUCHED`; no frontend contract was added in this
  provider-free stage.
- Fresh DB blocker `f05ab1af29bc` remains intentionally unchanged and is
  tracked for `MIGRATION_CHAIN_HARDENING`.

## Scope Boundary

No real MiMo/LLM call, image/video generation, embedding, object storage,
visual asset authoring, provider canary or media request execution was done.

Completion marker: `PROMPT_IR_AUTHORITY_CONTRACT_READY`
