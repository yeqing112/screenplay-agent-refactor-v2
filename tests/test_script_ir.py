import json
import unittest

from fastapi.testclient import TestClient

from api.server import app
from core.script_ir import build_script_ir, legacy_markdown_to_script_ir, validate_script_ir
from core.script_renderer import render_script_markdown
from models import Book, Script, ScriptIRVersion, Session, init_db


class ScriptIRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        with Session() as session:
            book = Book(title="ScriptIR test", filename="script-ir.txt", status="imported")
            session.add(book); session.flush()
            session.add(Script(book_id=book.id, episode=1, content=json.dumps({"title": "测试集", "scenes": [{"name": "门厅", "beats": [{"id": "B1", "event": "人物进入"}], "dialogues": [{"speaker": "甲", "text": "你好"}]}]}, ensure_ascii=False)))
            session.commit(); self.book_id = book.id

    def tearDown(self):
        with Session() as session:
            session.query(ScriptIRVersion).filter_by(book_id=self.book_id).delete()
            session.query(Script).filter_by(book_id=self.book_id).delete()
            session.query(Book).filter_by(id=self.book_id).delete(); session.commit()

    def test_structured_script_build_and_renderer_are_deterministic(self):
        payload = build_script_ir({"scenes": [{"name": "门厅", "beats": [{"id": "B1", "event": "进入"}]}]}, book_id=1, episode=1)
        self.assertEqual(payload["schema_version"], "script_ir_v1")
        self.assertEqual(validate_script_ir(payload)["status"], "qualified")
        markdown = render_script_markdown(payload)
        self.assertIn("## 场景 1：门厅", markdown)
        self.assertIn("进入", markdown)

    def test_build_preserves_explicit_blocking_and_props_for_downstream_gates(self):
        payload = build_script_ir({"scenes": [{
            "name": "门厅",
            "character_blocking": [{"character_id": "c1", "position": "screen_left", "facing": "screen_right", "anchor": "门边"}],
            "props": [{"prop_id": "p1", "state": "closed"}],
            "beats": [{"id": "B1", "event": "人物停下"}],
        }]}, book_id=1, episode=1)
        scene = payload["scenes"][0]
        self.assertEqual(scene["character_blocking"][0]["position"], "screen_left")
        self.assertEqual(scene["props"][0]["prop_id"], "p1")

    def test_legacy_markdown_reconstruction_requires_review(self):
        payload = legacy_markdown_to_script_ir("# 第1集\n\n## 门厅\n人物进入。", book_id=1, episode=1)
        self.assertEqual(validate_script_ir(payload)["status"], "qualified")
        self.assertEqual(payload["scenes"][0]["name"], "门厅")

    def test_validation_blocks_duplicate_scene_names(self):
        payload = build_script_ir({"scenes": [{"name": "门厅", "beats": [{"event": "进入"}]}, {"name": "门厅", "beats": [{"event": "离开"}]}]}, book_id=1, episode=1)
        report = validate_script_ir(payload)
        self.assertEqual(report["status"], "needs_review")
        self.assertTrue(any(item["code"] == "SCENE_NAME_DUPLICATE" for item in report["errors"]))

    def test_build_and_confirm_persists_version_and_current_reference(self):
        built = self.client.post(f"/api/books/{self.book_id}/episodes/1/script-ir/build", json={"persist": True})
        self.assertEqual(built.status_code, 200)
        self.assertFalse(built.json()["llm_called"])
        version_id = built.json()["persisted_draft_id"]
        confirmed = self.client.post(f"/api/books/{self.book_id}/episodes/1/script-ir/confirm", json={"versionId": version_id, "confirmed": True})
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["script_ir"]["status"], "qualified")
        with Session() as session:
            script = session.query(Script).filter_by(book_id=self.book_id, episode=1).one()
            self.assertEqual(script.current_script_ir_version_id, version_id)
            self.assertEqual(script.workflow_profile, "production")

    def test_production_director_runtime_blocks_without_qualified_script_ir(self):
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/preview", json={"workflowProfile": "production"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("qualified ScriptIR", str(response.json()["detail"]))


if __name__ == "__main__":
    unittest.main()
