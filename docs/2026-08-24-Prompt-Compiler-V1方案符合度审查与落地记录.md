# Prompt Compiler V1.0 方案符合度审查与落地记录

日期：2026-08-24  
参考外部方案：`D:\Download\AI影视生产系统_结构化分镜与Prompt_Compiler落地设计方案_V1.0.docx`

## 1. 审查结论

本项目已经吸收了 V1.0 方案中的一部分思想，但此前不能称为“完整按方案重构完成”。

当前真实状态是：

- 已有 `structured_shot`、`Prompt IR`、`Rule Compiler`、提示词版本、诊断、回滚和资产权威继承。
- `Prompt IR` 已进入分镜提示词编译上下文与版本元数据。
- 过去缺口在于 `Model Adapter` 虽然存在文件，但没有进入主编译链；真实提示词最终仍主要由 LLM 模板直接生成。
- 真实项目历史数据尚未全量迁移为完整 `structured_shot + shot_ir`，例如 `book 75` 仍主要是旧短提示词。

本轮已完成第一步修正：把 `Model Adapter` 正式接入分镜提示词编译链，作为确定性模型适配基线与 LLM 缺字段兜底。

## 2. V1.0 符合度矩阵

| V1.0 要求 | 当前实现状态 | 证据 | 结论 |
| --- | --- | --- | --- |
| Shot Schema 是唯一真相源 | 部分实现 | `storyboard_shots.meta_info.structured_shot` 可保存结构化镜头，但不是独立强约束表/字段 | 过渡态 |
| Prompt 是派生产物 | 部分实现 | `storyboard_prompt_versions` 保存编译版本，回滚可恢复 prompt 与结构快照 | 基本具备 |
| Rule Compiler 稳定生成语义 | 部分实现 | `core/rule_compiler.py` 已接入 `_compile_storyboard_prompts`，但规则仍偏薄 | 需要增强 |
| Prompt IR 中间表示 | 部分实现 | `core/prompt_ir.py` 已构建并持久化到 `prompt_compile_context.shot_ir` 与版本 meta | 基本接入 |
| Model Adapter 多模型适配 | 本轮前未真正接入；本轮已接入基线 | `core/model_adapter.py` 现在由 `_compile_storyboard_prompts` 调用，并写入 `prompt_compile_context.model_adapter` | 已开始落地 |
| LLM Polish 可选且受控 | 部分实现 | LLM 仍生成最终 JSON；已有 diagnostics/hard gates/repair，但不是纯 polish 层 | 仍需收敛 |
| 参考图/首帧一致性 | 部分实现 | `reference_images`、`reference_asset_ids`、资产状态与参考图诊断已存在 | 继续完善 |
| Continuity 与 Asset State | 部分实现 | 有 `continuity` 上下文与 retention 检查，但缺独立 `asset_states` 主模型 | 过渡态 |
| 自动 QA 阻止硬冲突 | 部分实现 | 编译诊断、QA workbench、hard gates 已有；AC01-AC12 尚未完整映射 | 需要补测试 |
| Generation 追溯 | 部分实现 | 图片/视频任务有任务记录与资产回写，但没有完全等价 V1.0 `generations` 表模型 | 需要后续演进 |

## 3. 本轮代码落地

### 3.1 Model Adapter 从死代码变成编译链环节

改动：

- 扩展 `core/model_adapter.py`：
  - 新增中文影视生产通用 Adapter。
  - 支持 `jimeng / kling / veo / seedance / poyo / storyboard / default` 等目标模型名。
  - 输出静态提示词、运动提示词、负面提示词的确定性 baseline。
- 修改 `api/server.py`：
  - 在 `ShotIR` 和 `Rule Compiler` 之后调用 `adapt_ir_to_model(...)`。
  - 将结果写入 `prompt_compile_context.model_adapter`。
  - LLM 输出缺少 `visual_prompt_static / visual_prompt_motion / negative_prompt` 时，由 Adapter 兜底。
  - 兜底行为会进入 `compiler_warnings`，不伪装成完全 pass。
- 更新 `prompts/storyboard/prompt_compiler.txt`：
  - 明确 `model_adapter` 是确定性基线，LLM 可润色但不得删除资产锚点、动作阶段、一致性约束和负面约束。

### 3.2 验证

已运行：

