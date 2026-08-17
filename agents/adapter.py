"""Adapter Agent - 改编规划。接入 genre 系统，不同赛道用不同策略。"""
import logging
import config
from models import Book, BookBible, CharacterProfile
from core.llm import call_llm
from genres import get_genre
from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class AdapterAgent(BaseAgent):
    """生成改编规划。根据 genre 自动切换策略。"""

    name = "adapter"

    def __init__(self, book_id: int, genre: str = "short_drama"):
        super().__init__(book_id)
        self.genre = get_genre(genre)

    def run(self) -> str:
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

                portraits = ""
                try:
                    profiles = s.query(CharacterProfile).filter(
                        CharacterProfile.book_id == self.book_id
                    ).all()
                    for p in profiles:
                        portraits += f"\n### {p.name}\n"
                        portraits += f"性别: {p.gender} | 年龄: {p.age_range} | 角色: {p.role}\n"
                        portraits += f"气质: {p.temperament} | 氛围: {p.vibe}\n"
                        portraits += f"穿着: {p.signature_outfit}\n"
                        portraits += f"说话风格: {p.speech_style}\n"
                except Exception as e:
                    logger.warning("Failed to load profiles: %s", e)

                prompt = self.genre.get_adapt_prompt(
                    bible=bible_entry.content[:config.BIBLE_EXCERPT_CHARS],
                    portraits=portraits[:config.PORTRAIT_EXCERPT_CHARS],
                )
                result = call_llm(
                    prompt,
                    system=self.genre.system_prompt,
                    estimated_tokens=config.SCRIPT_EXCERPT_CHARS,
                )

                output = config.output_path(book.title, f"{self.genre.name}_改编方案.md")
                output.write_text(
                    f"# {book.title} - {self.genre.description}改编方案\n\n{result}",
                    encoding="utf-8",
                )
                book.status = "adapted"
                s.commit()

            return str(output)

        except Exception as e:
            logger.error("Adaptation failed for book %s: %s", self.book_id, e)
            raise
