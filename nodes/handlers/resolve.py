from nodes.runner import NodeRunner
import threading

def run(runner: NodeRunner) -> None:
    runner.add_log("Starting alias resolution...")
    from core.alias_resolver import resolve_aliases
    from models import Session
    book_id = int(runner.get_input("book_id"))
    with Session() as s:
        resolve_aliases(book_id, s)
    runner.add_log("Alias resolution complete")
