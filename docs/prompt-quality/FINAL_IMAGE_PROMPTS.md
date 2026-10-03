# FINAL IMAGE PROMPTS

Provider-facing IMAGE prompts captured from the canonical PromptIR adapter. Real IMAGE Provider calls: `0`. Readiness: `BLOCKED` pending projection and authority fixes.

## Episode 01 · Shot 001 · SH_E01_SC001_001
- Model: `GENERIC_IMAGE`
- Mode: `TEXT_TO_IMAGE`
- References: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:TICKET", "asset_authority_ref": "book:990401:prop:TICKET", "authority_fingerprint": "19d26788c41cfa0979237951a56d9af2a7a2ef8ee0227b9275b18be7754e7751", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- PromptIR hash: `973745f392f7c2b3db50fd176e5d2257b170a1d9fbf526304125d1527e5c9569`
- Payload fingerprint: `24636485538edbab2ec601ddd66c977da6bcea0090b671f41d46eb756cd18669`

### Prompt

```text
SUBJECT: ["林晚","售票员"]
ENVIRONMENT: {"asset_identity_ref":"E01_SC001","scene_ref":"E01_SC001"}
PROPS: ["TICKET"]
ACTION: [{"action_id":"SH_E01_SC001_001_ACTION_001","actor_refs":["林晚","售票员"],"beat_refs":["SC01-B01"],"event_ref":"SC01-B01","projection_origin":"SHOT_PLAN_PROJECTION"},{"action_id":"SH_E01_SC001_001_ACTION_002","actor_refs":["林晚","售票员"],"beat_refs":["SC01-B02"],"event_ref":"SC01-B02","projection_origin":"SHOT_PLAN_PROJECTION"}]
CAMERA: {"framing_class":"WIDE","movement":"NONE","movement_end_condition":null,"movement_target":null,"movement_trigger":null,"orientation":"EYE_LEVEL","support":"STATIC"}
CONTINUITY: {"axis_policy":"PRESERVE","axis_ref":null,"axis_refs":[],"look_direction":{},"screen_side_assignments":{}}
TEMPORAL: {"continuous_take":true,"cut_events":[],"cut_trigger":"AUTHORED_INFORMATION_LANDS","duration_hint_seconds":4,"duration_mode":"ACTION_COMPLETION"}
VISIBILITY: "AUDIENCE_ONLY"
CONSTRAINTS: {"must_include_prop_refs":["TICKET"],"must_include_subject_refs":["林晚","售票员"],"must_preserve_axis":false}
```

### Negative Prompt

`NOT_SUPPORTED_BY_ADAPTER`

## Episode 01 · Shot 002 · SH_E01_SC001_002
- Model: `GENERIC_IMAGE`
- Mode: `TEXT_TO_IMAGE`
- References: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:RED_UMBRELLA", "asset_authority_ref": "book:990401:prop:RED_UMBRELLA", "authority_fingerprint": "9acdad16c814b59509b3a642246f2019f5b4dbe2b18b3bfb7451e6d2d6af9168", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- PromptIR hash: `382ed484d2fe67b6de68261d55ea382986bc11ea7ddaf3d18f3354d42cee96a4`
- Payload fingerprint: `15fddcb37a947e42a9baf2d32c904423883fb4faf59e10c905d5db60b5063bf2`

### Prompt

```text
SUBJECT: ["林晚"]
ENVIRONMENT: {"asset_identity_ref":"E01_SC001","scene_ref":"E01_SC001"}
PROPS: ["RED_UMBRELLA"]
ACTION: [{"action_id":"SH_E01_SC001_002_ACTION_001","actor_refs":["林晚"],"beat_refs":["SC01-B03"],"event_ref":"SC01-B03","projection_origin":"SHOT_PLAN_PROJECTION"}]
CAMERA: {"framing_class":"WIDE","movement":"REFRAME","movement_end_condition":"BEAT_INFORMATION_LANDS","movement_target":"林晚","movement_trigger":"AUTHORED_BEAT_TRANSITION","orientation":"EYE_LEVEL","support":"DOLLY"}
CONTINUITY: {"axis_policy":"PRESERVE","axis_ref":null,"axis_refs":[],"look_direction":{},"screen_side_assignments":{}}
TEMPORAL: {"continuous_take":true,"cut_events":[],"cut_trigger":"AUTHORED_INFORMATION_LANDS","duration_hint_seconds":4,"duration_mode":"REACTION_HOLD"}
VISIBILITY: "CHARACTER_AND_AUDIENCE"
CONSTRAINTS: {"must_include_prop_refs":["RED_UMBRELLA"],"must_include_subject_refs":["林晚"],"must_preserve_axis":false}
```

