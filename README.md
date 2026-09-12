# Screenplay Agent — AI 驱动的剧本智能生产平台

> 将长篇小说自动转化为竖屏短剧剧本的 AI Agent 系统。支持短剧爽文、古装甜宠等多体裁适配，一键完成从小说导入到分镜生成的完整管线。

---

## 核心能力

- **全自动管线** — 小说导入 → 逐章分析 → 世界观 Bible → 别名解析 → 人物画像 → 改编方案 → 分集大纲 → 剧本写作 → 质检 → 重写闭环 → 分镜生成 → 视觉设定，10+ 步骤端到端自动化
- **多体裁支持** — 内置「竖屏短剧」「漫剧」「电影」「电视剧」四种赛道，参数化配置，新增赛道无需写 Python
- **单一正式工作台** — React 前端统一到项目列表 → 正式工作台，覆盖内容准备、改编方向、人物质检、剧本、镜头、创作画布、资产、QA、任务、导出与模型管理
- **断点续跑** — 已完成的步骤自动跳过，1200+ 章节批量处理无压力
- **本地优先** — 所有数据存储于本地 SQLite + ChromaDB，仅 LLM 调用外部 API

---

## 目录结构

```
screenplay-agent/
├── api/                    # FastAPI 后端
│   ├── routes/             # API 路由
│   └── server.py           # 应用入口 + pipeline 编排端点
├── agents/                 # AI Agent 模块
│   ├── base.py             # Agent 基类
│   ├── reader.py           # 逐章分析（摘要 + 角色提取）
│   ├── bible.py            # 世界观 Bible 生成
│   ├── alias_resolver.py   # 别名解析（迁移至 core/，agents/ 保留引用）
│   ├── portrait.py         # 人物画像（含分层生图提示词）
│   ├── portrait_base.py    # 画像基础功能
│   ├── portrait_stages.py  # 角色阶段拆分
│   ├── adapter.py          # 改编方案生成
│   ├── outline.py          # 分集大纲
│   ├── scriptwriter.py     # 剧本写作
│   ├── qa.py               # 质检
│   ├── rewrite.py          # 剧本重写（QA 反馈闭环）
│   ├── storyboard.py       # 分镜生成
│   ├── scene_setup.py      # 视觉设定（定妆/场景/道具/时代）
│   └── prompt_synthesizer.py # 提示词合成
├── core/                   # 核心基础设施
│   ├── llm.py              # LLM 调用封装（DeepSeek / OpenAI-compatible）
│   ├── ingest.py           # 文档导入（TXT/Markdown）
│   ├── prompts.py          # 提示词模板加载
│   ├── vector_search.py    # 向量搜索（ChromaDB）
│   ├── hybrid_retriever.py # 混合检索（向量 + 关键词）
│   ├── alias_resolver.py   # 别名解析引擎
│   └── keyword_search.py   # 关键词搜索
├── genres/                 # 体裁适配
│   └── base.py             # 赛道基础类
├── models/                 # SQLAlchemy ORM 模型
│   ├── base.py             # 模型基类
│   ├── book.py             # 书籍
│   ├── character.py        # 角色
│   ├── script.py           # 剧本
│   ├── storyboard.py       # 分镜
│   ├── visual.py           # 视觉资产
│   ├── bridge.py           # 关联表
│   └── kv.py               # 键值存储
├── nodes/                  # Legacy DevCanvas 节点引擎（兼容保留，正式工作台不直接依赖）
│   ├── handlers/           # 节点处理器
│   ├── registry.py         # 节点注册表
│   └── runner.py           # 节点运行器
├── web/                    # React 前端
│   └── src/
│       ├── components/         # 正式工作台组件
│       │   ├── ProductWorkspace.tsx              # 单一正式工作台编排入口
│       │   ├── ProductWorkspaceShell.tsx         # 工作台外壳与导航
│       │   ├── ProductWorkspaceSectionContent.tsx # 分区内容路由
│       │   ├── ProductWorkspace*Section.tsx      # 控制台/内容/剧本/镜头/资产/QA/任务/导出等分区
│       │   └── productWorkspace*Controller.ts    # 工作台数据、导航、资产、上游状态控制器
│       ├── pages/
│       │   ├── ProjectsPage.tsx    # 项目列表
│       │   └── CanvasPage.tsx      # 正式工作台入口
│       ├── hooks/                  # 正式工作台与业务 Hook
│       ├── services/               # 模型注册表、API 服务
│       └── domain/                 # 业务输出归一化
├── prompts/                # Prompt 模板（.txt 文件）
├── scripts/                # 辅助脚本
├── tools/                  # 开发工具
├── tests/                  # 测试
├── docs/                   # 文档
├── outputs/                # 输出目录（按小说命名）
├── work/                   # 工作目录
│   ├── books/              # 原始小说文件
│   ├── indexes/            # ChromaDB 向量索引
│   └── db/                 # SQLite 数据库
├── config.py               # 配置
├── cli.py                  # 命令行工具
├── run_audit.py            # 代码审计
├── dev.sh                  # 开发启动脚本
├── alembic/                # 数据库迁移
├── requirements.txt        # Python 依赖
└── .env                    # 环境变量
```

