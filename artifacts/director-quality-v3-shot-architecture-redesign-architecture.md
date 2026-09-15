# Director Quality V3 — Shot Architecture Generation Architecture Redesign

```text
SceneDirectingStrategy → VisualEditorialSpine → ShotTopologySkeleton → DeterministicGraphBinder → BoundShotTopology → AtomicShotExpansion → shot_architecture_candidate_v3
```

Spine owns macro visual progression; Skeleton owns ordered semantic shot nodes; Binder resolves only program-owned graph IDs and rejects ambiguity, missing and future references; Expansion owns execution detail but cannot mutate topology; Materializer owns canonical IDs, references, provenance and fingerprints. Production and providers remain disconnected.
