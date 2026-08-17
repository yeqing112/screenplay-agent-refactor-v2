from nodes.runner import NodeRunner


def run(runner: NodeRunner) -> None:
    runner.log("Starting ingest...")
    from core.ingest import ingest
    filepath = runner.get_input("filepath")
    result = ingest(filepath)
    runner.set_output("book_id", str(result["book_id"]))
    runner.set_result({"title": result["title"], "chapters": result["chapters"]})
    runner.log(f"Ingested: {result['title']} ({result['chapters']} chapters)")
