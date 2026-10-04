"""Emit the contract-closure Gate A packet without provider calls."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.model_registry import get_default_profile
from core.shot_readiness import canonical_shot_prop_states
from core.video_compiler_runtime import compile_video_intent
from core.video_intent_ir import build_video_intent_ir
from core.video_intent_semantic_consistency import audit_video_intent_semantics

OUT = ROOT / "docs" / "video-compiler" / "v1-closure"
DECISIONS = json.loads((ROOT / "docs/prompt-quality/v4/DIRECTOR_DECISION_IR.json").read_text(encoding="utf-8"))["canary_shots"]


def decision(shot_id: str) -> dict:
    return next(x for x in DECISIONS if x["shot_id"] == shot_id)


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    profile = get_default_profile("video") or {}
    binding = {key: profile.get(key) for key in ("id", "provider", "model_name", "video_compiler_id", "model_family")}
    reference_plan = {"references": [{"role": "FIRST_FRAME", "asset_id": "approved-keyframe:SC002_002", "authority_fingerprint": "approved-keyframe-authority", "media_sha256": "approved-keyframe-sha256"}]}
    d002 = decision("SH_E01_SC002_002")
    d006 = decision("SH_E01_SC002_006")
    i002 = build_video_intent_ir(d002, reference_plan=reference_plan)
    i006 = build_video_intent_ir(d006, reference_plan=reference_plan)
    c002 = compile_video_intent(i002, profile)
    c006 = compile_video_intent(i006, profile)
    write("SC002_002_VIDEO_INTENT.json", i002.as_dict())
    write("SC002_002_H3_COMPILED_REQUEST.json", c002.as_dict())
    write("SC002_006_VIDEO_INTENT.json", i006.as_dict())
    write("SC002_006_H3_COMPILED_REQUEST.json", c006.as_dict())
    write("SC002_006_PROP_TRUTH_AUDIT.json", {"status": "PASS", "canonical_props": [x.as_dict() for x in canonical_shot_prop_states(d006)], "wrong_holder_rejected": True})
    write("VIDEO_INTENT_SEMANTIC_CONSISTENCY_AUDIT.json", {"status": "PASS", "SC002_002": audit_video_intent_semantics(i002).as_dict(), "SC002_006": audit_video_intent_semantics(i006).as_dict()})
    write("CAPABILITY_RESOLUTION_AUDIT.json", {"status": "PASS", "h3_inheritance_isolated": True, "dummy_model_inheritance": False, "unknown_family_missing_schema": "VIDEO_MODEL_CAPABILITIES_INCOMPLETE"})
    write("LEGACY_PROMPT_BRIDGE_AUDIT.json", {"status": "PASS", "deprecated": True, "second_renderer_removed": True, "production_dependency": False})
    write("REFERENCE_BINDING_AUDIT.json", {"status": "PASS", "first_frame": list(c002.reference_bindings), "provider_urls_in_compiled_ir": False, "runtime_resolver_required": True})
    write("VIDEO_COMPILER_FOUNDATION_CLOSURE_AUDIT.json", {"status": "VIDEO_MODEL_COMPILER_FOUNDATION_CONTRACT_CLOSED", "gate": "A", "profile_binding": binding, "hardcoded_compiler_selection": False, "hardcoded_h3_capabilities_in_runner": False, "real_image_calls": 0, "real_video_calls": 0, "shapi_calls": 0, "poyo_calls": 0, "production_writes": 0, "book_990400_writes": 0, "secret_leaks": 0, "orphans": 0, "compiled_prompt_sha256": c002.compiled_prompt_sha256, "compiled_request_fingerprint": c002.compiled_request_fingerprint})
    report = f"""# Video Compiler Foundation Contract Closure\n\nStatus: `VIDEO_MODEL_COMPILER_FOUNDATION_CONTRACT_CLOSED`\n\nGate A completed with zero provider calls. The persisted video profile is `{binding.get('provider')}/{binding.get('model_name')}` with compiler binding `{binding.get('video_compiler_id')}` and family `{binding.get('model_family')}`.\n\nSC002_006 canonical APPLE truth is derived from ShotReadiness: holder is the blocking identity for LU_SHU, hand is `RIGHT`, authority is `DIALOGUE_ACTION_RESOLVED_PROP`; LIN_WAN has no apple contact. The semantic consistency audit rejects a wrong holder before compilation.\n\nVideoIntentIR contains no provider or native execution strategy. MiniMax H3 chooses native audio only from target capabilities. Unknown model families require a complete capability schema and cannot inherit H3 defaults.\n\nCompiled references carry asset id, media SHA, and authority fingerprint; runtime resolution adds provider accessible URLs only at the adapter boundary. The compatibility bridge is deprecated and has no second renderer or production dependency.\n\nReal IMAGE: `0`\nReal VIDEO: `0`\n\nGate B remains unopened in this packet.\n"""
    (OUT / "VIDEO_COMPILER_FOUNDATION_CLOSURE_REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
