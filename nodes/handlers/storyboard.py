"""Storyboard handler — 返回分镜表结构化数据。"""
import json
from nodes.runner import NodeRunner


def run(runner: NodeRunner) -> None:
    runner.add_log("Starting storyboard generation...")
    book_id = int(runner.get_input("book_id"))
    episode = int(runner.get_input("episode"))
    genre = runner.get_input("genre", "short_drama")

    runner.add_log(f"Book ID: {book_id}, Episode: {episode}")
    from agents.storyboard import StoryboardAgent

    agent = StoryboardAgent(book_id, genre=genre)
    shots = agent.run(episode)

    # Return structured result
    runner.add_log(f"Generated {len(shots)} shots across scenes")
    runner.set_result({
        "shots": shots,
        "total_shots": len(shots),
    })
