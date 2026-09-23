# Phase J2.2 Media-Scoped PromptIR Resolver Contract

## Required input

Every current resolver and production generation boundary must receive an explicit canonical `target_media`:

```text
resolve_current_authoritative_prompt_ir(book_id, episode, storyboard_shot_id, target_media, ...)
validate_prompt_ir_integrity(book_id, episode, storyboard_shot_id, target_media, ...)
validate_current_prompt_ir_authority(book_id, episode, storyboard_shot_id, target_media, ...)
```

Missing or invalid scope returns 409. The resolver never calls `.first()`, `.latest()`, or defaults to IMAGE when scope is absent. An internal caller may pass `GenerationExecutionRecord.target_media` only after that field has itself passed the canonical media invariant.

## Resolution sequence

1. Validate exact `IMAGE`/`VIDEO` input.
2. Query `PromptIRPointer` by `(book_id, episode, storyboard_shot_id, target_media)`.
3. If missing, return `PROMPT_IR_POINTER_MISSING`; do not return another media scope or a historical version.
4. Validate pointer/version book, episode, shot, qualification state, payload hash, schema version, and authority envelope.
5. Parse `payload_json.generation_policy.target_media` and require exact equality with `pointer.target_media`. Any mismatch returns `PROMPT_IR_POINTER_MEDIA_SCOPE_MISMATCH` and does not auto-correct either row.
6. Run `validate_prompt_ir_historical_integrity` against the version and authority without requiring current-pointer state. Historical validity and current lineage are separate results.
7. Compare the stored version's policy and media scope to the current shared storyboard/asset snapshot. A shared upstream change may stale this scope, but the comparison uses this scope's stored policy, never the policy from another media request.

`validate_prompt_ir_historical_integrity(version, authority, payload)` remains a pure historical function and must not be forced to choose a current pointer.

## Compile and update

The Phase E compile request already carries an explicit `generation_policy.target_media`. After normalization, one compile operation creates or updates only the matching pointer scope. Its map is:

```python
existing_by_scope[(storyboard_shot_id, target_media)] = pointer
```

IMAGE compilation cannot move/delete/revise the VIDEO pointer merely because policies differ. VIDEO compilation has the symmetric rule. Pointer scope is derived from `ir["generation_policy"]["target_media"]`, never from a free pointer field supplied by the caller. A compile response includes `target_media` beside the version ID and payload hash.

## Adapter preview and canonical generation

Adapter preview must require an explicit media scope. If the request carries a generation-policy override, its normalized target must be the resolver scope; otherwise return `PROMPT_IR_MEDIA_SCOPE_REQUIRED`. A VIDEO request can read only the VIDEO pointer and cannot read IMAGE then overwrite the policy.

The future canonical generation equality gate is:

```text
ProductionGenerationSelection.target_media
== PromptIRVersion.payload_json.generation_policy.target_media
== PromptIRPointer.target_media
== GenerationExecutionRecord.target_media
== MediaCandidateRecord.media_type
== OfficialMediaVersion.media_type
```

Any mismatch fails closed before Provider transport.

## OfficialMedia resolver

OfficialMedia resolution does not parse `media_role`. It follows structured lineage:

```text
OfficialMediaPointer
  → OfficialMediaVersion
  → GenerationExecutionRecord.target_media
  → candidate/media-version type equality
  → PromptIRPointer(shot, execution.target_media)
  → exact PromptIR version/hash/authority checks
```

The resolver may use `execution.target_media` because it is persisted execution lineage; it must verify the candidate and official version type first. `SHOT_PRIMARY_IMAGE` and `SHOT_PRIMARY_VIDEO` remain independent role pointers, while target media remains the generation type.

## IMAGE_TO_VIDEO reference contract

An IMAGE_TO_VIDEO payload carries a structured binding to the current IMAGE OfficialMedia authority:

```json
{
  "authority_class": "OFFICIAL_MEDIA",
  "official_media_authority_id": "...",
  "official_media_version_id": "...",
  "media_role": "SHOT_PRIMARY_IMAGE",
  "checksum_sha256": "...",
  "source_prompt_ir_version_id": 123,
  "source_prompt_ir_payload_hash": "..."
}
```

The resolver must resolve that IMAGE authority in IMAGE scope, verify currentness, checksum, and source PromptIR lineage, then persist the binding in the VIDEO execution snapshot. A Provider URL, storyboard URL, filename, or duplicated `VisualReferenceAuthority` is not a substitute. Transport URLs may be derived only at the Provider boundary.

## Error and fallback rules

- No target scope: `PROMPT_IR_MEDIA_SCOPE_REQUIRED`.
- No pointer in requested scope: `PROMPT_IR_POINTER_MISSING`.
- Only another media scope exists: still `PROMPT_IR_POINTER_MISSING`.
- Pointer/payload target mismatch: `PROMPT_IR_POINTER_MEDIA_SCOPE_MISMATCH`.
- Historical invalidity: tamper/integrity error; current obsolescence: stale/current-lineage error.
- No latest, first, IMAGE default, role-string inference, stale-media fallback, or cross-media fallback.

## Required resolver acceptance cases

The implementation test plan must cover:

1. IMAGE and VIDEO pointers for one shot both resolve `PASS` with their matching OfficialMedia rows.
2. A VIDEO request with only an IMAGE pointer returns `PROMPT_IR_POINTER_MISSING`; it never returns IMAGE or a VIDEO historical version.
3. A pointer whose scope says VIDEO while its payload policy says IMAGE returns `PROMPT_IR_POINTER_MEDIA_SCOPE_MISMATCH`.
4. A legal VIDEO pointer creation leaves an unchanged IMAGE OfficialMedia current and resolvable.
5. IMAGE_TO_VIDEO resolves the current IMAGE OfficialMedia binding, verifies checksum/authority/source PromptIR, and persists a structured reference.
6. Replacing that IMAGE with I2 leaves the old Video historically valid but current-lineage obsolete when its contract requires current IMAGE; no automatic regeneration occurs.
