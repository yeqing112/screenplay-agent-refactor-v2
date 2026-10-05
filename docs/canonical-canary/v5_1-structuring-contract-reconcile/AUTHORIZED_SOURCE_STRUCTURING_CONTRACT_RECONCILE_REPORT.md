# Authorized Source Structuring Contract Reconcile v1.1

- Status: `SOURCE_GROUNDED_SCRIPT_IR_PREPARATION_READY`
- Next state: `AUTHORIZED_LLM_RECALL_REQUIRED`
- Historical V1: `HISTORICAL_INVALID_RESPONSE_UNREPLAYABLE`; replayable: `false`; exact root cause: `UNKNOWN`
- Source: Book 990402 / Chapter 16; SHA-256: `190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1`
- Candidate V2 offline fixture: `PASS`
- Strict preparation policy: `SOURCE_GROUNDED_STRICT`
- Strict ScriptIR validation: `qualified`
- Strict ScriptIR warnings: `[{'code': 'SCENE_BEATS_EMPTY', 'message': 'CH03_SC01 has no beats.'}, {'code': 'SCENE_TRANSITIONS_EMPTY', 'message': 'ScriptIR has no SceneTransitionContract records.'}]`
- Source → ScriptIR semantic diff: `SOURCE_TO_SCRIPT_IR_SEMANTIC_DIFF_EMPTY`
- Invented dialogue/action/character/beat/transition/dramatic classification: `[0, 0, 0, 0, 0, 0]`
- Evidence locator: `PASS` (char offsets, UTF-8 byte offsets, SHA-256 and occurrence count are local)
- Speaker binding: `AUTHORIZED_SEMANTIC_BINDING` for `他 → 顾沉`; no literal-binding claim is made
- Reported speech audit: `REPORTED_SPEECH_PROMOTION_AUDIT_V2`
- Response retention: forensic artifact required before validation; secrets forbidden
- Next provider profile: `local-llm-2vydoz` / `mimo-v2.5`
- Prior dry-run contract fingerprint: `2af9f6a1375ec7d8bb252150ab899e680611340c6bc039e403312166a182445a`
- Current dry-run request fingerprint: `2af9f6a1375ec7d8bb252150ab899e680611340c6bc039e403312166a182445a`
- Actual request fingerprint: `NOT_COMPUTED_NOT_SENT`
- Next LLM call authorization required: `true`
- External LLM / IMAGE / VIDEO / SHAPI / Poyo / 75API calls this phase: `0`
- Production DB / PromptIR / Media / OfficialMedia writes: `0`

The dry run was not sent. No production source, Script, ScriptIR or media authority was created.
