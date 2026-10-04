# Prompt Production Quality Report V4

Final status: `PROMPT_PRODUCTION_DETAIL_QUALITY_BLOCKED`

## Director LLM
- Calls: `5/5`
- Result: `BLOCKED`
- Profile/model: `local-llm-2vydoz / mimo-v2.5`
- Reason: `REUSED_LAST_CONTROLLED_CANARY_RESPONSES`
- Nested IR blockers: `8`
- Source fact conflicts: `0` in deterministic decisions
- Policy: invalid nested output is rejected without automatic retry
- Alternate configured Doubao profile: transport returned HTTP 404; no call was counted

## Asset prompts
- Schema-dump count: `0`
- Provider-executable: `6`
- Representative character: `林晚`
- Representative scene: `E01_SC001`
- Representative props: `RED_UMBRELLA`, `HANDBAG`

## Keyframes
- Unresolved performance-plan refs: `0`
- Unresolved ShotPlan refs: `0`
- Concrete starting states: `5`

## Motion
- Adaptive timelines: `true`
- Fixed timeline count: `0`
- Generic body actions: `0`
- Generic hand actions: `0`
- Generic eye targets: `0`
- Generic ending states: `0`

## Dialogue
- Shots: `3`
- Duplicated windows: `0`
- Duration overflow: `0`
- Phrase-level timing windows: `19`

## Camera
- Timed moves: `16`
- Concrete start/end framing: `16`

## Shot handoff
- Concrete ending states: `5`
- Concrete next starting states: `5`
- Mismatches: `0`

## Representative shots
- Shot 002: eye-to-head delay, ticket hand position, red umbrella rib target, adaptive 0.65/1.05/1.8/1.5 second beats.
- Shot 005: bag transfers from 林晚 right hand to 陆叔 right hand, then left fingertip identifies the hard object.
- Shot 010: every dialogue phrase gets an authoritative window; shot is extended to fit estimated mouth time.
- Shot 014: smile appears at one corner, eyes remain cold, fingertip taps twice, apple stays outside 林晚’s reach.
- Shot 015: 林晚 retreats 10cm then 20cm to the door frame; camera arcs 20 degrees and stops at 3.8–4.4 seconds.

No IMAGE or VIDEO provider calls were made. Five Mimo LLM calls completed, but the returned DirectorDecisionIR nested structure failed validation and was rejected without retry.
