# Visual Authoring Provider Canary

## Boundary result

Provider is wired as `PROPOSE_ONLY`. A successful provider response is persisted only as `VisualAuthoringProposal` with status `REVIEW_REQUIRED`. The route never creates a `VisualAssetVersion`, moves a `VisualAssetPointer`, creates a `VisualReferenceAuthority`, marks downstream PromptIR stale, or invokes image/video providers.

## Implemented contract

- `visual_authoring_provider_contract_v1`
- `visual_authoring_proposal_v1`
- Explicit `model_profile_id`; no default LLM fallback.
- Explicit `confirmed_provider_call=true`; missing confirmation returns `PROVIDER_CALL_CONFIRMATION_REQUIRED` before any LLM call.
- One request, one asset, one logical provider call per invocation.
- `core.llm.call_llm_json` is reused with parser retries disabled and bounded transport attempts.
- Audit stores hashes, safe provider metadata, usage, latency, validation status and transport attempt count; credentials and raw payloads are not persisted.

## Review boundary

`VisualAuthoringProposal` and `VisualAuthoringDecision` are separate tables. Approval requires `confirmed=true`, revalidates against the current request, creates a Decision only, and does not activate a version or pointer in this stage.

## Verification

`tests/test_visual_authoring_provider_canary.py`: 5 passed.

The deterministic suite confirms missing confirmation produces zero provider calls, valid output stops at `REVIEW_REQUIRED`, identical request fingerprints deduplicate, forbidden/source-conflicting output is rejected, unknowns are preserved, and approval does not create a version or pointer.

- Production/authority targeted backend: 15 passed.
- Full backend: 1341 passed, 1 historical failure in `test_director_quality_v3_final_spine_topology_preflight_wiring.py` (`HISTORICAL_RECANARY_RETIRED` is returned before the test's older worktree assertion).
- Frontend: 49 files / 291 passed.
- Frontend build: PASS.
- Deterministic Golden: 5/5.
- Migration bootstrap (`init_db` on isolated SQLite): PASS.
- `alembic check` against the developer database remains blocked by pre-existing schema/index drift; no user database was changed by this stage.

## Real provider status

One disposable character request was used with the explicit `local-llm-2vydoz` / `mimo-v2.5` profile. The first HTTP-success response was rejected because it omitted required identity keys; the contract was tightened and the manually retried response passed without relaxing validation. The final proposal is `REVIEW_REQUIRED`. Across the two bounded manual attempts, logical provider calls and transport calls were both 2; no parser retry, image call, video call, version creation, pointer movement, reference-authority mutation, or PromptIR stale propagation occurred.

## Next gate

The visual authoring provider canary is now closed at `REVIEW_REQUIRED`. Do not enter reference-image, director, scene-blocking, shot-plan, video, or media execution canaries from this stage. Human review of the proposal is the only next action in this domain.

Readiness token: `VISUAL_AUTHORING_PROVIDER_CANARY_READY`

## Delivery

- Branch: `codex/unify-formal-workspace`
- Commit: `38fc155`
- Remote: `origin/codex/unify-formal-workspace`
