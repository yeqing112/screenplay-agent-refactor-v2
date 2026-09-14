# 智能导演台 Agent 调研源报告

日期：2026-09-05  
完整研究备忘录：[docs/2026-09-05-智能导演台-Agent-深度调研与架构建议.md](docs/2026-09-05-智能导演台-Agent-深度调研与架构建议.md)

## 直接结论

本项目应演进为受控导演编排 Agent：先以证据包生成计划和草案，再通过版本、审批、执行与验收闭环调度现有工具；不应将自由聊天直接连接到外部生成或不可逆写入。

## 证据账本

| 主张 | 来源 | 访问说明 |
|---|---|---|
| Flow 使用可复用角色/场景资产、场景图发起镜头、镜头控制、Scene Builder 与资产管理 | [Google：Introducing Flow](https://blog.google/technology/ai/google-flow-veo-ai-filmmaking-tool/) | 官方产品文章，已读取，2026-09-05 |
| Gen-4 将视觉参考与指令结合，用于跨镜头人物、地点、物体和风格一致性 | [Runway：Gen-4](https://runwayml.com/research/introducing-runway-gen-4) | 官方产品文章，已读取，2026-09-05 |
| Skills 是含元数据、指令、资源/代码且按需加载的模块化能力 | [Anthropic：Agent Skills](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills/overview) | 官方技术文档，已读取，2026-09-05 |
| 高风险工具可以暂停、审批/拒绝、持久化并恢复 Agent 运行 | [OpenAI Agents SDK：Human-in-the-loop](https://openai.github.io/openai-agents-python/human_in_the_loop/) | 官方技术文档，已读取，2026-09-05 |
| 输入、输出与工具调用可以设置 Guardrails 和中断 | [OpenAI Agents SDK：Guardrails](https://openai.github.io/openai-agents-python/guardrails/) | 官方技术文档，已读取，2026-09-05 |
| C2PA 定义内容凭证的声明、清单、绑定、校验与处理链 | [C2PA 2.2 Specification](https://spec.c2pa.org/specifications/specifications/2.2/specs/C2PA_Specification.html) | 官方规范，已读取，2026-09-05 |

## 当前项目核对

已核对现有 `api/server.py` 与 `core`：项目存在 DecisionPacket、Prompt Compiler/Shot IR、资产锁定、验收记录、连续性合同以及项目级 production skill runtime；因此建议复用这些对象作为 Agent 的事实层、工具层与审计层。

## 限制

以上来源不证明任何第三方已经提供完整的“智能导演台”产品；它们只支持相应的工程模式。外部模型 API、价格、商用权利与地区可用性需在实际接入时复核。

