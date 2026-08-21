"""Bible Agent - 合并所有分析，生成小说圣经。"""
import logging
import re
import config
from models import Book, Chapter, BookBible, CharacterProfile
from core import safe_json_loads
from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class BibleAgent(BaseAgent):
    """汇总所有章节分析，生成小说圣经。"""

    name = "bible"

    def run(self) -> str:
        try:
            with self.session() as s:
                book = s.get(Book, self.book_id)
                if not book:
                    raise ValueError(f"Book {self.book_id} not found")

                chapters = s.query(Chapter).filter(
                    Chapter.book_id == self.book_id
                ).order_by(Chapter.seq).all()

                if not any(ch.status == "analyzed" for ch in chapters):
                    raise ValueError("No analyzed chapters. Run 'read' first.")

                # Build character database
                all_characters = {}
                all_events = []
                all_locations = set()
                all_foreshadowing = []

                for ch in chapters:
                    if ch.status != "analyzed":
                        continue

                    for c in safe_json_loads(ch.character_table, []):
                        name = c.get("name", "")
                        if name:
                            if name not in all_characters:
                                all_characters[name] = {
                                    "name": name,
                                    "aliases": c.get("aliases", []),
                                    "identity": c.get("identity", ""),
                                    "personality": c.get("personality", ""),
                                    "relationships": c.get("relationships", {}),
                                    "chapters": [ch.seq],
                                }
                            else:
                                all_characters[name]["chapters"].append(ch.seq)
                                new_id = c.get("identity", "")
                                if new_id and not all_characters[name].get("identity"):
                                    all_characters[name]["identity"] = new_id

                    for e in safe_json_loads(ch.events, []):
                        e["chapter"] = ch.seq
                        all_events.append(e)

                    for sc in safe_json_loads(ch.scenes, []):
                        if sc.get("location"):
                            all_locations.add(sc["location"])

                    for f in safe_json_loads(ch.foreshadowing, []):
                        all_foreshadowing.append({"text": f, "chapter": ch.seq})

                doc = self._build_bible(book, chapters, all_characters,
                                         all_events, all_locations, all_foreshadowing,
                                         session=s)

                # ── Bible QA check ──
                try:
                    from agents.bible_qa import BibleQAChecker
                    bible_qa = BibleQAChecker(self.book_id)
                    qa_result = bible_qa.run(bible_content=doc)
                    qa_score = qa_result.get("overall_score", 9)
                    auto_fixes = qa_result.get("auto_fixes", [])
                    if auto_fixes:
                        doc = self._apply_bible_qa_fixes(doc, auto_fixes)
                    if qa_score < 6:
                        logger.warning(
                            "Bible QA score=%d for book %s — review recommended",
                            qa_score, self.book_id,
                        )
                except Exception as qa_exc:
                    logger.warning("Bible QA non-blocking error: %s", qa_exc)

                output = config.output_path(book.title, "bible.md")
                output.write_text(doc, encoding="utf-8")

                bible_entry = s.query(BookBible).filter(
                    BookBible.book_id == self.book_id
                ).first()
                if bible_entry:
                    bible_entry.content = doc
                else:
                    s.add(BookBible(book_id=self.book_id, content=doc))
                book.status = "bibled"
                s.commit()

            return str(output)

        except Exception as e:
            logger.error("Bible generation failed for book %s: %s", self.book_id, e)
            raise

    def _build_bible(self, book, chapters, characters, events, locations,
                     foreshadowing, session=None):
        """Build the novel bible markdown document."""
        lines = [f"# 小说圣经 - {book.title}\n"]

        lines.append("\n## 一、人物数据库\n")
        portraits = {}
        db_session = session or self.session
        try:
            for p in db_session.query(CharacterProfile).filter(
                CharacterProfile.book_id == book.id
            ).all():
                portraits[p.name] = p
        except Exception as e:
            logger.warning("Failed to load portraits for bible: %s", e)

        for c in characters.values():
            name = c['name']
            lines.append(f"### {name}")
            if c.get('identity'):
                lines.append(f"**身份/职业：** {c['identity']}")
            if c['aliases']:
                lines.append(f"**别名：** {', '.join(c['aliases'])}")
            lines.append(f"**性格：** {c['personality']}")
            if c['relationships']:
                lines.append("**关系：**")
                for rel, desc in c['relationships'].items():
                    lines.append(f"- {rel}: {desc}")
            lines.append(f"**出场章节：** 第{min(c['chapters'])}章 ~ 第{max(c['chapters'])}章")

            p = portraits.get(name)
            if p:
                lines.append(f"\n**【人物画像】**")
                lines.append(f"- 性别: {p.gender} | 年龄: {p.age_range} | 定位: {p.role}")
                lines.append(f"- 脸型: {p.face_shape}")
                lines.append(f"- 五官: {p.facial_features}")
                lines.append(f"- 体型: {p.body_type}")
                lines.append(f"- 肤色: {p.skin_tone}")
                if p.distinguishing_marks and p.distinguishing_marks != "无":
                    lines.append(f"- 辨识特征: {p.distinguishing_marks}")
                lines.append(f"- 穿着: {p.signature_outfit}")
                if p.accessories and p.accessories != "无":
                    lines.append(f"- 配饰: {p.accessories}")
                lines.append(f"- 气质: {p.temperament}")
                lines.append(f"- 氛围: {p.vibe}")
                lines.append(f"- 代表色: {p.color_palette}")
                lines.append(f"- 说话风格: {p.speech_style}")
                lines.append(f"- 体态: {p.body_language}")
            lines.append("")

        lines.append("\n## 二、主线与支线\n")
        high_events = [e for e in events if e.get("importance") == "high"]
        for e in high_events:
            lines.append(f"- **第{e.get('chapter', '?')}章：** {e.get('description', '')}")
        lines.append("\n### 支线")
        mid_events = [e for e in events if e.get("importance") == "medium"]
        for e in mid_events[:20]:
            lines.append(f"- **第{e.get('chapter', '?')}章：** {e.get('description', '')}")

        lines.append("\n## 三、世界观与设定\n")
        lines.append("### 重要地点")
        for loc in sorted(locations):
            lines.append(f"- {loc}")

        lines.append("\n## 四、时间线\n")
        key_events = sorted(events, key=lambda x: x.get("chapter", 0))[:30]
        for e in key_events:
            lines.append(f"- **第{e.get('chapter', '?')}章：** {e.get('description', '')}")

        lines.append("\n## 五、伏笔与悬念\n")
        for f in foreshadowing:
            lines.append(f"- **第{f['chapter']}章：** {f['text']}")

        lines.append("\n## 六、主题表达\n")
        lines.append("(由后续 AI 分析补充)")

        return "\n".join(lines)

    def _apply_bible_qa_fixes(self, doc: str, auto_fixes: list[dict]) -> str:
        """Apply deterministic auto-fixes to bible markdown."""
        for fix in auto_fixes:
            old_val = str(fix.get("old_value", "") or "")
            new_val_raw = fix.get("new_value", "")
            new_val = str(new_val_raw or "")
            char_name = str(fix.get("character", "") or "")
            if not old_val or not new_val:
                continue

            updated = self._replace_in_character_section(doc, char_name, old_val, new_val)
            if updated == doc:
                logger.warning(
                    "Skipped Bible QA auto-fix without unique character section: %s %s → %s",
                    char_name, old_val, new_val,
                )
                continue

            doc = updated
            logger.info(
                "Bible QA auto-fix: %s %s → %s",
                char_name, old_val, new_val,
            )
        return doc

    def _replace_in_character_section(
        self,
        doc: str,
        character_name: str,
        old_val: str,
        new_val: str,
    ) -> str:
        """Replace a value only inside the intended character section.

        Bible QA auto-fixes are derived from character-scoped portrait data. A
        plain document-wide replace can silently update the wrong person when
        common values such as "20-30岁" appear in several sections.
        """
        if not character_name:
            return doc

        heading_pattern = re.compile(rf"(?m)^###\s+{re.escape(character_name)}\s*$")
        heading_match = heading_pattern.search(doc)
        if not heading_match:
            return doc

        start = heading_match.start()
        next_heading = re.search(r"(?m)^###\s+", doc[heading_match.end():])
        end = heading_match.end() + next_heading.start() if next_heading else len(doc)
        section = doc[start:end]
        if old_val not in section:
            return doc

        updated_section = section.replace(old_val, new_val, 1)
        return f"{doc[:start]}{updated_section}{doc[end:]}"
