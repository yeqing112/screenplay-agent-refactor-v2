# screenplay-agent-refactor-v2 功能变更说明

> 最近一次版本（基于 commit `1e2367d init: screenplay-agent-refactor-v2 初始提交`）以来的所有功能改动。
> 编写时间：2026-08-20
> 适用对象：接手开发的同事

---

## 一、变更概览

| 类别 | 文件数 | 新增行数 | 说明 |
|------|--------|----------|------|
| Agent 层 | 7 | +1,292 | 读取、圣经、改写、编剧、人物质检等 |
| API 层 | 1 | +435 | 新增 6 个角色管理端点 |
| Core 库 | 5+11 新 | +696/+3,000+ | 短剧库、约束引擎、校验器、别名解析增强 |
| 前端 | 11 改+2 新 | +154/+486 | 人物质检面板、章节查看器、一键生成按钮 |
| Prompt | 3 | +187 | 别名解析增强、分镜提示词增强 |
| 合计 | 60+ 文件 | ~7,300+ 行 | |

---

## 二、核心功能改动详解

### 2.1 短剧专用库系统 (`core/short_drama_library.py`)

**新增文件，519 行。** 提供 10 个结构化知识库，注入到所有 LLM prompt 中：

| 库名 | 说明 |
|------|------|
| `EPISODE_BEAT_ENGINE` | 5 拍节拍引擎：hook → setup → friction → spike → button |
| `EPISODE_EMOTION_NODES` | 8 个情绪时间节点 |
| `HOOK_LIBRARY` | 4 类钩子：开场钩/片尾钩/中段钩/系列钩 |
| `SHORT_DRAMA_CONFLICT_PATTERNS` | 8 种冲突模式：身份反转、公开羞辱、复仇重生等 |
| `SHORT_DRAMA_DIALOGUE_RULES` | 黄金法则 + 6 种台词类型 + 禁忌模式 |
| `SHORT_DRAMA_VISUAL_GRAMMAR` | 构图、镜头时长、表情优先级、AI 一致性 |
| `SHORT_DRAMA_PACING_TEMPLATES` | 4 种节奏模板：60s/90s/120s/180s |
| `SERIES_ARCHITECTURE_LIBRARY` | 按阶段的剧集结构 |
| `COMMON_PITFALLS` | 8 个致命陷阱及修复方案 |
| `EMOTION_CHECKPOINT_LIBRARY` | 5 种情绪检查点：虐/满足/甜/燃/悬疑 |

**用途：** 在 `api/server.py` 的 `_build_prompt_compiler_diagnostics()` 中注入到分镜 prompt。

### 2.2 约束引擎 (`core/constraint_engine.py`)

**新增文件，664 行。** 自动生成 + 注册 + 校验约束规则：

- 7 个自动生成器：镜头运动、情绪、镜头目的、速度、时长、短剧规则、格式
- `ConstraintRegistry`：约束注册表，支持按 ID 查询
- `ConstraintValidator`：校验器，支持 Levenshtein 模糊匹配修复枚举值
- `Violation` 数据结构：记录违规字段、严重级别、修复策略

### 2.3 校验器体系 (`core/validators/`)

**新增 7 个文件，~1,000 行：**

| 文件 | 功能 |
|------|------|
| `programmatic_repair.py` | 确定性修复引擎：枚举模糊匹配、范围钳位、禁忌值替换 |
| `screenplay_validator.py` | 剧本校验：冲突类型枚举、台词长度、场景结构、致命陷阱、钩子检查 |
| `storyboard_validator.py` | 分镜校验：镜头级约束、场景级检查（开场必须是钩子、结尾必须有悬念） |
| `prompt_validator.py` | 提示词校验：术语一致性、情绪动作、短剧节奏元素 |
| `violation_logger.py` | 违规日志：持久化到 `AgentViolationLog` 表 |
| `violation_repair_orchestrator.py` | 修复调度器：3 级调度（程序化 → 混合 → LLM），重校验循环 |

### 2.4 人物画像质检 (`core/portrait_qa.py`)

**新增文件，322 行。** 解决「一人多角」「性别混乱」问题：

**5 项检测：**
1. **性别缺失**：gender 为空或"人物"
2. **孤立 profile**：仅出场 1 章、无关系链接、无外貌描述
3. **疑似重复**：外貌相似度 > 30% + 章节互补（无重叠）
4. **性别冲突**：同一 canonical 下 gender 不一致
5. **合并操作**：`merge_characters()` 合并 aliases、fragments、stages

