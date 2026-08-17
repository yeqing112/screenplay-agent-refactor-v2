"""Era scan handler — 扫描时代规范。"""
from nodes.runner import NodeRunner


def run(runner: NodeRunner) -> None:
    runner.add_log("Starting era scan...")
    from agents.scene_setup import SceneSetupAgent
    from models import Session, Book
    book_id = int(runner.get_input("book_id"))
    genre = runner.get_input("genre")
    agent = SceneSetupAgent(book_id, genre=genre)
    agent.run_era_scan()
    with Session() as s:
        book = s.get(Book, book_id)
    agent.save_era_spec_output(book.title)
    runner.add_log("Era scan complete")

    # Load era spec count
    from models import Session as DB, VisualEraSpec
    with DB() as s:
        count = s.query(VisualEraSpec).filter(
            VisualEraSpec.book_id == book_id
        ).count()
        runner.set_result({"count": count, "status": "completed"})
