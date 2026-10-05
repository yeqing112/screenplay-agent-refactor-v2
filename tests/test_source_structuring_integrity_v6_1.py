from __future__ import annotations

import ast

from core.source_structuring_v3 import (
    AUTHORITY_LATTICE,
    SCHEMA_VERSION_V3_1,
    SOURCE_FORM_SPEAKER_LABELED,
    SOURCE_FORM_STRUCTURED_DIALOGUE_BLOCK,
    SourceStructuringPolicy,
    ground_candidate_v3,
    reconcile_candidate_v3,
)
from scripts.source_structuring_scanner import scan_source_text


def _candidate(raw: str, dialogue: dict, *, label: str = "") -> dict:
    return {"schema_version": SCHEMA_VERSION_V3_1, "scenes": [{
        "scene_evidence": [raw], "display_label": label,
        "participants": [{"name": dialogue["speaker"], "evidence": [raw]}],
        "actions": [], "dialogues": [dialogue],
    }], "unknowns": []}


def test_semantic_scanner_detects_literal_escape_concat_arithmetic_and_fstring() -> None:
    source = '''\nraw = "\\u987e\\u6c89"\njoined = "顾" + "沉"\nnumber = 990000 + 402\nprefix = "CH"\ncode = f"{prefix}03"\n'''
    hits = scan_source_text(source)
    assert {hit["token"] for hit in hits} >= {"顾沉", "990402", "CH03"}


def test_semantic_scanner_clean_generic_source() -> None:
    assert scan_source_text('speaker = "MAYA"\nline = f"{speaker}: Stay here."\n') == []


def test_display_label_is_unresolved_without_explicit_caller_authorization() -> None:
    raw = "雨停了。"
    candidate = {"schema_version": SCHEMA_VERSION_V3_1, "scenes": [{"scene_evidence": [raw], "display_label": "车站重逢", "participants": [], "actions": [{"text": raw, "source_evidence": raw}], "dialogues": []}], "unknowns": []}
    grounded = ground_candidate_v3(raw, candidate)
    assert grounded["status"] == "PASS"
    scene = grounded["grounded_candidate"]["scenes"][0]
    assert scene["display_label"] == ""
    assert scene["display_label_authority"] == "UNRESOLVED"
    assert scene["untrusted_display_label"] == "车站重逢"
    candidate["scenes"][0]["display_label_authority"] = "AUTHORIZED_SEMANTIC_LABEL"
    authorized = ground_candidate_v3(raw, candidate, policy=SourceStructuringPolicy(authorize_semantic_display_label=True))
    assert authorized["grounded_candidate"]["scenes"][0]["display_label_authority"] == "AUTHORIZED_SEMANTIC_LABEL"


def test_reconciliation_never_upgrades_label_authority() -> None:
    raw = "雨停了。"
    candidate = {"schema_version": SCHEMA_VERSION_V3_1, "scenes": [{"display_label": "模型标签", "display_label_authority": "UNTRUSTED_MODEL_OUTPUT", "participants": [], "actions": [], "dialogues": []}], "unknowns": []}
    result = reconcile_candidate_v3(raw, candidate)
    entry = result["transformation_journal"][0]
    assert entry["authority_delta"] == "DOWNGRADE"
    assert entry["authority_after"] == "UNRESOLVED"
    assert all(item["authority_delta"] != "UPGRADE" for item in result["transformation_journal"])
    assert AUTHORITY_LATTICE.index("UNRESOLVED") < AUTHORITY_LATTICE.index("SOURCE_FACT")


def test_speaker_labeled_chinese_and_english_forms() -> None:
    for raw, speaker, text in (("顾问甲：门已经锁了。", "顾问甲", "门已经锁了。"), ("MAYA: Stay here.", "MAYA", "Stay here.")):
        result = ground_candidate_v3(raw, _candidate(raw, {"speaker": speaker, "text": text, "utterance_evidence": [raw], "speaker_identity_evidence": [raw], "binding_type": "SOURCE_LITERAL"}))
        assert result["status"] == "PASS", result
        assert result["grounded_candidate"]["scenes"][0]["dialogues"][0]["source_form"] == SOURCE_FORM_SPEAKER_LABELED


def test_structured_dialogue_block_is_explicit_and_coreference_stays_semantic() -> None:
    raw = "MAYA says: Stay here."
    dialogue = {"speaker": "MAYA", "text": "Stay here.", "source_form": SOURCE_FORM_STRUCTURED_DIALOGUE_BLOCK, "utterance_evidence": [raw], "speaker_identity_evidence": [raw], "binding_type": "COREFERENCE_RESOLUTION"}
    result = ground_candidate_v3(raw, _candidate(raw, dialogue))
    assert result["status"] == "PASS", result
    grounded = result["grounded_candidate"]["scenes"][0]["dialogues"][0]
    assert grounded["binding_classification"] == "AUTHORIZED_SEMANTIC_BINDING"


def test_repeated_action_requires_context_and_resolves_distinct_occurrences() -> None:
    raw = "门开了。随后灯亮。门开了。"
    candidate = {"schema_version": SCHEMA_VERSION_V3_1, "scenes": [{"scene_evidence": [raw], "participants": [], "actions": [
        {"text": "门开了。", "source_evidence": "门开了。随后灯亮。"},
        {"text": "门开了。", "source_evidence": "灯亮。门开了。"},
    ], "dialogues": []}], "unknowns": []}
    result = ground_candidate_v3(raw, candidate)
    assert result["status"] == "PASS", result
    starts = [item["source_evidence"]["char_start"] for item in result["grounded_candidate"]["scenes"][0]["actions"]]
    assert starts == [0, 9]


def test_no_tautological_assertions_in_integrity_tests() -> None:
    path = __file__
    tree = ast.parse(open(path, encoding="utf-8").read())
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name):
            if len(node.test.comparators) == 1 and isinstance(node.test.comparators[0], ast.Name) and node.test.left.id == node.test.comparators[0].id:
                violations.append(node.lineno)
    assert violations == []
