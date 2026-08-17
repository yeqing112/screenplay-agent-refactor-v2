"""Props handler — 提取道具并返回列表。"""
from nodes.runner import NodeRunner


def run(runner: NodeRunner) -> None:
    runner.add_log("Starting props extraction...")
    from agents.scene_setup import SceneSetupAgent
    book_id = int(runner.get_input("book_id"))
    episode = int(runner.get_input("episode"))
    genre = runner.get_input("genre")
    agent = SceneSetupAgent(book_id, genre=genre)
    agent.run_props(episode)
    runner.add_log(f"Props complete for episode {episode}")

    # Load from DB
    from models import Session, VisualProp
    with Session() as s:
        props = (
            s.query(VisualProp)
            .filter(VisualProp.book_id == book_id)
            .all()
        )
        items = []
        for p in props:
            items.append({
                "prop_name": p.name,
                "description": p.description or "",
                "visual_prompt_zh": p.visual_prompt_zh or "",
            })
        runner.set_result(items)
        runner.add_log(f"Loaded {len(items)} props")
