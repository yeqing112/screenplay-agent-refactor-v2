import json
import unittest

from api.generation_adapters import build_task_adapter_asset
from api.server import _adopt_asset_version, _save_asset_to_storyboard
from models import Session, StoryboardShot, init_db


class CreativeTaskPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
      init_db()

    def setUp(self):
        self.book_id = 990001
        self.episode = 1
        self.shot_id = 1
        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=self.episode,
                    scene_name='测试场景',
                    shot_id=self.shot_id,
                    dialogue='测试对白',
                    asset_links='{}',
                    asset_status='pending',
                ),
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.commit()

    def test_build_task_adapter_asset_includes_traceability_metadata(self):
        asset = build_task_adapter_asset(
            kind='image',
            title='分镜图 1 v1',
            prompt='夜景街道，人物回头望向身后。',
            model_name='fake-image-model',
            source_asset_id='ref-image-1',
            asset_scope='shot',
            asset_subject='1',
            aspect_ratio='16:9',
            duration_seconds=0,
            reference_asset_ids=['ref-a', 'ref-b'],
            reference_images=[{"reference_asset_id": "ref-a", "image_url": "https://example.com/ref-a.png"}],
            shot_id='1',
            source_node_id='shot-1',
            model_profile_id='stage9-image-fake',
            provider='openai-compatible',
            source='real',
            preview_url='https://example.com/image-v1.png',
        )

        self.assertEqual(asset['metadata']['provider'], 'openai-compatible')
        self.assertEqual(asset['metadata']['modelProfileId'], 'stage9-image-fake')
        self.assertEqual(asset['metadata']['modelName'], 'fake-image-model')
        self.assertEqual(asset['metadata']['sourceNodeId'], 'shot-1')
        self.assertEqual(asset['metadata']['sourceAssetId'], 'ref-image-1')
        self.assertEqual(asset['metadata']['prompt'], '夜景街道，人物回头望向身后。')
        self.assertEqual(asset['metadata']['referenceImages'][0]['reference_asset_id'], 'ref-a')
        self.assertIn('createdAt', asset['metadata'])
        self.assertFalse(asset['metadata']['usesMock'])

    def test_save_asset_to_storyboard_persists_images_and_adoption_switch(self):
        first = build_task_adapter_asset(
            kind='image',
            title='分镜图 1 v1',
            prompt='第一版提示词',
            model_name='mock-image-v1',
            source_asset_id='',
            asset_scope='shot',
            asset_subject='1',
            aspect_ratio='16:9',
            duration_seconds=0,
            reference_asset_ids=[],
            reference_images=[],
            shot_id='1',
            source_node_id='shot-1',
            model_profile_id='builtin-mock-image',
            provider='prototype-task-adapter',
            source='mock',
            preview_url='https://example.com/mock-v1.png',
        )
        first['label'] = 'v1'
        _save_asset_to_storyboard(self.book_id, self.episode, '1', 'image', first)

        second = build_task_adapter_asset(
            kind='image',
            title='分镜图 1 v2',
            prompt='第二版提示词',
            model_name='fake-image-model',
            source_asset_id='',
            asset_scope='shot',
            asset_subject='1',
            aspect_ratio='16:9',
            duration_seconds=0,
            reference_asset_ids=['ref-a'],
            reference_images=[{"reference_asset_id": "ref-a", "image_url": "https://example.com/ref-a.png"}],
            shot_id='1',
            source_node_id='shot-1',
            model_profile_id='stage9-image-fake',
            provider='openai-compatible',
            source='real',
            preview_url='https://example.com/real-v2.png',
        )
        second['label'] = 'v2'
        _save_asset_to_storyboard(self.book_id, self.episode, '1', 'image', second)

        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            self.assertIsNotNone(shot)
            payload = json.loads(shot.asset_links)
            self.assertEqual(shot.asset_status, 'asset_ready')
            self.assertEqual(len(payload['images']), 2)
            self.assertFalse(payload['images'][0]['adopted'])
            self.assertTrue(payload['images'][1]['adopted'])
            self.assertEqual(payload['images'][1]['metadata']['modelProfileId'], 'stage9-image-fake')
            self.assertEqual(payload['images'][1]['metadata']['provider'], 'openai-compatible')
            self.assertEqual(payload['images'][1]['metadata']['sourceNodeId'], 'shot-1')

        _adopt_asset_version(self.book_id, self.episode, '1', 'image', first['id'])

        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            payload = json.loads(shot.asset_links)
            adopted_flags = {item['id']: item.get('adopted') for item in payload['images']}
            self.assertTrue(adopted_flags[first['id']])
            self.assertFalse(adopted_flags[second['id']])


if __name__ == '__main__':
    unittest.main()
