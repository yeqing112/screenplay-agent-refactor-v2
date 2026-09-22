# Phase J1 Model Management / Real Provider Readiness Audit

## Audit decision

```text
PHASE_J1_PARALLEL_PROVIDER_PATH_DETECTED
```

The audit is terminated at the architecture boundary. The repository contains a Model Registry and real image/video adapters, but the production storyboard routes do not use the Phase F canonical `PromptIR → GenerationPayload → ProviderExecutionProfile → GenerationExecutionRecord → MediaCandidateRecord` path. Adding an adapter shim would hide the split rather than close it.

Related required follow-up states:

```text
PHASE_J1_MODEL_MANAGEMENT_PRODUCTION_INTEGRATION_REQUIRED
PHASE_J1_PRODUCTION_MODEL_SELECTION_CONTRACT_REQUIRED
```

## Scope and safety boundary

- Source branch: `codex/visual-authoring-provider-canary-reconcile`
- Audited repository HEAD: `4754f5d91f1a771b424e722ea5f848918461daf9`
- Implementation snapshot before this report commit: `f59605d`
- Worktree status at audit start: clean; branch matched its remote tracking branch.
- This phase is architecture and runtime-readiness audit only.
- No LLM, image, video, storage, or Provider API was called.
- No business logic, Provider contract, authorization gate, test, fixture, or Production Authority record was changed.
- Secret values were not read into the report or committed.

## Auditable interface commit lineage

The audited model interfaces are present on the auditable branch. Their relevant ancestor commits are:

| Commit | Contribution |
|---|---|
| `1e2367d` | Initial Model Registry/API and image/video profile surface. |
| `880c701` | MiniMax H3 async video adapter and registry alignment. |
| `b1678da` | MiniMax H3 adapter/provider contract alignment. |
| `ed32775` | Media model default strategy in the management UI. |
| `9745519` | Phase F GenerationExecution provider canary. |
| `0600e3a` | ProviderExecutionProfile boundary, fingerprinting, and replay closure. |

No model interface was found only in an uncommitted worktree; the audit therefore continues with the parallel-path result.

## Model management implementation inventory

| Concept / path | Responsibility | Production authority boundary |
|---|---|---|
| `web/src/services/modelRegistry.ts:1-108` | Typed UI client for registry read, defaults, save, and connectivity-test endpoints. | Management/configuration surface; it does not create generation records. |
| `web/src/components/ModelRegistryModal.tsx:16-90,374-520,690-1685` | Profile editing, capability/provider options, default parameters, and test action. | UI parameter guidance only; it is not PromptIR or media authority. |
| `web/src/components/poyoModelCatalog.ts:1-46` | Suggestions and family helpers for PoYo model names. | Heuristic UI suggestions; not a production capability authority. |
| `api/server.py:3281-3312` | HTTP routes for registry read, defaults, save, and test. | API façade for model management; connectivity test is separate from execution. |
| `api/model_registry.py:1-620` | Profile schema validation, persistence, default resolution, and connectivity probes. | Registry/Profile source; currently accepts raw `api_key` and has no runtime resolver contract. |
| `api/generation_adapters.py:48-1716` | Resolves profiles and maps image/video requests to provider transports. | Adapter implementation; production storyboard calls it through a legacy branch. |
| `core/provider_execution_profile.py:183-233` | Typed, secret-free Phase F projection and fingerprint. | Canonical execution projection; credential reference/resolution is incomplete. |
| `api/generation_canary_api.py:251-798` | Current PromptIR → payload → execution/candidate canary for IMAGE. | Canonical Phase F production boundary, but not yet the storyboard production route. |
| `models/generation_execution.py:1-110` | Durable `GenerationExecutionRecord` and `MediaCandidateRecord` fields. | Evidence lineage for canonical execution/candidate results. |

### Structured capability contract

The existing equivalent capability contract is the structured registry field `capability ∈ {llm, embedding, image, video}`. It is not inferred from a model name, endpoint, or provider string. Provider-specific model-name helpers in the UI only suggest parameters; they do not define Production capability.

| Capability | Model identity | Profile/provider identity | Structured inputs/parameters | Output type | Credential | Adapter identity |
|---|---|---|---|---|---|---|
| Image | `model_name` in `ModelProfile` | `model_profile_id`, `provider`, `base_url` | `default_params`, reference-image/negative-prompt flags, aspect ratio | image asset / `MediaCandidateRecord` in canonical path | `key_configured` plus raw registry key today; canonical runtime reference missing | `MODEL_ADAPTER_REGISTRY` for Phase F; provider dispatch in `generate_image_asset()` |
| Video | `model_name` in `ModelProfile` | `model_profile_id`, `provider`, `base_url` | `default_params`, text/image/reference task modes, first frame, duration, aspect ratio | video asset / intended `MediaCandidateRecord` | same unresolved credential boundary | provider dispatch in `generate_video_asset()`; no canonical Phase F video route |