```bash
python -m unittest tests.test_model_adapter tests.test_storyboard_prompt_compile tests.test_storyboard_prompt_compile_repair tests.test_storyboard_prompt_authority_diagnostics
```

结果：

- 57 个测试通过。
- 验证正常 LLM 编译时会持久化 `model_adapter` baseline。
- 验证 LLM 返回空 prompt 字段时，Adapter 能生成可用提示词并落库为 warning 状态，而不是写入空/短提示词。
- 验证 Rule Compiler 修改的 IR 字段仍能进入上下文、结构化镜头和版本元数据。

## 4. 对 `book 75` 的影响

本轮没有直接改写 `book 75` 的真实镜头提示词。

原因：

- `book 75` 是真实业务数据；永久批量重写提示词应继续走受保护 preflight/apply 流程。
- 本轮先修主编译链，避免继续用旧的“LLM 直接生成 prompt”口径推进。
- 已基于新 Adapter baseline 对 `book 75` 生成 14 镜头只读预览；下一步应先补齐场景资产参考图/正式场景描述，再考虑真实 apply。

### 4.1 已生成只读预览

本轮新增命令：

```bash
npm run preview:book75-compiler-v1
```

该命令只读真实库，不调用 LLM，不写入任何分镜或版本数据；输出：

```text
artifacts/book75-storyboard-compiler-v1-preview.json
artifacts/book75-storyboard-compiler-v1-preview.md
```

最新预览结果：

- 镜头数：14
- 当前静态提示词低于 80 字：14
- 当前动态提示词低于 80 字：13
- 命中的场景资产：`158`、`159`
- Adapter 静态提示词最短长度：243
- Adapter 运动提示词最短长度：192
- 每镜绑定资产数范围：1 - 3
- 每镜参考图数范围：0 - 2
- warning 总数：16
- 真实库字段、JSON 预览和 Markdown 预览均可按 UTF-8 读取，`U+FFFD` 替换符数量为 0；此前看到的乱码应归因于 PowerShell/npm 输出显示编码，而不是业务数据损坏。

结论：

- `book 75` 已经可以通过当前真实 `VisualLocation` 进入 `structured_shot -> shot_ir -> model_adapter` 只读编译预览。
- 当前仍不应直接真实 apply，因为预览暴露出两类后续问题：一是当前落库提示词普遍偏短，二是 draft 场景资产缺参考图，导致 Adapter 能生成 baseline，但还不等于生产级首帧/视频输入。

### 4.2 场景资产生产可用性审计

本轮已增强 `npm run audit:scene-assets`：

- 保留原有 `status` 语义，只表示场景名是否能绑定到 `VisualLocation`，避免误触发重复创建场景资产。
- 新增 `production_status / production_issues`，检查场景资产是否仍为 draft、是否仍使用分镜派生占位描述、是否缺 selected/locked 参考图。
- 新增 `ready_for_binding_repair_apply` 与 `ready_for_prompt_batch_apply`，区分“可做缺失绑定修复”和“可做生产级提示词批量 apply”。

针对 `book 75` 的最新只读审计：

```bash
SCENE_ASSET_AUDIT_BOOK_IDS=75 npm run audit:scene-assets
```

输出：

```text
artifacts/storyboard-scene-asset-readiness-20260824T151007Z.json
artifacts/storyboard-scene-asset-readiness-20260824T151007Z.md
```

结果：

- 绑定状态：ready，缺失场景名 0。
- 生产状态：blocked。
- 生产阻塞场景名：2。
- 生产阻塞镜头：14。
- 阻塞项：
  - `监控室`：asset_status=draft，参考图 0，影响 8 镜。
  - `便利店收银台`：asset_status=draft，参考图 0，影响 6 镜。

### 4.3 场景参考图生产计划

本轮新增只读计划命令：

```bash
npm run plan:book75-scene-references
```

该命令不调用生图、不写库，只根据真实分镜和场景资产生成：

- 正式场景描述候选。
- 场景参考图生成提示词。
- 负向提示词。
- 可提交给 `/api/prototyping/generate-reference-image` 的请求草案。

输出：

```text
artifacts/book75-scene-reference-plan.json
artifacts/book75-scene-reference-plan.md
```

最新结果：

- 分镜镜头数：14。
- 场景资产数：2。
- 参考资产数：3，均为角色参考资产；场景参考资产为 0。
- 需规划场景参考图：2。
- 影响镜头：14。
- 已为 `便利店收银台`、`监控室` 分别生成正式场景描述候选、16:9 无人物场景参考图提示词和 API 请求草案。

