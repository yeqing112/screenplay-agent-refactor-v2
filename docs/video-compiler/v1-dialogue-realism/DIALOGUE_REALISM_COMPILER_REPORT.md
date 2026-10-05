# Dialogue Realism Compiler Report

Status: `MINIMAX_H3_DIALOGUE_REALISM_COMPILER_READY`

## Dialogue Single Emission

- Full authoritative dialogue plain occurrence: `0`
- `<d>` block count: `4`
- Phrase occurrence counts: `[1, 1, 1, 1]`
- Coverage: `PASS`
- Duplication: `PASS`
- Order: `PASS`

## Performance and Camera Realism

Performance uses deterministic, provider neutral intent for micro expressions, gaze behavior, 0.2–0.6 second listener reaction delay, subtle breathing, natural weight shift, secondary motion and imperfect gestures. Camera intent is restrained handheld with very subtle drift, subtle operator breathing, reaction lag, corrective reframing, natural settling and rare focus behavior.

Maximum micro actions per window: `3`. Maximum camera realism modifiers per window: `2`. Compression triggered: `false`.

Speaker mouth micro directives: `0`; dialogue is driven only by `<d>`. Silent listener speech-like directives: `0`; mouth sanitization: `PASS`.

## SC002_002

- Unauthorized props: `0`
- Positive bag state: `0`
- Negative bag constraint: `PRESENT`
- Terminal hold dialogue count: `0`

## Prompt

- Final word count: `1873`
- Compiled SHA256: `c87f2d638cfc21aa5601f9a4b475d16641bff659dcc0c1891ae67134e63c47cb`
- Full compiled request: `SC002_002_H3_COMPILED_REQUEST.json`

## Test and Provider Budget

- Targeted regression: `102 passed`
- Full regression: `2110 passed, 24 failed`; baseline failures: `24`; new failed nodes: `0`
- Real IMAGE: `0`
- Real VIDEO: `0`
- Historical rejected candidate retained; no new provider call was made.
