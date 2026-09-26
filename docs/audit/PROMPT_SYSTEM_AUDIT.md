# Prompt System Audit

## 当前来源

### Legacy storyboard

StoryboardShot.visual_prompt_static、visual_prompt_motion、visual_prompt_final；StoryboardPromptVersion（storyboard_prompt_versions）；web/src/domain/bookOutputs.ts 仍暴露这些字段；api/server.py 提供 compile、version、rollback、lock 入口。

### Structured PromptIR

PromptIRVersion 保存结构化 payload、hash、compiler/policy/retention 版本和 qualification/stale 状态；PromptIRAuthority 保存不可变 authority envelope；PromptIRPointer 按 shot + target media 指向当前合格版本；canonical generation 将 PromptIR hash/version 纳入 request fingerprint。

### Production Prompt Lineage

ProductionPromptVersion 是 append-only 版本；ProductionGenerationIntent 保存 shot-derived requirements/constraints 快照；ProductionPromptLineage 把 asset version、shot、prompt version、intent 连接成不可变边。

## 权威冲突

当前没有代码级规则宣布 visual_prompt_final、StoryboardPromptVersion、PromptIRPointer、ProductionPromptVersion 中只有一个是最终权威。旧 UI/compile 链仍可读旧字段；canonical execution 偏向 PromptIR Pointer；新 lineage 尚未替代全部旧读取面。

因此：Production generation 的执行权威已偏向 PromptIR Pointer；编辑/产品权威仍是 legacy 与 production lineage 并存。

## 统一方案

1. PromptIRPointer 作为可执行 Prompt 的唯一入口。
2. ProductionPromptVersion 作为 append-only 创作/谱系记录，不能绕过 compiler 直接替代 PromptIR。
3. 明确 compiler/materialization step，从 editor input 生成 PromptIR version 并写 source lineage。
4. 将 visual_prompt_* 和 StoryboardPromptVersion 降为兼容 read-only projection。
5. workspace 同时返回 source lineage、PromptIR pointer、stale/reason codes。
6. 无合格 PromptIR pointer 时返回 production readiness blocker。

PromptIR、authority、provider 和 fingerprint 只能出现在 technical/production view，不应泄漏到读者剧本文本。
