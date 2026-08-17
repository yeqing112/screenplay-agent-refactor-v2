"""Read handler — 逐章分析。"""
from nodes.runner import NodeRunner


def run(runner: NodeRunner) -> None:
    runner.add_log("Starting read analysis...")
    from agents.reader import ReaderAgent
    book_id = int(runner.get_input("book_id"))
    agent = ReaderAgent(book_id)
    output = agent.run()
    runner.add_log(f"Read complete: {output}")

    # Return chapter count
    from models import Session, Book, Chapter
    with Session() as s:
        book = s.get(Book, book_id)
        chapters = s.query(Chapter).filter(
            Chapter.book_id == book_id
        ).all()
        analyzed = sum(1 for c in chapters if c.status == "analyzed")
        runner.set_result({
            "chapters": analyzed,
            "title": book.title if book else "",
            "total_chapters": len(chapters),
        })
        runner.add_log(f"Analyzed {analyzed}/{len(chapters)} chapters")
