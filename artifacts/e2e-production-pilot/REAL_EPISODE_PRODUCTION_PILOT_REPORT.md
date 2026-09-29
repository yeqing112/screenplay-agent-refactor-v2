# REAL_EPISODE_PRODUCTION_PILOT_BLOCKED

## Phase

`PHASE_REAL_EPISODE_PRODUCTION_PILOT`

- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Remote: [screenplay-agent-refactor-v2](https://github.com/yeqing112/screenplay-agent-refactor-v2)
- Implementation commit: `a7fb192`
- Migration head: `m4h5i6j7k8l9`
- Pilot target: Episode `13`, requested shots `1`, `2`
- Preflight evidence: [REAL_EPISODE_PRODUCTION_PREFLIGHT.json](REAL_EPISODE_PRODUCTION_PREFLIGHT.json)

## Result

The controlled two-shot real production pilot is **BLOCKED**. The runner performed a read-only preflight and did not submit paid work. It will only execute one provider operation at a time after explicit consent, exact shot allowlisting, current source authority, budget checks, and both provider gates are present.

The configured image provider is SHAPI ([https://www.shapi.vip/](https://www.shapi.vip/)); its Model Registry profile is present as `shapi-openai-images` with transport `shapi-openai-images.image.v1`. The video profile is the existing MiniMax H3 async profile. Credentials are represented only as `credential_present: true`; no secret is recorded.

## Preflight facts

| Check | Result |
|---|---:|
| Render plan for requested episode | unavailable (`EpisodeRenderingError`) |
| Requested unique shots | 2 |
| Planned real SHAPI calls | 0 |
| Planned real MiniMax H3 submissions | 0 |
| Production writes | 0 |
| Real SHAPI calls | 0 |
| Real MiniMax H3 submissions | 0 |
| Real LLM calls | 0 |
| Official real videos | 0 |
| Secrets emitted | 0 |

Blocking conditions include missing render plan/shot authority in the current local database and unset `PHASE_F_PROVIDER_CANARY_REAL`, `MINIMAX_H3_GRAY_REAL`, `MINIMAX_H3_GRAY_CONFIRM`, and exact `MINIMAX_H3_GRAY_WHITELIST`.

## Delivered implementation

- Added `scripts/run_real_episode_production_pilot.py` as a fail-closed, read-only-by-default pilot runner.
- Reused the existing Episode production, keyframe image, shot video, Model Registry, GenerationExecution, MediaCandidate, review, promotion, and OfficialMedia paths.
- Enforced one operation per execute invocation, exact two-shot scope, image budget `<=4`, video budget `<=2`, explicit consent, provider/transport matching, and no automatic retry.
- Added safety tests for missing gates, exact allowlist, provider contract, missing episode write isolation, explicit consent, budget exhaustion, and secret-free blocker serialization.

## Verification

| Check | Result |
|---|---:|
| Pilot safety tests | 7 passed |
| Full regression | 1940 passed |
| Golden fixtures | 5/5 |
| Migration CI | PASS: fresh/repeat/legacy/drift; head `m4h5i6j7k8l9` |
| Compileall | PASS |
| `git diff --check` | PASS |

## Completion status

`REAL_EPISODE_PRODUCTION_PILOT_COMPLETE` is not claimed because no real SHAPI request or MiniMax H3 submission occurred. The next run requires a valid two-shot Episode render plan, current authority records, and the separately controlled real-provider gates. No Source Fact or ScriptIR mutation occurred.

See the machine-readable [Truth Audit](REAL_EPISODE_PRODUCTION_PILOT_TRUTH_AUDIT.json) and [Vertical Slice](REAL_EPISODE_PRODUCTION_PILOT_VERTICAL_SLICE.json).
