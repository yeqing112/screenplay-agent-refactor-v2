# SC002_002 H3 Semantic Residue and Real Canary Closure

## Status

- Final status: `H3_SC002_002_SEMANTIC_RESIDUE_CLOSED`
- Gate A: `PASS`
- Gate B: `BLOCKED_BEFORE_POST`
- Reason: `VIDEO_REFERENCE_LINEAGE_INCOMPLETE`
- Real IMAGE: `0`
- Real VIDEO: `0`
- Provider POST: `0`
- Promotion: `0`; candidate media: none

## Semantic residue

- Canonical props: empty.
- Lin Wan 0.0–2.4s: hand close to her side, fingers gradually relax, hand naturally loose beside her body.
- Lin Wan 7.2–9.6s: small unconscious adjustment, then the hand settles naturally beside her body.
- Positive visual strap occurrences: `0`; negative strap occurrences: `1`; total strap occurrences: `1`.
- Positive visual apple occurrences: `0`; canonical dialogue mention: `1`; negative apple occurrences: `2`.
- Orphan prop interactions: `0`.
- `APPLE` visual authority: `NONE`; `APPLE` is absent from `VideoIntentIR.props`.
- Required negative visual statements are present in the compiled prompt.

## Temporal and prompt contract

- Compiler: `minimax-h3` / `4-semantic-residue-closure`.
- Prompt words: `1799`.
- Compiled prompt SHA: `bfed0de8fe178c819219d0e7f8a59e549cd7d8dcb7727482d65b0c5aff3e8495`.
- Performance: `13/13/0` source/compiled/duplicates.
- Camera: `4/4/0` source/compiled/duplicates.
- Dialogue windows: `4`; timing drift: `0`; `<d>` blocks: `4`; plain full dialogue occurrence: `0`.
- Reaction delay events: `1`; terminal hold: `1`; unexpected state resets: `0`.
- Static camera sentence uses restrained static medium two-shot wording with barely perceptible handheld breathing drift.

## Reference lineage and Gate B

- Persisted profile: `75api-minimax-h3 / minimax_h3 / minimax-h3 / minimax-h3`.
- Existing approved keyframe evidence: review `APPROVE`, media SHA present, provider preview URL present.
- Missing required lineage: `asset_id`, `authority_fingerprint`, `generation_execution_id`, `official_lineage`.
- The runner uses `compile_video_intent -> resolve_compiled_references -> build_75api_h3_payload_from_compiled_request`; it does not hardcode a URL.
- Because the reference binding was incomplete, no POST, task, reconcile, poll, download, retry, or promotion was attempted.

## Tests

- Targeted semantic/compiler/provider suite: `111 passed, 29 warnings`.
- Full suite: `2119 passed, 24 failed, 8264 warnings`.
- The 24 full-suite failures are the established baseline migration/fixture failures; no new failure appeared in the targeted semantic residue suite.
- `compileall`: pass.
- `git diff --check`: pass.

## Safety

- SHAPI calls: `0`; Poyo calls: `0`.
- Production writes: `0`; Book 990400 writes: `0`.
- Secret leaks: `0`; raw base64 persisted: `0`; signed URL query persisted: `0`; orphan rows: `0`.

## Evidence

- Gate A report: `../v1-semantic-residue/SEMANTIC_RESIDUE_CLOSURE_REPORT.md`
- Compiled request: `../v1-semantic-residue/SC002_002_H3_COMPILED_REQUEST.json`
- Reference preflight: `SC002_002_REAL_CANARY_PREFLIGHT.json`
- Reference lineage: `SC002_002_REFERENCE_LINEAGE.json`
- Gate B report: `SC002_002_REAL_CANARY_REPORT.md`

## Git

- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Remote HEAD: recorded by the final Git command in the delivery summary.
- Working tree: clean
