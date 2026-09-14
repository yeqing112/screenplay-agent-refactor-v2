# Production release gate

- Generated: 2026-09-12T09:33:14.721Z
- Result: **BLOCKED**

## Steps

| Step | Status | Exit code | Release blocker |
| --- | --- | ---: | --- |
| production configuration verification | BLOCKED | 0 | DEPLOYMENT_ENV must be production or staging for a release gate |
| production sample registry validation | PASS | 0 |  |
| shot planning quality gate | BLOCKED | 2 |  |
| storyboard prompt zero-error gate | BLOCKED | 1 |  |
| deterministic production regression | PASS | 0 |  |

The gate is fail-closed: every step must pass. See the JSON report and the command-specific artifacts for blockers.

