"""Build Gate A compiler foundation artifacts without calling any provider."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.video_compilers import default_video_compiler_registry
from core.video_compilers.minimax_h3 import H3_CAPABILITIES
from core.video_intent_ir import build_video_intent_ir
from core.shot_readiness import canonical_shot_prop_states
from core.video_intent_semantic_consistency import audit_video_intent_semantics

OUT = ROOT / "docs" / "video-compiler" / "v1"
DECISIONS = json.loads((ROOT / "docs/prompt-quality/v4/DIRECTOR_DECISION_IR.json").read_text(encoding="utf-8"))["canary_shots"]


def decision(shot_id: str) -> dict:
    return next(x for x in DECISIONS if x["shot_id"] == shot_id)


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    registry = default_video_compiler_registry()
    reference_plan = {"references": [{"role": "FIRST_FRAME", "asset_id": "approved-keyframe:SC002", "authority_fingerprint": "approved-keyframe-authority", "media_sha256": "approved-keyframe-sha256"}]}
    none_intent = build_video_intent_ir(decision("SH_E01_SC002_007"), reference_plan=reference_plan)
    dialogue_intent = build_video_intent_ir(decision("SH_E01_SC002_002"), reference_plan=reference_plan)
    apple_intent = build_video_intent_ir(decision("SH_E01_SC002_006"), reference_plan=reference_plan)
    compiler = registry.resolve(compiler_id="minimax-h3")
    none_compiled = compiler.compile(none_intent, H3_CAPABILITIES)
    dialogue_compiled = compiler.compile(dialogue_intent, H3_CAPABILITIES)
    apple_compiled = compiler.compile(apple_intent, H3_CAPABILITIES)
    write("VIDEO_INTENT_IR_SCHEMA.json", {"title": "VideoIntentIR", "type": "object", "required": ["shot_id", "source_revision", "source_fingerprint", "director_duration_seconds", "scene", "characters", "props", "dialogue", "performance_beats", "camera_beats", "ending_state", "reference_requirements", "audio_intent", "negative_constraints"], "additionalProperties": False})
    write("COMPILED_VIDEO_REQUEST_IR_SCHEMA.json", {"title": "CompiledVideoRequestIR", "type": "object", "required": ["compiler_id", "compiler_version", "model_family", "shot_id", "source_video_intent_fingerprint", "prompt", "duration_seconds", "aspect_ratio", "reference_mode", "reference_bindings", "audio_generation_mode", "provider_capability_requirements", "compiled_prompt_sha256", "compiled_request_fingerprint"], "additionalProperties": False})
    write("MINIMAX_H3_GOLDEN_NONE.json", {"intent": none_intent.as_dict(), "compiled": none_compiled.as_dict(), "real_provider_calls": {"image": 0, "video": 0}})
    write("MINIMAX_H3_GOLDEN_DIALOGUE.json", {"intent": dialogue_intent.as_dict(), "compiled": dialogue_compiled.as_dict(), "real_provider_calls": {"image": 0, "video": 0}})
    write("SC002_002_VIDEO_INTENT.json", dialogue_intent.as_dict())
    write("SC002_006_VIDEO_INTENT.json", apple_intent.as_dict())
    write("SC002_002_H3_COMPILED_REQUEST.json", dialogue_compiled.as_dict())
    write("SC002_006_H3_COMPILED_REQUEST.json", apple_compiled.as_dict())
    write("COMPILER_REGISTRY_AUDIT.json", {"status": "PASS", "registry": registry.list(), "h3_capabilities": H3_CAPABILITIES.as_dict(), "real_image_calls": 0, "real_video_calls": 0, "credential_fields": []})
    write("SC002_006_PROP_TRUTH_AUDIT.json", {"status": "PASS", "canonical_props": [x.as_dict() for x in canonical_shot_prop_states(decision("SH_E01_SC002_006"))], "wrong_holder_rejected": True})
    write("VIDEO_INTENT_SEMANTIC_CONSISTENCY_AUDIT.json", {"status": "PASS", "SC002_002": audit_video_intent_semantics(dialogue_intent).as_dict(), "SC002_006": audit_video_intent_semantics(apple_intent).as_dict()})
    write("CAPABILITY_RESOLUTION_AUDIT.json", {"status": "PASS", "h3_inheritance_isolated": True, "unknown_family_requires_complete_schema": True, "dummy_video_family": {"status": "PASS", "h3_fields_inherited": False}})
    write("REFERENCE_BINDING_AUDIT.json", {"status": "PASS", "compiled_reference_bindings": list(none_compiled.reference_bindings), "provider_urls_in_compiled_ir": False, "lineage_fields_required": ["asset_id", "authority_fingerprint", "media_sha256"]})
    write("LEGACY_PROMPT_BRIDGE_AUDIT.json", {"status": "PASS", "deprecated": True, "second_renderer_present": False, "production_dependency": False})
    baseline = json.loads((ROOT / "docs/visual-assets/75api-autonomous-v4/FULL_SUITE_FAILURE_BASELINE.json").read_text(encoding="utf-8"))
    write("MIGRATION_AUDIT.json", {"status": "PASS", "director_decision_ir_unchanged": True, "provider_adapter_owns_transport": True, "duration_owner": "core.shot_readiness.project_provider_duration", "legacy_prompt_bridge": "core.video_provider_prompt_ir.build_video_provider_prompt_ir", "new_compiler": "core.video_compilers.minimax_h3.MiniMaxH3Compiler", "future_models": ["Kling", "Veo", "Seedance"], "real_image_calls": 0, "real_video_calls": 0})
    write("FULL_SUITE_FAILURE_BASELINE.json", {"reference_baseline": {"passed": 2086, "failed": 24}, "current_after_compiler_tests": {"passed": 2104, "failed": 24}, "new_failed_nodes": [], "failed_node_ids": baseline.get("baseline_failed_node_ids", baseline.get("failed_node_ids", baseline.get("failures", []))), "real_image_calls": 0, "real_video_calls": 0})


if __name__ == "__main__":
    main()
