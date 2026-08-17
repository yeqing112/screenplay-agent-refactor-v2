# Screenplay Agent 全面审计报告

- **生成时间**: 2026-06-20 12:54:47
- **审计模型**: deepseek-v4-flash
- **源文件**: 36 | **Prompt 文件**: 31

## 摘要

| 维度 | 综合评分 |
|------|---------|
| 📝 代码质量 (35 文件) | **6.1/10** |
| 📋 提示词质量 (30 文件) | **6.2/10** |
| 🏗️ 架构设计 | **6/10** |

## Top 严重问题

1. 🔴 **core/hybrid_retriever.py** [error_handling] 所有外部调用（vs.search, ks.init_fts, ks.keyword_search）均未捕获异常，可能导致未处理的崩溃。
2. 🔴 **core/hybrid_retriever.py** [error_handling] 未对输入参数（如 query, where）进行合法性校验，空查询或无效 where 可能引发意外错误。
3. 🔴 **core/prompts.py** [security] 严重路径遍历漏洞：`name` 参数未做检查，可包含 `../` 导致读取任意目录下 `.txt` 文件，如 `load_prompt('../../etc/passwd')` 可读取 `prompts/../../etc/passwd.txt`。
4. 🔴 **agents/base.py** [error_handling] 数据库操作未捕获异常，如 get 可能抛出 NoResultFound、MultipleResultsFound 或数据库连接错误。
5. 🔴 **agents/base.py** [error_handling] is_short_story 属性中 b 可能为 None，访问 b.chapter_count 会抛出 AttributeError。
6. 🔴 **agents/base.py** [error_handling] session 上下文管理器未处理 Session 初始化或查询异常。
7. 🔴 **agents/base.py** [error_handling] run 方法未定义任何异常处理，子类实现可能抛出未捕获异常。
8. 🔴 **agents/outline.py** [type_safety] episodes 和 fixed_sliots 的元素是字典，但缺少类型注解，且字段类型（如 characters 期望 list 但可能为 None）未校验。
9. 🔴 **agents/outline.py** [type_safety] bible.content[:4000] 当 content 为 None 时会抛出 TypeError。
10. 🔴 **agents/outline.py** [type_safety] book.chapter_count 未验证类型，可能为字符串或其他导致计算错误。

---
## A. 代码质量审查

| 文件 | LOC | 错误处理 | 类型安全 | 架构 | 安全 | 可维护 | 总分 |
|------|-----|---------|---------|------|------|--------|------|
| agents/adapter.py | 56 | 5 | 6 | 7 | 6 | 6 | **6** |
| agents/base.py | 42 | 3 | 4 | 6 | 7 | 5 | **5** |
| agents/bible.py | 180 | 4 | 6 | 5 | 7 | 5 | **5** |
| agents/outline.py | 421 | 4 | 3 | 5 | 7 | 4 | **6** |
| agents/portrait.py | 251 | 5 | 7 | 6 | 9 | 7 | **7** |
| agents/portrait_base.py | 214 | 4 | 6 | 7 | 7 | 6 | **6** |
| agents/portrait_stages.py | 102 | 5 | 6 | 6 | 7 | 5 | **6** |
| agents/prompt_synthesizer.py | 216 | 5 | 4 | 6 | 4 | 5 | **5** |
| agents/qa.py | 107 | 4 | 6 | 6 | 8 | 5 | **6** |
| agents/reader.py | 253 | 6 | 5 | 7 | 8 | 6 | **7** |
| agents/rewrite.py | 38 | 5 | 7 | 6 | 6 | 5 | **6** |
| agents/scene_setup.py | 1148 | 6 | 5 | 7 | 8 | 6 | **6** |
| agents/scriptwriter.py | 232 | 6 | 5 | 6 | 7 | 6 | **6** |
| agents/storyboard.py | 1290 | 5 | 6 | 5 | 7 | 5 | **6** |
| cli.py | 542 | 6 | 7 | 7 | 8 | 6 | **7** |
| config.py | 50 | 3 | 5 | 6 | 4 | 6 | **5** |
| core/__init__.py | 35 | 3 | 5 | 5 | 7 | 6 | **5** |
| core/alias_resolver.py | 598 | 3 | 4 | 5 | 6 | 4 | **4** |
| core/hybrid_retriever.py | 56 | 1 | 6 | 5 | 5 | 6 | **5** |
| core/ingest.py | 106 | 5 | 8 | 5 | 4 | 6 | **6** |
| core/keyword_search.py | 85 | 3 | 7 | 6 | 6 | 8 | **5** |
| core/llm.py | 249 | 7 | 6 | 7 | 8 | 6 | **7** |
| core/prompts.py | 46 | 4 | 8 | 7 | 2 | 6 | **5** |
| core/vector_search.py | 108 | 6 | 8 | 6 | 7 | 6 | **7** |
| genres/__init__.py | 5 | 10 | 10 | 10 | 10 | 10 | **10** |
| genres/base.py | 138 | 5 | 7 | 6 | 8 | 7 | **7** |
| models/__init__.py | 25 | 10 | 8 | 8 | 10 | 9 | **9** |
| models/base.py | 40 | 5 | 7 | 6 | 8 | 7 | **6** |
| models/book.py | 41 | 6 | 6 | 7 | 8 | 7 | **7** |
| models/bridge.py | 60 | 3 | 4 | 5 | 6 | 5 | **5** |
| models/character.py | — | — | — | — | — | — | ❌ Failed to parse JSON |
| models/kv.py | 9 | 6 | 7 | 8 | 7 | 8 | **7** |
| models/script.py | 43 | 5 | 7 | 7 | 8 | 6 | **7** |
| models/storyboard.py | 51 | 5 | 6 | 7 | 8 | 7 | **6** |
| models/visual.py | 135 | 6 | 5 | 7 | 8 | 7 | **7** |
| run_pipeline.py | 166 | 5 | 4 | 5 | 8 | 4 | **5** |

### 详细审查


#### agents/adapter.py (评分: 6/10)
> 代码结构清晰，但存在空指针、路径注入、异常处理不足等问题，需加强健壮性、安全性和可维护性。

🟡 **错误处理**: 5/10
  - book = s.get(Book, self.book_id) 可能返回 None，后续直接使用 book.title 会引发 AttributeError
  - bible 查询后未检查是否成功，但已有 ValueError 抛出，可接受
  - call_llm 可能抛出网络/API 异常，未捕获处理
  → 增加检查 book 是否为 None，并抛出明确异常; 使用 try-except 包裹 LLM 调用和数据库提交，异常时回滚 session

🟡 **类型安全**: 6/10
  - p.gender、p.age_range 等字段可能为 None，拼接字符串时显示 'None'
  - book.title 可能为 None，路径生成和文件写入时会出错
  - bible.content[:6000] 直接切片，若 content 为 None 则报错
  → 使用 str(p.gender or '') 或提供默认值; 确保 book.title 非空，或使用 book.id 作为 fallback

🟢 **架构**: 7/10
  - session 来源于父类 BaseAgent，但未明确其定义，可能存在隐式依赖
  - bible.content 硬编码截断 6000 字符，可能导致重要内容丢失，不适合所有 genre
  - prompt 构建与 LLM 调用耦合，不利于测试和扩展
  → 显式注入 session 或使用依赖注入模式; 采用可配置的截断策略（如按 token 数或段落切割）

🟡 **安全**: 6/10
  - output_path 基于 book.title 构建，未消毒文件名，可能导致路径遍历或注入
  - 文件以写入模式创建，未设置权限限制（在共享环境中可能有风险）
  - LLM 返回的内容直接写入文件，可能包含恶意脚本或注入符号，但风险较低
  → 对 book.title 进行清洗，移除路径分隔符和特殊字符; 使用 os.path.basename 或安全的 slugify 函数

🟡 **可维护**: 6/10
  - 硬编码魔法数字 6000、3000，缺乏注释说明
  - 硬编码字符串 'bible'、'adapted'，应使用常量或枚举
  - portraits 拼接格式硬编码，不易调整
  → 将截断长度提取为类常量或配置项; 定义 BookStatus 枚举类替代 'adapted'

#### agents/base.py (评分: 5/10)
> 基类初具框架但存在重复导入、异常处理缺失、类型安全性不足及日志不完善等问题，需强化鲁棒性和维护性。

🔴 **错误处理**: 3/10
  - 数据库操作未捕获异常，如 get 可能抛出 NoResultFound、MultipleResultsFound 或数据库连接错误。
  - is_short_story 属性中 b 可能为 None，访问 b.chapter_count 会抛出 AttributeError。
  - session 上下文管理器未处理 Session 初始化或查询异常。
  → 在 is_short_story 中添加 try-except 或检查 b 是否为 None。; 在 session 上下文中使用 try-finally 确保资源释放并记录异常。

🟡 **类型安全**: 4/10
  - book_id 参数未进行类型校验，可能传入非 int 类型导致运行时错误。
  - name 类型声明为 str，但未强制子类赋值。
  - is_short_story 返回类型不明确（可能为 None 或引发异常）。
  → 在 __init__ 中添加类型检查或使用 Pydantic 模型。; 为 name 添加抽象属性或使用 @abstractmethod。

🟡 **架构**: 6/10
  - 重复导入 models.Session 和 models.Book, Session，应合并为一行。
  - session 上下文管理器与 is_short_story 中分别创建 Session，未复用连接。
  - 基类依赖具体数据库模型（Book），降低了通用性。
  → 合并导入语句：from models import Book, Session。; 考虑将 session 作为实例属性或使用依赖注入。

🟢 **安全**: 7/10
  - 直接使用传入的 book_id 从数据库获取对象，未进行授权检查（可能越权访问其他用户的书）。
  - print 日志可能泄露敏感信息（如书名或章节数）。
  → 在获取 Book 前验证当前用户是否有权限访问该 book_id。; 使用结构化日志库（如 logging）并配置输出级别，避免生产环境打印敏感信息。

🟡 **可维护**: 5/10
  - 重复导入语句，降低可读性。
  - 使用 print 而非 logging 模块，不利于日志管理和级别控制。
  - name 属性未强制子类必须覆盖，可能导致运行时错误。
  → 删除重复导入，仅保留 from models import Book, Session。; 替换 print 为 logging.getLogger(__name__).info。

#### agents/bible.py (评分: 5/10)
> 代码整体功能完整，但存在错误处理不足、session 管理混乱、代码可维护性较差等问题，需重构并增加防御性编程。

🟡 **错误处理**: 4/10
  - 静默忽略 JSON 解析异常，可能导致数据丢失且无日志记录
  - 在 _build_bible 中使用 session or self.session，但 self.session 可能不是有效会话，且未正确管理连接
  - 文件写入未检查写入失败或权限问题
  → 捕获异常时记录日志，而非直接 pass; 统一使用传入的 session 参数，避免依赖 self.session

🟡 **类型安全**: 6/10
  - all_characters 合并时只更新 chapters 和 identity，忽略不同章节的 personality 等其他属性的合并
  - json.loads 结果未进行类型检查，假设字段存在可能引发 KeyError
  - all_events 中直接修改 JSON 项（添加 'chapter'）可能导致后续影响
  → 对重复角色进行完整合并（如累积 personality 描述）; 使用类型守卫或 Pydantic 模型确保数据结构

🟡 **架构**: 5/10
  - session 管理混乱：_build_bible 同时使用 session 参数和 self.session，可能导致连接泄漏或事务不一致
  - run 方法中先查询 chapter 再构建数据，逻辑分散在多个循环中，不易测试和扩展
  - 硬编码限制（mid_events 取前20，key_events 取前30）缺乏依据
  → 统一使用 session 参数，移除 self.session 备选; 将数据收集步骤抽离为独立方法，便于单元测试

🟢 **安全**: 7/10
  - 文件路径直接使用 book.title，可能包含路径遍历字符（如 ../）
  - 未对用户输入（如 chapter.character_table）进行验证，存在注入风险（但通常内部数据）
  - JSON 解析可能被恶意构造的字符串触发重解析攻击（但数据来自数据库）
  → 对 book.title 进行清洗，只允许安全字符; 考虑对 chapter 中的 JSON 字段进行 schema 验证

🟡 **可维护**: 5/10
  - 多处重复的 try-except 块（JSON 解析），可提取为辅助函数
  - magic number（20, 30）散落在代码中
  - 字符串拼接生成 markdown 难以维护和格式化
  → 提取 JSON 安全解析函数（def safe_json_loads(data, default)）; 将 magic number 定义为类常量或配置

#### agents/outline.py (评分: 6/10)
> 功能基本完整，但在错误处理、类型安全和架构设计上存在明显不足，建议重构以提升健壮性和可维护性。

