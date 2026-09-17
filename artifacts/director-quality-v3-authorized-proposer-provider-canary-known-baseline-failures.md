# Known Baseline Failures — Authorized Proposer Provider Canary

These failures were observed before this canary and are retained as baseline
exceptions. They are not caused by targeted semantic evidence or the proposer
bridge.

| Test | Baseline reason | Fact/Coverage/ScriptIR related? |
|---|---|---|
| `test_offline_replay_emits_provenance_reports_and_nonempty_gate_reasons` | Provenance assertion expects `codex/unify-formal-workspace`, while this isolated baseline runs on `codex/fact-semantic-grounding-foundation`. | No |
| `test_authorized_real_path_requires_entire_worktree_clean` | Historical recanary is intentionally retired before worktree cleanliness evaluation. | No |
| `test_real_database_has_no_non_retired_fresh_candidates_after_six_scene_retirement` | Shared local database has no fresh approved candidates after historical sample retirement. | No |
| `test_provider_runner_uses_one_strategy_call_per_scene_and_zero_retries` | Historical Director V3 fresh integration runner is retired; its provider call expectation is not part of this fact canary. | No |

Current targeted semantic suite: **35 passed**. No fifth failure was introduced.
