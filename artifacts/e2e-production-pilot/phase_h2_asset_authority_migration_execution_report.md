# PHASE_H2_ASSET_AUTHORITY_MIGRATION_EXECUTION_REPORT

## Status

`PHASE_H2_ASSET_AUTHORITY_SCHEMA_MIGRATION_READY`

## Migration

- Revision: `a1b2c3d4e5f6`
- Down revision: `z0a1b2c3d4e5`
- New typed tables: Character, Scene and Prop authority/version/pointer tables.
- New binding table: `shot_asset_bindings`.
- Internal FK bridge: `production_asset_authority_registry` and `production_asset_version_registry`.
- Rollback: binding → pointers → authorities → versions → registry tables.

The two registry tables are empty support tables. They let the polymorphic shot binding use real foreign keys without promoting `VisualReferenceAuthority` or changing the existing A–G2 authority chain.

## Verification

- Empty database: upgrade → downgrade to `z0a1b2c3d4e5` → upgrade again passed.
- Fresh SQLite: upgrade passed; all H2 asset tables contain 0 rows.
- Existing A–G2 database fixture: all tracked Script/Director/Blocking/ShotPlan/Storyboard/PromptIR/Candidate/OfficialMedia/Reference counts unchanged.
- Production pilot copy fixture: same count preservation and 0 H2 asset rows.
- Constraints: duplicate pointer rejected; invalid FK rejected; invalid lifecycle status rejected.
- Migration chain: `MIGRATION_CHAIN_HARDENING_READY` with head `a1b2c3d4e5f6`.
- Full backend regression: `1721 passed, 4 failed`; the four failures are the existing baseline failures recorded before H2 (branch/provenance expectation, retired real-path expectation, gray registry expectation, and targeted fact snapshot expectation).

## Isolation and non-goals

- Provider calls: `0`
- Image calls: `0`
- Video calls: `0`
- PromptIR changes: none
- Storyboard changes: none
- ShotPlan changes: none
- Candidate changes: none
- Official Media changes: none
- Legacy visual/reference rows: no backfill and no upgrade
- `FULL_REAL_END_TO_END_PRODUCTION_ACCEPTANCE_TRIGGERED=false`

Detailed columns, indexes, unique constraints, foreign keys, checks, rollback order and count evidence are in [phase_h2_schema_migration_audit.json](phase_h2_schema_migration_audit.json).
