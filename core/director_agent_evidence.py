"""Server-authoritative evidence packets for Smart Director suggestions.

The browser may describe its current screen, but it is not an authority for
production facts.  This module reads the bounded, relevant project state on
the server and returns a deterministic snapshot suitable for fingerprinting
and later audit/replay.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from models import (
    Book, CharacterProfile, DecisionPacketRecord, QAIssue, Script,
    StoryboardPromptVersion, StoryboardShot, TaskRun, VisualLocation,
    VisualProp, VisualReferenceAsset, Session,
)


def _text(value: Any, limit: int = 1200) -> str:
    return str(value or "").strip()[:limit]


def _int(value: Any) -> int | None:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _counts(rows: list[Any], attr: str) -> dict[str, int]:
    return dict(sorted(Counter(str(getattr(row, attr, "") or "unknown") for row in rows).items()))


def build_project_evidence(scope: dict[str, Any]) -> dict[str, Any]:
    """Read a compact, deterministic fact snapshot for a project scope.

    It intentionally excludes credentials, raw remote URLs and unbounded text.
    ``book_id`` is mandatory because an Agent decision without a project cannot
    be audited against the production graph.
    """
    safe_scope = scope if isinstance(scope, dict) else {}
    book_id = _int(safe_scope.get("book_id"))
    if not book_id:
        raise ValueError("智能导演台证据包必须绑定有效项目")
    episode = _int(safe_scope.get("episode"))
    shot_id = _int(safe_scope.get("shot_id"))
    asset_id = _int(safe_scope.get("asset_id"))

    with Session() as session:
        book = session.get(Book, book_id)
        if not book:
            raise ValueError("项目不存在，无法冻结智能导演台证据包")
        scripts = session.query(Script).filter_by(book_id=book_id).order_by(Script.episode, Script.id).all()
        shots_query = session.query(StoryboardShot).filter_by(book_id=book_id)
        if episode:
            shots_query = shots_query.filter_by(episode=episode)
        if shot_id:
            shots_query = shots_query.filter_by(shot_id=shot_id)
        shots = shots_query.order_by(StoryboardShot.episode, StoryboardShot.shot_id, StoryboardShot.id).limit(80).all()
        characters = session.query(CharacterProfile).filter_by(book_id=book_id).order_by(CharacterProfile.id).limit(80).all()
        locations = session.query(VisualLocation).filter_by(book_id=book_id).order_by(VisualLocation.id).limit(80).all()
        props = session.query(VisualProp).filter_by(book_id=book_id).order_by(VisualProp.id).limit(80).all()
        refs = session.query(VisualReferenceAsset).filter_by(book_id=book_id).order_by(VisualReferenceAsset.id).all()
        qa_query = session.query(QAIssue).filter_by(book_id=book_id)
        if episode:
            qa_query = qa_query.filter_by(episode=episode)
        qa = qa_query.order_by(QAIssue.id.desc()).limit(40).all()
        tasks_query = session.query(TaskRun).filter_by(book_id=book_id)
        if episode:
            tasks_query = tasks_query.filter_by(episode=episode)
        tasks = tasks_query.order_by(TaskRun.id.desc()).limit(40).all()
        packet_rows = session.query(DecisionPacketRecord).filter_by(book_id=book_id).order_by(DecisionPacketRecord.id.desc()).limit(40).all()
        versions_query = session.query(StoryboardPromptVersion).filter_by(book_id=book_id)
        if episode:
            versions_query = versions_query.filter_by(episode=episode)
        if shot_id:
            versions_query = versions_query.filter_by(shot_id=shot_id)
        versions = versions_query.order_by(StoryboardPromptVersion.episode, StoryboardPromptVersion.shot_id, StoryboardPromptVersion.version.desc(), StoryboardPromptVersion.id.desc()).limit(40).all()

    scoped_scripts = [row for row in scripts if not episode or row.episode == episode]
    return {
        "source": "server_project_snapshot_v1",
        "scope": {"book_id": book_id, "episode": episode, "shot_id": shot_id, "asset_id": asset_id, "section": _text(safe_scope.get("section"), 120)},
        "project": {"id": book.id, "title": _text(book.title, 240), "status": _text(book.status, 80), "chapter_count": int(book.chapter_count or 0), "total_words": int(book.total_words or 0)},
        "scripts": [{"episode": row.episode, "status": _text(row.status, 80), "word_count": int(row.word_count or 0), "excerpt": _text(row.content, 2400)} for row in scoped_scripts[:12]],
        "shots": [{"id": row.id, "episode": row.episode, "shot_id": row.shot_id, "scene_name": _text(row.scene_name, 240), "duration": int(row.duration or 0), "asset_status": _text(row.asset_status, 80), "start_state": _text(row.start_state, 600), "action_process": _text(row.action_process, 900), "end_state": _text(row.end_state, 600), "camera": {"angle": _text(row.camera_angle, 80), "movement": _text(row.camera_movement, 80), "transition": _text(row.transition, 80)}, "prompt_state": {"static": bool(_text(row.visual_prompt_static, 1)), "motion": bool(_text(row.visual_prompt_motion, 1))}} for row in shots],
        "assets": {
            "characters": [{"id": row.id, "name": _text(row.name, 160), "gender": _text(row.gender, 40), "identity": _text(row.identity, 240), "hairstyle": _text(row.hairstyle, 240), "outfit": _text(row.signature_outfit, 360)} for row in characters],
            "locations": [{"id": row.id, "name": _text(row.name, 160), "asset_status": _text(row.asset_status, 80), "lighting_mood": _text(row.lighting_mood, 240)} for row in locations],
            "props": [{"id": row.id, "name": _text(row.name, 160), "importance": _text(row.importance, 40), "asset_status": _text(row.asset_status, 80)} for row in props],
            "reference_status_counts": _counts(refs, "status"),
            "locked_reference_count": sum(1 for row in refs if str(row.status or "") == "locked"),
        },
        "qa": {"status_counts": _counts(qa, "fix_status"), "issues": [{"id": row.id, "episode": row.episode, "severity": _text(row.severity, 40), "type": _text(row.issue_type, 100), "title": _text(row.title, 240), "status": _text(row.fix_status, 80), "reason": _text(row.status_reason, 360)} for row in qa[:20]]},
        "tasks": {"status_counts": _counts(tasks, "status"), "recent": [{"task_kind": _text(row.task_kind, 100), "status": _text(row.status, 80), "episode": row.episode, "progress": int(row.progress or 0), "error": _text(row.error, 300)} for row in tasks[:12]]},
        "prompt_versions": [{"episode": row.episode, "shot_id": row.shot_id, "version": row.version, "reason": _text(row.compile_reason, 120)} for row in versions],
        "decision_packets": [{"domain": _text(row.domain, 80), "status": _text(row.status, 80), "fingerprint": _text(row.packet_fingerprint, 80)} for row in packet_rows],
    }
