# Screenplay Agent 修复计划

基于 AUDIT_REPORT.md（2026-06-20）生成。

---

## 一、P0 — 安全与健壮性问题（必须修复，32项）

### 1.1 路径遍历漏洞（🔴 critical）
**文件**: `core/prompts.py`
**问题**: `load_prompt(name)` 未验证 name 参数，可读取任意目录
**修复**: 添加路径白名单校验，禁止 `../` 和绝对路径
**优先级**: P0 | 预计工时: 15min

### 1.2 基类错误处理（🔴 high）
**文件**: `agents/base.py`
**问题**: Book.get() 不检查 None、is_short_story 空指针、session 无异常处理
**修复**: 添加 None 检查、try-except 包裹 session 操作
**优先级**: P0 | 预计工时: 20min

### 1.3 Outline Agent 类型安全（🔴 high）
**文件**: `agents/outline.py`
**问题**: bible.content[:4000] 未判空、book.chapter_count 无类型断言、LLM JSON 无结构校验
**修复**: 判空保护 + TypedDict + 类型断言
**优先级**: P0 | 预计工时: 30min

### 1.4 Hybrid Retriever 异常处理（🔴 high）
**文件**: `core/hybrid_retriever.py`
**问题**: vs.search / ks.init_fts / ks.keyword_search 均未 try-except
**修复**: 添加异常捕获，失败返回空列表
**优先级**: P0 | 预计工时: 10min

### 1.5 空 rules.txt 文件（🔴 high）
**文件**: `prompts/genres/manhua_rules.txt` `movie_rules.txt` `short_drama_rules.txt` `tv_series_rules.txt`
**问题**: 4 个文件为空，导致 genre rules prompt 完全不可用
**修复**: 填充基本规则内容（或删除以 fallback 到通用规则）
**优先级**: P0 | 预计工时: 40min

### 1.6 Pipeline 硬编码（🟡 medium）
**文件**: `run_pipeline.py`
**问题**: BOOK_ID=6 硬编码、BOOK_TITLE='神农架历险记' 硬编码
**修复**: 提取为配置或环境变量
**优先级**: P0 | 预计工时: 15min

### 1.7 reader/analysis.txt JSON 格式问题
**文件**: `prompts/reader/analysis.txt`
**问题**: 双花括号导致 output JSON 非法
**修复**: 修正转义
**优先级**: P0 | 预计工时: 10min

---

## 二、P1 — 系统缺陷（建议修复，355项）

### 2.1 JSON 解析容错（高频问题）
**涉及文件**: `agents/bible.py`, `agents/reader.py`, `agents/outline.py`, `agents/qa.py`, `agents/scene_setup.py`, `agents/storyboard.py`
**修复**: 统一使用 safe_json_loads 辅助函数，捕获 json.JSONDecodeError
**优先级**: P1 | 预计工时: 60min

### 2.2 数据库异常处理
**涉及文件**: `agents/base.py`, `agents/portrait.py`, `agents/portrait_base.py`, `agents/portrait_stages.py`, `agents/reader.py`, `agents/rewrite.py`, `agents/scene_setup.py`, `agents/scriptwriter.py`
**修复**: 所有 session.query/commit 加 try-except，失败回滚
**优先级**: P1 | 预计工时: 45min

### 2.3 LLM 调用异常处理
**涉及文件**: 所有 agent 文件
**问题**: call_llm_json 调用无网络异常重试、无超时保护
**修复**: 在 `core/llm.py` 层增加重试和超时，agent 层增加顶层 try-except
**优先级**: P1 | 预计工时: 60min

### 2.4 路径安全（文件写入）
**涉及文件**: `agents/adapter.py`, `agents/bible.py`, `agents/outline.py`, `agents/qa.py`, `agents/rewrite.py`, `agents/scriptwriter.py`, `agents/storyboard.py`, `agents/prompt_synthesizer.py`
**问题**: book.title 直接用于文件路径，可包含 `../`
**修复**: 统一使用安全文件名函数（sanitize + 校验）
**优先级**: P1 | 预计工时: 30min

### 2.5 魔术数字常量化
**涉及文件**: 全部
**问题**: 3000, 6000, 15000, 5000 等截断长度散落各处
**修复**: 提取为模块级常量或配置项
**优先级**: P1 | 预计工时: 30min

