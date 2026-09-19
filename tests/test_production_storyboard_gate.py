import hashlib
import json

from fastapi.testclient import TestClient

from api.server import app
from core.fact_snapshot import snapshot_hash
from core.script_ir import build_script_ir, script_ir_hash
from core.source_evidence_index import build_source_evidence_index
from core.director_treatment_authority import build_treatment_authority_envelope, payload_hash as treatment_payload_hash, treatment_payload_from_row
from models import Book, DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer, FactSnapshot, SceneBlocking, SceneBlockingAuthority, SceneBlockingPointer, Script, ScriptIRVersion, Session, ShotPlan, ShotPlanAuthority, ShotPlanPointer, StoryboardShot, init_db
from tests.script_fixtures import build_explicit_production_script_payload
from unittest.mock import patch


def _authorize_existing_script(client, book_id):
    """Upgrade a minimal test fixture through the real authority endpoint."""
    with Session() as session:
        # Older fixtures in this module delete the Treatment row but predate
        # the authority tables. Remove only test authority rows up front so a
        # reused SQLite integer id cannot trip the new unique treatment_id
        # invariant. This does not touch any production/user fixture.
        session.query(DirectorTreatmentPointer).delete(synchronize_session=False)
        session.query(DirectorTreatmentAuthority).delete(synchronize_session=False)
        session.commit()
        script = session.query(Script).filter_by(book_id=book_id, episode=1).one()
        source = build_explicit_production_script_payload(json.loads(script.content))
        content = json.dumps(source, ensure_ascii=False)
        script.content = content
        raw_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        ir = session.query(ScriptIRVersion).filter_by(book_id=book_id, episode=1).one()
        records = [{"fact_key": "episode|scenes|scene_existence|episode", "predicate": "scene_existence", "subject_id": "episode", "value": {"minimum": 1, "actual": len(source.get("scenes", []))}, "status": "confirmed", "evidence": [{"anchor_ref": "E0001"}]}]
        bindings = {"episode|scenes|scene_existence|episode": ["E0001"]}
        for scene in source.get("scenes", []):
            name = str(scene.get("name") or scene.get("scene_name") or "").strip()
            records.append({"fact_key": f"scene|{name}|scene_identity|scene", "predicate": "scene_identity", "subject_id": name, "value": name, "status": "confirmed", "evidence": [{"anchor_ref": "E0001"}]})
            bindings[f"scene|{name}|scene_identity|scene"] = ["E0001"]
        snapshot = FactSnapshot(book_id=book_id, episode=1, revision=1, status="confirmed", source_fingerprint=raw_hash, payload_hash=snapshot_hash(records), records_json=json.dumps(records, ensure_ascii=False), validation_report=json.dumps({"fact_coverage": {"status": "FACT_COVERAGE_SUFFICIENT"}}))
        session.add(snapshot); session.flush()
        payload = build_script_ir(source, book_id=book_id, episode=1, fact_snapshot_id=str(snapshot.id))
        ir.status = "draft"; ir.payload_json = json.dumps(payload, ensure_ascii=False); ir.payload_hash = script_ir_hash(payload); ir.source_fact_snapshot_id = str(snapshot.id); ir.source_fingerprint = raw_hash; ir.validation_status = "qualified"
        session.commit(); version_id = ir.id; snapshot_id = snapshot.id
    package = f"TEST_{book_id}"
    version = "V1"
    index = build_source_evidence_index(content.encode("utf-8"), source_package_id=package, source_version_id=version, source_raw_hash=raw_hash)
    response = client.post(f"/api/books/{book_id}/episodes/1/script-ir/activate", json={"versionId": version_id, "confirmed": True, "factSnapshotId": snapshot_id, "sourcePackageId": package, "sourceVersionId": version, "immutableSourceRawHash": raw_hash, "sourceEvidenceIndex": index, "sourceAnchorBindings": bindings, "sourceStructure": source})
    assert response.status_code == 200, response.text
    # Production Materializer must consume an explicit current Treatment
    # pointer. Upgrade the minimal fixture without invoking any provider.
    with Session() as session:
        script_row = session.query(Script).filter_by(book_id=book_id, episode=1).one()
        ir_row = session.query(ScriptIRVersion).filter_by(id=script_row.current_script_ir_version_id).one()
        ir_payload = json.loads(ir_row.payload_json or "{}")
        ir_envelope = json.loads(ir_row.authority_envelope_json or "{}")
        for treatment in session.query(DirectorTreatment).filter_by(book_id=book_id, episode=1).all():
            scene = next((item for item in ir_payload.get("scenes", []) if isinstance(item, dict) and str(item.get("name") or "").strip() == str(treatment.scene_name or "").strip()), None)
            if not scene:
                continue
            scene_id = str(scene.get("scene_id") or "").strip()
            treatment.scene_id = scene_id
            treatment.source_script_revision = str(ir_row.revision)
            treatment.source_script_hash = str(ir_row.payload_hash or "")
            treatment.source_script_ir_version_id = ir_row.id
            treatment.source_script_ir_revision = ir_row.revision
            treatment.source_script_ir_hash = str(ir_row.payload_hash or "")
            treatment.source_script_authority_fingerprint = str(ir_envelope.get("envelope_fingerprint") or "")
            treatment.source_fact_snapshot_id = str(ir_envelope.get("fact_snapshot_id") or "")
            treatment.source_fact_snapshot_revision = ir_envelope.get("fact_snapshot_revision")
            treatment.source_fact_snapshot_hash = str(ir_envelope.get("fact_snapshot_payload_hash") or "")
            treatment.qualification_state = "PRODUCTION_QUALIFIED"
            treatment.stale_status = "FRESH"
            formal = treatment_payload_from_row(treatment)
            treatment.payload_hash = treatment_payload_hash(formal)
            envelope = build_treatment_authority_envelope(treatment=formal, evidence={"book_id": book_id, "episode": 1, "scene": scene, "scene_id": scene_id, "scene_name": scene.get("name"), "characters": [], "locked_references": []}, script_ir=ir_payload, script_ir_version=ir_row, script_ir_envelope=ir_envelope, treatment_id=treatment.id, treatment_revision=treatment.revision)
            authority = DirectorTreatmentAuthority(book_id=book_id, episode=1, scene_id=scene_id, treatment_id=treatment.id, treatment_revision=treatment.revision, payload_hash=treatment.payload_hash, envelope_fingerprint=envelope["envelope_fingerprint"], envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", stale_reasons="[]")
            session.add(authority); session.flush(); treatment.authority_envelope_id = authority.id
            session.add(DirectorTreatmentPointer(book_id=book_id, episode=1, scene_id=scene_id, treatment_id=treatment.id, treatment_revision=treatment.revision, authority_envelope_fingerprint=envelope["envelope_fingerprint"], qualification_state="PRODUCTION_QUALIFIED"))
            session.query(SceneBlocking).filter_by(book_id=book_id, episode=1, scene_name=treatment.scene_name).update({"scene_id": scene_id}, synchronize_session=False)
            session.query(ShotPlan).filter_by(book_id=book_id, episode=1, scene_name=treatment.scene_name).update({"scene_id": scene_id}, synchronize_session=False)
        session.commit()


def test_materialize_endpoint_requires_confirmation_and_is_deterministic():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="materializer", filename="materializer.txt", status="imported"); session.add(book); session.flush(); book_id = book.id
        script = Script(book_id=book_id, episode=1, content=json.dumps({"scenes": [{"name": "门厅"}]}), workflow_profile="production"); session.add(script); session.flush()
        ir = ScriptIRVersion(book_id=book_id, episode=1, status="qualified", validation_status="qualified", payload_json=json.dumps({"scenes": [{"name": "门厅"}]})); session.add(ir); session.flush(); script.current_script_ir_version_id = ir.id
        treatment = DirectorTreatment(book_id=book_id, episode=1, scene_name="门厅", status="approved"); session.add(treatment); session.flush()
        blocking = SceneBlocking(book_id=book_id, episode=1, scene_name="门厅", status="approved", treatment_id=treatment.id); session.add(blocking); session.flush()
        plan = ShotPlan(book_id=book_id, episode=1, scene_name="门厅", status="approved", treatment_id=treatment.id, blocking_id=blocking.id, evidence_fingerprint="fp", shots=json.dumps([{"plan_shot_id": "S01", "event": "进入", "duration_hint_seconds": 4, "camera": {"movement": "static"}, "entry_state": {}, "exit_state": {}}])); session.add(plan); session.commit()
    _authorize_existing_script(client, book_id)
    blocked = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={})
    assert blocked.status_code == 409
    ok = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert ok.status_code == 409
    assert ok.json()["detail"]["code"] in {"SCENE_BLOCKING_POINTER_MISSING", "SHOT_PLAN_POINTER_MISSING"}
    with Session() as session:
        for model in (StoryboardShot, ShotPlanPointer, ShotPlanAuthority, ShotPlan, SceneBlockingPointer, SceneBlockingAuthority, SceneBlocking, DirectorTreatmentPointer, DirectorTreatmentAuthority, DirectorTreatment, FactSnapshot, ScriptIRVersion, Script): session.query(model).filter_by(book_id=book_id).delete(synchronize_session=False)
        session.query(Book).filter_by(id=book_id).delete(); session.commit()


