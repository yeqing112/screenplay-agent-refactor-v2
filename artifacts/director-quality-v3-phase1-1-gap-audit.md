# Director Quality V3 Phase 1.1 — Repository Audit

**Audit date:** 2026-09-15  
**Branch:** `codex/unify-formal-workspace`  
**Audited HEAD:** `027da13ee9be25343957f4c4038efea4e1b8b7b2`  
**Scope:** provider-free read-only audit preceding Phase 1.1 implementation.

## Executive result

Phase 1.1 is **not implemented yet**. The repository contains a V3 Foundation and
Phase 1 strategy canary, but the current production path still uses a single
`director_scene_strategy_v1` object as provider contract, validator input and QA
input. A new semantic IR, SSOT compiler, canonical V2 strategy, protocol/content
status split, legacy replay normalizer and provider-free previews are missing.

The Phase 1 canary's `0/3` final schema result is therefore not evidence that the
provider cannot express directing intent. It is a mixed result containing contract
shape drift, provider-owned fingerprint errors, and one unknown beat reference.

## 1. Provider contract actually exposed

`core/director_strategy_prompt.py` imports `STRATEGY_FIELDS` from
`core/director_scene_strategy.py` and exposes all V1 fields as required. It tells
the provider to emit `strategy_fingerprint`, while also describing nested rules
that are not represented in a typed schema or generated skeleton. The prompt
accepts ordered arrays for `audience_knowledge_arc`, `emotional_arc`,
`power_arc`, and `information_reveal_plan`, and a list-shaped performance arc,
but it does not provide exact nested field names, allowed IDs, alias rules, or
N/A rules.

The provider contract artifact confirms two attempts per scene (`CREATIVE_GENERATION`
and `FORMAT_REPAIR`) and a strategy-only side-effect boundary, but has no SSOT
schema reference and no model-facing IR boundary.

## 2. Validator actually required

`parse_scene_directing_strategy()` requires V1 top-level fields, rejects unknown
top-level keys, requires every arc to cover every source beat, requires
`information_reveal_plan` to match source beat order, and validates source facts.
It hard-codes `power_arc[*].controller` to a canonical character ID or `shared`/
`none`, and hard-codes `performance_arc` to a list of rows with `character_id`.
It computes/validates the SHA-256 fingerprint after parsing, but the provider is
still required to supply that computed field.

## 3. Quality diagnostics actually assumed

`core/director_strategy_quality.py` assumes:

- `audience_knowledge_arc[*].phase_id`, `does_not_know_yet`, `suspects`;
- `emotional_arc[*].trigger`, `emotion_state`, `transition_reason`;
- list-shaped `performance_arc[*]` with `objective`, list tactic/visible progress,
  and `turning_point`;
- object-shaped `edit_arc` and `visual_grammar`.

`core/director_professional_qa.py` consumes the legacy V1 arrays and a separate
ShotPlan trace contract. It does not consume a phase-centric IR and has no
independent `protocol_status` / `directing_content_status` result.

## 4. Drift taxonomy

| Area | Provider output | Validator / QA expectation | Classification |
|---|---|---|---|
| Knowledge arc | `knowledge_state`, `transition_trigger`, sometimes `knowledge` | `phase_id`, `does_not_know_yet`, `suspects` | `FIELD_NAME_MISMATCH`, `QA_SHAPE_MISMATCH` |
| Emotion arc | `emotion` | `emotion_state` | `FIELD_NAME_MISMATCH`, `QA_SHAPE_MISMATCH` |
| Power | `power_holder`, `power_dynamic(s)`, `dynamic` | `controller` in character/shared/none set | `FIELD_NAME_MISMATCH`, `VALIDATOR_OVERCONSTRAINT` |
| Power authority | object/relationship/information holders occur | character-only controller check | `VALIDATOR_OVERCONSTRAINT` |
| Performance | character-keyed object or list with `character_name` | list rows with canonical `character_id` | `SHAPE_MISMATCH`, `QA_SHAPE_MISMATCH` |
| Edit/visual | prose strings | object/list structures | `SHAPE_MISMATCH` |
| Beat IDs | numeric strings (`1`) and `B1` mixed | exact canonical IDs | `SHAPE_MISMATCH` / normalization gap |
| Fingerprint | provider emits fake identical values | program validates provider value | `COMPUTED_FIELD_PROVIDER_ERROR` |

