"""Runtime binding from a persisted model profile to a semantic video compiler."""
from __future__ import annotations

from typing import Any

from .video_compilers import CompiledVideoRequestIR, VideoModelCapabilities, default_video_compiler_registry
from .video_intent_ir import VideoIntentIR
from .video_compilers.minimax_h3 import H3_CAPABILITIES


def capabilities_for_profile(profile: dict[str, Any]) -> VideoModelCapabilities:
    """Resolve capabilities with H3 inheritance isolated to the H3 family."""
    params = profile.get("default_params") if isinstance(profile.get("default_params"), dict) else {}
    declared = params.get("video_capabilities") if isinstance(params.get("video_capabilities"), dict) else None
    family = str(profile.get("model_family") or "")
    if family == H3_CAPABILITIES.model_family:
        values = H3_CAPABILITIES.as_dict() | (declared or {})
        values["model_family"] = family
        values["allowed_aspect_ratios"] = tuple(values.get("allowed_aspect_ratios") or ())
        return VideoModelCapabilities(**values)
    required = {"model_family", "supports_text_to_video", "supports_first_frame", "supports_reference_images", "supports_native_dialogue", "supports_native_audio", "supports_first_last_frame", "min_duration", "max_duration", "allowed_aspect_ratios", "max_reference_images"}
    if not declared or not required <= set(declared):
        raise LookupError("VIDEO_MODEL_CAPABILITIES_INCOMPLETE")
    values = dict(declared)
    values["model_family"] = family
    values["allowed_aspect_ratios"] = tuple(values.get("allowed_aspect_ratios") or ())
    return VideoModelCapabilities(**values)


def compile_video_intent(intent: VideoIntentIR, profile: dict[str, Any], *, registry=None) -> CompiledVideoRequestIR:
    compiler_id = str(profile.get("video_compiler_id") or "").strip()
    model_family = str(profile.get("model_family") or "").strip()
    if not compiler_id or not model_family:
        raise LookupError("VIDEO_COMPILER_NOT_CONFIGURED")
    registry = registry or default_video_compiler_registry()
    compiler = registry.resolve(compiler_id=compiler_id, model_family=model_family)
    capabilities = capabilities_for_profile(profile)
    return compiler.compile(intent, capabilities)


__all__ = ["capabilities_for_profile", "compile_video_intent"]
