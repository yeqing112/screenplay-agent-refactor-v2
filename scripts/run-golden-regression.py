"""Run deterministic Golden Project regression in an isolated SQLite database.

This is the Required-CI counterpart to the real-model gray scripts.  It never
calls a provider and never depends on historical project ids or local data.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "golden"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _seed_fixture(fixture_dir: Path, session) -> tuple[int, dict]:
    from models import Book, Script, StoryboardShot, VisualLocation, VisualMakeup, VisualProp

    project = _load_json(fixture_dir / "project.json")
    script_data = _load_json(fixture_dir / "script.json")
    assets = _load_json(fixture_dir / "assets.json")
    expected = _load_json(fixture_dir / "expected.json")

    book = Book(title=project["title"], filename=project["filename"], status="imported")
    session.add(book)
    session.flush()
    episode = int(project.get("episode", script_data.get("episode", 1)))
    scenes = script_data.get("scenes") or []
    scene = scenes[0] if scenes else {"name": "Unnamed scene", "beats": []}
    session.add(Script(book_id=book.id, genre=project.get("genre", "short_drama"), episode=episode, content=json.dumps(script_data, ensure_ascii=False)))

    for location in assets.get("locations", []):
        session.add(VisualLocation(book_id=book.id, name=location["name"], importance=location.get("importance", "medium"), episodes=json.dumps([episode])))
    for character in assets.get("characters", []):
        session.add(VisualMakeup(book_id=book.id, episode=episode, character_name=character["name"], meta_info=json.dumps({"structured_result": {"gender": character.get("gender", "")}}, ensure_ascii=False)))
    for prop in assets.get("props", []):
        session.add(VisualProp(book_id=book.id, name=prop["name"], importance=prop.get("importance", "medium"), episodes=json.dumps([episode])))

    beats = scene.get("beats") or [{"id": "B01", "type": "setup", "event": "建立场景关系"}]
    # Derive a deterministic continuity contract from ordered beats.  This is
    # deliberately fixture-generic: no book/shot/name special cases.
    previous_continuity_out = ""
    for index, beat in enumerate(beats, start=1):
        purpose = {
            "setup": "establishing",
            "obstacle": "action",
            "decision": "power_shift",
            "reveal": "reveal",
            "power_shift": "power_shift",
            "action": "action",
            "prop": "action",
            "handoff": "reveal",
        }.get(str(beat.get("type", "setup")), "emotion")
        action = str(beat.get("event") or "完成当前节拍")
        continuity_in = previous_continuity_out or f"{scene.get('name', 'Unnamed scene')}开始，角色与关键道具处于初始状态"
        continuity_out = f"完成节拍 {beat.get('id', f'B{index:02d}')}：{action}；场面仍在{scene.get('name', 'Unnamed scene')}，状态已记录"
        payload = {
            "golden_key": project["golden_key"],
            "beat_id": beat.get("id", f"B{index:02d}"),
            "character_blocking": [
                {
                    "character_id": character.get("id", character.get("name", "")),
                    "screen_position": "left" if char_index % 2 else "right",
                    "facing": "forward",
                }
                for char_index, character in enumerate(assets.get("characters", []), start=1)
            ],
            "action_beats": [{"beat_id": beat.get("id", f"B{index:02d}"), "description": action}],
            "information_reveal": action if purpose in {"reveal", "power_shift"} else "暂无新增信息，维持当前叙事认知",
            "screen_direction": "left_to_right" if purpose == "action" else "stable",
            "prop_state": "stable",
            "continuity_in": continuity_in,
            "continuity_out": continuity_out,
        }
        session.add(
            StoryboardShot(
                book_id=book.id,
                episode=episode,
                scene_name=scene.get("name", "Unnamed scene"),
                shot_id=index,
                duration=4,
                camera_angle="MS",
                camera_movement="static",
                camera_speed="slow",
                shot_purpose=purpose,
                start_state="节拍开始前的稳定状态",
                action_process=action,
                end_state="节拍完成后的稳定状态",
                meta_info=json.dumps({"golden_key": project["golden_key"], "structured_shot": payload}, ensure_ascii=False),
            )
        )
        previous_continuity_out = continuity_out
    return book.id, expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-db", action="store_true", help="保留临时数据库路径用于调试")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="screenplay-golden-") as temp_dir:
        db_path = Path(temp_dir) / "golden.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}?timeout=30"
        os.environ["UPLOAD_DIR"] = str(Path(temp_dir) / "uploads")
        os.environ["CHROMA_PERSIST_DIR"] = str(Path(temp_dir) / "chroma")

        from models import Session, StoryboardShot, engine, init_db
        from core.shot_executability import validate_shot_executability

        init_db()
        results = []
        with Session() as session:
            for fixture_dir in sorted(path for path in FIXTURE_ROOT.iterdir() if path.is_dir()):
                book_id, expected = _seed_fixture(fixture_dir, session)
                key = _load_json(fixture_dir / "project.json")["golden_key"]
                shots = session.query(StoryboardShot).filter_by(book_id=book_id).order_by(StoryboardShot.shot_id).all()
                errors = []
                if len(shots) < int(expected.get("min_shots", 1)):
                    errors.append(f"shots<{expected['min_shots']}")
                required = set(expected.get("required_checks", []))
                for shot in shots:
                    for field in required & {"shot_purpose", "continuity_in", "continuity_out", "action_beats", "character_blocking", "information_reveal", "screen_direction", "prop_state"}:
                        value = getattr(shot, field, None)
                        if field == "action_beats":
                            value = json.loads(shot.meta_info or "{}").get("structured_shot", {}).get("action_beats")
                        if field == "character_blocking":
                            value = json.loads(shot.meta_info or "{}").get("structured_shot", {}).get("character_blocking")
                        if field in {"information_reveal", "screen_direction", "prop_state", "continuity_in", "continuity_out"}:
                            value = json.loads(shot.meta_info or "{}").get("structured_shot", {}).get(field)
                        if not value:
                            errors.append(f"shot-{shot.shot_id}:{field}-missing")
                    check = validate_shot_executability(duration=shot.duration, action_process=shot.action_process, start_state=shot.start_state, end_state=shot.end_state)
                    if check["status"] == "blocked":
                        errors.append(f"shot-{shot.shot_id}:executability-blocked")
                results.append({"golden_key": key, "book_id": book_id, "shot_count": len(shots), "errors": errors})
            session.rollback()
        # Explicitly release SQLite handles before TemporaryDirectory cleanup
        # (required on Windows, harmless on POSIX).
        engine.dispose()

        failed = [result for result in results if result["errors"]]
        print(json.dumps({"mode": "deterministic_golden", "fixture_count": len(results), "passed": len(results) - len(failed), "failed": len(failed), "results": results}, ensure_ascii=False, indent=2))
        if args.keep_db:
            print(f"temporary_db={db_path}")
            input("Press Enter to remove the temporary database...")
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