## 5. Phase 1 failure classification

The three historical raw outputs are preserved unchanged under
`artifacts/director-quality-v3-phase1-strategies/` and in the real canary
artifact. Their observed failures classify as follows:

- **True semantic invalidity:** one unknown beat reference in the
  `回声照相馆` power arc; any invented reveal would also remain a true semantic
  error, but the canary recorded fact invention count `0`.
- **Contract/shape drift:** all three outputs use at least one legacy or
  provider-invented nested shape not described by the validator/QA contract.
- **Computed-field error:** all three providers supplied a fingerprint even
  though fingerprinting is deterministic program work; the historical values
  were identical and must be ignored during replay.
- **Validator overconstraint:** non-character power centers (notably an object/
  evidence holder) were rejected by the character-only controller rule.
- **QA shape mismatch:** the historical outputs contain meaningful performance,
  emotion and information progression, but legacy QA reads different field names
  and reports weak/zero coverage.

## 6. What is genuinely directing-weak?

The raw outputs contain scene-specific objectives, questions, evidence anchors,
progression, and character tactics. They are not sufficient to claim “professional
director pass”, but the available evidence supports at least `USABLE` or
`INCONCLUSIVE` content diagnostics after normalization. The old `STRATEGY_WEAK`
outcomes conflate protocol invalidity with content quality and cannot be used as
the Phase 1.1 content verdict.

## 7. False template leakage

`compare_strategies()` marks a hard failure whenever provider fingerprints match,
regardless of creative content. The canary shows empty `exact_core_fields` and
very low Jaccard similarity (`0.0208–0.0278`) while all three fingerprints are
the same fake provider value. This is a confirmed false positive, not evidence
of repeated creative content. Phase 1.1 must compare a program-owned
`creative_core_fingerprint` that excludes scene IDs, fingerprints, source IDs,
timestamps and metadata, and use exact semantic evidence before a hard failure.

## 8. Legacy V1 assessment

V1 is useful as a readable historical replay format, but it is not suitable as the
future provider output contract. It forces duplicate beat-by-beat arrays, exposes
computed fields to the model, and lets Provider/Validator/QA shapes drift. It must
remain readable for replay while future requests use `director_scene_strategy_ir_v1`
and deterministic compilation to `director_scene_strategy_v2`.

## 9. Missing Phase 1.1 deliverables

The following are absent at audit time and must be produced only after the
corresponding implementation/tests are complete:

`director-quality-v3-phase1-1-semantic-spec.json`,
`director-quality-v3-phase1-1-strategy-ir-schema.json`,
`director-quality-v3-phase1-1-canonical-strategy-v2-schema.json`,
`director-quality-v3-phase1-1-historical-replay.json`,
`director-quality-v3-phase1-1-evaluation-alignment.json`,
`director-quality-v3-phase1-1-distinctiveness-audit.json`,
`director-quality-v3-phase1-1-provider-contract-preview.json`,
`director-quality-v3-phase1-1-format-repair-preview.json`,
`director-quality-v3-phase1-1-recanary-manifest.json`,
`director-quality-v3-phase1-1-provider-free-preflight.json`, and
`director-quality-v3-phase1-1-report.md`.

## Audit conclusion

The first unmet milestone is **Semantic Spec SSOT + model-facing IR**. Proceeding
with provider-free implementation is justified. Phase 1.2 Re-Canary and Shot
Architecture remain explicitly unauthorized until the Phase 1.1 hard gate passes.
