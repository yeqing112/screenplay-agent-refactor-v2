# Production UI V3 Retry / Regenerate Contract Audit

## Executive Summary

Phase: PHASE_PRODUCTION_UI_V3_RETRY_REGENERATE_CONTRACT_AUDIT

Baseline: 8a7c72bd94a4e8a7a85eac2e03331f0e0cb6656d

Completion marker: PRODUCTION_UI_V3_RETRY_REGENERATE_CONTRACT_AUDIT_COMPLETE

This is a contract and architecture audit. It does not add retry or regenerate
buttons, provider calls, routes, migrations, or production writes.

The current repository has enough evidence to keep the V3 retry action disabled.
Canonical generation can create a durable execution and candidate, and it can
reuse a successful request. It cannot yet create a new business retry execution
with durable parent lineage. The Foundation state machine has a RETRYING
transition, but it mutates the same execution and increments the field currently
exposed as transport_retry_count. That is not the required business retry
contract.

The legacy task restart and the fixed-input video continuity retry are useful
compatibility mechanisms. They are not V3 canonical retry because both create or
requeue process/task records rather than a new GenerationExecutionRecord linked
to an immutable parent execution.

## Current Retry-like Mechanisms

| Mechanism | Current owner | New provider submission | New GenerationExecution | V3 meaning |
| --- | --- | ---: | ---: | --- |
| Transport retry / HTTP status retry | provider adapter transport and status polling | only status polling may repeat | no | same transport operation |
| Provider reconcile | creative task external task id | no, reads the existing task | no | continue observing an existing task |
| POST /api/prototyping/tasks/{id}/restart | legacy creative task | yes, after fresh confirmation | no | LEGACY_COMPATIBILITY_ONLY |
| StoryboardVideoRetryAttempt confirm route | legacy fixed-input continuity workflow | yes, after fixed-input confirmation | no | LEGACY_VIDEO_RETRY_COMPATIBILITY |
| Foundation FAILED -> RETRYING | GenerationExecutionService | no provider adapter is attached | no, same row | transitional state-machine evidence only |
| Canonical canary replay | canonical generation facade | no when the request is reusable | no | idempotent replay, not retry |
| Canonical business retry | none | not available | not available | NO_GO |
| Canonical regenerate | none | not available | not available | NO_GO |

## Transport Retry

GenerationExecutionRecord has transport_retry_count, and canonical request
snapshots initialize it to zero. The canonical image and video submit paths make
one logical provider call and persist the terminal result. They do not expose an
adapter-level submit retry that would create a second generation attempt.

The provider adapters contain bounded status polling. MiniMax H3, 75api H3 and
PoYo polling retain the same external task id; their bounded max_attempts loops
and selected HTTP 429 backoff are repeated status reads. They do not submit a
new creative request. The caller controls the polling bound through the
provider timeout and poll interval configuration.

The Foundation service currently treats RETRYING as a transition on the same
row and executes row.retry_count = row.retry_count + 1. The model property
retry_count is an alias for transport_retry_count. Therefore the current
Foundation test proves a same-row retry-shaped transition, not a correct
business retry implementation. This field must remain transport-only when
business lineage is added.

Answer:

- Same GenerationExecution: no canonical transport submit retry is currently
  wired; status polling stays with the same provider task.
- Same provider_request_fingerprint: status polling keeps the original task and
  request identity.
- Paid provider call: polling can contact the provider status API; it does not
  create another generation submission. A future transport policy must state
  whether status requests are billable separately.
- Automatic: polling and adapter backoff can be automatic; user business retry
  must not be automatic.
- Maximum: polling bounds come from provider timeout/interval settings. A
  business retry bound must be a separate policy.

## Provider Reconcile

POST /api/prototyping/tasks/{task_id}/reconcile loads the persisted creative
task, reads its external_task_id, and calls the provider-specific reconcile
function. It observes the existing provider task and updates the task
projection. It does not call the provider submit endpoint and does not create a
GenerationExecutionRecord.

provider_task_id is therefore a provider handle, not a retry lineage id.
Process restart recovery can continue observing the task through the persisted
TaskRun projection, but it is still reconcile/recovery rather than a new
creative operation.

## Legacy Task Restart

POST /api/prototyping/tasks/{task_id}/restart:

