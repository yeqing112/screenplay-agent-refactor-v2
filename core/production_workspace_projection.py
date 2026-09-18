"""Read-only Production Workspace projection.

This module is the UI read model for the production authority spine.  It is
deliberately pointer-first: a row that is merely the latest approved revision
is not considered current unless the corresponding authority pointer and
fresh authority envelope agree.  The projection never mutates the database,
creates artifacts, or calls a provider.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable


STAGE_KEYS = (
    "CONTENT",
    "SCRIPT_IR",
    "DIRECTOR_TREATMENT",
    "SCENE_BLOCKING",
    "SHOT_PLAN",
    "STORYBOARD",
    "PROMPT_IR",
    "VISUAL_ASSET",
    "REFERENCE",
    "MEDIA",
    "QA",
)

STAGE_LABELS = {
    "CONTENT": "内容",
    "SCRIPT_IR": "剧本权威",
    "DIRECTOR_TREATMENT": "导演方案",
    "SCENE_BLOCKING": "场面调度",
    "SHOT_PLAN": "镜头规划",
    "STORYBOARD": "分镜物化",
    "PROMPT_IR": "PromptIR",
    "VISUAL_ASSET": "视觉资产",
    "REFERENCE": "参考图",
    "MEDIA": "媒体",
    "QA": "QA",
}

STATE_PRIORITY = {
    "blocked": 80,
    "stale": 70,
    "needs_action": 60,
    "warning": 50,
    "in_progress": 40,
    "ready": 30,
    "complete": 20,
    # A project/episode with one completed stage and another untouched stage
    # must not be presented as complete.
    "not_started": 25,
}

BLOCKER_COPY = {
    "CONTENT_MISSING": ("还没有内容", "先导入故事内容。", "content"),
    "SCRIPT_SOURCE_MISSING": ("缺少分集剧本", "先生成或确认这一集的剧本。", "scripts"),
    "SCRIPT_IR_AUTHORITY_MISSING": ("剧本还未确认", "需要先确认当前剧本的权威版本。", "scripts"),
    "SCRIPT_IR_STALE": ("剧本已过期", "上游内容变化后，当前剧本权威需要重新确认。", "scripts"),
    "DIRECTOR_TREATMENT_MISSING": ("导演方案待设计", "为当前场景补齐导演方案。", "scripts"),
    "DIRECTOR_TREATMENT_STALE": ("导演方案需要更新", "上游剧本变化后，重新确认导演方案。", "scripts"),
    "SCENE_BLOCKING_MISSING": ("场面调度待设计", "补齐人物位置、空间关系和运动规则。", "storyboard"),
    "SCENE_BLOCKING_STALE": ("场面调度需要更新", "上游导演方案变化后，重新确认场面调度。", "storyboard"),
    "SHOT_PLAN_MISSING": ("镜头规划待确认", "确认这一场的镜头数量和镜头动作。", "storyboard"),
    "SHOT_PLAN_STALE": ("镜头规划需要更新", "上游场面调度变化后，重新确认镜头规划。", "storyboard"),
    "STORYBOARD_MISSING": ("分镜还未物化", "把已确认的镜头规划物化为分镜。", "storyboard"),
    "STORYBOARD_STALE": ("分镜需要更新", "当前分镜不再对应最新镜头规划。", "storyboard"),
    "PROMPT_IR_MISSING": ("提示词待编译", "为当前分镜编译 PromptIR。", "storyboard"),
    "PROMPT_IR_STALE": ("提示词需要更新", "资产或上游镜头变化后，重新编译 PromptIR。", "storyboard"),
    "PROMPT_IR_NOT_QUALIFIED": ("提示词尚未确认", "先完成 PromptIR 质检和确认。", "storyboard"),
    "VISUAL_ASSET_MISSING": ("视觉资产待设计", "先完成角色、场景或道具的视觉设计。", "assets"),
    "VISUAL_ASSET_STALE": ("视觉资产需要更新", "当前资产版本已过期，不能作为生产约束。", "assets"),
    "REFERENCE_MISSING": ("参考图待生成", "为当前资产准备正式参考图。", "assets"),
    "REFERENCE_NOT_LOCKED": ("参考图待锁定", "选择并锁定正式参考图后再进入生产。", "assets"),
    "MEDIA_MISSING": ("媒体尚未生成", "完成参考图后，再按镜头提交图片或视频生成。", "storyboard"),
    "MEDIA_AUTHORITY_NOT_ESTABLISHED": ("媒体状态待验收", "媒体结果需要在镜头工作台完成验收。", "qa"),
    "QA_OPEN": ("还有 QA 问题", "处理并复检当前生产问题。", "qa"),
}


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _text(value: Any) -> str:
    return str(value or "").strip()


def _fresh(value: Any) -> bool:
    return _text(value).upper() in {"", "FRESH", "CURRENT"}


def _qualified(value: Any) -> bool:
    return _text(value).upper() in {
        "PRODUCTION_QUALIFIED",
        "AUTHORITY_BOUND",
        "PROMPT_IR_QUALIFIED",
        "MATERIALIZED",
        "PRODUCTION_READY",
        "SPEC_APPROVED",
        "REFERENCE_LOCKED",
        "APPROVED",
    }


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def make_blocker(*, code: str, book_id: int, episode: int | None = None, scene_id: str | None = None, shot_id: str | None = None, asset_key: str | None = None, scope: str = "project", detail: str | None = None) -> dict[str, Any]:
    title, description, target_section = BLOCKER_COPY.get(code, (code, "需要处理生产链路中的阻塞。", "dashboard"))
    return {
        "code": code,
        "title": title,
        "description": detail or description,
        "severity": "blocked" if code.endswith("MISSING") or code in {"QA_OPEN", "PROMPT_IR_NOT_QUALIFIED"} else "warning",
        "stage": code.split("_")[0],
        "scope": scope,
        "book_id": int(book_id),
        "episode": episode,
        "scene_id": scene_id,
        "shot_id": shot_id,
        "asset_key": asset_key,
        "recommended_action": title,
        "target_section": target_section,
        "target_params": {
            "episode": episode,
            "scene_id": scene_id,
            "shot_id": shot_id,
            "asset_key": asset_key,
        },
    }


def _state_from_items(items: Iterable[dict[str, Any]], *, empty_state: str = "not_started") -> str:
    values = list(items)
    if not values:
        return empty_state
    return max((str(item.get("state") or empty_state) for item in values), key=lambda value: STATE_PRIORITY.get(value, 0))


def _counts(items: list[dict[str, Any]]) -> dict[str, int]:
    result = {"total": len(items), "complete": 0, "ready": 0, "blocked": 0, "stale": 0, "needs_action": 0, "warning": 0, "not_started": 0}
    for item in items:
        state = str(item.get("state") or "not_started")
        result[state] = result.get(state, 0) + 1
    return result


def _stage(*, key: str, state: str, detail: str, blockers: list[dict[str, Any]], counts: dict[str, int] | None = None, target_route: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "key": key,
        "label": STAGE_LABELS[key],
        "state": state,
        "detail": detail,
        "completed": state == "complete",
        "blocked": state == "blocked",
        "stale": state == "stale",
        "warning": state == "warning",
        "counts": counts or {"total": 1, state: 1},
        "reason_codes": sorted({str(item.get("code")) for item in blockers}),
        "target_route": target_route or {"section": "dashboard"},
        "blockers": blockers,
    }


def _authority_item(*, key: str, row: Any, pointer: Any, authority: Any, required_status: str | None = None) -> dict[str, Any]:
    row_status = _text(getattr(row, "qualification_state", "")) or _text(getattr(row, "production_status", ""))
    pointer_status = _text(getattr(pointer, "qualification_state", ""))
    authority_status = _text(getattr(authority, "qualification_state", "")) if authority else ""
    stale = not (_fresh(getattr(row, "stale_status", "")) and _fresh(getattr(authority, "stale_status", "")) if authority else _fresh(getattr(row, "stale_status", "")))
    if not row or not pointer or not authority:
        return {"key": key, "state": "blocked", "reason": "missing_authority"}
    if stale:
        return {"key": key, "state": "stale", "reason": "stale_authority"}
    if required_status and row_status != required_status:
        return {"key": key, "state": "blocked", "reason": "qualification_not_met"}
    if not (_qualified(row_status) or _qualified(pointer_status) or _qualified(authority_status)):
        return {"key": key, "state": "blocked", "reason": "qualification_not_met"}
    return {"key": key, "state": "complete", "reason": "current_authority", "row_id": getattr(row, "id", None), "revision": getattr(row, "revision", None)}


def _script_scene_ids(script_ir: Any) -> set[str]:
    payload = _json(getattr(script_ir, "payload_json", "{}"), {}) if script_ir else {}
    scenes = payload.get("scenes") if isinstance(payload, dict) else []
    result: set[str] = set()
    if isinstance(scenes, list):
        for item in scenes:
            if isinstance(item, dict):
                value = _text(item.get("scene_id") or item.get("id") or item.get("scene_key") or item.get("name"))
            else:
                value = _text(item)
            if value:
                result.add(value)
    return result


def _scene_stage(*, key: str, code_missing: str, code_stale: str, book_id: int, episode: int, scene_ids: list[str], pointers: dict[str, Any], rows: dict[int, Any], authorities: dict[tuple[int, str], Any], target_section: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for scene_id in scene_ids:
        pointer = pointers.get(scene_id)
        if not pointer:
            items.append({"scene_id": scene_id, "state": "needs_action", "reason": "pointer_missing"})
            blockers.append(make_blocker(code=code_missing, book_id=book_id, episode=episode, scene_id=scene_id, scope="scene"))
            continue
        row_id = int(getattr(pointer, {"DIRECTOR_TREATMENT": "treatment_id", "SCENE_BLOCKING": "blocking_id", "SHOT_PLAN": "shot_plan_id"}[key]))
        row = rows.get(row_id)
        authority = authorities.get((row_id, _text(getattr(pointer, "authority_envelope_fingerprint", ""))))
        item = _authority_item(key=key, row=row, pointer=pointer, authority=authority)
        item["scene_id"] = scene_id
        items.append(item)
        if item["state"] == "stale":
            blockers.append(make_blocker(code=code_stale, book_id=book_id, episode=episode, scene_id=scene_id, scope="scene"))
        elif item["state"] != "complete":
            blockers.append(make_blocker(code=code_missing, book_id=book_id, episode=episode, scene_id=scene_id, scope="scene", detail="当前权威记录不完整，需要重新确认。"))
    state = _state_from_items(items)
    return _stage(key=key, state=state, detail=f"{len([item for item in items if item.get('state') == 'complete'])}/{len(items)} 个场景已确认" if items else "等待上游剧本场景", blockers=blockers, counts=_counts(items), target_route={"section": target_section, "episode": episode}), items


def build_production_workspace_projection(session: Any, *, book_id: int) -> dict[str, Any]:
    """Build the current authority projection without any database mutation."""
    from models import (
        Book, Chapter, DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer,
        QAIssue, PromptIRAuthority, PromptIRPointer, PromptIRVersion, SceneBlocking, SceneBlockingAuthority,
        SceneBlockingPointer, Script, ScriptIRVersion, ShotPlan, ShotPlanAuthority, ShotPlanPointer,
        StoryboardMaterializationPointer, StoryboardMaterializationSet, StoryboardShot,
        VisualAssetPointer, VisualAssetVersion, VisualReferenceAuthority,
    )

    book = session.query(Book).filter_by(id=book_id).first()
    scripts = session.query(Script).filter_by(book_id=book_id).order_by(Script.episode.asc(), Script.id.desc()).all()
    latest_scripts: dict[int, Any] = {}
    for row in scripts:
        latest_scripts.setdefault(int(row.episode), row)
    ir_ids = [int(row.current_script_ir_version_id) for row in latest_scripts.values() if row.current_script_ir_version_id]
    ir_rows = {int(row.id): row for row in session.query(ScriptIRVersion).filter(ScriptIRVersion.id.in_(ir_ids)).all()} if ir_ids else {}

    treatment_pointers = session.query(DirectorTreatmentPointer).filter_by(book_id=book_id).all()
    treatment_rows = {int(row.id): row for row in session.query(DirectorTreatment).filter_by(book_id=book_id).all()}
    treatment_authorities = {(int(row.treatment_id), _text(row.envelope_fingerprint)): row for row in session.query(DirectorTreatmentAuthority).filter_by(book_id=book_id).all()}
    blocking_pointers = session.query(SceneBlockingPointer).filter_by(book_id=book_id).all()
    blocking_rows = {int(row.id): row for row in session.query(SceneBlocking).filter_by(book_id=book_id).all()}
    blocking_authorities = {(int(row.blocking_id), _text(row.envelope_fingerprint)): row for row in session.query(SceneBlockingAuthority).filter_by(book_id=book_id).all()}
    plan_pointers = session.query(ShotPlanPointer).filter_by(book_id=book_id).all()
    plan_rows = {int(row.id): row for row in session.query(ShotPlan).filter_by(book_id=book_id).all()}
    plan_authorities = {(int(row.shot_plan_id), _text(row.envelope_fingerprint)): row for row in session.query(ShotPlanAuthority).filter_by(book_id=book_id).all()}
    materialization_pointers = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id).all()
    materialization_sets = {int(row.id): row for row in session.query(StoryboardMaterializationSet).filter_by(book_id=book_id).all()}
    storyboard_shots = session.query(StoryboardShot).filter_by(book_id=book_id).all()
    prompt_pointers = session.query(PromptIRPointer).filter_by(book_id=book_id).all()
    prompt_versions = {int(row.id): row for row in session.query(PromptIRVersion).filter_by(book_id=book_id).all()}
    prompt_authorities = {int(row.prompt_ir_version_id): row for row in session.query(PromptIRAuthority).filter_by(book_id=book_id).all()}
    asset_pointers = session.query(VisualAssetPointer).filter_by(book_id=book_id).all()
    asset_versions = {int(row.id): row for row in session.query(VisualAssetVersion).filter_by(book_id=book_id).all()}
    reference_authorities = session.query(VisualReferenceAuthority).filter_by(asset_key="__never__").all()
    # VisualReferenceAuthority has no book_id column; scope through the asset
    # keys/version ids represented by this book's current pointers.
    asset_version_ids = {int(pointer.current_version_id) for pointer in asset_pointers}
    reference_authorities = session.query(VisualReferenceAuthority).filter(VisualReferenceAuthority.asset_version_id.in_(asset_version_ids)).all() if asset_version_ids else []
    qa_rows = session.query(QAIssue).filter_by(book_id=book_id).all()
    chapters = session.query(Chapter).filter_by(book_id=book_id).count()

    episode_ids: set[int] = set(latest_scripts)
    for rows in (treatment_pointers, blocking_pointers, plan_pointers, materialization_pointers, storyboard_shots, prompt_pointers):
        episode_ids.update(int(getattr(row, "episode", 0) or 0) for row in rows if int(getattr(row, "episode", 0) or 0) > 0)
    if not episode_ids and book:
        episode_ids.update(range(1, max(1, int(getattr(book, "chapter_count", 1) or 1)) + 1))
    episode_ids = {item for item in episode_ids if item > 0}

    treatment_by_episode = defaultdict(dict)
    for pointer in treatment_pointers:
        treatment_by_episode[int(pointer.episode)][_text(pointer.scene_id)] = pointer
    blocking_by_episode = defaultdict(dict)
    for pointer in blocking_pointers:
        blocking_by_episode[int(pointer.episode)][_text(pointer.scene_id)] = pointer
    plan_by_episode = defaultdict(dict)
    for pointer in plan_pointers:
        plan_by_episode[int(pointer.episode)][_text(pointer.scene_id)] = pointer
    materialization_by_episode = defaultdict(dict)
    for pointer in materialization_pointers:
        materialization_by_episode[int(pointer.episode)][_text(pointer.scene_id)] = pointer

    all_episode_payloads: list[dict[str, Any]] = []
    all_shot_payloads: list[dict[str, Any]] = []
    all_asset_payloads: list[dict[str, Any]] = []

    for episode in sorted(episode_ids):
        script = latest_scripts.get(episode)
        script_ir = ir_rows.get(int(script.current_script_ir_version_id)) if script and script.current_script_ir_version_id else None
        script_stage_blockers: list[dict[str, Any]] = []
        if not script:
            script_stage = _stage(key="SCRIPT_IR", state="not_started", detail="还没有这一集的剧本", blockers=[make_blocker(code="SCRIPT_SOURCE_MISSING", book_id=book_id, episode=episode)])
        elif not script_ir:
            script_stage_blockers.append(make_blocker(code="SCRIPT_IR_AUTHORITY_MISSING", book_id=book_id, episode=episode))
            script_stage = _stage(key="SCRIPT_IR", state="blocked", detail="剧本存在，但没有当前 ScriptIR 权威指针", blockers=script_stage_blockers, target_route={"section": "scripts", "episode": episode})
        elif not _fresh(getattr(script_ir, "stale_status", "")):
            script_stage_blockers.append(make_blocker(code="SCRIPT_IR_STALE", book_id=book_id, episode=episode))
            script_stage = _stage(key="SCRIPT_IR", state="stale", detail="当前 ScriptIR 已过期", blockers=script_stage_blockers, target_route={"section": "scripts", "episode": episode})
        elif not (_qualified(getattr(script_ir, "qualification_state", "")) or _text(getattr(script_ir, "status", "")).lower() in {"qualified", "production_qualified"}):
            script_stage_blockers.append(make_blocker(code="SCRIPT_IR_AUTHORITY_MISSING", book_id=book_id, episode=episode, detail="当前 ScriptIR 尚未达到生产确认状态。"))
            script_stage = _stage(key="SCRIPT_IR", state="blocked", detail="ScriptIR 尚未达到生产确认状态", blockers=script_stage_blockers, target_route={"section": "scripts", "episode": episode})
        else:
            script_stage = _stage(key="SCRIPT_IR", state="complete", detail=f"ScriptIR v{getattr(script_ir, 'revision', '')} 已确认", blockers=[], target_route={"section": "scripts", "episode": episode})

        scene_ids = {scene for scene in treatment_by_episode[episode] | blocking_by_episode[episode] | plan_by_episode[episode] | materialization_by_episode[episode] if scene}
        scene_ids.update(_script_scene_ids(script_ir))
        if not scene_ids:
            scene_ids = {"episode:%s" % episode} if script_stage["state"] == "complete" else set()
        scene_list = sorted(scene_ids)
        treatment_stage, _ = _scene_stage(key="DIRECTOR_TREATMENT", code_missing="DIRECTOR_TREATMENT_MISSING", code_stale="DIRECTOR_TREATMENT_STALE", book_id=book_id, episode=episode, scene_ids=scene_list, pointers=treatment_by_episode[episode], rows=treatment_rows, authorities=treatment_authorities, target_section="scripts")
        blocking_stage, _ = _scene_stage(key="SCENE_BLOCKING", code_missing="SCENE_BLOCKING_MISSING", code_stale="SCENE_BLOCKING_STALE", book_id=book_id, episode=episode, scene_ids=scene_list, pointers=blocking_by_episode[episode], rows=blocking_rows, authorities=blocking_authorities, target_section="storyboard")
        plan_stage, _ = _scene_stage(key="SHOT_PLAN", code_missing="SHOT_PLAN_MISSING", code_stale="SHOT_PLAN_STALE", book_id=book_id, episode=episode, scene_ids=scene_list, pointers=plan_by_episode[episode], rows=plan_rows, authorities=plan_authorities, target_section="storyboard")

        episode_shot_rows = [row for row in storyboard_shots if int(row.episode) == episode and row.materialization_set_id]
        current_set_ids = {int(pointer.materialization_set_id) for pointer in materialization_by_episode[episode].values()}
        material_items: list[dict[str, Any]] = []
        material_blockers: list[dict[str, Any]] = []
        for scene_id in scene_list:
            pointer = materialization_by_episode[episode].get(scene_id)
            if not pointer:
                material_items.append({"scene_id": scene_id, "state": "needs_action"})
                material_blockers.append(make_blocker(code="STORYBOARD_MISSING", book_id=book_id, episode=episode, scene_id=scene_id, scope="scene"))
                continue
            material_set = materialization_sets.get(int(pointer.materialization_set_id))
            set_shots = [row for row in episode_shot_rows if int(row.materialization_set_id or 0) == int(pointer.materialization_set_id)]
            expected = int(getattr(material_set, "expected_shot_count", len(set_shots)) or 0) if material_set else 0
            valid = bool(material_set and _fresh(getattr(material_set, "stale_status", "")) and _fresh(getattr(pointer, "qualification_state", "")) and expected == len(set_shots) and expected > 0)
            state = "complete" if valid else ("stale" if material_set and not _fresh(getattr(material_set, "stale_status", "")) else "blocked")
            material_items.append({"scene_id": scene_id, "state": state, "shot_count": len(set_shots), "expected_shot_count": expected})
            if state == "stale":
                material_blockers.append(make_blocker(code="STORYBOARD_STALE", book_id=book_id, episode=episode, scene_id=scene_id, scope="scene"))
            elif state != "complete":
                material_blockers.append(make_blocker(code="STORYBOARD_MISSING", book_id=book_id, episode=episode, scene_id=scene_id, scope="scene", detail="分镜物化集合缺失或镜头数量不一致。"))
        storyboard_stage = _stage(key="STORYBOARD", state=_state_from_items(material_items), detail=f"{sum(1 for item in material_items if item.get('state') == 'complete')}/{len(material_items)} 个场景已物化" if material_items else "等待镜头物化", blockers=material_blockers, counts=_counts(material_items), target_route={"section": "storyboard", "episode": episode})

        prompt_items: list[dict[str, Any]] = []
        prompt_blockers: list[dict[str, Any]] = []
        episode_shot_ids = {int(row.id): row for row in episode_shot_rows if int(row.materialization_set_id or 0) in current_set_ids}
        for shot in sorted(episode_shot_ids.values(), key=lambda row: int(row.shot_id)):
            pointer = next((item for item in prompt_pointers if int(item.storyboard_shot_id) == int(shot.id)), None)
            version = prompt_versions.get(int(pointer.prompt_ir_version_id)) if pointer else None
            authority = prompt_authorities.get(int(pointer.prompt_ir_version_id)) if pointer else None
            current = bool(pointer and version and authority and _fresh(getattr(version, "stale_status", "")) and _fresh(getattr(authority, "stale_status", "")))
            qualified = current and (_qualified(getattr(pointer, "qualification_state", "")) or _qualified(getattr(version, "qualification_state", "")) or _qualified(getattr(authority, "qualification_state", "")))
            state = "complete" if qualified else ("stale" if pointer and version and not _fresh(getattr(version, "stale_status", "")) else "needs_action")
            prompt_items.append({"shot_id": str(shot.shot_id), "storyboard_shot_id": int(shot.id), "state": state})
            if state == "stale":
                prompt_blockers.append(make_blocker(code="PROMPT_IR_STALE", book_id=book_id, episode=episode, shot_id=str(shot.shot_id), scope="shot"))
            elif state != "complete":
                code = "PROMPT_IR_MISSING" if not pointer else "PROMPT_IR_NOT_QUALIFIED"
                prompt_blockers.append(make_blocker(code=code, book_id=book_id, episode=episode, shot_id=str(shot.shot_id), scope="shot"))
            all_shot_payloads.append({"episode": episode, "shot_id": str(shot.shot_id), "storyboard_shot_id": int(shot.id), "scene_id": _text(shot.scene_id), "plan_shot_id": _text(shot.plan_shot_id), "duration": int(shot.duration or 0), "camera": {"angle": _text(shot.camera_angle), "movement": _text(shot.camera_movement), "speed": _text(shot.camera_speed)}, "action": _text(shot.action_process), "entry_state": _text(shot.start_state), "exit_state": _text(shot.end_state), "prompt_ir_state": state, "reference_state": "unknown", "media_state": _text(shot.asset_status) or "not_started"})
        prompt_stage = _stage(key="PROMPT_IR", state=_state_from_items(prompt_items, empty_state="not_started"), detail=f"{sum(1 for item in prompt_items if item.get('state') == 'complete')}/{len(prompt_items)} 个镜头已确认" if prompt_items else "等待分镜物化", blockers=prompt_blockers, counts=_counts(prompt_items), target_route={"section": "storyboard", "episode": episode})

        episode_qa = [row for row in qa_rows if int(row.episode) == episode and _text(getattr(row, "fix_status", "")).lower() not in {"resolved", "closed", "accepted", "recheck_passed", "wont_fix"}]
        qa_blockers = [make_blocker(code="QA_OPEN", book_id=book_id, episode=episode, scope="episode", detail=f"{len(episode_qa)} 个 QA 问题仍未关闭。") for _ in ([1] if episode_qa else [])]
        qa_stage = _stage(key="QA", state="blocked" if episode_qa else ("complete" if episode_shot_rows else "not_started"), detail=f"{len(episode_qa)} 个问题待处理" if episode_qa else ("没有未关闭 QA" if episode_shot_rows else "等待分镜"), blockers=qa_blockers, target_route={"section": "qa", "episode": episode})

        episode_assets = [pointer for pointer in asset_pointers if int(pointer.book_id) == book_id]
        asset_items: list[dict[str, Any]] = []
        reference_items: list[dict[str, Any]] = []
        asset_blockers: list[dict[str, Any]] = []
        reference_blockers: list[dict[str, Any]] = []
        refs_by_version: dict[int, list[Any]] = defaultdict(list)
        for ref in reference_authorities:
            refs_by_version[int(ref.asset_version_id)].append(ref)
        for pointer in episode_assets:
            version = asset_versions.get(int(pointer.current_version_id))
            asset_key = _text(pointer.asset_key)
            if not version or not _fresh(getattr(pointer, "stale_status", "")) or not _fresh(getattr(version, "stale_status", "")):
                asset_state = "stale"
                asset_blockers.append(make_blocker(code="VISUAL_ASSET_STALE", book_id=book_id, episode=episode, asset_key=asset_key, scope="asset"))
            elif not (_qualified(getattr(pointer, "authority_status", "")) or _qualified(getattr(version, "authority_status", ""))):
                asset_state = "needs_action"
                asset_blockers.append(make_blocker(code="VISUAL_ASSET_MISSING", book_id=book_id, episode=episode, asset_key=asset_key, scope="asset"))
            else:
                asset_state = "complete"
            asset_items.append({"asset_key": asset_key, "asset_type": _text(pointer.asset_type), "current_version_id": getattr(version, "id", None), "revision": getattr(version, "revision", None), "state": asset_state})
            refs = refs_by_version.get(int(pointer.current_version_id), []) if version else []
            locked = any(_text(getattr(ref, "status", "")).upper() == "LOCKED" and _fresh(getattr(ref, "stale_status", "")) for ref in refs)
            reference_state = "complete" if asset_state == "complete" and locked else ("stale" if asset_state == "stale" else "needs_action")
            reference_items.append({"asset_key": asset_key, "state": reference_state, "locked": locked, "reference_count": len(refs)})
            if reference_state == "stale":
                reference_blockers.append(make_blocker(code="VISUAL_ASSET_STALE", book_id=book_id, episode=episode, asset_key=asset_key, scope="asset"))
            elif reference_state != "complete":
                reference_blockers.append(make_blocker(code="REFERENCE_NOT_LOCKED" if refs else "REFERENCE_MISSING", book_id=book_id, episode=episode, asset_key=asset_key, scope="asset"))
            all_asset_payloads.append({"asset_key": asset_key, "asset_type": _text(pointer.asset_type), "current_version_id": getattr(version, "id", None), "revision": getattr(version, "revision", None), "authority_status": _text(getattr(pointer, "authority_status", "")), "stale_status": _text(getattr(pointer, "stale_status", "")) or "FRESH", "reference_state": reference_state, "reference_count": len(refs), "locked_reference": locked})

        visual_stage = _stage(key="VISUAL_ASSET", state=_state_from_items(asset_items), detail=f"{sum(1 for item in asset_items if item.get('state') == 'complete')}/{len(asset_items)} 个资产已确认" if asset_items else "还没有当前视觉资产", blockers=asset_blockers, counts=_counts(asset_items), target_route={"section": "assets", "episode": episode})
        reference_stage = _stage(key="REFERENCE", state=_state_from_items(reference_items), detail=f"{sum(1 for item in reference_items if item.get('state') == 'complete')}/{len(reference_items)} 个资产已锁定参考图" if reference_items else "等待视觉资产", blockers=reference_blockers, counts=_counts(reference_items), target_route={"section": "assets", "episode": episode})
        media_done = [row for row in episode_shot_rows if _text(getattr(row, "asset_status", "")).lower() in {"done", "video_ready", "complete"}]
        media_items = [{"shot_id": str(row.shot_id), "state": "complete" if row in media_done else "needs_action"} for row in episode_shot_rows]
        media_blockers = [] if len(media_done) == len(episode_shot_rows) and episode_shot_rows else [make_blocker(code="MEDIA_MISSING", book_id=book_id, episode=episode, scope="episode")] if episode_shot_rows else []
        media_stage = _stage(key="MEDIA", state=_state_from_items(media_items), detail=f"{len(media_done)}/{len(episode_shot_rows)} 个镜头已有媒体" if episode_shot_rows else "等待分镜", blockers=media_blockers, counts=_counts(media_items), target_route={"section": "storyboard", "episode": episode})

        stages = {
            "CONTENT": _stage(key="CONTENT", state="complete" if book and (chapters or int(getattr(book, "chapter_count", 0) or 0) > 0) else "needs_action", detail="内容已导入" if book and (chapters or int(getattr(book, "chapter_count", 0) or 0) > 0) else "等待导入内容", blockers=[] if book and (chapters or int(getattr(book, "chapter_count", 0) or 0) > 0) else [make_blocker(code="CONTENT_MISSING", book_id=book_id)], target_route={"section": "content"}),
            "SCRIPT_IR": script_stage,
            "DIRECTOR_TREATMENT": treatment_stage,
            "SCENE_BLOCKING": blocking_stage,
            "SHOT_PLAN": plan_stage,
            "STORYBOARD": storyboard_stage,
            "PROMPT_IR": prompt_stage,
            "VISUAL_ASSET": visual_stage,
            "REFERENCE": reference_stage,
            "MEDIA": media_stage,
            "QA": qa_stage,
        }
        episode_blockers = [blocker for stage in stages.values() for blocker in stage.get("blockers", [])]
        first_action = next((item for item in episode_blockers if item.get("severity") == "blocked"), episode_blockers[0] if episode_blockers else None)
        stage_states = [stage["state"] for stage in stages.values()]
        episode_state = "blocked" if "blocked" in stage_states else ("stale" if "stale" in stage_states else ("needs_action" if "needs_action" in stage_states else ("complete" if all(value == "complete" for value in stage_states) else "in_progress")))
        all_episode_payloads.append({"episode": episode, "overall_state": episode_state, "overall_progress": round(sum(1 for stage in stages.values() if stage["state"] == "complete") / len(stages) * 100) if stages else 0, "blockers": episode_blockers, "next_action": first_action, "stages": stages})

    project_stages: dict[str, dict[str, Any]] = {}
    for key in STAGE_KEYS:
        items = [episode["stages"][key] for episode in all_episode_payloads if key in episode["stages"]]
        state = _state_from_items(items)
        blockers = [blocker for item in items for blocker in item.get("blockers", [])]
        project_stages[key] = _stage(key=key, state=state, detail=f"{sum(1 for item in items if item.get('state') == 'complete')}/{len(items)} 集已完成" if items else "尚未开始", blockers=blockers, counts={"total": len(items), "complete": sum(1 for item in items if item.get("state") == "complete"), "blocked": sum(1 for item in items if item.get("state") == "blocked"), "stale": sum(1 for item in items if item.get("state") == "stale"), "needs_action": sum(1 for item in items if item.get("state") == "needs_action")}, target_route={"section": "dashboard"})

    project_blockers = [blocker for episode in all_episode_payloads for blocker in episode["blockers"]]
    if not all_episode_payloads and not book:
        project_blockers.append(make_blocker(code="CONTENT_MISSING", book_id=book_id, scope="project"))
    next_action = next((item for item in project_blockers if item.get("severity") == "blocked"), project_blockers[0] if project_blockers else None)
    total_stage_count = len(all_episode_payloads) * len(STAGE_KEYS)
    completed_stage_count = sum(1 for episode in all_episode_payloads for stage in episode["stages"].values() if stage["state"] == "complete")
    project_state = _state_from_items(list(project_stages.values()), empty_state="not_started")
    return {
        "schema_version": "production_workspace_projection_v1",
        "book_id": int(book_id),
        "workflow_profile": "production",
        "read_only": True,
        "authority_source": "current_authority_pointers_only",
        "provider_calls": 0,
        "project": {"title": _text(getattr(book, "title", "")) if book else "", "overall_state": project_state, "overall_progress": round(completed_stage_count / total_stage_count * 100) if total_stage_count else 0, "current_blockers": project_blockers, "next_actions": [next_action] if next_action else []},
        "stages": project_stages,
        "episodes": all_episode_payloads,
        "shots": all_shot_payloads,
        "assets": all_asset_payloads,
    }


__all__ = ["STAGE_KEYS", "STAGE_LABELS", "build_production_workspace_projection", "make_blocker"]
