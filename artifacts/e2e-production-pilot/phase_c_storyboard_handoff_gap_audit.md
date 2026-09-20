# Phase C Storyboard Production Handoff Gap Audit

## Boundary

`ShotPlan.shots[]` remains the only canonical creative `ShotDesignDecision[]`.
`storyboard_handoff_v1` is a deterministic projection consumed by the
Production materializer.  The adapter does not read legacy creative copies or
invent defaults.

| Storyboard strict field | Current canonical source | Can derive deterministically? | Legacy duplicate? | Correct action | Classification |
| --- | --- | --- | --- | --- | --- |
| `purpose` | `shot_purpose` | Yes, identity projection | `purpose` may exist in recorded fixture | Project `shot_purpose` only | `DETERMINISTIC_PROJECTION` |
| `camera.shot_size` | `camera_state.framing_class` | Yes | `camera.shot_size` | Project at handoff time | `DETERMINISTIC_PROJECTION` |
| `camera.angle` | `camera_state.orientation` | Yes, enum normalization only | `camera.angle` | Project lower-case normalized value | `DETERMINISTIC_PROJECTION` |
| `camera.movement` | `camera_state.movement` | Yes, enum normalization only | `camera.movement` | Project lower-case normalized value | `DETERMINISTIC_PROJECTION` |
| `camera.speed` | No Phase C canonical speed intent | No | `camera.speed` is a compatibility copy | Make optional and leave unspecified | `NOT_AVAILABLE` |
| `duration` | `duration_hint_seconds` | Yes, positive authored hint | `duration` | Project authored hint; no numeric fallback | `DETERMINISTIC_PROJECTION` |
| `action_beats` | `beat_refs` + `subjects` | Yes, structural action units | Timed `action_beats` may exist in old fixture | Project beat/actor/event refs; omit invented timing | `DETERMINISTIC_PROJECTION` |
| `entry_state` | `spatial_binding.blocking_state_refs[0]` + Blocking Authority | Yes | `entry_state` may exist in old fixture | Resolve first bound Blocking state | `DETERMINISTIC_PROJECTION` |
| `exit_state` | `spatial_binding.blocking_state_refs[-1]` + Blocking Authority | Yes | `exit_state` may exist in old fixture | Resolve last bound Blocking state | `DETERMINISTIC_PROJECTION` |
| `asset_bindings` | canonical `asset_bindings`, with scene/subject/prop refs | Yes | legacy asset links | Preserve identity refs only | `CANONICAL_SOURCE` |
| `continuity_contract` | `axis_contract` + `spatial_binding` + `continuous_take`/`cut_events` | Yes | `continuity_contract` may exist in old fixture | Project axis, sides, look, state refs and cut policy | `DETERMINISTIC_PROJECTION` |
| `beat_id` | first `beat_refs` entry | Yes | legacy `beat_id` | Preserve stable first bound beat | `DETERMINISTIC_PROJECTION` |
| `dialogue` | ScriptIR beat data when present | Yes, otherwise empty | no canonical Phase C dialogue field | Carry existing authored value only; no prose generation | `NOT_AVAILABLE` |
| `transition` | no Phase C canonical field | No | legacy transition | Keep optional empty value | `NOT_AVAILABLE` |
| `lighting` | no Phase C canonical field | No | legacy lighting | Keep optional empty value | `NOT_AVAILABLE` |

## Production decisions

- Camera speed is not required by the Phase C handoff contract.  The
  materializer stores an empty value when no canonical source exists.
- `camera_side` and `screen_direction=maintain` are not generated.  Screen
  sides and look direction come from `axis_contract`.
- Timed `start_seconds=0` / `end_seconds=min(3, duration)` action units are
  not consumed as Production truth.  Action units carry beat and actor refs.
- A missing canonical source, missing Blocking state reference, invalid axis
  continuity, or stale Phase C Authority fails before any materialization
  write.

