# Current Database Relationship

## 关系总览

Project 在当前 ORM 中以 Book 为主实体，Book → Episode/Chapter → StoryboardShot。Shot → PromptIRVersion → PromptIRAuthority；Shot + target_media → PromptIRPointer。Shot → ProductionGenerationIntent。ProductionPromptLineage 连接 asset version、shot、ProductionPromptVersion、generation intent。

GenerationExecutionRecord → MediaCandidateRecord → MediaValidationRecord → OfficialMediaVersion → OfficialMediaAuthority/OfficialMediaPointer。TaskRun 是 book/episode scope 的通用 pipeline task，不代替 generation execution。Review 由 production_asset_reviews/production_asset_review_history、VisualAuthoringDecision/Proposal 和 media validation 分层承担。Model Registry 使用 KV（model_registry_profiles、model_registry_defaults），与 shot 没有 SQL 外键，execution 通过 model_profile_id 和 fingerprint 逻辑关联。

## 关键关系字段

- ProductionGenerationIntent.shot_id → storyboard_shots.id
- ProductionPromptLineage.asset_version_id → production_asset_version_registry.version_id
- ProductionPromptLineage.prompt_version_id → production_prompt_versions.prompt_version_id
- ProductionPromptLineage.generation_intent_id → production_generation_intents.generation_intent_id
- MediaValidationRecord.candidate_id/execution_id → candidate/execution
- OfficialMediaVersion.candidate_id/validation_id → candidate/validation
- OfficialMediaPointer.official_media_version_id/authority_id → official version/authority
- production asset review/history → production asset version registry

## Migration evidence

核心 schema 来自：d4e5f6a7b8c9_add_persistent_task_runs.py、b2c3d4e5f6g7_add_media_scoped_prompt_pointer.py、y8h9i0j1k2l3_add_generation_execution_records.py、z0a1b2c3d4e5_add_media_authority_foundation.py、v5e6f7g8h9i0_add_visual_asset_authority.py、u4d5e6f7g8h9_add_prompt_ir_authority.py、a1b2c3d4e5f6_add_h2_production_asset_authority.py。

这些迁移建立了关键外键/唯一约束，但旧表是兼容结构；表存在不等于所有运行路径已经迁移。
