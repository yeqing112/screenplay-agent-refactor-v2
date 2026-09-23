# Phase J2.1 Media Authority Cardinality Matrix

## Scope

This is a provider-free design gate for `PHASE_J2_1_PROMPT_IR_MEDIA_POLICY_CARDINALITY_REVIEW`. The reproduction used a temporary SQLite database and fixture-only H2.2 scene/character bindings. No production database, migration, Provider, LLM, image, video, or production-authority write was used.

## Matrix

| Authority surface | Cardinality today | Current pointer scope today | Historical behavior | Legitimate stale trigger | J2.1 finding |
|---|---|---|---|---|---|
| `StoryboardShot` | One row per shot | Shot identity (`book_id`, `episode`, `id`) | Row identity and projection fingerprint are historical evidence | Storyboard projection, materialization, or upstream shot change | Stable semantic anchor |
| `PromptIRVersion` | Many immutable versions per shot | Reached through one `PromptIRPointer` | Version payload, payload hash, and authority envelope remain immutable evidence | Semantic storyboard/asset/compiler change, or explicit policy revision | Payload currently embeds `generation_policy`, including `target_media` |
| `PromptIRPointer` | **One current row per shot** | Unique `storyboard_shot_id` (with book/episode lookup) | Moving the pointer makes the previous version non-current for shot-level resolution | Any new current PromptIR revision | **Cardinality conflict:** IMAGE A and VIDEO B cannot both be current |
| `GenerationPolicy` | One policy projection inside each PromptIR version | Indirectly follows the single PromptIR pointer | Historical policy is retained with its PromptIR version | Policy itself or its semantic inputs change | Existing J2 decision keeps policy semantic; do not silently move it to execution intent |
| `GenerationExecutionRecord` | Many executions per shot | Execution row carries `target_media`, PromptIR version, policy fingerprint, request fingerprint | Execution/candidate lineage is immutable evidence | Current PromptIR, asset/reference, selection, profile, or credential lineage changes | Persistence already supports IMAGE and VIDEO; no new execution table required |
| `OfficialMediaVersion` | Many revisions per `(shot, media_role)` | Revision scope `(book_id, episode, shot, media_role)` | Older revisions are `SUPERSEDED`; authority envelope keeps exact lineage | Re-generation for same role or upstream lineage invalidation | Media role is already media-scoped |
| `OfficialMediaPointer` | One current pointer per `(shot, media_role)` | Unique `(book_id, episode, storyboard_shot_id, media_role)` | Pointer moves within a role; other roles are independent | New official revision for that role | Naturally expresses `SHOT_PRIMARY_IMAGE` and `SHOT_PRIMARY_VIDEO` together |
| `VisualReferenceAuthority` | Many locked reference authorities | Authority fingerprint plus current VisualAssetPointer | Historical reference remains evidence; current pointer controls usability | Asset version/pointer drift or lock/status change | Must not become a second truth for an official IMAGE |

## Reproduced transition

```text
PromptIRPointer(SHOT) -> PromptIR A(target_media=IMAGE)
OfficialMediaPointer(SHOT_PRIMARY_IMAGE) -> Official Image A
                                   |
                                   v
PromptIRPointer(SHOT) -> PromptIR B(target_media=VIDEO)
```

Before the pointer move, the strict resolver returned `PASS`. After the legal move to PromptIR B, resolving the existing IMAGE official returned `OFFICIAL_MEDIA_BINDING_INVALID` with the underlying cause `MEDIA_OFFICIAL_RESOLUTION_FAILED` because current upstream PromptIR/policy lineage no longer matched the IMAGE execution. The IMAGE candidate, validation, authority envelope, checksum, and lineage hashes remained internally valid.

## Cardinality conclusion

The current implementation has asymmetric scopes: Official Media is per `media_role`, while PromptIR currentness is per shot. The product flow requires a current official IMAGE and a current official VIDEO for the same shot, with the IMAGE available as the first/reference frame for `IMAGE_TO_VIDEO`. The current one-pointer PromptIR scope therefore cannot represent the required state.
