"""Novel ingestion: parse source text and import it into the project store."""

import re
from pathlib import Path

from core import vector_search as vs
from models import Book, Chapter, Session

CHAPTER_PATTERNS = [
    r"^第[一二三四五六七八九十百千万两零\d]+章",
    r"^第[一二三四五六七八九十百千万两零\d]+节",
    r"^Chapter\s+\d+",
    r"^CHAPTER\s+\d+",
    r"^\d+\.\s+.{2,30}$",
    r"^#{1,3}\s+第.+章",
]

INVALID_EXTRACTED_TITLE_SIGNALS = [
    "无法从给定文本中提取标题",
    "请提供包含书名",
    "请提供包含书籍/故事标题",
    "请提供包含书籍",
    "未包含书籍或故事标题信息",
    "标题信息",
]


def _detect_chapters(text: str) -> list[tuple[str, str]]:
    """Split text by chapter headings. Returns list of (title, content)."""

    def _is_document_title_only(value: str) -> bool:
        """Ignore a standalone book title before the first chapter heading.

        Uploaded novels commonly put ``《书名》`` (and optional blank lines)
        before ``第一章``.  Treating that title as an empty chapter shifts every
        subsequent chapter number.  Substantive prologues remain untouched.
        """

        compact = "".join(str(value or "").split())
        return bool(re.fullmatch(r"《[^《》]{1,80}》", compact))

    lines = text.split("\n")
    chapters: list[tuple[str, str]] = []
    current_title = ""
    current_lines: list[str] = []

    for line in lines:
        is_chapter = any(re.match(pattern, line.strip()) for pattern in CHAPTER_PATTERNS)
        if is_chapter:
            if current_lines:
                preface = "\n".join(current_lines).strip()
                if current_title or not _is_document_title_only(preface):
                    chapters.append((current_title, preface))
            current_title = line.strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        chapters.append((current_title, "\n".join(current_lines).strip()))

    return chapters


def _should_auto_extract_title(candidate: str) -> bool:
    return candidate in ("text_input", "paste", "input", "unknown") or bool(
        re.match(r"^\d{8}_\d{6}_", candidate)
    )


def _is_invalid_extracted_title(candidate: str) -> bool:
    text = str(candidate or "").strip()
    if not text:
        return True

    compact = "".join(text.split())
    if "锟" in compact:
        return True

    question_mark_ratio = compact.count("?") / len(compact) if compact else 0
    if compact.count("?") >= 2 and question_mark_ratio >= 0.2:
        return True

    if any(signal in text for signal in INVALID_EXTRACTED_TITLE_SIGNALS):
        return True

    if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", text):
        return True

    return False


def ingest(filepath: str, preferred_title: str | None = None) -> dict:
    """Import a novel file. Returns {book_id, title, chapters, words}."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("gbk")

    title = (preferred_title or "").strip() or path.stem

    # Auto-extract book title only when no explicit preferred title is provided
    # and the uploaded filename is clearly a temporary placeholder.
    if not (preferred_title or "").strip() and _should_auto_extract_title(title):
        try:
            from core.llm import call_llm

            extract_prompt = (
                "从以下文本中提取书籍/故事标题，只返回标题本身，不超过20个字。\n\n"
                f"{text[:2000]}"
            )
            extracted = call_llm(extract_prompt, estimated_tokens=200).strip()
            extracted = extracted.strip("\"'\n").split("\n")[0][:50]
            if extracted and 1 < len(extracted) < 50 and not _is_invalid_extracted_title(extracted):
                title = extracted
                path.rename(path.parent / f"{title}{path.suffix}")
        except Exception:
            pass

    raw_chapters = _detect_chapters(text)
    if not raw_chapters:
        raw_chapters = [(title, text)]

    import config

    with Session() as session:
        book = Book(title=title, filename=path.name, status="imported")
        session.add(book)
        session.flush()

        total_words = 0
        chapter_ids: list[str] = []
        chapter_docs: list[str] = []
        chapter_metas: list[dict] = []

        for index, (chapter_title, content) in enumerate(raw_chapters, 1):
            word_count = len(content)
            total_words += word_count

            chapter = Chapter(
                book_id=book.id,
                seq=index,
                title=chapter_title,
                content=content,
                word_count=word_count,
                status="imported",
            )
            session.add(chapter)
            session.flush()
            chapter_ids.append(str(chapter.id))
            chapter_docs.append(f"{chapter_title}\n{content[:2000]}")
            chapter_metas.append({"book_id": book.id, "seq": index, "title": chapter_title})

        book.chapter_count = len(raw_chapters)
        book.total_words = total_words

        output_path = config.output_path(title, "原始小说.txt")
        output_path.write_text(text, encoding="utf-8")

        session.commit()

        if chapter_docs:
            vs.add_documents("chapters", chapter_ids, chapter_docs, chapter_metas)

        return {
            "book_id": book.id,
            "title": title,
            "chapters": len(raw_chapters),
            "words": total_words,
        }
