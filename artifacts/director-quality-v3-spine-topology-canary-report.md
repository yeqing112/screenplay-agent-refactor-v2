# Director Quality V3 — Spine → Topology Canary

**Status:** `DIRECTOR_V3_SPINE_TOPOLOGY_CANARY_FAILED`

## Baseline Audit

- Frozen cohort: 3 approved Strategy Authority scenes; base commit `36e7efb`.
- System prompts, contracts and six request templates were frozen before the first call.
- No old Shot Architecture, ShotPlan, Storyboard or media output was supplied to either provider prompt.

## Final As-Built Verification

- Original real MiMo calls: **6** (Spine 3, Skeleton 3); replay provider calls: **0**; retries: **0**.
- Spine Protocol/Authority/Coverage: 0/3 / 0/3 / 0/3; Strong/Usable: 0/3; future leaks: 0; mechanical beat→segment: 0.
- Skeleton Protocol/Authority/Coverage: 0/3 / 0/3 / 0/3; forbidden execution fields: 0; canonical graph refs: 0.
- Reaction nodes: 0; missing semantic stimulus: 0; Binder edges: 0; ambiguous/missing/future/self-edge: 0/0/0/0.
- Topology Strong/Usable: 0/3; mechanical beat→node: 0; hard template leakage: `False`.

## Scene Results

- `book990402:e3:暗房惊魂`: Spine=SPINE_INVALID, segments=3; Topology=TOPOLOGY_INVALID, nodes=9; Binder=PASS
- `book990402:e3:暗房惊魂（2）`: Spine=SPINE_INVALID, segments=3; Topology=TOPOLOGY_INVALID, nodes=4; Binder=PASS
- `book990402:e2:回声照相馆`: Spine=SPINE_INVALID, segments=3; Topology=TOPOLOGY_INVALID, nodes=9; Binder=PASS

## Release Boundary

`READY_FOR_ATOMIC_EXPANSION_CANARY=false`
`ATOMIC_EXPANSION_CANARY_AUTHORIZED=false`
`READY_FOR_PRODUCTION_SHOTPLAN=false`
`READY_FOR_STORYBOARD=false`
`READY_FOR_MEDIA=false`

## Failure Summary

- `book990402:e3:暗房惊魂`: Spine codes=['SPINE_MUST_PRESERVE_UNCOVERED']; Skeleton codes=['SKELETON_IDENTITY_BINDING_INVALID', 'SKELETON_PHASE_MEMBERSHIP_INVALID', 'TOPOLOGY_ROLE_INVALID', 'TOPOLOGY_SECONDARY_ROLE_INVALID', 'UNKNOWN_SPINE_SEGMENT']
- `book990402:e3:暗房惊魂（2）`: Spine codes=['SPINE_FIELD_MISSING', 'SPINE_MUST_PRESERVE_UNCOVERED', 'UNKNOWN_SPINE_SEGMENT_FIELD']; Skeleton codes=['SKELETON_IDENTITY_BINDING_INVALID', 'SKELETON_PHASE_MEMBERSHIP_INVALID', 'TOPOLOGY_ROLE_INVALID', 'TOPOLOGY_SECONDARY_ROLE_INVALID', 'UNKNOWN_SPINE_SEGMENT']
- `book990402:e2:回声照相馆`: Spine codes=['SPINE_FIELD_MISSING', 'SPINE_MUST_PRESERVE_UNCOVERED', 'UNKNOWN_SPINE_SEGMENT_FIELD']; Skeleton codes=['SKELETON_IDENTITY_BINDING_INVALID', 'SKELETON_PHASE_MEMBERSHIP_INVALID', 'TOPOLOGY_ROLE_INVALID', 'TOPOLOGY_SECONDARY_ROLE_INVALID', 'UNKNOWN_SPINE_SEGMENT']
