# Production release gate

- Generated: 2026-09-25T16:25:32.563Z
- Result: **BLOCKED**

## Steps

| Step | Status | Exit code | Release blocker |
| --- | --- | ---: | --- |
| production configuration verification | BLOCKED | 0 | DEPLOYMENT_ENV must be production or staging for a release gate |
| production sample registry validation | PASS | 0 |  |
| shot planning quality gate | BLOCKED | 1 |  |
| storyboard prompt zero-error gate | BLOCKED | 1 |  |
| deterministic production regression | PASS | 0 |  |
| production real-browser regression | BLOCKED | 1 |  |

The gate is fail-closed: every step must pass. See the JSON report and the command-specific artifacts for blockers.

