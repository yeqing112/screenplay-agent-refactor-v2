# Asset Runtime Integration

## 1. 目标

Generation Runtime 复用已有 Asset Authority、Asset Version、Pointer、Binding 和 Review，不创建新的 Asset 表或 AssetManager。

需要区分：

- Visual Asset Authority：角色、场景、道具等语义资产的 identity/version/pointer。
- Generated Media Authority：一次图片/视频生成的 candidate、validation、official media version/pointer。
- Visual authoring proposal：LLM 提议，必须经过人工决策，不等于媒体资产。

## 2. 生成结果如何进入资产链

GenerationExecution 成功时只完成：

1. provider terminal response 已归一化。
2. 媒体被写入 canonical storage identity。
3. checksum、mime、byte size、尺寸/时长可验证。
4. 创建 MediaCandidateRecord，绑定 execution_id、PromptIR hash/version、model profile fingerprint、provider request/response hash。

随后：

MediaCandidateRecord
→ MediaValidationRecord
→ 人工/权限确认
→ OfficialMediaVersion
→ OfficialMediaAuthority
→ OfficialMediaPointer

因此 provider 成功不等于 production asset。OfficialMediaPointer 移动是唯一可供生产读取的晋级动作。

## 3. 与 VisualAsset Graph 的关系

对于 CHARACTER、SCENE、PROP：

- VisualAssetVersion/Pointer 保存 canonical identity、语义 payload、revision 和 stale 状态。
- 生成请求通过 reference authority 和 shot binding 读取当前 fresh 版本。
- candidate/official media 通过 asset_key、shot、media_role 和 lineage 关联到该语义资产。
- official media 晋级不会静默覆盖 VisualAssetVersion；如需变更语义事实，必须走新的 authoring decision/version。
- ShotAssetBinding 仍是 shot 到 canonical asset authority 的关系，不能被 provider response 直接替换。

对于 shot frame/video：

- OfficialMediaVersion 以 book、episode、storyboard_shot_id、media_role、revision 唯一化。
- OfficialMediaPointer 选择当前官方版本。
- 旧 asset_links 和 prototyping asset URL 仅作为兼容读取面，不能绕过 candidate/validation。

## 4. Review 集成

技术验证和人工 review 分层：

1. Media validation 检查可读性、容器、尺寸/时长、checksum 和 authority snapshot。
2. Review Workflow 记录 reviewer、decision、notes、state history。
3. 通过后调用 media authority promote，生成 official version/authority/pointer。
4. 拒绝保留 candidate 和 validation history，不删除执行记录。
5. 新 revision 通过新 execution 或明确的 manual replacement 产生，旧 official version 可审计回溯。

Visual authoring proposal 的 approve 只产生 VisualAuthoringDecision；它不会自动创建 VisualAssetVersion 或移动 pointer，除非另一个显式的 authority mutation 被调用。

## 5. Provenance 最小集合

每个 candidate/official media 必须能够回溯：

- shot、book、episode、media_role
- ProductionGenerationIntent
- ProductionPromptVersion 和 PromptIR version/hash
- model_profile_id/fingerprint
- provider_adapter_id/version 和 transport_binding_id
- provider request/task/response hash
- reference authority fingerprints
- request payload/policy fingerprints
- storage identity、checksum、mime、尺寸/时长
- validation id/fingerprint、review decision、promotion fingerprint

## 6. Stale 与回滚

当 PromptIR、reference authority、VisualAssetPointer 或 source official media 失效时，新的执行必须被阻止或标记 stale。已生成的 candidate 不自动删除；它保留历史 provenance，但不能被新 pointer 选为 current。回滚是选择历史 official revision 或重新生成，不是修改旧 row。

## 7. 迁移边界

本设计不执行 migration。现有 candidate/validation/official schema 已足以承载第一阶段。若运行时需要跨进程 lease，应单独设计 generation execution 的 claim/reconcile 字段迁移；不新增 Asset 表，也不复制现有 authority/pointer/review 表。