### Negative Prompt

`NOT_SUPPORTED_BY_ADAPTER`

## Episode 01 · Shot 003 · SH_E01_SC001_003
- Model: `GENERIC_IMAGE`
- Mode: `TEXT_TO_IMAGE`
- References: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:BROKEN_UMBRELLA_RIB", "asset_authority_ref": "book:990401:prop:BROKEN_UMBRELLA_RIB", "authority_fingerprint": "ed60d561d9a90d0fca22feb23a8653581a561f900ee5b8d417c731892b2ca5b1", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- PromptIR hash: `b986e9fd7a4c7624143cd24cd866ad024b5bdd06f502122dbc327d9e56add972`
- Payload fingerprint: `452e4e4906c935df1a28de34b00e96fc9cea0eaaa3d09d52e001cfc03579bf92`

### Prompt

```text
SUBJECT: ["林晚","顾沉"]
ENVIRONMENT: {"asset_identity_ref":"E01_SC001","scene_ref":"E01_SC001"}
PROPS: ["BROKEN_UMBRELLA_RIB"]
ACTION: [{"action_id":"SH_E01_SC001_003_ACTION_001","actor_refs":["林晚","顾沉"],"beat_refs":["SC01-B04"],"event_ref":"SC01-B04","projection_origin":"SHOT_PLAN_PROJECTION"}]
CAMERA: {"framing_class":"INSERT","movement":"NONE","movement_end_condition":null,"movement_target":null,"movement_trigger":null,"orientation":"EYE_LEVEL","support":"STATIC"}
CONTINUITY: {"axis_policy":"PRESERVE","axis_ref":null,"axis_refs":[],"look_direction":{},"screen_side_assignments":{}}
TEMPORAL: {"continuous_take":true,"cut_events":[],"cut_trigger":"AUTHORED_INFORMATION_LANDS","duration_hint_seconds":4,"duration_mode":"REACTION_HOLD"}
VISIBILITY: "CHARACTER_AND_AUDIENCE"
CONSTRAINTS: {"must_include_prop_refs":["BROKEN_UMBRELLA_RIB"],"must_include_subject_refs":["林晚","顾沉"],"must_preserve_axis":false}
```

### Negative Prompt

`NOT_SUPPORTED_BY_ADAPTER`

## Episode 01 · Shot 004 · SH_E01_SC001_004
- Model: `GENERIC_IMAGE`
- Mode: `TEXT_TO_IMAGE`
- References: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- PromptIR hash: `f756c136a6cdb1413b2d1df24f058b6a8597060f5d7d8eefc694f3cdd665ab6f`
- Payload fingerprint: `0b65bd8b3f8eb2facc1a5c5b9f9352867f790935154c9990a5d09fdf9046483c`

### Prompt

```text
SUBJECT: ["顾沉","林晚"]
ENVIRONMENT: {"asset_identity_ref":"E01_SC001","scene_ref":"E01_SC001"}
ACTION: [{"action_id":"SH_E01_SC001_004_ACTION_001","actor_refs":["顾沉","林晚"],"beat_refs":["SC01-B05"],"event_ref":"SC01-B05","projection_origin":"SHOT_PLAN_PROJECTION"},{"action_id":"SH_E01_SC001_004_ACTION_002","actor_refs":["顾沉","林晚"],"beat_refs":["SC01-B06"],"event_ref":"SC01-B06","projection_origin":"SHOT_PLAN_PROJECTION"}]
CAMERA: {"framing_class":"TWO_SHOT","movement":"NONE","movement_end_condition":null,"movement_target":null,"movement_trigger":null,"orientation":"EYE_LEVEL","support":"STATIC"}
CONTINUITY: {"axis_policy":"PRESERVE","axis_ref":"AXIS_LW_GC","axis_refs":["AXIS_LW_GC"],"look_direction":{"林晚":"SCREEN_RIGHT","顾沉":"SCREEN_LEFT"},"screen_side_assignments":{"林晚":"LEFT","顾沉":"RIGHT"}}
TEMPORAL: {"continuous_take":true,"cut_events":[],"cut_trigger":"AUTHORED_INFORMATION_LANDS","duration_hint_seconds":4,"duration_mode":"REACTION_HOLD"}
VISIBILITY: "CHARACTER_AND_AUDIENCE"
CONSTRAINTS: {"must_include_prop_refs":[],"must_include_subject_refs":["顾沉","林晚"],"must_preserve_axis":true}
```

### Negative Prompt

`NOT_SUPPORTED_BY_ADAPTER`

