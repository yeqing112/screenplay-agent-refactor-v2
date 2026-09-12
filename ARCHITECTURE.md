# Screenplay Agent 架构文档

## 项目概述

Screenplay Agent 是一个 AI 驱动的剧本智能生产平台。输入小说文本，经过多级 AI Agent 管线处理，输出：

- 世界观圣经 (World Bible)
- 人物画像 (Character Portrait)
- 改编方案 (Adaptation Plan)
- 分集大纲 (Episode Outline)
- 正式剧本 (Script)
- 质检报告 (QA Report)
- 分镜表 (Storyboard)
- 视觉设定 (Visual Setup)

支持多体裁：短剧爽文、古装甜宠、现代霸总、玄幻仙侠、悬疑。

---

## 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                    用户界面 (UI Layer)                     │
│  ┌────────────────────────────────────────────────────┐  │
│  │ React + Vite + TypeScript + Tailwind CSS           │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │  ProductWorkspace（正式工作台）              │  │  │
│  │  │  项目控制台 → 内容准备 → 改编/人物质检       │  │  │
│  │  │  剧本 → 镜头 → 创作画布 → 资产/任务/导出     │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP (Vite Proxy → :18765)
                       ▼
┌──────────────────────────────────────────────────────────┐
│                  API 服务器 (API Layer)                     │
│  FastAPI (api/server.py) — 端口 18765                     │
│  ┌────────────────────────────────────────────────────┐  │
│  │  /api/pipeline/script        # 剧本管线            │  │
│  │  /api/pipeline/storyboard    # 分镜生成            │  │
│  │  /api/pipeline/visual-setup  # 视觉设定生成         │  │
│  │  /api/pipeline/book/{id}/outputs  # 取产出数据      │  │
│  │  /api/books                  # 项目管理             │  │
│  │  /api/upload                 # 文件上传             │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│                AI Agent 管道 (Agent Layer)                 │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐     │
│  │ingest│→ │ read │→ │bible │→ │port. │→ │adapt │     │
│  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘     │
│     ↓        ↓        ↓         ↓                      │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐     │
│  │ali.  │  │sum.  │  │char  │  │attr. │  │scene │     │
│  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘     │
│     ↓                                                    │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐     │
│  │outl. │→ │scrip │→ │ QA   │→ │stor. │→ │vis.  │     │
│  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘     │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│              数据层 (Data Layer)                          │
│  ┌────────────────────┐  ┌────────────────────┐         │
│  │  SQLite (SQLAlchemy)│  │  ChromaDB (向量索引)│        │
│  │  - books           │  │  - 章节向量          │        │
│  │  - scripts         │  │  - 角色向量          │        │
│  │  - outlines        │  │  - 场景向量          │        │
│  │  - storyboards     │  │                     │        │
│  │  - visuals         │  └────────────────────┘         │
│  └────────────────────┘                                  │
└──────────────────────────────────────────────────────────┘
```

---

## 后端目录 (Python)

```
api/server.py      # FastAPI 服务器，路由注册，后台任务调度
agents/            # AI Agent 模块，每个 Agent 一个文件
  ├── base.py      #   BaseAgent 基类 (LLM 调用、prompt 渲染、输出持久化)
  ├── reader.py    #   逐章分析：角色、情感线
  ├── bible.py     #   世界观 Bible 生成
  ├── portrait_base.py  # 人物画像基础（外貌提取）
  ├── portrait.py       # 人物画像整合
  ├── portrait_stages.py # 分阶段画像生成
  ├── outline.py   #   分集大纲
  ├── scriptwriter.py   # 剧本写作
  ├── adapter.py   #   改编方案
  ├── storyboard.py     # 分镜生成
  ├── qa.py        #   质检
  ├── scene_setup.py    # 视觉设定
  ├── prompt_synthesizer.py # 提示词合成
  └── rewrite.py   #   剧本重写
core/              # 核心基础设施
  ├── llm.py       #   LLM 调用封装（HTTP + 重试 + 节流）
  ├── ingest.py    #   文档导入（TXT/PDF/URL）
  ├── prompts.py   #   提示词模板文件
  ├── vector_search.py  # ChromaDB 向量搜索
  ├── hybrid_retriever.py # 向量+关键词混合检索
  ├── keyword_search.py  # FTS5 全文搜索
  └── alias_resolver.py  # 角色别名解析归并
genres/            # 体裁适配
  ├── __init__.py
  └── base.py      #   体裁基类
models/            # SQLAlchemy ORM 模型
  ├── book.py      #   书本/项目
  ├── script.py    #   剧本
  ├── storyboard.py     # 分镜
  ├── visual.py    #   视觉设定
  ├── character.py #   角色
  ├── bridge.py    #   关系桥接
  └── kv.py        #   KV 存储
