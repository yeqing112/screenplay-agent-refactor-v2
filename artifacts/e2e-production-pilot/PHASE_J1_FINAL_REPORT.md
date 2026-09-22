# Phase J1 Final Report — Model Management / Real Provider Integration Audit

## Final result

```text
PHASE_J1_PARALLEL_PROVIDER_PATH_DETECTED
```

The Model Registry and real image/video adapter inventory are present, but production storyboard generation is not integrated with the Phase F canonical GenerationExecution lineage. The audit therefore stops before any Provider call.

Primary status is exactly `PHASE_J1_PARALLEL_PROVIDER_PATH_DETECTED`; the integration and model-selection gaps below are follow-up findings, not additional terminal statuses.

Audited repository HEAD: `4754f5d91f1a771b424e722ea5f848918461daf9` on `codex/visual-authoring-provider-canary-reconcile`. The implementation snapshot was already committed and pushed before this report was finalized.

## What was audited

- Model Registry capability labels, profile defaults, and profile resolution.
- Canonical ProviderExecutionProfile projection and credential fields.
- Model connectivity-test boundary.
- Phase F generation-canary preview/execute path.
- Production storyboard frame/video generation path.
- Image and video adapter coverage.

## Readiness summary

| Capability | Registry/profile | Adapter | Credential resolver | Canonical production path | Ready |
|---|---:|---:|---:|---:|---:|
| Image | Resolved | Resolved | Missing | Bypassed by storyboard route | No |
| Video | Resolved | Resolved | Missing | No canonical Phase F video route; storyboard route bypasses lineage | No |

The registry read found 9 profiles, 7 non-mock profiles, and 6 configured non-mock profiles. The configured defaults are `shapi-openai-images / gpt-image-2.5-flare` for image and `minimax-h3-async / MiniMax-H3` for video. These defaults are not an Episode/Shot production policy binding.

Image and video are reported separately: both have a resolved registry profile and adapter inventory, but neither has a selected Production GenerationPolicy, runtime credential reference, validated credential, or valid canonical production execution path.

## Primary findings

1. **Parallel provider path:** Phase F canary persists `GenerationExecutionRecord` and `MediaCandidateRecord`, while storyboard `generate-frame` / `generate-video` invoke adapters and write storyboard asset links directly.
2. **Model-selection contract gap:** an omitted `model_profile_id` falls back to a capability default; there is no explicit authoritative Production GenerationPolicy binding for the storyboard request.
3. **Credential contract gap:** registry `key_configured` and raw `api_key` storage/consumption do not provide a secret-safe runtime credential reference, resolver, or validation result in the canonical execution profile.
4. **Video canonical gap:** real video adapters exist, but no canonical Phase F video GenerationExecution route was found; OpenAI-compatible video remains explicitly unsupported.
5. **Connectivity is not execution:** model tests can check reachability or catalog shape, but they do not produce execution, candidate, validation, promotion, or OfficialMedia records.
6. **Currentness is incomplete on the storyboard branch:** canonical Phase F records freeze `model_profile_id`, profile fingerprint, adapter identity, and version; storyboard tasks do not persist that canonical fingerprinted execution lineage before adapter invocation.

## Side-effect accounting

```text
Provider calls:             0
LLM calls:                  0
Image calls:                0
Video calls:                0
Production Authority writes: 0
Secret values recorded:     false
FULL_REAL_END_TO_END_PRODUCTION_ACCEPTANCE_COMPLETE: false
```

## Required Phase J gate

For image and video independently, real execution must require:

```text
human_authorized
AND production_model_selected
AND model_profile_current
AND provider_profile_valid
AND credential_resolved
AND credential_validated
AND adapter_available
```

The current audit fails the gate on model selection authority, canonical path convergence, credential resolution/validation, and human authorization. `key_configured=true` remains a registry declaration and is not treated as credential validation.

## Required next phase

Resolve the authoritative Production GenerationPolicy and canonicalize both storyboard image and video routes before authorizing real Provider execution. Add runtime credential reference/resolution/validation evidence without putting secret material into the canonical fingerprint. Do not mask the split with an adapter-only compatibility layer.

The structured integration plan is documented in the [model management audit](./phase_j1_model_management_audit.md): selection authority, canonical image/video convergence, secret-safe credential resolution, currentness freezing, and separate capability gates.

## Artifacts

- [Model management audit](./phase_j1_model_management_audit.md)
- [Real Provider readiness matrix](./phase_j1_real_provider_readiness_matrix.json)
- [Provider integration topology](./phase_j1_provider_integration_topology.md)

Relevant interface lineage includes `1e2367d` (registry), `880c701`/`b1678da` (video adapters), `ed32775` (defaults), `9745519` (Phase F canary), and `0600e3a` (ProviderExecutionProfile boundary).
