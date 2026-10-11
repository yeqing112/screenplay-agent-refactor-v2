# DIRECTOR SEMANTIC GROUNDING V3 FOUNDATION

Status: `DIRECTOR_SEMANTIC_GROUNDING_V3_FOUNDATION_READY`

V3 is deterministic, typed, versioned and `SHADOW_ONLY`. It does not replace V2 production gating, call a provider, confirm a proposal, or mutate Packet 64. It uses schema-aware extraction and typed subject/predicate/object support; it does not use a phrase-specific whitelist or blacklist as semantic authority.

## Claim sets

- ClaimIR schema: `director_claim_ir_v1`; shadow schema: `director_semantic_grounding_v3_shadow_audit_v1`.
- Source claims: `31`; Stage A attempt-7: `34`; Attempt-9: `134`; Attempt-10: `141`; Attempt-11: `145`; compiled: `306`.
- Source claim fingerprint: `93218b1cd5fceb0dd97e7396250ed7ad05a95ebdfd5a0fff4b3620d3e854f0a6`.

## Shadow statuses

- Stage A: `BLOCKED`; fact bootstrap: `BLOCKED`.
- Attempt-9: `BLOCKED`; historical violations reproduced: certainty collapse, unsupported key-prop action, spatial blocking.
- Attempt-10: `DIAGNOSTIC_ONLY` (`DIAGNOSTIC_ONLY`; structural schema remains invalid because `visual_priority` is missing).
- Attempt-11: `BLOCKED`; structural schema `PASS`, coverage `11/11`, `visual_priority` present.
- Compiled: `BLOCKED`; upstream unsupported claims are not laundered into source authority.

## Mandatory Attempt-11 and Stage A cases

