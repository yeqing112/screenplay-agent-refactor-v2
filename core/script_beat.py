"""Deterministic script beat index.

A beat is the smallest editable unit of a screenplay.  The index is derived
from canonical markers (``## 场景N`` / ``**[场景结束]**`` / ``[视觉证明N]`` /
dialogue headings) and is rebuilt after every script change.  ``beat_id`` is the
stable anchor for QA and edit operations; line numbers are only a transient
view of the current text and must never be used as a cross-version key.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any


_NUM_MAP = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _parse_scene_no(text: str) -> int:
    raw = str(text or "").strip()
    if raw.isdigit():
        return int(raw)
    if raw == "十":
        return 10
    if "十" in raw:
        parts = raw.split("十", 1)
        tens = _NUM_MAP.get(parts[0], 1 if parts[0] == "" else 0)
        ones = _NUM_MAP.get(parts[1], 0)
        return tens * 10 + ones
    return _NUM_MAP.get(raw, 0)


_SCENE_HEADING_RE = re.compile(r"^\s*(?:##\s*|\*\*\s*)场景([零一二两三四五六七八九十0-9]+)[：:，,]?[^\n]*", re.MULTILINE)
_SCENE_END_RE = re.compile(r"^\s*\[?[【\[【\[]?\s*(?:场景结束|画面渐隐|画面渐暗|淡出)\s*[】\]】\]]?\s*$")
_VISUAL_PROOF_RE = re.compile(r"^[【\[]\s*视觉证明\s*")
_ACTION_MARKER_RE = re.compile(r"^[【\[]\s*动作(?:\s*(?:开始|结束))?\s*[】\]]")
_DICTATE_RE = re.compile(r"^\s*\*\*([^*]+?)\*\*")

_MARKER_KEYWORDS = {
    "开场", "人物入场", "字幕", "闪回", "淡出", "画面渐隐", "画面渐暗",
}
_ACTION_MARKERS = {"动作", "动作开始", "动作结束"}
_SCENE_END_MARKERS = {"场景结束", "画面渐隐", "画面渐暗", "淡出"}


@dataclass
class ScriptBeat:
    """One editable unit of a screenplay."""

    beat_id: str
    beat_index: int
    scene_no: int
    scene_name: str
    kind: str  # heading / dialogue / action / visual_proof / marker
    speaker: str
    content: str
    start_line: int
    end_line: int
    fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "beat_id": self.beat_id,
            "beat_index": self.beat_index,
            "scene_no": self.scene_no,
            "scene_name": self.scene_name,
            "kind": self.kind,
            "speaker": self.speaker,
            "content": self.content,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "fingerprint": self.fingerprint,
        }


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def normalize_text(text: str) -> str:
    """Public normalize used by edit validation for no-op detection."""
    return _norm(text)


STRUCTURAL_HINTS = ("[场景结束]", "【场景结束】", "[画面渐隐]", "【画面渐隐】", "[动作开始]", "【动作开始】", "[动作结束]", "【动作结束】")


def is_structural_beat(content: str, kind: str) -> bool:
    """True when a beat is a structural boundary that must never be rewritten."""
    return kind == "heading" or any(hint in (content or "") for hint in STRUCTURAL_HINTS)


def _classify_cluster(first_line: str) -> tuple[str, str]:
    """Return (kind, speaker) for a content cluster's first non-empty line."""
    scene = _SCENE_HEADING_RE.match(first_line)
    if scene:
        return "heading", ""
    raw = first_line.strip()
    # A `**角色**` heading is a dialogue turn, but `**[开场]**` / `**林晚**`
    # share the same `**...**` shape.  Classify the captured inner token first.
    m = _DICTATE_RE.match(raw)
    if m:
        inner = m.group(1).strip()
        core_token = inner.strip("【】[]*").strip()
        head = core_token.split("：")[0].split(":")[0].strip()
        if head.startswith("视觉证明") and "视觉证明" in core_token:
            return "visual_proof", ""
        if head in _ACTION_MARKERS or head in _SCENE_END_MARKERS or head in _MARKER_KEYWORDS:
            return "marker", ""
        return "dialogue", head
    if _VISUAL_PROOF_RE.match(raw):
        return "visual_proof", ""
    if _ACTION_MARKER_RE.match(raw):
        return "marker", ""
    return "action", ""


