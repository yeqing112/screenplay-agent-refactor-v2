# 分镜批量修复预检计划

- 生成时间：2026-08-26T00:38:01.176806
- 模式：dry-run / 未修改真实项目
- 临时项目：`book 999906`
- 确认令牌：`60caf6ec2647fafb`
- 样本数：9
- error：9 -> 0
- warning：26 -> 9
- 可进入人工评审：是
- 可直接进入未来 apply 命令：是
- 缺少回滚锚点：9
- 真实 apply 阻塞项：0

## 样本影响清单

| 项目 | 镜头 | 修复前 error | 修复后 error | 修复前 warning | 修复后 warning | 回滚锚点 | 真实 apply 状态 |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| #3 金丝雀 | 1-17 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-22 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-23 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-24 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-25 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-27 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-28 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-29 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-9 | 1 | 0 | 2 | 1 | missing_prompt_version | ready |

## 落库前门禁

1. 必须由用户明确确认本预检报告。
2. apply 命令必须要求确认令牌，不能仅凭默认参数写真实项目。
3. 每个真实镜头必须有可回滚锚点；没有 prompt version 的镜头，应先创建 baseline version。
4. 真实项目必须存在可绑定的场景资产；克隆预检中的临时场景资产不能作为真实 apply 依据。
5. apply 后必须立即产出二次审计和推荐 rollback 清单。