### 2.5 别名解析增强 (`core/alias_resolver.py`)

**修改文件，+91 行。** 关键改动：

1. **新增跨章数据聚合**（91-111 行）：从所有章节收集 `appearance_fragments` 和 `relationships`
2. **Prompt 增强**（201-273 行）：每个角色现在传入 gender、外貌片段（去重，最多 8 条）、人物关系（最多 6 条）
3. **输出格式扩展**：LLM 现在返回 `pending_confirm`（中置信度合并）和 `gender_conflicts`
4. **中置信度合并处理**（133-149 行）：自动加入合并组但标记「需确认」

**对应 Prompt 改动** (`prompts/alias_resolve.txt`)：
- 新增「外貌比对规则」「关系网络规则」「性别一致性规则」
- 输出格式增加 `pending_confirm` 和 `gender_conflicts`

### 2.6 剧本生成增强 (`agents/scriptwriter.py`)

**修改文件，+547 行。** 关键改动：

- **逐场景生成** (`_generate_scenes_sequentially`)：将剧本拆分为场景依次生成
- **场景状态传递** (`SceneState`)：场景间传递角色状态、道具状态
- **场景完成校验** (`_validate_scene_completion`)：确保每个场景结构完整
- **场景结尾续写** (`_continue_scene_ending`)：处理跨场景续写
- **结构化编译** (`_compile_with_structure`)：使用结构化生成框架

### 2.7 改写增强 (`agents/rewrite.py`)

**修改文件，+227 行。**

- **回归保护** (`_calculate_similarity`)：基于字符 n-gram 的相似度计算，防止改写偏离
- **多轮改写** (`run_perfect`)：目标 QA 评分 9+ 的迭代改写
- **台词精炼** (`_refine_dialogue`)：专门优化对话质量

### 2.8 结构化场景状态 (`core/production_skill.py`)

**修改文件，+519 行。**

- **CharacterState / PropState / SceneState** 数据结构：结构化传递场景状态
- **性格行为护栏**：内向/神秘/疲惫/古怪性格的行为约束
- **性别推断**：从名字后缀推断角色性别
- **大纲状态推断**：可见/隐藏/过渡状态

### 2.9 修复集成 (`core/repair/integration.py`)

**修改文件，+84 行。** 原为 no-op 的 `apply_structural_repair_directives()` 现已实现：

- `CONSTRAINT_FIX`：场景开头/结尾修复
- `PROP_FIX`：道具修复
- `CHARACTER_FIX`：角色修复

---

## 三、新增 API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| `GET` | `/api/books/{id}/chapters` | 章节列表（含原文） |
| `GET` | `/api/books/{id}/chapters/{ch_id}` | 单章详情 |
| `GET` | `/api/books/{id}/characters` | 角色列表 |
| `GET` | `/api/books/{id}/characters/qa` | 人物画像质检报告 |
| `POST` | `/api/books/{id}/characters/merge` | 合并两个角色 |
| `POST` | `/api/books/{id}/characters/resolve-aliases` | 重新归并别名 |
| `PATCH` | `/api/books/{id}/characters/{ch_id}` | 修改角色属性 |
| `GET` | `/api/books/{id}/characters/{ch_id}/appearance` | 外貌片段详情 |

---

## 四、新增前端组件

### 4.1 CharacterQAPanel (`web/src/components/CharacterQAPanel.tsx`)

**新增文件，344 行。** 侧边栏「人物质检」入口：

- 显示所有角色列表（性别、身份、aliases）
- 性别冲突列表 → 用户选择正确性别
- 疑似重复角色 → 用户点击「合并」
- 「重新归并别名」按钮 → 触发 alias resolver
- 「重新检测」按钮 → 刷新 QA 报告

### 4.2 ChapterViewer (`web/src/components/ChapterViewer.tsx`)

**新增文件，142 行。** 集成在「内容准备」section 底部：

- 章节标签切换
- 原文阅读器（serif 字体，60vh 高度滚动）
- 章节摘要展示
- 前后翻页导航

### 4.3 一键生成按钮

**修改 `ProductWorkspaceScriptsSection.tsx` + `ProductWorkspaceStoryboardSection.tsx`：**

