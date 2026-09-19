# Phase A Timeline Fail-Closed Audit

## Semantics

- `timeline_origin=EXPLICIT` means the authoring payload supplied `scene.script_blocks`; Production accepts only this value.
- Missing timelines receive `timeline_origin=LEGACY_INFERRED` and may receive a deterministic readable fallback for Creative Draft only.
- `UNKNOWN` and invalid origins are not production eligible.

## Production rules

- Production quality evaluation adds `SCRIPT_TIMELINE_NOT_EXPLICIT` for every scene without an explicit origin.
- `SCRIPT_BLOCK_ORDER_REQUIRED`, `SCRIPT_BLOCK_ORDER_CONFLICT`, `SCRIPT_BLOCK_REF_MISSING`, `SCRIPT_BLOCK_TYPE_INVALID`, `SCRIPT_BLOCK_TARGET_MISSING`, and coverage failures remain hard gates.
- Explicit invalid `order` values are preserved for validation; the normalizer does not renumber them.
- Missing refs are preserved as missing; no array-index identity is guessed.
- Authority activation runs the Production creative quality gate before creating the authority envelope.
- Production Reader rendering rejects missing/inferred/invalid timelines and never calls the fallback path.

## Legacy rules

Creative Draft and legacy reconstruction may infer a timeline and render a readable preview, but the scene remains `LEGACY_INFERRED` and cannot activate as Production authority.

## Story-specific logic removal

`core/script_ir.py` no longer scans dialogue text or knows any sample-story names. `open_questions` are copied only from the input payload. The pilot ScriptIR input explicitly carries `OPEN_QUESTION_REQUIRES_FUTURE_RESOLUTION` for the two-ticket question.

## Reader diff

The approved Reader prose is unchanged in scene content, causal order, D029/D027 placement, and the red-umbrella suspense chain. Only timeline provenance was added to ScriptIR metadata.

## Authority activation

Activation now fails closed with the first applicable timeline or creative-quality code before writing the production authority envelope.

## Verification

Targeted timeline, renderer, creative-quality, ScriptIR, authority-activation, and Reader API tests are run for this change. Golden regression remains 5/5. Full-backend historical failures are reported separately when present.

## Current verification record

- Timeline fail-closed regression tests: 3 passed.
- Script creative quality / ScriptIR / renderer targeted suite: 15 passed.
- Golden regression: 5/5 passed.
- Full backend: 1516 passed, 35 failed, 926 warnings. The failures are historical integration fixtures that activate minimal ScriptIR payloads without explicit `script_blocks`, plus unrelated pre-existing branch/provider checks; they now surface the intended `SCRIPT_TIMELINE_NOT_EXPLICIT` blocker where applicable. No unrelated source files were changed to mask them.
- Frontend: no frontend files or build scripts were touched.
- Migration: no database schema migration required.

Additional closure checks:

- Inferred scenes serialize `production_eligible=false`; explicit scenes serialize `production_eligible=true`.
- Explicit block aliases such as `action_ref`/`dialogue_ref` are not promoted into `ref`; missing `ref` remains missing and emits `SCRIPT_BLOCK_REF_MISSING`.
