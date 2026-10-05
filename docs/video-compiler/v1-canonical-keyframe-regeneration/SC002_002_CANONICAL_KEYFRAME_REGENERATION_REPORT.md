# SC002_002 Canonical Keyframe Regeneration

Status: `SC002_002_CANONICAL_IMAGE_PREFLIGHT_BLOCKED`
Run: `20261005T044836Z`
Shot: `SH_E01_SC002_002`

## Gate A

The run stopped before provider POST with `CANONICAL_SHOT_SOURCE_MISSING`. The current canonical database has no matching durable `StoryboardShot` or media-scoped `PromptIRPointer` for `SH_E01_SC002_002`. Historical Markdown prompts and the historical keyframe remain forensic evidence only and were not adopted, modified, or used as authority.

## Provider and persistence safety

- Real IMAGE calls: `0` (authorized maximum: `1`)
- Real VIDEO calls: `0`
- Provider IMAGE POST count: `0`
- Provider VIDEO POST count: `0`
- SHAPI/Poyo fallback calls: `0`
- GenerationExecution / Candidate / Validation / Review / Promotion / OfficialMedia writes: `0`
- Book 990400 writes: `0`
- Historical lineage changes: `0`
- Secret or raw base64 persistence: `0`

## Current active IMAGE profile

`{"adapter_id": "image_generic", "adapter_version": "image_generic_adapter_v1", "credential_configured": true, "default_params": {"allowed_models": ["gpt-image-2-1k", "gpt-image-2-2k"], "evidence_status": "provider_probe_required", "n": 1, "quality": "high", "response_format": "url", "size": "auto", "supports_async_tasks": false, "supports_file_upload": false, "supports_image_url": true, "supports_negative_prompt": false, "supports_reference_images": true, "task_modes": ["text_to_image", "image_to_image"], "transport": "75api-images-generations"}, "generation_capability": "IMAGE_GENERATION", "id": "local-image-c4a7yu", "model": "gpt-image-2-1k", "provider": "75api-image", "transport_binding_id": "75api-image.image.v1"}`

The profile was resolved dynamically. Credential readiness is recorded in `SC002_002_CANONICAL_IMAGE_PREFLIGHT.json` without exposing the credential.

## Gates B–H

Provider submission, candidate validation, review/promotion, OfficialMedia creation, IMAGE-to-VIDEO bridge construction, and VIDEO reference preflight were not executed because Gate A failed closed. `REAL_VIDEO_NOT_EXECUTED`.
