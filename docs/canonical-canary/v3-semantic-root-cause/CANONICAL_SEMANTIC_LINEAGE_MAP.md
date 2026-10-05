# Canonical Semantic Lineage Map V3

Run: `20261005T095639Z`

This map follows persisted semantic fields from source text through canary selection. It is provider-free and read-only.

## Stages

| Stage | Schema/model | Persistence | Writer | Reader | Legacy skip | Empty allowed |
|---|---|---|---|---|---:|---:|
| `source_text_screenplay` | `Chapter.content / Script.content` | `chapters.content; scripts.content` | `book/script import and pipeline content preparation` | `core.script_ir.resolve_script_payload and API scene resolution` | `True` | `True` |
| `fact_snapshot` | `FactSnapshot / FactRecord` | `fact_snapshots.records_json; fact_records` | `fact snapshot preparation` | `DirectorTreatment/SceneBlocking authority` | `True` | `True` |
| `script_ir` | `ScriptIRVersion` | `script_ir_versions.payload_json` | `core/script_ir.py:131` | `core/script_ir.py:332` | `True` | `True` |
| `episode_scene_semantics` | `ScriptIR scenes[]` | `payload_json.scenes[].participants/characters/dialogues` | `core/script_ir.py:189` | `scene blocking preview and treatment authority` | `False` | `True` |
| `director_treatment` | `DirectorTreatment` | `director_treatments.character_intents; beat_map` | `DirectorTreatment proposal/confirmation API` | `core.scene_blocking and core.phase_c_shot_plan` | `True` | `True` |
| `scene_blocking` | `SceneBlocking` | `scene_blockings.participants; spatial_model.initial_state/beat_spatial_states` | `api/scene_blocking_api.py:199` | `core/scene_blocking.py:340` | `True` | `True` |
| `shot_plan` | `ShotPlan` | `shot_plans.shots JSON; shots[].subjects/dialogue/asset_bindings` | `core/phase_c_shot_plan.py:366` | `core.storyboard_handoff.project_shot_design_to_storyboard_handoff` | `True` | `True` |
| `visual_semantic_handoff` | `visual_semantic_handoff` | `StoryboardShot.meta_info.visual_semantic_handoff` | `core/storyboard_visual_semantics.py:181` | `core.canonical_canary_selection.extract_canary_semantic_features` | `True` | `True` |
| `canonical_storyboard_projection` | `StoryboardShot` | `storyboard_shots.dialogue; meta_info.projection_payload; meta_info.visual_semantic_handoff` | `core/storyboard_materializer.py:161` | `core/storyboard_materializer.py:581` | `True` | `True` |
| `prompt_ir_compile_input` | `PromptIRVersion / PromptIRPointer` | `prompt_ir_versions.payload_json; prompt_ir_pointers` | `core/prompt_ir_phase_e.py:556` | `generation readiness and provider adapter` | `True` | `True` |
| `production_canary_selector` | `canonical semantic inventory` | `docs/canonical-canary/v2-semantic-selection/*.json` | `core/canonical_canary_selection.py:224` | `core/canonical_canary_selection.py:314` | `False` | `False` |

## Proven boundary

- Function: `api/scene_blocking_api.py:292`
- Production preview compiled an empty initial_state even when SceneBlocking participants were populated; the compiled states and Phase C subjects then remained empty.
- Repair: initial_state_from_participants projects declared participant identity into the blocking compiler seed.

## Field-level interpretation

- Character identity is authoritative only when it is present in ScriptIR/SceneBlocking/ShotPlan semantic fields; `prompt_compiler_handoff.asset_identity_bindings` is excluded.
- Dialogue is independently traced through structured source fields, ScriptIR dialogues, ShotPlan dialogue, StoryboardShot dialogue, and PromptIR payloads.
- Missing PromptIR is a downstream readiness condition and was not compiled during this audit.