## Episode 01 · Shot 005 · SH_E01_SC001_005
- Model: `GENERIC_IMAGE`
- Mode: `TEXT_TO_IMAGE`
- References: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:HANDBAG", "asset_authority_ref": "book:990401:prop:HANDBAG", "authority_fingerprint": "71a415f0129a56d418f16c89af3c4cbda4de63607c7bef0634aa2b6582a31538", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- PromptIR hash: `7df3b1d19358742f4cebd7036aff3666d927a201f80d9381cae3838aeb9ac01b`
- Payload fingerprint: `42e182c0e867810c06832de277cfc2a2992f448efb57c6fc560e8e11d176c650`

### Prompt

```text
SUBJECT: ["陆叔","林晚"]
ENVIRONMENT: {"asset_identity_ref":"E01_SC001","scene_ref":"E01_SC001"}
PROPS: ["HANDBAG"]
ACTION: [{"action_id":"SH_E01_SC001_005_ACTION_001","actor_refs":["陆叔","林晚"],"beat_refs":["SC01-B07"],"event_ref":"SC01-B07","projection_origin":"SHOT_PLAN_PROJECTION"},{"action_id":"SH_E01_SC001_005_ACTION_002","actor_refs":["陆叔","林晚"],"beat_refs":["SC01-B08"],"event_ref":"SC01-B08","projection_origin":"SHOT_PLAN_PROJECTION"}]
CAMERA: {"framing_class":"MEDIUM_WIDE","movement":"TRACK","movement_end_condition":"BEAT_INFORMATION_LANDS","movement_target":"陆叔","movement_trigger":"AUTHORED_BEAT_TRANSITION","orientation":"EYE_LEVEL","support":"DOLLY"}
CONTINUITY: {"axis_policy":"PRESERVE","axis_ref":"AXIS_LW_GC","axis_refs":["AXIS_LW_GC","AXIS_LW_LS"],"look_direction":{"林晚":"SCREEN_RIGHT","顾沉":"SCREEN_LEFT"},"screen_side_assignments":{"林晚":"LEFT","顾沉":"RIGHT"}}
TEMPORAL: {"continuous_take":true,"cut_events":[],"cut_trigger":"AUTHORED_INFORMATION_LANDS","duration_hint_seconds":4,"duration_mode":"REACTION_HOLD"}
VISIBILITY: "CHARACTER_AND_AUDIENCE"
CONSTRAINTS: {"must_include_prop_refs":["HANDBAG"],"must_include_subject_refs":["陆叔","林晚"],"must_preserve_axis":true}
```

### Negative Prompt

`NOT_SUPPORTED_BY_ADAPTER`

## Episode 01 · Shot 006 · SH_E01_SC001_006
- Model: `GENERIC_IMAGE`
- Mode: `TEXT_TO_IMAGE`
- References: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:BROKEN_UMBRELLA_RIB", "asset_authority_ref": "book:990401:prop:BROKEN_UMBRELLA_RIB", "authority_fingerprint": "ed60d561d9a90d0fca22feb23a8653581a561f900ee5b8d417c731892b2ca5b1", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:RED_UMBRELLA", "asset_authority_ref": "book:990401:prop:RED_UMBRELLA", "authority_fingerprint": "9acdad16c814b59509b3a642246f2019f5b4dbe2b18b3bfb7451e6d2d6af9168", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- PromptIR hash: `e33b3620f792fc58e0cb178ae8ce7d2df65e2fda53641609eab497d3a917428d`
- Payload fingerprint: `f426d04c0e0398263a8ef9d8e62ea387ce545cd66c84943c335cd55d4eefdbbe`

### Prompt

```text
SUBJECT: ["林晚"]
ENVIRONMENT: {"asset_identity_ref":"E01_SC001","scene_ref":"E01_SC001"}
PROPS: ["BROKEN_UMBRELLA_RIB","RED_UMBRELLA"]
ACTION: [{"action_id":"SH_E01_SC001_006_ACTION_001","actor_refs":["林晚"],"beat_refs":["SC01-B09"],"event_ref":"SC01-B09","projection_origin":"SHOT_PLAN_PROJECTION"},{"action_id":"SH_E01_SC001_006_ACTION_002","actor_refs":["林晚"],"beat_refs":["SC01-B10"],"event_ref":"SC01-B10","projection_origin":"SHOT_PLAN_PROJECTION"}]
CAMERA: {"framing_class":"INSERT","movement":"NONE","movement_end_condition":null,"movement_target":null,"movement_trigger":null,"orientation":"EYE_LEVEL","support":"STATIC"}
CONTINUITY: {"axis_policy":"PRESERVE","axis_ref":"AXIS_LW_GC","axis_refs":["AXIS_LW_GC","AXIS_LW_LS"],"look_direction":{"林晚":"SCREEN_RIGHT","顾沉":"SCREEN_LEFT"},"screen_side_assignments":{"林晚":"LEFT","顾沉":"RIGHT"}}
TEMPORAL: {"continuous_take":true,"cut_events":[],"cut_trigger":"AUTHORED_INFORMATION_LANDS","duration_hint_seconds":4,"duration_mode":"REACTION_HOLD"}
VISIBILITY: "AUDIENCE_ONLY"
CONSTRAINTS: {"must_include_prop_refs":["BROKEN_UMBRELLA_RIB","RED_UMBRELLA"],"must_include_subject_refs":["林晚"],"must_preserve_axis":true}
```

