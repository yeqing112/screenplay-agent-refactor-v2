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
- Audited source commit: `f59605d`
- This phase is architecture and runtime-readiness audit only.
- No LLM, image, video, storage, or Provider API was called.
- No business logic, Provider contract, authorization gate, test, fixture, or Production Authority record was changed.
- Secret values were not read into the report or committed.

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

## Readiness conclusion

The registry and adapters are discoverable, but the system is not production-ready for real Provider execution under the requested contract. The architecture audit must stop on the parallel path finding. The next implementation phase must first define one authoritative production model-selection contract and route both storyboard image and video execution through the same canonical lineage, including a runtime credential reference/resolver and validation result.

