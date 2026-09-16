# Director V3 新真实剧本 Intake

此目录只接收用户明确提供、并显式指定路径或 manifest 的真实剧本源文件。它是
Source Package 的输入边界，不是生产数据库，也不是测试 fixture 目录。

## 使用规则

- 允许格式以当前解析器为准：UTF-8 `.txt` / `.md` / `.markdown`、可提取文本的
  `.docx` / `.pdf`，以及 manifest 中的 `source_text`（粘贴文本）。首选 UTF-8
  plain text 或 Markdown。
- 不要把测试样本、Golden、内部示例、模型生成内容或旧项目导出物放入这里。
- 原始文件一旦被 Intake 接收即视为不可变；修改必须产生新的 source version，不能
  覆盖旧文件或旧 package。
- Intake 不会自动创建 book、scene、FactSnapshot、ScriptIR、Treatment 或
  Blocking，也不会调用 LLM、MiMo、图像/视频供应商或外部存储。
- 只有显式运行 Intake CLI 并提供 `--source` 或 `--manifest` 才会读取文件；系统不会
  扫描工作区来猜测剧本。

示例（只做 provider-free 预检）：

```text
python scripts/run_director_v3_new_source_intake.py --source <absolute-path-to-screenplay.txt>
```

如需保存不可变 Source Package，必须在人工确认后显式增加 `--commit`；这仍只写入
本目录，不推进任何上游创作阶段。
