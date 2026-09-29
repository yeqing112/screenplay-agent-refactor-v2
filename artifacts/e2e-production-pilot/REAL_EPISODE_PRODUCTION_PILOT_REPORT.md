# REAL_EPISODE_PRODUCTION_PILOT_BLOCKED

## Phase

`PHASE_REAL_EPISODE_PRODUCTION_PILOT`

- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Remote: [screenplay-agent-refactor-v2](https://github.com/yeqing112/screenplay-agent-refactor-v2)
- Implementation commit: `7f56309`
- Report commit: see the remote HEAD after this report commit is pushed
- Migration head: `m4h5i6j7k8l9`
- Pilot target: Episode `13`, requested shots `1`, `2`
- Preflight evidence: [REAL_EPISODE_PRODUCTION_PREFLIGHT.json](REAL_EPISODE_PRODUCTION_PREFLIGHT.json)
- Preflight snapshot HEAD: `5ae6632ac67737e40224497e868a54486ce2b053`
- Preflight timestamp: `2026-09-29T03:09:23.487293+00:00`

## Result

The controlled two-shot real production pilot is **BLOCKED**. The runner performed a read-only preflight and did not submit paid work. It now requires an exact Episode allowlist entry, exact Shot allowlisting, current source authority, budget checks, explicit consent, and both provider gates before any paid operation. Stage B is fail-closed until Stage A is `COMPLETE`.

The configured image provider is SHAPI ([https://www.shapi.vip/](https://www.shapi.vip/)); its Model Registry profile is present as `shapi-openai-images` with transport `shapi-openai-images.image.v1`. The video profile is the existing MiniMax H3 async profile. Credentials are represented only as `credential_present: true`; no secret is recorded.

## Preflight facts

| Check | Result |
|---|---:|
| Render plan for requested episode | unavailable (`EpisodeRenderingError`) |
| Preflight branch / working tree | correct / clean at snapshot |
| Preflight migration head | `i0d1e2f3g4h5` (expected `m4h5i6j7k8l9`) |
| Exact Episode allowlist | matched (`13`) |
| Requested unique shots | 2 |
| Planned real SHAPI calls | 0 |
| Planned real MiniMax H3 submissions | 0 |
| Production writes | 0 |
| Real SHAPI calls | 0 |
| Real MiniMax H3 submissions | 0 |
| Real LLM calls | 0 |
| Official real videos | 0 |
| Provider task IDs | none |
| Image candidates / approved keyframe images | 0 / 0 |
| Video candidates / approved shot videos | 0 / 0 |
| Human review decisions | 0 image, 0 video |
| Duplicate paid requests | 0 |
| Provider failures | 0 |
| Stale blocks | 0 paid executions; authority unavailable in preflight |
| Automatic retries | 0 |
| Secrets emitted | 0 |

Dry run was requested and returned `BLOCKED` with `production_writes = 0`; planned operations, existing assets, new executions, and review gates were empty because the Episode render plan was unavailable.

Blocking conditions include migration head drift (`i0d1e2f3g4h5` vs expected `m4h5i6j7k8l9`), missing render plan/shot authority in the current local database, and unset `PHASE_F_PROVIDER_CANARY_REAL`, `MINIMAX_H3_GRAY_REAL`, `MINIMAX_H3_GRAY_CONFIRM`, and exact `MINIMAX_H3_GRAY_WHITELIST`.

## Delivered implementation

- Added `scripts/run_real_episode_production_pilot.py` as a fail-closed, read-only-by-default pilot runner.
- Added an explicit `--allow-episode-id` requirement and a Stage A → Stage B execution gate.
- Added read-only repository, working-tree, and migration-head checks to preflight.
- Reused the existing Episode production, keyframe image, shot video, Model Registry, GenerationExecution, MediaCandidate, review, promotion, and OfficialMedia paths.
- Enforced one operation per execute invocation, exact two-shot scope, image budget `<=4`, video budget `<=2`, explicit consent, provider/transport matching, and no automatic retry.
- Added safety tests for missing gates, exact allowlist, provider contract, missing episode write isolation, explicit consent, budget exhaustion, and secret-free blocker serialization.

## Verification

| Check | Result |
|---|---:|
| Pilot safety tests | 11 passed |
| Full regression | 1944 passed |
| Golden fixtures | 5/5 |
| Migration CI | PASS: fresh/repeat/legacy/drift; head `m4h5i6j7k8l9` |
| Compileall | PASS |
| `git diff --check` | PASS |

## Completion status

`REAL_EPISODE_PRODUCTION_PILOT_COMPLETE` is not claimed because no real SHAPI request or MiniMax H3 submission occurred. The next run requires a valid two-shot Episode render plan, current authority records, the exact Episode/Shot allowlists, and the separately controlled real-provider gates. No Source Fact or ScriptIR mutation occurred.

See the machine-readable [Truth Audit](REAL_EPISODE_PRODUCTION_PILOT_TRUTH_AUDIT.json) and [Vertical Slice](REAL_EPISODE_PRODUCTION_PILOT_VERTICAL_SLICE.json).
