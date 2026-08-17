"""Makeup handler — 定妆照，返回角色列表。"""
from nodes.runner import NodeRunner


def run(runner: NodeRunner) -> None:
    runner.add_log("Starting makeup...")
    from agents.scene_setup import SceneSetupAgent
    book_id = int(runner.get_input("book_id"))
    episode = int(runner.get_input("episode"))
    genre = runner.get_input("genre")
    agent = SceneSetupAgent(book_id, genre=genre)
    agent.run_makeup(episode)
    runner.add_log(f"Makeup complete for episode {episode}")

    # Load from DB
    from models import Session, VisualMakeup
    with Session() as s:
        makeups = (
            s.query(VisualMakeup)
            .filter(VisualMakeup.book_id == book_id, VisualMakeup.episode == episode)
            .all()
        )
        items = []
        for m in makeups:
            items.append({
                "name": m.character_name,
                "core_prompt_zh": m.core_prompt_zh or "",
                "visual_prompt_zh": m.visual_prompt_zh or "",
            })
        runner.set_result(items)
        runner.add_log(f"Loaded {len(items)} makeups")
