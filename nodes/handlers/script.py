"""Script handler — 生成剧本并返回内容。"""
from nodes.runner import NodeRunner


def run(runner: NodeRunner) -> None:
    runner.add_log("Starting script generation...")
    from agents.scriptwriter import ScriptwriterAgent
    book_id = int(runner.get_input("book_id"))
    episode = int(runner.get_input("episode"))
    genre = runner.get_input("genre")
    agent = ScriptwriterAgent(book_id, genre=genre)
    output = agent.run(episode)
    runner.add_log(f"Script complete: {output}")

    # Load actual script content from DB
    from models import Session, Script
    with Session() as s:
        script = (
            s.query(Script)
            .filter(Script.book_id == book_id, Script.episode == episode)
            .first()
        )
        if script:
            runner.set_result(script.content)
            runner.add_log(f"Loaded {len(script.content)} chars from DB")
        else:
            runner.set_result("(剧本内容未找到)")
            runner.add_log("WARNING: script not found in DB")
