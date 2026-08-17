# 2026-07-25 authority_prompt_inheritance 二次补验记录

## 补验目标

验证《三个和尚》项目中，第 1 集镜头 2 / 3 / 4 的 `authority_prompt_inheritance` 是否已经从误报收敛为可用于生产的判断结果。

## 本轮调整

1. 修复 `authority_prompt_inheritance` 的关键词抽取规则，避免中文标点/模板文本导致的抽取异常。
2. 增强等价匹配，支持更自然的中文表达命中。
3. 将权威继承判断从“逐条机械命中”调整为“剔除模板噪音后，按资产检查关键事实最低命中数/命中率”。
4. 重启本地后端服务 `http://127.0.0.1:18769`，确保验收基于最新代码。

## 代码验收

执行时间：2026-07-25

执行命令：

```powershell
python -m unittest tests.test_storyboard_prompt_authority_diagnostics -v
python -m unittest tests.test_storyboard_prompt_repair_context tests.test_storyboard_prompt_context_legacy_refresh -v
```

结果：

- 两组测试全部通过

## 接口复验

复验对象：

- 项目：`三个和尚`
- 范围：第 1 集镜头 `2 / 3 / 4`

复验接口：

- `GET /api/books/14/storyboard/1/2/prompt-versions`
- `GET /api/books/14/storyboard/1/3/prompt-versions`
- `GET /api/books/14/storyboard/1/4/prompt-versions`
- `GET /api/pipeline/book/14/outputs`

复验结果：

- 镜头 2：当前版本 `v2`，无失败检查项
- 镜头 3：当前版本 `v1`，无失败检查项
- 镜头 4：当前版本 `v1`，无失败检查项

说明：

- 当前 `compiler_diagnostics.status` 仍可为 `warning`
- 但 `checks` 中已不存在 `authority_prompt_inheritance` 失败项
- 当前 warning 主要来自“候选参考图未锁定”，不再属于提示词继承失败

## 真浏览器复验

复验时间：2026-07-25

前端入口：

- `http://127.0.0.1:5182`

路径：

1. 打开项目 `三个和尚`
2. 进入 `正式工作台`
3. 进入 `镜头工作台`
4. 打开第 1 集镜头 2

页面结果：

- 镜头 2 的 `authority_prompt_inheritance` 已显示为“通过”
- 页面不再提示“静态提示词对这些资产的权威原文继承不足”
- 当前仍保留 1 条 warning：`木桶 目前只有候选参考图，尚未锁定`

## 本轮结论

本轮补验确认：

1. `authority_prompt_inheritance` 的误报已经明显收敛
2. 镜头 2 / 3 / 4 不再因为权威继承检查被卡住
3. 当前剩余问题已切换为资产治理问题，而不是提示词继承问题

## 下一步建议

1. 继续处理“候选参考图未锁定”问题，尤其是道具参考图
2. 按相同验收方法继续巡检第 1 集其余镜头
3. 将本轮规则收敛同步纳入后续全项目 QA 基线
