# Video Model Compiler Architecture Foundation

## Status

`VIDEO_MODEL_COMPILER_FOUNDATION_READY` (Gate A, zero-call)

## Boundaries

`DirectorDecisionIR` remains immutable. `VideoIntentIR` is the model-independent semantic contract: scene topology, character starting states, authorized props, time-coded performance and camera beats, dialogue authority, audio intent, references, and negative constraints. A model compiler translates that contract into a deterministic `CompiledVideoRequestIR`. A provider adapter translates the compiled request into a 75api payload and owns HTTP submission, retry, polling, reconciliation, credentials, and API model naming.

The runtime is `DirectorDecisionIR → VideoIntentIR → CompilerRegistry → ModelCompiler → CompiledVideoRequestIR → ProviderAdapter → GenerationExecution`. Existing `VideoProviderPromptIR` remains a compatibility bridge and delegates prompt text to the compiler.

## H3 V1 contract

The MiniMax H3 compiler uses the integrated multimodal description structure, first-frame/reference mode, stable `S1`, `S2` speaker allocation, timed natural-language performance and camera timelines, and explicit audio sections. `AUTHORITATIVE` dialogue keeps the exact text and language label. `NONE` dialogue contains no dialogue markup, no positive speaking-mouth language, and requests a closed relaxed stable mouth state. The H3 target is 5–15 seconds and 16:9.

75api H3 accepts `minimax_h3` and the backward-compatible `minimax_h3_no_audios`; the production default is `minimax_h3`. The adapter receives the compiled prompt and applies the configured API model name. No compiler silently changes a model or capability.

## Lifecycle and future models

The registry resolves an explicit `video_compiler_id` and `model_family`; missing bindings fail closed. Duration remains in the shared shot readiness projection. A future Kling, Veo, or Seedance compiler implements the same protocol with its own capability declaration and prompt grammar; DirectorDecisionIR, VideoIntentIR, and the provider-neutral lifecycle remain unchanged.

## Verification

Golden fixtures cover NONE dialogue, authoritative dialogue, SC002_002 prop exclusion, SC002_006 APPLE continuity, capability gates, stable fingerprints, and credential-free compiled output. Gate A produced no real IMAGE or VIDEO calls.
