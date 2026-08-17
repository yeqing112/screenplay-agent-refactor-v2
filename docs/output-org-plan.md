# 输出目录重组 — 最终状态

> 已完成并部署。所有 Agent 已改为通过 `config.output_path(book_title, *parts)` 写入。

## 新结构

```
outputs/{小说名}/
├─ 原始小说.txt                    ← ingest 时写入
├─ bible.md                        ← bible agent
├─ {genre}_改编方案.md              ← adapter agent (e.g. short_drama_改编方案.md)
├─ analysis/                       ← reader agent
│   ├─ 角色汇总.csv
│   ├─ 外貌片段.json
│   └─ 剧情摘要.md
├─ portraits/                      ← portrait agent
│   ├─ 角色画像.json               (含 core/outfit/scene 分层 prompt)
│   ├─ 角色画像.md
│   └─ 生图提示词.txt
├─ outlines/                       ← outline agent
│   └─ 大纲.md
├─ scripts/                        ← scriptwriter agent
│   ├─ 第01集脚本.md
│   └─ ...
└─ qa/                             ← qa agent
    └─ 质检报告.md
```

## 变更加总

| 文件 | 变更 |
|------|------|
| `config.py` | 删除 7 个目录常量，新增 `sanitize_filename()` + `output_path()` |
| `agents/reader.py` | `ANALYSIS_DIR` → `output_path(title, "analysis", ...)` |
| `agents/bible.py` | `BIBLES_DIR` → `output_path(title, "bible.md")` |
| `agents/adapter.py` | `ADAPTATIONS_DIR` → `output_path(title, "{genre}_改编方案.md")` |
| `agents/portrait.py` | `WORK/portraits` → `output_path(title, "portraits", ...)` |
| `agents/outline.py` | `OUTLINES_DIR` → `output_path(title, "outlines", "大纲.md")` |
| `agents/scriptwriter.py` | `SCRIPTS_DIR` → `output_path(title, "scripts", "第{ep:02d}集脚本.md")` |
| `agents/qa.py` | `QA_DIR` → `output_path(title, "qa", "质检报告.md")` |
| `core/ingest.py` | 导入后写入 `output_path(title, "原始小说.txt")` |
| `scripts/migrate_outputs.py` | 新增迁移脚本 |

## 保留的目录

- `work/books/` — 原始小说文件
- `work/indexes/` — ChromaDB 向量索引
- `work/db/` — SQLite 数据库文件

## 迁移（旧→新）

```bash
cd ~/projects/screenplay-agent
source .venv/bin/activate
# 试运行
python -m scripts.migrate_outputs --dry-run
# 执行
python -m scripts.migrate_outputs
```

## 验证结果

全链路端到端验证通过（mjds, 1137章, 前5章分析 → bible → portrait → adapt → outline → script）：
- 11 个输出文件全部写入 `outputs/mjds/` 下
- 分层 prompt 字段正常（core=visual, outfit/scene 留空）
- 文件名均为中文，`sanitize_filename` 保证跨平台兼容

Commit: `ed05d79`
