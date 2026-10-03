# PHASE_PRODUCTION_UI_V3_75API_CANONICAL_ASYNC_ZERO_CALL_CLOSURE

## Status

- V4: `CLOSED_BLOCKED_TECHNICAL_VALIDATION`
- V4 used: `2/3`
- V4 reserve: `1` unused and permanently closed
- real Provider calls in this phase: `0`
- `READY_FOR_REAL_PROVIDER_VIDEO_V5_BUDGET`: **NO**

## Credential authority

Canonical profiles remain secret-free. The canonical transport now passes the short-lived `runtime_credential_value` into all three 75API boundaries:

- `POST /v1/videos`
- `GET /v1/videos/{task_id}`
- `GET /v1/videos/{task_id}/content`

The content download header is constructed only from `runtime_credential_value`; `profile.api_key` is not used by the canonical content path. Provider responses, execution snapshots, candidates, audit JSON, and browser traffic contain no credential value.

## Async runtime

The exact async binding now exposes separate `SUBMIT` and `RECONCILE` operations. Canonical submit persists `status=RUNNING`, provider, model, request identity, task identity, response hash, and `logical_provider_calls=1` before returning. Reconcile uses the persisted task ID and never calls POST again.

A dedicated reconcile route is available at:

```text
POST /api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation/reconcile
```

The canary-compatible route is also available under `generation-canary/reconcile`.

## Provider-free evidence

A local HTTP protocol fixture implements:

```text
POST /v1/videos -> task-001
GET /v1/videos/task-001 -> processing -> completed
GET /v1/videos/task-001/content -> authenticated MP4
```

The fixture rejects missing authentication with HTTP 401. Tests prove:

- one POST for one logical generation;
- the same runtime credential on submit, poll, and content;
- authenticated MP4 persistence;
- canonical RUNNING task identity;
- reconcile after reload-shaped state without duplicate POST;
- regenerate creates a new execution/task and preserves Official v1 during Candidate v2 review.

The browser-level Production UI V3 snapshot capture has not been run in this zero-call phase, so V5 authorization remains blocked.

## Technical diagnostics

The canonical VIDEO boundary retains the public error `VIDEO_TECHNICAL_VALIDATION_FAILED` while recording secret-free diagnostic codes such as `CONTENT_AUTH_FAILED`, `CONTENT_DOWNLOAD_HTTP_ERROR`, `CONTENT_EMPTY`, `INVALID_MP4_CONTAINER`, `INVALID_DURATION`, and `LOCAL_PERSIST_FAILURE`. Provider task identity is preserved when post-processing fails.

## Security and isolation

- 75API POST: `0`
- 75API poll: `0`
- 75API content: `0`
- real IMAGE calls: `0`
- browser direct Provider calls: `0`
- production DB writes: `0`
- Book 990400 writes: `0`
- orphan rows: `0`
- secrets leaked: `0`

Historical V4 evidence remains unchanged apart from the root-cause clarification: [V4 evidence](./PRODUCTION_UI_V3_REAL_PROVIDER_VIDEO_CLOSURE_V4_EVIDENCE.json).
