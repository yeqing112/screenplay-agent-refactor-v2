"""Outline handler — 生成分集大纲并返回结构化数据。"""
from nodes.runner import NodeRunner


def run(runner: NodeRunner) -> None:
    runner.add_log("Starting outline generation...")
    from agents.outline import OutlineAgent
    book_id = int(runner.get_input("book_id"))
    runner.add_log(f"Book ID: {book_id}")
    agent = OutlineAgent(book_id)
    output = agent.run()
    runner.set_meta("output_path", output)
    runner.add_log(f"Outline complete: {output}")

    # Load actual result from DB for display
    from models import Session, EpisodeOutline
    with Session() as s:
        outlines = (
            s.query(EpisodeOutline)
            .filter(EpisodeOutline.book_id == book_id)
            .order_by(EpisodeOutline.episode)
            .all()
        )
        episodes = []
        for o in outlines:
            episodes.append({
                "episode": o.episode,
                "title": o.title,
                "summary": o.core_event[:200] if o.core_event else '',
            })
        runner.set_result({
            "episodes": episodes,
            "total_episodes": len(episodes),
        })
        runner.add_log(f"Loaded {len(episodes)} episodes from DB")
