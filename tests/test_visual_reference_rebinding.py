import json
import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import Session, StoryboardShot, VisualMakeup, VisualReferenceAsset, init_db


class VisualReferenceRebindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990707
        with Session() as session:
            session.query(VisualReferenceAsset).filter_by(book_id=self.book_id).delete()
            session.query(StoryboardShot).filter_by(book_id=self.book_id).delete()
            session.query(VisualMakeup).filter_by(book_id=self.book_id).delete()
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(VisualReferenceAsset).filter_by(book_id=self.book_id).delete()
            session.query(StoryboardShot).filter_by(book_id=self.book_id).delete()
            session.query(VisualMakeup).filter_by(book_id=self.book_id).delete()
            session.commit()

    def _add_reference(self, asset_id, name="Hero", episode=1):
        with Session() as session:
            row = VisualReferenceAsset(
                book_id=self.book_id,
                episode=episode,
                asset_type="character",
                asset_id=str(asset_id),
                asset_name=name,
                image_url="/api/prototyping/manual-media/hero.png",
                local_path="uploads/manual-media/hero.png",
                status="locked",
                meta_info=json.dumps({"source": "test"}),
            )
            session.add(row)
            session.commit()
            return row.id

    def test_unique_dangling_reference_requires_explicit_write_and_preserves_reference(self):
        with Session() as session:
            target = VisualMakeup(book_id=self.book_id, episode=1, character_name="Hero")
            session.add(target)
            session.commit()
            target_id = target.id
        reference_id = self._add_reference(999991)
        with Session() as session:
            session.add(StoryboardShot(
                book_id=self.book_id, episode=1, shot_id=1, scene_name="Room",
                meta_info=json.dumps({"structured_shot": {
                    "character_asset_ids": ["999991"],
                    "character_blocking": [{"character_id": "999991", "visual_alias": "Hero"}],
                }}),
            ))
            session.commit()

        plan = self.client.get(f"/api/books/{self.book_id}/visual-reference-rebinding-plan")
        self.assertEqual(plan.status_code, 200, plan.text)
        payload = plan.json()
        self.assertEqual(len(payload["proposed_migrations"]), 1)
        self.assertEqual(payload["proposed_migrations"][0]["target_asset_id"], str(target_id))

        denied = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-rebinding-plan/apply",
            json={"planFingerprint": payload["plan_fingerprint"], "confirmed": True},
        )
        self.assertEqual(denied.status_code, 409)
        with Session() as session:
            self.assertEqual(session.query(VisualReferenceAsset).filter_by(id=reference_id).one().asset_id, "999991")

        applied = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-rebinding-plan/apply",
            json={"planFingerprint": payload["plan_fingerprint"], "confirmed": True, "allowWrite": True},
        )
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(applied.json()["migrated_count"], 1)
        self.assertEqual(applied.json()["affected_structured_shots"], ["1-1"])
        with Session() as session:
            reference = session.query(VisualReferenceAsset).filter_by(id=reference_id).one()
            self.assertEqual(reference.asset_id, str(target_id))
            # A legacy reference without a fingerprint cannot prove that it
            # depicts the newly bound asset, even when its name matches.
            self.assertEqual(reference.status, "stale")
            self.assertEqual(reference.image_url, "/api/prototyping/manual-media/hero.png")
            audit = json.loads(reference.meta_info)["assetRebindingAudit"]
            self.assertEqual(audit[-1]["source_asset_id"], "999991")
            self.assertEqual(audit[-1]["target_asset_id"], str(target_id))
            self.assertFalse(audit[-1]["authority_compatible"])
            shot = session.query(StoryboardShot).filter_by(book_id=self.book_id, episode=1, shot_id=1).one()
            structured = json.loads(shot.meta_info)["structured_shot"]
            self.assertEqual(structured["character_asset_ids"], [str(target_id)])
            self.assertEqual(structured["character_blocking"][0]["character_id"], str(target_id))

    def test_ambiguous_or_live_reference_is_never_auto_rebound(self):
        with Session() as session:
            one = VisualMakeup(book_id=self.book_id, episode=1, character_name="Twin")
            two = VisualMakeup(book_id=self.book_id, episode=1, character_name="Twin")
            live = VisualMakeup(book_id=self.book_id, episode=1, character_name="Live")
            session.add_all([one, two, live])
            session.commit()
            live_id = live.id
        ambiguous_reference_id = self._add_reference(999992, "Twin")
        live_reference_id = self._add_reference(live_id, "Live")

        payload = self.client.get(f"/api/books/{self.book_id}/visual-reference-rebinding-plan").json()
        self.assertEqual(payload["proposed_migrations"], [])
        self.assertEqual(len(payload["ambiguous"]), 1)
        self.assertEqual(payload["ambiguous"][0]["reference_id"], ambiguous_reference_id)
        self.assertIn(live_reference_id, payload["unchanged_reference_ids"])
