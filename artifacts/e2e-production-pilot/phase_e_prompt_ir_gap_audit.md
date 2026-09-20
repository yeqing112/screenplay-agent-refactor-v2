# Phase E Production Boundary Authority and Reuse Gap Audit

## Closed blockers

| Former gap | Production result | Evidence |
| --- | --- | --- |
| Legacy V1 could overwrite current pointer | Closed; single-shot endpoint returns `PROMPT_IR_LEGACY_PRODUCTION_DISABLED` | API contract and pilot legacy gate |
| Legacy adapter fallback | Closed; adapter preview requires `prompt_ir_v2` | Pilot V1 adapter gate |
| Reuse checked only hash/FRESH | Closed; reuse calls `validate_current_prompt_ir_authority` | 15/15 clean reuse and tamper compile-again trace |
| Request asset authority injection | Closed; Production request has only GenerationPolicy | Fake `FAKE` binding absent from persisted payload |
| Missing GenerationPolicy defaulted to TEXT_TO_IMAGE | Closed; explicit mode and target are required | `GENERATION_POLICY_REQUIRED` 409 |
| Visual Reference latest fallback | Closed; no `order_by(id.desc())`; ambiguous matches fail | `visual_reference_latest_fallback=false` audit field |
| `*_REFERENCE` checked only identity | Closed; requires concrete LOCKED/FRESH authority and current asset fingerprint | Required reference missing/stale validators |

## Canonical validation

`validate_current_prompt_ir_authority()` is the shared reuse/resolution contract.
It validates the current Pointer → Version → Authority chain, v2 schema,
FRESH state, pointer/version hashes, payload JSON and fingerprint, authority
envelope fingerprint and payload/policy/asset bindings, current Storyboard
materialization and semantic recompilation, GenerationPolicy fingerprint, and
current Visual Asset/Reference lineage.

## Compatibility boundary

V1 models, the legacy compiler, and `serialize_prompt_ir_to_adapter()` remain
available for read, audit, and compatibility tests. They are not reachable from
Production adapter preview or Production compile mutation.

## Remaining negative proof

The pilot intentionally does not create reference media. It proves the negative
required-reference gate with an existing current asset version and no concrete
LOCKED/FRESH reference authority. No provider or image generation is used to
manufacture a positive reference.
