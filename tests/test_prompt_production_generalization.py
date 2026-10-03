import json
from pathlib import Path

from core.prompt_production import build_context, compare_semantic_pair, render_image_prompt, render_video_prompt, validate_projection, validate_semantic_integrity


def test_independent_book75_fixture_produces_both_prompt_surfaces():
    fixture = json.loads((Path(__file__).parent / "fixtures/prompt-production/independent-book75.json").read_text(encoding="utf-8"))
    authority = {"characters": fixture["characters"], "scenes": fixture["scenes"], "props": fixture["props"], "visual_style": fixture["visual_style"]}
    for index, shot in enumerate(fixture["shots"], 1):
        ir = {"scene_id": shot["scene_id"], "plan_shot_id": shot["plan_shot_id"], "storyboard_shot_id": index, "subjects": [{"subject_ref": x} for x in shot["subjects"]], "props": [{"prop_ref": x} for x in shot["props"]], "camera": shot["camera"], "action": {"action_beats": shot["action_beats"]}, "continuity": {"screen_side_assignments": {}, "look_direction": {}}}
        plan = {"scene_id": shot["scene_id"], "subjects": shot["subjects"], "exit_state": shot["ending_state"]}
        direction = {"subjects": shot["subjects"], "camera": shot["camera"], "action_beats": shot["action_beats"], "ending_state": shot["ending_state"]}
        image_ctx = build_context(ir, shot_plan=plan, shot_direction=direction, authority=authority, shot_number=index, book_id=75, episode=1)
        video_ctx = build_context(ir, shot_plan=plan, shot_direction=direction, authority=authority, shot_number=index, book_id=75, episode=1)
        image, video = render_image_prompt(image_ctx), render_video_prompt(video_ctx)
        assert validate_semantic_integrity(image_ctx) == []
        assert compare_semantic_pair(image_ctx, video_ctx) == []
        assert validate_projection(image) == []
        assert validate_projection(video) == []
        assert image["language"] == video["language"] == "zh-CN"
        assert image["prompt"] != video["prompt"]
        assert all(ref["status"] == "LOCKED" and ref["stale_status"] == "FRESH" for ref in video["reference_bindings"])
