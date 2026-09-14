# Production release gate

- Generated: 2026-09-12T10:04:52.794Z
- Result: **BLOCKED**

## Steps

| Step | Status | Exit code | Release blocker |
| --- | --- | ---: | --- |
| production configuration verification | BLOCKED | 0 | DEPLOYMENT_ENV must be production or staging for a release gate |
| production sample registry validation | PASS | 0 |  |
| shot planning quality gate | BLOCKED | 2 | 真实 active 镜头不足（3/30）；缺少意图状态：needs_information；缺少节拍状态：conflict |
| ↳ next actions | — | — | 补充真实 active 镜头，直到达到至少 30 个；在正式镜头工作台补齐意图证据：needs_information；在正式镜头工作台补齐节拍证据：conflict |
| storyboard prompt zero-error gate | BLOCKED | 1 |  |
| deterministic production regression | PASS | 0 |  |

The gate is fail-closed: every step must pass. See the JSON report and the command-specific artifacts for blockers.