---

## 快速开始

### 后端

```bash
cd ~/projects/screenplay-agent

# Python 3.11+
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Key

# 启动 API 服务器
uvicorn api.server:app --host 0.0.0.0 --port 18765
# API 运行于 http://localhost:18765
```

### 前端

```bash
cd web
npm install
npx vite --host --port 5175
# 前端运行于 http://localhost:5175
```

### 一键开发启动

```bash
./dev.sh
```

自动启动后端 (:18765) 和前端 (:5175)。

### 生产发布门禁

发布前使用统一入口运行配置、样本、可拍性、Prompt 质量和完整回归检查：

```bash
npm run gate:production
```

该命令 fail-closed：任一步骤失败都会返回非零，并在 `artifacts/production-release-gate-*.json|md` 生成完整结果。发布门禁要求 `DEPLOYMENT_ENV=production` 或 `staging`；开发环境中的“跳过生产配置检查”不会被视为通过。

---

## 真实 LLM 灰度（受保护）

真实 MiMo 灰度不会随 push/PR 自动执行，也不会进入 Required CI。推荐使用 GitHub Actions 的 `Storyboard real LLM gray` 工作流：

1. 在仓库 `Settings → Environments` 创建环境 `real-llm-gray`，添加 Secret `MIMO_API_KEY`。
2. 手动运行 workflow 时，将确认输入填写为 `RUN_REAL_LLM_GRAY`；可按需修改 `targets` 和 `shot_count`。
3. 工作流先创建证据完整的临时样本，再通过 clone-only 验证脚本调用模型；结束后自动回滚并清理临时克隆。
4. JSON/Markdown 灰度报告会作为 workflow artifact 上传，不创建正式 Prompt Version、图片或视频任务。

定时运行默认关闭。只有显式设置仓库变量 `ENABLE_REAL_LLM_NIGHTLY=true` 才会启用；模型地址和模型名可通过 `MIMO_BASE_URL`、`MIMO_MODEL` 仓库变量覆盖，默认分别为 MiMo 官方兼容地址和 `mimo-v2.5`。

本地安全路径：

```bash
npm run seed:storyboard-gray-sample
STORYBOARD_REAL_LLM_GRAY_MOCK=1 \
STORYBOARD_REAL_LLM_GRAY_TARGETS=990301:1:1,990301:1:2,990301:1:3 \
npm run validate:storyboard-real-llm-gray
```

---

## 配置

主要环境变量（详见 `.env` / `.env.example`）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENAI_API_KEY` | API Key | — |
| `OPENAI_BASE_URL` | API 地址 | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | LLM 模型 | `deepseek-v4-flash` |
| `LLM_TEMPERATURE` | 生成温度 | `0.3` |
| `LLM_MAX_TOKENS` | 最大 Token 数 | `65536` |
| `LLM_RPM` | 每分钟请求数上限 | `10` |
| `LLM_TPM` | 每分钟 Token 数上限 | `200000` |
| `OLLAMA_BASE_URL` | Ollama 地址 | `http://localhost:11434` |
| `EMBEDDING_MODEL` | 向量嵌入模型 | `nomic-embed-text` |
| `EMBEDDING_DIM` | 嵌入向量维度 | `768` |
| `CHROMA_PERSIST_DIR` | ChromaDB 持久化目录 | `./work/indexes/chroma` |
| `DATABASE_URL` | 数据库连接 | `sqlite:///./work/db/screenplay.db` |

---

