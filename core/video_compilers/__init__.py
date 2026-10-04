"""Video model compiler interfaces and canonical registry."""
from .base import (
    CompiledVideoRequestIR,
    CompilerSupportResult,
    PromptComplexityAudit,
    VideoModelCapabilities,
    VideoModelCompiler,
    VideoModelCompilerRegistry,
)
from .minimax_h3 import MiniMaxH3Compiler


def default_video_compiler_registry() -> VideoModelCompilerRegistry:
    registry = VideoModelCompilerRegistry()
    registry.register(MiniMaxH3Compiler())
    return registry


__all__ = [
    "CompiledVideoRequestIR", "CompilerSupportResult", "PromptComplexityAudit",
    "VideoModelCapabilities", "VideoModelCompiler", "VideoModelCompilerRegistry",
    "MiniMaxH3Compiler", "default_video_compiler_registry",
]
