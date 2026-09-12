# 分镜批量修复预检计划

- 生成时间：2026-09-12T15:07:27.503520
- 模式：dry-run / 未修改真实项目
- 临时项目：`book 999906`
- 确认令牌：`1978882d2a412dda`
- 样本数：10
- error：30 -> 3
- warning：30 -> 4
- 可进入人工评审：否
- 可直接进入未来 apply 命令：否
- 缺少回滚锚点：10
- 真实 apply 阻塞项：10

## 样本影响清单

| 项目 | 镜头 | 修复前 error | 修复后 error | 修复前 warning | 修复后 warning | 回滚锚点 | 真实 apply 状态 |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| #990401 潮汐回声·生产链路测试样本 | 1-1 | 3 | 0 | 3 | 1 | missing_prompt_version | real_project_missing_bindable_scene_asset |
| #990401 潮汐回声·生产链路测试样本 | 1-2 | 3 | 0 | 3 | 0 | missing_prompt_version | real_project_missing_bindable_scene_asset |
| #990401 潮汐回声·生产链路测试样本 | 1-3 | 3 | 0 | 3 | 0 | missing_prompt_version | real_project_missing_bindable_scene_asset |
| #990401 潮汐回声·生产链路测试样本 | 1-4 | 3 | 3 | 3 | 3 | missing_prompt_version | real_project_missing_bindable_scene_asset |
| #990401 潮汐回声·生产链路测试样本 | 1-5 | 3 | 0 | 3 | 0 | missing_prompt_version | real_project_missing_bindable_scene_asset |
| #990401 潮汐回声·生产链路测试样本 | 1-6 | 3 | 0 | 3 | 0 | missing_prompt_version | real_project_missing_bindable_scene_asset |
| #990401 潮汐回声·生产链路测试样本 | 1-7 | 3 | 0 | 3 | 0 | missing_prompt_version | real_project_missing_bindable_scene_asset |
| #990401 潮汐回声·生产链路测试样本 | 1-8 | 3 | 0 | 3 | 0 | missing_prompt_version | real_project_missing_bindable_scene_asset |
| #990401 潮汐回声·生产链路测试样本 | 2-3 | 3 | 0 | 3 | 0 | missing_prompt_version | real_project_missing_bindable_scene_asset |
| #990401 潮汐回声·生产链路测试样本 | 3-1 | 3 | 0 | 3 | 0 | missing_prompt_version | real_project_missing_bindable_scene_asset |

## 落库前门禁

1. 必须由用户明确确认本预检报告。
2. apply 命令必须要求确认令牌，不能仅凭默认参数写真实项目。
3. 每个真实镜头必须有可回滚锚点；没有 prompt version 的镜头，应先创建 baseline version。
4. 真实项目必须存在可绑定的场景资产；克隆预检中的临时场景资产不能作为真实 apply 依据。
5. apply 后必须立即产出二次审计和推荐 rollback 清单。