🟡 **错误处理**: 4/10
  - _generate_single_episode 中 try-except 捕获所有异常并 pass，可能隐藏真正的错误（如正则匹配失败）。
  - _parse_json_sliots 未处理 json.JSONDecodeError，若 LLM 返回非 JSON 将导致程序崩溃。
  - run 方法中 call_llm 调用没有超时或重试机制，网络故障可能导致挂起。
  → 使用更具体的异常捕获，如 except (json.JSONDecodeError, KeyError) as e，并记录错误日志。; 为 _parse_json_sliots 添加 try-except，解析失败时返回空列表并记录警告。

🔴 **类型安全**: 3/10
  - episodes 和 fixed_sliots 的元素是字典，但缺少类型注解，且字段类型（如 characters 期望 list 但可能为 None）未校验。
  - bible.content[:4000] 当 content 为 None 时会抛出 TypeError。
  - book.chapter_count 未验证类型，可能为字符串或其他导致计算错误。
  → 为所有字典类型定义 TypedDict 或 dataclass，确保字段类型一致。; 访问 bible.content 前检查是否为 None 或提供默认值。

🟡 **架构**: 5/10
  - run 方法承担了读取数据、调用 LLM、合并结果、格式化、保存到文件和数据库等多个职责，违反单一职责原则。
  - 短篇模式 (short story) 和普通模式共享大部分代码，但分支逻辑分散，导致重复代码（如 _format_outline 被共用，但单集生成逻辑独立）。
  - 固定 sliot 的提取和合并逻辑与主流程紧耦合，难以独立测试。
  → 将职责拆分：设计 OutlineGenerator、SliotExtractor、OutlineFormatter 等类或方法。; 为短篇模式使用独立的子类或多态实现，避免在 run 中 if-else 分支。

🟢 **安全**: 7/10
  - 从 LLM 返回的 JSON 未经严格校验直接存储到数据库，可能包含恶意脚本（XSS）？但后续输出为文本文件，风险低。
  - 文件路径依赖于 book.title，若标题包含路径分隔符（如 /../）可能导致目录遍历。
  - 将圣经内容（bible.content）发送到外部 LLM 存在数据泄露风险，但这是功能需求。
  → 对 LLM 返回的 JSON 中的字符串字段进行转义或清洗，防止注入（例如使用 bleach 库）。; 在 config.output_path 中对 book.title 进行 sanitize，移除不安全字符。

🟡 **可维护**: 4/10
  - 代码中存在重复的 JSON 解析逻辑（_parse_json_response 和 _parse_json_sliots 可能功能重叠）。
  - 缺少文档和注释，特别是复杂逻辑（如固定 sliot 的合并规则）没有说明。
  - 硬编码了 magic number（如 4000, 6000, 262144）且多处出现，修改时容易遗漏。
  → 合并 _parse_json_response 和 _parse_json_sliots 为一个通用 JSON 提取函数，根据 schema 区分。; 为每个公共方法添加 docstring，说明输入输出和副作用。

#### agents/portrait.py (评分: 7/10)
> 代码结构清晰、模块化良好，但存在错误处理薄弱、部分方法过长、硬编码等问题，建议增强异常管理、拆分复杂方法、统一日志和配置

🟡 **错误处理**: 5/10
  - raise ValueError 无外层 try-catch，可能导致程序未处理异常而崩溃
  - JSON 解析异常被静默忽略，可能丢失数据或隐藏错误
  - 文件写入操作（write_text）没有异常处理，可能因权限或磁盘问题失败
  → 在 run 方法外层添加顶层异常捕获，记录错误后优雅退出或重试; JSON 解析失败时至少记录警告日志，而非直接 pass

🟢 **类型安全**: 7/10
  - _aggregate 返回值类型标注为 tuple[dict, dict]，但内部实际嵌套结构更复杂，精确性不足
  - all_fragments 和 all_characters 未使用更具体的类型（如 Dict[str, List[str]] 和 Dict[str, dict]）
  - char_info 变量类型未标注，实际从字典 get 获取，可能为 None 引起后续属性访问错误
  → 使用 TypedDict 或 dataclass 定义碎片和角色信息的结构，提升类型安全; 为 _aggregate 返回值添加精确的泛型标注，或拆分为两个独立函数

🟡 **架构**: 6/10
  - _aggregate 方法同时处理外貌片段和角色基础信息，违反单一职责原则，可拆分为两个方法
  - _save_outputs 方法过长（约 80 行），包含 JSON、Markdown、文本三种输出生成逻辑，难维护
  - 重要角色筛选逻辑（min_ch、min_frag）直接写在 run 方法中，不利于配置和测试
  → 将 _aggregate 拆分为 _collect_fragments 和 _collect_characters 两个独立私有方法; 将 _save_outputs 拆分为 _save_json, _save_markdown, _save_prompts 三个方法，或使用策略模式

🟢 **安全**: 9/10
  - book_title 经过 config.sanitize_filename 处理，但未验证是否为合法路径，极端情况可能引发路径遍历（如包含 '..'）
  - 文件写入路径依赖于数据库中的 book.title，但假设其内容受控，未做额外清理
  → 在 sanitize_filename 基础上增加路径遍历检测，如禁止包含 '..' 或 '/'; book.title 写入前可进行再次校验，限制特殊字符

🟢 **可维护**: 7/10
  - 硬编码大量 print 语句用于输出日志，在正式环境中应替换为 logging 模块
  - 重要角色筛选逻辑（min_ch, min_frag）重复出现两次（第一次过滤 chapters 数量，第二次过滤片段数量），可合并
  - 多处使用 'name' 字符串字面量，若字段名变更需全局替换，易遗漏
  → 将 print 替换为 logging.info，并配置日志级别; 将两次过滤合并为一次条件判断，减少重复

#### agents/portrait_base.py (评分: 6/10)
> 代码结构清晰，但错误处理薄弱、硬编码较多，建议加强异常捕获、类型校验和模块化重构。

🟡 **错误处理**: 4/10
  - call_llm_json 调用未处理异常，可能因网络或格式错误导致程序崩溃
  - session.query 和 session.commit 未包裹 try/except，数据库操作失败会直接抛出未处理异常
  - 缺乏对 LLM 返回 JSON 结构完整性的校验（如键缺失、类型错误）
  → 在 generate_base_profile 中增加顶层 try/except，记录错误并返回默认或空结果; 对 call_llm_json 返回结果进行 validate，确保必填字段存在且类型正确

🟡 **类型安全**: 6/10
  - chapter_range 拼接时 first_chapter 可能为 '?' 字符串，但 max(chapters) 为整数，类型混合但不会出错
  - importance 的判断逻辑依赖 len(char_info.get('chapters', [])) 的整型比较，若 chapters 包含非列表值会抛 AttributeError
  - force_string_types 中 for 循环未处理 None 值（d.get 返回 None 时 isinstance(val, list) 通过，但 join 会出错）
  → 明确处理 char_info.get('chapters') 的非列表情况，例如确保返回列表; 在 force_string_types 中对 val 为 None 做额外处理，如 d[k] = ''

🟢 **架构**: 7/10
  - generate_base_profile 函数过长，同时处理了推理、LLM 调用、数据库更新，职责过多
  - infer_gender 和 infer_age 的复杂逻辑（关键词匹配、邻近查找）更应抽取为独立模块或配置化规则
  - 硬编码了 CharacterProfile 模型，不利于测试和替换
  → 将数据库 CRUD 操作抽取为单独函数，如 upsert_character_profile; 考虑将性别/年龄推断规则以配置或策略模式组织，便于维护和扩展

🟢 **安全**: 7/10
  - LLM 提示词中直接拼接 fragments_text 等用户输入，存在 prompt injection 风险
  - relationships_str 通过 json.dumps 序列化后传入 prompt，可能包含恶意内容
  → 对用户输入进行转义或限制长度（已有 fragments[:50]），但建议增加对 prompt 中特殊字符的过滤; 考虑对 LLM 返回结果进行安全校验，防止生成恶意 SQL 或 XSS（但存入数据库后由前端控制显示）

🟡 **可维护**: 6/10
  - force_string_types 硬编码了大量字段名称，新增 prompt 层时容易遗漏
  - infer_gender 和 infer_age 中关键词列表（如 animal_kw, elderly_kw）重复定义，且分散在函数内
  - 多处使用 len(char_info.get('chapters', [])) 重复计算，可缓存在变量中
  → 将字段列表定义为模块级常量或与 CharacterProfile 模型联动; 将性别/年龄关键词统一提取为配置文件或常量

#### agents/portrait_stages.py (评分: 6/10)
> 代码功能基本完整，但在异常处理、可维护性和类型安全方面存在一定风险，建议重构以提升健壮性和可读性。

🟡 **错误处理**: 5/10
  - call_llm_json异常仅打印并return，无重试或降级机制
  - session.query和commit无异常处理，数据库操作可能失败未捕获
  → 添加重试逻辑或回退方案（如使用默认阶段）; 包裹数据库操作在try-except中，失败时回滚并记录错误

🟡 **类型安全**: 6/10
  - char_info.get('chapters', [0])[-1] 若chapters为None会引发AttributeError
  - chapters[:100] 假设chapters是列表，未验证类型
  → 使用char_info.get('chapters') or [] 并检查是否为空; 添加类型注解或运行时检查确保chapters是列表

🟡 **架构**: 6/10
  - 函数同时负责数据获取、LLM调用、数据库写入，单一职责原则违反
  - stage字段推断逻辑嵌入在主流程中，难以测试和复用
  → 拆分函数：数据提取、生成阶段、存储阶段; 将字段推断逻辑独立为辅助函数，便于单元测试

🟢 **安全**: 7/10
  - LLM输出直接存入数据库，未做输入验证或清洗，可能注入恶意内容
  → 对LLM返回的字符串做长度、字符集校验，避免异常数据

🟡 **可维护**: 5/10
  - 大量重复的stage.get()赋值，难以维护字段变更
  - 硬编码魔术数字30、100，降低灵活性
  - 缺少注释说明force_string_types和推断逻辑的目的
  → 使用字典映射或数据类自动赋值，减少重复代码; 将魔术数字提取为常量或配置参数

#### agents/prompt_synthesizer.py (评分: 5/10)
> 代码功能清晰但实现粗糙，存在资产链接检查不全、路径穿越安全漏洞、重复查询和硬编码模板等典型问题，建议加强异常处理、安全检查和代码复用。

🟡 **错误处理**: 5/10
  - asset_links 为空字符串时 json.loads 会抛出异常，当前 or '{}' 仅对 None 有效，对空字符串无效
  - run 中只检查前 3 个镜头的 asset_links，若第 4 个镜头才就绪则会错误跳过 Phase 2
  - synthesize_single_shot 未对 shot 属性（如 camera_angle）可能为 None 做防御，拼接时可能产生空字符串或异常
  → 统一使用 sh.asset_links or '{}' 并额外处理空字符串：json.loads(sh.asset_links) if sh.asset_links else {}; 改为检查所有镜头的 asset_links，而不是只检查前 3 个

🟡 **类型安全**: 4/10
  - synthesize_single_shot 的 shot 参数缺少类型标注，应为 StoryboardShot
  - run 方法返回类型 list[dict] 但 Phase 2 未实现时返回空列表，类型不完整
  - self.genre 类型未明确，依赖 get_genre 返回的对象，其 description 属性可能不存在
  → 为 shot 参数添加类型标注：def synthesize_single_shot(self, shot: StoryboardShot) -> str; 统一 run 返回类型为 Optional[List[Dict]]，或使用明确的数据结构

🟡 **架构**: 6/10
  - run、batch_synthesize、save_synthesized_output 重复执行相同的数据库查询（过滤 episode）
  - Phase 1 仅日志输出，没有实际返回框架数据，调用方需自行判断
  - synthesize_single_shot 硬编码模板字符串，扩展性差，修改 prompt 格式需改代码
  → 提取公共方法 _get_shots(episode) -> List[StoryboardShot] 以避免重复查询; Phase 1 返回包含占位提示词（如 '待 asset_links 就绪'）的词典，让调用方能对应处理

🟡 **安全**: 4/10
  - save_synthesized_output 中 title 直接用于路径拼接（outputs / title / video），存在目录穿越风险，攻击者可写入任意位置文件
  - 输出 JSON 文件使用 sh.asset_links 直接解析，虽无直接注入但可能暴露内部路径
  - 日志打印 asset_links 信息可能泄露敏感路径（如内部文件结构）
  → 对 title 进行路径安全校验，只允许字母、数字、下划线、中文等，拒绝包含 '..' 或 '/' 的输入; 使用 os.path.basename 或 Path.name 提取安全文件名，或限定 title 必须为已知书籍目录

🟡 **可维护**: 5/10
  - 存在大量重复代码：查询 shots 的逻辑在三处重复，硬编码的日志字符串也重复
  - run 方法中残留注释掉的 Phase 2 实现代码，应清理
  - synthesize_single_shot 中 parts 列表直接拼接，未过滤空值，导致输出可能有多余空行
  → 抽取重复查询为 _get_shots 方法，统一的日志格式可使用 f-string 或 logger; 删除注释掉的死代码

