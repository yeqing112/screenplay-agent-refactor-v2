# Visual Asset Authority and Authoring Activation Report

Stage: `VISUAL_ASSET_AUTHORITY_AND_AUTHORING`
Provider policy: **0 external calls**
Branch: `codex/shot-plan-authority-contract`

## Baseline Audit

The legacy registry used mutable `VisualMakeup`, `VisualLocation` and
`VisualProp` rows, with display-name lookups and prompt text mixed into the
same records. `VisualReferenceAsset(status=locked)` had no mandatory version
lineage, checksum or scope contract. PromptIR could receive caller-supplied
asset authority rather than resolving a current immutable visual version.

## Final As-Built Verification

- Stable identities are `book:{book_id}:character:{character_id}`,
  `book:{book_id}:scene:{scene_id}` and `book:{book_id}:prop:{prop_id}`.
  Production registry sync rejects missing canonical IDs and never creates a
  production authority from a display name.
- `VisualAssetVersion` is the immutable structured snapshot. `VisualAssetPointer`
  selects the current version by asset key and scope; mutable legacy cards remain
  UI/authoring projections.
- Character canonical facts are separate from episode/scene/shot variants;
  scene look is separated from SceneBlocking geometry; prop look is separated
  from ShotPlan continuity state.
- Source constraints, production authoring decisions, variants, derived
  constraints, reference media and advisory legacy text have distinct authority
  classes. Source conflicts fail closed.
- `VisualAuthoringDecisionRequest` and `VisualAuthoringDecision` provide the
  pending → review → confirmed boundary. No provider resolves authoring.
- Reference authority requires asset-version lineage, scope, image identity,
  checksum, storage/import provenance, token mapping and lock revision.
  Legacy locked rows are classified as `LEGACY_REFERENCE_MIGRATION_REQUIRED`
  and are not auto-promoted.
- PromptIR production compilation resolves assets only through current
  `VisualAssetPointer` / `VisualReferenceAuthority`. It reports
  `ASSET_AUTHORING_PENDING`, `ASSET_REFERENCE_PENDING` or
  `ASSET_REFERENCE_READY`; no visual facts are invented.
- Version/reference changes propagate staleness only to bound PromptIR payloads.
- Reference generation creates only a `READY_FOR_PROVIDER_CANARY` draft with
  `provider_not_called=true`.

## Readiness Snapshot

- Current workspace database: empty/unseeded; authoritative asset counts are
  `ASSET_AUTHORING_PENDING=0`, `ASSET_REFERENCE_PENDING=0`,
  `ASSET_REFERENCE_READY=0` until assets are explicitly authored.
- Contract-level replay covers all three readiness states and provider-free
  reference drafts.

## Verification

- Visual authority + PromptIR + registry targeted suite: **35 passed**.
- Authority API integration: **1 passed**.
- SceneBlocking / ShotPlan / PromptIR impacted regression: **63 passed**.
- Full backend: **1524 passed, 5 known historical baseline failures**.
- Golden pilot regression: **9 passed** (`5/5` golden fixtures covered).
- Provider calls: **0**.
- Media writes: **0**.
- Frontend: `FRONTEND_NOT_TOUCHED`.

## Known Baseline Failures

1. Offline replay test expects retired branch `codex/unify-formal-workspace`.
2. Retired provider-canary test expects historical worktree behavior.
3–4. Fresh integration pilot reads an unseeded local database without the
   historical ScriptIR tables.
5. Targeted missing-fact API test observes an existing database-isolation
   baseline snapshot.

## Migration Gate

`f05ab1af29bc` remains intentionally unchanged as
`FRESH_DB_MIGRATION_BASELINE_BLOCKER`. No visual/provider canary is authorized
until `MIGRATION_CHAIN_HARDENING` closes that gate.

Completion marker: `VISUAL_ASSET_AUTHORITY_AND_AUTHORING_READY`
