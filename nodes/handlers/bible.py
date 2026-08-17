"""Bible handler — 生成小说圣经。"""
from nodes.runner import NodeRunner


def run(runner: NodeRunner) -> None:
    runner.add_log("Starting bible generation...")
    from agents.bible import BibleAgent
    book_id = int(runner.get_input("book_id"))
    agent = BibleAgent(book_id)
    output = agent.run()
    runner.add_log(f"Bible complete: {output}")

    # Return bible content info
    from models import Session, BookBible
    with Session() as s:
        bible = (
            s.query(BookBible)
            .filter(BookBible.book_id == book_id)
            .first()
        )
        if bible and bible.content:
            runner.set_result({
                "content_length": len(bible.content),
                "preview": bible.content[:500],
            })
        else:
            runner.set_result({"status": "completed"})
