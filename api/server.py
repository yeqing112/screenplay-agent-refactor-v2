"""DevCanvas API server."""
import asyncio
import difflib
import json
import logging
import os
import uuid
import re
from types import SimpleNamespace
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, BackgroundTasks, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
import config
from api.generation_adapters import (
    ModelProfileError,
    build_task_adapter_asset,
    generate_image_asset,
    generate_video_asset,
    reconcile_minimax_h3_generation,
    reconcile_poyo_generation,
    resolve_generation_profile,
)
from api.model_registry import save_registry, serialize_registry_payload, test_profile_connection
from core import safe_json_loads
import core.llm as llm_client
from core.model_adapter import sanitize_machine_prompt_text
from core.prompts import load_prompt
from core.production_skill import (
    build_production_skill_prompt_block,
    build_script_rule_family_repair_goal,
    build_script_skill_execution_plan_prompt_block,
    build_script_skill_foundation_prompt_block,
    build_script_skill_repair_packet_prompt_block,
    build_project_production_skill_runtime,
    classify_script_qa_rule_family,
    get_builtin_production_skill,
    list_builtin_production_skills,
    load_latest_script_qa_issues,
    normalize_project_production_skill_state,
    read_project_production_skill_state,
    write_project_production_skill_state,
)

from nodes.registry import REGISTRY, get_handler
from nodes.runner import NodeRunner, WORKFLOWS_DIR, RUNS_DIR
from models import Session, Book

logger = logging.getLogger(__name__)

app = FastAPI(title="Screenplay DevCanvas", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.API_CORS_ORIGINS,
    allow_credentials=config.API_CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {
        "ok": True,
        "service": "screenplay-devcanvas-api",
        "version": app.version,
    }


def _parse_task_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _persist_task_state(task_id: str, task_kind: str, task_state: dict[str, Any]) -> None:
    if not task_id or not isinstance(task_state, dict):
        return
    try:
        from models import Session, TaskRun

        now = datetime.utcnow()
        payload = json.dumps(task_state, ensure_ascii=False, default=str)
        with Session() as s:
            row = s.query(TaskRun).filter(TaskRun.task_id == task_id).first()
            if not row:
                row = TaskRun(
                    task_id=task_id,
                    task_kind=task_kind,
                    created_at=_parse_task_datetime(task_state.get("created_at") or task_state.get("started_at")) or now,
                )
                s.add(row)
            row.task_kind = task_kind
            row.status = str(task_state.get("status") or "queued")
            row.progress = int(task_state.get("progress") or 0)
            row.book_id = int(task_state.get("book_id")) if task_state.get("book_id") not in {None, ""} else None
            row.episode = int(task_state.get("episode")) if task_state.get("episode") not in {None, ""} else None
            row.payload = payload
            row.error = str(task_state.get("error") or "")
            row.updated_at = now
            row.finished_at = _parse_task_datetime(task_state.get("finished_at"))
            s.commit()
    except Exception as exc:
        logger.warning("Failed to persist %s task %s: %s", task_kind, task_id, exc)


def _load_persisted_task_state(task_id: str, expected_kind: str | None = None) -> dict[str, Any] | None:
    if not task_id:
        return None
    try:
        from models import Session, TaskRun

        with Session() as s:
            row = s.query(TaskRun).filter(TaskRun.task_id == task_id).first()
            if not row:
                return None
            if expected_kind and row.task_kind != expected_kind:
                return None
            payload = safe_json_loads(row.payload, {})
            if not isinstance(payload, dict):
                payload = {}
            payload.setdefault("task_id", row.task_id)
            payload.setdefault("task_kind", row.task_kind)
            payload.setdefault("status", row.status or "queued")
            payload.setdefault("progress", row.progress or 0)
            payload.setdefault("book_id", row.book_id)
            payload.setdefault("episode", row.episode)
            payload.setdefault("error", row.error or None)
            payload.setdefault("created_at", row.created_at.isoformat() if row.created_at else None)
            payload.setdefault("updated_at", row.updated_at.isoformat() if row.updated_at else None)
            payload.setdefault("finished_at", row.finished_at.isoformat() if row.finished_at else None)
            return payload
    except Exception as exc:
        logger.warning("Failed to load persisted task %s: %s", task_id, exc)
        return None


def _list_persisted_task_states(task_kind: str, book_id: int, limit: int = 20) -> list[dict[str, Any]]:
    try:
        from models import Session, TaskRun

        with Session() as s:
            rows = s.query(TaskRun).filter(
                TaskRun.task_kind == task_kind,
                TaskRun.book_id == book_id,
            ).order_by(TaskRun.updated_at.desc(), TaskRun.id.desc()).limit(limit).all()
            result: list[dict[str, Any]] = []
            for row in rows:
                payload = safe_json_loads(row.payload, {})
                if not isinstance(payload, dict):
                    payload = {}
                payload.setdefault("task_id", row.task_id)
                payload.setdefault("task_kind", row.task_kind)
                payload.setdefault("status", row.status or "queued")
                payload.setdefault("progress", row.progress or 0)
                payload.setdefault("book_id", row.book_id)
                payload.setdefault("episode", row.episode)
                payload.setdefault("updated_at", row.updated_at.isoformat() if row.updated_at else None)
                result.append(payload)
            return result
    except Exception as exc:
        logger.warning("Failed to list persisted %s tasks for book %s: %s", task_kind, book_id, exc)
        return []


def _is_creative_task_state(task: dict[str, Any] | None) -> bool:
    if not isinstance(task, dict):
        return False
    task_kind = str(task.get("task_kind") or "").strip()
    kind = str(task.get("kind") or task.get("target_kind") or "").strip()
    return task_kind.startswith("creative") or kind in {"image", "video", "reference-image", "machine_prompt_api_submission"}

# --- Data models ---


class WorkflowData(BaseModel):
    nodes: list[dict]
    edges: list[dict]
    viewport: dict | None = None


class RunRequest(BaseModel):
    node_id: str
    node_type: str
    inputs: dict
    config: dict = {}


class RunStatus(BaseModel):
    run_id: str
    status: str
    result: dict | None = None


class ModelProfilePayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = None
    name: str
    capability: str
    provider: str
    base_url: str = Field(default="", validation_alias=AliasChoices("base_url", "baseUrl"))
    model_name: str = Field(default="", validation_alias=AliasChoices("model_name", "modelName"))
    default_params: dict = Field(default_factory=dict, validation_alias=AliasChoices("default_params", "defaultParams"))
    enabled: bool = True
    api_key: Optional[str] = Field(default=None, validation_alias=AliasChoices("api_key", "apiKey"))


class ModelRegistryUpdateRequest(BaseModel):
    profiles: list[ModelProfilePayload] = Field(default_factory=list)
    defaults: dict[str, str] = Field(default_factory=dict)


class ModelRegistryTestRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    profile_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("profile_id", "profileId"))
    profile: Optional[ModelProfilePayload] = None


class VisualAssetPatchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    jimeng_ref_name: Optional[str] = Field(default=None, validation_alias=AliasChoices("jimeng_ref_name", "jimengRefName"))
    negative_prompt: Optional[str] = Field(default=None, validation_alias=AliasChoices("negative_prompt", "negativePrompt"))
    asset_status: Optional[str] = Field(default=None, validation_alias=AliasChoices("asset_status", "assetStatus"))
    shot_ids: Optional[list[str]] = Field(default=None, validation_alias=AliasChoices("shot_ids", "shotIds"))


class CharacterShotVariantCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    episode: int
    shot_id: str = Field(validation_alias=AliasChoices("shot_id", "shotId"))
    variant_name: Optional[str] = Field(default=None, validation_alias=AliasChoices("variant_name", "variantName"))
    refined_outfit: Optional[str] = Field(default=None, validation_alias=AliasChoices("refined_outfit", "refinedOutfit"))
    refined_accessories: Optional[str] = Field(default=None, validation_alias=AliasChoices("refined_accessories", "refinedAccessories"))
    makeup_spec: Optional[str] = Field(default=None, validation_alias=AliasChoices("makeup_spec", "makeupSpec"))
    hair_style: Optional[str] = Field(default=None, validation_alias=AliasChoices("hair_style", "hairStyle"))
    expression_mood: Optional[str] = Field(default=None, validation_alias=AliasChoices("expression_mood", "expressionMood"))
    scene_prompt_zh: Optional[str] = Field(default=None, validation_alias=AliasChoices("scene_prompt_zh", "scenePromptZh"))
    jimeng_ref_name: Optional[str] = Field(default=None, validation_alias=AliasChoices("jimeng_ref_name", "jimengRefName"))
    negative_prompt: Optional[str] = Field(default=None, validation_alias=AliasChoices("negative_prompt", "negativePrompt"))
    shot_ids: Optional[list[str]] = Field(default=None, validation_alias=AliasChoices("shot_ids", "shotIds"))


class VisualReferenceAssetRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    episode: Optional[int] = None
    asset_type: str = Field(validation_alias=AliasChoices("asset_type", "assetType"))
    asset_id: str = Field(validation_alias=AliasChoices("asset_id", "assetId"))
    asset_name: Optional[str] = Field(default=None, validation_alias=AliasChoices("asset_name", "assetName"))
    image_url: str = Field(default="", validation_alias=AliasChoices("image_url", "imageUrl"))
    local_path: str = Field(default="", validation_alias=AliasChoices("local_path", "localPath"))
    reference_token: str = Field(default="", validation_alias=AliasChoices("reference_token", "referenceToken"))
    status: str = "candidate"
    prompt: str = ""
    model: str = ""
    notes: str = ""
    meta_info: dict = Field(default_factory=dict, validation_alias=AliasChoices("meta_info", "metaInfo"))


class VisualReferenceAssetPatchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asset_name: Optional[str] = Field(default=None, validation_alias=AliasChoices("asset_name", "assetName"))
    image_url: Optional[str] = Field(default=None, validation_alias=AliasChoices("image_url", "imageUrl"))
    local_path: Optional[str] = Field(default=None, validation_alias=AliasChoices("local_path", "localPath"))
    reference_token: Optional[str] = Field(default=None, validation_alias=AliasChoices("reference_token", "referenceToken"))
    status: Optional[str] = None
    prompt: Optional[str] = None
    model: Optional[str] = None
    notes: Optional[str] = None
    meta_info: Optional[dict] = Field(default=None, validation_alias=AliasChoices("meta_info", "metaInfo"))


class StoryboardStructurePatchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    duration: Optional[int] = None
    camera_angle: Optional[str] = Field(default=None, validation_alias=AliasChoices("camera_angle", "cameraAngle"))
    camera_movement: Optional[str] = Field(default=None, validation_alias=AliasChoices("camera_movement", "cameraMovement"))
    transition: Optional[str] = None
    scene_asset_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("scene_asset_id", "sceneAssetId"))
    character_asset_ids: Optional[list[str]] = Field(default=None, validation_alias=AliasChoices("character_asset_ids", "characterAssetIds"))
    prop_asset_ids: Optional[list[str]] = Field(default=None, validation_alias=AliasChoices("prop_asset_ids", "propAssetIds"))
    style_key: Optional[str] = Field(default=None, validation_alias=AliasChoices("style_key", "styleKey"))
    character_blocking: Optional[list[dict]] = Field(default=None, validation_alias=AliasChoices("character_blocking", "characterBlocking"))
    action_beats: Optional[list[dict]] = Field(default=None, validation_alias=AliasChoices("action_beats", "actionBeats"))


class StoryboardAutoBindRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    episodes: Optional[list[int]] = None


class StoryboardPromptCompileRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    compile_reason: str = Field(default="manual", validation_alias=AliasChoices("compile_reason", "compileReason"))
    force: bool = False


class StoryboardPromptLockRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    locked: bool


class StoryboardPromptRollbackRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reason: str = "manual-rollback"


class StoryboardGenerationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    model_profile_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("model_profile_id", "modelProfileId"))
    aspect_ratio: str = Field(default="16:9", validation_alias=AliasChoices("aspect_ratio", "aspectRatio"))
    duration_seconds: Optional[int] = Field(default=5, validation_alias=AliasChoices("duration_seconds", "durationSeconds"))
    first_frame_asset_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("first_frame_asset_id", "firstFrameAssetId"))
    reference_asset_ids: list[str] = Field(default_factory=list, validation_alias=AliasChoices("reference_asset_ids", "referenceAssetIds"))
    compile_if_missing: bool = Field(default=True, validation_alias=AliasChoices("compile_if_missing", "compileIfMissing"))
    generation_chain: Optional[str] = Field(default=None, validation_alias=AliasChoices("generation_chain", "generationChain"))
    triggered_by_prompt_recompile: bool = Field(default=False, validation_alias=AliasChoices("triggered_by_prompt_recompile", "triggeredByPromptRecompile"))
    prompt_recompile_reason: Optional[str] = Field(default=None, validation_alias=AliasChoices("prompt_recompile_reason", "promptRecompileReason"))
    prompt_recompile_task_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("prompt_recompile_task_id", "promptRecompileTaskId"))
    prompt_recompile_version: Optional[int] = Field(default=None, validation_alias=AliasChoices("prompt_recompile_version", "promptRecompileVersion"))


class StoryboardAcceptanceRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asset_kind: str = Field(default="image", validation_alias=AliasChoices("asset_kind", "assetKind"))
    asset_id: str = Field(default="", validation_alias=AliasChoices("asset_id", "assetId"))
    status: str = "retrying"
    failure_tags: list[str] = Field(default_factory=list, validation_alias=AliasChoices("failure_tags", "failureTags"))
    notes: str = ""
    meta_info: dict = Field(default_factory=dict, validation_alias=AliasChoices("meta_info", "metaInfo"))


class ScriptDecisionUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    locked_at: Optional[str] = Field(default=None, validation_alias=AliasChoices("locked_at", "lockedAt"))
    released_at: Optional[str] = Field(default=None, validation_alias=AliasChoices("released_at", "releasedAt"))
    note: str = ""


class AdaptationStateUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    selected_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("selected_id", "selectedId"))
    selected_name: Optional[str] = Field(default=None, validation_alias=AliasChoices("selected_name", "selectedName"))
    custom_note: str = Field(default="", validation_alias=AliasChoices("custom_note", "customNote"))
    locked_at: Optional[str] = Field(default=None, validation_alias=AliasChoices("locked_at", "lockedAt"))


class ProductionSkillStateUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    skill_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("skill_id", "skillId"))
    platform: Optional[str] = None
    track: Optional[str] = None
    emotion_goal: Optional[str] = Field(default=None, validation_alias=AliasChoices("emotion_goal", "emotionGoal"))
    rhythm_strength: Optional[str] = Field(default=None, validation_alias=AliasChoices("rhythm_strength", "rhythmStrength"))
    visual_style: Optional[str] = Field(default=None, validation_alias=AliasChoices("visual_style", "visualStyle"))
    priorities: Optional[list[str]] = None
    enforcement: Optional[str] = None
    custom_note: Optional[str] = Field(default=None, validation_alias=AliasChoices("custom_note", "customNote"))
    locked_at: Optional[str] = Field(default=None, validation_alias=AliasChoices("locked_at", "lockedAt"))


class ProductionExportRecordRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    export_format: str = Field(default="json", validation_alias=AliasChoices("export_format", "exportFormat"))
    status: str = "completed"
    total_shots: int = Field(default=0, validation_alias=AliasChoices("total_shots", "totalShots"))
    deliverable_shots: int = Field(default=0, validation_alias=AliasChoices("deliverable_shots", "deliverableShots"))
    pending_review_shots: int = Field(default=0, validation_alias=AliasChoices("pending_review_shots", "pendingReviewShots"))
    blocked_shots: int = Field(default=0, validation_alias=AliasChoices("blocked_shots", "blockedShots"))
    summary: str = ""
    meta_info: dict = Field(default_factory=dict, validation_alias=AliasChoices("meta_info", "metaInfo"))


class StoryboardMachinePromptExportRecordRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    target_model: str = Field(default="minimax-h3", validation_alias=AliasChoices("target_model", "targetModel"))
    export_channel: str = Field(default="webui", validation_alias=AliasChoices("export_channel", "exportChannel"))
    operator_name: str = Field(default="user", validation_alias=AliasChoices("operator_name", "operatorName"))
    notes: str = ""


class StoryboardMachinePromptApiSubmissionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    target_model: str = Field(default="minimax-h3", validation_alias=AliasChoices("target_model", "targetModel"))
    export_channel: str = Field(default="api", validation_alias=AliasChoices("export_channel", "exportChannel"))
    operator_name: str = Field(default="user", validation_alias=AliasChoices("operator_name", "operatorName"))
    submission_mode: str = Field(default="task_intent_only", validation_alias=AliasChoices("submission_mode", "submissionMode"))
    source_export_record_id: Optional[int] = Field(default=None, validation_alias=AliasChoices("source_export_record_id", "sourceExportRecordId"))
    has_manual_export_draft: bool = Field(default=False, validation_alias=AliasChoices("has_manual_export_draft", "hasManualExportDraft"))
    export_payload: dict = Field(default_factory=dict, validation_alias=AliasChoices("export_payload", "exportPayload"))
    notes: str = ""


class StoryboardDirectorShotTextUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    director_shot_text: str = Field(default="", validation_alias=AliasChoices("director_shot_text", "directorShotText"))
    operator_name: str = Field(default="user", validation_alias=AliasChoices("operator_name", "operatorName"))
    reset_to_system: bool = Field(default=False, validation_alias=AliasChoices("reset_to_system", "resetToSystem"))


class QAFixOptionsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mode: str = "semi_auto"
    option_count: int = Field(default=3, validation_alias=AliasChoices("option_count", "optionCount"))
    custom_requirement: str = Field(default="", validation_alias=AliasChoices("custom_requirement", "customRequirement"))


class QAApplyFixRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mode: str = "manual"
    patched_text: str = Field(default="", validation_alias=AliasChoices("patched_text", "patchedText"))
    change_reason: str = Field(default="", validation_alias=AliasChoices("change_reason", "changeReason"))
    option_id: str = Field(default="", validation_alias=AliasChoices("option_id", "optionId"))
    operator_name: str = Field(default="user", validation_alias=AliasChoices("operator_name", "operatorName"))
    rerun_qa: bool = Field(default=True, validation_alias=AliasChoices("rerun_qa", "rerunQa"))


class QAPreviewFixRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mode: str = "manual"
    patched_text: str = Field(default="", validation_alias=AliasChoices("patched_text", "patchedText"))
    option_id: str = Field(default="", validation_alias=AliasChoices("option_id", "optionId"))


class QAAutoFixRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mode: str = "auto"
    option_count: int = Field(default=3, validation_alias=AliasChoices("option_count", "optionCount"))
    custom_requirement: str = Field(default="", validation_alias=AliasChoices("custom_requirement", "customRequirement"))
    operator_name: str = Field(default="auto-fixer", validation_alias=AliasChoices("operator_name", "operatorName"))
    rerun_qa: bool = Field(default=True, validation_alias=AliasChoices("rerun_qa", "rerunQa"))
    max_issues: int = Field(default=10, validation_alias=AliasChoices("max_issues", "maxIssues"))
    max_diff_lines: int = Field(default=16, validation_alias=AliasChoices("max_diff_lines", "maxDiffLines"))
    max_length_delta_ratio: float = Field(default=0.8, validation_alias=AliasChoices("max_length_delta_ratio", "maxLengthDeltaRatio"))
    stop_after_failed_rechecks: int = Field(default=2, validation_alias=AliasChoices("stop_after_failed_rechecks", "stopAfterFailedRechecks"))


class QARollbackRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    operator_name: str = Field(default="user", validation_alias=AliasChoices("operator_name", "operatorName"))
    rerun_qa: bool = Field(default=True, validation_alias=AliasChoices("rerun_qa", "rerunQa"))


class QAWorkflowUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workflow_status: Optional[str] = Field(default=None, validation_alias=AliasChoices("workflow_status", "workflowStatus"))
    repair_version: Optional[str] = Field(default=None, validation_alias=AliasChoices("repair_version", "repairVersion"))
    note: Optional[str] = None


# In-memory run state (could be DB, but good enough for now)
_runs: dict[str, dict] = {}

# --- Workflow CRUD ---


def _wf_path(workflow_id: str) -> Path:
    return WORKFLOWS_DIR / f"{workflow_id}.json"


_SCRIPT_DECISIONS_DIR = RUNS_DIR.parent / "script_decisions"
_SCRIPT_DECISIONS_DIR.mkdir(parents=True, exist_ok=True)


def _script_decision_path(book_id: int) -> Path:
    return _SCRIPT_DECISIONS_DIR / f"book_{book_id}.json"


def _read_script_decisions(book_id: int) -> dict:
    path = _script_decision_path(book_id)
    if not path.exists():
        return {"book_id": book_id, "episodes": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"book_id": book_id, "episodes": {}}
    if not isinstance(payload, dict):
        return {"book_id": book_id, "episodes": {}}
    episodes = payload.get("episodes", {})
    return {
        "book_id": book_id,
        "episodes": episodes if isinstance(episodes, dict) else {},
    }


def _write_script_decisions(book_id: int, payload: dict) -> dict:
    normalized = {
        "book_id": book_id,
        "episodes": payload.get("episodes", {}) if isinstance(payload.get("episodes", {}), dict) else {},
    }
    _script_decision_path(book_id).write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return normalized


def _adaptation_state_key(book_id: int) -> str:
    return f"product_workspace:adaptation:{book_id}"


def _normalize_adaptation_state_payload(book_id: int, payload: dict | None = None) -> dict:
    source = payload if isinstance(payload, dict) else {}
    selected_id = str(source.get("selected_id") or source.get("selectedId") or "").strip() or None
    selected_name = str(source.get("selected_name") or source.get("selectedName") or "").strip() or None
    custom_note = str(source.get("custom_note") or source.get("customNote") or "").strip()
    locked_at = str(source.get("locked_at") or source.get("lockedAt") or "").strip() or None
    updated_at = str(source.get("updated_at") or source.get("updatedAt") or "").strip() or None
    created_at = str(source.get("created_at") or source.get("createdAt") or "").strip() or None
    production_skill_runtime = build_project_production_skill_runtime(book_id)

    return {
        "book_id": book_id,
        "selected_id": selected_id,
        "selected_name": selected_name,
        "custom_note": custom_note,
        "locked_at": locked_at,
        "updated_at": updated_at,
        "created_at": created_at,
    }


def _read_adaptation_state(book_id: int) -> dict:
    from models import get_kv

    raw = get_kv(_adaptation_state_key(book_id), "")
    if not raw:
        return _normalize_adaptation_state_payload(book_id)
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {}
    return _normalize_adaptation_state_payload(book_id, parsed)


def _write_adaptation_state(book_id: int, payload: dict) -> dict:
    from models import set_kv

    normalized = _normalize_adaptation_state_payload(book_id, payload)
    normalized["updated_at"] = datetime.now(timezone.utc).isoformat()
    normalized["created_at"] = normalized.get("created_at") or normalized["updated_at"]
    set_kv(_adaptation_state_key(book_id), json.dumps(normalized, ensure_ascii=False))
    return normalized


def _production_skill_state_payload(book_id: int) -> dict:
    state = read_project_production_skill_state(book_id)
    runtime = build_project_production_skill_runtime(book_id)
    builtin = get_builtin_production_skill(state.get("skill_id"))
    return {
        **state,
        "skill_meta": builtin.get("skill_meta", {}),
        "runtime_summary": runtime.get("runtime_summary", {}),
    }


@app.get("/api/production-skills")
def list_production_skills():
    skills = list_builtin_production_skills()
    return {
        "skills": skills,
        "default_skill_id": skills[0]["skill_meta"]["id"] if skills else None,
    }


@app.get("/api/books/{book_id}/production-skill-state")
def get_production_skill_state(book_id: int):
    return _production_skill_state_payload(book_id)


@app.put("/api/books/{book_id}/production-skill-state")
def update_production_skill_state(book_id: int, req: ProductionSkillStateUpdateRequest):
    current = read_project_production_skill_state(book_id)
    payload = {
        **current,
        **req.model_dump(exclude_none=True, by_alias=False),
    }
    normalized = write_project_production_skill_state(book_id, payload)
    runtime = build_project_production_skill_runtime(book_id)
    builtin = get_builtin_production_skill(normalized.get("skill_id"))
    return {
        **normalized,
        "skill_meta": builtin.get("skill_meta", {}),
        "runtime_summary": runtime.get("runtime_summary", {}),
    }


@app.get("/api/books")
def list_books():
    """List imported books."""
    from models import Script, StoryboardShot, SceneCharacter, SceneProp
    with Session() as s:
        books = s.query(Book).order_by(Book.id.desc()).all()
        result = []
        for b in books:
            script_count = s.query(Script).filter(Script.book_id == b.id).count()
            shot_count = s.query(StoryboardShot).filter(StoryboardShot.book_id == b.id).count()
            result.append({
                "id": b.id,
                "title": _normalize_book_title_for_display(getattr(b, "title", None), getattr(b, "id", None)),
                "chapters": b.chapter_count,
                "words": b.total_words,
                "status": b.status or "imported",
                "scripts": script_count,
                "storyboard_shots": shot_count,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            })
    return result


@app.get("/api/workflows")
def list_workflows():
    files = sorted(WORKFLOWS_DIR.glob("*.json"))
    result = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        result.append({
            "id": f.stem,
            "name": data.get("name", f.stem),
            "updated_at": data.get("updated_at", ""),
        })
    return result


@app.post("/api/workflows")
def create_workflow(data: WorkflowData):
    wf_id = str(uuid.uuid4())[:8]
    payload = {
        "id": wf_id,
        "name": f"Workflow {wf_id}",
        "nodes": data.nodes,
        "edges": data.edges,
        "viewport": data.viewport,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _wf_path(wf_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"id": wf_id}


@app.get("/api/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    path = _wf_path(workflow_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Workflow not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.put("/api/workflows/{workflow_id}")
def update_workflow(workflow_id: str, data: WorkflowData):
    path = _wf_path(workflow_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Workflow not found")
    existing = json.loads(path.read_text(encoding="utf-8"))
    existing["nodes"] = data.nodes
    existing["edges"] = data.edges
    existing["viewport"] = data.viewport
    existing["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}

# --- Node registry ---


@app.get("/api/nodes/registry")
def get_registry():
    from pathlib import Path as PPath
    return [{
        **spec.model_dump(),
        "support_upload": spec.name == "ingest",
    } for spec in REGISTRY.values()]


def _safe_upload_filename(filename: str | None) -> str:
    raw_name = str(filename or "").replace("\\", "/").split("/")[-1].strip()
    safe_name = config.sanitize_filename(raw_name)
    if not safe_name:
        raise HTTPException(status_code=400, detail="Upload filename is required.")
    suffix = Path(safe_name).suffix.lower()
    if suffix not in config.UPLOAD_ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(config.UPLOAD_ALLOWED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Unsupported upload file type. Allowed: {allowed}")
    return safe_name


def _read_upload_bytes(file: UploadFile) -> bytes:
    max_bytes = max(1, int(config.UPLOAD_MAX_BYTES or 0))
    content = file.file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Upload file is too large. Max size: {max_bytes} bytes.")
    return content


@app.post("/api/upload")
def upload_file(file: UploadFile = File(...)):
    """Receive file upload and return a server-side temp path."""
    from datetime import datetime as udt

    safe_name = _safe_upload_filename(file.filename)
    upload_dir = config.UPLOAD_DIR.resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    ts = udt.now().strftime("%Y%m%d_%H%M%S")
    dest = (upload_dir / f"{ts}_{uuid.uuid4().hex[:8]}_{safe_name}").resolve()
    try:
        dest.relative_to(upload_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid upload path.")

    content = _read_upload_bytes(file)
    if not content:
        raise HTTPException(status_code=400, detail="Upload file is empty.")
    dest.write_bytes(content)
    return {"filepath": str(dest), "filename": safe_name, "size": len(content)}


@app.get("/api/prompts")
def list_prompts():
    from core.prompts import list_prompts as _lp
    return _lp()


@app.get("/api/prompts/{name:path}")
def get_prompt(name: str):
    from core.prompts import load_prompt
    try:
        content = load_prompt(name)
        return {"name": name, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Prompt not found")


@app.get("/api/model-registry")
def get_model_registry():
    return serialize_registry_payload()


@app.get("/api/model-registry/defaults")
def get_model_registry_defaults():
    payload = serialize_registry_payload()
    return {
        "defaults": payload.get("defaults", {}),
        "default_profiles": payload.get("default_profiles", {}),
    }


@app.put("/api/model-registry")
def update_model_registry(req: ModelRegistryUpdateRequest):
    try:
        return save_registry(
            profiles=[item.model_dump(by_alias=False, exclude_none=True) for item in req.profiles],
            defaults=req.defaults,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/model-registry/test")
async def test_model_registry_profile(req: ModelRegistryTestRequest):
    try:
        return await test_profile_connection(
            profile_id=req.profile_id,
            profile_payload=req.profile.model_dump(by_alias=False, exclude_none=True) if req.profile else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --- Node execution ---

@app.post("/api/nodes/run")
def run_node(req: RunRequest, background: BackgroundTasks):
    run_id = str(uuid.uuid4())[:8]

    # Create runner
    runner = NodeRunner(node_type=req.node_type)
    runner.run_id = run_id
    runner.set_inputs(req.inputs)
    runner.set_config(req.config)

    _runs[run_id] = {"status": "running", "result": None, "runner": runner}

    handler = get_handler(req.node_type)
    if not handler:
        _runs[run_id] = {"status": "error", "result": {"error": f"Unknown node type: {req.node_type}"}}
        return {"run_id": run_id, "status": "error"}

    def execute():
        try:
            handler(runner)
            runner.save_snapshot()
            _runs[run_id] = {"status": "done", "result": runner._outputs, "runner": runner}
        except Exception as e:
            import traceback
            runner.add_log(f"ERROR: {e}")
            runner.set_meta("error", str(e))
            runner.set_meta("traceback", traceback.format_exc())
            runner.save_snapshot()
            _runs[run_id] = {"status": "error", "result": {"error": str(e)}, "runner": runner}

    background.add_task(execute)
    return {"run_id": run_id, "status": "running"}


@app.get("/api/nodes/run/{run_id}")
def get_run_status(run_id: str):
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    resp = {
        "status": run["status"],
        "result": run["result"],
        "logs": run.get("runner", NodeRunner("")).logs if hasattr(run.get("runner"), "_logs") else [],
    }
    return resp


@app.get("/api/nodes/run/{run_id}/stream")
def stream_run_logs(run_id: str):
    """SSE stream for real-time log delivery."""
    from fastapi.responses import StreamingResponse
    import asyncio

    run = _runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    runner = run.get("runner")
    if not runner:
        raise HTTPException(status_code=400, detail="No runner")

    async def event_stream():
        seen = len(runner.logs)
        while True:
            current = len(runner.logs)
            if current > seen:
                for line in runner.logs[seen:]:
                    yield f"data: {line}\n\n"
                seen = current
            if run["status"] != "running":
                yield f"data: [STATUS] {run['status']}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/runs")
def list_runs(node_type: str = ""):
    """List run snapshots, optionally filter by node_type."""
    if not RUNS_DIR.exists():
        return []
    runs = []
    for d in sorted(RUNS_DIR.iterdir(), reverse=True)[:50]:
        meta_file = d / "meta.json"
        if not meta_file.exists():
            continue
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        if node_type and meta.get("node_type", "") != node_type:
            continue
        # Read output summary
        output_file = d / "output.json"
        if output_file.exists():
            output = json.loads(output_file.read_text(encoding="utf-8"))
            meta["output_summary"] = {k: v for k, v in output.items()
                                        if k in ("output_path", "score")}
        runs.append(meta)
    return runs


@app.get("/api/runs/{run_id}/replay")
def replay_run(run_id: str, background: BackgroundTasks):
    """Replay a previous run with its exact inputs and config."""
    for d in RUNS_DIR.iterdir():
        if d.is_dir() and run_id in d.name:
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            node_type = meta.get("node_type", "")
            inp_file = d / "input.json"
            cfg_file = d / "config.json"
            inputs = json.loads(inp_file.read_text(encoding="utf-8")) if inp_file.exists() else {}
            config = json.loads(cfg_file.read_text(encoding="utf-8")) if cfg_file.exists() else {}

            new_run_id = str(uuid.uuid4())[:8]
            runner = NodeRunner(node_type=node_type)
            runner.run_id = new_run_id
            runner.set_inputs(inputs)
            runner.set_config(config)
            _runs[new_run_id] = {"status": "running", "result": None, "runner": runner}

            handler = get_handler(node_type)
            if not handler:
                _runs[new_run_id] = {"status": "error", "result": {"error": f"Unknown node type: {node_type}"}}
                return {"run_id": new_run_id, "status": "error"}

            def execute():
                try:
                    handler(runner)
                    runner.save_snapshot()
                    _runs[new_run_id] = {"status": "done", "result": runner._outputs, "runner": runner}
                except Exception as e:
                    import traceback
                    runner.add_log(f"ERROR: {e}")
                    runner.set_meta("error", str(e))
                    runner.set_meta("traceback", traceback.format_exc())
                    runner.save_snapshot()
                    _runs[new_run_id] = {"status": "error", "result": {"error": str(e)}, "runner": runner}

            background.add_task(execute)
            return {"run_id": new_run_id, "status": "running", "replayed_from": run_id}

    raise HTTPException(status_code=404, detail="Run not found")


@app.get("/api/runs/{run_id}")
def get_run_snapshot(run_id: str):
    """Get full run snapshot data."""
    # Find by run_id prefix
    for d in RUNS_DIR.iterdir():
        if d.is_dir() and run_id in d.name:
            result = {}
            for f in d.iterdir():
                if f.suffix == ".json":
                    result[f.stem] = json.loads(f.read_text(encoding="utf-8"))
                elif f.suffix == ".txt":
                    result[f.stem] = f.read_text(encoding="utf-8")
            return result
    raise HTTPException(status_code=404, detail="Run not found")


@app.get("/api/search")
def search(query: str = ""):
    """Unified search: workflows, runs, prompts."""
    import fnmatch
    results = []
    q = query.lower().strip()

    if RUNS_DIR.exists():
        for d in RUNS_DIR.iterdir():
            if not d.is_dir():
                continue
            meta_file = d / "meta.json"
            if not meta_file.exists():
                continue
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if q and q not in meta.get("node_type", "").lower():
                continue
            results.append({
                "type": "run",
                "id": meta.get("run_id", ""),
                "label": f"{meta.get('node_type', '?')} run",
                "sub": meta.get("started_at", "")[:19],
            })

    if WORKFLOWS_DIR.exists():
        for f in WORKFLOWS_DIR.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            name = data.get("name", f.stem)
            if q and q not in name.lower():
                continue
            results.append({
                "type": "workflow",
                "id": f.stem,
                "label": name,
                "sub": f"{len(data.get('nodes', []))} nodes",
            })

    return results[:20]


@app.get("/api/runs/{run_id_a}/diff")
def diff_runs(run_id_a: str, run_id_b: str):
    """Compare two run outputs."""
    def load(run_id):
        for d in RUNS_DIR.iterdir():
            if d.is_dir() and run_id in d.name:
                inp = json.loads((d / "input.json").read_text(encoding="utf-8")) if (d / "input.json").exists() else {}
                out = json.loads((d / "output.json").read_text(encoding="utf-8")) if (d / "output.json").exists() else {}
                raw = (d / "raw_llm.json").read_text(encoding="utf-8") if (d / "raw_llm.json").exists() else ""
                return {"inputs": inp, "outputs": out, "raw_llm": raw[:2000]}
        return None

    a = load(run_id_a)
    b = load(run_id_b)
    if not a or not b:
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "left_run": run_id_a,
        "right_run": run_id_b,
        "left": a,
        "right": b,
        "input_match": a["inputs"] == b["inputs"],
        "output_match": a["outputs"] == b["outputs"],
    }


# === Pipeline API ===

class PipelineRequest(BaseModel):
    book_id: int = 0
    filepath: str = ""
    genre: str = "short_drama"
    episode_count: int = 20
    episode_duration: int = 3
    scope: str = "auto"
    scope_chapters: int = 0
    from_step: str | None = None
    stop_after: str | None = None
    preferred_title: str | None = Field(default=None, validation_alias=AliasChoices("preferred_title", "preferredTitle"))


# In-memory task tracking
_pipeline_tasks: dict[str, dict] = {}


@app.post("/api/pipeline/script")
async def run_script_pipeline(req: PipelineRequest, bg: BackgroundTasks):
    """Run the full script production pipeline as a background task."""
    import uuid
    from pathlib import Path

    task_id = uuid.uuid4().hex[:12]
    requested_episodes = list(range(1, max(int(req.episode_count or 0), 0) + 1))
    _pipeline_tasks[task_id] = {
        "status": "queued",
        "progress": 0,
        "current_step": "queued",
        "warnings": [],
        "book_id": req.book_id,
        "genre": req.genre,
        "requested_episodes": requested_episodes,
        "episodes": [_make_storyboard_episode_task(ep) for ep in requested_episodes],
        "started_at": datetime.utcnow().isoformat(),
        "finished_at": None,
        "error": None,
    }
    _summarize_storyboard_task(_pipeline_tasks[task_id])
    _persist_task_state(task_id, "pipeline", _pipeline_tasks[task_id])

    async def _run():
        try:
            _pipeline_tasks[task_id]["status"] = "running"
            _pipeline_tasks[task_id]["current_step"] = "starting"
            _persist_task_state(task_id, "pipeline", _pipeline_tasks[task_id])
            from models import Session, Book, Chapter, BookBible, EpisodeOutline, Script, StoryboardShot
            from core.ingest import ingest
            from agents.reader import ReaderAgent
            from agents.bible import BibleAgent
            from agents.portrait import PortraitAgent
            from agents.adapter import AdapterAgent
            from agents.outline import OutlineAgent
            from agents.scriptwriter import ScriptwriterAgent
            from agents.qa import QAAgent
            from agents.storyboard import StoryboardAgent

            book_id = req.book_id
            genre = req.genre
            ep_count = req.episode_count

            # Determine current pipeline stage from book status
            current_status = "imported"
            if not req.filepath:
                with Session() as s:
                    book_obj = s.get(Book, book_id)
                    if not book_obj:
                        _pipeline_tasks[task_id]["status"] = "error"
                        _pipeline_tasks[task_id]["current_step"] = "Book not found"
                        _pipeline_tasks[task_id]["finished_at"] = datetime.utcnow().isoformat()
                        _persist_task_state(task_id, "pipeline", _pipeline_tasks[task_id])
                        return
                    current_status = book_obj.status or "imported"

            status_ranks = {
                "imported": 0, "ingested": 1, "read": 1, "bibeled": 2,
                "portraited": 3, "adapted": 4, "outlined": 5, "scripted": 6,
                "storyboarded": 7,
            }
            rank = status_ranks.get(current_status, 0)

            # Check genre-specific progress
            with Session() as s:
                genre_outlines = s.query(EpisodeOutline).filter(
                    EpisodeOutline.book_id == book_id,
                    EpisodeOutline.genre == genre,
                ).count()
                genre_scripts = s.query(Script).filter(
                    Script.book_id == book_id,
                    Script.genre == genre,
                ).count()

            genre_adapted = genre_outlines > 0 or genre_scripts > 0
            genre_outlined = genre_outlines > 0

            # Count existing QA results to know if we need to re-run
            with Session() as s:
                from models import QAResult
                existing_qa = s.query(QAResult).filter(
                    QAResult.book_id == book_id
                ).count()

            steps = [
                ("ingest", rank < 0 or req.filepath != ""),
                ("read", rank < 1),
                ("bible", rank < 2),
                ("portrait", rank < 3),
                ("adapt", rank < 4 and not genre_adapted),
                ("outline", not genre_outlined),
                ("script", genre_outlined and genre_scripts < ep_count),
                ("qa", genre_outlined and genre_scripts > 0 and existing_qa < genre_scripts),
            ]

            script_steps_needed = max(0, ep_count - genre_scripts)
            base_steps = sum(1 for _, needed in steps if needed)
            total_steps = base_steps + script_steps_needed
            completed = 0
            non_blocking_warnings: list[str] = []

            def update_step(step_name: str):
                nonlocal completed
                completed += 1
                pct = min(99, int((completed / max(total_steps, 1)) * 100))
                _pipeline_tasks[task_id]["progress"] = pct
                _pipeline_tasks[task_id]["current_step"] = step_name
                _persist_task_state(task_id, "pipeline", _pipeline_tasks[task_id])

            # Handle filepath ingest at step level
            if req.filepath:
                update_step("瀵煎叆鏂囦欢")
                ingest_result = await asyncio.to_thread(ingest, req.filepath, req.preferred_title)
                book_id = ingest_result["book_id"]
                _pipeline_tasks[task_id]["new_book_id"] = book_id
                _pipeline_tasks[task_id]["book_id"] = book_id
                _persist_task_state(task_id, "pipeline", _pipeline_tasks[task_id])
                update_step("鏂囦欢瀵煎叆瀹屾垚")

            # Step: ingest (skip if already imported)
            if rank < 1:
                update_step("loading text")
                await asyncio.sleep(0.5)
                update_step("鍒嗗壊绔犺妭")
                # ingest can only be called if we have filepath
                # For existing books that are already imported, we skip
                if current_status == "imported":
                    update_step("ingest (no-op, no file)")
                update_step("ingest complete")

            # Step: read
            if rank < 1:
                update_step("閫愮珷鍒嗘瀽 (reader)")
                reader = ReaderAgent(book_id)
                # Apply scope via end_ch parameter (acts as limit)
                reader_limit = 0
                if req.scope == "first_n" and req.scope_chapters > 0:
                    reader_limit = req.scope_chapters
                await asyncio.to_thread(reader.run, None, reader_limit if reader_limit > 0 else None)
                update_step("reader complete")

            # Step: bible
            if rank < 2:
                update_step("生成世界观 Bible")
                bible_agent = BibleAgent(book_id)
                await asyncio.to_thread(bible_agent.run)
                update_step("bible complete")

            # Step: portrait
            if rank < 3:
                # Step: resolve aliases (before portrait)
                try:
                    from core.alias_resolver import resolve_aliases
                    with Session() as s:
                        update_step("归并角色别名")
                        resolve_aliases(book_id, s)
                        update_step("alias resolve complete")
                except Exception as resolve_exc:
                    logger.warning("Alias resolution failed (non-blocking): %s", resolve_exc)
                    non_blocking_warnings.append(f"别名归并已跳过：{resolve_exc}")

                update_step("生成人物画像")
                portrait_agent = PortraitAgent(book_id)
                try:
                    await asyncio.wait_for(asyncio.to_thread(portrait_agent.run), timeout=20)
                    update_step("portrait complete")
                except Exception as portrait_exc:
                    portrait_reason = str(portrait_exc).strip() or "portrait step timed out"
                    non_blocking_warnings.append(f"人物画像已跳过：{portrait_reason}")
                    _pipeline_tasks[task_id]["warnings"] = non_blocking_warnings
                    _pipeline_tasks[task_id]["current_step"] = "人物画像跳过，继续主链路"
                    _persist_task_state(task_id, "pipeline", _pipeline_tasks[task_id])

                # Step: portrait QA (auto-detect issues after portrait)
                try:
                    from core.portrait_qa import run_portrait_qa
                    with Session() as s:
                        qa_report = run_portrait_qa(book_id, s)
                        if qa_report.gender_conflicts:
                            non_blocking_warnings.append(f"检测到 {len(qa_report.gender_conflicts)} 个人物性别冲突，请在「人物质检」面板中确认")
                        if qa_report.merge_candidates:
                            high_conf = [m for m in qa_report.merge_candidates if m.confidence == "high"]
                            if high_conf:
                                non_blocking_warnings.append(f"检测到 {len(high_conf)} 组高置信度疑似重复角色，请在「人物质检」面板中合并")
                        _pipeline_tasks[task_id]["warnings"] = non_blocking_warnings
                        _persist_task_state(task_id, "pipeline", _pipeline_tasks[task_id])
                except Exception as qa_exc:
                    logger.warning("Portrait QA failed (non-blocking): %s", qa_exc)

            if str(req.stop_after or "").strip().lower() == "content":
                with Session() as s:
                    book = s.get(Book, book_id)
                    if book:
                        current_book_status = str(book.status or "").strip().lower()
                        if current_book_status in {"", "draft", "imported", "ingested", "read"}:
                            book.status = "bibeled" if rank < 2 else (book.status or "bibeled")
                        s.commit()

                _pipeline_tasks[task_id]["status"] = "done"
                _pipeline_tasks[task_id]["progress"] = 100
                _pipeline_tasks[task_id]["current_step"] = "content preparation complete"
                _pipeline_tasks[task_id]["warnings"] = non_blocking_warnings
                _pipeline_tasks[task_id]["finished_at"] = datetime.utcnow().isoformat()
                _persist_task_state(task_id, "pipeline", _pipeline_tasks[task_id])
                return

            # Step: adapt (genre-specific, skip if already done for this genre)
            if rank < 4 and not genre_adapted:
                update_step("生成改编方案")
                adapt_agent = AdapterAgent(book_id, genre=genre)
                await asyncio.to_thread(adapt_agent.run)
                update_step("adapt complete")

            # Step: outline (genre-specific)
            if not genre_outlined:
                update_step("鐢熸垚鍒嗛泦澶х翰")
                outline_agent = OutlineAgent(book_id, genre=genre, episode_count=ep_count)
                await asyncio.to_thread(outline_agent.run)
                update_step("outline complete")

            # Step: script (genre-specific)
            # Determine how many episodes have outlines to write scripts for
            with Session() as s:
                actual_outlines = s.query(EpisodeOutline).filter(
                    EpisodeOutline.book_id == book_id,
                    EpisodeOutline.genre == genre,
                ).count()
            script_target = min(ep_count, actual_outlines) if actual_outlines > 0 else ep_count
            if genre_scripts < script_target:
                for ep in range(genre_scripts + 1, script_target + 1):
                    update_step(f"Generate episode {ep} script")
                    script_agent = ScriptwriterAgent(book_id, genre=genre)
                    await asyncio.to_thread(script_agent.run, ep)
                update_step("script writing complete")
            else:
                update_step("scripts already generated")

            # Step: QA (genre-specific, runs on all existing scripts)
            with Session() as s:
                from models import QAResult
                qa_count = s.query(QAResult).filter(
                    QAResult.book_id == book_id
                ).count()
            with Session() as s:
                actual_scripts = s.query(Script).filter(
                    Script.book_id == book_id,
                    Script.genre == genre,
                ).count()
            if qa_count < actual_scripts:
                qa_agent = QAAgent(book_id)
                for ep in range(1, actual_scripts + 1):
                    update_step(f"Run QA for episode {ep} script")
                    await asyncio.to_thread(qa_agent.run, ep)
                update_step("qa complete")

            with Session() as s:
                book = s.get(Book, book_id)
                if book:
                    book.status = "scripted"
                    s.commit()

            _pipeline_tasks[task_id]["status"] = "done"
            _pipeline_tasks[task_id]["progress"] = 100
            _pipeline_tasks[task_id]["warnings"] = non_blocking_warnings
            _pipeline_tasks[task_id]["finished_at"] = datetime.utcnow().isoformat()
            _persist_task_state(task_id, "pipeline", _pipeline_tasks[task_id])

        except Exception as exc:
            _pipeline_tasks[task_id]["status"] = "error"
            _pipeline_tasks[task_id]["current_step"] = str(exc)
            _pipeline_tasks[task_id]["error"] = str(exc)
            import traceback
            _pipeline_tasks[task_id]["traceback"] = traceback.format_exc()
            _pipeline_tasks[task_id]["finished_at"] = datetime.utcnow().isoformat()
            _persist_task_state(task_id, "pipeline", _pipeline_tasks[task_id])

    bg.add_task(_run)
    return {"task_id": task_id}


@app.get("/api/pipeline/task/{task_id}")
def get_pipeline_task(task_id: str):
    task = _pipeline_tasks.get(task_id)
    if not task:
        task = _load_persisted_task_state(task_id, "pipeline")
    if not task:
        raise HTTPException(status_code=404, detail="Pipeline task not found")
    _pipeline_tasks.setdefault(task_id, task)
    return task


class StoryboardRequest(BaseModel):
    book_id: int
    genre: str = "short_drama"
    episodes: Optional[list[int]] = None  # None = all
    resume_from_scene: dict[str, str] = Field(default_factory=dict, validation_alias=AliasChoices("resume_from_scene", "resumeFromScene"))


def _make_storyboard_episode_task(episode: int) -> dict:
    return {
        "episode": int(episode),
        "status": "queued",
        "progress": 0,
        "current_step": "queued",
        "error": "",
        "failure_kind": "",
        "guidance": "",
        "shot_count": 0,
        "total_scenes": 0,
        "completed_scenes": 0,
        "current_scene": "",
        "last_completed_scene_name": "",
        "failed_scene_name": "",
        "resume_anchor": "",
        "retry_count": 0,
        "last_retry_reason": "",
        "warning_count": 0,
        "fallback_scene_count": 0,
        "started_at": None,
        "finished_at": None,
    }


def _summarize_storyboard_task(task: dict) -> None:
    episodes = task.get("episodes", [])
    if not isinstance(episodes, list) or not episodes:
        task["completed_episodes"] = 0
        task["failed_episodes"] = 0
        task["queued_episodes"] = 0
        return

    completed = sum(1 for item in episodes if item.get("status") == "done")
    failed = sum(1 for item in episodes if item.get("status") == "error")
    queued = sum(1 for item in episodes if item.get("status") in {"queued", "running"})
    task["completed_episodes"] = completed
    task["failed_episodes"] = failed
    task["queued_episodes"] = queued


def _classify_storyboard_failure(message: str) -> tuple[str, str]:
    text = str(message or "").strip().lower()
    if (
        "failed to parse llm json response" in text
        or "truncated" in text
        or "unexpected end" in text
        or "unterminated" in text
    ):
        return (
            "llm_truncated",
            "本集输出疑似被截断。建议只重试失败集；如已有场景进度，可从断点继续。",
        )
    if (
        "empty shots" in text
        or "returned empty" in text
        or "scene split" in text
        or "not a list" in text
        or "storyboard prompts are empty" in text
    ):
        return (
            "structure_invalid",
            "结构化分镜结果不完整。请先检查剧本分场和场景结构，再重试失败集。",
        )
    if "script not found" in text or "没有剧本" in text:
        return (
            "missing_script",
            "本集还没有可用剧本。请先完成剧本，再重新生成分镜。",
        )
    return (
        "unknown_error",
        "本集分镜生成失败。建议先重试失败集；若仍失败，再检查剧本和提示词上下文。",
    )


def _update_storyboard_episode_progress(task: dict, event: dict) -> None:
    episodes = task.get("episodes", [])
    if not isinstance(episodes, list):
        return

    episode = int(event.get("episode") or 0)
    if episode <= 0:
        return
    episode_task = next((item for item in episodes if int(item.get("episode", 0)) == episode), None)
    if not episode_task:
        return

    stage = str(event.get("stage") or "").strip()
    scene_name = str(event.get("scene_name") or "").strip()
    total_scenes = int(event.get("total_scenes") or episode_task.get("total_scenes") or 0)
    if total_scenes > 0:
        episode_task["total_scenes"] = total_scenes

    if stage == "scene_list_loaded":
        episode_task["progress"] = max(int(episode_task.get("progress") or 0), 5)
        episode_task["current_step"] = f"Detected {total_scenes} scenes"
        return

    if stage == "resume_initialized":
        completed_scenes = int(event.get("completed_scenes") or 0)
        resume_after_scene = str(event.get("resume_after_scene") or "").strip()
        if completed_scenes > 0:
            episode_task["completed_scenes"] = completed_scenes
            episode_task["last_completed_scene_name"] = resume_after_scene
            episode_task["resume_anchor"] = (
                f"已完成到第 {completed_scenes} 个场景"
                + (f"，可从 {resume_after_scene} 后继续" if resume_after_scene else "，可继续生成")
            )
        episode_task["current_step"] = episode_task.get("resume_anchor") or "Resume from breakpoint"
        episode_task["progress"] = max(int(episode_task.get("progress") or 0), 8)
        return

    if stage == "scene_started":
        episode_task["current_scene"] = scene_name
        episode_task["failed_scene_name"] = scene_name
        completed_scenes = int(episode_task.get("completed_scenes") or 0)
        if total_scenes > 0:
            ratio = completed_scenes / max(total_scenes, 1)
            episode_task["progress"] = max(int(episode_task.get("progress") or 0), min(95, 10 + int(ratio * 70)))
        episode_task["current_step"] = f"Generating scene: {scene_name or 'Unnamed scene'}"
        return

    if stage == "scene_retrying":
        episode_task["current_scene"] = scene_name or episode_task.get("current_scene") or ""
        episode_task["failed_scene_name"] = episode_task["current_scene"]
        current_scene_label = episode_task["current_scene"] or "scene"
        episode_task["current_step"] = f"Retrying scene automatically: {current_scene_label}"
        episode_task["retry_count"] = int(episode_task.get("retry_count") or 0) + 1
        episode_task["guidance"] = "The first generation attempt for this scene was incomplete. The system is retrying automatically."
        episode_task["last_retry_reason"] = str(event.get("reason") or "scene_retrying")
        episode_task["progress"] = max(int(episode_task.get("progress") or 0), 12)
        return

    if stage == "scene_fallback_used":
        episode_task["current_scene"] = scene_name or episode_task.get("current_scene") or ""
        episode_task["warning_count"] = int(episode_task.get("warning_count") or 0) + 1
        episode_task["fallback_scene_count"] = int(episode_task.get("fallback_scene_count") or 0) + 1
        episode_task["last_retry_reason"] = str(event.get("reason") or "scene_fallback_used")
        episode_task["guidance"] = "This scene fell back to the structured safe-generation path. Review it first after generation finishes."
        episode_task["current_step"] = f"Using fallback scene generation: {episode_task['current_scene'] or 'Unnamed scene'}"
        episode_task["progress"] = max(int(episode_task.get("progress") or 0), 18)
        return

    if stage == "scene_completed":
        completed_scenes = int(episode_task.get("completed_scenes") or 0) + 1
        episode_task["completed_scenes"] = completed_scenes
        episode_task["last_completed_scene_name"] = scene_name
        if total_scenes > 0:
            ratio = completed_scenes / max(total_scenes, 1)
            episode_task["progress"] = max(int(episode_task.get("progress") or 0), min(95, 15 + int(ratio * 75)))
            episode_task["resume_anchor"] = f"Completed {completed_scenes}/{total_scenes} scenes"
        else:
            episode_task["resume_anchor"] = f"Completed {completed_scenes} scenes"
        episode_task["current_step"] = f"Completed scene: {scene_name or 'Unnamed scene'}"


@app.post("/api/pipeline/storyboard")
async def run_storyboard(req: StoryboardRequest, bg: BackgroundTasks):
    """Run storyboard generation independently, optionally for selected episodes."""
    import uuid
    task_id = uuid.uuid4().hex[:12]
    requested_episodes = sorted(set(int(ep) for ep in (req.episodes or []) if int(ep) > 0))
    _storyboard_tasks[task_id] = {
        "status": "running",
        "progress": 0,
        "current_step": "starting",
        "book_id": req.book_id,
        "genre": req.genre,
        "requested_episodes": requested_episodes,
        "episodes": [_make_storyboard_episode_task(ep) for ep in requested_episodes],
        "started_at": datetime.utcnow().isoformat(),
        "finished_at": None,
        "error": None,
    }
    _summarize_storyboard_task(_storyboard_tasks[task_id])
    _persist_task_state(task_id, "storyboard", _storyboard_tasks[task_id])

    def persist_storyboard_task() -> None:
        _summarize_storyboard_task(_storyboard_tasks[task_id])
        _persist_task_state(task_id, "storyboard", _storyboard_tasks[task_id])

    async def _run():
        try:
            from agents.storyboard import StoryboardAgent
            from models import Session, Script

            with Session() as s:
                q = s.query(Script).filter(
                    Script.book_id == req.book_id,
                    Script.genre == req.genre,
                )
                if req.episodes:
                    q = q.filter(Script.episode.in_(req.episodes))
                scripts = q.order_by(Script.episode).all()

            if not scripts:
                _storyboard_tasks[task_id]["status"] = "error"
                _storyboard_tasks[task_id]["current_step"] = "No scripts found. Generate scripts first."
                _storyboard_tasks[task_id]["finished_at"] = datetime.utcnow().isoformat()
                persist_storyboard_task()
                return

            sb_agent = StoryboardAgent(
                req.book_id,
                genre=req.genre,
                progress_callback=lambda event: (
                    _update_storyboard_episode_progress(_storyboard_tasks[task_id], event),
                    _persist_task_state(task_id, "storyboard", _storyboard_tasks[task_id]),
                ),
            )
            episodes = [int(sc.episode) for sc in scripts]
            _storyboard_tasks[task_id]["requested_episodes"] = episodes
            _storyboard_tasks[task_id]["episodes"] = [_make_storyboard_episode_task(ep) for ep in episodes]
            persist_storyboard_task()
            total = len(scripts)
            for i, sc in enumerate(scripts):
                episode_task = next(
                    (item for item in _storyboard_tasks[task_id]["episodes"] if int(item.get("episode", 0)) == int(sc.episode)),
                    None,
                )
                if episode_task:
                    episode_task["status"] = "running"
                    episode_task["progress"] = 10
                    episode_task["current_step"] = "starting"
                    episode_task["started_at"] = datetime.utcnow().isoformat()
                    resume_after_scene = str(req.resume_from_scene.get(str(sc.episode)) or "").strip()
                    if resume_after_scene:
                        episode_task["resume_anchor"] = f"Resume after scene {resume_after_scene}"
                else:
                    resume_after_scene = str(req.resume_from_scene.get(str(sc.episode)) or "").strip()
                _storyboard_tasks[task_id]["current_step"] = f"Generate episode {sc.episode} storyboard ({i + 1}/{total})"
                _persist_task_state(task_id, "storyboard", _storyboard_tasks[task_id])
                try:
                    shots = await asyncio.to_thread(sb_agent.run, sc.episode, resume_after_scene=resume_after_scene or None)
                    if episode_task:
                        episode_task["status"] = "done"
                        episode_task["progress"] = 100
                        episode_task["current_step"] = "storyboard complete"
                        if int(episode_task.get("warning_count") or 0) > 0:
                            episode_task["current_step"] = "Storyboard done with fallback scenes"
                        episode_task["shot_count"] = len(shots or [])
                        episode_task["failure_kind"] = ""
                        episode_task["guidance"] = ""
                        if int(episode_task.get("warning_count") or 0) > 0:
                            episode_task["guidance"] = "Some scenes were auto-degraded to structured fallback shots. Please review those scenes first after generation."
                        episode_task["finished_at"] = datetime.utcnow().isoformat()
                except Exception as episode_exc:
                    failure_kind, guidance = _classify_storyboard_failure(str(episode_exc))
                    if episode_task:
                        episode_task["status"] = "error"
                        episode_task["progress"] = 100
                        episode_task["current_step"] = str(episode_exc)
                        episode_task["error"] = str(episode_exc)
                        episode_task["failure_kind"] = failure_kind
                        episode_task["guidance"] = guidance
                        if episode_task.get("last_completed_scene_name") and episode_task.get("resume_anchor"):
                            episode_task["guidance"] = (
                                f"{guidance} 当前已完成到 {episode_task['last_completed_scene_name']}，可优先从后续场景继续。"
                            )
                        episode_task["finished_at"] = datetime.utcnow().isoformat()
                finally:
                    pct = int(((i + 1) / total) * 100)
                    _storyboard_tasks[task_id]["progress"] = pct
                    persist_storyboard_task()

            completed = int(_storyboard_tasks[task_id].get("completed_episodes") or 0)
            failed = int(_storyboard_tasks[task_id].get("failed_episodes") or 0)
            if completed > 0 and failed > 0:
                _storyboard_tasks[task_id]["status"] = "partial"
                _storyboard_tasks[task_id]["current_step"] = (
                    f"Storyboard partially completed: {completed} succeeded, {failed} failed"
                )
            elif completed > 0:
                _storyboard_tasks[task_id]["status"] = "done"
                _storyboard_tasks[task_id]["current_step"] = "storyboard generation complete"
            else:
                _storyboard_tasks[task_id]["status"] = "error"
                _storyboard_tasks[task_id]["current_step"] = "storyboard generation failed"
            _storyboard_tasks[task_id]["progress"] = 100
            _storyboard_tasks[task_id]["finished_at"] = datetime.utcnow().isoformat()
            persist_storyboard_task()

        except Exception as exc:
            _storyboard_tasks[task_id]["status"] = "error"
            _storyboard_tasks[task_id]["current_step"] = str(exc)
            _storyboard_tasks[task_id]["error"] = str(exc)
            import traceback
            _storyboard_tasks[task_id]["traceback"] = traceback.format_exc()
            _storyboard_tasks[task_id]["finished_at"] = datetime.utcnow().isoformat()
        finally:
            persist_storyboard_task()

    bg.add_task(_run)
    return {"task_id": task_id}


_storyboard_tasks: dict = {}
_creative_tasks: dict[str, dict] = {}
_storyboard_prompt_compile_tasks: dict[str, dict] = {}


def _stamp_creative_task_state(task_state: dict[str, Any], *, created: bool = False) -> None:
    now = datetime.utcnow().isoformat()
    if created and not str(task_state.get("created_at") or "").strip():
        task_state["created_at"] = now
    task_state["updated_at"] = now
    task_id = str(task_state.get("task_id") or "").strip()
    if task_id:
        raw_kind = str(task_state.get("kind") or task_state.get("task_kind") or "").strip()
        if raw_kind in {"image", "video", "reference-image"}:
            task_kind = f"creative-{raw_kind}"
        elif raw_kind == "machine_prompt_api_submission":
            task_kind = "creative-machine_prompt_api_submission"
        elif raw_kind.startswith("creative"):
            task_kind = raw_kind
        else:
            target_kind = str(task_state.get("target_kind") or "creative").strip()
            task_kind = "creative-reference-image" if target_kind == "reference-image" else f"creative-{target_kind}"
        _persist_task_state(task_id, task_kind, task_state)


class CreativeGenerationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    book_id: int = Field(validation_alias=AliasChoices("book_id", "bookId"))
    episode: int
    shot_id: str = Field(validation_alias=AliasChoices("shot_id", "shotId"))
    source_node_id: str = Field(validation_alias=AliasChoices("source_node_id", "sourceNodeId"))
    source_asset_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("source_asset_id", "sourceAssetId"))
    first_frame_asset_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("first_frame_asset_id", "firstFrameAssetId"))
    first_frame_url: Optional[str] = Field(default=None, validation_alias=AliasChoices("first_frame_url", "firstFrameUrl"))
    asset_scope: Optional[str] = Field(default=None, validation_alias=AliasChoices("asset_scope", "assetScope"))
    asset_subject: Optional[str] = Field(default=None, validation_alias=AliasChoices("asset_subject", "assetSubject"))
    target_kind: Optional[str] = Field(default=None, validation_alias=AliasChoices("target_kind", "targetKind"))
    prompt: str = ""
    model: Optional[str] = None
    model_profile_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("model_profile_id", "modelProfileId"))
    reference_asset_ids: list[str] = Field(default_factory=list, validation_alias=AliasChoices("reference_asset_ids", "referenceAssetIds"))
    reference_images: list[dict] = Field(default_factory=list, validation_alias=AliasChoices("reference_images", "referenceImages"))
    aspect_ratio: str = Field(default="16:9", validation_alias=AliasChoices("aspect_ratio", "aspectRatio"))
    negative_prompt: str = Field(default="", validation_alias=AliasChoices("negative_prompt", "negativePrompt"))
    duration_seconds: Optional[int] = Field(default=None, validation_alias=AliasChoices("duration_seconds", "durationSeconds"))
    count: int = 1
    simulate_error: bool = Field(default=False, validation_alias=AliasChoices("simulate_error", "simulateError"))


class AdoptVersionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    book_id: int = Field(validation_alias=AliasChoices("book_id", "bookId"))
    episode: int
    shot_id: str = Field(validation_alias=AliasChoices("shot_id", "shotId"))
    kind: str
    asset_id: str = Field(validation_alias=AliasChoices("asset_id", "assetId"))


def _make_asset_preview(kind: str, title: str, subtitle: str) -> str:
    accent = "#eab308" if kind == "image" else "#22c55e" if kind == "video" else "#ec4899"
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
      <defs>
        <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#0f172a" />
          <stop offset="100%" stop-color="#020617" />
        </linearGradient>
      </defs>
      <rect width="640" height="360" rx="24" fill="url(#g)" />
      <rect x="30" y="30" width="580" height="300" rx="18" fill="#0b1220" stroke="{accent}" stroke-width="2" />
      <circle cx="90" cy="88" r="16" fill="{accent}" />
      <text x="122" y="94" fill="#e2e8f0" font-size="26" font-family="Segoe UI, sans-serif">{title}</text>
      <text x="44" y="146" fill="#94a3b8" font-size="18" font-family="Segoe UI, sans-serif">{subtitle}</text>
      <text x="44" y="302" fill="#64748b" font-size="15" font-family="Segoe UI, sans-serif">鐢卞師鍨嬪伐浣滃彴浠诲姟閫傞厤灞傜敓鎴愬苟鍥炲～</text>
    </svg>
    """
    from urllib.parse import quote
    return f"data:image/svg+xml,{quote(svg)}"


def _normalize_display_text(value: str | None, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback

    text = value.strip()
    if not text:
        return fallback

    compact = "".join(text.split())
    if "锟" in compact:
        return fallback

    question_mark_ratio = compact.count("?") / len(compact) if compact else 0
    if compact.count("?") >= 2 and question_mark_ratio >= 0.2:
        return fallback

    return text


_INVALID_BOOK_TITLE_SIGNALS = [
    "无法从给定文本中提取标题",
    "请提供包含书名",
    "请提供包含书籍/故事标题",
    "请提供包含书籍",
    "未包含书籍或故事标题信息",
    "标题信息",
]


def _normalize_book_title_for_display(value: str | None, book_id: int | None = None) -> str:
    fallback = f"未命名项目 {book_id}" if book_id else "未命名项目"
    normalized = _normalize_display_text(value, fallback)
    if normalized == fallback:
        return fallback

    text = normalized.strip()
    if any(signal in text for signal in _INVALID_BOOK_TITLE_SIGNALS):
        return fallback

    compact = "".join(text.split())
    if (
        not any("\u4e00" <= ch <= "\u9fff" for ch in compact)
        and any(token in compact for token in ["脙", "脗", "脜", "脝", "脨", "脴", "脼", "茫", "氓", "忙", "莽"])
    ):
        return fallback

    return text


def _refresh_mock_reference_asset_preview(row) -> None:
    image_url = str(getattr(row, "image_url", "") or "").strip()
    if not image_url.startswith("data:image/svg+xml,"):
        return

    model_name = str(getattr(row, "model", "") or "").strip()
    meta_info = safe_json_loads(getattr(row, "meta_info", None)) if getattr(row, "meta_info", None) else {}
    uses_mock = bool(meta_info.get("usesMock")) or model_name == "mock-image-v1"
    if not uses_mock:
        return

    asset_name = _normalize_display_text(getattr(row, "asset_name", None), "未命名资产")
    version = str(meta_info.get("version") or "v1").strip() or "v1"
    row.image_url = _make_asset_preview("image", f"{asset_name} 参考图 {version}", model_name or "mock-image-v1")


def _sanitize_asset_payload(value):
    if isinstance(value, list):
        return [_sanitize_asset_payload(item) for item in value]

    if not isinstance(value, dict):
        return value

    cleaned = {key: _sanitize_asset_payload(item) for key, item in value.items()}

    if any(key in cleaned for key in ("url", "uri", "path", "src", "file", "filepath", "previewUrl", "preview_url")):
        metadata = cleaned.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        fallback_subject = _normalize_display_text(
            cleaned.get("asset_subject")
            or cleaned.get("assetSubject")
            or cleaned.get("subject")
            or cleaned.get("shot_id")
            or cleaned.get("shotId"),
            "资产",
        )
        kind = cleaned.get("kind")
        label = cleaned.get("label") or cleaned.get("version") or "v1"
        default_title = f"{'视频' if kind == 'video' else '音频' if kind == 'audio' else '分镜图'} {fallback_subject} {label}"
        if metadata.get("imageRole") == "reference":
            default_title = f"{fallback_subject} 参考图 {label}"
        cleaned["title"] = _normalize_display_text(cleaned.get("title"), default_title)

    return cleaned


def _sanitize_reference_asset(asset: dict, subject: str) -> dict:
    cleaned = _sanitize_asset_payload(asset)
    if not isinstance(cleaned, dict):
        return asset

    subject_text = _normalize_display_text(subject, "参考资产")
    metadata = cleaned.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    label = cleaned.get("label") or cleaned.get("version") or "v1"
    cleaned["title"] = _normalize_display_text(cleaned.get("title"), f"{subject_text} 参考图 {label}")
    cleaned["prompt"] = _normalize_display_text(cleaned.get("prompt"), "")
    metadata["assetSubject"] = _normalize_display_text(metadata.get("assetSubject"), subject_text)
    cleaned["metadata"] = metadata
    return cleaned


def _sanitize_storyboard_asset_links(asset_links: dict, scene_name: str | None) -> dict:
    cleaned = _sanitize_asset_payload(asset_links)
    if not isinstance(cleaned, dict):
        return {}

    references = cleaned.get("references", {})
    if not isinstance(references, dict):
        return cleaned

    if isinstance(references.get("scene"), list):
        references["scene"] = [
            _sanitize_reference_asset(asset, _normalize_display_text(scene_name, "场景"))
            for asset in references["scene"]
            if isinstance(asset, dict)
        ]

    for bucket_key in ("characters", "props"):
        bucket = references.get(bucket_key, {})
        if not isinstance(bucket, dict):
            continue
        references[bucket_key] = {
            subject: [
                _sanitize_reference_asset(asset, subject)
                for asset in assets
                if isinstance(asset, dict)
            ]
            for subject, assets in bucket.items()
            if isinstance(assets, list)
        }

    cleaned["references"] = references
    return cleaned


def _load_asset_links(raw_value: str | None) -> dict:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _coerce_storyboard_shot_id(shot_id: str | int) -> int:
    if isinstance(shot_id, int):
        return shot_id

    raw = str(shot_id).strip()
    if not raw:
        raise ValueError("shot_id is empty")

    if raw.isdigit():
        return int(raw)

    tail = raw.split("-")[-1].strip()
    if tail.isdigit():
        return int(tail)

    raise ValueError(f"Unsupported shot_id format: {shot_id}")


def _json_loads_list(raw_value: str | None) -> list:
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        return raw_value
    text = str(raw_value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return [item.strip() for item in re.split(r"[，,；;\n\r]+", text) if item.strip()]


def _normalize_asset_shot_ids(shot_ids: list | None) -> list[str]:
    normalized: list[str] = []
    for item in shot_ids or []:
        value = str(item or "").strip()
        if not value:
            continue
        normalized.append(value)
    return list(dict.fromkeys(normalized))


def _normalize_makeup_stage_name(value: str | None) -> str:
    return str(value or "").strip().lower()


def _normalize_makeup_scene_key(value: str | None) -> str:
    text = _normalize_asset_match_text(value)
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)


def _makeup_scope_from_stage_name(stage_name: str | None, shot_ids: list | None = None) -> str:
    normalized = _normalize_makeup_stage_name(stage_name)
    if normalized in {"base_identity", "base", "identity", "鍩虹瀹氬"}:
        return "base_identity"
    if normalized.startswith("shot_") or normalized.startswith("shot-") or (shot_ids and len(shot_ids) > 0):
        return "shot_variant"
    if normalized.startswith("scene_") or normalized.startswith("scene-"):
        return "scene_variant"
    if normalized.startswith("episode_") or normalized.startswith("episode-") or normalized.endswith("_default"):
        return "episode_default"
    if not normalized:
        return "episode_default"
    return "custom_variant"


def _makeup_scope_from_row(row, peer_rows: list | None = None) -> str:
    shot_ids = _json_loads_list(getattr(row, "shot_ids", None))
    explicit_scope = _makeup_scope_from_stage_name(getattr(row, "stage_name", ""), shot_ids)
    if explicit_scope != "custom_variant":
        return explicit_scope

    meta_info = safe_json_loads(getattr(row, "meta_info", "{}")) if getattr(row, "meta_info", None) else {}
    if isinstance(meta_info, dict):
        structured_scope = str(meta_info.get("scope", "") or "").strip()
        if structured_scope in {"base_identity", "episode_default", "scene_variant", "shot_variant"}:
            return structured_scope

    normalized_stage = _normalize_makeup_stage_name(getattr(row, "stage_name", ""))
    valid_peers = [peer for peer in (peer_rows or []) if getattr(peer, "id", None) is not None]
    if not shot_ids and normalized_stage and len(valid_peers) == 1:
        return "base_identity"

    return explicit_scope


def _makeup_scope_label(scope: str) -> str:
    mapping = {
        "base_identity": "基础定妆",
        "episode_default": "集默认定妆",
        "scene_variant": "场次精调定妆",
        "shot_variant": "镜头精调定妆",
        "custom_variant": "自定义定妆",
    }
    return mapping.get(scope, "定妆")


def _needs_state_change_makeup_warning(payload: dict) -> bool:
    reference_source = str(payload.get("reference_source") or "").strip()
    variant_scope = str(payload.get("variant_scope") or payload.get("makeup_scope") or "").strip()
    has_versioned_makeup = any(
        str(payload.get(key) or "").strip()
        for key in ("stage_name", "base_stage_name")
    )
    if reference_source == "missing":
        return False
    if not has_versioned_makeup:
        return False
    if variant_scope in {"shot_variant", "scene_variant"}:
        return False
    return reference_source in {"base_identity", "active_variant", "resolved_makeup"}


def _makeup_targets_scene(stage_name: str | None, scene_name: str | None) -> bool:
    normalized_stage = _normalize_makeup_stage_name(stage_name)
    if not normalized_stage.startswith("scene_") and not normalized_stage.startswith("scene-"):
        return False
    stage_tail = re.split(r"scene[_-]", normalized_stage, maxsplit=1)[-1]
    return bool(stage_tail and stage_tail == _normalize_makeup_scene_key(scene_name))


def _makeup_targets_shot(shot_ids: list | None, shot_id: str | int) -> bool:
    target = str(shot_id).strip()
    for item in shot_ids or []:
        normalized = str(item).strip()
        if not normalized:
            continue
        if normalized == target:
            return True
        tail = normalized.split("-")[-1].strip()
        if tail == target:
            return True
    return False


def _is_integer_string(value: str | int | None) -> bool:
    return bool(re.fullmatch(r"-?\d+", str(value or "").strip()))


def _build_character_profile_fallback_makeup_row(profile):
    profile_id = int(getattr(profile, "id", 0) or 0)
    name = str(getattr(profile, "name", "") or "").strip()
    identity = str(getattr(profile, "identity", "") or "").strip()
    age_range = str(getattr(profile, "age_range", "") or "").strip()
    gender = str(getattr(profile, "gender", "") or "").strip()
    temperament = str(getattr(profile, "temperament", "") or "").strip()
    facial_features = str(getattr(profile, "facial_features", "") or "").strip()
    body_type = str(getattr(profile, "body_type", "") or "").strip()
    skin_tone = str(getattr(profile, "skin_tone", "") or "").strip()
    distinguishing_marks = str(getattr(profile, "distinguishing_marks", "") or "").strip()
    refined_outfit = str(getattr(profile, "signature_outfit", "") or "").strip()
    refined_accessories = str(getattr(profile, "accessories", "") or "").strip()
    hair_style = str(getattr(profile, "hairstyle", "") or "").strip()
    vibe = str(getattr(profile, "vibe", "") or "").strip()
    appearance_parts = [facial_features, body_type, skin_tone, distinguishing_marks]
    appearance = "，".join([part for part in appearance_parts if part])
    if not appearance:
        appearance = vibe

    meta_info = {
        "scope": "base_identity",
        "record_source": "character_profile_fallback",
        "profile_id": profile_id,
        "readonly": True,
    }

    return SimpleNamespace(
        id=profile_id,
        profile_id=profile_id,
        episode=0,
        character_name=name,
        stage_name="base_identity",
        makeup_scope="base_identity",
        scope_label="基础定妆",
        gender=gender,
        identity=identity,
        age_range=age_range,
        temperament=temperament,
        appearance=appearance,
        refined_outfit=refined_outfit,
        refined_accessories=refined_accessories,
        makeup_spec="",
        hair_style=hair_style,
        expression_mood=vibe,
        visual_prompt_en="",
        visual_prompt_zh=str(getattr(profile, "visual_prompt_zh", "") or "").strip(),
        core_prompt_en="",
        core_prompt_zh=str(getattr(profile, "core_prompt_zh", "") or "").strip(),
        outfit_prompt_en="",
        outfit_prompt_zh=str(getattr(profile, "outfit_prompt_zh", "") or "").strip(),
        scene_prompt_en="",
        scene_prompt_zh=str(getattr(profile, "scene_prompt_zh", "") or "").strip(),
        consistency_notes="legacy-character-profile-fallback",
        meta_info=json.dumps(meta_info, ensure_ascii=False),
        shot_ids="[]",
        jimeng_ref_name="",
        negative_prompt="",
        asset_status="draft",
        record_source="character_profile_fallback",
        is_readonly=True,
        created_at=getattr(profile, "created_at", None),
        updated_at=getattr(profile, "updated_at", None),
    )


def _materialize_character_profile_fallback_makeup(s, book_id: int, asset_id: str | int | None):
    from models import Book, CharacterProfile, VisualMakeup

    if not _is_integer_string(asset_id):
        return None
    target_id = int(str(asset_id).strip())

    existing = s.query(VisualMakeup).filter(
        VisualMakeup.book_id == book_id,
        VisualMakeup.id == target_id,
    ).first()
    if existing:
        return existing

    profile = s.query(CharacterProfile).filter(
        CharacterProfile.book_id == book_id,
        CharacterProfile.id == target_id,
    ).first()
    if not profile:
        return None

    fallback = _build_character_profile_fallback_makeup_row(profile)
    book = s.query(Book).filter(Book.id == book_id).first()
    row = VisualMakeup(
        id=target_id,
        book_id=book_id,
        book_title=str(getattr(book, "title", "") or ""),
        episode=0,
        character_name=str(getattr(fallback, "character_name", "") or "").strip(),
        stage_name="base_identity",
        refined_outfit=str(getattr(fallback, "refined_outfit", "") or "").strip(),
        refined_accessories=str(getattr(fallback, "refined_accessories", "") or "").strip(),
        makeup_spec=str(getattr(fallback, "makeup_spec", "") or "").strip(),
        hair_style=str(getattr(fallback, "hair_style", "") or "").strip(),
        expression_mood=str(getattr(fallback, "expression_mood", "") or "").strip(),
        visual_prompt_zh=str(getattr(fallback, "visual_prompt_zh", "") or "").strip(),
        core_prompt_zh=str(getattr(fallback, "core_prompt_zh", "") or "").strip(),
        outfit_prompt_zh=str(getattr(fallback, "outfit_prompt_zh", "") or "").strip(),
        scene_prompt_zh=str(getattr(fallback, "scene_prompt_zh", "") or "").strip(),
        consistency_notes=str(getattr(fallback, "consistency_notes", "") or "").strip(),
        meta_info=json.dumps({
            "scope": "base_identity",
            "record_source": "materialized_character_profile",
            "profile_id": target_id,
            "fallback_origin": "character_profile",
            "gender": str(getattr(fallback, "gender", "") or "").strip(),
            "identity": str(getattr(fallback, "identity", "") or "").strip(),
            "age_range": str(getattr(fallback, "age_range", "") or "").strip(),
            "temperament": str(getattr(fallback, "temperament", "") or "").strip(),
            "appearance": str(getattr(fallback, "appearance", "") or "").strip(),
        }, ensure_ascii=False),
        shot_ids="[]",
        jimeng_ref_name="",
        negative_prompt="",
        asset_status="draft",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    s.add(row)
    s.flush()
    return row


def _load_makeup_rows_or_profile_fallback(s, book_id: int):
    from models import CharacterProfile, VisualMakeup

    makeup_rows = s.query(VisualMakeup).filter(
        VisualMakeup.book_id == book_id,
    ).order_by(VisualMakeup.episode, VisualMakeup.character_name, VisualMakeup.id).all()

    profiles = s.query(CharacterProfile).filter(
        CharacterProfile.book_id == book_id,
    ).order_by(CharacterProfile.name.asc(), CharacterProfile.id.asc()).all()
    materialized_ids = {
        int(getattr(row, "id", 0) or 0)
        for row in makeup_rows
        if int(getattr(row, "id", 0) or 0) > 0
    }
    materialized_names = {
        str(getattr(row, "character_name", "") or "").strip()
        for row in makeup_rows
        if str(getattr(row, "character_name", "") or "").strip()
    }
    fallback_rows = [
        _build_character_profile_fallback_makeup_row(profile)
        for profile in profiles
        if int(getattr(profile, "id", 0) or 0) not in materialized_ids
        and str(getattr(profile, "name", "") or "").strip() not in materialized_names
    ]
    return [*makeup_rows, *fallback_rows]


def _find_profile_fallback_makeup_by_id(s, book_id: int, asset_id: str | int | None):
    if not _is_integer_string(asset_id):
        return None
    target_id = int(str(asset_id).strip())
    for row in _load_makeup_rows_or_profile_fallback(s, book_id):
        if int(getattr(row, "id", 0) or 0) == target_id:
            return row
    return None


def _serialize_makeup_row(row, reference_assets: list[dict] | None = None, peer_rows: list | None = None) -> dict:
    summary = _derive_visual_asset_reference_summary(reference_assets or [])
    shot_ids = _json_loads_list(getattr(row, "shot_ids", None))
    scope = _makeup_scope_from_row(row, peer_rows)
    meta_info = safe_json_loads(getattr(row, "meta_info", "{}")) if getattr(row, "meta_info", None) else {}
    gender = str(getattr(row, "gender", "") or meta_info.get("gender") or "").strip()
    identity = str(getattr(row, "identity", "") or meta_info.get("identity") or "").strip()
    temperament = str(getattr(row, "temperament", "") or meta_info.get("temperament") or "").strip()
    appearance = str(getattr(row, "appearance", "") or meta_info.get("appearance") or "").strip()
    payload = {
        "id": row.id,
        "episode": row.episode,
        "character_name": row.character_name,
        "stage_name": getattr(row, "stage_name", "") or "",
        "makeup_scope": scope,
        "scope_label": _makeup_scope_label(scope),
        "gender": gender,
        "identity": identity,
        "temperament": temperament,
        "appearance": appearance,
        "refined_outfit": row.refined_outfit,
        "refined_accessories": row.refined_accessories,
        "makeup_spec": row.makeup_spec,
        "hair_style": row.hair_style,
        "expression_mood": row.expression_mood,
        "visual_prompt_zh": row.visual_prompt_zh,
        "core_prompt_zh": row.core_prompt_zh,
        "outfit_prompt_zh": row.outfit_prompt_zh,
        "scene_prompt_zh": row.scene_prompt_zh,
        "consistency_notes": row.consistency_notes,
        "meta_info": meta_info,
        "jimeng_ref_name": row.jimeng_ref_name,
        "negative_prompt": row.negative_prompt,
        "asset_status": row.asset_status or "draft",
        "record_source": str(getattr(row, "record_source", "") or meta_info.get("record_source") or "visual_makeup"),
        "is_readonly": bool(getattr(row, "is_readonly", False) or meta_info.get("readonly")),
        "reference_assets": reference_assets or [],
        "shot_ids": shot_ids,
        **summary,
    }
    return payload


def _resolve_makeup_for_character(s, book_id: int, episode: int, shot_id: str | int, scene_name: str | None, character_name: str, preferred_asset_id: str | None = None) -> dict | None:
    rows = [
        row
        for row in _load_makeup_rows_or_profile_fallback(s, book_id)
        if str(getattr(row, "character_name", "") or "").strip() == character_name
    ]
    rows = sorted(
        rows,
        key=lambda row: (
            str(getattr(row, "updated_at", "") or ""),
            int(getattr(row, "id", 0) or 0),
        ),
        reverse=True,
    )
    if not rows:
        return None

    normalized_scene = _normalize_makeup_scene_key(scene_name)
    target_shot = str(shot_id).strip()
    preferred_row = None
    if _is_integer_string(preferred_asset_id):
        preferred_id = int(str(preferred_asset_id).strip())
        preferred_row = next((row for row in rows if row.id == preferred_id), None)

    scoped_rows = [row for row in rows if int(getattr(row, "episode", 0) or 0) in {0, episode}]
    if not scoped_rows:
        scoped_rows = rows

    candidates: list[tuple[tuple[int, int, int, int], object, str]] = []
    for row in scoped_rows:
        row_shot_ids = _json_loads_list(getattr(row, "shot_ids", None))
        scope = _makeup_scope_from_row(row, scoped_rows)
        stage_name = getattr(row, "stage_name", "") or ""
        reason = ""
        priority = 0
        episode_bonus = 1 if int(getattr(row, "episode", 0) or 0) == episode else 0
        preferred_bonus = 1 if preferred_row and row.id == preferred_row.id else 0

        if _makeup_targets_shot(row_shot_ids, target_shot):
            priority = 50
            reason = "shot_ids"
        elif scope == "shot_variant" and re.search(rf"(^|[_-]){re.escape(target_shot)}($|[_-])", _normalize_makeup_stage_name(stage_name)):
            priority = 45
            reason = "stage_shot"
        elif normalized_scene and _makeup_targets_scene(stage_name, normalized_scene):
            priority = 40
            reason = "scene_stage"
        elif scope == "episode_default" and int(getattr(row, "episode", 0) or 0) == episode:
            priority = 30
            reason = "episode_default"
        elif scope == "base_identity":
            priority = 20
            reason = "base_identity"
        elif preferred_bonus:
            priority = 10
            reason = "preferred_asset"
        elif int(getattr(row, "episode", 0) or 0) == episode:
            priority = 5
            reason = "episode_fallback"
        else:
            priority = 1
            reason = "global_fallback"

        candidates.append(((priority, preferred_bonus, episode_bonus, int(getattr(row, "id", 0) or 0)), row, reason))

    candidates.sort(key=lambda item: item[0], reverse=True)
    resolved_row, resolution_reason = candidates[0][1], candidates[0][2]
    resolved_scope = _makeup_scope_from_row(resolved_row, scoped_rows)
    base_row = next(
        (
            row for row in scoped_rows
            if _makeup_scope_from_row(row, scoped_rows) == "base_identity"
        ),
        None,
    )
    if base_row is None:
        base_row = next(
            (
                row for row in scoped_rows
                if _makeup_scope_from_row(row, scoped_rows) == "episode_default"
            ),
            None,
        )
    if base_row is None:
        base_row = resolved_row

    return {
        "row": resolved_row,
        "scope": resolved_scope,
        "scope_label": _makeup_scope_label(resolved_scope),
        "resolution_reason": resolution_reason,
        "base_row": base_row,
        "peer_rows": scoped_rows,
    }


def _resolve_shot_makeup_payloads(s, book_id: int, shot, structure: dict, reference_index: dict[tuple[str, str], list[dict]] | None = None) -> list[dict]:
    reference_index = reference_index or {}
    preferred_ids = [str(item).strip() for item in (structure.get("character_asset_ids") or []) if str(item).strip()]
    resolved_payloads: list[dict] = []
    seen_names: set[str] = set()

    preferred_rows = []
    for asset_id in preferred_ids:
        if not _is_integer_string(asset_id):
            continue
        row = _find_profile_fallback_makeup_by_id(s, book_id, asset_id)
        if row:
            preferred_rows.append(row)

    for row in preferred_rows:
        character_name = str(row.character_name or "").strip()
        if not character_name or character_name in seen_names:
            continue
        resolved = _resolve_makeup_for_character(
            s,
            book_id,
            shot.episode,
            shot.shot_id,
            shot.scene_name,
            character_name,
            preferred_asset_id=str(row.id),
        )
        if not resolved or resolved.get("row") is None:
            continue
        resolved_row = resolved["row"]
        payload = _serialize_makeup_row(
            resolved_row,
            reference_index.get(("character", str(resolved_row.id)), []),
            resolved.get("peer_rows"),
        )
        payload["resolution_reason"] = resolved.get("resolution_reason", "")
        seen_names.add(character_name)
        resolved_payloads.append(payload)

    if resolved_payloads:
        return resolved_payloads

    fallback_rows = [
        row
        for row in _load_makeup_rows_or_profile_fallback(s, book_id)
        if int(getattr(row, "episode", 0) or 0) in {0, int(getattr(shot, "episode", 0) or 0)}
    ]
    by_name: dict[str, list[object]] = {}
    for row in fallback_rows:
        name = str(row.character_name or "").strip()
        if not name:
            continue
        by_name.setdefault(name, []).append(row)
    return [
        _serialize_makeup_row(rows_for_name[0], reference_index.get(("character", str(rows_for_name[0].id)), []), rows_for_name)
        for rows_for_name in by_name.values()
        if rows_for_name
    ]


def _normalize_structured_id_list(values: list | None) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _normalize_structure_item(item: dict | None) -> dict:
    if not isinstance(item, dict):
        return {}
    alias_map = {
        "characterId": "character_id",
        "visualAlias": "visual_alias",
        "screenPosition": "screen_position",
        "subjectType": "subject_type",
        "subjectId": "subject_id",
        "timeSlice": "time_slice",
    }
    normalized: dict = {}
    for key, value in item.items():
        normalized[alias_map.get(key, key)] = value
    return normalized


def _normalize_scene_asset_id(book_id: int, scene_name: str | None) -> str:
    from models import Session, VisualLocation

    def _scene_tokens(value: str | None) -> tuple[str, set[str]]:
        text = str(value or "").strip().lower()
        if not text:
            return "", set()
        for separator in ("·", "•", "/", "|", "-", "—", ":", "：", "（", "(", "[", "【", ",", "，"):
            if separator in text:
                text = text.split(separator, 1)[0].strip()
        compact = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)
        return compact, set(compact)

    raw_name = str(scene_name or "").strip()
    if not raw_name:
        return ""

    normalized_compact, normalized_chars = _scene_tokens(raw_name)
    if not normalized_compact:
        return ""

    with Session() as s:
        rows = s.query(VisualLocation).filter(VisualLocation.book_id == book_id).order_by(VisualLocation.id.asc()).all()
        best_fuzzy_match: tuple[float, str] | None = None
        for row in rows:
            name = str(getattr(row, "name", "") or "").strip()
            if not name:
                continue
            if name == raw_name:
                return str(row.id)
            row_compact, row_chars = _scene_tokens(name)
            if normalized_compact and row_compact and (
                normalized_compact == row_compact
                or normalized_compact in row_compact
                or row_compact in normalized_compact
            ):
                return str(row.id)
            if normalized_chars and row_chars:
                overlap = len(normalized_chars & row_chars) / max(len(normalized_chars | row_chars), 1)
                if overlap >= 0.4:
                    if best_fuzzy_match is None or overlap > best_fuzzy_match[0]:
                        best_fuzzy_match = (overlap, str(row.id))
        if best_fuzzy_match is not None:
            return best_fuzzy_match[1]
    return ""


def _extract_character_asset_ids(book_id: int, episode: int, structure_seed: dict, existing_ids: list[str]) -> list[str]:
    from models import Session

    if existing_ids:
        return existing_ids

    search_parts = [
        structure_seed.get("action_process"),
        structure_seed.get("dialogue"),
        structure_seed.get("start_state"),
        structure_seed.get("end_state"),
        structure_seed.get("scene_name"),
    ]
    search_text = " ".join(str(part or "") for part in search_parts)
    normalized_text = _normalize_asset_match_text(search_text)
    if not normalized_text:
        return []

    with Session() as s:
        rows = _load_makeup_rows_or_profile_fallback(s, book_id)
        episode_rows = [row for row in rows if int(getattr(row, "episode", 0) or 0) in {0, episode}]
        rows = episode_rows or rows

        matched_ids: list[str] = []
        seen_names: set[str] = set()
        for row in rows:
            name = str(getattr(row, "character_name", "") or "").strip()
            if not name or name in seen_names:
                continue
            normalized_name = _normalize_asset_match_text(name)
            if normalized_name and normalized_name in normalized_text:
                matched_ids.append(str(row.id))
                seen_names.add(name)
        return matched_ids


def _extract_prop_asset_ids(book_id: int, structure_seed: dict, existing_ids: list[str]) -> list[str]:
    from models import Session, VisualProp

    if existing_ids:
        return existing_ids

    search_parts = [
        structure_seed.get("action_process"),
        structure_seed.get("dialogue"),
        structure_seed.get("start_state"),
        structure_seed.get("end_state"),
        structure_seed.get("scene_name"),
    ]
    search_text = " ".join(str(part or "") for part in search_parts)
    normalized_text = _normalize_asset_match_text(search_text)
    if not normalized_text:
        return []

    with Session() as s:
        rows = s.query(VisualProp).filter(
            VisualProp.book_id == book_id,
        ).order_by(VisualProp.id.asc()).all()

        matched_ids: list[str] = []
        for row in rows:
            candidates = _build_prop_match_candidates(getattr(row, "name", ""))
            if any(candidate in normalized_text for candidate in candidates):
                matched_ids.append(str(row.id))
        return matched_ids


def _hydrate_character_blocking(book_id: int, episode: int, character_asset_ids: list[str], existing_rows: list[dict]) -> list[dict]:
    from models import Session, VisualMakeup

    if existing_rows:
        return existing_rows
    if not character_asset_ids:
        return []

    with Session() as s:
        rows: list[dict] = []
        for asset_id in character_asset_ids:
            if not _is_integer_string(asset_id):
                continue
            row = s.query(VisualMakeup).filter(
                VisualMakeup.book_id == book_id,
                VisualMakeup.id == int(asset_id),
            ).first()
            if not row:
                row = _find_profile_fallback_makeup_by_id(s, book_id, asset_id)
            if not row:
                continue
            rows.append({
                "character_id": str(row.id),
                "visual_alias": str(row.character_name or "").strip(),
                "screen_position": "",
                "pose": "",
                "emotion": "",
                "status": "derived",
                "episode": episode,
            })
        return rows


def _derive_action_beats(existing_rows: list[dict], structure_seed: dict) -> list[dict]:
    if existing_rows:
        return existing_rows
    description = str(structure_seed.get("action_process") or "").strip()
    if not description:
        return []
    return [{
        "sequence": 1,
        "subject_type": "scene",
        "subject_id": "",
        "time_slice": "",
        "description": description,
        "emotion": "",
        "intensity": "medium",
    }]


def _get_camera_library_snapshot() -> dict:
    """返回标准化的摄影词典快照（用于 prompt 编译）"""
    from core.camera_library import CAMERA_LIBRARY, SHOT_SIZE_LIBRARY, CAMERA_ANGLE_LIBRARY, TRANSITION_LIBRARY, LIGHTING_LIBRARY
    from core.style_library import DIRECTOR_STYLE_LIBRARY, VISUAL_STYLE_LIBRARY, COLOR_PALETTE_LIBRARY, COMPOSITION_LIBRARY, ASPECT_RATIO_LIBRARY
    from core.screenwriting_library import CHARACTER_ARCHETYPE_LIBRARY, STORY_STRUCTURE_LIBRARY, CONFLICT_TYPE_LIBRARY, DIALOGUE_STYLE_LIBRARY, SCENE_STRUCTURE_LIBRARY, NARRATIVE_DEVICE_LIBRARY, PACING_TEMPLATE_LIBRARY
    return {
        "camera_motions": {k: {"zh": v["zh"], "en": v["en"], "category": v.get("category", ""), "speed_variants": v.get("speed_variants", {})} for k, v in CAMERA_LIBRARY.items()},
        "shot_sizes": {k: {"zh": v["zh"], "en": v["en"], "usage": v["usage"]} for k, v in SHOT_SIZE_LIBRARY.items()},
        "camera_angles": {k: {"zh": v["zh"], "en": v["en"], "usage": v["usage"]} for k, v in CAMERA_ANGLE_LIBRARY.items()},
        "transitions": {k: {"zh": v["zh"], "en": v["en"], "usage": v["usage"]} for k, v in TRANSITION_LIBRARY.items()},
        "lighting": {k: {"zh": v["zh"], "en": v["en"], "usage": v["usage"]} for k, v in LIGHTING_LIBRARY.items()},
        "director_styles": {k: {"name": v["name"], "signature": v["signature"], "camera": v["camera"], "lighting": v["lighting"], "color": v["color"], "composition": v["composition"]} for k, v in DIRECTOR_STYLE_LIBRARY.items()},
        "visual_styles": {k: {"name": v["name"], "signature": v["signature"], "lighting": v["lighting"], "color": v["color"], "composition": v["composition"]} for k, v in VISUAL_STYLE_LIBRARY.items()},
        "color_palettes": {k: {"name": v["name"], "colors": v["colors"], "emotion": v["emotion"]} for k, v in COLOR_PALETTE_LIBRARY.items()},
        "compositions": {k: {"name": v["name"], "description": v["description"], "usage": v["usage"]} for k, v in COMPOSITION_LIBRARY.items()},
        "aspect_ratios": {k: {"name": v["name"], "usage": v["usage"], "emotion": v["emotion"]} for k, v in ASPECT_RATIO_LIBRARY.items()},
        "character_archetypes": {k: {"name": v["name"], "dramatic_function": v["dramatic_function"], "variations": v["variations"]} for k, v in CHARACTER_ARCHETYPE_LIBRARY.items()},
        "story_structures": {k: {"name": v["name"], "stages": [s["name"] for s in v["stages"]], "usage": v["usage"]} for k, v in STORY_STRUCTURE_LIBRARY.items()},
        "conflict_types": {k: {"name": v["name"], "subtypes": v["subtypes"], "usage": v["usage"]} for k, v in CONFLICT_TYPE_LIBRARY.items()},
        "dialogue_styles": {k: {"name": v["name"], "techniques": v["techniques"], "emotion_effect": v["emotion_effect"]} for k, v in DIALOGUE_STYLE_LIBRARY.items()},
        "scene_structures": {k: {"name": v["name"], "function": v["function"], "pacing": v["pacing"]} for k, v in SCENE_STRUCTURE_LIBRARY.items()},
        "narrative_devices": {k: {"name": v["name"], "description": v["description"], "emotion_effect": v["emotion_effect"]} for k, v in NARRATIVE_DEVICE_LIBRARY.items()},
        "pacing_templates": {k: {"name": v["name"], "description": v["description"], "emotion_effect": v["emotion_effect"]} for k, v in PACING_TEMPLATE_LIBRARY.items()},
    }


def _get_emotion_library_snapshot() -> dict:
    """返回情绪词典快照（用于 prompt 编译）"""
    from core.emotion_library import EMOTION_MOTION_LIBRARY
    return {
        emotion: {
            "low": data.get("low", ""),
            "medium": data.get("medium", ""),
            "high": data.get("high", ""),
            "facs_au": data.get("facs_au", ""),
            "body": data.get("body", ""),
            "camera_suggestion": data.get("camera_suggestion", ""),
        }
        for emotion, data in EMOTION_MOTION_LIBRARY.items()
    }


def _get_shot_size_library_snapshot() -> dict:
    """返回景别词典快照（用于 prompt 编译）"""
    from core.camera_library import SHOT_SIZE_LIBRARY
    return {k: {"zh": v["zh"], "en": v["en"], "usage": v["usage"]} for k, v in SHOT_SIZE_LIBRARY.items()}


def _get_short_drama_library_snapshot() -> dict:
    """返回短剧专属基础库快照（用于 prompt 编译）"""
    from core.short_drama_library import (
        EPISODE_BEAT_ENGINE,
        EPISODE_EMOTION_NODES,
        HOOK_LIBRARY,
        SHORT_DRAMA_CONFLICT_PATTERNS,
        SHORT_DRAMA_DIALOGUE_RULES,
        SHORT_DRAMA_VISUAL_GRAMMAR,
        SHORT_DRAMA_PACING_TEMPLATES,
        SERIES_ARCHITECTURE_LIBRARY,
        COMMON_PITFALLS,
        EMOTION_CHECKPOINT_LIBRARY,
    )
    return {
        "beat_engine": EPISODE_BEAT_ENGINE,
        "emotion_nodes": EPISODE_EMOTION_NODES,
        "hook_library": HOOK_LIBRARY,
        "conflict_patterns": SHORT_DRAMA_CONFLICT_PATTERNS,
        "dialogue_rules": SHORT_DRAMA_DIALOGUE_RULES,
        "visual_grammar": SHORT_DRAMA_VISUAL_GRAMMAR,
        "pacing_templates": SHORT_DRAMA_PACING_TEMPLATES,
        "series_architecture": SERIES_ARCHITECTURE_LIBRARY,
        "common_pitfalls": COMMON_PITFALLS,
        "emotion_checkpoints": EMOTION_CHECKPOINT_LIBRARY,
    }


def _infer_emotion_from_text(text: str) -> str:
    """从文本中推导情绪词"""
    if not text:
        return ""
    for emotion in ["绝望", "恐惧", "害怕", "暴怒", "愤怒", "悲伤", "焦虑", "紧张", "心虚", "厌恶", "轻蔑", "惊喜", "坚定", "犹豫", "温暖", "平静"]:
        if emotion in text:
            return emotion
    return ""


def _infer_emotion_intensity(start_emotion: str, end_emotion: str, shot) -> str:
    """推导情绪强度"""
    text = f"{shot.start_state or ''} {shot.end_state or ''} {shot.action_process or ''}"
    high_indicators = ["崩溃", "大吼", "尖叫", "颤抖", "泪流", "猛扑", "暴怒", "绝望", "疯狂"]
    low_indicators = ["微微", "轻轻", "略", "稍", "自然", "平静"]
    for indicator in high_indicators:
        if indicator in text:
            return "high"
    for indicator in low_indicators:
        if indicator in text:
            return "low"
    return "medium"


def _derive_structured_shot_payload(meta_info: dict | None, fallback: dict | None = None) -> dict:
    fallback = fallback if isinstance(fallback, dict) else {}
    structured = meta_info.get("structured_shot", {}) if isinstance(meta_info, dict) else {}
    if not isinstance(structured, dict):
        structured = {}

    return {
        "shot_id": str(structured.get("shot_id") or fallback.get("shot_id") or "").strip(),
        "scene_name": str(structured.get("scene_name") or fallback.get("scene_name") or "").strip(),
        "duration": int(structured.get("duration") or fallback.get("duration") or 3),
        "camera_angle": str(structured.get("camera_angle") or fallback.get("camera_angle") or "MS").strip() or "MS",
        "camera_movement": str(structured.get("camera_movement") or fallback.get("camera_movement") or "static").strip() or "static",
        "transition": str(structured.get("transition") or fallback.get("transition") or "cut").strip() or "cut",
        "scene_asset_id": str(structured.get("scene_asset_id") or fallback.get("scene_asset_id") or "").strip(),
        "character_asset_ids": _normalize_structured_id_list(structured.get("character_asset_ids") or fallback.get("character_asset_ids")),
        "prop_asset_ids": _normalize_structured_id_list(structured.get("prop_asset_ids") or fallback.get("prop_asset_ids")),
        "style_key": str(structured.get("style_key") or fallback.get("style_key") or "default").strip() or "default",
        "character_blocking": [
            _normalize_structure_item(item)
            for item in _normalize_structure_list(structured.get("character_blocking") or fallback.get("character_blocking"))
        ],
        "action_beats": [
            _normalize_structure_item(item)
            for item in _normalize_structure_list(structured.get("action_beats") or fallback.get("action_beats"))
        ],
        "action_process": str(structured.get("action_process") or fallback.get("action_process") or "").strip(),
        "dialogue": str(structured.get("dialogue") or fallback.get("dialogue") or "").strip(),
        "start_state": str(structured.get("start_state") or fallback.get("start_state") or "").strip(),
        "end_state": str(structured.get("end_state") or fallback.get("end_state") or "").strip(),
        "makeup_prompts": fallback.get("makeup_prompts") if isinstance(fallback.get("makeup_prompts"), list) else [],
        "retention": structured.get("retention") if isinstance(structured.get("retention"), dict) else {
            "face": "fully_preserved",
            "hair": "fully_preserved",
            "costume": "fully_preserved",
            "background": "mostly_preserved",
            "composition": "free",
        },
        "emotion_arc": structured.get("emotion_arc") if isinstance(structured.get("emotion_arc"), dict) else {},
        "shot_purpose": str(structured.get("shot_purpose") or "").strip(),
        "camera_speed": str(structured.get("camera_speed") or "slow").strip() or "slow",
    }


def _auto_bind_structured_shot_assets(book_id: int, episode: int, structure: dict, structure_seed: dict | None = None) -> dict:
    structure_seed = structure_seed if isinstance(structure_seed, dict) else {}
    payload = _derive_structured_shot_payload({"structured_shot": structure}, structure_seed)

    if not payload["scene_asset_id"]:
        payload["scene_asset_id"] = _normalize_scene_asset_id(book_id, payload.get("scene_name") or structure_seed.get("scene_name"))

    payload["character_asset_ids"] = _extract_character_asset_ids(book_id, episode, payload, payload["character_asset_ids"])
    payload["prop_asset_ids"] = _extract_prop_asset_ids(book_id, payload, payload["prop_asset_ids"])
    payload["character_blocking"] = _hydrate_character_blocking(book_id, episode, payload["character_asset_ids"], payload["character_blocking"])
    payload["action_beats"] = _derive_action_beats(payload["action_beats"], payload)

    return {
        "shot_id": payload["shot_id"],
        "scene_name": payload["scene_name"],
        "duration": payload["duration"],
        "camera_angle": payload["camera_angle"],
        "camera_movement": payload["camera_movement"],
        "transition": payload["transition"],
        "scene_asset_id": payload["scene_asset_id"],
        "character_asset_ids": payload["character_asset_ids"],
        "prop_asset_ids": payload["prop_asset_ids"],
        "style_key": payload["style_key"],
        "character_blocking": payload["character_blocking"],
        "action_beats": payload["action_beats"],
    }


def _merge_structured_shot_payload(current_meta: dict | None, req: StoryboardStructurePatchRequest) -> dict:
    current_meta = current_meta if isinstance(current_meta, dict) else {}
    base = _derive_structured_shot_payload(current_meta, {})

    if req.duration is not None:
        base["duration"] = int(req.duration)
    if req.camera_angle is not None:
        base["camera_angle"] = req.camera_angle
    if req.camera_movement is not None:
        base["camera_movement"] = req.camera_movement
    if req.transition is not None:
        base["transition"] = req.transition
    if req.scene_asset_id is not None:
        base["scene_asset_id"] = str(req.scene_asset_id).strip()
    if req.character_asset_ids is not None:
        base["character_asset_ids"] = _normalize_structured_id_list(req.character_asset_ids)
    if req.prop_asset_ids is not None:
        base["prop_asset_ids"] = _normalize_structured_id_list(req.prop_asset_ids)
    if req.style_key is not None:
        base["style_key"] = str(req.style_key).strip() or "default"
    if req.character_blocking is not None:
        base["character_blocking"] = [_normalize_structure_item(item) for item in _normalize_structure_list(req.character_blocking)]
    if req.action_beats is not None:
        base["action_beats"] = [_normalize_structure_item(item) for item in _normalize_structure_list(req.action_beats)]

    next_meta = dict(current_meta)
    next_meta["structured_shot"] = {
        "shot_id": base.get("shot_id", ""),
        "scene_name": base.get("scene_name", ""),
        "duration": base["duration"],
        "camera_angle": base["camera_angle"],
        "camera_movement": base["camera_movement"],
        "transition": base["transition"],
        "scene_asset_id": base["scene_asset_id"],
        "character_asset_ids": base["character_asset_ids"],
        "prop_asset_ids": base["prop_asset_ids"],
        "style_key": base["style_key"],
        "character_blocking": base["character_blocking"],
        "action_beats": base["action_beats"],
    }
    return next_meta


def _load_episode_makeup_prompt_stub(book_id: int, episode: int) -> list[dict]:
    from models import Session

    with Session() as s:
        rows = _load_makeup_rows_or_profile_fallback(s, book_id)
        filtered_rows = [row for row in rows if int(getattr(row, "episode", 0) or 0) in {0, episode}]
        rows = filtered_rows or rows
        return [
            {
                "id": row.id,
                "character_name": row.character_name,
                "stage_name": getattr(row, "stage_name", "") or "",
                "makeup_scope": _makeup_scope_from_row(row, rows),
                "scope_label": _makeup_scope_label(_makeup_scope_from_row(row, rows)),
                "visual_prompt_zh": getattr(row, "visual_prompt_zh", "") or "",
                "scene_prompt_zh": getattr(row, "scene_prompt_zh", "") or "",
                "refined_outfit": getattr(row, "refined_outfit", "") or "",
                "hair_style": getattr(row, "hair_style", "") or "",
                "makeup_spec": getattr(row, "makeup_spec", "") or "",
            }
            for row in rows
        ]


def _persist_auto_bound_storyboard_structures(book_id: int, episodes: list[int] | None = None) -> dict:
    from models import Session, StoryboardShot

    target_episodes = {int(item) for item in (episodes or []) if str(item).strip()}
    inspected_shots = 0
    changed_shots = 0

    with Session() as s:
        query = s.query(StoryboardShot).filter(StoryboardShot.book_id == book_id)
        if target_episodes:
            query = query.filter(StoryboardShot.episode.in_(sorted(target_episodes)))
        rows = query.order_by(StoryboardShot.episode.asc(), StoryboardShot.shot_id.asc()).all()

        for shot in rows:
            inspected_shots += 1
            current_meta = safe_json_loads(shot.meta_info) if shot.meta_info else {}
            if not isinstance(current_meta, dict):
                current_meta = {}
            seed = {
                "shot_id": shot.shot_id,
                "scene_name": shot.scene_name,
                "action_process": shot.action_process,
                "dialogue": shot.dialogue,
                "start_state": shot.start_state,
                "end_state": shot.end_state,
                "duration": shot.duration,
                "camera_angle": shot.camera_angle,
                "camera_movement": shot.camera_movement,
                "transition": shot.transition,
                "makeup_prompts": _load_episode_makeup_prompt_stub(book_id, shot.episode),
            }
            previous = _derive_structured_shot_payload(current_meta, seed)
            bound = _auto_bind_structured_shot_assets(
                book_id,
                shot.episode,
                previous,
                seed,
            )
            if current_meta.get("structured_shot") != bound:
                current_meta["structured_shot"] = bound
                shot.meta_info = json.dumps(current_meta, ensure_ascii=False)
                shot.updated_at = datetime.utcnow()
                changed_shots += 1

        if changed_shots:
            s.commit()

    return {
        "book_id": book_id,
        "episodes": sorted(target_episodes) if target_episodes else [],
        "inspected_shots": inspected_shots,
        "changed_shots": changed_shots,
    }


def _serialize_reference_asset_row(row) -> dict:
    return {
        "id": row.id,
        "book_id": row.book_id,
        "episode": row.episode,
        "asset_type": row.asset_type,
        "asset_id": row.asset_id,
        "asset_name": row.asset_name,
        "image_url": row.image_url,
        "local_path": row.local_path,
        "reference_token": row.reference_token,
        "status": row.status,
        "prompt": row.prompt,
        "model": row.model,
        "notes": row.notes,
        "meta_info": json.loads(row.meta_info) if row.meta_info else {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _derive_visual_asset_reference_summary(reference_assets: list[dict] | None) -> dict:
    items = reference_assets or []
    selected_items = [item for item in items if str(item.get("status") or "") == "selected"]
    locked_items = [item for item in items if str(item.get("status") or "") == "locked"]
    rejected_items = [item for item in items if str(item.get("status") or "") == "rejected"]
    candidate_items = [item for item in items if str(item.get("status") or "") == "candidate"]
    primary_reference = locked_items[-1] if locked_items else selected_items[-1] if selected_items else None
    latest_item = None
    if items:
        latest_item = max(items, key=lambda item: str(item.get("created_at") or ""))

    if locked_items:
        derived_status = "locked"
    elif selected_items:
        derived_status = "ref_ready"
    elif items and len(rejected_items) == len(items):
        derived_status = "rejected"
    else:
        derived_status = "draft"

    return {
        "derived_asset_status": derived_status,
        "primary_reference_id": primary_reference.get("id") if isinstance(primary_reference, dict) else None,
        "primary_reference_token": primary_reference.get("reference_token") if isinstance(primary_reference, dict) else "",
        "locked_reference_id": locked_items[-1].get("id") if locked_items else None,
        "locked_reference_token": locked_items[-1].get("reference_token", "") if locked_items else "",
        "selected_reference_count": len(selected_items),
        "locked_reference_count": len(locked_items),
        "candidate_reference_count": len(candidate_items),
        "rejected_reference_count": len(rejected_items),
        "reference_count": len(items),
        "latest_generated_at": latest_item.get("created_at") if isinstance(latest_item, dict) else None,
    }


def _serialize_visual_asset_row(row, asset_type: str, *, episode: int | None = None, reference_assets: list[dict] | None = None, peer_rows: list | None = None) -> dict:
    if asset_type == "character":
        payload = {
            "asset_type": "character",
            "asset_id": str(row.id),
            "name": getattr(row, "character_name", ""),
            **_serialize_makeup_row(row, reference_assets, peer_rows),
        }
        return payload

    summary = _derive_visual_asset_reference_summary(reference_assets or [])
    payload = {
        "id": row.id,
        "asset_type": asset_type,
        "asset_id": str(row.id),
        "name": getattr(row, "name", None) or getattr(row, "character_name", ""),
        "jimeng_ref_name": getattr(row, "jimeng_ref_name", "") or "",
        "negative_prompt": getattr(row, "negative_prompt", "") or "",
        "asset_status": getattr(row, "asset_status", "") or "draft",
        "references": reference_assets or [],
        "shot_ids": _json_loads_list(getattr(row, "shot_ids", None)),
        **summary,
    }
    if asset_type == "scene":
        payload.update(_build_scene_variant_metadata(row, peer_rows))
    elif asset_type == "prop":
        payload.update(_build_prop_variant_metadata(row, peer_rows))
    if episode is not None:
        payload["episode"] = episode
    return payload


def _normalize_visual_variant_group_key(value: str | None) -> str:
    return str(value or "").strip().casefold()


def _has_formal_visual_variants(row, peer_rows: list | None = None) -> bool:
    if not isinstance(peer_rows, list) or len(peer_rows) <= 1:
        return False

    current_name = _normalize_visual_variant_group_key(getattr(row, "name", ""))
    if not current_name:
        return False

    sibling_count = sum(
        1
        for peer in peer_rows
        if _normalize_visual_variant_group_key(getattr(peer, "name", "")) == current_name
    )
    return sibling_count > 1


def _build_scene_variant_metadata(row, peer_rows: list | None = None) -> dict:
    if not _has_formal_visual_variants(row, peer_rows):
        return {
            "variant_scope": "",
            "scope_label": "",
            "stage_name": "",
        }

    stage_name = (
        str(getattr(row, "lighting_mood", "") or "").strip()
        or str(getattr(row, "color_palette", "") or "").strip()
        or str(getattr(row, "style", "") or "").strip()
        or str(getattr(row, "name", "") or "").strip()
    )
    return {
        "variant_scope": "scene_variant",
        "scope_label": "场景变体",
        "stage_name": stage_name,
    }


def _build_prop_variant_metadata(row, peer_rows: list | None = None) -> dict:
    if not _has_formal_visual_variants(row, peer_rows):
        return {
            "variant_scope": "",
            "scope_label": "",
            "stage_name": "",
        }

    stage_name = (
        str(getattr(row, "associated_characters", "") or "").strip()
        or str(getattr(row, "time_period", "") or "").strip()
        or str(getattr(row, "importance", "") or "").strip()
        or str(getattr(row, "name", "") or "").strip()
    )
    return {
        "variant_scope": "prop_variant",
        "scope_label": "道具变体",
        "stage_name": stage_name,
    }


def _normalize_structure_list(values: list | None) -> list:
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, dict)]


def _normalize_scene_lookup_text(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for separator in ("?", "/", "|", "-", "?", "(", "?", ":", "?"):
        if separator in text:
            text = text.split(separator, 1)[0].strip()
    return text.replace("??", "").replace("??", "").strip()


def _normalize_asset_match_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    for marker in (
        "\r",
        "\n",
        "\t",
        "(",
        ")",
        "[",
        "]",
        ",",
        ".",
        ":",
        ";",
        "?",
        "!",
        '"',
        "'",
        "?",
        "-",
        "/",
        "\\",
        "?",
        "?",
        "?",
        "?",
        "?",
        "?",
        "?",
        "?",
        "?",
        "?",
        "?",
        "?",
        "?",
    ):
        text = text.replace(marker, " ")
    return " ".join(text.split())


def _build_prop_match_candidates(name: str | None) -> list[str]:
    raw_name = str(name or "").strip()
    if not raw_name:
        return []

    candidates: list[str] = []

    def add(value: str | None) -> None:
        normalized = _normalize_asset_match_text(value)
        if not normalized:
            return
        compact = normalized.replace(" ", "")
        if compact and (len(compact) >= 2 or any(ch.isascii() and ch.isalpha() for ch in compact)):
            candidates.append(normalized)

    add(raw_name)
    if "?" in raw_name:
        add(raw_name.split("?", 1)[0].strip())
    if "(" in raw_name:
        add(raw_name.split("(", 1)[0].strip())

    alias_map = {
        "????": ["??", "??", "???", "???", "???"],
        "???": ["??", "???", "??"],
        "????": ["??"],
        "??????????": ["????", "??", "??", "????"],
        "????": ["??", "??"],
        "?????": ["???", "??", "??"],
        "????": ["??"],
        "????": ["??"],
        "????": ["??"],
        "????": ["??"],
        "??": ["??"],
        "??": ["??", "??"],
        "???": ["??", "??"],
        "??": ["?", "??"],
    }
    for alias in alias_map.get(raw_name, []):
        add(alias)

    return list(dict.fromkeys(candidates))


def _build_scene_match_candidates(name: str | None) -> list[str]:
    raw_name = str(name or "").strip()
    if not raw_name:
        return []

    candidates: list[str] = []

    def add(value: str | None) -> None:
        normalized = _normalize_asset_match_text(value)
        if normalized:
            candidates.append(normalized)

    add(raw_name)
    alias_map = {
        "????": ["?????", "???", "??", "??"],
        "?????": ["????", "??", "???", "??"],
        "??": ["????"],
        "????": ["??"],
        "??????": ["??", "????"],
        "??": ["??????"],
    }
    for alias in alias_map.get(raw_name, []):
        add(alias)

    return list(dict.fromkeys(candidates))


def _collect_visual_negative_prompts(book_id: int, structure: dict) -> list[str]:
    from models import Session, VisualLocation, VisualMakeup, VisualProp

    prompts: list[str] = []
    with Session() as s:
        scene_asset_id = str(structure.get("scene_asset_id") or "")
        if scene_asset_id:
            row = s.query(VisualLocation).filter(VisualLocation.book_id == book_id, VisualLocation.id == int(scene_asset_id)).first()
            if row and row.negative_prompt:
                prompts.append(row.negative_prompt.strip())
        for asset_id in structure.get("character_asset_ids", []) or []:
            if not _is_integer_string(asset_id):
                continue
            row = s.query(VisualMakeup).filter(VisualMakeup.book_id == book_id, VisualMakeup.id == int(asset_id)).first()
            if not row:
                row = _find_profile_fallback_makeup_by_id(s, book_id, asset_id)
            if row and row.negative_prompt:
                prompts.append(row.negative_prompt.strip())
        for asset_id in structure.get("prop_asset_ids", []) or []:
            row = s.query(VisualProp).filter(VisualProp.book_id == book_id, VisualProp.id == int(asset_id)).first()
            if row and row.negative_prompt:
                prompts.append(row.negative_prompt.strip())
    return [item for item in prompts if item]


FAILURE_TAG_CONSTRAINTS = {
    "character_count_error": "preserve the exact number of characters already specified, do not add or remove people",
    "character_blocking_error": "keep every character fixed in the intended screen position and spatial relationship",
    "character_inconsistency": "keep the same face, body type, age, and identity for every recurring character",
    "costume_error": "preserve wardrobe, accessories, and styling continuity exactly",
    "prop_missing": "ensure all key props are fully visible and present in frame",
    "scene_error": "keep the intended scene layout, architecture, and environment unchanged",
    "mood_error": "match the required emotional atmosphere and lighting mood precisely",
    "composition_error": "maintain a clean, intentional composition with clear subject focus",
    "hand_error": "render hands naturally with correct anatomy and finger count",
    "new_character_added": "do not introduce any extra person, face, or background figure",
    "subtitle_watermark_logo": "exclude subtitles, captions, watermarks, logos, and any embedded text",
    "needs_retry": "strictly follow the latest structured shot constraints and avoid repeating prior mistakes",
}


def _collect_acceptance_constraints(book_id: int, episode: int, shot_id: int) -> dict:
    from models import Session, StoryboardAcceptanceRecord

    with Session() as s:
        rows = s.query(StoryboardAcceptanceRecord).filter(
            StoryboardAcceptanceRecord.book_id == book_id,
            StoryboardAcceptanceRecord.episode == episode,
            StoryboardAcceptanceRecord.shot_id == shot_id,
            StoryboardAcceptanceRecord.status.in_(["failed", "retrying"]),
        ).order_by(StoryboardAcceptanceRecord.created_at.desc(), StoryboardAcceptanceRecord.id.desc()).all()

    constraints: list[str] = []
    tags: list[str] = []
    notes: list[str] = []
    for row in rows[:5]:
        row_tags = _json_loads_list(row.failure_tags)
        for tag in row_tags:
            if not isinstance(tag, str):
                continue
            normalized = tag.strip()
            if not normalized:
                continue
            tags.append(normalized)
            constraint = FAILURE_TAG_CONSTRAINTS.get(normalized)
            if constraint:
                constraints.append(constraint)
        if row.notes and row.notes.strip():
            notes.append(row.notes.strip())

    return {
        "failure_tags": list(dict.fromkeys(tags)),
        "constraints": list(dict.fromkeys(constraints)),
        "notes": list(dict.fromkeys(notes)),
    }


def _localize_storyboard_term(value: str | None, mapping: dict[str, str]) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if normalized in mapping:
        return mapping[normalized]
    lowered = normalized.lower()
    for key, mapped in mapping.items():
        if str(key).lower() == lowered:
            return mapped
    return normalized


def _collect_asset_reference_diagnostics(book_id: int, asset_type: str, asset_id: str, episode: int | None = None) -> dict:
    from models import Session, VisualReferenceAsset

    if not str(asset_id or "").strip():
        return {
            "has_reference": False,
            "locked": False,
            "selected": False,
            "total": 0,
            "statuses": [],
        }

    with Session() as s:
        query = s.query(VisualReferenceAsset).filter(
            VisualReferenceAsset.book_id == book_id,
            VisualReferenceAsset.asset_type == asset_type,
            VisualReferenceAsset.asset_id == str(asset_id),
        )
        if episode is not None:
            query = query.filter((VisualReferenceAsset.episode == episode) | (VisualReferenceAsset.episode.is_(None)))
        rows = query.order_by(VisualReferenceAsset.id.desc()).all()

    statuses = [str(row.status or "").strip() for row in rows if str(row.status or "").strip()]
    return {
        "has_reference": len(rows) > 0,
        "locked": any(status == "locked" for status in statuses),
        "selected": any(status in {"selected", "locked"} for status in statuses),
        "total": len(rows),
        "statuses": list(dict.fromkeys(statuses)),
    }


def _looks_like_garbled_text(value: str | None) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    compact = "".join(text.split())
    if not compact:
        return False
    if "锟" in compact:
        return True
    if compact.count("?") >= 3 and compact.count("?") / max(len(compact), 1) >= 0.15:
        return True
    return False


def _contains_cjk(value: str | None) -> bool:
    text = str(value or "")
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    normalized = str(text or "")
    return sum(1 for token in keywords if token and token in normalized)


def _extract_authority_keywords(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(text or "").strip())
    if not normalized:
        return []
    fragments = re.split(r"[\u3001\u3002\uff0c\uff1b\uff1a\uff01\uff1f\u201c\u201d\u2018\u2019\uff08\uff09\(\)\[\]\{\}\|/\n\r\t]+", normalized)
    keywords: list[str] = []
    generic_tokens = {
        "人物",
        "角色",
        "场景",
        "道具",
        "状态",
        "镜头",
        "当前",
        "保持",
        "一致",
        "统一",
        "六个视角",
        "同一个人",
        "基础定妆",
        "当前分镜状态",
        "角色设定板",
        "人物分镜精调定妆设定板",
    }
    for fragment in fragments:
        candidate = fragment.strip()
        if len(candidate) < 2 or len(candidate) > 18:
            cjk_chunks = re.findall(r"[\u4e00-\u9fff]{2,12}", candidate)
            for chunk in cjk_chunks:
                if chunk in generic_tokens:
                    continue
                if chunk not in keywords:
                    keywords.append(chunk)
            continue
        if candidate in generic_tokens:
            continue
        if candidate not in keywords:
            keywords.append(candidate)
    return keywords[:10]


def _normalize_authority_match_text(text: str) -> str:
    normalized = re.sub(r"\s+", "", str(text or "").strip())
    normalized = re.sub(r"[，。；：、“”‘’\.\,\;\:\!\?（）()\[\]{}·]", "", normalized)
    return normalized


def _build_authority_match_variants(keyword: str) -> list[str]:
    text = str(keyword or "").strip()
    if not text:
        return []
    variants: list[str] = []
    normalized = _normalize_authority_match_text(text)
    if normalized:
        variants.append(normalized)
    stripped_parenthetical = re.sub(r"[\u4e00-\u9fffA-Za-z0-9_-]*[\uff08\(][^\uff09\)]*[\uff09\)]", lambda m: m.group(0).split("（")[0].split("(")[0], text)
    stripped_parenthetical = _normalize_authority_match_text(stripped_parenthetical)
    if stripped_parenthetical:
        variants.append(stripped_parenthetical)
    collapsed = normalized
    for token in ["的", "地", "得", "为", "由", "与", "及", "并", "或", "和", "内", "中"]:
        collapsed = collapsed.replace(token, "")
    if collapsed:
        variants.append(collapsed)
    simplified = normalized
    for token in ["仍", "还", "正", "已", "略", "微", "棉麻", "粗布", "旧"]:
        simplified = simplified.replace(token, "")
    if simplified:
        variants.append(simplified)
    if "寺庙僧侣" in normalized:
        variants.append(normalized.replace("寺庙僧侣", "和尚"))
    if "木质或竹编水桶" in normalized:
        variants.extend(["木质水桶", "竹编水桶", "水桶"])
    if "外壁多道竹箍或铁" in normalized:
        variants.extend(["竹箍", "铁箍", "多道竹箍", "多道铁箍"])
    if "桶口略呈圆形" in normalized:
        variants.extend(["桶口圆形", "圆形桶口"])
    if "中央一口老井" in normalized:
        variants.extend(["老井", "一口老井", "中央老井"])
    if "井口由青石砌成" in normalized:
        variants.extend(["青石砌成", "井口青石砌成", "青石井口"])
    if "四周为灰白色墙壁" in normalized:
        variants.extend(["灰白色墙壁", "四周灰白色墙壁"])
    if normalized.startswith("略显") and len(normalized) > 2:
        variants.append(normalized[2:])
    if normalized.endswith("气") and len(normalized) > 1:
        variants.append(normalized[:-1])
    if normalized.startswith("的") and len(normalized) > 1:
        variants.append(normalized[1:])
    return list(dict.fromkeys([item for item in variants if item]))


def _build_authority_overlap_terms(keyword: str) -> list[str]:
    normalized = _normalize_authority_match_text(keyword)
    if not normalized:
        return []
    if re.search(r"[\u4e00-\u9fff]", normalized):
        simplified = normalized
        for token in ["可见", "可以", "看出", "仍在", "仍露", "仍", "还", "正", "已", "被", "把", "将", "从", "到", "与", "和", "及", "并", "的", "地", "得"]:
            simplified = simplified.replace(token, " ")
        terms: list[str] = []
        for chunk in re.findall(r"[\u4e00-\u9fff]{2,12}", simplified):
            if 2 <= len(chunk) <= 3:
                terms.append(chunk)
                continue
            terms.append(chunk)
            for size in (2, 3, 4):
                for index in range(len(chunk) - size + 1):
                    terms.append(chunk[index:index + size])
        return list(dict.fromkeys([term for term in terms if len(term) >= 2]))[:24]
    ascii_terms = re.findall(r"[A-Za-z0-9_-]{3,}", normalized)
    return list(dict.fromkeys(ascii_terms))[:12]


def _authority_keyword_present(keyword: str, prompt_text: str) -> bool:
    normalized_prompt = _normalize_authority_match_text(prompt_text)
    if not normalized_prompt:
        return False
    variants = _build_authority_match_variants(keyword)
    for variant in variants:
        if variant and len(variant) >= 2 and variant in normalized_prompt:
            return True
    chunks = [
        chunk
        for chunk in _extract_authority_keywords(keyword)
        if chunk and len(_normalize_authority_match_text(chunk)) >= 2
    ]
    chunk_hits = 0
    for chunk in list(dict.fromkeys(chunks)):
        normalized_chunk = _normalize_authority_match_text(chunk)
        if normalized_chunk and normalized_chunk in normalized_prompt:
            chunk_hits += 1
    if chunk_hits >= (2 if len(chunks) >= 2 else 1):
        return True
    overlap_terms = _build_authority_overlap_terms(keyword)
    overlap_hits = sum(1 for term in overlap_terms if term and term in normalized_prompt)
    if overlap_terms and overlap_hits >= (3 if len(overlap_terms) >= 6 else 2):
        return True
    return False


def _normalize_reference_status(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"locked", "selected", "candidate", "rejected", "missing"}:
        return normalized
    return "candidate" if normalized else "missing"


def _pick_primary_reference_row(rows: list) -> object | None:
    if not rows:
        return None
    for target_status in ("locked", "selected", "candidate"):
        for row in rows:
            if _normalize_reference_status(getattr(row, "status", "")) == target_status:
                return row
    return rows[0]


def _build_asset_reference_payload(reference_row, asset_type: str, asset_id: str, asset_name: str) -> dict:
    if not reference_row:
        return {
            "reference_asset_id": None,
            "reference_token": "",
            "image_url": "",
            "reference_status": "missing",
            "has_reference": False,
            "locked_reference": False,
        }
    reference_status = _normalize_reference_status(getattr(reference_row, "status", ""))
    image_url = str(getattr(reference_row, "image_url", "") or getattr(reference_row, "local_path", "") or "").strip()
    return {
        "reference_asset_id": f"ref-{reference_row.id}",
        "reference_token": str(getattr(reference_row, "reference_token", "") or "").strip(),
        "image_url": image_url,
        "reference_status": reference_status,
        "has_reference": bool(image_url),
        "locked_reference": reference_status == "locked",
    }


def _build_generation_reference_item(asset_payload: dict) -> dict | None:
    if not isinstance(asset_payload, dict):
        return None
    image_url = str(asset_payload.get("image_url") or "").strip()
    if not image_url:
        return None
    return {
        "asset_type": str(asset_payload.get("asset_type") or "").strip(),
        "asset_id": str(asset_payload.get("asset_id") or "").strip(),
        "asset_name": str(asset_payload.get("asset_name") or "").strip(),
        "reference_asset_id": str(asset_payload.get("reference_asset_id") or "").strip(),
        "reference_token": str(asset_payload.get("reference_token") or "").strip(),
        "image_url": image_url,
        "reference_status": _normalize_reference_status(asset_payload.get("reference_status")),
        "role": "character" if str(asset_payload.get("asset_type") or "").strip() == "character" else "scene" if str(asset_payload.get("asset_type") or "").strip() == "scene" else "prop",
        "weight": 1.2 if str(asset_payload.get("asset_type") or "").strip() == "character" else 1.0,
    }


def _build_effective_compiled_reference_payloads(context: dict, used_assets: list[dict] | None) -> tuple[list[str], list[dict]]:
    if not isinstance(context, dict):
        return [], []

    bound_assets_by_key = {
        (str(item.get("asset_type") or "").strip(), str(item.get("asset_id") or "").strip()): item
        for item in (context.get("bound_assets") or [])
        if isinstance(item, dict)
    }

    compiled_reference_images: list[dict] = []
    seen_reference_asset_ids: set[str] = set()

    for item in used_assets or []:
        if not isinstance(item, dict):
            continue
        asset_type = str(item.get("asset_type") or "").strip()
        asset_id = str(item.get("asset_id") or "").strip()
        bound_item = bound_assets_by_key.get((asset_type, asset_id), item)
        reference_item = _build_generation_reference_item(bound_item)
        if not isinstance(reference_item, dict):
            continue
        reference_asset_id = str(reference_item.get("reference_asset_id") or "").strip()
        if not reference_asset_id or reference_asset_id in seen_reference_asset_ids:
            continue
        seen_reference_asset_ids.add(reference_asset_id)
        compiled_reference_images.append(reference_item)

    compiled_reference_asset_ids = [
        str(item.get("reference_asset_id") or "").strip()
        for item in compiled_reference_images
        if str(item.get("reference_asset_id") or "").strip()
    ]
    return compiled_reference_asset_ids, compiled_reference_images


def _normalize_compiler_asset_text(value: str | None, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return str(fallback or "").strip()
    parts = [item.strip() for item in re.split(r"[，,。；;：:\n\r]+", text) if item.strip()]
    deduped: list[str] = []
    generic_visual_template_tokens = (
        "道具视觉描述",
        "高质量写实道具多角度展示图",
        "横向构图",
        "2行3列",
        "六个极正视角",
        "绝对正前方视图",
        "绝对正后方视图",
        "绝对左侧视图",
        "绝对右侧视图",
        "绝对正上方俯拍视图",
        "绝对正下方仰拍视图",
        "纯白色纯净背景",
        "专业产品影棚摄影",
        "标准六视图参考",
        "所有视图必须是同一道具",
        "材质、颜色、比例、结构完全一致",
        "使用超长焦镜头或移轴镜头效果",
        "透视变形降到最低",
        "不得出现任何人物",
        "无其他道具",
        "无文字",
        "无水印",
        "无logo",
        "无UI元素",
    )
    for part in parts:
        if any(token in part for token in generic_visual_template_tokens):
            continue
        if any(part == existing or part in existing for existing in deduped):
            continue
        deduped = [existing for existing in deduped if existing not in part]
        deduped.append(part)
    return "，".join(deduped) if deduped else str(fallback or "").strip()


def _normalize_compiler_importance(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if text in {"high", "medium", "low"}:
        return text
    mapping = {
        "高": "high",
        "重要": "high",
        "核心": "high",
        "中": "medium",
        "一般": "medium",
        "低": "low",
        "次要": "low",
    }
    return mapping.get(text, "medium")


def _non_empty_canonical_parts(parts: list[tuple[str, str | None]]) -> list[dict]:
    normalized: list[dict] = []
    for key, value in parts:
        text = str(value or "").strip()
        if not text:
            continue
        normalized.append({"key": key, "text": text})
    return normalized


def _build_storyboard_character_canonical_payload(row) -> dict:
    from agents.portrait_base import canonicalize_character_prompt_inputs, canonicalize_variant_prompt_inputs

    meta_info = safe_json_loads(getattr(row, "meta_info", "{}")) if getattr(row, "meta_info", None) else {}
    if not isinstance(meta_info, dict):
        meta_info = {}
    structured = meta_info.get("structured_result", {}) if isinstance(meta_info.get("structured_result", {}), dict) else {}
    shot_ids = structured.get("shot_ids", [])
    if not isinstance(shot_ids, list):
        shot_ids = []

    scope = str(structured.get("scope") or meta_info.get("scope") or getattr(row, "stage_name", "") or "episode_default").strip()
    identity = str(structured.get("identity") or "").strip()
    temperament = str(structured.get("temperament") or "").strip()
    appearance_source = str(getattr(row, "core_prompt_zh", "") or structured.get("core_prompt_zh") or structured.get("appearance") or "").strip()
    appearance = _normalize_compiler_asset_text(appearance_source)
    canonical_fields = canonicalize_character_prompt_inputs(
        identity=identity,
        temperament=temperament,
        appearance=appearance,
    )
    makeup_source = str(structured.get("makeup_spec") or structured.get("expression_mood") or getattr(row, "makeup_spec", "") or "").strip()
    scene_effects_source = str(getattr(row, "scene_prompt_zh", "") or structured.get("scene_prompt_zh") or "").strip()
    hairstyle_source = str(getattr(row, "hair_style", "") or structured.get("hair_style") or "").strip()
    outfit_source = str(getattr(row, "refined_outfit", "") or structured.get("refined_outfit") or "").strip()
    accessories_source = str(getattr(row, "refined_accessories", "") or structured.get("refined_accessories") or "").strip()
    variant_fields = canonicalize_variant_prompt_inputs(
        identity=canonical_fields["identity"],
        makeup_expression=makeup_source,
        scene_effects=scene_effects_source,
        hairstyle=hairstyle_source,
        outfit=outfit_source,
        accessories=accessories_source,
    )
    consistency_source = str(getattr(row, "consistency_notes", "") or structured.get("consistency_notes") or "").strip()
    consistency_notes = _normalize_compiler_asset_text(consistency_source)

    canonical = {
        "scope": scope or "episode_default",
        "stage_name": str(structured.get("stage_name") or getattr(row, "stage_name", "") or "").strip(),
        "variant_name": str(structured.get("variant_name") or structured.get("stage_name") or getattr(row, "stage_name", "") or "").strip(),
        "shot_ids": [str(item).strip() for item in shot_ids if str(item).strip()],
        "identity": canonical_fields["identity"] if identity else "",
        "temperament": canonical_fields["temperament"] if temperament else "",
        "appearance": canonical_fields["appearance"] or appearance,
        "hairstyle": _normalize_compiler_asset_text(variant_fields["hairstyle"]) if hairstyle_source else "",
        "outfit": _normalize_compiler_asset_text(variant_fields["outfit"]) if outfit_source else "",
        "accessories": _normalize_compiler_asset_text(variant_fields["accessories"]) if accessories_source else "",
        "makeup_expression": _normalize_compiler_asset_text(variant_fields["makeup_expression"]) if makeup_source else "",
        "scene_effects": _normalize_compiler_asset_text(variant_fields["scene_effects"]) if scene_effects_source else "",
        "consistency_notes": consistency_notes,
    }
    parts = _non_empty_canonical_parts([
        ("canonical_identity", canonical["identity"]),
        ("canonical_temperament", canonical["temperament"]),
        ("canonical_appearance", canonical["appearance"]),
        ("canonical_hairstyle", canonical["hairstyle"]),
        ("canonical_outfit", canonical["outfit"]),
        ("canonical_accessories", canonical["accessories"]),
        ("canonical_makeup_expression", canonical["makeup_expression"]),
        ("canonical_scene_effects", canonical["scene_effects"]),
        ("canonical_consistency", canonical["consistency_notes"]),
    ])
    if canonical["scope"]:
        parts.append({"key": "variant_scope", "text": canonical["scope"]})
    if canonical["variant_name"]:
        parts.append({"key": "variant_name", "text": canonical["variant_name"]})
    if canonical["stage_name"]:
        parts.append({"key": "stage_name", "text": canonical["stage_name"]})
    if canonical["shot_ids"]:
        parts.append({"key": "shot_ids", "text": "、".join(canonical["shot_ids"])})
    return {
        "canonical_prompt_profile": canonical,
        "canonical_prompt_parts": parts,
        "canonical_prompt_raw": "\n".join(f"{item['key']}: {item['text']}" for item in parts if str(item.get("text") or "").strip()),
    }


def _build_storyboard_scene_canonical_payload(row) -> dict:
    canonical = {
        "description": _normalize_compiler_asset_text(
            str(getattr(row, "description", "") or getattr(row, "visual_prompt_zh", "") or getattr(row, "core_prompt_zh", "") or "")
        ),
        "style": _normalize_compiler_asset_text(str(getattr(row, "style", "") or "")),
        "lighting_mood": _normalize_compiler_asset_text(str(getattr(row, "lighting_mood", "") or "")),
        "color_palette": _normalize_compiler_asset_text(str(getattr(row, "color_palette", "") or "")),
        "core_visual": _normalize_compiler_asset_text(
            str(getattr(row, "visual_prompt_zh", "") or getattr(row, "core_prompt_zh", "") or getattr(row, "description", "") or "")
        ),
    }
    parts = _non_empty_canonical_parts([
        ("canonical_description", canonical["description"]),
        ("canonical_style", canonical["style"]),
        ("canonical_lighting_mood", canonical["lighting_mood"]),
        ("canonical_color_palette", canonical["color_palette"]),
        ("canonical_core_visual", canonical["core_visual"]),
    ])
    return {
        "canonical_prompt_profile": canonical,
        "canonical_prompt_parts": parts,
        "canonical_prompt_raw": "\n".join(f"{item['key']}: {item['text']}" for item in parts if str(item.get("text") or "").strip()),
    }


def _build_storyboard_prop_canonical_payload(row) -> dict:
    canonical = {
        "description": _normalize_compiler_asset_text(
            str(getattr(row, "description", "") or getattr(row, "visual_prompt_zh", "") or getattr(row, "core_prompt_zh", "") or "")
        ),
        "category": _normalize_compiler_asset_text(str(getattr(row, "category", "") or "")),
        "importance": _normalize_compiler_importance(getattr(row, "importance", "")) if str(getattr(row, "importance", "") or "").strip() else "",
        "core_visual": _normalize_compiler_asset_text(
            str(getattr(row, "visual_prompt_zh", "") or getattr(row, "core_prompt_zh", "") or getattr(row, "description", "") or "")
        ),
    }
    parts = _non_empty_canonical_parts([
        ("canonical_description", canonical["description"]),
        ("canonical_category", canonical["category"]),
        ("canonical_importance", canonical["importance"]),
        ("canonical_core_visual", canonical["core_visual"]),
    ])
    return {
        "canonical_prompt_profile": canonical,
        "canonical_prompt_parts": parts,
        "canonical_prompt_raw": "\n".join(f"{item['key']}: {item['text']}" for item in parts if str(item.get("text") or "").strip()),
    }


def _build_prompt_compile_context(book_id: int, shot, structure: dict, acceptance_feedback: dict, reference_summary: dict) -> dict:
    scene_asset_id = str(structure.get("scene_asset_id") or "").strip()
    character_asset_ids = [str(item).strip() for item in (structure.get("character_asset_ids") or []) if str(item).strip()]
    prop_asset_ids = [str(item).strip() for item in (structure.get("prop_asset_ids") or []) if str(item).strip()]
    style_key = str(structure.get("style_key") or "default").strip() or "default"
    warnings: list[str] = []

    from models import Session, VisualLocation, VisualMakeup, VisualProp, VisualReferenceAsset

    with Session() as s:
        def build_asset_payload(asset_type: str, asset_id: str, row, asset_name: str) -> dict:
            query = s.query(VisualReferenceAsset).filter(
                VisualReferenceAsset.book_id == book_id,
                VisualReferenceAsset.asset_type == asset_type,
                VisualReferenceAsset.asset_id == str(asset_id),
            )
            query = query.filter((VisualReferenceAsset.episode == shot.episode) | (VisualReferenceAsset.episode.is_(None)))
            reference_rows = query.order_by(VisualReferenceAsset.id.desc()).all()
            reference_diag = _collect_asset_reference_diagnostics(book_id, asset_type, asset_id, shot.episode)
            primary_reference = _pick_primary_reference_row(reference_rows)
            reference_payload = _build_asset_reference_payload(primary_reference, asset_type, asset_id, asset_name)
            payload = {
                "asset_type": asset_type,
                "asset_id": str(asset_id or "").strip(),
                "asset_name": str(asset_name or "").strip(),
                "asset_status": str(getattr(row, "asset_status", "") or "draft").strip() or "draft",
                "reference_total": int(reference_diag.get("total") or 0),
                "reference_statuses": reference_diag.get("statuses", []),
                **reference_payload,
            }
            if not payload["has_reference"]:
                asset_label = "场景" if asset_type == "scene" else "角色" if asset_type == "character" else "道具"
                warnings.append(f"{asset_label}资产“{payload['asset_name']}”还没有参考图。")
            elif payload["reference_status"] == "candidate":
                warnings.append(f"{payload['asset_name']} 目前只有候选参考图，尚未锁定。")
            return payload

        def infer_reference_source(payload: dict) -> str:
            explicit = str(payload.get("reference_source") or "").strip().lower()
            if explicit:
                return explicit
            status = _normalize_reference_status(payload.get("reference_status"))
            if status == "locked":
                return "locked"
            if status == "selected":
                return "selected"
            if status == "candidate":
                return "candidate"
            return "missing"

        scene_payload = None
        scene_name = str(shot.scene_name or "").strip()
        if scene_asset_id:
            scene_row = s.query(VisualLocation).filter(
                VisualLocation.book_id == book_id,
                VisualLocation.id == int(scene_asset_id),
            ).first()
            if scene_row:
                scene_name = str(scene_row.name or scene_name).strip()
                scene_payload = build_asset_payload("scene", scene_asset_id, scene_row, scene_row.name)

        character_payloads: list[dict] = []
        for asset_id in character_asset_ids:
            row = s.query(VisualMakeup).filter(
                VisualMakeup.book_id == book_id,
                VisualMakeup.id == int(asset_id),
            ).first()
            if row:
                character_payloads.append(build_asset_payload("character", asset_id, row, row.character_name))

        prop_payloads: list[dict] = []
        for asset_id in prop_asset_ids:
            row = s.query(VisualProp).filter(
                VisualProp.book_id == book_id,
                VisualProp.id == int(asset_id),
            ).first()
            if row:
                prop_payloads.append(build_asset_payload("prop", asset_id, row, row.name))

    if not scene_asset_id:
        warnings.append("缺少场景资产绑定。")

    bound_assets = [item for item in [scene_payload, *character_payloads, *prop_payloads] if isinstance(item, dict)]
    reference_images = [item for item in (_build_generation_reference_item(asset) for asset in bound_assets) if isinstance(item, dict)]

    return {
        "episode": shot.episode,
        "shot_id": shot.shot_id,
        "scene": scene_name,
        "scene_name": scene_name,
        "camera_angle": shot.camera_angle,
        "camera_movement": shot.camera_movement,
        "transition": shot.transition,
        "lighting": shot.lighting,
        "duration": shot.duration,
        "start_state": shot.start_state,
        "action_process": shot.action_process,
        "end_state": shot.end_state,
        "dialogue": shot.dialogue,
        "style_key": style_key,
        "character_names": [item["asset_name"] for item in character_payloads],
        "prop_names": [item["asset_name"] for item in prop_payloads],
        "asset_bindings": {
            "scene": scene_payload,
            "characters": character_payloads,
            "props": prop_payloads,
        },
        "bound_assets": bound_assets,
        "reference_images": reference_images,
        "reference_asset_ids": [item["reference_asset_id"] for item in reference_images if str(item.get("reference_asset_id") or "").strip()],
        "compiled_reference_images": reference_images,
        "compiled_reference_asset_ids": [item["reference_asset_id"] for item in reference_images if str(item.get("reference_asset_id") or "").strip()],
        "reference_summary": reference_summary if isinstance(reference_summary, dict) else {},
        "acceptance_feedback": acceptance_feedback if isinstance(acceptance_feedback, dict) else {},
        "warnings": list(dict.fromkeys(warnings)),
        "continuity": _build_continuity_context(book_id, shot),
        "retention": structure.get("retention", {}),
        "emotion_arc": structure.get("emotion_arc", {}),
        "shot_purpose": structure.get("shot_purpose", ""),
        "camera_library": _get_camera_library_snapshot(),
        "emotion_library": _get_emotion_library_snapshot(),
        "shot_size_library": _get_shot_size_library_snapshot(),
        "short_drama_library": _get_short_drama_library_snapshot(),
    }


def _build_continuity_context(book_id: int, current_shot) -> dict:
    """构建跨镜头连续性上下文。

    读取同一集的上一个镜头，将其 end_state 作为当前镜头的连续性约束。
    """
    from models import Session, StoryboardShot

    with Session() as s:
        prev_shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == current_shot.episode,
            StoryboardShot.shot_id < current_shot.shot_id,
        ).order_by(StoryboardShot.shot_id.desc()).first()

        if not prev_shot:
            return {"has_previous": False}

        return {
            "has_previous": True,
            "previous_shot_id": prev_shot.shot_id,
            "previous_end_state": prev_shot.end_state or "",
            "previous_scene_name": prev_shot.scene_name or "",
        }


def _build_prompt_compile_context_v2(book_id: int, shot, structure: dict, acceptance_feedback: dict, reference_summary: dict) -> dict:
    scene_asset_id = str(structure.get("scene_asset_id") or "").strip()
    character_asset_ids = [str(item).strip() for item in (structure.get("character_asset_ids") or []) if str(item).strip()]
    prop_asset_ids = [str(item).strip() for item in (structure.get("prop_asset_ids") or []) if str(item).strip()]
    style_key = str(structure.get("style_key") or "default").strip() or "default"
    warnings: list[str] = []

    from models import Session, VisualLocation, VisualMakeup, VisualProp, VisualReferenceAsset

    with Session() as s:
        location_rows = s.query(VisualLocation).filter(VisualLocation.book_id == book_id).all()
        prop_rows = s.query(VisualProp).filter(VisualProp.book_id == book_id).all()

        def _join_authority_lines(parts: list[tuple[str, str]]) -> tuple[str, list[dict]]:
            normalized_parts: list[dict] = []
            lines: list[str] = []
            for key, value in parts:
                text = str(value or "").strip()
                if not text:
                    continue
                normalized_parts.append({"key": key, "text": text})
                lines.append(f"{key}: {text}")
            return "\n".join(lines), normalized_parts

        def build_authority_prompt_payload(asset_type: str, row) -> dict:
            if asset_type == "character":
                authority_raw, authority_parts = _join_authority_lines([
                    ("confirmed_prompt_raw", getattr(row, "visual_prompt_zh", "") or getattr(row, "scene_prompt_zh", "") or ""),
                    ("core_prompt", getattr(row, "core_prompt_zh", "") or ""),
                    ("outfit_prompt", getattr(row, "outfit_prompt_zh", "") or ""),
                    ("refined_outfit", getattr(row, "refined_outfit", "") or ""),
                    ("hair_style", getattr(row, "hair_style", "") or ""),
                    ("makeup_spec", getattr(row, "makeup_spec", "") or ""),
                    ("consistency_notes", getattr(row, "consistency_notes", "") or ""),
                ])
                canonical_payload = _build_storyboard_character_canonical_payload(row)
                authority_parts = [*authority_parts, *(canonical_payload.get("canonical_prompt_parts") or [])]
                authority_raw = "\n".join([
                    item for item in [authority_raw, canonical_payload.get("canonical_prompt_raw", "")]
                    if str(item or "").strip()
                ])
                return {
                    "authority_prompt_raw": authority_raw,
                    "authority_prompt_parts": authority_parts,
                    "authority_prompt_source": "character_makeup",
                    **canonical_payload,
                }

            if asset_type == "scene":
                authority_raw, authority_parts = _join_authority_lines([
                    ("confirmed_prompt_raw", getattr(row, "zh_prompt", "") or getattr(row, "visual_prompt_zh", "") or getattr(row, "core_prompt_zh", "") or ""),
                    ("description", getattr(row, "description", "") or ""),
                    ("style", getattr(row, "style", "") or ""),
                    ("lighting_mood", getattr(row, "lighting_mood", "") or ""),
                    ("color_palette", getattr(row, "color_palette", "") or ""),
                ])
                canonical_payload = _build_storyboard_scene_canonical_payload(row)
                authority_parts = [*authority_parts, *(canonical_payload.get("canonical_prompt_parts") or [])]
                authority_raw = "\n".join([
                    item for item in [authority_raw, canonical_payload.get("canonical_prompt_raw", "")]
                    if str(item or "").strip()
                ])
                return {
                    "authority_prompt_raw": authority_raw,
                    "authority_prompt_parts": authority_parts,
                    "authority_prompt_source": "scene_asset",
                    **canonical_payload,
                }

            authority_raw, authority_parts = _join_authority_lines([
                ("confirmed_prompt_raw", getattr(row, "zh_prompt", "") or getattr(row, "visual_prompt_zh", "") or getattr(row, "core_prompt_zh", "") or ""),
                ("description", getattr(row, "description", "") or ""),
                ("importance", getattr(row, "importance", "") or ""),
                ("category", getattr(row, "category", "") or ""),
            ])
            canonical_payload = _build_storyboard_prop_canonical_payload(row)
            authority_parts = [*authority_parts, *(canonical_payload.get("canonical_prompt_parts") or [])]
            authority_raw = "\n".join([
                item for item in [authority_raw, canonical_payload.get("canonical_prompt_raw", "")]
                if str(item or "").strip()
            ])
            return {
                "authority_prompt_raw": authority_raw,
                "authority_prompt_parts": authority_parts,
                "authority_prompt_source": "prop_asset",
                **canonical_payload,
            }

        def build_asset_payload(asset_type: str, asset_id: str, row, asset_name: str) -> dict:
            query = s.query(VisualReferenceAsset).filter(
                VisualReferenceAsset.book_id == book_id,
                VisualReferenceAsset.asset_type == asset_type,
                VisualReferenceAsset.asset_id == str(asset_id),
            )
            query = query.filter((VisualReferenceAsset.episode == shot.episode) | (VisualReferenceAsset.episode.is_(None)))
            reference_rows = query.order_by(VisualReferenceAsset.id.desc()).all()
            reference_diag = _collect_asset_reference_diagnostics(book_id, asset_type, asset_id, shot.episode)
            primary_reference = _pick_primary_reference_row(reference_rows)
            reference_payload = _build_asset_reference_payload(primary_reference, asset_type, asset_id, asset_name)
            payload = {
                "asset_type": asset_type,
                "asset_id": str(asset_id or "").strip(),
                "asset_name": str(asset_name or "").strip(),
                "asset_status": str(getattr(row, "asset_status", "") or "draft").strip() or "draft",
                "reference_total": int(reference_diag.get("total") or 0),
                "reference_statuses": reference_diag.get("statuses", []),
                **build_authority_prompt_payload(asset_type, row),
                **reference_payload,
            }
            if not payload["has_reference"]:
                asset_label = "场景" if asset_type == "scene" else "角色" if asset_type == "character" else "道具"
                warnings.append(f"{asset_label}资产“{payload['asset_name']}”还没有参考图。")
            elif payload["reference_status"] == "candidate":
                warnings.append(f"{payload['asset_name']} 目前只有候选参考图，尚未锁定。")
            return payload

        def infer_reference_source(payload: dict) -> str:
            explicit = str(payload.get("reference_source") or "").strip().lower()
            if explicit:
                return explicit
            status = _normalize_reference_status(payload.get("reference_status"))
            if status == "locked":
                return "locked"
            if status == "selected":
                return "selected"
            if status == "candidate":
                return "candidate"
            return "missing"

        def build_character_payload(asset_id: str) -> dict | None:
            if not _is_integer_string(asset_id):
                return None

            preferred_row = s.query(VisualMakeup).filter(
                VisualMakeup.book_id == book_id,
                VisualMakeup.id == int(asset_id),
            ).first()
            if not preferred_row:
                preferred_row = _find_profile_fallback_makeup_by_id(s, book_id, asset_id)
            if not preferred_row:
                return None

            resolved = _resolve_makeup_for_character(
                s,
                book_id,
                shot.episode,
                shot.shot_id,
                shot.scene_name,
                str(preferred_row.character_name or "").strip(),
                preferred_asset_id=asset_id,
            )
            if not resolved or resolved.get("row") is None:
                return build_asset_payload("character", asset_id, preferred_row, preferred_row.character_name)

            resolved_row = resolved["row"]
            base_row = resolved.get("base_row")
            payload = build_asset_payload("character", str(resolved_row.id), resolved_row, resolved_row.character_name)

            active_query = s.query(VisualReferenceAsset).filter(
                VisualReferenceAsset.book_id == book_id,
                VisualReferenceAsset.asset_type == "character",
                VisualReferenceAsset.asset_id == str(resolved_row.id),
            ).filter((VisualReferenceAsset.episode == shot.episode) | (VisualReferenceAsset.episode.is_(None)))
            active_reference = _build_asset_reference_payload(
                _pick_primary_reference_row(active_query.order_by(VisualReferenceAsset.id.desc()).all()),
                "character",
                str(resolved_row.id),
                resolved_row.character_name,
            )

            base_reference = {
                "reference_asset_id": None,
                "reference_token": "",
                "image_url": "",
                "reference_status": "missing",
                "has_reference": False,
                "locked_reference": False,
            }
            if base_row is not None:
                base_query = s.query(VisualReferenceAsset).filter(
                    VisualReferenceAsset.book_id == book_id,
                    VisualReferenceAsset.asset_type == "character",
                    VisualReferenceAsset.asset_id == str(base_row.id),
                ).filter((VisualReferenceAsset.episode == shot.episode) | (VisualReferenceAsset.episode.is_(None)))
                base_reference = _build_asset_reference_payload(
                    _pick_primary_reference_row(base_query.order_by(VisualReferenceAsset.id.desc()).all()),
                    "character",
                    str(base_row.id),
                    base_row.character_name,
                )

            selected_reference = active_reference if active_reference.get("has_reference") else base_reference
            payload.update({
                "requested_asset_id": str(asset_id),
                "resolved_from_asset_id": str(preferred_row.id),
                "variant_scope": resolved.get("scope", "episode_default"),
                "variant_name": str(getattr(resolved_row, "stage_name", "") or "").strip() or resolved.get("scope_label", "瀹氬"),
                "resolution_reason": resolved.get("resolution_reason", ""),
                "stage_name": str(getattr(resolved_row, "stage_name", "") or "").strip(),
                "makeup_scope": resolved.get("scope", "episode_default"),
                "scope_label": resolved.get("scope_label", "瀹氬"),
                "base_makeup_id": str(base_row.id) if base_row is not None else None,
                "base_stage_name": str(getattr(base_row, "stage_name", "") or "").strip() if base_row is not None else "",
                "base_reference": base_reference,
                "active_variant_reference": active_reference,
                "reference_source": "active_variant" if active_reference.get("has_reference") else "base_identity" if base_reference.get("has_reference") else "missing",
                "reference_asset_id": selected_reference.get("reference_asset_id"),
                "reference_token": selected_reference.get("reference_token", ""),
                "image_url": selected_reference.get("image_url", ""),
                "reference_status": selected_reference.get("reference_status", "missing"),
                "has_reference": bool(selected_reference.get("has_reference")),
                "locked_reference": bool(selected_reference.get("locked_reference")),
            })
            if payload["reference_source"] == "base_identity":
                warnings.append(
                    f"{payload['asset_name']} 当前镜头没有命中精调参考图，已回退到基础定妆参考图。"
                )
            return payload

        scene_payload = None
        scene_name = str(shot.scene_name or "").strip()
        if scene_asset_id and scene_asset_id.isdigit():
            scene_row = next((item for item in location_rows if int(getattr(item, "id", 0) or 0) == int(scene_asset_id)), None)
            if scene_row:
                scene_name = str(scene_row.name or scene_name).strip()
                scene_payload = build_asset_payload("scene", scene_asset_id, scene_row, scene_row.name)
                scene_payload.update(_build_scene_variant_metadata(scene_row, location_rows))
                scene_payload["reference_source"] = infer_reference_source(scene_payload)

        character_payloads: list[dict] = []
        for asset_id in character_asset_ids:
            payload = build_character_payload(asset_id)
            if payload:
                character_payloads.append(payload)

        prop_payloads: list[dict] = []
        for asset_id in prop_asset_ids:
            if not _is_integer_string(asset_id):
                continue
            row = next((item for item in prop_rows if int(getattr(item, "id", 0) or 0) == int(asset_id)), None)
            if row:
                payload = build_asset_payload("prop", asset_id, row, row.name)
                payload.update(_build_prop_variant_metadata(row, prop_rows))
                payload["reference_source"] = infer_reference_source(payload)
                prop_payloads.append(payload)

    if not scene_asset_id:
        warnings.append("缺少场景资产绑定。")

    bound_assets = [item for item in [scene_payload, *character_payloads, *prop_payloads] if isinstance(item, dict)]
    reference_images = [item for item in (_build_generation_reference_item(asset) for asset in bound_assets) if isinstance(item, dict)]
    compile_prompt_contract = _build_compile_prompt_contract(bound_assets)
    state_change_text = " ".join([
        str(shot.start_state or "").strip(),
        str(shot.action_process or "").strip(),
        str(shot.end_state or "").strip(),
        str(shot.dialogue or "").strip(),
    ])
    state_change_markers = [
        "湿",
        "雨",
        "血",
        "伤",
        "脏",
        "泥",
        "灰",
        "破",
        "换装",
        "狼狈",
        "疲惫",
        "哭",
        "泪",
        "rain",
        "wet",
        "blood",
        "injur",
        "mud",
        "dust",
        "tear",
        "cry",
    ]
    has_state_change = any(marker in state_change_text for marker in state_change_markers)
    if has_state_change:
        for payload in character_payloads:
            if _needs_state_change_makeup_warning(payload):
                warnings.append(
                    f"{payload.get('asset_name', '角色')} 当前镜头存在明显状态变化，建议补一条分镜精调定妆。"
                )

    production_skill_runtime = build_project_production_skill_runtime(book_id)

    return {
        "episode": shot.episode,
        "shot_id": shot.shot_id,
        "scene": scene_name,
        "scene_name": scene_name,
        "camera_angle": shot.camera_angle,
        "camera_movement": shot.camera_movement,
        "transition": shot.transition,
        "lighting": shot.lighting,
        "duration": shot.duration,
        "start_state": shot.start_state,
        "action_process": shot.action_process,
        "end_state": shot.end_state,
        "dialogue": shot.dialogue,
        "style_key": style_key,
        "character_names": [item["asset_name"] for item in character_payloads],
        "prop_names": [item["asset_name"] for item in prop_payloads],
        "asset_bindings": {
            "scene": scene_payload,
            "characters": character_payloads,
            "props": prop_payloads,
        },
        "character_variants": character_payloads,
        "bound_assets": bound_assets,
        "compile_prompt_contract": compile_prompt_contract,
        "visual_fact_targets": compile_prompt_contract.get("visual_fact_targets", []),
        "required_used_assets": compile_prompt_contract.get("required_used_assets", []),
        "reference_images": reference_images,
        "reference_asset_ids": [item["reference_asset_id"] for item in reference_images if str(item.get("reference_asset_id") or "").strip()],
        "compiled_reference_images": reference_images,
        "compiled_reference_asset_ids": [item["reference_asset_id"] for item in reference_images if str(item.get("reference_asset_id") or "").strip()],
        "reference_summary": reference_summary if isinstance(reference_summary, dict) else {},
        "acceptance_feedback": acceptance_feedback if isinstance(acceptance_feedback, dict) else {},
        "production_skill": {
            "runtime_summary": production_skill_runtime.get("runtime_summary", {}),
            "directing_rules": production_skill_runtime.get("directing_rules", {}),
            "asset_rules": production_skill_runtime.get("asset_rules", {}),
            "hard_constraints": production_skill_runtime.get("hard_constraints", []),
            "soft_preferences": production_skill_runtime.get("soft_preferences", []),
            "forbidden_patterns": production_skill_runtime.get("forbidden_patterns", []),
            "output_contracts": production_skill_runtime.get("output_contracts", {}),
        },
        "warnings": list(dict.fromkeys(warnings)),
        "continuity": _build_continuity_context(book_id, shot),
        "retention": structure.get("retention", {}),
        "emotion_arc": structure.get("emotion_arc", {}),
        "shot_purpose": structure.get("shot_purpose", ""),
        "camera_library": _get_camera_library_snapshot(),
        "emotion_library": _get_emotion_library_snapshot(),
        "shot_size_library": _get_shot_size_library_snapshot(),
        "short_drama_library": _get_short_drama_library_snapshot(),
    }


def _prompt_compile_context_needs_refresh(prompt_compile_context: dict) -> bool:
    if not isinstance(prompt_compile_context, dict):
        return True
    if "compiled_reference_asset_ids" not in prompt_compile_context:
        return True
    if "compiled_reference_images" not in prompt_compile_context:
        return True
    if "compile_prompt_contract" not in prompt_compile_context:
        return True
    if "visual_fact_targets" not in prompt_compile_context:
        return True
    if "required_used_assets" not in prompt_compile_context:
        return True

    asset_bindings = prompt_compile_context.get("asset_bindings", {})
    if not isinstance(asset_bindings, dict):
        return True

    scene = asset_bindings.get("scene")
    if isinstance(scene, dict) and scene:
        if not str(scene.get("authority_prompt_source") or "").strip():
            return True
        if not str(scene.get("variant_scope") or "").strip():
            return True
        if not str(scene.get("reference_source") or "").strip():
            return True

    for item in asset_bindings.get("characters", []) or []:
        if isinstance(item, dict) and item and not str(item.get("authority_prompt_source") or "").strip():
            return True

    for item in asset_bindings.get("props", []) or []:
        if isinstance(item, dict) and item:
            if not str(item.get("authority_prompt_source") or "").strip():
                return True
            if not str(item.get("variant_scope") or "").strip():
                return True
            if not str(item.get("reference_source") or "").strip():
                return True

    return False


def _normalize_prompt_binding_contract(binding: dict | None) -> dict:
    if not isinstance(binding, dict):
        return {}
    return {
        "asset_id": str(binding.get("asset_id") or "").strip(),
        "asset_name": str(binding.get("asset_name") or "").strip(),
        "reference_asset_id": str(binding.get("reference_asset_id") or "").strip(),
        "reference_status": str(binding.get("reference_status") or "").strip(),
        "has_reference": bool(binding.get("has_reference")),
        "locked_reference": bool(binding.get("locked_reference")),
        "variant_scope": str(binding.get("variant_scope") or "").strip(),
        "scope_label": str(binding.get("scope_label") or "").strip(),
        "stage_name": str(binding.get("stage_name") or "").strip(),
        "reference_source": str(binding.get("reference_source") or "").strip(),
        "authority_prompt_source": str(binding.get("authority_prompt_source") or "").strip(),
    }


def _prompt_compile_context_contract_drifted(current_context: dict, rebuilt_context: dict) -> bool:
    if not isinstance(current_context, dict) or not isinstance(rebuilt_context, dict):
        return False

    current_bindings = current_context.get("asset_bindings", {}) if isinstance(current_context.get("asset_bindings", {}), dict) else {}
    rebuilt_bindings = rebuilt_context.get("asset_bindings", {}) if isinstance(rebuilt_context.get("asset_bindings", {}), dict) else {}

    if _normalize_prompt_binding_contract(current_bindings.get("scene")) != _normalize_prompt_binding_contract(rebuilt_bindings.get("scene")):
        return True

    current_characters = current_bindings.get("characters", []) if isinstance(current_bindings.get("characters", []), list) else []
    rebuilt_characters = rebuilt_bindings.get("characters", []) if isinstance(rebuilt_bindings.get("characters", []), list) else []
    current_character_signatures = sorted(
        json.dumps(_normalize_prompt_binding_contract(item), ensure_ascii=False, sort_keys=True)
        for item in current_characters
        if isinstance(item, dict)
    )
    rebuilt_character_signatures = sorted(
        json.dumps(_normalize_prompt_binding_contract(item), ensure_ascii=False, sort_keys=True)
        for item in rebuilt_characters
        if isinstance(item, dict)
    )
    if current_character_signatures != rebuilt_character_signatures:
        return True

    current_props = current_bindings.get("props", []) if isinstance(current_bindings.get("props", []), list) else []
    rebuilt_props = rebuilt_bindings.get("props", []) if isinstance(rebuilt_bindings.get("props", []), list) else []
    current_prop_signatures = sorted(
        json.dumps(_normalize_prompt_binding_contract(item), ensure_ascii=False, sort_keys=True)
        for item in current_props
        if isinstance(item, dict)
    )
    rebuilt_prop_signatures = sorted(
        json.dumps(_normalize_prompt_binding_contract(item), ensure_ascii=False, sort_keys=True)
        for item in rebuilt_props
        if isinstance(item, dict)
    )
    return current_prop_signatures != rebuilt_prop_signatures


def _prompt_compiler_diagnostics_need_refresh(diagnostics: dict) -> bool:
    if not isinstance(diagnostics, dict):
        return True
    normalized_checks = [
        item
        for item in (diagnostics.get("checks") or [])
        if isinstance(item, dict) and str(item.get("key") or "").strip()
    ]
    check_keys = {
        str(item.get("key") or "").strip()
        for item in normalized_checks
    }
    required_check_keys = {
        "meta_prompt_leakage",
        "static_prompt_quality",
        "motion_prompt_quality",
        "screenplay_prompt_residue",
        "visual_fact_target_coverage",
        "authority_prompt_inheritance",
        "character_variant_state",
        "scene_variant_state",
        "prop_variant_state",
        "high_importance_prop_presence",
        "critical_bound_asset_usage",
    }
    if not required_check_keys.issubset(check_keys):
        return True
    for item in normalized_checks:
        if str(item.get("key") or "").strip() != "visual_fact_target_coverage":
            continue
        details = item.get("details", []) if isinstance(item.get("details", []), list) else []
        for detail in details:
            text = str(detail or "").strip()
            if len(text) > 120:
                return True
            if text.count(" / ") > 4:
                return True
    return False


def _scene_name_match_text(value: Any) -> str:
    return re.sub(r"[·・•\s\t\n\r\-_\/\\—，。、；：:（）()]", "", str(value or "").strip())


def _scene_name_parts_for_match(value: Any) -> list[str]:
    return [
        item.strip()
        for item in re.split(r"[·・•\s\t\n\r\-_\/\\—，。、；：:（）()]+", str(value or "").strip())
        if len(item.strip()) >= 2
    ]


def _prompt_contains_scene_name(prompt_text: str, scene_name: str) -> bool:
    scene_text = str(scene_name or "").strip()
    prompt = str(prompt_text or "").strip()
    if not scene_text or not prompt:
        return True
    if scene_text in prompt:
        return True
    normalized_scene = _scene_name_match_text(scene_text)
    normalized_prompt = _scene_name_match_text(prompt)
    if normalized_scene and normalized_scene in normalized_prompt:
        return True
    parts = _scene_name_parts_for_match(scene_text)
    return bool(len(parts) >= 2 and all(_scene_name_match_text(part) in normalized_prompt for part in parts))


def _ensure_prompt_preserves_scene_name(prompt_text: str, scene_name: str) -> str:
    prompt = str(prompt_text or "").strip()
    scene_text = str(scene_name or "").strip()
    if not prompt or not scene_text or _prompt_contains_scene_name(prompt, scene_text):
        return prompt
    return f"{scene_text}，{prompt}"


def _refresh_legacy_prompt_compile_meta(
    book_id: int,
    shot,
    structured_shot: dict,
    prompt_compiler_meta: dict,
    prompt_static_override: str | None = None,
    prompt_motion_override: str | None = None,
) -> dict:
    if not isinstance(prompt_compiler_meta, dict):
        return {}

    prompt_compile_context = (
        prompt_compiler_meta.get("prompt_compile_context", {})
        if isinstance(prompt_compiler_meta.get("prompt_compile_context", {}), dict)
        else {}
    )
    rebuilt_context = _build_prompt_compile_context_v2(
        book_id,
        shot,
        structured_shot if isinstance(structured_shot, dict) else {},
        prompt_compiler_meta.get("acceptance_feedback", {}),
        prompt_compiler_meta.get("locked_reference_summary", {}),
    )
    diagnostics = prompt_compiler_meta.get("compiler_diagnostics", {}) if isinstance(prompt_compiler_meta.get("compiler_diagnostics", {}), dict) else {}
    if (
        not _prompt_compile_context_needs_refresh(prompt_compile_context)
        and not _prompt_compile_context_contract_drifted(prompt_compile_context, rebuilt_context)
        and not _prompt_compiler_diagnostics_need_refresh(diagnostics)
    ):
        return prompt_compiler_meta

    return _rebuild_prompt_compiler_runtime_state(
        prompt_compiler_meta,
        rebuilt_context,
        str(prompt_static_override if prompt_static_override is not None else getattr(shot, "visual_prompt_static", "") or ""),
        str(prompt_motion_override if prompt_motion_override is not None else getattr(shot, "visual_prompt_motion", "") or ""),
    )


def _normalize_compiler_used_assets(raw_used_assets: list, context: dict) -> tuple[list[dict], list[str], list[str]]:
    allowed_assets = {
        (str(item.get("asset_type") or "").strip(), str(item.get("asset_id") or "").strip()): item
        for item in (context.get("bound_assets") or [])
        if isinstance(item, dict)
    }
    missing_assets: list[str] = []
    overflow_assets: list[str] = []
    normalized: list[dict] = []

    for item in raw_used_assets or []:
        if not isinstance(item, dict):
            continue
        asset_type = str(item.get("asset_type") or "").strip()
        asset_id = str(item.get("asset_id") or "").strip()
        if (asset_type, asset_id) not in allowed_assets:
            overflow_assets.append(f"{asset_type}:{asset_id}" if asset_type or asset_id else json.dumps(item, ensure_ascii=False))
            continue
        bound_item = allowed_assets[(asset_type, asset_id)]
        normalized.append({
            "asset_type": asset_type,
            "asset_id": asset_id,
            "asset_name": str(bound_item.get("asset_name") or item.get("asset_name") or "").strip(),
            "reference_token": str(bound_item.get("reference_token") or item.get("reference_token") or "").strip() or None,
            "reference_status": _normalize_reference_status(item.get("reference_status") or bound_item.get("reference_status")),
            "has_reference": bool(bound_item.get("has_reference")),
            "locked_reference": bool(bound_item.get("locked_reference")),
            "image_url": str(bound_item.get("image_url") or "").strip(),
            "reference_asset_id": str(bound_item.get("reference_asset_id") or "").strip() or None,
        })

    for bound_item in allowed_assets.values():
        if bound_item.get("locked_reference") and not any(
            str(entry.get("asset_type") or "").strip() == str(bound_item.get("asset_type") or "").strip()
            and str(entry.get("asset_id") or "").strip() == str(bound_item.get("asset_id") or "").strip()
            for entry in normalized
        ):
            missing_assets.append(str(bound_item.get("asset_name") or "").strip())

    return normalized, missing_assets, overflow_assets


def _is_critical_bound_asset_for_usage(item: dict) -> bool:
    if not isinstance(item, dict) or not bool(item.get("has_reference")):
        return False
    asset_type = str(item.get("asset_type") or "").strip()
    if asset_type in {"scene", "character"}:
        return True
    if asset_type == "prop":
        profile = item.get("canonical_prompt_profile", {}) if isinstance(item.get("canonical_prompt_profile", {}), dict) else {}
        return str(profile.get("importance") or "").strip().lower() == "high"
    return False


def _hydrate_used_asset_from_bound_item(bound_item: dict) -> dict:
    return {
        "asset_type": str(bound_item.get("asset_type") or "").strip(),
        "asset_id": str(bound_item.get("asset_id") or "").strip(),
        "asset_name": str(bound_item.get("asset_name") or "").strip(),
        "reference_token": str(bound_item.get("reference_token") or "").strip() or None,
        "reference_status": _normalize_reference_status(bound_item.get("reference_status")),
        "has_reference": bool(bound_item.get("has_reference")),
        "locked_reference": bool(bound_item.get("locked_reference")),
        "image_url": str(bound_item.get("image_url") or "").strip(),
        "reference_asset_id": str(bound_item.get("reference_asset_id") or "").strip() or None,
    }


def _supplement_used_assets_from_prompt_mentions(
    used_assets: list[dict],
    context: dict,
    prompt_static: str,
    prompt_motion: str,
) -> list[dict]:
    normalized_used_assets = [item for item in (used_assets or []) if isinstance(item, dict)]
    bound_assets = context.get("bound_assets", []) if isinstance(context.get("bound_assets", []), list) else []
    combined_prompt = f"{str(prompt_static or '').strip()}\n{str(prompt_motion or '').strip()}"
    used_keys = {
        (
            str(item.get("asset_type") or "").strip(),
            str(item.get("asset_id") or "").strip(),
        )
        for item in normalized_used_assets
    }

    supplemented = list(normalized_used_assets)
    for bound_item in bound_assets:
        if not _is_critical_bound_asset_for_usage(bound_item):
            continue
        asset_type = str(bound_item.get("asset_type") or "").strip()
        asset_id = str(bound_item.get("asset_id") or "").strip()
        asset_name = str(bound_item.get("asset_name") or "").strip()
        reference_token = str(bound_item.get("reference_token") or "").strip()
        if not asset_type or not asset_id or (asset_type, asset_id) in used_keys:
            continue
        if asset_name and asset_name in combined_prompt:
            supplemented.append(_hydrate_used_asset_from_bound_item(bound_item))
            used_keys.add((asset_type, asset_id))
            continue
        if reference_token and reference_token in combined_prompt:
            supplemented.append(_hydrate_used_asset_from_bound_item(bound_item))
            used_keys.add((asset_type, asset_id))

    return supplemented


def _rebuild_prompt_compiler_runtime_state(
    prompt_compiler_meta: dict,
    compile_context: dict,
    prompt_static: str,
    prompt_motion: str,
) -> dict:
    base_meta = dict(prompt_compiler_meta) if isinstance(prompt_compiler_meta, dict) else {}
    normalized_context = dict(compile_context) if isinstance(compile_context, dict) else {}
    raw_used_assets = base_meta.get("used_assets", []) if isinstance(base_meta.get("used_assets", []), list) else []
    used_assets, missing_locked_assets, overflow_assets = _normalize_compiler_used_assets(raw_used_assets, normalized_context)
    if not used_assets:
        used_assets = [
            _hydrate_used_asset_from_bound_item(item)
            for item in (normalized_context.get("bound_assets") or [])
            if isinstance(item, dict)
        ]
        missing_locked_assets = []
        overflow_assets = []
    used_assets = _supplement_used_assets_from_prompt_mentions(
        used_assets,
        normalized_context,
        prompt_static,
        prompt_motion,
    )

    compiled_reference_asset_ids, compiled_reference_images = _build_effective_compiled_reference_payloads(
        normalized_context,
        used_assets,
    )
    runtime_context = {
        **normalized_context,
        "compiled_reference_images": compiled_reference_images,
        "compiled_reference_asset_ids": compiled_reference_asset_ids,
    }
    diagnostics = _build_prompt_compiler_diagnostics(
        prompt_static,
        prompt_motion,
        runtime_context,
        used_assets,
    )
    if missing_locked_assets:
        diagnostics["blocking_issues"] = list(
            dict.fromkeys([*diagnostics.get("blocking_issues", []), f"LLM 没有使用这些已锁定资产：{'、'.join(missing_locked_assets)}"])
        )
        diagnostics["status"] = "blocked"
    if overflow_assets:
        diagnostics["blocking_issues"] = list(
            dict.fromkeys([*diagnostics.get("blocking_issues", []), f"LLM 输出了未绑定资产：{'、'.join(overflow_assets)}"])
        )
        diagnostics["status"] = "blocked"

    refreshed = dict(base_meta)
    refreshed["prompt_compile_context"] = runtime_context
    refreshed["used_assets"] = used_assets
    refreshed["reference_images"] = compiled_reference_images
    refreshed["reference_asset_ids"] = compiled_reference_asset_ids
    refreshed["compiler_warnings"] = diagnostics.get("warnings", [])
    refreshed["compiler_diagnostics"] = diagnostics
    return refreshed


def _build_storyboard_prompt_version_audit(meta_payload: dict) -> dict:
    payload = meta_payload if isinstance(meta_payload, dict) else {}
    prompt_compile_context = payload.get("prompt_compile_context", {}) if isinstance(payload.get("prompt_compile_context", {}), dict) else {}
    compiler_diagnostics = payload.get("compiler_diagnostics", {}) if isinstance(payload.get("compiler_diagnostics", {}), dict) else {}
    used_assets = payload.get("used_assets", []) if isinstance(payload.get("used_assets", []), list) else []
    bound_assets = prompt_compile_context.get("bound_assets", []) if isinstance(prompt_compile_context.get("bound_assets", []), list) else []

    critical_bound_assets: list[dict] = []
    for item in bound_assets:
        if not isinstance(item, dict) or not bool(item.get("has_reference")):
            continue
        asset_type = str(item.get("asset_type") or "").strip()
        if asset_type in {"scene", "character"}:
            critical_bound_assets.append(item)
            continue
        if asset_type == "prop":
            profile = item.get("canonical_prompt_profile", {}) if isinstance(item.get("canonical_prompt_profile", {}), dict) else {}
            if str(profile.get("importance") or "").strip().lower() == "high":
                critical_bound_assets.append(item)

    critical_keys = {
        (str(item.get("asset_type") or "").strip(), str(item.get("asset_id") or "").strip())
        for item in critical_bound_assets
    }
    used_keys = {
        (str(item.get("asset_type") or "").strip(), str(item.get("asset_id") or "").strip())
        for item in used_assets
        if isinstance(item, dict)
    }
    missing_critical_assets = [
        str(item.get("asset_name") or "").strip() or f"{item.get('asset_type')}:{item.get('asset_id')}"
        for item in critical_bound_assets
        if (
            str(item.get("asset_type") or "").strip(),
            str(item.get("asset_id") or "").strip(),
        ) not in used_keys
    ]
    used_asset_types = {
        str(item.get("asset_type") or "").strip()
        for item in used_assets
        if isinstance(item, dict)
    }
    failed_check_keys = [
        str(item.get("key") or "").strip()
        for item in (compiler_diagnostics.get("checks") or [])
        if isinstance(item, dict) and not bool(item.get("passed"))
    ]
    scene_only = (
        bool(used_assets)
        and used_asset_types == {"scene"}
        and any(str(item.get("asset_type") or "").strip() in {"character", "prop"} for item in critical_bound_assets)
    )
    recoverable = not scene_only and len(missing_critical_assets) == 0 and str(compiler_diagnostics.get("status") or "").strip() != "blocked"

    return {
        "critical_bound_assets": [
            {
                "asset_type": str(item.get("asset_type") or "").strip(),
                "asset_id": str(item.get("asset_id") or "").strip(),
                "asset_name": str(item.get("asset_name") or "").strip(),
            }
            for item in critical_bound_assets
        ],
        "missing_critical_assets": missing_critical_assets,
        "missing_critical_count": len(missing_critical_assets),
        "used_asset_names": [
            str(item.get("asset_name") or "").strip()
            for item in used_assets
            if isinstance(item, dict) and str(item.get("asset_name") or "").strip()
        ],
        "used_asset_types": sorted([item for item in used_asset_types if item]),
        "failed_check_keys": failed_check_keys,
        "is_scene_only_candidate": scene_only,
        "is_recoverable_version": recoverable,
        "is_degraded_version": bool(missing_critical_assets) or scene_only,
    }


def _recommend_storyboard_restore_version(version_payloads: list[dict], current_version: int | None) -> dict | None:
    if not isinstance(version_payloads, list) or not version_payloads:
        return None

    current_payload = next(
        (item for item in version_payloads if isinstance(item, dict) and item.get("version") == current_version),
        None,
    )
    if current_payload and not bool((current_payload.get("version_audit") or {}).get("is_degraded_version")):
        return None

    healthy_candidates = [
        item
        for item in version_payloads
        if isinstance(item, dict) and bool((item.get("version_audit") or {}).get("is_recoverable_version"))
    ]
    if healthy_candidates:
        best = max(healthy_candidates, key=lambda item: int(item.get("version") or 0))
        return {
            "version": best.get("version"),
            "id": best.get("id"),
            "reason": "latest_recoverable_version",
        }

    fallback_candidates = [
        item
        for item in version_payloads
        if isinstance(item, dict) and int(((item.get("version_audit") or {}).get("missing_critical_count") or 9999)) == 0
    ]
    if fallback_candidates:
        best = max(fallback_candidates, key=lambda item: int(item.get("version") or 0))
        return {
            "version": best.get("version"),
            "id": best.get("id"),
            "reason": "latest_version_without_missing_critical_assets",
        }

    if current_payload:
        current_audit = current_payload.get("version_audit", {}) if isinstance(current_payload.get("version_audit", {}), dict) else {}
        current_missing = int(current_audit.get("missing_critical_count") or 9999)
        partial_candidates = [
            item
            for item in version_payloads
            if isinstance(item, dict)
            and int(item.get("version") or 0) < int(current_payload.get("version") or 0)
            and not bool((item.get("version_audit") or {}).get("is_scene_only_candidate"))
            and int(((item.get("version_audit") or {}).get("missing_critical_count") or 9999)) < current_missing
        ]
        if partial_candidates:
            best = sorted(
                partial_candidates,
                key=lambda item: (
                    int(((item.get("version_audit") or {}).get("missing_critical_count") or 9999)),
                    -int(item.get("version") or 0),
                ),
            )[0]
            return {
                "version": best.get("version"),
                "id": best.get("id"),
                "reason": "best_partial_recovery_version",
            }
    return None


def _build_storyboard_prompt_version_payloads(s, book_id: int, shot, current_version: int | None, locked_version: int | None) -> list[dict]:
    from models import StoryboardPromptVersion

    rows = s.query(StoryboardPromptVersion).filter(
        StoryboardPromptVersion.book_id == book_id,
        StoryboardPromptVersion.episode == shot.episode,
        StoryboardPromptVersion.shot_id == shot.shot_id,
    ).order_by(StoryboardPromptVersion.version.desc()).all()
    version_payloads: list[dict] = []
    for row in rows:
        row_meta = safe_json_loads(row.meta_info) if row.meta_info else {}
        row_structured_shot = (
            row_meta.get("structured_shot", {})
            if isinstance(row_meta, dict) and isinstance(row_meta.get("structured_shot", {}), dict)
            else {}
        )
        refreshed_meta = _refresh_legacy_prompt_compile_meta(
            book_id,
            shot,
            _auto_bind_structured_shot_assets(
                book_id,
                shot.episode,
                row_structured_shot,
                {
                    "shot_id": shot.shot_id,
                    "scene_name": shot.scene_name,
                    "action_process": shot.action_process,
                    "dialogue": shot.dialogue,
                    "start_state": shot.start_state,
                    "end_state": shot.end_state,
                    "duration": shot.duration,
                    "camera_angle": shot.camera_angle,
                    "camera_movement": shot.camera_movement,
                    "transition": shot.transition,
                },
            ),
            row_meta,
            prompt_static_override=row.prompt_static,
            prompt_motion_override=row.prompt_motion,
        )
        version_payloads.append({
            "id": row.id,
            "version": row.version,
            "compile_reason": row.compile_reason,
            "prompt_static": row.prompt_static,
            "prompt_motion": row.prompt_motion,
            "negative_prompt": row.negative_prompt,
            "meta_info": refreshed_meta,
            "locked_reference_summary": refreshed_meta.get("locked_reference_summary", {}) if isinstance(refreshed_meta, dict) else {},
            "prompt_compile_context": refreshed_meta.get("prompt_compile_context", {}) if isinstance(refreshed_meta, dict) else {},
            "used_assets": refreshed_meta.get("used_assets", []) if isinstance(refreshed_meta, dict) else [],
            "reference_images": refreshed_meta.get("reference_images", []) if isinstance(refreshed_meta, dict) else [],
            "reference_asset_ids": refreshed_meta.get("reference_asset_ids", []) if isinstance(refreshed_meta, dict) else [],
            "compiler_warnings": refreshed_meta.get("compiler_warnings", []) if isinstance(refreshed_meta, dict) else [],
            "compiler_diagnostics": refreshed_meta.get("compiler_diagnostics", {}) if isinstance(refreshed_meta, dict) else {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "is_current": row.version == current_version,
            "is_locked_version": row.version == locked_version,
        })
    return [
        {
            **item,
            "version_audit": _build_storyboard_prompt_version_audit(item.get("meta_info", {})),
        }
        for item in version_payloads
    ]


def _create_storyboard_prompt_rollback(s, shot, target, req: StoryboardPromptRollbackRequest) -> dict:
    from models import StoryboardPromptVersion

    shot_meta = safe_json_loads(shot.meta_info) if shot.meta_info else {}
    if not isinstance(shot_meta, dict):
        shot_meta = {}
    prompt_compiler_meta = shot_meta.get("prompt_compiler", {}) if isinstance(shot_meta.get("prompt_compiler", {}), dict) else {}

    latest = s.query(StoryboardPromptVersion).filter(
        StoryboardPromptVersion.book_id == shot.book_id,
        StoryboardPromptVersion.episode == shot.episode,
        StoryboardPromptVersion.shot_id == shot.shot_id,
    ).order_by(StoryboardPromptVersion.version.desc()).first()
    next_version = (latest.version if latest else 0) + 1

    target_meta = safe_json_loads(target.meta_info) if target.meta_info else {}
    if not isinstance(target_meta, dict):
        target_meta = {}

    rollback_reason = str(req.reason or "").strip() or "manual-rollback"
    rollback_row = StoryboardPromptVersion(
        book_id=shot.book_id,
        episode=shot.episode,
        shot_id=shot.shot_id,
        version=next_version,
        compile_reason=f"rollback:v{target.version}:{rollback_reason}",
        prompt_static=target.prompt_static,
        prompt_motion=target.prompt_motion,
        negative_prompt=target.negative_prompt,
        meta_info=json.dumps(target_meta, ensure_ascii=False),
    )
    s.add(rollback_row)

    shot.visual_prompt_static = target.prompt_static
    shot.visual_prompt_motion = target.prompt_motion
    shot.visual_prompt_final = target.negative_prompt

    prompt_compiler_meta["latest_version"] = next_version
    prompt_compiler_meta["negative_prompt"] = target.negative_prompt
    prompt_compiler_meta["compile_reason"] = rollback_row.compile_reason
    prompt_compiler_meta["locked_reference_summary"] = target_meta.get("locked_reference_summary", {})
    prompt_compiler_meta["prompt_compile_context"] = target_meta.get("prompt_compile_context", {})
    prompt_compiler_meta["used_assets"] = target_meta.get("used_assets", [])
    prompt_compiler_meta["reference_images"] = target_meta.get("reference_images", [])
    prompt_compiler_meta["reference_asset_ids"] = target_meta.get("reference_asset_ids", [])
    prompt_compiler_meta["compiler_warnings"] = target_meta.get("compiler_warnings", [])
    prompt_compiler_meta["compiler_diagnostics"] = target_meta.get("compiler_diagnostics", {})
    shot_meta["prompt_compiler"] = prompt_compiler_meta
    has_target_structured = "structured_shot" in target_meta and isinstance(target_meta.get("structured_shot"), dict)
    target_structured = target_meta.get("structured_shot", {}) if has_target_structured else {}
    if has_target_structured:
        shot_meta["structured_shot"] = target_structured
    if target_structured:
        if target_structured.get("duration") is not None:
            try:
                shot.duration = int(target_structured.get("duration") or shot.duration or 3)
            except (TypeError, ValueError):
                pass
        if str(target_structured.get("camera_angle") or "").strip():
            shot.camera_angle = str(target_structured.get("camera_angle") or "").strip()
        if str(target_structured.get("camera_movement") or "").strip():
            shot.camera_movement = str(target_structured.get("camera_movement") or "").strip()
        if str(target_structured.get("transition") or "").strip():
            shot.transition = str(target_structured.get("transition") or "").strip()
    shot.meta_info = json.dumps(shot_meta, ensure_ascii=False)
    shot.updated_at = datetime.utcnow()

    s.commit()
    s.refresh(rollback_row)

    return {
        "book_id": shot.book_id,
        "episode": shot.episode,
        "shot_id": shot.shot_id,
        "version": rollback_row.version,
        "restored_from_version": target.version,
        "compile_reason": rollback_row.compile_reason,
        "prompt_static": rollback_row.prompt_static,
        "prompt_motion": rollback_row.prompt_motion,
        "negative_prompt": rollback_row.negative_prompt,
    }


def _build_prompt_compiler_diagnostics(prompt_static: str, prompt_motion: str, context: dict, used_assets: list[dict]) -> dict:
    static_text = str(prompt_static or "").strip()
    motion_text = str(prompt_motion or "").strip()
    warnings = list(context.get("warnings", [])) if isinstance(context.get("warnings", []), list) else []
    blocking_issues: list[str] = []
    checks: list[dict] = []
    combined = f"{static_text}\n{motion_text}"

    meta_prompt_tokens = ["请生成", "用于首帧", "输出应为", "你需要", "不要暴露", "必须从首帧"]
    meta_hits = [token for token in meta_prompt_tokens if token in combined]
    if meta_hits:
        blocking_issues.append("提示词残留任务指令。")
    checks.append({
        "key": "meta_prompt_leakage",
        "passed": len(meta_hits) == 0,
        "message": "未发现任务指令泄漏。" if len(meta_hits) == 0 else f"发现泄漏：{' / '.join(meta_hits)}",
    })

    english_tokens = ["Scene:", "Shot:", "Lighting:", "Camera movement:", "Action beats:", "Preserve first-frame composition"]
    english_hits = [token for token in english_tokens if token in combined]
    if english_hits:
        blocking_issues.append("提示词残留英文模板字段。")
    checks.append({
        "key": "english_template_residue",
        "passed": len(english_hits) == 0,
        "message": "未发现旧英文模板字段。" if len(english_hits) == 0 else f"发现字段：{' / '.join(english_hits)}",
    })

    screenplay_labels = {"前景", "后景", "中景", "近景", "远景", "特写", "全景", "画面", "镜头", "场景", "主体", "背景", "中部", "左侧", "右侧", "中央"}
    screenplay_label_fragments = {"前景", "后景", "中景", "近景", "远景", "特写", "全景", "画面", "镜头", "场景", "主体", "背景", "起始", "开始", "结束", "结尾", "构图", "焦点", "左侧", "右侧", "中部", "中央", "门口", "门框", "大门处", "左下角", "右下角", "左上角", "右上角"}
    dialogue_like_labels = []
    for match in re.finditer(r"([\u4e00-\u9fa5A-Za-z0-9]{2,12})：", combined):
        label = str(match.group(1) or "").strip()
        if label and label not in screenplay_labels and not any(fragment in label for fragment in screenplay_label_fragments):
            dialogue_like_labels.append(label)
    screenplay_residue_text = combined
    for neutral_dialogue_marker in ("无对白", "无台词", "没有对白", "无人物对白"):
        screenplay_residue_text = screenplay_residue_text.replace(neutral_dialogue_marker, "")
    screenplay_residue_hits: list[str] = []
    if any(token in screenplay_residue_text for token in ["[", "]", "【", "】"]):
        screenplay_residue_hits.append("方括号舞台提示")
    if any(token in screenplay_residue_text for token in ["对白", "画面切", "切到", "（大笑）", "（停顿）", "（沉默）"]):
        screenplay_residue_hits.append("对白/舞台动作描述")
    unique_dialogue_labels = list(dict.fromkeys(dialogue_like_labels))
    if len(unique_dialogue_labels) >= 1:
        screenplay_residue_hits.append(f"角色对白标签：{' / '.join(unique_dialogue_labels[:3])}")
    screenplay_residue_hits = list(dict.fromkeys([item for item in screenplay_residue_hits if item]))
    if screenplay_residue_hits:
        warnings.append("提示词残留对白稿或舞台提示写法，建议改回镜头画面提示词。")
    checks.append({
        "key": "screenplay_prompt_residue",
        "passed": len(screenplay_residue_hits) == 0,
        "message": "未发现对白稿或舞台提示残留。"
        if len(screenplay_residue_hits) == 0
        else f"发现残留：{'；'.join(screenplay_residue_hits)}",
        "details": screenplay_residue_hits,
    })

    text_encoding_ok = not (_looks_like_garbled_text(static_text) or _looks_like_garbled_text(motion_text))
    if not text_encoding_ok:
        blocking_issues.append("提示词存在乱码。")
    checks.append({
        "key": "text_encoding",
        "passed": text_encoding_ok,
        "message": "文本编码正常。" if text_encoding_ok else "检测到乱码或异常字符。",
    })

    static_scene_hits = _count_keyword_hits(static_text, ["场景", "画面", "构图", "光", "光线", "氛围", "环境", "室内", "室外", "中景", "近景", "特写", "全景", "广角"])
    static_subject_hits = _count_keyword_hits(static_text, ["角色", "人物", "主体", "站", "看", "对视", "对峙", "相对", "而立", "表情", "神情", "动作", "姿态", "门口", "屋内", "前景", "后景"])
    mentioned_asset_names = sum(
        1
        for item in (used_assets or [])
        if isinstance(item, dict) and str(item.get("asset_name") or "").strip() and str(item.get("asset_name") or "").strip() in static_text
    )
    static_quality_pass = (
        _contains_cjk(static_text)
        and len(static_text) >= 24
        and static_scene_hits >= 1
        and (static_subject_hits >= 1 or mentioned_asset_names >= 1)
        and "动作过程" not in static_text
    )
    if not static_quality_pass:
        warnings.append("静态提示词质量不达标，建议补充更明确的画面描述。")
    checks.append({
        "key": "static_prompt_quality",
        "passed": static_quality_pass,
        "message": "静态提示词看起来是自然中文画面描述。" if static_quality_pass else "静态提示词缺少中文画面描述要素。",
    })

    motion_camera_hits = _count_keyword_hits(motion_text, ["镜头", "机位", "固定机位", "推进", "推近", "拉远", "摇镜", "摇摄", "跟拍", "平移", "俯拍", "仰拍", "倾斜", "定镜", "静止", "静态", "运动"])
    motion_timeline_hits = _count_keyword_hits(motion_text, ["开始", "先", "随后", "接着", "之后", "最后", "结束", "逐渐", "缓缓", "慢慢", "从", "转向", "转为", "停在", "同时", "准备"])
    motion_continuity_hits = _count_keyword_hits(motion_text, ["一致", "保持", "延续", "首帧", "固定", "连续", "不变"])
    motion_quality_pass = (
        _contains_cjk(motion_text)
        and len(motion_text) >= 28
        and motion_camera_hits >= 1
        and motion_timeline_hits >= 1
        and motion_continuity_hits >= 1
    )
    if not motion_quality_pass:
        warnings.append("运动提示词质量不达标，建议补充更明确的镜头推进和一致性描述。")
    checks.append({
        "key": "motion_prompt_quality",
        "passed": motion_quality_pass,
        "message": "运动提示词具备镜头运动和动作推进。"
        if motion_quality_pass
        else "运动提示词缺少运动、起止或一致性约束。",
    })

    missing_reference_assets = [item.get("asset_name") for item in (context.get("bound_assets") or []) if isinstance(item, dict) and not item.get("has_reference")]
    if missing_reference_assets:
        warnings.append(f"这些绑定资产还没有参考图：{'、'.join([str(name) for name in missing_reference_assets if str(name).strip()])}。")
    checks.append({
        "key": "asset_reference_coverage",
        "passed": len(missing_reference_assets) == 0,
        "message": "绑定资产都有参考图。"
        if len(missing_reference_assets) == 0
        else f"缺少参考图：{'、'.join([str(name) for name in missing_reference_assets if str(name).strip()])}",
    })

    visual_fact_targets = context.get("visual_fact_targets", []) if isinstance(context.get("visual_fact_targets", []), list) else []
    visual_fact_target_misses: list[str] = []
    visual_fact_target_details: list[str] = []
    for item in visual_fact_targets:
        if not isinstance(item, dict):
            continue
        asset_name = str(item.get("asset_name") or "").strip()
        required_facts = [str(fact).strip() for fact in (item.get("required_facts") or []) if str(fact).strip()]
        if not asset_name or not required_facts:
            continue
        min_facts_to_include = int(item.get("min_facts_to_include") or 1)
        covered_count = 0
        missing_facts: list[str] = []
        for fact in required_facts:
            direct_hit = fact in static_text
            keyword_hits = _extract_authority_keywords(fact)
            indirect_hit = any(keyword in static_text for keyword in keyword_hits[:3] if keyword)
            if direct_hit or indirect_hit:
                covered_count += 1
            else:
                missing_facts.append(fact)
        if covered_count < min_facts_to_include:
            visual_fact_target_misses.append(asset_name)
            summarized_missing_facts = [
                summary
                for summary in (
                    _summarize_visual_fact_requirement(fact, max_keywords=2)
                    for fact in missing_facts[:2]
                )
                if summary
            ]
            visual_fact_target_details.append(
                f"{asset_name}：至少补入 {min_facts_to_include - covered_count} 条视觉事实 / {'；'.join(summarized_missing_facts or missing_facts[:1])}"
            )
    if visual_fact_target_misses:
        warnings.append(f"静态提示词对这些资产的首轮视觉事实继承不足：{'、'.join([name for name in visual_fact_target_misses if name])}。")
    checks.append({
        "key": "visual_fact_target_coverage",
        "passed": len(visual_fact_target_misses) == 0,
        "message": "静态提示词已覆盖首轮编译要求的关键视觉事实。"
        if len(visual_fact_target_misses) == 0
        else f"这些资产没有满足首轮编译要求的视觉事实覆盖：{'、'.join([name for name in visual_fact_target_misses if name])}",
        "details": visual_fact_target_details,
    })
    visual_fact_target_miss_set = set([name for name in visual_fact_target_misses if name])

    authority_inheritance_misses: list[str] = []
    authority_inheritance_details: list[str] = []
    for item in (context.get("bound_assets") or []):
        if not isinstance(item, dict):
            continue
        asset_name = str(item.get("asset_name") or "").strip()
        asset_type = str(item.get("asset_type") or "").strip()
        if asset_name and asset_name in visual_fact_target_miss_set:
            continue
        canonical_parts = item.get("canonical_prompt_parts", []) if isinstance(item.get("canonical_prompt_parts", []), list) else []
        authority_parts = canonical_parts or (
            item.get("authority_prompt_parts", []) if isinstance(item.get("authority_prompt_parts", []), list) else []
        )
        authority_keywords: list[str] = []
        for part in authority_parts:
            if not isinstance(part, dict):
                continue
            key = str(part.get("key") or "").strip()
            if asset_type == "character" and key not in {
                "core_prompt", "outfit_prompt", "refined_outfit", "hair_style", "makeup_spec", "consistency_notes",
                "canonical_identity", "canonical_temperament", "canonical_appearance", "canonical_hairstyle",
                "canonical_outfit", "canonical_accessories", "canonical_makeup_expression", "canonical_scene_effects",
                "canonical_consistency",
            }:
                continue
            if asset_type == "scene" and key not in {
                "description", "style", "lighting_mood", "color_palette",
                "canonical_description", "canonical_style", "canonical_lighting_mood", "canonical_color_palette", "canonical_core_visual",
            }:
                continue
            if asset_type == "prop" and key not in {
                "description",
                "canonical_description", "canonical_core_visual",
            }:
                continue
            authority_keywords.extend(_extract_authority_keywords(str(part.get("text") or "")))
        authority_keywords = list(dict.fromkeys([keyword for keyword in authority_keywords if keyword and keyword != asset_name]))
        matched_authority_keywords = [keyword for keyword in authority_keywords if _authority_keyword_present(keyword, static_text)]
        missing_authority_keywords = [keyword for keyword in authority_keywords if keyword not in matched_authority_keywords]
        keyword_total = len(authority_keywords)
        keyword_hits = len(matched_authority_keywords)
        if asset_type == "character":
            minimum_hits = min(5, keyword_total) if keyword_total else 0
            minimum_ratio = 0.35
        elif asset_type == "scene":
            minimum_hits = min(4, keyword_total) if keyword_total else 0
            minimum_ratio = 0.4
        elif asset_type == "prop":
            minimum_hits = min(3, keyword_total) if keyword_total else 0
            minimum_ratio = 0.35
        else:
            minimum_hits = min(3, keyword_total) if keyword_total else 0
            minimum_ratio = 0.4
        authority_passed = (
            keyword_total == 0
            or keyword_hits >= minimum_hits
            or (keyword_total > 0 and (keyword_hits / keyword_total) >= minimum_ratio)
        )
        if not authority_passed and missing_authority_keywords:
            asset_label = asset_name or f"{asset_type}:{item.get('asset_id') or ''}"
            authority_inheritance_misses.append(asset_label)
            authority_inheritance_details.append(
                f"{asset_label}：补入 {' / '.join(list(dict.fromkeys(missing_authority_keywords))[:3])}"
            )
    if authority_inheritance_misses:
        warnings.append(f"静态提示词对这些资产的权威原文继承不足：{'、'.join([name for name in authority_inheritance_misses if name])}。")
    checks.append({
        "key": "authority_prompt_inheritance",
        "passed": len(authority_inheritance_misses) == 0,
        "message": "静态提示词已继承权威原文中的关键特征。"
        if len(authority_inheritance_misses) == 0
        else f"这些资产的权威原文关键特征没有明显进入静态提示词：{'、'.join([name for name in authority_inheritance_misses if name])}",
        "details": authority_inheritance_details,
    })

    variant_state_misses: list[str] = []
    variant_state_details: list[str] = []
    for item in (context.get("bound_assets") or []):
        if not isinstance(item, dict) or str(item.get("asset_type") or "").strip() != "character":
            continue
        variant_scope = str(item.get("variant_scope") or item.get("makeup_scope") or "").strip()
        if variant_scope not in {"shot_variant", "scene_variant"}:
            continue
        state_parts = item.get("authority_prompt_parts", []) if isinstance(item.get("authority_prompt_parts", []), list) else []
        state_keywords: list[str] = []
        for part in state_parts:
            if not isinstance(part, dict):
                continue
            key = str(part.get("key") or "").strip()
            if key not in {
                "refined_outfit", "hair_style", "makeup_spec",
                "canonical_hairstyle", "canonical_outfit", "canonical_accessories",
                "canonical_makeup_expression", "canonical_scene_effects",
            }:
                continue
            state_keywords.extend(_extract_authority_keywords(str(part.get("text") or "")))
        asset_name = str(item.get("asset_name") or "").strip()
        state_keywords = list(dict.fromkeys([keyword for keyword in state_keywords if keyword and keyword != asset_name]))
        matched_state_keywords = [keyword for keyword in state_keywords if _authority_keyword_present(keyword, static_text)]
        missing_state_keywords = [keyword for keyword in state_keywords if keyword not in matched_state_keywords]
        keyword_total = len(state_keywords)
        keyword_hits = len(matched_state_keywords)
        state_passed = (
            keyword_total == 0
            or keyword_hits >= min(3, keyword_total)
            or (keyword_total > 0 and (keyword_hits / keyword_total) >= 0.3)
        )
        if not state_passed and missing_state_keywords:
            asset_label = asset_name or f"character:{item.get('asset_id') or ''}"
            variant_state_misses.append(asset_label)
            variant_state_details.append(
                f"{asset_label}：补入 {' / '.join(list(dict.fromkeys(missing_state_keywords))[:3])}"
            )
    if variant_state_misses:
        warnings.append(f"这些人物已命中精调定妆，但静态提示词没有体现当前状态：{'、'.join([name for name in variant_state_misses if name])}。")
    checks.append({
        "key": "character_variant_state",
        "passed": len(variant_state_misses) == 0,
        "message": "命中的人物精调定妆已进入静态提示词。"
        if len(variant_state_misses) == 0
        else f"这些人物的当前镜头状态没有明显进入静态提示词：{'、'.join([name for name in variant_state_misses if name])}",
        "details": variant_state_details,
    })

    scene_variant_misses: list[str] = []
    scene_variant_details: list[str] = []
    for item in (context.get("bound_assets") or []):
        if not isinstance(item, dict) or str(item.get("asset_type") or "").strip() != "scene":
            continue
        variant_scope = str(item.get("variant_scope") or "").strip()
        if variant_scope != "scene_variant":
            continue
        authority_parts = item.get("authority_prompt_parts", []) if isinstance(item.get("authority_prompt_parts", []), list) else []
        variant_keywords: list[str] = []
        for part in authority_parts:
            if not isinstance(part, dict):
                continue
            key = str(part.get("key") or "").strip()
            if key not in {
                "description",
                "style",
                "lighting_mood",
                "color_palette",
                "core_visual",
                "canonical_description",
                "canonical_style",
                "canonical_lighting_mood",
                "canonical_color_palette",
                "canonical_core_visual",
            }:
                continue
            variant_keywords.extend(_extract_authority_keywords(str(part.get("text") or "")))
        asset_name = str(item.get("asset_name") or "").strip()
        variant_keywords = [keyword for keyword in variant_keywords if keyword and keyword != asset_name]
        missing_keywords = [keyword for keyword in variant_keywords if keyword not in static_text]
        if missing_keywords:
            asset_label = asset_name or f"scene:{item.get('asset_id') or ''}"
            scene_variant_misses.append(asset_label)
            scene_variant_details.append(
                f"{asset_label}：补入 {' / '.join(list(dict.fromkeys(missing_keywords))[:3])}"
            )
    if scene_variant_misses:
        warnings.append(f"这些场景变体的当前状态没有明显进入静态提示词：{'、'.join([name for name in scene_variant_misses if name])}。")
    checks.append({
        "key": "scene_variant_state",
        "passed": len(scene_variant_misses) == 0,
        "message": "命中的场景变体已进入静态提示词。"
        if len(scene_variant_misses) == 0
        else f"这些场景变体的当前状态没有明显进入静态提示词：{'、'.join([name for name in scene_variant_misses if name])}",
        "details": scene_variant_details,
    })

    prop_variant_misses: list[str] = []
    prop_variant_details: list[str] = []
    for item in (context.get("bound_assets") or []):
        if not isinstance(item, dict) or str(item.get("asset_type") or "").strip() != "prop":
            continue
        variant_scope = str(item.get("variant_scope") or "").strip()
        if variant_scope != "prop_variant":
            continue
        authority_parts = item.get("authority_prompt_parts", []) if isinstance(item.get("authority_prompt_parts", []), list) else []
        variant_keywords: list[str] = []
        for part in authority_parts:
            if not isinstance(part, dict):
                continue
            key = str(part.get("key") or "").strip()
            if key not in {
                "description",
                "category",
                "importance",
                "core_visual",
                "canonical_description",
                "canonical_category",
                "canonical_importance",
                "canonical_core_visual",
            }:
                continue
            variant_keywords.extend(_extract_authority_keywords(str(part.get("text") or "")))
        asset_name = str(item.get("asset_name") or "").strip()
        variant_keywords = [keyword for keyword in variant_keywords if keyword and keyword != asset_name]
        missing_keywords = [keyword for keyword in variant_keywords if keyword not in static_text]
        if missing_keywords:
            asset_label = asset_name or f"prop:{item.get('asset_id') or ''}"
            prop_variant_misses.append(asset_label)
            prop_variant_details.append(
                f"{asset_label}：补入 {' / '.join(list(dict.fromkeys(missing_keywords))[:3])}"
            )
    if prop_variant_misses:
        warnings.append(f"这些道具变体的当前状态没有明显进入静态提示词：{'、'.join([name for name in prop_variant_misses if name])}。")
    checks.append({
        "key": "prop_variant_state",
        "passed": len(prop_variant_misses) == 0,
        "message": "命中的道具变体已进入静态提示词。"
        if len(prop_variant_misses) == 0
        else f"这些道具变体的当前状态没有明显进入静态提示词：{'、'.join([name for name in prop_variant_misses if name])}",
        "details": prop_variant_details,
    })

    missing_locked_mentions: list[str] = []
    for item in used_assets:
        asset_name = str(item.get("asset_name") or "").strip()
        token = str(item.get("reference_token") or "").strip()
        if not asset_name:
            continue
        if item.get("locked_reference") and asset_name not in static_text and (not token or token not in static_text):
            missing_locked_mentions.append(asset_name)
    if missing_locked_mentions:
        blocking_issues.append("静态提示词未自然提及关键锁定资产。")
    checks.append({
        "key": "asset_usage",
        "passed": len(missing_locked_mentions) == 0,
        "message": "锁定资产已进入静态提示词。"
        if len(missing_locked_mentions) == 0
        else f"未提及：{'、'.join(missing_locked_mentions)}",
    })

    high_importance_prop_misses: list[str] = []
    high_importance_prop_details: list[str] = []
    for item in (context.get("bound_assets") or []):
        if not isinstance(item, dict) or str(item.get("asset_type") or "").strip() != "prop":
            continue
        profile = item.get("canonical_prompt_profile", {}) if isinstance(item.get("canonical_prompt_profile", {}), dict) else {}
        importance = str(profile.get("importance") or "").strip().lower()
        if importance != "high":
            continue
        asset_name = str(item.get("asset_name") or "").strip()
        token = str(item.get("reference_token") or "").strip()
        if asset_name and asset_name in static_text:
            continue
        if token and token in static_text:
            continue
        prop_facts = _build_high_importance_prop_presence_facts(item)
        fact_hits = [fact for fact in prop_facts if fact in static_text]
        if len(list(dict.fromkeys(fact_hits))) >= 2:
            continue
        asset_label = asset_name or f"prop:{str(item.get('asset_id') or '').strip()}"
        high_importance_prop_misses.append(asset_label)
        if prop_facts:
            high_importance_prop_details.append(
                f"{asset_label}：至少补入 {' / '.join(list(dict.fromkeys(prop_facts))[:3])}"
            )
    if high_importance_prop_misses:
        warnings.append(f"这些高重要度道具没有进入静态提示词：{'、'.join([name for name in high_importance_prop_misses if name])}。")
    checks.append({
        "key": "high_importance_prop_presence",
        "passed": len(high_importance_prop_misses) == 0,
        "message": "高重要度道具已进入静态提示词。"
        if len(high_importance_prop_misses) == 0
        else f"这些高重要度道具没有被明确提及：{'、'.join([name for name in high_importance_prop_misses if name])}",
        "details": high_importance_prop_details or [name for name in high_importance_prop_misses if name],
    })

    critical_used_asset_keys = {
        (
            str(item.get("asset_type") or "").strip(),
            str(item.get("asset_id") or "").strip(),
        )
        for item in (used_assets or [])
        if isinstance(item, dict)
    }
    critical_bound_asset_usage_misses: list[str] = []
    critical_bound_asset_usage_details: list[str] = []
    for item in (context.get("bound_assets") or []):
        if not isinstance(item, dict):
            continue
        asset_type = str(item.get("asset_type") or "").strip()
        asset_id = str(item.get("asset_id") or "").strip()
        asset_name = str(item.get("asset_name") or "").strip()
        if not asset_type or not asset_id or not bool(item.get("has_reference")):
            continue

        profile = item.get("canonical_prompt_profile", {}) if isinstance(item.get("canonical_prompt_profile", {}), dict) else {}
        importance = str(profile.get("importance") or "").strip().lower()
        requires_persisted_usage = (
            asset_type == "scene"
            or asset_type == "character"
            or (asset_type == "prop" and importance == "high")
        )
        if not requires_persisted_usage:
            continue
        if (asset_type, asset_id) in critical_used_asset_keys:
            continue

        asset_label = asset_name or f"{asset_type}:{asset_id}"
        critical_bound_asset_usage_misses.append(asset_label)
        if asset_type == "scene":
            critical_bound_asset_usage_details.append(f"{asset_label}：已绑定场景且有参考图，但本次编译未纳入 used_assets")
        elif asset_type == "character":
            critical_bound_asset_usage_details.append(f"{asset_label}：已绑定人物且有参考图，但本次编译未纳入 used_assets")
        else:
            critical_bound_asset_usage_details.append(f"{asset_label}：高重要度道具已绑定且有参考图，但本次编译未纳入 used_assets")
    if critical_bound_asset_usage_misses:
        warnings.append(
            f"这些关键绑定资产在本次编译结果中丢失：{'、'.join([name for name in critical_bound_asset_usage_misses if name])}。"
        )
    checks.append({
        "key": "critical_bound_asset_usage",
        "passed": len(critical_bound_asset_usage_misses) == 0,
        "message": "关键绑定资产仍保留在 used_assets 中。"
        if len(critical_bound_asset_usage_misses) == 0
        else f"这些关键绑定资产没有被保留在 used_assets 中：{'、'.join([name for name in critical_bound_asset_usage_misses if name])}",
        "details": critical_bound_asset_usage_details,
    })

    reference_images = (
        context.get("compiled_reference_images", [])
        if isinstance(context.get("compiled_reference_images", []), list)
        else context.get("reference_images", [])
        if isinstance(context.get("reference_images", []), list)
        else []
    )
    reference_payload_ok = all(
        str(item.get("reference_asset_id") or "").strip() and str(item.get("image_url") or "").strip()
        for item in reference_images
    )
    if reference_images and not reference_payload_ok:
        blocking_issues.append("参考图载荷不完整。")
    checks.append({
        "key": "reference_image_payload",
        "passed": reference_payload_ok,
        "message": "参考图载荷完整。"
        if reference_payload_ok
        else "存在缺少 reference_asset_id 或 image_url 的参考图条目。",
    })

    retention = context.get("retention", {}) if isinstance(context.get("retention", {}), dict) else {}
    retention_warnings: list[str] = []
    if retention:
        for field, level in retention.items():
            if level == "fully_preserved" and field in ("face", "hair", "costume"):
                field_names = {"face": "面部", "hair": "发型", "costume": "服装"}
                field_zh = field_names.get(field, field)
                if field_zh not in static_text:
                    retention_warnings.append(f"retention 要求 {field_zh} fully_preserved，但静态提示词未提及")
    if retention_warnings:
        warnings.append(f"retention 维护不足：{'；'.join(retention_warnings)}。")
    checks.append({
        "key": "retention_coverage",
        "passed": len(retention_warnings) == 0,
        "message": "retention 约束已体现在静态提示词中。"
        if len(retention_warnings) == 0
        else f"retention 维护不足：{'；'.join(retention_warnings)}",
        "details": retention_warnings,
    })

    continuity = context.get("continuity", {}) if isinstance(context.get("continuity", {}), dict) else {}
    continuity_warnings: list[str] = []
    if continuity.get("has_previous"):
        prev_end_state = str(continuity.get("previous_end_state") or "").strip()
        if prev_end_state and prev_end_state not in static_text and prev_end_state not in motion_text:
            continuity_warnings.append(f"上一镜头 end_state「{prev_end_state[:20]}」未在本镜头提示词中体现衔接")
    if continuity_warnings:
        warnings.append(f"continuity 衔接不足：{'；'.join(continuity_warnings)}。")
    checks.append({
        "key": "continuity_coverage",
        "passed": len(continuity_warnings) == 0,
        "message": "镜头间连续性已维护。"
        if len(continuity_warnings) == 0
        else f"continuity 衔接不足：{'；'.join(continuity_warnings)}",
        "details": continuity_warnings,
    })

    metrics = {
        "static_chars": len(static_text),
        "motion_chars": len(motion_text),
        "used_asset_count": len(used_assets),
        "reference_image_count": len(reference_images),
        "warning_count": len(list(dict.fromkeys(warnings))),
        "blocking_count": len(list(dict.fromkeys(blocking_issues))),
    }

    status = "pass"
    if blocking_issues:
        status = "blocked"
    elif warnings:
        status = "warning"

    return {
        "status": status,
        "warnings": list(dict.fromkeys(warnings)),
        "blocking_issues": list(dict.fromkeys(blocking_issues)),
        "checks": checks,
        "metrics": metrics,
    }


def _should_attempt_prompt_repair(diagnostics: dict) -> bool:
    if not isinstance(diagnostics, dict) or str(diagnostics.get("status") or "").strip() != "warning":
        return False
    retryable_checks = {
        "visual_fact_target_coverage",
        "authority_prompt_inheritance",
        "static_prompt_quality",
        "motion_prompt_quality",
        "screenplay_prompt_residue",
        "character_variant_state",
        "scene_variant_state",
        "prop_variant_state",
        "high_importance_prop_presence",
        "critical_bound_asset_usage",
    }
    failed_keys = {
        str(item.get("key") or "").strip()
        for item in (diagnostics.get("checks") or [])
        if isinstance(item, dict) and not bool(item.get("passed"))
    }
    return bool(failed_keys & retryable_checks)


def _apply_prompt_compiler_hard_gates(diagnostics: dict, repair_attempted: bool) -> dict:
    if not isinstance(diagnostics, dict):
        return diagnostics
    if not repair_attempted:
        return diagnostics
    hard_gate_checks = {
        "screenplay_prompt_residue": "自动修复后，提示词仍残留对白稿或舞台提示写法。",
        "character_variant_state": "自动修复后，人物精调定妆的当前状态仍未进入静态提示词。",
        "scene_variant_state": "自动修复后，场景变体的当前状态仍未进入静态提示词。",
        "prop_variant_state": "自动修复后，道具变体的当前状态仍未进入静态提示词。",
        "high_importance_prop_presence": "自动修复后，高重要度道具仍未进入静态提示词。",
        "critical_bound_asset_usage": "自动修复后，关键绑定资产仍未保留在本次编译的 used_assets 中。",
    }
    failed_hard_gates = [
        key
        for key in hard_gate_checks
        if any(
            isinstance(item, dict)
            and str(item.get("key") or "").strip() == key
            and not bool(item.get("passed"))
            for item in (diagnostics.get("checks") or [])
        )
    ]
    if not failed_hard_gates:
        return diagnostics
    blocking_issues = list(diagnostics.get("blocking_issues", [])) if isinstance(diagnostics.get("blocking_issues", []), list) else []
    blocking_issues.extend([hard_gate_checks[key] for key in failed_hard_gates])
    return {
        **diagnostics,
        "status": "blocked",
        "blocking_issues": list(dict.fromkeys([item for item in blocking_issues if str(item).strip()])),
    }


def _parse_failed_check_detail(detail: str) -> tuple[str, list[str]]:
    text = str(detail or "").strip()
    if not text:
        return "", []
    asset_name, separator, remainder = text.partition("：")
    if not separator:
        return text, []
    normalized_remainder = re.sub(r"至少补入\s*\d+\s*条视觉事实", " ", remainder)
    normalized_remainder = normalized_remainder.replace("补入", " ")
    facts = [item.strip() for item in re.split(r"[／/]", normalized_remainder) if item.strip()]
    return asset_name.strip(), facts


def _extract_compile_required_facts(bound_item: dict) -> list[str]:
    if not isinstance(bound_item, dict):
        return []
    asset_type = str(bound_item.get("asset_type") or "").strip()
    profile = bound_item.get("canonical_prompt_profile", {}) if isinstance(bound_item.get("canonical_prompt_profile", {}), dict) else {}
    if asset_type == "character":
        ordered_fields = [
            str(profile.get("identity") or "").strip(),
            str(profile.get("temperament") or "").strip(),
            str(profile.get("appearance") or "").strip(),
            str(profile.get("hairstyle") or "").strip(),
            str(profile.get("outfit") or "").strip(),
            str(profile.get("accessories") or "").strip(),
            str(profile.get("makeup_expression") or "").strip(),
            str(profile.get("scene_effects") or "").strip(),
            str(profile.get("consistency_notes") or "").strip(),
        ]
    elif asset_type == "scene":
        ordered_fields = [
            str(profile.get("description") or "").strip(),
            str(profile.get("style") or "").strip(),
            str(profile.get("lighting_mood") or "").strip(),
            str(profile.get("color_palette") or "").strip(),
            str(profile.get("core_visual") or "").strip(),
        ]
    elif asset_type == "prop":
        ordered_fields = [
            str(profile.get("description") or "").strip(),
            str(profile.get("core_visual") or "").strip(),
        ]
    else:
        ordered_fields = []
    facts: list[str] = []
    for field in ordered_fields:
        normalized = _normalize_compiler_asset_text(field)
        if normalized:
            facts.append(normalized)
    return list(dict.fromkeys([fact for fact in facts if fact]))


def _build_high_importance_prop_presence_facts(bound_item: dict) -> list[str]:
    if not isinstance(bound_item, dict):
        return []
    facts: list[str] = []
    profile = bound_item.get("canonical_prompt_profile", {}) if isinstance(bound_item.get("canonical_prompt_profile", {}), dict) else {}
    for field in [
        "description",
        "core_visual",
        "canonical_description",
        "canonical_core_visual",
        "category",
        "canonical_category",
    ]:
        facts.extend(_extract_authority_keywords(str(profile.get(field) or "").strip()))
    for part in (bound_item.get("authority_prompt_parts") or []):
        if not isinstance(part, dict):
            continue
        key = str(part.get("key") or "").strip().lower()
        if key not in {
            "description",
            "core_visual",
            "canonical_description",
            "canonical_core_visual",
            "category",
            "canonical_category",
        }:
            continue
        facts.extend(_extract_authority_keywords(str(part.get("text") or "").strip()))
    asset_name = str(bound_item.get("asset_name") or "").strip()
    return list(dict.fromkeys([fact for fact in facts if fact and fact != asset_name]))


def _summarize_visual_fact_requirement(text: str, max_keywords: int = 3) -> str:
    normalized = _normalize_compiler_asset_text(text)
    if not normalized:
        return ""
    keywords = [
        fragment.strip()
        for fragment in re.split(r"[，,。；;：:\n\r\t/（）()\[\]{}|]+", normalized)
        if fragment and fragment.strip()
    ]
    compact_keywords: list[str] = []
    for keyword in keywords:
        token = keyword.strip()
        if len(token) > 18:
            token = token[:18]
        if token and token not in compact_keywords:
            compact_keywords.append(token)
    keywords = compact_keywords or [keyword for keyword in _extract_authority_keywords(normalized) if keyword]
    if keywords:
        return " / ".join(list(dict.fromkeys(keywords))[:max_keywords])
    if len(normalized) > 48:
        return f"{normalized[:48]}..."
    return normalized


def _build_compile_visual_fact_targets(bound_assets: list[dict]) -> list[dict]:
    targets: list[dict] = []
    for item in bound_assets or []:
        if not isinstance(item, dict):
            continue
        asset_name = str(item.get("asset_name") or "").strip()
        required_facts = _extract_compile_required_facts(item)
        if not asset_name or not required_facts:
            continue
        targets.append({
            "asset_type": str(item.get("asset_type") or "").strip(),
            "asset_id": str(item.get("asset_id") or "").strip(),
            "asset_name": asset_name,
            "reference_token": str(item.get("reference_token") or "").strip() or None,
            "required_facts": required_facts[:4],
            "min_facts_to_include": (
                1
                if str(item.get("asset_type") or "").strip() == "prop"
                else 2 if len(required_facts) >= 2 else 1
            ),
            "requires_used_asset": _is_critical_bound_asset_for_usage(item),
        })
    return targets


def _build_compile_required_used_assets(bound_assets: list[dict]) -> list[dict]:
    required_assets: list[dict] = []
    for item in bound_assets or []:
        if not _is_critical_bound_asset_for_usage(item):
            continue
        required_assets.append({
            "asset_type": str(item.get("asset_type") or "").strip(),
            "asset_id": str(item.get("asset_id") or "").strip(),
            "asset_name": str(item.get("asset_name") or "").strip(),
            "reference_token": str(item.get("reference_token") or "").strip() or None,
            "reference_status": _normalize_reference_status(item.get("reference_status")),
        })
    return required_assets


def _build_compile_prompt_contract(bound_assets: list[dict]) -> dict:
    visual_fact_targets = _build_compile_visual_fact_targets(bound_assets)
    required_used_assets = _build_compile_required_used_assets(bound_assets)
    summary_lines: list[str] = []
    for target in visual_fact_targets:
        fact_preview = " / ".join(target["required_facts"][: target["min_facts_to_include"]])
        anchor = f" {target['reference_token']}" if target.get("reference_token") else ""
        summary_lines.append(
            f"{target['asset_name']}（{target['asset_type']}）{anchor}：静态提示词至少吸收 {target['min_facts_to_include']} 个视觉事实：{fact_preview}"
        )
    return {
        "visual_fact_targets": visual_fact_targets,
        "required_used_assets": required_used_assets,
        "summary_lines": summary_lines,
    }


def _build_repair_visual_fact_targets(diagnostics: dict) -> list[dict]:
    targets: list[dict] = []
    for item in (diagnostics.get("checks") or []):
        if not isinstance(item, dict) or bool(item.get("passed")):
            continue
        check_key = str(item.get("key") or "").strip()
        if check_key not in {"authority_prompt_inheritance", "character_variant_state", "scene_variant_state", "prop_variant_state", "high_importance_prop_presence", "visual_fact_target_coverage"}:
            continue
        for detail in (item.get("details") or []):
            asset_name, facts = _parse_failed_check_detail(str(detail))
            if not asset_name:
                continue
            deduped_facts = list(dict.fromkeys([fact for fact in facts if fact]))
            targets.append({
                "check_key": check_key,
                "asset_name": asset_name,
                "required_facts": deduped_facts,
                "min_facts_to_include": 2 if len(deduped_facts) >= 2 else len(deduped_facts),
            })
    return targets


def _build_repair_required_used_assets(context: dict, diagnostics: dict) -> list[dict]:
    failed_keys = {
        str(item.get("key") or "").strip()
        for item in (diagnostics.get("checks") or [])
        if isinstance(item, dict) and not bool(item.get("passed"))
    }
    if "critical_bound_asset_usage" not in failed_keys:
        return []
    required_assets: list[dict] = []
    for item in (context.get("bound_assets") or []):
        if not _is_critical_bound_asset_for_usage(item):
            continue
        required_assets.append({
            "asset_type": str(item.get("asset_type") or "").strip(),
            "asset_id": str(item.get("asset_id") or "").strip(),
            "asset_name": str(item.get("asset_name") or "").strip(),
            "reference_token": str(item.get("reference_token") or "").strip() or None,
            "reference_status": _normalize_reference_status(item.get("reference_status")),
        })
    return required_assets


def _build_repair_priority_fixes(diagnostics: dict) -> list[dict]:
    failed_checks = {
        str(item.get("key") or "").strip(): item
        for item in (diagnostics.get("checks") or [])
        if isinstance(item, dict) and not bool(item.get("passed")) and str(item.get("key") or "").strip()
    }
    ordered_keys = [
        "screenplay_prompt_residue",
        "visual_fact_target_coverage",
        "authority_prompt_inheritance",
        "character_variant_state",
        "scene_variant_state",
        "prop_variant_state",
        "high_importance_prop_presence",
        "critical_bound_asset_usage",
        "motion_prompt_quality",
        "static_prompt_quality",
    ]
    instructions = {
        "screenplay_prompt_residue": "把提示词整体改写成纯画面描述，彻底删除对白、角色台词标签、方括号舞台提示和剪辑口令。",
        "visual_fact_target_coverage": "优先把缺失的视觉事实自然吸收到静态提示词，不要只提资产名。",
        "authority_prompt_inheritance": "优先继承权威资产原文中的关键外观、材质、空间和状态事实。",
        "character_variant_state": "人物必须继承当前镜头命中的角色变体，而不是回退到泛化基础人设。",
        "scene_variant_state": "场景必须继承当前状态版本的时段、结构、材质和氛围。",
        "prop_variant_state": "道具必须继承当前状态版本的形制、磨损、材质和功能状态。",
        "high_importance_prop_presence": "高重要度道具必须在静态提示词里被明确提及并带出关键外观细节。",
        "critical_bound_asset_usage": "所有关键绑定资产必须进入 used_assets，不能漏掉。",
        "motion_prompt_quality": "运动提示词只写镜头运动、人物动作、节奏和情绪推进，不要回退成剧本说明。",
        "static_prompt_quality": "静态提示词要落到首帧画面本身，明确主体、空间、服装、道具和光色。",
    }
    priority_fixes: list[dict] = []
    for key in ordered_keys:
        failed = failed_checks.get(key)
        if not failed:
            continue
        details = [str(detail).strip() for detail in (failed.get("details") or []) if str(detail).strip()]
        priority_fixes.append({
            "key": key,
            "instruction": instructions.get(key, str(failed.get("message") or "").strip()),
            "details": details[:3],
        })
    return priority_fixes


def _build_repair_screenplay_residue_details(diagnostics: dict) -> list[str]:
    for item in (diagnostics.get("checks") or []):
        if not isinstance(item, dict):
            continue
        if str(item.get("key") or "").strip() != "screenplay_prompt_residue":
            continue
        return [str(detail).strip() for detail in (item.get("details") or []) if str(detail).strip()]
    return []


def _build_prompt_repair_context(context: dict, candidate_output: dict, diagnostics: dict, attempt: int) -> dict:
    screenplay_residue_details = _build_repair_screenplay_residue_details(diagnostics)
    return {
        **(context if isinstance(context, dict) else {}),
        "repair_request": {
            "attempt": attempt,
            "goal": "请修复上一版候选提示词中的继承不足或画面描述不足问题，输出更稳定的最终版本。",
            "failed_checks": [
                {
                    "key": str(item.get("key") or "").strip(),
                    "message": str(item.get("message") or "").strip(),
                    "details": [str(detail).strip() for detail in (item.get("details") or []) if str(detail).strip()],
                }
                for item in (diagnostics.get("checks") or [])
                if isinstance(item, dict) and not bool(item.get("passed"))
            ],
            "warnings": [str(item).strip() for item in (diagnostics.get("warnings") or []) if str(item).strip()],
            "visual_fact_targets": _build_repair_visual_fact_targets(diagnostics),
            "required_used_assets": _build_repair_required_used_assets(context, diagnostics),
            "priority_fixes": _build_repair_priority_fixes(diagnostics),
            "screenplay_residue_details": screenplay_residue_details,
            "rewrite_constraints": {
                "static_prompt": [
                    "只保留首帧可见画面，不写对白、不写舞台提示、不写剪辑说明。",
                    "优先补齐场景、人物、道具的缺失视觉事实，写成自然中文画面描述。",
                ],
                "motion_prompt": [
                    "只描述镜头运动、人物动作推进、节奏变化和结束落点。",
                    "保留与首帧一致的角色、服装、场景、道具连续性，不要重复对白稿。",
                ],
                "forbidden_patterns": [
                    "角色名：对白",
                    "[舞台提示] / 【舞台提示】",
                    "画面切 / 切到 / 对白 / 台词 / 旁白",
                ],
                "full_rewrite_required": bool(screenplay_residue_details),
            },
            "previous_candidate": {
                "visual_prompt_static": str(candidate_output.get("visual_prompt_static") or "").strip(),
                "visual_prompt_motion": str(candidate_output.get("visual_prompt_motion") or "").strip(),
                "negative_prompt": str(candidate_output.get("negative_prompt") or "").strip(),
                "used_assets": candidate_output.get("used_assets", []) if isinstance(candidate_output.get("used_assets", []), list) else [],
            },
        },
    }


def _call_storyboard_prompt_compiler(context: dict) -> object:
    if os.environ.get("E2E_STORYBOARD_PROMPT_MOCK") == "1":
        scene_name = str(context.get("scene_name") or "当前场景").strip()
        bound_assets = [item for item in context.get("bound_assets", []) if isinstance(item, dict)]
        adapter = context.get("model_adapter", {}) if isinstance(context.get("model_adapter"), dict) else {}
        static_prompt = str(adapter.get("static_prompt") or "").strip()
        motion_prompt = str(adapter.get("motion_prompt") or "").strip()
        negative_prompt = str(adapter.get("negative_prompt") or "").strip()
        return {
            "visual_prompt_static": static_prompt or (
                f"{scene_name}中景构图，画面清晰保留当前场景、人物与关键道具。"
                "空间光线、人物站位、关键道具和环境氛围都以绑定资产为准，前景动作与背景层次分明。"
            ),
            "visual_prompt_motion": motion_prompt or (
                f"镜头保持{scene_name}的空间连续性，按照结构化动作节拍推进，最后停在关键反应瞬间。"
                "场景、服装、道具、光线和构图在动作推进中保持连续。"
            ),
            "negative_prompt": negative_prompt or "低质量，字幕，水印，logo，多余手指，变形肢体，错误场景，错误服装",
            "used_assets": [
                {
                    "asset_type": item.get("asset_type"),
                    "asset_id": item.get("asset_id"),
                    "asset_name": item.get("asset_name"),
                    "reference_token": item.get("reference_token"),
                    "reference_status": item.get("reference_status"),
                }
                for item in bound_assets
            ],
            "warnings": ["E2E storyboard prompt mock uses deterministic Model Adapter baseline"],
        }

    prompt_payload = load_prompt(
        "storyboard/prompt_compiler",
        context_json=json.dumps(context, ensure_ascii=False, indent=2),
    )
    system_prompt = (
        "You are a storyboard prompt compiler for short drama production. "
        "Return only usable Chinese JSON prompt fields based on the provided structured context. "
        "Do not output task instructions, markdown, explanations, or extra fields."
    )
    return llm_client.call_llm_json(
        prompt_payload,
        system=system_prompt,
        estimated_tokens=5000,
    )


def _compile_storyboard_prompts(book_id: int, shot, structure: dict) -> dict:
    acceptance_feedback = _collect_acceptance_constraints(book_id, shot.episode, shot.shot_id)
    feedback_constraints = acceptance_feedback.get("constraints", []) if isinstance(acceptance_feedback.get("constraints", []), list) else []
    asset_link_summary = _build_storyboard_reference_summary(_load_asset_links(shot.asset_links), str(shot.scene_name or "").strip())
    compile_context = _build_prompt_compile_context_v2(book_id, shot, structure, acceptance_feedback, asset_link_summary)
    reference_summary = _build_storyboard_reference_summary_from_bound_assets(
        compile_context.get("bound_assets", []),
        str(compile_context.get("scene_name") or shot.scene_name or "").strip(),
    )
    compile_context["reference_summary"] = reference_summary

    from core.model_adapter import adapt_ir_to_model
    from core.prompt_ir import build_shot_ir_from_context, serialize_shot_ir
    from core.rule_compiler import compile_rules
    shot_ir = build_shot_ir_from_context(compile_context)
    production_skill_runtime = compile_context.get("production_skill", {})
    shot_ir = compile_rules(shot_ir, production_skill_runtime)
    shot_ir_payload = serialize_shot_ir(shot_ir)
    target_model = str(
        compile_context.get("target_model")
        or compile_context.get("model")
        or compile_context.get("default_model")
        or "jimeng"
    ).strip() or "jimeng"
    adapter_output = adapt_ir_to_model(shot_ir, target_model)
    compile_context = {
        **compile_context,
        "duration": shot_ir.duration,
        "camera_angle": shot_ir.camera_angle,
        "camera_movement": shot_ir.camera_movement,
        "camera_speed": shot_ir.camera_speed,
        "transition": shot_ir.transition,
        "shot_purpose": shot_ir.shot_purpose,
        "emotion_arc": shot_ir_payload.get("emotion_arc", {}),
        "shot_ir": shot_ir_payload,
        "model_adapter": {
            "target_model": target_model,
            "adapter": adapter_output.get("adapter", ""),
            "static_prompt": adapter_output.get("static_prompt", ""),
            "motion_prompt": adapter_output.get("motion_prompt", ""),
            "negative_prompt": adapter_output.get("negative_prompt", ""),
        },
    }
    compile_context["shot_ir_metadata"] = {
        "static_sections": shot_ir.static_sections,
        "motion_sections": shot_ir.motion_sections,
        "forbidden_patterns_applied": shot_ir.metadata.get("forbidden_patterns_applied", []),
        "required_elements": shot_ir.metadata.get("required_elements", []),
    }

    negative_parts = [
        "low quality",
        "deformed anatomy",
        "extra fingers",
        "broken hands",
        "subtitles",
        "watermark",
        "logo",
        *(_collect_visual_negative_prompts(book_id, structure)),
        *feedback_constraints,
    ]
    fallback_negative_prompt = ", ".join([part.strip() for part in negative_parts if str(part).strip()])

    llm_output = _call_storyboard_prompt_compiler(compile_context)
    if not isinstance(llm_output, dict):
        raise HTTPException(status_code=422, detail={
            "message": "LLM compile result is not a JSON object.",
            "compiler_diagnostics": {
                "status": "blocked",
                "warnings": [],
                "blocking_issues": ["LLM compile result is not a JSON object."],
                "checks": [{"key": "llm_json", "passed": False, "message": "Return value is not a JSON object."}],
                "metrics": {},
            },
            "candidate_output": llm_output,
        })

    adapter_static_prompt = str(adapter_output.get("static_prompt") or "").strip()
    adapter_motion_prompt = str(adapter_output.get("motion_prompt") or "").strip()
    adapter_negative_prompt = str(adapter_output.get("negative_prompt") or "").strip()
    prompt_static_raw = sanitize_machine_prompt_text(llm_output.get("visual_prompt_static"))
    prompt_motion_raw = sanitize_machine_prompt_text(llm_output.get("visual_prompt_motion"))
    llm_negative_prompt = sanitize_machine_prompt_text(llm_output.get("negative_prompt"))
    adapter_fallback_fields: list[str] = []
    scene_name_for_prompt = str(compile_context.get("scene_name") or shot.scene_name or "").strip()
    prompt_static = _ensure_prompt_preserves_scene_name(prompt_static_raw or adapter_static_prompt, scene_name_for_prompt)
    prompt_motion = prompt_motion_raw or adapter_motion_prompt
    if not prompt_static_raw and adapter_static_prompt:
        adapter_fallback_fields.append("visual_prompt_static")
    if not prompt_motion_raw and adapter_motion_prompt:
        adapter_fallback_fields.append("visual_prompt_motion")
    if not llm_negative_prompt and adapter_negative_prompt:
        adapter_fallback_fields.append("negative_prompt")
    negative_prompt_parts = [llm_negative_prompt] if llm_negative_prompt else [fallback_negative_prompt]
    if not llm_negative_prompt and adapter_negative_prompt:
        negative_prompt_parts.insert(0, adapter_negative_prompt)
    negative_prompt_parts.extend([item for item in feedback_constraints if item and item not in llm_negative_prompt])
    negative_prompt = ", ".join([item.strip() for item in negative_prompt_parts if str(item).strip()])
    raw_used_assets = llm_output.get("used_assets", []) if isinstance(llm_output.get("used_assets", []), list) else []
    llm_warnings = [str(item).strip() for item in (llm_output.get("warnings") or []) if str(item).strip()]
    if adapter_fallback_fields:
        llm_warnings.append(
            "Model Adapter 已接管这些缺失的 LLM 编译字段："
            + "、".join(adapter_fallback_fields)
        )
    used_assets, missing_locked_assets, overflow_assets = _normalize_compiler_used_assets(raw_used_assets, compile_context)
    used_assets = _supplement_used_assets_from_prompt_mentions(
        used_assets,
        compile_context,
        prompt_static,
        prompt_motion,
    )
    compile_context = {
        **compile_context,
        "warnings": list(dict.fromkeys([*(compile_context.get("warnings", []) if isinstance(compile_context.get("warnings", []), list) else []), *llm_warnings])),
    }
    compiled_reference_asset_ids, compiled_reference_images = _build_effective_compiled_reference_payloads(
        compile_context,
        used_assets,
    )
    compile_context = {
        **compile_context,
        "compiled_reference_images": compiled_reference_images,
        "compiled_reference_asset_ids": compiled_reference_asset_ids,
    }

    diagnostics = _build_prompt_compiler_diagnostics(prompt_static, prompt_motion, compile_context, used_assets)
    repair_attempted = False
    if _should_attempt_prompt_repair(diagnostics):
        repair_attempted = True
        repair_context = _build_prompt_repair_context(
            compile_context,
            {
                "visual_prompt_static": prompt_static,
                "visual_prompt_motion": prompt_motion,
                "negative_prompt": negative_prompt,
                "used_assets": used_assets,
            },
            diagnostics,
            1,
        )
        repaired_output = _call_storyboard_prompt_compiler(repair_context)
        if isinstance(repaired_output, dict):
            repaired_static_raw = sanitize_machine_prompt_text(repaired_output.get("visual_prompt_static"))
            repaired_motion_raw = sanitize_machine_prompt_text(repaired_output.get("visual_prompt_motion"))
            repaired_negative_raw = sanitize_machine_prompt_text(repaired_output.get("negative_prompt"))
            repaired_fallback_fields: list[str] = []
            repaired_static = _ensure_prompt_preserves_scene_name(repaired_static_raw or adapter_static_prompt, scene_name_for_prompt)
            repaired_motion = repaired_motion_raw or adapter_motion_prompt
            if not repaired_static_raw and adapter_static_prompt:
                repaired_fallback_fields.append("visual_prompt_static")
            if not repaired_motion_raw and adapter_motion_prompt:
                repaired_fallback_fields.append("visual_prompt_motion")
            if not repaired_negative_raw and adapter_negative_prompt:
                repaired_fallback_fields.append("negative_prompt")
            repaired_negative_parts = [repaired_negative_raw] if repaired_negative_raw else [fallback_negative_prompt]
            if not repaired_negative_raw and adapter_negative_prompt:
                repaired_negative_parts.insert(0, adapter_negative_prompt)
            repaired_negative_parts.extend([item for item in feedback_constraints if item and item not in repaired_negative_raw])
            repaired_negative = ", ".join([item.strip() for item in repaired_negative_parts if str(item).strip()])
            repaired_raw_used_assets = repaired_output.get("used_assets", []) if isinstance(repaired_output.get("used_assets", []), list) else []
            repaired_llm_warnings = [str(item).strip() for item in (repaired_output.get("warnings") or []) if str(item).strip()]
            if repaired_fallback_fields:
                repaired_llm_warnings.append(
                    "Model Adapter 已接管这些缺失的 LLM 修复字段："
                    + "、".join(repaired_fallback_fields)
                )
            repaired_used_assets, repaired_missing_locked_assets, repaired_overflow_assets = _normalize_compiler_used_assets(
                repaired_raw_used_assets, compile_context
            )
            repaired_used_assets = _supplement_used_assets_from_prompt_mentions(
                repaired_used_assets,
                compile_context,
                repaired_static,
                repaired_motion,
            )
            repaired_context = {
                **compile_context,
                "warnings": list(dict.fromkeys([
                    *(compile_context.get("warnings", []) if isinstance(compile_context.get("warnings", []), list) else []),
                    *repaired_llm_warnings,
                ])),
            }
            repaired_compiled_reference_asset_ids, repaired_compiled_reference_images = _build_effective_compiled_reference_payloads(
                repaired_context,
                repaired_used_assets,
            )
            repaired_context = {
                **repaired_context,
                "compiled_reference_images": repaired_compiled_reference_images,
                "compiled_reference_asset_ids": repaired_compiled_reference_asset_ids,
            }
            repaired_diagnostics = _build_prompt_compiler_diagnostics(
                repaired_static,
                repaired_motion,
                repaired_context,
                repaired_used_assets,
            )
            if repaired_missing_locked_assets:
                repaired_diagnostics["blocking_issues"] = list(
                    dict.fromkeys([*repaired_diagnostics.get("blocking_issues", []), f"LLM 没有使用这些已锁定资产：{'、'.join(repaired_missing_locked_assets)}"])
                )
                repaired_diagnostics["status"] = "blocked"
            if repaired_overflow_assets:
                repaired_diagnostics["blocking_issues"] = list(
                    dict.fromkeys([*repaired_diagnostics.get("blocking_issues", []), f"LLM 输出了未绑定资产：{'、'.join(repaired_overflow_assets)}"])
                )
                repaired_diagnostics["status"] = "blocked"

            status_order = {"pass": 3, "warning": 2, "blocked": 1}
            if status_order.get(str(repaired_diagnostics.get("status") or ""), 0) >= status_order.get(str(diagnostics.get("status") or ""), 0):
                prompt_static = repaired_static
                prompt_motion = repaired_motion
                negative_prompt = repaired_negative
                used_assets = repaired_used_assets
                diagnostics = repaired_diagnostics
                compile_context = repaired_context
                missing_locked_assets = repaired_missing_locked_assets
                overflow_assets = repaired_overflow_assets
                llm_output = repaired_output
    if missing_locked_assets:
        diagnostics["blocking_issues"] = list(
            dict.fromkeys([*diagnostics.get("blocking_issues", []), f"LLM 没有使用这些已锁定资产：{'、'.join(missing_locked_assets)}"])
        )
        diagnostics["status"] = "blocked"
    if overflow_assets:
        diagnostics["blocking_issues"] = list(
            dict.fromkeys([*diagnostics.get("blocking_issues", []), f"LLM 输出了未绑定资产：{'、'.join(overflow_assets)}"])
        )
        diagnostics["status"] = "blocked"
    diagnostics = _apply_prompt_compiler_hard_gates(diagnostics, repair_attempted)

    if diagnostics["status"] == "blocked":
        raise HTTPException(status_code=422, detail={
            "message": "Prompt compile was blocked by diagnostics and did not overwrite the previous version.",
            "compiler_diagnostics": diagnostics,
            "repair_attempted": repair_attempted,
            "candidate_output": {
                "visual_prompt_static": prompt_static,
                "visual_prompt_motion": prompt_motion,
                "negative_prompt": negative_prompt,
                "used_assets": used_assets,
            },
            "candidate_raw_response": json.dumps(llm_output, ensure_ascii=False),
        })

    return {
        "prompt_static": prompt_static,
        "prompt_motion": prompt_motion,
        "negative_prompt": negative_prompt,
        "acceptance_feedback": acceptance_feedback,
        "locked_reference_summary": reference_summary,
        "prompt_compile_context": compile_context,
        "used_assets": used_assets,
        "compiler_warnings": diagnostics.get("warnings", []),
        "compiler_diagnostics": diagnostics,
        "reference_images": compile_context.get("compiled_reference_images", []),
        "reference_asset_ids": compile_context.get("compiled_reference_asset_ids", []),
        "repair_attempted": repair_attempted,
        "shot_ir_metadata": compile_context.get("shot_ir_metadata", {}),
        "shot_ir": compile_context.get("shot_ir", {}),
    }


def _persist_storyboard_prompt_compile(s, book_id: int, episode: int, shot, compile_reason: str) -> dict:
    from models import StoryboardPromptVersion

    meta_info = safe_json_loads(shot.meta_info) if shot.meta_info else {}
    if not isinstance(meta_info, dict):
        meta_info = {}
    previous_compiler = meta_info.get("prompt_compiler", {}) if isinstance(meta_info.get("prompt_compiler", {}), dict) else {}
    structured_seed = {
        "shot_id": shot.shot_id,
        "scene_name": shot.scene_name,
        "makeup_prompts": _load_episode_makeup_prompt_stub(book_id, episode),
        "action_process": shot.action_process,
        "dialogue": shot.dialogue,
        "start_state": shot.start_state,
        "end_state": shot.end_state,
        "duration": shot.duration,
        "camera_angle": shot.camera_angle,
        "camera_movement": shot.camera_movement,
        "transition": shot.transition,
    }
    structured = _auto_bind_structured_shot_assets(
        book_id,
        episode,
        _derive_structured_shot_payload(meta_info, structured_seed),
        structured_seed,
    )
    compiled = _compile_storyboard_prompts(book_id, shot, structured)
    compiled_structured = _apply_compiled_shot_ir_to_structure(structured, compiled.get("shot_ir", {}))
    latest = s.query(StoryboardPromptVersion).filter(
        StoryboardPromptVersion.book_id == book_id,
        StoryboardPromptVersion.episode == episode,
        StoryboardPromptVersion.shot_id == shot.shot_id,
    ).order_by(StoryboardPromptVersion.version.desc()).first()
    next_version = (latest.version if latest else 0) + 1

    version_meta = {
        "structured_shot": compiled_structured,
        "shot_ir": compiled.get("shot_ir", {}),
        "locked_reference_summary": compiled.get("locked_reference_summary", {}),
        "prompt_compile_context": compiled.get("prompt_compile_context", {}),
        "used_assets": compiled.get("used_assets", []),
        "reference_images": compiled.get("reference_images", []),
        "reference_asset_ids": compiled.get("reference_asset_ids", []),
        "compiler_warnings": compiled.get("compiler_warnings", []),
        "compiler_diagnostics": compiled.get("compiler_diagnostics", {}),
        "repair_attempted": bool(compiled.get("repair_attempted")),
    }

    row = StoryboardPromptVersion(
        book_id=book_id,
        episode=episode,
        shot_id=shot.shot_id,
        version=next_version,
        compile_reason=compile_reason,
        prompt_static=compiled["prompt_static"],
        prompt_motion=compiled["prompt_motion"],
        negative_prompt=compiled["negative_prompt"],
        meta_info=json.dumps(version_meta, ensure_ascii=False),
    )
    s.add(row)

    shot.visual_prompt_static = compiled["prompt_static"]
    shot.visual_prompt_motion = compiled["prompt_motion"]
    shot.visual_prompt_final = compiled["negative_prompt"]
    shot.duration = int(compiled_structured.get("duration") or shot.duration or 3)
    shot.camera_angle = str(compiled_structured.get("camera_angle") or shot.camera_angle or "MS")
    shot.camera_movement = str(compiled_structured.get("camera_movement") or shot.camera_movement or "static")
    shot.transition = str(compiled_structured.get("transition") or shot.transition or "cut")
    meta_info["structured_shot"] = compiled_structured
    meta_info["prompt_compiler"] = {
        "latest_version": next_version,
        "negative_prompt": compiled["negative_prompt"],
        "compile_reason": compile_reason,
        "failure_tags": compiled.get("acceptance_feedback", {}).get("failure_tags", []),
        "feedback_notes": compiled.get("acceptance_feedback", {}).get("notes", []),
        "feedback_constraints": compiled.get("acceptance_feedback", {}).get("constraints", []),
        "locked_reference_summary": compiled.get("locked_reference_summary", {}),
        "prompt_compile_context": compiled.get("prompt_compile_context", {}),
        "shot_ir": compiled.get("shot_ir", {}),
        "used_assets": compiled.get("used_assets", []),
        "reference_images": compiled.get("reference_images", []),
        "reference_asset_ids": compiled.get("reference_asset_ids", []),
        "compiler_warnings": compiled.get("compiler_warnings", []),
        "compiler_diagnostics": compiled.get("compiler_diagnostics", {}),
        "locked": bool(previous_compiler.get("locked")),
        "locked_version": previous_compiler.get("locked_version"),
    }
    shot.meta_info = json.dumps(meta_info, ensure_ascii=False)
    shot.updated_at = datetime.utcnow()
    s.flush()

    return {
        "version": next_version,
        "row": row,
        "compiled": compiled,
        "structured": compiled_structured,
        "meta_info": meta_info,
    }


def _apply_compiled_shot_ir_to_structure(structured: dict, shot_ir: dict) -> dict:
    """Merge rule-compiled ShotIR fields back into structured shot state."""
    result = dict(structured if isinstance(structured, dict) else {})
    if not isinstance(shot_ir, dict):
        return result

    for field in ("duration", "camera_angle", "camera_movement", "transition", "shot_purpose", "camera_speed"):
        value = shot_ir.get(field)
        if value is not None and str(value).strip() != "":
            result[field] = value

    for field in ("emotion_arc", "retention"):
        value = shot_ir.get(field)
        if isinstance(value, dict) and value:
            result[field] = value

    return result


def _ensure_storyboard_prompt_compiler_state(s, shot) -> tuple[dict, dict, bool]:
    from models import StoryboardPromptVersion

    shot_meta = safe_json_loads(shot.meta_info) if shot.meta_info else {}
    if not isinstance(shot_meta, dict):
        shot_meta = {}
    prompt_compiler_meta = shot_meta.get("prompt_compiler", {}) if isinstance(shot_meta.get("prompt_compiler", {}), dict) else {}
    if prompt_compiler_meta.get("latest_version"):
        return shot_meta, prompt_compiler_meta, False

    latest = s.query(StoryboardPromptVersion).filter(
        StoryboardPromptVersion.book_id == shot.book_id,
        StoryboardPromptVersion.episode == shot.episode,
        StoryboardPromptVersion.shot_id == shot.shot_id,
    ).order_by(StoryboardPromptVersion.version.desc()).first()
    if not latest:
        return shot_meta, prompt_compiler_meta, False

    latest_meta = safe_json_loads(latest.meta_info) if latest.meta_info else {}
    if not isinstance(latest_meta, dict):
        latest_meta = {}

    shot.visual_prompt_static = latest.prompt_static or shot.visual_prompt_static
    shot.visual_prompt_motion = latest.prompt_motion or shot.visual_prompt_motion
    shot.visual_prompt_final = latest.negative_prompt or shot.visual_prompt_final
    prompt_compiler_meta = {
        "latest_version": latest.version,
        "negative_prompt": latest.negative_prompt,
        "compile_reason": latest.compile_reason,
        "failure_tags": prompt_compiler_meta.get("failure_tags", []),
        "feedback_notes": prompt_compiler_meta.get("feedback_notes", []),
        "feedback_constraints": prompt_compiler_meta.get("feedback_constraints", []),
        "locked_reference_summary": latest_meta.get("locked_reference_summary", {}),
        "prompt_compile_context": latest_meta.get("prompt_compile_context", {}),
        "used_assets": latest_meta.get("used_assets", []),
        "reference_images": latest_meta.get("reference_images", []),
        "reference_asset_ids": latest_meta.get("reference_asset_ids", []),
        "compiler_warnings": latest_meta.get("compiler_warnings", []),
        "compiler_diagnostics": latest_meta.get("compiler_diagnostics", {}),
        "locked": bool(prompt_compiler_meta.get("locked", False)),
        "locked_version": prompt_compiler_meta.get("locked_version"),
    }
    shot_meta["prompt_compiler"] = prompt_compiler_meta
    shot.meta_info = json.dumps(shot_meta, ensure_ascii=False)
    shot.updated_at = datetime.utcnow()
    s.flush()
    return shot_meta, prompt_compiler_meta, True


def _collect_adopted_reference_asset_ids(asset_links: dict) -> list[str]:
    references = asset_links.get("references", {})
    if not isinstance(references, dict):
        return []

    collected: list[str] = []

    def visit(items):
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("adopted") and item.get("id"):
                collected.append(str(item["id"]))

    visit(references.get("scene"))

    characters = references.get("characters", {})
    if isinstance(characters, dict):
        for items in characters.values():
            visit(items)

    props = references.get("props", {})
    if isinstance(props, dict):
        for items in props.values():
            visit(items)

    return collected


def _normalize_compiled_reference_payloads(
    reference_images: list | None,
    reference_asset_ids: list | None,
    asset_links: dict | None = None,
) -> tuple[list[str], list[dict]]:
    cleaned_images = []
    for item in reference_images or []:
        if not isinstance(item, dict):
            continue
        image_url = str(item.get("image_url") or "").strip()
        reference_asset_id = str(item.get("reference_asset_id") or "").strip()
        if not image_url or not reference_asset_id:
            continue
        cleaned_images.append({
            "asset_type": str(item.get("asset_type") or "").strip(),
            "asset_id": str(item.get("asset_id") or "").strip(),
            "asset_name": str(item.get("asset_name") or "").strip(),
            "reference_asset_id": reference_asset_id,
            "reference_token": str(item.get("reference_token") or "").strip(),
            "image_url": image_url,
            "reference_status": _normalize_reference_status(item.get("reference_status")),
            "role": str(item.get("role") or "").strip() or ("character" if str(item.get("asset_type") or "").strip() == "character" else "scene" if str(item.get("asset_type") or "").strip() == "scene" else "prop"),
            "weight": float(item.get("weight") or (1.2 if str(item.get("asset_type") or "").strip() == "character" else 1.0)),
        })

    if cleaned_images:
        unique_asset_ids = [item["reference_asset_id"] for item in cleaned_images]
        return list(dict.fromkeys(unique_asset_ids)), cleaned_images

    normalized_ids = [
        str(item).strip()
        for item in (reference_asset_ids or [])
        if str(item).strip()
    ]
    if normalized_ids:
        return list(dict.fromkeys(normalized_ids)), []

    fallback_asset_ids = _collect_adopted_reference_asset_ids(asset_links or {})
    return fallback_asset_ids, []


def _collect_compiled_reference_payloads(shot) -> tuple[list[str], list[dict]]:
    shot_meta = safe_json_loads(shot.meta_info) if getattr(shot, "meta_info", None) else {}
    if not isinstance(shot_meta, dict):
        shot_meta = {}
    prompt_compiler_meta = shot_meta.get("prompt_compiler", {}) if isinstance(shot_meta.get("prompt_compiler", {}), dict) else {}
    reference_images = prompt_compiler_meta.get("reference_images", []) if isinstance(prompt_compiler_meta.get("reference_images", []), list) else []
    reference_asset_ids = prompt_compiler_meta.get("reference_asset_ids", []) if isinstance(prompt_compiler_meta.get("reference_asset_ids", []), list) else []
    return _normalize_compiled_reference_payloads(
        reference_images,
        reference_asset_ids,
        _load_asset_links(getattr(shot, "asset_links", None)),
    )


def _find_adopted_shot_asset(asset_links: dict, group_key: str) -> dict | None:
    items = asset_links.get(group_key, [])
    if not isinstance(items, list):
        return None

    for item in reversed(items):
        if isinstance(item, dict) and item.get("adopted"):
            return item
    return None


def _find_shot_asset_by_id(asset_links: dict, group_key: str, asset_id: str | None) -> dict | None:
    normalized_asset_id = str(asset_id or "").strip()
    if not normalized_asset_id:
        return None

    items = asset_links.get(group_key, [])
    if not isinstance(items, list):
        return None

    for item in items:
        if isinstance(item, dict) and str(item.get("id") or "").strip() == normalized_asset_id:
            return item
    return None


def _resolve_storyboard_reference_payloads(
    shot,
    requested_reference_asset_ids: list[str] | None,
) -> tuple[list[str], list[dict]]:
    reference_asset_ids, reference_images = _collect_compiled_reference_payloads(shot)
    requested_ids = [str(item).strip() for item in (requested_reference_asset_ids or []) if str(item).strip()]
    if not requested_ids:
        return reference_asset_ids, reference_images

    requested_id_set = set(requested_ids)
    filtered_images = [
        item for item in reference_images
        if str(item.get("reference_asset_id") or "").strip() in requested_id_set
    ]
    filtered_ids = [
        str(item.get("reference_asset_id") or "").strip()
        for item in filtered_images
        if str(item.get("reference_asset_id") or "").strip()
    ]
    return list(dict.fromkeys(filtered_ids)), filtered_images


def _resolve_storyboard_video_generation_context(shot, req: StoryboardGenerationRequest) -> dict[str, Any]:
    asset_links = _load_asset_links(shot.asset_links)
    adopted_image = _find_adopted_shot_asset(asset_links, "images")
    requested_first_frame = _find_shot_asset_by_id(asset_links, "images", req.first_frame_asset_id)
    first_frame_asset = requested_first_frame or adopted_image
    if not first_frame_asset:
        raise HTTPException(status_code=400, detail="An adopted first-frame image is required before generating video.")

    first_frame_url = str(first_frame_asset.get("uri") or first_frame_asset.get("previewUrl") or "").strip()
    if not first_frame_url:
        raise HTTPException(status_code=400, detail="The selected first-frame image is missing a usable preview URL.")

    reference_asset_ids, reference_images = _resolve_storyboard_reference_payloads(shot, req.reference_asset_ids)
    return {
        "asset_links": asset_links,
        "first_frame_asset": first_frame_asset,
        "first_frame_asset_id": str(first_frame_asset.get("id") or "").strip(),
        "first_frame_url": first_frame_url,
        "reference_asset_ids": reference_asset_ids,
        "reference_images": reference_images,
    }


def _select_reference_context_asset(items: list) -> dict | None:
    if not isinstance(items, list):
        return None

    for item in reversed(items):
        if isinstance(item, dict) and str(item.get("status") or item.get("label") or "").strip() == "locked":
            return item

    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or item.get("label") or "").strip()
        if item.get("adopted") or status in {"selected", "locked"}:
            return item
    return None


def _serialize_reference_context_item(item: dict, scope: str, subject: str) -> dict:
    metadata = item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {}
    status = str(item.get("status") or item.get("label") or ("selected" if item.get("adopted") else "")).strip() or "selected"
    token = str(
        metadata.get("referenceToken")
        or item.get("reference_token")
        or item.get("referenceToken")
        or ""
    ).strip()
    resolved_subject = str(metadata.get("assetSubject") or subject or item.get("title") or "").strip()
    return {
        "id": str(item.get("id") or ""),
        "scope": scope,
        "subject": resolved_subject,
        "title": str(item.get("title") or resolved_subject or "").strip(),
        "token": token,
        "status": status,
        "locked": status == "locked",
        "adopted": bool(item.get("adopted") or status in {"selected", "locked"}),
        "image_url": str(item.get("previewUrl") or item.get("uri") or "").strip(),
    }


def _build_storyboard_reference_summary(asset_links: dict, scene_name: str | None = None) -> dict:
    references = asset_links.get("references", {}) if isinstance(asset_links, dict) else {}
    if not isinstance(references, dict):
        return {
            "scene": None,
            "characters": [],
            "props": [],
            "all": [],
            "counts": {"total": 0, "locked": 0, "selected": 0},
            "summary_text": "",
        }

    scene_item = _select_reference_context_asset(references.get("scene", []))
    scene_payload = (
        _serialize_reference_context_item(scene_item, "scene", str(scene_name or "").strip())
        if isinstance(scene_item, dict)
        else None
    )

    character_payloads: list[dict] = []
    character_bucket = references.get("characters", {})
    if isinstance(character_bucket, dict):
        for subject, items in character_bucket.items():
            selected = _select_reference_context_asset(items)
            if isinstance(selected, dict):
                character_payloads.append(_serialize_reference_context_item(selected, "character", str(subject or "").strip()))

    prop_payloads: list[dict] = []
    prop_bucket = references.get("props", {})
    if isinstance(prop_bucket, dict):
        for subject, items in prop_bucket.items():
            selected = _select_reference_context_asset(items)
            if isinstance(selected, dict):
                prop_payloads.append(_serialize_reference_context_item(selected, "prop", str(subject or "").strip()))

    all_items = [item for item in [scene_payload, *character_payloads, *prop_payloads] if isinstance(item, dict)]
    locked_count = sum(1 for item in all_items if item.get("locked"))
    selected_count = sum(1 for item in all_items if item.get("status") == "selected")

    def render_summary(item: dict) -> str:
        token = str(item.get("token") or "").strip()
        label = str(item.get("subject") or item.get("title") or "").strip() or str(item.get("scope") or "asset")
        status = "locked" if item.get("locked") else str(item.get("status") or "selected")
        return f"{label} ({token}) [{status}]" if token else f"{label} [{status}]"

    return {
        "scene": scene_payload,
        "characters": character_payloads,
        "props": prop_payloads,
        "all": all_items,
        "counts": {
            "total": len(all_items),
            "locked": locked_count,
            "selected": selected_count,
        },
        "summary_text": "; ".join(render_summary(item) for item in all_items),
    }


def _build_storyboard_reference_summary_from_bound_assets(bound_assets: list[dict], scene_name: str | None = None) -> dict:
    scene_payload = None
    character_payloads: list[dict] = []
    prop_payloads: list[dict] = []

    for item in bound_assets or []:
        if not isinstance(item, dict):
            continue
        if not item.get("has_reference"):
            continue
        scope = str(item.get("asset_type") or "").strip()
        status = str(item.get("reference_status") or "selected").strip() or "selected"
        payload = {
            "id": str(item.get("reference_asset_id") or ""),
            "scope": scope,
            "subject": str(item.get("asset_name") or scene_name or "").strip(),
            "title": str(item.get("asset_name") or scene_name or "").strip(),
            "token": str(item.get("reference_token") or "").strip(),
            "status": status,
            "locked": bool(item.get("locked_reference") or status == "locked"),
            "adopted": status in {"selected", "locked"},
            "image_url": str(item.get("image_url") or "").strip(),
        }
        if scope == "scene":
            scene_payload = payload
        elif scope == "character":
            character_payloads.append(payload)
        elif scope == "prop":
            prop_payloads.append(payload)

    all_items = [entry for entry in [scene_payload, *character_payloads, *prop_payloads] if isinstance(entry, dict)]
    locked_count = sum(1 for entry in all_items if entry.get("locked"))
    selected_count = sum(1 for entry in all_items if entry.get("status") == "selected")

    def render_summary(entry: dict) -> str:
        token = str(entry.get("token") or "").strip()
        label = str(entry.get("subject") or entry.get("title") or "").strip() or str(entry.get("scope") or "asset")
        status = "locked" if entry.get("locked") else str(entry.get("status") or "selected")
        return f"{label} ({token}) [{status}]" if token else f"{label} [{status}]"

    return {
        "scene": scene_payload,
        "characters": character_payloads,
        "props": prop_payloads,
        "all": all_items,
        "counts": {
            "total": len(all_items),
            "locked": locked_count,
            "selected": selected_count,
        },
        "summary_text": "; ".join(render_summary(entry) for entry in all_items),
    }


def _resolve_visual_asset_subject(book_id: int, asset_type: str, asset_id: str, fallback_name: str = "") -> tuple[str, int | None]:
    from models import Session, VisualLocation, VisualMakeup, VisualProp

    model_map = {
        "scene": (VisualLocation, "name", None),
        "prop": (VisualProp, "name", None),
        "character": (VisualMakeup, "character_name", "episode"),
    }
    model_info = model_map.get(asset_type)
    if model_info is None:
        return fallback_name, None

    model, subject_field, episode_field = model_info
    with Session() as s:
        row = s.query(model).filter(model.book_id == book_id, model.id == int(asset_id)).first()
        if not row:
            return fallback_name, None
        return getattr(row, subject_field, fallback_name) or fallback_name, getattr(row, episode_field) if episode_field else None


def _coerce_reference_meta_info(row) -> dict:
    raw_meta = getattr(row, "meta_info", None)
    if isinstance(raw_meta, dict):
        return raw_meta
    if not raw_meta:
        return {}
    parsed = safe_json_loads(raw_meta)
    return parsed if isinstance(parsed, dict) else {}


def _mirror_reference_asset_to_storyboard(book_id: int, row) -> None:
    if row.status not in {"selected", "locked"}:
        return

    scope = "location" if row.asset_type == "scene" else row.asset_type
    subject, episode = _resolve_visual_asset_subject(book_id, row.asset_type, row.asset_id, row.asset_name)
    if not subject:
        return

    asset_uri = row.image_url or row.local_path
    if not asset_uri:
        return

    row_meta = _coerce_reference_meta_info(row)

    asset = {
        "id": f"ref-{row.id}",
        "kind": "image",
        "title": row.asset_name or subject,
        "label": row.status,
        "uri": asset_uri,
        "previewUrl": asset_uri,
        "prompt": row.prompt,
        "model": row.model,
        "status": row.status,
        "adopted": row.status in {"selected", "locked"},
        "metadata": {
            "imageRole": "reference",
            "assetSubject": subject,
            "referenceToken": row.reference_token,
            "source": "visual-reference-assets",
            "shotId": row_meta.get("shotId"),
            "shotIds": row_meta.get("shotIds"),
        },
    }
    _save_reference_asset_to_storyboard(book_id, episode or row.episode or 1, scope, subject, asset)


def _build_reference_sync_warning(exc: Exception) -> str:
    detail = str(exc)
    if "No related shots found for reference asset" in detail:
        return "The reference image was generated and saved, but it is not bound to a shot yet. Bind it in the visual asset view first."
    return f"Reference image was saved, but shot-link synchronization failed: {detail}"


def _make_reference_row_from_payload(payload: dict):
    return type("ReferenceAssetRow", (), payload)()


def _slugify_reference_token(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", str(value or "").strip().lower()).strip("-")
    if normalized:
        return f"@{normalized}"
    return fallback


def _resolve_visual_reference_token(book_id: int, asset_type: str, asset_id: str, fallback_name: str = "") -> str:
    from models import Session, VisualLocation, VisualMakeup, VisualProp

    model_map = {
        "scene": VisualLocation,
        "prop": VisualProp,
        "character": VisualMakeup,
    }
    model = model_map.get(asset_type)
    if model is None:
        return _slugify_reference_token(fallback_name, f"@asset-{asset_id}")

    with Session() as s:
        row = s.query(model).filter(model.book_id == book_id, model.id == int(asset_id)).first()
        if row is None and asset_type == "character":
            row = _materialize_character_profile_fallback_makeup(s, book_id, asset_id)
            if row is not None:
                s.commit()
        configured = str(getattr(row, "jimeng_ref_name", "") or "").strip() if row else ""
        if configured:
            return configured
    return _slugify_reference_token(fallback_name, f"@asset-{asset_id}")


def _slugify_stage_suffix(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", str(value or "").strip().lower()).strip("-")
    return normalized or "variant"


def _build_profile_namespace_from_makeup_row(row) -> SimpleNamespace:
    meta_info = safe_json_loads(getattr(row, "meta_info", None)) if getattr(row, "meta_info", None) else {}
    if not isinstance(meta_info, dict):
        meta_info = {}
    return SimpleNamespace(
        precise_age=None,
        age_range=str(meta_info.get("age_range") or ""),
        nationality=str(meta_info.get("region") or meta_info.get("nationality") or "中国"),
        gender=str(getattr(row, "gender", "") or meta_info.get("gender") or "人物"),
        identity=str(getattr(row, "identity", "") or meta_info.get("identity") or getattr(row, "character_name", "") or "角色"),
        temperament=str(getattr(row, "temperament", "") or meta_info.get("temperament") or ""),
        facial_features=str(getattr(row, "core_prompt_zh", "") or meta_info.get("appearance") or ""),
        signature_outfit=str(getattr(row, "refined_outfit", "") or ""),
        accessories=str(getattr(row, "refined_accessories", "") or ""),
        hairstyle=str(getattr(row, "hair_style", "") or ""),
    )


def _create_or_update_character_shot_variant(
    s,
    book_id: int,
    character_asset_id: int,
    req: CharacterShotVariantCreateRequest,
):
    from agents.scene_setup import SceneSetupAgent
    from models import Book, StoryboardShot, VisualMakeup

    base_row = s.query(VisualMakeup).filter(
        VisualMakeup.book_id == book_id,
        VisualMakeup.id == character_asset_id,
    ).first()
    if base_row is None:
        base_row = _materialize_character_profile_fallback_makeup(s, book_id, character_asset_id)
    if base_row is None:
        raise HTTPException(status_code=404, detail="Character visual asset not found")

    shot_id = _coerce_storyboard_shot_id(req.shot_id)
    shot_row = s.query(StoryboardShot).filter(
        StoryboardShot.book_id == book_id,
        StoryboardShot.episode == req.episode,
        StoryboardShot.shot_id == shot_id,
    ).first()
    if shot_row is None:
        raise HTTPException(status_code=404, detail="Storyboard shot not found")

    shot_ids = [str(item).strip() for item in (req.shot_ids or [str(shot_id)]) if str(item).strip()]
    if not shot_ids:
        shot_ids = [str(shot_id)]
    stage_suffix = _slugify_stage_suffix(str(req.variant_name or shot_row.scene_name or shot_id))
    stage_name = f"shot_{shot_id}_{stage_suffix}"
    variant_name = str(req.variant_name or f"第{req.episode}集镜头{shot_id}状态").strip()

    profile = _build_profile_namespace_from_makeup_row(base_row)
    result_payload = {
        "scope": "shot_variant",
        "stage_name": stage_name,
        "variant_name": variant_name,
        "shot_ids": shot_ids,
        "core_prompt_zh": str(getattr(base_row, "core_prompt_zh", "") or ""),
        "refined_outfit": str(req.refined_outfit or getattr(base_row, "refined_outfit", "") or "").strip(),
        "refined_accessories": str(req.refined_accessories or getattr(base_row, "refined_accessories", "") or "").strip(),
        "hair_style": str(req.hair_style or getattr(base_row, "hair_style", "") or "").strip(),
        "makeup_spec": str(req.makeup_spec or getattr(base_row, "makeup_spec", "") or "").strip(),
        "expression_mood": str(req.expression_mood or getattr(base_row, "expression_mood", "") or "").strip(),
        "scene_prompt_zh": str(req.scene_prompt_zh or getattr(base_row, "scene_prompt_zh", "") or shot_row.scene_name or "").strip(),
        "age": str(getattr(profile, "age_range", "") or ""),
        "region": str(getattr(profile, "nationality", "") or "中国"),
        "gender": str(getattr(profile, "gender", "") or "人物"),
        "identity": str(getattr(profile, "identity", "") or base_row.character_name or "角色"),
        "temperament": str(getattr(profile, "temperament", "") or ""),
    }
    rendered_prompt = SceneSetupAgent(book_id)._render_makeup_prompt_from_result(
        str(base_row.character_name or "").strip() or "角色",
        req.episode,
        profile,
        result_payload,
    )

    now = datetime.utcnow()
    meta_info = safe_json_loads(getattr(base_row, "meta_info", None)) if getattr(base_row, "meta_info", None) else {}
    if not isinstance(meta_info, dict):
        meta_info = {}
    variant_meta = {
        **meta_info,
        "scope": "shot_variant",
        "base_makeup_id": int(getattr(base_row, "id", 0) or 0),
        "base_stage_name": str(getattr(base_row, "stage_name", "") or "base_identity"),
        "variant_name": variant_name,
        "shot_ids": shot_ids,
        "scene_name": str(getattr(shot_row, "scene_name", "") or ""),
        "source": "manual-shot-variant-create",
        "structured_result": result_payload,
    }

    existing = s.query(VisualMakeup).filter(
        VisualMakeup.book_id == book_id,
        VisualMakeup.episode == req.episode,
        VisualMakeup.character_name == base_row.character_name,
        VisualMakeup.stage_name == stage_name,
    ).first()
    book = s.query(Book).filter(Book.id == book_id).first()
    if existing is None:
        existing = VisualMakeup(
            book_id=book_id,
            book_title=str(getattr(book, "title", "") or ""),
            episode=req.episode,
            character_name=base_row.character_name,
            stage_name=stage_name,
            refined_outfit=result_payload["refined_outfit"],
            refined_accessories=result_payload["refined_accessories"],
            makeup_spec=result_payload["makeup_spec"],
            hair_style=result_payload["hair_style"],
            expression_mood=result_payload["expression_mood"],
            visual_prompt_zh=rendered_prompt,
            core_prompt_zh=str(getattr(base_row, "core_prompt_zh", "") or ""),
            outfit_prompt_zh=result_payload["refined_outfit"],
            scene_prompt_zh=result_payload["scene_prompt_zh"],
            consistency_notes=f"inherits:{getattr(base_row, 'id', '')}",
            meta_info=json.dumps(variant_meta, ensure_ascii=False),
            shot_ids=json.dumps(shot_ids, ensure_ascii=False),
            jimeng_ref_name=str(req.jimeng_ref_name or f"@{base_row.character_name}-{shot_id}").strip(),
            negative_prompt=str(req.negative_prompt or getattr(base_row, "negative_prompt", "") or "").strip(),
            asset_status="draft",
            created_at=now,
            updated_at=now,
        )
        s.add(existing)
    else:
        existing.refined_outfit = result_payload["refined_outfit"]
        existing.refined_accessories = result_payload["refined_accessories"]
        existing.makeup_spec = result_payload["makeup_spec"]
        existing.hair_style = result_payload["hair_style"]
        existing.expression_mood = result_payload["expression_mood"]
        existing.visual_prompt_zh = rendered_prompt
        existing.core_prompt_zh = str(getattr(base_row, "core_prompt_zh", "") or "")
        existing.outfit_prompt_zh = result_payload["refined_outfit"]
        existing.scene_prompt_zh = result_payload["scene_prompt_zh"]
        existing.consistency_notes = f"inherits:{getattr(base_row, 'id', '')}"
        existing.meta_info = json.dumps(variant_meta, ensure_ascii=False)
        existing.shot_ids = json.dumps(shot_ids, ensure_ascii=False)
        existing.jimeng_ref_name = str(req.jimeng_ref_name or existing.jimeng_ref_name or f"@{base_row.character_name}-{shot_id}").strip()
        existing.negative_prompt = str(req.negative_prompt or existing.negative_prompt or getattr(base_row, "negative_prompt", "") or "").strip()
        existing.updated_at = now

    s.flush()
    peer_rows = [
        row for row in _load_makeup_rows_or_profile_fallback(s, book_id)
        if str(getattr(row, "character_name", "") or "").strip() == str(base_row.character_name or "").strip()
    ]
    payload = _serialize_visual_asset_row(existing, "character", episode=existing.episode, peer_rows=peer_rows)
    payload["rendered_prompt_zh"] = rendered_prompt
    payload["base_makeup_id"] = int(getattr(base_row, "id", 0) or 0)
    return payload


def _create_visual_reference_asset_record(
    book_id: int,
    *,
    episode: int | None,
    asset_type: str,
    asset_id: str,
    asset_name: str,
    image_url: str | None,
    local_path: str | None,
    reference_token: str,
    status: str,
    prompt: str | None,
    model: str | None,
    notes: str | None,
    meta_info: dict | None,
) -> dict:
    from models import Session, VisualLocation, VisualMakeup, VisualProp, VisualReferenceAsset

    now = datetime.utcnow()
    meta_payload = meta_info or {}
    task_id = str(meta_payload.get("taskId") or "").strip()

    def infer_binding_shot_ids(payload: dict | None, fallback_episode: int | None) -> list[str]:
        if not isinstance(payload, dict):
            return []

        raw_shot_ids = payload.get("shotIds")
        if isinstance(raw_shot_ids, list):
            return _normalize_asset_shot_ids(raw_shot_ids)

        raw_shot_id = str(payload.get("shotId") or "").strip()
        if not raw_shot_id:
            return []

        if "-" in raw_shot_id:
            return [raw_shot_id]
        if fallback_episode and int(fallback_episode or 0) > 0:
            return [f"{int(fallback_episode)}-{raw_shot_id}"]
        return [raw_shot_id]

    def backfill_asset_shot_ids(session, normalized_asset_type: str, normalized_asset_id: str, shot_ids: list[str]) -> None:
        normalized_shot_ids = _normalize_asset_shot_ids(shot_ids)
        if not normalized_shot_ids:
            return

        model_map = {
            "scene": VisualLocation,
            "prop": VisualProp,
            "character": VisualMakeup,
        }
        model = model_map.get(normalized_asset_type)
        if model is None:
            return

        row = session.query(model).filter(
            model.book_id == book_id,
            model.id == int(normalized_asset_id),
        ).first()
        if row is None and normalized_asset_type == "character":
            row = _materialize_character_profile_fallback_makeup(session, book_id, normalized_asset_id)
        if row is None:
            return

        existing_shot_ids = _normalize_asset_shot_ids(_json_loads_list(getattr(row, "shot_ids", None)))
        merged_shot_ids = _normalize_asset_shot_ids(existing_shot_ids + normalized_shot_ids)
        if merged_shot_ids == existing_shot_ids:
            return

        row.shot_ids = json.dumps(merged_shot_ids, ensure_ascii=False)
        row.updated_at = now

    with Session() as s:
        if asset_type == "character":
            _materialize_character_profile_fallback_makeup(s, book_id, asset_id)
        existing_row = None
        if task_id:
            candidates = s.query(VisualReferenceAsset).filter(
                VisualReferenceAsset.book_id == book_id,
                VisualReferenceAsset.asset_type == asset_type,
                VisualReferenceAsset.asset_id == str(asset_id),
            ).order_by(VisualReferenceAsset.id.desc()).all()
            for candidate in candidates:
                candidate_meta = safe_json_loads(candidate.meta_info) if candidate.meta_info else {}
                if isinstance(candidate_meta, dict) and str(candidate_meta.get("taskId") or "").strip() == task_id:
                    existing_row = candidate
                    break

        if existing_row is not None:
            if image_url:
                existing_row.image_url = image_url
            if local_path:
                existing_row.local_path = local_path
            existing_row.reference_token = reference_token
            existing_row.status = status
            existing_row.prompt = prompt
            existing_row.model = model
            existing_row.notes = notes
            existing_row.meta_info = json.dumps(meta_payload, ensure_ascii=False)
            existing_row.updated_at = now
            row = existing_row
        else:
            row = VisualReferenceAsset(
                book_id=book_id,
                episode=episode,
                asset_type=asset_type,
                asset_id=str(asset_id),
                asset_name=asset_name or "",
                image_url=image_url,
                local_path=local_path,
                reference_token=reference_token,
                status=status,
                prompt=prompt,
                model=model,
                notes=notes,
                meta_info=json.dumps(meta_payload, ensure_ascii=False),
                created_at=now,
                updated_at=now,
            )
            s.add(row)
            s.flush()

        binding_shot_ids = infer_binding_shot_ids(meta_payload, episode or getattr(row, "episode", None))
        if binding_shot_ids:
            backfill_asset_shot_ids(s, asset_type, str(asset_id), binding_shot_ids)

        demoted_rows = _demote_selected_reference_siblings(s, row)
        s.commit()
        s.refresh(row)
        payload = _serialize_reference_asset_row(row)
        try:
            _sync_visual_reference_asset_to_storyboard(book_id, row)
            for demoted in demoted_rows:
                _sync_visual_reference_asset_to_storyboard(book_id, _make_reference_row_from_payload(demoted))
        except Exception as exc:
            payload["sync_warning"] = _build_reference_sync_warning(exc)
        return payload


def _demote_selected_reference_siblings(session, row) -> list[dict]:
    if row.status != "selected":
        return []

    from models import VisualReferenceAsset

    demoted_rows = session.query(VisualReferenceAsset).filter(
        VisualReferenceAsset.book_id == row.book_id,
        VisualReferenceAsset.asset_type == row.asset_type,
        VisualReferenceAsset.asset_id == row.asset_id,
        VisualReferenceAsset.id != row.id,
        VisualReferenceAsset.status == "selected",
    ).all()

    affected = []
    for sibling in demoted_rows:
        sibling.status = "candidate"
        sibling.updated_at = datetime.utcnow()
        affected.append(_serialize_reference_asset_row(sibling))
    return affected


def _normalize_reference_asset_group(session, rows) -> bool:
    active_rows = [row for row in rows if row.status in {"selected", "locked"}]
    if len(active_rows) <= 1:
        return False

    locked_rows = [row for row in active_rows if row.status == "locked"]
    winner_pool = locked_rows or active_rows
    winner = max(
        winner_pool,
        key=lambda item: item.updated_at or item.created_at or datetime.min,
    )

    changed = False
    for row in active_rows:
        if row.id == winner.id:
            continue
        row.status = "candidate"
        row.updated_at = datetime.utcnow()
        changed = True
    return changed


def _normalize_visual_reference_assets(book_id: int) -> None:
    from models import Session, VisualReferenceAsset

    affected_assets: set[tuple[str, str]] = set()
    with Session() as s:
        rows = s.query(VisualReferenceAsset).filter(
            VisualReferenceAsset.book_id == book_id,
        ).order_by(
            VisualReferenceAsset.asset_type,
            VisualReferenceAsset.asset_id,
            VisualReferenceAsset.id,
        ).all()

        grouped: dict[tuple[str, str], list] = {}
        for row in rows:
            grouped.setdefault((row.asset_type, row.asset_id), []).append(row)

        for asset_key, group_rows in grouped.items():
            if _normalize_reference_asset_group(s, group_rows):
                affected_assets.add(asset_key)

        if affected_assets:
            s.commit()

    for asset_type, asset_id in affected_assets:
        try:
            _sync_active_reference_assets_for_visual_asset(book_id, asset_type, int(asset_id))
        except Exception:
            continue


def _remove_reference_asset_from_storyboard(book_id: int, row) -> int:
    from models import Session, StoryboardShot

    def resolve_fallback_shot_ids(meta_payload: dict | None) -> list[int]:
        if not isinstance(meta_payload, dict):
            return []
        resolved: list[int] = []
        raw_shot_ids = meta_payload.get("shotIds")
        if isinstance(raw_shot_ids, list):
            for item in raw_shot_ids:
                normalized = str(item or "").strip()
                if not normalized:
                    continue
                candidate = normalized.split("-", 1)[-1] if "-" in normalized else normalized
                shot_value = _coerce_storyboard_shot_id(candidate)
                if shot_value:
                    resolved.append(shot_value)
        if resolved:
            return sorted(set(resolved))
        raw_shot_id = meta_payload.get("shotId")
        if raw_shot_id:
            shot_value = _coerce_storyboard_shot_id(raw_shot_id)
            if shot_value:
                return [shot_value]
        return []

    scope = "location" if row.asset_type == "scene" else row.asset_type
    subject, episode = _resolve_visual_asset_subject(book_id, row.asset_type, row.asset_id, row.asset_name)
    if not subject:
        return 0

    target_shot_ids = _collect_reference_target_shots(book_id, episode or row.episode or 1, scope, subject)
    row_meta = _coerce_reference_meta_info(row)
    if not target_shot_ids:
        target_shot_ids = resolve_fallback_shot_ids(row_meta)
    if not target_shot_ids:
        return 0

    reference_id = f"ref-{row.id}"
    removed_count = 0

    def matches_reference_item(item: dict) -> bool:
        if not isinstance(item, dict):
            return False
        metadata = item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {}
        source_asset_id = str(
            item.get("sourceAssetId")
            or metadata.get("sourceAssetId")
            or ""
        ).strip()
        item_id = str(item.get("id") or "").strip()
        item_scope = str(
            metadata.get("assetScope")
            or item.get("scope")
            or ""
        ).strip()
        normalized_scope = "location" if item_scope == "scene" else item_scope
        if item_id and item_id == reference_id:
            return True
        return bool(source_asset_id) and source_asset_id == str(row.asset_id) and normalized_scope == scope

    def remove_from_bucket(items: object) -> tuple[list, int]:
        if not isinstance(items, list):
            return [], 0
        next_items = []
        removed = 0
        for item in items:
            if matches_reference_item(item):
                removed += 1
                continue
            next_items.append(item)
        return next_items, removed

    with Session() as s:
        shots = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == (episode or row.episode or 1),
            StoryboardShot.shot_id.in_(target_shot_ids),
        ).all()
        for shot in shots:
            asset_links = _load_asset_links(shot.asset_links)
            references = asset_links.get("references", {})
            if not isinstance(references, dict):
                continue

            if scope == "character":
                characters = references.get("characters", {})
                if not isinstance(characters, dict):
                    continue
                changed = False
                for bucket_subject in list(characters.keys()):
                    next_items, removed = remove_from_bucket(characters.get(bucket_subject, []))
                    if not removed:
                        continue
                    removed_count += removed
                    changed = True
                    if next_items:
                        characters[bucket_subject] = next_items
                    else:
                        characters.pop(bucket_subject, None)
                if changed:
                    references["characters"] = characters
            elif scope == "prop":
                props = references.get("props", {})
                if not isinstance(props, dict):
                    continue
                changed = False
                for bucket_subject in list(props.keys()):
                    next_items, removed = remove_from_bucket(props.get(bucket_subject, []))
                    if not removed:
                        continue
                    removed_count += removed
                    changed = True
                    if next_items:
                        props[bucket_subject] = next_items
                    else:
                        props.pop(bucket_subject, None)
                if changed:
                    references["props"] = props
            else:
                next_items, removed = remove_from_bucket(references.get("scene", []))
                if removed:
                    removed_count += removed
                    references["scene"] = next_items

            asset_links["references"] = references
            shot.asset_links = json.dumps(asset_links, ensure_ascii=False)

        if removed_count:
            s.commit()

    return removed_count


def _sync_visual_reference_asset_to_storyboard(book_id: int, row) -> None:
    _remove_reference_asset_from_storyboard(book_id, row)
    if row.status in {"selected", "locked"}:
        _mirror_reference_asset_to_storyboard(book_id, row)
    _refresh_storyboard_prompt_compiler_for_reference(book_id, row)


def _refresh_storyboard_prompt_compiler_for_reference(book_id: int, row) -> int:
    from models import Session, StoryboardShot

    def resolve_fallback_shot_ids(meta_payload: dict | None) -> list[int]:
        if not isinstance(meta_payload, dict):
            return []
        resolved: list[int] = []
        raw_shot_ids = meta_payload.get("shotIds")
        if isinstance(raw_shot_ids, list):
            for item in raw_shot_ids:
                normalized = str(item or "").strip()
                if not normalized:
                    continue
                candidate = normalized.split("-", 1)[-1] if "-" in normalized else normalized
                shot_value = _coerce_storyboard_shot_id(candidate)
                if shot_value:
                    resolved.append(shot_value)
        if resolved:
            return sorted(set(resolved))
        raw_shot_id = meta_payload.get("shotId")
        if raw_shot_id:
            shot_value = _coerce_storyboard_shot_id(raw_shot_id)
            if shot_value:
                return [shot_value]
        return []

    scope = "location" if row.asset_type == "scene" else row.asset_type
    subject, episode = _resolve_visual_asset_subject(book_id, row.asset_type, row.asset_id, row.asset_name)
    if not subject:
        return 0

    target_shot_ids = _collect_reference_target_shots(book_id, episode or row.episode or 1, scope, subject)
    row_meta = _coerce_reference_meta_info(row)
    if not target_shot_ids:
        target_shot_ids = resolve_fallback_shot_ids(row_meta)
    if not target_shot_ids:
        return 0

    refreshed_count = 0
    with Session() as s:
        shots = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == (episode or row.episode or 1),
            StoryboardShot.shot_id.in_(target_shot_ids),
        ).all()
        for shot in shots:
            shot_meta = safe_json_loads(shot.meta_info) if shot.meta_info else {}
            if not isinstance(shot_meta, dict):
                shot_meta = {}
            prompt_compiler_meta = shot_meta.get("prompt_compiler", {}) if isinstance(shot_meta.get("prompt_compiler", {}), dict) else {}
            if not prompt_compiler_meta:
                continue

            structured_seed = {
                "shot_id": shot.shot_id,
                "scene_name": shot.scene_name,
                "makeup_prompts": _load_episode_makeup_prompt_stub(book_id, shot.episode),
                "action_process": shot.action_process,
                "dialogue": shot.dialogue,
                "start_state": shot.start_state,
                "end_state": shot.end_state,
                "duration": shot.duration,
                "camera_angle": shot.camera_angle,
                "camera_movement": shot.camera_movement,
                "transition": shot.transition,
            }
            structured = _auto_bind_structured_shot_assets(
                book_id,
                shot.episode,
                _derive_structured_shot_payload(shot_meta, structured_seed),
                structured_seed,
            )
            refreshed_meta = _refresh_legacy_prompt_compile_meta(
                book_id,
                shot,
                structured,
                prompt_compiler_meta,
            )
            refreshed_context = (
                refreshed_meta.get("prompt_compile_context", {})
                if isinstance(refreshed_meta.get("prompt_compile_context", {}), dict)
                else {}
            )
            refreshed_meta["locked_reference_summary"] = _build_storyboard_reference_summary_from_bound_assets(
                refreshed_context.get("bound_assets", []) if isinstance(refreshed_context.get("bound_assets", []), list) else [],
                str(structured.get("scene_name") or shot.scene_name or "").strip(),
            )

            if refreshed_meta == prompt_compiler_meta:
                continue

            shot_meta["prompt_compiler"] = refreshed_meta
            shot.meta_info = json.dumps(shot_meta, ensure_ascii=False)
            shot.updated_at = datetime.utcnow()
            refreshed_count += 1

        if refreshed_count:
            s.commit()

    return refreshed_count


def _sync_active_reference_assets_for_visual_asset(book_id: int, asset_type: str, asset_id: int) -> list[str]:
    from models import Session, VisualReferenceAsset

    warnings: list[str] = []
    with Session() as s:
        rows = s.query(VisualReferenceAsset).filter(
            VisualReferenceAsset.book_id == book_id,
            VisualReferenceAsset.asset_type == asset_type,
            VisualReferenceAsset.asset_id == str(asset_id),
        ).all()

    for row in rows:
        try:
            _sync_visual_reference_asset_to_storyboard(book_id, row)
        except Exception as exc:
            warnings.append(_build_reference_sync_warning(exc))
    return warnings


def _save_asset_to_storyboard(
    book_id: int,
    episode: int,
    shot_id: str,
    kind: str,
    asset: dict,
):
    from models import Session, StoryboardShot

    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if not shot:
            raise ValueError(f"Shot not found: book={book_id} episode={episode} shot={shot_id}")

        asset_links = _load_asset_links(shot.asset_links)
        group_key = "images" if kind == "image" else "videos" if kind == "video" else "audios"
        current_assets = asset_links.get(group_key, [])
        if not isinstance(current_assets, list):
            current_assets = []

        if asset.get("adopted"):
            for current in current_assets:
                if isinstance(current, dict):
                    current["adopted"] = False

        current_assets.append(asset)
        asset_links[group_key] = current_assets
        shot.asset_links = json.dumps(asset_links, ensure_ascii=False)
        if kind == "image":
            shot.asset_status = "asset_ready"
        elif kind == "video":
            shot.asset_status = "done"
        s.commit()


def _upsert_reference_asset(asset_links: dict, scope: str, subject: str | None, asset: dict) -> dict:
    def merge_assets(current_assets: list, next_asset: dict) -> list:
        merged = []
        replaced = False
        next_id = str(next_asset.get("id") or "")
        for current in current_assets:
            if isinstance(current, dict) and next_id and str(current.get("id") or "") == next_id:
                merged.append(next_asset)
                replaced = True
            else:
                merged.append(current)
        if not replaced:
            merged.append(next_asset)
        return merged

    references = asset_links.get("references", {})
    if not isinstance(references, dict):
        references = {}

    if scope == "character":
        characters = references.get("characters", {})
        if not isinstance(characters, dict):
            characters = {}
        current_assets = characters.get(subject or "", [])
        if not isinstance(current_assets, list):
            current_assets = []
        if asset.get("adopted"):
            for current in current_assets:
                if isinstance(current, dict):
                    current["adopted"] = False
        current_assets = merge_assets(current_assets, asset)
        characters[subject or ""] = current_assets
        references["characters"] = characters
    elif scope == "prop":
        props = references.get("props", {})
        if not isinstance(props, dict):
            props = {}
        current_assets = props.get(subject or "", [])
        if not isinstance(current_assets, list):
            current_assets = []
        if asset.get("adopted"):
            for current in current_assets:
                if isinstance(current, dict):
                    current["adopted"] = False
        current_assets = merge_assets(current_assets, asset)
        props[subject or ""] = current_assets
        references["props"] = props
    else:
        current_assets = references.get("scene", [])
        if not isinstance(current_assets, list):
            current_assets = []
        if asset.get("adopted"):
            for current in current_assets:
                if isinstance(current, dict):
                    current["adopted"] = False
        current_assets = merge_assets(current_assets, asset)
        references["scene"] = current_assets

    asset_links["references"] = references
    return asset_links


def _collect_reference_target_shots(book_id: int, episode: int, scope: str, subject: str | None) -> list[int]:
    from models import Session, StoryboardShot, VisualLocation, VisualProp, VisualMakeup

    with Session() as s:
        if scope == "location":
            shot_ids = []
            location = s.query(VisualLocation).filter(
                VisualLocation.book_id == book_id,
                VisualLocation.name == subject,
            ).first()
            if location:
                shot_ids = [_coerce_storyboard_shot_id(item) for item in _json_loads_list(location.shot_ids)]
            if shot_ids:
                return sorted(set(shot_ids))
            shots = s.query(StoryboardShot).filter(
                StoryboardShot.book_id == book_id,
                StoryboardShot.episode == episode,
                StoryboardShot.scene_name == subject,
            ).order_by(StoryboardShot.shot_id).all()
            return [int(shot.shot_id) for shot in shots]

        if scope == "prop":
            prop = s.query(VisualProp).filter(
                VisualProp.book_id == book_id,
                VisualProp.name == subject,
            ).first()
            return sorted({_coerce_storyboard_shot_id(item) for item in _json_loads_list(prop.shot_ids if prop else None)})

        makeup_rows = s.query(VisualMakeup).filter(
            VisualMakeup.book_id == book_id,
            VisualMakeup.episode == episode,
            VisualMakeup.character_name == subject,
        ).all()
        shot_ids: set[int] = set()
        for row in makeup_rows:
            for item in _json_loads_list(row.shot_ids):
                shot_ids.add(_coerce_storyboard_shot_id(item))
        if shot_ids:
            return sorted(shot_ids)

        candidate_asset_ids = {
            str(row.id).strip()
            for row in makeup_rows
            if str(getattr(row, "id", "") or "").strip()
        }
        if not candidate_asset_ids and not str(subject or "").strip():
            return []

        shots = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
        ).order_by(StoryboardShot.shot_id).all()
        for shot in shots:
            meta_info = safe_json_loads(shot.meta_info) if shot.meta_info else {}
            structured = meta_info.get("structured_shot", {}) if isinstance(meta_info, dict) else {}
            if not isinstance(structured, dict):
                continue

            structured_character_ids = {
                str(item).strip()
                for item in (structured.get("character_asset_ids") or structured.get("characterAssetIds") or [])
                if str(item).strip()
            }
            if candidate_asset_ids.intersection(structured_character_ids):
                shot_ids.add(int(shot.shot_id))
                continue

            blocking_items = _normalize_structure_list(
                structured.get("character_blocking") or structured.get("characterBlocking")
            )
            blocking_names = {
                str(item.get("character_id") or item.get("visual_alias") or "").strip()
                for item in blocking_items
                if isinstance(item, dict) and str(item.get("character_id") or item.get("visual_alias") or "").strip()
            }
            if str(subject or "").strip() in blocking_names:
                shot_ids.add(int(shot.shot_id))
                continue

            searchable_parts = [
                getattr(shot, "visual_desc", ""),
                getattr(shot, "dialogue", ""),
                getattr(shot, "action_process", ""),
                getattr(shot, "start_state", ""),
                getattr(shot, "end_state", ""),
                getattr(shot, "scene_name", ""),
            ]
            searchable_text = " ".join(str(part or "") for part in searchable_parts)
            if str(subject or "").strip() and str(subject).strip() in searchable_text:
                shot_ids.add(int(shot.shot_id))

        return sorted(shot_ids)


def _save_reference_asset_to_storyboard(
    book_id: int,
    episode: int,
    scope: str,
    subject: str | None,
    asset: dict,
):
    from models import Session, StoryboardShot

    def resolve_fallback_shot_ids(metadata: dict | None) -> list[int]:
        if not isinstance(metadata, dict):
            return []
        resolved: list[int] = []
        raw_shot_ids = metadata.get("shotIds")
        if isinstance(raw_shot_ids, list):
            for item in raw_shot_ids:
                normalized = str(item or "").strip()
                if not normalized:
                    continue
                candidate = normalized.split("-", 1)[-1] if "-" in normalized else normalized
                shot_value = _coerce_storyboard_shot_id(candidate)
                if shot_value:
                    resolved.append(shot_value)
        if resolved:
            return sorted(set(resolved))
        fallback_shot_id = _coerce_storyboard_shot_id(metadata.get("shotId", 0) or 0) if metadata.get("shotId") else None
        if fallback_shot_id:
            return [fallback_shot_id]
        return []

    target_shot_ids = _collect_reference_target_shots(book_id, episode, scope, subject)
    if not target_shot_ids:
        metadata = asset.get("metadata", {}) if isinstance(asset.get("metadata", {}), dict) else {}
        target_shot_ids = resolve_fallback_shot_ids(metadata)
    if not target_shot_ids:
        raise ValueError(f"No related shots found for reference asset: scope={scope} subject={subject}")

    with Session() as s:
        shots = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id.in_(target_shot_ids),
        ).all()
        for shot in shots:
            asset_links = _load_asset_links(shot.asset_links)
            asset_links = _upsert_reference_asset(asset_links, scope, subject, asset.copy())
            shot.asset_links = json.dumps(asset_links, ensure_ascii=False)
            if shot.asset_status in (None, "", "pending"):
                shot.asset_status = "asset_ready"
        s.commit()


def _next_asset_version(book_id: int, episode: int, shot_id: str, kind: str) -> int:
    from models import Session, StoryboardShot

    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if not shot:
            return 1
        asset_links = _load_asset_links(shot.asset_links)
        group_key = "images" if kind == "image" else "videos" if kind == "video" else "audios"
        current_assets = asset_links.get(group_key, [])
        return len(current_assets) + 1


def _next_reference_asset_version(book_id: int, episode: int, scope: str, subject: str | None) -> int:
    from models import Session, StoryboardShot

    target_shot_ids = _collect_reference_target_shots(book_id, episode, scope, subject)
    if not target_shot_ids:
        return 1

    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == target_shot_ids[0],
        ).first()
        if not shot:
            return 1

        references = _load_asset_links(shot.asset_links).get("references", {})
        if not isinstance(references, dict):
            return 1
        if scope == "character":
            values = references.get("characters", {})
            current_assets = values.get(subject or "", []) if isinstance(values, dict) else []
        elif scope == "prop":
            values = references.get("props", {})
            current_assets = values.get(subject or "", []) if isinstance(values, dict) else []
        else:
            current_assets = references.get("scene", [])
        return len(current_assets if isinstance(current_assets, list) else []) + 1


def _adopt_asset_version(
    book_id: int,
    episode: int,
    shot_id: str,
    kind: str,
    asset_id: str,
):
    from models import Session, StoryboardShot

    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if not shot:
            raise ValueError(f"Shot not found: book={book_id} episode={episode} shot={shot_id}")

        asset_links = _load_asset_links(shot.asset_links)
        group_key = "images" if kind == "image" else "videos" if kind == "video" else "audios"
        current_assets = asset_links.get(group_key, [])
        if not isinstance(current_assets, list):
            current_assets = []

        found = False
        for current in current_assets:
            if not isinstance(current, dict):
                continue
            current["adopted"] = str(current.get("id")) == asset_id
            found = found or current["adopted"]

        if not found:
            raise ValueError(f"Asset not found: {asset_id}")

        asset_links[group_key] = current_assets
        shot.asset_links = json.dumps(asset_links, ensure_ascii=False)
        s.commit()


def _resolve_creative_profile(req: CreativeGenerationRequest, capability: str) -> dict:
    profile = resolve_generation_profile(capability, req.model_profile_id)
    if req.model and not profile.get("model_name"):
        profile = {**profile, "model_name": req.model}
    return profile


def _store_creative_task_request(task_state: dict, req: CreativeGenerationRequest, kind: str) -> None:
    task_state["kind"] = kind
    task_state["request_payload"] = req.model_dump(mode="json", by_alias=False)
    task_state["prompt_encoding_audit"] = _build_provider_prompt_encoding_audit(req.prompt)
    _stamp_creative_task_state(task_state)


def _build_provider_prompt_encoding_audit(
    original_prompt: str | None,
    provider_request_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    original = str(original_prompt or "")
    submitted_prompt = ""
    if isinstance(provider_request_payload, dict):
        input_payload = provider_request_payload.get("input")
        if isinstance(input_payload, dict):
            submitted_prompt = str(input_payload.get("prompt") or "")

    def _question_mark_count(text: str) -> int:
        return text.count("?")

    submitted_effective = submitted_prompt if submitted_prompt else original
    return {
        "original_prompt": original,
        "original_contains_cjk": _contains_cjk(original),
        "original_looks_garbled": _looks_like_garbled_text(original),
        "original_question_mark_count": _question_mark_count(original),
        "submitted_prompt": submitted_prompt,
        "submitted_contains_cjk": _contains_cjk(submitted_effective),
        "submitted_looks_garbled": _looks_like_garbled_text(submitted_effective),
        "submitted_question_mark_count": _question_mark_count(submitted_effective),
        "provider_payload_captured": isinstance(provider_request_payload, dict) and bool(provider_request_payload),
    }


def _apply_provider_submission_snapshot(
    task_state: dict[str, Any],
    asset: dict[str, Any] | None,
    req: CreativeGenerationRequest,
    generated: dict[str, Any] | None = None,
    exc: ModelProfileError | None = None,
) -> None:
    provider_request_payload: dict[str, Any] | None = None
    if isinstance(generated, dict):
        raw_payload = generated.get("providerRequestPayload")
        if isinstance(raw_payload, dict):
            provider_request_payload = raw_payload
    if provider_request_payload is None and isinstance(exc, ModelProfileError):
        raw_payload = getattr(exc, "provider_request_payload", None)
        if isinstance(raw_payload, dict):
            provider_request_payload = raw_payload
    if provider_request_payload is None:
        existing_payload = task_state.get("provider_request_payload")
        if isinstance(existing_payload, dict):
            provider_request_payload = existing_payload

    task_state["provider_request_payload"] = provider_request_payload
    task_state["prompt_encoding_audit"] = _build_provider_prompt_encoding_audit(req.prompt, provider_request_payload)
    if isinstance(asset, dict) and isinstance(asset.get("metadata"), dict):
        asset["metadata"]["providerRequestPayload"] = provider_request_payload or {}
        asset["metadata"]["promptEncodingAudit"] = task_state["prompt_encoding_audit"]


def _infer_creative_video_task_mode(req: CreativeGenerationRequest, generated: dict[str, Any] | None = None) -> str:
    if isinstance(generated, dict):
        task_mode = str(generated.get("taskMode") or "").strip()
        if task_mode:
            return task_mode
    if str(req.first_frame_url or "").strip():
        return "image_to_video"
    if req.reference_images:
        return "reference_to_video"
    return "text_to_video"


def _extract_provider_error_message(provider_response: Any) -> str:
    if not isinstance(provider_response, dict):
        return ""

    candidates: list[str] = []
    stack: list[Any] = [provider_response]
    while stack:
        current = stack.pop()
        if not isinstance(current, dict):
            continue
        for key in ("error_message", "message", "detail", "error", "msg"):
            value = current.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
            elif isinstance(value, dict):
                stack.append(value)
        for key in ("data", "result", "output"):
            nested = current.get(key)
            if isinstance(nested, dict):
                stack.append(nested)

    for raw in candidates:
        if "HTTP" in raw and "{" in raw:
            json_part = raw[raw.find("{") :]
            try:
                nested = json.loads(json_part)
            except json.JSONDecodeError:
                pass
            else:
                nested_message = _extract_provider_error_message(nested)
                if nested_message:
                    return nested_message
        return raw
    return ""


def _is_minor_safety_provider_error(message: str) -> bool:
    normalized = str(message or "").strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    return any(
        keyword in lowered
        for keyword in ("child", "children", "minor")
    ) or any(keyword in normalized for keyword in ("青少年", "儿童", "未成年人", "未成年", "少年"))


def _build_provider_safe_storyboard_prompt(prompt: str) -> str:
    adjusted = str(prompt or "").strip()
    if not adjusted:
        return adjusted

    replacements = (
        ("9岁男孩", "体型轻巧的探险者"),
        ("9 岁男孩", "体型轻巧的探险者"),
        ("小男孩", "体型轻巧的探险者"),
        ("男孩", "探险者"),
        ("小女孩", "体型轻巧的探险者"),
        ("女孩", "探险者"),
        ("儿童", "年轻角色"),
        ("未成年", "年轻角色"),
        ("高速下坠姿态", "腾跃穿越的悬空动作姿态"),
        ("即将接触泥面", "悬停在泥坑上方的动作定格瞬间"),
        ("坠落", "跃动"),
        ("跌落", "跨越"),
        ("惊慌紧绷", "专注紧张"),
        ("部分发丝贴在额前", "发丝被动作气流带起"),
        ("额头和鼻尖带汗与泥点", "面部带有少量泥点与户外痕迹"),
        ("衣摆和裤腿已被泥点与湿气打脏边缘贴身", "衣摆和裤腿沾有泥点与湿气，呈现野外历险后的质感"),
        ("双肩小背包背带被下坠拉紧", "双肩背包背带被动作张力带起"),
    )
    for old, new in replacements:
        adjusted = adjusted.replace(old, new)
    if "不表现受伤" not in adjusted:
        adjusted = (
            f"{adjusted} 画面强调冒险电影的动作定格瞬间，不表现受伤、凌虐、惊吓失控或任何未成年人危险伤害内容。"
        )
    return adjusted


def _build_provider_safer_storyboard_prompt(prompt: str) -> str:
    softened = _build_provider_safe_storyboard_prompt(prompt)
    if not softened:
        return softened

    replacements = (
        ("高速下坠姿态", "越过障碍的动态姿态"),
        ("腾跃穿越的悬空动作姿态", "越过障碍的动态姿态"),
        ("悬停在泥坑上方的动作定格瞬间", "跨越泥坑上方的电影动作定格"),
        ("专注紧张", "沉着专注"),
        ("泥坑", "林间泥地区域"),
        ("泥面", "地面"),
        ("泥点", "户外痕迹"),
        ("动作张力", "运动势能"),
    )
    adjusted = softened
    for old, new in replacements:
        adjusted = adjusted.replace(old, new)

    adjusted = re.sub(r"他是一名[^，。]*", "角色是一名小体型探险者", adjusted)
    adjusted = re.sub(r"他是[^，。]*", "角色是一名小体型探险者", adjusted)

    if "环境质感" not in adjusted:
        adjusted = (
            f"{adjusted} 镜头以环境质感、构图节奏和角色运动线条为主，不强调年龄，不表现危险伤害。"
        )
    return adjusted


def _build_provider_safe_storyboard_prompt_variants(prompt: str) -> list[str]:
    primary = _build_provider_safe_storyboard_prompt(prompt)
    secondary = _build_provider_safer_storyboard_prompt(prompt)
    variants: list[str] = []
    for item in (primary, secondary):
        normalized = str(item or "").strip()
        if normalized and normalized not in variants and normalized != str(prompt or "").strip():
            variants.append(normalized)
    return variants


async def _generate_image_asset_with_provider_recovery(
    profile: dict[str, Any],
    *,
    kind: str,
    prompt: str,
    aspect_ratio: str | None,
    negative_prompt: str | None,
    reference_images: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    try:
        return await generate_image_asset(
            profile,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            negative_prompt=negative_prompt,
            reference_images=reference_images,
        )
    except ModelProfileError as exc:
        provider_message = _extract_provider_error_message(getattr(exc, "provider_response", None))
        should_retry = (
            kind == "image"
            and str(profile.get("provider") or "") == "poyo-async"
            and _is_minor_safety_provider_error(provider_message or str(exc))
        )
        if not should_retry:
            raise

        retry_error: ModelProfileError = exc
        variants = _build_provider_safe_storyboard_prompt_variants(prompt)
        for adjusted_prompt in variants:
            try:
                recovered = await generate_image_asset(
                    profile,
                    prompt=adjusted_prompt,
                    aspect_ratio=aspect_ratio,
                    negative_prompt=negative_prompt,
                    reference_images=reference_images,
                )
                recovered["providerSafePrompt"] = adjusted_prompt
                recovered["providerPromptAdjusted"] = True
                recovered["providerPromptAdjustmentReason"] = provider_message or str(exc)
                return recovered
            except ModelProfileError as retry_exc:
                retry_error = retry_exc
                retry_message = _extract_provider_error_message(getattr(retry_exc, "provider_response", None))
                if not _is_minor_safety_provider_error(retry_message or str(retry_exc)):
                    raise
        raise retry_error


def _complete_reconciled_creative_task(
    task_id: str,
    task_state: dict,
    req: CreativeGenerationRequest,
    generated: dict,
) -> dict:
    kind = str(task_state.get("kind") or task_state.get("target_kind") or "image")
    version = int(task_state.get("version", 1))
    asset_kind = "image" if kind == "reference-image" else kind
    capability = "image" if asset_kind == "image" else "video"
    profile = _resolve_creative_profile(req, capability)
    provider = str(profile.get("provider") or "")
    model_profile_id = str(profile.get("id") or "")
    normalized_subject = _normalize_display_text(req.asset_subject, "未命名资产")
    normalized_shot_id = _normalize_display_text(req.shot_id, "未命名镜头")
    asset_scope = req.asset_scope or "shot"
    asset_subject = normalized_subject if kind == "reference-image" else normalized_shot_id
    model_name = req.model or str(profile.get("model_name") or ("Seedream v4.5" if asset_kind == "image" else "Kling 1.6"))

    if kind == "reference-image":
        title = f"{normalized_subject} 参考图 v{version}"
    else:
        title = f"{'分镜图' if kind == 'image' else '视频'} {normalized_shot_id} v{version}"

    asset = build_task_adapter_asset(
        kind=kind,
        title=title,
        prompt=(generated.get("revisedPrompt") or req.prompt) if asset_kind == "image" else req.prompt,
        model_name=model_name,
        source_asset_id=req.source_asset_id,
        asset_scope=asset_scope,
        asset_subject=asset_subject,
        aspect_ratio=req.aspect_ratio,
        duration_seconds=req.duration_seconds or 0,
        reference_asset_ids=req.reference_asset_ids or [],
        reference_images=req.reference_images or [],
        shot_id=normalized_shot_id,
        source_node_id=req.source_node_id,
        model_profile_id=model_profile_id,
        provider=provider,
        source="mock" if provider == "prototype-task-adapter" else "real",
        preview_url=generated["previewUrl"],
        first_frame_asset_id=req.first_frame_asset_id,
        first_frame_url=req.first_frame_url,
        provider_task_mode=_infer_creative_video_task_mode(req, generated) if asset_kind == "video" else "",
    )
    asset["uri"] = generated.get("uri") or generated["previewUrl"]
    if asset_kind == "image":
        asset["prompt"] = generated.get("revisedPrompt") or req.prompt

    asset["label"] = f"v{version}"
    asset["adopted"] = True
    asset["metadata"].update({
        "imageRole": "reference" if kind == "reference-image" else "storyboard" if asset_kind == "image" else "",
        "modelName": model_name,
        "usesMock": provider == "prototype-task-adapter",
        "negativePrompt": req.negative_prompt or "",
        "externalTaskId": generated.get("externalTaskId") or "",
        "externalStatus": generated.get("externalStatus") or "",
        "pollAttempts": generated.get("pollAttempts") or 0,
        "providerResponse": generated.get("providerResponse") or {},
        "providerPromptAdjusted": bool(generated.get("providerPromptAdjusted")),
        "providerPromptAdjustmentReason": generated.get("providerPromptAdjustmentReason") or "",
        "providerSafePrompt": generated.get("providerSafePrompt") or "",
    })
    _apply_provider_submission_snapshot(task_state, asset, req, generated=generated)

    if kind == "reference-image":
        persisted_reference = None
        asset_type = "scene" if (req.asset_scope or "location") == "location" else str(req.asset_scope or "scene")
        image_uri = str(asset.get("uri") or asset.get("previewUrl") or "").strip()
        if str(req.source_asset_id or "").strip() and image_uri:
            reference_token = _resolve_visual_reference_token(
                req.book_id,
                asset_type,
                str(req.source_asset_id),
                req.asset_subject or title,
            )
            persisted_reference = _create_visual_reference_asset_record(
                req.book_id,
                episode=req.episode,
                asset_type=asset_type,
                asset_id=str(req.source_asset_id),
                asset_name=req.asset_subject or title,
                image_url=image_uri,
                local_path="",
                reference_token=reference_token,
                status="selected",
                prompt=asset.get("prompt") or req.prompt,
                model=model_name,
                notes=f"视觉资产库生成 · {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                meta_info={
                    "source": "visual-asset-library-generate",
                    "taskId": task_id,
                    "externalTaskId": generated.get("externalTaskId") or "",
                    "version": asset.get("label") or "",
                    "generatedAt": datetime.utcnow().isoformat(),
                    "assetScope": req.asset_scope or "location",
                    "assetSubject": req.asset_subject or title,
                    "usesMock": provider == "prototype-task-adapter",
                },
            )
            asset["metadata"]["referenceAssetId"] = persisted_reference.get("id")
            asset["metadata"]["referenceStatus"] = persisted_reference.get("status")
            if persisted_reference.get("sync_warning"):
                asset["metadata"]["referenceSyncWarning"] = persisted_reference.get("sync_warning")
        task_state["reference_asset"] = persisted_reference
    else:
        _save_asset_to_storyboard(req.book_id, req.episode, req.shot_id, kind, asset)

    task_state["progress"] = 100
    task_state["status"] = "done"
    task_state["error"] = None
    task_state["asset"] = asset
    task_state["model_profile_id"] = model_profile_id
    task_state["provider"] = provider
    task_state["first_frame_asset_id"] = req.first_frame_asset_id or ""
    task_state["first_frame_url"] = req.first_frame_url or ""
    task_state["provider_task_mode"] = asset.get("metadata", {}).get("providerTaskMode") if isinstance(asset.get("metadata"), dict) else ""
    task_state["uses_mock"] = provider == "prototype-task-adapter"
    task_state["external_task_id"] = generated.get("externalTaskId") if provider != "prototype-task-adapter" else None
    task_state["external_status"] = generated.get("externalStatus") if provider != "prototype-task-adapter" else None
    task_state["poll_attempts"] = generated.get("pollAttempts") if provider != "prototype-task-adapter" else None
    task_state["provider_response"] = generated.get("providerResponse") if provider != "prototype-task-adapter" else None
    _stamp_creative_task_state(task_state)
    return task_state


async def _run_creative_task(task_id: str, kind: str, req: CreativeGenerationRequest):
    try:
        task_state = _creative_tasks[task_id]
        task_state["status"] = "running"
        task_state["progress"] = 25
        await asyncio.sleep(1.0)

        if req.simulate_error:
            raise RuntimeError("已按请求模拟真实生成失败。")

        task_state["progress"] = 70
        await asyncio.sleep(1.0)

        version = int(task_state.get("version", 1))
        asset_kind = "image" if kind == "reference-image" else kind
        profile = _resolve_creative_profile(req, "image" if asset_kind == "image" else "video")
        provider = str(profile.get("provider") or "")
        model_profile_id = str(profile.get("id") or "")
        normalized_subject = _normalize_display_text(req.asset_subject, "未命名资产")
        normalized_shot_id = _normalize_display_text(req.shot_id, "未命名镜头")
        asset_scope = req.asset_scope or "shot"
        asset_subject = normalized_subject if kind == "reference-image" else normalized_shot_id
        model_name = req.model or str(profile.get("model_name") or ("Seedream v4.5" if asset_kind == "image" else "Kling 1.6"))

        if kind == "reference-image":
            title = f"{normalized_subject} 参考图 v{version}"
        else:
            title = f"{'分镜图' if kind == 'image' else '视频'} {normalized_shot_id} v{version}"

        generated: dict[str, Any] = {}
        if provider == "prototype-task-adapter":
            preview_url = _make_asset_preview(asset_kind, title, model_name)
            asset = build_task_adapter_asset(
                kind=kind,
                title=title,
                prompt=req.prompt,
                model_name=model_name,
                source_asset_id=req.source_asset_id,
                asset_scope=asset_scope,
                asset_subject=asset_subject,
                aspect_ratio=req.aspect_ratio,
                duration_seconds=req.duration_seconds or 0,
                reference_asset_ids=req.reference_asset_ids or [],
                reference_images=req.reference_images or [],
                shot_id=normalized_shot_id,
                source_node_id=req.source_node_id,
                model_profile_id=model_profile_id,
                provider=provider,
                source="mock",
                preview_url=preview_url,
                first_frame_asset_id=req.first_frame_asset_id,
                first_frame_url=req.first_frame_url,
                provider_task_mode=_infer_creative_video_task_mode(req) if asset_kind == "video" else "",
            )
        elif asset_kind == "image":
            generated = await _generate_image_asset_with_provider_recovery(
                profile,
                kind=kind,
                prompt=req.prompt,
                aspect_ratio=req.aspect_ratio,
                negative_prompt=req.negative_prompt,
                reference_images=req.reference_images or [],
            )
            asset = build_task_adapter_asset(
                kind=kind,
                title=title,
                prompt=generated.get("revisedPrompt") or req.prompt,
                model_name=model_name,
                source_asset_id=req.source_asset_id,
                asset_scope=asset_scope,
                asset_subject=asset_subject,
                aspect_ratio=req.aspect_ratio,
                duration_seconds=req.duration_seconds or 0,
                reference_asset_ids=req.reference_asset_ids or [],
                reference_images=req.reference_images or [],
                shot_id=normalized_shot_id,
                source_node_id=req.source_node_id,
                model_profile_id=model_profile_id,
                provider=provider,
                source="real",
                preview_url=generated["previewUrl"],
            )
            asset["uri"] = generated.get("uri") or generated["previewUrl"]
            asset["prompt"] = generated.get("revisedPrompt") or req.prompt
        else:
            generated = await generate_video_asset(
                profile,
                prompt=req.prompt,
                duration_seconds=req.duration_seconds,
                negative_prompt=req.negative_prompt,
                aspect_ratio=req.aspect_ratio,
                first_frame_url=req.first_frame_url,
                reference_images=req.reference_images or [],
            )
            asset = build_task_adapter_asset(
                kind=kind,
                title=title,
                prompt=req.prompt,
                model_name=model_name,
                source_asset_id=req.source_asset_id,
                asset_scope=asset_scope,
                asset_subject=asset_subject,
                aspect_ratio=req.aspect_ratio,
                duration_seconds=req.duration_seconds or 0,
                reference_asset_ids=req.reference_asset_ids or [],
                reference_images=req.reference_images or [],
                shot_id=normalized_shot_id,
                source_node_id=req.source_node_id,
                model_profile_id=model_profile_id,
                provider=provider,
                source="real",
                preview_url=generated["previewUrl"],
                first_frame_asset_id=req.first_frame_asset_id,
                first_frame_url=req.first_frame_url,
                provider_task_mode=_infer_creative_video_task_mode(req, generated),
            )
            asset["uri"] = generated.get("uri") or generated["previewUrl"]

        asset["label"] = f"v{version}"
        asset["adopted"] = True
        asset["metadata"].update({
            "imageRole": "reference" if kind == "reference-image" else "storyboard" if asset_kind == "image" else "",
            "modelName": model_name,
            "usesMock": provider == "prototype-task-adapter",
            "negativePrompt": req.negative_prompt or "",
            "externalTaskId": generated.get("externalTaskId") or "",
            "externalStatus": generated.get("externalStatus") or "",
            "pollAttempts": generated.get("pollAttempts") or 0,
            "providerResponse": generated.get("providerResponse") or {},
            "providerPromptAdjusted": bool(generated.get("providerPromptAdjusted")),
            "providerPromptAdjustmentReason": generated.get("providerPromptAdjustmentReason") or "",
            "providerSafePrompt": generated.get("providerSafePrompt") or "",
        })
        _apply_provider_submission_snapshot(task_state, asset, req, generated=generated)

        if kind == "reference-image":
            persisted_reference = None
            asset_type = "scene" if (req.asset_scope or "location") == "location" else str(req.asset_scope or "scene")
            image_uri = str(asset.get("uri") or asset.get("previewUrl") or "").strip()
            if str(req.source_asset_id or "").strip() and image_uri:
                reference_token = _resolve_visual_reference_token(
                    req.book_id,
                    asset_type,
                    str(req.source_asset_id),
                    req.asset_subject or title,
                )
                persisted_reference = _create_visual_reference_asset_record(
                    req.book_id,
                    episode=req.episode,
                    asset_type=asset_type,
                    asset_id=str(req.source_asset_id),
                    asset_name=req.asset_subject or title,
                    image_url=image_uri,
                    local_path="",
                    reference_token=reference_token,
                    status="selected",
                    prompt=asset.get("prompt") or req.prompt,
                    model=model_name,
                    notes=f"视觉资产库生成 · {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                    meta_info={
                        "source": "visual-asset-library-generate",
                        "taskId": task_id,
                        "externalTaskId": generated.get("externalTaskId") or "",
                        "version": asset.get("label") or "",
                        "generatedAt": datetime.utcnow().isoformat(),
                        "assetScope": req.asset_scope or "location",
                        "assetSubject": req.asset_subject or title,
                        "usesMock": provider == "prototype-task-adapter",
                    },
                )
                asset["metadata"]["referenceAssetId"] = persisted_reference.get("id")
                asset["metadata"]["referenceStatus"] = persisted_reference.get("status")
                if persisted_reference.get("sync_warning"):
                    asset["metadata"]["referenceSyncWarning"] = persisted_reference.get("sync_warning")
            task_state["reference_asset"] = persisted_reference
        else:
            _save_asset_to_storyboard(req.book_id, req.episode, req.shot_id, kind, asset)

        task_state["progress"] = 100
        task_state["status"] = "done"
        task_state["asset"] = asset
        task_state["model_profile_id"] = model_profile_id
        task_state["provider"] = provider
        task_state["first_frame_asset_id"] = req.first_frame_asset_id or ""
        task_state["first_frame_url"] = req.first_frame_url or ""
        task_state["provider_task_mode"] = asset.get("metadata", {}).get("providerTaskMode") if isinstance(asset.get("metadata"), dict) else ""
        task_state["uses_mock"] = provider == "prototype-task-adapter"
        task_state["external_task_id"] = generated.get("externalTaskId") if provider != "prototype-task-adapter" else None
        task_state["external_status"] = generated.get("externalStatus") if provider != "prototype-task-adapter" else None
        task_state["poll_attempts"] = generated.get("pollAttempts") if provider != "prototype-task-adapter" else None
        task_state["provider_response"] = generated.get("providerResponse") if provider != "prototype-task-adapter" else None
        _stamp_creative_task_state(task_state)
    except Exception as exc:
        task_state = _creative_tasks[task_id]
        task_state["status"] = "error"
        task_state["error"] = str(exc)
        if isinstance(exc, ModelProfileError):
            provider_message = _extract_provider_error_message(getattr(exc, "provider_response", None))
            if provider_message:
                task_state["error"] = provider_message
            if getattr(exc, "external_task_id", None):
                task_state["external_task_id"] = exc.external_task_id
            if getattr(exc, "external_status", None):
                task_state["external_status"] = exc.external_status
            if getattr(exc, "poll_attempts", None) is not None:
                task_state["poll_attempts"] = exc.poll_attempts
            if getattr(exc, "provider_response", None) is not None:
                task_state["provider_response"] = exc.provider_response
            _apply_provider_submission_snapshot(task_state, None, req, exc=exc)
        _stamp_creative_task_state(task_state)


@app.post("/api/prototyping/generate-image")
async def generate_image(req: CreativeGenerationRequest, bg: BackgroundTasks):
    return await _enqueue_creative_task(req, bg, "image")


@app.post("/api/prototyping/generate-reference-image")
async def generate_reference_image(req: CreativeGenerationRequest, bg: BackgroundTasks):
    return await _enqueue_creative_task(req, bg, "reference-image")


@app.post("/api/prototyping/generate-video")
async def generate_video(req: CreativeGenerationRequest, bg: BackgroundTasks):
    return await _enqueue_creative_task(req, bg, "video")


@app.get("/api/prototyping/assets/{asset_id}")
def get_legacy_prototyping_asset_placeholder(asset_id: str):
    from fastapi.responses import Response
    from urllib.parse import quote

    normalized_asset_id = str(asset_id or "legacy-asset").strip()[:80]
    escaped_asset_id = (
        normalized_asset_id
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
      <defs>
        <linearGradient id="legacy-preview" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#111827" />
          <stop offset="100%" stop-color="#020617" />
        </linearGradient>
      </defs>
      <rect width="640" height="360" rx="24" fill="url(#legacy-preview)" />
      <rect x="32" y="32" width="576" height="296" rx="18" fill="#0f172a" stroke="#64748b" stroke-width="2" stroke-dasharray="10 8" />
      <text x="56" y="126" fill="#e2e8f0" font-size="30" font-family="Segoe UI, sans-serif">历史预览图不可用</text>
      <text x="56" y="176" fill="#94a3b8" font-size="20" font-family="Segoe UI, sans-serif">旧原型任务资源已丢失，系统已降级保留任务记录。</text>
      <text x="56" y="230" fill="#64748b" font-size="16" font-family="Segoe UI, sans-serif">asset: {escaped_asset_id}</text>
    </svg>
    """
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "no-store",
            "X-Legacy-Prototyping-Asset": quote(normalized_asset_id),
        },
    )


async def _enqueue_creative_task(req: CreativeGenerationRequest, bg: BackgroundTasks, kind: str):
    task_id = uuid.uuid4().hex[:12]
    capability = "image" if kind in {"image", "reference-image"} else "video"
    try:
        profile = _resolve_creative_profile(req, capability)
    except (ModelProfileError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    version = (
        _next_reference_asset_version(req.book_id, req.episode, req.asset_scope or "location", req.asset_subject)
        if kind == "reference-image"
        else _next_asset_version(req.book_id, req.episode, req.shot_id, "video" if kind == "video" else "image")
    )

    _creative_tasks[task_id] = {
        "task_id": task_id,
        "status": "queued",
        "progress": 0,
        "target_kind": "video" if kind == "video" else "image",
        "book_id": req.book_id,
        "episode": req.episode,
        "shot_id": req.shot_id,
        "version": version,
        "model_profile_id": profile.get("id"),
        "provider": profile.get("provider"),
        "uses_mock": profile.get("provider") == "prototype-task-adapter",
        "external_task_id": None,
        "external_status": None,
        "poll_attempts": 0,
        "provider_response": None,
        "provider_request_payload": None,
        "restarted_from_task_id": None,
        "restart_count": 0,
        "last_restarted_at": None,
    }
    _stamp_creative_task_state(_creative_tasks[task_id], created=True)
    _store_creative_task_request(_creative_tasks[task_id], req, kind)
    bg.add_task(_run_creative_task, task_id, kind, req)
    return {"task_id": task_id, "status": "queued", "model_profile_id": profile.get("id"), "uses_mock": profile.get("provider") == "prototype-task-adapter"}


@app.get("/api/prototyping/tasks/{task_id}")
def get_creative_task(task_id: str):
    task = _creative_tasks.get(task_id)
    if not task:
        task = _load_persisted_task_state(task_id)
        if _is_creative_task_state(task):
            _creative_tasks.setdefault(task_id, task)
        else:
            task = None
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/api/books/{book_id}/creative-tasks")
def list_book_creative_tasks(book_id: int, limit: int = 20):
    capped_limit = max(1, min(int(limit or 20), 100))
    tasks_by_id: dict[str, dict] = {}
    live_task_ids: set[str] = set()
    for task_kind in ("creative-image", "creative-video", "creative-reference-image", "creative-machine_prompt_api_submission"):
        for task in _list_persisted_task_states(task_kind, book_id, capped_limit):
            task_id = str(task.get("task_id") or "").strip()
            if task_id:
                tasks_by_id[task_id] = task
    for task in _creative_tasks.values():
        if (
            int(task.get("book_id") or 0) == int(book_id)
            and str(task.get("kind") or task.get("target_kind") or "").strip() in {"image", "video", "reference-image", "machine_prompt_api_submission"}
        ):
            task_id = str(task.get("task_id") or "").strip()
            if task_id:
                live_task_ids.add(task_id)
                tasks_by_id[task_id] = task
    tasks = list(tasks_by_id.values())
    tasks.sort(
        key=lambda item: (
            0 if str(item.get("task_id") or "") in live_task_ids else -1,
            str(item.get("updated_at") or item.get("created_at") or ""),
            str(item.get("task_id") or ""),
        ),
        reverse=True,
    )
    return {"tasks": tasks[:capped_limit]}


@app.post("/api/prototyping/tasks/{task_id}/reconcile")
async def reconcile_creative_task(task_id: str):
    task = _creative_tasks.get(task_id)
    if not task:
        task = _load_persisted_task_state(task_id)
        if _is_creative_task_state(task):
            _creative_tasks[task_id] = task
        else:
            task = None
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.get("status") == "done":
        return task
    external_task_id = str(task.get("external_task_id") or "").strip()
    if not external_task_id:
        return task

    request_payload = task.get("request_payload")
    if not isinstance(request_payload, dict):
        return task

    kind = str(task.get("kind") or task.get("target_kind") or "image")
    capability = "image" if kind in {"image", "reference-image"} else "video"

    try:
        req = CreativeGenerationRequest.model_validate(request_payload)
        profile = _resolve_creative_profile(req, capability)
        provider = str(profile.get("provider") or "")
        if provider == "poyo-async":
            reconciled = await reconcile_poyo_generation(profile, external_task_id=external_task_id)
        elif provider == "minimax-h3-async":
            reconciled = await reconcile_minimax_h3_generation(profile, external_task_id=external_task_id)
        else:
            return task
        if reconciled.get("status") == "done":
            return _complete_reconciled_creative_task(task_id, task, req, reconciled)

        task["status"] = "running"
        task["progress"] = max(int(task.get("progress") or 0), 85)
        task["error"] = None
        task["provider"] = provider
        task["uses_mock"] = False
        task["external_status"] = reconciled.get("externalStatus")
        task["poll_attempts"] = (int(task.get("poll_attempts") or 0) + int(reconciled.get("pollAttempts") or 0))
        task["provider_response"] = reconciled.get("providerResponse")
        _stamp_creative_task_state(task)
        return task
    except Exception as exc:
        task["status"] = "error"
        task["error"] = str(exc)
        if isinstance(exc, ModelProfileError):
            if getattr(exc, "external_status", None):
                task["external_status"] = exc.external_status
            if getattr(exc, "provider_response", None) is not None:
                task["provider_response"] = exc.provider_response
            if getattr(exc, "poll_attempts", None) is not None:
                task["poll_attempts"] = int(task.get("poll_attempts") or 0) + int(exc.poll_attempts or 0)
        _stamp_creative_task_state(task)
        return task


@app.post("/api/prototyping/tasks/{task_id}/restart")
async def restart_creative_task(task_id: str, bg: BackgroundTasks):
    task = _creative_tasks.get(task_id)
    if not task:
        task = _load_persisted_task_state(task_id)
        if _is_creative_task_state(task):
            _creative_tasks[task_id] = task
        else:
            task = None
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    request_payload = task.get("request_payload")
    if not isinstance(request_payload, dict):
        raise HTTPException(status_code=400, detail="Task request payload is unavailable")

    kind = str(task.get("kind") or task.get("target_kind") or "image")
    try:
        req = CreativeGenerationRequest.model_validate({
            **request_payload,
            "simulate_error": False,
        })
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Task request payload is invalid: {exc}") from exc

    restarted = await _enqueue_creative_task(req, bg, kind)
    new_task_id = str(restarted.get("task_id") or "").strip()
    if new_task_id:
        restart_count = int(task.get("restart_count") or 0) + 1
        restarted_at = datetime.utcnow().isoformat()
        restarted_task = _creative_tasks.get(new_task_id)
        if isinstance(restarted_task, dict):
            restarted_task["restarted_from_task_id"] = task_id
            restarted_task["restart_count"] = restart_count
            restarted_task["last_restarted_at"] = restarted_at
            _stamp_creative_task_state(restarted_task)
        restarted["restart_count"] = restart_count
        restarted["last_restarted_at"] = restarted_at
    return {
        **restarted,
        "restarted_from_task_id": task_id,
        "kind": kind,
    }


@app.post("/api/prototyping/adopt-version")
def adopt_creative_version(req: AdoptVersionRequest):
    _adopt_asset_version(req.book_id, req.episode, req.shot_id, req.kind, req.asset_id)
    return {"ok": True}


@app.post("/api/pipeline/visual-setup")
async def run_visual_setup(req: PipelineRequest, bg: BackgroundTasks):
    """Run visual setup: era scan plus per-episode location/prop/makeup extraction."""
    import uuid
    task_id = uuid.uuid4().hex[:12]
    _visual_tasks[task_id] = {
        "status": "running",
        "progress": 0,
        "current_step": "starting",
        "book_id": req.book_id,
    }

    async def _run():
        try:
            from agents.scene_setup import SceneSetupAgent
            from models import Session, Script

            with Session() as s:
                scripts = s.query(Script).filter(
                    Script.book_id == req.book_id,
                    Script.genre == req.genre,
                ).order_by(Script.episode).all()

            if not scripts:
                _visual_tasks[task_id]["status"] = "error"
                _visual_tasks[task_id]["current_step"] = "没有剧本，请先运行剧本生成。"
                return

            agent = SceneSetupAgent(req.book_id, genre=req.genre)

            # 1. 时代扫描
            _visual_tasks[task_id]["current_step"] = "扫描时代规范"
            update_vt = lambda step: _visual_tasks[task_id].update(current_step=step)
            update_vt("扫描时代规范")
            try:
                await asyncio.to_thread(agent.run_era_scan)
            except Exception as e:
                update_vt(f"时代扫描跳过: {e}")

            total = len(scripts)
            for i, sc in enumerate(scripts):
                ep = sc.episode
                pct = int(((i + 1) / total) * 90 + 10)
                update_vt(f"提取第 {ep} 集场景设定 ({i+1}/{total})")
                await asyncio.to_thread(agent.run_locations, ep)
                update_vt(f"提取第 {ep} 集道具设定 ({i+1}/{total})")
                await asyncio.to_thread(agent.run_props, ep)
                update_vt(f"精调第 {ep} 集定妆 ({i+1}/{total})")
                await asyncio.to_thread(agent.run_makeup, ep)
                _visual_tasks[task_id]["progress"] = pct

            _visual_tasks[task_id]["status"] = "done"
            _visual_tasks[task_id]["progress"] = 100
            _visual_tasks[task_id]["current_step"] = "视觉设定完成"

        except Exception as exc:
            _visual_tasks[task_id]["status"] = "error"
            _visual_tasks[task_id]["current_step"] = str(exc)
            _visual_tasks[task_id]["error"] = str(exc)
            import traceback
            _visual_tasks[task_id]["traceback"] = traceback.format_exc()

    bg.add_task(_run)
    return {"task_id": task_id}


_visual_tasks: dict = {}


# ── Character QA & Merge endpoints ──────────────────────────────────────────

class CharacterMergeRequest(BaseModel):
    name_a: str
    name_b: str
    canonical_name: str | None = None

class CharacterUpdateRequest(BaseModel):
    gender: str | None = None
    identity: str | None = None
    name: str | None = None


@app.get("/api/books/{book_id}/chapters")
def list_chapters(book_id: int):
    """获取章节列表摘要；正文由单章详情接口懒加载。"""
    from models import Chapter as ChapterModel
    with Session() as s:
        chapters = s.query(ChapterModel).filter(
            ChapterModel.book_id == book_id
        ).order_by(ChapterModel.seq).all()
        result = []
        for ch in chapters:
            result.append({
                "id": ch.id,
                "seq": ch.seq,
                "title": ch.title or "",
                "word_count": ch.word_count or 0,
                "status": ch.status or "",
                "summary": ch.summary or "",
            })
        return result


@app.get("/api/books/{book_id}/chapters/{chapter_id}")
def get_chapter(book_id: int, chapter_id: int):
    """获取单个章节详情（含原文）。"""
    from models import Chapter as ChapterModel
    with Session() as s:
        ch = s.query(ChapterModel).filter(
            ChapterModel.id == chapter_id,
            ChapterModel.book_id == book_id,
        ).first()
        if not ch:
            raise HTTPException(status_code=404, detail="Chapter not found")
        return {
            "id": ch.id,
            "seq": ch.seq,
            "title": ch.title or "",
            "content": ch.content or "",
            "word_count": ch.word_count or 0,
            "status": ch.status or "",
            "summary": ch.summary or "",
            "character_table": ch.character_table or "[]",
            "events": ch.events or "[]",
            "scenes": ch.scenes or "[]",
            "foreshadowing": ch.foreshadowing or "[]",
        }


@app.get("/api/books/{book_id}/characters/qa")
def get_character_qa(book_id: int):
    """获取人物画像质检报告。"""
    from core.portrait_qa import run_portrait_qa
    with Session() as s:
        report = run_portrait_qa(book_id, s)
        return report.to_dict()


@app.post("/api/books/{book_id}/characters/merge")
def merge_characters_endpoint(book_id: int, req: CharacterMergeRequest):
    """合并两个角色。"""
    from core.portrait_qa import merge_characters
    with Session() as s:
        result = merge_characters(book_id, req.name_a, req.name_b, s, req.canonical_name)
        if isinstance(result, dict) and result.get("error"):
            raise HTTPException(status_code=409, detail=result["error"])
        return result


@app.post("/api/books/{book_id}/characters/resolve-aliases")
def resolve_aliases_endpoint(book_id: int):
    """重新运行别名归并。"""
    from core.alias_resolver import resolve_aliases
    with Session() as s:
        result = resolve_aliases(book_id, s)
        return {"canonical_map": {k: v for k, v in result.items()}}


@app.get("/api/books/{book_id}/characters")
def list_characters(book_id: int):
    """获取所有角色列表。"""
    from models import CharacterProfile, CharacterStage
    with Session() as s:
        profiles = s.query(CharacterProfile).filter(
            CharacterProfile.book_id == book_id
        ).all()
        result = []
        for p in profiles:
            aliases = []
            try:
                aliases = json.loads(p.aliases) if p.aliases else []
            except (json.JSONDecodeError, TypeError):
                pass
            relationships = {}
            try:
                relationships = json.loads(p.relationships) if p.relationships else {}
            except (json.JSONDecodeError, TypeError):
                pass
            stages = s.query(CharacterStage).filter(
                CharacterStage.book_id == book_id,
                CharacterStage.character_name == p.name,
            ).all()
            result.append({
                "id": p.id,
                "name": p.name,
                "aliases": aliases,
                "gender": p.gender or "",
                "age_range": p.age_range or "",
                "role": p.role or "",
                "identity": p.identity or "",
                "personality": p.personality or "",
                "relationships": relationships,
                "importance": p.importance or "",
                "chapter_range": p.chapter_range or "",
                "stages": [{"stage_name": st.stage_name, "chapter_start": st.chapter_start, "chapter_end": st.chapter_end} for st in stages],
            })
        return result


@app.patch("/api/books/{book_id}/characters/{char_id}")
def update_character(book_id: int, char_id: int, req: CharacterUpdateRequest):
    """更新角色属性。"""
    from models import CharacterProfile
    with Session() as s:
        p = s.query(CharacterProfile).filter(
            CharacterProfile.id == char_id,
            CharacterProfile.book_id == book_id,
        ).first()
        if not p:
            raise HTTPException(status_code=404, detail="Character not found")
        if req.gender is not None:
            p.gender = req.gender
        if req.identity is not None:
            p.identity = req.identity
        if req.name is not None and req.name != p.name:
            # 检查新名字是否已存在
            existing = s.query(CharacterProfile).filter(
                CharacterProfile.book_id == book_id,
                CharacterProfile.name == req.name,
            ).first()
            if existing:
                raise HTTPException(status_code=409, detail=f"角色名「{req.name}」已存在")
            old_name = p.name
            p.name = req.name
            # 更新 stages
            stages = s.query(CharacterStage).filter(
                CharacterStage.book_id == book_id,
                CharacterStage.character_name == old_name,
            ).all()
            for st in stages:
                st.character_name = req.name
        s.commit()
        return {"ok": True, "id": p.id, "name": p.name}


@app.get("/api/books/{book_id}/characters/{char_id}/appearance")
def get_character_appearance(book_id: int, char_id: int):
    """获取角色的所有外貌片段（跨章节）。"""
    from models import CharacterProfile, Chapter as ChapterModel
    with Session() as s:
        p = s.query(CharacterProfile).filter(
            CharacterProfile.id == char_id,
            CharacterProfile.book_id == book_id,
        ).first()
        if not p:
            raise HTTPException(status_code=404, detail="Character not found")
        # 从 chapter 表收集 appearance_fragments
        chapters = s.query(ChapterModel).filter(
            ChapterModel.book_id == book_id
        ).order_by(ChapterModel.seq).all()
        all_frags = []
        for ch in chapters:
            try:
                frags = safe_json_loads(ch.appearance_fragments, {})
                if p.name in frags:
                    for f in frags[p.name]:
                        all_frags.append({"chapter": ch.seq, "fragment": f})
            except (json.JSONDecodeError, TypeError):
                pass
        # 也检查旧名字的 fragments
        try:
            aliases = json.loads(p.aliases) if p.aliases else []
        except:
            aliases = []
        for alias in aliases:
            for ch in chapters:
                try:
                    frags = safe_json_loads(ch.appearance_fragments, {})
                    if alias in frags:
                        for f in frags[alias]:
                            all_frags.append({"chapter": ch.seq, "fragment": f, "via_alias": alias})
                except (json.JSONDecodeError, TypeError):
                    pass
        return {"character": p.name, "fragments": all_frags}


# ── Visual Assets endpoints ────────────────────────────────────────────────
@app.get("/api/books/{book_id}/visual-assets")
def get_visual_assets(book_id: int):
    from models import Session, VisualLocation, VisualProp, VisualReferenceAsset

    _normalize_visual_reference_assets(book_id)

    with Session() as s:
        reference_rows = (
            s.query(VisualReferenceAsset)
            .filter(VisualReferenceAsset.book_id == book_id)
            .order_by(VisualReferenceAsset.asset_type, VisualReferenceAsset.asset_id, VisualReferenceAsset.id)
            .all()
        )
        reference_index: dict[tuple[str, str], list[dict]] = {}
        for row in reference_rows:
            reference_index.setdefault((row.asset_type, row.asset_id), []).append(_serialize_reference_asset_row(row))

        location_rows = s.query(VisualLocation).filter(VisualLocation.book_id == book_id).order_by(VisualLocation.name).all()
        prop_rows = s.query(VisualProp).filter(VisualProp.book_id == book_id).order_by(VisualProp.name).all()

        locations = [
            _serialize_visual_asset_row(
                row,
                "scene",
                reference_assets=reference_index.get(("scene", str(row.id)), []),
                peer_rows=location_rows,
            )
            for row in location_rows
        ]
        props = [
            _serialize_visual_asset_row(
                row,
                "prop",
                reference_assets=reference_index.get(("prop", str(row.id)), []),
                peer_rows=prop_rows,
            )
            for row in prop_rows
        ]
        makeup_rows = _load_makeup_rows_or_profile_fallback(s, book_id)
        makeup_peer_rows: dict[str, list[object]] = {}
        for makeup_row in makeup_rows:
            makeup_peer_rows.setdefault(str(getattr(makeup_row, "character_name", "") or ""), []).append(makeup_row)
        characters = [
            _serialize_visual_asset_row(
                row,
                "character",
                episode=row.episode,
                reference_assets=reference_index.get(("character", str(row.id)), []),
                peer_rows=makeup_peer_rows.get(str(getattr(row, "character_name", "") or ""), []),
            )
            for row in makeup_rows
        ]

    return {
        "book_id": book_id,
        "locations": locations,
        "props": props,
        "characters": characters,
    }


@app.patch("/api/books/{book_id}/visual-assets/{asset_type}/{asset_id}")
def patch_visual_asset(book_id: int, asset_type: str, asset_id: int, req: VisualAssetPatchRequest):
    from models import Session, VisualLocation, VisualMakeup, VisualProp

    model_map = {
        "scene": VisualLocation,
        "prop": VisualProp,
        "character": VisualMakeup,
    }
    model = model_map.get(asset_type)
    if model is None:
        raise HTTPException(status_code=400, detail=f"Unsupported asset_type: {asset_type}")

    with Session() as s:
        row = s.query(model).filter(model.book_id == book_id, model.id == asset_id).first()
        if row is None and asset_type == "character":
            row = _materialize_character_profile_fallback_makeup(s, book_id, asset_id)
        if not row:
            raise HTTPException(status_code=404, detail="Visual asset not found")

        if req.jimeng_ref_name is not None:
            row.jimeng_ref_name = req.jimeng_ref_name
        if req.negative_prompt is not None:
            row.negative_prompt = req.negative_prompt
        if req.asset_status is not None:
            row.asset_status = req.asset_status
        if req.shot_ids is not None:
            row.shot_ids = json.dumps([str(item) for item in req.shot_ids if str(item).strip()], ensure_ascii=False)
        row.updated_at = datetime.utcnow()
        s.commit()
        s.refresh(row)
        payload = _serialize_visual_asset_row(row, asset_type, episode=getattr(row, "episode", None))

    warnings = _sync_active_reference_assets_for_visual_asset(book_id, asset_type, asset_id)
    if warnings:
        payload["sync_warning"] = warnings[0]
        if len(warnings) > 1:
            payload["sync_warnings"] = warnings
    return payload


@app.post("/api/books/{book_id}/visual-assets/character/{asset_id}/shot-variant")
def create_character_shot_variant(book_id: int, asset_id: int, req: CharacterShotVariantCreateRequest):
    with Session() as s:
        payload = _create_or_update_character_shot_variant(s, book_id, asset_id, req)
        s.commit()
        return payload


@app.post("/api/books/{book_id}/visual-reference-assets")
def create_visual_reference_asset(book_id: int, req: VisualReferenceAssetRequest):
    return _create_visual_reference_asset_record(
        book_id,
        episode=req.episode,
        asset_type=req.asset_type,
        asset_id=req.asset_id,
        asset_name=req.asset_name or "",
        image_url=req.image_url,
        local_path=req.local_path,
        reference_token=req.reference_token,
        status=req.status,
        prompt=req.prompt,
        model=req.model,
        notes=req.notes,
        meta_info=req.meta_info,
    )


@app.patch("/api/books/{book_id}/visual-reference-assets/{reference_id}")
def patch_visual_reference_asset(book_id: int, reference_id: int, req: VisualReferenceAssetPatchRequest):
    from models import Session, VisualReferenceAsset

    with Session() as s:
        row = s.query(VisualReferenceAsset).filter(
            VisualReferenceAsset.book_id == book_id,
            VisualReferenceAsset.id == reference_id,
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="Reference asset not found")

        if req.asset_name is not None:
            row.asset_name = req.asset_name
        if req.image_url is not None:
            row.image_url = req.image_url
        if req.local_path is not None:
            row.local_path = req.local_path
        if req.reference_token is not None:
            row.reference_token = req.reference_token
        if req.status is not None:
            row.status = req.status
        if req.prompt is not None:
            row.prompt = req.prompt
        if req.model is not None:
            row.model = req.model
        if req.notes is not None:
            row.notes = req.notes
        if req.meta_info is not None:
            row.meta_info = json.dumps(req.meta_info, ensure_ascii=False)
        _refresh_mock_reference_asset_preview(row)
        row.updated_at = datetime.utcnow()
        demoted_rows = _demote_selected_reference_siblings(s, row)
        s.commit()
        s.refresh(row)
        payload = _serialize_reference_asset_row(row)
        try:
            _sync_visual_reference_asset_to_storyboard(book_id, row)
            for demoted in demoted_rows:
                _sync_visual_reference_asset_to_storyboard(book_id, _make_reference_row_from_payload(demoted))
        except Exception as exc:
            payload["sync_warning"] = _build_reference_sync_warning(exc)
        return payload


@app.delete("/api/books/{book_id}/visual-reference-assets/{reference_id}")
def delete_visual_reference_asset(book_id: int, reference_id: int):
    from models import Session, VisualReferenceAsset

    with Session() as s:
        row = s.query(VisualReferenceAsset).filter(
            VisualReferenceAsset.book_id == book_id,
            VisualReferenceAsset.id == reference_id,
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="Reference asset not found")

        payload = _serialize_reference_asset_row(row)
        s.delete(row)
        s.commit()

    response = {"deleted": True, "reference": payload}
    try:
        removed = _remove_reference_asset_from_storyboard(book_id, type("DeletedReferenceRow", (), payload)())
        response["removed_storyboard_references"] = removed
    except Exception as exc:
        response["sync_warning"] = _build_reference_sync_warning(exc)
    return response


@app.get("/api/books/{book_id}/storyboard/{episode}/{shot_id}/structure")
def get_storyboard_structure(book_id: int, episode: int, shot_id: str):
    from models import Session, StoryboardShot

    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if not shot:
            raise HTTPException(status_code=404, detail="Storyboard shot not found")

        meta_info = safe_json_loads(shot.meta_info) if shot.meta_info else {}
        structure_seed = {
            "shot_id": shot.shot_id,
            "scene_name": shot.scene_name,
            "action_process": shot.action_process,
            "dialogue": shot.dialogue,
            "start_state": shot.start_state,
            "end_state": shot.end_state,
            "duration": shot.duration,
            "camera_angle": shot.camera_angle,
            "camera_movement": shot.camera_movement,
            "transition": shot.transition,
            "makeup_prompts": _load_episode_makeup_prompt_stub(book_id, episode),
        }
        structure = _auto_bind_structured_shot_assets(
            book_id,
            episode,
            _derive_structured_shot_payload(meta_info, structure_seed),
            structure_seed,
        )
        return {
            "book_id": book_id,
            "episode": episode,
            "shot_id": shot.shot_id,
            "structured_shot": structure,
        }


@app.patch("/api/books/{book_id}/storyboard/{episode}/{shot_id}/structure")
def patch_storyboard_structure(book_id: int, episode: int, shot_id: str, req: StoryboardStructurePatchRequest):
    from models import Session, StoryboardShot

    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if not shot:
            raise HTTPException(status_code=404, detail="Storyboard shot not found")

        current_meta = safe_json_loads(shot.meta_info) if shot.meta_info else {}
        if not isinstance(current_meta, dict):
            current_meta = {}
        next_meta = _merge_structured_shot_payload(current_meta, req)
        if req.duration is not None:
            shot.duration = int(req.duration)
        if req.camera_angle is not None:
            shot.camera_angle = req.camera_angle
        if req.camera_movement is not None:
            shot.camera_movement = req.camera_movement
        if req.transition is not None:
            shot.transition = req.transition
        shot.meta_info = json.dumps(next_meta, ensure_ascii=False)
        shot.updated_at = datetime.utcnow()
        s.commit()

        return {
            "book_id": book_id,
            "episode": episode,
            "shot_id": shot.shot_id,
            "structured_shot": next_meta["structured_shot"],
        }


@app.post("/api/books/{book_id}/storyboard/auto-bind-visual-assets")
def auto_bind_storyboard_visual_assets(book_id: int, req: StoryboardAutoBindRequest):
    return _persist_auto_bound_storyboard_structures(book_id, req.episodes)


@app.get("/api/books/{book_id}/storyboard/{episode}/{shot_id}/prompt-versions")
def get_storyboard_prompt_versions(book_id: int, episode: int, shot_id: str):
    from models import Session, StoryboardPromptVersion, StoryboardShot

    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if shot:
            shot_meta, prompt_compiler_meta, repaired = _ensure_storyboard_prompt_compiler_state(s, shot)
            if repaired:
                s.commit()
        else:
            shot_meta = {}
            prompt_compiler_meta = {}
        current_version = prompt_compiler_meta.get("latest_version")
        locked_version = prompt_compiler_meta.get("locked_version")
        version_payloads = _build_storyboard_prompt_version_payloads(s, book_id, shot, current_version, locked_version)
        return {
            "book_id": book_id,
            "episode": episode,
            "shot_id": _coerce_storyboard_shot_id(shot_id),
            "locked": bool(prompt_compiler_meta.get("locked", False)),
            "current_version": current_version,
            "locked_version": locked_version,
            "recommended_restore_version": _recommend_storyboard_restore_version(version_payloads, current_version),
            "versions": version_payloads,
        }


@app.post("/api/books/{book_id}/storyboard/{episode}/{shot_id}/prompt-versions/{version_id}/rollback")
def rollback_storyboard_prompt_version(book_id: int, episode: int, shot_id: str, version_id: int, req: StoryboardPromptRollbackRequest):
    from models import Session, StoryboardPromptVersion, StoryboardShot

    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if not shot:
            raise HTTPException(status_code=404, detail="Storyboard shot not found")

        target = s.query(StoryboardPromptVersion).filter(
            StoryboardPromptVersion.book_id == book_id,
            StoryboardPromptVersion.episode == episode,
            StoryboardPromptVersion.shot_id == _coerce_storyboard_shot_id(shot_id),
            StoryboardPromptVersion.id == version_id,
        ).first()
        if not target:
            raise HTTPException(status_code=404, detail="Prompt version not found")
        return _create_storyboard_prompt_rollback(s, shot, target, req)


@app.post("/api/books/{book_id}/storyboard/{episode}/{shot_id}/prompt-versions/recommended-rollback")
def rollback_storyboard_prompt_to_recommended_version(book_id: int, episode: int, shot_id: str, req: StoryboardPromptRollbackRequest):
    from models import Session, StoryboardPromptVersion, StoryboardShot

    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if not shot:
            raise HTTPException(status_code=404, detail="Storyboard shot not found")

        shot_meta, prompt_compiler_meta, repaired = _ensure_storyboard_prompt_compiler_state(s, shot)
        if repaired:
            s.commit()
        current_version = prompt_compiler_meta.get("latest_version")
        locked_version = prompt_compiler_meta.get("locked_version")
        version_payloads = _build_storyboard_prompt_version_payloads(s, book_id, shot, current_version, locked_version)
        recommendation = _recommend_storyboard_restore_version(version_payloads, current_version)
        if not recommendation:
            raise HTTPException(status_code=409, detail="No recommended restore version is currently available.")

        target = s.query(StoryboardPromptVersion).filter(
            StoryboardPromptVersion.book_id == book_id,
            StoryboardPromptVersion.episode == episode,
            StoryboardPromptVersion.shot_id == _coerce_storyboard_shot_id(shot_id),
            StoryboardPromptVersion.id == int(recommendation.get("id") or 0),
        ).first()
        if not target:
            raise HTTPException(status_code=404, detail="Recommended restore version not found.")

        result = _create_storyboard_prompt_rollback(s, shot, target, req)
        result["recommended_restore_version"] = recommendation
        return result


def _preview_storyboard_machine_prompt_export(book_id: int, shot, target_model: str) -> dict:
    meta_info = safe_json_loads(shot.meta_info) if shot.meta_info else {}
    if not isinstance(meta_info, dict):
        meta_info = {}

    seed = {
        "shot_id": str(shot.shot_id),
        "scene_name": str(shot.scene_name or "").strip(),
        "duration": int(shot.duration or 3),
        "camera_angle": str(shot.camera_angle or "MS").strip(),
        "camera_movement": str(shot.camera_movement or "static").strip(),
        "transition": str(shot.transition or "cut").strip(),
        "start_state": str(shot.start_state or "").strip(),
        "action_process": str(shot.action_process or "").strip(),
        "end_state": str(shot.end_state or "").strip(),
        "dialogue": str(shot.dialogue or "").strip(),
        "style_key": "default",
    }
    structured = _auto_bind_structured_shot_assets(
        book_id,
        int(shot.episode),
        _derive_structured_shot_payload(meta_info, seed),
        seed,
    )
    asset_link_summary = _build_storyboard_reference_summary(
        _load_asset_links(shot.asset_links),
        str(shot.scene_name or "").strip(),
    )
    compile_context = _build_prompt_compile_context_v2(
        book_id,
        shot,
        structured,
        {},
        asset_link_summary,
    )
    compile_context["target_model"] = target_model
    compile_context["reference_summary"] = _build_storyboard_reference_summary_from_bound_assets(
        compile_context.get("bound_assets", []),
        str(compile_context.get("scene_name") or shot.scene_name or "").strip(),
    )

    from core.machine_prompt import (
        build_director_shot_text,
        compile_machine_prompt,
        export_generic_zh_video_webui,
        export_machine_prompt,
        export_minimax_h3_webui,
    )
    from core.prompt_ir import build_shot_ir_from_context, serialize_shot_ir
    from core.rule_compiler import compile_rules

    shot_ir = build_shot_ir_from_context(compile_context)
    shot_ir = compile_rules(shot_ir, compile_context.get("production_skill", {}))
    system_director_shot_text = build_director_shot_text(shot_ir)
    director_state = meta_info.get("director_shot_language", {}) if isinstance(meta_info.get("director_shot_language", {}), dict) else {}
    user_director_shot_text = str(director_state.get("text") or "").strip()
    director_shot_text = user_director_shot_text or system_director_shot_text
    machine_prompt = compile_machine_prompt(
        shot_ir,
        reference_images=compile_context.get("reference_images", []),
        reference_summary=compile_context.get("reference_summary", ""),
        director_shot_text=director_shot_text,
    )
    return {
        "mode": "readonly_machine_prompt_export_preview",
        "book_id": book_id,
        "episode": int(shot.episode),
        "shot_id": int(shot.shot_id),
        "scene_name": str(shot.scene_name or "").strip(),
        "target_model": target_model,
        "api_submission": False,
        "source_layers": {
            "director_shot_text_is_user_editable": True,
            "director_shot_text_source": "user_override" if user_director_shot_text else "system_generated",
            "has_user_director_shot_override": bool(user_director_shot_text),
            "machine_prompt_is_compiled": True,
            "model_export_is_submission_ready_but_not_submitted": True,
        },
        "director_shot_text": director_shot_text,
        "system_director_shot_text": system_director_shot_text,
        "structured_shot": structured,
        "shot_ir": serialize_shot_ir(shot_ir),
        "machine_prompt": machine_prompt,
        "model_exports": {
            target_model: export_machine_prompt(machine_prompt, target_model),
            "minimax-h3": export_minimax_h3_webui(machine_prompt),
            "generic-zh-video": export_generic_zh_video_webui(machine_prompt),
        },
        "bound_asset_count": len(compile_context.get("bound_assets", [])),
        "reference_image_count": len(compile_context.get("reference_images", [])),
        "warnings": compile_context.get("warnings", []),
    }


@app.get("/api/books/{book_id}/storyboard/{episode}/{shot_id}/machine-prompt-export")
def get_storyboard_machine_prompt_export(
    book_id: int,
    episode: int,
    shot_id: str,
    target_model: str = Query(default="minimax-h3", alias="target_model"),
):
    from models import Session, StoryboardShot

    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if not shot:
            raise HTTPException(status_code=404, detail="Storyboard shot not found")
        return _preview_storyboard_machine_prompt_export(book_id, shot, str(target_model or "minimax-h3").strip() or "minimax-h3")


@app.patch("/api/books/{book_id}/storyboard/{episode}/{shot_id}/director-shot-text")
def update_storyboard_director_shot_text(
    book_id: int,
    episode: int,
    shot_id: str,
    req: StoryboardDirectorShotTextUpdateRequest,
    target_model: str = Query(default="minimax-h3", alias="target_model"),
):
    from models import Session, StoryboardShot

    target_model = str(target_model or "minimax-h3").strip() or "minimax-h3"
    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if not shot:
            raise HTTPException(status_code=404, detail="Storyboard shot not found")

        meta_info = safe_json_loads(shot.meta_info) if shot.meta_info else {}
        if not isinstance(meta_info, dict):
            meta_info = {}

        if req.reset_to_system:
            meta_info.pop("director_shot_language", None)
        else:
            director_text = str(req.director_shot_text or "").strip()
            if not director_text:
                raise HTTPException(status_code=400, detail="director_shot_text is required unless reset_to_system is true")
            meta_info["director_shot_language"] = {
                "text": director_text,
                "source": "user_override",
                "operator_name": str(req.operator_name or "user").strip() or "user",
                "updated_at": datetime.utcnow().isoformat(),
                "does_not_overwrite_shot_schema": True,
                "does_not_create_prompt_version": True,
            }

        shot.meta_info = json.dumps(meta_info, ensure_ascii=False)
        shot.updated_at = datetime.utcnow()
        s.commit()
        s.refresh(shot)
        return _preview_storyboard_machine_prompt_export(book_id, shot, target_model)


@app.post("/api/books/{book_id}/storyboard/{episode}/{shot_id}/machine-prompt-export-records")
def create_storyboard_machine_prompt_export_record(
    book_id: int,
    episode: int,
    shot_id: str,
    req: StoryboardMachinePromptExportRecordRequest,
):
    from models import ProductionExportRecord, Session, StoryboardShot

    target_model = str(req.target_model or "minimax-h3").strip() or "minimax-h3"
    export_channel = str(req.export_channel or "webui").strip() or "webui"
    now = datetime.utcnow()

    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if not shot:
            raise HTTPException(status_code=404, detail="Storyboard shot not found")

        preview = _preview_storyboard_machine_prompt_export(book_id, shot, target_model)
        scene_name = str(preview.get("scene_name") or getattr(shot, "scene_name", "") or "").strip()
        summary_parts = [
            f"第 {int(getattr(shot, 'episode', episode) or episode)} 集",
            f"镜头 {getattr(shot, 'shot_id', shot_id)}",
        ]
        if scene_name:
            summary_parts.append(scene_name)
        summary_parts.append(f"{target_model} {export_channel.upper()} 机器提示词导出快照")
        summary_parts.append("API 未提交")

        meta_info = {
            "record_type": "storyboard_machine_prompt_export",
            "api_submission": False,
            "target_model": target_model,
            "export_channel": export_channel,
            "operator_name": str(req.operator_name or "user").strip() or "user",
            "notes": str(req.notes or "").strip(),
            "book_id": book_id,
            "episode": int(getattr(shot, "episode", episode) or episode),
            "shot_id": int(getattr(shot, "shot_id", 0) or 0),
            "scene_name": scene_name,
            "director_shot_text": preview.get("director_shot_text", ""),
            "machine_prompt": preview.get("machine_prompt", {}),
            "model_exports": preview.get("model_exports", {}),
            "reference_image_count": int(preview.get("reference_image_count") or 0),
            "bound_asset_count": int(preview.get("bound_asset_count") or 0),
            "warnings": preview.get("warnings", []),
            "source_layers": preview.get("source_layers", {}),
        }

        row = ProductionExportRecord(
            book_id=book_id,
            export_format=f"storyboard-machine-prompt-{target_model}-{export_channel}",
            status="completed",
            total_shots=1,
            deliverable_shots=1,
            pending_review_shots=0,
            blocked_shots=0,
            summary=" · ".join(summary_parts),
            meta_info=json.dumps(meta_info, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        return _serialize_production_export_record(row)


@app.post("/api/books/{book_id}/storyboard/{episode}/{shot_id}/machine-prompt-api-submissions")
def create_storyboard_machine_prompt_api_submission_task(
    book_id: int,
    episode: int,
    shot_id: str,
    req: StoryboardMachinePromptApiSubmissionRequest,
):
    from models import Book, Session, StoryboardShot

    target_model = str(req.target_model or "minimax-h3").strip() or "minimax-h3"
    export_channel = str(req.export_channel or "api").strip() or "api"
    submission_mode = str(req.submission_mode or "task_intent_only").strip() or "task_intent_only"
    now = datetime.utcnow()

    with Session() as s:
        book = s.query(Book).filter(Book.id == book_id).first()
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if not shot:
            raise HTTPException(status_code=404, detail="Storyboard shot not found")

    export_payload = req.export_payload if isinstance(req.export_payload, dict) else {}
    model_exports = export_payload.get("model_exports") if isinstance(export_payload.get("model_exports"), dict) else {}
    target_export = model_exports.get(target_model) if isinstance(model_exports.get(target_model), dict) else {}
    fields = target_export.get("fields") if isinstance(target_export.get("fields"), dict) else {}
    prompt_text = str(
        fields.get("integrated_multimodal_description")
        or target_export.get("prompt")
        or export_payload.get("director_shot_text")
        or ""
    ).strip()

    task_id = f"mpapi-{uuid.uuid4().hex[:12]}"
    task_state = {
        "task_id": task_id,
        "task_kind": "creative-machine_prompt_api_submission",
        "kind": "machine_prompt_api_submission",
        "target_kind": "machine_prompt_api_submission",
        "status": "queued",
        "progress": 5,
        "book_id": book_id,
        "episode": episode,
        "shot_id": str(shot_id),
        "target_model": target_model,
        "export_channel": export_channel,
        "submission_mode": submission_mode,
        "generation_chain": "machine_prompt_api_submission",
        "provider": "pending-generation-adapter",
        "uses_mock": False,
        "external_task_id": None,
        "external_status": "waiting_for_generation_adapter",
        "api_submission": True,
        "actual_provider_submission": False,
        "has_manual_export_draft": bool(req.has_manual_export_draft),
        "source_export_record_id": req.source_export_record_id,
        "operator_name": str(req.operator_name or "user").strip() or "user",
        "notes": str(req.notes or "").strip(),
        "request_payload": {
            "book_id": book_id,
            "episode": episode,
            "shot_id": str(shot_id),
            "target_model": target_model,
            "export_channel": export_channel,
            "submission_mode": submission_mode,
            "generation_chain": "machine_prompt_api_submission",
            "api_submission": True,
            "actual_provider_submission": False,
            "source_export_record_id": req.source_export_record_id,
            "has_manual_export_draft": bool(req.has_manual_export_draft),
            "export_payload": export_payload,
        },
        "prompt_encoding_audit": _build_provider_prompt_encoding_audit(prompt_text),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    _creative_tasks[task_id] = task_state
    _stamp_creative_task_state(task_state, created=True)
    return {
        "task_id": task_id,
        "status": task_state["status"],
        "progress": task_state["progress"],
        "book_id": book_id,
        "episode": episode,
        "shot_id": str(shot_id),
        "target_model": target_model,
        "export_channel": export_channel,
        "generation_chain": "machine_prompt_api_submission",
        "external_status": task_state["external_status"],
        "api_submission": True,
        "actual_provider_submission": False,
        "has_manual_export_draft": bool(req.has_manual_export_draft),
    }


@app.post("/api/books/{book_id}/storyboard/{episode}/{shot_id}/compile-prompts")
def compile_storyboard_prompts(book_id: int, episode: int, shot_id: str, req: StoryboardPromptCompileRequest):
    from models import Session, StoryboardShot

    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if not shot:
            raise HTTPException(status_code=404, detail="Storyboard shot not found")
        shot_meta = safe_json_loads(shot.meta_info) if shot.meta_info else {}
        if not isinstance(shot_meta, dict):
            shot_meta = {}
        prompt_compiler_meta = shot_meta.get("prompt_compiler", {}) if isinstance(shot_meta.get("prompt_compiler", {}), dict) else {}
        if prompt_compiler_meta.get("locked") and not req.force:
            raise HTTPException(status_code=409, detail="Storyboard prompt version is locked. Unlock or force compile to continue.")

        result = _persist_storyboard_prompt_compile(s, book_id, episode, shot, req.compile_reason)
        s.commit()
        s.refresh(result["row"])

        return {
            "book_id": book_id,
            "episode": episode,
            "shot_id": shot.shot_id,
            "version": result["row"].version,
            "prompt_static": result["row"].prompt_static,
            "prompt_motion": result["row"].prompt_motion,
            "negative_prompt": result["row"].negative_prompt,
            "acceptance_feedback": result["compiled"].get("acceptance_feedback", {}),
            "locked_reference_summary": result["compiled"].get("locked_reference_summary", {}),
            "prompt_compile_context": result["compiled"].get("prompt_compile_context", {}),
            "used_assets": result["compiled"].get("used_assets", []),
            "reference_images": result["compiled"].get("reference_images", []),
            "reference_asset_ids": result["compiled"].get("reference_asset_ids", []),
            "compiler_warnings": result["compiled"].get("compiler_warnings", []),
            "compiler_diagnostics": result["compiled"].get("compiler_diagnostics", {}),
            "repair_attempted": bool(result["compiled"].get("repair_attempted")),
        }


async def _run_storyboard_prompt_compile_task(
    task_id: str,
    book_id: int,
    episode: int,
    shot_id: str,
    compile_reason: str,
):
    from models import Session, StoryboardShot

    task_state = _storyboard_prompt_compile_tasks[task_id]
    try:
        task_state["status"] = "running"
        task_state["progress"] = 15
        _stamp_creative_task_state(task_state)

        with Session() as s:
            shot = s.query(StoryboardShot).filter(
                StoryboardShot.book_id == book_id,
                StoryboardShot.episode == episode,
                StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
            ).first()
            if not shot:
                raise RuntimeError("Storyboard shot not found")

            task_state["progress"] = 45
            _stamp_creative_task_state(task_state)
            result = _persist_storyboard_prompt_compile(s, book_id, episode, shot, compile_reason)
            s.commit()
            s.refresh(result["row"])

            compiled = result["compiled"]
            task_state["status"] = "done"
            task_state["progress"] = 100
            task_state["prompt_version"] = result["row"].version
            task_state["version"] = result["row"].version
            task_state["compile_reason"] = compile_reason
            task_state["repair_attempted"] = bool(compiled.get("repair_attempted"))
            task_state["compiler_diagnostics"] = compiled.get("compiler_diagnostics", {})
            task_state["compiler_warnings"] = compiled.get("compiler_warnings", [])
            task_state["reference_asset_ids"] = compiled.get("reference_asset_ids", [])
            task_state["result"] = {
                "book_id": book_id,
                "episode": episode,
                "shot_id": shot.shot_id,
                "version": result["row"].version,
                "prompt_static": result["row"].prompt_static,
                "prompt_motion": result["row"].prompt_motion,
                "negative_prompt": result["row"].negative_prompt,
                "repair_attempted": bool(compiled.get("repair_attempted")),
            }
            _stamp_creative_task_state(task_state)
    except Exception as exc:
        task_state = _storyboard_prompt_compile_tasks[task_id]
        task_state["status"] = "error"
        task_state["progress"] = max(int(task_state.get("progress") or 0), 15)
        task_state["error"] = str(exc)
        _stamp_creative_task_state(task_state)


@app.post("/api/books/{book_id}/storyboard/{episode}/{shot_id}/compile-prompts/async")
async def compile_storyboard_prompts_async(
    book_id: int,
    episode: int,
    shot_id: str,
    req: StoryboardPromptCompileRequest,
    bg: BackgroundTasks,
):
    from models import Session, StoryboardShot

    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if not shot:
            raise HTTPException(status_code=404, detail="Storyboard shot not found")

        shot_meta = safe_json_loads(shot.meta_info) if shot.meta_info else {}
        if not isinstance(shot_meta, dict):
            shot_meta = {}
        prompt_compiler_meta = shot_meta.get("prompt_compiler", {}) if isinstance(shot_meta.get("prompt_compiler", {}), dict) else {}
        if prompt_compiler_meta.get("locked") and not req.force:
            raise HTTPException(status_code=409, detail="Storyboard prompt version is locked. Unlock or force compile to continue.")

    task_id = uuid.uuid4().hex[:12]
    _storyboard_prompt_compile_tasks[task_id] = {
        "task_id": task_id,
        "kind": "storyboard-prompt-compile",
        "status": "queued",
        "progress": 0,
        "book_id": book_id,
        "episode": episode,
        "shot_id": _coerce_storyboard_shot_id(shot_id),
        "compile_reason": req.compile_reason,
        "prompt_version": None,
        "error": None,
    }
    _stamp_creative_task_state(_storyboard_prompt_compile_tasks[task_id], created=True)

    def _run_compile_in_thread():
        asyncio.run(_run_storyboard_prompt_compile_task(task_id, book_id, episode, shot_id, req.compile_reason))

    bg.add_task(_run_compile_in_thread)
    return {
        "task_id": task_id,
        "status": "queued",
        "book_id": book_id,
        "episode": episode,
        "shot_id": _coerce_storyboard_shot_id(shot_id),
        "compile_reason": req.compile_reason,
    }


@app.get("/api/storyboard-prompt-compile-tasks/{task_id}")
def get_storyboard_prompt_compile_task(task_id: str):
    task = _storyboard_prompt_compile_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.patch("/api/books/{book_id}/storyboard/{episode}/{shot_id}/prompt-lock")
def set_storyboard_prompt_lock(book_id: int, episode: int, shot_id: str, req: StoryboardPromptLockRequest):
    from models import Session, StoryboardShot

    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if not shot:
            raise HTTPException(status_code=404, detail="Storyboard shot not found")

        shot_meta = safe_json_loads(shot.meta_info) if shot.meta_info else {}
        if not isinstance(shot_meta, dict):
            shot_meta = {}
        prompt_compiler_meta = shot_meta.get("prompt_compiler", {}) if isinstance(shot_meta.get("prompt_compiler", {}), dict) else {}
        prompt_compiler_meta["locked"] = req.locked
        if req.locked:
            prompt_compiler_meta["locked_version"] = prompt_compiler_meta.get("latest_version")
        else:
            prompt_compiler_meta["locked_version"] = None
        shot_meta["prompt_compiler"] = prompt_compiler_meta
        shot.meta_info = json.dumps(shot_meta, ensure_ascii=False)
        shot.updated_at = datetime.utcnow()
        s.commit()

        return {
            "book_id": book_id,
            "episode": episode,
            "shot_id": shot.shot_id,
            "locked": bool(prompt_compiler_meta.get("locked")),
            "locked_version": prompt_compiler_meta.get("locked_version"),
        }


async def _queue_storyboard_generation_task(
    book_id: int,
    episode: int,
    shot_id: str,
    kind: str,
    req: StoryboardGenerationRequest,
    bg: BackgroundTasks,
):
    from models import Session, StoryboardShot

    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == _coerce_storyboard_shot_id(shot_id),
        ).first()
        if not shot:
            raise HTTPException(status_code=404, detail="Storyboard shot not found")

        if req.compile_if_missing and (not shot.visual_prompt_static or not shot.visual_prompt_motion):
            _persist_storyboard_prompt_compile(s, book_id, episode, shot, f"auto-{kind}")

        prompt = (shot.visual_prompt_static if kind == "image" else shot.visual_prompt_motion or "").strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="Storyboard prompts are empty. Compile prompts first.")

        negative_prompt = (shot.visual_prompt_final or "").strip()
        asset_links = _load_asset_links(shot.asset_links)
        first_frame_asset_id = ""
        first_frame_url = ""
        if kind == "video":
            video_context = _resolve_storyboard_video_generation_context(shot, req)
            asset_links = video_context["asset_links"]
            reference_asset_ids = video_context["reference_asset_ids"]
            reference_images = video_context["reference_images"]
            first_frame_asset_id = video_context["first_frame_asset_id"]
            first_frame_url = video_context["first_frame_url"]
        else:
            reference_asset_ids, reference_images = _resolve_storyboard_reference_payloads(shot, req.reference_asset_ids)

        task_id = uuid.uuid4().hex[:12]
        creative_req = CreativeGenerationRequest(
            book_id=book_id,
            episode=episode,
            shot_id=str(shot.shot_id),
            source_node_id=f"production-shot-{episode}-{shot.shot_id}",
            source_asset_id=first_frame_asset_id,
            first_frame_asset_id=first_frame_asset_id,
            first_frame_url=first_frame_url,
            asset_scope="shot",
            asset_subject=str(shot.shot_id),
            target_kind=kind,
            prompt=prompt,
            negative_prompt=negative_prompt,
            model_profile_id=req.model_profile_id,
            reference_asset_ids=reference_asset_ids,
            reference_images=reference_images,
            aspect_ratio=req.aspect_ratio,
            duration_seconds=req.duration_seconds,
        )

        try:
            profile = _resolve_creative_profile(creative_req, "image" if kind == "image" else "video")
        except (ModelProfileError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        _creative_tasks[task_id] = {
            "task_id": task_id,
            "status": "queued",
            "progress": 0,
            "target_kind": kind,
            "book_id": book_id,
            "episode": episode,
            "shot_id": str(shot.shot_id),
            "version": _next_asset_version(book_id, episode, str(shot.shot_id), kind),
            "model_profile_id": profile.get("id"),
            "provider": profile.get("provider"),
            "uses_mock": profile.get("provider") == "prototype-task-adapter",
            "prompt_version": safe_json_loads(shot.meta_info).get("prompt_compiler", {}).get("latest_version") if shot.meta_info else None,
            "negative_prompt": negative_prompt,
            "first_frame_asset_id": first_frame_asset_id,
            "first_frame_url": first_frame_url,
            "reference_asset_ids": reference_asset_ids,
            "reference_images": reference_images,
            "provider_task_mode": "image_to_video" if kind == "video" and first_frame_asset_id else ("reference_to_video" if kind == "video" and reference_asset_ids else "text_to_video" if kind == "video" else ""),
            "external_task_id": None,
            "external_status": None,
            "poll_attempts": 0,
            "provider_response": None,
            "provider_request_payload": None,
            "generation_chain": (req.generation_chain or "").strip() or None,
            "triggered_by_prompt_recompile": bool(req.triggered_by_prompt_recompile),
            "prompt_recompile_reason": (req.prompt_recompile_reason or "").strip() or None,
            "prompt_recompile_task_id": (req.prompt_recompile_task_id or "").strip() or None,
            "prompt_recompile_version": req.prompt_recompile_version,
        }
        _store_creative_task_request(_creative_tasks[task_id], creative_req, kind)
        if req.generation_chain or req.triggered_by_prompt_recompile or req.prompt_recompile_task_id or req.prompt_recompile_version is not None:
            request_payload = _creative_tasks[task_id].get("request_payload")
            if isinstance(request_payload, dict):
                request_payload["generation_chain"] = (req.generation_chain or "").strip() or None
                request_payload["triggered_by_prompt_recompile"] = bool(req.triggered_by_prompt_recompile)
                request_payload["prompt_recompile_reason"] = (req.prompt_recompile_reason or "").strip() or None
                request_payload["prompt_recompile_task_id"] = (req.prompt_recompile_task_id or "").strip() or None
                request_payload["prompt_recompile_version"] = req.prompt_recompile_version
        s.commit()

    bg.add_task(_run_creative_task, task_id, kind, creative_req)
    return {
        "task_id": task_id,
        "status": "queued",
        "prompt": creative_req.prompt,
        "negative_prompt": negative_prompt,
        "first_frame_asset_id": first_frame_asset_id,
        "first_frame_url": first_frame_url,
        "reference_asset_ids": reference_asset_ids,
        "reference_images": reference_images,
        "model_profile_id": profile.get("id"),
        "uses_mock": profile.get("provider") == "prototype-task-adapter",
    }


@app.post("/api/books/{book_id}/storyboard/{episode}/{shot_id}/generate-frame")
async def generate_storyboard_frame(book_id: int, episode: int, shot_id: str, req: StoryboardGenerationRequest, bg: BackgroundTasks):
    return await _queue_storyboard_generation_task(book_id, episode, shot_id, "image", req, bg)


@app.post("/api/books/{book_id}/storyboard/{episode}/{shot_id}/generate-video")
async def generate_storyboard_video(book_id: int, episode: int, shot_id: str, req: StoryboardGenerationRequest, bg: BackgroundTasks):
    return await _queue_storyboard_generation_task(book_id, episode, shot_id, "video", req, bg)


@app.get("/api/books/{book_id}/storyboard/{episode}/{shot_id}/acceptance-records")
def get_storyboard_acceptance_records(book_id: int, episode: int, shot_id: str):
    from models import Session, StoryboardAcceptanceRecord

    coerced_shot_id = _coerce_storyboard_shot_id(shot_id)
    with Session() as s:
        rows = s.query(StoryboardAcceptanceRecord).filter(
            StoryboardAcceptanceRecord.book_id == book_id,
            StoryboardAcceptanceRecord.episode == episode,
            StoryboardAcceptanceRecord.shot_id == coerced_shot_id,
        ).order_by(StoryboardAcceptanceRecord.created_at.desc(), StoryboardAcceptanceRecord.id.desc()).all()
        return {
            "book_id": book_id,
            "episode": episode,
            "shot_id": coerced_shot_id,
            "records": [
                {
                    "id": row.id,
                    "asset_kind": row.asset_kind,
                    "asset_id": row.asset_id,
                    "status": row.status,
                    "failure_tags": _json_loads_list(row.failure_tags),
                    "notes": row.notes,
                    "meta_info": safe_json_loads(row.meta_info) if row.meta_info else {},
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
                for row in rows
            ],
        }


@app.post("/api/books/{book_id}/storyboard/{episode}/{shot_id}/acceptance-records")
def create_storyboard_acceptance_record(book_id: int, episode: int, shot_id: str, req: StoryboardAcceptanceRequest):
    from models import Session, StoryboardAcceptanceRecord, StoryboardShot

    now = datetime.utcnow()
    coerced_shot_id = _coerce_storyboard_shot_id(shot_id)
    with Session() as s:
        shot = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == coerced_shot_id,
        ).first()
        if not shot:
            raise HTTPException(status_code=404, detail="Storyboard shot not found")

        row = StoryboardAcceptanceRecord(
            book_id=book_id,
            episode=episode,
            shot_id=coerced_shot_id,
            asset_kind=req.asset_kind,
            asset_id=req.asset_id,
            status=req.status,
            failure_tags=json.dumps([tag for tag in req.failure_tags if str(tag).strip()], ensure_ascii=False),
            notes=req.notes,
            meta_info=json.dumps(req.meta_info, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
        s.add(row)

        shot_meta = safe_json_loads(shot.meta_info) if shot.meta_info else {}
        if not isinstance(shot_meta, dict):
            shot_meta = {}
        shot_meta["acceptance"] = {
            "status": req.status,
            "asset_kind": req.asset_kind,
            "asset_id": req.asset_id,
            "failure_tags": [tag for tag in req.failure_tags if str(tag).strip()],
            "notes": req.notes,
            "updated_at": now.isoformat(),
        }
        shot.meta_info = json.dumps(shot_meta, ensure_ascii=False)
        shot.updated_at = now
        s.commit()
        s.refresh(row)

        return {
            "id": row.id,
            "asset_kind": row.asset_kind,
            "asset_id": row.asset_id,
            "status": row.status,
            "failure_tags": _json_loads_list(row.failure_tags),
            "notes": row.notes,
            "meta_info": safe_json_loads(row.meta_info) if row.meta_info else {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


def _normalize_export_format_label(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "JSON"
    if normalized == "pdf":
        return "PDF"
    if normalized == "json":
        return "JSON"
    if normalized == "delivery":
        return "交付快照"
    return normalized.upper()


def _looks_corrupted_export_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text == "[object Object]":
        return True
    if "????" in text or "锟" in text:
        return True
    if "manual verification snapshot" in text.lower():
        return True
    if " 璺" in text:
        return True
    return any(token in text for token in ["閸", "闂", "鐠", "缁", "瀵板懘", "閺堫亝"])


def _normalize_export_record_summary(row, meta_info: dict) -> str:
    raw_summary = str(getattr(row, "summary", "") or "").strip()
    if raw_summary and not _looks_corrupted_export_text(raw_summary):
        return raw_summary

    episode = int(meta_info.get("episode") or 0)
    format_label = _normalize_export_format_label(getattr(row, "export_format", ""))
    blocked_reasons = meta_info.get("blocked_reasons", [])
    if not isinstance(blocked_reasons, list):
        blocked_reasons = []
    blocked_reasons = [str(item).strip() for item in blocked_reasons if str(item).strip()]
    blocked_reasons = [item for item in blocked_reasons if not _looks_corrupted_export_text(item)]
    if not blocked_reasons:
        legacy_issues = meta_info.get("issues", [])
        if isinstance(legacy_issues, list):
            blocked_reasons = [
                str(item).strip()
                for item in legacy_issues
                if str(item).strip() and not _looks_corrupted_export_text(str(item))
            ]
    if not blocked_reasons and int(getattr(row, "blocked_shots", 0) or 0) > 0:
        blocked_reasons = [f"历史阻塞镜头 {int(getattr(row, 'blocked_shots', 0) or 0)} 个，待补录明细"]

    script_status = str(meta_info.get("script_status") or "").strip()
    if not script_status:
        script_locked = bool(meta_info.get("script_locked"))
        script_released = bool(meta_info.get("script_released"))
        if script_locked and script_released:
            script_status = "已锁稿并放行"
        elif script_locked:
            script_status = "待放行"
        elif "script_locked" in meta_info or "script_released" in meta_info:
            script_status = "待锁稿"

    parts: list[str] = []
    if episode > 0:
        parts.append(f"第 {episode} 集")
    if script_status:
        parts.append(f"剧本 {script_status}")
    parts.append(
        f"可交付镜头 {int(getattr(row, 'deliverable_shots', 0) or 0)}/{int(getattr(row, 'total_shots', 0) or 0)}"
    )

    pending_review_shots = int(getattr(row, "pending_review_shots", 0) or 0)
    if pending_review_shots > 0:
        parts.append(f"待复核 {pending_review_shots}")

    if blocked_reasons:
        parts.append(" / ".join(blocked_reasons[:3]))
    else:
        parts.append("已登记交付版本" if getattr(row, "status", "") == "completed" else f"{format_label} 快照")

    return " | ".join(parts)


def _serialize_production_export_record(row) -> dict:
    meta_info = safe_json_loads(row.meta_info) if row.meta_info else {}
    if not isinstance(meta_info, dict):
        meta_info = {}
    return {
        "id": row.id,
        "book_id": row.book_id,
        "export_format": row.export_format,
        "format_label": _normalize_export_format_label(getattr(row, "export_format", "")),
        "status": row.status,
        "total_shots": row.total_shots,
        "deliverable_shots": row.deliverable_shots,
        "pending_review_shots": row.pending_review_shots,
        "blocked_shots": row.blocked_shots,
        "summary": _normalize_export_record_summary(row, meta_info),
        "meta_info": meta_info,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _get_production_export_record_asset_type(record: dict) -> str:
    meta_info = record.get("meta_info") if isinstance(record.get("meta_info"), dict) else {}
    record_type = str(meta_info.get("record_type") or "").strip()
    export_format = str(record.get("export_format") or "").strip()
    if record_type == "storyboard_machine_prompt_export" or export_format.startswith("storyboard-machine-prompt-"):
        return "machine_prompt"
    return "delivery_package"


def _production_export_record_matches_record_type(record: dict, record_type_filter: str | None) -> bool:
    record_type_filter = str(record_type_filter or "").strip().lower()
    if not record_type_filter or record_type_filter == "all":
        return True
    meta_info = record.get("meta_info") if isinstance(record.get("meta_info"), dict) else {}
    meta_record_type = str(meta_info.get("record_type") or "").strip().lower()
    asset_type = _get_production_export_record_asset_type(record)
    if record_type_filter in {"machine_prompt", "delivery_package"}:
        return asset_type == record_type_filter
    return meta_record_type == record_type_filter


def _production_export_record_matches_format(record: dict, format_filter: str | None) -> bool:
    format_filter = str(format_filter or "").strip().lower()
    if not format_filter or format_filter == "all":
        return True
    export_format = str(record.get("export_format") or "").strip().lower()
    format_label = str(record.get("format_label") or "").strip().lower()
    normalized_filter_label = _normalize_export_format_label(format_filter).lower()
    return format_filter in {export_format, format_label} or normalized_filter_label == format_label


def _build_production_export_record_search_text(record: dict) -> str:
    meta_info = record.get("meta_info") if isinstance(record.get("meta_info"), dict) else {}
    search_items = [
        record.get("id"),
        record.get("episode"),
        record.get("status"),
        record.get("export_format"),
        record.get("format_label"),
        record.get("summary"),
        meta_info.get("record_type"),
        meta_info.get("target_model"),
        meta_info.get("export_channel"),
        meta_info.get("scene_name"),
        meta_info.get("episode"),
        meta_info.get("shot_id"),
        meta_info.get("director_shot_text"),
    ]
    for key in ("blocked_reasons", "blockedReasons", "issues", "warnings"):
        value = meta_info.get(key)
        if isinstance(value, list):
            search_items.extend(value)
        elif value:
            search_items.append(value)
    return " ".join(str(item or "").lower() for item in search_items)


def _production_export_record_matches_query(record: dict, query_text: str | None) -> bool:
    terms = [term for term in str(query_text or "").strip().lower().split() if term]
    if not terms:
        return True
    search_text = _build_production_export_record_search_text(record)
    return all(term in search_text for term in terms)


def _production_export_record_matches_filters(
    record: dict,
    *,
    record_type: str | None,
    episode: int | None,
    status: str | None,
    export_format: str | None,
    query_text: str | None,
) -> bool:
    meta_info = record.get("meta_info") if isinstance(record.get("meta_info"), dict) else {}
    if episode is not None:
        try:
            record_episode = int(meta_info.get("episode") or 0)
        except (TypeError, ValueError):
            record_episode = 0
        if record_episode != episode:
            return False

    status_filter = str(status or "").strip().lower()
    if status_filter and status_filter != "all" and str(record.get("status") or "").strip().lower() != status_filter:
        return False

    if not _production_export_record_matches_record_type(record, record_type):
        return False
    if not _production_export_record_matches_format(record, export_format):
        return False
    if not _production_export_record_matches_query(record, query_text):
        return False
    return True


def _is_storyboard_shot_deliverable_for_export(shot) -> bool:
    asset_links = _load_asset_links(getattr(shot, "asset_links", None))
    adopted_video = _find_adopted_shot_asset(asset_links, "videos")
    meta_info = safe_json_loads(getattr(shot, "meta_info", None)) if getattr(shot, "meta_info", None) else {}
    acceptance = meta_info.get("acceptance", {}) if isinstance(meta_info, dict) else {}
    acceptance_status = str(acceptance.get("status") or "").strip().lower()
    return bool(adopted_video) and acceptance_status in {"approved", "accepted"}


def _build_export_shot_payload(shot) -> dict:
    asset_links = _load_asset_links(getattr(shot, "asset_links", None))
    meta_info = safe_json_loads(getattr(shot, "meta_info", None)) if getattr(shot, "meta_info", None) else {}
    acceptance = meta_info.get("acceptance", {}) if isinstance(meta_info, dict) else {}
    prompt_compiler = meta_info.get("prompt_compiler", {}) if isinstance(meta_info, dict) else {}
    reference_summary = _build_storyboard_reference_summary(asset_links, str(getattr(shot, "scene_name", "") or "").strip())
    adopted_image = _find_adopted_shot_asset(asset_links, "images") or {}
    adopted_video = _find_adopted_shot_asset(asset_links, "videos") or {}

    return {
        "episode": getattr(shot, "episode", ""),
        "shot_id": getattr(shot, "shot_id", ""),
        "scene_name": str(getattr(shot, "scene_name", "") or ""),
        "camera_angle": str(getattr(shot, "camera_angle", "") or ""),
        "camera_movement": str(getattr(shot, "camera_movement", "") or ""),
        "duration": str(getattr(shot, "duration", "") or ""),
        "dialogue": str(getattr(shot, "dialogue", "") or ""),
        "action_process": str(getattr(shot, "action_process", "") or ""),
        "prompt_version": prompt_compiler.get("latest_version") or "",
        "acceptance_status": str(acceptance.get("status") or ""),
        "acceptance_notes": str(acceptance.get("notes") or ""),
        "adopted_image_title": str(adopted_image.get("title") or adopted_image.get("id") or ""),
        "adopted_video_title": str(adopted_video.get("title") or adopted_video.get("id") or ""),
        "reference_summary_text": str(reference_summary.get("summary_text") or ""),
        "reference_count": int((reference_summary.get("counts") or {}).get("total") or 0),
    }


def _serialize_storyboard_output_row(
    s,
    book_id: int,
    shot,
    locations: list,
    makeups: list,
    reference_index: dict[tuple[str, str], list[dict]],
) -> dict:
    payload = {
        "episode": shot.episode,
        "shot_id": shot.shot_id,
        "scene_name": shot.scene_name,
        "dialogue": shot.dialogue,
        "duration": shot.duration,
        "camera_angle": shot.camera_angle,
        "camera_movement": shot.camera_movement,
        "transition": shot.transition,
        "lighting": shot.lighting,
        "sound_effects": __import__("json").loads(shot.sound_effects)
        if isinstance(shot.sound_effects, str) and shot.sound_effects.startswith("[")
        else [],
        "bgm_mood": shot.bgm_mood,
        "start_state": shot.start_state,
        "action_process": shot.action_process,
        "end_state": shot.end_state,
        "visual_prompt_static": shot.visual_prompt_static,
        "visual_prompt_motion": shot.visual_prompt_motion,
        "visual_prompt_final": shot.visual_prompt_final,
        "makeup_prompts": [
            {
                "character_name": m.character_name,
                "refined_outfit": m.refined_outfit,
                "refined_accessories": m.refined_accessories,
                "makeup_spec": m.makeup_spec,
                "hair_style": m.hair_style,
                "visual_prompt_zh": m.visual_prompt_zh,
            }
            for m in (__import__("copy").copy(makeups))
            if m.episode == shot.episode
        ],
    }
    sanitized_asset_links = (
        _sanitize_storyboard_asset_links(safe_json_loads(shot.asset_links), shot.scene_name)
        if shot.asset_links else {}
    )
    meta_info = safe_json_loads(shot.meta_info) if shot.meta_info else {}
    if not isinstance(meta_info, dict):
        meta_info = {}
    structured_shot = _auto_bind_structured_shot_assets(
        book_id,
        shot.episode,
        _derive_structured_shot_payload(meta_info, payload),
        payload,
    )
    prompt_compiler_meta = meta_info.get("prompt_compiler", {}) if isinstance(meta_info.get("prompt_compiler", {}), dict) else {}
    prompt_compiler_meta = _refresh_legacy_prompt_compile_meta(
        book_id,
        shot,
        structured_shot,
        prompt_compiler_meta,
    )
    acceptance_meta = meta_info.get("acceptance", {}) if isinstance(meta_info.get("acceptance", {}), dict) else {}
    prompt_compile_context = (
        prompt_compiler_meta.get("prompt_compile_context", {})
        if isinstance(prompt_compiler_meta.get("prompt_compile_context", {}), dict)
        else {}
    )
    scene_binding = (
        prompt_compile_context.get("asset_bindings", {}).get("scene", {})
        if isinstance(prompt_compile_context.get("asset_bindings", {}), dict)
        else {}
    )
    if not isinstance(scene_binding, dict):
        scene_binding = {}
    resolved_scene_name = (
        str(scene_binding.get("asset_name") or "").strip()
        or str(structured_shot.get("scene_name") or "").strip()
        or str(structured_shot.get("scene") or "").strip()
        or str(shot.scene_name or "").strip()
    )
    locked_reference_summary = prompt_compiler_meta.get("locked_reference_summary", {})
    has_locked_summary_content = (
        isinstance(locked_reference_summary, dict)
        and (
            bool(str(locked_reference_summary.get("summary_text") or "").strip())
            or bool(locked_reference_summary.get("scene"))
            or bool(locked_reference_summary.get("characters"))
            or bool(locked_reference_summary.get("props"))
            or bool(locked_reference_summary.get("all"))
        )
    )
    if not has_locked_summary_content:
        locked_reference_summary = _build_storyboard_reference_summary(
            sanitized_asset_links,
            resolved_scene_name,
        )
    prompt_version_audit = _build_storyboard_prompt_version_audit(prompt_compiler_meta)
    recommended_restore_version = None
    if prompt_compiler_meta.get("latest_version"):
        version_payloads = _build_storyboard_prompt_version_payloads(
            s,
            book_id,
            shot,
            prompt_compiler_meta.get("latest_version"),
            prompt_compiler_meta.get("locked_version"),
        )
        recommended_restore_version = _recommend_storyboard_restore_version(
            version_payloads,
            prompt_compiler_meta.get("latest_version"),
        )

    return {
        "episode": shot.episode,
        "shot_id": shot.shot_id,
        "scene_name": resolved_scene_name,
        "dialogue": shot.dialogue,
        "duration": shot.duration,
        "camera_angle": shot.camera_angle,
        "camera_movement": shot.camera_movement,
        "transition": shot.transition,
        "lighting": shot.lighting,
        "sound_effects": payload["sound_effects"],
        "bgm_mood": shot.bgm_mood,
        "start_state": shot.start_state,
        "action_process": shot.action_process,
        "end_state": shot.end_state,
        "visual_prompt_static": shot.visual_prompt_static,
        "visual_prompt_motion": shot.visual_prompt_motion,
        "visual_prompt_final": shot.visual_prompt_final,
        "asset_links": sanitized_asset_links,
        "assets": {
            "images": sanitized_asset_links.get("images", []) if isinstance(sanitized_asset_links.get("images", []), list) else [],
            "videos": sanitized_asset_links.get("videos", []) if isinstance(sanitized_asset_links.get("videos", []), list) else [],
            "audios": sanitized_asset_links.get("audios", []) if isinstance(sanitized_asset_links.get("audios", []), list) else [],
        },
        "asset_status": shot.asset_status,
        "meta_info": meta_info,
        "structured_shot": structured_shot,
        "negative_prompt": prompt_compiler_meta.get("negative_prompt", ""),
        "acceptance": acceptance_meta,
        "prompt_locked": bool(prompt_compiler_meta.get("locked", False)),
        "prompt_version": prompt_compiler_meta.get("latest_version"),
        "prompt_compile_context": prompt_compile_context,
        "used_assets": prompt_compiler_meta.get("used_assets", []),
        "reference_images": prompt_compiler_meta.get("reference_images", []),
        "reference_asset_ids": prompt_compiler_meta.get("reference_asset_ids", []),
        "compiler_warnings": prompt_compiler_meta.get("compiler_warnings", []),
        "compiler_diagnostics": prompt_compiler_meta.get("compiler_diagnostics", {}),
        "prompt_version_audit": prompt_version_audit,
        "recommended_restore_version": recommended_restore_version,
        "repair_attempted": bool(prompt_compiler_meta.get("repair_attempted", False)),
        "locked_reference_summary": locked_reference_summary,
        "makeup_prompts": _resolve_shot_makeup_payloads(
            s,
            book_id,
            shot,
            structured_shot,
            reference_index,
        ),
        "scene_prompt": (
            next(
                (
                    loc.visual_prompt_zh
                    or loc.core_prompt_zh
                    or ""
                )
                for loc in locations
                if loc.name == resolved_scene_name
            )
            if any(loc.name == resolved_scene_name for loc in locations)
            else ""
        ),
    }


def _build_production_export_pdf(book, scripts: list, storyboard_rows: list, summary: dict | None = None) -> bytes:
    try:
        from io import BytesIO
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as error:
        raise HTTPException(status_code=500, detail=f"PDF export dependency missing: {error}") from error

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ExportTitle", parent=styles["Title"], fontName="STSong-Light", fontSize=18, leading=24)
    body_style = ParagraphStyle("ExportBody", parent=styles["BodyText"], fontName="STSong-Light", fontSize=10, leading=14)
    small_style = ParagraphStyle("ExportSmall", parent=styles["BodyText"], fontName="STSong-Light", fontSize=8, leading=11)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    export_summary = summary if isinstance(summary, dict) else {}
    total_shots = int(export_summary.get("total_shots") or len(storyboard_rows))
    deliverable_shots = int(export_summary.get("deliverable_shots") or len(storyboard_rows))
    blocked_shots = int(export_summary.get("blocked_shots") or max(total_shots - deliverable_shots, 0))
    story = [
        Paragraph(f"{book.title} Production Export", title_style),
        Spacer(1, 4 * mm),
        Paragraph(f"Export time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC", body_style),
        Paragraph(f"Scripts: {len(scripts)} | Total shots: {total_shots}", body_style),
        Paragraph(f"Deliverable shots: {deliverable_shots} | Blocked shots: {blocked_shots}", body_style),
        Spacer(1, 6 * mm),
        Paragraph("Scripts", body_style),
        Spacer(1, 2 * mm),
    ]

    if scripts:
        for script in scripts:
            story.append(Paragraph(f"Episode {script.episode}", body_style))
            for line in str(script.content or "").splitlines():
                if line.strip():
                    story.append(Paragraph(line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), small_style))
            story.append(Spacer(1, 4 * mm))
    else:
        story.append(Paragraph("No script content available", small_style))
        story.append(Spacer(1, 4 * mm))

    shot_payloads = [_build_export_shot_payload(shot) for shot in storyboard_rows[:200]]

    story.append(Paragraph("Storyboard Table (approved shots with adopted video only)", body_style))
    table_rows = [["Ep", "Shot", "Scene", "Camera", "Prompt", "Acceptance", "Adopted Video", "Refs"]]
    for shot in shot_payloads:
        table_rows.append([
            str(shot["episode"]),
            str(shot["shot_id"]),
            str(shot["scene_name"]),
            f'{shot["camera_angle"]}/{shot["camera_movement"]}'[:24],
            f'v{shot["prompt_version"]}' if shot["prompt_version"] else "-",
            str(shot["acceptance_status"] or "-"),
            str(shot["adopted_video_title"] or "-")[:28],
            str(shot["reference_count"]),
        ])

    if len(table_rows) == 1:
        table_rows.append(["-", "-", "No deliverable shots", "", "", "", "", ""])

    table = Table(table_rows, repeatRows=1, colWidths=[12 * mm, 14 * mm, 28 * mm, 16 * mm, 22 * mm, 14 * mm, 32 * mm, 42 * mm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(table)
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Shot Delivery Details", body_style))

    if shot_payloads:
        for shot in shot_payloads:
            story.append(
                Paragraph(
                    f'E{shot["episode"]} / {shot["shot_id"]} / {shot["scene_name"] or "Unnamed scene"}',
                    body_style,
                )
            )
            story.append(
                Paragraph(
                    (
                        f'Camera: {shot["camera_angle"] or "-"} | Motion: {shot["camera_movement"] or "-"} | '
                        f'Duration: {shot["duration"] or "-"} | Prompt: {("v" + str(shot["prompt_version"])) if shot["prompt_version"] else "-"}'
                    ),
                    small_style,
                )
            )
            if shot["adopted_image_title"] or shot["adopted_video_title"]:
                story.append(
                    Paragraph(
                        f'Adopted frame: {shot["adopted_image_title"] or "-"} | Adopted video: {shot["adopted_video_title"] or "-"}',
                        small_style,
                    )
                )
            if shot["reference_summary_text"]:
                story.append(Paragraph(f'References: {shot["reference_summary_text"]}', small_style))
            if shot["dialogue"]:
                story.append(Paragraph(f'Dialogue: {shot["dialogue"][:160]}', small_style))
            if shot["action_process"]:
                story.append(Paragraph(f'Action: {shot["action_process"][:200]}', small_style))
            if shot["acceptance_status"] or shot["acceptance_notes"]:
                story.append(
                    Paragraph(
                        f'Acceptance: {shot["acceptance_status"] or "-"} | Notes: {shot["acceptance_notes"][:180] or "-"}',
                        small_style,
                    )
                )
            story.append(Spacer(1, 3 * mm))
    else:
        story.append(Paragraph("No deliverable shots are available in the current export scope.", small_style))

    doc.build(story)
    return buffer.getvalue()


@app.get("/api/books/{book_id}/export-records")
def get_production_export_records(
    book_id: int,
    record_type: str | None = Query(default=None),
    episode: int | None = Query(default=None),
    status: str | None = Query(default=None),
    export_format: str | None = Query(default=None, alias="format"),
    query: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    from models import ProductionExportRecord, Session

    with Session() as s:
        rows = s.query(ProductionExportRecord).filter(
            ProductionExportRecord.book_id == book_id,
        ).order_by(ProductionExportRecord.created_at.desc(), ProductionExportRecord.id.desc()).all()
        records = [
            record
            for record in (_serialize_production_export_record(row) for row in rows)
            if _production_export_record_matches_filters(
                record,
                record_type=record_type,
                episode=episode,
                status=status,
                export_format=export_format,
                query_text=query,
            )
        ]
        total = len(records)
        paged_records = records[offset : offset + limit] if limit is not None else records[offset:]
        return {
            "book_id": book_id,
            "records": paged_records,
            "total": total,
            "limit": limit,
            "offset": offset,
            "returned": len(paged_records),
            "has_more": offset + len(paged_records) < total,
            "filters": {
                "record_type": record_type,
                "episode": episode,
                "status": status,
                "format": export_format,
                "query": query,
            },
        }


@app.post("/api/books/{book_id}/export-records")
def create_production_export_record(book_id: int, req: ProductionExportRecordRequest):
    from models import Book, ProductionExportRecord, Session

    now = datetime.utcnow()
    with Session() as s:
        book = s.query(Book).filter(Book.id == book_id).first()
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        meta_info = dict(req.meta_info or {})
        episode_value = meta_info.get("episode")
        try:
            episode = int(episode_value) if episode_value is not None else None
        except (TypeError, ValueError):
            episode = None
        qa_gate = _build_qa_delivery_gate(s, book_id, episode)
        status = req.status
        blocked_shots = req.blocked_shots
        summary = req.summary
        if qa_gate["blocked"]:
            blocked_codes = _coerce_string_list(meta_info.get("blocked_codes"))
            if "qa_blocked" not in blocked_codes:
                blocked_codes.append("qa_blocked")
            blocked_reasons = _coerce_string_list(meta_info.get("blocked_reasons"))
            qa_blocked_reason = _build_qa_delivery_blocked_reason(qa_gate)
            if not any(str(item).startswith("QA 待处理") for item in blocked_reasons):
                blocked_reasons.append(qa_blocked_reason)
            meta_info["blocked_codes"] = blocked_codes
            meta_info["blocked_reasons"] = blocked_reasons
            meta_info["qa_delivery_gate"] = qa_gate
            status = "blocked"
            blocked_shots = max(int(blocked_shots or 0), 1)
            if not str(summary or "").strip() or req.status == "completed":
                summary = qa_blocked_reason
        elif qa_gate["total_issue_count"] > 0:
            meta_info["qa_delivery_gate"] = qa_gate

        row = ProductionExportRecord(
            book_id=book_id,
            export_format=req.export_format,
            status=status,
            total_shots=req.total_shots,
            deliverable_shots=req.deliverable_shots,
            pending_review_shots=req.pending_review_shots,
            blocked_shots=blocked_shots,
            summary=summary,
            meta_info=json.dumps(meta_info, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        return _serialize_production_export_record(row)


@app.get("/api/books/{book_id}/export-pdf")
def export_production_pdf(book_id: int, episode: int | None = Query(default=None)):
    from io import BytesIO
    from fastapi.responses import StreamingResponse
    from models import Book, Script, Session, StoryboardShot

    with Session() as s:
        book = s.query(Book).filter(Book.id == book_id).first()
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
        scripts_query = s.query(Script).filter(Script.book_id == book_id)
        shots_query = s.query(StoryboardShot).filter(StoryboardShot.book_id == book_id)
        if episode is not None:
            scripts_query = scripts_query.filter(Script.episode == episode)
            shots_query = shots_query.filter(StoryboardShot.episode == episode)
        qa_gate = _build_qa_delivery_gate(s, book_id, episode)
        if qa_gate["blocked"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "qa_blocked",
                    "message": "当前导出范围仍有可执行 QA 问题，不能生成正式 PDF 交付件。",
                    "qa_delivery_gate": qa_gate,
                },
            )
        scripts = scripts_query.order_by(Script.episode.asc()).all()
        all_storyboard_rows = shots_query.order_by(StoryboardShot.episode.asc(), StoryboardShot.shot_id.asc()).all()

    storyboard_rows = [shot for shot in all_storyboard_rows if _is_storyboard_shot_deliverable_for_export(shot)]
    pdf_bytes = _build_production_export_pdf(
        book,
        scripts,
        storyboard_rows,
        {
            "total_shots": len(all_storyboard_rows),
            "deliverable_shots": len(storyboard_rows),
            "blocked_shots": max(len(all_storyboard_rows) - len(storyboard_rows), 0),
        },
    )
    safe_title = "".join(ch if ch.isascii() and (ch.isalnum() or ch in "-_") else "_" for ch in (book.title or "project"))
    filename = f"{safe_title}-episode-{episode}-production-export.pdf" if episode is not None else f"{safe_title}-production-export.pdf"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


@app.delete("/api/pipeline/visual-setup/book/{book_id}")
def delete_visual_setup(book_id: int):
    """Delete all visual asset data for a book."""
    from models import Session, VisualEraSpec, VisualLocation, VisualProp, VisualMakeup, VisualReferenceAsset
    with Session() as s:
        deleted_era = s.query(VisualEraSpec).filter(VisualEraSpec.book_id == book_id).delete()
        deleted_loc = s.query(VisualLocation).filter(VisualLocation.book_id == book_id).delete()
        deleted_prop = s.query(VisualProp).filter(VisualProp.book_id == book_id).delete()
        deleted_makeup = s.query(VisualMakeup).filter(VisualMakeup.book_id == book_id).delete()
        deleted_refs = s.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == book_id).delete()
        s.commit()
    return {"deleted": {"era": deleted_era, "locations": deleted_loc, "props": deleted_prop, "makeups": deleted_makeup, "reference_assets": deleted_refs}}


@app.get("/api/pipeline/visual-setup/task/{task_id}")
def get_visual_task(task_id: str):
    task = _visual_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Visual setup task not found")
    return task


@app.get("/api/pipeline/storyboard/task/{task_id}")
def get_storyboard_task(task_id: str):
    task = _storyboard_tasks.get(task_id)
    if not task:
        task = _load_persisted_task_state(task_id, "storyboard")
    if not task:
        raise HTTPException(status_code=404, detail="Storyboard task not found")
    _storyboard_tasks.setdefault(task_id, task)
    return task


@app.delete("/api/pipeline/storyboard/book/{book_id}")
def delete_storyboard(book_id: int):
    """Delete all storyboard data for a book."""
    from models import Session, StoryboardAcceptanceRecord, StoryboardPromptVersion, StoryboardShot
    with Session() as s:
        s.query(StoryboardAcceptanceRecord).filter(
            StoryboardAcceptanceRecord.book_id == book_id
        ).delete()
        s.query(StoryboardPromptVersion).filter(
            StoryboardPromptVersion.book_id == book_id
        ).delete()
        deleted = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id
        ).delete()
        s.commit()
    return {"deleted": deleted}


@app.get("/api/pipeline/book/{book_id}/outputs")
def get_book_outputs(book_id: int, genre: str = "short_drama"):
    """Get all outputs for a book, filtered by genre."""
    from models import Session, BookBible, EpisodeOutline, Script, CharacterProfile, QAResult, \
        VisualEraSpec, VisualLocation, VisualProp, VisualMakeup, VisualReferenceAsset, SceneCharacter, SceneProp, StoryboardShot
    from core import safe_json_loads

    _normalize_visual_reference_assets(book_id)

    with Session() as s:
        bible = s.query(BookBible).filter(BookBible.book_id == book_id).first()
        outlines = s.query(EpisodeOutline).filter(
            EpisodeOutline.book_id == book_id,
            EpisodeOutline.genre == genre,
        ).order_by(EpisodeOutline.episode).all()
        scripts = s.query(Script).filter(
            Script.book_id == book_id,
            Script.genre == genre,
        ).order_by(Script.episode).all()

        # Fetch portrait data
        profiles = s.query(CharacterProfile).filter(
            CharacterProfile.book_id == book_id
        ).all()
        portrait_text = ""
        if profiles:
            parts = []
            for p in profiles:
                parts.append(f"## {p.name}\n韬唤: {p.identity}\n骞撮緞: {p.age_range}\n姘旇川: {p.temperament}\n绌跨潃: {p.signature_outfit or ''}\n璇磋瘽椋庢牸: {p.speech_style}\n")
            portrait_text = "\n---\n".join(parts)

        # Fetch visual production data
        era_spec = s.query(VisualEraSpec).filter(VisualEraSpec.book_id == book_id).first()
        locations = s.query(VisualLocation).filter(VisualLocation.book_id == book_id).order_by(VisualLocation.name).all()
        props = s.query(VisualProp).filter(VisualProp.book_id == book_id).order_by(VisualProp.name).all()
        makeups = _load_makeup_rows_or_profile_fallback(s, book_id)
        reference_assets = s.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == book_id).order_by(
            VisualReferenceAsset.asset_type,
            VisualReferenceAsset.asset_id,
            VisualReferenceAsset.id,
        ).all()
        reference_index: dict[tuple[str, str], list[dict]] = {}
        for row in reference_assets:
            reference_index.setdefault((row.asset_type, row.asset_id), []).append(_serialize_reference_asset_row(row))
        storyboard_rows = s.query(StoryboardShot).filter(
            StoryboardShot.book_id == book_id
        ).order_by(StoryboardShot.episode, StoryboardShot.shot_id).all()
        repaired_storyboard = False
        for shot_row in storyboard_rows:
            _, _, repaired = _ensure_storyboard_prompt_compiler_state(s, shot_row)
            repaired_storyboard = repaired_storyboard or repaired
        if repaired_storyboard:
            s.commit()

        return {
            "bible": bible.content if bible else "",
            "portrait": portrait_text,
            "production_skill": _production_skill_state_payload(book_id),
            "genres": list({
                o.genre for o in s.query(EpisodeOutline.genre).filter(
                    EpisodeOutline.book_id == book_id
                ).distinct().all()
            } | {
                scr.genre for scr in s.query(Script.genre).filter(
                    Script.book_id == book_id
                ).distinct().all()
            }),
            "visual": {
                "era": {
                    "timeline_start": era_spec.timeline_start if era_spec else "",
                    "timeline_end": era_spec.timeline_end if era_spec else "",
                    "clothing_spec": era_spec.clothing_spec if era_spec else "",
                    "color_palette": era_spec.color_palette if era_spec else "",
                    "architecture_spec": era_spec.architecture_spec if era_spec else "",
                    "prop_spec": era_spec.prop_spec if era_spec else "",
                    "color_curve": era_spec.color_curve if era_spec else "",
                } if era_spec else None,
                "locations": [
                    _serialize_visual_asset_row(
                        l,
                        "scene",
                        reference_assets=reference_index.get(("scene", str(l.id)), []),
                        peer_rows=locations,
                    )
                    for l in locations
                ],
                "props": [
                    _serialize_visual_asset_row(
                        p,
                        "prop",
                        reference_assets=reference_index.get(("prop", str(p.id)), []),
                        peer_rows=props,
                    )
                    for p in props
                ],
                "makeups": [
                    _serialize_makeup_row(
                        m,
                        reference_index.get(("character", str(m.id)), []),
                        [peer for peer in makeups if str(getattr(peer, "character_name", "") or "") == str(getattr(m, "character_name", "") or "")]
                    )
                    for m in makeups
                ],
            },
            "outlines": [
                {
                    "id": o.id,
                    "episode": o.episode,
                    "title": o.title,
                    "core_event": o.core_event or o.raw_content[:200] if o.raw_content else "",
                    "opening_hook": o.opening_hook or "",
                    "core_conflict": o.core_conflict or "",
                    "climax": o.climax or "",
                    "ending_hook": o.ending_hook or "",
                    "characters": _json_loads_list(o.characters),
                }
                for o in outlines
            ],
            "scripts": [
                {
                    "id": s.id,
                    "episode": s.episode,
                    "content": s.content,
                    "status": s.status,
                }
                for s in scripts
            ],
            "qa": [
                {
                    "id": q.id,
                    "episode": q.episode,
                    "result": __import__('json').loads(q.result) if isinstance(q.result, str) and q.result.startswith('{') else q.result,
                    "error_count": q.error_count,
                }
                for q in s.query(QAResult).filter(
                    QAResult.book_id == book_id
                ).order_by(QAResult.episode).all()
            ],
            "storyboard": [
                _serialize_storyboard_output_row(
                    s,
                    book_id,
                    sh,
                    locations,
                    makeups,
                    reference_index,
                )
                for sh in storyboard_rows
            ],
        }


@app.delete("/api/books/{book_id}")
def delete_book(book_id: int):
    """Delete a book and all associated data."""
    from models import Session, Book, BookBible, Chapter, EpisodeOutline, Script, \
        CharacterProfile, CharacterStage, SceneCharacter, SceneProp, StoryboardAcceptanceRecord, StoryboardPromptVersion, StoryboardShot, VisualEraSpec, VisualLocation, VisualMakeup, VisualProp, VisualReferenceAsset, KV, QAIssue, ScriptVersion
    with Session() as s:
        book = s.get(Book, book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        title = book.title

        # Cascade delete all related data
        for model in [ScriptVersion, QAIssue, Script, EpisodeOutline, CharacterStage, CharacterProfile,
                      SceneCharacter, SceneProp, StoryboardAcceptanceRecord, StoryboardPromptVersion, StoryboardShot,
                      VisualEraSpec, VisualLocation, VisualMakeup, VisualProp, VisualReferenceAsset,
                      Chapter, BookBible]:
            s.query(model).filter(model.book_id == book_id).delete()

        # Delete the book itself
        s.delete(book)
        s.commit()

        # Also clean up ingestion file
        import config
        ingest_dir = config.BOOKS_DIR / title
        if ingest_dir.exists():
            import shutil
            shutil.rmtree(ingest_dir, ignore_errors=True)

    return {"ok": True, "deleted": title}


def _qa_fix_mode_for_issue(issue_type: str) -> str:
    normalized = str(issue_type or "").strip().lower()
    if normalized in {"dialogue_style", "pace", "hook", "emotion_arc", "format", "word_count"}:
        return "auto"
    if normalized in {"logic_gap", "motivation", "relationship_conflict", "foreshadowing", "continuity"}:
        return "semi_auto"
    return "manual"


def _parse_issue_location(raw_location) -> tuple[str, Optional[int], Optional[int]]:
    if isinstance(raw_location, dict):
        section = str(raw_location.get("script_section") or raw_location.get("section") or "").strip()
        line_range = raw_location.get("line_range") or raw_location.get("lines") or []
        if isinstance(line_range, list) and len(line_range) >= 2:
            try:
                return section, int(line_range[0]), int(line_range[1])
            except (TypeError, ValueError):
                return section, None, None
        return section, None, None

    if isinstance(raw_location, str):
        section = raw_location.strip()
        match = re.search(r"(\d+)\s*[-~]\s*(\d+)", section)
        if match:
            return section, int(match.group(1)), int(match.group(2))
        single = re.search(r"line\s*(\d+)", section, re.IGNORECASE)
        if single:
            line_no = int(single.group(1))
            return section, line_no, line_no
        return section, None, None

    return "", None, None


def _extract_script_excerpt(content: str, line_start: Optional[int], line_end: Optional[int]) -> str:
    if not content:
        return ""
    if line_start and line_end and line_start > 0 and line_end >= line_start:
        lines = content.splitlines()
        start = min(len(lines), line_start) - 1
        end = min(len(lines), line_end)
        if start >= 0 and end > start:
            excerpt = "\n".join(lines[start:end]).strip()
            if excerpt:
                return excerpt
    return ""


def _chinese_numeral_to_int(text: str) -> Optional[int]:
    mapping = {
        "零": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    if raw == "十":
        return 10
    if "十" in raw:
        parts = raw.split("十", 1)
        tens = mapping.get(parts[0], 1 if parts[0] == "" else 0)
        ones = mapping.get(parts[1], 0)
        return tens * 10 + ones
    return mapping.get(raw)


def _extract_scene_blocks(content: str) -> list[tuple[int, str]]:
    if not content:
        return []
    pattern = re.compile(r"\*\*场景([零一二两三四五六七八九十0-9]+)[：:，,]?[^\n]*", re.MULTILINE)
    matches = list(pattern.finditer(content))
    blocks = []
    for index, match in enumerate(matches):
        scene_no = _chinese_numeral_to_int(match.group(1))
        if scene_no is None:
            continue
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        blocks.append((scene_no, content[start:end].strip()))
    return blocks


def _excerpt_from_scene_blocks(content: str, script_section: str) -> str:
    blocks = _extract_scene_blocks(content)
    if not blocks:
        return ""
    section = str(script_section or "")
    tail_match = re.search(r"场景([零一二两三四五六七八九十0-9]+).*末尾", section)
    if tail_match:
        scene_no = _chinese_numeral_to_int(tail_match.group(1))
        for current_no, block in blocks:
            if current_no == scene_no:
                return block[-700:].strip()

    range_match = re.search(r"场景([零一二两三四五六七八九十0-9]+)\s*[至到\-~]\s*([零一二两三四五六七八九十0-9]+)", section)
    if range_match:
        start_no = _chinese_numeral_to_int(range_match.group(1))
        end_no = _chinese_numeral_to_int(range_match.group(2))
        if start_no and end_no:
            chosen = [block for current_no, block in blocks if start_no <= current_no <= end_no]
            if chosen:
                return "\n\n".join(chosen)[:1400].strip()

    single_match = re.search(r"场景([零一二两三四五六七八九十0-9]+)", section)
    if single_match:
        scene_no = _chinese_numeral_to_int(single_match.group(1))
        for current_no, block in blocks:
            if current_no == scene_no:
                return block[:1200].strip()
    return ""


def _excerpt_from_keywords(content: str, keywords: list[str]) -> str:
    if not content:
        return ""
    lines = content.splitlines()
    cleaned_keywords = []
    for keyword in keywords:
        token = str(keyword or "").strip()
        if len(token) < 2:
            continue
        if token in {"剧本", "场景", "人物", "问题", "建议", "完整性"}:
            continue
        cleaned_keywords.append(token)
    for index, line in enumerate(lines):
        if any(keyword in line for keyword in cleaned_keywords):
            start = max(0, index - 4)
            end = min(len(lines), index + 5)
            excerpt = "\n".join(lines[start:end]).strip()
            if excerpt:
                return excerpt[:1200]
    return ""


def _derive_issue_source_excerpt(content: str, script_section: str, title: str, description: str) -> str:
    excerpt = _excerpt_from_scene_blocks(content, script_section)
    if excerpt:
        return excerpt

    keyword_candidates = []
    keyword_pattern = r"[\u4e00-\u9fffA-Za-z0-9]{2,8}"
    keyword_candidates.extend(re.findall(keyword_pattern, script_section or ""))
    keyword_candidates.extend(re.findall(keyword_pattern, title or ""))
    keyword_candidates.extend(re.findall(keyword_pattern, description or ""))
    excerpt = _excerpt_from_keywords(content, keyword_candidates)
    if excerpt:
        return excerpt

    return (content or "")[:800].strip()


def _build_issue_fingerprint(episode: int, issue_type: str, description: str, line_start: Optional[int], line_end: Optional[int], script_section: str) -> str:
    return "||".join([
        str(episode),
        str(issue_type or "").strip().lower(),
        str(description or "").strip(),
        str(line_start or ""),
        str(line_end or ""),
        str(script_section or "").strip(),
    ])


def _serialize_qa_issue(issue) -> dict:
    meta_info = safe_json_loads(issue.meta_info, {})
    issue_payload = {"type": issue.issue_type}
    rule_family = classify_script_qa_rule_family(issue_payload)
    return {
        "id": issue.id,
        "issue_id": issue.issue_key,
        "episode": issue.episode,
        "severity": issue.severity,
        "type": issue.issue_type,
        "title": issue.title,
        "description": issue.description,
        "location": {
            "script_section": issue.script_section or "",
            "line_range": [issue.line_start, issue.line_end] if issue.line_start and issue.line_end else [],
        },
        "suggestion": issue.suggestion or "",
        "fix_mode": issue.fix_mode or "manual",
        "fix_status": issue.fix_status or "pending",
        "rule_family": rule_family,
        "repair_goal": build_script_rule_family_repair_goal(rule_family),
        "workflow_status": str(meta_info.get("workflow_status") or "").strip() or None,
        "repair_version": str(meta_info.get("repair_version") or "").strip(),
        "note": str(meta_info.get("note") or "").strip(),
        "status_reason": issue.status_reason or "",
        "source_excerpt": issue.source_excerpt or "",
        "meta_info": meta_info,
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
        "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
    }


def _normalize_qa_lifecycle_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _qa_issue_workflow_status(issue) -> str:
    meta_info = safe_json_loads(getattr(issue, "meta_info", None), {})
    if not isinstance(meta_info, dict):
        return ""
    return _normalize_qa_lifecycle_status(meta_info.get("workflow_status"))


def _is_qa_issue_resolved_for_delivery(issue) -> bool:
    fix_status = _normalize_qa_lifecycle_status(getattr(issue, "fix_status", None))
    workflow_status = _qa_issue_workflow_status(issue)
    return (
        fix_status in {"recheck_passed", "resolved", "closed", "accepted"}
        or workflow_status in {"resolved", "wont_fix"}
    )


def _is_qa_issue_in_progress_for_delivery(issue) -> bool:
    fix_status = _normalize_qa_lifecycle_status(getattr(issue, "fix_status", None))
    workflow_status = _qa_issue_workflow_status(issue)
    return (
        fix_status in {"fixing", "fixed", "rechecking", "in_progress"}
        or workflow_status == "in_progress"
    )


def _build_qa_delivery_gate_from_issues(issues: list) -> dict:
    open_issues = [issue for issue in issues if not _is_qa_issue_resolved_for_delivery(issue) and not _is_qa_issue_in_progress_for_delivery(issue)]
    in_progress_issues = [issue for issue in issues if _is_qa_issue_in_progress_for_delivery(issue)]
    resolved_issues = [issue for issue in issues if _is_qa_issue_resolved_for_delivery(issue)]
    high_open_issues = [
        issue
        for issue in open_issues
        if _normalize_qa_lifecycle_status(getattr(issue, "severity", None)) == "high"
    ]
    blocking_issue_count = len(open_issues) + len(in_progress_issues)
    return {
        "total_issue_count": len(issues),
        "open_issue_count": len(open_issues),
        "in_progress_count": len(in_progress_issues),
        "resolved_count": len(resolved_issues),
        "high_open_issue_count": len(high_open_issues),
        "blocking_issue_count": blocking_issue_count,
        "blocked": blocking_issue_count > 0,
    }


def _build_qa_delivery_gate(session, book_id: int, episode: int | None = None) -> dict:
    from models import QAIssue, QAResult

    query = session.query(QAIssue).filter(QAIssue.book_id == book_id)
    if episode is not None:
        query = query.filter(QAIssue.episode == episode)
    issues = query.order_by(QAIssue.episode.asc(), QAIssue.created_at.asc(), QAIssue.id.asc()).all()
    gate = _build_qa_delivery_gate_from_issues(issues)
    issue_episodes = {int(getattr(issue, "episode", 0) or 0) for issue in issues if getattr(issue, "episode", None)}
    qa_result_query = session.query(QAResult).filter(QAResult.book_id == book_id)
    if episode is not None:
        qa_result_query = qa_result_query.filter(QAResult.episode == episode)
    legacy_blocking_count = 0
    for qa_result in qa_result_query.order_by(QAResult.episode.asc(), QAResult.created_at.desc(), QAResult.id.desc()).all():
        qa_episode = int(getattr(qa_result, "episode", 0) or 0)
        if qa_episode in issue_episodes:
            continue
        legacy_blocking_count += max(int(getattr(qa_result, "error_count", 0) or 0), 0)
        if qa_episode:
            issue_episodes.add(qa_episode)
    if legacy_blocking_count > 0:
        gate["total_issue_count"] += legacy_blocking_count
        gate["open_issue_count"] += legacy_blocking_count
        gate["blocking_issue_count"] += legacy_blocking_count
        gate["blocked"] = True
        gate["legacy_error_count"] = legacy_blocking_count
    gate["episode"] = episode
    gate["episodes"] = sorted(issue_episodes)
    return gate


def _build_qa_delivery_blocked_reason(gate: dict) -> str:
    parts = [
        f"开放 {gate.get('open_issue_count', 0)}" if int(gate.get("open_issue_count", 0) or 0) > 0 else "",
        f"修复/复检中 {gate.get('in_progress_count', 0)}" if int(gate.get("in_progress_count", 0) or 0) > 0 else "",
        f"高优先级 {gate.get('high_open_issue_count', 0)}" if int(gate.get("high_open_issue_count", 0) or 0) > 0 else "",
    ]
    detail = "，".join([part for part in parts if part]) or f"待处理 {gate.get('blocking_issue_count', 0)}"
    return f"QA 待处理 {gate.get('blocking_issue_count', 0)} 项（{detail}）"


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _serialize_script_version(version) -> dict:
    return {
        "id": version.id,
        "episode": version.episode,
        "version_no": version.version_no,
        "label": version.label,
        "change_type": version.change_type,
        "change_reason": version.change_reason,
        "qa_issue_id": version.qa_issue_key,
        "operator_name": version.operator_name,
        "diff_text": version.diff_text or "",
        "recheck_status": version.recheck_status or "pending",
        "recheck_summary": version.recheck_summary or "",
        "created_at": version.created_at.isoformat() if version.created_at else None,
        "updated_at": version.updated_at.isoformat() if version.updated_at else None,
    }


def _ensure_script_baseline_version(session, script) -> None:
    from models import ScriptVersion

    existing = session.query(ScriptVersion).filter(
        ScriptVersion.book_id == script.book_id,
        ScriptVersion.episode == script.episode,
    ).count()
    if existing > 0:
        return

    session.add(
        ScriptVersion(
            book_id=script.book_id,
            episode=script.episode,
            script_id=script.id,
            version_no=1,
            label="v1 原始剧本",
            change_type="baseline",
            change_reason="Initial baseline snapshot",
            qa_issue_key="",
            operator_name="system",
            content_before=script.content or "",
            content_after=script.content or "",
            diff_text="",
            recheck_status="not_run",
            recheck_summary="Baseline snapshot",
            meta_info=json.dumps({}, ensure_ascii=False),
        )
    )


def _next_script_version_no(session, book_id: int, episode: int) -> int:
    from models import ScriptVersion

    rows = session.query(ScriptVersion).filter(
        ScriptVersion.book_id == book_id,
        ScriptVersion.episode == episode,
    ).all()
    return max([row.version_no for row in rows] + [0]) + 1


def _build_script_diff(before_text: str, after_text: str, episode: int) -> str:
    return "\n".join(
        difflib.unified_diff(
            (before_text or "").splitlines(),
            (after_text or "").splitlines(),
            fromfile=f"episode-{episode}-before",
            tofile=f"episode-{episode}-after",
            lineterm="",
        )
    )


def _apply_patch_to_script(content: str, issue, patched_text: str) -> str:
    original = content or ""
    replacement = patched_text or ""
    if issue.line_start and issue.line_end:
        lines = original.splitlines()
        start = issue.line_start - 1
        end = issue.line_end
        if start < 0 or start >= len(lines):
            raise HTTPException(status_code=400, detail="Issue line range is outside the current script.")
        new_lines = lines[:start] + replacement.splitlines() + lines[end:]
        return "\n".join(new_lines)

    excerpt = (issue.source_excerpt or "").strip()
    if excerpt and excerpt in original:
        return original.replace(excerpt, replacement, 1)

    raise HTTPException(status_code=400, detail="Cannot locate the original script segment for this issue.")


def _load_episode_outline_payload(session, book_id: int, episode: int) -> dict[str, Any]:
    from models import EpisodeOutline

    ep_row = session.query(EpisodeOutline).filter(
        EpisodeOutline.book_id == book_id,
        EpisodeOutline.episode == episode,
    ).order_by(EpisodeOutline.id.desc()).first()
    if not ep_row:
        return {}

    def _split_csv(value: Any) -> list[str]:
        text = str(value or "").strip()
        if not text:
            return []
        return [item.strip() for item in text.split(",") if item.strip()]

    return {
        "episode": ep_row.episode,
        "title": ep_row.title or "",
        "core_event": ep_row.core_event or "",
        "opening_hook": ep_row.opening_hook or "",
        "core_conflict": ep_row.core_conflict or "",
        "climax": ep_row.climax or "",
        "ending_hook": ep_row.ending_hook or "",
        "characters": _split_csv(ep_row.characters),
        "scenes": _split_csv(ep_row.scenes),
    }


def _build_qa_fix_repair_context(issue, episode_outline: dict[str, Any] | None = None) -> str:
    outline = episode_outline if isinstance(episode_outline, dict) else {}
    qa_issues = load_latest_script_qa_issues(issue.book_id, issue.episode)
    script_content = ""
    with Session() as session:
        from models import Script

        script_row = session.query(Script).filter(
            Script.book_id == issue.book_id,
            Script.episode == issue.episode,
        ).first()
        script_content = script_row.content if script_row else ""
    focus_block = {
        **_build_qa_fix_focus_payload(issue),
        "source_excerpt": issue.source_excerpt or "",
    }
    skill_block = build_production_skill_prompt_block(issue.book_id, "script")
    foundation_block = build_script_skill_foundation_prompt_block(
        issue.book_id,
        episode_outline=outline,
        qa_issues=qa_issues,
        script_content=script_content,
    )
    execution_plan_block = build_script_skill_execution_plan_prompt_block(
        issue.book_id,
        episode_outline=outline,
        qa_issues=qa_issues,
    )
    repair_packet_block = build_script_skill_repair_packet_prompt_block(
        issue.book_id,
        episode_outline=outline,
        qa_issues=qa_issues,
        script_content=script_content,
    )
    return (
        f"{skill_block}\n\n"
        f"{foundation_block}\n\n"
        f"{execution_plan_block}\n\n"
        f"{repair_packet_block}\n\n"
        f"## Script Repair Focus\n{json.dumps(focus_block, ensure_ascii=False, indent=2)}"
    )


def _build_qa_fix_focus_payload(issue) -> dict[str, Any]:
    issue_payload = {
        "type": issue.issue_type,
        "severity": issue.severity,
        "title": issue.title,
        "description": issue.description,
        "suggestion": issue.suggestion,
        "fix_mode": issue.fix_mode,
    }
    rule_family = classify_script_qa_rule_family(issue_payload)
    return {
        "issue_id": issue.issue_key,
        "episode": issue.episode,
        "issue_type": issue.issue_type or "unknown",
        "severity": issue.severity or "medium",
        "rule_family": rule_family,
        "repair_goal": build_script_rule_family_repair_goal(rule_family),
        "title": issue.title or "",
        "description": issue.description or "",
        "suggestion": issue.suggestion or "",
        "script_section": issue.script_section or "",
        "line_range": [issue.line_start, issue.line_end] if issue.line_start and issue.line_end else [],
    }


def _generate_qa_fix_options_for_issue(issue, script, mode: str, option_count: int = 3, custom_requirement: str = "") -> tuple[str, list[dict]]:
    excerpt = issue.source_excerpt or _extract_script_excerpt(script.content or "", issue.line_start, issue.line_end)
    episode_outline: dict[str, Any] = {}
    with Session() as session:
        episode_outline = _load_episode_outline_payload(session, issue.book_id, issue.episode)
    repair_context_block = _build_qa_fix_repair_context(issue, episode_outline=episode_outline)
    repair_focus = _build_qa_fix_focus_payload(issue)
    prompt = load_prompt(
        "qa/fix_options",
        option_count=max(1, min(option_count, 3)),
        issue_type=issue.issue_type or "unknown",
        severity=issue.severity or "medium",
        issue_title=issue.title or "",
        issue_description=issue.description or "",
        issue_location=f"{issue.script_section or '未标注'} {f'行 {issue.line_start}-{issue.line_end}' if issue.line_start and issue.line_end else ''}".strip(),
        original_excerpt=excerpt,
        fix_mode=mode,
        extra_requirement=custom_requirement or "保持短剧节奏，台词总量不超过原片段的 120%。",
    )
    full_prompt = f"{repair_context_block}\n\n{prompt}"

    try:
        result = llm_client.call_llm_json(
            full_prompt,
            system="你是短剧剧本修复编译器。必须优先遵守 Production Skill、脚本中间结构与当前 QA 修复目标，只修当前问题，不得发散重写整集。",
        )
        options = result.get("options", []) if isinstance(result, dict) else []
    except Exception:
        options = []

    if not options:
        options = [
            {
                "id": "A",
                "title": "保守修复",
                "strategy": issue.suggestion or "围绕原片段补一处更明确的动作、因果或情绪递进。",
                "patched_text": excerpt,
            }
        ]
    for option in options:
        if isinstance(option, dict):
            option.setdefault("rule_family", repair_focus["rule_family"])
            option.setdefault("repair_goal", repair_focus["repair_goal"])
    return excerpt, options


def _score_qa_fix_option(issue, excerpt: str, option: dict) -> tuple[int, int, int, str]:
    patched_text = str(option.get("patched_text") or "").strip()
    strategy = str(option.get("strategy") or "").strip().lower()
    suggestion = str(issue.suggestion or "").strip().lower()
    issue_type = str(issue.issue_type or "").strip().lower()
    excerpt_len = max(1, len(excerpt or ""))
    length_delta = abs(len(patched_text) - excerpt_len)

    conservative_bonus = 0
    if issue_type in {"format", "pace", "dialogue_style", "word_count"}:
        conservative_bonus += 20
    if length_delta <= max(40, int(excerpt_len * 0.35)):
        conservative_bonus += 15
    if suggestion and any(token and token in strategy for token in suggestion.split()[:6]):
        conservative_bonus += 10
    if any(keyword in strategy for keyword in ["保守", "最小", "局部", "不改动其他"]):
        conservative_bonus += 8

    patched_lines = len([line for line in patched_text.splitlines() if line.strip()])
    return (
        conservative_bonus,
        -length_delta,
        -patched_lines,
        str(option.get("id") or ""),
    )


def _select_best_qa_fix_option(issue, excerpt: str, options: list[dict]) -> Optional[dict]:
    usable_options = [item for item in options if str(item.get("patched_text") or "").strip()]
    if not usable_options:
        return None
    ranked = sorted(usable_options, key=lambda item: _score_qa_fix_option(issue, excerpt, item), reverse=True)
    return ranked[0]


def _qa_fix_guard_result(issue, script_content: str, patched_text: str, max_diff_lines: int, max_length_delta_ratio: float) -> dict:
    excerpt = issue.source_excerpt or _extract_script_excerpt(script_content or "", issue.line_start, issue.line_end)
    before_text = script_content or ""
    after_text = _apply_patch_to_script(before_text, issue, patched_text.strip())
    diff_text = _build_script_diff(before_text, after_text, issue.episode)
    changed_lines = [
        line for line in diff_text.splitlines()
        if line and (line.startswith("+") or line.startswith("-")) and not line.startswith("+++") and not line.startswith("---")
    ]
    excerpt_len = max(1, len(excerpt or ""))
    length_delta_ratio = abs(len(patched_text or "") - excerpt_len) / excerpt_len
    blocked = len(changed_lines) > max_diff_lines or length_delta_ratio > max_length_delta_ratio
    reasons = []
    if len(changed_lines) > max_diff_lines:
        reasons.append(f"diff lines {len(changed_lines)} > {max_diff_lines}")
    if length_delta_ratio > max_length_delta_ratio:
        reasons.append(f"length delta ratio {length_delta_ratio:.2f} > {max_length_delta_ratio:.2f}")
    return {
        "blocked": blocked,
        "reasons": reasons,
        "changed_line_count": len(changed_lines),
        "length_delta_ratio": length_delta_ratio,
        "diff_text": diff_text,
    }


def _summarize_qa_auto_fix_failed_items(failed_items: list[dict]) -> dict:
    summary = {
        "safety_guard_blocked": 0,
        "stopped_after_failed_rechecks": 0,
        "no_usable_option": 0,
        "runtime_error": 0,
    }
    for item in failed_items or []:
        kind = str(item.get("failure_kind") or "runtime_error")
        if kind not in summary:
            kind = "runtime_error"
        summary[kind] += 1
    return summary


def _apply_qa_fix_internal(session, book_id: int, issue, script, mode: str, patched_text: str, change_reason: str, option_id: str, operator_name: str, rerun_qa: bool) -> tuple[int, str, int]:
    from models import ScriptVersion

    _ensure_script_baseline_version(session, script)
    before_text = script.content or ""
    after_text = _apply_patch_to_script(before_text, issue, patched_text.strip())
    diff_text = _build_script_diff(before_text, after_text, issue.episode)
    version_no = _next_script_version_no(session, book_id, issue.episode)
    repair_focus = _build_qa_fix_focus_payload(issue)
    version = ScriptVersion(
        book_id=book_id,
        episode=issue.episode,
        script_id=script.id,
        version_no=version_no,
        label=f"v{version_no} {mode}修复：{(issue.title or 'QA').strip()[:16]}",
        change_type=f"{mode}_fix",
        change_reason=change_reason or issue.description,
        qa_issue_key=issue.issue_key,
        operator_name=operator_name or "user",
        content_before=before_text,
        content_after=after_text,
        diff_text=diff_text,
        recheck_status="running" if rerun_qa else "not_run",
        recheck_summary="QA recheck is running in background." if rerun_qa else "Saved without recheck",
        meta_info=json.dumps({
            "option_id": option_id,
            "change_reason": change_reason or issue.description,
            "repair_focus": repair_focus,
            "auto_fix_report": {
                "issue_id": issue.issue_key,
                "issue_title": issue.title or issue.description,
                "issue_type": issue.issue_type or "unknown",
                "rule_family": repair_focus["rule_family"],
                "repair_goal": repair_focus["repair_goal"],
                "option_id": option_id,
                "operator_name": operator_name or "user",
            },
        }, ensure_ascii=False),
    )
    session.add(version)

    script.content = after_text
    script.word_count = len(after_text)
    issue.fix_status = "rechecking" if rerun_qa else "fixed"
    issue.status_reason = "Fix applied. QA recheck is running in background." if rerun_qa else "Fix applied. Recheck not started."
    issue.updated_at = datetime.now()
    session.flush()
    return version.id, diff_text, issue.episode


def _sync_episode_qa_issues(session, book_id: int, episode: int) -> list:
    from models import QAIssue, QAResult, Script

    qa_result = session.query(QAResult).filter(
        QAResult.book_id == book_id,
        QAResult.episode == episode,
    ).order_by(QAResult.created_at.desc(), QAResult.id.desc()).first()
    if not qa_result:
        return []

    script = session.query(Script).filter(
        Script.book_id == book_id,
        Script.episode == episode,
    ).first()
    script_content = script.content if script else ""
    payload = safe_json_loads(qa_result.result, {})
    raw_issues = payload.get("issues") if isinstance(payload.get("issues"), list) else payload.get("errors", [])
    suggestions = payload.get("suggestions", []) if isinstance(payload.get("suggestions"), list) else []

    existing_rows = session.query(QAIssue).filter(
        QAIssue.book_id == book_id,
        QAIssue.episode == episode,
    ).all()
    existing_by_fp = {}
    for row in existing_rows:
        fp = _build_issue_fingerprint(
            row.episode,
            row.issue_type,
            row.description,
            row.line_start,
            row.line_end,
            row.script_section,
        )
        existing_by_fp[fp] = row

    seen_fps = set()
    synced_rows = []
    for index, raw_issue in enumerate(raw_issues or [], start=1):
        issue_type = str(raw_issue.get("type") or "unknown").strip()
        description = str(raw_issue.get("description") or raw_issue.get("message") or "").strip()
        title = str(raw_issue.get("title") or description[:24] or f"QA issue {index}").strip()
        script_section, line_start, line_end = _parse_issue_location(raw_issue.get("location"))
        suggestion = str(raw_issue.get("suggestion") or (suggestions[0] if suggestions else "")).strip()
        source_excerpt = _extract_script_excerpt(script_content, line_start, line_end)
        if not source_excerpt and isinstance(raw_issue.get("excerpt"), str):
            source_excerpt = raw_issue.get("excerpt", "").strip()
        if not source_excerpt:
            source_excerpt = _derive_issue_source_excerpt(
                script_content,
                script_section,
                title,
                description,
            )
        fp = _build_issue_fingerprint(episode, issue_type, description, line_start, line_end, script_section)
        seen_fps.add(fp)
        row = existing_by_fp.get(fp)
        if not row:
            row = QAIssue(
                issue_key=f"qa-ep{episode}-{uuid.uuid4().hex[:8]}",
                book_id=book_id,
                episode=episode,
                fix_status="pending",
            )
            session.add(row)
        row.qa_result_id = qa_result.id
        row.severity = str(raw_issue.get("severity") or "medium").strip() or "medium"
        row.issue_type = issue_type or "unknown"
        row.title = title
        row.description = description
        row.script_section = script_section
        row.line_start = line_start
        row.line_end = line_end
        row.suggestion = suggestion
        row.fix_mode = _qa_fix_mode_for_issue(issue_type)
        row.source_excerpt = source_excerpt
        row.meta_info = json.dumps({"raw_issue": raw_issue}, ensure_ascii=False)
        if row.fix_status in {"fixed", "fixing", "rechecking", "recheck_passed"}:
            row.fix_status = "recheck_failed"
            row.status_reason = description or "Issue still exists after recheck."
            meta = safe_json_loads(row.meta_info, {})
            meta["auto_fix_recheck_fail_count"] = int(meta.get("auto_fix_recheck_fail_count") or 0) + 1
            row.meta_info = json.dumps(meta, ensure_ascii=False)
        elif row.fix_status in {"rolled_back"}:
            row.fix_status = "pending"
            row.status_reason = "Rolled back to a previous version."
        row.updated_at = datetime.now()
        synced_rows.append(row)

    for row in existing_rows:
        fp = _build_issue_fingerprint(
            row.episode,
            row.issue_type,
            row.description,
            row.line_start,
            row.line_end,
            row.script_section,
        )
        if fp not in seen_fps and row.fix_status in {"pending", "fixing", "fixed", "rechecking", "recheck_failed"}:
            row.fix_status = "recheck_passed"
            row.status_reason = "Issue no longer appears in the latest QA run."
            meta = safe_json_loads(row.meta_info, {})
            meta["auto_fix_recheck_fail_count"] = 0
            row.meta_info = json.dumps(meta, ensure_ascii=False)
            row.updated_at = datetime.now()

    session.flush()
    return session.query(QAIssue).filter(
        QAIssue.book_id == book_id,
        QAIssue.episode == episode,
    ).order_by(QAIssue.created_at.asc(), QAIssue.id.asc()).all()


def _backfill_episode_issue_excerpts(session, book_id: int, episode: int) -> None:
    from models import QAIssue, Script

    script = session.query(Script).filter(
        Script.book_id == book_id,
        Script.episode == episode,
    ).first()
    if not script or not script.content:
        return
    rows = session.query(QAIssue).filter(
        QAIssue.book_id == book_id,
        QAIssue.episode == episode,
    ).all()
    for row in rows:
        if row.source_excerpt:
            continue
        row.source_excerpt = _derive_issue_source_excerpt(
            script.content,
            row.script_section or "",
            row.title or "",
            row.description or "",
        )
        row.updated_at = datetime.now()


def _run_episode_qa_and_sync(book_id: int, episode: int) -> dict:
    from agents.qa import QAAgent
    from models import Session, QAIssue

    QAAgent(book_id).run(episode)
    with Session() as session:
        issues = _sync_episode_qa_issues(session, book_id, episode)
        session.commit()
        qa_gate = _build_qa_delivery_gate_from_issues(issues)
        open_count = qa_gate["blocking_issue_count"]
        failed_count = sum(1 for issue in issues if issue.fix_status == "recheck_failed")
        rows = session.query(QAIssue).filter(
            QAIssue.book_id == book_id,
            QAIssue.episode == episode,
        ).order_by(QAIssue.created_at.asc(), QAIssue.id.asc()).all()
        return {
            "episode": episode,
            "open_issue_count": open_count,
            "in_progress_count": qa_gate["in_progress_count"],
            "resolved_count": qa_gate["resolved_count"],
            "high_open_issue_count": qa_gate["high_open_issue_count"],
            "recheck_failed_count": failed_count,
            "issues": [_serialize_qa_issue(row) for row in rows],
        }


def _finish_script_version_recheck(version_id: Optional[int], issue_key: Optional[str], passed: bool, summary: str) -> None:
    if not version_id and not issue_key:
        return
    from models import QAIssue, ScriptVersion

    with Session() as session:
        if version_id:
            version_row = session.query(ScriptVersion).filter(ScriptVersion.id == version_id).first()
            if version_row:
                version_row.recheck_status = "passed" if passed else "failed"
                version_row.recheck_summary = summary
                version_row.updated_at = datetime.now()
        if issue_key:
            issue_row = session.query(QAIssue).filter(QAIssue.issue_key == issue_key).first()
            if issue_row and issue_row.fix_status == "rechecking":
                issue_row.fix_status = "recheck_passed" if passed else "recheck_failed"
                issue_row.status_reason = summary
                meta = safe_json_loads(issue_row.meta_info, {})
                if passed:
                    meta["auto_fix_recheck_fail_count"] = 0
                else:
                    meta["auto_fix_recheck_fail_count"] = int(meta.get("auto_fix_recheck_fail_count") or 0) + 1
                issue_row.meta_info = json.dumps(meta, ensure_ascii=False)
                issue_row.updated_at = datetime.now()
        session.commit()


def _mark_recheck_runtime_error(version_id: Optional[int], issue_key: Optional[str], message: str) -> None:
    if not version_id and not issue_key:
        return
    from models import QAIssue, ScriptVersion

    with Session() as session:
        if version_id:
            version_row = session.query(ScriptVersion).filter(ScriptVersion.id == version_id).first()
            if version_row:
                version_row.recheck_status = "error"
                version_row.recheck_summary = message
                version_row.updated_at = datetime.now()
        if issue_key:
            issue_row = session.query(QAIssue).filter(QAIssue.issue_key == issue_key).first()
            if issue_row and issue_row.fix_status == "rechecking":
                issue_row.fix_status = "fixed"
                issue_row.status_reason = message
                issue_row.updated_at = datetime.now()
        session.commit()


def _run_episode_recheck_in_background(book_id: int, episode: int, version_id: Optional[int] = None, issue_key: Optional[str] = None) -> None:
    try:
        recheck_payload = _run_episode_qa_and_sync(book_id, episode)
        if issue_key:
            matched_issue = next((item for item in recheck_payload.get("issues", []) if item.get("issue_id") == issue_key), None)
            if matched_issue:
                passed = matched_issue.get("fix_status") == "recheck_passed"
                summary = matched_issue.get("status_reason") or ("Recheck passed" if passed else "Issue still present")
            else:
                passed = True
                summary = "Issue no longer appears in the latest QA run."
        else:
            passed = (recheck_payload.get("open_issue_count") or 0) == 0
            summary = "Episode recheck passed." if passed else f"Episode still has {recheck_payload.get('open_issue_count') or 0} open issues."
        _finish_script_version_recheck(version_id, issue_key, passed, summary)
    except Exception as exc:
        _mark_recheck_runtime_error(version_id, issue_key, f"QA recheck failed: {exc}")


@app.get("/api/books/{book_id}/qa/workbench")
def get_qa_workbench(book_id: int):
    from models import QAIssue, QAResult, Script, ScriptVersion

    with Session() as session:
        scripts = session.query(Script).filter(
            Script.book_id == book_id
        ).order_by(Script.episode.asc()).all()
        for script in scripts:
            latest_qa = session.query(QAResult).filter(
                QAResult.book_id == book_id,
                QAResult.episode == script.episode,
            ).order_by(QAResult.created_at.desc(), QAResult.id.desc()).first()
            has_issues = session.query(QAIssue).filter(
                QAIssue.book_id == book_id,
                QAIssue.episode == script.episode,
            ).count() > 0
            if latest_qa and not has_issues:
                _sync_episode_qa_issues(session, book_id, script.episode)
            _backfill_episode_issue_excerpts(session, book_id, script.episode)
        session.commit()
        episodes = []
        for script in scripts:
            latest_qa = session.query(QAResult).filter(
                QAResult.book_id == book_id,
                QAResult.episode == script.episode,
            ).order_by(QAResult.created_at.desc(), QAResult.id.desc()).first()
            issues = session.query(QAIssue).filter(
                QAIssue.book_id == book_id,
                QAIssue.episode == script.episode,
            ).order_by(QAIssue.created_at.asc(), QAIssue.id.asc()).all()
            versions = session.query(ScriptVersion).filter(
                ScriptVersion.book_id == book_id,
                ScriptVersion.episode == script.episode,
            ).order_by(ScriptVersion.version_no.desc(), ScriptVersion.id.desc()).all()
            qa_payload = safe_json_loads(latest_qa.result, {}) if latest_qa else {}
            qa_gate = _build_qa_delivery_gate_from_issues(issues)
            episodes.append({
                "episode": script.episode,
                "script_id": script.id,
                "script_status": script.status,
                "qa_summary": {
                    "qa_result_id": latest_qa.id if latest_qa else None,
                    "overall_score": qa_payload.get("overall_score"),
                    "error_count": latest_qa.error_count if latest_qa else len(issues),
                    "open_issue_count": qa_gate["open_issue_count"],
                    "in_progress_count": qa_gate["in_progress_count"],
                    "resolved_count": qa_gate["resolved_count"],
                    "high_open_issue_count": qa_gate["high_open_issue_count"],
                    "blocking_issue_count": qa_gate["blocking_issue_count"],
                    "suggestions": qa_payload.get("suggestions", []) if isinstance(qa_payload.get("suggestions", []), list) else [],
                },
                "issues": [_serialize_qa_issue(issue) for issue in issues],
                "versions": [_serialize_script_version(version) for version in versions],
            })
        return {"book_id": book_id, "episodes": episodes}


@app.post("/api/books/{book_id}/qa/episodes/{episode}/sync")
def sync_qa_episode(book_id: int, episode: int):
    with Session() as session:
        rows = _sync_episode_qa_issues(session, book_id, episode)
        session.commit()
        return {
            "ok": True,
            "episode": episode,
            "issues": [_serialize_qa_issue(row) for row in rows],
        }


@app.post("/api/books/{book_id}/qa/issues/{issue_key}/preview-fix")
def preview_qa_fix(book_id: int, issue_key: str, req: QAPreviewFixRequest):
    from models import QAIssue, Script

    with Session() as session:
        issue = session.query(QAIssue).filter(
            QAIssue.book_id == book_id,
            QAIssue.issue_key == issue_key,
        ).first()
        if not issue:
            raise HTTPException(status_code=404, detail="QA issue not found.")

        script = session.query(Script).filter(
            Script.book_id == book_id,
            Script.episode == issue.episode,
        ).first()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found.")

        patched_text = (req.patched_text or "").strip()
        if not patched_text:
            raise HTTPException(status_code=400, detail="patched_text is required.")

        before_text = script.content or ""
        after_text = _apply_patch_to_script(before_text, issue, patched_text)
        diff_text = _build_script_diff(before_text, after_text, issue.episode)
        return {
            "issue_id": issue.issue_key,
            "episode": issue.episode,
            "mode": req.mode,
            "option_id": req.option_id,
            "source_excerpt": issue.source_excerpt or "",
            "patched_text": patched_text,
            "diff_text": diff_text,
        }


@app.post("/api/books/{book_id}/qa/episodes/{episode}/recheck")
def recheck_qa_episode(book_id: int, episode: int, background: BackgroundTasks):
    from models import QAIssue

    with Session() as session:
        rows = session.query(QAIssue).filter(
            QAIssue.book_id == book_id,
            QAIssue.episode == episode,
        ).all()
        for row in rows:
            if row.fix_status != "recheck_passed":
                row.fix_status = "rechecking"
                row.status_reason = "Episode QA recheck is running in background."
                row.updated_at = datetime.now()
        session.commit()
    background.add_task(_run_episode_recheck_in_background, book_id, episode, None, None)
    return {"ok": True, "episode": episode, "status": "running"}


@app.patch("/api/books/{book_id}/qa/issues/{issue_key}/workflow")
def update_qa_issue_workflow(book_id: int, issue_key: str, req: QAWorkflowUpdateRequest):
    from models import QAIssue

    allowed_statuses = {"open", "in_progress", "resolved", "wont_fix"}
    with Session() as session:
        issue = session.query(QAIssue).filter(
            QAIssue.book_id == book_id,
            QAIssue.issue_key == issue_key,
        ).first()
        if not issue:
            raise HTTPException(status_code=404, detail="QA issue not found.")

        meta = safe_json_loads(issue.meta_info, {})
        if req.workflow_status is not None:
            workflow_status = str(req.workflow_status or "").strip()
            if workflow_status and workflow_status not in allowed_statuses:
                raise HTTPException(status_code=400, detail="Unsupported workflow status.")
            if workflow_status:
                meta["workflow_status"] = workflow_status
            else:
                meta.pop("workflow_status", None)
        if req.repair_version is not None:
            meta["repair_version"] = str(req.repair_version or "").strip()
        if req.note is not None:
            meta["note"] = str(req.note or "").strip()

        issue.meta_info = json.dumps(meta, ensure_ascii=False)
        issue.updated_at = datetime.now()
        session.commit()
        session.refresh(issue)
        return {
            "ok": True,
            "issue": _serialize_qa_issue(issue),
        }


@app.get("/api/books/{book_id}/scripts/{episode}/versions")
def get_script_versions(book_id: int, episode: int):
    from models import ScriptVersion

    with Session() as session:
        rows = session.query(ScriptVersion).filter(
            ScriptVersion.book_id == book_id,
            ScriptVersion.episode == episode,
        ).order_by(ScriptVersion.version_no.desc(), ScriptVersion.id.desc()).all()
        return {"versions": [_serialize_script_version(row) for row in rows]}


@app.get("/api/books/{book_id}/script-decisions")
def get_script_decisions(book_id: int):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        content=_read_script_decisions(book_id),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/books/{book_id}/adaptation-state")
def get_adaptation_state(book_id: int):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        content=_read_adaptation_state(book_id),
        headers={"Cache-Control": "no-store"},
    )


@app.put("/api/books/{book_id}/adaptation-state")
def update_adaptation_state(book_id: int, req: AdaptationStateUpdateRequest):
    from fastapi.responses import JSONResponse
    from models import Session, Book

    with Session() as s:
        book = s.query(Book).filter(Book.id == book_id).first()
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

    current = _read_adaptation_state(book_id)
    saved = _write_adaptation_state(
        book_id,
        {
            **current,
            "selected_id": req.selected_id,
            "selected_name": req.selected_name,
            "custom_note": req.custom_note,
            "locked_at": req.locked_at,
        },
    )
    return JSONResponse(
        content={"ok": True, "book_id": book_id, "adaptation_state": saved},
        headers={"Cache-Control": "no-store"},
    )


@app.put("/api/books/{book_id}/script-decisions/{episode}")
def update_script_decision(book_id: int, episode: int, req: ScriptDecisionUpdateRequest):
    from fastapi.responses import JSONResponse

    payload = _read_script_decisions(book_id)
    episodes = payload.get("episodes", {})
    current = episodes.get(str(episode), {}) if isinstance(episodes, dict) else {}
    episodes[str(episode)] = {
        "locked_at": req.locked_at,
        "released_at": req.released_at,
        "note": req.note or "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "created_at": current.get("created_at") or datetime.now(timezone.utc).isoformat(),
    }
    payload["episodes"] = episodes
    saved = _write_script_decisions(book_id, payload)
    return JSONResponse(
        content={
        "ok": True,
        "book_id": book_id,
        "episode": episode,
        "decision": saved["episodes"].get(str(episode), {}),
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/books/{book_id}/qa/issues/{issue_key}/generate-fix-options")
def generate_qa_fix_options(book_id: int, issue_key: str, req: QAFixOptionsRequest):
    from models import QAIssue, Script

    with Session() as session:
        issue = session.query(QAIssue).filter(
            QAIssue.book_id == book_id,
            QAIssue.issue_key == issue_key,
        ).first()
        if not issue:
            raise HTTPException(status_code=404, detail="QA issue not found.")

        script = session.query(Script).filter(
            Script.book_id == book_id,
            Script.episode == issue.episode,
        ).first()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found.")

        excerpt, options = _generate_qa_fix_options_for_issue(
            issue,
            script,
            req.mode,
            option_count=req.option_count,
            custom_requirement=req.custom_requirement,
        )

        meta = safe_json_loads(issue.meta_info, {})
        meta["repair_options"] = options
        meta["last_generated_mode"] = req.mode
        issue.meta_info = json.dumps(meta, ensure_ascii=False)
        issue.fix_status = "fixing"
        issue.status_reason = "Fix options generated. Please preview a diff before applying."
        issue.updated_at = datetime.now()
        session.commit()

        return {
            "issue": _serialize_qa_issue(issue),
            "options": options,
            "original_excerpt": excerpt,
        }


@app.post("/api/books/{book_id}/qa/issues/{issue_key}/auto-fix")
def auto_fix_qa_issue(book_id: int, issue_key: str, req: QAAutoFixRequest, background: BackgroundTasks):
    from models import QAIssue, Script, ScriptVersion

    version_id = None
    diff_text = ""
    selected_option = None
    issue_episode = None
    with Session() as session:
        issue = session.query(QAIssue).filter(
            QAIssue.book_id == book_id,
            QAIssue.issue_key == issue_key,
        ).first()
        if not issue:
            raise HTTPException(status_code=404, detail="QA issue not found.")

        script = session.query(Script).filter(
            Script.book_id == book_id,
            Script.episode == issue.episode,
        ).first()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found.")

        current_meta = safe_json_loads(issue.meta_info, {})
        failed_rechecks = int(current_meta.get("auto_fix_recheck_fail_count") or 0)
        if failed_rechecks >= int(req.stop_after_failed_rechecks or 2):
            raise HTTPException(status_code=409, detail=f"Auto-fix stopped because this issue has already failed recheck {failed_rechecks} times.")

        issue_episode = issue.episode
        excerpt, options = _generate_qa_fix_options_for_issue(
            issue,
            script,
            req.mode or issue.fix_mode or "auto",
            option_count=req.option_count,
            custom_requirement=req.custom_requirement,
        )
        selected_option = _select_best_qa_fix_option(issue, excerpt, options)
        if not selected_option:
            raise HTTPException(status_code=400, detail="No usable auto-fix option generated.")
        guard = _qa_fix_guard_result(
            issue,
            script.content or "",
            str(selected_option.get("patched_text") or ""),
            int(req.max_diff_lines or 16),
            float(req.max_length_delta_ratio or 0.8),
        )
        if guard["blocked"]:
            raise HTTPException(status_code=409, detail=f"Auto-fix blocked by safety guard: {', '.join(guard['reasons'])}")

        meta = safe_json_loads(issue.meta_info, {})
        meta["repair_options"] = options
        meta["last_generated_mode"] = req.mode
        meta["auto_fix_selected_option_id"] = selected_option.get("id") or "A"
        meta["auto_fix_selection_reason"] = "best-scored-option"
        meta["auto_fix_guard"] = {
            "changed_line_count": guard["changed_line_count"],
            "length_delta_ratio": guard["length_delta_ratio"],
        }
        issue.meta_info = json.dumps(meta, ensure_ascii=False)
        version_id, diff_text, issue_episode = _apply_qa_fix_internal(
            session,
            book_id,
            issue,
            script,
            req.mode or issue.fix_mode or "auto",
            str(selected_option.get("patched_text") or ""),
            f"Auto fix: {issue.title or issue.description}",
            str(selected_option.get("id") or "A"),
            req.operator_name,
            req.rerun_qa,
        )
        session.commit()

    recheck_payload = None
    if req.rerun_qa:
        background.add_task(_run_episode_recheck_in_background, book_id, issue_episode, version_id, issue_key)
        recheck_payload = {"status": "running", "message": "QA recheck started in background."}

    with Session() as session:
        version = session.query(ScriptVersion).filter(ScriptVersion.id == version_id).first()
        issue = session.query(QAIssue).filter(QAIssue.book_id == book_id, QAIssue.issue_key == issue_key).first()

    return {
        "ok": True,
        "issue": _serialize_qa_issue(issue),
        "episode": issue_episode,
        "selected_option": selected_option,
        "selection_reason": "best-scored-option",
        "guard": {
            "changed_line_count": guard["changed_line_count"],
            "length_delta_ratio": guard["length_delta_ratio"],
        },
        "diff_text": diff_text,
        "version": _serialize_script_version(version),
        "recheck": recheck_payload,
    }


@app.post("/api/books/{book_id}/qa/episodes/{episode}/auto-fix")
def auto_fix_qa_episode(book_id: int, episode: int, req: QAAutoFixRequest, background: BackgroundTasks):
    from models import QAIssue, Script, ScriptVersion

    applied = []
    failed = []
    version_ids = []
    with Session() as session:
        script = session.query(Script).filter(
            Script.book_id == book_id,
            Script.episode == episode,
        ).first()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found.")

        issues = session.query(QAIssue).filter(
            QAIssue.book_id == book_id,
            QAIssue.episode == episode,
        ).all()
        open_issues = [item for item in issues if item.fix_status not in {"recheck_passed", "rechecking"}]
        ordered_issues = sorted(
            open_issues,
            key=lambda item: (
                0 if item.line_start else 1,
                -(item.line_start or 0),
                -int(item.id or 0),
            ),
        )[: max(1, int(req.max_issues or 10))]

        for issue in ordered_issues:
            try:
                issue_meta = safe_json_loads(issue.meta_info, {})
                failed_rechecks = int(issue_meta.get("auto_fix_recheck_fail_count") or 0)
                if failed_rechecks >= int(req.stop_after_failed_rechecks or 2):
                    failed.append({
                        "issue_id": issue.issue_key,
                        "title": issue.title,
                        "failure_kind": "stopped_after_failed_rechecks",
                        "reason": f"Auto-fix stopped because recheck has already failed {failed_rechecks} times.",
                    })
                    continue
                excerpt, options = _generate_qa_fix_options_for_issue(
                    issue,
                    script,
                    req.mode or issue.fix_mode or "auto",
                    option_count=req.option_count,
                    custom_requirement=req.custom_requirement,
                )
                selected_option = _select_best_qa_fix_option(issue, excerpt, options)
                if not selected_option:
                    failed.append({
                        "issue_id": issue.issue_key,
                        "title": issue.title,
                        "failure_kind": "no_usable_option",
                        "reason": "No usable auto-fix option generated.",
                    })
                    continue
                guard = _qa_fix_guard_result(
                    issue,
                    script.content or "",
                    str(selected_option.get("patched_text") or ""),
                    int(req.max_diff_lines or 16),
                    float(req.max_length_delta_ratio or 0.8),
                )
                if guard["blocked"]:
                    failed.append({
                        "issue_id": issue.issue_key,
                        "title": issue.title,
                        "failure_kind": "safety_guard_blocked",
                        "reason": f"Auto-fix blocked by safety guard: {', '.join(guard['reasons'])}",
                    })
                    continue

                meta = safe_json_loads(issue.meta_info, {})
                meta["repair_options"] = options
                meta["last_generated_mode"] = req.mode
                meta["auto_fix_selected_option_id"] = selected_option.get("id") or "A"
                meta["auto_fix_selection_reason"] = "best-scored-option"
                meta["auto_fix_guard"] = {
                    "changed_line_count": guard["changed_line_count"],
                    "length_delta_ratio": guard["length_delta_ratio"],
                }
                issue.meta_info = json.dumps(meta, ensure_ascii=False)
                version_id, diff_text, _ = _apply_qa_fix_internal(
                    session,
                    book_id,
                    issue,
                    script,
                    req.mode or issue.fix_mode or "auto",
                    str(selected_option.get("patched_text") or ""),
                    f"Episode auto-fix: {issue.title or issue.description}",
                    str(selected_option.get("id") or "A"),
                    req.operator_name,
                    False,
                )
                version_ids.append(version_id)
                applied.append({
                    "issue_id": issue.issue_key,
                    "title": issue.title,
                    "issue_type": issue.issue_type,
                    "option_id": selected_option.get("id") or "A",
                    "selection_reason": "best-scored-option",
                    "strategy": selected_option.get("strategy") or "",
                    "guard": {
                        "changed_line_count": guard["changed_line_count"],
                        "length_delta_ratio": guard["length_delta_ratio"],
                    },
                    "diff_text": diff_text,
                    "version_id": version_id,
                })
            except Exception as exc:
                failed.append({
                    "issue_id": issue.issue_key,
                    "title": issue.title,
                    "failure_kind": "runtime_error",
                    "reason": str(exc),
                })

        session.commit()

    recheck_payload = None
    if req.rerun_qa and (applied or failed):
        background.add_task(_run_episode_recheck_in_background, book_id, episode, None, None)
        recheck_payload = {"status": "running", "message": "Episode QA recheck started in background."}

    with Session() as session:
        versions = session.query(ScriptVersion).filter(
            ScriptVersion.id.in_(version_ids)
        ).order_by(ScriptVersion.version_no.desc(), ScriptVersion.id.desc()).all() if version_ids else []

    return {
        "ok": True,
        "episode": episode,
        "applied_count": len(applied),
        "failed_count": len(failed),
        "applied": applied,
        "failed": failed,
        "report": {
            "episode": episode,
            "applied_count": len(applied),
            "failed_count": len(failed),
            "failed_summary": _summarize_qa_auto_fix_failed_items(failed),
            "applied": applied,
            "failed": failed,
        },
        "versions": [_serialize_script_version(version) for version in versions],
        "recheck": recheck_payload,
    }


@app.post("/api/books/{book_id}/qa/issues/{issue_key}/apply-fix")
def apply_qa_fix(book_id: int, issue_key: str, req: QAApplyFixRequest, background: BackgroundTasks):
    from models import QAIssue, Script, ScriptVersion

    issue_episode = None
    version_id = None
    with Session() as session:
        issue = session.query(QAIssue).filter(
            QAIssue.book_id == book_id,
            QAIssue.issue_key == issue_key,
        ).first()
        if not issue:
            raise HTTPException(status_code=404, detail="QA issue not found.")

        script = session.query(Script).filter(
            Script.book_id == book_id,
            Script.episode == issue.episode,
        ).first()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found.")
        if not (req.patched_text or "").strip():
            raise HTTPException(status_code=400, detail="patched_text is required.")

        version_id, diff_text, issue_episode = _apply_qa_fix_internal(
            session,
            book_id,
            issue,
            script,
            req.mode,
            req.patched_text.strip(),
            req.change_reason or issue.description,
            req.option_id,
            req.operator_name or "user",
            req.rerun_qa,
        )
        session.commit()

    recheck_payload = None
    if req.rerun_qa:
        background.add_task(_run_episode_recheck_in_background, book_id, issue_episode, version_id, issue_key)
        recheck_payload = {"status": "running", "message": "QA recheck started in background."}
    with Session() as session:
        version = session.query(ScriptVersion).filter(ScriptVersion.id == version_id).first()

    return {
        "ok": True,
        "issue_id": issue_key,
        "episode": issue_episode,
        "diff_text": diff_text,
        "version": _serialize_script_version(version),
        "recheck": recheck_payload,
    }


@app.post("/api/books/{book_id}/scripts/{episode}/versions/{version_id}/rollback")
def rollback_script_version(book_id: int, episode: int, version_id: int, req: QARollbackRequest, background: BackgroundTasks):
    from models import QAIssue, Script, ScriptVersion

    created_version_id = None
    with Session() as session:
        script = session.query(Script).filter(
            Script.book_id == book_id,
            Script.episode == episode,
        ).first()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found.")

        target = session.query(ScriptVersion).filter(
            ScriptVersion.book_id == book_id,
            ScriptVersion.episode == episode,
            ScriptVersion.id == version_id,
        ).first()
        if not target:
            raise HTTPException(status_code=404, detail="Version not found.")

        _ensure_script_baseline_version(session, script)
        before_text = script.content or ""
        rollback_text = target.content_before if target.change_type != "baseline" else target.content_after
        diff_text = _build_script_diff(before_text, rollback_text, episode)
        version_no = _next_script_version_no(session, book_id, episode)
        version = ScriptVersion(
            book_id=book_id,
            episode=episode,
            script_id=script.id,
            version_no=version_no,
            label=f"v{version_no} 回滚到 {target.label}",
            change_type="rollback",
            change_reason=f"Rollback from version {target.id}",
            qa_issue_key=target.qa_issue_key or "",
            operator_name=req.operator_name or "user",
            content_before=before_text,
            content_after=rollback_text,
            diff_text=diff_text,
            recheck_status="running" if req.rerun_qa else "not_run",
            recheck_summary="QA recheck is running in background." if req.rerun_qa else "Rolled back without recheck",
            meta_info=json.dumps({"rollback_target_id": target.id}, ensure_ascii=False),
        )
        session.add(version)
        script.content = rollback_text
        script.word_count = len(rollback_text or "")
        if target.qa_issue_key:
            issue = session.query(QAIssue).filter(QAIssue.issue_key == target.qa_issue_key).first()
            if issue:
                issue.fix_status = "rolled_back"
                issue.status_reason = f"Rolled back from {target.label}"
                issue.updated_at = datetime.now()
        session.commit()
        session.refresh(version)
        created_version_id = version.id

    recheck_payload = None
    if req.rerun_qa:
        background.add_task(_run_episode_recheck_in_background, book_id, episode, created_version_id, None)
        recheck_payload = {"status": "running", "message": "QA recheck started in background."}
    with Session() as session:
        version = session.query(ScriptVersion).filter(ScriptVersion.id == created_version_id).first()

    return {
        "ok": True,
        "episode": episode,
        "diff_text": diff_text,
        "version": _serialize_script_version(version),
        "recheck": recheck_payload,
    }


@app.patch("/api/books/{book_id}")
def update_book(book_id: int, data: dict):
    """Update book metadata, e.g. rename."""
    from models import Session, Book
    with Session() as s:
        book = s.get(Book, book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
        if "title" in data:
            book.title = data["title"]
        s.commit()
        return {"ok": True, "title": book.title}


@app.put("/api/bibles/{book_id}")
def update_bible(book_id: int, data: dict):
    """Save edited bible content."""
    from models import Session, BookBible
    with Session() as s:
        bible = s.query(BookBible).filter(BookBible.book_id == book_id).first()
        if not bible:
            bible = BookBible(book_id=book_id, content=data.get("content", ""))
            s.add(bible)
        else:
            bible.content = data.get("content", "")
        s.commit()
    return {"ok": True}


@app.put("/api/outlines/{outline_id}")
def update_outline(outline_id: int, data: dict):
    """Save edited outline."""
    from models import Session, EpisodeOutline
    with Session() as s:
        outline = s.query(EpisodeOutline).filter(EpisodeOutline.id == outline_id).first()
        if not outline:
            raise HTTPException(status_code=404, detail="Outline not found")
        if "title" in data:
            outline.title = data["title"]
        if "core_event" in data:
            outline.core_event = data["core_event"]
        if "opening_hook" in data:
            outline.opening_hook = data["opening_hook"]
        if "core_conflict" in data:
            outline.core_conflict = data["core_conflict"]
        if "climax" in data:
            outline.climax = data["climax"]
        if "ending_hook" in data:
            outline.ending_hook = data["ending_hook"]
        s.commit()
    return {"ok": True}


@app.put("/api/scripts/{script_id}")
def update_script(script_id: int, data: dict):
    """Save edited script."""
    from models import Session, Script
    with Session() as s:
        script = s.query(Script).filter(Script.id == script_id).first()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")
        if "content" in data:
            script.content = data["content"]
            script.word_count = len(data["content"])
        s.commit()
    return {"ok": True}


@app.post("/api/cli/serve")
def serve_check():
    return {"ok": True, "message": "DevCanvas server running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)
