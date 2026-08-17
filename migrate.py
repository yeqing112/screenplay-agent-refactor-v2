"""Database migration: add appearance_fragments to chapters, add character_profiles table."""
import sqlite3
import sys
from pathlib import Path

# Ensure we can import config
sys.path.insert(0, str(Path(__file__).parent))
import config

DB_PATH = Path(config.DATABASE_URL.replace("sqlite:///", ""))


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        print("Run 'python cli.py ingest <novel.txt>' first.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # 1. Add appearance_fragments to chapters
    cur.execute("PRAGMA table_info(chapters)")
    columns = [row[1] for row in cur.fetchall()]
    if "appearance_fragments" not in columns:
        cur.execute("ALTER TABLE chapters ADD COLUMN appearance_fragments TEXT DEFAULT '{}'")
        print("[OK] Added 'appearance_fragments' to chapters table")
    else:
        print("[SKIP] 'appearance_fragments' already exists")

    # 2. Create character_profiles table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS character_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            aliases TEXT DEFAULT '[]',
            gender TEXT DEFAULT '',
            age_range TEXT DEFAULT '',
            role TEXT DEFAULT '',
            face_shape TEXT DEFAULT '',
            facial_features TEXT DEFAULT '',
            body_type TEXT DEFAULT '',
            skin_tone TEXT DEFAULT '',
            distinguishing_marks TEXT DEFAULT '',
            style_era TEXT DEFAULT '',
            signature_outfit TEXT DEFAULT '',
            accessories TEXT DEFAULT '',
            temperament TEXT DEFAULT '',
            vibe TEXT DEFAULT '',
            color_palette TEXT DEFAULT '',
            personality TEXT DEFAULT '',
            speech_style TEXT DEFAULT '',
            body_language TEXT DEFAULT '',
            relationships TEXT DEFAULT '{}',
            visual_prompt_en TEXT DEFAULT '',
            visual_prompt_zh TEXT DEFAULT '',
            chapter_range TEXT DEFAULT '',
            importance TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("[OK] character_profiles table ready")

    conn.commit()
    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()
