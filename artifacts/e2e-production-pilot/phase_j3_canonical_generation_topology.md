# Phase J3.1 canonical generation topology

## Boundary status

The Production HTTP generation aliases (`generate-frame` and
`generate-video`) are aliases of the canonical service. A request without an
explicit `model_profile_id` fails with `409 PRODUCTION_MODEL_SELECTION_REQUIRED`
before a legacy queue, provider call, task row, execution row, candidate row,
or storyboard media write.

The historical `_queue_storyboard_generation_task` and
`_save_asset_to_storyboard` helpers remain available to non-Production
historical tooling. They are not reachable from the Production HTTP
generation aliases.

## Canonical path

```text
Storyboard / Canvas / Batch / Task Center / Direct API
                         |
                         v
              Explicit Model Selection
                         |
                         v
                  media-scoped PromptIR
                         |
                         v
             Production Asset / Reference Authority
                         |
                         v
                    GenerationPayload
                         |
                         v
                      ModelProfile
                         |
                         v
                 Profile-bound Adapter
                         |
                         v
                ProviderExecutionProfile
                         |
                         v
                  Runtime Credential
                         |
                         v
                ONE Canonical Generation Service
                         |
                         v
                 Exact Transport Registry
                    /                 \
                   v                   v
                IMAGE                VIDEO
```

## Transport boundary

`core/provider_transport_registry.py` owns exact `(provider_id,
target_media, transport_binding_id)` bindings. IMAGE and VIDEO use the same
canonical dispatcher. The video bindings reuse the existing adapter functions:

- `poyo-async`: `submit_poyo_generation` → `poll_poyo_generation`
- `minimax-h3-async`: `submit_minimax_h3_generation` → `poll_minimax_h3_generation`
- `75api-minimax-h3`: `submit_75api_minimax_h3_generation` →
  `poll_75api_minimax_h3_generation`

The submit task id, poll lifecycle, terminal response and candidate all remain
bound to one `GenerationExecutionRecord`; polling never creates a second
execution or resubmits automatically.

## Credential boundary

`RuntimeCredentialBinding` provides an explicit resolver and validator. A
resolved secret is passed only as a short-lived transport argument. Missing or
false validation returns `RUNTIME_CREDENTIAL_NOT_VALIDATED`; the canonical
profile, request snapshot, fingerprint, candidate and audit projections remain
secret-free. Human authorization for a real provider is checked separately by
the existing `PHASE_J_PROVIDER_AUTHORIZED` gate.

## Evidence

- `phase_j3_1_legacy_generation_shutdown_audit.json`
- `phase_j3_1_runtime_credential_validation_audit.json`
- `phase_j3_1_provider_transport_matrix.json`
- `phase_j3_1_full_canonical_provider_free_pilot.json`