- 剧本工作台空状态显示「一键生成剧本」按钮
- 镜头工作台空状态显示「一键生成分镜」按钮
- 按钮触发后台管线任务，带 loading 状态

---

## 五、管线流程改动

在 `api/server.py` 的 `run_script_pipeline()` 中：

1. **Portrait 前自动运行别名归并**：`resolve_aliases(book_id, session)`
2. **Portrait 后自动运行质检**：`run_portrait_qa(book_id, s)`
3. 性别冲突和高置信度合并候选作为 warning 输出到前端

---

## 六、数据库改动

### 新增表

```sql
-- 违规日志表 (models/violation_log.py)
CREATE TABLE agent_violation_logs (
    id INTEGER PRIMARY KEY,
    agent_type VARCHAR(50),     -- 'storyboard', 'screenplay', 'prompt'
    book_id INTEGER,
    episode INTEGER,
    violation_id VARCHAR(100),  -- 约束 ID
    field VARCHAR(200),         -- 违规字段路径
    severity VARCHAR(20),       -- 'error', 'warning', 'info'
    repair_strategy VARCHAR(50),-- 'programmatic', 'hybrid', 'llm'
    repair_result TEXT,         -- JSON 修复结果
    regression BOOLEAN DEFAULT 0,
    created_at DATETIME
);
```

### 无 schema 变更

所有现有表结构不变。新功能使用已有字段或 JSON 字段存储。

---

## 七、配置改动

| 文件 | 改动 |
|------|------|
| `config.py` | `LLM_MAX_TOKENS` 从 8192 → 24000 |
| `web/vite.config.ts` | API proxy 目标端口从 18765 → 8765 |

---

## 八、已知问题

### 需要修复（生产就绪前）

| 严重度 | 问题 | 位置 |
|--------|------|------|
| CRITICAL | CORS 允许所有来源 | `server.py:49-55` |
| CRITICAL | 无认证/授权 | 全局 |
| CRITICAL | 文件上传路径穿越 | `server.py:562` |
| CRITICAL | 无文件类型/大小限制 | `server.py:554-565` |
| HIGH | `return {...}, 404` 实际返回 200 | 多处端点 |
| HIGH | 无外键约束 | 所有 model |
| HIGH | 无数据库索引 | `book_id` 查询 |
| MEDIUM | 内存任务状态无 TTL | `_pipeline_tasks` 等 |
| MEDIUM | SQLite 并发写入限制 | 生产环境瓶颈 |

### 功能待完善

1. 分镜尚未集成约束引擎的完整校验循环
2. 别名解析器对「完全不同的名字但同一人」的场景识别能力有限
3. 人物画像 stage 分割未触发（需要角色出场 ≥5 章 + ≥3 条外貌片段）
4. 前端无全局 ErrorBoundary
5. 无 `/health` 健康检查端点

---

## 九、测试文件

根目录有 15+ 个 `test_*.py` 文件，为集成/验收测试。`tests/` 目录有 46 个单元测试文件。

**注意：** 根目录的测试文件是临时测试脚本，不是正式测试套件。部分文件（如 `check_scripts.py`、`verify_buttons.py`）可以在确认不需要后删除。

---

## 十、环境依赖

- **LLM API**：mimo-v2.5 (`https://api.xiaomimimo.com/v1`)，通过 model registry 配置
- **本地 Ollama**：`http://10.126.126.2:11434`（deepseek-r1:14b, gemma4:12b, nomic-embed-text）
- **数据库**：SQLite (`work/db/screenplay.db`)
- **向量库**：ChromaDB（内嵌）
- **前端**：React 18 + TypeScript + Vite

---

## 十一、关键文件速查

| 需要了解 | 文件 |
|----------|------|
| 管线主入口 | `api/server.py:868` (`run_script_pipeline`) |
| 短剧知识库 | `core/short_drama_library.py` |
| 约束引擎 | `core/constraint_engine.py` |
| 校验器 | `core/validators/` (7 个文件) |
| 人物质检 | `core/portrait_qa.py` |
| 别名解析 | `core/alias_resolver.py` |
| 提示词模板 | `prompts/` 目录 |
| 前端入口 | `web/src/App.tsx` |
| 前端工作区 | `web/src/components/ProductWorkspace.tsx` |
| 角色 API | `api/server.py:8194` (characters endpoints) |
