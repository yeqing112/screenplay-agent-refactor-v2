"""Storyboard handler — 返回分镜表结构化数据。"""
import json
from nodes.runner import NodeRunner


def run(runner: NodeRunner) -> None:
    runner.add_log("Starting storyboard generation...")
    book_id = int(runner.get_input("book_id"))
    episode = int(runner.get_input("episode"))
    genre = runner.get_input("genre", "short_drama")
    generation_mode = str(runner.get_input("generation_mode", "director_llm") or "director_llm").strip().lower()
    if generation_mode not in {"director_llm", "deterministic_safe"}:
        raise ValueError("generation_mode must be director_llm or deterministic_safe")

    runner.add_log(f"Book ID: {book_id}, Episode: {episode}")
    from agents.storyboard import StoryboardAgent

    agent = StoryboardAgent(book_id, genre=genre, force_llm=generation_mode == "director_llm")
    shots = agent.run(episode)

    # Return structured result
    runner.add_log(f"Generated {len(shots)} shots across scenes")
    runner.set_result({
        "shots": shots,
        "total_shots": len(shots),
    })