nodes/             # Legacy DevCanvas 节点引擎（兼容保留，正式工作台不直接依赖）
  ├── registry.py  #   节点注册中心
  ├── runner.py    #   节点执行器 + 工作流
  └── handlers/    #   各执行节点处理器
config.py          # 配置（环境变量驱动）
cli.py             # CLI 命令行工具
run_audit.py       # 代码审计分析
```

---

## 前端目录 (React/TypeScript)

```
web/
├── src/
│   ├── main.tsx              # 入口
│   ├── App.tsx               # 路由
│   ├── pages/
│   │   ├── ProjectsPage.tsx  # 项目列表页（默认首页）
│   │   └── CanvasPage.tsx    # 项目详情页（正式工作台入口）
│   ├── components/
│   │   ├── ProductWorkspace.tsx               # 正式工作台编排入口
│   │   ├── ProductWorkspaceShell.tsx          # 工作台外壳、导航、项目标题区
│   │   ├── ProductWorkspaceSectionContent.tsx # 工作台分区内容路由
│   │   ├── ProductWorkspace*Section.tsx       # 控制台/内容/剧本/镜头/画布/资产/QA/任务/导出/模型
│   │   ├── productWorkspace*Controller.ts     # 数据、导航、上游状态、资产视图控制器
│   │   └── ResultRenderer.tsx                 # 结构化结果渲染
│   ├── hooks/
│   │   └── useBookOutputs.ts                  # 正式输出加载
│   ├── domain/
│   │   └── bookOutputs.ts                     # 业务输出归一化
│   └── services/
│       └── modelRegistry.ts                   # 模型注册表
├── vite.config.ts            # Vite 配置（含 API proxy）
├── package.json
└── tsconfig.json
```

---

## AI Agent 运行流程

每个 Agent 继承 `BaseAgent`，实现 `run(book_id, ...)` 方法。标准流程：

```
BaseAgent.run(book_id, params)
  ├─ 1. 从 DB 加载书本数据 + 上下文
  ├─ 2. 组装 prompt（使用 prompts/ 下的模板 + 动态上下文注入）
  ├─ 3. 调用 LLM（core/llm.py，带重试和节流）
  ├─ 4. 解析 LLM 输出（JSON/文本）
  ├─ 5. 持久化到 DB 和文件系统（outputs/ 目录）
  └─ 6. 返回结果
```

## 关键约定

1. **Agent 文件名 = pipeline 步骤名**（reader → bible → portrait → adapt → outline → script → check → storyboard）
2. **所有 Agent 返回的数据结构**：每种体裁（genre）有独立格式，通过 genres/ 配置
3. **API 路由前缀**: `/api/pipeline/*` 是管线接口，`/api/books` 是项目管理
4. **输出持久化**: outputs/{book_title}/ 目录存人类可读产物，DB 存结构化数据
5. **配置优先环境变量**: `config.py` 中所有配置先从环境变量读，次从 `.env` 文件

## 启动方式

### 后端
```bash
cd screenplay-agent
source .venv/bin/activate
PYTHONPATH=. python3 api/server.py
# → http://localhost:18765
```

### 前端
```bash
cd screenplay-agent/web
npm install
npx vite --host
# → http://localhost:5175 (API 自动代理到 :18765)
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| OPENAI_API_KEY | LLM API Key | (空) |
| OPENAI_BASE_URL | LLM API Base URL | http://127.0.0.1:11434/v1 |
| LLM_MODEL | 模型名 | deepseek-chat |
| OLLAMA_BASE_URL | Ollama 地址（向量嵌入用） | http://localhost:11434 |
| DATABASE_URL | SQLite 路径 | sqlite:///work/db/screenplay.db |

## 开发注意事项

- `ProductWorkspace.tsx` 是当前唯一项目工作台入口；新增能力应落到对应 `ProductWorkspace*Section.tsx` 或 `productWorkspace*Controller.ts`，避免重新形成巨型单文件。
- 后端 pipeline 是后台异步任务（`BackgroundTasks`），通过轮询 `/api/pipeline/task/{id}` 获取进度
- ChromaDB 用于语义搜索（向量维度 768，nomic-embed-text 模型）
- 多体裁支持通过 `genres/` 目录下的配置文件和 `agents/adapter.py` 中的策略模式实现
- `/api/workflows*`、`/api/nodes*`、`/api/runs*` 属于 Legacy DevCanvas 兼容接口；正式工作台当前不直接依赖，迁移/关停需另行完成历史数据与测试兼容评估。
