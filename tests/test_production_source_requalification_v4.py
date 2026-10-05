import json

from core.script_ir import legacy_markdown_to_script_ir
from scripts.run_production_source_requalification_audit_v4 import _selection


def test_legacy_source_projection_does_not_fabricate_dialogue():
    payload = legacy_markdown_to_script_ir(
        "## 场景一\n林晚：你来了。\n顾沉：我来了。",
        book_id=990402,
        episode=1,
    )
    assert payload["scenes"][0]["participants"]
    assert payload["scenes"][0]["dialogues"] == []


def test_v4_selection_stays_blocked_without_new_production_source():
    result = _selection(
        {"source_authority_fingerprint": "source-fp"},
        {"outcome": "SOURCE_DIALOGUE_CONFIRMED"},
    )
    assert result["status"] == "NO_SEMANTICALLY_USEFUL_CANONICAL_CANARY_TARGET"
    assert result["candidates"] == []
    assert result["provider_calls"] == 0
    assert result["blockers"]["STRUCTURED_DIALOGUE_REQUIRES_AUTHORIZATION"] == 1


def test_v4_evidence_is_json_serializable_without_credentials():
    result = _selection({"source_authority_fingerprint": "source-fp"}, {"outcome": "SOURCE_DIALOGUE_CONFIRMED"})
    encoded = json.dumps(result, ensure_ascii=False)
    assert "OPENAI_API_KEY" not in encoded
    assert "75API" not in encoded
