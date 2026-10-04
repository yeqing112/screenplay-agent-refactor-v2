# 75API Image Timeout Hierarchy and Fresh Character Canary

- Status: `AUTONOMOUS_VISUAL_ASSET_PIPELINE_PARTIAL`
- Run: `20261004T102258Z`
- Failure: `LIN_WAN:SUBMISSION_UNKNOWN::timeout_evidence={"connect_timeout_seconds": 10, "elapsed_seconds": 40.106, "margin_seconds": 60, "orchestration_read_timeout_seconds": 180, "orchestration_timeout_seconds": 180, "pool_timeout_seconds": 30, "provider_timeout_seconds": 120, "request_finished_at": 449318.4749267, "request_started_at": 449278.3688166, "timeout_layer": "NONE", "write_timeout_seconds": 60}`
- Old ambiguous run `de83476`: `CLOSED_SUBMISSION_AMBIGUOUS`; retry/resume/reuse disabled
- Real IMAGE calls: `1`; real VIDEO calls: `0`
- Partial run retained under publish-staging; failed authorities have no final board.
- Lin Wan: status=INCOMPLETE; board=NOT_PUBLISHED; reason=PROVIDER_NO_IMAGE_DATA
- Lu Shu: status=NOT_STARTED; board=NOT_PUBLISHED
- HANDBAG: status=INCOMPLETE/NOT_STARTED; board=NOT_PUBLISHED
- Staging retained: `D:\Work\Project\screenplay-agent-refactor-v2\work\75api-autonomous-character-prop-canary-v2\20261004T102258Z\publish-staging`