[
  {
    "case": "delegation",
    "present": true,
    "expected_claim_type": "AUTHORITY_DELEGATION",
    "claim": {
      "schema_version": "director_claim_ir_v1",
      "claim_id": "DC_STAGE_B_note_AUTHORITY_DELEGATION_00",
      "source_path": "note",
      "raw_text": "本 IR 严格基于 SOURCE_AUTHORING_UNITS 与 Stage A 已验证的 beat plan 生成，未引入新的故事事实、角色知识或感官细节。所有表演方向均为可执行的表演选项，保留了来源中的不确定性（想不起、也许）。未指定具体镜头执行与空间走位，交由下游 SceneBlocking 与 ShotPlan 权威处理。",
      "claim_type": "AUTHORITY_DELEGATION",
      "subject": {
        "kind": "DIRECTOR",
        "ref": "stage_b"
      },
      "predicate": "delegates_to",
      "object": {
        "kind": "AUTHORITY",
        "ref": "SceneBlocking+ShotPlan"
      },
      "qualifiers": {},
      "polarity": "DELEGATION",
      "modality": "DELEGATED",
      "canonicality": "META",
      "authority_required": "NONE",
      "source_refs": [],
      "upstream_claim_refs": [],
      "origin": "STAGE_B",
      "support_status": "META_SAFE",
      "metadata": {
        "target_authority": [
          "SceneBlocking",
          "ShotPlan"
        ]
      },
      "fingerprint": "3e9f21e4c6c21387a2b76a182f7af42dacbf024723252714026cfe45415fa282"
    },
    "support": "META_SAFE",
    "authority": {
      "status": "META_SAFE",
      "authority_required": "NONE",
      "reason": "metadata_or_delegation_does_not_assert_story_fact"
    },
    "result": "SAFE_META_DELEGATION",
    "reason": "metadata_or_delegation_does_not_assert_story_fact"
  },
  {
    "case": "试探林晚",
    "present": true,
    "expected_claim_type": "CHARACTER_INTENT",
    "claim": {
      "schema_version": "director_claim_ir_v1",
      "claim_id": "DC_STAGE_B_beat_enrichments_2_performance_CHARACTER_INTENT_02",
      "source_path": "beat_enrichments[2].performance",
      "raw_text": "顾沉说出'也许是你自己'时语气应平静而带有试探性，不作断言；林晚的追问'是谁'应带着急切与不安，听到回答后出现明显的僵住或呼吸停滞，但不作辩解或承认。",
      "claim_type": "CHARACTER_INTENT",
      "subject": {
        "kind": "CHARACTER",
        "ref": "顾沉"
      },
      "predicate": "test_or_probe",
      "object": {
        "kind": "CHARACTER",
        "ref": "林晚"
      },
      "qualifiers": {
        "dialogue_cue": "也许是你自己"
      },
      "polarity": "POSITIVE",
      "modality": "ASSERTED",
      "canonicality": "CANONICAL_ASSERTION",
      "authority_required": "SOURCE",
      "source_refs": [
        "SAU_E01_SC001_006",
        "SAU_E01_SC001_007",
        "SAU_E01_SC001_008"
      ],
      "upstream_claim_refs": [],
      "origin": "STAGE_B",
      "support_status": "UNRESOLVED",
      "fingerprint": "32eec6a41bd232a7779b88b72be2b4b48bf9299716ff49f9b1f9f029d18a9755"
    },
    "support": "UNSUPPORTED",
    "authority": {
      "status": "SOURCE_SUPPORT_REQUIRED",
      "authority_required": "SOURCE",
      "reason": "stage_b cannot create a new canonical fact"
    },
    "result": "UNSUPPORTED",
    "reason": "Dialogue and observable action do not authorize a canonical motive or hidden strategy."
  },
  {
    "case": "不惊动林晚",
    "present": true,
    "expected_claim_type": "CHARACTER_INTENT",
    "claim": {
      "schema_version": "director_claim_ir_v1",
      "claim_id": "DC_STAGE_B_character_directions_1_obstacle_CHARACTER_INTENT_03",
      "source_path": "character_directions[1].obstacle",
      "raw_text": "顾沉需要在不惊动林晚的前提下观察她的反应，同时应对门外神秘人的出现。",
      "claim_type": "CHARACTER_INTENT",
      "subject": {
        "kind": "CHARACTER",
        "ref": "顾沉"
      },
      "predicate": "observe_without_alerting",
      "object": {
        "kind": "CHARACTER",
        "ref": "林晚"
      },
      "qualifiers": {
        "strategy": "observe_reaction"
      },
      "polarity": "POSITIVE",
      "modality": "ASSERTED",
      "canonicality": "CANONICAL_ASSERTION",
      "authority_required": "SOURCE",
      "source_refs": [],
      "upstream_claim_refs": [],
      "origin": "STAGE_B",
      "support_status": "UNRESOLVED",
      "fingerprint": "338ade20faad8b24c32bc37013d551b0255b7fe8eaba3765625e7505b64d64ee"
    },
    "support": "UNSUPPORTED",
    "authority": {
      "status": "SOURCE_SUPPORT_REQUIRED",
      "authority_required": "SOURCE",
      "reason": "stage_b cannot create a new canonical fact"
    },
    "result": "UNSUPPORTED",
    "reason": "Dialogue and observable action do not authorize a canonical motive or hidden strategy."
  },
  {
    "case": "微弱光线",
    "present": true,
    "expected_claim_type": "ENVIRONMENT_STATE",
    "claim": {
      "schema_version": "director_claim_ir_v1",
      "claim_id": "DC_STAGE_B_beat_enrichments_3_character_effects_1_effect_ENVIRONMENT_STATE_04",
      "source_path": "beat_enrichments[3].character_effects[1].effect",
      "raw_text": "林晚在黑暗中配合躲藏，接过车票后在微弱光线下阅读背面指令，表情从紧张转为困惑与警觉。",
      "claim_type": "ENVIRONMENT_STATE",
      "subject": {
        "kind": "ENVIRONMENT",
        "ref": "暗房"
      },
      "predicate": "light_level",
      "object": {
        "kind": "LIGHT",
        "ref": "dim"
      },
      "qualifiers": {},
      "polarity": "POSITIVE",
      "modality": "ASSERTED",
      "canonicality": "CANONICAL_ASSERTION",
      "authority_required": "SOURCE",
      "source_refs": [],
      "upstream_claim_refs": [],
      "origin": "STAGE_B",
      "support_status": "UNRESOLVED",
      "fingerprint": "a0e31be986daa8ff5f969782124d011ca57d9bb0ae270bbf167392352521fb33"
    },
    "support": "UNSUPPORTED",
    "authority": {
      "status": "SOURCE_SUPPORT_REQUIRED",
      "authority_required": "SOURCE",
      "reason": "stage_b cannot create a new canonical fact"
    },
    "result": "UNSUPPORTED",
    "reason": "A flickering red safety light and later extinguishing it do not entail a remaining dim-light state."
  },
  {
    "case": "车票背面的手写指令",
    "present": true,
    "expected_claim_type": "OBJECT_PROPERTY",
    "claim": {
      "schema_version": "director_claim_ir_v1",
      "claim_id": "DC_STAGE_B_visual_priority_6_OBJECT_PROPERTY_05",
      "source_path": "visual_priority[6]",
      "raw_text": "车票背面的手写指令",
      "claim_type": "OBJECT_PROPERTY",
      "subject": {
        "kind": "OBJECT",
        "ref": "车票背面"
      },
      "predicate": "handwritten",
      "object": {
        "kind": "PROPERTY",
        "ref": "handwritten"
      },
      "qualifiers": {},
      "polarity": "POSITIVE",
      "modality": "ASSERTED",
      "canonicality": "CANONICAL_ASSERTION",
      "authority_required": "SOURCE",
      "source_refs": [],
      "upstream_claim_refs": [],
      "origin": "STAGE_B",
      "support_status": "UNRESOLVED",
      "metadata": {
        "explicit_target": "车票背面"
      },
      "fingerprint": "b5aff4381ca028150e28e60277bd1fe4baca92f4cd64f9f7f85d13d4a8846b7e"
    },
    "support": "AMBIGUOUS_REVIEW_REQUIRED",
    "authority": {
      "status": "SOURCE_SUPPORT_REQUIRED",
      "authority_required": "SOURCE",
      "reason": "stage_b cannot create a new canonical fact"
    },
    "result": "AMBIGUOUS_REVIEW_REQUIRED",
    "reason": "Source says the ticket back contains text, but does not state that the ticket writing is handwritten."
  },
  {
    "case": "接过车票",
    "present": true,
    "expected_claim_type": "OBJECT_POSSESSION",
    "claim": {
      "schema_version": "director_claim_ir_v1",
      "claim_id": "DC_STAGE_B_beat_enrichments_3_performance_OBJECT_POSSESSION_06",
      "source_path": "beat_enrichments[3].performance",
      "raw_text": "顾沉熄灯与拉林晚躲藏的动作应迅速而果断，两人在黑暗中保持静止与屏息；林晚接过车票后阅读背面文字，表情从紧张转为困惑与警觉，不作多余动作。",
      "claim_type": "OBJECT_POSSESSION",
      "subject": {
        "kind": "CHARACTER",
        "ref": "顾沉"
      },
      "predicate": "receives",
      "object": {
        "kind": "OBJECT",
        "ref": "车票"
      },
      "qualifiers": {},
      "polarity": "POSITIVE",
      "modality": "ASSERTED",
      "canonicality": "CANONICAL_ASSERTION",
      "authority_required": "SOURCE",
      "source_refs": [
        "SAU_E01_SC001_009",
        "SAU_E01_SC001_010",
        "SAU_E01_SC001_011",
        "SAU_E01_SC001_012"
      ],
      "upstream_claim_refs": [],
      "origin": "STAGE_B",
      "support_status": "UNRESOLVED",
      "fingerprint": "6f4be0f1344461eff23450096fca329299d956c1dc485ca4fc2241fb28e62947"
    },
    "support": "AMBIGUOUS_REVIEW_REQUIRED",
    "authority": {
      "status": "SOURCE_SUPPORT_REQUIRED",
      "authority_required": "SOURCE",
      "reason": "stage_b cannot create a new canonical fact"
    },
    "result": "AMBIGUOUS_REVIEW_REQUIRED",
    "reason": "The source says an unknown person inserts a ticket; it does not state that Lin Wan takes possession of it."
  },
  {
    "case": "母亲留下的物件",
    "present": true,
    "expected_claim_type": "OBJECT_PROVENANCE",
    "claim": {
      "schema_version": "director_claim_ir_v1",
      "claim_id": "DC_STAGE_B_character_directions_0_direction_OBJECT_PROVENANCE_07",
      "source_path": "character_directions[0].direction",
      "raw_text": "林晚在暗房中保持警觉与克制，对母亲留下的物件有细微的身体反应但不作确认性表态，全程处于'认出但想不起'的悬置状态。",
      "claim_type": "OBJECT_PROVENANCE",
      "subject": {
        "kind": "PERSON",
        "ref": "母亲"
      },
      "predicate": "left_by",
      "object": {
        "kind": "OBJECT",
        "ref": "暗房"
      },
      "qualifiers": {},
      "polarity": "POSITIVE",
      "modality": "ASSERTED",
      "canonicality": "CANONICAL_ASSERTION",
      "authority_required": "SOURCE",
      "source_refs": [],
      "upstream_claim_refs": [],
      "origin": "STAGE_B",
      "support_status": "UNRESOLVED",
      "fingerprint": "eb675ea9436dffdf99f4cb527d0441f8392b4ec9c89ce0f017f145fbcf9dafc3"
    },
    "support": "UNSUPPORTED",
    "authority": {
      "status": "SOURCE_SUPPORT_REQUIRED",
      "authority_required": "SOURCE",
      "reason": "stage_b cannot create a new canonical fact"
    },
    "result": "UNSUPPORTED",
    "reason": "A mother-authored label does not entail that the mother left or owned the referenced object."
  },
  {
    "case": "第一次直面母亲留下的暗房",
    "present": true,
    "expected_claim_type": "CERTAINTY_ASSERTION",
    "claim": {
      "schema_version": "director_claim_ir_v1",
      "claim_id": "DC_STAGE_B_rhythm_strategy_reveal_CERTAINTY_ASSERTION_08",
      "source_path": "rhythm_strategy.reveal",
      "raw_text": "铁盒的空缺、烧焦胶片与海鸥别针依次揭示，节奏由缓转紧；林晚认出别针却想不起的空白制造第一次心理悬念。",
      "claim_type": "CERTAINTY_ASSERTION",
      "subject": {
        "kind": "CHARACTER",
        "ref": "林晚"
      },
      "predicate": "first_or_never",
      "object": {
        "kind": "EVENT",
        "ref": "darkroom_visit"
      },
      "qualifiers": {
        "cue": "第一次"
      },
      "polarity": "POSITIVE",
      "modality": "ASSERTED",
      "canonicality": "CANONICAL_ASSERTION",
      "authority_required": "SOURCE",
      "source_refs": [],
      "upstream_claim_refs": [],
      "origin": "STAGE_B",
      "support_status": "UNRESOLVED",
      "fingerprint": "40147be168b26324817a0da9c7c22a051d27560638484667b4ca7513166e5ae1"
    },
    "support": "UNSUPPORTED",
    "authority": {
      "status": "SOURCE_SUPPORT_REQUIRED",
      "authority_required": "SOURCE",
      "reason": "stage_b cannot create a new canonical fact"
    },
    "result": "UNSUPPORTED",
    "reason": "No typed SourceClaim supports this canonical assertion."
  },
  {
    "case": "母亲留下的暗房",
    "present": true,
    "expected_claim_type": "OBJECT_PROVENANCE",
    "claim": {
      "schema_version": "director_claim_ir_v1",
      "claim_id": "DC_STAGE_B_character_directions_0_direction_OBJECT_PROVENANCE_07",
      "source_path": "character_directions[0].direction",
      "raw_text": "林晚在暗房中保持警觉与克制，对母亲留下的物件有细微的身体反应但不作确认性表态，全程处于'认出但想不起'的悬置状态。",
      "claim_type": "OBJECT_PROVENANCE",
      "subject": {
        "kind": "PERSON",
        "ref": "母亲"
      },
      "predicate": "left_by",
      "object": {
        "kind": "OBJECT",
        "ref": "暗房"
      },
      "qualifiers": {},
      "polarity": "POSITIVE",
      "modality": "ASSERTED",
      "canonicality": "CANONICAL_ASSERTION",
      "authority_required": "SOURCE",
      "source_refs": [],
      "upstream_claim_refs": [],
      "origin": "STAGE_B",
      "support_status": "UNRESOLVED",
      "fingerprint": "eb675ea9436dffdf99f4cb527d0441f8392b4ec9c89ce0f017f145fbcf9dafc3"
    },
    "support": "UNSUPPORTED",
    "authority": {
      "status": "SOURCE_SUPPORT_REQUIRED",
      "authority_required": "SOURCE",
      "reason": "stage_b cannot create a new canonical fact"
    },
    "result": "UNSUPPORTED",
    "reason": "A mother-authored label does not entail that the mother left or owned the referenced object."
  },
  {
    "case": "delegation",
    "present": false,
    "expected_claim_type": "AUTHORITY_DELEGATION",
    "status": "MISSING_CLAIM"
  },
  {
    "case": "试探林晚",
    "present": false,
    "expected_claim_type": "CHARACTER_INTENT",
    "status": "MISSING_CLAIM"
  },
  {
    "case": "不惊动林晚",
    "present": false,
    "expected_claim_type": "CHARACTER_INTENT",
    "status": "MISSING_CLAIM"
  },
  {
    "case": "微弱光线",
    "present": false,
    "expected_claim_type": "ENVIRONMENT_STATE",
    "status": "MISSING_CLAIM"
  },
  {
    "case": "车票背面的手写指令",
    "present": false,
    "expected_claim_type": "OBJECT_PROPERTY",
    "status": "MISSING_CLAIM"
  },
  {
    "case": "接过车票",
    "present": true,
    "expected_claim_type": "OBJECT_POSSESSION",
    "claim": {
      "schema_version": "director_claim_ir_v1",
      "claim_id": "DC_STAGE_A_beats_3_objective_OBJECT_POSSESSION_06",
      "source_path": "beats[3].objective",
      "raw_text": "让顾沉与林晚在黑暗中躲藏并接收门外陌生人递入的车票，为下一场戏埋下行动目标。",
      "claim_type": "OBJECT_POSSESSION",
      "subject": {
        "kind": "CHARACTER",
        "ref": "顾沉"
      },
      "predicate": "receives",
      "object": {
        "kind": "OBJECT",
        "ref": "车票"
      },
      "qualifiers": {},
      "polarity": "POSITIVE",
      "modality": "ASSERTED",
      "canonicality": "CANONICAL_ASSERTION",
      "authority_required": "SOURCE",
      "source_refs": [
        "SAU_E01_SC001_009",
        "SAU_E01_SC001_010",
        "SAU_E01_SC001_011",
        "SAU_E01_SC001_012"
      ],
      "upstream_claim_refs": [],
      "origin": "STAGE_A",
      "support_status": "UNRESOLVED",
      "fingerprint": "56a19992a6f03394b1fb1edb3bdc0c033c2cdfe9b2f91c2a5d05e538f9a8c604"
    },
    "support": "AMBIGUOUS_REVIEW_REQUIRED",
    "authority": {
      "status": "SOURCE_SUPPORT_REQUIRED",
      "authority_required": "SOURCE",
      "reason": "stage_a_cannot_bootstrap_canonical_fact"
    },
    "result": "AMBIGUOUS_REVIEW_REQUIRED",
    "reason": "The source says an unknown person inserts a ticket; it does not state that Lin Wan takes possession of it."
  },
  {
    "case": "母亲留下的物件",
    "present": true,
    "expected_claim_type": "OBJECT_PROVENANCE",
    "claim": {
      "schema_version": "director_claim_ir_v1",
      "claim_id": "DC_STAGE_A_scene_objective_OBJECT_PROVENANCE_07",
      "source_path": "scene_objective",
      "raw_text": "建立暗房的压抑氛围与林晚被卷入的悬疑处境，让母亲留下的空铁盒与海鸥别针成为撬动她记忆缺口的支点。",
      "claim_type": "OBJECT_PROVENANCE",
      "subject": {
        "kind": "PERSON",
        "ref": "母亲"
      },
      "predicate": "left_by",
      "object": {
        "kind": "OBJECT",
        "ref": "暗房"
      },
      "qualifiers": {},
      "polarity": "POSITIVE",
      "modality": "ASSERTED",
      "canonicality": "CANONICAL_ASSERTION",
      "authority_required": "SOURCE",
      "source_refs": [],
      "upstream_claim_refs": [],
      "origin": "STAGE_A",
      "support_status": "UNRESOLVED",
      "fingerprint": "bba5fcd52ccac6b0a9f44de5730a41acf760e644a81df20622fffe7c6eb60063"
    },
    "support": "UNSUPPORTED",
    "authority": {
      "status": "SOURCE_SUPPORT_REQUIRED",
      "authority_required": "SOURCE",
      "reason": "stage_a_cannot_bootstrap_canonical_fact"
    },
    "result": "UNSUPPORTED",
    "reason": "A mother-authored label does not entail that the mother left or owned the referenced object."
  },
  {
    "case": "第一次直面母亲留下的暗房",
    "present": true,
    "expected_claim_type": "CERTAINTY_ASSERTION",
    "claim": {
      "schema_version": "director_claim_ir_v1",
      "claim_id": "DC_STAGE_A_beats_0_objective_CERTAINTY_ASSERTION_08",
      "source_path": "beats[0].objective",
      "raw_text": "让林晚在顾沉的引导下第一次直面母亲留下的暗房与那只贴着标签的铁盒。",
      "claim_type": "CERTAINTY_ASSERTION",
      "subject": {
        "kind": "CHARACTER",
        "ref": "顾沉"
      },
      "predicate": "first_or_never",
      "object": {
        "kind": "EVENT",
        "ref": "darkroom_visit"
      },
      "qualifiers": {
        "cue": "第一次"
      },
      "polarity": "POSITIVE",
      "modality": "ASSERTED",
      "canonicality": "CANONICAL_ASSERTION",
      "authority_required": "SOURCE",
      "source_refs": [
        "SAU_E01_SC001_001",
        "SAU_E01_SC001_002",
        "SAU_E01_SC001_003"
      ],
      "upstream_claim_refs": [],
      "origin": "STAGE_A",
      "support_status": "UNRESOLVED",
      "fingerprint": "2da373289f1957d5e8b9e6897417f1c9eb5a5cbc437c10de549d09c25a7b0550"
    },
    "support": "UNSUPPORTED",
    "authority": {
      "status": "SOURCE_SUPPORT_REQUIRED",
      "authority_required": "SOURCE",
      "reason": "stage_a_cannot_bootstrap_canonical_fact"
    },
    "result": "UNSUPPORTED",
    "reason": "No typed SourceClaim supports this canonical assertion."
  },
  {
    "case": "母亲留下的暗房",
    "present": true,
    "expected_claim_type": "OBJECT_PROVENANCE",
    "claim": {
      "schema_version": "director_claim_ir_v1",
      "claim_id": "DC_STAGE_A_scene_objective_OBJECT_PROVENANCE_07",
      "source_path": "scene_objective",
      "raw_text": "建立暗房的压抑氛围与林晚被卷入的悬疑处境，让母亲留下的空铁盒与海鸥别针成为撬动她记忆缺口的支点。",
      "claim_type": "OBJECT_PROVENANCE",
      "subject": {
        "kind": "PERSON",
        "ref": "母亲"
      },
      "predicate": "left_by",
      "object": {
        "kind": "OBJECT",
        "ref": "暗房"
      },
      "qualifiers": {},
      "polarity": "POSITIVE",
      "modality": "ASSERTED",
      "canonicality": "CANONICAL_ASSERTION",
      "authority_required": "SOURCE",
      "source_refs": [],
      "upstream_claim_refs": [],
      "origin": "STAGE_A",
      "support_status": "UNRESOLVED",
      "fingerprint": "bba5fcd52ccac6b0a9f44de5730a41acf760e644a81df20622fffe7c6eb60063"
    },
    "support": "UNSUPPORTED",
    "authority": {
      "status": "SOURCE_SUPPORT_REQUIRED",
      "authority_required": "SOURCE",
      "reason": "stage_a_cannot_bootstrap_canonical_fact"
    },
    "result": "UNSUPPORTED",
    "reason": "A mother-authored label does not entail that the mother left or owned the referenced object."
  }
]

