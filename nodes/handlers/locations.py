"""Locations handler — 提取场景并返回列表。"""
from nodes.runner import NodeRunner


def run(runner: NodeRunner) -> None:
    runner.add_log("Starting locations extraction...")
    from agents.scene_setup import SceneSetupAgent
    book_id = int(runner.get_input("book_id"))
    episode = int(runner.get_input("episode"))
    genre = runner.get_input("genre")
    agent = SceneSetupAgent(book_id, genre=genre)
    agent.run_locations(episode)
    runner.add_log(f"Locations complete for episode {episode}")

    # Load from DB
    from models import Session, VisualLocation
    with Session() as s:
        locs = (
            s.query(VisualLocation)
            .filter(VisualLocation.book_id == book_id)
            .all()
        )
        items = []
        for loc in locs:
            items.append({
                "name": loc.name,
                "description": loc.description or "",
                "visual_prompt_zh": loc.visual_prompt_zh or loc.core_prompt_zh or "",
            })
        runner.set_result(items)
        runner.add_log(f"Loaded {len(items)} locations")
