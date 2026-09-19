# Phase A — Script Creative Quality Closure 报告

## 目标

Phase A 属于四阶段生产质量收口的第一阶段，范围严格限定在**剧本层**：

1. ScriptIR 升级为“可验证戏剧结构”（DramaticBeat / SceneTransitionContract / Character Knowledge·Deception）
2. 新增 `core/script_creative_quality.py` 剧本专业质量闸门
3. 重做剧本渲染器：Reader Script（用户阅读） + Technical Script View（工程视图）
4. 修复《红伞倒影》剧情（补 Scene1→Scene2 因果、Gaslighting 语义、去 AI 标记、去摄影机方向）
5. 保留旧版为负面 fixture，闸门必须能发现其问题
6. 990401 样例分类调整为 `E2E_INTEGRATION_SAMPLE`（非 `PRODUCTION_QUALITY_GOLDEN`）

本阶段**不进入** Director/Blocking/ShotPlan 层（Phase B/C/D）。

## 完成项

### ScriptIR 升级（`core/script_ir.py`）

- 每个戏剧节拍归一化为 `dramatic_beats`，包含 `beat_id / beat_type / objective / information_delta / emotional_delta / requires_reaction / importance`
- Dialogue 附带 `assertion_mode`（OBJECTIVE_FACT / CHARACTER_BELIEF / DECEPTION / UNCERTAIN_CLAIM）、`contradicts_fact_refs`、`audience_should_notice`
- 新增 `scene_transitions`（SceneTransitionContract）：`from/to_scene_id / time_relation / location_change / exit_state / entry_state / transition_event / causal_reason / travel_or_elapsed_time / status`
- 继续复用现有 `ScriptIRVersion / Pointer / Authority`，**没有建立第二套版本体系**

### 剧本专业闸门（`core/script_creative_quality.py`）

Hard gates（必须阻断）：

- `SCENE_TRANSITION_UNRESOLVED`
- `CHARACTER_STATEMENT_CONTINUITY_CONFLICT`（对白引用事实但未标记 DECEPTION/UNCERTAIN，系统无法区分撒谎与编剧矛盾）
- `CHARACTER_STATE_DISCONTINUITY`
- `PROP_STATE_CONFLICT`
- `TIMELINE_CONFLICT`
- `UNMARKED_FACT_CONTRADICTION`
- `CRITICAL_BEAT_MISSING`

Soft diagnostics（不阻断）：

- `REPETITIVE_INTERROGATION`
- `EXPOSITION_HEAVY_DIALOGUE`
- `LOW_ESCALATION`
- `OVERDIRECTED_SCRIPT`（读者剧本含摄影机/导演标记）
- `INTERNAL_LABEL_LEAK`

闸门为只读，不写版本、不移动 Pointer、不触发媒体。

### 剧本渲染器（`core/script_renderer.py`）

- `render_reader_script`：专业可读剧本，不含摄影机方向、不含内部工程标记
- `render_technical_script_view`：工程视图，含 beat_id / fact refs / knowledge state / transition contracts
- `render_script_markdown`：保留旧格式作为向后兼容别名，既有测试不破坏

### 剧情修复（990401 / 第1集）

- 新增 Scene1→Scene2 因果：林晚发现包扣被重动、断伞骨丢失 → 放弃登车 → 对陆叔说“忘了拿一样东西先回去” → 陆叔过快同意成为新的怀疑节拍
- Scene2 的 Gaslighting 明确标记为 `DECEPTION`：陆叔“我们一直在一起”引用 `contradicts_fact_refs`，观众应察觉
- Reader 剧本已清除 `【视觉证明1】`、`【隐藏层泄露种子】`、`【强钩子】`、`镜头推近` 等标记
- 固定版通过闸门：`PRODUCTION_QUALIFIED`

### 负面 fixture（`creative-quality-negative-fixture.json`）

旧版问题剧本被保留为负面样例，闸门必须能发现：

- `SCENE_TRANSITION_UNRESOLVED`
- `CHARACTER_STATEMENT_CONTINUITY_CONFLICT`
- `CRITICAL_BEAT_MISSING`
- 摄影机泄漏：`主观视角 / 推近 / 特写 / 镜头`
- 内部标签泄漏：`【视觉证明`

Treatment / Blocking / ShotPlan 层的负面信号（`DIRECTOR_TREATMENT_PLACEHOLDER`、`BLOCKING_NOT_MATERIALIZED`、`SHOT_COVERAGE_INCOMPLETE`、`NON_ATOMIC_SHOT`、`SHOT_RUNTIME_MISMATCH`、`CAMERA_MOVEMENT_SEMANTIC_CONFLICT`）在 Phase B/C 覆盖，负面 fixture 中已登记预期信号清单。

### 样例分类（`production-sample-registry.json`）

- `990401` 注册为 `E2E_INTEGRATION_SAMPLE`（证明 Authority Pipeline 能跑通，不证明 Creative Quality 达生产级）
- 注册表校验通过（`ok: true`）

### API 接入（`api/script_ir_api.py`）

- 新增只读 `POST /api/books/{book_id}/episodes/{episode}/script-ir/creative-quality`
- `confirm` 支持 `enforceCreativeQuality=true`，硬错误时返回 `SCRIPT_CREATIVE_QUALITY_BLOCKED`

## 产物

- `artifacts/e2e-production-pilot/episode_01_script_ir_phase_a.json` — 修复版 ScriptIR（含 dramatic_beats / transitions / assertion semantics）
- `artifacts/e2e-production-pilot/episode_01_full_script_phase_a.md` — 用户可读剧本（Reader）
- `artifacts/e2e-production-pilot/episode_01_script_technical_view_phase_a.md` — 工程视图（Technical）
- `artifacts/e2e-production-pilot/creative-quality-negative-fixture.json` — 负面 fixture

## 测试

- `tests/test_script_creative_quality.py`：5 passed（固定版通过、负面版阻断、Reader 无泄漏、Technical 含 refs、端点只读+阻断）
- 既有 `test_script_ir.py` / `test_script_ir_renderer.py` / `test_script_ir_authority_activation.py`：17 passed（向后兼容）
- 样例注册表校验：ok

## 验收剧本

请验收：

[episode_01_full_script_phase_a.md](./e2e-production-pilot/episode_01_full_script_phase_a.md)

验收要点：

- Scene1→Scene2 是否因果成立（为什么不上车）
- 陆叔 Gaslighting 是否从“连续性 Bug”变成“人物威胁”
- Reader 剧本是否干净（无摄影机、无 AI 标记）
- 剧情是否保留原有核心悬念

## 下一步

等你验收 Phase A 剧本。通过后再进入 Phase B（`DIRECTOR_BLOCKING_QUALITY_CLOSURE`）。
