# Shot Canary Report

Status: `REAL_SHOT_MEDIA_CANARY_MEDIA_QUALITY_FAILED`
Run: `20261004T162533Z`

## Shot Readiness

- Gate A: `SHOT_CANARY_READY_FOR_REAL_MEDIA`
- Duration projection: `5.0→5`, `13.5→14`, `8.5→9`; fractional truncation `0`.
- Unauthorized props: `0`; hand/prop mismatch: `0`; missing authorities: `0`.
- APPLE Authority: `READY` via one 75api IMAGE and semantic Judge PASS.

## Keyframes

- Three initial keyframes: semantic/identity/prop-state Judge PASS; explicit review `APPROVE`.
- SC002_007 v1 remained authoritative while v2 Candidate was pending; v2 was then explicitly approved.
- Geometry: all returned `1672×941`, requested/submitted `16:9`, valid.

## VIDEO

- First VIDEO `SH_E01_SC002_007` submitted once with `seconds=5`; reconcile and polling used the same provider task.
- Provider completed successfully, but ffprobe found `audio_streams=1`; required value is `0`.
- Result: `MEDIA_QUALITY_FAILED`; stopped before SC002_002, SC002_006, and the VIDEO preservation regenerate.

## Safety

- Real IMAGE calls: `5` total external submissions (Apple, three initial keyframes, and the mandated SC002_007 keyframe regenerate; two were reused from the audited first attempt to avoid duplicate billing).
- Real VIDEO calls: `1`.
- Production writes: `0`; Book 990400 writes: `0`; SHAPI: `0`; Poyo: `0`; secret leaks: `0`; orphans: `0`.
- No automatic regeneration after the quality failure.
