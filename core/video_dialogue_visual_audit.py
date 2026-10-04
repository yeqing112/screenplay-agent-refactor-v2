"""Dense temporal QA primitives for no-dialogue video regression checks.

The module deliberately separates frame/strip extraction, automated evidence,
and human correction.  No ASR or external speech service is required for the
hard audio gate or for the regression fixtures.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path
import subprocess
from typing import Any, Mapping

from PIL import Image, ImageDraw


@dataclass(frozen=True)
class CharacterTemporalRegion:
    character_id: str
    normalized_x_range: tuple[float, float]
    normalized_y_range: tuple[float, float]
    face_y_range: tuple[float, float]
    source: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "normalized_x_range": list(self.normalized_x_range),
            "normalized_y_range": list(self.normalized_y_range),
            "face_y_range": list(self.face_y_range),
        }


@dataclass(frozen=True)
class TemporalWindowVerdict:
    character_id: str
    window_index: int
    start_time: float
    end_time: float
    strip_path: str
    automated_label: str
    automated_confidence: float
    first_evidence_time: float | None
    last_evidence_time: float | None
    human_label: str | None
    final_label: str
    override_reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def derive_character_temporal_regions(decision: Mapping[str, Any]) -> tuple[CharacterTemporalRegion, ...]:
    """Derive broad face/upper-body crops from immutable ShotBlocking."""
    regions: list[CharacterTemporalRegion] = []
    for item in (decision.get("blocking") or []):
        if not isinstance(item, Mapping):
            continue
        character_id = str(item.get("identity") or item.get("character") or "").strip()
        if not character_id:
            continue
        center = _number(item.get("screen_x"), 0.5)
        center = min(max(center, 0.15), 0.85)
        half_width = 0.22
        regions.append(CharacterTemporalRegion(
            character_id=character_id,
            normalized_x_range=(max(0.0, center - half_width), min(1.0, center + half_width)),
            normalized_y_range=(0.04, 0.90),
            face_y_range=(0.08, 0.56),
            source="DirectorDecisionIR.blocking.screen_x",
        ))
    return tuple(regions)


def _ffprobe_dimensions(video_path: Path) -> dict[str, float]:
    raw = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,codec_type",
        "-of", "json", str(video_path),
    ], capture_output=True, text=True, check=True).stdout
    import json
    data = json.loads(raw)
    streams = data.get("streams") or []
    video = next((x for x in streams if x.get("codec_type") == "video"), {})
    return {"width": float(video.get("width") or 0), "height": float(video.get("height") or 0), "duration_seconds": float((data.get("format") or {}).get("duration") or 0)}


def sample_video_dense(video_path: Path, output_dir: Path, *, sampling_fps: int = 8) -> dict[str, Any]:
    if sampling_fps < 6:
        raise ValueError("sampling_fps must be >= 6 for dialogue visual QA")
    output_dir.mkdir(parents=True, exist_ok=True)
    for old in output_dir.glob("frame-*.jpg"):
        old.unlink()
    dimensions = _ffprobe_dimensions(video_path)
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video_path),
        "-vf", f"fps={sampling_fps}", "-q:v", "2", str(output_dir / "frame-%04d.jpg"),
    ], check=True)
    frames = sorted(output_dir.glob("frame-*.jpg"))
    return {
        "sampling_fps": sampling_fps,
        "minimum_sampling_fps": 6,
        "preserved_original_resolution": True,
        "source_width": int(dimensions["width"]),
        "source_height": int(dimensions["height"]),
        "duration_seconds": dimensions["duration_seconds"],
        "frame_count": len(frames),
        "frames": [{"path": str(path), "frame_index": index, "time_seconds": round(index / sampling_fps, 3)} for index, path in enumerate(frames)],
    }


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_") or "character"


def build_temporal_strips(
    frame_manifest: Mapping[str, Any],
    regions: tuple[CharacterTemporalRegion, ...],
    output_dir: Path,
    *,
    window_seconds: float = 1.0,
    tile_size: tuple[int, int] = (256, 256),
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    width = int(frame_manifest.get("source_width") or 0)
    height = int(frame_manifest.get("source_height") or 0)
    fps = float(frame_manifest.get("sampling_fps") or 8)
    result: dict[str, Any] = {"window_seconds": window_seconds, "characters": {}, "frame_order_strict": True}
    frames = frame_manifest.get("frames") or []
    for region in regions:
        by_window: dict[int, list[Mapping[str, Any]]] = {}
        for frame in frames:
            index = int(frame.get("frame_index") or 0)
            window_index = int(math.floor((index / fps) / window_seconds))
            by_window.setdefault(window_index, []).append(frame)
        char_rows: list[dict[str, Any]] = []
        for window_index, window_frames in sorted(by_window.items()):
            tiles: list[Image.Image] = []
            timestamps: list[float] = []
            for frame in window_frames:
                with Image.open(str(frame["path"])) as source:
                    image = source.convert("RGB")
                    x0 = int(region.normalized_x_range[0] * width)
                    x1 = int(region.normalized_x_range[1] * width)
                    y0 = int(region.normalized_y_range[0] * height)
                    y1 = int(region.normalized_y_range[1] * height)
                    crop = image.crop((x0, y0, x1, y1))
                    crop.thumbnail(tile_size)
                    tile = Image.new("RGB", tile_size, "#202020")
                    tile.paste(crop, ((tile_size[0] - crop.width) // 2, (tile_size[1] - crop.height) // 2))
                    tiles.append(tile)
                timestamps.append(float(frame["time_seconds"]))
            strip = Image.new("RGB", (tile_size[0] * max(1, len(tiles)), tile_size[1] + 24), "#202020")
            draw = ImageDraw.Draw(strip)
            for index, tile in enumerate(tiles):
                strip.paste(tile, (index * tile_size[0], 24))
                draw.text((index * tile_size[0] + 4, 4), f"{timestamps[index]:.3f}s", fill="white")
            path = output_dir / f"{_slug(region.character_id)}-window-{window_index:02d}.jpg"
            strip.save(path, quality=92)
            char_rows.append({"window_index": window_index, "start_time": round(window_index * window_seconds, 3), "end_time": round((window_index + 1) * window_seconds, 3), "frame_indices": [int(x.get("frame_index") or 0) for x in window_frames], "timestamps": timestamps, "path": str(path)})
        result["characters"][region.character_id] = {"region": region.as_dict(), "windows": char_rows}
    return result


def build_window_verdicts(
    strips: Mapping[str, Any],
    *,
    automated_labels: Mapping[tuple[str, int], Mapping[str, Any]] | None = None,
    human_labels: Mapping[tuple[str, int], Mapping[str, Any]] | None = None,
) -> list[TemporalWindowVerdict]:
    automated_labels = automated_labels or {}
    human_labels = human_labels or {}
    verdicts: list[TemporalWindowVerdict] = []
    for character_id, character in (strips.get("characters") or {}).items():
        for window in character.get("windows") or []:
            key = (character_id, int(window["window_index"]))
            auto = dict(automated_labels.get(key) or {"label": "uncertain", "confidence": 0.0})
            human = dict(human_labels.get(key) or {})
            human_label = str(human.get("label") or "") or None
            automated_label = str(auto.get("label") or "uncertain")
            final_label = automated_label
            override_reason = None
            if human_label in {"speech_like_open_close_cycle", "speech_like_sustained_motion"}:
                final_label = human_label
                override_reason = "HUMAN_REVIEW_OVERRIDE_AUTOMATED_RESULT"
            elif automated_label in {"speech_like_open_close_cycle", "speech_like_sustained_motion"}:
                final_label = automated_label
            verdicts.append(TemporalWindowVerdict(
                character_id=character_id,
                window_index=int(window["window_index"]),
                start_time=float(window["start_time"]),
                end_time=float(window["end_time"]),
                strip_path=str(window["path"]),
                automated_label=automated_label,
                automated_confidence=float(auto.get("confidence") or 0.0),
                first_evidence_time=human.get("first_evidence_time") or auto.get("first_evidence_time"),
                last_evidence_time=human.get("last_evidence_time") or auto.get("last_evidence_time"),
                human_label=human_label,
                final_label=final_label,
                override_reason=override_reason,
            ))
    return verdicts


def aggregate_no_dialogue_verdict(verdicts: list[TemporalWindowVerdict], *, minimum_speech_seconds: float = 0.4) -> dict[str, Any]:
    positive = [x for x in verdicts if x.final_label in {"speech_like_open_close_cycle", "speech_like_sustained_motion"} and (x.end_time - x.start_time) >= minimum_speech_seconds]
    return {
        "status": "FAIL" if positive else "PASS",
        "minimum_speech_window_seconds": minimum_speech_seconds,
        "speech_like_windows": [x.as_dict() for x in positive],
        "characters_with_speech_like_motion": sorted({x.character_id for x in positive}),
        "automated_visual_judge_false_negative": any(x.human_label and x.automated_label not in {"speech_like_open_close_cycle", "speech_like_sustained_motion"} for x in positive),
    }


def hard_audio_gate(audio_stream_count: int, *, audio_generation_allowed: bool) -> dict[str, Any]:
    if not audio_generation_allowed and int(audio_stream_count) > 0:
        return {"status": "FAIL", "code": "UNEXPECTED_AUDIO_STREAM", "audio_stream_count": int(audio_stream_count)}
    return {"status": "PASS", "code": None, "audio_stream_count": int(audio_stream_count)}