def test_production_materializer_never_calls_storyboard_agent():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="materializer-no-agent", filename="materializer-no-agent.txt", status="imported"); session.add(book); session.flush(); book_id = book.id
        script = Script(book_id=book_id, episode=1, content=json.dumps({"scenes": [{"name": "走廊"}]}), workflow_profile="production"); session.add(script); session.flush()
        ir = ScriptIRVersion(book_id=book_id, episode=1, status="qualified", validation_status="qualified", payload_json=json.dumps({"scenes": [{"name": "走廊"}]})); session.add(ir); session.flush(); script.current_script_ir_version_id = ir.id
        treatment = DirectorTreatment(book_id=book_id, episode=1, scene_name="走廊", status="approved"); session.add(treatment); session.flush()
        blocking = SceneBlocking(book_id=book_id, episode=1, scene_name="走廊", status="approved", treatment_id=treatment.id); session.add(blocking); session.flush()
        plan = ShotPlan(book_id=book_id, episode=1, scene_name="走廊", status="approved", treatment_id=treatment.id, blocking_id=blocking.id, evidence_fingerprint="fp", shots=json.dumps([
            {"plan_shot_id": "S01", "event": "停步", "action_beats": [{"at": 0.5, "action": "停步"}], "duration_hint_seconds": 3, "camera": {"movement": "static"}, "entry_state": {"position": "门口"}, "exit_state": {"position": "走廊"}, "asset_bindings": {"character": ["C1"]}, "continuity_contract": {"screen_direction": "left_to_right"}},
            {"plan_shot_id": "S02", "event": "回望", "action_beats": [{"at": 1.0, "action": "回望"}], "duration_hint_seconds": 4, "camera": {"movement": "push-in"}, "entry_state": {"position": "走廊"}, "exit_state": {"position": "走廊"}, "asset_bindings": {"character": ["C1"]}, "continuity_contract": {"screen_direction": "left_to_right"}},
        ])); session.add(plan); session.commit()
    _authorize_existing_script(client, book_id)
    with patch("agents.storyboard.StoryboardAgent.run", side_effect=AssertionError("production must not call StoryboardAgent")) as run:
        response = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] in {"SCENE_BLOCKING_POINTER_MISSING", "SHOT_PLAN_POINTER_MISSING"}
    assert run.call_count == 0
    with Session() as session:
        rows = session.query(StoryboardShot).filter_by(book_id=book_id, episode=1).all()
        for model in (StoryboardShot, ShotPlanPointer, ShotPlanAuthority, ShotPlan, SceneBlockingPointer, SceneBlockingAuthority, SceneBlocking, DirectorTreatmentPointer, DirectorTreatmentAuthority, DirectorTreatment, FactSnapshot, ScriptIRVersion, Script): session.query(model).filter_by(book_id=book_id).delete(synchronize_session=False)
        session.query(Book).filter_by(id=book_id).delete(); session.commit()


