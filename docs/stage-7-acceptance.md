# Stage 7 Acceptance Notes

## Current Covered Flow

The current production-mode flow now supports:

1. Visual asset preparation
2. Structured storyboard editing
3. Prompt compilation with version history
4. Prompt lock / unlock protection
5. First-frame generation
6. Video generation gated on adopted first frame
7. Acceptance feedback persistence
8. Recompile from failure feedback
9. Batch compile / batch frame generation / batch video generation
10. Export readiness summary and blocked-shot checklist

## Recommended Manual Check

1. Open a book with storyboard and visual assets.
2. Pick one shot and bind scene / character / prop structure.
3. Compile prompts and confirm version number increases.
4. Lock the prompt version, then verify normal recompile is blocked.
5. Unlock or force compile and verify history still records the new version.
6. Generate a first frame and confirm the shot asset state updates.
7. Generate a video and confirm it is blocked until a first frame exists.
8. Save an acceptance record with failure tags and notes.
9. Recompile after feedback and confirm negative prompt becomes more specific.
10. Use batch operations on selected episodes and confirm locked prompts are skipped.
11. Open Export and confirm blocked shots / readiness numbers match storyboard state.

## Known Gaps

1. PDF / Word / Final Draft export buttons are still UI placeholders; JSON export and delivery history are now persisted.
2. Batch workflow is intentionally serial and conservative.
