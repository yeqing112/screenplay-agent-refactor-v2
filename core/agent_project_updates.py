"""Deterministic project-state summaries for Smart Director proactive updates.

This module deliberately does not call an LLM.  It turns the bounded,
server-authoritative evidence snapshot into small, user-facing update
proposals.  An LLM may later explain or rank these proposals, but it cannot
invent project state or bypass the confirmation boundary.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


UPDATE_TYPES = {"progress", "issue", "recommendation", "action_proposal", "completion", "failure"}
SEVERITIES = {"info", "warning", "blocking", "critical"}


def _fingerprint(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _status_counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _update(
    *,
    book_id: int,
    kind: str,
    severity: str,
    title: str,
    message: str,
    source_refs: list[dict[str, Any]],
    evidence_fingerprint: str,
    action_proposal: dict[str, Any] | None = None,
    requires_confirmation: bool = False,
    dedupe_suffix: Any = None,
) -> dict[str, Any]:
    if kind not in UPDATE_TYPES:
        raise ValueError(f"unsupported update type: {kind}")
    if severity not in SEVERITIES:
        raise ValueError(f"unsupported update severity: {severity}")
    dedupe_key = f"book:{book_id}:{kind}:{_fingerprint(dedupe_suffix if dedupe_suffix is not None else {'title': title, 'message': message})[:24]}"
    return {
        "book_id": book_id,
        "type": kind,
        "severity": severity,
        "title": title[:240],
        "message": message[:2000],
        "source_refs": source_refs[:20],
        "evidence_fingerprint": evidence_fingerprint,
        "action_proposal": action_proposal or {},
        "requires_confirmation": bool(requires_confirmation),
        "dedupe_key": dedupe_key,
    }


def derive_project_updates(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive bounded updates from one server-frozen project evidence packet."""
    if not isinstance(evidence, dict):
        return []
    scope = evidence.get("scope") if isinstance(evidence.get("scope"), dict) else {}
    book = evidence.get("project") if isinstance(evidence.get("project"), dict) else {}
    book_id = _safe_int(scope.get("book_id") or book.get("id"))
    if book_id <= 0:
        return []
    evidence_fingerprint = _fingerprint(evidence)
    scripts = [row for row in evidence.get("scripts", []) if isinstance(row, dict)]
    shots = [row for row in evidence.get("shots", []) if isinstance(row, dict)]
    qa = evidence.get("qa") if isinstance(evidence.get("qa"), dict) else {}
    tasks = evidence.get("tasks") if isinstance(evidence.get("tasks"), dict) else {}
    assets = evidence.get("assets") if isinstance(evidence.get("assets"), dict) else {}
    updates: list[dict[str, Any]] = []

    # One compact progress statement is always available when project facts
    # exist.  Counts are facts; wording does not imply that production is done.
    prompt_ready = sum(1 for shot in shots if (shot.get("prompt_state") or {}).get("static") and (shot.get("prompt_state") or {}).get("motion"))
    asset_ready = sum(1 for shot in shots if str(shot.get("asset_status") or "") in {"asset_ready", "video_pending", "done"})
    done = sum(1 for shot in shots if str(shot.get("asset_status") or "") == "done")
    progress_message = (
        f"当前项目已读取 {len(scripts)} 集剧本、{len(shots)} 个分镜；"
        f"其中 {prompt_ready} 个分镜具备完整提示词，{asset_ready} 个已具备资产条件，{done} 个已完成视频链路。"
    )
    updates.append(_update(
        book_id=book_id,
        kind="progress",
        severity="info",
        title="项目进度已更新",
        message=progress_message,
        source_refs=[{"kind": "book", "id": book_id}, {"kind": "scripts", "count": len(scripts)}, {"kind": "shots", "count": len(shots)}],
        evidence_fingerprint=evidence_fingerprint,
        dedupe_suffix={"scripts": len(scripts), "shots": len(shots), "prompt_ready": prompt_ready, "asset_ready": asset_ready, "done": done},
    ))

    open_issues = [row for row in qa.get("issues", []) if isinstance(row, dict) and str(row.get("status") or "") not in {"recheck_passed", "resolved", "closed"}]
    if open_issues:
        severity = "critical" if any(str(row.get("severity") or "").lower() in {"critical", "blocker"} for row in open_issues) else "blocking"
        issue_titles = "；".join(str(row.get("title") or row.get("type") or "未命名问题")[:100] for row in open_issues[:3])
        updates.append(_update(
            book_id=book_id,
            kind="issue",
            severity=severity,
            title=f"发现 {len(open_issues)} 个待处理质量问题",
            message=f"当前有 {len(open_issues)} 个 QA 问题尚未闭环：{issue_titles}。建议先查看问题来源和影响范围，再决定是否生成修复提案。",
            source_refs=[{"kind": "qa_issue", "id": row.get("id"), "type": row.get("type"), "severity": row.get("severity")} for row in open_issues[:20]],
            evidence_fingerprint=evidence_fingerprint,
            dedupe_suffix={"issue_ids": sorted(str(row.get("id")) for row in open_issues), "statuses": sorted(str(row.get("status")) for row in open_issues)},
        ))

    recent_tasks = [row for row in tasks.get("recent", []) if isinstance(row, dict)]
    failed_tasks = [row for row in recent_tasks if str(row.get("status") or "").lower() in {"failed", "error", "timeout"}]
    if failed_tasks:
        task = failed_tasks[0]
        task_kind = str(task.get("task_kind") or "生产任务")
        reason = str(task.get("error") or "外部任务未返回可用结果")[:300]
        updates.append(_update(
            book_id=book_id,
            kind="failure",
            severity="blocking",
            title=f"{task_kind}需要处理",
            message=f"最近一次 {task_kind} 失败：{reason}。请先查看任务详情和输入快照，确认修复后再重试。",
            source_refs=[{"kind": "task", "task_kind": task_kind, "episode": task.get("episode")}],
            evidence_fingerprint=evidence_fingerprint,
            dedupe_suffix={"task_kind": task_kind, "episode": task.get("episode"), "error": reason},
        ))

    pending_tasks = [row for row in recent_tasks if str(row.get("status") or "").lower() in {"queued", "running", "pending", "rechecking"}]
    if pending_tasks:
        updates.append(_update(
            book_id=book_id,
            kind="progress",
            severity="info",
            title=f"有 {len(pending_tasks)} 个任务正在处理",
            message="后台任务仍在执行或等待回收，完成后 Agent 会继续汇报结果；当前不建议重复提交相同任务。",
            source_refs=[{"kind": "task", "task_kind": row.get("task_kind"), "episode": row.get("episode"), "progress": row.get("progress")} for row in pending_tasks[:20]],
            evidence_fingerprint=evidence_fingerprint,
            dedupe_suffix={"tasks": [(row.get("task_kind"), row.get("episode"), row.get("status"), row.get("progress")) for row in pending_tasks]},
        ))

    locations = [row for row in assets.get("locations", []) if isinstance(row, dict)]
    characters = [row for row in assets.get("characters", []) if isinstance(row, dict)]
    props = [row for row in assets.get("props", []) if isinstance(row, dict)]
    missing_assets = [row for row in [*locations, *characters, *props] if str(row.get("asset_status") or "") in {"pending", "asset_pending", "missing"}]
    if missing_assets:
        names = "、".join(str(row.get("name") or "未命名资产")[:80] for row in missing_assets[:5])
        updates.append(_update(
            book_id=book_id,
            kind="recommendation",
            severity="warning",
            title=f"有 {len(missing_assets)} 个资产尚未就绪",
            message=f"以下资产仍缺少可用生产状态：{names}。建议先补齐或确认参考图，再继续下游镜头生成。",
            source_refs=[{"kind": "asset", "id": row.get("id"), "name": row.get("name")} for row in missing_assets[:20]],
            evidence_fingerprint=evidence_fingerprint,
            dedupe_suffix={"asset_ids": sorted(str(row.get("id")) for row in missing_assets), "statuses": sorted(str(row.get("asset_status")) for row in missing_assets)},
        ))

    return updates


def project_status_summary(evidence: dict[str, Any], updates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return a small plain-language snapshot suitable for the project header."""
    updates = updates if updates is not None else derive_project_updates(evidence)
    blocking = [item for item in updates if item.get("severity") in {"critical", "blocking"}]
    if blocking:
        next_action = blocking[0].get("title") or "处理阻塞问题"
    else:
        recommendations = [item for item in updates if item.get("type") == "recommendation"]
        next_action = recommendations[0].get("title") if recommendations else "继续当前生产流程"
    return {
        "book_id": ((evidence.get("scope") or {}).get("book_id") if isinstance(evidence.get("scope"), dict) else None),
        "project_title": ((evidence.get("project") or {}).get("title") if isinstance(evidence.get("project"), dict) else ""),
        "next_action": next_action,
        "blocking_count": len(blocking),
        "update_count": len(updates),
        "evidence_fingerprint": _fingerprint(evidence),
    }
