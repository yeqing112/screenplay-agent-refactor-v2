# Phase J2 Generation Truth Ownership Review

## Review decision

```text
PHASE_J2_CANONICAL_GENERATION_DESIGN_APPROVED_PENDING_IMPLEMENTATION
```

This is a design decision, not a runtime readiness approval. The existing generic execution and candidate records can represent both `IMAGE` and `VIDEO`; no new `VideoGenerationExecution`, `VideoMediaCandidate`, `ImageGenerationExecutionV2`, or `PhaseJExecution` table is justified.

- Baseline HEAD: `5487db94f9e98cbcbf647db7a12531921d18ca06`
- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Provider/LLM/Image/Video calls: `0 / 0 / 0 / 0`
- Database migration: not performed
- Production Authority writes: `0`
- Production logic changes: none

## Ownership matrix

| Object | Owner | Mutability | Fingerprinted? | Currentness source | May contain a secret? |
|---|---|---|---|---|---|
| `PromptIR` / `PromptIRVersion` | Phase E PromptIR authority | Version immutable; current pointer may advance | Yes: payload hash and authority envelope | Current `PromptIRPointer`, fresh authority, semantic re-resolution | No |
| `GenerationPolicy` | PromptIR semantic compiler / explicit policy | Immutable per PromptIR version | Yes: `generation_policy_v1.fingerprint` | PromptIR version and authority envelope | No |
| `ProductionGenerationSelection` | Canonical request / operator decision | Explicit at preview; frozen by execution | Yes: selection fingerprint and profile fingerprint | Explicit profile ID plus current profile fingerprint | No |
| `ModelProfile` | Model Registry | Registry revisions mutable; execution snapshot immutable | Yes through `ProviderExecutionProfile` | Registry profile ID, enabled state, profile fingerprint | No; reference/status only |
| `ProviderExecutionProfile` | Canonical execution service | Immutable for an execution | Yes: provider request fingerprint input | Exact profile fingerprint and adapter binding/version | No |
| `CredentialReference` | Registry + deployment secret binding | Reference may rotate; bound reference frozen per execution | Reference identity may be fingerprinted; secret never is | Resolver result and validation evidence | No |
| `GenerationPayload` | PromptIR adapter boundary | Immutable request snapshot | Yes: generation payload fingerprint | Current PromptIR, policy, selection, profile, authority bindings | No |
| `GenerationExecutionRecord` | Canonical execution service | Request immutable after preview; status advances | Yes: payload, policy, profile, reference, request fingerprints | Preview snapshot compared before execute | No; snapshot is redacted/non-secret |
| `MediaCandidateRecord` | Canonical execution service | Immutable candidate evidence | Yes: candidate fingerprint and execution lineage | Execution, storage checksum, media metadata, validation | No |
| `MediaValidationRecord` | Deterministic media validator | Immutable validation result | Yes: technical and authority snapshot fingerprints | Candidate bytes plus current authority snapshot | No |
| `OfficialMediaVersion` / Authority / Pointer | Media Authority service | Explicit promotion; current pointer may advance | Yes: lineage, promotion, payload, pointer fingerprints | Candidate → validation → promotion → current pointer | No |

Model Management owns model identity, capability, provider identity, parameter capability, credential reference/configuration, enabled state, and operator defaults. It does not own PromptIR, shot, asset, candidate, or official media truth.

## Existing schema verdict

`models/generation_execution.py` already contains the cross-media fields required by the canonical lifecycle:

- `GenerationExecutionRecord.target_media`, status, provider task/request IDs, model profile ID/fingerprint, adapter ID/version, payload/policy/reference fingerprints, and idempotent provider request fingerprint.
- `MediaCandidateRecord.media_type`, storage identity/reference, checksum, MIME, byte size, dimensions, `duration_ms`, provider task ID, and complete PromptIR/model/request lineage.
- `MediaValidationRecord` and existing OfficialMedia models preserve candidate → validation → explicit promotion for either media type.

The current technical validator in `core/media_authority.py` accepts image signatures only. That is a media-validation implementation gap, not a persistence-schema gap: add a deterministic video MIME/dimension/duration validator while reusing the same records and state machine.

Decision:

```text
NO_NEW_EXECUTION_SCHEMA_REQUIRED
NO_NEW_MEDIA_CANDIDATE_SCHEMA_REQUIRED
```

## Semantic policy versus execution selection

`generation_policy_v1` remains semantic. Its fields (`mode`, `target_media`, asset classes, style, language, and source) describe the intended operation and required authorities. `model_profile_id` does not belong in it; adding it would mix creative semantics with runtime selection.

The canonical request needs a separate, explicit selection object, not a new table:

```json
{
  "schema_version": "production_generation_selection_v1",
  "target_media": "IMAGE|VIDEO",
  "model_profile_id": "<explicit registry profile id>",
  "selection_scope": {"book_id": 0, "episode": 0, "shot_id": "..."},
  "model_profile_fingerprint": "<current profile projection fingerprint>",
  "selection_fingerprint": "<hash of non-secret fields>"
}
```

Registry defaults may prefill a UI draft, but production preview fails closed when `model_profile_id` is absent.

## Canonical media-field ownership

| Media input | Canonical source | Rule |
|---|---|---|
| `task_mode` | `GenerationPolicy.mode` | Validate against selected profile capabilities; never infer from model name. |
| Prompt/static and motion semantics | Current PromptIR → GenerationPayload | `visual_prompt_static`/`visual_prompt_motion` are display/projection compatibility only. |
| Character/scene/prop bindings | H2/H2.2 Production Asset Authority and current `ShotAssetBinding` | Resolve and fingerprint current versions before preview and execute. |
| Reference images | Fresh locked `VisualReferenceAuthority`, matching current `VisualAssetPointer`, or explicitly declared current OfficialMedia | Reject storyboard URLs, temporary URLs, UI cache URLs, and filenames as truth. |
| Duration | PromptIR temporal `duration_hint_seconds`, normalized by profile capability | A raw UI override is not production truth without a versioned typed request/policy. |
| Aspect ratio/resolution | ProviderExecutionProfile capability/default parameters | Reject unrepresented per-shot overrides; do not parse prompt text. |
| First/last frame | Current asset/reference/official/typed transition-frame authority binding | Fingerprint authority; derive transport URLs only at the Provider boundary. |
| Provider task ID | Adapter response | Store on the same execution/candidate; polling never creates another execution. |

GenerationPayload should expose a typed media request section derived from these sources. Model Management cannot author or rewrite prompt semantics.

## Currentness and fingerprint requirements

The provider request fingerprint binds PromptIR payload, GenerationPolicy, target media, explicit selection, profile projection, adapter identity/version, asset/reference bindings, and typed media request. The secret itself is excluded. Execute re-resolves current PromptIR, policy, authorities, profile, adapter binding, and credential state; any change marks the preview `STALE` rather than switching silently.

## Shared lifecycle and gate

Image and video use one lifecycle:

```text
PREVIEWED → AUTHORIZED → RUNNING → SUCCEEDED → MEDIA_CANDIDATE
                                  ↘ FAILED
```

For each capability, real execution requires:

```text
human_authorized
AND production_model_selected
AND model_profile_current
AND adapter_resolved
AND credential_resolved
AND credential_validated
```

Validation and explicit promotion remain downstream. Provider success never writes storyboard official assets, `VisualAssetPointer`, or OfficialMedia directly.

