"""Audits for single-emission temporal projections."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


def _f(value: Any) -> float:
    return float(value or 0.0)


def source_event_id(prefix: str, actor: str, start: Any, end: Any, ordinal: int = 0) -> str:
    role = "".join(ch for ch in str(actor).upper() if ch == "_" or (ch.isascii() and ch.isalnum())) or ("EVENT" if not actor else f"ACTOR{ordinal}")
    return f"{prefix}_{role}_{int(round(_f(start) * 100)):04d}_{int(round(_f(end) * 100)):04d}"


@dataclass(frozen=True)
class TemporalEmissionAudit:
    source_performance_beats: int
    compiled_performance_events: int
    duplicate_performance_emissions: tuple[str, ...]
    source_camera_beats: int
    compiled_camera_events: int
    duplicate_camera_emissions: tuple[str, ...]
    source_dialogue_windows: int
    compiled_dialogue_windows: int
    dialogue_timing_drift: tuple[dict[str, Any], ...]
    reaction_delay_count: int
    terminal_hold_count: int
    unexpected_state_resets: tuple[dict[str, Any], ...]
    camera_continuity_conflicts: tuple[dict[str, Any], ...]
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_performance_beats": self.source_performance_beats,
            "compiled_performance_events": self.compiled_performance_events,
            "duplicate_performance_emissions": list(self.duplicate_performance_emissions),
            "source_camera_beats": self.source_camera_beats,
            "compiled_camera_events": self.compiled_camera_events,
            "duplicate_camera_emissions": list(self.duplicate_camera_emissions),
            "source_dialogue_windows": self.source_dialogue_windows,
            "compiled_dialogue_windows": self.compiled_dialogue_windows,
            "dialogue_timing_drift": list(self.dialogue_timing_drift),
            "reaction_delay_count": self.reaction_delay_count,
            "terminal_hold_count": self.terminal_hold_count,
            "unexpected_state_resets": list(self.unexpected_state_resets),
            "camera_continuity_conflicts": list(self.camera_continuity_conflicts),
            "status": self.status,
        }


def audit_dialogue_timing(source: Sequence[Mapping[str, Any]], compiled: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    drift: list[dict[str, Any]] = []
    for index, item in enumerate(source):
        if index >= len(compiled):
            drift.append({"index": index, "reason": "MISSING_COMPILED_WINDOW"})
            continue
        other = compiled[index]
        if _f(item.get("start_time")) != _f(other.get("start_time")) or _f(item.get("end_time")) != _f(other.get("end_time")):
            drift.append({"index": index, "source": {"start_time": item.get("start_time"), "end_time": item.get("end_time")}, "compiled": {"start_time": other.get("start_time"), "end_time": other.get("end_time")}})
    if len(compiled) != len(source):
        drift.append({"reason": "WINDOW_COUNT_MISMATCH", "source_count": len(source), "compiled_count": len(compiled)})
    return drift


def audit_camera_continuity(beats: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    ordered = sorted(beats, key=lambda x: (_f(x.get("start_time")), _f(x.get("end_time"))))
    for previous, current in zip(ordered, ordered[1:]):
        if abs(_f(previous.get("end_time")) - _f(current.get("start_time"))) > 1e-6:
            continue
        previous_end = str(previous.get("end_framing") or "").lower()
        current_start = str(current.get("start_framing") or "").lower()
        previous_class = " ".join(previous_end.split(",", 1)[0].split()[:2])
        current_class = " ".join(current_start.split(",", 1)[0].split()[:2])
        if previous_end and current_start and previous_end != current_start and previous_class != current_class and not (previous_end in current_start or current_start in previous_end):
            conflicts.append({"previous_end_framing": previous.get("end_framing"), "current_start_framing": current.get("start_framing"), "code": "CAMERA_CONTINUITY_CONFLICT"})
    return conflicts


def detect_performance_state_resets(beats: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Detect explicit start/end state discontinuities without guessing prose."""
    resets: list[dict[str, Any]] = []
    ordered = sorted(beats, key=lambda x: (_f(x.get("start_time")), _f(x.get("end_time"))))
    previous_by_actor: dict[str, Mapping[str, Any]] = {}
    for beat in ordered:
        actor = str(beat.get("actor") or "")
        previous = previous_by_actor.get(actor)
        current_start = beat.get("start_state") or beat.get("starting_state")
        previous_end = (previous.get("ending_state") or previous.get("end_state")) if previous else None
        if previous and current_start not in (None, "") and previous_end not in (None, "") and str(current_start) != str(previous_end):
            resets.append({"actor": actor, "start_time": beat.get("start_time"), "previous_end": previous_end, "current_start": current_start, "code": "TEMPORAL_STATE_RESET_WITHOUT_TRANSITION"})
        previous_by_actor[actor] = beat
    return resets


def build_temporal_emission_audit(
    source_performance: Sequence[Mapping[str, Any]],
    compiled_performance: Sequence[Mapping[str, Any]],
    source_camera: Sequence[Mapping[str, Any]],
    compiled_camera: Sequence[Mapping[str, Any]],
    source_dialogue: Sequence[Mapping[str, Any]],
    compiled_dialogue: Sequence[Mapping[str, Any]],
    *,
    reaction_delay_count: int,
    terminal_hold_count: int,
    unexpected_state_resets: Sequence[Mapping[str, Any]] = (),
) -> TemporalEmissionAudit:
    perf_ids = [str(x.get("source_beat_id") or "") for x in compiled_performance]
    camera_ids = [str(x.get("source_beat_id") or "") for x in compiled_camera]
    perf_dupes = tuple(sorted({x for x in perf_ids if x and perf_ids.count(x) > 1}))
    camera_dupes = tuple(sorted({x for x in camera_ids if x and camera_ids.count(x) > 1}))
    drift = audit_dialogue_timing(source_dialogue, compiled_dialogue)
    conflicts = audit_camera_continuity(source_camera)
    status = "PASS" if not perf_dupes and not camera_dupes and not drift and not unexpected_state_resets and not conflicts and len(compiled_performance) == len(source_performance) and len(compiled_camera) == len(source_camera) else "FAIL"
    return TemporalEmissionAudit(len(source_performance), len(compiled_performance), perf_dupes, len(source_camera), len(compiled_camera), camera_dupes, len(source_dialogue), len(compiled_dialogue), tuple(drift), reaction_delay_count, terminal_hold_count, tuple(dict(x) for x in unexpected_state_resets), tuple(conflicts), status)
