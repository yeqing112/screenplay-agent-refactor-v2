import hashlib
import json
import unittest

from fastapi.testclient import TestClient

from api.server import app
from core.fact_snapshot import snapshot_hash
from core.script_ir import build_script_ir, script_ir_hash
from core.source_evidence_index import build_source_evidence_index
from models import Book, DirectorTreatment, FactSnapshot, SceneBlocking, Script, ScriptIRVersion, Session, init_db


class SceneBlockingV2ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        with Session() as session:
            book = Book(title="V2 API test", filename="v2-api.txt", status="imported")
            session.add(book); session.flush()
            source = {"scenes": [{"name": "门厅"}]}
            content = json.dumps(source, ensure_ascii=False)
            script = Script(book_id=book.id, episode=1, content=content)
            session.add(script); session.flush()
            raw_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            records = [
                {"fact_key": "episode|scenes|scene_existence|episode", "predicate": "scene_existence", "subject_id": "episode", "value": {"minimum": 1, "actual": 1}, "status": "confirmed", "evidence": [{"anchor_ref": "E0001"}]},
                {"fact_key": "scene|门厅|scene_identity|scene", "predicate": "scene_identity", "subject_id": "门厅", "value": "门厅", "status": "confirmed", "evidence": [{"anchor_ref": "E0001"}]},
            ]
            snapshot = FactSnapshot(book_id=book.id, episode=1, revision=1, status="confirmed", source_fingerprint=raw_hash, payload_hash=snapshot_hash(records), records_json=json.dumps(records, ensure_ascii=False), validation_report=json.dumps({"fact_coverage": {"status": "FACT_COVERAGE_SUFFICIENT"}}))
            session.add(snapshot); session.flush()
            payload = build_script_ir(source, book_id=book.id, episode=1, fact_snapshot_id=str(snapshot.id))
            ir = ScriptIRVersion(book_id=book.id, episode=1, revision=1, status="draft", payload_json=json.dumps(payload, ensure_ascii=False), payload_hash=script_ir_hash(payload), validation_status="qualified", source_fact_snapshot_id=str(snapshot.id), source_fingerprint=raw_hash)
            session.add(ir); session.flush(); script.current_script_ir_version_id = ir.id
            session.add(DirectorTreatment(book_id=book.id, episode=1, scene_name="门厅", status="approved", revision=1, character_intents=json.dumps({"c1": {"name": "林默"}, "c2": {"name": "苏晴"}}), beat_map=json.dumps([{"beat_id": "B01", "event": "两人对视"}]), prompt_fingerprint="tp"))
            session.commit(); self.book_id = book.id; version_id = ir.id; snapshot_id = snapshot.id
        source_index = build_source_evidence_index(content.encode("utf-8"), source_package_id="V2_TEST", source_version_id="V2_TEST:V01", source_raw_hash=raw_hash)
        activated = self.client.post(f"/api/books/{self.book_id}/episodes/1/script-ir/activate", json={
            "versionId": version_id, "confirmed": True, "factSnapshotId": snapshot_id,
            "sourcePackageId": "V2_TEST", "sourceVersionId": "V2_TEST:V01", "immutableSourceRawHash": raw_hash,
            "sourceEvidenceIndex": source_index,
            "sourceAnchorBindings": {"episode|scenes|scene_existence|episode": ["E0001"], "scene|门厅|scene_identity|scene": ["E0001"]},
            "sourceStructure": source,
        })
        self.assertEqual(activated.status_code, 200, activated.text)

    def tearDown(self):
        with Session() as session:
            session.query(SceneBlocking).filter_by(book_id=self.book_id).delete()
            session.query(DirectorTreatment).filter_by(book_id=self.book_id).delete()
            session.query(FactSnapshot).filter_by(book_id=self.book_id).delete()
            session.query(Script).filter_by(book_id=self.book_id).delete()
            session.query(ScriptIRVersion).filter_by(book_id=self.book_id).delete()
            session.query(Book).filter_by(id=self.book_id).delete(); session.commit()

    def test_production_preview_uses_v2_and_does_not_block_silent_position(self):
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True, "workflow_profile": "production"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse(body["llm_called"])
        self.assertEqual(body["blocking"]["schema_version"], "scene_blocking_v2")
        self.assertEqual(body["blocking"]["unknowns"], [])
        self.assertEqual(body["blocking"]["status"], "ready_for_review")
        draft_id = body["persisted_draft_id"]
        confirm = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/confirm", json={"blockingId": draft_id, "evidenceFingerprint": body["blocking"]["evidence_fingerprint"], "confirmed": True, "workflow_profile": "production", "schema_version": "scene_blocking_v2"})
        self.assertEqual(confirm.status_code, 200, confirm.text)
        self.assertEqual(confirm.json()["scene_blocking"]["schema_version"], "scene_blocking_v2")

    def test_production_preview_keeps_fact_conflict_blocked(self):
        with Session() as session:
            script = session.query(Script).filter_by(book_id=self.book_id, episode=1).one()
            payload = {"scenes": [{"name": "门厅", "character_blocking": [{"character": "林默", "position": "门口"}], "spatial_facts": [{"subject_id": "c1", "predicate": "position", "value": "窗边"}]}]}
            script.content = json.dumps(payload, ensure_ascii=False)
            ir = session.query(ScriptIRVersion).filter_by(book_id=self.book_id, episode=1).one()
            ir.payload_json = json.dumps(payload, ensure_ascii=False)
            session.commit()
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"workflow_profile": "production"})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn(response.json()["detail"]["code"], {"SCRIPT_IR_AUTHORITY_STALE", "FACT_SNAPSHOT_SOURCE_MISMATCH"})


if __name__ == "__main__":
    unittest.main()
