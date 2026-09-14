# Production release gate

- Generated: 2026-09-13T05:08:50.877Z
- Result: **BLOCKED**

## Steps

| Step | Status | Exit code | Release blocker |
| --- | --- | ---: | --- |
| production configuration verification | BLOCKED | 0 | DEPLOYMENT_ENV must be production or staging for a release gate |
| production sample registry validation | PASS | 0 |  |
| shot planning quality gate | BLOCKED | 2 | 真实 active 镜头不足（3/30）；缺少意图状态：needs_information；缺少节拍状态：conflict |
| ↳ next actions | — | — | 补充真实 active 镜头，直到达到至少 30 个；在正式镜头工作台补齐意图证据：needs_information；在正式镜头工作台补齐节拍证据：conflict |
| ↳ evidence artifact | — | — | D:\Work\Project\screenplay-agent-refactor-v2\artifacts\shot-executability-replay.json |
| storyboard prompt zero-error gate | BLOCKED | 1 |  |
| ↳ evidence artifact | — | — | D:\Work\Project\screenplay-agent-refactor-v2\artifacts\storyboard-prompt-real-sample-audit-2026-09-13T05-04-40-898Z.json |
| deterministic production regression | PASS | 0 |  |
| production real-browser regression | BLOCKED | 1 |  |

The gate is fail-closed: every step must pass. See the JSON report and the command-specific artifacts for blockers.

