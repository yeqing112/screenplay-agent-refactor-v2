# Storyboard Real LLM Gray Validation

- Generated at: `2026-09-10T17:36:02.257287`
- Compiler mode: `real-llm`
- Temp book id: `999905`
- Samples: `1`
- Passed / failed: `0 / 1`
- After audit errors / warnings: `1 / 1`
- Compiler diagnostics warnings: `0`
- Total / average / max elapsed: `31.677s / 31.677s / 31.677s`

## Samples

- `#990306:1:1` 生产就绪度测试 / 深夜便利店 => FAIL
  - failure_stage: `audit`
  - elapsed: `31.677s`
  - timings: `clone_seconds=0.044s, compile_seconds=31.6s, audit_seconds=0.003s, rollback_seconds=0.03s, rollback_verify_seconds=0.001s`
  - diagnostics_status: `pass`
  - warnings: `missing_structured_character_assets`
  - structured: scene=`2`, characters=`0`, props=`0`, action_beats=`2`
  - static_preview: 深夜便利店收银区，狭窄空间内货架与玻璃门形成纵深，冷白荧光灯照亮整个区域，写实电影感画面。一名男人站在收银台前，伸手将一张照片放在台面上。
  - motion_preview: 4秒内，镜头固定不动，保持首帧构图、场景、人物身份、服装、发型和关键道具连续一致。全过程不改变脸型、服装、场景布局和道具状态，不出现突然变形或无依据新增元素。
