# Phase E PromptIR semantic compilation and model adapter gap audit

## Scope

Phase E closes the boundary from the current `StoryboardProductionSnapshot` to
structured PromptIR v2 and provider neutral generation payloads. Compilation is
deterministic, provider free, and consumes no legacy prompt column as semantic
authority.

## Authority audit

| Boundary | Result | Evidence |
| --- | --- | --- |
| PromptIRVersion / Authority / Pointer | Current pointer is the only resolvable version; scene compile writes all shots after pure compilation succeeds | `api/prompt_ir_authority_api.py`, `core/prompt_ir_phase_e.py` |
| Prompt compiler handoff | Snapshot rows carry the structured handoff and visual semantic handoff; action beats fall back to immutable projection payload when the handoff copy is absent | `core/storyboard_materializer.py` |
| `visual_prompt_static/motion/final` | Not read by Phase E and never written by the snapshot compiler | semantic closure tests |
| Model adapter | Deterministic registry with explicit model profile and capability gates | `MODEL_ADAPTER_REGISTRY`, generation payload artifact |
| Generation payload | `generation_payload_v1` includes PromptIR reference, policy, model profile, adapter version, semantic projection, and fingerprint | `episode_01_generation_payload_phase_e.json` |
| Visual Asset Authority | Required asset classes must resolve through explicit bindings; ambiguous historical pointers are rejected rather than selected by newest row | `_production_asset_authority()` |
| Provider readiness | Qualification is distinct from model generation readiness; this pilot has zero provider, LLM, image, and video calls | Phase E trace |
| Legacy bypass | A non-empty legacy `visual_prompt_final` does not change adapter output | `test_prompt_ir_phase_e_semantic_closure.py` |
| Stale propagation | Snapshot freshness is required; current materialization and asset lineage are part of the authority envelope | compiler and trace evidence |
| Tamper validation | Payload fingerprint and exact structured semantic diff reject missing, extra, and changed fields | semantic closure tests |
| Current-only resolver | Scene compile resolves current Storyboard materialization pointers before compiling; no latest/max fallback is used | scene compile endpoint |

## Semantic fields carried

PromptIR v2 preserves subjects, props, information references, reaction
contract references, coverage roles, camera framing/orientation/support and
movement trigger/target/end condition, temporal intent, visibility, axis and
spatial references. The adapter serializes these sections without adding style,
lens, lighting, quality, or other un-authorized visual facts.

## Pilot result

- Scene `E01_SC001`: 8 PromptIR artifacts.
- Scene `E01_SC002`: 7 PromptIR artifacts.
- Total: 15 PromptIR artifacts, one per `plan_shot_id`.
- Adapter previews: 15 deterministic `image_generic_adapter_v1` payloads.
- Provider / LLM / image / video calls: 0.
- No database migration was added in Phase E.

