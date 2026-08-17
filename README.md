# Screenplay Agent — AI 驱动的剧本智能生产平台

> 将长篇小说自动转化为竖屏短剧剧本的 AI Agent 系统。支持短剧爽文、古装甜宠等多体裁适配，一键完成从小说导入到分镜生成的完整管线。

---

## 核心能力

- **全自动管线** — 小说导入 → 逐章分析 → 世界观 Bible → 别名解析 → 人物画像 → 改编方案 → 分集大纲 → 剧本写作 → 质检 → 重写闭环 → 分镜生成 → 视觉设定，10+ 步骤端到端自动化
- **多体裁支持** — 内置「竖屏短剧」「漫剧」「电影」「电视剧」四种赛道，参数化配置，新增赛道无需写 Python
- **可视化编辑器** — React 前端提供导演模式（分步骤操作）和原型模式（视频生产管线节点编辑器，React Flow 驱动）
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
├── nodes/                  # DevCanvas 节点引擎
│   ├── handlers/           # 节点处理器
│   ├── registry.py         # 节点注册表
│   └── runner.py           # 节点运行器
├── web/                    # React 前端
│   └── src/
│       ├── components/         # 通用组件
│       │   ├── ProductionMode.tsx  # 导演模式（生产管线主界面）
│       │   ├── Canvas.tsx       # 原型模式画布
│       │   ├── AgentNode.tsx    # Agent 节点组件
│       │   ├── NodePanel.tsx    # 节点面板
│       │   ├── NodeConfigPanel.tsx # 节点配置面板
│       │   ├── PromptSelector.tsx  # 提示词选择器
│       │   ├── ResultRenderer.tsx  # 结果渲染器
│       │   ├── ResultsPanel.tsx    # 结果面板
│       │   ├── HistorySidebar.tsx  # 历史侧边栏
│       │   ├── SearchBar.tsx       # 搜索栏
│       │   └── pipelineLayout.ts   # 管线布局
│       ├── prototyping/      # 原型模式组件
│       │   ├── DirectorMode.tsx    # 原型导演布局
│       │   ├── SceneComposer.tsx   # 视频生产管线
│       │   ├── VisualPanel.tsx     # 视觉资产面板
│       │   ├── mockData.ts         # Mock 数据
│       │   ├── useMockOutputs.ts   # Mock 输出 Hook
│       │   └── useTaskRunner.ts    # 任务运行器 Hook
│       ├── pages/
│       │   ├── ProjectsPage.tsx    # 项目列表
│       │   └── CanvasPage.tsx      # 编辑器主页
│       └── types/                  # TypeScript 类型定义
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
uvicorn api.server:app --host 0.0.0.0 --port 8765
# API 运行于 http://localhost:8765
```

### 前端

```bash
cd web
npm install
npx vite --host
# 前端运行于 http://localhost:5173
```

### 一键开发启动

```bash
./dev.sh
```

自动启动后端 (:8765) 和前端 (:5173)。

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
2. 进入**导演模式**（默认视图）
3. 在「剧本准备」步骤配置参数（体裁、集数），点击「**一键生产完整剧本**」
4. 剧本完成后切换到「**分镜生产**」，选集生成分镜
5. 分镜完成后切换到「**视觉资产**」，生成视觉设定（定妆图、场景、道具、时代色板）
6. 最后「**导出**」汇总所有产出

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

## 原型模式

右上角切换到「**原型**」标签页，体验视频生产管线节点编辑器（React Flow 驱动）。

支持可视化工作流：
- **分镜源节点** — 加载剧本分镜
- **文生图节点** — 将分镜描述转为图像
- **视频生成节点** — 将图像序列转为视频
- **合成器节点** — 组合最终输出

原型组件位于 `web/src/prototyping/` 目录。

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
- **节点编辑器**: React Flow (React Flow v11)
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

- 主要业务逻辑在 `web/src/components/ProductionMode.tsx`
- 原型组件在 `web/src/prototyping/`
- 类型定义在 `web/src/types/`

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
