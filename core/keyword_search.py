"""SQLite FTS5 keyword search."""
import sqlite3
import config


def _get_db():
    db_path = config.DB_DIR / "screenplay.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_fts():
    """Create FTS5 virtual table for keyword search."""
    conn = _get_db()
    # Keep the index self-contained.  The previous external-content
    # definition pointed at ``chapters`` while declaring a non-existent
    # ``chapter_id`` column, which made ordinary MATCH queries fail with
    # ``no such column: T.chapter_id``.  ``rebuild_fts`` already writes
    # the projection explicitly, so a contentless table is the correct
    # representation for this derived search index.
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chapter_fts USING fts5(
            chapter_id, book_id, seq, summary, characters, events, scenes
        )
    """)
    conn.commit()
    conn.close()


def rebuild_fts(book_id: int):
    """Rebuild FTS index for a book."""
    conn = _get_db()
    conn.execute("DELETE FROM chapter_fts WHERE book_id = ?", (book_id,))
    conn.execute("""
        INSERT INTO chapter_fts(chapter_id, book_id, seq, summary, characters, events, scenes)
        SELECT id, book_id, seq, summary, character_table, events, scenes
        FROM chapters WHERE book_id = ? AND status = 'analyzed'
    """, (book_id,))
    conn.commit()
    conn.close()


def keyword_search(query: str, book_id: int = None, limit: int = 20) -> list[dict]:
    """Full-text keyword search. Returns list of {chapter_id, seq, snippet, rank}."""
    conn = _get_db()

    # FTS5 MATCH treats raw strings as query syntax. Escape special chars.
    # Wrap entire query in double quotes to treat as literal phrase where possible.
    # Remove FTS5 "NEAR" / "AND" / "OR" operators that may come from CJK split.
    safe_query = _escape_fts_query(query)

    if book_id:
        rows = conn.execute("""
            SELECT chapter_id, seq, snippet(chapter_fts, 3, '<b>', '</b>', '...', 32) as snippet,
                   rank
            FROM chapter_fts
            WHERE chapter_fts MATCH ? AND book_id = ?
            ORDER BY rank
            LIMIT ?
        """, (safe_query, book_id, limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT chapter_id, seq, snippet(chapter_fts, 3, '<b>', '</b>', '...', 32) as snippet,
                   rank
            FROM chapter_fts
            WHERE chapter_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (safe_query, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _escape_fts_query(query: str) -> str:
    """Escape a query string for FTS5 MATCH to prevent syntax errors.

    Strategy: wrap each non-whitespace token in double quotes so FTS5
    treats them as literal column terms rather than query operators.
    This is necessary because unicode61 tokenizer splits CJK into
    unigrams, and FTS5 may interpret certain CJK characters as
    NEAR/AND/OR syntax (e.g. "大凤" → tokens ["大", "凤"] where
    "凤" could be misinterpreted).
    """
    # Tokenize by whitespace, wrap each in quotes
    tokens = query.split()
    if not tokens:
        return '""'
    return " ".join(f'"{t}"' for t in tokens)