#### agents/qa.py (评分: 6/10)
> 基本功能完整，但异常处理薄弱、硬编码常见，且存在逻辑耦合，建议通过拆分方法和加强校验提升健壮性。

🟡 **错误处理**: 4/10
  - 缺少对数据库查询失败的异常捕获
  - call_llm_json 调用未处理网络/解析错误
  - Json 解析 result 时未做类型校验，可能导致 KeyError
  → 为每个数据库查询添加 try/except 并记录错误; 对 LLM 调用结果增加重试机制和格式校验

🟡 **类型安全**: 6/10
  - result.get('errors') 假设 call_llm_json 返回 dict，但可能返回 None 或其他类型
  - generate_report 中 json.loads(r.result) 未捕获异常
  - 字符串切片 [':3000'] 可能截断有效字符，破坏 markdown 结构
  → 使用 type hints 明确 LLM 返回格式并在运行时断言; 对 json.loads 增加 try/except，确保数据完整性

🟡 **架构**: 6/10
  - bible 内容解析依赖硬编码的 '## 一、人物数据库' 字符串，脆弱且不可配置
  - run 方法过长（>60 行），混合了数据提取、LLM 调用和持久化
  - prompt 模板与运行时数据紧耦合，修改模板需同步更新代码
  → 将 bible 解析逻辑抽取为独立函数，支持配置分隔符; 拆分 run 方法：extract_char_info, extract_portrait, run_qa, save_results

🟢 **安全**: 8/10
  - book.title 用于拼接文件路径，若被恶意篡改可能导致路径遍历
  - write_text 写入前未校验 result 内容，可能存在 XSS 风险（若写入 HTML）
  → 对 book.title 进行合法性校验或过滤特殊字符; 对写入的 JSON 内容进行安全编码，避免直接写为 .md 文件中的原始内容

🟡 **可维护**: 5/10
  - 魔法数字 3000 和 5000 没有命名常量，难以维护
  - generate_report 使用字符串拼接生成 markdown，易出错
  - agent 内部直接操作数据库 ORM，未抽象数据访问层
  → 定义常量 MAX_CHAR_LENGTH、MAX_SCRIPT_LENGTH; 使用模板引擎（如 Jinja2）生成报告

#### agents/reader.py (评分: 7/10)
> 功能基本完备，架构合理，但错误处理、类型安全和可维护性有待加强，建议引入重试机制和类型校验

🟡 **错误处理**: 6/10
  - 内容截断硬编码15000字符，无法适应不同模型
  - 异常捕获太宽泛（Exception），可能掩盖非预期错误
  - 限流后仅sleep 30s无重试机制，导致章节永久失败
  → 将截断长度设为可配置参数; 区分网络错误、限流错误、业务错误，分别处理

🟡 **类型安全**: 5/10
  - call_llm_json返回值未做类型校验，非dict会异常
  - 字符聚合中c.get('name')可能为None，未处理
  - ch_data为dict但无类型标注
  → 使用TypedDict定义LLM返回结构，或isinstance校验; 添加对name为空的过滤或默认处理

🟢 **架构**: 7/10
  - 多处使用独立session但无统一事务管理，部分失败无法回滚
  - run方法中保存操作顺序依赖，失败后无法恢复
  - 角色聚合逻辑放在run中，违反单一职责
  → 引入工作单元模式，将多个写操作包装在事务中; 将角色聚合、文件保存抽取为独立方法

🟢 **安全**: 8/10
  - 输出文件路径由config.output_path生成，若配置不当可能存在路径遍历风险
  → 对book_title进行路径安全校验（如移除非法字符）; 确保config.output_path使用白名单或固定目录

🟡 **可维护**: 6/10
  - 硬编码多个常量（章节延迟、截断长度、backoff时间）
  - 重复的session创建模式（with RS() as s）
  - 角色聚合逻辑与主流程混合
  → 将硬编码值提取到配置类或环境变量; 创建session工厂函数减少重复

#### agents/rewrite.py (评分: 6/10)
> 功能实现基本正确，但存在错误处理不完善、安全风险（路径遍历）和代码可维护性不足的问题，建议增加异常处理和安全净化，并优化架构以分离关注点。

🟡 **错误处理**: 5/10
  - 缺少对 LLM 调用失败的处理（网络错误、超时、API 拒绝等），直接抛出异常可能导致数据不一致
  - 文件写入未捕获异常，若目录不可写或磁盘满会导致未处理的异常
  - 数据库更新部分未使用事务回滚，当文件写入成功但数据库更新失败时会出现不一致
  → 为 call_llm 添加重试机制或异常捕获，并在失败时记录日志或回滚操作; 文件写入失败时增加异常捕获并回滚数据库更改

🟢 **类型安全**: 7/10
  - 参数 episode 无类型注解，输入非整数时可能引发意外错误
  - 返回值类型声明为 str，但实际返回 str(output) 中 output 是 Path 对象，通过 str() 转换符合声明，但未在函数签名中明确返回字符串
  → 为 episode 参数添加类型注解：episode: int; 考虑返回类型可以使用 Path 或 str，保持一致即可

🟡 **架构**: 6/10
  - 方法承担了过多职责：查询数据库、调用 LLM、写入文件、更新数据库，违反了单一职责原则
  - 硬编码 prompt 的 system 消息和 estimated_tokens 等参数，不利于配置和测试
  → 考虑将 LLM 调用、文件保存、数据库更新分别抽象为单独的方法或服务; 将 system 提示、token 限制等抽离到配置或 prompt 模板中

🟡 **安全**: 6/10
  - file_path 构建使用了 f-string，但 self.book_id 和 episode 来自用户输入（虽然 episode 是 int，book_id 可能为字符串），存在路径遍历风险，例如 book_id 可能包含 '../' 等
  - script.content[:5000] 用于 prompt，但 content 可能包含恶意提示注入内容，LLM 可能受干扰
  → 对 book_id 进行净化或限制其格式（例如仅允许数字或 UUID）; 在将 content 传给 prompt 前考虑进行转义或限制长度（已经限制 5000 字符，但注入风险仍存在，可考虑使用系统提示强化边界）

🟡 **可维护**: 5/10
  - 硬编码 'rewrite/rewrite' prompt 名称，若路径变动不利于维护
  - 缺少对 script 对象的校验（如 content 是否为空）
  - estimated_tokens 和 max_tokens 直接硬编码，未来模型变更可能需调整
  → 将 prompt 名称、system 消息、token 限制等作为类常量或配置项; 添加对 script.content 存在性的检查并给出清晰错误信息

#### agents/scene_setup.py (评分: 6/10)
> 代码结构清晰但安全验证不足，错误处理不完整，存在较多重复逻辑，类型安全需通过 pydantic 或更好的类型注解改善，核心功能逻辑正确但维护性有待提升。

🟡 **错误处理**: 6/10
  - LLM 返回结果未充分校验 JSON 结构，如直接访问 result['time_periods'] 可能引发 KeyError
  - run_props 中假设 result 为 dict 或 list，但未处理其他类型（如 None）
  - _extract_timeline 中 ch.events 可能不是合法 JSON，json.loads 未捕获异常
  → 所有 LLM 返回解析后增加结构校验（如 isdict、has_key）并设置默认值; 对 json.loads 调用添加 try/except 或使用辅助函数

🟡 **类型安全**: 5/10
  - call_llm_json 返回类型未声明，下游代码假设为 dict (如 result.get('props', [result])) 但可能为 list
  - _force_string 接收 dict 但若 d 不是 dict 会抛 AttributeError
  - 变量 result 在不同路径下可能被赋值为不同结构（dict vs list），难以静态推断
  → 明确 call_llm_json 返回类型（如使用泛型 T = dict | list）并统一处理; 所有字段写入 DB 前统一使用 _force_string 或 json.dumps 确保字符串化

🟢 **架构**: 7/10
  - run_props 和 run_locations 存在大量重复代码（会话管理、去重逻辑、字段赋值）
  - 硬编码路径 _get_genre_rules 中 prompts_dir = .../prompts/genres，与 core.prompts 耦合
  - 去重逻辑在 run_props 和 run_locations 中重复实现，应提取公共方法
  → 提取公共方法如 _upsert_entity(table, filter, data) 来简化道具/场景的存储; 将路径管理放入 config 或通过依赖注入，避免硬编码

🟢 **安全**: 8/10
  - _get_genre_rules 中 path 拼接使用了 self.genre.name 未做路径清理，若 genre 名被恶意控制可能导致目录遍历
  - LLM prompt 中包含从数据库取出的文本（bible_excerpt, script_content），若包含特殊字符可能被注入恶意 prompt（但 LLM 内风险较低）
  → 对传入的 genre.name 进行合法性校验（如仅允许字母数字下划线）或使用 whitelist 匹配; 考虑对用户输入的内容（如 bible 内容）进行过滤或限制长度，防止 prompt 注入

🟡 **可维护**: 6/10
  - 多个方法中重复的字段赋值模式（如 `existing.description = prop.get(...)`）
  - 硬编码的 magic number（`timeline_text[:3000]`、`bible_excerpt[:6000]`）
  - _extract_timeline 中直接使用 JSON 序列化结果，与底层模型耦合
  → 定义常量存储 token 限制值，或从配置/ prompt 模板中读取; 提取公共的字段同步函数，接受模型类、现有对象、更新字典，批量赋值

#### agents/scriptwriter.py (评分: 6/10)
> 代码功能完整但结构松散，错误处理和类型安全待加强，缺少异常上下文和路径验证，建议拆分run方法并统一数据结构。

🟡 **错误处理**: 6/10
  - 缺少全面的异常捕获，例如数据库查询失败、LLM调用异常、文件写入失败等未处理
  - 文件写入时未检查目录是否存在，可能引发FileNotFoundError
  - _parse_outline方法假设格式严格，遇到非预期行可能静默忽略或导致错误数据
  → 在run方法中增加try-except-finally，记录关键错误日志并提供用户友好的回退; 写入文件前确保目录存在，如使用parent.mkdir(parents=True, exist_ok=True)

🟡 **类型安全**: 5/10
  - ep_data的类型不统一：旧结构返回列表，但后续始终当字典使用，存在潜在AttributeError
  - _parse_outline返回列表元素可能缺少某个字段，导致后续代码访问None属性
  - 函数返回注解为str，但实际返回Path对象（被str()隐式转换），建议显式返回字符串
  → 统一episode数据结构，强制使用字典类型，或使用Pydantic模型校验; 在访问字段前使用.get()并设置默认值，或增加断言检查

🟡 **架构**: 6/10
  - run方法过长（约120行），职责过多，违背单一职责原则
  - 旧结构与新结构的回退逻辑分散，导致可读性差
  - 角色肖像构建存在大量重复代码（if-else分支），不利于扩展
  → 将run方法拆分为fetch_episode_data、build_prompt_context、save_script等内部方法; 重构数据结构迁移，强制使用多行EpisodeOutline，移除旧回退代码

🟢 **安全**: 7/10
  - book.title直接用于文件路径构造，若包含../等特殊字符可能导致路径遍历
  - LLM prompt中拼接了用户可控的bible、excerpts等，存在prompt注入风险（但属于应用层）
  - 未对retriever.search返回结果做内容过滤，可能引入恶意数据
  → 使用uuid或安全命名替换book.title；或对title做路径安全校验（如只允许字母数字下划线）; 对LLM prompt中的用户输入做长度限制或转义；下游调用方应限制角色

🟡 **可维护**: 6/10
  - 多处硬编码字符串（如'**核心事件：**'、'白狐'等）重复出现，维护困难
  - 魔术数字5（retriever search n_results）未定义为常量
  - 中文注释夹杂少量英文，风格不统一
  → 定义常量类或配置文件集中管理所有magic strings和numbers; 将n_results作为类属性或配置参数暴露

#### agents/storyboard.py (评分: 6/10)
> 代码整体功能完整但设计上存在明显耦合与维护性挑战，错误处理可进一步加强，安全 risk 较低，建议重构为模块化架构并完善类型系统。

🟡 **错误处理**: 5/10
  - 缺乏全局异常捕获，LLM 调用失败可能抛出未处理异常
  - call_llm_json 返回值未进行严格验证，可能引发 KeyError 或类型错误
  - 数据库操作未包裹 try/except，可能导致连接泄漏或未回滚
  → 在 run 方法中添加 try/except 块，记录错误日志并优雅退出; 对 call_llm_json 返回结果进行类型检查，并验证必要字段存在

🟡 **类型安全**: 6/10
  - 许多函数参数和返回值缺少类型注释，如 _extract_scene_script_block
  - list[dict] 没有具体定义 dict 结构，易引发运行时错误
  - 函数内部动态类型（如 json.loads 结果）未做类型保护
  → 为所有公开方法添加完整类型提示，使用 TypedDict 定义场景/镜头的结构; 对 call_llm_json 的返回类型使用 Union[Dict, List] 并做 isinstance 检查

