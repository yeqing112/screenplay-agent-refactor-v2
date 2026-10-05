# Deterministic Candidate Salvage V1 Report

- Status: `DETERMINISTIC_CANDIDATE_SALVAGE_READY`
- Historical authorization: `HISTORICAL_AUTHORIZATION_REMAINS_CONSUMED`
- Original failure replay: `PASS`
- Demotions: `2`
- Target speaker/text/binding unchanged: `true`
- Scene label source literal: `false`; strict scene identity uses earliest exact scene evidence
- Salvaged grounding: `PASS`
- ScriptIR dry run: `qualified`
- Semantic diff: `SOURCE_TO_SCRIPT_IR_SEMANTIC_DIFF_EMPTY`
- Source requirement: `PASS`
- External LLM / IMAGE / VIDEO: `0 / 0 / 0`
- Production writes: `0`
- Next state: `PRODUCTION_PERSISTENCE_AUTHORIZATION_REQUIRED`

```json
{
  "demoted_action_texts": [
    "顾沉说胶片被人拿走了。",
    "林晚问是谁"
  ],
  "demoted_dialogues": 2,
  "external_llm_calls": 0,
  "grounding": "PASS",
  "historical_failure_replay": "PASS",
  "next_state": "PRODUCTION_PERSISTENCE_AUTHORIZATION_REQUIRED",
  "production_writes": 0,
  "reported_speech_promotion_count": 0,
  "run_id": "20261005T155952Z",
  "salvage_new_semantic_decisions": 0,
  "salvage_new_source_text_count": 0,
  "scene_label_source_literal": false,
  "script_ir": "qualified",
  "semantic_diff": "SOURCE_TO_SCRIPT_IR_SEMANTIC_DIFF_EMPTY",
  "source_requirement": "PASS",
  "status": "DETERMINISTIC_CANDIDATE_SALVAGE_READY",
  "strict_scene_identity": "顾沉带林晚进入暗房。",
  "target_binding_classification": "AUTHORIZED_SEMANTIC_BINDING",
  "target_binding_type": "COREFERENCE_RESOLUTION",
  "target_identity_recovery_rule": "same-scene same-participant exact evidence containing speaker and preceding utterance; nearest preceding char_start",
  "target_speaker": "顾沉",
  "target_text": "也许是你自己"
}
```
