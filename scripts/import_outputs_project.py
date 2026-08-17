import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models import (
    Book,
    BookBible,
    CharacterProfile,
    EpisodeOutline,
    QAResult,
    Script,
    Session,
    StoryboardShot,
    VisualEraSpec,
    VisualLocation,
    VisualMakeup,
    VisualProp,
    init_db,
)


ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "gbk")
CHILD_MODELS = (
    BookBible,
    CharacterProfile,
    EpisodeOutline,
    QAResult,
    Script,
    StoryboardShot,
    VisualEraSpec,
    VisualLocation,
    VisualMakeup,
    VisualProp,
)


def read_text_guess(path: Path) -> str:
    last_error: Exception | None = None
    for encoding in ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except Exception as error:  # pragma: no cover - best-effort fallback
            last_error = error
    raise RuntimeError(f"Unable to read {path}") from last_error


def load_json_guess(path: Path) -> Any:
    return json.loads(read_text_guess(path))


def parse_episode_number(name: str) -> int:
    match = re.search(r"第\s*0*(\d+)\s*集", name)
    return int(match.group(1)) if match else 1


def strip_timestamp_prefix(name: str) -> str:
    return re.sub(r"^\d{8}_\d{6}_?", "", name)


def find_title_from_markdown(project_dir: Path) -> str | None:
    for path in sorted(project_dir.glob("*.md")):
        text = read_text_guess(path)[:4000]
        match = re.search(r"《([^》]+)》", text)
        if match:
            return match.group(1).strip()
    return None


def detect_title(project_dir: Path) -> str:
    return find_title_from_markdown(project_dir) or strip_timestamp_prefix(project_dir.name)


def extract_section(text: str, heading: str) -> str:
    pattern = rf"##\s*{re.escape(heading)}\s*\n(.*?)(?=\n##\s+|\Z)"
    match = re.search(pattern, text, re.S)
    return match.group(1).strip() if match else ""


