from core.storyboard_materializer import materialize_storyboard_from_shot_plan


def test_materializer_has_one_to_one_plan_mapping():
    plan = {"scene_name": "走廊", "shots": [{"plan_shot_id": "S01", "event": "停下"}, {"plan_shot_id": "S02", "event": "回头"}]}
    result = materialize_storyboard_from_shot_plan(plan)
    assert [item["plan_shot_id"] for item in result] == ["S01", "S02"]
    assert len(result) == len(plan["shots"])

