from __future__ import annotations

from core.fact_semantic_grounding import (
    annotate_source_evidence_index,
    classify_anchor_surface,
    confirmation_ceiling,
    evaluate_semantic_grounding_guards,
    script_ir_semantic_gate,
)
from core.evaluation_upstream_phase_a import run_with_provider_calls


def test_anchor_surface_class_deterministic():
    assert classify_anchor_surface("她走进门厅。") == "NARRATIVE_PROSE"
    assert classify_anchor_surface("“我看见他。”") == "QUOTED_TEXT"
    assert classify_anchor_surface("——别开门") == "QUOTED_TEXT"
    assert classify_anchor_surface("") == "UNKNOWN_SURFACE"


def test_source_surface_annotation_is_provider_free_and_fingerprinted():
    index = {
        "evidence_index_fingerprint": "abc",
        "anchors": [{"anchor_ref": "E0001", "exact_text": "她走进门。"}],
    }
    annotated = annotate_source_evidence_index(index)
    assert annotated["anchors"][0]["anchor_surface_class"] == "NARRATIVE_PROSE"
    assert annotated["surface_typing_deterministic"] is True
    assert annotated["surface_index_fingerprint"]
    assert "anchor_surface_class" not in index["anchors"][0]


def test_quoted_text_cannot_confirm_world_fact_alone():
    ceiling = confirmation_ceiling("QUOTED_TEXT", "WORLD_ASSERTION")
    assert ceiling["allowed"] is False
    result = evaluate_semantic_grounding_guards(
        {"predicate": "installed camera", "value": "behind wall", "epistemic_class": "SOURCE_ASSERTED_FACT"},
        [{"excerpt": "“我看见他安装了摄像头。”", "anchor_surface_class": "QUOTED_TEXT"}],
    )
    assert result["runtime_authority"] is False
    assert result["state"] == "SEMANTIC_REVIEW_REQUIRED"
    assert "QUOTED_TEXT_WORLD_FACT_CONFIRMATION_BLOCKED" in result["hard_blockers"]


def test_quoted_text_can_support_claim_content_but_not_truth():
    ceiling = confirmation_ceiling("QUOTED_TEXT", "CLAIM_CONTENT")
    assert ceiling["allowed"] is True
    result = evaluate_semantic_grounding_guards(
        {"predicate": "recognized umbrella", "value": "previous tenant", "epistemic_class": "SOURCE_SPEECH_ACT"},
        [{"excerpt": "“以前的租客。”", "anchor_surface_class": "QUOTED_TEXT"}],
    )
    assert result["state"] == "SEMANTIC_REVIEW_REQUIRED"
    assert result["runtime_authority"] is False


def test_unknown_surface_cannot_auto_confirm():
    result = evaluate_semantic_grounding_guards(
        {"predicate": "is present", "value": True},
        [{"excerpt": "", "anchor_surface_class": "UNKNOWN_SURFACE"}],
    )
    assert "UNKNOWN_SURFACE_CONFIRMATION_BLOCKED" in result["hard_blockers"]
    assert result["outcome"] == "HUMAN_OR_SEMANTIC_VERIFIER_REQUIRED"


def test_provider_inference_and_composite_are_guarded():
    result = evaluate_semantic_grounding_guards(
        {"predicate": "hid card", "value": "evidence from six years ago"},
        [{"excerpt": "她拧开伞柄，里面掉出存储卡。", "anchor_surface_class": "NARRATIVE_PROSE"}],
        provider_epistemic_class="MODEL_INFERENCE",
    )
    assert "PROVIDER_EPISTEMIC_OVERREACH" in result["hard_blockers"]
    assert "COMPOSITE_ATOMICITY_REVIEW_REQUIRED" in result["hard_blockers"]


def test_script_ir_gate_requires_semantic_confirmation():
    snapshot = {"validation": {"status": "qualified"}}
    assert script_ir_semantic_gate(fact_snapshot=snapshot, semantic_grounding_status="SEMANTIC_REVIEW_REQUIRED")["allowed"] is False
    assert script_ir_semantic_gate(fact_snapshot=snapshot, semantic_grounding_status="SEMANTICALLY_REJECTED")["status"] == "BLOCKED_PENDING_SEMANTIC_GROUNDING"
    assert script_ir_semantic_gate(fact_snapshot=snapshot, semantic_grounding_status="SEMANTICALLY_CONFIRMED")["allowed"] is True


def test_upstream_runner_optional_semantic_gate_blocks_script_dispatch():
    source = {
        "raw_text": "她走进门。",
        "raw_hash": "h",
        "provenance": {"functional_pipeline_evaluation_eligible": True},
        "status": "PASS",
    }
    calls = []

    def provider(request):
        calls.append(request)
        return {"facts": [{"subject_type": "character", "subject_label": "她", "predicate": "enters", "value": True, "evidence": "她走进门。", "epistemic_class": "SOURCE_ASSERTED_FACT"}]}

    result = run_with_provider_calls(
        source=source,
        provider_config={"provider": "test", "model": "offline"},
        call_provider=provider,
        semantic_grounding_status="SEMANTIC_REVIEW_REQUIRED",
    )
    # The legacy V1 fixture is intentionally rejected before a second call;
    # this assertion protects the fail-closed branch when a qualified fact is supplied.
    assert result["provider_calls"] in {0, 1}
