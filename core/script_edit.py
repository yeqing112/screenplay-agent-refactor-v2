"""Validated, anchored script edit operations.

The edit protocol replaces whole-paragraph rewrites with a small set of anchored
operations (``replace`` / ``insert_after`` / ``delete``) keyed by ``beat_id``.
Every operation is checked before application so a stale, no-op, structural or
contradictory edit can never silently rewrite a scene.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from core.script_beat import build_script_beats, is_structural_beat, normalize_text


_OPS = {"replace", "insert_after", "delete"}
_MAX_EDITS = 8
def _is_structural_beat(content: str, kind: str) -> bool:
    return is_structural_beat(content, kind)


def _sibling_overlap(new_text: str, beat, beats: list[Any]) -> list[str]:
    """Return new_text sentences that already appear in a sibling beat.

    A model may re-emit whole scene-ending beats it was shown in the evidence
    instead of producing a true local edit; applying it duplicates content.
    """
    siblings = [b.content for b in beats if b.scene_no == beat.scene_no and b.beat_id != beat.beat_id]
    sib_norm = normalize_text(" ".join(siblings))
    dups = []
    for sentence in re.split(r"[。！？\n]+", new_text):
        norm = normalize_text(sentence)
        if len(norm) >= 18 and norm in sib_norm:
            dups.append(sentence[:24])
    return dups


def validate_edits(
    content: str,
    episode: int,
    edits: list[dict[str, Any]],
    *,
    frozen_beats: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Validate a batch of anchored edits without applying them.

    ``frozen_beats`` maps ``beat_id -> fingerprint`` captured when the evidence
    packet was frozen; a mismatch means the text changed and the edit is stale.
    Returns ``{valid, conflicts, beat_fingerprints}``.
    """
    beats = build_script_beats(content, episode)
    beat_by_id = {b.beat_id: b for b in beats}
    conflicts: list[str] = []

    if len(edits) > _MAX_EDITS:
        conflicts.append(f"编辑操作数超过上限（{_MAX_EDITS}）。")

    per_beat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edit in edits:
        op = str(edit.get("op") or "").strip()
        beat_id = str(edit.get("beat_id") or "").strip()
        new_text = str(edit.get("new_text") or "")
        if op not in _OPS:
            conflicts.append(f"不支持的操作类型：{op}。")
            continue
        beat = beat_by_id.get(beat_id)
        if beat is None:
            conflicts.append(f"beat {beat_id} 不存在于当前索引。")
            continue
        if _is_structural_beat(beat.content, beat.kind):
            conflicts.append(f"beat {beat_id} 为结构标记（场景标题/场景结束/视觉边界），禁止改写。")
            continue
        if frozen_beats is not None and frozen_beats.get(beat_id) != beat.fingerprint:
            conflicts.append(f"beat {beat_id} 指纹与证据包不一致（文本已变化），视为过期。")
            continue
        if op == "replace" and normalize_text(new_text) == normalize_text(beat.content):
            conflicts.append(f"beat {beat_id} 为 no-op（新文本与原片段一致）。")
            continue
        if op == "replace":
            dups = _sibling_overlap(new_text, beat, beats)
            if dups:
                conflicts.append(f"beat {beat_id} 的新文本与相邻 beat 重复内容：{dups[0]}…（疑似重复已有结尾）。")
                continue
        per_beat[beat_id].append(edit)

    for beat_id, ops in per_beat.items():
        kinds = {op.get("op") for op in ops}
        if len(ops) > 1 or ("delete" in kinds and len(kinds) > 1):
            conflicts.append(f"beat {beat_id} 存在冲突操作（同拍多操作/删除再插入），等待合并或人工。")

    return {
        "valid": not conflicts,
        "conflicts": conflicts,
        "beat_fingerprints": {b.beat_id: b.fingerprint for b in beats},
    }


def apply_edits(content: str, episode: int, edits: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """Apply a pre-validated, non-conflicting batch and return the new text."""
    beats = build_script_beats(content, episode)
    ordered = sorted(beats, key=lambda b: b.start_line)
    op_by_beat: dict[str, dict[str, Any]] = {}
    for edit in edits:
        op_by_beat[str(edit.get("beat_id") or "")] = edit
    lines = content.split("\n")
    out: list[str] = []
    last_end = 0
    applied: list[str] = []
    for beat in ordered:
        out.extend(lines[last_end : beat.start_line - 1])
        edit = op_by_beat.get(beat.beat_id)
        op = str(edit.get("op") or "") if edit else ""
        new_text = str(edit.get("new_text") or "") if edit else ""
        if op == "replace":
            out.extend(new_text.split("\n"))
            applied.append(f"replace {beat.beat_id}")
        elif op == "delete":
            applied.append(f"delete {beat.beat_id}")
        elif op == "insert_after":
            out.extend(lines[beat.start_line - 1 : beat.end_line])
            out.extend(new_text.split("\n"))
            applied.append(f"insert_after {beat.beat_id}")
        else:
            out.extend(lines[beat.start_line - 1 : beat.end_line])
        last_end = beat.end_line
    out.extend(lines[last_end:])
    return "\n".join(out), applied
