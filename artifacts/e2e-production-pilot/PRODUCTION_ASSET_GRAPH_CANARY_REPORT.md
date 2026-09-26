# Production Asset Graph Canary Report

- Status: `PHASE_PRODUCTION_ASSET_GRAPH_CANARY_COMPLETE`
- Mode: provider-free frozen response fixture
- Episode count: `1`; shot count: `10`
- Authority shape: `CHARACTER_A v1/v2/v3`, `CHARACTER_B v1/v2`, `CHARACTER_C v1`; `SCENE_HOSPITAL v1_day/v2_night/v3_destroyed`, `SCENE_OFFICE v1/v2`, `SCENE_STREET v1`
- Provider calls: `0`
- Approval state: `GRAPH_CANARY_APPROVED`

## Graph evidence

- Authority registry: `6`; Version registry: `12`; typed Pointer: `6`.
- Shot bindings: `25` total (`20` ACTIVE, `5` historical STALE).
- Authority uniqueness, Version lineage, Pointer validity, and multi-shot Binding resolution all pass.

## Pointer rollback

- `CHARACTER_A`: `pav_7cfbf5e720cc37ea30fe9196` → `pav_107886448a469aa15ff448b1` (logical target `v2`).
- Version history preserved: `True`; Authority identity mutations: `0`; Shot definition mutations: `False`.
- Old bindings are retained as STALE audit history and the affected shots are rebound through the formal binding helper.

## Truth boundary

- Source Fact mutations: `0`; ScriptIR mutations: `0`.
- `fixture-provider` and `assets.example.invalid` are frozen canary identities. They are provenance-bearing fixture inputs, not external provider execution or mock assets approved for production.
- Mock asset production approved: `False`; provenance metadata complete: `True`.

## Regression evidence

- Production Asset Graph canary plus H2.2 and workspace projection tests: `22 passed`.
- Full production regression: `1797 passed`.
- Golden regression: `5/5 passed`; release gate invariants: `passed`.
- Frontend tests: `318 passed`; frontend production build: `passed`.
- This report closes `PHASE_PRODUCTION_ASSET_GRAPH_CANARY`; it does not announce `UI_V2_COMPLETE`.