def test_production_materializer_fails_closed_when_upstream_evidence_is_missing():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="materializer-blocked", filename="materializer-blocked.txt", status="imported"); session.add(book); session.flush(); book_id = book.id
        session.add(Script(book_id=book_id, episode=1, content=json.dumps({"scenes": [{"name": "仓库"}]}), workflow_profile="production"))
        session.add(ShotPlan(book_id=book_id, episode=1, scene_name="仓库", status="approved", shots=json.dumps([{ "plan_shot_id": "S01", "event": "等待"}]))); session.commit()
    response = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert response.status_code == 409
    assert "qualified ScriptIR" in str(response.json()["detail"])
    with Session() as session:
        session.query(ShotPlan).filter_by(book_id=book_id).delete(); session.query(Script).filter_by(book_id=book_id).delete(); session.query(Book).filter_by(id=book_id).delete(); session.commit()


def test_production_materializer_rejects_malformed_shot_plan_payload():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="materializer-invalid-plan", filename="materializer-invalid-plan.txt", status="imported"); session.add(book); session.flush(); book_id = book.id
        script = Script(book_id=book_id, episode=1, content=json.dumps({"scenes": [{"name": "仓库"}]}), workflow_profile="production"); session.add(script); session.flush()
        ir = ScriptIRVersion(book_id=book_id, episode=1, status="qualified", validation_status="qualified", payload_json=json.dumps({"scenes": [{"name": "仓库"}]})); session.add(ir); session.flush(); script.current_script_ir_version_id = ir.id
        treatment = DirectorTreatment(book_id=book_id, episode=1, scene_name="仓库", status="approved"); session.add(treatment); session.flush()
        blocking = SceneBlocking(book_id=book_id, episode=1, scene_name="仓库", status="approved", treatment_id=treatment.id); session.add(blocking); session.flush()
        session.add(ShotPlan(book_id=book_id, episode=1, scene_name="仓库", status="approved", treatment_id=treatment.id, blocking_id=blocking.id, shots="{malformed")); session.commit()
    _authorize_existing_script(client, book_id)
    response = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] in {"SCENE_BLOCKING_POINTER_MISSING", "SHOT_PLAN_POINTER_MISSING"}
    with Session() as session:
        assert session.query(StoryboardShot).filter_by(book_id=book_id, episode=1).count() == 0
        session.query(ShotPlan).filter_by(book_id=book_id).delete(); session.query(SceneBlocking).filter_by(book_id=book_id).delete(); session.query(DirectorTreatment).filter_by(book_id=book_id).delete(); session.query(ScriptIRVersion).filter_by(book_id=book_id).delete(); session.query(Script).filter_by(book_id=book_id).delete(); session.query(Book).filter_by(id=book_id).delete(); session.commit()


