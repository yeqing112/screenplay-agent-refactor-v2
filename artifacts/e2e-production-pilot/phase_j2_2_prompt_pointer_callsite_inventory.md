# Phase J2.2 PromptIR Pointer Callsite Inventory

Inventory generated from repository-wide `rg` inspection at baseline `144e2a61f9355051127539a6cec4da7c9b3bb936`. No production callsite was changed in this review.

| File / lines | Current behavior | Required `target_media` source | Fail-closed / implementation impact |
|---|---|---|---|
| `models/prompt.py:73-86` | `PromptIRPointer.storyboard_shot_id` is `unique=True`; no media scope | Add persisted scope discriminator derived from pointed payload | Remove shot-only uniqueness; add exact composite unique/check contract |
| `alembic/versions/u4d5e6f7g8h9_add_prompt_ir_authority.py:66-81` | Creates inline unnamed SQLite unique on `storyboard_shot_id` and two named indexes | Migration backfill from `PromptIRVersion.payload_json.generation_policy.target_media` | SQLite batch rebuild; block malformed rows; named `uq_prompt_ir_pointer_media_scope` |
| `api/prompt_ir_authority_api.py:147` | Adapter preview selects first pointer by shot | Explicit request policy target, validated before query | Missing scope → `PROMPT_IR_MEDIA_SCOPE_REQUIRED`; query exact scope |
| `api/prompt_ir_authority_api.py:166` | Calls resolver without target; allows optional policy override | `req.generation_policy.target_media`, normalized and matched | Do not read IMAGE then override for VIDEO |
| `api/prompt_ir_authority_api.py:226` | `existing_by_shot` collapses all current pointers to one row | Key `(storyboard_shot_id, policy.target_media)` | IMAGE compile must not replace VIDEO pointer |
| `api/prompt_ir_authority_api.py:239,251` | Integrity checks call shot-only resolver | Existing pointer's validated scope, then requested compile scope | Historical check stays separate; no cross-media comparison |
| `api/prompt_ir_authority_api.py:301` | Creates/updates one pointer per shot | `ir["generation_policy"]["target_media"]` | Derive scope from compiled IR, never caller field |
| `core/prompt_ir_phase_e.py:688-722` | `validate_prompt_ir_integrity` looks up one shot pointer | Required `target_media` argument | Exact pointer scope plus payload scope invariant |
| `core/prompt_ir_phase_e.py:725-800` | Current resolver uses shot-only `.first()` and current policy | Required target; stored scope policy + current shared snapshot | No `.first()`, latest, or IMAGE default; preserve historical validator independence |
| `core/prompt_ir_phase_e.py:802-804` | Current-authority wrapper forwards shot-only arguments | Forward explicit target | Mismatch returns stable 409 |
| `core/prompt_ir_authority.py:278-314` | Compatibility resolver signatures omit target | Forward required scope to Phase E | Wrapper cannot infer from role or latest version |
| `api/generation_canary_api.py:260,267` | Phase F preview finds shot-only pointer, then resolver; later enforces IMAGE | `ProductionGenerationSelection.target_media` (currently IMAGE-only can pass explicit IMAGE) | Future VIDEO path must query VIDEO scope; invariant before execution |
| `core/media_authority.py:361-404` | Authority snapshot selects first shot pointer and compares candidate to it | `execution.target_media` after candidate/execution type validation | IMAGE candidate must compare IMAGE pointer; VIDEO must compare VIDEO pointer |
| `core/media_authority.py:693-721` | Strict OfficialMedia resolver selects shot-only PromptIR pointer | `execution.target_media`; verify execution/candidate/version media types first | Never derive target from `media_role`; no cross-media fallback |
| `core/production_workspace_projection.py:261,351-363` | Loads all pointers but chooses one per shot and emits no media scope | Group by `(shot_id,target_media)` and expose target in API snapshot | Frontend must stop assuming one PromptIR per shot |
| `scripts/phase_e_prompt_ir_real_pilot.py:59,166-179,205-234,318-325,417-525,558,597-618,666` | Pilot assertions/dictionaries/orderings collapse by shot or `.first()` | Use `(shot_id,target_media)` keys; explicit scope in every resolver call | Test/pilot evidence must cover dual scope and no fallback |
| `scripts/run_phase_f_real_authority_pilot.py:84,96` | Projects pointer without scope and orders by shot | Include target scope and select requested IMAGE | Pilot snapshot schema changes; no silent default for general APIs |
| `scripts/run_phase_i_official_media_binding_pilot.py:158` | Fixture creates pointer without target | Derive from fixture payload policy | Fixture must assert pointer/payload equality |
| `tests/test_media_validation_promotion_contract.py:188,205,234` | Fixtures create shot-only pointers | Add explicit IMAGE/VIDEO scope from payload | Add mismatch and cross-media currentness tests |
| `tests/test_prompt_ir_phase_e_semantic_closure.py:186,209,214` | Fixture and resolver calls assume one pointer | Pass target and assert response scope | Legacy tests need explicit IMAGE; add missing VIDEO failure case |
| `scripts/verify_migration_chain.py:51` | Verifies table existence only | Add post-migration scope/constraint checks | Must inspect named composite unique and target column |
| `web/src/domain/productionWorkspace.ts`, `web/src/components/ProductWorkspaceStoryboardSection.tsx` | Consumes stage/snapshot fields, no direct DB pointer query | API response carries `target_media` per PromptIR item | UI generation actions explicitly send IMAGE or VIDEO; no one-PromptIR assumption |

## Coverage conclusion

The production authority paths are not limited to the four resolver files: compile, adapter preview, canary execution, media currentness, workspace projection, pilots, migration verification, fixtures, and frontend snapshot consumers all encode the old one-pointer assumption. The implementation phase must update the complete inventory before migration is considered safe.
