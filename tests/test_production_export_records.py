import json
import unittest
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from api.server import app
from models import Book, ProductionExportRecord, QAIssue, QAResult, Script, Session, StoryboardShot, init_db


class ProductionExportRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990701
        with Session() as session:
            session.query(ProductionExportRecord).filter(ProductionExportRecord.book_id == self.book_id).delete()
            session.query(QAIssue).filter(QAIssue.book_id == self.book_id).delete()
            session.query(QAResult).filter(QAResult.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(Script).filter(Script.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.add(
                Book(
                    id=self.book_id,
                    title="Export Acceptance Book",
                    filename="export-acceptance-book.txt",
                    chapter_count=1,
                    total_words=1000,
                    status="storyboarded",
                )
            )
            session.add(
                Script(
                    book_id=self.book_id,
                    episode=1,
                    content="第1场 客厅 日\n主角走进房间。",
                    word_count=20,
                    status="done",
                )
            )
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=1,
                    scene_name="客厅",
                    shot_id=1,
                    dialogue="你回来了。",
                    action_process="主角推门进入，停在门口。",
                    duration=3,
                    camera_angle="MS",
                    camera_movement="static",
                    transition="cut",
                    meta_info="{}",
                    asset_links="{}",
                    asset_status="pending",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(ProductionExportRecord).filter(ProductionExportRecord.book_id == self.book_id).delete()
            session.query(QAIssue).filter(QAIssue.book_id == self.book_id).delete()
            session.query(QAResult).filter(QAResult.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(Script).filter(Script.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_export_record_persists_and_lists_history(self):
        create_response = self.client.post(
            f"/api/books/{self.book_id}/export-records",
            json={
                "exportFormat": "json",
                "status": "completed",
                "totalShots": 12,
                "deliverableShots": 10,
                "pendingReviewShots": 2,
                "blockedShots": 1,
                "summary": "已导出第 1 版交付包",
                "metaInfo": {
                    "issues": ["镜头 1-3 待验收"],
                    "blockedShotIds": ["1-3"],
                },
            },
        )
        self.assertEqual(create_response.status_code, 200)
        payload = create_response.json()
        self.assertEqual(payload["export_format"], "json")
        self.assertEqual(payload["deliverable_shots"], 10)
        self.assertEqual(payload["meta_info"]["blockedShotIds"], ["1-3"])

        list_response = self.client.get(f"/api/books/{self.book_id}/export-records")
        self.assertEqual(list_response.status_code, 200)
        records = list_response.json()["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["summary"], "已导出第 1 版交付包")
        self.assertEqual(records[0]["pending_review_shots"], 2)
        self.assertEqual(list_response.json()["total"], 1)
        self.assertEqual(list_response.json()["returned"], 1)

    def test_export_record_list_supports_filters_search_and_pagination(self):
        now = datetime.utcnow()
        with Session() as session:
            session.add_all(
                [
                    ProductionExportRecord(
                        book_id=self.book_id,
                        export_format="delivery",
                        status="completed",
                        total_shots=10,
                        deliverable_shots=10,
                        pending_review_shots=0,
                        blocked_shots=0,
                        summary="第 1 集正式交付包",
                        meta_info=json.dumps({"episode": 1}, ensure_ascii=False),
                        created_at=now + timedelta(seconds=1),
                        updated_at=now + timedelta(seconds=1),
                    ),
                    ProductionExportRecord(
                        book_id=self.book_id,
                        export_format="delivery",
                        status="blocked",
                        total_shots=8,
                        deliverable_shots=6,
                        pending_review_shots=1,
                        blocked_shots=2,
                        summary="第 2 集 QA 阻塞快照",
                        meta_info=json.dumps({"episode": 2, "blocked_reasons": ["QA 待处理 2 项"]}, ensure_ascii=False),
                        created_at=now + timedelta(seconds=2),
                        updated_at=now + timedelta(seconds=2),
                    ),
                    ProductionExportRecord(
                        book_id=self.book_id,
                        export_format="storyboard-machine-prompt-minimax-h3-webui",
                        status="completed",
                        total_shots=1,
                        deliverable_shots=1,
                        pending_review_shots=0,
                        blocked_shots=0,
                        summary="第 1 集 · 镜头 8 · minimax-h3 WEBUI 机器提示词导出快照",
                        meta_info=json.dumps(
                            {
                                "record_type": "storyboard_machine_prompt_export",
                                "episode": 1,
                                "shot_id": 8,
                                "scene_name": "便利店",
                                "target_model": "minimax-h3",
                                "export_channel": "webui",
                                "api_submission": False,
                            },
                            ensure_ascii=False,
                        ),
                        created_at=now + timedelta(seconds=3),
                        updated_at=now + timedelta(seconds=3),
                    ),
                ]
            )
            session.commit()

        machine_response = self.client.get(
            f"/api/books/{self.book_id}/export-records",
            params={
                "record_type": "machine_prompt",
                "episode": 1,
                "query": "便利店 minimax",
                "limit": 1,
                "offset": 0,
            },
        )
        self.assertEqual(machine_response.status_code, 200)
        machine_payload = machine_response.json()
        self.assertEqual(machine_payload["total"], 1)
        self.assertEqual(machine_payload["returned"], 1)
        self.assertFalse(machine_payload["has_more"])
        self.assertEqual(machine_payload["records"][0]["meta_info"]["record_type"], "storyboard_machine_prompt_export")

        blocked_delivery_response = self.client.get(
            f"/api/books/{self.book_id}/export-records",
            params={
                "record_type": "delivery_package",
                "status": "blocked",
                "format": "交付快照",
            },
        )
        self.assertEqual(blocked_delivery_response.status_code, 200)
        blocked_delivery_payload = blocked_delivery_response.json()
        self.assertEqual(blocked_delivery_payload["total"], 1)
        self.assertEqual(blocked_delivery_payload["records"][0]["summary"], "第 2 集 QA 阻塞快照")

        paged_response = self.client.get(
            f"/api/books/{self.book_id}/export-records",
            params={
                "limit": 2,
                "offset": 0,
            },
        )
        self.assertEqual(paged_response.status_code, 200)
        paged_payload = paged_response.json()
        self.assertEqual(paged_payload["total"], 3)
        self.assertEqual(paged_payload["returned"], 2)
        self.assertTrue(paged_payload["has_more"])

    def test_export_record_is_authoritatively_blocked_by_open_qa_issue(self):
        with Session() as session:
            session.add(
                QAIssue(
                    book_id=self.book_id,
                    episode=1,
                    issue_key=f"qa-export-open-{self.book_id}",
                    severity="high",
                    issue_type="logic_gap",
                    title="仍有开放 QA",
                    description="导出前必须处理。",
                    fix_status="pending",
                    meta_info="{}",
                )
            )
            session.commit()

        response = self.client.post(
            f"/api/books/{self.book_id}/export-records",
            json={
                "exportFormat": "delivery",
                "status": "completed",
                "totalShots": 1,
                "deliverableShots": 1,
                "blockedShots": 0,
                "summary": "前端误报可交付",
                "metaInfo": {
                    "episode": 1,
                    "blocked_reasons": [],
                    "blocked_codes": [],
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "blocked")
        self.assertIn("qa_blocked", payload["meta_info"]["blocked_codes"])
        self.assertEqual(payload["meta_info"]["qa_delivery_gate"]["blocking_issue_count"], 1)
        self.assertIn("QA 待处理", payload["summary"])

    def test_export_record_falls_back_to_legacy_qa_result_when_no_workbench_issues_exist(self):
        with Session() as session:
            session.add(
                QAResult(
                    book_id=self.book_id,
                    episode=1,
                    result=json.dumps({"errors": [{"title": "legacy"}]}, ensure_ascii=False),
                    error_count=2,
                )
            )
            session.commit()

        response = self.client.post(
            f"/api/books/{self.book_id}/export-records",
            json={
                "exportFormat": "delivery",
                "status": "completed",
                "totalShots": 1,
                "deliverableShots": 1,
                "blockedShots": 0,
                "summary": "旧 QA 未同步",
                "metaInfo": {
                    "episode": 1,
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["meta_info"]["qa_delivery_gate"]["blocking_issue_count"], 2)
        self.assertEqual(payload["meta_info"]["qa_delivery_gate"]["legacy_error_count"], 2)

    def test_export_record_allows_wont_fix_qa_issue(self):
        with Session() as session:
            session.add(
                QAIssue(
                    book_id=self.book_id,
                    episode=1,
                    issue_key=f"qa-export-wont-fix-{self.book_id}",
                    severity="high",
                    issue_type="logic_gap",
                    title="已人工豁免 QA",
                    description="制片负责人接受该风险。",
                    fix_status="pending",
                    meta_info=json.dumps({"workflow_status": "wont_fix"}, ensure_ascii=False),
                )
            )
            session.commit()

        response = self.client.post(
            f"/api/books/{self.book_id}/export-records",
            json={
                "exportFormat": "delivery",
                "status": "completed",
                "totalShots": 1,
                "deliverableShots": 1,
                "blockedShots": 0,
                "summary": "已放行交付",
                "metaInfo": {
                    "episode": 1,
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["meta_info"]["qa_delivery_gate"]["blocking_issue_count"], 0)
        self.assertEqual(payload["meta_info"]["qa_delivery_gate"]["resolved_count"], 1)

    def test_export_pdf_endpoint_returns_pdf_bytes(self):
        response = self.client.get(f"/api/books/{self.book_id}/export-pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertIn(".pdf", response.headers.get("content-disposition", ""))
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_export_pdf_endpoint_blocks_open_qa_issue(self):
        with Session() as session:
            session.add(
                QAIssue(
                    book_id=self.book_id,
                    episode=1,
                    issue_key=f"qa-pdf-open-{self.book_id}",
                    severity="medium",
                    issue_type="logic_gap",
                    title="PDF 导出阻塞",
                    description="仍有 QA 待处理。",
                    fix_status="rechecking",
                    meta_info="{}",
                )
            )
            session.commit()

        response = self.client.get(f"/api/books/{self.book_id}/export-pdf?episode=1")
        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertEqual(payload["detail"]["code"], "qa_blocked")
        self.assertEqual(payload["detail"]["qa_delivery_gate"]["blocking_issue_count"], 1)

    def test_export_pdf_endpoint_accepts_episode_scope(self):
        with Session() as session:
            session.add(
                Script(
                    book_id=self.book_id,
                    episode=2,
                    content="第二集剧本",
                    word_count=10,
                    status="done",
                )
            )
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=2,
                    scene_name="后院",
                    shot_id=2,
                    dialogue="第二集对白",
                    action_process="角色走向后院",
                    duration=4,
                    camera_angle="CU",
                    camera_movement="push-in",
                    transition="cut",
                    meta_info="{}",
                    asset_links="{}",
                    asset_status="pending",
                )
            )
            session.commit()

        response = self.client.get(f"/api/books/{self.book_id}/export-pdf?episode=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertIn("episode-2", response.headers.get("content-disposition", ""))
        self.assertTrue(response.content.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
