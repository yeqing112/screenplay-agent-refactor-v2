from api.server import _build_motion_prompt_contract, _render_motion_contract_fallback


def test_motion_contract_projects_nested_shot_ir_for_candidate_review():
    contract = _build_motion_prompt_contract({
        "shot_ir": {
            "continuity_in": "角色推门进入阁楼，马灯扫过地面。",
            "camera_movement": "static",
            "action_beats": [
                {"start": 0, "end": 2, "action": "老周提灯跨过门槛。"},
                {"start": 2, "end": 4, "action": "林晚跟随进入并看向落地钟。"},
            ],
            "continuity_out": "老周停在落地钟旁，林晚站在侧后方。",
        },
    })

    assert contract["camera"] == "static"
    assert [item["action"] for item in contract["action_beats"]] == [
        "老周提灯跨过门槛。",
        "林晚跟随进入并看向落地钟。",
    ]
    prompt = _render_motion_contract_fallback(contract)
    assert "固定机位" in prompt
    assert "老周提灯跨过门槛" in prompt
    assert "林晚跟随进入并看向落地钟" in prompt


def test_motion_contract_projects_legacy_description_action_beats():
    contract = _build_motion_prompt_contract({
        "shot_ir": {
            "continuity_in": "林晚站在铁门前。",
            "camera_movement": "static",
            "action_beats": [
                {"sequence": 1, "description": "林晚伸手推开铁门。"},
            ],
            "continuity_out": "铁门向内打开。",
        },
    })

    assert [item["action"] for item in contract["action_beats"]] == ["林晚伸手推开铁门。"]
    assert "林晚伸手推开铁门" in _render_motion_contract_fallback(contract)


def test_motion_contract_fallback_sanitizes_bracketed_action_beats():
    contract = {
        "camera": "static",
        "start_state": "林晚站在门口。",
        "action_beats": [{"action": "[动作开始：林晚缓慢抬头，确认门内动静。]"}],
        "end_state": "林晚停在门槛前。",
    }

    prompt = _render_motion_contract_fallback(contract)

    assert "[" not in prompt
    assert "]" not in prompt
    assert "林晚缓慢抬头" in prompt