### Negative Prompt

`NOT_SUPPORTED_BY_ADAPTER`

## Episode 01 · Shot 007 · SH_E01_SC001_007
- Model: `GENERIC_IMAGE`
- Mode: `TEXT_TO_IMAGE`
- References: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- PromptIR hash: `0f20a34863be5bf68f71fccee6628141488fdf9d22114613d2ee89faa48fd33b`
- Payload fingerprint: `68ae1e732a587965055e9023b00f338349efe9c0c03a55acc31c90519da4ee1d`

### Prompt

```text
SUBJECT: ["林晚","陆叔"]
ENVIRONMENT: {"asset_identity_ref":"E01_SC001","scene_ref":"E01_SC001"}
ACTION: [{"action_id":"SH_E01_SC001_007_ACTION_001","actor_refs":["林晚","陆叔"],"beat_refs":["SC01-B11"],"event_ref":"SC01-B11","projection_origin":"SHOT_PLAN_PROJECTION"},{"action_id":"SH_E01_SC001_007_ACTION_002","actor_refs":["林晚","陆叔"],"beat_refs":["SC01-B12"],"event_ref":"SC01-B12","projection_origin":"SHOT_PLAN_PROJECTION"}]
CAMERA: {"framing_class":"MEDIUM","movement":"PAN","movement_end_condition":"BEAT_INFORMATION_LANDS","movement_target":"林晚","movement_trigger":"AUTHORED_BEAT_TRANSITION","orientation":"EYE_LEVEL","support":"DOLLY"}
CONTINUITY: {"axis_policy":"PRESERVE","axis_ref":"AXIS_LW_GC","axis_refs":["AXIS_LW_GC","AXIS_LW_LS"],"look_direction":{"林晚":"SCREEN_RIGHT","顾沉":"SCREEN_LEFT"},"screen_side_assignments":{"林晚":"LEFT","顾沉":"RIGHT"}}
TEMPORAL: {"continuous_take":true,"cut_events":[],"cut_trigger":"AUTHORED_INFORMATION_LANDS","duration_hint_seconds":4,"duration_mode":"REACTION_HOLD"}
VISIBILITY: "CHARACTER_AND_AUDIENCE"
CONSTRAINTS: {"must_include_prop_refs":[],"must_include_subject_refs":["林晚","陆叔"],"must_preserve_axis":true}
```

### Negative Prompt

`NOT_SUPPORTED_BY_ADAPTER`

## Episode 01 · Shot 008 · SH_E01_SC001_008
- Model: `GENERIC_IMAGE`
- Mode: `TEXT_TO_IMAGE`
- References: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- PromptIR hash: `05c2e0ed28cde4e0e991ccf6fb078b5da167cf91b4eedae866211c632b2e8331`
- Payload fingerprint: `3d953583d70dbb9a756c9b25d62a8ab5c8deaa0fa024408633a86688a2fa700a`

### Prompt

```text
SUBJECT: ["顾沉","林晚"]
ENVIRONMENT: {"asset_identity_ref":"E01_SC001","scene_ref":"E01_SC001"}
ACTION: [{"action_id":"SH_E01_SC001_008_ACTION_001","actor_refs":["顾沉","林晚"],"beat_refs":["SC01-B13"],"event_ref":"SC01-B13","projection_origin":"SHOT_PLAN_PROJECTION"}]
CAMERA: {"framing_class":"MEDIUM_CLOSE","movement":"DOLLY_IN","movement_end_condition":"BEAT_INFORMATION_LANDS","movement_target":"顾沉","movement_trigger":"AUTHORED_BEAT_TRANSITION","orientation":"EYE_LEVEL","support":"DOLLY"}
CONTINUITY: {"axis_policy":"PRESERVE","axis_ref":"AXIS_LW_GC","axis_refs":["AXIS_LW_GC","AXIS_LW_LS"],"look_direction":{"林晚":"SCREEN_RIGHT","顾沉":"SCREEN_LEFT"},"screen_side_assignments":{"林晚":"LEFT","顾沉":"RIGHT"}}
TEMPORAL: {"continuous_take":true,"cut_events":[],"cut_trigger":"AUTHORED_INFORMATION_LANDS","duration_hint_seconds":4,"duration_mode":"REACTION_HOLD"}
VISIBILITY: "AUDIENCE_ONLY"
CONSTRAINTS: {"must_include_prop_refs":[],"must_include_subject_refs":["顾沉","林晚"],"must_preserve_axis":true}
```