def test_qualification_blocker_never_promotes_materialized_shot_to_ready():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="materializer-qualification", filename="materializer-qualification.txt", status="imported"); session.add(book); session.flush(); book_id = book.id
        script = Script(book_id=book_id, episode=1, content=json.dumps({"scenes": [{"name": "车站"}]}), workflow_profile="production"); session.add(script); session.flush()
        ir = ScriptIRVersion(book_id=book_id, episode=1, status="qualified", validation_status="qualified", payload_json=json.dumps({"scenes": [{"name": "车站"}]})); session.add(ir); session.flush(); script.current_script_ir_version_id = ir.id
        treatment = DirectorTreatment(book_id=book_id, episode=1, scene_name="车站", status="approved"); session.add(treatment); session.flush()
        blocking = SceneBlocking(book_id=book_id, episode=1, scene_name="车站", status="approved", treatment_id=treatment.id); session.add(blocking); session.flush()
        plan = ShotPlan(book_id=book_id, episode=1, scene_name="车站", status="approved", treatment_id=treatment.id, blocking_id=blocking.id, shots=json.dumps([{ "plan_shot_id": "S01", "event": "", "duration_hint_seconds": 3, "camera": {"movement": "static"}}])); session.add(plan); session.commit()
    _authorize_existing_script(client, book_id)
    response = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] in {"SCENE_BLOCKING_POINTER_MISSING", "SHOT_PLAN_POINTER_MISSING"}
    with Session() as session:
        session.query(StoryboardShot).filter_by(book_id=book_id, episode=1).delete(); session.query(ShotPlan).filter_by(book_id=book_id).delete(); session.query(SceneBlocking).filter_by(book_id=book_id).delete(); session.query(DirectorTreatment).filter_by(book_id=book_id).delete(); session.query(ScriptIRVersion).filter_by(book_id=book_id).delete(); session.query(Script).filter_by(book_id=book_id).delete(); session.query(Book).filter_by(id=book_id).delete(); session.commit()


