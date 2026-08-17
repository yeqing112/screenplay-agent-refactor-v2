"""将旧输出结构按小说名迁移到 outputs/{title}/ 新结构。

用法: python -m scripts.migrate_outputs [--dry-run]
"""
import json
import shutil
from pathlib import Path
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from models import Session, Book


def migrate(dry_run: bool = False):
    old_files = []

    # 扫描旧结构下的所有 book_{id}_* 文件
    old_dirs = [
        config.WORK_DIR / "analysis",
        config.WORK_DIR / "portraits",
        config.OUTPUT_DIR / "outlines",
        config.OUTPUT_DIR / "scripts",
        config.OUTPUT_DIR / "qa",
    ]
    for d in old_dirs:
        if d.exists():
            for f in d.iterdir():
                if f.is_file():
                    old_files.append(f)

    if not old_files:
        print("没有找到旧文件。")
        return

    # 获取 book_id → title 映射
    with Session() as s:
        books = {b.id: b.title for b in s.query(Book).all()}

    for old_path in sorted(old_files):
        # 解析 book_id (book_{id}_* 模式)
        name = old_path.stem
        parts = name.split("_", 2)
        if len(parts) < 2 or parts[0] != "book":
            continue
        try:
            book_id = int(parts[1])
        except ValueError:
            continue

        title = books.get(book_id)
        if not title:
            print(f"  [跳过] book_id={book_id} 未找到，跳过 {old_path.name}")
            continue

        # 解析类型和子目录
        suffix = old_path.suffix
        if "portrait" in old_path.parent.name or "profiles" in name or "prompts" in name:
            sub = "portraits"
        elif "bible" in name:
            sub = "."
        elif "adaptation" in name or "adapt" in name:
            sub = "."
        elif "outline" in name:
            sub = "outlines"
        elif "script" in name or "ep" in name:
            sub = "scripts"
        elif "qa" in name or "QA" in name:
            sub = "qa"
        elif "characters" in name:
            sub = "analysis"
        elif "fragments" in name:
            sub = "analysis"
        elif "summaries" in name:
            sub = "analysis"
        else:
            sub = "."

        if sub == ".":
            new_path = config.output_path(title, f"{old_path.name}")
        else:
            new_path = config.output_path(title, sub, f"{old_path.name}")

        if not dry_run:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(old_path), str(new_path))
        print(f"  {'->' if not dry_run else '=>'} {old_path} -> {new_path}")

    print(f"\n{'迁移完成' if not dry_run else '试运行完成'}。共处理 {len(old_files)} 个文件。")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv
    migrate(dry_run=dry_run)