### Negative Prompt

`NOT_SUPPORTED_BY_ADAPTER`

## Episode 01 · Shot 009 · SH_E01_SC002_001
- Model: `GENERIC_IMAGE`
- Mode: `TEXT_TO_IMAGE`
- References: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC002", "asset_authority_ref": "book:990401:scene:E01_SC002", "authority_fingerprint": "74f6bbdb9ac6c545d20e8e5610d1ad71aff7e270a5ed2df7a103093cc4ef8ef9", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:APPLE", "asset_authority_ref": "book:990401:prop:APPLE", "authority_fingerprint": "10ff684a8071dd7f7d27c276068aabfb962d97e5ab3387ca895dbbff1f06e812", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:DOOR_LOCK", "asset_authority_ref": "book:990401:prop:DOOR_LOCK", "authority_fingerprint": "bf33b28c4f7995de223faecc547c35a86772d615f7d1f296d782c5bb3a360149", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- PromptIR hash: `b803e727af9025cf78042385a8e113cb9d819eafc118685d9bed70fe0323b765`
- Payload fingerprint: `c6b059aac675a0eb1aca228a7f949b940152832d7aa5287d104abefa34fbbe4e`

### Prompt

```text
SUBJECT: ["陆叔","林晚"]
ENVIRONMENT: {"asset_identity_ref":"E01_SC002","scene_ref":"E01_SC002"}
PROPS: ["APPLE","DOOR_LOCK"]
ACTION: [{"action_id":"SH_E01_SC002_001_ACTION_001","actor_refs":["陆叔","林晚"],"beat_refs":["SC02-B01"],"event_ref":"SC02-B01","projection_origin":"SHOT_PLAN_PROJECTION"},{"action_id":"SH_E01_SC002_001_ACTION_002","actor_refs":["陆叔","林晚"],"beat_refs":["SC02-B02"],"event_ref":"SC02-B02","projection_origin":"SHOT_PLAN_PROJECTION"}]
CAMERA: {"framing_class":"WIDE","movement":"NONE","movement_end_condition":null,"movement_target":null,"movement_trigger":null,"orientation":"EYE_LEVEL","support":"STATIC"}
CONTINUITY: {"axis_policy":"PRESERVE","axis_ref":"AXIS_LW_LS_APT","axis_refs":["AXIS_LW_LS_APT"],"look_direction":{"林晚":"SCREEN_RIGHT","陆叔":"SCREEN_LEFT"},"screen_side_assignments":{"林晚":"LEFT","陆叔":"RIGHT"}}
TEMPORAL: {"continuous_take":true,"cut_events":[],"cut_trigger":"AUTHORED_INFORMATION_LANDS","duration_hint_seconds":4,"duration_mode":"REACTION_HOLD"}
VISIBILITY: "AUDIENCE_ONLY"
CONSTRAINTS: {"must_include_prop_refs":["APPLE","DOOR_LOCK"],"must_include_subject_refs":["陆叔","林晚"],"must_preserve_axis":true}
```

### Negative Prompt

`NOT_SUPPORTED_BY_ADAPTER`

## Episode 01 · Shot 010 · SH_E01_SC002_002
- Model: `GENERIC_IMAGE`
- Mode: `TEXT_TO_IMAGE`
- References: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC002", "asset_authority_ref": "book:990401:scene:E01_SC002", "authority_fingerprint": "74f6bbdb9ac6c545d20e8e5610d1ad71aff7e270a5ed2df7a103093cc4ef8ef9", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- PromptIR hash: `0eac64d7ab2297bc43f016989e30db1d5ef7da4607ebdd24abd13dbed9705e0a`
- Payload fingerprint: `140b9c70c079919017cda508f5992bc791957075c5741eeaa4c5f178aa5e0053`

### Prompt

