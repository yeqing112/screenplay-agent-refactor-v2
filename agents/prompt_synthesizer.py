"""Prompt Synthesizer — 合成最终视频生成提示词。

Phase 1: 框架 + 提示词模板（asset_links 未就绪时仅输出框架）
Phase 2: 实际合成（需要 asset_links 就绪后执行）
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from core.prompts import load_prompt, PROMPTS_DIR
from core import safe_json_loads
from models import Session, Book, Script, StoryboardShot
from agents.base import BaseAgent
from genres import get_genre

logger = logging.getLogger(__name__)


def _safe_title_path(title: str) -> str:
    """将书名校验为安全的路径成分。"""
    import re
    safe = re.sub(r'[^\w\u4e00-\u9fff\-_ ]', '', title).strip()
    if not safe:
        safe = "untitled"
    return safe


class PromptSynthesizer(BaseAgent):
    """提示词合成 Agent。"""

    name = "prompt_synthesizer"

    def __init__(self, book_id: int, genre: str = "short_drama"):
        super().__init__(book_id)
        self.genre = get_genre(genre)

    def run(self, episode: int) -> list[dict]:
        """入口：合成整集所有镜头的 final prompt。"""
        with self.session() as s:
            shots = (
                s.query(StoryboardShot)
                .filter(
                    StoryboardShot.book_id == self.book_id,
                    StoryboardShot.episode == episode,
                )
                .order_by(StoryboardShot.shot_id)
                .all()
            )
            if not shots:
                self.log(f"ep {episode}: no storyboard shots found")
                return []

            # Phase 1: 检查 asset_links 是否已回填
            has_assets = False
            for sh in shots[:3]:
                links = safe_json_loads(sh.asset_links, {})
                if not isinstance(links, dict):
                    continue
                if links.get("scene") or links.get("characters"):
                    has_assets = True
                    break

            if not has_assets:
                self.log(f"ep {episode}: asset_links not ready (Phase 1)")
                return []

            self.log(f"ep {episode}: {len(shots)} shots ready for synthesis")

        return []

    def synthesize_single_shot(self, shot) -> str:
        """合成单个镜头的 final prompt。"""
        links = safe_json_loads(shot.asset_links, {})

        scene_ref = links.get("scene", "") if isinstance(links, dict) else ""
        char_refs = links.get("characters", {}) if isinstance(links, dict) else {}
        prop_refs = links.get("props", {}) if isinstance(links, dict) else {}

        char_lines = []
        for name, path in char_refs.items():
            char_lines.append(f"@{name} (reference: {path}, weight:1.3)")

        prop_lines = []
        for name, path in prop_refs.items():
            prop_lines.append(f"[{name}] (reference: {path})")

        parts = [
            f"[{shot.camera_angle}]"
            f"[{shot.camera_movement}]",
            shot.lighting or "",
        ]
        if scene_ref:
            parts.append(f"场景参考图: {scene_ref}")
        if char_lines:
            parts.append("角色: " + ", ".join(char_lines))
        if prop_lines:
            parts.append("道具: " + ", ".join(prop_lines))
        parts.append(f"起始状态: {shot.start_state}")
        parts.append(f"动作过程: {shot.action_process} (约{shot.duration}秒)")
        parts.append(f"结束状态: {shot.end_state}")

        genre_style = self.genre.description or ""
        parts.append(f"[视觉风格: {genre_style}, 电影级光影, 高细节, 一致性]")

        return "\n".join(parts)

    def batch_synthesize(self, episode: int) -> list[dict]:
        """批量合成并更新 DB 中的 visual_prompt_final。"""
        with self.session() as s:
            shots = (
                s.query(StoryboardShot)
                .filter(
                    StoryboardShot.book_id == self.book_id,
                    StoryboardShot.episode == episode,
                )
                .all()
            )

            results = []
            now = datetime.utcnow()
            for sh in shots:
                final = self.synthesize_single_shot(sh)
                sh.visual_prompt_final = final
                sh.updated_at = now
                results.append({"shot_id": sh.shot_id, "final_prompt": final})

            s.commit()

        self.log(f"ep {episode}: synthesized {len(results)} shots")
        return results

    def save_synthesized_output(self, title: str, episode: int):
        """保存合成后的输出（带路径安全校验）。"""
        safe_title = _safe_title_path(title)

        with self.session() as s:
            shots = (
                s.query(StoryboardShot)
                .filter(
                    StoryboardShot.book_id == self.book_id,
                    StoryboardShot.episode == episode,
                )
                .order_by(StoryboardShot.shot_id)
                .all()
            )
            if not shots:
                return

            output_dir = (
                Path(__file__).parent.parent / "outputs" / safe_title / "video"
            )
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.error("Failed to create output dir %s: %s", output_dir, e)
                return

            data = []
            for sh in shots:
                data.append({
                    "shot_id": sh.shot_id,
                    "scene_name": sh.scene_name,
                    "final_prompt": sh.visual_prompt_final,
                    "asset_links": safe_json_loads(sh.asset_links, {}),
                    "duration": sh.duration,
                    "camera_movement": sh.camera_movement,
                })

            path = output_dir / f"第{episode:02d}集视频输入.json"
            try:
                path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self.log(f"Saved video input to {path}")
            except OSError as e:
                logger.error("Failed to write %s: %s", path, e)