1. Loads the in-memory task or its persisted TaskRun projection.
2. Copies the persisted request_payload.
3. Forces simulate_error=false.
4. Requires a fresh confirmed and allow_external_call boundary.
5. Enqueues a new creative task and provider submission.
6. Adds restarted_from_task_id, restart_count and timestamp to the task
   projection.

The new task is backed by the process-local _creative_tasks map while its
projection is persisted through the existing task persistence path. The restart
route does not construct a GenerationExecutionRecord, candidate, validation
record, or OfficialMedia record. It can call a real provider after its legacy
confirmation, so it is not a harmless replay.

Verdict: LEGACY_COMPATIBILITY_ONLY. It must not be wired to V3's
retry_generation action.

## StoryboardVideoRetryAttempt

StoryboardVideoRetryAttempt is an auditable record for the older continuity
video workflow. Its fields are source_task_id, retry_root_task_id,
attempt_number, input_fingerprint, input_snapshot, error/provider diagnostics,
retry_task_id, status and confirmation time.

The snapshot contains the legacy request payload, frozen model/provider values,
continuity data, public first-frame and reference assets, and the source task
id. The confirm route requires confirmed=true, allow_write=true, and the fixed
token CONFIRM_FIXED_VIDEO_RETRY. It revalidates the stored continuity frame and
frozen model, then calls _enqueue_creative_task to make a new legacy video
task. retry_task_id is that new creative task id; it is not a
GenerationExecution id.

The table is video-only, task-oriented, and continuity-specific. It does not
create a canonical candidate, does not bind to GenerationExecutionRecord,
does not create an OfficialMedia version, and does not move the official
pointer. It can retain a new legacy asset task result, but it is outside the
canonical candidate/review chain.

Verdict: LEGACY_VIDEO_RETRY_COMPATIBILITY. Do not generalize this table to
IMAGE or use it as the V3 lineage table.

## GenerationExecution Current Contract

GenerationExecutionRecord currently persists:

- execution, shot, PromptIR and model identity;
- generation payload, policy, model and reference fingerprints;
- one unique provider_request_fingerprint;
- request snapshot and confirmation binding hash;
- provider task/request projections and logical provider calls;
- transport_retry_count, failure fields and optional candidate_id;
- timestamps and an official promotion count.

It has no first-class parent_execution_id, retry_root_execution_id,
retry_attempt_number, retry_reason, supersedes_execution_id, regeneration intent
id, source candidate id, or source OfficialMedia version id. The
_generation_execution_foundation JSON metadata helper can hold arbitrary values,
but no current code writes or validates business retry lineage there.

The Foundation API in api/generation_execution_api.py exposes only:

- POST /generation/executions;
- GET /generation/executions/{execution_id};
- POST /generation/executions/{execution_id}/run.

There is no canonical POST .../{id}/retry and no regenerate endpoint.
Production V3 uses the existing shot-level preview/execute facades backed by the
canonical generation code. No second retry execution engine exists.

## Provider Request Fingerprint

The canonical production path already separates a content-oriented
generation_payload_fingerprint field from provider_request_fingerprint. The
canonical request fingerprint includes shot selection, PromptIR version and
payload, policy, model profile, adapter, assets, references and the
IMAGE_TO_VIDEO source binding. It is unique in the database and intentionally
deduplicates an equivalent ordinary request.

That is enough for accidental duplicate submission, but not enough for an
intentional business retry or regenerate. The current canonical fingerprint
does not include a persisted business operation identity. The Foundation
service uses a different construction that includes its newly generated
execution_id, so the Foundation and canonical paths do not currently share one
attempt identity contract.

Do not append a random nonce. The required split is:

- generation_payload_fingerprint: creative request/content identity;
- provider_request_fingerprint: exact provider attempt identity used by the
  dedupe boundary;
- persisted operation/lineage identity: explicit retry or regenerate intent,
  stable across duplicate clicks and distinct from ordinary generation.

For an intentional retry, create one persisted operation intent after a fresh
confirmation. Derive the new provider attempt fingerprint from the frozen
content identity plus that operation identity. A duplicate click reuses the
same operation intent; a new user retry creates a new intent. This is
auditable, replayable, and distinguishes accidental double-submit from a
deliberate paid attempt.

## FAILED Replay Current Behavior

Canonical execution failure is durable. Reusing the same failed preview and
confirmation token returns 409 GENERATION_CANARY_FAILED_REQUIRES_NEW_CONFIRMATION;
it does not submit again and does not create a new execution. A new confirmation
and a new operation contract are still missing.

