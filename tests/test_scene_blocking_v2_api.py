import hashlib
import json
import unittest

from fastapi.testclient import TestClient

from api.server import app
from core.fact_snapshot import snapshot_hash
from core.script_ir import build_script_ir, script_ir_hash
from core.source_evidence_index import build_source_evidence_index
from core.director_treatment import build_shadow_treatment
from core.director_treatment_authority import build_treatment_authority_envelope, payload_hash as treatment_payload_hash
from tests.script_fixtures import build_explicit_production_script_payload
from models import Book, DirectorTreatment, FactSnapshot, SceneBlocking, Script, ScriptIRVersion, Session, VisualLocation, init_db
from models import DirectorTreatmentAuthority, DirectorTreatmentPointer


class SceneBlockingV2ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        with Session() as session:
            # Authority rows have unique treatment_id/pointer keys.  Earlier
            # fixtures predate these tables and can leave orphan rows when a
            # SQLite id is reused; clear only this test database's authority
            # records before constructing the fixture.
            session.query(DirectorTreatmentPointer).delete(synchronize_session=False)
            session.query(DirectorTreatmentAuthority).delete(synchronize_session=False)
            session.commit()
            book = Book(title="V2 API test", filename="v2-api.txt", status="imported")
            session.add(book); session.flush()
            source = build_explicit_production_script_payload({"scenes": [{"name": "门厅", "scene_id": "E01_SC001"}]})
            content = json.dumps(source, ensure_ascii=False)
            script = Script(book_id=book.id, episode=1, content=content)
            session.add(script); session.flush()
            # Production SceneBlocking now requires an explicit locked scene
            # geometry authority; the fixture models that prerequisite instead
            # of relying on a name-only legacy location.
            session.add(VisualLocation(book_id=book.id, scene_id="E01_SC001", name="门厅", asset_status="locked", canonical_facts=json.dumps({"anchors": ["scene_center"], "zones": ["playing_area"]}, ensure_ascii=False)))
            session.flush()
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
        # Production SceneBlocking now consumes only an explicit current
        # Treatment authority pointer.  Build this fixture through the same
        # provider-free deterministic contract used by the production API.
        with Session() as session:
            script_row = session.query(Script).filter_by(book_id=self.book_id, episode=1).one()
            ir_row = session.query(ScriptIRVersion).filter_by(id=version_id).one()
            ir_payload = json.loads(ir_row.payload_json)
            scene = ir_payload["scenes"][0]
            shadow = build_shadow_treatment(scene=scene, characters=[{"id": "c1", "name": "林默"}, {"id": "c2", "name": "苏晴"}], source_script_revision=str(ir_row.revision))
            shadow["scene_id"] = scene["scene_id"]
            shadow["source_constraints"] = {"scene_identity": {"scene_id": scene["scene_id"], "scene_name": scene["name"]}, "declared_participants": [], "source_beats": shadow["beat_map"], "explicit_story_constraints": []}
            candidate_fields = ("dramatic_objective", "audience_question", "character_intents", "beat_map", "relationship_power_shift", "audience_emotion", "information_strategy", "performance_direction", "visual_strategy", "coverage_strategy", "sound_strategy", "edit_rhythm", "constraints", "unknowns")
            formal = {"scene_id": scene["scene_id"], "scene_name": scene["name"], **{field: shadow[field] for field in candidate_fields}}
            row = DirectorTreatment(book_id=self.book_id, episode=1, scene_id=scene["scene_id"], scene_name=scene["name"], revision=1, status="approved", source_script_revision=str(ir_row.revision), source_script_hash=ir_row.payload_hash, source_script_ir_version_id=ir_row.id, source_script_ir_revision=ir_row.revision, source_script_ir_hash=ir_row.payload_hash, source_script_authority_fingerprint=json.loads(ir_row.authority_envelope_json)["envelope_fingerprint"], source_fact_snapshot_id=str(snapshot_id), source_fact_snapshot_revision=snapshot.revision, source_fact_snapshot_hash=snapshot.payload_hash, dramatic_objective=formal["dramatic_objective"], audience_question=formal["audience_question"], character_intents=json.dumps(formal["character_intents"], ensure_ascii=False), beat_map=json.dumps(formal["beat_map"], ensure_ascii=False), source_constraints=json.dumps(shadow["source_constraints"], ensure_ascii=False), director_decisions=json.dumps({field: formal[field] for field in candidate_fields if field not in {"beat_map", "constraints", "unknowns"}}, ensure_ascii=False), unknown_unresolved=json.dumps(formal["unknowns"], ensure_ascii=False), relationship_power_shift=formal["relationship_power_shift"], audience_emotion=formal["audience_emotion"], information_strategy=formal["information_strategy"], performance_direction=formal["performance_direction"], visual_strategy=formal["visual_strategy"], coverage_strategy=formal["coverage_strategy"], sound_strategy=formal["sound_strategy"], edit_rhythm=formal["edit_rhythm"], constraints=json.dumps(formal["constraints"], ensure_ascii=False), unknowns=json.dumps(formal["unknowns"], ensure_ascii=False), model_info=json.dumps({"mode": "deterministic_test_fixture", "llm_called": False}), prompt_fingerprint="test-authority", payload_hash=treatment_payload_hash(formal), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", stale_reasons="[]", approved_at=__import__("datetime").datetime.now(), activated_at=__import__("datetime").datetime.now(), workflow_profile="production")
            session.add(row); session.flush()
            envelope = build_treatment_authority_envelope(treatment=formal, evidence={"book_id": self.book_id, "episode": 1, "scene": scene, "scene_id": scene["scene_id"], "scene_name": scene["name"], "characters": [], "locked_references": []}, script_ir=ir_payload, script_ir_version=ir_row, script_ir_envelope=json.loads(ir_row.authority_envelope_json), treatment_id=row.id, treatment_revision=row.revision)
            authority = DirectorTreatmentAuthority(book_id=self.book_id, episode=1, scene_id=scene["scene_id"], treatment_id=row.id, treatment_revision=1, payload_hash=row.payload_hash, envelope_fingerprint=envelope["envelope_fingerprint"], envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", stale_reasons="[]", approved_at=row.approved_at, activated_at=row.activated_at)
            session.add(authority); session.flush(); row.authority_envelope_id = authority.id
            session.add(DirectorTreatmentPointer(book_id=self.book_id, episode=1, scene_id=scene["scene_id"], treatment_id=row.id, treatment_revision=1, authority_envelope_fingerprint=envelope["envelope_fingerprint"], qualification_state="PRODUCTION_QUALIFIED"))
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(DirectorTreatmentPointer).filter_by(book_id=self.book_id).delete(synchronize_session=False)
            session.query(DirectorTreatmentAuthority).filter_by(book_id=self.book_id).delete(synchronize_session=False)
            session.query(SceneBlocking).filter_by(book_id=self.book_id).delete()
            session.query(VisualLocation).filter_by(book_id=self.book_id).delete()
            session.query(DirectorTreatmentPointer).filter_by(book_id=self.book_id).delete()
            session.query(DirectorTreatmentAuthority).filter_by(book_id=self.book_id).delete()
            session.query(DirectorTreatment).filter_by(book_id=self.book_id).delete()
            session.query(FactSnapshot).filter_by(book_id=self.book_id).delete()
            session.query(Script).filter_by(book_id=self.book_id).delete()
            session.query(ScriptIRVersion).filter_by(book_id=self.book_id).delete()
            session.query(Book).filter_by(id=self.book_id).delete(); session.commit()

    def test_production_preview_uses_v2_and_does_not_block_silent_position(self):
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True, "workflow_profile": "production", "sceneId": "E01_SC001"})
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
            payload = {"scenes": [{"name": "门厅", "scene_id": "E01_SC001", "character_blocking": [{"character": "林默", "position": "门口"}], "spatial_facts": [{"subject_id": "c1", "predicate": "position", "value": "窗边"}]}]}
            script.content = json.dumps(payload, ensure_ascii=False)
            ir = session.query(ScriptIRVersion).filter_by(book_id=self.book_id, episode=1).one()
            ir.payload_json = json.dumps(payload, ensure_ascii=False)
            session.commit()
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"workflow_profile": "production", "sceneId": "E01_SC001"})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn(response.json()["detail"]["code"], {"SCRIPT_IR_AUTHORITY_STALE", "FACT_SNAPSHOT_SOURCE_MISMATCH"})


if __name__ == "__main__":
    unittest.main()
