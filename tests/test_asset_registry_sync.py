import json

from core.asset_registry_sync import sync_assets_from_script_ir
from models import Book, Session, VisualLocation, VisualMakeup, VisualProp, init_db


def test_sync_creates_canonical_cards_idempotently():
    init_db()
    with Session() as session:
        book = Book(title="registry", filename="registry.txt", status="imported"); session.add(book); session.flush()
        payload = {"scenes": [{"scene_id": "E01_SC001", "name": "门厅", "time_of_day": "夜", "asset_mentions": [{"name": "旧照片"}]}], "characters": [{"character_id": "c1", "name": "林晚", "gender": "female"}]}
        first = sync_assets_from_script_ir(session, payload, book_id=book.id, episode=1, source_fingerprint="fp")
        session.commit()
        second = sync_assets_from_script_ir(session, payload, book_id=book.id, episode=1, source_fingerprint="fp")
        session.commit()
        assert first["created"] == {"scene": 1, "character": 1, "prop": 1}
        assert second["created"] == {"scene": 0, "character": 0, "prop": 0}
        assert session.query(VisualLocation).filter_by(book_id=book.id).count() == 1
        assert session.query(VisualMakeup).filter_by(book_id=book.id).count() == 1
        assert session.query(VisualProp).filter_by(book_id=book.id).count() == 1
        session.query(VisualMakeup).filter_by(book_id=book.id).delete(); session.query(VisualLocation).filter_by(book_id=book.id).delete(); session.query(VisualProp).filter_by(book_id=book.id).delete(); session.query(Book).filter_by(id=book.id).delete(); session.commit()