def parse_time_periods(section: str) -> list[dict[str, str]]:
    periods: list[dict[str, str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        content = stripped[2:]
        match = re.match(r"(.+?)\s+\((\d{4}(?:-\d{4})?)\)\s*(.*)", content)
        if match:
            periods.append(
                {
                    "period": match.group(1).strip(),
                    "years": match.group(2).strip(),
                    "description": match.group(3).strip(),
                }
            )
        else:
            periods.append({"period": content.strip(), "years": "", "description": ""})
    return periods


def count_chapters_and_words(original_text: str) -> tuple[int, int]:
    chapter_matches = re.findall(r"^\s*第[^\n]{1,20}章", original_text, re.M)
    word_count = len(re.sub(r"\s+", "", original_text))
    return len(chapter_matches), word_count


def choose_script_files(scripts_dir: Path) -> list[Path]:
    by_episode: dict[int, list[Path]] = {}
    for path in scripts_dir.glob("*.md"):
        episode = parse_episode_number(path.stem)
        by_episode.setdefault(episode, []).append(path)

    selected: list[Path] = []
    for episode in sorted(by_episode):
        candidates = sorted(
            by_episode[episode],
            key=lambda path: (
                0 if re.fullmatch(r"第\d+集脚本", path.stem) else 1,
                len(path.stem),
                path.name,
            ),
        )
        selected.append(candidates[0])
    return selected


def parse_outlines(outline_text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    pattern = r"##\s*第\s*(\d+)\s*集[:：]\s*(.+?)\n(.*?)(?=\n##\s*第\s*\d+\s*集|\Z)"
    for match in re.finditer(pattern, outline_text, re.S):
        episode = int(match.group(1))
        title = match.group(2).strip()
        block = match.group(3)

        def value(label: str) -> str:
            field_match = re.search(rf"\*\*{re.escape(label)}：\*\*\s*(.+)", block)
            return field_match.group(1).strip() if field_match else ""

        characters = [item.strip() for item in value("主要角色").split(",") if item.strip()]
        scenes = [item.strip() for item in value("关键场景").split(",") if item.strip()]
        results.append(
            {
                "episode": episode,
                "title": title,
                "core_event": value("核心事件"),
                "opening_hook": value("开场钩子"),
                "core_conflict": value("核心冲突"),
                "climax": value("反转/高潮"),
                "ending_hook": value("结尾悬念"),
                "characters": characters,
                "scenes": scenes,
                "raw_content": block.strip(),
            }
        )
    return results


def parse_makeup_markdown(summary_text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    episode_blocks = re.split(r"(?m)^##\s*第\s*0*(\d+)\s*集\s*$", summary_text)
    if len(episode_blocks) < 3:
        return results

    for index in range(1, len(episode_blocks), 2):
        episode = int(episode_blocks[index])
        content = episode_blocks[index + 1]
        for match in re.finditer(r"(?ms)^###\s*(.+?)\n(.*?)(?=^###\s+|\Z)", content):
            character_name = match.group(1).strip()
            block = match.group(2)

            def line_value(label: str) -> str:
                value_match = re.search(rf"^{re.escape(label)}：\s*(.+)$", block, re.M)
                return value_match.group(1).strip() if value_match else ""

            results.append(
                {
                    "episode": episode,
                    "character_name": character_name,
                    "refined_outfit": line_value("穿着"),
                    "makeup_spec": line_value("妆容"),
                    "expression_mood": line_value("表情"),
                }
            )
    return results


def infer_shot_ids_from_text(name: str, shots: list[dict[str, Any]], extra_text: str = "") -> list[int]:
    shot_ids: list[int] = []
    for shot in shots:
        text = " ".join(
            [
                str(shot.get("scene_name", "")),
                str(shot.get("dialogue", "")),
                str(shot.get("start_state", "")),
                str(shot.get("action_process", "")),
                str(shot.get("end_state", "")),
                str(shot.get("visual_prompt_static", "")),
                str(shot.get("visual_prompt_motion", "")),
                extra_text,
            ]
        )
        if name and name in text:
            shot_ids.append(int(shot.get("id") or shot.get("shot_id") or 0))
    return sorted({shot_id for shot_id in shot_ids if shot_id > 0})


def upsert_book(session: Session, title: str, filename: str, chapter_count: int, total_words: int) -> Book:
    book = session.query(Book).filter(Book.title == title).first()
    if book is None:
        book = Book(title=title, filename=filename)
        session.add(book)
        session.flush()

    book.filename = filename
    book.chapter_count = chapter_count
    book.total_words = total_words
    book.status = "storyboarded"
    return book


def clear_book_children(session: Session, book_id: int) -> None:
    for model in CHILD_MODELS:
        session.query(model).filter(model.book_id == book_id).delete()


def import_project(project_dir: Path) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    title = detect_title(project_dir)
    original_text_path = next(iter(project_dir.glob("*原始小说*.txt")), None)
    original_text = read_text_guess(original_text_path) if original_text_path else ""
    chapter_count, total_words = count_chapters_and_words(original_text)

    bible_text = read_text_guess(project_dir / "bible.md") if (project_dir / "bible.md").exists() else ""
    outline_path = next(iter((project_dir / "outlines").glob("*.md")), None) if (project_dir / "outlines").exists() else None
    outline_text = read_text_guess(outline_path) if outline_path else ""
    era_text = read_text_guess(project_dir / "visual" / "时代妆造规范.md") if (project_dir / "visual" / "时代妆造规范.md").exists() else ""

    storyboard_by_episode: dict[int, list[dict[str, Any]]] = {}
    storyboard_dir = project_dir / "storyboard"
    if storyboard_dir.exists():
        for path in sorted(storyboard_dir.glob("*.json")):
            episode = parse_episode_number(path.stem)
            storyboard_by_episode[episode] = load_json_guess(path)

    locations_data = load_json_guess(project_dir / "visual" / "场景提示词.json") if (project_dir / "visual" / "场景提示词.json").exists() else []
    props_data = load_json_guess(project_dir / "visual" / "道具提示词.json") if (project_dir / "visual" / "道具提示词.json").exists() else []
    portraits_data = load_json_guess(project_dir / "portraits" / "角色画像.json") if (project_dir / "portraits" / "角色画像.json").exists() else {"profiles": []}

    makeups_summary = project_dir / "makeups" / "定妆照汇总.md"
    makeup_items = parse_makeup_markdown(read_text_guess(makeups_summary)) if makeups_summary.exists() else []

    qa_by_episode: dict[int, Any] = {}
    qa_dir = project_dir / "qa"
    if qa_dir.exists():
        for path in sorted(qa_dir.glob("*.json")):
            qa_by_episode[parse_episode_number(path.stem)] = load_json_guess(path)

    with Session() as session:
        book = upsert_book(
            session=session,
            title=title,
            filename=original_text_path.name if original_text_path else project_dir.name,
            chapter_count=chapter_count,
            total_words=total_words,
        )
        book_id = book.id
        clear_book_children(session, book.id)

        if bible_text:
            session.add(BookBible(book_id=book.id, content=bible_text))

        if era_text:
            time_range_section = extract_section(era_text, "时间范围")
            time_period_section = extract_section(era_text, "时间分期")
            time_range_parts = [part.strip() for part in time_range_section.split("~")] if time_range_section else ["", ""]
            session.add(
                VisualEraSpec(
                    book_id=book.id,
                    timeline_start=time_range_parts[0] if time_range_parts else "",
                    timeline_end=time_range_parts[1] if len(time_range_parts) > 1 else "",
                    time_periods=json.dumps(parse_time_periods(time_period_section), ensure_ascii=False),
                    clothing_spec=extract_section(era_text, "服饰规范"),
                    architecture_spec=extract_section(era_text, "建筑风格"),
                    environment_spec=extract_section(era_text, "环境特征"),
                    color_palette=extract_section(era_text, "色彩基调"),
                    color_curve=extract_section(era_text, "色彩曲线"),
                    raw_periods=json.dumps(time_period_section.splitlines(), ensure_ascii=False),
                )
            )

        for outline in parse_outlines(outline_text):
            session.add(
                EpisodeOutline(
                    book_id=book.id,
                    genre="short_drama",
                    episode=outline["episode"],
                    title=outline["title"],
                    core_event=outline["core_event"],
                    opening_hook=outline["opening_hook"],
                    core_conflict=outline["core_conflict"],
                    climax=outline["climax"],
                    ending_hook=outline["ending_hook"],
                    characters=json.dumps(outline["characters"], ensure_ascii=False),
                    scenes=json.dumps(outline["scenes"], ensure_ascii=False),
                    raw_content=outline["raw_content"],
                )
            )

        scripts_dir = project_dir / "scripts"
        if scripts_dir.exists():
            for path in choose_script_files(scripts_dir):
                content = read_text_guess(path)
                session.add(
                    Script(
                        book_id=book.id,
                        genre="short_drama",
                        episode=parse_episode_number(path.stem),
                        content=content,
                        word_count=len(re.sub(r"\s+", "", content)),
                        status="done",
                    )
                )

        for episode, qa in sorted(qa_by_episode.items()):
            error_count = len(qa.get("errors", [])) if isinstance(qa, dict) else 0
            session.add(
                QAResult(
                    book_id=book.id,
                    episode=episode,
                    result=json.dumps(qa, ensure_ascii=False),
                    error_count=error_count,
                )
            )

        for episode, shots in sorted(storyboard_by_episode.items()):
            for shot in shots:
                session.add(
                    StoryboardShot(
                        book_id=book.id,
                        episode=episode,
                        scene_name=shot.get("scene_name") or f"第{episode}集场景",
                        shot_id=int(shot.get("id") or shot.get("shot_id") or 0),
                        dialogue=shot.get("dialogue", ""),
                        duration=int(shot.get("duration") or 3),
                        camera_angle=shot.get("camera_angle", "MS"),
                        camera_movement=shot.get("camera_movement", "static"),
                        transition=shot.get("transition", "cut"),
                        lighting=shot.get("lighting", ""),
                        sound_effects=json.dumps(shot.get("sound_effects", []), ensure_ascii=False),
                        bgm_mood=shot.get("bgm_mood", ""),
                        start_state=shot.get("start_state", ""),
                        action_process=shot.get("action_process", ""),
                        end_state=shot.get("end_state", ""),
                        visual_prompt_static=shot.get("visual_prompt_static", ""),
                        visual_prompt_motion=shot.get("visual_prompt_motion", ""),
                        visual_prompt_final=shot.get("visual_prompt_final", ""),
                        asset_links=json.dumps(shot.get("asset_links", {}), ensure_ascii=False),
                        asset_status=shot.get("asset_status", "pending"),
                    )
                )

        all_shots = [shot for shots in storyboard_by_episode.values() for shot in shots]

        for location in locations_data:
            shot_ids = [int(shot.get("id") or shot.get("shot_id") or 0) for shot in all_shots if shot.get("scene_name") == location.get("name")]
            session.add(
                VisualLocation(
                    book_id=book.id,
                    book_title=title,
                    name=location.get("name", ""),
                    category=location.get("category", ""),
                    style=location.get("style", ""),
                    description=location.get("description", ""),
                    color_palette=location.get("color_palette", ""),
                    lighting_mood=location.get("lighting_mood", ""),
                    key_props=location.get("key_props", "[]"),
                    episodes=location.get("episodes", "[]"),
                    time_period=location.get("time_period", ""),
                    visual_prompt_en=location.get("visual_prompt_en", ""),
                    visual_prompt_zh=location.get("visual_prompt_zh", ""),
                    core_prompt_en=location.get("core_prompt_en", ""),
                    core_prompt_zh=location.get("core_prompt_zh", ""),
                    importance=location.get("importance", "medium"),
                    shot_ids=json.dumps([shot_id for shot_id in shot_ids if shot_id > 0], ensure_ascii=False),
                )
            )

        for prop in props_data:
            shot_ids = infer_shot_ids_from_text(prop.get("name", ""), all_shots, prop.get("description", ""))
            session.add(
                VisualProp(
                    book_id=book.id,
                    book_title=title,
                    name=prop.get("name", ""),
                    category=prop.get("category", ""),
                    description=prop.get("description", ""),
                    associated_characters=prop.get("associated_characters", ""),
                    episodes=prop.get("episodes", "[]"),
                    time_period=prop.get("time_period", ""),
                    visual_prompt_en=prop.get("visual_prompt_en", ""),
                    visual_prompt_zh=prop.get("visual_prompt_zh", ""),
                    core_prompt_en=prop.get("core_prompt_en", ""),
                    core_prompt_zh=prop.get("core_prompt_zh", ""),
                    importance=prop.get("importance", "medium"),
                    shot_ids=json.dumps(shot_ids, ensure_ascii=False),
                )
            )

        for profile in portraits_data.get("profiles", []):
            session.add(
                CharacterProfile(
                    book_id=book.id,
                    name=profile.get("name", ""),
                    gender=profile.get("gender", ""),
                    identity=profile.get("identity", ""),
                    temperament=profile.get("temperament", ""),
                    vibe=profile.get("vibe", ""),
                    visual_prompt_en=profile.get("visual_prompt_en", ""),
                    visual_prompt_zh=profile.get("visual_prompt_zh", ""),
                    core_prompt_en=profile.get("core_prompt_en", ""),
                    core_prompt_zh=profile.get("core_prompt_zh", ""),
                    outfit_prompt_en=profile.get("outfit_prompt_en", ""),
                    outfit_prompt_zh=profile.get("outfit_prompt_zh", ""),
                    scene_prompt_en=profile.get("scene_prompt_en", ""),
                    scene_prompt_zh=profile.get("scene_prompt_zh", ""),
                )
            )

        for makeup in makeup_items:
            shot_ids = infer_shot_ids_from_text(makeup["character_name"], storyboard_by_episode.get(makeup["episode"], []))
            session.add(
                VisualMakeup(
                    book_id=book.id,
                    book_title=title,
                    episode=makeup["episode"],
                    character_name=makeup["character_name"],
                    refined_outfit=makeup["refined_outfit"],
                    makeup_spec=makeup["makeup_spec"],
                    expression_mood=makeup["expression_mood"],
                    visual_prompt_zh="\n".join(
                        [
                            f"穿着：{makeup['refined_outfit']}" if makeup["refined_outfit"] else "",
                            f"妆容：{makeup['makeup_spec']}" if makeup["makeup_spec"] else "",
                            f"表情：{makeup['expression_mood']}" if makeup["expression_mood"] else "",
                        ]
                    ).strip(),
                    shot_ids=json.dumps(shot_ids, ensure_ascii=False),
                )
            )

        session.commit()

    return {
        "title": title,
        "book_id": book_id,
        "scripts": len(choose_script_files(project_dir / "scripts")) if (project_dir / "scripts").exists() else 0,
        "storyboard_shots": sum(len(shots) for shots in storyboard_by_episode.values()),
        "locations": len(locations_data),
        "props": len(props_data),
        "profiles": len(portraits_data.get("profiles", [])),
        "makeups": len(makeup_items),
    }


def discover_projects(outputs_dir: Path) -> list[Path]:
    projects: list[Path] = []
    for child in sorted(outputs_dir.iterdir()):
        if not child.is_dir():
            continue
        if "text_input" in child.name.lower():
            continue
        rich_output_dirs = (
            child / "scripts",
            child / "storyboard",
            child / "visual",
            child / "portraits",
            child / "makeups",
        )
        if any(path.exists() for path in rich_output_dirs):
            projects.append(child)
    return projects


def main() -> None:
    parser = argparse.ArgumentParser(description="Import existing outputs folders into the local database.")
    parser.add_argument("project", nargs="?", default="outputs", help="Path to one outputs project folder or the outputs root.")
    parser.add_argument("--all", action="store_true", help="Import all detected project folders under the given root.")
    args = parser.parse_args()

    init_db()

    target = Path(args.project)
    if not target.exists():
        raise SystemExit(f"Path not found: {target}")

    if args.all or target.name == "outputs":
        project_dirs = discover_projects(target)
    else:
        project_dirs = [target]

    if not project_dirs:
        raise SystemExit("No importable project directories were found.")

    imported: list[dict[str, Any]] = []
    for project_dir in project_dirs:
        try:
            result = import_project(project_dir)
            imported.append(result)
            print(
                f"[OK] {result['title']} -> book_id={result['book_id']} "
                f"scripts={result['scripts']} shots={result['storyboard_shots']}"
            )
        except Exception as error:
            print(f"[FAIL] {project_dir}: {error}")

    print(f"Imported {len(imported)} project(s).")


if __name__ == "__main__":
    main()
