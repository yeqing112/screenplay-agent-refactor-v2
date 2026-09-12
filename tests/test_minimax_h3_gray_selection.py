import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate-minimax-h3-gray.py"
SPEC = importlib.util.spec_from_file_location("validate_minimax_h3_gray", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self.rows)


class _Session:
    def __init__(self, books, shots):
        self.books = books
        self.shots = shots

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def query(self, model):
        if model is MODULE.Book:
            return _Query(self.books)
        return _Query(self.shots)


class MinimaxH3GraySelectionTests(unittest.TestCase):
    def test_storage_publish_requires_separate_confirmation(self):
        self.assertTrue(MODULE.storage_publish_is_confirmed(False))
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("MINIMAX_H3_STORAGE_CONFIRM", None)
            self.assertFalse(MODULE.storage_publish_is_confirmed(True))
            os.environ["MINIMAX_H3_STORAGE_CONFIRM"] = MODULE.STORAGE_CONFIRMATION_TOKEN
            self.assertTrue(MODULE.storage_publish_is_confirmed(True))

    def test_reference_publish_forwards_explicit_unstable_gray_opt_in(self):
        source = {
            "reference_asset_id": "ref-local",
            "image_url": "/api/prototyping/manual-media/local.png",
        }
        published = SimpleNamespace(
            ok=True,
            public_url="http://temporary.hn-bkt.clouddn.com/signed.png?e=1&token=t",
            to_dict=lambda: {
                "ok": True,
                "source_url": source["image_url"],
                "public_url": "http://temporary.hn-bkt.clouddn.com/signed.png?e=1&token=t",
            },
        )
        with patch.object(MODULE, "ensure_provider_accessible_url", return_value=published) as publish:
            ready, public_assets = MODULE.provider_ready_reference_images(
                [source],
                publish=True,
                key_prefix="gray-test",
                allow_unstable_storage=True,
            )

        self.assertEqual(len(ready), 1)
        self.assertEqual(len(public_assets), 1)
        self.assertTrue(ready[0]["image_url"].startswith("http://temporary.hn-bkt.clouddn.com/"))
        self.assertTrue(publish.call_args.kwargs["force_storage"])
        self.assertTrue(publish.call_args.kwargs["allow_unstable_storage"])

    def test_preflight_does_not_publish_without_storage_confirmation(self):
        args = SimpleNamespace(
            book_id=990400,
            episode=1,
            shot_id=1,
            model_profile_id="",
            duration_seconds=None,
            aspect_ratio="16:9",
            first_frame_asset_id="",
            use_reference_images=True,
            publish_reference_images=True,
            allow_unstable_public_assets=True,
            use_first_frame=False,
            publish_first_frame=False,
            allow_real=False,
        )
        book = SimpleNamespace(title="gray")
        shot = SimpleNamespace(duration=6, scene_name="scene")
        export = {
            "reference_images": [{"reference_asset_id": "ref-local", "image_url": "/local.png"}],
            "model_exports": {"minimax-h3": {"fields": {"integrated_multimodal_description": "valid prompt"}}},
        }
        profile = {
            "id": "h3-test",
            "provider": "minimax-h3-async",
            "model_name": "MiniMax-H3",
            "base_url": "https://provider.example",
            "api_key": "real-test-key",
            "enabled": True,
        }
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MINIMAX_H3_STORAGE_CONFIRM", None)
            with patch.object(MODULE, "load_storyboard_target", return_value=(book, shot)), patch.object(
                MODULE, "load_machine_prompt_export", return_value=export
            ), patch.object(MODULE, "effective_video_profile", return_value=(profile, "")), patch.object(
                MODULE, "public_asset_storage_enabled", return_value=True
            ), patch.object(MODULE, "provider_ready_reference_images", return_value=([], [])) as publish:
                report = MODULE.build_preflight_report(args, client=None)

        self.assertFalse(publish.call_args.kwargs["publish"])
        self.assertIn("reference_publish_requires_storage_confirmation", report["readiness"]["blockers"])
        self.assertFalse(report["submission"]["storage_publish_performed"])

    def test_active_registry_is_the_default_candidate_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "production-sample-registry.json"
            registry.write_text(json.dumps({"active_book_ids": [990400, 990400, "bad", -1]}), encoding="utf-8")
            with patch.object(MODULE, "SAMPLE_REGISTRY_PATH", registry):
                self.assertEqual(MODULE.load_active_sample_book_ids(), [990400])
                self.assertEqual(MODULE.resolve_candidate_book_ids([]), [990400])
                self.assertEqual(MODULE.resolve_candidate_book_ids([990301]), [990301])

    def test_auto_selection_does_not_scan_retired_books(self):
        active_book = SimpleNamespace(id=990400, title="active")
        retired_book = SimpleNamespace(id=990301, title="retired")
        active_shot = SimpleNamespace(
            book_id=990400,
            episode=1,
            shot_id=1,
            scene_name="scene",
            asset_links=json.dumps({"images": [{"id": "img", "uri": "https://cdn.example/active.png", "adopted": True}]}),
        )
        retired_shot = SimpleNamespace(
            book_id=990301,
            episode=1,
            shot_id=1,
            scene_name="retired",
            asset_links=json.dumps({"images": [{"id": "img", "uri": "https://cdn.example/retired.png", "adopted": True}]}),
        )
        # The fake query models the database filter that receives the resolved
        # registry scope; a retired row is present in the database but is not
        # returned for the active-book query.
        session = _Session([active_book], [active_shot])
        with patch.object(MODULE, "load_active_sample_book_ids", return_value=[990400]), patch.object(MODULE, "Session", return_value=session):
            selected = MODULE.select_gray_candidate([], client=None)
        self.assertEqual(selected["book_id"], 990400)
        self.assertEqual(selected["candidate_count"], 1)


if __name__ == "__main__":
    unittest.main()
