# Character Consistency Runtime Report

## CHARACTER_CONSISTENCY_RUNTIME_COMPLETE

- **Commit:** `85a67e7` (`feat: add character consistency runtime`)
- **Branch:** `codex/visual-authoring-provider-canary-reconcile`
- **Migration head:** `e1f2a3b4c5d6`
- **Provider calls:** `0` (provider-free consistency and prompt constraint runtime)

## Delivered runtime

- Existing `CharacterProfile` remains the single Character Identity authority and now exposes `description`, `attributes`, and `appearance_profile`.
- `CharacterReferenceAsset` stores typed `portrait`, `full_body`, `costume`, and `expression` relations to existing visual/production asset identities.
- `ShotCharacterBinding` supports multiple characters per shot with role, selected reference identities, appearance rules, and constraint snapshots.
- `inject_character_constraints` validates bindings and derives a prompt candidate while returning the original prompt unchanged.
- `create_character_constrained_prompt_version` appends an immutable `ProductionPromptVersion` and keeps the source prompt in lineage structure.
- Validation fails closed when a shot has no character binding, no reference asset, or missing character constraints.
- APIs are available at both stable and `/api` paths:
  - `GET /characters/{id}`
  - `POST /shots/{id}/characters`
  - `GET /characters/{id}/references`
  - `GET /shots/{id}/characters/validation`
  - `POST /shots/{id}/characters/prompt`

No second asset store, Prompt store, character management system, face swap, face recognition, video generation, or LoRA training path was added.

## Verification

- `pytest -q tests/test_character_consistency_runtime.py` — **3 passed**
- `pytest -q tests/test_migration_chain_hardening.py tests/test_h2_asset_authority_schema.py` — **11 passed**
- Existing asset/Prompt/visual regression set — **34 passed**
- `pytest -q` — **1845 passed, 0 failed**
- `python -m scripts.verify_migration_chain` — **PASS**; fresh and repeated upgrade, legacy replay, schema drift
- `npm run test:golden` — **5/5 passed**
- API route import/registration check — **PASS**
- `python -m compileall` for new runtime modules — **PASS**
- `git diff --check` — **PASS**
