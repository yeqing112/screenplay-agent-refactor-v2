"""Scriptwriter Agent - 按集生成剧本。接入 genre 系统。"""
import json
import re
import logging
import config
from models import Book, BookBible, EpisodeOutline, Script, CharacterProfile, CharacterStage
from core.llm import call_llm
from core import hybrid_retriever as hr
from core.production_skill import (
    build_production_skill_prompt_block,
    build_script_generation_brief_prompt_block,
    build_script_skill_execution_plan_prompt_block,
    build_script_skill_foundation_prompt_block,
    load_latest_script_qa_issues,
)
from genres import get_genre
from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class ScriptwriterAgent(BaseAgent):
    """按集生成剧本。根据 genre 自动切换格式。"""

    name = "scriptwriter"

    def __init__(self, book_id: int, genre: str = "short_drama"):
        super().__init__(book_id)
        self.genre = get_genre(genre)

    def run(self, episode: int) -> str:
        try:
            with self.session() as s:
                book = s.get(Book, self.book_id)
                if not book:
                    raise ValueError(f"Book {self.book_id} not found")

                bible_entry = s.query(BookBible).filter(
                    BookBible.book_id == self.book_id
                ).first()
                if not bible_entry or not bible_entry.content:
                    raise ValueError("Bible not found. Run 'bible' first.")

                ep_data = self._get_episode_data(s, episode)
                if not ep_data:
                    raise ValueError(
                        f"Episode {episode} not found in outline. Run 'outline' first."
                    )

                excerpts = self._retrieve_excerpts(s, ep_data)
                portraits = self._build_portraits_context(s, ep_data.get("characters", []), episode)

                adaptation_settings = self._extract_adaptation_settings(
                    ep_data.get("title", "")
                )

                prompt = self.genre.get_script_prompt(
                    bible=bible_entry.content[:config.SCENE_EXCERPT_CHARS],
                    episode_outline=json.dumps(ep_data, ensure_ascii=False, indent=2),
                    source_excerpts=excerpts,
                    episode=episode,
                    episode_title=ep_data.get("title", ""),
                    portraits=portraits[:config.PROPS_LOCS_CHARS],
                    adaptation_settings=adaptation_settings,
                )
                skill_block = build_production_skill_prompt_block(self.book_id, "script")
                latest_qa_issues = load_latest_script_qa_issues(self.book_id, episode)
                foundation_block = build_script_skill_foundation_prompt_block(
                    self.book_id,
                    episode_outline=ep_data,
                    qa_issues=latest_qa_issues,
                    script_content="",
                )
                generation_brief_block = build_script_generation_brief_prompt_block(
                    self.book_id,
                    episode_outline=ep_data,
                    qa_issues=latest_qa_issues,
                    script_content="",
                )
                execution_plan_block = build_script_skill_execution_plan_prompt_block(
                    self.book_id,
                    episode_outline=ep_data,
                    qa_issues=latest_qa_issues,
                )
                prompt = f"{skill_block}\n\n{foundation_block}\n\n{generation_brief_block}\n\n{execution_plan_block}\n\n{prompt}"
                prompt += (
                    "\n\n## Generation Discipline\n"
                    "Treat `Script Generation Brief` as the primary structural source.\n"
                    "Write scene behavior, clue order, prop movement, and ending hook progression from that structure first, then realize it as screenplay.\n"
                    "Resolve scenes in the listed order, and let each `scene_compilation_card` explicitly drive the scene mover, visual anchor, new evidence, clue reuse, and exit delta.\n"
                )

                script_content = call_llm(
                    prompt,
                    system=self.genre.system_prompt,
                    estimated_tokens=config.ESTIMATED_TOKENS_LARGE,
                )

                output = config.output_path(book.title, "scripts", f"第{episode:02d}集脚本.md")
                output.write_text(script_content, encoding="utf-8")

                existing = s.query(Script).filter(
                    Script.book_id == self.book_id,
                    Script.genre == self.genre.name,
                    Script.episode == episode
                ).first()
                if existing:
                    existing.content = script_content
                    existing.word_count = len(script_content)
                else:
                    s.add(Script(
                        book_id=self.book_id, genre=self.genre.name,
                        episode=episode,
                        content=script_content, word_count=len(script_content),
                        status="draft",
                    ))
                s.commit()

            return str(output)

        except Exception as e:
            logger.error("Scriptwriting failed for book %s ep %s: %s",
                         self.book_id, episode, e)
            raise

    def _get_episode_data(self, session, episode: int) -> dict | None:
        """获取单集大纲数据。"""
        ep_row = session.query(EpisodeOutline).filter(
            EpisodeOutline.book_id == self.book_id,
            EpisodeOutline.genre == self.genre.name,
            EpisodeOutline.episode == episode,
        ).first()

        if ep_row:
            return {
                "episode": ep_row.episode,
                "title": ep_row.title or "",
                "core_event": ep_row.core_event or "",
                "opening_hook": ep_row.opening_hook or "",
                "core_conflict": ep_row.core_conflict or "",
                "climax": ep_row.climax or "",
                "ending_hook": ep_row.ending_hook or "",
                "characters": (ep_row.characters or "").split(", ") if ep_row.characters else [],
                "scenes": (ep_row.scenes or "").split(", ") if ep_row.scenes else [],
            }

        # Fallback: old single-blob format
        outline = session.query(EpisodeOutline).filter(
            EpisodeOutline.book_id == self.book_id,
            EpisodeOutline.genre == self.genre.name,
        ).first()
        if not outline:
            return None

        if outline.raw_content:
            episodes = self._parse_outline(outline.raw_content)
        elif outline.core_event:
            episodes = [{
                "episode": outline.episode,
                "title": outline.title or "",
                "core_event": outline.core_event or "",
                "opening_hook": outline.opening_hook or "",
                "core_conflict": outline.core_conflict or "",
                "climax": outline.climax or "",
                "ending_hook": outline.ending_hook or "",
                "characters": (outline.characters or "").split(", ") if outline.characters else [],
                "scenes": (outline.scenes or "").split(", ") if outline.scenes else [],
            }]
        else:
            return None

        return next((e for e in episodes if e.get("episode") == episode), None)

    def _retrieve_excerpts(self, session, ep_data: dict) -> str:
        """检索与当前集相关的素材片段。"""
        try:
            retriever = hr.HybridRetriever(self.book_id)
            query = f"{ep_data.get('core_event', '')} {' '.join(ep_data.get('characters', []))}"
            results = retriever.search(query, n_results=5)
            excerpts = "\n---\n".join([r["document"][:800] for r in results])
            return excerpts
        except Exception as e:
            logger.warning("Source retrieval failed: %s", e)
            return ""

    def _build_portraits_context(self, session, ep_chars: list, episode: int) -> str:
        """构建角色画像上下文。"""
        if not ep_chars:
            return ""

        portraits = ""
        for char_name in ep_chars:
            try:
                stage = session.query(CharacterStage).filter(
                    CharacterStage.book_id == self.book_id,
                    CharacterStage.character_name == char_name,
                    CharacterStage.chapter_start <= episode,
                    CharacterStage.chapter_end >= episode,
                ).first()

                if stage:
                    portraits += f"\n### {char_name} ({stage.stage_name})\n"
                    portraits += f"时间线: {stage.timeline}\n"
                    portraits += f"身份: {stage.identity}\n"
                    portraits += f"年龄: {stage.age_description}\n"
                    portraits += f"脸型: {stage.face_shape}\n"
                    portraits += f"五官: {stage.facial_features}\n"
                    portraits += f"体型: {stage.body_type}\n"
                    portraits += f"穿着: {stage.signature_outfit}\n"
                    portraits += f"配饰: {stage.accessories}\n"
                    portraits += f"气质: {stage.temperament}\n"
                    portraits += f"氛围: {stage.vibe}\n"
                    portraits += f"说话风格: {stage.speech_style}\n"
                    portraits += f"体态: {stage.body_language}\n"
                else:
                    profile = session.query(CharacterProfile).filter(
                        CharacterProfile.book_id == self.book_id,
                        CharacterProfile.name == char_name,
                    ).first()
                    if profile:
                        portraits += f"\n### {char_name}\n"
                        portraits += f"身份: {profile.identity}\n"
                        portraits += f"年龄: {profile.age_range}\n"
                        portraits += f"气质: {profile.temperament}\n"
                        portraits += f"穿着: {profile.signature_outfit}\n"
                        portraits += f"说话风格: {profile.speech_style}\n"
            except Exception as e:
                logger.warning("Failed to load portrait for %s: %s", char_name, e)
                continue

        return portraits

    def _parse_outline(self, content: str) -> list:
        episodes = []
        current = None
        for line in content.split("\n"):
            if line.startswith("## 第") and "集" in line:
                if current:
                    episodes.append(current)
                m = re.search(r"第(\d+)集", line)
                ep_num = int(m.group(1)) if m else len(episodes) + 1
                title = line.split("：", 1)[-1] if "：" in line else ""
                current = {"episode": ep_num, "title": title}
            elif current and "**核心事件：**" in line:
                current["core_event"] = line.split("**核心事件：**")[-1].strip()
            elif current and "**开场钩子：**" in line:
                current["opening_hook"] = line.split("**开场钩子：**")[-1].strip()
            elif current and "**核心冲突：**" in line:
                current["core_conflict"] = line.split("**核心冲突：**")[-1].strip()
            elif current and "**反转/高潮：**" in line:
                current["climax"] = line.split("**反转/高潮：**")[-1].strip()
            elif current and "**结尾悬念：**" in line:
                current["ending_hook"] = line.split("**结尾悬念：**")[-1].strip()
            elif current and "**主要角色：**" in line:
                current["characters"] = [c.strip() for c in line.split("**主要角色：**")[-1].split(",")]
        if current:
            episodes.append(current)
        return episodes

    def _extract_adaptation_settings(self, episode_title: str) -> str:
        """从改编方案中提取角色改编设定。"""
        try:
            with self.session() as s:
                book = s.get(Book, self.book_id)
                if not book:
                    return ""
                book_title = book.title
        except Exception as e:
            logger.warning("Failed to load book for adaptation settings: %s", e)
            return ""

        adapt_path = config.output_path(book_title, f"{self.genre.name}_改编方案.md")
        if not adapt_path.exists():
            return ""

        content = adapt_path.read_text(encoding="utf-8")
        parts = []

        char_redesign = re.search(
            r'(?:##|###)\s*[三3][、.]?\s*人设改造.*?(?=(?:##|###)\s*[四4]|\Z)',
            content,
            re.DOTALL,
        )
        if char_redesign:
            text = char_redesign.group(0)[:1200]
            parts.append("【角色改编设定（改编方案中的设定优先于原始圣经）】")
            parts.append(text)

        ep_pattern = re.compile(
            r'#{2,3}\s*第\d+集《([^》]+)》\s*(.*?)(?=#{2,3}\s*第\d+集|\Z)',
            re.DOTALL,
        )
        for match in ep_pattern.finditer(content):
            title = match.group(1).strip()
            if title == episode_title:
                block = match.group(2)[:800]
                parts.append(f"【本集（{episode_title}）钩子矩阵】")
                parts.append(block)
                break

        return "\n\n".join(parts) if parts else ""
