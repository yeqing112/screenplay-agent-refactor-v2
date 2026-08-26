# 2026-08-25 book75 提示词生产治理与 LLM JSON 稳定性验收记录

## 背景

本轮按生产级推进顺序执行：先治理 `book 75 / 深夜便利店` 的真实分镜提示词质量，再补真实 LLM JSON 稳定性底座。此前旧审计主要检查长度、资产绑定和场景资产，无法识别“提示词够长但仍残留灰度修复痕迹/占位式动态描述”的假通过。

## 本轮改动

1. 升级 `npm run audit:storyboard`
   - 新增 `internal_repair_marker_in_prompt`
   - 新增 `generic_motion_prompt`
   - 对监控屏幕、照片、台面、物件特写等合理无人物镜头，不再误报 `missing_structured_character_assets`

2. 改造确定性提示词修复输出
   - `E2E_STORYBOARD_PROMPT_MOCK=1` 后端 mock 改为消费 `prompt_compile_context.model_adapter`
   - `validate-storyboard-quality-repair-clone.py` 的克隆修复 mock 改为消费 Prompt IR + Rule Compiler + Model Adapter
   - `apply-storyboard-batch-repair.py` 的 deterministic apply mock 改为消费 Prompt IR + Rule Compiler + Model Adapter
   - `core/model_adapter.py` 清理短分类标签、方括号和冒号式对白残留，并显式补齐 `visual_fact_targets`

3. 完成 `book 75` 真实项目全量受保护 deterministic apply
   - 样本：`book 75 / episode 1 / shot 1-14`
   - apply 前创建当前 prompt baseline version
   - apply 命令仍受真实写入开关、preflight JSON、确认令牌和 compiler mode 保护

4. 增强真实 LLM JSON 解析稳定性
   - `core.llm.call_llm_json` 改为使用 balanced JSON object parser
   - 支持解析失败后自动重试一次
   - 支持 `LLM_JSON_RESPONSE_FORMAT=1` 时传入 Chat Completions JSON mode
   - 新增 `tests/test_llm_json_parsing.py`

## 验收结果

- `book 75` 升级审计前：`28 error / 0 warning`
- `book 75` 批量克隆修复：`28 error -> 0 error`，`0 warning -> 0 warning`
- `book 75` preflight：`real apply blockers = 0`
- `book 75` 真实 apply：`28 error -> 0 error`，`0 warning -> 0 warning`
- `book 75` 后审计：`0 error / 0 warning`
- 5 项目 / 50 镜头新基线：`29 error / 24 warning`

## 关键产物

- `artifacts/storyboard-prompt-real-sample-audit-2026-08-25T15-26-43-212Z.json`
- `artifacts/storyboard-batch-repair-clone-20260825T152844Z.json`
- `artifacts/storyboard-batch-repair-preflight-20260825T152845Z.json`
- `artifacts/storyboard-batch-repair-preflight-20260825T152845Z.md`
- `artifacts/storyboard-batch-repair-apply-20260825T152859Z.json`
- `artifacts/storyboard-prompt-real-sample-audit-2026-08-25T15-29-13-918Z.json`
- `artifacts/storyboard-prompt-real-sample-audit-2026-08-25T15-29-38-537Z.json`
- `artifacts/book75-storyboard-compiler-v1-preview.json`
- `artifacts/book75-storyboard-compiler-v1-preview.md`
- `artifacts/book75-machine-prompt-export-preview.json`
- `artifacts/book75-machine-prompt-export-preview.md`

## 已执行验证

- `AUDIT_STORYBOARD_BOOK_IDS=75 AUDIT_STORYBOARD_SHOT_COUNT=20 npm run audit:storyboard`
- `VALIDATE_STORYBOARD_REPAIR_SAMPLES=75:1:1,75:1:9 python scripts/validate-storyboard-quality-repair-clone.py`
- `BATCH_REPAIR_BOOK_IDS=75 BATCH_REPAIR_SHOT_COUNT=14 python scripts/validate-storyboard-batch-repair-clone.py`
- `BATCH_REPAIR_BOOK_IDS=75 BATCH_REPAIR_SHOT_COUNT=14 npm run plan:storyboard-batch-repair`
- `APPLY_STORYBOARD_BATCH_REPAIR_REAL=1 APPLY_STORYBOARD_BATCH_REPAIR_PREFLIGHT=artifacts/storyboard-batch-repair-preflight-20260825T152845Z.json APPLY_STORYBOARD_BATCH_REPAIR_CONFIRM=<preflight token> APPLY_STORYBOARD_BATCH_REPAIR_MOCK=1 npm run apply:storyboard-batch-repair`
- `npm run preview:book75-compiler-v1`
- `npm run preview:book75-h3-export`
- `python -m unittest tests.test_llm_json_parsing tests.test_reader_fallback tests.test_storyboard_prompt_compile tests.test_storyboard_prompt_compile_repair tests.test_machine_prompt_export tests.test_model_adapter`
- `npm --prefix web test -- ProductWorkspaceStoryboardRepairActions.test.tsx`
- `npm run e2e:machine-prompt-export`
- `npm run audit:storyboard`

## 后续任务

1. 将本轮治理方法扩展到 `book 14 / 5 / 3 / 1`，优先处理仍含内部灰度痕迹和短 prompt 的镜头。
2. 补导出历史中心与导演语言到结构事实变更建议。
3. 在真实 LLM JSON 底座稳定后，做单镜头真实模型灰度，仍不得绕过 preflight、确认令牌和 rollback anchor。
