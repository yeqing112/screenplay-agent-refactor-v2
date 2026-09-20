# Director V3 Strategy Authority Contract SSOT Gap Audit

## Baseline Audit

- Provider-facing Pilot #1 contract accepted `must_preserve: string[]`.
- Runtime authority expected structured preserve anchors, so the failed experiment was not a fair model-capability adjudication.

## Final As-Built Verification

- Machine authority is now `preserve_intents`; `must_preserve` is human-readable projection only and cannot pass Fresh V3 validation without an explicit projection marker.
- Anchor refs are required, exact and provider-visible; invalid or missing refs fail closed. No regex, fuzzy matching, embedding, semantic mapper or prose guessing is used.
- Program assigns `MP01...`, canonicalizes refs, provenance and fingerprints; the Provider never assigns constraint IDs.
- Authority completeness and Provider readiness require schema, identity, preserve and provenance checks before downstream calls.
- Fresh Pilot #1 is retained as historical `FAILED`, reclassified `INVALID`, and all six exposed scenes are retired from future Provider experiments.
- Fresh Pilot #2 is inventory/readiness only (`ready=false`, `authorized=false`, no cohort freeze).
- Provider calls in this closure: `0`.