## V2 comparison

- V2 false positive fixed: the delegation sentence `交由下游 SceneBlocking 与 ShotPlan 权威处理` is `AUTHORITY_DELEGATION`, `META_SAFE`; the substring `blocking` is not execution.
- V3 false negatives discovered: `17` typed canonical or ambiguous cases, including motive, dim light, ticket writing, possession and provenance where present.
- V3 does not consume V2 findings.

## Authority matrix

Source owns canonical source facts. Stage A owns dramatic grouping/objective/question and audience interpretation but cannot bootstrap facts. Stage B owns performance direction/options, audience effect, information/rhythm/visual intent, metadata and delegation; canonical motive, knowledge, provenance, properties, environment, possession, blocking and shot execution require Source support or are blocked.

## Next action

`STAGE_A_SEMANTIC_REVISION_BOUNDARY_REQUIRED`. Attempt-12 is not authorized and V3 cannot yet migrate into the production gate.

## Requirement-by-requirement answers

1. Lexical phrase blacklist/whitelist dependency: **no**; phrase tokens are extraction cues only and support is typed.
2. ClaimIR schema: `director_claim_ir_v1`, fingerprinted canonical payload.
3. Claim types: `SOURCE_EVENT, CHARACTER_ACTION, CHARACTER_KNOWLEDGE, CHARACTER_INTENT, CHARACTER_EMOTION, CHARACTER_RELATIONSHIP, CHARACTER_BACKSTORY, OBJECT_EXISTENCE, OBJECT_PROPERTY, OBJECT_OWNERSHIP, OBJECT_PROVENANCE, OBJECT_POSSESSION, ENVIRONMENT_STATE, SENSORY_FACT, SPATIAL_BLOCKING, SHOT_EXECUTION, PERFORMANCE_DIRECTION, PERFORMANCE_OPTION, AUDIENCE_EFFECT, AUDIENCE_INTERPRETATION, INFORMATION_REVEAL, INFORMATION_WITHHOLD, UNCERTAINTY, CERTAINTY_ASSERTION, AUTHORITY_DELEGATION, META_COMPLIANCE, PROHIBITION, DRAMATIC_GROUPING, DRAMATIC_OBJECTIVE, DRAMATIC_QUESTION, VISUAL_PRIORITY, INFORMATION_STRATEGY, RHYTHM_INTENT, CHARACTER_STATE`.
4. Authority Matrix: `director_claim_authority_matrix_v1`; Source precedes Stage A and Stage B.
5. Source claim count: `31`.
6. Stage A claim count: `34`.
7. Attempt-9 claim count: `134`.
8. Attempt-10 claim count: `141`.
9. Attempt-11 claim count: `145`.
10. Compiled claim count: `306`.
11. Stage A V3 status: `BLOCKED`.
12. Attempt-9 V3 status: `BLOCKED`.
13. Attempt-10 diagnostic status: `DIAGNOSTIC_ONLY`.
14. Attempt-11 V3 status: `BLOCKED`.
15. Compiled V3 status: `BLOCKED`.
16. Attempt-9 known violations reproduced: **yes** — certainty collapse, unsupported key-prop action, spatial blocking.
17. Delegation: `SAFE_META_DELEGATION; reason=metadata_or_delegation_does_not_assert_story_fact`.
18. “试探林晚”: `UNSUPPORTED; reason=Dialogue and observable action do not authorize a canonical motive or hidden strategy.`.
19. “不惊动林晚”: `UNSUPPORTED; reason=Dialogue and observable action do not authorize a canonical motive or hidden strategy.`.
20. “微弱光线”: `UNSUPPORTED; reason=A flickering red safety light and later extinguishing it do not entail a remaining dim-light state.`.
21. “车票背面的手写指令”: `AMBIGUOUS_REVIEW_REQUIRED; reason=Source says the ticket back contains text, but does not state that the ticket writing is handwritten.`.
22. “接过车票”: `AMBIGUOUS_REVIEW_REQUIRED; reason=The source says an unknown person inserts a ticket; it does not state that Lin Wan takes possession of it.`.
23. “母亲留下的物件”: `UNSUPPORTED; reason=A mother-authored label does not entail that the mother left or owned the referenced object.`.
24. Stage A “第一次直面”: `UNSUPPORTED; reason=No typed SourceClaim supports this canonical assertion.`.
25. Stage A “母亲留下的暗房”: `UNSUPPORTED; reason=A mother-authored label does not entail that the mother left or owned the referenced object.`.
26. V2 false positives found: `1` delegation case fixed structurally.
27. V2 false negatives found by V3: `17`.
28. Stage A fact bootstrap: `BLOCKED`.
29. Stage A semantic revision needed: **yes**.
30. Attempt-12: **not authorized**.
31. V3 production-gate migration: **no**, shadow-only.
32. Recommended next action: `STAGE_A_SEMANTIC_REVISION_BOUNDARY_REQUIRED`.
33. Provider calls: `0`.
34. Production writes: `0`.
35. Ledger before/after: `11` → `11`.
36. Active Stage B before/after: `attempt-11` → `attempt-11`.
37. Tests: V7.7 plus V7.2-V7.6 targeted regression **190 passed, 0 failed**; broad snapshot **227 passed, 3 pre-existing V2 SceneBlocking authority failures** (see `V3_V2_REGRESSION_AUDIT.json`).
38. Compileall: `PASS`.
39. Git diff check: `PASS`.
40. Working tree: **clean** after the final commit and push.
41. Implementation commit: `db610f03a0821eac0c8fd95c92f151df69afad5a`; report metadata commit: `82058c24b0fde2f7139eb4baaf74f2fda32e3277`.
42. Remote HEAD was verified equal to local HEAD after each push; the final delivery revision is recorded in repository history.

## Provider and production invariants

- Real Provider POST: `0`; Attempt-12: `0`; IMAGE/VIDEO/SHAPI/Poyo/75API: `0`.
- SceneBlocking/ShotPlan/PromptIR calls: `0`.
- Approved DirectorTreatment/Authority/Pointer writes: `0`.
- Ledger: `11` → `11`; active Stage B: `attempt-11` → `attempt-11`.
- Proposal unchanged: `True`; model_info unchanged: `True`.

## Verification

- ClaimIR and grounding tests are provider-free.
- The full regression suite is run separately before commit.
- `python -m compileall -q core api scripts`: PASS.
- `git diff --check`: PASS.

## Evidence

All JSON evidence is in this directory. V2 source and historical Attempt-7/9/10/11 raw, IR, proposal and archive artifacts were read only and remain unchanged.
