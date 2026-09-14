# Director Quality V2.4.5A Phase 1 — Scene-Level Repair

Status: `READY_FOR_SCENE_REPAIR_PROTOCOL_CANARY`

Provider-free deterministic analysis; all real provider/media/storage/CI calls are zero.

## Gate metrics

- Root-local ceiling mean/median: **8.466 / 8.4**.
- Bounded Scene Repair ceiling mean/median: **42.6853 / 44.5**.
- Mean gate (+15): **PASS**; median gate (+10): **PASS**.
- Tail reduction: **1.0**; 50% gate: **PASS**.
- Approved Record root-local mean/median: **7.69 / 7.8**.
- Approved Record bounded mean/median: **35.896 / 38.67**; scope gain: **28.206**; tail reduction: **1.0**.
- Average affected shot ratio: **0.907**; no shot topology expansion occurred.

## Per-scene approved and fixture evidence

- `book990402:e1:红伞幻影（二）`: baseline 61.45; root-local Δ2.40; bounded Δ23.55; upper Δ32.15; scope gain 21.15; tail escape=yes; dimensions=PERFORMANCE_DIRECTION,INFORMATION_STRATEGY,EDIT_RHYTHM,EMOTIONAL_PROGRESSION,SHOT_DIVERSITY; affected ratio=0.7000
- `book990402:e2:回声照相馆`: baseline 28.39; root-local Δ6.98; bounded Δ38.67; upper Δ43.66; scope gain 31.69; tail escape=yes; dimensions=SHOT_MOTIVATION,VISUAL_STORYTELLING,PERFORMANCE_DIRECTION,INFORMATION_STRATEGY,EDIT_RHYTHM; affected ratio=0.7273
- `book990402:e2:暗房门口的试探`: baseline 28.61; root-local Δ7.80; bounded Δ40.94; upper Δ45.49; scope gain 33.14; tail escape=yes; dimensions=SHOT_MOTIVATION,VISUAL_STORYTELLING,PERFORMANCE_DIRECTION,INFORMATION_STRATEGY,EDIT_RHYTHM; affected ratio=0.7500
- `book990402:e3:暗房惊魂`: baseline 28.39; root-local Δ10.27; bounded Δ38.67; upper Δ43.66; scope gain 28.40; tail escape=yes; dimensions=SHOT_MOTIVATION,VISUAL_STORYTELLING,PERFORMANCE_DIRECTION,INFORMATION_STRATEGY,EDIT_RHYTHM; affected ratio=0.7273
- `book990402:e3:暗房惊魂（2）`: baseline 28.45; root-local Δ11.00; bounded Δ37.65; upper Δ44.15; scope gain 26.65; tail escape=yes; dimensions=SHOT_MOTIVATION,VISUAL_STORYTELLING,PERFORMANCE_DIRECTION,INFORMATION_STRATEGY,EDIT_RHYTHM; affected ratio=0.7000
- `V21_FIXTURE_01`: baseline 47.80; root-local Δ8.40; bounded Δ47.00; upper Δ32.00; scope gain 38.60; tail escape=yes; dimensions=SHOT_MOTIVATION,PERFORMANCE_DIRECTION,INFORMATION_STRATEGY,EMOTIONAL_PROGRESSION,EDIT_RHYTHM; affected ratio=1.0000
- `V21_FIXTURE_04`: baseline 47.80; root-local Δ9.00; bounded Δ47.00; upper Δ32.00; scope gain 38.00; tail escape=yes; dimensions=SHOT_MOTIVATION,PERFORMANCE_DIRECTION,INFORMATION_STRATEGY,EMOTIONAL_PROGRESSION,EDIT_RHYTHM; affected ratio=1.0000
- `V21_FIXTURE_07`: baseline 50.30; root-local Δ10.00; bounded Δ44.50; upper Δ29.50; scope gain 34.50; tail escape=yes; dimensions=SHOT_MOTIVATION,PERFORMANCE_DIRECTION,INFORMATION_STRATEGY,EMOTIONAL_PROGRESSION,EDIT_RHYTHM; affected ratio=1.0000
- `V21_FIXTURE_08`: baseline 50.30; root-local Δ6.00; bounded Δ44.50; upper Δ29.50; scope gain 38.50; tail escape=yes; dimensions=SHOT_MOTIVATION,PERFORMANCE_DIRECTION,INFORMATION_STRATEGY,EMOTIONAL_PROGRESSION,EDIT_RHYTHM; affected ratio=1.0000
- `V21_FIXTURE_09`: baseline 47.80; root-local Δ8.40; bounded Δ47.00; upper Δ32.00; scope gain 38.60; tail escape=yes; dimensions=SHOT_MOTIVATION,PERFORMANCE_DIRECTION,INFORMATION_STRATEGY,EMOTIONAL_PROGRESSION,EDIT_RHYTHM; affected ratio=1.0000
- `V21_FIXTURE_10`: baseline 50.30; root-local Δ6.00; bounded Δ44.50; upper Δ29.50; scope gain 38.50; tail escape=yes; dimensions=SHOT_MOTIVATION,PERFORMANCE_DIRECTION,INFORMATION_STRATEGY,EMOTIONAL_PROGRESSION,EDIT_RHYTHM; affected ratio=1.0000
- `V21_FIXTURE_11`: baseline 50.30; root-local Δ10.00; bounded Δ44.50; upper Δ29.50; scope gain 34.50; tail escape=yes; dimensions=SHOT_MOTIVATION,PERFORMANCE_DIRECTION,INFORMATION_STRATEGY,EMOTIONAL_PROGRESSION,EDIT_RHYTHM; affected ratio=1.0000
- `fixture:dialogue_power_shift`: baseline 47.80; root-local Δ8.40; bounded Δ47.00; upper Δ32.00; scope gain 38.60; tail escape=yes; dimensions=SHOT_MOTIVATION,PERFORMANCE_DIRECTION,INFORMATION_STRATEGY,EMOTIONAL_PROGRESSION,EDIT_RHYTHM; affected ratio=1.0000
- `fixture:multi_character`: baseline 46.30; root-local Δ8.34; bounded Δ50.30; upper Δ35.30; scope gain 41.96; tail escape=yes; dimensions=SHOT_MOTIVATION,PERFORMANCE_DIRECTION,INFORMATION_STRATEGY,EDIT_RHYTHM,EMOTIONAL_PROGRESSION; affected ratio=1.0000
- `fixture:prop_continuity`: baseline 50.30; root-local Δ14.00; bounded Δ44.50; upper Δ29.50; scope gain 30.50; tail escape=yes; dimensions=SHOT_MOTIVATION,PERFORMANCE_DIRECTION,INFORMATION_STRATEGY,EMOTIONAL_PROGRESSION,EDIT_RHYTHM; affected ratio=1.0000

