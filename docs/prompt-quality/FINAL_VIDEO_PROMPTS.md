# FINAL VIDEO PROMPTS

Provider-facing VIDEO prompts captured from the canonical PromptIR adapter. Real VIDEO Provider calls: `0`. Model contract: `75api-minimax-h3` / `minimax_h3_no_audios`, IMAGE_TO_VIDEO, 5 sec, 768p, 16:9. Readiness: `BLOCKED`.

## Episode 01 · Shot 001 · SH_E01_SC001_001
- Model: `75api-minimax-h3 / minimax_h3_no_audios`
- Mode: `IMAGE_TO_VIDEO`
- Source mode: `IMAGE_TO_VIDEO`
- First frame: `{"mode": "CURRENT_OFFICIAL_IMAGE", "authority_required": true}`
- Source/reference bindings: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:TICKET", "asset_authority_ref": "book:990401:prop:TICKET", "authority_fingerprint": "19d26788c41cfa0979237951a56d9af2a7a2ef8ee0227b9275b18be7754e7751", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- Duration: `5 sec`; aspect ratio: `16:9`; resolution: `768p`
- PromptIR hash: `8f3e2978a58a4009a12ddfb55536946b439cb27b83ad3eae0881d8051898b701`
- Payload fingerprint: `05045db107f5f79b6a1a4421977fa47af882c793937eb2d22f75238ce0fb0877`

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
- Model: `75api-minimax-h3 / minimax_h3_no_audios`
- Mode: `IMAGE_TO_VIDEO`
- Source mode: `IMAGE_TO_VIDEO`
- First frame: `{"mode": "CURRENT_OFFICIAL_IMAGE", "authority_required": true}`
- Source/reference bindings: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:RED_UMBRELLA", "asset_authority_ref": "book:990401:prop:RED_UMBRELLA", "authority_fingerprint": "9acdad16c814b59509b3a642246f2019f5b4dbe2b18b3bfb7451e6d2d6af9168", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- Duration: `5 sec`; aspect ratio: `16:9`; resolution: `768p`
- PromptIR hash: `1547f94b3ed9fe0573a15e336ddb5dc8ae1438f1da84a20e1d9fdbaa59a10524`
- Payload fingerprint: `e70311b9440ca0d6dd5d9a74231d81fd7793498597ebd3750cbc4869b43078b9`

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
- Model: `75api-minimax-h3 / minimax_h3_no_audios`
- Mode: `IMAGE_TO_VIDEO`
- Source mode: `IMAGE_TO_VIDEO`
- First frame: `{"mode": "CURRENT_OFFICIAL_IMAGE", "authority_required": true}`
- Source/reference bindings: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:BROKEN_UMBRELLA_RIB", "asset_authority_ref": "book:990401:prop:BROKEN_UMBRELLA_RIB", "authority_fingerprint": "ed60d561d9a90d0fca22feb23a8653581a561f900ee5b8d417c731892b2ca5b1", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- Duration: `5 sec`; aspect ratio: `16:9`; resolution: `768p`
- PromptIR hash: `ce94955d13784d49010b71afc7de5f606bcd8fd09de4e8158a6703928e54f6da`
- Payload fingerprint: `88bd010bb0799dc56590ca54d0485853bec26e5d9ba431be27d456b7616f48b4`

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
- Model: `75api-minimax-h3 / minimax_h3_no_audios`
- Mode: `IMAGE_TO_VIDEO`
- Source mode: `IMAGE_TO_VIDEO`
- First frame: `{"mode": "CURRENT_OFFICIAL_IMAGE", "authority_required": true}`
- Source/reference bindings: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- Duration: `5 sec`; aspect ratio: `16:9`; resolution: `768p`
- PromptIR hash: `408d86ec8be41e271e07b6521546008622de2205d291843a2dbc4840496ee05a`
- Payload fingerprint: `a6f1d721742be242b04c3eaf818642dcb54885065e9483db58929f70b31c5d40`

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
- Model: `75api-minimax-h3 / minimax_h3_no_audios`
- Mode: `IMAGE_TO_VIDEO`
- Source mode: `IMAGE_TO_VIDEO`
- First frame: `{"mode": "CURRENT_OFFICIAL_IMAGE", "authority_required": true}`
- Source/reference bindings: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:HANDBAG", "asset_authority_ref": "book:990401:prop:HANDBAG", "authority_fingerprint": "71a415f0129a56d418f16c89af3c4cbda4de63607c7bef0634aa2b6582a31538", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- Duration: `5 sec`; aspect ratio: `16:9`; resolution: `768p`
- PromptIR hash: `9e9023c9e114d2e2db70d8c8f7efca7791fe846757e8182ff4d8579916d16a94`
- Payload fingerprint: `b67c844dfeaa8c9943f478bf6c7e53f5b14255f24ee876652c72e00c6ad975ce`

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
- Model: `75api-minimax-h3 / minimax_h3_no_audios`
- Mode: `IMAGE_TO_VIDEO`
- Source mode: `IMAGE_TO_VIDEO`
- First frame: `{"mode": "CURRENT_OFFICIAL_IMAGE", "authority_required": true}`
- Source/reference bindings: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:BROKEN_UMBRELLA_RIB", "asset_authority_ref": "book:990401:prop:BROKEN_UMBRELLA_RIB", "authority_fingerprint": "ed60d561d9a90d0fca22feb23a8653581a561f900ee5b8d417c731892b2ca5b1", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:RED_UMBRELLA", "asset_authority_ref": "book:990401:prop:RED_UMBRELLA", "authority_fingerprint": "9acdad16c814b59509b3a642246f2019f5b4dbe2b18b3bfb7451e6d2d6af9168", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- Duration: `5 sec`; aspect ratio: `16:9`; resolution: `768p`
- PromptIR hash: `a7bb9e8c168271fc30365441f472d40741683957717648de56827f5ddd217b63`
- Payload fingerprint: `f27d70c6df91f4a17952061b13263b88ffa0d93e0e534e6274fe7660c14635f9`

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
- Model: `75api-minimax-h3 / minimax_h3_no_audios`
- Mode: `IMAGE_TO_VIDEO`
- Source mode: `IMAGE_TO_VIDEO`
- First frame: `{"mode": "CURRENT_OFFICIAL_IMAGE", "authority_required": true}`
- Source/reference bindings: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- Duration: `5 sec`; aspect ratio: `16:9`; resolution: `768p`
- PromptIR hash: `36cc25ed06c19ae2722463fa81573363ca2804eec962dede295fb2b6ffba1e79`
- Payload fingerprint: `136ee9332abf9be13cb23d0510f7b2753b08601c184e84d2104aa8351d5515fe`

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
- Model: `75api-minimax-h3 / minimax_h3_no_audios`
- Mode: `IMAGE_TO_VIDEO`
- Source mode: `IMAGE_TO_VIDEO`
- First frame: `{"mode": "CURRENT_OFFICIAL_IMAGE", "authority_required": true}`
- Source/reference bindings: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC001", "asset_authority_ref": "book:990401:scene:E01_SC001", "authority_fingerprint": "ad74364e7df176a61852ea9c98867aae80454ebc014be49c2c875217ccb2c398", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- Duration: `5 sec`; aspect ratio: `16:9`; resolution: `768p`
- PromptIR hash: `727b25d1f73a1e2a2893ab0f5a66da16d76ac121a5630a86b66828fe2237acd9`
- Payload fingerprint: `64fb3b9dffdd0441e9be06144f89aaa09e811e01fe4af716642139db8745a814`

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
- Model: `75api-minimax-h3 / minimax_h3_no_audios`
- Mode: `IMAGE_TO_VIDEO`
- Source mode: `IMAGE_TO_VIDEO`
- First frame: `{"mode": "CURRENT_OFFICIAL_IMAGE", "authority_required": true}`
- Source/reference bindings: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC002", "asset_authority_ref": "book:990401:scene:E01_SC002", "authority_fingerprint": "74f6bbdb9ac6c545d20e8e5610d1ad71aff7e270a5ed2df7a103093cc4ef8ef9", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:APPLE", "asset_authority_ref": "book:990401:prop:APPLE", "authority_fingerprint": "10ff684a8071dd7f7d27c276068aabfb962d97e5ab3387ca895dbbff1f06e812", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:DOOR_LOCK", "asset_authority_ref": "book:990401:prop:DOOR_LOCK", "authority_fingerprint": "bf33b28c4f7995de223faecc547c35a86772d615f7d1f296d782c5bb3a360149", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- Duration: `5 sec`; aspect ratio: `16:9`; resolution: `768p`
- PromptIR hash: `d842870fee30191b299f51adc764e7211013d11e343a770fe2e4dcfa125a64e3`
- Payload fingerprint: `a9f9673c9a21fbe84c776b4a31af4db896f4668bfbebb231176b41b6a6d5e26e`

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
- Model: `75api-minimax-h3 / minimax_h3_no_audios`
- Mode: `IMAGE_TO_VIDEO`
- Source mode: `IMAGE_TO_VIDEO`
- First frame: `{"mode": "CURRENT_OFFICIAL_IMAGE", "authority_required": true}`
- Source/reference bindings: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC002", "asset_authority_ref": "book:990401:scene:E01_SC002", "authority_fingerprint": "74f6bbdb9ac6c545d20e8e5610d1ad71aff7e270a5ed2df7a103093cc4ef8ef9", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- Duration: `5 sec`; aspect ratio: `16:9`; resolution: `768p`
- PromptIR hash: `a264d37992437ac959360123facd7cb5585ae2ba214ff1b36b574bae8cb7ce54`
- Payload fingerprint: `f830e7386805d9e95a94b94f612c9f7628259144f5a07763037d1bedf0ef1a3f`

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
- Model: `75api-minimax-h3 / minimax_h3_no_audios`
- Mode: `IMAGE_TO_VIDEO`
- Source mode: `IMAGE_TO_VIDEO`
- First frame: `{"mode": "CURRENT_OFFICIAL_IMAGE", "authority_required": true}`
- Source/reference bindings: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC002", "asset_authority_ref": "book:990401:scene:E01_SC002", "authority_fingerprint": "74f6bbdb9ac6c545d20e8e5610d1ad71aff7e270a5ed2df7a103093cc4ef8ef9", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:HANDBAG", "asset_authority_ref": "book:990401:prop:HANDBAG", "authority_fingerprint": "71a415f0129a56d418f16c89af3c4cbda4de63607c7bef0634aa2b6582a31538", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- Duration: `5 sec`; aspect ratio: `16:9`; resolution: `768p`
- PromptIR hash: `4f4cffccce403ca9665c85613ebd8436668afbeb9aefadbc5c3382bb6d1d8cb4`
- Payload fingerprint: `c5b784fa228f29e6a239cbc53184f11db882be8b046b60d36087266528fe4a46`

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
- Model: `75api-minimax-h3 / minimax_h3_no_audios`
- Mode: `IMAGE_TO_VIDEO`
- Source mode: `IMAGE_TO_VIDEO`
- First frame: `{"mode": "CURRENT_OFFICIAL_IMAGE", "authority_required": true}`
- Source/reference bindings: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC002", "asset_authority_ref": "book:990401:scene:E01_SC002", "authority_fingerprint": "74f6bbdb9ac6c545d20e8e5610d1ad71aff7e270a5ed2df7a103093cc4ef8ef9", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:POCKET_HARD_OBJECT", "asset_authority_ref": "book:990401:prop:POCKET_HARD_OBJECT", "authority_fingerprint": "52f8ff73ee9dbd1890475391ab1ae3390d82f2d70b9ee5a4c37927b1186381fc", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:TABLE_SCRATCH", "asset_authority_ref": "book:990401:prop:TABLE_SCRATCH", "authority_fingerprint": "625c30701544f1359411fcb8e03c1cfcf921b20a5adbc8b688cee8fba802b763", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- Duration: `5 sec`; aspect ratio: `16:9`; resolution: `768p`
- PromptIR hash: `477da728ee23f9605fbfaffc7ee6455a79c48de9b8796e1da969a683593c4657`
- Payload fingerprint: `225d05fc13fa2de6a2b47991fbd7bb212b3d664e40d4c869d90d4f3c7b2adebc`

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
- Model: `75api-minimax-h3 / minimax_h3_no_audios`
- Mode: `IMAGE_TO_VIDEO`
- Source mode: `IMAGE_TO_VIDEO`
- First frame: `{"mode": "CURRENT_OFFICIAL_IMAGE", "authority_required": true}`
- Source/reference bindings: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC002", "asset_authority_ref": "book:990401:scene:E01_SC002", "authority_fingerprint": "74f6bbdb9ac6c545d20e8e5610d1ad71aff7e270a5ed2df7a103093cc4ef8ef9", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}, {"role": "PROP_REFERENCE", "identity_ref": "prop:RED_FIBER", "asset_authority_ref": "book:990401:prop:RED_FIBER", "authority_fingerprint": "a24881e736ace0d037eeecaaa26431450dd33097eb4ff6293999d2c7abb98660", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- Duration: `5 sec`; aspect ratio: `16:9`; resolution: `768p`
- PromptIR hash: `6cc2f82090f0d60e478021a19258571fedb9b165aba0ab0aa76073584f735d2e`
- Payload fingerprint: `847dcc15ab7338f325da35422e03a40133189766c6a4c6200c45121eb5498f79`

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
- Model: `75api-minimax-h3 / minimax_h3_no_audios`
- Mode: `IMAGE_TO_VIDEO`
- Source mode: `IMAGE_TO_VIDEO`
- First frame: `{"mode": "CURRENT_OFFICIAL_IMAGE", "authority_required": true}`
- Source/reference bindings: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC002", "asset_authority_ref": "book:990401:scene:E01_SC002", "authority_fingerprint": "74f6bbdb9ac6c545d20e8e5610d1ad71aff7e270a5ed2df7a103093cc4ef8ef9", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- Duration: `5 sec`; aspect ratio: `16:9`; resolution: `768p`
- PromptIR hash: `4cb1b90a90929c7b46c40f02c971355f1d2d58886a03874fb93598c71276299b`
- Payload fingerprint: `15e0d2fea5fa2babe68b9c38c0462d60fa7b5d2bffdbc5fc00396e809ac4ce2d`

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
- Model: `75api-minimax-h3 / minimax_h3_no_audios`
- Mode: `IMAGE_TO_VIDEO`
- Source mode: `IMAGE_TO_VIDEO`
- First frame: `{"mode": "CURRENT_OFFICIAL_IMAGE", "authority_required": true}`
- Source/reference bindings: `[{"role": "SCENE_REFERENCE", "identity_ref": "scene:E01_SC002", "asset_authority_ref": "book:990401:scene:E01_SC002", "authority_fingerprint": "74f6bbdb9ac6c545d20e8e5610d1ad71aff7e270a5ed2df7a103093cc4ef8ef9", "reference_authority_ref": "", "reference_authority_fingerprint": "", "reference_token": ""}]`
- Duration: `5 sec`; aspect ratio: `16:9`; resolution: `768p`
- PromptIR hash: `ecc93f7cd39c9f7dbd132acc9fca7129a5beeb7aa49487e7ffe2b85781112809`
- Payload fingerprint: `49114f87a5281d093a0c582d12ebc103c8b8b49fbdca3f67f9264094259b5e9e`

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

`NOT_APPLICABLE` — no current VIDEO PromptIR authority.
