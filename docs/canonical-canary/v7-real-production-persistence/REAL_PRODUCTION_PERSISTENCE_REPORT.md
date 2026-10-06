# Generalized Canary Real Production Persistence V7 Report

- Status: `GENERALIZED_CANARY_PRODUCTION_PERSISTED`
- Next state: `DIRECTOR_CREATIVE_AUTHORING_AUTHORIZATION_REQUIRED`
- Persistence run: `20261006T013634Z-8bf0de6a0e95514a`
- New Book: `990453`
- New Script: `64`
- New FactSnapshot: `49` (2 FactRecords)
- New ScriptIRVersion: `52`
- Source origin: Book `990402`, Chapter `16`, Seq `3`, raw SHA `190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1`
- Source lineage: structuring `f4204059934cf19eebf4fcb94278756c48eaefce853d947cb5af16db133452ef`, reconciliation `aee7ad3b79f2da379ce42af79082653970a7d5bba6b3382cd507adfcc3f5539c`, migration `4541e40f88dfcdada955f2603c2d8c7d71fe328b8c802b3a0746fec2ec61ed40`
- Canonical dialogue: 顾沉 / 也许是你自己 / assertion_mode empty / AUTHORIZED_SEMANTIC_BINDING / COREFERENCE_RESOLUTION
- Authority: `SOURCE_GROUNDED_V3_1`, qualification `PRODUCTION_QUALIFIED`, stale `FRESH`
- Creative readiness: `AUTHORING_REQUIRED`; production blocked reason `CREATIVE_AUTHORING_REQUIRED`
- Production resolve: `PASS`
- Delta: `{"agent_attachments": 0, "agent_audit_logs": 0, "agent_messages": 0, "agent_plans": 0, "agent_project_updates": 0, "agent_sessions": 0, "agent_violation_logs": 0, "alembic_version": 0, "asset_semantic_governance_records": 0, "automatic_keyframe_plans": 0, "book_bibles": 0, "books": 1, "chapter_fts": 0, "chapter_fts_config": 0, "chapter_fts_content": 0, "chapter_fts_data": 0, "chapter_fts_docsize": 0, "chapter_fts_idx": 0, "chapters": 0, "character_asset_authorities": 0, "character_asset_pointers": 0, "character_asset_versions": 0, "character_profiles": 0, "character_reference_assets": 0, "character_stages": 0, "decision_packet_records": 0, "director_benchmark_runs": 0, "director_plans": 0, "director_reasoning_generations": 0, "director_reasonings": 0, "director_scene_plans": 0, "director_story_beats": 0, "director_storyboard_plans": 0, "director_storyboard_shots": 0, "director_treatment_authorities": 0, "director_treatment_pointers": 0, "director_treatments": 0, "director_visual_decisions": 0, "episode_outlines": 0, "episode_render_items": 0, "episode_render_plans": 0, "fact_records": 2, "fact_snapshots": 1, "generation_execution_attempt_lineages": 0, "generation_execution_records": 0, "keyframe_asset_bindings": 0, "keyframe_sequences": 0, "keyframes": 0, "kv": 0, "media_candidate_records": 0, "media_promotion_records": 0, "media_validation_records": 0, "official_media_authorities": 0, "official_media_pointers": 0, "official_media_versions": 0, "production_asset_authority_registry": 0, "production_asset_review_history": 0, "production_asset_reviews": 0, "production_asset_version_registry": 0, "production_batch_items": 0, "production_batches": 0, "production_export_records": 0, "production_generation_intents": 0, "production_prompt_lineages": 0, "production_prompt_versions": 0, "prompt_ir_authorities": 0, "prompt_ir_pointers": 0, "prompt_ir_versions": 0, "prop_asset_authorities": 0, "prop_asset_pointers": 0, "prop_asset_versions": 0, "public_asset_storage_migration_records": 0, "qa_issues": 0, "qa_results": 0, "repair_attempts": 0, "scene_asset_authorities": 0, "scene_asset_pointers": 0, "scene_asset_versions": 0, "scene_blocking_authorities": 0, "scene_blocking_pointers": 0, "scene_blockings": 0, "scene_characters": 0, "scene_props": 0, "scene_reference_assets": 0, "script_ir_versions": 1, "script_versions": 0, "scripts": 1, "shot_asset_bindings": 0, "shot_character_bindings": 0, "shot_directions": 0, "shot_plan_authorities": 0, "shot_plan_pointers": 0, "shot_plans": 0, "shot_scene_bindings": 0, "shot_style_bindings": 0, "storyboard_acceptance_records": 0, "storyboard_materialization_pointers": 0, "storyboard_materialization_sets": 0, "storyboard_prompt_versions": 0, "storyboard_shots": 0, "storyboard_transition_continuity_reviews": 0, "storyboard_transition_contracts": 0, "storyboard_transition_frames": 0, "storyboard_video_retry_attempts": 0, "style_reference_assets": 0, "task_runs": 0, "video_generation_intents": 0, "visual_asset_pointers": 0, "visual_asset_versions": 0, "visual_authoring_decision_requests": 0, "visual_authoring_decisions": 0, "visual_authoring_proposals": 0, "visual_era_specs": 0, "visual_locations": 0, "visual_makeups": 0, "visual_props": 0, "visual_reference_assets": 0, "visual_reference_authorities": 0, "visual_reference_generation_requests": 0, "visual_reference_sets": 0, "visual_style_profiles": 0}`
- Downstream rows: `0`
- External Provider calls: LLM `0`, IMAGE `0`, VIDEO `0`
- Director/scene blocking/shot plan/storyboard/prompt/media writes: `0`

## Integrity

- Base commit: `50b874f6869cc9e27006c2ce5bdd1ec8a8e576db`
- Working tree was clean before write: `True`
- V3.1 migration replay: `PASS`
- Final prewrite preflight: `PASS`
- Origin refreeze: `PASS`
- FactRecord anchors: `PASS`
- Authority envelope v2: `PASS`
- Canonical dialogue propagation: `PASS`

## Formal lifecycle

- Book: `core.book_lifecycle.create_book`
- Script: `core.book_lifecycle.create_script`
- ScriptIR: `prepare_script_ir_production(confirmed=True)`
- No manual primary key allocation was used.

## Partial persistence handling

The first orchestration process stopped after the formal Book/Script commits and before ScriptIR preparation because its detached ORM access failed. The existing run was detected by its unique run id and continued exactly once; no duplicate Book or Script was created.
