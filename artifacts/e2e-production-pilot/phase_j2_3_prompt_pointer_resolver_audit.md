# Phase J2.3 PromptIR Pointer Resolver Audit

Status: `READY_FOR_REVIEW`

## Exact scope resolution

All current PromptIR resolver paths require canonical `target_media` (`IMAGE` or `VIDEO`) and query the exact `(book, episode, shot, target_media)` pointer. Missing scope returns `PROMPT_IR_POINTER_MISSING`; invalid scope returns `PROMPT_IR_MEDIA_SCOPE_INVALID`; pointer/payload disagreement returns `PROMPT_IR_POINTER_MEDIA_SCOPE_MISMATCH`.

Updated surfaces:

- `core/prompt_ir_phase_e.py`: integrity, current-authority resolver, and currentness validation
- `core/prompt_ir_authority.py`: compatibility wrappers with explicit media scope
- `api/prompt_ir_authority_api.py`: preview and compile reuse keyed by media scope
- `api/generation_canary_api.py`: explicit IMAGE canary scope
- `core/media_authority.py`: execution, candidate, official version, and PromptIR media scope checks
- `core/production_workspace_projection.py`: typed IMAGE/VIDEO PromptIR map

## Callsite status

| Area | Status |
|---|---|
| ORM and Alembic migration | UPDATED |
| Phase E API preview/compile | UPDATED |
| Phase F IMAGE canary | UPDATED |
| OfficialMedia currentness | UPDATED |
| Workspace projection | UPDATED |
| Phase E real pilot resolver probes | UPDATED |
| J3 provider convergence | NOT_APPLICABLE (out of phase) |
| Real provider/media acceptance | BLOCKED_BY_PHASE_BOUNDARY |

## Deterministic checks

- Phase E semantic closure: PASS
- media validation/promotion contract: PASS
- migration chain hardening: PASS
- H2 schema regression: PASS
- provider/LLM/image/video calls: 0
