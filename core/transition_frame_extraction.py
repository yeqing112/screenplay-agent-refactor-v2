"""Deterministic local extraction of a reviewed video handoff frame."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


class TransitionFrameExtractionError(RuntimeError):
    pass


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)


def probe_video_duration_ms(video_path: Path, *, ffprobe_bin: str | None = None) -> int:
    binary = ffprobe_bin or shutil.which("ffprobe")
    if not binary:
        raise TransitionFrameExtractionError("ffprobe is not installed or not on PATH")
    result = _run([binary, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video_path)])
    if result.returncode != 0:
        raise TransitionFrameExtractionError(f"ffprobe failed: {(result.stderr or result.stdout).strip()}")
    try:
        duration_seconds = float(json.loads(result.stdout).get("format", {}).get("duration") or 0)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TransitionFrameExtractionError("ffprobe returned no readable duration") from exc
    if duration_seconds <= 0:
        raise TransitionFrameExtractionError("source video duration is not positive")
    return max(1, round(duration_seconds * 1000))


def probe_png_dimensions(png_bytes: bytes) -> tuple[int, int]:
    """Read PNG IHDR dimensions without a Pillow runtime dependency."""
    if len(png_bytes) < 24 or png_bytes[:8] != b"\x89PNG\r\n\x1a\n" or png_bytes[12:16] != b"IHDR":
        raise TransitionFrameExtractionError("extracted frame is not a readable PNG")
    width = int.from_bytes(png_bytes[16:20], "big")
    height = int.from_bytes(png_bytes[20:24], "big")
    if width <= 0 or height <= 0:
        raise TransitionFrameExtractionError("extracted PNG dimensions are invalid")
    return width, height


def extract_transition_frame(
    video_path: Path,
    output_path: Path,
    *,
    frame_kind: str = "near_last",
    frame_time_ms: int | None = None,
    ffmpeg_bin: str | None = None,
    ffprobe_bin: str | None = None,
) -> dict[str, object]:
    """Extract one PNG, without making any storage or database decision."""
    if frame_kind not in {"last", "near_last"}:
        raise TransitionFrameExtractionError("frame_kind must be last or near_last")
    binary = ffmpeg_bin or shutil.which("ffmpeg")
    if not binary:
        raise TransitionFrameExtractionError("ffmpeg is not installed or not on PATH")
    if not video_path.exists() or not video_path.is_file():
        raise TransitionFrameExtractionError("source video file does not exist")

    duration_ms = probe_video_duration_ms(video_path, ffprobe_bin=ffprobe_bin)
    # A frame exactly at EOF often does not decode.  The universal near-last
    # offset remains deterministic and is persisted in extraction_profile.
    default_offset_ms = 1 if frame_kind == "last" else min(120, max(1, duration_ms // 10))
    resolved_time_ms = frame_time_ms if frame_time_ms is not None else max(0, duration_ms - default_offset_ms)
    if resolved_time_ms >= duration_ms:
        raise TransitionFrameExtractionError("frame_time_ms must be inside source video duration")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = _run([
        binary,
        "-y",
        "-ss", f"{resolved_time_ms / 1000:.3f}",
        "-i", str(video_path),
        "-frames:v", "1",
        "-vf", "format=rgb24",
        str(output_path),
    ])
    if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size <= 0:
        raise TransitionFrameExtractionError(f"ffmpeg frame extraction failed: {(result.stderr or result.stdout).strip()}")
    data = output_path.read_bytes()
    width, height = probe_png_dimensions(data)
    return {
        "duration_ms": duration_ms,
        "frame_time_ms": resolved_time_ms,
        "frame_kind": frame_kind,
        "checksum": hashlib.sha256(data).hexdigest(),
        "bytes_count": len(data),
        "width": width,
        "height": height,
        "local_path": str(output_path),
        "extraction_profile": {
            "extractor": "ffmpeg",
            "ffmpeg_bin": Path(binary).name,
            "duration_ms": duration_ms,
            "frame_time_ms": resolved_time_ms,
            "frame_kind": frame_kind,
            "output_format": "png",
            "width": width,
            "height": height,
        },
    }
