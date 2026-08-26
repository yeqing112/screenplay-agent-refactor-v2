# 分镜批量修复预检计划

- 生成时间：2026-08-24T20:54:03.169915
- 模式：dry-run / 未修改真实项目
- 临时项目：`book 999906`
- 确认令牌：`5620f49a1becf3b8`
- 样本数：60
- error：115 -> 0
- warning：177 -> 22
- 可进入人工评审：是
- 可直接进入未来 apply 命令：是
- 缺少回滚锚点：55
- 真实 apply 阻塞项：0

## 样本影响清单

| 项目 | 镜头 | 修复前 error | 修复后 error | 修复前 warning | 修复后 warning | 回滚锚点 | 真实 apply 状态 |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| #5 神农架历险记 | 1-2 | 3 | 0 | 3 | 0 | v9 / id 139 | ready |
| #5 神农架历险记 | 1-5 | 3 | 0 | 3 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-7 | 3 | 0 | 3 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-9 | 3 | 0 | 3 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-10 | 3 | 0 | 3 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-11 | 3 | 0 | 3 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-12 | 3 | 0 | 3 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-13 | 3 | 0 | 2 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-14 | 3 | 0 | 2 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-15 | 3 | 0 | 3 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-1 | 2 | 0 | 3 | 1 | v2 / id 46 | ready |
| #5 神农架历险记 | 1-4 | 2 | 0 | 3 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-6 | 2 | 0 | 3 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-8 | 2 | 0 | 3 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-16 | 2 | 0 | 3 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-17 | 2 | 0 | 3 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-18 | 2 | 0 | 3 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-19 | 2 | 0 | 3 | 0 | missing_prompt_version | ready |
| #5 神农架历险记 | 1-3 | 1 | 0 | 3 | 0 | v7 / id 52 | ready |
| #5 神农架历险记 | 1-20 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #3 金丝雀 | 1-14 | 3 | 0 | 3 | 1 | v3 / id 131 | ready |
| #3 金丝雀 | 1-19 | 3 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-20 | 3 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-21 | 3 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-12 | 2 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-18 | 2 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-26 | 2 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-30 | 2 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-31 | 2 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-32 | 2 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-33 | 2 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-34 | 2 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-1 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-2 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-3 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-4 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-5 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-6 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-7 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #3 金丝雀 | 1-8 | 1 | 0 | 3 | 1 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-15 | 3 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-2 | 2 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-4 | 2 | 0 | 3 | 1 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-5 | 2 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-6 | 2 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-16 | 2 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-17 | 2 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-19 | 2 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-20 | 2 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-21 | 2 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-1 | 1 | 0 | 2 | 0 | v3 / id 43 | ready |
| #1 苗疆道事 | 1-3 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-7 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-8 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-9 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-10 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-11 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-12 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-13 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |
| #1 苗疆道事 | 1-14 | 1 | 0 | 3 | 0 | missing_prompt_version | ready |

## 落库前门禁

1. 必须由用户明确确认本预检报告。
2. apply 命令必须要求确认令牌，不能仅凭默认参数写真实项目。
3. 每个真实镜头必须有可回滚锚点；没有 prompt version 的镜头，应先创建 baseline version。
4. 真实项目必须存在可绑定的场景资产；克隆预检中的临时场景资产不能作为真实 apply 依据。
5. apply 后必须立即产出二次审计和推荐 rollback 清单。