🟡 **架构**: 5/10
  - StoryboardAgent 类职责过重，耦合了 LLM、数据库、文件 I/O、预算校验
  - run 方法过长，未遵循单一职责原则
  - 通过 sys.path.insert 加载外部工具，破坏了模块结构和可移植性
  → 将预算分配、镜头生成、场景去重等拆分为独立模块或服务类; 将 run 方法拆分为多个小步骤，每个步骤调用独立组件

🟢 **安全**: 7/10
  - LLM prompt 中包含用户可控的剧本内容，存在 prompt injection 风险
  - book.title 直接用于文件路径，未做路径规范化，可能引起目录遍历
  - 未对 episode 参数进行合法性校验（如负数或越界）
  → 对剧本内容进行长度限制和特殊字符过滤，考虑使用系统 prompt 隔离; 对 book.title 使用 safe_filename 函数处理，限制路径可访问范围

🟡 **可维护**: 5/10
  - 代码行数过多（1290 行），方法内逻辑复杂
  - 相似度计算中的阈值（0.52、0.5 等）没有注释说明来源或含义
  - 多处重复计算 duration（如 sum(sh.get('duration',3))），未提取常量或工具函数
  → 将长方法拆分为多个小函数，并添加文档字符串; 将阈值定义为类常量或配置参数，并添加注释解释其设计依据

#### cli.py (评分: 7/10)
> 代码结构清晰、模块化良好，但存在异常处理不足、硬编码、少量安全风险和重复代码，改进后可达到较高水平

🟡 **错误处理**: 6/10
  - 所有命令依赖 `_init()` 但未处理数据库初始化失败异常
  - `ingest`, `read`, `bible` 等命令未捕获子 agent 或底层函数可能的异常，异常会直接传播到 typer 导致原始堆栈信息泄露
  - `_print_qa_result` 中未处理 `result.get('errors')` 可能为 None 的情况（逻辑上安全但防御不足）
  → 为每个命令添加 try-except 块，捕获通用异常并输出友好的错误信息（使用 rich 或 typer.Exit）; 考虑在 `_init` 中处理 `init_db` 异常，并使用 `console.print` 报告失败原因后退出

🟢 **类型安全**: 7/10
  - `genre` 参数使用字符串字面量（如 'short_drama'），未使用枚举或类型别名，容易因拼写错误导致运行时失败
  - `adaptation_type` 手动验证有效性，但验证后仍作为字符串传递给 agent，未使用强类型
  - 部分函数返回类型未显式标注（如 `do_ingest` 返回字典结构无类型提示）
  → 定义枚举类 `Genre` 和 `AdaptationType`，使用 Literal 或自定义类型，在参数声明中使用枚举值; 对 agent 方法添加返回类型注解（如 TypedDict 或 dataclass），提高可维护性和 IDE 支持

🟢 **架构**: 7/10
  - `_init()` 在每个命令中重复调用，可能导致多次数据库初始化（`init_db` 应设计为幂等，但架构上可优化）
  - 批处理逻辑（如 `rewrite` 和 `check` 中的循环）直接在 CLI 层实现，增加了命令函数的复杂度，应抽取到共享逻辑
  - `_print_qa_result` 是 UI 渲染代码，应属于 CLI 层，但散布在 agent 与 CLI 之间，职责边界模糊
  → 使用 Typer 回调函数或依赖注入容器，自动在命令执行前初始化数据库（例如 `@app.callback`）; 将批处理逻辑提取为独立的辅助函数（如 `_batch_process(agent, start, end, callback)`）

🟢 **安全**: 8/10
  - `ingest` 命令接受 `filepath` 字符串参数，未校验路径是否在允许的目录范围内，可能存在路径遍历风险（恶意用户可读取任意文件）
  - 无输入验证检查 file 是否存在或是否为可接受的文件类型（如 .txt/.epub），可能引入不安全的文件操作
  → 在校验 `filepath` 时，使用 `Path.resolve()` 并限制在预定义的导入目录下（如 '~/imports'）; 添加文件扩展名白名单验证，并检查文件是否存在，若不存在则明确报错并拒绝操作

🟡 **可维护**: 6/10
  - 代码重复：每个命令都编写相同的 `_init()`、Progress 使用模式，可提取公共装饰器或命令基类
  - 魔术字符串硬编码：`genre` 默认值 'short_drama'、`adaptation_type` 有效列表重复出现在多个地方
  - 逻辑耦合：`check` 命令中混合了单集与批处理逻辑，同时直接操作 `Book` 模型（从 CLI 层），增加了维护负担
  → 创建 `@with_db` 装饰器或命令基类 `BaseCommand`，自动包含 _init() 和进度条上下文管理器; 将魔术字符串定义为模块级常量或配置类，统一引用

#### config.py (评分: 5/10)
> 配置文件结构清晰但存在安全、健壮性和可维护性问题，建议通过配置类化、异常处理和安全加固提升质量

🔴 **错误处理**: 3/10
  - 模块加载时执行目录创建操作，无异常处理，可能因权限、磁盘不足等原因静默失败
  - 环境变量转换为float/int时（如LLM_TEMPERATURE、LLM_MAX_TOKENS）未处理ValueError，传递无效值会导致程序崩溃
  - sanitize_filename 和 output_path 未进行异常处理，例如Path操作可能因系统限制失败
  → 将目录创建逻辑移至惰性初始化或显式调用函数中，并捕获异常（如PermissionError）; 环境变量转换使用try-except，失败时回退到默认值或记录警告

🟡 **类型安全**: 5/10
  - LLM_TEMPERATURE 和 LLM_MAX_TOKENS 等变量依赖环境字符串，float/int转换可能隐性出错（如空字符串、非数字）
  - 未对EMBEDDING_DIM等数值进行范围校验（例如必须为正整数）
  - sanitize_filename 返回类型为str，但未验证输入是否为字符串（虽然Python动态类型，但缺乏显式断言）
  → 使用类型转换时添加显式校验，如int(x)后判断是否大于0; 定义配置类或TypedDict，提供类型提示和默认值校验

🟡 **架构**: 6/10
  - 模块级代码（目录创建、环境变量加载）在导入时执行，导致副作用，不利于单元测试和模块复用
  - 硬编码默认值分散在各处，难以统一管理和覆盖所有配置参数
  - output_path 在每次调用时都创建目录，可能产生不必要的I/O开销
  → 将配置加载封装为函数或配置类，延迟初始化直到首次调用; 使用配置中心或单一配置字典管理所有默认值，便于维护和测试

🟡 **安全**: 4/10
  - 硬编码默认API密钥 'sk-placeholder' 作为占位符，若生产环境未覆盖则可能被攻击者利用或泄露
  - sanitize_filename 仅过滤特殊字符，未防止路径遍历攻击（如 '../' 或空字符串）
  - 环境变量敏感信息（如API密钥）在代码中直接引用，无安全存储或加密措施
  → 移除默认API密钥占位符，改用显式错误提示用户必须设置环境变量; 在sanitize_filename中使用Path.resolve()或白名单字符集，严格限制路径成分

🟡 **可维护**: 6/10
  - 全局变量过多且分散，缺乏统一配置对象，难以添加新参数或修改默认值
  - 目录创建逻辑与配置定义混合，降低了模块的内聚性
  - 缺乏文档说明各环境变量的意义和取值范围
  → 将配置参数封装为类（如Config），通过属性访问，便于扩展和重构; 分离配置定义与初始化逻辑，目录创建可单独作为启动任务

#### core/__init__.py (评分: 5/10)
> 基础功能可用，但错误处理薄弱、类型安全有隐患、架构设计可优化，需加强健壮性与可维护性。

🔴 **错误处理**: 3/10
  - 未捕获 httpx 请求异常（超时、连接失败等），可能导致程序崩溃
  - 未处理 JSON 解析错误（如 API 返回非预期格式）
  - 未验证输入为空或模型不存在等情况
  → 在 __call__ 方法中添加 try-except 块，分别处理 httpx.HTTPError、json.JSONDecodeError 等异常; 为 embed_query 和 embed_documents 添加输入参数校验，例如确保列表非空

🟡 **类型安全**: 5/10
  - embed_query 方法参数 text 和 input 类型不一致，容易混淆调用者
  - embed_documents 中 texts or input 可能返回 None 传递给 __call__，导致类型错误
  - __call__ 缺少对 input 为 None 或非列表的防御
  → 统一 embed_query 方法签名，仅接受 input: list[str] = None; 在 embed_documents 中确保传入的参数不为 None 且为列表

🟡 **架构**: 5/10
  - 每次调用 __call__ 都新建 httpx.Client，浪费资源且无法复用连接
  - 依赖全局 config 模块，不利于单元测试和配置灵活性
  - 类设计简单，但缺少抽象基类或接口定义，扩展性受限
  → 在 __init__ 中创建 httpx.Client 实例并复用到请求中，或使用连接池; 使用依赖注入方式传入配置（如直接传 model 和 base_url），避免硬编码全局变量

🟢 **安全**: 7/10
  - base_url 由用户提供，存在 SSRF 风险，未做域名/IP 白名单校验
  - 未限制请求大小，大文本可能导致内存压力
  → 建议对 base_url 进行验证，仅允许可信任的端点; 可增加输入文本长度限制或在配置中设置上限

🟡 **可维护**: 6/10
  - 类型提示不完善（如 __call__ 返回类型忽略可能异常）
  - 缺乏文档和异常处理，未来维护者可能不清楚边界情况
  → 补充函数文档字符串，说明参数和返回值含义; 添加适当的日志记录以帮助调试

#### core/alias_resolver.py (评分: 4/10)
> 代码主体逻辑有效，但存在多处严重语法错误、异常处理粗糙、类型不安全及维护性问题，需要重构核心函数并修复截断代码才能达到生产级别。

🔴 **错误处理**: 3/10
  - 多处使用 `except:` 裸捕获，未指定异常类型（如 `except json.JSONDecodeError, TypeError`），可能掩盖意外错误
  - `except Exception as e` 后仅打印错误，未处理或重试，可能导致数据不一致
  - `_build_prompt` 中直接访问 `p.identity` 未检查 `p` 是否为 None，导致 AttributeError
  → 为所有 `try` 块指定明确的异常类型，避免裸 except; 在 `_build_prompt` 中增加 `p` 为 None 时的默认处理

🟡 **类型安全**: 4/10
  - 类型提示使用 `object`（如 `name_map: dict[str, object]`），未利用具体类 `CharacterProfile`
  - `canonical_map` 和 `old_to_canonical` 类型未声明，降低可读性与静态检查效果
  - `json.loads` 结果未加类型标注，返回类型为 `Any`
  → 使用 `from typing import Dict, List` 并声明具体类型，如 `Dict[str, CharacterProfile]`; 为关键变量添加类型注解，并启用 pyright/mypy 静态检查

🟡 **架构**: 5/10
  - `resolve_aliases` 函数过长（超过200行），职责过多，可拆分为多个步骤函数
  - 硬编码魔术数字 3000（bible 截断长度），应作为参数或配置
  - 无用导入 `from models import Book`（在 `_analyze_name_chapter_overlap` 中）
  → 将主函数拆分为 `collect_names`, `build_prompt`, `call_llm`, `update_db` 等独立函数; 将截断长度等常量提取到配置类或模块顶部

🟡 **安全**: 6/10
  - `_build_prompt` 中直接拼接用户可控数据（名字、身份等）到 prompt，存在 prompt 注入风险（虽限于数据库内部数据）
  - `call_llm_json` 的输出未做严格过滤，可能生成恶意 JSON 导致破坏数据库
  - 数据库删除操作（`session.delete(p)`）未记录日志，难以追溯
  → 对 prompt 中的角色名、别名等字段进行转义或限制长度; 对 LLM 返回的 JSON 进行 Schema 校验（如使用 pydantic），拒绝不合规结果

🟡 **可维护**: 4/10
  - 使用 `print` 输出调试信息，应替换为 `logging` 模块
  - 大量内联 JSON 解析（`json.loads`）重复出现，可抽取为辅助函数
  - 代码格式化不一致（如缩进、空行），缺少注释说明关键逻辑
  → 统一使用 `logging.getLogger(__name__)` 进行日志输出; 创建 `safe_json_loads` 函数封装异常处理

#### core/hybrid_retriever.py (评分: 5/10)
> 代码实现了基本的混合检索功能，但缺乏错误处理、类型保护和安全校验，架构耦合度高，可维护性一般。

🔴 **错误处理**: 1/10
  - 所有外部调用（vs.search, ks.init_fts, ks.keyword_search）均未捕获异常，可能导致未处理的崩溃。
  - 未对输入参数（如 query, where）进行合法性校验，空查询或无效 where 可能引发意外错误。
  → 为每个外部调用添加 try-except 块，记录错误日志并返回空列表或重试。; 在方法入口处验证参数：检查 query 非空、where 为合法字典（如果提供）等。

