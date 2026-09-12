from core.ingest import _detect_chapters


def test_standalone_book_title_before_chapters_is_not_counted_as_a_chapter():
    chapters = _detect_chapters("《潮汐回声》\n\n第一章  雨夜\n林晚回到小镇。\n\n第二章  照相馆\n她推开门。")

    assert [title for title, _ in chapters] == ["第一章  雨夜", "第二章  照相馆"]
    assert [content for _, content in chapters] == ["林晚回到小镇。", "她推开门。"]


def test_substantive_preface_is_preserved_before_first_chapter():
    chapters = _detect_chapters("序章\n这是一段必须保留的前史。\n第一章  开始\n故事继续。")

    assert chapters[0] == ("", "序章\n这是一段必须保留的前史。")
    assert chapters[1] == ("第一章  开始", "故事继续。")

