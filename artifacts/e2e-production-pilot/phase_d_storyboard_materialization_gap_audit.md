# Phase D Storyboard Materialization Gap Audit

## Scope

The Production boundary is the current ShotPlan Authority →
`storyboard_handoff_v1` → `StoryboardMaterializationSet` →
`StoryboardShot` projection.  Phase D adds validation around that existing
chain without adding a database column or a second creative authority.

## Findings and closure

| Area | Previous gap | Phase D closure | Authority class |
| --- | --- | --- | --- |
| `StoryboardMaterializationSet` | Set stored ShotPlan lineage but did not fully revalidate Blocking and handoff semantics | Set envelope now binds current ShotPlan, current Blocking, handoff schema/projection/source fingerprint and handoff fingerprint; resolver recomputes them | `STRUCTURAL_MATERIALIZATION_METADATA` |
| `StoryboardMaterializationPointer` | Current pointer existed, but freshness was not enough to prove a valid set | Resolver reads only the explicit scene pointer and rejects stale, missing, superseded or tampered targets | `STRUCTURAL_MATERIALIZATION_METADATA` |
| `StoryboardShot` | Row fields could be changed without a complete semantic check | Projection payload and structured visual semantic handoff are fingerprinted; any mismatch marks the Set and rows stale | `SHOT_PLAN_PROJECTION`, `PRODUCTION_CONTINUITY_STATE`, `ASSET_IDENTITY_BINDING` |
| Resolver | Checked count/order and a basic projection fingerprint | Revalidates ShotPlan Authority, Blocking Authority, handoff fingerprint, Set fingerprint, exact IDs/order, row fingerprints, semantic payload and prompt-field state | `STRUCTURAL_MATERIALIZATION_METADATA` |
| Visual semantic handoff | Information/reaction/coverage/camera/axis/asset refs were not all carried in one structured payload | Added `storyboard_visual_semantic_handoff_v1`; it contains refs/enums only and no prompt prose | `DOWNSTREAM_HANDOFF_METADATA` |
| Semantic diff | No structured missing/extra gate | Deterministic `compare_shotplan_storyboard_semantics()` reports missing, extra, camera, continuity and asset mismatches before writes | `STRUCTURAL_MATERIALIZATION_METADATA` |
| Asset bindings | Existing bindings were carried but not identity-gated | Scene, declared subject and declared prop identities are checked; reference images/variants are not required | `ASSET_IDENTITY_BINDING` |
| `visual_prompt_*` | Legacy fields could be a prompt bypass | Phase D materialization writes empty fields; resolver rejects premature mutation with `STORYBOARD_PROMPT_PREMATURE_MUTATION` | `MEDIA_STATE` / downstream only |
| Legacy paths | Legacy compatibility materializer remained callable | Production API continues to require `phase_c_semantic_ready`; no legacy Production fallback or latest/max fallback is used | `UNKNOWN_INVALID` when used for Production |

## Explicit authority classes

- `SHOT_PLAN_PROJECTION`: purpose, camera projection, duration intent,
  action/beat refs, information/reaction/coverage refs, subject and prop refs.
- `PRODUCTION_CONTINUITY_STATE`: Blocking state refs, entry/exit snapshots,
  axis, screen side, look direction, continuous-take and cut policy.
- `ASSET_IDENTITY_BINDING`: canonical scene, character and prop identities
  already declared by ShotPlan.
- `STRUCTURAL_MATERIALIZATION_METADATA`: Set/Pointer identity, order,
  fingerprints, schema and lineage.
- `DOWNSTREAM_HANDOFF_METADATA`: the structured visual semantic handoff and
  PromptIR boundary metadata.
- `MEDIA_STATE`: media remains `NOT_GENERATED`; no image/video or prompt
  compilation is started.
- `UNKNOWN_INVALID`: legacy or unclassified values cannot make a Production
  Set fresh.

`STORYBOARD_CREATIVE_DECISION` was not introduced.  Storyboard does not infer
framing, movement, composition, sides, duration, props or action semantics.

## Fingerprint and freshness contract

Each Set binds `storyboard_handoff_v1` schema/projection/source/handoff
fingerprints, ShotPlan and Blocking Authority fingerprints, exact expected
count and ordered `plan_shot_id` values.  Each row binds the source ShotPlan
Authority fingerprint, handoff shot fingerprint, semantic projection and
projection fingerprint.  Resolver recomputes all of these from the current
Authority pointers.

An upstream ShotPlan or Blocking change, a handoff/set/row tamper, missing or
extra row, order change, semantic loss/addition, or prompt-field mutation marks
the Set `STALE`, marks its rows stale/blocked, and returns HTTP `409`.  It does
not repair the row in place.

## Atomicity and identity

Production materialization validates the complete handoff, semantic diff,
cardinality and asset identities before creating the Set.  A failed candidate
does not move the Pointer.  A repeated request with the same deterministic Set
fingerprint reuses the existing fresh Set; it never selects a latest Set by
timestamp or ID.

The real Phase D pilot runs this sequence against a temporary SQLite database
migrated through Alembic.  It records persisted Set, Pointer and StoryboardShot
IDs in `episode_01_phase_d_trace.json`; negative cases restore a valid baseline
database before each mutation so no test relies on repairing a stale Set.

The resolver also compares mutable StoryboardShot columns with the protected
projection payload.  A direct camera, duration, purpose or state column edit
cannot remain fresh by leaving `meta_info.projection_payload` untouched.

## Out of scope

No PromptIR compilation, prompt prose, image/video generation, provider call,
visual variant selection or database migration is part of Phase D.
