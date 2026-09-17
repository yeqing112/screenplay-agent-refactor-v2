# Director Quality V3 — Fact Requirement Semantics & Authoring Boundary

## Baseline Audit

- Baseline branch: `codex/fact-semantic-grounding-foundation`
- Baseline commit: `1d6f9260f16e25fecdffe7f0d5fe33844fcdb9ec`
- The previous MiMo proposer canary remains historical and immutable: 4 provider calls, 0 acceptable candidates, 0 writes.
- The previous six-item manifest treated source facts, production authoring, and continuity state as one blocking class.

## Implemented Contract

- Added `fact_requirement_registry_v1` in `core/fact_requirement_semantics.py`.
- Four authority classes are explicit: `SOURCE_FACT`, `DERIVED_SOURCE_FACT`, `PRODUCTION_AUTHORING_DECISION`, and `PRODUCTION_CONTINUITY_STATE`.
- Registry entries define predicate meaning, value schema, scope type, resolution policy, blocking stage, retrieval semantics, provider instruction, validation policy, and authoring fallback.
- `visual_identity` defaults to a production authoring decision at `VISUAL_ASSET_GENERATION`.
- `current_state` defaults to production continuity state at `SCENE_BLOCKING`; a global scope is represented as episode scope with the original scope preserved.
- `geometry` defaults to authoring at `SCENE_BLOCKING`; explicit source spatial constraints remain source evidence.
- `state` defaults to production continuity state at `SHOT_PLAN`; source prop facts remain possible when explicitly required.
- Missing-fact coverage now reports `authoring_decision_pending` and structured `authoring_decision_request_v1` records without putting those items in the ScriptIR blocking manifest.
- Explicit `source_required=true` remains fail-closed and can keep a requirement in the ScriptIR gate.
- Retrieval consumes registry aliases, semantic terms, source surfaces, and scope strategy. Surface taxonomy is a tie-breaker only and cannot create candidates without lexical evidence.
- Strict Provider evidence now uses `{anchor_ref, quote_span}` where `quote_span` must be a verbatim substring of the immutable anchor. Program code still owns full text and offsets. Legacy full-quote fields remain replay-compatible only.

## Six-Requirement Reclassification

| Requirement family | New authority | Blocking stage | ScriptIR gate |
|---|---|---|---|
| character visual identity | `PRODUCTION_AUTHORING_DECISION` | `VISUAL_ASSET_GENERATION` | no |
| character current state | `PRODUCTION_CONTINUITY_STATE` | `SCENE_BLOCKING` | no |
| scene geometry | `PRODUCTION_AUTHORING_DECISION` | `SCENE_BLOCKING` | no |
| prop state | `PRODUCTION_CONTINUITY_STATE` | `SHOT_PLAN` | no |

The source extractor is still required to preserve explicit source constraints. A genuinely missing `SOURCE_FACT` with `blocking_stage=SCRIPT_IR` continues to fail closed.

## Final As-Built Verification

- Provider calls in this implementation phase: `0`.
- FactSnapshot/authority/production writes: `0`.
- Targeted semantic, coverage, extraction, and proposer tests: **71 passed**.
- Full local suite: **1429 passed, 10 failed**. The 10 failures are known historical artifact/branch-baseline assertions (authority pointer provenance, retired recanary fixtures, and fresh integration fixture expectations); no failure is in the new registry, boundary, retrieval, or quote-span tests.
- Golden and full-suite verification must be rerun from a clean tree; unrelated historical artifact edits are not part of this phase.
- This phase does not activate `SEMANTIC_RETRIEVAL_V2` or `PROVIDER_CANARY_V2`, and does not rerun MiMo.

## Decision

`FACT_REQUIREMENT_SEMANTICS_AND_AUTHORING_BOUNDARY_IMPLEMENTED`

The formal ScriptIR gate remains fail-closed for source facts while production-only gaps are surfaced as authoring/continuity work instead of fabricated source facts.
