import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import (
    Book,
    DirectorTreatment,
    Script,
    ScriptIRVersion,
    Session,
    VisualAssetPointer,
    VisualAssetVersion,
    init_db,
)


class ProductionWorkspaceProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990501
        with Session() as session:
            for model in (VisualAssetPointer, VisualAssetVersion, DirectorTreatment, ScriptIRVersion, Script):
                session.query(model).filter(model.book_id == self.book_id).delete(synchronize_session=False)
            session.query(Book).filter(Book.id == self.book_id).delete(synchronize_session=False)
            session.add(Book(id=self.book_id, title="Projection Test", filename="projection.txt", chapter_count=1, total_words=100))
            session.commit()

    def test_empty_project_is_read_only_and_exposes_next_action(self):
        before = self._counts()
        response = self.client.get(f"/api/books/{self.book_id}/production-workspace")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["authority_source"], "current_authority_pointers_only")
        self.assertEqual(payload["provider_calls"], 0)
        self.assertIn(payload["project"]["overall_state"], {"needs_action", "not_started", "blocked"})
        self.assertTrue(payload["project"]["current_blockers"])
        self.assertEqual(before, self._counts())

    def test_v2_projection_is_read_only_and_keeps_media_lanes_separate(self):
        before = self._counts()
        response = self.client.get(f"/api/books/{self.book_id}/production-workspace-v2")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "production_workspace_projection_v2")
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["authority_source"], "current_authority_pointers_only")
        self.assertTrue(payload["legacy_adopted_is_display_only"])
        self.assertNotIn("provider_calls", payload["view_contract"]["standard"])
        for shot in payload["shots"]:
            self.assertIn("IMAGE", shot)
            self.assertIn("VIDEO", shot)
            self.assertIn("next_action", shot)
            self.assertIn("asset_readiness", shot)
        self.assertEqual(before, self._counts())

    def test_latest_approved_without_pointer_does_not_become_production_truth(self):
        with Session() as session:
            script = Script(book_id=self.book_id, episode=1, content="scene", status="approved", production_status="ready")
            session.add(script)
            session.flush()
            script_ir = ScriptIRVersion(book_id=self.book_id, episode=1, revision=1, status="production_qualified", qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", payload_hash="ir-hash", payload_json='{"scenes":[{"scene_id":"scene-1"}]}')
            session.add(script_ir)
            session.flush()
            script.current_script_ir_version_id = script_ir.id
            session.add(DirectorTreatment(book_id=self.book_id, episode=1, scene_id="scene-1", scene_name="Scene 1", status="approved", production_status="ready", qualification_state="PRODUCTION_QUALIFIED"))
            session.commit()

        payload = self.client.get(f"/api/books/{self.book_id}/production-workspace").json()
        episode = payload["episodes"][0]
        self.assertEqual(episode["stages"]["SCRIPT_IR"]["state"], "complete")
        self.assertNotEqual(episode["stages"]["DIRECTOR_TREATMENT"]["state"], "complete")
        self.assertIn("DIRECTOR_TREATMENT_MISSING", episode["stages"]["DIRECTOR_TREATMENT"]["reason_codes"])

    def test_current_asset_pointer_is_reported_separately_from_reference_lock(self):
        with Session() as session:
            version = VisualAssetVersion(book_id=self.book_id, asset_key="book:990501:character:1", asset_type="character", canonical_id="1", revision=2, payload_hash="asset-hash", authority_status="SPEC_APPROVED", stale_status="FRESH")
            session.add(version)
            session.flush()
            session.add(VisualAssetPointer(book_id=self.book_id, asset_key=version.asset_key, asset_type="character", scope_key="canonical", current_version_id=version.id, payload_hash=version.payload_hash, authority_status="SPEC_APPROVED", stale_status="FRESH"))
            session.commit()

        payload = self.client.get(f"/api/books/{self.book_id}/production-workspace").json()
        episode = payload["episodes"][0]
        self.assertEqual(episode["stages"]["VISUAL_ASSET"]["state"], "complete")
        self.assertEqual(episode["stages"]["REFERENCE"]["state"], "needs_action")
        self.assertIn("REFERENCE_MISSING", episode["stages"]["REFERENCE"]["reason_codes"])

    def _counts(self):
        with Session() as session:
            return {
                "books": session.query(Book).filter_by(id=self.book_id).count(),
                "scripts": session.query(Script).filter_by(book_id=self.book_id).count(),
                "visual_versions": session.query(VisualAssetVersion).filter_by(book_id=self.book_id).count(),
                "visual_pointers": session.query(VisualAssetPointer).filter_by(book_id=self.book_id).count(),
            }


if __name__ == "__main__":
    unittest.main()
