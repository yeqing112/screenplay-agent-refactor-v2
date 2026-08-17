"""Reader Agent - chapter analysis with resilient local fallbacks."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime

import config
from agents.base import BaseAgent
from core import safe_json_loads
from core import vector_search as vs
from core.llm import call_llm_json, get_limiter
from core.prompts import load_prompt
from models import Book, Chapter

logger = logging.getLogger(__name__)

MIN_CHAPTER_BODY_CHARS = 30


class ReaderAgent(BaseAgent):
    """Read chapters and extract structured story information."""

    name = "reader"

    def __init__(self, book_id: int, chapter_delay: float = 1.0):
        super().__init__(book_id)
        self.chapter_delay = chapter_delay

    def _get_book_title(self) -> str:
        from models.base import Session as read_session

        with read_session() as session:
            book = session.get(Book, self.book_id)
            return book.title if book else ""

    def _get_unanalyzed_chapters(self, limit: int = 0) -> list[dict]:
        from models.base import Session as read_session

        with read_session() as session:
            query = (
                session.query(Chapter)
                .filter(Chapter.book_id == self.book_id, Chapter.status != "analyzed")
                .order_by(Chapter.seq)
            )
            if limit > 0:
                query = query.limit(limit)
            chapters = query.all()
            return [
                {"id": chapter.id, "seq": chapter.seq, "title": chapter.title, "content": chapter.content}
                for chapter in chapters
            ]

    def run(self, start_ch: int = None, end_ch: int = None) -> dict:
        book_title = self._get_book_title()
        if not book_title:
            raise ValueError(f"Book {self.book_id} not found")

        chapters = self._get_unanalyzed_chapters(limit=end_ch or 0)
        if not chapters:
            return {"message": "All chapters already analyzed"}

        total = len(chapters)
        processed = 0
        errors = []
        all_characters: dict[str, dict] = {}
        last_time = time.time()

        for index, chapter_data in enumerate(chapters):
            elapsed = time.time() - last_time
            if elapsed < self.chapter_delay and index > 0:
                time.sleep(self.chapter_delay - elapsed)

            try:
                result = self._analyze_chapter(chapter_data)
                processed += 1
                last_time = time.time()

                for character in result.get("characters", []):
                    name = character.get("name", "")
                    if not name:
                        continue
                    if name not in all_characters:
                        all_characters[name] = {
                            "name": name,
                            "aliases": character.get("aliases", []),
                            "identity": character.get("identity", ""),
                            "personality": character.get("personality", ""),
                            "relationships": character.get("relationships", {}),
                            "first_chapter": chapter_data["seq"],
                            "chapters": [chapter_data["seq"]],
                        }
                    else:
                        all_characters[name]["chapters"].append(chapter_data["seq"])
                        new_identity = character.get("identity", "")
                        if new_identity and not all_characters[name].get("identity"):
                            all_characters[name]["identity"] = new_identity

                limiter = get_limiter()
                stats = limiter.stats()
                logger.info(
                    "[reader] [%s/%s] Ch%s: %s | RPM:%s/%s | Daily:%s",
                    processed,
                    total,
                    chapter_data["seq"],
                    str(chapter_data["title"] or "")[:30],
                    stats["rpm_used"],
                    stats["rpm_limit"],
                    f"{stats['daily_tokens']:,}",
                )
            except Exception as exc:
                errors.append({"chapter": chapter_data["seq"], "error": str(exc)})
                logger.error("[reader] Chapter %s failed: %s", chapter_data["seq"], exc)
                if "429" in str(exc) or "quota" in str(exc).lower():
                    logger.warning("[reader] Rate limited, sleeping 30s")
                    time.sleep(30)

        self._save_character_table(all_characters, book_title)
        self._save_appearance_fragments(book_title)
        self._save_summaries(book_title)

        if errors:
            first_error = errors[0]["error"]
            raise RuntimeError(f"Reader analysis failed for {len(errors)} chapter(s): {first_error}")

        from models.base import Session as write_session

        with write_session() as session:
            book = session.get(Book, self.book_id)
            if book:
                book.status = "read"
                session.commit()

        return {
            "processed": processed,
            "total": total,
            "errors": errors,
            "characters": len(all_characters),
        }

    def _analyze_chapter(self, chapter_data: dict) -> dict:
        content = str(chapter_data.get("content") or "")
        title = str(chapter_data.get("title") or "")
        normalized_content = content.strip()

        if self._should_skip_llm_for_short_content(title, normalized_content):
            result = self._build_short_chapter_fallback(title, normalized_content)
            self._persist_chapter_result(chapter_data, result)
            return result

        if len(content) > config.CHAPTER_MAX_CHARS:
            content = content[:config.CHAPTER_MAX_CHARS] + "\n...(章节过长，已截断)"

        prompt = load_prompt("reader/analysis", title=title, content=content)
        try:
            result = call_llm_json(prompt, estimated_tokens=len(content) + config.ESTIMATED_TOKENS_SMALL)
        except Exception as exc:
            logger.warning("Reader LLM parse failed for ch%s, using local fallback: %s", chapter_data["seq"], exc)
            result = self._build_local_fallback(title, normalized_content)

        result = self._normalize_result_payload(result)
        self._persist_chapter_result(chapter_data, result)
        self._update_vector_index(chapter_data, result)
        return result

    def _normalize_result_payload(self, result: dict | None) -> dict:
        payload = result if isinstance(result, dict) else {}
        for field in ["characters", "events", "scenes", "foreshadowing"]:
            if not isinstance(payload.get(field), list):
                payload[field] = []
        if not isinstance(payload.get("summary"), str):
            payload["summary"] = str(payload.get("summary") or "")
        if not isinstance(payload.get("appearance_fragments"), dict):
            payload["appearance_fragments"] = {}
        return payload

    def _persist_chapter_result(self, chapter_data: dict, result: dict) -> None:
        from models.base import Session as write_session

        with write_session() as session:
            chapter = session.get(Chapter, chapter_data["id"])
            if not chapter:
                return
            chapter.summary = result.get("summary", "")
            chapter.character_table = json.dumps(result.get("characters", []), ensure_ascii=False)
            chapter.events = json.dumps(result.get("events", []), ensure_ascii=False)
            chapter.scenes = json.dumps(result.get("scenes", []), ensure_ascii=False)
            chapter.foreshadowing = json.dumps(result.get("foreshadowing", []), ensure_ascii=False)
            chapter.appearance_fragments = json.dumps(result.get("appearance_fragments", {}), ensure_ascii=False)
            chapter.status = "analyzed"
            chapter.analyzed_at = datetime.utcnow()
            session.commit()

    def _update_vector_index(self, chapter_data: dict, result: dict) -> None:
        try:
            doc = (
                f"{chapter_data['title']}\n{result.get('summary', '')}\n"
                f"人物：{json.dumps(result.get('characters', []), ensure_ascii=False)}"
            )
            vs.add_documents(
                "chapters",
                [str(chapter_data["id"])],
                [doc],
                [{"book_id": self.book_id, "seq": chapter_data["seq"], "title": chapter_data["title"]}],
            )
        except Exception as exc:
            logger.warning("Failed to update vector index for ch%s: %s", chapter_data["seq"], exc)

    def _should_skip_llm_for_short_content(self, title: str, content: str) -> bool:
        normalized_title = str(title or "").strip()
        normalized_content = str(content or "").strip()
        if not normalized_content:
            return True
        if len(normalized_content) < MIN_CHAPTER_BODY_CHARS:
            return True
        if normalized_title and normalized_title == normalized_content:
            return True
        if re.fullmatch(r"[《》\w一-龥\-\s]+", normalized_content) and "。" not in normalized_content and len(normalized_content) <= 20:
            return True
        return False

    def _build_short_chapter_fallback(self, title: str, content: str) -> dict:
        marker = str(title or content or "章节占位").strip() or "章节占位"
        return {
            "summary": f"该章节当前仅包含标题或极短文本：{marker}。",
            "characters": [],
            "events": [],
            "scenes": [],
            "foreshadowing": [],
            "appearance_fragments": {},
        }

    def _build_local_fallback(self, title: str, content: str) -> dict:
        normalized_title = str(title or "").strip() or "未命名章节"
        normalized_content = str(content or "").strip()
        sentences = [item.strip() for item in re.split(r"[。！？\n]+", normalized_content) if item.strip()]
        summary = "；".join(sentences[:3])[:180] if sentences else f"{normalized_title} 内容待补充。"

        names = self._extract_character_names(normalized_content)
        characters = []
        appearance_fragments: dict[str, list[str]] = {}

        for name in names:
            identity = "普通角色（推测）"
            personality = ""
            if "和尚" in name:
                identity = "和尚（寺庙僧侣）"
                personality = "懒散、轻慢"
            elif name in {"阿宁", "阿寧"}:
                identity = "寺中新来的弟子（推测）"
                personality = "克制、隐忍"

            characters.append(
                {
                    "name": name,
                    "aliases": [],
                    "identity": identity,
                    "personality": personality,
                    "relationships": {},
                }
            )

            matched = [
                sentence
                for sentence in sentences
                if name in sentence and any(
                    keyword in sentence for keyword in ["光头", "僧袍", "包袱", "脸色", "念珠", "湿衣", "站姿", "神情"]
                )
            ]
            if matched:
                appearance_fragments[name] = matched[:4]

        scenes = []
        if normalized_content:
            location = "寺门" if "寺" in normalized_content else ("院落" if "院" in normalized_content else "未明确地点")
            mood = "压抑" if any(token in normalized_content for token in ["雨", "冷", "沉沉"]) else "平稳"
            scenes.append(
                {
                    "location": location,
                    "time": "未明确时间",
                    "mood": mood,
                    "description": (sentences[0] if sentences else normalized_content[:80])[:120],
                }
            )

        events = []
        for index, sentence in enumerate(sentences[:5], start=1):
            events.append(
                {
                    "seq": index,
                    "description": sentence[:120],
                    "importance": "medium" if index == 1 else "low",
                    "characters_involved": [name for name in names if name in sentence],
                }
            )

        return {
            "summary": summary,
            "characters": characters,
            "events": events,
            "scenes": scenes,
            "foreshadowing": [],
            "appearance_fragments": appearance_fragments,
        }

    def _extract_character_names(self, content: str) -> list[str]:
        found: list[str] = []
        explicit_patterns = [
            r"和尚[甲乙丙丁戊己庚辛壬癸]",
            r"阿[一-龥]",
            r"[一-龥]{2,4}(?:姐|姨|叔|伯|爷|娘|哥)",
        ]
        for pattern in explicit_patterns:
            for match in re.findall(pattern, content or ""):
                name = str(match).strip()
                if name and name not in found:
                    found.append(name)
        if found:
            return found[:8]

        for match in re.findall(r"(?:角色|人物)[:：]?([一-龥]{2,4})", content or ""):
            name = str(match).strip()
            if not name:
                continue
            if name in {"第1章", "雨夜归门", "新人就该", "青石板", "土墙发冷", "钟声沉沉", "看见灶间"}:
                continue
            if name not in found:
                found.append(name)
        return found[:8]

    def _save_character_table(self, all_characters: dict, book_title: str):
        if not all_characters:
            return
        from agents.bible import BibleAgent

        try:
            agent = BibleAgent(self.book_id)
            path_str = agent.run()
            self.log(f"Bible generated: {path_str}")
        except Exception as exc:
            self.log(f"Bible generation failed (non-fatal): {exc}")

    def _save_appearance_fragments(self, book_title: str):
        from models.base import Session as read_session

        with read_session() as session:
            chapters = (
                session.query(Chapter)
                .filter(
                    Chapter.book_id == self.book_id,
                    Chapter.status == "analyzed",
                    Chapter.appearance_fragments.isnot(None),
                    Chapter.appearance_fragments != "{}",
                    Chapter.appearance_fragments != "[]",
                )
                .order_by(Chapter.seq)
                .all()
            )

            fragments_by_char = {}
            for chapter in chapters:
                chapter_fragments = safe_json_loads(chapter.appearance_fragments, {})
                if not isinstance(chapter_fragments, dict):
                    continue
                for name, fragments in chapter_fragments.items():
                    if name not in fragments_by_char:
                        fragments_by_char[name] = []
                    fragments_by_char[name].append(
                        {
                            "chapter": chapter.seq,
                            "fragments": fragments if isinstance(fragments, list) else [str(fragments)],
                        }
                    )

            if not fragments_by_char:
                return

            path = config.output_path(book_title, "appearance_fragments.md")
            lines = ["# 外貌片段汇总\n"]
            for name, fragments_list in sorted(fragments_by_char.items()):
                lines.append(f"## {name}\n")
                for entry in fragments_list:
                    lines.append(f"### 第{entry['chapter']}章\n")
                    for fragment in entry["fragments"]:
                        lines.append(f"- {fragment}")
                    lines.append("")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines), encoding="utf-8")
            self.log(f"Appearance fragments saved: {path.name}")

    def _save_summaries(self, book_title: str):
        from models.base import Session as read_session

        with read_session() as session:
            chapters = (
                session.query(Chapter)
                .filter(Chapter.book_id == self.book_id, Chapter.status == "analyzed")
                .order_by(Chapter.seq)
                .all()
            )

            lines = [f"# 《{book_title}》章节摘要\n"]
            for chapter in chapters:
                lines.append(f"## 第{chapter.seq}章：{chapter.title}\n")
                lines.append(chapter.summary or "(无摘要)")
                lines.append("")
                lines.append("---")
                lines.append("")

            path = config.output_path(book_title, "summaries.md")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines), encoding="utf-8")
            self.log(f"Summaries saved: {path.name}")