## What Scene-Level adds

Scene-level repair expands root-local scope by bounded multi-shot coverage, up to five selected creative dimensions, and cross-shot progression (camera, emotion, edit, performance and information reveal) while preserving facts, identities, assets, continuity and topology. It removes the approved-record zero-uplift limitation without changing scorer weights or gates.

## Dimension contribution breakdown

- DRAMATIC_CLARITY: selected in 0/15 scenes; aggregate weighted contribution **0.0**.
- SHOT_MOTIVATION: selected in 14/15 scenes; aggregate weighted contribution **193.56**.
- EMOTIONAL_PROGRESSION: selected in 11/15 scenes; aggregate weighted contribution **36.6**.
- VISUAL_STORYTELLING: selected in 4/15 scenes; aggregate weighted contribution **34.848**.
- SPATIAL_CLARITY: selected in 0/15 scenes; aggregate weighted contribution **0.0**.
- PERFORMANCE_DIRECTION: selected in 15/15 scenes; aggregate weighted contribution **136.04**.
- EDIT_RHYTHM: selected in 15/15 scenes; aggregate weighted contribution **83.208**.
- INFORMATION_STRATEGY: selected in 15/15 scenes; aggregate weighted contribution **108.832**.
- POWER_DYNAMICS: selected in 0/15 scenes; aggregate weighted contribution **12.5**.
- SHOT_DIVERSITY: selected in 1/15 scenes; aggregate weighted contribution **34.715**.

## Safety and validation

- Contract pass: **True**; fact boundary: **True**; topology: **True**.
- Over-directing: **within policy**; shot inflation: **True**.
- Camera coherence, emotion progression, edit rhythm, information chronology and performance character IDs are validated per scene and remain within contract.
- Scene Repair IR deterministically compiles to the existing canonical patch schema; a new patch engine is not required.
- CV status: `CV_CEILING_NOT_MEASURABLE` (provider-free synthetic intervention; no CV is fabricated).

## Provider-free preflight

- real_llm_calls=0; real_mimo_calls=0; production=0; storyboard=0; media=0; image=0; video=0; object_storage=0; shadow=0; CI=not_run.

## Final gate

`READY_FOR_SCENE_REPAIR_PROTOCOL_CANARY` — Phase 2 real MiMo canary is **not automatically executed**; waiting for explicit approval.
