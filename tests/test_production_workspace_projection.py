import unittest
from unittest.mock import patch
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.server import app
import core.production_workspace_projection_v2 as projection_v2
from core.production_workspace_projection_v2 import build_production_workspace_projection_v2
from core.production_workspace_projection_v2 import _official_projection
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


def _projection_lane(*, policy_mode: str, official_current: bool = False):
    official = {
        "current": official_current,
        "currentness": "current" if official_current else "missing",
        "version": {"id": "omv-image", "revision": 1, "media_type": "IMAGE", "storage_identity": "https://example.invalid/media", "checksum": "sha", "mime": "image/png", "width": 1, "height": 1, "duration_ms": None, "candidate_id": "candidate", "validation_id": "validation"} if official_current else None,
        "authority": None,
        "pointer": None,
        "preview": None,
        "preview_url": None,
    }
    return {
        "prompt_ir": {"current": True, "version": 1, "stale": False, "state": "complete", "payload_hash": "prompt", "generation_policy": {"mode": policy_mode, "target_media": "VIDEO"}},
        "generation_mode": None,
        "source_official_image": None,
        "model": {"selected_profile_id": "profile", "provider": None, "model_name": None, "last_execution_profile_id": None, "last_execution_model": None},
        "latest_execution": None,
        "candidates": {"count": 0, "latest": None, "items": []},
        "official": official,
    }


def test_v2_video_mode_comes_from_current_prompt_ir_even_when_official_image_exists():
    base = {"project": {"overall_progress": 0, "overall_state": "ready", "current_blockers": [], "next_actions": []}, "stages": {}, "episodes": [], "shots": [{"episode": 1, "shot_id": "1", "storyboard_shot_id": 7, "plan_shot_id": "P7", "scene_id": "S1", "duration": 1, "camera": {}, "action": ""}], "assets": []}
    image_lane = _projection_lane(policy_mode="TEXT_TO_IMAGE", official_current=True)
    video_lane = _projection_lane(policy_mode="TEXT_TO_VIDEO")
    with patch.object(projection_v2, "build_production_workspace_projection", return_value=base), \
        patch.object(projection_v2, "_asset_readiness", return_value={"state": "ready", "required": {}, "required_entities": [], "missing": [], "stale": [], "current": True, "required_entity_count": 0, "requirement_source": "test"}), \
        patch.object(projection_v2, "_asset_projection", return_value=[]), \
        patch.object(projection_v2, "_lane", side_effect=[image_lane, video_lane]):
        payload = build_production_workspace_projection_v2(object(), book_id=77, generation_profile_selection={"IMAGE": "image", "VIDEO": "video"})
    shot = payload["shots"][0]
    assert shot["IMAGE"]["official"]["current"] is True
    assert shot["VIDEO"]["generation_mode"] == "TEXT_TO_VIDEO"
    assert shot["VIDEO"]["source_official_image"] is None


def test_v2_image_to_video_without_current_official_image_is_blocked():
    base = {"project": {"overall_progress": 0, "overall_state": "ready", "current_blockers": [], "next_actions": []}, "stages": {}, "episodes": [], "shots": [{"episode": 1, "shot_id": "1", "storyboard_shot_id": 7, "plan_shot_id": "P7", "scene_id": "S1", "duration": 1, "camera": {}, "action": ""}], "assets": []}
    image_lane = _projection_lane(policy_mode="TEXT_TO_IMAGE", official_current=False)
    video_lane = _projection_lane(policy_mode="IMAGE_TO_VIDEO")
    with patch.object(projection_v2, "build_production_workspace_projection", return_value=base), \
        patch.object(projection_v2, "_asset_readiness", return_value={"state": "ready", "required": {}, "required_entities": [], "missing": [], "stale": [], "current": True, "required_entity_count": 0, "requirement_source": "test"}), \
        patch.object(projection_v2, "_asset_projection", return_value=[]), \
        patch.object(projection_v2, "_lane", side_effect=[image_lane, video_lane]):
        payload = build_production_workspace_projection_v2(object(), book_id=77, generation_profile_selection={"IMAGE": "image", "VIDEO": "video"})
    shot = payload["shots"][0]
    assert shot["VIDEO"]["generation_mode"] == "IMAGE_TO_VIDEO"
    assert shot["VIDEO"]["source_official_image"] is None
    assert "OFFICIAL_IMAGE_REQUIRED" in shot["VIDEO"]["generation_readiness"]["reason_codes"]


class _ProjectionQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter_by(self, **filters):
        self.rows = [row for row in self.rows if all(getattr(row, key, None) == value for key, value in filters.items())]
        return self

    def first(self):
        return self.rows[0] if self.rows else None


class _ProjectionSession:
    def __init__(self, *, pointers=(), versions=(), authorities=()):
        self.rows = {
            "OfficialMediaPointer": list(pointers),
            "OfficialMediaVersion": list(versions),
            "OfficialMediaAuthority": list(authorities),
        }

    def query(self, model):
        return _ProjectionQuery(self.rows.get(model.__name__, []))


def test_v2_official_currentness_marks_current_status_obsolete_after_prompt_pointer_moves():
    pointer = SimpleNamespace(id=1, authority_id="oma-1", fingerprint="pointer-fp", official_media_version_id="omv-1", book_id=77, episode=1, storyboard_shot_id=7, media_role="SHOT_PRIMARY_IMAGE")
    version = SimpleNamespace(official_media_version_id="omv-1", prompt_ir_version_id=1, prompt_ir_payload_hash="old-hash", status="CURRENT", revision=1, media_type="IMAGE", storage_identity="https://example.invalid/image.png", checksum_sha256="sha", mime_type="image/png", width=1, height=1, duration_ms=None, candidate_id="candidate-1", validation_id="validation-1")
    authority = SimpleNamespace(authority_id="oma-1", official_media_version_id="omv-1", status="CURRENT", payload_hash="payload", lineage_hash="lineage", authority_envelope_json="{}")
    session = _ProjectionSession(pointers=[pointer], versions=[version], authorities=[authority])
    with patch("core.media_authority.resolve_current_official_media_for_shot", side_effect=RuntimeError("prompt pointer moved")), \
        patch.object(projection_v2, "_prompt_lane", return_value={"current": True, "version": 2, "payload_hash": "new-hash", "generation_policy": {}, "stale": False, "state": "complete", "reason_codes": []}):
        result = _official_projection(session, shot={"book_id": 77, "episode": 1, "storyboard_shot_id": 7}, target_media="IMAGE")
    assert result["current"] is False
    assert result["currentness"] == "obsolete"


if __name__ == "__main__":
    unittest.main()