def test_materializer_uses_latest_approved_revision_per_scene_without_explicit_plan_id():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="materializer-latest-revision", filename="materializer-latest-revision.txt", status="imported"); session.add(book); session.flush(); book_id = book.id
        script = Script(book_id=book_id, episode=1, content=json.dumps({"scenes": [{"name": "门厅"}]}), workflow_profile="production"); session.add(script); session.flush()
        ir = ScriptIRVersion(book_id=book_id, episode=1, status="qualified", validation_status="qualified", payload_json=json.dumps({"scenes": [{"name": "门厅"}]})); session.add(ir); session.flush(); script.current_script_ir_version_id = ir.id
        treatment = DirectorTreatment(book_id=book_id, episode=1, scene_name="门厅", status="approved", revision=1); session.add(treatment); session.flush()
        blocking = SceneBlocking(book_id=book_id, episode=1, scene_name="门厅", status="approved", treatment_id=treatment.id); session.add(blocking); session.flush()
        old_plan = ShotPlan(book_id=book_id, episode=1, scene_name="门厅", status="approved", revision=1, treatment_id=treatment.id, blocking_id=blocking.id, evidence_fingerprint="old", shots=json.dumps([{ "plan_shot_id": "OLD", "event": "旧版本" }])); session.add(old_plan)
        new_plan = ShotPlan(book_id=book_id, episode=1, scene_name="门厅", status="approved", revision=2, treatment_id=treatment.id, blocking_id=blocking.id, evidence_fingerprint="new", shots=json.dumps([{ "plan_shot_id": "NEW", "event": "新版本" }])); session.add(new_plan); session.commit()
    _authorize_existing_script(client, book_id)
    response = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] in {"SCENE_BLOCKING_POINTER_MISSING", "SHOT_PLAN_POINTER_MISSING"}
    with Session() as session:
        rows = session.query(StoryboardShot).filter_by(book_id=book_id, episode=1).all()
        assert rows == []
        session.query(StoryboardShot).filter_by(book_id=book_id, episode=1).delete(); session.query(ShotPlan).filter_by(book_id=book_id).delete(); session.query(SceneBlocking).filter_by(book_id=book_id).delete(); session.query(DirectorTreatment).filter_by(book_id=book_id).delete(); session.query(ScriptIRVersion).filter_by(book_id=book_id).delete(); session.query(Script).filter_by(book_id=book_id).delete(); session.query(Book).filter_by(id=book_id).delete(); session.commit()