🟡 **类型安全**: 6/10
  - 合并 scores 字典时假设 r['id']、r['document']、r['metadata'] 始终存在，但未做类型或键存在性检查，可能因外部返回结构变化导致 KeyError。
  - 内部 scores 字典的值结构混合了字符串和字典，但未使用数据类或 TypedDict 强制类型，易出错。
  → 在访问字典键前使用 .get() 或检查键是否存在，并处理缺失情况。; 考虑使用 dataclass 或 TypedDict 定义结果类型，提升类型安全性和可读性。

🟡 **架构**: 5/10
  - HybridRetriever 直接依赖 vs 和 ks 模块的具体函数，无法替换为其他搜索后端（如不同向量数据库或全文检索引擎），缺乏抽象层。
  - 混合搜索的权重和排序策略硬编码在 search 方法中，不利于扩展其他融合算法（如 RRF 的不同变体）。
  → 将向量搜索和关键词搜索抽象为协议或抽象基类，通过依赖注入传入 HybridRetriever，提高可测试性和可替换性。; 提取评分融合策略为独立类或函数，允许通过配置或参数切换不同融合方式。

🟡 **安全**: 5/10
  - where 参数直接透传给 vs.search，如果 vs.search 未做安全处理（如未使用参数化查询），可能引入注入风险。
  - ks.keyword_search 的 query 参数可能被恶意构造，若底层拼接 SQL 或命令则存在注入漏洞。
  → 审查 vs.search 和 ks.keyword_search 的实现，确保使用参数化查询或输入转义。; 对 where 参数进行白名单验证，仅允许特定键值对，限制嵌套深度。

🟡 **可维护**: 6/10
  - search 方法中分数计算逻辑重复（两次 1.0/(1.0+i)），未提取为辅助函数。
  - search_character、search_event、search_scene 硬编码了搜索前缀和权重，但未复用 search 的全部参数（如 n_results、vector_weight），导致行为不一致。
  → 提取计算排名分数的公共方法，如 _rank_score(index, weight)。; 在 search_character 等方法中允许调用者覆盖 n_results 和权重参数，或使用默认值且保持一致性。

#### core/ingest.py (评分: 6/10)
> 代码功能完整，但错误处理薄弱，存在路径遍历安全风险，架构耦合向量库，可维护性中等，需要加强异常处理、安全检查和模块化设计。

🟡 **错误处理**: 5/10
  - read_text() 默认编码为 utf-8，若文件不是 utf-8 编码，会出现 UnicodeDecodeError，未捕获
  - 数据库操作失败（如约束冲突、连接超时）未处理，commit 失败导致数据不一致
  - vs.add_documents 未处理异常，若向量数据库不可用，整个请求失败且不回滚数据库操作
  → 使用 try-except 捕获 UnicodeDecodeError，并支持其他常见编码（如 gbk）; 在数据库操作外层增加 try-except，失败时回滚事务并记录日志

🟢 **类型安全**: 8/10
  - 函数返回值类型为 dict，但文档注释未指明各字段类型
  - 内部变量如 raw_chapters 类型为 list[tuple[str, str]]，但未显式标注
  → 使用 typing 注解，如 from typing import List, Tuple; 为 ingest 函数添加完整类型签名

🟡 **架构**: 5/10
  - ingest 函数直接耦合向量数据库，违反单一职责与可测试性
  - 数据库操作循环内多次 flush()，性能较差，应批量提交
  - 章节检测逻辑硬编码，不易扩展新格式
  → 将向量索引解耦为回调或事件，由上层调用决定; 收集所有 Chapter 对象后一次性 s.add_all() 并最后 commit

🟡 **安全**: 4/10
  - title = path.stem 可能包含路径遍历字符（如 '../'），用于 output_path 时可能写入任意目录
  - 未对文件名做任何消毒，可能导致恶意文件写出到敏感位置
  - 未限制文件大小，大文件可能导致内存溢出
  → 对 title 进行路径安全检查，如仅保留合法字符，或使用 uuid 作为输出目录名; 对 path.stem 进行白名单过滤，拒绝包含 '../' 或绝对路径的内容

🟡 **可维护**: 6/10
  - CHAPTER_PATTERNS 硬编码在模块内部，修改需改源码
  - 章节检测算法基于行匹配，对混合格式（如 Markdown 标题）可能误判
  - 缺少日志记录，调试困难
  → 将 CHAPTER_PATTERNS 定义为模块级变量或从外部配置加载，便于扩展; 增加更智能的章节识别逻辑，或提供回调机制让调用方自定义

#### core/keyword_search.py (评分: 5/10)
> 功能基本完整，但错误处理、连接管理存在明显缺陷，FTS5 查询转义不够健壮，需改进异常处理和安全性。

🔴 **错误处理**: 3/10
  - 数据库操作（_get_db、init_fts、rebuild_fts、keyword_search）均未捕获 sqlite3 异常，可能导致程序崩溃
  - 未使用上下文管理器（with 语句）管理数据库连接，手动 close 易因异常而泄露连接
  - rebuild_fts 中的 DELETE+INSERT 未包裹在事务中（虽有 commit，但缺少回滚逻辑）
  → 使用 try/except 捕获 sqlite3.OperationalError 等异常，至少打印日志或返回空结果; 改用 with 语句（with _get_db() as conn:）自动管理连接，或使用 connection context manager

🟢 **类型安全**: 7/10
  - book_id 参数虽已标注 int，但未在函数内验证是否实际为 int；若传入 None 或非 int 会导致类型错误
  - _escape_fts_query 接受 str，但未处理非字符串输入（如 None）
  → 在函数入口对 book_id 和 query 进行类型检查或转换（如 int(book_id) 或强制 str(query)）; 在 _escape_fts_query 中添加 if not isinstance(query, str): return '' 的保护

🟡 **架构**: 6/10
  - 每次调用数据库函数都创建新的 SQLite 连接，频繁打开关闭开销大
  - rebuild_fts 使用 DELETE + INSERT 而非 INSERT OR REPLACE 或更高效的重建方式
  - config.DB_DIR 未在本文件定义，依赖外部配置，缺乏文档或默认值
  → 考虑使用连接池（如 sqlite3 的 shareable connection）或单例模式复用连接; 使用 INSERT OR REPLACE 或先 DROP TABLE 再 CREATE VIRTUAL TABLE 以完全重建索引

🟡 **安全**: 6/10
  - _escape_fts_query 仅对空格分割的 token 加双引号，未转义 token 内部的双引号，可能导致 FTS5 语法错误或注入（如用户输入包含双引号）
  - 缺少对查询长度的限制，可能引发拒绝服务（如超长查询字符串）
  → 增强转义：将每个 token 中的双引号替换为两个双引号（FTS5 标准转义）后再加外层双引号; 在 keyword_search 中对 query 长度做限制（如 MAX_QUERY_LENGTH=200）

🟢 **可维护**: 8/10
  - 注释中存在拼写错误（whitespace 应为 whitespace，unicode61 应为 unicode61）
  - config.DB_DIR 的依赖未显式声明，维护者需额外查找
  - rebuild_fts 中字段名 character_table 与 FTS 表定义的 characters 列名不一致，易造成混淆
  → 修正注释拼写; 添加 docstring 说明依赖的外部配置

#### core/llm.py (评分: 7/10)
> 整体实现稳健，但导入规范、错误处理细节和代码可维护性方面存在明显改进空间。

🟢 **错误处理**: 7/10
  - QuotaExceeded 异常在 call_llm 中未捕获，可能导致未处理的异常终止调用链
  - 429 重试后再次调用 wait_if_needed，可能造成双重等待或速率记录不匹配
  - 所有 retry 失败后返回空字符串，掩盖了错误，不利于上层调试
  → 在 call_llm 中捕获 QuotaExceeded，对于每日配额耗尽可直接抛出，若为临时限制则等待后重试; 将 429 处理逻辑独立，标记当前尝试已使用 wait_if_needed，避免循环内重复调用

🟡 **类型安全**: 6/10
  - 函数参数和返回值缺少类型注解，降低代码可读性和 IDE 支持
  - RateLimiter 类方法无类型提示
  → 为 call_llm、call_llm_json 等函数添加返回类型注解（如 -> str）; 为 RateLimiter 的方法添加参数和返回值类型提示

🟢 **架构**: 7/10
  - import re 出现在文件中部（约 160 行），违反 PEP8 导入规范
  - 全局 _limiter 使用 __import__('os') 动态导入，可读性差且可能导致 lint 问题
  - call_llm 强依赖 config 模块和全局 _limiter，不利于单元测试和依赖注入
  → 将所有 import 移到文件顶部，并合并重复的 import re; 在文件顶部直接 import os，然后使用 os.getenv

🟢 **安全**: 8/10
  - config.OPENAI_BASE_URL 未做合法性校验，可能被恶意配置为任意地址
  - httpx timeout=600秒，可能导致资源长时间占用（通常非安全但可能被利用于资源耗尽）
  → 启动时验证 BASE_URL 格式，限制为 HTTPS 知名 API; 将超时调整至合理范围（如 120秒），或根据模型响应时间动态调整

🟡 **可维护**: 6/10
  - _try_close_brackets 函数逻辑复杂且包含多个嵌套修复步骤，难以理解
  - call_llm_json 内使用 re.sub 和多次 json.loads 进行暴力修复，性能差且维护成本高
  - 存在两个 import re（文件顶部和函数内部），容易混淆
  → 考虑使用第三方库（如 json5、demjson）解析鲁棒性 JSON，替代手动修复; 若坚持手动修复，应抽取为独立函数并添加详细注释

#### core/prompts.py (评分: 5/10)
> 代码结构简单但存在严重路径遍历安全漏洞，且错误处理和替换逻辑有缺陷，需优先修复安全与鲁棒性问题。

🟡 **错误处理**: 4/10
  - load_prompt: 未处理 IO 错误（如无权限读取文件、磁盘故障），可能抛出未捕获的异常。
  - load_prompt: 模板变量替换的 fallback 仅匹配 `{word}` 模式，但 Python format 支持 `{key:format}`、`{0}` 等语法，fallback 可能遗漏或错误处理。
  - list_prompts: `rglob` 无异常处理，若 prompts 目录不可访问或包含无效条目会崩溃。
  → 在文件读取时捕获 `OSError` 并给出友好错误信息或转换为自定义异常。; 使用 `string.Formatter` 的子类实现安全的变量的缺失替换，替代异常+正则的 fallback。

🟢 **类型安全**: 8/10
  → 可考虑对 `kwargs` 的值进行类型限制（如仅允许 str）来避免 format 时隐式转换问题。

🟢 **架构**: 7/10
  - load_prompt 中根据异常类型切换替换逻辑，导致两种行为不一致（format 规则 vs 正则规则）。
  → 统一使用自定义 Formatter（如继承 string.Formatter 并重写 get_field 返回空字符串）来避免异常分支。

