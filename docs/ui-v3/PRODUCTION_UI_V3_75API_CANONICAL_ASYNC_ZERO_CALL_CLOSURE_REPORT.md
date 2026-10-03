# Production UI V3 · 75API Canonical Async Zero Call Closure

## Status

`READY_FOR_REAL_PROVIDER_VIDEO_V5_BUDGET`

This phase used only an isolated SQLite database and a local HTTP fixture that implements the 75API protocol. No V5 budget was created and no real provider was contacted. Historical V4 evidence remains `CLOSED_BLOCKED_TECHNICAL_VALIDATION`, used `2/3`, with its reserve permanently unused.

## Browser evidence

The actual Production UI V3 browser run used Book `990452`, Shot `1`, profile `browser-fixture-75api-v1` (`75api-minimax-h3`, `minimax_h3_no_audios`, `75api-minimax-h3.video.v1`). The browser clicked Generate VIDEO, observed authoritative RUNNING state, reloaded the same page, resumed through backend reconcile, approved Candidate v1, regenerated, reviewed Candidate v2 while Official v1 stayed current, and approved Official v2.

- Before reload: execution `46b41d450757419ba2206dec81180077`, task `browser-task-001`.
- After reload: the same execution and task remained RUNNING; no second submit occurred.
- Candidate v1: `candidate-e98c034e820c420890431bebe8133082`; Official v1: `omv-d9589ef1b403bf0c5d18798b08e27db5782a80e0`.
- Regenerate: execution `be61bf5d92444ebcb4502359d1f95d71`, task `browser-task-002`.
- Candidate v2: `candidate-b374746b1a954f9b8360c770cd940986`; Official v2: `omv-5a404d844ae4477f3a73560b935410301b2b1d8d`.

Screenshots and browser-produced authoritative snapshots are under [`PRODUCTION_UI_V3_75API_CANONICAL_ASYNC_ZERO_CALL_CLOSURE`](./PRODUCTION_UI_V3_75API_CANONICAL_ASYNC_ZERO_CALL_CLOSURE/). The independent network ledger is [`PRODUCTION_UI_V3_75API_ASYNC_BROWSER_ZERO_CALL_NETWORK.json`](./PRODUCTION_UI_V3_75API_CANONICAL_ASYNC_ZERO_CALL_CLOSURE/PRODUCTION_UI_V3_75API_ASYNC_BROWSER_ZERO_CALL_NETWORK.json).

## Network and fixture ledger

- Browser generation submits: `2`; backend reconcile POSTs: `8`; promotion POSTs: `2`.
- Browser direct Provider calls: `0`; browser external hosts: `0`.
- Local fixture submit POSTs: `2`; status polls: `6`; authenticated content GETs: `2`; auth failures: `0`.
- Real 75API POST/poll/content: `0/0/0`; real IMAGE calls: `0`.

The fixture required `Authorization: Bearer <test-runtime-secret>` and only recorded redacted presence markers. The runtime secret was supplied to the isolated backend process and never persisted in the model profile or browser artifacts.

## Runtime fix

Production UI V3 now publishes the durable RUNNING projection before reconcile, then calls `POST /api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation/reconcile` on a bounded refresh loop. Reload recovery uses the persisted execution ID, task ID, and derived confirmation token from `production-workspace-v2`; it never re-submits the Provider. Reconcile accepts regenerate attempt lineage when its stored base provider request fingerprint still matches current authority.

## Isolation

- Production backend `18765` and production frontend `5175` were not used for writes.
- The isolated backend/frontend were `18768/5176`.
- Book `990400` writes: `0`; production write audit: `0`; orphan rows: `0`; secret leaks: `0`.
- The prior production DB audit hash remains unchanged at `d729360fae56fe082729962db48d26de272cd956e500b1cda6702328d424c026`.

## Validation

- Browser E2E: passed; screenshots `08` through `14`, all required state snapshots, and network ledger written.
- 75API async fixture tests: `4 passed`.
- Canonical focused backend suite: previous targeted `100 passed`; this run also re-ran the async lifecycle `4 passed`.
- Web baseline: `447 passed`; frontend build: passed.
- Python compileall and `git diff --check`: passed.
- Alembic baseline: `p1q2r3s4t5u6`.

`VIDEO_REAL_PROVIDER_CLOSURE_COMPLETE` is not set. The next authorized stage may create V5 budget only after separate approval.
