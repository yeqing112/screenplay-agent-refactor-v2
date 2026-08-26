# 分镜批量修复预检计划

- 生成时间：2026-08-26T00:34:56.775260
- 模式：dry-run / 未修改真实项目
- 临时项目：`book 999906`
- 确认令牌：`3b214ff519416f24`
- 样本数：30
- error：30 -> 0
- warning：90 -> 24
- 可进入人工评审：是
- 可直接进入未来 apply 命令：是
- 缺少回滚锚点：16
- 真实 apply 阻塞项：0

## 样本影响清单

| 项目 | 镜头 | 修复前 error | 修复后 error | 修复前 warning | 修复后 warning | 回滚锚点 | 真实 apply 状态 |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| #14 三个和尚 | 1-2 | 1 | 0 | 3 | 1 | v17 / id 138 | ready |
| #14 三个和尚 | 1-3 | 1 | 0 | 3 | 1 | v2 / id 88 | ready |
| #14 三个和尚 | 1-4 | 1 | 0 | 3 | 1 | v2 / id 67 | ready |
| #14 三个和尚 | 1-5 | 1 | 0 | 3 | 1 | v2 / id 70 | ready |
| #14 三个和尚 | 1-6 | 1 | 0 | 3 | 1 | v2 / id 85 | ready |
| #14 三个和尚 | 1-7 | 1 | 0 | 3 | 1 | v2 / id 73 | ready |
| #14 三个和尚 | 1-8 | 1 | 0 | 3 | 1 | v2 / id 74 | ready |
| #14 三个和尚 | 1-9 | 1 | 0 | 3 | 1 | v1 / id 75 | ready |
| #14 三个和尚 | 1-10 | 1 | 0 | 3 | 1 | v3 / id 82 | ready |
| #14 三个和尚 | 1-11 | 1 | 0 | 3 | 1 | v3 / id 83 | ready |
| #3 金丝雀 | 1-4 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-5 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-6 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-7 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-8 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-10 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-11 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-13 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #3 金丝雀 | 1-15 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-16 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-10 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-11 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-12 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-13 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-14 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-18 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #14 三个和尚 | 1-12 | 1 | 0 | 3 | 1 | v3 / id 84 | ready |
| #14 三个和尚 | 1-13 | 1 | 0 | 3 | 1 | v1 / id 97 | ready |
| #14 三个和尚 | 1-14 | 1 | 0 | 3 | 1 | v1 / id 98 | ready |
| #14 三个和尚 | 1-15 | 1 | 0 | 3 | 2 | v2 / id 99 | ready |

## 落库前门禁

1. 必须由用户明确确认本预检报告。
2. apply 命令必须要求确认令牌，不能仅凭默认参数写真实项目。
3. 每个真实镜头必须有可回滚锚点；没有 prompt version 的镜头，应先创建 baseline version。
4. 真实项目必须存在可绑定的场景资产；克隆预检中的临时场景资产不能作为真实 apply 依据。
5. apply 后必须立即产出二次审计和推荐 rollback 清单。
