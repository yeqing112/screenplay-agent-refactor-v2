from nodes.runner import NodeRunner


def run(runner: NodeRunner) -> None:
    runner.log("Starting rewrite...")
    from agents.rewrite import RewriteAgent
    book_id = int(runner.get_input("book_id"))
    episode = int(runner.get_input("episode"))
    agent = RewriteAgent(book_id)
    output = agent.run(episode)
    runner.log(f"Rewrite complete: {output}")