### 4.4 场景参考图真实生成与尺寸审计

本轮已新增受保护命令：

```bash
npm run enqueue:book75-scene-references
npm run apply:book75-scene-reference-plan
```

执行记录：

- `artifacts/storyboard-scene-reference-generation-20260824T152907Z.json`
  - 成功调用 PoYo GPT Image 2 生成 2 张真实场景参考图。
  - `便利店收银台` 参考资产：`ref-64`，selected，非 mock。
  - `监控室` 参考资产：`ref-65`，selected，非 mock。
- `artifacts/storyboard-scene-reference-plan-apply-20260824T153156Z.json`
  - 已把 `VisualLocation#158 监控室`、`VisualLocation#159 便利店收银台` 从 draft 提升为 `ref_ready`。
  - 已把两个场景资产描述替换为正式场景描述候选。
  - 已修正本次生成 reference notes 的历史乱码。

视觉抽检：

- `artifacts/book75-scene-ref-convenience-counter.png`
- `artifacts/book75-scene-ref-monitor-room.png`

内容判断：

- 两张图均为无人物场景图。
- 便利店收银台符合深夜便利店、冷白灯、货架、玻璃门、收银台等语义。
- 监控室符合多监控屏、冷蓝绿屏幕光、杂乱桌面、压抑悬疑氛围等语义。

尺寸发现与修复：

- 两张图实际尺寸均为 `1024x1024`，不是计划要求的 16:9 横图。
- 因此新增 `SCENE_ASSET_AUDIT_VALIDATE_IMAGE_DIMENSIONS=1` 严格审计模式。
- 严格审计输出：`artifacts/storyboard-scene-asset-readiness-20260824T154257Z.md`
- 初次严格审计结论：场景绑定 ready、场景资产 ref_ready、场景参考图存在，但生产状态仍 blocked，因为没有符合横构图比例的 selected/locked 场景参考图。
- 经查 PoYo GPT Image 2 官方参数，正确横图参数不是 `aspect_ratio: "16:9"`，而是 `size: "16:9"` 且需配合 `resolution: "2K"` 或 `resolution: "4K"`。
- 已修正 `api/generation_adapters.py`：当 `model_name=gpt-image-2` 时，将内部 `aspect_ratio` 映射为 PoYo 官方 `size`，并默认补 `resolution=2K`。
- 已重新真实生成横图：`artifacts/storyboard-scene-reference-generation-20260824T161212Z.json`。
  - `便利店收银台` 新参考资产：`ref-66`，selected，旧方图 `ref-64` 自动降为 candidate。
  - `监控室` 新参考资产：`ref-67`，selected，旧方图 `ref-65` 自动降为 candidate。
- 新图本地抽检：
  - `artifacts/book75-scene-ref-convenience-counter-16x9.png`：`2560x1440`，16:9。
  - `artifacts/book75-scene-ref-monitor-room-16x9.png`：`2560x1440`，16:9。
- 最新严格审计输出：`artifacts/storyboard-scene-asset-readiness-20260824T161327Z.md`。
- 最新严格审计结论：`ready_for_prompt_batch_apply=true`，场景生产阻塞清零。

## 5. 后续优先级

### 5.1 `book 75` 提示词批量修复灰度落库记录

在场景参考图严格审计通过后，已对 `book 75` 执行提示词批量修复 preflight：

```bash
BATCH_REPAIR_BOOK_IDS=75 \
BATCH_REPAIR_SHOT_COUNT=14 \
PLAN_STORYBOARD_BATCH_REPAIR_STRICT_READY=1 \
npm run plan:storyboard-batch-repair
```

输出：

- `artifacts/storyboard-batch-repair-preflight-20260824T161809Z.json`
- `artifacts/storyboard-batch-repair-preflight-20260824T161809Z.md`

preflight 结果：

- 覆盖镜头：14/14。
- errors：33 -> 0。
- warnings：40 -> 1。
- real apply blockers：0。
- 唯一剩余 warning：`#75:1:9 missing_structured_character_assets`。该镜头是监控屏幕插入镜头，无可见人物，因此可作为非阻塞 warning 放行。
- confirmation token：`4ac036f7cbeb0631`。

随后执行确定性灰度落库，不调用真实大模型：

