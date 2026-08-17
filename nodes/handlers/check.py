"""Check handler — 剧本质检，返回评分和问题列表。"""
from nodes.runner import NodeRunner


def run(runner: NodeRunner) -> None:
    runner.add_log("Starting QA check...")
    from agents.qa import QAAgent
    book_id = int(runner.get_input("book_id"))
    episode = int(runner.get_input("episode"))
    agent = QAAgent(book_id)
    result = agent.run(episode)
    runner.add_log(f"QA complete: score={result.get('overall_score')}")

    # Return the full result dict
    runner.set_result(result)
    runner.set_output("score", str(result.get("overall_score", 0)))
