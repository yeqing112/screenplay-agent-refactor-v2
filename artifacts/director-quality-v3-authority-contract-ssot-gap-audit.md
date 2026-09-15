# Director V3 Authority & Contract SSOT Gap Audit

- Final Re-Canary remains `BLOCKED` and the original three scenes are retired for provider experiments.
- The previous pre-call miss occurred because Preserve fingerprints were checked without checking anchor completeness.
- Legacy `must_preserve` strings are human-readable projections only; they are not machine authority.
- Structured constraints now require authoritative beat/event/source anchors and fail closed on missing or ambiguous bindings.
- Provider readiness is upstream of every Provider call and checks content completeness plus schema/enum/forbidden-field parity.
- Spine and Skeleton Provider contracts, normalizers and validators consume versioned SSOT specifications with schema fingerprints.
- This stage made no Provider, LLM, media, storage or CI calls.