## 管线完整流程

```
                    ┌──────────┐
                    │  导入小说  │  Ingest
                    └────┬─────┘
                         ▼
                    ┌──────────┐
                    │  逐章分析  │  Reader
                    └────┬─────┘
                         ▼
              ┌─────────────────────┐
              │    世界观 Bible      │  Bible (人物数据库 + 事件年表)
              └────────┬────────────┘
                       ▼
              ┌─────────────────────┐
              │     别名解析         │  Alias Resolve (角色去重合并)
              └────────┬────────────┘
                       ▼
              ┌─────────────────────┐
              │     人物画像         │  Portrait (含分层生图提示词)
              └────────┬────────────┘
                       ▼
              ┌─────────────────────┐
              │     改编方案         │  Adapter (体裁适配)
              └────────┬────────────┘
                       ▼
              ┌─────────────────────┐
              │     分集大纲         │  Outline
              └────────┬────────────┘
                       ▼
              ┌─────────────────────┐
              │     视觉设定         │  Scene Setup (定妆/场景/道具/时代)
              └────────┬────────────┘
                       ▼
              ┌─────────────────────┐
              │     剧本写作         │  Scriptwriter
              └────────┬────────────┘
                       ▼
              ┌─────────────────────┐
              │       质检           │  QA
              └────────┬────────────┘
                  ╱          ╲
                 ✅           ❌
               通过           重写 + 再质检 (Rewrite 反馈闭环)
                  │
                  ▼
              ┌─────────────────────┐
              │     分镜生成         │  Storyboard
              └─────────────────────┘
```

### 在 UI 中的操作流程

1. 从**项目列表**选择一个书（或导入新书）
2. 进入**正式工作台**（唯一项目工作入口）
3. 在「内容准备」「改编方向」确认书稿、体裁、集数与上游产出
4. 在「剧本工作台」生成、审阅、修复和回滚剧本版本
5. 在「镜头工作台」生成分镜、编译/锁定提示词并提交验收记录
6. 在「创作画布」「资产中心」「任务中心」串联图片、视频、参考图与长任务回收
7. 在「QA 修复」「导出中心」完成质量闭环与交付汇总

---

## CLI 使用

```bash
# 完整流程（一键）
python cli.py pipeline your_novel.txt --episodes 30

# 分步执行
python cli.py ingest your_novel.txt              # 导入小说
python cli.py read 1                              # 逐章分析
python cli.py read 1 --start 50 --end 100         # 只分析第 50-100 章
python cli.py bible 1                             # 生成小说圣经
python cli.py adapt 1 --genre short_drama         # 生成改编方案
python cli.py portrait 1                          # 角色画像
python cli.py outline 1                           # 分集大纲
python cli.py scene-setup 1                       # 视觉设定
python cli.py script 1 -e 1 -g short_drama        # 生成第 1 集剧本
python cli.py check 1 -e 1                        # 质检第 1 集
python cli.py rewrite 1 -e 1                      # 重写第 1 集剧本
python cli.py storyboard 1 -e 1                   # 生成第 1 集分镜
python cli.py genres                              # 查看可用赛道
python cli.py status                              # 查看处理状态
```

---

## 输出目录结构

```
outputs/{小说名称}/
├── 原始小说.txt                      # 导入的小说原文
├── bible.md                          # 人物数据库 + 事件年表
├── short_drama_改编方案.md            # 竖屏短剧改编方案
├── analysis/                         # 阅读分析阶段
│   ├── 角色汇总.csv                   # 角色与别名表
│   ├── 外貌片段.json                  # 外貌描写摘录
│   └── 剧情摘要.md                    # 每章摘要
├── portraits/                        # 人物画像
│   ├── 角色画像.json
│   ├── 角色画像.md
│   └── 生图提示词.txt
├── outlines/                         # 分集大纲
│   └── 大纲.md
├── scripts/                          # 剧本
│   ├── 第01集脚本.md
│   └── ...
└── qa/                               # 质检报告
    └── 质检报告.md
```

---

## 支持的书稿格式

| 格式 | 说明 |
|------|------|
| TXT | 自动按章节目录检测拆分 |
| Markdown | 完整 Markdown 支持 |

---

## 赛道（Genre）

