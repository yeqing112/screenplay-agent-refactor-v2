"""Outline Agent - 生成分集大纲。"""
import json
import re
import config
from models import Book, BookBible, EpisodeOutline
from core.llm import call_llm
from core import hybrid_retriever as hr
from core.prompts import load_prompt
from agents.base import BaseAgent

# 改编类型枚举
ADAPTATION_TYPES = {
    "faithful": {
        "label": "忠实改编",
        "desc": "严格对齐改编方案的 sliot 设计，前 N 集固定，后续自由发挥",
        "fixed_sliot_count": 10,  # 锁死前 10 集
    },
    "extractive": {
        "label": "提取改编",
        "desc": "对齐改编方案的核心节奏，前 5 集固定 sliot",
        "fixed_sliot_count": 5,
    },
    "loose": {
        "label": "灵感改编",
        "desc": "仅参考改编方案的核心设定，不固定任何集",
        "fixed_sliot_count": 0,
    },
}


class OutlineAgent(BaseAgent):
    """生成分集大纲。"""

    name = "outline"

    def __init__(self, book_id: int, genre: str = "short_drama", adaptation_type: str = "extractive", episode_count: int | None = None):
        super().__init__(book_id)
        self.genre = genre
        self.adaptation_type = adaptation_type
        self._episode_count = episode_count
        if adaptation_type not in ADAPTATION_TYPES:
            raise ValueError(f"Unknown adaptation_type: {adaptation_type}. Available: {', '.join(ADAPTATION_TYPES.keys())}")

    def run(self) -> str:
        with self.session() as s:
            book = s.get(Book, self.book_id)
            bible = s.query(BookBible).filter(BookBible.book_id == self.book_id).first()
            if not bible:
                raise ValueError("Run 'bible' first.")

            # Read adaptation plan — full content
            if book:
                adapt_path = config.output_path(book.title, f"short_drama_改编方案.md")
                adaptation = adapt_path.read_text(encoding="utf-8") if adapt_path.exists() else ""
            else:
                adaptation = ""

            # Extract fixed sliot from adaptation plan
            fixed_sliots = self._extract_fixed_sliots(adaptation)

            # Determine episode count based on adaptation type
            # 1137 chapters total
            if book and book.chapter_count:
                cc = book.chapter_count
            else:
                cc = 100  # fallback default
            if self._episode_count and self._episode_count > 0:
                episode_count = self._episode_count
            elif self.adaptation_type == "faithful":
                episode_count = max(10, min(30, cc // 25))
            elif self.adaptation_type == "extractive":
                episode_count = max(8, min(20, cc // 40))
            else:
                episode_count = max(5, min(10, cc // 80))

            # Build fixed sliot prompt section
            fixed_sliot_text = ""
            fixed_sliot_extra = ""
            if fixed_sliots:
                lines = []
                sliot_episodes = json.dumps(fixed_sliots, ensure_ascii=False, indent=2)
                sliot_desc = ADAPTATION_TYPES[self.adaptation_type]["desc"]
                lines.append(f"## 改编类型: {ADAPTATION_TYPES[self.adaptation_type]['label']}")
                lines.append(f"{sliot_desc}")
                lines.append("")
                lines.append(f"## 改编方案固定的前 {len(fixed_sliots)} 集 sliot")
                lines.append("以下 sliot 是改编方案设计的固定纲次，生成分集大纲时**必须严格对齐**：")
                lines.append("")
                lines.append(sliot_episodes)
                lines.append("")
                lines.append("请将这些固定 sliot 映射到分集大纲的前 {n} 集，核心事件、开场钩子、冲突、角色必须与 sliot 一致。".format(n=len(fixed_sliots)))
                lines.append("后续集数可以自由发挥，但需保持与前几集一致的风格和节奏。")
                fixed_sliot_text = "\n".join(lines)
                fixed_sliot_extra = "前 {n} 集必须严格遵循改编方案的固定 sliot，不得自行修改核心事件。".format(n=len(fixed_sliots))

            bible_content = (bible.content or "")[:config.SCENE_EXCERPT_CHARS]
            prompt = load_prompt(
                "outline/outline",
                bible=bible_content,
                adaptation=adaptation,  # 完整改编方案，不再截断
                fixed_sliots=fixed_sliot_text,
                fixed_sliots_extra=fixed_sliot_extra,
                episode_count=episode_count,
            )

            raw = call_llm(prompt, estimated_tokens=config.ESTIMATED_TOKENS_CHAPTER)
            episodes = self._parse_json_response(raw)
            if not episodes:
                self.log("Failed to parse outline JSON, using fallback")
                episodes = [{"episode": i+1, "title": f"第{i+1}集", "core_event": "待定"} for i in range(max(10, len(fixed_sliots)))]

            # Merge fixed sliot data into first N episodes
            # 强制覆盖：slots 数据优先于 LLM 输出
            if fixed_sliots:
                self.log(f"Merging {len(fixed_sliots)} fixed sliots into episodes (total={len(episodes)})")
                for i, sliot in enumerate(fixed_sliots):
                    if i < len(episodes):
                        ep = episodes[i]
                        if not isinstance(ep, dict):
                            self.log(f"  Ep{i+1}: episode is not a dict, skipping")
                            continue
                        old_title = ep.get("title", "")
                        # 强制覆盖所有字段
                        ep["title"] = sliot.get("title", ep.get("title", f"第{i+1}集"))
                        ep["core_event"] = sliot.get("core_event", ep.get("core_event", ""))
                        ep["opening_hook"] = sliot.get("opening_hook", ep.get("opening_hook", ""))
                        ep["core_conflict"] = sliot.get("core_conflict", ep.get("core_conflict", ""))
                        ep["climax"] = sliot.get("climax", ep.get("climax", ""))
                        ep["ending_hook"] = sliot.get("ending_hook", ep.get("ending_hook", ""))
                        if isinstance(sliot.get("characters"), list):
                            ep["characters"] = sliot["characters"]
                        elif isinstance(ep.get("characters"), str):
                            ep["characters"] = ep["characters"]
                        elif "characters" not in ep or not isinstance(ep.get("characters"), list):
                            ep["characters"] = []
                        if isinstance(sliot.get("scenes"), list):
                            ep["scenes"] = sliot["scenes"]
                        elif "scenes" not in ep or not isinstance(ep.get("scenes"), list):
                            ep["scenes"] = []
                        self.log(f"  Ep{i+1}: sliot title='{ep['title']}' (was '{old_title}') | opening_hook='{ep['opening_hook'][:30]}'")
                    else:
                        self.log(f"  Ep{i+1}: skipped (i >= {len(episodes)})")

            # Format as readable outline
            outline = self._format_outline(book.title, episodes)

            output = config.output_path(book.title, "outlines", "大纲.md")
            output.write_text(outline, encoding="utf-8")

            # Save to DB — one row per episode (按 genre 隔离)
            s.query(EpisodeOutline).filter(
                EpisodeOutline.book_id == self.book_id,
                EpisodeOutline.genre == self.genre,
            ).delete()
            for i, ep in enumerate(episodes):
                is_fixed = 1 if fixed_sliots and i < len(fixed_sliots) else 0
                chars = ep.get("characters", [])
                if isinstance(chars, list):
                    chars_str = ", ".join(
                        c.get("name", str(c)) if isinstance(c, dict) else str(c)
                        for c in chars
                    )
                else:
                    chars_str = str(chars) if chars else ""
                scenes = ep.get("scenes", [])
                if isinstance(scenes, list):
                    scenes_str = ", ".join(
                        s.get("scene_name", str(s)) if isinstance(s, dict) else str(s)
                        for s in scenes
                    )
                else:
                    scenes_str = str(scenes) if scenes else ""
                s.add(EpisodeOutline(
                    book_id=self.book_id,
                    genre=self.genre,
                    episode=ep.get("episode", i + 1),
                    title=ep.get("title", ""),
                    core_event=ep.get("core_event", ""),
                    opening_hook=ep.get("opening_hook", ""),
                    core_conflict=ep.get("core_conflict", ""),
                    climax=ep.get("climax", ""),
                    ending_hook=ep.get("ending_hook", ""),
                    characters=chars_str,
                    scenes=scenes_str,
                    is_fixed=is_fixed,
                    raw_content="",
                ))
            book.status = "outlined"
            s.commit()

        return str(output)

    def _extract_fixed_sliots(self, adaptation: str) -> list:
        """从改编方案中解析固定的 sliot 数据。

        优先级：
        1. 查 DB 中 book_id 下已有 is_fixed=1 的记录（方案 A：由 AdapterAgent 写入）
        2. 若无，用 LLM 解析改编方案 Markdown 提取结构化数据（通用兜底）

        提取前 N 集（根据 adaptation_type 配置）写入 DB 并返回。
        """
        fixed_count = ADAPTATION_TYPES[self.adaptation_type]["fixed_sliot_count"]
        if fixed_count == 0:
            return []

        # 先尝试从 DB 读取已有的固定 sliot
        with self.session() as s:
            existing = s.query(EpisodeOutline).filter(
                EpisodeOutline.book_id == self.book_id,
                EpisodeOutline.genre == self.genre,
                EpisodeOutline.is_fixed == 1,
                EpisodeOutline.episode >= 1,
                EpisodeOutline.episode <= fixed_count,
            ).order_by(EpisodeOutline.episode).all()

            if existing:
                sliots = []
                for row in existing:
                    sliot = {
                        "episode": row.episode,
                        "title": row.title or "",
                        "core_event": row.core_event or "",
                        "opening_hook": row.opening_hook or "",
                        "core_conflict": row.core_conflict or "",
                        "climax": row.climax or "",
                        "ending_hook": row.ending_hook or "",
                    }
                    if row.characters:
                        sliot["characters"] = [c.strip() for c in row.characters.split(",")]
                    else:
                        sliot["characters"] = []
                    if row.scenes:
                        sliot["scenes"] = [c.strip() for c in row.scenes.split(",")]
                    else:
                        sliot["scenes"] = []
                    sliots.append(sliot)
                self.log(f"从 DB 读取到 {len(sliots)} 个固定 sliot 记录")
                return sliots

        # DB 中没有 → 用 LLM 解析改编方案（通用兜底）
        if not adaptation:
            return []

        self.log(f"DB 中无固定 sliot，使用 LLM 解析改编方案")

        parse_prompt = f"""从以下改编方案中提取前 {fixed_count} 集的结构化数据。

每集需要提取的字段：
1. episode (集号)
2. title (集标题)
3. core_event (核心事件，一句话)
4. opening_hook (开场钩子)
5. core_conflict (核心冲突)
6. climax (高潮/反转)
7. ending_hook (结尾悬念)
8. characters (主要角色，数组)
9. scenes (关键场景，数组)

改编方案：
{adaptation[:config.OUTLINE_EXCERPT_CHARS]}

以 JSON 格式返回，格式如下：
{{"sliots": [{{"episode": 1, "title": "...", ...}}, ...]}}
直接返回 JSON，不要额外解释。
"""

        result = call_llm(
            parse_prompt,
            system="你是一个改编方案解析器。提取结构化数据，直接输出 JSON。",
            estimated_tokens=config.ESTIMATED_TOKENS_DEFAULT,
        )

        sliots = self._parse_json_sliots(result)

        if sliots:
            # 写入 DB 供后续复用
            self._write_fixed_sliots_to_db(sliots)

        return sliots

    def _parse_json_sliots(self, raw: str) -> list:
        """从 LLM 返回的文本中提取 JSON 格式的 sliot 数组。"""
        import json

        # 尝试直接解析
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "sliots" in parsed:
                return parsed["sliots"][:ADAPTATION_TYPES[self.adaptation_type]["fixed_sliot_count"]]
            if isinstance(parsed, list):
                return parsed[:ADAPTATION_TYPES[self.adaptation_type]["fixed_sliot_count"]]
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown code block 提取
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                if isinstance(parsed, dict) and "sliots" in parsed:
                    return parsed["sliots"][:ADAPTATION_TYPES[self.adaptation_type]["fixed_sliot_count"]]
                if isinstance(parsed, list):
                    return parsed[:ADAPTATION_TYPES[self.adaptation_type]["fixed_sliot_count"]]
            except json.JSONDecodeError:
                pass

        self.log(f"⚠️ 无法解析 LLM 返回的 JSON sliot: {raw[:200]}")
        return []

    def _write_fixed_sliots_to_db(self, sliots: list):
        """将解析出的固定 sliot 写入 DB。"""
        with self.session() as s:
            # 删除旧的固定记录
            old = s.query(EpisodeOutline).filter(
                EpisodeOutline.book_id == self.book_id,
                EpisodeOutline.genre == self.genre,
                EpisodeOutline.is_fixed == 1,
            ).all()
            for o in old:
                s.delete(o)
            s.flush()

            for sliot in sliots:
                ep = sliot.get("episode", 0)
                row = EpisodeOutline(
                    book_id=self.book_id,
                    genre=self.genre,
                    episode=ep,
                    title=sliot.get("title", ""),
                    core_event=sliot.get("core_event", ""),
                    opening_hook=sliot.get("opening_hook", ""),
                    core_conflict=sliot.get("core_conflict", ""),
                    climax=sliot.get("climax", ""),
                    ending_hook=sliot.get("ending_hook", ""),
                    characters=", ".join(sliot.get("characters", [])) if isinstance(sliot.get("characters"), list) else sliot.get("characters", ""),
                    scenes=", ".join(sliot.get("scenes", [])) if isinstance(sliot.get("scenes"), list) else sliot.get("scenes", ""),
                    is_fixed=1,
                )
                s.add(row)
            s.commit()
            self.log(f"已写入 {len(sliots)} 个固定 sliot 到 DB")

    def _extract_adaptation_path(self) -> str | None:
        """查找当前 book 的改编方案文件路径。"""
        from pathlib import Path

        with self.session() as s:
            book = s.get(Book, self.book_id)
            if not book:
                return None
            title = book.title

        # 搜索可能的文件名
        base = config.output_path(title)
        candidates = list(Path(base).glob(f"*改编方案*")) + list(Path(base).glob(f"*adapt*"))
        if candidates:
            return str(candidates[0])
        return None

    def _parse_json_response(self, text: str) -> list:
        """Parse JSON from LLM response, handling markdown fences and truncation."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("[")
            end = text.rfind("]") + 1
            raw_json = text[start:end]
            try:
                return json.loads(raw_json)
            except json.JSONDecodeError:
                # Last resort: lenient parse
                items = re.findall(r'\{[^}]+\}', raw_json)
                episodes = []
                for item in items:
                    try:
                        episodes.append(json.loads(item))
                    except json.JSONDecodeError:
                        pass
                return episodes

    def _format_outline(self, title: str, episodes: list) -> str:
        lines = [f"# {title} - 分集大纲\n"]
        for ep in episodes:
            lines.append(f"\n## 第{ep.get('episode', '?')}集：{ep.get('title', '')}\n")
            lines.append(f"**核心事件：** {ep.get('core_event', '')}")
            lines.append(f"**开场钩子：** {ep.get('opening_hook', '')}")
            lines.append(f"**核心冲突：** {ep.get('core_conflict', '')}")
            lines.append(f"**反转/高潮：** {ep.get('climax', '')}")
            lines.append(f"**结尾悬念：** {ep.get('ending_hook', '')}")
            chars = ep.get('characters', [])
            lines.append(f"**主要角色：** {', '.join(str(c) for c in chars)}")
            scenes = ep.get('scenes', [])
            lines.append(f"**关键场景：** {', '.join(str(s) for s in scenes)}")
        return "\n".join(lines)
