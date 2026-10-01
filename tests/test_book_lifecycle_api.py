import json
import uuid
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import server
from api.server import app
from models import (
    AgentAuditLog,
    AgentMessage,
    AgentPlan,
    AgentSession,
    Book,
    DirectorPlan,
    DirectorReasoning,
    DirectorReasoningGeneration,
    FactRecord,
    FactSnapshot,
    Script,
    ScriptIRVersion,
    ScenePlan,
    StoryBeat,
    VisualDecision,
    Session,
    ShotAssetBinding,
    StoryboardShot,
    StoryboardPlan,
    init_db,
)


class BookLifecycleApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def _create_book(self, title=None):
        title = title or f"Lifecycle {uuid.uuid4().hex[:8]}"
        response = self.client.post("/api/books", json={"title": title})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _delete(self, book_id):
        response = self.client.delete(f"/api/books/{book_id}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json().get("orphan_rows"), 0, response.text)

    def _create_script_ir(self, book_id, script_id, *, episode=1, payload_hash=None):
        payload_hash = payload_hash or f"sha256:ir-{book_id}"
        with Session() as session:
            ir = ScriptIRVersion(
                book_id=book_id,
                episode=episode,
                revision=1,
                payload_json=json.dumps({"episode": episode, "scenes": []}, ensure_ascii=False),
                payload_hash=payload_hash,
                validation_status="valid",
            )
            session.add(ir)
            session.flush()
            source = session.get(Script, script_id)
            source.current_script_ir_version_id = ir.id
            session.commit()
            return ir.id

    def test_create_book_is_provider_free_and_server_owned(self):
        payload = self._create_book("  Lifecycle Book  ")
        book_id = payload["id"]
        try:
            self.assertEqual(payload["title"], "Lifecycle Book")
            self.assertEqual(payload["chapters"], 0)
            self.assertEqual(payload["words"], 0)
            self.assertEqual(payload["status"], "imported")
            self.assertEqual(payload["provider_calls"], 0)
            self.assertEqual(payload["llm_calls"], 0)
            with Session() as session:
                book = session.get(Book, book_id)
                self.assertIsNotNone(book)
                self.assertTrue(book.filename.startswith("api-"))
                self.assertTrue(book.filename.endswith(".json"))
                self.assertEqual(book.chapter_count, 0)
                self.assertEqual(book.total_words, 0)
            listed = self.client.get("/api/books")
            self.assertEqual(listed.status_code, 200)
            self.assertTrue(any(row["id"] == book_id for row in listed.json()))
        finally:
            self._delete(book_id)

    def test_book_create_rejects_empty_title_and_caller_owned_fields(self):
        self.assertEqual(self.client.post("/api/books", json={"title": "   "}).status_code, 422)
        self.assertEqual(self.client.post("/api/books", json={"title": "x", "id": 990400}).status_code, 422)
        self.assertEqual(self.client.post("/api/books", json={"title": "x", "filename": "../../screenplay.db"}).status_code, 422)

    def test_structured_script_bootstraps_script_ir_without_legacy_reconstruction(self):
        book = self._create_book()
        book_id = book["id"]
        content = {
            "scenes": [
                {
                    "scene_id": "E01_SC001",
                    "location": "测试房间",
                    "characters": [{"id": "CANARY_CHARACTER_01"}],
                    "beats": [{"beat_id": "E01_SC001_B001", "action": "人物站在房间中央"}],
                }
            ]
        }
        try:
            response = self.client.post(
                f"/api/books/{book_id}/scripts",
                json={"episode": 1, "content": content, "genre": "short_drama", "workflowProfile": "production"},
            )
            self.assertEqual(response.status_code, 201, response.text)
            script = response.json()
            self.assertEqual(script["workflow_profile"], "production")
            self.assertEqual(script["provider_calls"], 0)
            self.assertEqual(script["llm_calls"], 0)

            with Session() as session:
                source = session.query(Script).filter_by(id=script["id"]).one()
                self.assertEqual(source.content, json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
                self.assertIsNone(source.current_script_ir_version_id)

            duplicate = self.client.post(
                f"/api/books/{book_id}/scripts",
                json={"episode": 1, "content": "duplicate", "genre": "short_drama", "workflowProfile": "production"},
            )
            self.assertEqual(duplicate.status_code, 409)
            self.assertEqual(duplicate.json()["detail"]["code"], "SCRIPT_ALREADY_EXISTS")

            build = self.client.post(f"/api/books/{book_id}/episodes/1/script-ir/build", json={"persist": True})
            self.assertEqual(build.status_code, 200, build.text)
            self.assertFalse(build.json().get("legacy_reconstruction"))
            self.assertFalse(build.json().get("llm_called"))
            self.assertIsNotNone(build.json().get("persisted_draft_id"))
            with Session() as session:
                self.assertEqual(session.query(ScriptIRVersion).filter_by(book_id=book_id).count(), 1)
        finally:
            self._delete(book_id)

    def test_script_contract_validation_and_missing_book(self):
        missing = self.client.post("/api/books/99999999/scripts", json={"episode": 1, "content": "x"})
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"]["code"], "BOOK_NOT_FOUND")
        book = self._create_book()
        book_id = book["id"]
        try:
            self.assertEqual(self.client.post(f"/api/books/{book_id}/scripts", json={"episode": 0, "content": "x"}).status_code, 422)
            self.assertEqual(self.client.post(f"/api/books/{book_id}/scripts", json={"episode": 1, "content": "   "}).status_code, 422)
            self.assertEqual(self.client.post(f"/api/books/{book_id}/scripts", json={"episode": 1, "content": [], "filename": "x"}).status_code, 422)
            with Session() as session:
                self.assertEqual(session.query(Script).filter_by(book_id=book_id).count(), 0)
                self.assertEqual(session.query(ScriptIRVersion).filter_by(book_id=book_id).count(), 0)
        finally:
            self._delete(book_id)

    def test_delete_does_not_mutate_neighbor_book(self):
        left = self._create_book("Duplicate Title")
        right = self._create_book("Duplicate Title")
        try:
            left_script = self.client.post(f"/api/books/{left['id']}/scripts", json={"episode": 1, "content": "left"})
            right_script = self.client.post(f"/api/books/{right['id']}/scripts", json={"episode": 1, "content": "right"})
            self.assertEqual(left_script.status_code, 201)
            self.assertEqual(right_script.status_code, 201)
            self._delete(left["id"])
            with Session() as session:
                self.assertIsNotNone(session.get(Book, right["id"]))
                self.assertEqual(session.query(Script).filter_by(book_id=right["id"]).count(), 1)
        finally:
            with Session() as session:
                session.query(Script).filter(Script.book_id.in_([left["id"], right["id"]])).delete(synchronize_session=False)
                session.query(Book).filter(Book.id.in_([left["id"], right["id"]])).delete(synchronize_session=False)
                session.commit()

    def test_delete_cleans_indirect_agent_fact_and_shot_children(self):
        book = self._create_book()
        book_id = book["id"]
        with Session() as session:
            shot = StoryboardShot(book_id=book_id, episode=1, scene_name="canary", shot_id=1)
            session.add(shot)
            session.flush()
            agent = AgentSession(book_id=book_id, user_prompt="disposable canary")
            session.add(agent)
            session.flush()
            session.add_all([
                AgentPlan(session_id=agent.id, objective="cleanup"),
                AgentMessage(session_id=agent.id, role="user", content="discard"),
                AgentAuditLog(session_id=agent.id, operation="test"),
            ])
            snapshot = FactSnapshot(book_id=book_id, episode=1, source_fingerprint="canary")
            session.add(snapshot)
            session.flush()
            session.add(FactRecord(snapshot_id=snapshot.id, fact_id="CANARY_FACT", subject_type="scene", subject_id="1", predicate="exists", value_json="true"))
            session.add(ShotAssetBinding(
                storyboard_shot_id=shot.id,
                asset_type="CHARACTER",
                authority_id="disposable-authority",
                version_id="disposable-version",
                binding_fingerprint="canary",
                status="ACTIVE",
            ))
            session.commit()
        response = self.client.delete(f"/api/books/{book_id}")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["orphan_rows"], 0, payload)
        self.assertGreaterEqual(payload["deleted_rows"].get("agent_plans", 0), 1)
        self.assertGreaterEqual(payload["deleted_rows"].get("agent_messages", 0), 1)
        self.assertGreaterEqual(payload["deleted_rows"].get("agent_audit_logs", 0), 1)
        self.assertGreaterEqual(payload["deleted_rows"].get("fact_records", 0), 1)
        self.assertGreaterEqual(payload["deleted_rows"].get("shot_asset_bindings", 0), 1)

    def test_delete_cleans_canonical_director_runtime_without_outline(self):
        """Canonical source IR ownership cleans runtime rows before outlines exist."""
        book = self._create_book()
        book_id = book["id"]
        script = self.client.post(
            f"/api/books/{book_id}/scripts",
            json={"episode": 1, "content": {"scenes": []}, "workflowProfile": "production"},
        )
        self.assertEqual(script.status_code, 201, script.text)
        ir_id = self._create_script_ir(book_id, script.json()["id"])
        generated_plan = self.client.post(
            f"/episodes/{ir_id}/director-plan",
            json={"episode_context": {"book_id": 999999, "source_script_ir_hash": "sha256:caller-forged"}},
        )
        self.assertEqual(generated_plan.status_code, 201, generated_plan.text)
        generated_lineage = generated_plan.json()["plan"]["lineage"]
        self.assertEqual(generated_lineage["book_id"], book_id)
        self.assertEqual(generated_lineage["source_script_ir_version_id"], ir_id)
        self.assertEqual(generated_lineage["source_script_ir_hash"], f"sha256:ir-{book_id}")
        generated_reasoning = self.client.post(
            f"/episodes/{ir_id}/director-reasoning",
            json={"episode_context": {"book_id": 999999, "source_script_ir_hash": "sha256:caller-forged"}},
        )
        self.assertEqual(generated_reasoning.status_code, 201, generated_reasoning.text)
        reasoning_lineage = generated_reasoning.json()["reasoning"]["lineage"]
        self.assertEqual(reasoning_lineage["book_id"], book_id)
        self.assertEqual(reasoning_lineage["source_script_ir_version_id"], ir_id)
        self.assertEqual(reasoning_lineage["source_script_ir_hash"], f"sha256:ir-{book_id}")
        # Remove the API-created empty runtime rows before adding the richer
        # canonical graph below; the lineage assertions above are the contract
        # under test and the rows are all in the same disposable Book scope.
        with Session() as session:
            session.query(DirectorPlan).filter_by(episode_id=str(ir_id)).delete(synchronize_session=False)
            session.query(DirectorReasoning).filter_by(episode_id=str(ir_id)).delete(synchronize_session=False)
            session.commit()
        with Session() as session:
            plan = DirectorPlan(episode_id="1", version=1, source_script_ir_version_id=ir_id, source_script_ir_hash=f"sha256:ir-{book_id}", lineage_json=json.dumps({"book_id": book_id, "source_script_ir_version_id": ir_id, "source_script_ir_hash": f"sha256:ir-{book_id}"}))
            session.add(plan)
            session.flush()
            scene_plan = ScenePlan(director_plan_id=plan.id, episode_id="1", scene_id=f"S-{book_id}")
            session.add(scene_plan)
            reasoning = DirectorReasoning(episode_id="1", version=1, source_script_ir_hash=f"sha256:ir-{book_id}", lineage_json=json.dumps({"book_id": book_id, "source_script_ir_version_id": ir_id, "source_script_ir_hash": f"sha256:ir-{book_id}"}))
            session.add(reasoning)
            session.flush()
            beat = StoryBeat(director_reasoning_id=reasoning.id, sequence=1)
            decision = VisualDecision(director_reasoning_id=reasoning.id, story_beat_sequence=1)
            generation = DirectorReasoningGeneration(generation_id=f"gen-{book_id}", episode_id="1", director_reasoning_id=reasoning.id)
            session.add_all([beat, decision, generation])
            session.flush()
            plan_id, scene_plan_id, reasoning_id, beat_id, decision_id, generation_id = plan.id, scene_plan.id, reasoning.id, beat.id, decision.id, generation.id
            session.commit()

        response = self.client.delete(f"/api/books/{book_id}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["orphan_rows"], 0, response.text)
        with Session() as session:
            self.assertIsNone(session.get(DirectorPlan, plan_id))
            self.assertIsNone(session.get(ScenePlan, scene_plan_id))
            self.assertIsNone(session.get(DirectorReasoning, reasoning_id))
            self.assertIsNone(session.get(StoryBeat, beat_id))
            self.assertIsNone(session.get(VisualDecision, decision_id))
            self.assertIsNone(session.get(DirectorReasoningGeneration, generation_id))

    def test_delete_isolates_same_episode_neighbor_runtime(self):
        left = self._create_book("Director Neighbor A")
        right = self._create_book("Director Neighbor B")
        left_script = self.client.post(f"/api/books/{left['id']}/scripts", json={"episode": 1, "content": {"scenes": []}}).json()
        right_script = self.client.post(f"/api/books/{right['id']}/scripts", json={"episode": 1, "content": {"scenes": []}}).json()
        shared_hash = "sha256:identical-source-payload"
        left_ir = self._create_script_ir(left["id"], left_script["id"], payload_hash=shared_hash)
        right_ir = self._create_script_ir(right["id"], right_script["id"], payload_hash=shared_hash)
        with Session() as session:
            left_plan = DirectorPlan(episode_id="1", version=1, source_script_ir_version_id=left_ir, source_script_ir_hash=shared_hash, lineage_json=json.dumps({"book_id": left["id"], "source_script_ir_version_id": left_ir, "source_script_ir_hash": shared_hash}))
            right_plan = DirectorPlan(episode_id="1", version=2, source_script_ir_version_id=right_ir, source_script_ir_hash=shared_hash, lineage_json=json.dumps({"book_id": right["id"], "source_script_ir_version_id": right_ir, "source_script_ir_hash": shared_hash}))
            session.add_all([left_plan, right_plan])
            session.flush()
            left_reasoning = DirectorReasoning(episode_id="1", version=1, source_script_ir_hash=shared_hash, lineage_json=json.dumps({"book_id": left["id"], "source_script_ir_version_id": left_ir, "source_script_ir_hash": shared_hash}))
            right_reasoning = DirectorReasoning(episode_id="1", version=2, source_script_ir_hash=shared_hash, lineage_json=json.dumps({"book_id": right["id"], "source_script_ir_version_id": right_ir, "source_script_ir_hash": shared_hash}))
            session.add_all([left_reasoning, right_reasoning])
            session.flush()
            left_storyboard = StoryboardPlan(episode_id="1", version=1, director_reasoning_id=left_reasoning.id, lineage_json=json.dumps({"director_reasoning_id": left_reasoning.id}))
            right_storyboard = StoryboardPlan(episode_id="1", version=2, director_reasoning_id=right_reasoning.id, lineage_json=json.dumps({"director_reasoning_id": right_reasoning.id}))
            session.add_all([left_storyboard, right_storyboard])
            session.flush()
            rows = [
                ScenePlan(director_plan_id=left_plan.id, episode_id="1", scene_id="left-scene"),
                ScenePlan(director_plan_id=right_plan.id, episode_id="1", scene_id="right-scene"),
                StoryBeat(director_reasoning_id=left_reasoning.id, sequence=1),
                StoryBeat(director_reasoning_id=right_reasoning.id, sequence=1),
                VisualDecision(director_reasoning_id=left_reasoning.id, story_beat_sequence=1),
                VisualDecision(director_reasoning_id=right_reasoning.id, story_beat_sequence=1),
                DirectorReasoningGeneration(generation_id=f"left-{left['id']}", episode_id="1", director_reasoning_id=left_reasoning.id),
                DirectorReasoningGeneration(generation_id=f"right-{right['id']}", episode_id="1", director_reasoning_id=right_reasoning.id),
            ]
            session.add_all(rows)
            session.flush()
            right_ids = {"plan": right_plan.id, "reasoning": right_reasoning.id, "storyboard": right_storyboard.id, "scene": rows[1].id, "beat": rows[3].id, "decision": rows[5].id, "generation": rows[7].id}
            session.commit()
        try:
            self._delete(left["id"])
            with Session() as session:
                self.assertIsNotNone(session.get(Book, right["id"]))
                self.assertIsNotNone(session.get(Script, right_script["id"]))
                self.assertIsNotNone(session.get(ScriptIRVersion, right_ir))
                self.assertIsNotNone(session.get(DirectorPlan, right_ids["plan"]))
                self.assertIsNotNone(session.get(DirectorReasoning, right_ids["reasoning"]))
                self.assertIsNotNone(session.get(StoryboardPlan, right_ids["storyboard"]))
                self.assertIsNotNone(session.get(ScenePlan, right_ids["scene"]))
                self.assertIsNotNone(session.get(StoryBeat, right_ids["beat"]))
                self.assertIsNotNone(session.get(VisualDecision, right_ids["decision"]))
                self.assertIsNotNone(session.get(DirectorReasoningGeneration, right_ids["generation"]))
        finally:
            with Session() as session:
                right_exists = session.get(Book, right["id"]) is not None
            if right_exists:
                self._delete(right["id"])

    def test_ambiguous_legacy_director_row_fails_closed_without_partial_delete(self):
        book = self._create_book()
        script = self.client.post(f"/api/books/{book['id']}/scripts", json={"episode": 1, "content": {"scenes": []}}).json()
        with Session() as session:
            row = DirectorPlan(episode_id="1", version=1)
            session.add(row)
            session.commit()
            row_id = row.id
        try:
            response = self.client.delete(f"/api/books/{book['id']}")
            self.assertEqual(response.status_code, 409, response.text)
            detail = response.json()["detail"]
            self.assertEqual(detail["code"], "BOOK_DELETE_DIRECTOR_SCOPE_AMBIGUOUS")
            self.assertEqual(detail["ambiguous_rows"], 1)
            with Session() as session:
                self.assertIsNotNone(session.get(Book, book["id"]))
                self.assertIsNotNone(session.get(Script, script["id"]))
                self.assertIsNotNone(session.get(DirectorPlan, row_id))
        finally:
            with Session() as session:
                session.query(DirectorPlan).filter_by(id=row_id).delete(synchronize_session=False)
                session.query(Script).filter_by(book_id=book["id"]).delete(synchronize_session=False)
                session.query(Book).filter_by(id=book["id"]).delete(synchronize_session=False)
                session.commit()

    def test_same_hash_without_source_id_is_ambiguous(self):
        left = self._create_book("Hash Ambiguous A")
        right = self._create_book("Hash Ambiguous B")
        left_script = self.client.post(f"/api/books/{left['id']}/scripts", json={"episode": 1, "content": {"same": True}}).json()
        right_script = self.client.post(f"/api/books/{right['id']}/scripts", json={"episode": 1, "content": {"same": True}}).json()
        shared_hash = "sha256:ambiguous-hash"
        self._create_script_ir(left["id"], left_script["id"], payload_hash=shared_hash)
        self._create_script_ir(right["id"], right_script["id"], payload_hash=shared_hash)
        with Session() as session:
            row = DirectorPlan(episode_id="1", version=1, source_script_ir_hash=shared_hash, lineage_json="{}")
            session.add(row)
            session.commit()
            row_id = row.id
        try:
            response = self.client.delete(f"/api/books/{left['id']}")
            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual(response.json()["detail"]["code"], "BOOK_DELETE_DIRECTOR_SCOPE_AMBIGUOUS")
            with Session() as session:
                self.assertIsNotNone(session.get(Book, left["id"]))
                self.assertIsNotNone(session.get(Book, right["id"]))
                self.assertIsNotNone(session.get(DirectorPlan, row_id))
        finally:
            with Session() as session:
                session.query(DirectorPlan).filter_by(id=row_id).delete(synchronize_session=False)
                session.commit()
            self._delete(left["id"])
            self._delete(right["id"])

    def test_new_write_routes_remain_under_api_auth_middleware(self):
        original_enabled = server.config.API_AUTH_ENABLED
        original_token = server.config.API_AUTH_TOKEN
        original_roles = server.config.API_AUTH_ROLE_TOKENS
        original_roles_error = server.config.API_AUTH_ROLE_TOKENS_ERROR
        try:
            server.config.API_AUTH_ENABLED = True
            server.config.API_AUTH_TOKEN = ""
            server.config.API_AUTH_ROLE_TOKENS = {"viewer": "v" * 40, "editor": "e" * 40}
            server.config.API_AUTH_ROLE_TOKENS_ERROR = False
            self.assertEqual(self.client.post("/api/books", json={"title": "auth"}).status_code, 401)
            created = self.client.post("/api/books", json={"title": "auth"}, headers={"X-API-Key": "e" * 40})
            self.assertEqual(created.status_code, 201, created.text)
            deleted = self.client.delete(f"/api/books/{created.json()['id']}", headers={"X-API-Key": "e" * 40})
            self.assertEqual(deleted.status_code, 200, deleted.text)
        finally:
            server.config.API_AUTH_ENABLED = original_enabled
            server.config.API_AUTH_TOKEN = original_token
            server.config.API_AUTH_ROLE_TOKENS = original_roles
            server.config.API_AUTH_ROLE_TOKENS_ERROR = original_roles_error


if __name__ == "__main__":
    unittest.main()