The provider-free Foundation tests exercise a different transitional behavior:
FAILED -> RETRYING -> QUEUED keeps the same execution_id, preserves the error,
and increments the property backed by transport_retry_count. This is exact
observed behavior, but it violates the desired separation between transport
retry count and business retry lineage.

Successful canonical replay is different: the same current request returns the
existing execution/candidate with provider_calls=0 and reused=true. That is
ordinary idempotent replay and must not be called regenerate.

## Canonical Business Retry Definition

Retry means: a user explicitly authorizes one new provider execution for a
FAILED canonical GenerationExecution, while preserving the failed execution as
immutable history and preserving the allowed input boundary.

A future retry must:

- create a new execution id and a new candidate lineage;
- preserve the failed execution and its error;
- retain parent/root/attempt/reason and the frozen source relationship;
- require a fresh preview/confirmation and allowExternalCall=true;
- never reuse the failed confirmation token;
- never turn FAILED back into RUNNING on the old row;
- never move the OfficialMedia pointer;
- never auto-promote the new candidate.

## Retry Original vs Generate Current

| Intent | Meaning | Inputs | UI copy proposal |
| --- | --- | --- | --- |
| Retry Original | Repeat the same frozen creative request with a new provider attempt | immutable request snapshot, source version ids, original model/profile unless explicitly unsupported | 重试本次生成 |
| Generate Current | Re-resolve current authorities and create a new request | current PromptIR, assets, model, policy and current source | 按当前配置生成新版本 |

Recommendation: expose Retry Original only for a genuinely failed execution
whose frozen sources remain readable and policy-allowed. If PromptIR, assets,
model, policy or the VIDEO source changed, fail closed for Retry Original and
offer Generate Current as a different intent. A model override changes provider
request identity and therefore belongs to Generate Current/regenerate, not Retry
Original.

## IMAGE Retry

Current verdict: NO_GO.

IMAGE has a durable PromptIR, asset, model and request snapshot, but lacks a
canonical retry API, business lineage, new confirmation flow and attempt
identity. The future contract is feasible after the shared lineage foundation:
validate the immutable prompt/materialized asset snapshot, create a new
execution, submit only after fresh confirmation, persist a new candidate, and
leave the current Official pointer unchanged.

## VIDEO Retry

Current verdict: NO_GO.

VIDEO adds a strict dependency on the current Official IMAGE source, source
checksum/version, motion/Shot Direction and video intent. The canonical
IMAGE_TO_VIDEO path already records a source binding and blocks stale source
promotion. That is useful evidence, but it is not a retry lineage. Retry
Original must retain an immutable readable source version; if it is unavailable
or no longer permitted, fail closed. If the user wants the current Official
IMAGE and current motion inputs, that is Generate Current, not Retry Original.

## Regenerate Definition

Regenerate means that a successful candidate or Official Media version exists
and the user intentionally asks for a new creative alternative. It is not
failure recovery and it must not reuse the ordinary request fingerprint as if
another idempotent submit were a new version.

The future intent needs a persisted operation identity, regeneration reason,
creative variant index, source candidate/Official version and a new execution
lineage. A successful existing candidate remains history. The new candidate
must pass validation and review before promotion.

## IMAGE Regenerate

Current verdict: NO_GO.

The current data model can retain more than one candidate because
MediaCandidateRecord.execution_id is unique per execution, not per shot.
However, there is no explicit regenerate intent or variant lineage and no V3
endpoint. The first implementation should use current PromptIR/assets/model
after a fresh confirmation and create a new execution identity.

## VIDEO Regenerate

Current verdict: NO_GO.

VIDEO regeneration must additionally bind the current Official IMAGE source,
motion/Shot Direction and video intent. A changed Official IMAGE makes a prior
video source stale; the new version must be generated from current source
authorities or from a deliberately frozen immutable source. It cannot be
implemented by the legacy continuity retry table.

## Candidate Cardinality

The schema supports candidate history: each execution can have one immutable
candidate, and a shot can have multiple executions/candidates. Validation is
idempotent per candidate/authority snapshot. MediaPromotionRecord is one review
record per candidate. OfficialMediaVersion stores revisions, while
OfficialMediaPointer has one current pointer per shot/media role.