🔴 **安全**: 2/10
  - 严重路径遍历漏洞：`name` 参数未做检查，可包含 `../` 导致读取任意目录下 `.txt` 文件，如 `load_prompt('../../etc/passwd')` 可读取 `prompts/../../etc/passwd.txt`。
  → 验证 `name` 不包含路径分隔符（如 `/`、`\`），或仅允许字母数字和下划线。; 使用 `Path.resolve()` 并确保解析后的路径在 `PROMPTS_DIR` 下。

🟡 **可维护**: 6/10
  - re 模块在异常处理分支内导入，不符合 Python 导入惯例，且每次异常时重复导入。
  - 没有日志记录，难以诊断问题。
  - `load_prompt` fallback 逻辑复杂，依赖正则内部实现，可读性差。
  → 将 `import re` 移至文件顶部。; 添加适当的日志（如 warning 或 debug）用于追踪模板加载状况。

#### core/vector_search.py (评分: 7/10)
> 代码功能正确且简洁，但错误处理不完善、全局状态设计存在风险、可配置性差，建议增强健壮性和可测试性。

🟡 **错误处理**: 6/10
  - add_documents 中批处理失败仅打印警告，无重试或回滚机制，可能导致部分数据丢失
  - delete_where 捕获异常后完全静默，调用者无法得知操作是否成功
  - is_available 返回 None 时语义模糊，调用方需要额外判断 True/False
  → 为 add_documents 添加重试逻辑（如指数退避）或事务性回滚; delete_where 至少应打印警告日志，或返回布尔值指示成功/失败

🟢 **类型安全**: 8/10
  - get_collection 返回类型未明确标注（实际为 Optional[Collection]），可能导致调用者未检查 None 而出错
  - add_documents 中 batch_size 参数类型为 int | None，但内部使用 bs 做切片，可能引发 TypeError（若意外传入非 int）
  → 添加明确返回值类型注解，如 -> Optional[chromadb.Collection]; 对 batch_size 进行类型校验或使用默认值替代 None

🟡 **架构**: 6/10
  - 使用全局变量 _client 和 _embed_fn 作为单例，在多线程环境中可能产生竞态条件
  - 批处理大小和延迟硬编码为模块常量，无法根据不同模型或硬件灵活调整
  - 依赖全局 config 和 OllamaEmbedding，耦合度高，不利于单元测试
  → 考虑使用类封装状态，或引入 threading.Lock 保护全局资源; 将 _EMBED_BATCH_SIZE 和 _EMBED_DELAY 改为可配置参数（如通过函数参数或配置类）

🟢 **安全**: 7/10
  - 异常信息通过 print 直接输出，可能泄露内部路径或数据库信息（如在生产环境）
  - 没有对 where 过滤条件进行校验，可能存在注入风险（若 where 来自用户输入）
  → 使用 logging 模块替代 print，并配置合适的日志级别，避免敏感信息暴露; 对 where 参数进行白名单校验或使用参数化查询方式

🟡 **可维护**: 6/10
  - 全局状态和硬编码常量使代码难以扩展和维护
  - delete_where 中完全忽略异常，维护者难以定位删除失败原因
  - add_documents 和 search 中的错误处理不一致（一个打印警告，一个返回空列表）
  → 统一错误处理策略：所有公共方法应抛出或返回明确的错误状态; 为批处理参数提供外部配置入口（如环境变量或构造函数参数）

#### genres/__init__.py (评分: 10/10)
> 模块设计简洁合理，从JSON加载配置避免硬编码，无安全或维护问题。

🟢 **错误处理**: 10/10

🟢 **类型安全**: 10/10

🟢 **架构**: 10/10

🟢 **安全**: 10/10

🟢 **可维护**: 10/10

#### genres/base.py (评分: 7/10)
> 代码结构清晰，功能基本完整，但在错误处理、配置验证和可扩展性方面存在不足，建议加强异常管理和数据验证。

🟡 **错误处理**: 5/10
  - 模板文件缺失时直接抛出 FileNotFoundError，没有提供上下文友好的错误信息
  - str.format() 未捕获 KeyError，当模板字符串缺少占位符或参数缺失时会崩溃
  - JSON 配置解析异常（如文件损坏）未被捕获，会向上传播 json.JSONDecodeError
  → 在模板读取和 format 时使用 try-except，转化为自定义异常并附加详细信息; 在 Genre.__init__ 中验证必需配置键，抛出明确的配置错误

🟢 **类型安全**: 7/10
  - 部分属性（如 name、description）直接使用 self._config[key]，当键缺失时会抛出 KeyError 而非类型安全错误
  - get_adapt_prompt 和 get_script_prompt 的返回值依赖于 format 成功，类型标注为 str 但可能抛出异常
  - 未对输入的 bible、portraits 等参数进行类型检查或格式化安全处理
  → 使用 .get() 并设置类型默认值，或使用类型提示和运行时类型检查; 在 format 前验证模板字符串中所需的占位符是否存在，避免意外 KeyError

🟡 **架构**: 6/10
  - 模板文件路径硬编码为 PROMPTS_DIR，不利于测试和部署
  - 模板文件名与 genre name 绑定，若 name 包含特殊字符可能导致文件系统错误
  - _adapt_template 和 _script_template 是实例缓存，但 registry 中的 Genre 实例是全局单例，破坏了测试隔离性
  → 将 PROMPTS_DIR 设为可配置参数（如环境变量或构造函数参数）; 使用更健壮的模板定位策略（如文件名使用 slugify 后的 name）

🟢 **安全**: 8/10
  - bible、portraits 等用户输入直接注入模板字符串，若包含 Python 格式化语法（如大括号）会引发 ValueError，但无直接注入执行风险
  - 未对输入字符串中的大括号进行转义，可能导致模板渲染异常或信息泄露
  - 文件读取未设置大小限制，恶意大文件可能导致内存耗尽（但文件受控）
  → 对输入参数中的大括号进行转义（如替换 {{ 和 }}），避免 format 异常; 考虑使用安全模板引擎（如 Jinja2 的沙箱模式）替代 str.format

🟢 **可维护**: 7/10
  - 缺少对每个属性的文档注释，读者难以快速理解配置字段含义
  - to_dict 方法手工映射键名，如果新增属性需要同步修改，容易遗漏
  - 未提供单元测试，难以保证重构安全性
  → 为每个属性添加文档字符串，说明来源和预期格式; 利用 __annotations__ 或 dataclass 的 asdict() 自动生成 to_dict

#### models/__init__.py (评分: 9/10)
> 文件结构清晰，导出合理，仅在架构封装性上略有改进空间

🟢 **错误处理**: 10/10

🟢 **类型安全**: 8/10
  - `__all__` 列表中的名称均为字符串，未使用类型注解，但通常可接受
  → 考虑为 `__all__` 添加类型注解，例如 `__all__: list[str] = [...]`

🟢 **架构**: 8/10
  - 导出了 `engine` 和 `Base`，这些通常是内部实现细节，暴露后可能导致模块耦合
  → 考虑将 `engine` 和 `Base` 从 `__all__` 中移除，仅通过 `init_db` 等函数间接使用

🟢 **安全**: 10/10

🟢 **可维护**: 9/10
  - 文件较为简洁，但未明确标注每个导入模块的来源
  → 为每个 `from .xxx import ...` 添加简短注释说明模块用途（可选）

#### models/base.py (评分: 6/10)
> 代码简洁但错误处理薄弱，全局状态管理不利于测试，需改进日志和初始化策略。

🟡 **错误处理**: 5/10
  - init_db 中捕获所有异常后仅用 print 输出，缺少日志记录；get_kv/set_kv 未处理数据库操作异常
  - fallback 到 create_all 可能掩盖真正的迁移错误，且 create_all 不会更新已有表结构
  → 使用 logging 替代 print 记录错误; 在 get_kv/set_kv 中添加异常处理（如捕获 SQLAlchemyError）并适当重试或告知调用者

🟢 **类型安全**: 7/10
  - get_kv/set_kv 中 value 参数和返回值均为 str，但未校验 key 类型
  - set_kv 中将任意值强制 str()，可能导致意外转换
  → 可添加类型注解和运行时类型检查（如 isinstance）; 明确声明仅支持字符串键值对，或支持序列化

🟡 **架构**: 6/10
  - 全局 engine 和 sessionmaker 在模块加载时创建，不易于测试和配置切换
  - init_db 与模块级 engine 分离，但外部仍可直接使用未初始化的 engine 执行查询
  - get_kv/set_kv 函数耦合了具体的 KV 模型，不利于扩展或替换存储后端
  → 使用懒加载初始化 engine，或通过工厂模式提供 session; 将 KV 操作抽象为独立服务类，便于测试

🟢 **安全**: 8/10
  - 无直接安全漏洞，但 print 输出可能在生产环境暴露敏感信息（如连接错误细节）
  - config 模块中 DATABASE_URL 可能包含明文密码，但不在本文件范围内
  → 使用 logging 模块并配置过滤敏感信息; 建议通过环境变量或密钥管理服务加载数据库凭证

🟢 **可维护**: 7/10
  - init_db 函数混合了迁移和创建两种初始化策略，职责单一性不足
  - 全局模块导入顺序依赖（config 在基类前导入）可能引发循环导入
  → 将初始化逻辑拆分为独立模块，如 db_init.py; 明确文档说明导入顺序

#### models/book.py (评分: 7/10)
> 模型定义基本正确，但存在时间戳默认值陷阱、缺少外键约束及类型精度不足等可改进点

🟡 **错误处理**: 6/10
  - 模型定义中未包含任何异常处理或验证逻辑
  → 在业务逻辑层增加输入验证和异常捕获，模型本身可不处理

🟡 **类型安全**: 6/10
  - String类型缺少长度限制，可能导致数据库兼容性问题
  - default=datetime.now 在类定义时只计算一次，导致所有新记录使用相同时间戳
  → 指定String长度，如 title = Column(String(255)); 将 default 改为 callable，如 default=datetime.utcnow

🟢 **架构**: 7/10
  - Book 与 Chapter 之间未定义外键约束，引用完整性靠应用层保证
  - BookBible 的 book_id 虽 unique 但无外键
  → 在 book_id 上使用 ForeignKey('books.id'); 考虑添加 relationship 以简化关联查询

🟢 **安全**: 8/10
  - character_table 等字段存储 JSON 文本，存在潜在的 JSON 注入风险（低）
  → 存储前校验 JSON 合法性，或使用 JSON 类型字段（如 SQLAlchemy 的 JSON 类型）

🟢 **可维护**: 7/10
  - 缺少文档字符串和类型注解
  - 部分字段默认值为空字符串或列表，但类型是 Text，语义不明确
  → 添加类和方法 docstring; 使用类型注解标注字段含义

#### models/bridge.py (评分: 5/10)
> 模型定义基本完成功能，但缺乏正确的数据库约束、类型安全、外键关系和可维护性设计，建议重构以遵循规范化和最佳实践。

🔴 **错误处理**: 3/10
  - 未定义任何数据校验逻辑，非法或缺失数据不会被捕获
  - 默认值仅适用于创建时，更新操作无保护
  - created_at 使用 datetime.now 为函数调用时固定值，而非每次创建时动态获取（应为 default=datetime.utcnow）
  → 在模型层增加 @validates 装饰器校验字段完整性（如 book_id、location_name 非空）; 考虑使用 SQLAlchemy 的事件监听或 before_insert 钩子进行数据清洗

🟡 **类型安全**: 4/10
  - String 字段未指定长度，数据库默认可能为 VARCHAR(255) 或不一致，且无业务长度约束
  - Integer 字段缺少可空或默认值约束（book_id、episode 等），插入时可能意外为空
  - importance 字段为 String 但无枚举约束，可写入任意值
  → 为所有 String 字段添加明确长度（如 location_name VARCHAR(200)）; 为 book_id 和 episode 添加 nullable=False 并考虑添加 CheckConstraint('book_id > 0')

🟡 **架构**: 5/10
  - 桥接表缺少与主表的外键关系，仅靠命名约定关联，数据库无完整性保证
  - SceneCharacter 与 SceneProp 重复定义 location_name+episode 组合，但未定义联合唯一索引，可能产生重复记录
  - book_id 字段存在但无对应 Book 模型的外键，不符合规范化设计
  → 添加 ForeignKeyConstraint 引用 VisualLocation、CharacterProfile、VisualProp 和 Book 表; 为 (location_name, episode, character_name) 和 (location_name, episode, prop_name) 添加 UniqueConstraint

🟡 **安全**: 6/10
  - 无输入过滤或转义机制，若通过原始 SQL 或 ORM 注入（尽管 ORM 通常安全，但 Text 字段可能存储 XSS 内容）
  - 字段默认值为空字符串，但未限制长度，可能遭受大数据量攻击
  - created_at 使用 datetime.now 而非 UTC，可能引发时区相关歧义或日志注入
  → 在应用层对所有用户输入进行清洗和长度验证，特别是在前端展示时转义 HTML; 为 Text 字段添加最大长度约束（如 Text(5000)）或使用后台校验

🟡 **可维护**: 5/10
  - 两个桥接表结构高度相似，存在重复代码（book_id、location_name、episode、notes、created_at）
  - 字段注释散落在代码中，未使用文档字符串或一致的元数据
  - 缺少清晰的命名规范，例如 location_name 与 episode 组合的语义不直观（应使用 location_episode 或直接外键）
  → 抽取公共基类（如 BaseBridge）包含 book_id、location_name、episode、notes、created_at 等共用字段; 将场景特有状态字段（state, outfit, makeup等）考虑合为一个 JSON 字段（如 attributes）以提升扩展性

#### models/character.py — ❌ Failed to parse JSON

#### models/kv.py (评分: 7/10)
> 代码简洁但缺乏关键字段约束和错误处理机制，建议完善类型定义与输入验证

🟡 **错误处理**: 6/10
  - 缺少数据库层面的约束处理（如唯一性、非空等）
  → 为key列添加unique约束（已通过主键实现），建议显式设置nullable=False; 考虑在模型层增加数据验证逻辑

🟢 **类型安全**: 7/10
  - key列未指定长度，可能导致索引性能问题或超长键写入
  → 为key列添加长度限制，如String(255)

🟢 **架构**: 8/10
  - 作为简单KV存储，架构合理，无重大问题
  → 无

🟢 **安全**: 7/10
  - value字段未做输入过滤，可能存储恶意内容
  → 在业务层对value进行必要的转义或验证; 考虑使用Blob或Binary类型存储敏感数据

🟢 **可维护**: 8/10
  - 缺少docstring或注释说明默认值及使用场景
  → 增加类的文档字符串，描述字段用途和约束; 考虑添加索引注释

#### models/script.py (评分: 7/10)
> 代码整体清晰，但存在时间戳默认值错误、类型不严谨、缺乏关系和约束等常见问题，改进后可提升健壮性和可维护性。

🟡 **错误处理**: 5/10
  - created_at 列的 default=datetime.now 在类定义时执行，导致所有记录共享同一个时间戳（仅在解释器加载时计算一次）
  - 缺少对输入数据长度的校验（如 title 字段为 String 但未指定长度，可能超过数据库限制）
  - 无异常处理机制，模型操作（如保存）的错误需由调用方处理
  → 将 default 改为 datetime.utcnow（无括号）或 datetime.now（无括号）以在插入时动态生成时间; 为 String 类型字段指定长度（如 title = Column(String(255))）

🟢 **类型安全**: 7/10
  - is_fixed 字段使用 Integer 表示布尔语义（1/0），但未使用 Boolean 类型，类型表达不准确
  - status 字段为 String，但未限制有效值范围（如 'draft'/'published' 等），存在非法状态风险
  - word_count 字段存储整数，但未与 content 字段关联校验，可能手动输入错误值
  → 将 is_fixed 改为 Column(Boolean, default=False) 并相应调整注释; 使用 enum 或 CheckConstraint 限制 status 字段的有效值（如 Enum('draft','published')）

🟢 **架构**: 7/10
  - 缺少外键关联，book_id 和 episode 等字段仅作为普通整数字段，未与 Book 等主表建立关系
  - 未定义关系（relationship）来简化关联查询，需手动编写 JOIN
  - episode_outlines 表的 raw_content 列与已有字段（如 core_event）表示相似内容，可能造成数据冗余
  → [新增外键约束] book_id = Column(Integer, ForeignKey('books.id'))，并添加 relationship 方便 ORM 访问; 定义关系属性，如 book = relationship('Book', backref='scripts')

🟢 **安全**: 8/10
  - 部分字段（如 content）使用 Text 类型，若直接渲染未转义可能存在 XSS 风险，但模型层本身不涉及输出
  - 未对敏感字段（如用户私密信息）做加密存储假设，当前模型中无敏感字段
  → 在展示层对 Text 类型字段进行 HTML 转义（如使用 Jinja2 的 escape 过滤器）; 若后续引入用户数据，应使用加密库对敏感字段进行处理

🟡 **可维护**: 6/10
  - 字段命名中 episode_outlines 使用了单数形式（core_event、opening_hook），但 table 名使用了复数，命名不一致
  - 缺少模型间的文档说明（如 book_id 指向哪个表，episode 的编号范围等）
  - raw_content 注释为“兼容旧数据”，暗示存在历史遗留问题，未清理冗余字段
  → 统一命名风格（如表名用复数，列名用单数；核心事件建议使用 core_event 等保持连贯）; 添加 docstring 或表注释说明各字段的用途、约束及与其他模型的关系

#### models/storyboard.py (评分: 6/10)
> 模型结构清晰，但缺失类型约束、索引及状态校验，存在轻微类型安全和维护性问题，需完善字段定义与验证。

🟡 **错误处理**: 5/10
  - 缺少字段级别的有效性验证（如 shot_id 应为正整数）
  - asset_status 未限制为枚举值，可能导致非法状态
  → 添加自定义验证或使用 SQLAlchemy 的 validator 装饰器检查 shot_id 为正整数; 使用 enum 类型或至少添加 CHECK 约束限制 asset_status 的允许值

🟡 **类型安全**: 6/10
  - String 类型未指定长度，可能导致数据库兼容性问题
  - JSON 字段使用 Text 存储，而非更精确的 JSON 类型
  - updated_at 的 default=datetime.now 不会自动更新，应使用 onupdate=datetime.now
  → 为所有 String 字段指定合理长度（如 String(255)）; 若数据库支持，使用 sqlalchemy.dialects.postgresql.JSON 或 sqlalchemy.JSON

🟢 **架构**: 7/10
  - asset_status 使用字符串而非枚举，状态管理不严谨
  - JSON 字段（sound_effects, asset_links, meta_info）使用 Text 而非 JSON 类型，解析时无类型保证
  → 定义 enum 类或使用 SQLAlchemy Enum 列类型存储 asset_status; 迁移至 JSON 列类型以利用数据库原生 JSON 校验和查询能力

🟢 **安全**: 8/10
  - JSON 字段存储后若程序反序列化时使用 eval 或不当解析，可能有注入风险
  - 未对字符串长度做限制，可能造成存储过大内容
  → 反序列化 JSON 字段时始终使用 json.loads() 而非 eval; 为 Text 字段添加长度限制或应用层截断

🟢 **可维护**: 7/10
  - 缺少索引定义，查询 book_id + episode 或 shot_id 时可能性能下降
  - 字段数量较多，但缺乏分组或文档化说明
  → 添加复合索引 (book_id, episode) 及单独索引 shot_id; 使用 __table_args__ 定义索引，并在字段注释中简要说明用途

#### models/visual.py (评分: 7/10)
> 模型设计清晰合理，但存在类型安全缺失、字段未约束、缺少外键和索引等常见 ORM 问题，建议统一字段规范并加强数据完整性。

🟡 **错误处理**: 6/10
  - 未定义 onupdate 参数，updated_at 仅创建时设置，不自动更新
  - 未对模型字段进行输入验证，如 importance 字段接受任意字符串
  → 为 updated_at 添加 onupdate=datetime.now 以确保每次更新时自动修改; 可以使用 SQLAlchemy 的 CheckConstraint 限制 importance 的枚举值

🟡 **类型安全**: 5/10
  - JSON 字段（如 time_periods, episodes 等）使用 Text 存储，缺乏 JSON 结构校验
  - 多个 String 字段未指定长度（如 name, category），可能导致数据库拒绝或截断
  - importance 字段类型为 String 但无枚举约束
  → 改用 JSON 类型（如果数据库支持）或自定义 TypeDecorator 序列化/反序列化; 为所有 String 字段显式指定长度，如 String(100)

🟢 **架构**: 7/10
  - 缺乏外键约束（如 book_id），数据完整性由应用层保证
  - 缺少联合唯一约束或索引（如 book_id + name）
  - created_at 和 updated_at 在多个模型中重复，未抽象为 Mixin
  → 为 book_id 添加 ForeignKey 引用到书籍表; 根据需要添加唯一约束或索引，如 (book_id, name) 唯一

🟢 **安全**: 8/10
  - 未对用户输入进行长度或格式校验，可能存储不合理数据
  - 未对 JSON 字段做安全解析，但 SQLAlchemy ORM 已防止 SQL 注入
  → 使用 SQLAlchemy 的验证机制（如 @validates decorator）或自定义类型来过滤输入

🟢 **可维护**: 7/10
  - 字段命名不一致：VisualEraSpec 中 timeline_start 和 timeline_end 为单独字段，其他模型则用 time_period String
  - 视觉提示词字段（visual_prompt_*）在多个模型中重复，可通过抽象减少冗余
  → 统一时间表示方式，或使用时段模型关联; 考虑定义 PromptMixin 包含 visual_prompt_en/zh 等字段，减少重复

#### run_pipeline.py (评分: 5/10)
> 管线基本可用但错误处理不一致、类型安全缺失、架构耦合度高，需重构以提升健壮性和可维护性

🟡 **错误处理**: 5/10
  - step() 函数对异常捕获后只打印并重新抛出，导致后续未捕获时管线中断，不如统一处理为可跳过或记录而不中断
  - 部分步骤（如 era_scan、props、locations、makeup）的异常被静默忽略（仅打印 warning），可能隐藏关键错误
  - Storyboard 步骤使用 step() 函数，异常会导致整个管线终止，与其他步骤处理方式不一致
  → 统一管线步骤的错误处理策略：关键步骤失败应终止，非关键步骤应记录错误并继续; 为 step() 添加可选参数 `optional=False`，非关键步骤失败时返回 None 而非抛出异常

🟡 **类型安全**: 4/10
  - 函数参数和返回值均无类型注解，易造成运行时类型错误
  - `Session()` 直接作为参数传入 `resolve_aliases(BOOK_ID, Session())`，但函数签名未声明参数类型
  - `SceneSetupAgent` 的 `run_era_scan` 等方法未标注返回类型
  → 为所有函数添加完整类型注解，包括参数和返回值; 使用 `from typing import ...` 明确类型

🟡 **架构**: 5/10
  - 管线步骤顺序硬编码，扩展性差（如要插入新步骤需要修改主流程）
  - Episode 只处理了 1-3 集，但常量 FULL_EPISODE_COUNT=6 表示目标为6集，逻辑矛盾
  - 状态检查逻辑分散，依赖数据库状态和文件存在性，耦合度高
  → 引入管线配置或管线定义类，将步骤顺序和参数集中管理; 统一使用 FULL_EPISODE_COUNT 决定生成集数，避免硬编码范围

🟢 **安全**: 8/10
  - 虽然无明显注入漏洞，但硬编码的路径 'outputs/神农架历险记/' 包含 Unicode 字符，在部分文件系统下可能存在问题
  - 未对生成的输出文件进行权限或内容安全审查（尽管代码中无用户输入）
  - 数据库连接字符串（如果有）未暴露，但注意不要在生产中硬编码敏感信息
  → 使用纯 ASCII 路径或通过系统 locale 处理 Unicode 路径; 确保输出目录权限合理，避免写入到服务器根目录

🟡 **可维护**: 4/10
  - 代码中混杂了大量调试打印和状态提示，影响可读性
  - bible_exists 的判断逻辑复杂且存在冗余（第一次查不到再查第二次），不易维护
  - 多处重复的硬编码字符串 '神农架历险记'，应定义为常量
  → 将管线编排逻辑抽离为 Pipeline 类，分离关注点; 所有字符串常量集中定义，避免重复

---
## B. 提示词质量审查

| 文件 | 大小 | 完整性 | 一致性 | LLM可靠性 | 可维护 | 总分 |
|------|------|--------|--------|----------|--------|------|
| prompts/alias_resolve.txt | 1266B | 7 | 8 | 7 | 8 | **7.5** |
| prompts/genres/manhua.json | 397B | 6 | 8 | 5 | 7 | **6** |
| prompts/genres/manhua_adapt.txt | 866B | 7 | 6 | 5 | 8 | **6** |
| prompts/genres/manhua_rules.txt | 0B | 1 | 1 | 1 | 3 | **1** |
| prompts/genres/manhua_script.txt | 639B | 8 | 9 | 7 | 8 | **8** |
| prompts/genres/movie.json | 392B | 8 | 9 | 7 | 8 | **8** |
| prompts/genres/movie_adapt.txt | 1067B | 8 | 9 | 8 | 8 | **8** |
| prompts/genres/movie_rules.txt | 0B | 1 | 1 | 1 | 1 | **1** |
| prompts/genres/movie_script.txt | 618B | 6 | 5 | 5 | 7 | **6** |
| prompts/genres/short_drama.json | 1220B | 9 | 8 | 9 | 8 | **8** |
| prompts/genres/short_drama_adapt.txt | 692B | 7 | 8 | 7 | 9 | **7** |
| prompts/genres/short_drama_rules.txt | 0B | 1 | 1 | 1 | 2 | **1** |
| prompts/genres/short_drama_script.txt | 773B | 6 | 3 | 4 | 7 | **4** |
| prompts/genres/tv_series.json | 399B | 8 | 9 | 7 | 8 | **8** |
| prompts/genres/tv_series_adapt.txt | 1118B | 8 | 9 | 7 | 8 | **8** |
| prompts/genres/tv_series_rules.txt | 0B | 1 | 1 | 1 | 1 | **1** |
| prompts/genres/tv_series_script.txt | 659B | 8 | 7 | 6 | 8 | **7** |
| prompts/outline/outline.txt | 413B | 6 | 5 | 6 | 5 | **5** |
| prompts/portrait/base_profile.txt | 1385B | 7 | 6 | 8 | 7 | **7** |
| prompts/portrait/stage_split.txt | 1285B | 8 | 7 | 6 | 7 | **7** |
| prompts/qa/qa.txt | 594B | 7 | 5 | 6 | 6 | **6** |
| prompts/reader/analysis.txt | 531B | 9 | 4 | 7 | 6 | **7** |
| prompts/rewrite/rewrite.txt | 699B | 7 | 8 | 6 | 8 | **7** |
| prompts/scene/era_scan.txt | 856B | 8 | 9 | 7 | 8 | **8** |
| prompts/scene/locations.txt | — | — | — | — | — | ❌ |
| prompts/scene/makeup.txt | 1342B | 8 | 9 | 6 | 8 | **8** |
| prompts/scene/props.txt | 1517B | 8 | 9 | 7 | 8 | **8** |
| prompts/shot-time-budget.md | 1826B | 7 | 5 | 7 | 6 | **6** |
| prompts/storyboard/cinematic_reference.md | 6644B | 6 | 9 | 6 | 8 | **7** |
| prompts/storyboard/scene_shots.txt | 2295B | 7 | 6 | 5 | 8 | **6** |
| prompts/storyboard/scene_split.txt | 504B | 9 | 7 | 6 | 8 | **7** |

### 详细审查


#### prompts/alias_resolve.txt (评分: 7.5/10)
> 模板整体质量良好，规则详细，但存在未定义的占位符和部分边界模糊，建议补充说明并改善输出示例以提升 LLM 可靠性与可维护性。

#### prompts/genres/manhua.json (评分: 6/10)
> 模板结构完整，但核心system_prompt过于薄弱，严重依赖外部规则文件，导致LLM可靠性不足；需补充输出格式和详细编剧指导以提升可用性。

#### prompts/genres/manhua_adapt.txt (评分: 6/10)
> 模板结构清晰但变量定义缺失，输出部分有冗余，且缺乏防止模型幻觉的可靠性设计，需完善输入说明和输出约束。

#### prompts/genres/manhua_rules.txt (评分: 1/10)
> 该prompt模板文件为空，无法生效，需要完整定义manhua类的生成规则

#### prompts/genres/manhua_script.txt (评分: 8/10)
> 模板结构清晰且覆盖了关键要素，但缺乏示例和约束，可能影响LLM输出的可靠性和一致性，建议补充示例和明确规则。

#### prompts/genres/movie.json (评分: 8/10)
> 模板覆盖了电影类型核心要素，整体一致性好，但system_prompt缺少具体格式约束，依赖外部规则文件，可适当增强LLM输出的可控性。

#### prompts/genres/movie_adapt.txt (评分: 8/10)
> 结构清晰、逻辑自洽的电影改编模板，但输入变量说明不足、部分指令可能引发LLM泛化输出，需增强示例与约束。

#### prompts/genres/movie_rules.txt (评分: 1/10)
> 该prompt模板文件为空，完全无法使用，必须填充有效内容才能用于LLM交互

#### prompts/genres/movie_script.txt (评分: 6/10)
> 模板具备基本电影剧本生成能力，但在格式一致性和LLM可靠性方面存在显著矛盾与抽象，需统一标准、补充示例并约束输出结构。

#### prompts/genres/short_drama.json (评分: 8/10)
> 模板高度专业，细节丰富，但在输出模板、角色统一和可维护性方面略有不足，稍加完善即可成为优秀 Prompt。

#### prompts/genres/short_drama_adapt.txt (评分: 7/10)
> 模板结构清晰、核心逻辑正确，但缺乏输入规范和极端指令易导致 LLM 输出不稳定，建议补充约束和示例

#### prompts/genres/short_drama_rules.txt (评分: 1/10)
> 该Prompt模板为空文件，完全无效，需从零开始构建短剧规则。

#### prompts/genres/short_drama_script.txt (评分: 4/10)
> 模板存在严重的内部冲突（时长与字数不可兼得），导致实际可用性低，需要重大修正规则一致性才能发挥效用。

#### prompts/genres/tv_series.json (评分: 8/10)
> 模板覆盖了电视剧场景核心信息，但缺乏输出规范和详细约束，可进一步提升LLM产出稳定性。

#### prompts/genres/tv_series_adapt.txt (评分: 8/10)
> 模板结构完整、逻辑清晰，但变量定义与主观表述可能影响LLM输出的稳定性与可维护性。

#### prompts/genres/tv_series_rules.txt (评分: 1/10)
> 空文件无法作为有效提示模板，各维度均得最低分，需从头构建内容

#### prompts/genres/tv_series_script.txt (评分: 7/10)
> 模板结构清晰、内容详实，但在输出一致性、LLM执行难度和灵活维护方面存在可改进点。

#### prompts/outline/outline.txt (评分: 5/10)
> 模板基本功能完整，但存在变量拼写错误、JSON格式歧义和字数约束不明确的问题，实用性中等需改进

#### prompts/portrait/base_profile.txt (评分: 7/10)
> 模板整体可用，但存在变量不一致和缺失别名的问题，需修复格式并补充示例以提升可靠性。

#### prompts/portrait/stage_split.txt (评分: 7/10)
> 模板涵盖角色切分核心需求，但字段冗余、格式歧义和输入未优化降低了LLM输出的稳定性与一致性。

#### prompts/qa/qa.txt (评分: 6/10)
> 模板基本覆盖核心审计点，但在语法一致性和LLM鲁棒性上存在明显缺陷，需优化转义与标准制定。

#### prompts/reader/analysis.txt (评分: 7/10)
> 模板覆盖信息全面，但存在致命的一致性缺陷（双花括号导致非法 JSON），修复后可用于章节结构化分析。

#### prompts/rewrite/rewrite.txt (评分: 7/10)
> 模板结构清晰、指令明确，但存在对白长度限制的矛盾、缺乏输入格式约定和防幻觉措施，建议补充示例和约束以提高 LLM 输出稳定性。

#### prompts/scene/era_scan.txt (评分: 8/10)
> Prompt结构清晰，覆盖主要维度，但需增强对输入不确定性的处理说明并规范输出格式以提升LLM执行稳定性。

#### prompts/scene/makeup.txt (评分: 8/10)
> 模板功能完整，结构清晰，但存在非人类角色判定模糊、JSON格式可靠性不足、字段维护成本较高的问题，建议增加容错指导和模块化规则

#### prompts/scene/props.txt (评分: 8/10)
> 模板结构完整、指令清晰，但在LLM图像生成可靠性（特别是六视图精确性）和输入变量处理上存在不足，建议适度简化视觉要求并补充示例。

#### prompts/shot-time-budget.md (评分: 6/10)
> 模板覆盖了核心检视点，但对白时间计量不一致及情绪定义模糊导致内部冲突，维护性一般，需统一逻辑并参数化。

#### prompts/storyboard/cinematic_reference.md (评分: 7/10)
> 内容详实专业，但缺乏明确的输出格式和任务指令绑定，导致直接用作 LLM 生成 prompt 时可靠性不足，需增加执行约束与示例。

#### prompts/storyboard/scene_shots.txt (评分: 6/10)
> 模板功能全面但存在多个规则冲突和抽象要求，LLM 容易产生幻觉或遗漏关键细节，建议统一时长、简化标记、将抽象要求转化为显式字段约束。

#### prompts/storyboard/scene_split.txt (评分: 7/10)
> 模板整体设计合理，但输出格式中的双花括号是主要缺陷，且场景分割规则细节可能导致LLM输出不稳定，需修正格式并增加示例/反例。

---
## D. 架构与数据模型审查

🟢 **数据库 Schema**: 7/10
  - JSON 数据使用 Text 列存储，缺乏数据库级别的格式校验和查询能力
  - 外键关系通过整数字段手动维护，未使用 ForeignKey 约束，数据完整性由应用层保证
  - 部分模型字段（如 color_curve, genre_adapt_rules）定义为 Text，语义模糊
  - status 字段使用字符串值（如 'imported', 'draft'），未用枚举或常量化
  → 若数据库支持（如 PostgreSQL），使用 JSON/JSONB 类型替代 Text; 为 book_id, character_name 等关联字段添加 ForeignKey 约束; 引入 Enum 类型或应用层常量定义状态值

🟡 **Pipeline 设计**: 5/10
  - 硬编码 BOOK_ID=6 和 GENRE='short_drama'，缺乏通用性
  - 步骤依赖检测逻辑存在缺陷（如 bible_exists 判断错误，混淆状态）
  - 错误处理采用 try-except 打印后继续，可能导致数据不一致
  - 无幂等性保障，重复运行会重复生成数据（如 Props, Locations 每次覆盖）
  → 改为可配置 YAML/JSON 定义 pipeline 步骤和参数; 在数据库中维护任务执行状态表，支持幂等重试; 统一错误处理策略，支持事务回滚

🟡 **配置管理**: 6/10
  - OPENAI_API_KEY 默认值为 'sk-placeholder'，生产环境可能遗忘覆盖
  - 敏感信息（API Key、数据库路径）均明文存储在 .env 和代码中
  - 无配置校验，缺少对运行环境的区分（dev/staging/prod）
  - 数据库 URL 硬编码部分路径，环境变量覆盖不够灵活
  → 添加配置加载后的断言，确保关键变量已设置; 使用加密存储（如环境加密变量、Vault）保存敏感值; 提供多环境配置文件（.env.development, .env.production）

🟢 **CLI 设计**: 7/10
  - portrait 命令实现不完整，只有文档字符串
  - 部分命令（如 read）虽定义了 start/end 参数但在代理调用中未传递
  - 错误提示不够友好，直接抛出 typer.Exit(1) 无详细信息
  - 缺少全局选项（如 --verbose, --config-path）
  → 补全所有命令的实现; 增加输入验证（如 episode 必须为正整数）; 丰富帮助信息，添加使用示例

🟡 **整体架构**: 6/10
  - Agent 之间通过数据库紧密耦合，数据流隐式，难以追踪
  - 业务逻辑与数据访问层混合（如 SceneSetupAgent 直接查询模型）
  - 无依赖注入，各 Agent 内部直接实例化 LLM 客户端，不利于测试
  - 可视化组件（VisualProp/Location）与核心业务逻辑耦合过深
  → 定义清晰的 Agent 接口（如 run(book_id, params) -> result）; 将数据库访问移入 Repository 层，Agent 只调用 Repository; 使用依赖注入（如通过构造函数传入 LLM 客户端）

🔴 **测试覆盖**: 1/10
  - 代码库中未发现任何测试文件或测试脚本
  - Agent 核心逻辑、数据库操作、CLI 命令均无测试覆盖
  - 缺少对 LLM 调用的 mock 测试
  - 无集成测试验证完整 pipeline 流程
  → 为每个 Agent 编写单元测试，mock 外部依赖（LLM、数据库）; 添加集成测试，使用内存数据库测试完整 pipeline 执行; 增加安全测试（如 SQL 注入、配置泄露）

---
## E. 建议优先级

### P0 — 必须修复 (32 项)

🔴 **P0** [agents/base.py] 在 is_short_story 中添加 try-except 或检查 b 是否为 None。

🔴 **P0** [agents/base.py] 在 session 上下文中使用 try-finally 确保资源释放并记录异常。

🔴 **P0** [agents/base.py] 定义自定义异常类（如 AgentError），并在 run 中捕获并包装异常。

🔴 **P0** [agents/base.py] 为 session 添加异常日志记录。

🔴 **P0** [agents/outline.py] 为所有字典类型定义 TypedDict 或 dataclass，确保字段类型一致。

🔴 **P0** [agents/outline.py] 访问 bible.content 前检查是否为 None 或提供默认值。

🔴 **P0** [agents/outline.py] 使用 isinstance(book.chapter_count, int) 进行类型断言或转换。

🔴 **P0** [agents/outline.py] 在合并固定 sliot 时，对 characters 和 scenes 进行类型检查和转换：if not isinstance(..., list): characters = []。

🔴 **P0** [config.py] 将目录创建逻辑移至惰性初始化或显式调用函数中，并捕获异常（如PermissionError）

🔴 **P0** [config.py] 环境变量转换使用try-except，失败时回退到默认值或记录警告

… 还有 22 项

### P1 — 建议修复 (355 项)

🟡 **P1** [agents/adapter.py] 增加检查 book 是否为 None，并抛出明确异常

🟡 **P1** [agents/adapter.py] 使用 try-except 包裹 LLM 调用和数据库提交，异常时回滚 session

🟡 **P1** [agents/adapter.py] 在 __init__ 中验证 genre 是否有效，避免 later error

🟡 **P1** [agents/adapter.py] 使用 str(p.gender or '') 或提供默认值

🟡 **P1** [agents/adapter.py] 确保 book.title 非空，或使用 book.id 作为 fallback

🟡 **P1** [agents/adapter.py] 对 bible.content 进行空值检查

🟡 **P1** [agents/adapter.py] 对 book.title 进行清洗，移除路径分隔符和特殊字符

🟡 **P1** [agents/adapter.py] 使用 os.path.basename 或安全的 slugify 函数

🟡 **P1** [agents/adapter.py] 考虑设置文件权限为 600 或 640

🟡 **P1** [agents/adapter.py] 将截断长度提取为类常量或配置项

… 还有 345 项

### P2 — 可优化 (140 项)

🟢 **P2** [agents/adapter.py] 显式注入 session 或使用依赖注入模式

🟢 **P2** [agents/adapter.py] 采用可配置的截断策略（如按 token 数或段落切割）

🟢 **P2** [agents/adapter.py] 将 prompt 构建分离为独立函数或策略类

🟢 **P2** [agents/base.py] 在获取 Book 前验证当前用户是否有权限访问该 book_id。

🟢 **P2** [agents/base.py] 使用结构化日志库（如 logging）并配置输出级别，避免生产环境打印敏感信息。

🟢 **P2** [agents/bible.py] 对 book.title 进行清洗，只允许安全字符

🟢 **P2** [agents/bible.py] 考虑对 chapter 中的 JSON 字段进行 schema 验证

🟢 **P2** [agents/bible.py] 限制 JSON 解析的最大大小和深度

🟢 **P2** [agents/outline.py] 对 LLM 返回的 JSON 中的字符串字段进行转义或清洗，防止注入（例如使用 bleach 库）。

🟢 **P2** [agents/outline.py] 在 config.output_path 中对 book.title 进行 sanitize，移除不安全字符。

… 还有 130 项


---
*报告由 Audit Agent 自动生成*