def build_script_beats(content: str, episode: int = 1) -> list[ScriptBeat]:
    """Build a deterministic beat index for one episode's script."""
    text = str(content or "")
    lines = text.splitlines()
    # Split into paragraph clusters separated by blank lines, preserving line numbers.
    clusters: list[tuple[int, int, list[str]]] = []
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        start = i + 1
        cluster_lines = []
        while i < len(lines) and lines[i].strip():
            cluster_lines.append(lines[i])
            i += 1
        clusters.append((start, i, cluster_lines))

    # Iterate scenes by slicing the cluster list at scene-heading clusters.
    scene_spans: list[tuple[int, int, int, str]] = []  # (start_cluster_idx, end_cluster_idx, scene_no, scene_name)
    current: list[int] = []
    scene_no = 0
    scene_name = ""
    for idx, (start, end, cluster_lines) in enumerate(clusters):
        first = cluster_lines[0].strip()
        m = _SCENE_HEADING_RE.match(first)
        if m:
            if current:
                scene_spans.append((current[0], current[-1], scene_no, scene_name))
            scene_no = _parse_scene_no(m.group(1))
            scene_name = first
            current = [idx]
        else:
            current.append(idx)
    if current:
        scene_spans.append((current[0], current[-1], scene_no, scene_name))

    beats: list[ScriptBeat] = []
    for (start, end, scene_no, scene_name) in scene_spans:
        if scene_no <= 0:
            continue  # skip preamble before the first scene heading
        beat_in_scene = 0
        for idx in range(start, end + 1):
            cluster_start_line, cluster_end_line, cluster_lines = clusters[idx]
            first = cluster_lines[0].strip()
            kind, speaker = _classify_cluster(first)
            if kind == "heading":
                continue  # scene heading handled as scene span; skip as a beat
            beat_in_scene += 1
            content = "\n".join(cluster_lines)
            beat_id = f"ep{episode}-s{scene_no}-b{beat_in_scene:02d}"
            beats.append(
                ScriptBeat(
                    beat_id=beat_id,
                    beat_index=beat_in_scene,
                    scene_no=scene_no,
                    scene_name=scene_name,
                    kind=kind,
                    speaker=speaker,
                    content=content,
                    start_line=cluster_start_line,
                    end_line=cluster_end_line,
                    fingerprint=_fingerprint(content),
                )
            )
    return beats


def find_issue_beats(
    content: str,
    episode: int,
    *,
    source_excerpt: str = "",
    line_start: int | None = None,
    line_end: int | None = None,
    script_section: str = "",
) -> tuple[list[str], bool]:
    """Map a QA issue's stated location onto stable beat_ids.

    Returns ``(beat_ids, reliable)``.  ``reliable`` is ``True`` only when the
    mapping is unambiguous: an exact normalized-substring hit of ``source_excerpt``
    inside a beat, or a line-range overlap that falls inside a single scene.
    Otherwise ``( [], False )`` so the caller can downgrade to strategy/manual.
    """
    beats = build_script_beats(content, episode)
    if not beats:
        return [], False

    norm_excerpt = _norm(source_excerpt)
    if norm_excerpt:
        matched = [b for b in beats if norm_excerpt in _norm(b.content) or _norm(b.content) in norm_excerpt]
        if matched:
            return [b.beat_id for b in matched], True

    if line_start and line_end:
        overlapped = [b for b in beats if b.start_line <= int(line_end) and b.end_line >= int(line_start)]
        if overlapped:
            scenes = {b.scene_no for b in overlapped}
            if len(scenes) == 1:
                return [b.beat_id for b in overlapped], True
            return [], False

    return [], False