### 2.6 print → logging 替换
**涉及文件**: 全部 agent 文件、core 文件
**问题**: 均使用 print 输出调试信息
**修复**: 替换为 logging，配置日志级别
**优先级**: P1 | 预计工时: 30min

### 2.7 session 管理混乱
**涉及文件**: `agents/bible.py`, `agents/reader.py`
**问题**: 混用 self.session 和参数 session，可能导致连接泄漏
**修复**: 统一使用参数 session，移除 self.session 备选
**优先级**: P1 | 预计工时: 15min

### 2.8 Prompt 双花括号问题
**涉及文件**: `prompts/reader/analysis.txt`, `prompts/storyboard/scene_split.txt`
**问题**: 模板中 `{` 未转义为 `{{`
**修复**: 修正转义或更改模板变量语法
**优先级**: P1 | 预计工时: 10min

### 2.9 prompt 变量缺失
**涉及文件**: `prompts/genres/manhua_adapt.txt`, `prompts/portrait/base_profile.txt`
**问题**: 使用的变量未在调用方传入
**修复**: 同步调用方代码补充变量，或从 prompt 中移除
**优先级**: P1 | 预计工时: 20min

---

## 三、P2 — 架构优化与代码改进（140项）

### 3.1 数据模型改进
**文件**: `models/*.py`
**问题**: 无外键约束、JSON 存 Text 列、String 无长度限制、datetime.now 计算时机错误、status 用字符串而非枚举
**修复**: 添加 ForeignKey、JSON 类型、String(255)、default=datetime.utcnow、枚举
**优先级**: P2 | 预计工时: 60min

### 3.2 测试框架搭建
**问题**: 全项目零测试
**修复**: pytest + pytest-cov，先为核心模块（llm、vector_search、ingest）编写单元测试
**优先级**: P2 | 预计工时: 120min

### 3.3 依赖注入
**问题**: Agent 内部直接实例化 LLM 客户端，耦合度高
**修复**: LLM 客户端通过构造函数传入，便于 Mock
**优先级**: P2 | 预计工时: 60min

### 3.4 Repository 层
**问题**: Agent 直接操作 SQLAlchemy 模型，耦合数据库 Schema
**修复**: 新增 `repositories/` 目录，封装 CRUD 操作
**优先级**: P2 | 预计工时: 120min

### 3.5 Agent 接口标准化
**问题**: Agent 无统一接口，run 方法签名不一致
**修复**: 定义 BaseAgent 抽象接口（book_id, session, params → result）
**优先级**: P2 | 预计工时: 30min

### 3.6 CLI 命令补全和验证
**文件**: `cli.py`
**问题**: portrait 命令未实现、缺少输入验证、无全局选项
**修复**: 补全 portrait 实现，添加参数校验
**优先级**: P2 | 预计工时: 30min

---

## 四、执行计划

### Phase 1（2h）— P0 安全与健壮性
1. `core/prompts.py` — 路径遍历漏洞修复
2. `agents/base.py` — 基类错误处理增强
3. `agents/outline.py` — 类型安全修复
4. `core/hybrid_retriever.py` — 异常捕获
5. 4 个空 rules.txt — 填充或删除
6. `run_pipeline.py` — 硬编码消除
7. `prompts/reader/analysis.txt` — 双花括号修复

### Phase 2（3h）— P1 系统缺陷
1. 统一 `safe_json_loads` 辅助函数 ✅ 14个文件替换完成
2. 数据库操作异常处理（全部 agent） ✅ 6个agent添加try/except
3. LLM 调用重试增强（core/llm.py已有retries=3）
4. 路径安全（文件写入） ✅ prompt_synthesizer + config.output_path
5. 魔术数字常量化 ✅ 6个文件替换为config常量
6. print → logging 替换 ✅ 全项目清零
7. session 管理统一 ✅ 统一使用with self.session() as s模式
8. Prompt 模板修复 ✅ 双花括号修复 + genres/base.py模板异常保护

### Phase 3（5h）— P2 架构优化
1. 数据模型增强
2. 测试框架搭建（pytest）
3. 依赖注入改造
4. Repository 层
5. Agent 接口标准化
6. CLI 命令补全

### 不纳入本次修复
- 测试覆盖（P2，工期长，另开任务）
- 配置加密（需外部工具）
- 完整的 Repository 层重构（P2，需设计评审）
