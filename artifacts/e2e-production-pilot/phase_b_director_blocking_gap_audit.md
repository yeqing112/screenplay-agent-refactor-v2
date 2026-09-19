# Phase B DirectorTreatment / SceneBlocking Gap Audit

- Pilot: `990401 / Episode 1 / 红伞倒影`
- Baseline: `87a510e`
- Scope: `ScriptIR → DirectorTreatment → SceneBlocking`
- Authority policy: reuse `DirectorTreatment` / `SceneBlocking` version, pointer, and authority envelopes.

## Evidence inspected

- `core/director_treatment.py::build_shadow_treatment`
- `core/scene_blocking.py::build_scene_blocking_v2`
- `models/director_treatment.py`
- `models/scene_blocking.py`
- Phase A `episode_01_script_ir_phase_a.json`
- Existing pilot artifacts `episode_01_director_treatment.md` and `episode_01_scene_blocking.md`

## DirectorTreatment findings

| Requirement | Current evidence | Finding |
|---|---|---|
| Scene objective | `dramatic_objective` is assembled from first/last event; empty scenes become generic phrases | **Gap: placeholder / non-specific objective** |
| Character direction | `character_intents` defaults every character to `完成本场戏的叙事目标`, generic obstacle/tactic | **Gap: generic actor direction** |
| Audience question | fixed generic question or reveal template | **Gap: generic audience question** |
| Visual strategy | one fixed sentence for every scene | **Gap: generic visual strategy** |
| Editing rhythm | one fixed sentence for every scene | **Gap: generic editing rhythm** |
| Per-character strategy | no strategy shift, performance notes, or avoid contract | **Gap: missing per-character strategy** |
| Beat bindings | `beat_map` carries source beats but no director intent/performance/information/tempo binding | **Gap: missing beat bindings** |
| Information strategy | single generic scene string; no ordered audience/character visibility records | **Gap: missing information strategy** |
| Suspicion transfer | no explicit suspicion transfer decision | **Gap: missing suspicion transfer** |
| Performance arc | no scene-level arc or beat-level reaction intent | **Gap: missing performance arc** |
| Audience state | no `audience_state_in/out` | **Gap: missing audience state** |

**Director production gate:** currently must be blocked with `DIRECTOR_TREATMENT_PLACEHOLDER` and the more specific missing-field gates. The existing approved markdown is not sufficient evidence of a materialized V2 treatment.

## SceneBlocking findings

| Requirement | Current evidence | Finding |
|---|---|---|
| Spatial rule | existing artifact says `由确定性调度补齐` | **Gap: placeholder spatial rule** |
| Zone model | V2 only projects optional anchors/zones; pilot has no materialized zone graph | **Gap: no materialized zone model** |
| Entrances/exits | participants omit entry/exit when ScriptIR has no source blocking | **Gap: missing entrances/exits** |
| Movement paths | V2 carries only optional source path and otherwise empty list | **Gap: missing movement paths** |
| Facing | defaults to another character/id or `scene_action` | **Gap: weak/non-materialized facing** |
| Eyelines | defaults to another participant; no beat-bound eyeline records | **Gap: missing beat-bound eyelines** |
| Prop spatial state | no red umbrella, broken rib, handbag, apple, water, fiber state timeline | **Gap: missing prop spatial state** |
| Interaction positions | no interaction contract records | **Gap: missing interaction positions** |
| Beat-bound blocking | `beat_transitions` says `preserve_existing_spatial_relationship` for every beat | **Gap: not materialized per beat** |
| Axis declaration | `camera_axis` is a camera-oriented placeholder and is not grounded in interaction geometry | **Gap: meaningless camera axis declaration / leakage risk** |
| Treatment binding | no explicit director-direction provenance on blocking decisions | **Gap: missing Treatment → Blocking binding** |

**Blocking production gate:** currently must be blocked with `BLOCKING_NOT_MATERIALIZED`, plus spatial, entry/exit, beat coverage, eyeline, prop, and camera leakage gates as applicable.

## Locked Phase A invariants

The Phase B authoring input must remain the current Production-qualified ScriptIR and must not rewrite ScriptIR, dialogue, ScriptBlock order, character identity, SceneTransitionContract, red umbrella facts, or deception semantics (`D029` before evidence escalation; `D027` after evidence escalation).

## Required closure

1. Enrich the existing DirectorTreatment payload and validator while preserving its existing authority/pointer model.
2. Materialize a scene-specific SceneBlocking payload with relative geometry where locked geometry is absent; do not invent camera/lens/shot decisions.
3. Run the candidate → validate → targeted repair → confirm → authority flow; failed candidates must not move pointers.
4. Produce human-readable and JSON pilot artifacts plus a provenance trace.

## Conclusion

Current state is **not Production-qualified for Phase B**. The correct fail-closed reasons are:

- `DIRECTOR_TREATMENT_PLACEHOLDER`
- `BLOCKING_NOT_MATERIALIZED`

Phase B implementation may proceed without changing ScriptIR or entering ShotPlan/Storyboard/PromptIR/Visual work.
