import json
import asyncio
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api import server
from api.server import CreativeGenerationRequest, app
from core.video_continuity import normalize_video_capabilities, resolve_video_continuity_strategy
from core.transition_frame_extraction import extract_transition_frame
from models import Session, StoryboardShot, StoryboardTransitionContract, StoryboardTransitionFrame, StoryboardTransitionContinuityReview, StoryboardVideoRetryAttempt, TaskRun, init_db


class VideoContinuityStrategyTests(unittest.TestCase):
    def test_h3_strict_mode_omits_references_instead_of_silently_overriding_frame(self):
        result = resolve_video_continuity_strategy(
            contract={"continuity_level": "strict", "status": "confirmed"},
            transition_frame={"status": "locked", "public_url": "https://cdn.example/frame.png"},
            model_profile={"provider": "minimax-h3-async", "default_params": {}},
            reference_images=[{"image_url": "https://cdn.example/reference.png"}],
        )
        self.assertEqual(result["strategy"], "strict_first_frame")
        self.assertEqual(result["first_frame_url"], "https://cdn.example/frame.png")
        self.assertEqual(result["reference_images"], [])
        self.assertIn("reference-images-omitted-because-keyframe-mode-is-mutually-exclusive", result["warnings"])
        self.assertFalse(result["capability_snapshot"]["reference_and_keyframe_compatible"])

    def test_strict_mode_requires_confirmed_contract_and_locked_public_frame(self):
        result = resolve_video_continuity_strategy(
            contract={"continuity_level": "strict", "status": "draft"},
            transition_frame={"status": "candidate", "public_url": ""},
            model_profile={"default_params": {"video_capabilities": {"first_frame": True}}},
            reference_images=[],
        )
        self.assertEqual(result["strategy"], "strict_first_frame")
        self.assertEqual(
            result["blocking_issues"],
            [
                "strict-continuity-requires-confirmed-contract",
                "strict-continuity-requires-locked-transition-frame",
                "strict-continuity-requires-provider-accessible-transition-frame",
            ],
        )

    def test_unknown_provider_is_conservative(self):
        capabilities = normalize_video_capabilities({"provider": "future-video", "default_params": {}})
        self.assertFalse(capabilities["first_frame"])
        self.assertEqual(capabilities["evidence_status"], "pending_field_verification")

    def test_confirmed_soft_contract_is_compiled_into_provider_prompt(self):
        prompt = server._append_video_continuity_contract_to_prompt(
            "Base H3 prompt.",
            {
                "continuity_level": "soft",
                "contract": {
                    "status": "confirmed",
                    "continuity_level": "soft",
                    "entry_state": "人物仍在门口光柱内",
                    "exit_state": "人物保持紧张状态",
                    "inherit_rules": {"identity": "preserve face and costume"},
                    "allowed_changes": ["cut to close-up"],
                    "forbidden_changes": ["identity drift"],
                },
            },
        )
        self.assertIn("Confirmed soft continuity contract", prompt)
        self.assertIn("人物仍在门口光柱内", prompt)
        self.assertIn("preserve face and costume", prompt)
        self.assertIn("identity drift", prompt)

    def test_extraction_uses_a_deterministic_near_last_timestamp_and_checksum(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "source.mp4"
            output = root / "frame.png"
            video.write_bytes(b"not-a-real-video")

            def fake_run(command):
                if "ffprobe" in Path(command[0]).name:
                    return CompletedProcess(command, 0, '{"format":{"duration":"4.000"}}', "")
                # Minimal valid 1920x1080 PNG header: the production extractor
                # reads dimensions from IHDR instead of relying on a UI guess.
                Path(command[-1]).write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR\x00\x00\x07\x80\x00\x00\x04\x38" + b"png-frame-content")
                return CompletedProcess(command, 0, "", "")

            with patch("core.transition_frame_extraction.shutil.which", side_effect=lambda name: name), patch(
                "core.transition_frame_extraction._run", side_effect=fake_run
            ):
                result = extract_transition_frame(video, output, frame_kind="near_last")

        self.assertEqual(result["frame_time_ms"], 3880)
        self.assertEqual(result["frame_kind"], "near_last")
        self.assertEqual((result["width"], result["height"]), (1920, 1080))
        self.assertEqual(len(str(result["checksum"])), 64)


class VideoContinuityApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990499
        self.episode = 1
        with Session() as session:
            session.query(StoryboardTransitionFrame).filter(StoryboardTransitionFrame.book_id == self.book_id).delete()
            session.query(StoryboardTransitionContinuityReview).filter(StoryboardTransitionContinuityReview.book_id == self.book_id).delete()
            session.query(StoryboardTransitionContract).filter(StoryboardTransitionContract.book_id == self.book_id).delete()
            session.query(StoryboardVideoRetryAttempt).filter(StoryboardVideoRetryAttempt.book_id == self.book_id).delete()
            session.query(TaskRun).filter(TaskRun.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.add_all([
                StoryboardShot(
                    book_id=self.book_id,
                    episode=self.episode,
                    shot_id=10,
                    scene_name="room",
                    end_state="人物停在门边",
                    asset_links=json.dumps({"videos": [{"id": "video-10", "uri": "https://cdn.example/source.mp4", "adopted": True}]}),
                    # ``passed`` is the status persisted by the acceptance
                    # record endpoint and must be accepted by the handoff gate.
                    meta_info=json.dumps({"acceptance": {"status": "passed"}}),
                ),
                StoryboardShot(book_id=self.book_id, episode=self.episode, shot_id=20, scene_name="room", start_state="人物仍在门边"),
            ])
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(StoryboardTransitionFrame).filter(StoryboardTransitionFrame.book_id == self.book_id).delete()
            session.query(StoryboardTransitionContinuityReview).filter(StoryboardTransitionContinuityReview.book_id == self.book_id).delete()
            session.query(StoryboardTransitionContract).filter(StoryboardTransitionContract.book_id == self.book_id).delete()
            session.query(StoryboardVideoRetryAttempt).filter(StoryboardVideoRetryAttempt.book_id == self.book_id).delete()
            session.query(TaskRun).filter(TaskRun.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.commit()

    def test_failed_video_records_frozen_inputs_and_only_retries_after_explicit_confirmation(self):
        task_id = "continuity-failed-video"
        req = CreativeGenerationRequest(
            book_id=self.book_id,
            episode=self.episode,
            shot_id="20",
            source_node_id="test-continuity-retry",
            prompt="keep the locked handoff frame",
            model_profile_id="mock-video",
            first_frame_asset_id="transition-frame-1",
            first_frame_url="https://cdn.example/handoff.png",
            duration_seconds=4,
            simulate_error=True,
        )
        profile = {"id": "mock-video", "provider": "prototype-task-adapter", "model_name": "mock-video", "enabled": True}
        server._creative_tasks[task_id] = {
            "task_id": task_id, "kind": "video", "target_kind": "video", "status": "queued", "progress": 0,
            "book_id": self.book_id, "episode": self.episode, "shot_id": "20", "version": 1,
            "model_profile_id": "mock-video", "provider": "prototype-task-adapter", "continuity": {},
        }
        server._store_creative_task_request(server._creative_tasks[task_id], req, "video")
        with patch("api.server.resolve_generation_profile", return_value=profile), patch("api.server.asyncio.sleep", new=AsyncMock(return_value=None)):
            asyncio.run(server._run_creative_task(task_id, "video", req))

            with Session() as session:
                record = session.query(StoryboardVideoRetryAttempt).filter_by(source_task_id=task_id).first()
                self.assertIsNotNone(record)
                self.assertEqual(record.status, "failed")
                snapshot = json.loads(record.input_snapshot)
                self.assertEqual(snapshot["request_payload"]["first_frame_url"], "https://cdn.example/handoff.png")
                self.assertEqual(snapshot["request_payload"]["duration_seconds"], 4)
                retry_id = record.id

            endpoint = f"/api/books/{self.book_id}/storyboard/{self.episode}/20/video-retry-attempts/{retry_id}/confirm"
            denied = self.client.post(endpoint, json={"confirmed": True, "allowWrite": True})
            self.assertEqual(denied.status_code, 400)
            submitted = self.client.post(endpoint, json={
                "confirmed": True, "allowWrite": True, "confirmationToken": "CONFIRM_FIXED_VIDEO_RETRY",
            })
            self.assertEqual(submitted.status_code, 200)
            self.assertTrue(submitted.json()["retry_task_id"])
            self.assertFalse(submitted.json()["automatic_retry"])

        with Session() as session:
            records = session.query(StoryboardVideoRetryAttempt).filter_by(retry_root_task_id=task_id).order_by(StoryboardVideoRetryAttempt.attempt_number).all()
            self.assertEqual([row.attempt_number for row in records], [1, 2])
            self.assertEqual(records[0].status, "submitted")
            self.assertEqual(records[1].status, "failed")

    def test_draft_is_read_only_and_confirmation_registers_versioned_contract(self):
        base = f"/api/books/{self.book_id}/storyboard/{self.episode}/20/transition-contract"
        draft = self.client.post(f"{base}/draft")
        self.assertEqual(draft.status_code, 200)
        self.assertFalse(draft.json()["mutated"])
        self.assertEqual(draft.json()["draft"]["source_shot_id"], 10)

        denied = self.client.post(f"{base}/confirm", json={"sourceShotId": 10, "continuityLevel": "strict"})
        self.assertEqual(denied.status_code, 409)
        confirmed = self.client.post(f"{base}/confirm", json={
            "sourceShotId": 10,
            "continuityLevel": "strict",
            "confirmed": True,
            "allowWrite": True,
        })
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["contract"]["status"], "confirmed")

    def test_first_shot_continuity_reads_are_explicit_no_ops(self):
        base = f"/api/books/{self.book_id}/storyboard/{self.episode}/10"
        contract = self.client.get(f"{base}/transition-contract")
        state = self.client.get(f"{base}/transition-state")

        self.assertEqual(contract.status_code, 200)
        self.assertTrue(contract.json()["not_applicable"])
        self.assertEqual(contract.json()["reason"], "first_shot")
        self.assertEqual(state.status_code, 200)
        self.assertTrue(state.json()["not_applicable"])
        self.assertEqual(state.json()["frames"], [])

    def test_replaced_source_video_marks_handoff_evidence_stale_without_deleting_history(self):
        with Session() as session:
            session.add(StoryboardTransitionContract(
                book_id=self.book_id, episode=self.episode, source_shot_id=10, target_shot_id=20,
                continuity_level="strict", status="confirmed",
            ))
            session.add(StoryboardTransitionFrame(
                book_id=self.book_id, episode=self.episode, source_shot_id=10, target_shot_id=20,
                source_video_asset_id="video-from-older-cut", public_url="https://cdn.example/old.png", status="locked",
            ))
            session.commit()

        response = self.client.get(f"/api/books/{self.book_id}/storyboard/{self.episode}/20/transition-state")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["readiness"]["status"], "stale")
        self.assertEqual(payload["frames"][0]["evidence_status"], "stale")

        overview = self.client.get(f"/api/books/{self.book_id}/storyboard/{self.episode}/transition-overview")
        self.assertEqual(overview.status_code, 200)
        item = next(row for row in overview.json()["items"] if row["shot_id"] == 20)
        self.assertEqual(item["label"], "需重新检查")

    def test_frame_cannot_lock_without_explicit_confirmation(self):
        frames = f"/api/books/{self.book_id}/storyboard/{self.episode}/20/transition-frames"
        created = self.client.post(frames, json={
            "sourceShotId": 10,
            "publicUrl": "https://cdn.example/handoff.png",
            "confirmed": True,
            "allowWrite": True,
        })
        self.assertEqual(created.status_code, 200)
        frame_id = created.json()["frame"]["id"]
        denied = self.client.patch(f"{frames}/{frame_id}", json={"status": "locked"})
        self.assertEqual(denied.status_code, 409)
        locked = self.client.patch(f"{frames}/{frame_id}", json={"status": "locked", "confirmed": True, "allowWrite": True})
        self.assertEqual(locked.status_code, 200)
        self.assertEqual(locked.json()["frame"]["status"], "locked")

    def test_extraction_requires_confirmation_before_accessing_source_video(self):
        response = self.client.post(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/20/transition-frames/extract",
            json={"sourceShotId": 10},
        )
        self.assertEqual(response.status_code, 409)

    def test_confirmed_extraction_persists_candidate_but_never_locks_it(self):
        def fake_extract(_source, output, **_kwargs):
            output.write_bytes(b"handoff-frame")
            return {
                "checksum": "a" * 64,
                "frame_time_ms": 3880,
                "width": 1920,
                "height": 1080,
                "local_path": str(output),
                "extraction_profile": {"extractor": "ffmpeg", "frame_kind": "near_last"},
            }

        storage_result = SimpleNamespace(
            ok=True,
            public_url="https://cdn.example/transition.png",
            object_key="transition.png",
            storage_provider="qiniu",
            uploaded=True,
        )
        with TemporaryDirectory() as temp_dir, patch("api.server.public_asset_storage_enabled", return_value=True), patch(
            "api.server._load_source_bytes", return_value=(b"video", "video/mp4")
        ), patch("api.server.extract_transition_frame", side_effect=fake_extract), patch(
            "api.server.ensure_provider_accessible_url", return_value=storage_result
        ), patch("api.server.config.UPLOAD_DIR", Path(temp_dir)):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/20/transition-frames/extract",
                json={"sourceShotId": 10, "confirmed": True, "allowWrite": True},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["mutated"])
        self.assertEqual(payload["frame"]["status"], "candidate")
        self.assertEqual(payload["frame"]["public_url"], "https://cdn.example/transition.png")
        self.assertEqual((payload["frame"]["width"], payload["frame"]["height"]), (1920, 1080))


if __name__ == "__main__":
    unittest.main()
