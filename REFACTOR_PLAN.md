# 重构计划 - Screenplay Agent v2 (已完成)

> 所有 4 个 Phase 已在 `refactor/v2` 分支完成并合并。

## 当前状态

- ~4000 行 Python，30+ 个文件
- 9 个 Agent，4 个 Genre，9 张数据库表
- 14 个 CLI 命令
- 重构分支：`refactor/v2`（可合并回 main）

## 已解决的问题

| # | 问题 | 解决方式 | Commit |
|---|------|---------|--------|
| 1 | portrait.py 516 行职责过重 | 拆分为 3 个文件：portrait.py / portrait_base.py / portrait_stages.py | `1e36abc` |
| 2 | 16 处 Session() 散落各 Agent | BaseAgent + `self.session()` context manager | `246e935` |
| 3 | 9 个 Agent 无基类 | 新建 `agents/base.py`，所有 Agent 继承 BaseAgent | `246e935` |
| 4 | Prompt 硬编码在 Python 里 | 新建 `prompts/` 目录 + `core/prompts.py` 加载器 | `24627cf` |
| 5 | 4 个 Genre 文件 80% 重复 | Genre JSON 配置化 + Genre 类配置驱动 | `24627cf` |
| 6 | portrait.py 硬编码 chapter_count=1137 | 从 DB Book 对象获取 `book.chapter_count` | `1e36abc` |
| 7 | migrate.py 手写 SQL | 引入 Alembic + 基线迁移 `v2 baseline` | `dc434d6` |
| 8 | requirements.txt 未使用依赖 | 清理 4 个未使用依赖 | `dc434d6` |
| 9 | models.py 193 行 9 张表混在一起 | 拆分为 5 个子模块（book/character/script/kv/__init__） | `dc434d6` |

## Extra 变更

| 事项 | 说明 | Commit |
|------|------|--------|
| 输出目录重组 | 取消按类型分散的目录常量，统一 `outputs/{title}/` 结构 | `ed05d79` |
| `output_path()` + `sanitize_filename()` | 新增 config 辅助函数 | `ed05d79` |
| prompt 模板变量冲突 | `{name}` → `{character_name}` 避免与 `load_prompt(name, **kwargs)` 冲突 | `06c8e48` |
| 分层 prompt 回退 | core←visual，outfit/scene 留空 | `1e36abc` |

## 当前架构

```
outputs/{小说名}/
  ├─ 原始小说.txt
  ├─ bible.md
  ├─ {genre}_改编方案.md
  ├─ analysis/     (reader 分析结果)
  ├─ portraits/    (角色画像 JSON/MD/TXT)
  ├─ outlines/     (分集大纲)
  ├─ scripts/      (剧本)
  └─ qa/           (质检报告)
```

## 后续建议

1. 填充 `prompts/genres/*_rules.txt` 实际规则内容（长期，优先级低）
2. 更新 `docs/output-org-plan.md` 为最终状态
3. 合并 `refactor/v2` → main
4. 端到端 pipeline 测试（已跑通 read→bible→portrait→adapt→outline→script 全链路）