```bash
APPLY_STORYBOARD_BATCH_REPAIR_REAL=1 \
APPLY_STORYBOARD_BATCH_REPAIR_PREFLIGHT=artifacts/storyboard-batch-repair-preflight-20260824T161809Z.json \
APPLY_STORYBOARD_BATCH_REPAIR_CONFIRM=4ac036f7cbeb0631 \
APPLY_STORYBOARD_BATCH_REPAIR_MOCK=1 \
npm run apply:storyboard-batch-repair
```

输出：

- `artifacts/storyboard-batch-repair-apply-20260824T162025Z.json`

落库结果：

- 14 个镜头均已写入 deterministic-mock compiler 产物。
- 每个镜头均在写入前创建 `batch-quality-repair-current-baseline` 版本锚点。
- 每个镜头均创建 `batch-quality-repair-confirmed` 应用版本。
- apply 汇总：errors 33 -> 0，warnings 40 -> 1。

落库后回归：

- `npm run preview:book75-compiler-v1`
  - `shot_count=14`
  - 当前静态 prompt 最短长度：392。
  - 当前运动 prompt 最短长度：91。
  - `static_lt_80=0`
  - `motion_lt_80=0`
  - `zero_reference_shots=0`
  - 剩余 2 条质量建议：`林小夏 当前镜头存在明显状态变化，建议补一条分镜精调定妆。`
- `SCENE_ASSET_AUDIT_BOOK_IDS=75 SCENE_ASSET_AUDIT_VALIDATE_IMAGE_DIMENSIONS=1 npm run audit:scene-assets`
  - `book 75` 场景绑定 ready。
  - 生产状态 ready。
  - production blocking scenes：0。
- `npm run audit:storyboard`
  - 全局采样 50 镜，剩余 errors 主要来自其他书籍。
  - `book 75` 抽检 10 镜：issues=0，warnings=0。
- `python -m unittest tests.test_generation_adapters tests.test_poyo_creative_task_state tests.test_storyboard_scene_asset_readiness tests.test_model_adapter tests.test_storyboard_prompt_compile tests.test_storyboard_prompt_compile_repair tests.test_storyboard_prompt_authority_diagnostics`
  - 81 tests OK。

### 5.2 `book 5` 场景资产与提示词批量修复记录

在 `book 75` 链路验证后，已把同一套生产门禁推进到 `book 5 神农架历险记`。

前置审计：

- 初始严格场景资产审计：`artifacts/storyboard-scene-asset-readiness-20260824T205355Z.json`
  - `book 5` 分镜镜头：20。
  - 绑定状态 ready。
  - 生产状态 blocked。
  - 阻塞场景：`原始丛林上空`、`原始丛林深处`、`部落营地`。

本轮修复了场景参考图计划器：

- 场景参考图 prompt 改为“单张 16:9 横构图”，明确禁止分格、拼图、多视角排版。
- 负向提示词追加：人物、人脸、人形、角色、分格、拼图、多宫格、四宫格、多视角排版、文字说明。
- 对当前阻塞场景加入稳定场景级描述模板，避免把分镜动作/人物光效混入场景资产 prompt。
- 增强 enqueue 脚本：
  - 支持 `--scene-name` 单场景提交。
  - 支持 `--limit` 限量提交。
  - 增加逐场景提交/完成日志，避免真实 provider 调用黑箱等待。
- 修正 scene-reference-plan apply notes，使来源标记按实际 book 写入，不再固定为 book75。
- 修正 deterministic mock batch apply：优先使用真实 `shot.scene_name`，避免绑定资产名与分镜场景名同义但不一致时触发 `scene_name_not_in_static_prompt`。

真实生成记录：

- `原始丛林上空`
  - report：`artifacts/storyboard-scene-reference-generation-20260824T210724Z.json`
  - reference asset：`ref-68`
  - URL：`https://cdn.doculator.org/images/QSLRTUUCFTEMI5ZI/QSLRTUUCFTEMI5ZI.png`
- `原始丛林深处`
  - report：`artifacts/storyboard-scene-reference-generation-20260824T210946Z.json`
  - reference asset：`ref-69`
  - URL：`https://cdn.doculator.org/images/W64T2ORPGHYUD46D/W64T2ORPGHYUD46D.png`