The video task modes and inputs are read from structured request/profile fields (`task_modes`, `supports_reference_images`, first-frame/reference payloads, duration, and aspect ratio). The audit does not infer them from model names or URLs.

## Evidence reviewed

| Area | Evidence | Finding |
|---|---|---|
| Registry surface | `api/model_registry.py:279-317,393-415`; `web/src/services/modelRegistry.ts`; `web/src/components/ModelRegistryModal.tsx` | Profiles expose `llm`, `embedding`, `image`, and `video`; defaults are a capability map. |
| Registry state | Read-only registry inspection | 9 profiles; 7 non-mock; 6 non-mock profiles declare `key_configured`; default image is `local-image-mw4y52 / shapi-openai-images / gpt-image-2.5-flare`; default video is `local-video-7deneh / minimax-h3-async / MiniMax-H3`. |
| Credential contract | `api/model_registry.py:133-151,393-415`; `core/provider_execution_profile.py:183-233` | Registry accepts and persists `api_key`; the canonical projection retains only `credential.configured` and `credential.source_identity`. No runtime secret resolver or validation result is part of the canonical contract. |
| Connectivity test | `api/model_registry.py:469-620` | `/models` or structural checks can prove reachability/catalog shape, but do not create `GenerationExecutionRecord`, `MediaCandidateRecord`, or `OfficialMedia`. This is a connectivity test, not production execution. |
| Canonical Phase F path | `api/generation_canary_api.py:251-285,565-798` | Re-resolves current PromptIR and persists execution before a provider call; first canary is explicitly IMAGE-only and produces a media candidate. |
| Production storyboard path | `api/server.py:19114-19430`; `api/server.py:13554-13767` | `generate-frame` and `generate-video` read `visual_prompt_static` / `visual_prompt_motion`, resolve a profile, invoke adapters, and save assets directly to storyboard links. They do not create the canonical execution/candidate records. |
| Adapters | `api/generation_adapters.py:1533-1716` | Image adapters exist for PoYo, SHAPI, and OpenAI-compatible providers. Video adapters exist for PoYo, MiniMax H3 async, and 75api; OpenAI-compatible video explicitly remains unsupported. |

## Model management findings

### 1. Capability metadata is present, but production selection is not a policy binding

The registry has capability labels and a default profile map. Production requests may omit `model_profile_id`; `resolve_generation_profile()` then falls back to `get_default_profile(capability)`. That fallback is an implementation convenience, not an explicit Episode/Shot `Production GenerationPolicy` binding. Therefore `production_model_selected=false` in the readiness matrix even though a registry default exists.

The UI also contains model-name family helpers for PoYo parameter suggestions. The reviewed evidence places these in UI parameter guidance, not in the authoritative production capability contract. They remain a boundary risk until capability and task-mode support are resolved from the registry contract.

### 2. Credential declaration is not runtime credential resolution

`key_configured=true` is derived from registry metadata. The current save/load path accepts an `api_key` and stores it in the model-registry KV payload; adapters read `profile["api_key"]` directly. The Phase F canonical profile deliberately excludes key material and keeps only a configured flag plus source identity. There is no canonical resolver reference, runtime injection result, or credential validation evidence.

The resulting state is:

```text
registry declaration       = present for configured profiles
credential reference       = absent
runtime resolver           = absent
credential validated       = false
```

This is both a readiness gap and a secret-storage risk. It is recorded for follow-up only; this audit does not alter the credential contract.

### 3. Connectivity test is correctly separate from production execution

The model test endpoint may call a provider catalog endpoint for supported profiles, or perform local structural checks for some providers. It does not write a production execution, candidate, validation, promotion, or official media record. A successful connectivity test therefore cannot be used as evidence that a production generation path is ready.

## Parallel provider paths

### Canonical Phase F canary

```text
current PromptIR authority
  → GenerationPayload
  → ProviderExecutionProfile
  → GenerationExecutionRecord
  → image adapter
  → MediaCandidateRecord
```

The route is `/api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation-canary/{preview|execute}`. `_resolve_execution_inputs()` rejects non-image policies with `GENERATION_CANARY_IMAGE_REQUIRED`; no equivalent canonical video GenerationExecution route was found.

### Production storyboard routes

