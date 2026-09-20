"""Production SceneBlocking authority contract regression tests (provider-free)."""
import hashlib
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from core.director_treatment import build_shadow_treatment
from core.director_semantics import build_suggested_director_decisions, DIRECTOR_CONTRACT_VERSION
from core.director_treatment_authority import build_treatment_authority_envelope, payload_hash as treatment_payload_hash, _envelope_fingerprint
from core.fact_snapshot import snapshot_hash
from core.scene_blocking_authority import (
    BLOCKING_AUTHORING_DECISION,
    DERIVED_SPATIAL_CONSTRAINT,
    SOURCE_SPATIAL_CONSTRAINT,
    blocking_payload_hash,
    classify_scene_asset,
    initialize_continuity_state,
    scene_blocking_contract,
    validate_scene_blocking_candidate_authority,
)
from core.script_ir import build_script_ir, script_ir_hash
from core.source_evidence_index import build_source_evidence_index
from tests.script_fixtures import build_explicit_production_script_payload
from models import (
    Book,
    DirectorTreatment,
    DirectorTreatmentAuthority,
    DirectorTreatmentPointer,
    FactSnapshot,
    SceneBlocking,
    SceneBlockingAuthority,
    SceneBlockingPointer,
    ShotPlan,
    ShotPlanAuthority,
    ShotPlanPointer,
    StoryboardShot,
    StoryboardMaterializationSet,
    Script,
    ScriptIRVersion,
    Session,
    VisualLocation,
    init_db,
)
from tests.phase_b_contract_fixtures import build_phase_b_production_blocking_candidate, build_phase_b_production_director_provenance


class SceneBlockingAuthorityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        with Session() as session:
            book = Book(title="SceneBlocking authority test", filename="scene-blocking-authority.txt", status="imported")
            session.add(book); session.flush()
            source = build_explicit_production_script_payload({"scenes": [{"name": "门厅", "scene_id": "E01_SC001", "participants": [{"character_id": "c1"}, {"character_id": "c2"}], "beats": [{"beat_id": "B01", "type": "setup", "event": "两人对视"}], "spatial_facts": [{"subject_id": "c1", "predicate": "anchor", "value": "门口"}], "required_anchors": ["门口"]}]})
            content = json.dumps(source, ensure_ascii=False)
            script = Script(book_id=book.id, episode=1, content=content)
            session.add(script); session.flush()
            raw_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            records = [{"fact_key": "episode|scenes|scene_existence|episode", "predicate": "scene_existence", "subject_id": "episode", "value": {"minimum": 1, "actual": 1}, "status": "confirmed", "evidence": [{"anchor_ref": "E0001"}]}, {"fact_key": "scene|门厅|scene_identity|scene", "predicate": "scene_identity", "subject_id": "门厅", "value": "门厅", "status": "confirmed", "evidence": [{"anchor_ref": "E0001"}]}]
            snapshot = FactSnapshot(book_id=book.id, episode=1, revision=1, status="confirmed", source_fingerprint=raw_hash, payload_hash=snapshot_hash(records), records_json=json.dumps(records, ensure_ascii=False), validation_report=json.dumps({"fact_coverage": {"status": "FACT_COVERAGE_SUFFICIENT"}}))
            session.add(snapshot); session.flush()
            ir_payload = build_script_ir(source, book_id=book.id, episode=1, fact_snapshot_id=str(snapshot.id))
            ir = ScriptIRVersion(book_id=book.id, episode=1, revision=1, status="draft", payload_json=json.dumps(ir_payload, ensure_ascii=False), payload_hash=script_ir_hash(ir_payload), validation_status="qualified", source_fact_snapshot_id=str(snapshot.id), source_fingerprint=raw_hash)
            session.add(ir); session.flush(); script.current_script_ir_version_id = ir.id
            session.add(VisualLocation(book_id=book.id, scene_id="E01_SC001", name="门厅", asset_status="locked", canonical_facts=json.dumps({"anchors": ["门口"], "zones": ["playing_area"]}, ensure_ascii=False)))
            session.commit(); self.book_id, version_id, snapshot_id = book.id, ir.id, snapshot.id
        source_index = build_source_evidence_index(content.encode("utf-8"), source_package_id="SB_AUTH", source_version_id="SB_AUTH:V01", source_raw_hash=raw_hash)
        activated = self.client.post(f"/api/books/{self.book_id}/episodes/1/script-ir/activate", json={"versionId": version_id, "confirmed": True, "factSnapshotId": snapshot_id, "sourcePackageId": "SB_AUTH", "sourceVersionId": "SB_AUTH:V01", "immutableSourceRawHash": raw_hash, "sourceEvidenceIndex": source_index, "sourceAnchorBindings": {"episode|scenes|scene_existence|episode": ["E0001"], "scene|门厅|scene_identity|scene": ["E0001"]}, "sourceStructure": source})
        self.assertEqual(activated.status_code, 200, activated.text)
        with Session() as session:
            script_row = session.query(Script).filter_by(book_id=self.book_id, episode=1).one(); ir_row = session.query(ScriptIRVersion).filter_by(id=version_id).one(); fact = session.query(FactSnapshot).filter_by(id=snapshot_id).one(); scene = json.loads(ir_row.payload_json)["scenes"][0]
            shadow = build_shadow_treatment(scene=scene, characters=[{"id": "c1", "name": "林默"}, {"id": "c2", "name": "苏晴"}], source_script_revision=str(ir_row.revision))
            formal = {"scene_id": scene["scene_id"], "scene_name": scene["name"], **{field: shadow[field] for field in ("dramatic_objective", "audience_question", "character_intents", "beat_map", "relationship_power_shift", "audience_emotion", "information_strategy", "performance_direction", "visual_strategy", "coverage_strategy", "sound_strategy", "edit_rhythm", "constraints", "unknowns")}}
            formal["director_contract_version"] = DIRECTOR_CONTRACT_VERSION
            formal["director_beat_decisions"] = build_suggested_director_decisions(scene)
            provenance, confirmation, canonical_origin = build_phase_b_production_director_provenance()
            # Some repository-wide legacy tests intentionally recycle SQLite
            # primary keys after cleanup.  Use a deterministic book-scoped id
            # here so the authority table's global unique(treatment_id)
            # constraint cannot collide with an unrelated fixture.
            row = DirectorTreatment(id=self.book_id * 100 + 1, book_id=self.book_id, episode=1, scene_id=scene["scene_id"], scene_name=scene["name"], revision=1, status="approved", source_script_revision="1", source_script_hash=ir_row.payload_hash, source_script_ir_version_id=ir_row.id, source_script_ir_revision=ir_row.revision, source_script_ir_hash=ir_row.payload_hash, source_script_authority_fingerprint=json.loads(ir_row.authority_envelope_json)["envelope_fingerprint"], source_fact_snapshot_id=str(fact.id), source_fact_snapshot_revision=fact.revision, source_fact_snapshot_hash=fact.payload_hash, dramatic_objective=formal["dramatic_objective"], audience_question=formal["audience_question"], character_intents=json.dumps(formal["character_intents"], ensure_ascii=False), beat_map=json.dumps(formal["beat_map"], ensure_ascii=False), source_constraints=json.dumps({"scene_identity": {"scene_id": scene["scene_id"], "scene_name": scene["name"]}, "declared_participants": scene.get("participants", []), "source_beats": formal["beat_map"]}, ensure_ascii=False), director_decisions=json.dumps({"director_contract_version": formal["director_contract_version"], "director_beat_decisions": formal["director_beat_decisions"]}, ensure_ascii=False), unknown_unresolved=json.dumps(formal["unknowns"], ensure_ascii=False), relationship_power_shift=formal["relationship_power_shift"], audience_emotion=formal["audience_emotion"], information_strategy=formal["information_strategy"], performance_direction=formal["performance_direction"], visual_strategy=formal["visual_strategy"], coverage_strategy=formal["coverage_strategy"], sound_strategy=formal["sound_strategy"], edit_rhythm=formal["edit_rhythm"], constraints=json.dumps(formal["constraints"], ensure_ascii=False), unknowns=json.dumps(formal["unknowns"], ensure_ascii=False), model_info=json.dumps({"mode": "test", "proposal_provenance": provenance, "confirmation_event": confirmation, "canonical_origin": canonical_origin, "llm_called": False, "llm_generated": False}), prompt_fingerprint="sb-auth-treatment", payload_hash=treatment_payload_hash(formal), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", stale_reasons="[]", workflow_profile="production")
            session.add(row); session.flush()
            treatment_envelope = build_treatment_authority_envelope(treatment=formal, evidence={"book_id": self.book_id, "episode": 1, "scene": scene, "scene_id": scene["scene_id"], "scene_name": scene["name"], "characters": [], "locked_references": []}, script_ir=json.loads(ir_row.payload_json), script_ir_version=ir_row, script_ir_envelope=json.loads(ir_row.authority_envelope_json), treatment_id=row.id, treatment_revision=1, provenance=provenance, confirmation=confirmation, canonical_origin=canonical_origin)
            authority = DirectorTreatmentAuthority(book_id=self.book_id, episode=1, scene_id=scene["scene_id"], treatment_id=row.id, treatment_revision=1, payload_hash=row.payload_hash, envelope_fingerprint=treatment_envelope["envelope_fingerprint"], envelope_json=json.dumps(treatment_envelope, ensure_ascii=False), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", stale_reasons="[]")
            session.add(authority); session.flush(); row.authority_envelope_id = authority.id; session.add(DirectorTreatmentPointer(book_id=self.book_id, episode=1, scene_id=scene["scene_id"], treatment_id=row.id, treatment_revision=1, authority_envelope_fingerprint=treatment_envelope["envelope_fingerprint"], qualification_state="PRODUCTION_QUALIFIED")); session.commit()

    def tearDown(self):
        with Session() as session:
            for model in (StoryboardShot, ShotPlanPointer, ShotPlanAuthority, ShotPlan, SceneBlockingPointer, SceneBlockingAuthority, SceneBlocking, DirectorTreatmentPointer, DirectorTreatmentAuthority, DirectorTreatment, VisualLocation, FactSnapshot, ScriptIRVersion, Script):
                session.query(model).filter_by(book_id=self.book_id).delete(synchronize_session=False)
            session.query(Book).filter_by(id=self.book_id).delete(synchronize_session=False); session.commit()

    def test_contract_classifies_authority_layers(self):
        contract = scene_blocking_contract()
        self.assertEqual(contract["schema_version"], "scene_blocking_authority_contract_v1")
        self.assertIn("participants", contract["blocking_authoring_fields"])
        self.assertIn("source_spatial_facts", contract["source_spatial_fields"])
        self.assertIn("continuity_state", contract["derived_constraint_fields"])

    def test_locked_scene_asset_and_continuity_have_provenance(self):
        with Session() as session:
            location = session.query(VisualLocation).filter_by(book_id=self.book_id).one()
            classified = classify_scene_asset(location, scene_id="E01_SC001")
            self.assertEqual(classified["authority_class"], "LOCKED_PRODUCTION_CONSTRAINT")
            state = initialize_continuity_state(scene={"scene_id": "E01_SC001", "participants": ["c1"], "character_states": {"c1": "警觉"}}, treatment={"character_intents": {"c1": {"name": "林默"}}})
            self.assertEqual(state["states"][0]["authority_class"], SOURCE_SPATIAL_CONSTRAINT)
            self.assertEqual(state["states"][0]["state"], "警觉")

    def test_name_only_locked_scene_asset_is_advisory(self):
        """Legacy rows without scene_id must not become production authority."""
        with Session() as session:
            location = VisualLocation(
                book_id=self.book_id,
                scene_id="",
                name="门厅",
                asset_status="locked",
                canonical_facts=json.dumps({"anchors": ["门口"]}, ensure_ascii=False),
            )
            session.add(location); session.commit(); session.refresh(location)
            classified = classify_scene_asset(location, scene_id="E01_SC001")
            self.assertEqual(classified["authority_class"], "ADVISORY_SCENE_CONTEXT")
            self.assertEqual(classified["status"], "identity_mismatch")
            self.assertFalse(classified["locked_constraints"])

    def test_locked_asset_fingerprint_covers_non_geometry_inputs(self):
        with Session() as session:
            location = session.query(VisualLocation).filter_by(book_id=self.book_id).one()
            before = classify_scene_asset(location, scene_id="E01_SC001")["fingerprint"]
            location.key_props = json.dumps(["收银台"], ensure_ascii=False)
            session.commit(); session.refresh(location)
            after = classify_scene_asset(location, scene_id="E01_SC001")["fingerprint"]
            self.assertNotEqual(before, after)

    def test_production_preview_confirm_and_shot_plan_use_explicit_pointer(self):
        treatment_readable = self.client.get(f"/api/books/{self.book_id}/episodes/1/director-treatment/authority/E01_SC001")
        self.assertEqual(treatment_readable.status_code, 200, treatment_readable.text)
        self.assertTrue(treatment_readable.json()["phase_b_semantic_ready"])
        preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True, "workflowProfile": "production", "sceneId": "E01_SC001"})
        self.assertEqual(preview.status_code, 200, preview.text)
        body = preview.json(); self.assertFalse(body["llm_called"]); self.assertEqual(body["blocking"]["production_blockers"], [])
        confirm = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/confirm", json={"blockingId": body["persisted_draft_id"], "evidenceFingerprint": body["blocking"]["evidence_fingerprint"], "confirmed": True, "workflowProfile": "production", "schemaVersion": "scene_blocking_v2", "blocking": build_phase_b_production_blocking_candidate(body["blocking"])})
        self.assertEqual(confirm.status_code, 200, confirm.text)
        approved = confirm.json()["scene_blocking"]
        self.assertEqual(approved["qualification_state"], "PRODUCTION_QUALIFIED"); self.assertEqual(approved["production_status"], "ready"); self.assertTrue(confirm.json()["authority_envelope"]["envelope_fingerprint"])
        # Replaying an identical preview must create/reuse an open candidate,
        # never return the superseded draft that was just finalized.
        replay = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True, "workflowProfile": "production", "sceneId": "E01_SC001"})
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertNotEqual(replay.json()["persisted_draft_id"], approved["id"])
        plan = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/preview", json={"workflowProfile": "production", "sceneId": "E01_SC001"})
        self.assertEqual(plan.status_code, 200, plan.text)

    def test_legacy_semantic_authority_without_provenance_is_readable_but_blocks_production(self):
        with Session() as session:
            authority = session.query(DirectorTreatmentAuthority).filter_by(book_id=self.book_id, scene_id="E01_SC001").one()
            pointer = session.query(DirectorTreatmentPointer).filter_by(book_id=self.book_id, scene_id="E01_SC001").one()
            treatment = session.query(DirectorTreatment).filter_by(id=authority.treatment_id).one()
            envelope = json.loads(authority.envelope_json)
            for field in ("proposal_provenance", "confirmation_event", "canonical_origin_summary", "provider_provenance"):
                envelope.pop(field, None)
            envelope.pop("provenance", None)
            authority.envelope_fingerprint = _envelope_fingerprint(envelope)
            authority.envelope_json = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
            pointer.authority_envelope_fingerprint = authority.envelope_fingerprint
            treatment.model_info = json.dumps({"mode": "legacy_semantic_fixture", "llm_called": False, "llm_generated": False}, ensure_ascii=False)
            session.commit()
        readable = self.client.get(f"/api/books/{self.book_id}/episodes/1/director-treatment/authority/E01_SC001")
        self.assertEqual(readable.status_code, 200, readable.text)
        body = readable.json()
        self.assertFalse(body["phase_b_semantic_ready"])
        self.assertEqual(body["authority_envelope"]["phase_b_readiness_reasons"], ["DIRECTOR_PROVENANCE_CONTRACT_MISSING"])
        blocked = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True, "workflowProfile": "production", "sceneId": "E01_SC001"})
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["detail"]["code"], "DIRECTOR_TREATMENT_SEMANTIC_NOT_READY")

    def test_shot_plan_blocks_legacy_semantic_treatment_without_provenance(self):
        preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True, "workflowProfile": "production", "sceneId": "E01_SC001"})
        self.assertEqual(preview.status_code, 200, preview.text)
        confirm = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/confirm", json={"blockingId": preview.json()["persisted_draft_id"], "evidenceFingerprint": preview.json()["blocking"]["evidence_fingerprint"], "confirmed": True, "workflowProfile": "production", "schemaVersion": "scene_blocking_v2", "blocking": build_phase_b_production_blocking_candidate(preview.json()["blocking"])})
        self.assertEqual(confirm.status_code, 200, confirm.text)
        with Session() as session:
            authority = session.query(DirectorTreatmentAuthority).filter_by(book_id=self.book_id, scene_id="E01_SC001").one()
            pointer = session.query(DirectorTreatmentPointer).filter_by(book_id=self.book_id, scene_id="E01_SC001").one()
            treatment = session.query(DirectorTreatment).filter_by(id=authority.treatment_id).one()
            envelope = json.loads(authority.envelope_json)
            for field in ("proposal_provenance", "confirmation_event", "canonical_origin_summary", "provider_provenance"):
                envelope.pop(field, None)
            envelope.pop("provenance", None)
            authority.envelope_fingerprint = _envelope_fingerprint(envelope)
            authority.envelope_json = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
            pointer.authority_envelope_fingerprint = authority.envelope_fingerprint
            treatment.model_info = json.dumps({"mode": "legacy_semantic_fixture", "llm_called": False, "llm_generated": False}, ensure_ascii=False)
            session.commit()
        blocked = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/preview", json={"workflowProfile": "production", "sceneId": "E01_SC001"})
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["detail"]["code"], "DIRECTOR_TREATMENT_SEMANTIC_NOT_READY")

    def test_shot_plan_activation_and_materializer_use_current_pointer_without_agent(self):
        blocking_preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True, "workflowProfile": "production", "sceneId": "E01_SC001"})
        self.assertEqual(blocking_preview.status_code, 200, blocking_preview.text)
        blocking_body = blocking_preview.json()
        blocking_confirm = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/confirm", json={"blockingId": blocking_body["persisted_draft_id"], "evidenceFingerprint": blocking_body["blocking"]["evidence_fingerprint"], "confirmed": True, "workflowProfile": "production", "schemaVersion": "scene_blocking_v2", "blocking": build_phase_b_production_blocking_candidate(blocking_body["blocking"])})
        self.assertEqual(blocking_confirm.status_code, 200, blocking_confirm.text)
        plan_preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/preview", json={"persist": True, "workflowProfile": "production", "sceneId": "E01_SC001"})
        self.assertEqual(plan_preview.status_code, 200, plan_preview.text)
        plan_body = plan_preview.json()
        plan_confirm = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/confirm", json={"planId": plan_body["persisted_draft_id"], "evidenceFingerprint": plan_body["plan"]["evidence_fingerprint"], "confirmed": True, "workflowProfile": "production"})
        self.assertEqual(plan_confirm.status_code, 200, plan_confirm.text)
        approved = plan_confirm.json()["shot_plan"]
        self.assertEqual(approved["qualification_state"], "PRODUCTION_QUALIFIED")
        with Session() as session:
            script_row = session.query(Script).filter_by(book_id=self.book_id, episode=1).one()
            original_script_content = script_row.content
            script_row.content = json.dumps({"scenes": [{"name": "伪造旧内容", "scene_id": "wrong"}]}, ensure_ascii=False)
            session.commit()
        readiness = self.client.get(f"/api/books/{self.book_id}/episodes/1/storyboard/readiness", params={"workflowProfile": "production"})
        self.assertEqual(readiness.status_code, 200, readiness.text)
        self.assertFalse(readiness.json()["allowed"])
        self.assertTrue(readiness.json()["blocking_issues"])
        with Session() as session:
            session.query(Script).filter_by(book_id=self.book_id, episode=1).one().content = original_script_content
            session.commit()
        with Session() as session:
            legacy_plan = session.query(ShotPlan).filter_by(id=approved["id"], book_id=self.book_id, episode=1).one()
            current_pointer = session.query(ShotPlanPointer).filter_by(book_id=self.book_id, episode=1, scene_id="E01_SC001").one()
            pointer_before = (current_pointer.shot_plan_id, current_pointer.plan_revision, current_pointer.authority_envelope_fingerprint)
            set_count_before = session.query(StoryboardMaterializationSet).filter_by(book_id=self.book_id, episode=1).count()
            shot_count_before = session.query(StoryboardShot).filter_by(book_id=self.book_id, episode=1).count()
            plan_stale_before = legacy_plan.stale_status
        with patch("agents.storyboard.StoryboardAgent.run", side_effect=AssertionError("production must not call StoryboardAgent")) as run:
            materialized = self.client.post(f"/api/books/{self.book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
        self.assertEqual(materialized.status_code, 409, materialized.text)
        self.assertEqual(materialized.json()["detail"]["code"], "SHOT_PLAN_PHASE_C_NOT_READY")
        self.assertEqual(run.call_count, 0)
        with Session() as session:
            legacy_plan = session.query(ShotPlan).filter_by(id=approved["id"], book_id=self.book_id, episode=1).one()
            current_pointer = session.query(ShotPlanPointer).filter_by(book_id=self.book_id, episode=1, scene_id="E01_SC001").one()
            self.assertEqual(session.query(StoryboardMaterializationSet).filter_by(book_id=self.book_id, episode=1).count(), set_count_before)
            self.assertEqual(session.query(StoryboardShot).filter_by(book_id=self.book_id, episode=1).count(), shot_count_before)
            self.assertEqual((current_pointer.shot_plan_id, current_pointer.plan_revision, current_pointer.authority_envelope_fingerprint), pointer_before)
            self.assertEqual(legacy_plan.stale_status, plan_stale_before)
        old_plan_id = approved["id"]
        second_preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/preview", json={"persist": True, "workflowProfile": "production", "sceneId": "E01_SC001"})
        self.assertEqual(second_preview.status_code, 200, second_preview.text)
        second_body = second_preview.json()
        second_confirm = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/confirm", json={"planId": second_body["persisted_draft_id"], "evidenceFingerprint": second_body["plan"]["evidence_fingerprint"], "confirmed": True, "workflowProfile": "production"})
        self.assertEqual(second_confirm.status_code, 200, second_confirm.text)
        old_materialize = self.client.post(f"/api/books/{self.book_id}/episodes/1/storyboard/materialize", json={"confirmed": True, "planId": old_plan_id})
        self.assertEqual(old_materialize.status_code, 409)
        self.assertEqual(old_materialize.json()["detail"]["code"], "SHOT_PLAN_NOT_CURRENT_POINTER")

    def test_failed_activation_does_not_move_pointer_and_payload_tamper_stales_it(self):
        blocking_preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True, "workflowProfile": "production", "sceneId": "E01_SC001"}).json()
        blocking_confirm = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/confirm", json={"blockingId": blocking_preview["persisted_draft_id"], "evidenceFingerprint": blocking_preview["blocking"]["evidence_fingerprint"], "confirmed": True, "workflowProfile": "production", "schemaVersion": "scene_blocking_v2", "blocking": build_phase_b_production_blocking_candidate(blocking_preview["blocking"])})
        self.assertEqual(blocking_confirm.status_code, 200, blocking_confirm.text)
        plan_preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/preview", json={"persist": True, "workflowProfile": "production", "sceneId": "E01_SC001"}).json()
        first_confirm = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/confirm", json={"planId": plan_preview["persisted_draft_id"], "evidenceFingerprint": plan_preview["plan"]["evidence_fingerprint"], "confirmed": True, "workflowProfile": "production"})
        self.assertEqual(first_confirm.status_code, 200, first_confirm.text)
        first_id = first_confirm.json()["shot_plan"]["id"]
        with Session() as session:
            pointer_before = session.query(ShotPlanPointer).filter_by(book_id=self.book_id, episode=1, scene_id="E01_SC001").one()
            pointer_id_before = pointer_before.shot_plan_id
        second_preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/preview", json={"persist": True, "workflowProfile": "production", "sceneId": "E01_SC001"}).json()
        invalid_plan = json.loads(json.dumps(second_preview["plan"], ensure_ascii=False))
        invalid_plan["shots"][0]["action_beats"] = [{"action": "冲突动作", "start_seconds": 0, "end_seconds": 99}]
        failed = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/confirm", json={"planId": second_preview["persisted_draft_id"], "evidenceFingerprint": second_preview["plan"]["evidence_fingerprint"], "confirmed": True, "workflowProfile": "production", "plan": {field: invalid_plan[field] for field in ("scene_id", "scene_name", "schema_version", "shots", "unknowns")}})
        self.assertEqual(failed.status_code, 409)
        with Session() as session:
            self.assertEqual(session.query(ShotPlanPointer).filter_by(book_id=self.book_id, episode=1, scene_id="E01_SC001").one().shot_plan_id, pointer_id_before)
            plan_row = session.query(ShotPlan).filter_by(id=first_id).one()
            plan_row.shots = "[]"
            session.commit()
        tampered = self.client.post(f"/api/books/{self.book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
        self.assertEqual(tampered.status_code, 409)
        self.assertEqual(tampered.json()["detail"]["code"], "SHOT_PLAN_PAYLOAD_TAMPERED")
        with Session() as session:
            self.assertIsNone(session.query(ShotPlanPointer).filter_by(book_id=self.book_id, episode=1, scene_id="E01_SC001").first())

    def test_missing_pointer_and_latest_approved_fallback_are_blocked(self):
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/preview", json={"workflowProfile": "production", "sceneId": "E01_SC001"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "SCENE_BLOCKING_POINTER_MISSING")

    def test_exact_fact_snapshot_change_blocks_and_stales_blocking(self):
        preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True, "workflowProfile": "production", "sceneId": "E01_SC001"}).json()
        with Session() as session:
            fact = session.query(FactSnapshot).filter_by(book_id=self.book_id, episode=1).one(); fact.payload_hash = "changed"; session.commit()
        confirm = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/confirm", json={"blockingId": preview["persisted_draft_id"], "evidenceFingerprint": preview["blocking"]["evidence_fingerprint"], "confirmed": True, "workflowProfile": "production", "blocking": build_phase_b_production_blocking_candidate(preview["blocking"])})
        self.assertEqual(confirm.status_code, 409)
        self.assertIn(confirm.json()["detail"]["code"], {"FACT_SNAPSHOT_CHANGED", "SCRIPT_IR_AUTHORITY_STALE", "DIRECTOR_TREATMENT_STALE"})

    def test_candidate_cannot_change_source_identity_or_clear_unknown_without_resolution(self):
        baseline = {"scene_id": "S1", "scene_name": "门厅", "source_spatial_facts": [{"subject_id": "c1", "predicate": "anchor", "value": "门口"}], "participants": [{"character_id": "c1", "name": "林默", "entry": {"value": "门外"}}], "beat_transitions": [{"beat_id": "B01"}], "unknowns": ["geometry"]}
        with self.assertRaises(ValueError):
            validate_scene_blocking_candidate_authority({"scene_id": "S2", "participants": baseline["participants"], "beat_transitions": baseline["beat_transitions"], "source_spatial_facts": baseline["source_spatial_facts"], "unknowns": baseline["unknowns"]}, baseline)
        with self.assertRaises(ValueError):
            validate_scene_blocking_candidate_authority({"participants": baseline["participants"], "beat_transitions": baseline["beat_transitions"], "source_spatial_facts": baseline["source_spatial_facts"], "unknowns": []}, baseline)

    def test_locked_geometry_cannot_be_changed_through_spatial_model_alias(self):
        baseline = {
            "scene_id": "S1",
            "scene_name": "门厅",
            "space": {"anchors": ["门口"], "zones": ["playing_area"]},
            "_locked_space": True,
            "source_spatial_facts": [],
            "participants": [{"character_id": "c1", "name": "林默"}],
            "beat_transitions": [{"beat_id": "B01"}],
            "unknowns": [],
        }
        with self.assertRaises(ValueError):
            validate_scene_blocking_candidate_authority({
                "scene_id": "S1",
                "scene_name": "门厅",
                "space": baseline["space"],
                "spatial_model": {"anchors": ["窗边"], "zones": ["playing_area"]},
                "source_spatial_facts": [],
                "participants": baseline["participants"],
                "beat_transitions": baseline["beat_transitions"],
                "unknowns": [],
            }, baseline)

    def test_missing_scene_asset_is_production_blocker_but_not_legacy_authority(self):
        with Session() as session:
            session.query(VisualLocation).filter_by(book_id=self.book_id).delete(); session.commit()
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True, "workflowProfile": "production", "sceneId": "E01_SC001"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json(); self.assertTrue(body["blocking"]["production_blockers"])
        self.assertEqual(body["blocking"]["production_blockers"][0]["code"], "SCENE_ASSET_MISSING")
        confirm = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/confirm", json={"blockingId": body["persisted_draft_id"], "confirmed": True, "workflowProfile": "production", "blocking": build_phase_b_production_blocking_candidate(body["blocking"])})
        self.assertEqual(confirm.status_code, 409)
        self.assertEqual(confirm.json()["detail"]["code"], "SCENE_BLOCKING_NOT_READY")

    def test_pointer_or_authority_metadata_tamper_is_fail_closed(self):
        preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True, "workflowProfile": "production", "sceneId": "E01_SC001"}).json()
        confirm = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/confirm", json={"blockingId": preview["persisted_draft_id"], "confirmed": True, "workflowProfile": "production", "blocking": build_phase_b_production_blocking_candidate(preview["blocking"])})
        self.assertEqual(confirm.status_code, 200, confirm.text)
        with Session() as session:
            pointer = session.query(SceneBlockingPointer).filter_by(book_id=self.book_id, episode=1, scene_id="E01_SC001").one()
            pointer.blocking_revision += 1
            session.commit()
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/preview", json={"workflowProfile": "production", "sceneId": "E01_SC001"})
        self.assertEqual(response.status_code, 409)
        self.assertIn(response.json()["detail"]["code"], {"SCENE_BLOCKING_POINTER_LINEAGE_CHANGED", "SCENE_BLOCKING_NOT_PRODUCTION_QUALIFIED"})


if __name__ == "__main__":
    unittest.main()