```text
SUBJECT: ["陆叔","林晚"]
ENVIRONMENT: {"asset_identity_ref":"E01_SC002","scene_ref":"E01_SC002"}
ACTION: [{"action_id":"SH_E01_SC002_002_ACTION_001","actor_refs":["陆叔","林晚"],"beat_refs":["SC02-B03"],"event_ref":"SC02-B03","projection_origin":"SHOT_PLAN_PROJECTION"}]
CAMERA: {"framing_class":"OVER_SHOULDER","movement":"NONE","movement_end_condition":null,"movement_target":null,"movement_trigger":null,"orientation":"EYE_LEVEL","support":"STATIC"}
CONTINUITY: {"axis_policy":"PRESERVE","axis_ref":"AXIS_LW_LS_APT","axis_refs":["AXIS_LW_LS_APT"],"look_direction":{"林晚":"SCREEN_RIGHT","陆叔":"SCREEN_LEFT"},"screen_side_assignments":{"林晚":"LEFT","陆叔":"RIGHT"}}
TEMPORAL: {"continuous_take":true,"cut_events":[],"cut_trigger":"AUTHORED_INFORMATION_LANDS","duration_hint_seconds":4,"duration_mode":"REACTION_HOLD"}
VISIBILITY: "CHARACTER_AND_AUDIENCE"
CONSTRAINTS: {"must_include_prop_refs":[],"must_include_subject_refs":["陆叔","林晚"],"must_preserve_axis":true}
```

### Negative Prompt

`NOT_SUPPORTED_BY_ADAPTER`

## Episode 01 · Shot 011 · SH_E01_SC002_003
- Model: `GENERIC_IMAGE`
- Mode: `TEXT_TO_IMAGE`
- References: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC002", "asset_authority_ref": "book:990401:scene:E01_SC002", "authority_fingerprint": "74f6bbdb9ac6c545d20e8e5610d1ad71aff7e270a5ed2df7a103093cc4ef8ef9", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:HANDBAG", "asset_authority_ref": "book:990401:prop:HANDBAG", "authority_fingerprint": "71a415f0129a56d418f16c89af3c4cbda4de63607c7bef0634aa2b6582a31538", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- PromptIR hash: `a2423e362824f44ce6f523a76f1ae5b77f9791f0cf252b19b52e958f19b52d94`
- Payload fingerprint: `562f06440d9a4d4001d5db86f39250f3a2b0a7b19428f2370b22586433b11f77`

### Prompt

```text
SUBJECT: ["林晚"]
ENVIRONMENT: {"asset_identity_ref":"E01_SC002","scene_ref":"E01_SC002"}
PROPS: ["HANDBAG"]
ACTION: [{"action_id":"SH_E01_SC002_003_ACTION_001","actor_refs":["林晚"],"beat_refs":["SC02-B04"],"event_ref":"SC02-B04","projection_origin":"SHOT_PLAN_PROJECTION"}]
CAMERA: {"framing_class":"MEDIUM_CLOSE","movement":"NONE","movement_end_condition":null,"movement_target":null,"movement_trigger":null,"orientation":"EYE_LEVEL","support":"STATIC"}
CONTINUITY: {"axis_policy":"PRESERVE","axis_ref":"AXIS_LW_LS_APT","axis_refs":["AXIS_LW_LS_APT"],"look_direction":{"林晚":"SCREEN_RIGHT","陆叔":"SCREEN_LEFT"},"screen_side_assignments":{"林晚":"LEFT","陆叔":"RIGHT"}}
TEMPORAL: {"continuous_take":true,"cut_events":[],"cut_trigger":"AUTHORED_INFORMATION_LANDS","duration_hint_seconds":4,"duration_mode":"REACTION_HOLD"}
VISIBILITY: "AUDIENCE_OBSERVES_CHARACTER_DOUBT"
CONSTRAINTS: {"must_include_prop_refs":["HANDBAG"],"must_include_subject_refs":["林晚"],"must_preserve_axis":true}
```

### Negative Prompt

`NOT_SUPPORTED_BY_ADAPTER`

## Episode 01 · Shot 012 · SH_E01_SC002_004
- Model: `GENERIC_IMAGE`
- Mode: `TEXT_TO_IMAGE`
- References: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC002", "asset_authority_ref": "book:990401:scene:E01_SC002", "authority_fingerprint": "74f6bbdb9ac6c545d20e8e5610d1ad71aff7e270a5ed2df7a103093cc4ef8ef9", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:POCKET_HARD_OBJECT", "asset_authority_ref": "book:990401:prop:POCKET_HARD_OBJECT", "authority_fingerprint": "52f8ff73ee9dbd1890475391ab1ae3390d82f2d70b9ee5a4c37927b1186381fc", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:TABLE_SCRATCH", "asset_authority_ref": "book:990401:prop:TABLE_SCRATCH", "authority_fingerprint": "625c30701544f1359411fcb8e03c1cfcf921b20a5adbc8b688cee8fba802b763", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- PromptIR hash: `57095290c539075aed441249c6158158dda5f528c19a07be38faf4a2b59d5c73`
- Payload fingerprint: `b1e57241b1b63eafe06172135071702196f5ace804e688c1e335018873c8ecb2`

