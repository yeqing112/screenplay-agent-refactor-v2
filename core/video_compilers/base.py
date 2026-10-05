"""Provider independent compiler protocol and compiled request IR."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Protocol

from core.video_intent_ir import VideoIntentIR


@dataclass(frozen=True)
class VideoModelCapabilities:
    model_family: str
    supports_text_to_video: bool
    supports_first_frame: bool
    supports_reference_images: bool
    supports_native_dialogue: bool
    supports_native_audio: bool
    supports_first_last_frame: bool
    min_duration: int
    max_duration: int
    allowed_aspect_ratios: tuple[str, ...]
    max_reference_images: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"allowed_aspect_ratios": list(self.allowed_aspect_ratios)}


@dataclass(frozen=True)
class CompilerSupportResult:
    supported: bool
    code: str | None = None
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"warnings": list(self.warnings)}


@dataclass(frozen=True)
class PromptComplexityAudit:
    characters: int
    words: int
    performance_beats: int
    camera_beats: int
    dialogue_length: int
    blocked: bool = False
    code: str | None = None
    timeline_windows: int = 0
    primary_actions: int = 0
    micro_actions: int = 0
    camera_realism_modifiers: int = 0
    dialogue_blocks: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompiledVideoRequestIR:
    compiler_id: str
    compiler_version: str
    model_family: str
    shot_id: str
    source_video_intent_fingerprint: str
    prompt: str
    duration_seconds: int
    aspect_ratio: str
    reference_mode: str
    reference_bindings: tuple[dict[str, Any], ...]
    audio_generation_mode: str
    provider_capability_requirements: dict[str, Any]
    warnings: tuple[str, ...]
    compiled_prompt_sha256: str
    compiled_request_fingerprint: str
    prompt_complexity: PromptComplexityAudit

    def as_dict(self) -> dict[str, Any]:
        return {
            "compiler_id": self.compiler_id,
            "compiler_version": self.compiler_version,
            "model_family": self.model_family,
            "shot_id": self.shot_id,
            "source_video_intent_fingerprint": self.source_video_intent_fingerprint,
            "prompt": self.prompt,
            "duration_seconds": self.duration_seconds,
            "aspect_ratio": self.aspect_ratio,
            "reference_mode": self.reference_mode,
            "reference_bindings": [dict(x) for x in self.reference_bindings],
            "audio_generation_mode": self.audio_generation_mode,
            "provider_capability_requirements": dict(self.provider_capability_requirements),
            "warnings": list(self.warnings),
            "compiled_prompt_sha256": self.compiled_prompt_sha256,
            "compiled_request_fingerprint": self.compiled_request_fingerprint,
            "prompt_complexity": self.prompt_complexity.as_dict(),
        }


class VideoModelCompiler(Protocol):
    compiler_id: str
    compiler_version: str
    model_family: str

    def supports(self, intent: VideoIntentIR, capabilities: VideoModelCapabilities) -> CompilerSupportResult: ...

    def compile(self, intent: VideoIntentIR, target: VideoModelCapabilities) -> CompiledVideoRequestIR: ...


class VideoModelCompilerRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, VideoModelCompiler] = {}
        self._by_family: dict[str, VideoModelCompiler] = {}

    def register(self, compiler: VideoModelCompiler) -> None:
        if compiler.compiler_id in self._by_id or compiler.model_family in self._by_family:
            raise ValueError("VIDEO_COMPILER_DUPLICATE")
        self._by_id[compiler.compiler_id] = compiler
        self._by_family[compiler.model_family] = compiler

    def resolve(self, *, compiler_id: str | None = None, model_family: str | None = None) -> VideoModelCompiler:
        compiler = self._by_id.get(str(compiler_id or "")) if compiler_id else self._by_family.get(str(model_family or ""))
        if compiler is None:
            raise LookupError("VIDEO_COMPILER_NOT_CONFIGURED")
        return compiler

    def list(self) -> list[dict[str, str]]:
        return [{"compiler_id": x.compiler_id, "compiler_version": x.compiler_version, "model_family": x.model_family} for x in self._by_id.values()]