- `部落营地`
  - report：`artifacts/storyboard-scene-reference-generation-20260824T211204Z.json`
  - reference asset：`ref-70`
  - URL：`https://cdn.doculator.org/images/NOQCNFLU8838Z1MK/NOQCNFLU8838Z1MK.png`
- 三次 PoYo GPT Image 2 请求均使用：
  - `size=16:9`
  - `resolution=2K`
  - 每张 provider response 记录 `credits_amount=4.0`

场景资产 apply：

- 初次 apply：`artifacts/storyboard-scene-reference-plan-apply-20260824T211232Z.json`
  - 更新 3 个场景资产为 `ref_ready`。
  - 严格场景资产审计通过：`artifacts/storyboard-scene-asset-readiness-20260824T211244Z.json`
- 精确场景名补丁后，二次 apply：`artifacts/storyboard-scene-reference-plan-apply-20260824T211800Z.json`
  - 更新 `原始丛林深处` 正式描述，保留精确分镜场景名。

提示词批量修复：

- preflight：`artifacts/storyboard-batch-repair-preflight-20260824T211256Z.json`
  - 覆盖镜头：20/20。
  - errors：48 -> 0。
  - warnings：58 -> 1。
  - real apply blockers：0。
  - confirmation token：`b4246e9c862fa66b`。
- 初次灰度落库：`artifacts/storyboard-batch-repair-apply-20260824T211327Z.json`
  - errors：48 -> 0。
  - warnings：58 -> 7。
  - 差异原因：绑定资产名 `原始森林深处` 覆盖了分镜场景名 `原始丛林深处`。
- 修正后再次灰度落库：`artifacts/storyboard-batch-repair-apply-20260824T211848Z.json`
  - errors：0 -> 0。
  - warnings：7 -> 1。

落库后回归：

- `python scripts/preview-storyboard-compiler-v1.py --book-id 5 --target-model jimeng`
  - 输出：`artifacts/book5-storyboard-compiler-v1-preview.json`
  - `shot_count=20`
  - 当前静态 prompt 最短长度：283。
  - 当前运动 prompt 最短长度：99。
  - `static_lt_80=0`
  - `motion_lt_80=0`
- `SCENE_ASSET_AUDIT_BOOK_IDS=5 SCENE_ASSET_AUDIT_VALIDATE_IMAGE_DIMENSIONS=1 npm run audit:scene-assets`
  - 输出：`artifacts/storyboard-scene-asset-readiness-20260824T211913Z.json`
  - 生产阻塞场景：0。
- `npm run audit:storyboard`
  - 输出：`artifacts/storyboard-prompt-real-sample-audit-2026-08-24T21-19-25-496Z.json`
  - 全局采样 errors：22 -> 9。
  - `book 5` 抽检 10 镜：issues=0，warnings=1。
- `python -m unittest tests.test_generation_adapters tests.test_poyo_creative_task_state tests.test_storyboard_scene_asset_readiness tests.test_model_adapter tests.test_storyboard_prompt_compile tests.test_storyboard_prompt_compile_repair tests.test_storyboard_prompt_authority_diagnostics`
  - 85 tests OK。

后续注意：

- `book 5` 的主质量门禁已通过，但 preview 仍提示角色/道具资产增强项：
  - `神农 / 姬由 / 姬瑶 / 神农大帝` 等角色缺参考图。
  - `石矛` 道具缺参考图。
  - 多个 `胡涂` 状态变化镜头建议补分镜精调定妆。
- 这些属于生产资产丰富度问题，不再是“短 prompt / 场景绑定缺失 / 16:9 场景参考图缺失”的主链路 blocker。

### 5.3 后续优先级

1. 处理剩余 2 条 `林小夏 当前镜头存在明显状态变化，建议补一条分镜精调定妆。`：补角色镜头状态变体，或明确作为生产前非阻塞 warning 放行。
2. 以 `book 75 / book 5` 为模板，把同一套“场景资产严格审计 -> 场景参考图计划/生成/apply -> batch repair preflight -> 确定性灰度落库 -> 全局真实样本审计”复制到 `book 3 / book 1`。
3. 补 AC01-AC12 自动验收矩阵，至少先覆盖 AC01、AC02、AC03、AC04、AC10、AC12。
4. 将 `Model Adapter` 从 baseline/fallback 进一步推进为真正的模型目标输出层，LLM 退回到受控 polish。
5. 设计独立 `shot_schema / generation / asset_state` 迁移方案，不直接用一次性大迁移冲击真实库。
