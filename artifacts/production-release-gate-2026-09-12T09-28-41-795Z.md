# Production release gate

- Generated: 2026-09-12T09:28:41.796Z
- Result: **BLOCKED**

## Steps

| Step | Status | Exit code |
| --- | --- | ---: |
| production configuration verification | PASS | 0 |
| production sample registry validation | PASS | 0 |
| shot planning quality gate | BLOCKED | 2 |
| storyboard prompt zero-error gate | BLOCKED | 1 |
| deterministic production regression | PASS | 0 |

The gate is fail-closed: every step must pass. See the JSON report and the command-specific artifacts for blockers.

