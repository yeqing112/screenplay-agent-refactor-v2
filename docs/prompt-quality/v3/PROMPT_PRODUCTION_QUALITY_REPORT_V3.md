# Prompt Production Quality Report V3

`PROMPT_PRODUCTION_V3_READY_FOR_MEDIA_CANARY`

## Asset gate
- Character assets: `4`
- Character variants: `4`
- Scenes: `2`
- Props: `9`
- Visual style: `1`
- Asset prompt readiness: `PASS`

## Shot and motion gate
- Keyframes: `15`; average `8.8`; lowest `8.1`
- Timecoded VIDEO prompts: `15`
- Dialogue timing: present only where ScriptIR has dialogue; audio generation disabled
- Emotion arcs, physical body, hand, head, eye and facial details: `PASS`
- Reaction timing: `PASS`
- Camera timing: `PASS`
- Ending-state precision: `PASS`
- Generic placeholder count: `0`

## Architecture
Asset → Keyframe → PerformancePlan → TimecodedMotionIR → Provider Projection. V2/V2.1 remain unchanged. No real LLM, IMAGE, or VIDEO calls were made.

## Deep manual audit
### Shot 002
Single actor reaction is split into eye movement, delayed head lift, hand freeze, brow tension and a held final gaze.
### Shot 005
The handoff between two actors is explicit: one releases the bag, the other receives it, both eye lines and weight shifts remain bounded.
### Shot 008
顾沉 + 林晚 are the authoritative actors; the ending preserves the station exit geometry and the camera holds after the authorized push-in.
### Shot 010
Dialogue timing uses the ScriptIR source text, with mouth timing and reaction windows only; `dialogue_audio_generated=false`.
### Shot 014
Threat is expressed through a controlled smile, fingertip taps, gaze lock and a visible emotion arc.
### Shot 015
The camera move is time bounded, slows before the door-side ending, and stops on a precise handoff pose.

## Shot 016
Explicit `NON_GENERATIVE_TRANSITION`; no fabricated asset, keyframe, or video prompt.