| 赛道 | 说明 | 单集时长 | 集数 |
|------|------|---------|------|
| `short_drama` | 竖屏短剧 | 60-120 秒 | 10-60 集 |
| `manhua` | 漫剧（动态漫画） | 2-5 分钟 | 20-100 集 |
| `movie` | 电影 | 90-120 分钟 | 单片或三部曲 |
| `tv_series` | 电视剧 | 30-45 分钟 | 20-60 集 |

赛道参数通过 JSON 配置化，新增赛道无需写 Python 代码。

---

## 正式工作台模块

正式工作台是当前唯一用户工作入口，侧栏模块包括：

- **项目控制台**：项目状态、生产进度、上游缺口与继续动作。
- **内容准备 / 改编方向 / 人物质检**：书稿、体裁、角色与改编输入治理。
- **剧本工作台 / QA 修复**：剧本生成、质检、人工修复、diff 预览、应用修复与版本回滚。
- **镜头工作台 / 创作画布**：分镜生成、提示词编译与锁定、图片/视频创作链路。
- **资产中心 / 任务中心 / 导出中心 / 模型管理**：视觉资产、长任务恢复、交付导出与模型配置。

历史旧版生产、创作沙盘、高级编排和产品原型 Demo 已不再作为用户入口或新增功能承载面。

---

## 技术栈

### 后端
- **运行时**: Python 3.11
- **框架**: FastAPI (Uvicorn)
- **ORM**: SQLAlchemy 2.0 + Alembic 迁移
- **数据库**: SQLite (本地存储)
- **向量数据库**: ChromaDB (本地持久化)
- **LLM API**: DeepSeek (OpenAI-compatible)
- **向量嵌入**: Nomic Embed Text (Ollama 本地部署)
- **CLI**: Typer + Rich

### 前端
- **框架**: React 18 + TypeScript
- **构建**: Vite 5
- **UI 组件库**: Tailwind CSS + Lucide React Icons
- **创作画布**: React Flow (React Flow v11)，作为正式工作台内的一级模块
- **状态管理**: React Hooks（无额外状态库）

### AI
- **LLM**: DeepSeek v4 Flash（默认）
- **向量模型**: nomic-embed-text（Ollama）

---

## 开发指引

### 后端

- Agent 代码在 `agents/` 目录下，每个 Agent 继承 `base.py` 的 `BaseAgent`
- 核心基础设施在 `core/` 目录
- Prompt 模板作为 `.txt` 文件存放在 `prompts/`，修改 Prompt 无需改代码
- 数据库模型在 `models/`，Schema 变更通过 Alembic 迁移追踪
- 配置项集中在 `config.py`

### 前端

- 项目入口为 `web/src/pages/ProjectsPage.tsx` → `web/src/pages/CanvasPage.tsx`
- 正式工作台编排入口为 `web/src/components/ProductWorkspace.tsx`
- 分区 UI 位于 `web/src/components/ProductWorkspace*Section.tsx`
- 工作台数据、导航、资产和上游状态控制器位于 `web/src/components/productWorkspace*Controller.ts`
- 业务输出归一化位于 `web/src/domain/`，模型注册表位于 `web/src/services/`

### QA 反馈闭环

剧本经过质检（QA Agent）评分，不达标则进入重写（Rewrite Agent）→ 再质检循环，直到质量达标或达到最大轮次。

### 数据库迁移

```bash
alembic revision --autogenerate -m "描述"
alembic upgrade head
```

---

## 特性一览

- ✅ **Prompt 模板化** — 所有 prompt 存为 `.txt` 文件，改 prompt 不动代码
- ✅ **Genre 配置化** — 赛道参数通过 JSON 配置，新增赛道无需写 Python
- ✅ **断点续跑** — 已分析的章节不会重复处理
- ✅ **1200+ 章节支持** — 批量处理，增量索引
- ✅ **本地运行** — 所有数据存本地，LLM 仅调 API
- ✅ **别名解析** — 自动合并角色别名（母亲/我娘、老陈/陈二蛋他爹）
- ✅ **分层生图提示词** — 角色画像包含各年龄阶段/场景的视觉提示词
- ✅ **Appearance 碎片管理** — 基于外貌摘录生成画像，未出场角色不虚构
- ✅ **Alembic 迁移** — 数据库 Schema 变更可追踪
- ✅ **A2A 剧本质检闭环** — 支持 AI Agent 间的剧本 QA → 修复 → 验证编排