The backend therefore supports multiple historical candidates, but the current
UI does not define a formal multiple-active-candidates policy. Recommendation
for the first regenerate contract: resolve an existing review candidate
explicitly (approve, reject or request change) before allowing another
regenerate operation. Later multi-active-candidate review may be added only with
an explicit inbox/queue contract.

## Official Pointer Safety

Generation submission creates an execution and candidate only. The canonical
path sets official_promotion_count=0; it does not create or update
OfficialMediaVersion, OfficialMediaAuthority or OfficialMediaPointer.

Promotion performs deterministic validation, explicit review confirmation and
then creates a new OfficialMedia revision and updates the single current
pointer. Older official versions are marked superseded only during promotion.
Therefore the future retry/regenerate flow must keep the old Official pointer
current until the new candidate is validated and promoted. If the new execution
fails, the old Official version remains valid.

## Schema Gap

Schema result: DB_MIGRATION_REQUIRED.

| Option | Assessment |
| --- | --- |
| Add parent/root/attempt columns to GenerationExecutionRecord | Queryable and FK-friendly, but couples retry and regenerate semantics to one row and does not naturally carry source candidate/Official version, intent reason or active operation identity. |
| Put lineage in request_snapshot_json | Preserves old schema but has weak queryability, no FK/integrity enforcement, no useful index, and makes accidental omission/tampering easy to miss. Not sufficient for business lineage. |
| Reuse StoryboardVideoRetryAttempt | Incorrect scope: task ids, frozen public assets and continuity VIDEO semantics cannot express IMAGE or canonical candidate lineage. |
| Add GenerationExecutionAttemptLineage | Recommended. One row per new business attempt, FK-linked to execution and optional parent/root execution, with operation kind and source references. Works for IMAGE and VIDEO without changing legacy task semantics. |

Recommended future table fields include:

- lineage_id, execution_id, parent_execution_id, root_execution_id;
- operation_kind (INITIAL, RETRY, REGENERATE);
- attempt_number, reason, intent_id, variant_index;
- frozen source snapshot fingerprint and source PromptIR/asset/model/policy
  fingerprints;
- optional source_candidate_id, source_official_media_version_id;
- confirmation binding hash, actor, timestamps and a unique operation
  idempotency key.

transport_retry_count remains on GenerationExecutionRecord and continues to
mean only same-execution transport behavior.

## API Gap

There is no canonical retry or regenerate endpoint. A future public contract
should be a shot-level facade backed by one shared execution/lineage service:

- POST /api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation/retry
- POST /api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation/regenerate

Both routes should create a preview/operation intent, require a fresh
confirmation, and then delegate to the same canonical execution service. A
thin POST /generation/executions/{id}/retry foundation route may exist for
internal tooling, but it must not become a second execution implementation.
The response should continue to refetch/project Production Workspace V2 as the
shot-state truth.

## Lineage Proposal

Use the recommended GenerationExecutionAttemptLineage record for both business
retry and regenerate, with operation_kind separating their semantics. Keep the
original execution immutable after terminal failure. Create the lineage/operation
row before the provider boundary, bind it to a fresh confirmation, and make its
idempotency key unique. Store source candidate/Official version ids for
regenerate and the frozen request/source snapshot relationship for Retry
Original.

Do not promote, overwrite or supersede an Official pointer during submission.
Do not let a legacy task id stand in for an execution id.

## Idempotency Proposal

Ordinary generation uses the current canonical request fingerprint to dedupe
double-submit. Retry and regenerate first create a durable operation intent.
The intent id/key is stable across duplicate clicks and is included in the new
attempt identity. The new provider request fingerprint is deterministic from
the operation kind, intent identity, parent/root lineage and frozen/current
content fingerprints. It is not a random nonce and it cannot collide with the
ordinary generation intent.

## Double Submit vs Intentional Retry

| User action | Required result |
| --- | --- |
| Double click ordinary Generate | one preview/operation, one provider call, same execution winner |
| Double click the same confirmed Retry operation | same retry intent, one new execution at most |
| User explicitly starts another Retry | a new intent, new confirmation and another new execution |
| Ordinary Generate with unchanged inputs | reuse existing execution/candidate |
| Regenerate | never reuse ordinary generation identity; create a new variant intent |

## Cost Confirmation