### Prompt

```text
SUBJECT: ["陆叔","林晚"]
ENVIRONMENT: {"asset_identity_ref":"E01_SC002","scene_ref":"E01_SC002"}
PROPS: ["POCKET_HARD_OBJECT","TABLE_SCRATCH"]
ACTION: [{"action_id":"SH_E01_SC002_004_ACTION_001","actor_refs":["陆叔","林晚"],"beat_refs":["SC02-B05"],"event_ref":"SC02-B05","projection_origin":"SHOT_PLAN_PROJECTION"}]
CAMERA: {"framing_class":"MEDIUM_CLOSE","movement":"REFRAME","movement_end_condition":"BEAT_INFORMATION_LANDS","movement_target":"陆叔","movement_trigger":"AUTHORED_BEAT_TRANSITION","orientation":"EYE_LEVEL","support":"DOLLY"}
CONTINUITY: {"axis_policy":"PRESERVE","axis_ref":"AXIS_LW_LS_APT","axis_refs":["AXIS_LW_LS_APT"],"look_direction":{"林晚":"SCREEN_RIGHT","陆叔":"SCREEN_LEFT"},"screen_side_assignments":{"林晚":"LEFT","陆叔":"RIGHT"}}
TEMPORAL: {"continuous_take":true,"cut_events":[],"cut_trigger":"AUTHORED_INFORMATION_LANDS","duration_hint_seconds":4,"duration_mode":"REACTION_HOLD"}
VISIBILITY: "CHARACTER_AND_AUDIENCE"
CONSTRAINTS: {"must_include_prop_refs":["POCKET_HARD_OBJECT","TABLE_SCRATCH"],"must_include_subject_refs":["陆叔","林晚"],"must_preserve_axis":true}
```

### Negative Prompt

`NOT_SUPPORTED_BY_ADAPTER`

## Episode 01 · Shot 013 · SH_E01_SC002_005
- Model: `GENERIC_IMAGE`
- Mode: `TEXT_TO_IMAGE`
- References: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC002", "asset_authority_ref": "book:990401:scene:E01_SC002", "authority_fingerprint": "74f6bbdb9ac6c545d20e8e5610d1ad71aff7e270a5ed2df7a103093cc4ef8ef9", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:RED_FIBER", "asset_authority_ref": "book:990401:prop:RED_FIBER", "authority_fingerprint": "a24881e736ace0d037eeecaaa26431450dd33097eb4ff6293999d2c7abb98660", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- PromptIR hash: `debb6d9ecb135bb300315825d256ed1cfa5afac204bc9bee430c1278ceaf8799`
- Payload fingerprint: `464e2dda54061b8e137e21043521a894315524c02e7a148b4953e0b4a1c6565a`

### Prompt

```text
SUBJECT: ["林晚"]
ENVIRONMENT: {"asset_identity_ref":"E01_SC002","scene_ref":"E01_SC002"}
PROPS: ["RED_FIBER"]
ACTION: [{"action_id":"SH_E01_SC002_005_ACTION_001","actor_refs":["林晚"],"beat_refs":["SC02-B06"],"event_ref":"SC02-B06","projection_origin":"SHOT_PLAN_PROJECTION"}]
CAMERA: {"framing_class":"INSERT","movement":"NONE","movement_end_condition":null,"movement_target":null,"movement_trigger":null,"orientation":"EYE_LEVEL","support":"STATIC"}
CONTINUITY: {"axis_policy":"PRESERVE","axis_ref":"AXIS_LW_LS_APT","axis_refs":["AXIS_LW_LS_APT"],"look_direction":{"林晚":"SCREEN_RIGHT","陆叔":"SCREEN_LEFT"},"screen_side_assignments":{"林晚":"LEFT","陆叔":"RIGHT"}}
TEMPORAL: {"continuous_take":true,"cut_events":[],"cut_trigger":"AUTHORED_INFORMATION_LANDS","duration_hint_seconds":4,"duration_mode":"REACTION_HOLD"}
VISIBILITY: "AUDIENCE_ONLY"
CONSTRAINTS: {"must_include_prop_refs":["RED_FIBER"],"must_include_subject_refs":["林晚"],"must_preserve_axis":true}
```

### Negative Prompt

`NOT_SUPPORTED_BY_ADAPTER`

