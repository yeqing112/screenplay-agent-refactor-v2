# Production Canary Authorized Source Structuring V2 Report

- Run ID: `20261005T154004Z`
- Status: `LLM_STRUCTURING_SOURCE_GROUNDING_FAILED`
- Base HEAD: `d5d2907e3e95843cee62aca244748b19a2c16f2f`
- Source SHA unchanged: `true`
- Profile: `local-llm-2vydoz / mimo-v2.5 / openai-compatible`
- Actual request fingerprint: `3dcb8e154f0572720b2bf327cb77b770fe71ca51390f558bffed6a5cc3ba8950`
- Transport attempts: `1 / 1`
- Retry: `false`
- Raw response persisted before parse: `true`
- Raw response SHA-256: `f4204059934cf19eebf4fcb94278756c48eaefce853d947cb5af16db133452ef`
- JSON parse: `PASS`
- Candidate V2 schema: `PASS`
- Grounding: `FAIL`
- Participants: `林晚`, `顾沉`
- Target dialogue: `也许是你自己` exactly once, speaker `顾沉`
- Binding: `AUTHORIZED_SEMANTIC_BINDING / COREFERENCE_RESOLUTION`
- Reported speech promotion count: `2`
- New Book / Script / FactSnapshot / ScriptIR: `not created`
- ScriptIR qualification: `not reached`
- Production resolve: `not reached`
- Treatment / Blocking / ShotPlan / Storyboard / PromptIR: `0`
- IMAGE / VIDEO: `0 / 0`
- Production writes: `0`

## Failure reason

The provider returned two reported-speech fragments as dialogue, and the target dialogue speaker identity evidence did not contain the literal `顾沉`. Deterministic grounding rejected the candidate. The single authorization was consumed; no retry, repair, fallback, persistence, or downstream execution occurred.

```json
{
  "actual_request_fingerprint": "3dcb8e154f0572720b2bf327cb77b770fe71ca51390f558bffed6a5cc3ba8950",
  "base_head": "d5d2907e3e95843cee62aca244748b19a2c16f2f",
  "binding_classification": "AUTHORIZED_SEMANTIC_BINDING",
  "binding_type": "COREFERENCE_RESOLUTION",
  "candidate_schema": "PASS",
  "candidate_v2_schema_status": "PASS",
  "db_writes": 0,
  "director_executed": false,
  "downstream_execution": {
    "image": 0,
    "prompt_ir": 0,
    "scene_blocking": 0,
    "shot_plan": 0,
    "storyboard": 0,
    "treatment": 0,
    "video": 0
  },
  "expected_status": "PRODUCTION_CANARY_SOURCE_STRUCTURED_V2",
  "external_llm_calls": 1,
  "fact_snapshot_id": null,
  "failure_rule": "No retry, no fallback, no production persistence after grounding failure.",
  "grounding": "FAIL",
  "grounding_errors": [
    {
      "code": "DIALOGUE_NOT_DIRECT_QUOTE",
      "text": "胶片被人拿走了。"
    },
    {
      "code": "REPORTED_SPEECH_PROMOTED",
      "text": "胶片被人拿走了。"
    },
    {
      "code": "DIALOGUE_NOT_DIRECT_QUOTE",
      "text": "是谁"
    },
    {
      "code": "REPORTED_SPEECH_PROMOTED",
      "text": "是谁"
    },
    {
      "code": "SPEAKER_IDENTITY_EVIDENCE_MISSING",
      "speaker": "顾沉"
    }
  ],
  "grounding_status": "FAIL",
  "implementation_commit_sha": "ab46be8c8f3609301f0f40d33088238f88ff4f09",
  "json_parse": "PASS",
  "json_parse_status": "PASS",
  "model": "mimo-v2.5",
  "new_book_id": null,
  "new_script_id": null,
  "participants": [
    "林晚",
    "顾沉"
  ],
  "production_resolve": "NOT_RUN",
  "production_writes": {
    "book": 0,
    "fact_records": 0,
    "fact_snapshot": 0,
    "script": 0,
    "script_ir_version": 0
  },
  "profile_id": "local-llm-2vydoz",
  "provider": "openai-compatible",
  "raw_response_length": 1418,
  "raw_response_persisted_before_parse": true,
  "raw_response_sha256": "f4204059934cf19eebf4fcb94278756c48eaefce853d947cb5af16db133452ef",
  "real_image_calls": 0,
  "real_video_calls": 0,
  "reported_speech_promotion_count": 2,
  "retry": false,
  "retry_occurred": false,
  "run_id": "20261005T154004Z",
  "script_ir_qualification_state": null,
  "script_ir_version_id": null,
  "semantic_diff_status": "NOT_RUN_AFTER_GROUNDING_FAILURE",
  "source_sha256": "190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1",
  "source_sha_unchanged": true,
  "speaker_binding": {
    "participants": [
      "林晚",
      "顾沉"
    ],
    "run_id": "20261005T154004Z",
    "status": "PASS",
    "target": {
      "binding_classification": "AUTHORIZED_SEMANTIC_BINDING",
      "binding_type": "COREFERENCE_RESOLUTION",
      "match_count": 1,
      "run_id": "20261005T154004Z",
      "speaker": "顾沉",
      "status": "PASS",
      "target_quote": "也许是你自己",
      "target_quote_sha256": "f77d206835ad01882841e6e3c864de7543fbcf478a39cab3ad0bbce90722939a"
    }
  },
  "status": "LLM_STRUCTURING_SOURCE_GROUNDING_FAILED",
  "target_dialogue": {
    "binding_classification": "AUTHORIZED_SEMANTIC_BINDING",
    "binding_type": "COREFERENCE_RESOLUTION",
    "match_count": 1,
    "run_id": "20261005T154004Z",
    "speaker": "顾沉",
    "status": "PASS",
    "target_quote": "也许是你自己",
    "target_quote_sha256": "f77d206835ad01882841e6e3c864de7543fbcf478a39cab3ad0bbce90722939a"
  },
  "target_dialogue_exact": true,
  "target_dialogue_sha256": "f77d206835ad01882841e6e3c864de7543fbcf478a39cab3ad0bbce90722939a",
  "target_dialogue_speaker": "顾沉",
  "target_dialogue_text": "也许是你自己",
  "transport_attempts": 1,
  "transport_attempts_exactly_one": true,
  "working_tree": "clean_before_report_update"
}
```
