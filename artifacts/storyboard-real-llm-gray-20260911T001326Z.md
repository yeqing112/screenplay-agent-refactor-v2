# Storyboard Real LLM Gray Validation

- Generated at: `2026-09-11T00:13:26.736272`
- Compiler mode: `deterministic-mock`
- Temp book id: `999905`
- Samples: `3`
- Passed / failed: `3 / 0`
- After audit errors / warnings: `0 / 0`
- Compiler diagnostics warnings: `3`
- LLM attempts/tokens: `0 / prompt=0 / cached=0 / completion=0`
- LLM cache hit rate / max latency: `None / 0.0ms`
- Total / average / max elapsed: `0.274s / 0.091s / 0.121s`

## Samples

- `#990301:1:1` 导演运行时灰度样本 / 雨夜旧公寓门厅 => PASS
  - elapsed: `0.121s`
  - timings: `clone_seconds=0.024s, compile_seconds=0.075s, audit_seconds=0.003s, rollback_seconds=0.018s, rollback_verify_seconds=0.001s`
  - diagnostics_status: `warning`
  - compiler_warnings: `deterministic clone repair uses Model Adapter baseline`
  - structured: scene=`3`, characters=`1`, props=`0`, action_beats=`2`
  - static_preview: 雨夜旧公寓门厅（@雨夜旧公寓门厅），中景构图，电影感首帧画面。开场画面中，深色铁门关闭，林晚站在门外，雨水顺着风衣滴落。主体人物为林晚（@林晚），身份、脸型、发型和服装以对应参考图为准。画面细节包含雨夜旧公寓门厅（@雨夜旧公寓门厅），老旧公寓门厅，深色铁门、潮湿水泥地面、墙面剥落，门外是雨夜街灯。门外冷色雨光从侧后方进入，门厅顶部一盏昏黄灯形成轮廓光。林晚（
  - motion_preview: 6秒内，镜头缓慢slow push-in，保持首帧构图、场景、人物身份、服装、发型和关键道具连续一致。随后林晚推开深色铁门进入门厅，随后她回头确认门外无人，再缓慢关门。全过程不改变脸型、服装、场景布局和道具状态，不出现突然变形或无依据新增元素。
- `#990301:1:2` 导演运行时灰度样本 / 雨夜旧公寓门厅 => PASS
  - elapsed: `0.077s`
  - timings: `clone_seconds=0.01s, compile_seconds=0.046s, audit_seconds=0.003s, rollback_seconds=0.017s, rollback_verify_seconds=0.001s`
  - diagnostics_status: `warning`
  - compiler_warnings: `deterministic clone repair uses Model Adapter baseline`
  - structured: scene=`3`, characters=`1`, props=`0`, action_beats=`2`
  - static_preview: 雨夜旧公寓门厅（@雨夜旧公寓门厅），中景构图，电影感首帧画面。开场画面中，铁门已经关闭，林晚站在门厅右侧，手握银色钥匙串。主体人物为林晚（@林晚），身份、脸型、发型和服装以对应参考图为准。画面细节包含雨夜旧公寓门厅（@雨夜旧公寓门厅），老旧公寓门厅，深色铁门、潮湿水泥地面、墙面剥落，门外是雨夜街灯。门外冷色雨光从侧后方进入，门厅顶部一盏昏黄灯形成轮廓光。林晚
  - motion_preview: 起始画面中，铁门已经关闭，林晚站在门厅右侧，手握银色钥匙串。固定机位，镜头不移动。随后，林晚拧干风衣袖口的雨水；随后，她抬眼看向门缝并停住。最终，她停止拧袖口，目光锁定门缝，银色钥匙串垂在右手边。全过程保持与首帧一致，人物身份、服装、发型、场景、道具、光线和构图不突变。
- `#990301:1:3` 导演运行时灰度样本 / 雨夜旧公寓门厅 => PASS
  - elapsed: `0.076s`
  - timings: `clone_seconds=0.01s, compile_seconds=0.048s, audit_seconds=0.003s, rollback_seconds=0.015s, rollback_verify_seconds=0.001s`
  - diagnostics_status: `warning`
  - compiler_warnings: `deterministic clone repair uses Model Adapter baseline`
  - structured: scene=`3`, characters=`1`, props=`0`, action_beats=`2`
  - static_preview: 雨夜旧公寓门厅（@雨夜旧公寓门厅），中景构图，电影感首帧画面。开场画面中，林晚仍站在铁门右侧，目光锁定门缝，钥匙串垂在手边。主体人物为林晚（@林晚），身份、脸型、发型和服装以对应参考图为准。画面细节包含雨夜旧公寓门厅（@雨夜旧公寓门厅），老旧公寓门厅，深色铁门、潮湿水泥地面、墙面剥落，门外是雨夜街灯。门外冷色雨光从侧后方进入，门厅顶部一盏昏黄灯形成轮廓光。林
  - motion_preview: 起始画面中，林晚仍站在铁门右侧，目光锁定门缝，钥匙串垂在手边。镜头采用slow pan-right运动方式。随后，林晚沿墙向门厅深处迈出两步；随后，她在楼梯口停下回望铁门。最终，林晚停在楼梯口，半侧身回望关闭的深色铁门，门厅保持安静。全过程保持与首帧一致，人物身份、服装、发型、场景、道具、光线和构图不突变。
