# Phase J3 canonical generation topology

## Scope

IMAGE and VIDEO now resolve through one production generation contract. The
media type changes the registered capability, adapter and transport, while
selection, authority resolution, confirmation, idempotency, execution records
and candidate lineage stay shared.

## Path

1. The caller supplies `book_id`, `episode`, `storyboard_shot_id`, an explicit
   `target_media` (`IMAGE` or `VIDEO`) and an explicit `model_profile_id`.
2. The resolver loads the current media-scoped PromptIR pointer, Generation
   Policy, asset/reference authority and profile-bound adapter. It rejects
   missing, stale or cross-media authority before any provider call.
3. PromptIR is adapted to a typed GenerationPayload. VIDEO carries an explicit
   `TEXT_TO_VIDEO` or `IMAGE_TO_VIDEO` mode, duration, aspect ratio and
   resolution. IMAGE_TO_VIDEO additionally binds the current
   `SHOT_PRIMARY_IMAGE` OfficialMedia authority and storage identity.
4. The model profile is projected to a secret-free
   `provider_execution_profile_v2`. Adapter identity and version come from the
   registry; the request cannot inject an adapter id. The registry is read via
   its non-sensitive projection, and a runtime credential enters only through
   an injected/environment resolver at the transport boundary.
5. A deterministic request fingerprint includes selection, PromptIR lineage,
   generation policy/payload, profile fingerprint, adapter version, reference
   bindings and the IMAGE_TO_VIDEO source binding.
6. Preview persists a `GenerationExecutionRecord` and returns a confirmation
   token. Execute reuses the same record, claims it idempotently, performs the
   provider-free mock transport in this phase, persists one `MediaCandidateRecord`
   and validates the stored bytes before success.
7. IMAGE uses the existing canonical image storage bridge. VIDEO uses the
   canonical video storage bridge and `ffprobe` technical validation for
   container, MIME, dimensions, duration, checksum, byte size and storage
   identity.

## Public surfaces

- `POST /api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation/preview`
- `POST /api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation/execute`
- Existing storyboard frame/video endpoints delegate only when a caller sends
  an explicit `model_profile_id`; the no-profile branch remains an explicitly
  marked legacy compatibility surface.

## Provider boundary

The built-in `prototype-task-adapter` returns deterministic PNG/MP4 fixtures.
Real Provider execution remains confirmation-gated and opt-in; no Provider,
Image, Video or paid LLM call is made by the J3 tests or this audit.
