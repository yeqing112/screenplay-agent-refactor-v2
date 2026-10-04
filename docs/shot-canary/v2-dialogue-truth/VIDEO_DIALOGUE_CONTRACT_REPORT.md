# Video Dialogue Contract Truth Closure

- Zero-call Gate: `PASS`.
- Historical run: `VIDEO_PROVIDER_PROMPT_PROJECTION_SPLIT_BRAIN`.
- Canonical SC002_007 prompt has `DialogueMode.NONE` and explicit silence contract.
- Historical Provider input contained `严格按照导演动作和对白时间执行`; this is a positive dialogue leakage in the old submission path.
- Existing audio forensics and sampled visual mouth-motion audit are captured separately; no audio was stripped.
- Real IMAGE calls: `0`; Real VIDEO calls: `0` in this zero-call step.
