# SC002_002 H3 Semantic Residue Closure

Status: `H3_SC002_002_SEMANTIC_RESIDUE_CLOSED`

Gate A completed with `Real IMAGE = 0` and `Real VIDEO = 0`. No provider POST was made.

## Unauthorized prop semantic scrubber

- Canonical ShotPropState for SC002_002: empty.
- Unauthorized bag and strap relationships were removed structurally from Lin Wan's performance beats.
- Lin Wan 0.0–2.4s: hand close to her side, fingers gradually relax, hand naturally loose beside her body.
- Lin Wan 7.2–9.6s: small unconscious adjustment, then the hand settles naturally beside her body.
- Orphan prop interactions: `0`.
- Source facts and ScriptIR: unchanged.

## Prompt semantic partition

- POSITIVE_VISUAL: unauthorized prop tokens `0`.
- NEGATIVE_VISUAL: one `strap` occurrence and two `apple` occurrences.
- DIALOGUE: four canonical `<d>` blocks; apple is dialogue-only (`苹果`) and is not in `VideoIntentIR.props`.
- APPLE visual authority: `NONE`.

## Temporal and dialogue contract

- Performance: `13/13/0` source/compiled/duplicates.
- Camera: `4/4/0` source/compiled/duplicates.
- Dialogue timing drift: `0`.
- Reaction delay events: `1`; terminal hold: `1`.
- `<d>` blocks: `4`; plain full dialogue occurrence: `0`.

## Reference lineage

Gate B preflight is recorded separately and intentionally deferred. The real canary must resolve an existing Approved/Official SC002_002 keyframe through the canonical resolver and provide asset id, media SHA, authority fingerprint, lineage, and a provider-accessible URL before POST.

## Evidence

- Compiled request: `SC002_002_H3_COMPILED_REQUEST.json`
- Semantic scrub audit: `UNAUTHORIZED_PROP_SEMANTIC_AUDIT.json`
- Partition audit: `PROMPT_SEMANTIC_PARTITION_AUDIT.json`
- Strap audit: `SC002_002_STRAP_AUDIT.json`
- Dialogue mentioned prop audit: `SC002_002_DIALOGUE_MENTIONED_PROP_AUDIT.json`
