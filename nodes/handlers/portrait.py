"""Portrait handler — 生成人物画像。"""
from nodes.runner import NodeRunner


def run(runner: NodeRunner) -> None:
    runner.add_log("Starting portrait generation...")
    from agents.portrait import PortraitAgent
    book_id = int(runner.get_input("book_id"))
    agent = PortraitAgent(book_id)
    output = agent.run()
    runner.add_log(f"Portrait complete: {output}")

    # Load from DB
    from models import Session, CharacterProfile
    with Session() as s:
        profiles = (
            s.query(CharacterProfile)
            .filter(CharacterProfile.book_id == book_id)
            .all()
        )
        items = []
        for p in profiles:
            items.append({
                "name": p.name,
                "visual_prompt": p.visual_prompt_zh or "",
                "core_prompt": p.core_prompt_zh or "",
            })
        runner.set_result(items)
