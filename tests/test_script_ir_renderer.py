from core.script_renderer import render_script_markdown


def test_renderer_is_stable_for_empty_optional_fields():
    payload = {"schema_version": "script_ir_v1", "episode": 2, "scenes": [{"name": "走廊", "location_name": "走廊", "beats": []}]}
    assert render_script_markdown(payload) == "# 第2集\n\n## 场景 1：走廊\n"
