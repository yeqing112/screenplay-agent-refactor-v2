# MiniMax H3 灰度预检｜Book 990400 E1 S1

- 模式：dry-run-preflight
- 项目：导演运行时灰度样本
- 场景：雨夜旧公寓门厅
- Prompt 长度：915
- 时长：6s（分镜 6s）
- 任务模式：text_to_video
- 参考图：0/2 张可提交
- 首帧兜底：无
- 首帧可访问：None
- Provider 首帧 URL：-
- 模型配置：local-video-7deneh / minimax-h3-async / MiniMax-H3
- API Key：已配置
- 可真实提交：False
- 本次会真实提交：False

## Blockers

- compiled_reference_images_not_provider_accessible

## Warnings

- qiniu_public_asset_storage_configured_but_publish_reference_images_flag_not_enabled

## 自动候选选择

- 候选总数：3
- 参考图数量：2
- 选中首帧：
- 外部 URL：False
- 首帧 URL 可访问：False
- 已有视频：False
- Prompt 遗留导演标记：False
- Prompt 灰度安全风险：False
- 备选：
  - 990400:1:2｜雨夜旧公寓门厅｜external=False｜accessible=False｜hasVideo=False｜legacyMarkers=False｜safetyRisk=False
  - 990400:1:3｜雨夜旧公寓门厅｜external=False｜accessible=False｜hasVideo=False｜legacyMarkers=False｜safetyRisk=False

## 真实运行门禁

- allow_real_cli: False
- real_env_enabled: False
- confirmation_matches: False
- target_whitelisted: False

## 真实运行命令

```powershell
$env:MINIMAX_H3_GRAY_REAL="1"
$env:MINIMAX_H3_GRAY_CONFIRM="CONFIRM_MINIMAX_H3_SUBMIT"
$env:MINIMAX_H3_GRAY_WHITELIST="990400:1:1"
python scripts/validate-minimax-h3-gray.py --book-id 990400 --episode 1 --shot-id 1 --allow-real
```

## H3 Prompt 预览

```text
[Shot 1] Live-action cinematic footage. Scene: 雨夜旧公寓门厅. Duration: 6 seconds. Reference assignments: Reference image 1 (雨夜旧公寓门厅): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林晚): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 深色铁门关闭，林晚站在门外，雨水顺着风衣滴落. Observable action timeline: 0.00-1.20s: 深色铁门关闭，林晚站在门外，雨水顺着风衣滴落。 Camera: 缓慢slow push-in. 1.20-4.50s: 林晚推开深色铁门进入门厅，回头确认门外无人，再缓慢关门。 Camera: 缓慢slow push-in. 4.50-6.00s: 铁门重新关闭，林晚停在门厅右侧，手仍握着银色钥匙串。 Camera: 缓慢slow push-in. Final frame: 铁门重新关闭，林晚停在门厅右侧，手仍握着银色钥匙串. Shot size: 中景; camera movement: 缓慢slow push-in. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或
```
