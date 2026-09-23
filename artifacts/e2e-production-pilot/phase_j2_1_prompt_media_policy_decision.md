# Phase J2.1 PromptIR / Media Policy Decision

## Decision

```text
PHASE_J2_1_MEDIA_SCOPED_PROMPT_IR_SCHEMA_REQUIRED
```

The deterministic reproduction proves a real currentness/cardinality conflict. The selected direction is **Option B: media-scoped PromptIR pointers**. This preserves the Phase J2 authority decision that `GenerationPolicy` remains semantic policy while allowing IMAGE and VIDEO PromptIR lineages to be current independently.

## Evidence

- IMAGE PromptIR A and IMAGE OfficialMedia A resolved `PASS` in a temporary SQLite fixture.
- A legal VIDEO PromptIR B was created and the existing unique per-shot pointer was advanced to B.
- Resolving IMAGE OfficialMedia A then failed with `OFFICIAL_MEDIA_BINDING_INVALID` / `MEDIA_OFFICIAL_RESOLUTION_FAILED` due to current upstream PromptIR/policy mismatch.
- Historical candidate, validation, official version, authority envelope, checksum, and lineage checks remained valid. The failure is current-lineage obsolescence, not tamper.
- Provider, LLM, image, and video calls were all zero.

## Option comparison

| Option | Authority consistency | Migration / implementation cost | Stale semantics | IMAGE_TO_VIDEO | Phase E / Phase I | Decision |
|---|---|---|---|---|---|---|
| **A. Media-neutral PromptIR + execution policy** | Makes one semantic PromptIR feed multiple execution policies, but reclassifies the current `generation_policy` authority surface | High authority/API/compiler/history change; execution selection must become the policy owner | Avoids cross-media staleness only after redefining PromptIR history and currentness | IMAGE OfficialMedia can remain current as an execution reference | Conflicts with J2 decision that GenerationPolicy remains semantic and with Phase E historical envelopes that bind it | Rejected for this gate |
| **B. Media-scoped PromptIR pointers** | Keeps `GenerationPolicy` in PromptIR and aligns current PromptIR scope with media-scoped OfficialMedia roles | Requires a migration/backfill and updates to pointer uniqueness, API/resolvers, stale propagation, snapshots, and currentness checks | IMAGE becomes stale only for IMAGE lineage changes; VIDEO policy changes do not invalidate IMAGE automatically | IMAGE_TO_VIDEO uses current IMAGE PromptIR/OfficialMedia as the declared first/reference frame and a separate VIDEO PromptIR/execution lineage | Preserves Phase E payload and historical authority semantics; Phase I must resolve the pointer for the requested media role | **Selected** |
| **C. IMAGE is reference-only** | Removes IMAGE from OfficialMedia truth and places it under a separate reference authority | Avoids the pointer conflict by changing the product model, but creates a second media truth and migration burden | IMAGE promotion/currentness no longer follows OfficialMedia | Can use a locked reference, but loses official IMAGE delivery semantics | Does not match the required product flow where IMAGE is a produced official frame | Rejected |

## Required design constraints for the next implementation phase

1. Add an explicit `target_media` scope to `PromptIRPointer` (and its uniqueness/index contract), with deterministic backfill from each version's stored `generation_policy.target_media`.
2. Keep `PromptIRVersion` and `PromptIRAuthority` payload/envelope semantics unchanged for historical rows; do not treat the new VIDEO pointer as a mutation of IMAGE A.
3. Update PromptIR compile/update APIs and all current resolvers to require the requested target media. A shot may have one current IMAGE PromptIR and one current VIDEO PromptIR.
4. Update OfficialMedia currentness to compare a media role's execution against the PromptIR pointer for the corresponding target media. `SHOT_PRIMARY_IMAGE` and `SHOT_PRIMARY_VIDEO` must remain independent pointers.
5. Propagate stale status by the affected media lineage. A VIDEO generation intent alone must not stale a valid IMAGE OfficialMedia; an IMAGE semantic/asset change may stale both media lineages when the shared upstream actually changed.
6. For `IMAGE_TO_VIDEO`, declare the source explicitly as the current `SHOT_PRIMARY_IMAGE` OfficialMedia authority (or another single approved typed authority), including checksum and PromptIR lineage. Do not use latest-PromptIR fallback or role-specific bypasses.
7. Add a video-capable technical validator inside the existing shared media validation boundary; this gate does not implement it.

## Why Option A is not selected despite its conceptual appeal

The static and motion surfaces can coexist in one PromptIR, but the approved J2 contract explicitly keeps `GenerationPolicy` semantic and stores its fingerprint in the PromptIR authority envelope. Moving it to execution intent would revise Phase E historical meaning and the current compiler/API contract. That is a separate authority redesign, not a safe cardinality fix for this gate.

## Gate boundary

No migration or production code change is authorized by J2.1. Stop before J3/implementation until the media-scoped pointer schema and resolver contract are approved.
