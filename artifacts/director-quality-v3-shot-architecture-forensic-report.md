# Director Quality V3 — Shot Architecture Forensic Final Report

**Status:** `DIRECTOR_V3_SHOT_ARCHITECTURE_FORENSIC_ADJUDICATION_CLOSED`

## Original Experiment Validity

- Provider calls: **3**; exactly one per scene; retries: **0**; new calls in this stage: **0**; raw evidence immutable: **true**.
- Original parser valid: **false**; strict outer envelope valid: **true**.
- Original Strategy Authority valid: **false**; provider Contract complete: **false**.
- `ORIGINAL_CANARY_EXPERIMENT_VALIDITY=INVALID` (`WRONG_STRATEGY_AUTHORITY_SOURCE`, `PARSER_SELECTED_NESTED_SHOT_OBJECT`, `PROVIDER_CONTRACT_INCOMPLETE`).

## Authority and Raw Evidence Matrix

| Scene | Original Strategy FP | Current Strategy FP | Raw shots | Protocol after normalization | Composite bundles | Topology hard errors | Capability |
|---|---|---|---:|---|---:|---:|---|
| book990402:e3:暗房惊魂 | `f456c2f3f69f4c537537df3fa6f9d77787365edf3f8c9c406740917d46706993` | `8a98151b7e7e2801b8daa5d576003da529717f61796dce491c2aa791037f3c04` | 7 | PASS | 3 | 1 | WEAK |
| book990402:e3:暗房惊魂（2） | `e7cf30b5b5fd42dae780594dde0ca63e60b194ded5d091a8ebb731e5ad858af9` | `95a18cc7b7f9096934bb668f6d3ba81bc7a1ce489d33074734fe9abccef465e2` | 10 | FAIL | 1 | 1 | WEAK |
| book990402:e2:回声照相馆 | `1a517bca15ee51deb8295d44ea8f08a93d3bb0e6a9d5e8f5a735ecfa05d5f6dc` | `e38dd057db5a7bf53f93e6cc416a7576d0d010b523e9a8971e5dcfdc924ce0b5` | 12 | PASS | 3 | 0 | PROMISING_BUT_NEEDS_CONTRACT |

The original request used the historical Base Strategy fingerprints; the current pointer uses the exact finalized Revised Strategy fingerprints. These contexts are never conflated.

## Parser Forensics

- All three raw files contain a complete outer `{architecture_summary, shots[]}` envelope.
- The legacy parser selected a nested shot object because it scored by object key count without requiring both envelope keys; this produced the historical 1/1/1 result.
- The strict parser now requires **both** top-level keys and preserves the raw fingerprint.

## Raw Architecture Capability

- Outer envelopes: 3/3; reconstructed raw shot counts: 7, 10, 12.
- Protocol after lossless normalization: 2/3; beat coverage: 3/3; phase coverage: 3/3.
- Composite coverage bundles: 7; future information leaks: 0; topology hard errors: 2.
- Mechanical beat mapping: book990402:e3:暗房惊魂=no, book990402:e3:暗房惊魂（2）=no, book990402:e2:回声照相馆=no; mechanical dialogue coverage: book990402:e3:暗房惊魂=0, book990402:e3:暗房惊魂（2）=0, book990402:e2:回声照相馆=0.
- `RAW_ARCHITECTURE_CAPABILITY=WEAK`.

## Scene-specific Director QA

- `book990402:e3:暗房惊魂`: {"pressure_body_defense_core": true, "mechanical_visual_stack": false}
- `book990402:e3:暗房惊魂（2）`: {"primary_secondary_expression_declared": true, "reflection_keeps_uncertainty": true}
- `book990402:e2:回声照相馆`: {"trace_prop_character_photo_loop": true, "standard_ots_dependency": true}

## Contract / Authority Closure

- Parser now requires `architecture_summary` **and** `shots`; nullable string arrays are normalized losslessly; B<n> beat aliases are canonicalized; unknown movement remains review-required.
- Contract V2 explicitly defines enum vocabularies and the Atomic Shot Rule; composite bundles are reported, not silently split.
- Current Strategy Authority pointer is established with exact fingerprints; historical Strategy Repair FAILED artifacts are not authority.
- Director Critic Review: `PASS_WITH_NOTES`; Human Preference Review: `NOT_RECORDED`; no Human Approval was fabricated.
- `CONTRACT_V2=CLOSED`; production ShotPlan remains HOLD.

## Final Re-Canary Decision

`READY_FOR_FINAL_SHOT_ARCHITECTURE_RECANARY=false`

The decision authorizes only a future, explicitly approved three-call re-canary. This provider-free forensic pass made **0** new calls and did not enter ShotPlan, Storyboard or media.
