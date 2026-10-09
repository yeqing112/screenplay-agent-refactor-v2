# V7.6.19 Director Stage B Structural Failure Feedback + Output Completeness

`DIRECTOR_STAGE_B_STRUCTURAL_COMPLETENESS_COMPLETE`

## Attempt-10 failure

- Failure status: `DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_SCHEMA_INVALID`.
- Raw SHA256: `5daf096fd07ad58ffe8848b25a8d633797234ce325dba1986f21de4af4ca39f0`.
- Missing schema field: `visual_priority` at `$`, expected `array<string>`.
- Root cause classification: LLM final-output structural completeness failure. Attempt-10 already had schema/prompt parity markers; it omitted a required field at final emission.
- Formal schema required keys: `['version', 'beat_enrichments', 'character_directions', 'performance_arc', 'information_strategy', 'rhythm_strategy', 'visual_priority', 'scene_exit_intent', 'prohibited_interpretations', 'confidence', 'note']`.
- Prompt required keys: `['version', 'beat_enrichments', 'character_directions', 'performance_arc', 'information_strategy', 'rhythm_strategy', 'visual_priority', 'scene_exit_intent', 'prohibited_interpretations', 'confidence', 'note']`.
- Final completeness keys: `['version', 'beat_enrichments', 'character_directions', 'performance_arc', 'information_strategy', 'rhythm_strategy', 'visual_priority', 'scene_exit_intent', 'prohibited_interpretations', 'confidence', 'note']`; count `11`.
- `visual_priority` remains required and is not replaced by `audience_focus` or `rhythm_strategy`.

## Dual lineage

- Semantic parent: `attempt-9`, IR `591bf4ec2f7df8b80a8fdd3a7166c6a76c39a7de0939ba3b1323b6af2320dfaa`, raw SHA `8cbb4343c4c762e74eba92a6cf6a2e5a02d74c6e789c636f1bd5f405e7521589`.
- Semantic policy: `director_creative_semantic_review_v2`, policy fingerprint `9df29513e7bf0433dae06b148b60e93f9afcb5517fd63d75a8b7b98c3994b501`.
- Semantic review fingerprint: `e021e4d1380f5d6b91092e892fc9d7a37d71ca3e13a0f17ded88320e74f6c66a`.
- Semantic feedback count: `4`.
- Structural feedback source: `attempt-10`.
- Structural feedback count: `1`.
- Structural feedback fingerprint: `4d17ddadda4a473154491359f2dae9a7ae3a190669113fd16a2572cc89a64be4`.

## Diagnostic only

Attempt-10 parsed successfully but remains `DIAGNOSTIC_ONLY_STRUCTURALLY_INVALID`.
Ignoring only the missing field, semantic V2 result is `BLOCKED` with counts:
certainty collapse `0`, unsupported story action `1`, SceneBlocking leakage `0`, ShotPlan leakage `1`. It is not authority, active parent, or confirmable output.

## Attempt-11 preflight

- Status: `DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_AUTHORIZATION_REQUIRED`.
- Expected attempt: `attempt-11`; history count `10`.
- Semantic parent: `attempt-9`.
- Structural failure source: `attempt-10` (`DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_SCHEMA_INVALID`).
- System SHA: `6d2c045e97fdc3cfee6797a925010d5e7340fa71d04c41ed3ed59e65ff749baa`.
- User SHA: `74e1665b6b1aaebc186141a2b795ba3f6d0ee74eabc21c6a2a9461c9ea8118f2`.
- Prompt fingerprint: `3c641b248825354ca694131216a2806f0609fc888ab43ff93c618246408fead1`.
- Provider request fingerprint: `b29e45841e84aa0d86653310db06a11dc10ffacc397df2de90f0e8236f578a28`.
- Prompt fingerprint differs from Attempt-10: `True`.
- Prompt contains separate semantic/structural feedback blocks, excludes Attempt-9 raw and Attempt-10 raw, and ends with the schema-derived completeness gate.
- Authorization: `REQUIRED_NOT_GRANTED`; provider calls: `0`.

## Mock executor results

- Complete 11-key output: structural/text/runtime/compile PASS; semantic PASS; `confirm_allowed=true`; next state review required.
- Missing `visual_priority`: schema invalid; active parent remains Attempt-9; Attempt-12 is not created.
- Semantic BLOCKED fixture: structural validated; V2 BLOCKED for `首次进入`/`打开铁盒`/`带到铁盒前`; `confirm_allowed=false`.
- Semantic PASS fixture: structural validated; V2 PASS; `confirm_allowed=true`; next state review required.
- Archive idempotency: Attempt-9 repeat is a no-op; Attempt-10 failure and Attempt-11 preflight coexist without conflict.

## Scope and production invariants

- Attempt-8/9/10 forensic scope fingerprints are equal: `True`.
- Real Provider POST: `0`; Attempt-11: `0`; Attempt-12: `0`.
- IMAGE/VIDEO/SHAPI/Poyo/75API: `0`.
- DirectorTreatment approved / Authority / Pointer / SceneBlocking / ShotPlan writes: `0`.
- Ledger: `10 -> 10`.
- Active Stage B after preflight: `attempt-9`.
- Proposal SHA: `b2dd22fbfa197b06ba61044b44db151686564c419fa030a79201f23e39a598b4 -> b2dd22fbfa197b06ba61044b44db151686564c419fa030a79201f23e39a598b4` unchanged.
- model_info SHA unchanged: `True`.

## Verification and delivery

- Focused Stage B/revision/semantic/provider-free suite: `82 passed`.
- `python -m compileall -q core api scripts`: PASS.
- `git diff --check`: PASS.
- Working tree: `DIRTY`.
- Commit: `53fb9d04c6b8d1676f15533725426685f0604872`.
- Remote HEAD: `6f0bc565559bc1ae83b73e5379c6bc720a0614d4`.

All evidence is derived from persisted production failure data or isolated provider-free fixtures; evidence JSON is not used as production authority.