## Episode 01 · Shot 014 · SH_E01_SC002_006
- Model: `GENERIC_IMAGE`
- Mode: `TEXT_TO_IMAGE`
- References: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC002", "asset_authority_ref": "book:990401:scene:E01_SC002", "authority_fingerprint": "74f6bbdb9ac6c545d20e8e5610d1ad71aff7e270a5ed2df7a103093cc4ef8ef9", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- PromptIR hash: `91acdd7bc981779baa73bb13b70861325b8ac241f2149a89d8508e9fc5b1ab62`
- Payload fingerprint: `ab0074ec1e8c89e3ccf8c41b79313f109b6800472fdb7af241b52b061710feff`

### Prompt

```text
SUBJECT: ["陆叔","林晚"]
ENVIRONMENT: {"asset_identity_ref":"E01_SC002","scene_ref":"E01_SC002"}
ACTION: [{"action_id":"SH_E01_SC002_006_ACTION_001","actor_refs":["陆叔","林晚"],"beat_refs":["SC02-B07"],"event_ref":"SC02-B07","projection_origin":"SHOT_PLAN_PROJECTION"}]
CAMERA: {"framing_class":"CLOSE","movement":"DOLLY_IN","movement_end_condition":"BEAT_INFORMATION_LANDS","movement_target":"陆叔","movement_trigger":"AUTHORED_BEAT_TRANSITION","orientation":"EYE_LEVEL","support":"DOLLY"}
CONTINUITY: {"axis_policy":"PRESERVE","axis_ref":"AXIS_LW_LS_APT","axis_refs":["AXIS_LW_LS_APT"],"look_direction":{"林晚":"SCREEN_RIGHT","陆叔":"SCREEN_LEFT"},"screen_side_assignments":{"林晚":"LEFT","陆叔":"RIGHT"}}
TEMPORAL: {"continuous_take":true,"cut_events":[],"cut_trigger":"AUTHORED_INFORMATION_LANDS","duration_hint_seconds":4,"duration_mode":"REACTION_HOLD"}
VISIBILITY: "CHARACTER_AND_AUDIENCE"
CONSTRAINTS: {"must_include_prop_refs":[],"must_include_subject_refs":["陆叔","林晚"],"must_preserve_axis":true}
```

### Negative Prompt

`NOT_SUPPORTED_BY_ADAPTER`

## Episode 01 · Shot 015 · SH_E01_SC002_007
- Model: `GENERIC_IMAGE`
- Mode: `TEXT_TO_IMAGE`
- References: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC002", "asset_authority_ref": "book:990401:scene:E01_SC002", "authority_fingerprint": "74f6bbdb9ac6c545d20e8e5610d1ad71aff7e270a5ed2df7a103093cc4ef8ef9", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- PromptIR hash: `88a3057b270426aac5f8ed717e9650a3797534dc12564667b561b5ebe98fec7c`
- Payload fingerprint: `89b86b864fb3b366d4afb1d2748c7d490f80baa128df5c51da2a42574c816d6a`

### Prompt

```text
SUBJECT: ["林晚","陆叔"]
ENVIRONMENT: {"asset_identity_ref":"E01_SC002","scene_ref":"E01_SC002"}
ACTION: [{"action_id":"SH_E01_SC002_007_ACTION_001","actor_refs":["林晚","陆叔"],"beat_refs":["SC02-B08"],"event_ref":"SC02-B08","projection_origin":"SHOT_PLAN_PROJECTION"},{"action_id":"SH_E01_SC002_007_ACTION_002","actor_refs":["林晚","陆叔"],"beat_refs":["SC02-B09"],"event_ref":"SC02-B09","projection_origin":"SHOT_PLAN_PROJECTION"}]
CAMERA: {"framing_class":"TWO_SHOT","movement":"ARC","movement_end_condition":"BEAT_INFORMATION_LANDS","movement_target":"林晚","movement_trigger":"AUTHORED_BEAT_TRANSITION","orientation":"EYE_LEVEL","support":"DOLLY"}
CONTINUITY: {"axis_policy":"PRESERVE","axis_ref":"AXIS_LW_LS_APT","axis_refs":["AXIS_LW_LS_APT"],"look_direction":{"林晚":"SCREEN_RIGHT","陆叔":"SCREEN_LEFT"},"screen_side_assignments":{"林晚":"LEFT","陆叔":"RIGHT"}}
TEMPORAL: {"continuous_take":true,"cut_events":[],"cut_trigger":"AUTHORED_INFORMATION_LANDS","duration_hint_seconds":4,"duration_mode":"REACTION_HOLD"}
VISIBILITY: "AUDIENCE_ONLY"
CONSTRAINTS: {"must_include_prop_refs":[],"must_include_subject_refs":["林晚","陆叔"],"must_preserve_axis":true}
```

### Negative Prompt

`NOT_SUPPORTED_BY_ADAPTER`

## Shot 016

`NOT_APPLICABLE` — no current IMAGE PromptIR authority.
