# Canonical Semantic Rematerialization Dry-Run Plan

This is a design only. It was not executed and contains no database mutation.

## Input scope

- Book IDs: `[990448, 990449, 990450, 990451, 990452]`
- Affected canonical rows: `20`
- Provider calls: `0`
- Production writes: `0`

## Preconditions

1. Validate explicit production provenance for each input book and reject UNKNOWN_PROVENANCE/CANARY_PROJECT.
2. Resolve the current ScriptIR, DirectorTreatment, SceneBlocking and ShotPlan pointers; reject stale or superseded envelopes.
3. Require the patched SceneBlocking preview/compiler path and compare the source semantic fingerprint before materialization.
4. Keep source facts and ScriptIR immutable; no PromptIR compilation is part of this plan.

## Before fingerprints

```json
{
  "372": "9b01333eea7b963d64974aaf997dca02ffe3674dbb583e1c1aa153ddfc5d2ef9",
  "373": "e669e58741405a02ace371769948a1caf08887a800b4fe0daf64b0c81fbc4e02",
  "374": "dcf9fbb1bd450bc1426f89feb9d4dcfa5d3f2219d8e07fd80d54e37a3dad8852",
  "375": "3de1657ea1a9ce8845f5b913693c9aea6b41864d7a908204ce727a4b5d9fec06",
  "376": "dc804e8472ae33d11ebe873fe63ac5e6103de8b8ea9b3250c925523ba0edb81b",
  "377": "86321aac1d9d4a399cf41b4bf036b6ba481cda33c54576f29e5a969ccb00642d",
  "378": "899e783d9f32cc3116f49b6423b39720f41bc2225801968695bdc12b8799af14",
  "379": "2966f9cf78f827eabf8f1f9d42ea9eb187e18ecaaad66ed05d4e4978f8fa333e",
  "380": "7f39b909d2ad105f955f47ebebd95390fd7a3d92551cc5c4e66d751d621eb641",
  "381": "9aaa4b48a0e6933ddd5b4a0bc0b66d5bc3e5ccb2e134b0d2faf1c28dce002184",
  "382": "c972f67bae0ee4071f0f8e5005deb76b3e824053119bc8333894a6447a24d8eb",
  "383": "7e92c716883030de7ca938ec557af54972a9f02b93c2dedb3fb098ea46889994",
  "384": "d7298f40329a1147d2cf0b71342d208460af7bd4f3e341ee43aebcfeec1b7daf",
  "385": "878c51ffff592f88aaf01011c88cbd231f6473ecf1a0660dc8cd003bfdad9893",
  "386": "bf221e42a53d703eb13668a723cd95e59dac8795d7452814aae67f12710870bf",
  "387": "8119be90f810b50f7cf34f860c7399dd09a4ba473faa56ec062a32d1488cd081",
  "388": "f6e7ac8ce38a22c1254087d36b20ec605899142e89c8b60264704f54c3882f8c",
  "389": "e8687f5752cb77d7880be9be32ef1e65eef612737d06039cf6863165d164e68d",
  "390": "3b4434d852e8364a126dcdd1a84249daa793f129b4344329879a80189e0f5619",
  "391": "3c89546af239c230bb30afd41e3f413bf78104255056b9bad9960e6ad2d6589f"
}
```

## Expected projection diff

- Character subjects: current empty arrays would become only the already-declared SceneBlocking participant(s) after the hydration repair.
- Dialogue: no change; source and ScriptIR dialogue are empty.
- Props: no change; no authoritative props are present.
- `canonical_asset_identity`: recomputed only from the repaired ShotPlan semantic projection; never from legacy prompt handoff.

## Idempotency and stale-write protection

- Use the source ScriptIR authority fingerprint, ShotPlan authority fingerprint, materialization set fingerprint, and semantic projection fingerprint as an idempotency tuple.
- Abort if any current pointer, payload hash, source fingerprint, or materialization set changes between dry-run and authorized execution.
- Never update an existing set in place; create a new immutable set and move the explicit pointer only after all rows validate.

## Rollback

- Keep the prior materialization set and StoryboardShot rows immutable and addressable.
- On failure, leave the new set unpublished and restore the pointer to the prior fresh set; PromptIR and OfficialMedia remain untouched.

## Authorization gate

Production execution requires explicit user authorization after a review of the dry-run diff and provenance audit. This phase did not receive or consume that authorization.