Legacy restart and fixed-input video retry already require explicit
confirmation boundaries. V3 business retry/regenerate must require a new
confirmation bound to the new operation, current/frozen fingerprints and
allowExternalCall=true. A failed or successful old token cannot authorize a
new paid call.

## Adapter Mapping Proposal

The current adapter should remain disabled for retry_generation until the
backend contract exists. Future mapping:

| Canonical state | Proposed action |
| --- | --- |
| true GenerationExecution FAILED | retry_generation -> 重试本次生成 |
| current/stale upstream | refresh_stale_source or 按当前配置生成新版本 after re-resolution |
| validated candidate pending review | review_candidate |
| current Official | primary view_official; secondary future generate_new_version |
| blocked/unknown/validation failure | resolve_blocker or review-specific action, never retry |

laneState already maps execution FAILED to retry_generation, stale to
refresh_stale_source, review to review_candidate, and blocked to
resolve_blocker. One audit issue remains: normalizeExecution.retryAllowed
currently includes stale even though stale's primary action is refresh. The
field must be narrowed to a true failed GenerationExecution before a retry UI
uses it. Candidate technical validation/review failure must not be translated
into provider retry.

## UI Copy Proposal

- Retry: 重试本次生成
- Current-state generation/regenerate: 按当前配置生成新版本
- Existing candidate: 先处理候选审核
- Official primary: 查看正式版本
- Official secondary future action: 生成新版本

Do not label both Retry Original and Generate Current as 重新生成.

## Test Evidence

Current provider-free evidence:

- tests/test_generation_execution_foundation.py proves the exact Foundation
  same-row FAILED -> RETRYING -> QUEUED behavior and the current
  transport_retry_count alias.
- tests/test_phase_j3_canonical_generation.py proves successful IMAGE/VIDEO
  replay returns provider_calls=0, reused=true, and one execution/candidate;
  it also proves IMAGE_TO_VIDEO source drift fails closed before provider work.
- canonical canary execution rejects a failed preview with the same
  confirmation token using GENERATION_CANARY_FAILED_REQUIRES_NEW_CONFIRMATION.
- tests/test_generation_adapters.py exercises provider status reconciliation
  with mocked HTTP responses and no real provider calls.
- tests/test_retry_regenerate_contract_audit.py checks the route/schema
  absence and the candidate/official cardinality constraints without a
  provider or database migration.
- The combined provider-free directed audit suite passed 74 tests, including
  Generation Execution Foundation, canonical IMAGE/VIDEO replay, profile
  replay semantics, mocked provider reconciliation, and legacy video
  continuity retry.

The current phase does not add a retry or regenerate implementation, so no
test claims that a canonical business retry already works.

## Readiness Verdict

| Capability | Current verdict | Reason |
| --- | --- | --- |
| IMAGE Retry | NO_GO | No new execution endpoint, business lineage, fresh retry confirmation or attempt identity. |
| VIDEO Retry | NO_GO | Same gaps plus immutable Official IMAGE/source lineage; legacy video retry is task-only. |
| IMAGE Regenerate | NO_GO | No regenerate intent/endpoint/variant lineage; ordinary generation is idempotent reuse. |
| VIDEO Regenerate | NO_GO | Same gaps plus current IMAGE source, motion and video intent requirements. |

## Recommended Next Phase

PHASE_GENERATION_EXECUTION_ATTEMPT_LINEAGE_FOUNDATION

This single backend foundation phase should add the shared operation/lineage
record, separate transport retry count from business attempts, define stable
operation idempotency and fresh confirmation, and expose provider-free retry and
regenerate contract tests. It should precede any V3 button or adapter enablement.

Review Inbox, Retry/Regenerate UI, large-scale pagination and Legacy
deprecation remain out of scope.

## Validation

- Web baseline remains 61 test files / 435 tests.
- Backend targeted regression baseline remains 34 tests.
- Audit tests: 7 provider-free tests passed.
- Combined directed audit suite: 74 tests passed.
- No real LLM, image, video, Shapi or MiniMax call.
- No production write and no database migration in this audit phase.
- Build, Python compilation and git diff --check are required before commit.

## Files

- docs/ui-v3/PRODUCTION_UI_V3_RETRY_REGENERATE_CONTRACT_AUDIT.md
- docs/ui-v3/PRODUCTION_UI_V3_RETRY_REGENERATE_CONTRACT_AUDIT.json
- tests/test_retry_regenerate_contract_audit.py