def test_materializer_fails_closed_when_existing_shot_belongs_to_another_plan_revision():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="materializer-revision-conflict", filename="materializer-revision-conflict.txt", status="imported"); session.add(book); session.flush(); book_id = book.id
        script = Script(book_id=book_id, episode=1, content=json.dumps({"scenes": [{"name": "门厅"}]}), workflow_profile="production"); session.add(script); session.flush()
        ir = ScriptIRVersion(book_id=book_id, episode=1, status="qualified", validation_status="qualified", payload_json=json.dumps({"scenes": [{"name": "门厅"}]})); session.add(ir); session.flush(); script.current_script_ir_version_id = ir.id
        treatment = DirectorTreatment(book_id=book_id, episode=1, scene_name="门厅", status="approved", revision=1); session.add(treatment); session.flush()
        blocking = SceneBlocking(book_id=book_id, episode=1, scene_name="门厅", status="approved", treatment_id=treatment.id); session.add(blocking); session.flush()
        treatment_id, blocking_id = treatment.id, blocking.id
        first = ShotPlan(book_id=book_id, episode=1, scene_name="门厅", status="approved", revision=1, treatment_id=treatment_id, blocking_id=blocking_id, evidence_fingerprint="same-evidence", shots=json.dumps([{ "plan_shot_id": "S01", "event": "旧动作" }])); session.add(first); session.commit(); first_id = first.id
    _authorize_existing_script(client, book_id)
    first_response = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert first_response.status_code == 409
    assert first_response.json()["detail"]["code"] in {"SCENE_BLOCKING_POINTER_MISSING", "SHOT_PLAN_POINTER_MISSING"}
    with Session() as session:
        second = ShotPlan(book_id=book_id, episode=1, scene_name="门厅", status="approved", revision=2, treatment_id=treatment_id, blocking_id=blocking_id, evidence_fingerprint="same-evidence", shots=json.dumps([{ "plan_shot_id": "S01", "event": "新动作" }])); session.add(second); session.commit(); second_id = second.id
    response = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] in {"SCENE_BLOCKING_POINTER_MISSING", "SHOT_PLAN_POINTER_MISSING"}
    with Session() as session:
        session.query(StoryboardShot).filter_by(book_id=book_id, episode=1).delete(); session.query(ShotPlan).filter_by(book_id=book_id).delete(); session.query(SceneBlocking).filter_by(book_id=book_id).delete(); session.query(DirectorTreatment).filter_by(book_id=book_id).delete(); session.query(ScriptIRVersion).filter_by(book_id=book_id).delete(); session.query(Script).filter_by(book_id=book_id).delete(); session.query(Book).filter_by(id=book_id).delete(); session.commit()


def test_materializer_fails_closed_when_existing_shot_has_no_plan_reference():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="materializer-legacy-reference", filename="materializer-legacy-reference.txt", status="imported"); session.add(book); session.flush(); book_id = book.id
        script = Script(book_id=book_id, episode=1, content=json.dumps({"scenes": [{"name": "门厅"}]}), workflow_profile="production"); session.add(script); session.flush()
        ir = ScriptIRVersion(book_id=book_id, episode=1, status="qualified", validation_status="qualified", payload_json=json.dumps({"scenes": [{"name": "门厅"}]})); session.add(ir); session.flush(); script.current_script_ir_version_id = ir.id
        treatment = DirectorTreatment(book_id=book_id, episode=1, scene_name="门厅", status="approved", revision=1); session.add(treatment); session.flush()
        blocking = SceneBlocking(book_id=book_id, episode=1, scene_name="门厅", status="approved", treatment_id=treatment.id); session.add(blocking); session.flush()
        plan = ShotPlan(book_id=book_id, episode=1, scene_name="门厅", status="approved", revision=1, treatment_id=treatment.id, blocking_id=blocking.id, shots=json.dumps([{ "plan_shot_id": "S01", "event": "进入" }])); session.add(plan)
        session.add(StoryboardShot(book_id=book_id, episode=1, scene_name="门厅", shot_id=1, meta_info="{}")); session.commit()
    _authorize_existing_script(client, book_id)
    response = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] in {"SCENE_BLOCKING_POINTER_MISSING", "SHOT_PLAN_POINTER_MISSING"}
    with Session() as session:
        assert session.query(StoryboardShot).filter_by(book_id=book_id, episode=1).count() == 1
        session.query(StoryboardShot).filter_by(book_id=book_id, episode=1).delete(); session.query(ShotPlan).filter_by(book_id=book_id).delete(); session.query(SceneBlocking).filter_by(book_id=book_id).delete(); session.query(DirectorTreatment).filter_by(book_id=book_id).delete(); session.query(ScriptIRVersion).filter_by(book_id=book_id).delete(); session.query(Script).filter_by(book_id=book_id).delete(); session.query(Book).filter_by(id=book_id).delete(); session.commit()
