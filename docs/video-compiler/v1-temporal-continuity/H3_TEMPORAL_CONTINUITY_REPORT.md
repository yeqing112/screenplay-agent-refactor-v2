# H3 Temporal Continuity Report

Status: `MINIMAX_H3_TEMPORAL_CONTINUITY_READY`

## Dialogue

- `<d>` count: `4`
- Phrase occurrence: `[1, 1, 1, 1]`
- Timing exact: `true`
- Plain full authoritative occurrence: `0`

## Performance

- Source beats: `13`
- Compiled events: `13`
- Duplicate emissions: `0`
- State resets: `0`

## Camera

- Source beats: `4`
- Compiled events: `4`
- Duplicate emissions: `0`
- Continuity conflicts: `0`

## Realism

- Reaction-delay count: `1`
- Listener meaningful reactions: `3`
- Primary action duplication: `0`
- Camera realism duplication: `0`

## Terminal hold

- Count: `1`
- Dialogue: `0`
- New events: `0`

## Prompt

- Old word count: `1873`
- New word count: `1793`
- Old SHA: `c87f2d638cfc21aa5601f9a4b475d16641bff659dcc0c1891ae67134e63c47cb`
- New SHA: `bd2a0e5e5fa6daefe880a6f1468596b6c58dd6700d4483d6d3e6cb0ff743cb60`
- Full request: `SC002_002_H3_COMPILED_REQUEST.json`

## Tests and provider budget

- Targeted temporal/compiler tests: `107 passed`
- Full regression: `2113 passed, 25 failed`; one transient HTTP fixture failure was rerun and passed; effective result `2114 passed, 24 baseline failures`; new failed nodes: `0`
- Real IMAGE: `0`
- Real VIDEO: `0`
