# Phase J1 Final Report — Model Management / Real Provider Integration Audit

## Final result

```text
PHASE_J1_PARALLEL_PROVIDER_PATH_DETECTED
```

The Model Registry and real image/video adapter inventory are present, but production storyboard generation is not integrated with the Phase F canonical GenerationExecution lineage. The audit therefore stops before any Provider call.

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

## Primary findings

1. **Parallel provider path:** Phase F canary persists `GenerationExecutionRecord` and `MediaCandidateRecord`, while storyboard `generate-frame` / `generate-video` invoke adapters and write storyboard asset links directly.
2. **Model-selection contract gap:** an omitted `model_profile_id` falls back to a capability default; there is no explicit authoritative Production GenerationPolicy binding for the storyboard request.
3. **Credential contract gap:** registry `key_configured` and raw `api_key` storage/consumption do not provide a secret-safe runtime credential reference, resolver, or validation result in the canonical execution profile.
4. **Video canonical gap:** real video adapters exist, but no canonical Phase F video GenerationExecution route was found; OpenAI-compatible video remains explicitly unsupported.
5. **Connectivity is not execution:** model tests can check reachability or catalog shape, but they do not produce execution, candidate, validation, promotion, or OfficialMedia records.

## Side-effect accounting

```text
Provider calls:             0
LLM calls:                  0
Image calls:                0
Video calls:                0
Production Authority writes: 0
Secret values recorded:     false
```

## Required next phase

Resolve the authoritative Production GenerationPolicy and canonicalize both storyboard image and video routes before authorizing real Provider execution. Add runtime credential reference/resolution/validation evidence without putting secret material into the canonical fingerprint. Do not mask the split with an adapter-only compatibility layer.

## Artifacts

- [Model management audit](./phase_j1_model_management_audit.md)
- [Real Provider readiness matrix](./phase_j1_real_provider_readiness_matrix.json)
- [Provider integration topology](./phase_j1_provider_integration_topology.md)

Source commit audited: `f59605d` on `codex/visual-authoring-provider-canary-reconcile`.