```text
generate-frame / generate-video
  → storyboard visual_prompt_static / visual_prompt_motion
  → resolve_generation_profile (explicit id or capability default)
  → image/video adapter
  → _save_asset_to_storyboard
```

This path bypasses current PromptIR resolution, `GenerationPayload`, `GenerationExecutionRecord`, and `MediaCandidateRecord`. It is therefore an independent provider path with separate persistence semantics. The same split exists for both image and video, while video additionally lacks a canonical Phase F execution route.

## Actual UI/API and Production topology

```text
UI Model Management
  web/src/components/ModelRegistryModal.tsx
    → web/src/services/modelRegistry.ts
    → api/server.py:/api/model-registry[GET|PUT|POST /test]
    → api/model_registry.py
    → ModelProfile / default map / connectivity probe
    → api/generation_adapters.py provider dispatch
    → external Provider (only when a management test or legacy generation task is explicitly run)

Production Generation
  storyboard request in api/server.py
    → _queue_storyboard_generation_task()
    → _resolve_creative_profile() / resolve_generation_profile()
    → _run_creative_task()
    → generate_image_asset() or generate_video_asset()
    → _save_asset_to_storyboard()

Canonical Phase F Generation
  current PromptIR authority
    → GenerationPolicy / GenerationPayload
    → ProviderExecutionProfile + fingerprint
    → GenerationExecutionRecord
    → registered image adapter
    → MediaCandidateRecord
```

The management and canonical paths share profile/adapter primitives, but the production storyboard path does not traverse the canonical execution records. The first point at which the two production branches could be said to meet is provider adapter code; that is too late to establish one Production Generation Truth.

## Currentness and exact model identity

The canonical canary stores `model_profile_id`, `model_profile_fingerprint`, `provider_adapter_id`, and adapter version in the execution and candidate lineage (`api/generation_canary_api.py:299-306,588-607,770-778`). It re-resolves current inputs before execution and rejects stale fingerprints.

The storyboard task snapshots a `model_profile_id` and provider in task state, but it does not persist the canonical ProviderExecutionProfile fingerprint or a GenerationExecution record before adapter invocation. A registry/default change can therefore affect a later legacy task resolution without the canonical currentness proof required by Phase J.

## GenerationPayload ownership

The canonical path keeps PromptIR and asset/reference authority upstream of `GenerationPayload`. Model Management supplies model identity, capability, transport parameters, enablement, and credential configuration only. The reviewed Model Registry code does not generate prompts, add character/style text, rewrite negative prompts, or mutate PromptIR. The storyboard branch is nevertheless a separate consumer of already stored storyboard prompts, which is the integration boundary to close.

## Structured integration plan (audit only)

No implementation is performed in Phase J1. The required plan is:

1. **Selection authority:** define an Episode/Shot Production `GenerationPolicy` that stores an explicit image and video `model_profile_id` (or an equivalent typed selection reference), with no implicit first/enabled/default fallback for production execution.
2. **Canonical convergence:** route storyboard image and video requests through current PromptIR, Asset/Reference Authority, `GenerationPayload`, and a media-typed canonical execution service. Extend the existing Phase F schema for video instead of creating a Phase J provider path.
3. **Credential boundary:** replace raw-key dependence at the canonical boundary with a secret-safe credential reference, runtime resolver, and validation result. Keep key material out of canonical JSON, fingerprints, persisted payloads, logs, artifacts, and plaintext database storage.
4. **Currentness:** freeze selected model identity, ProviderExecutionProfile, adapter identity/version, and fingerprints in `GenerationExecutionRecord`; reject execution when current policy/profile differs.
5. **Separate readiness gates:** evaluate image and video independently, then require both human authorization and the selected capability's validated runtime credential before any real call.

Acceptance evidence for that future phase must show one production path, distinct image/video readiness, zero implicit fallback, and candidate lineage before any OfficialMedia promotion.

## Proposed Phase J gate

For each media capability, the production gate should be:

```text
human_authorized
AND production_model_selected
AND model_profile_current
AND provider_profile_valid
AND credential_resolved
AND credential_validated
AND adapter_available
```

`FULL_REAL_END_TO_END_PRODUCTION_ACCEPTANCE_COMPLETE=false` remains in force for this audit.

## Readiness conclusion

The registry and adapters are discoverable, but the system is not production-ready for real Provider execution under the requested contract. The architecture audit must stop on the parallel path finding. The next implementation phase must first define one authoritative production model-selection contract and route both storyboard image and video execution through the same canonical lineage, including a runtime credential reference/resolver and validation result.
