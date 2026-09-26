# Asset System Audit

## 资产层次

1. Legacy visual assets：models/visual.py 的 VisualAsset、reference asset、shot media，兼容旧 workspace。
2. Production Asset Authority：VisualAssetVersion、VisualAssetPointer、VisualReferenceAsset、authoring decision/proposal，负责 canonical identity、版本、引用和人工治理。
3. Generated media authority：MediaCandidateRecord → MediaValidationRecord → OfficialMediaVersion → OfficialMediaAuthority/OfficialMediaPointer，负责生成媒体晋级。

## 真实生命周期

canonical asset identity → VisualAssetVersion → VisualAssetPointer → optional reference generation request/reference authority → PromptIR + generation intent → GenerationExecution → MediaCandidate（bytes/storage/checksum/provenance）→ technical validation → human/authority promotion → OfficialMediaVersion + OfficialMediaPointer。

Visual authoring proposal 单独走 DecisionRequest → provider proposal → validator → REVIEW_REQUIRED → human approve/reject → VisualAuthoringDecision；批准不自动创建 version 或移动 pointer。

## 已确认能力

- Authority：VisualAssetVersion.authority_status、OfficialMediaAuthority
- Version：revision、official_media_version_id、production asset version registry
- Pointer：VisualAssetPointer、OfficialMediaPointer
- Provenance：request snapshot、provider response hash、lineage/promotion envelopes
- Checksum：MediaCandidateRecord/OfficialMediaVersion.checksum_sha256
- Prompt：PromptIR version/hash、production prompt lineage
- Model：model profile id/fingerprint、provider/model
- Generation metadata：request/payload/policy fingerprints、provider ids、latency/retry
- Review：production asset reviews/history、media validation、proposal review

## 主要问题

Legacy asset_links/shot media 与 canonical candidate/official media 可能形成两个读取面；storage identity 与真实对象存储的统一 ingestion 尚需证据；引用 stale 状态、PromptIR stale 状态和 execution 失效传播虽已建模，旧入口不一定全部强制检查。

## 结论

Asset Authority Graph 已足够作为 production read model。下一步不是再造 Asset Manager，而是让所有生成入口写入同一 candidate/validation/official 链，并让 workspace 读取 canonical projection。
