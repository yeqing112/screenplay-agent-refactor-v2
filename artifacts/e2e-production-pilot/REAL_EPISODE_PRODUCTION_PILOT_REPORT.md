# REAL_EPISODE_PRODUCTION_PILOT_BLOCKED

## Phase

`PHASE_REAL_EPISODE_PRODUCTION_PILOT`

- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Remote: [screenplay-agent-refactor-v2](https://github.com/yeqing112/screenplay-agent-refactor-v2)
- Implementation commit: `17f24a5ea1a78bf750101977e372ebbf57192bf4`
- Report commit: `pending-report-commit`
- Migration head: `m4h5i6j7k8l9`
- Episode: `13` (`book_id=990402`, episode number `1`)
- Provider policy: SHAPI ([https://www.shapi.vip/](https://www.shapi.vip/)) + MiniMax H3

## Current result

The pilot remains **BLOCKED** before paid execution. An idempotent source-preparation command now creates a deterministic two-shot StoryboardPlan candidate from the existing Episode 13 context while retaining the original ScriptIR and FactSnapshot hashes. The candidate is `COMPILED` and awaits an explicit human StoryboardPlan approval. No materialized shots, render plan, keyframe sequences, candidates, official media, or provider calls were created.

This run does not claim `REAL_EPISODE_PRODUCTION_PILOT_COMPLETE`.

## Source fixture

- ScriptIR source: version `2`, hash `de49e08ab2504c0465d1b6b83a510e330825f90298c3ab9edf800a8f428b313f`
- FactSnapshot source: id `1`, hash `c4f5e1a2c722e2daf2cd83e8faf4ec2c1d6307ea22f46f38bd715d770679b3ba`
- Planned shot keys: `pilot-e13-shot-a` → `pilot-e13-shot-b`
- StoryboardPlan: id `1`, version `1`, status `COMPILED`
- Human review: required; no approval was fabricated
- Original ScriptIR / FactSnapshot mutations: `0 / 0`

## Pilot safety

| Check | Result |
|---|---:|
| Preflight | BLOCKED |
| Dry run production writes | 0 |
| Planned SHAPI calls | 0 |
| Actual SHAPI calls | 0 |
| Planned MiniMax H3 submissions | 0 |
| Actual MiniMax H3 submissions | 0 |
| Real LLM calls | 0 |
| Automatic paid retry | disabled |
| Human approval bypass | disabled |
| Secrets emitted | 0 |

Provider gates remain unset: `PHASE_F_PROVIDER_CANARY_REAL`, `MINIMAX_H3_GRAY_REAL`, `MINIMAX_H3_GRAY_CONFIRM`, and the exact two-shot `MINIMAX_H3_GRAY_WHITELIST`.

## Verification

- Pilot source tests: **2 passed**
- Pilot safety tests: **12 passed**
- `python -m compileall -q scripts/prepare_real_episode_production_pilot_source.py`: **PASS**
- `git diff --check`: **PASS**
- Real provider calls: **0**

## Next required review gate

An operator must review and approve the two-shot StoryboardPlan. After that, the existing deterministic materialization, ShotDirection, AutomaticKeyframePlan review/compile, and PromptIR paths can create the exact numeric shot allowlist. Only then can a separately controlled real-provider preflight be evaluated.

See [REAL_EPISODE_PRODUCTION_PREFLIGHT.json](REAL_EPISODE_PRODUCTION_PREFLIGHT.json), [Truth Audit](REAL_EPISODE_PRODUCTION_PILOT_TRUTH_AUDIT.json), and [Vertical Slice](REAL_EPISODE_PRODUCTION_PILOT_VERTICAL_SLICE.json).
