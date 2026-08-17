"""Adapt handler — 改编方案。"""
from nodes.runner import NodeRunner


def run(runner: NodeRunner) -> None:
    runner.add_log("Starting adaptation planning...")
    from agents.adapter import AdapterAgent
    book_id = int(runner.get_input("book_id"))
    genre = runner.get_input("genre")
    agent = AdapterAgent(book_id, genre=genre)
    output = agent.run()
    runner.add_log(f"Adapt complete: {output}")

    # Return genre info
    runner.set_result({
        "genre": genre,
        "status": "completed",
    })
