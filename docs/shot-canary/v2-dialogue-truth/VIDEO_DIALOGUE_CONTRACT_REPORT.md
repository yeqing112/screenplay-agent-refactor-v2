# Video Dialogue Contract Truth Closure

Status: `VIDEO_DIALOGUE_CONTRACT_BLOCKED`

Provider evidence:
- task_id: `task_RWLHafO80Ll53cDtReyNDn1KqKUqNetg`
- provider `properties.input` captured: `False`
- prompt truth chain: `VIDEO_PROMPT_TRUTH_CHAIN_BROKEN`
- origin/upstream/completion model: `None` / `None` / `75api-minimax-h3-fast-20260911`

Root cause:
- Provider status responses did not expose `properties.input`; provider-side prompt truth is unavailable. The fresh media also contains an AAC audio stream, but the audio contract violation cannot be promoted to a proven classification while the provider truth chain is blocked.

Existing video forensic:
- `EXISTING_VIDEO_AUDIO_FORENSICS.json`; `EXISTING_VIDEO_DIALOGUE_VISUAL_AUDIT.json`
- Historical run: `VIDEO_PROVIDER_PROMPT_PROJECTION_SPLIT_BRAIN`; original evidence unchanged.
- Historical visual audit: Lin Wan `False`, Lu Shu `True` speech-like mouth motion.

Truth chain:
- Canonical and submission SHA match: `True`.
- Provider recorded prompt SHA: missing properties input.
- SC002_007 contract: `DialogueMode.NONE`, both characters silent, no visual lipsync, no audio generation.

Fresh SC002_007:
- Real IMAGE: `0`; Real VIDEO: `1`
- Audio streams: `1` (AAC stereo, 32 kHz)
- Speech-like mouth motion: `False` for Lin Wan and Lu Shu
- Media: `docs/shot-canary/v2-dialogue-truth/fresh-media/20261004T183140Z/SH_E01_SC002_007-video-fresh.mp4`

Tests:
- Prompt IR targeted suite: `43 passed`
- Existing baseline remains `2086 passed / 24 failed`; new failures: `0`

Safety:
- Production writes: `0`; Book 990400 writes: `0`; SHAPI: `0`; PoYo: `0`; secret leaks: `0`; orphan rows: `0`

Commit:
- Execution base: `36a40d7206f52b1ae5fa0f399a1f9f3b84453d6b`
- Final docs commit: `331a912280a29c2addc4d066e70872af5a5673ec`

Working tree:
- Working tree clean after commit.
