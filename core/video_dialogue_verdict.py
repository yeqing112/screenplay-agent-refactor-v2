"""Separated media verdict and root-cause attribution contracts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class HumanMediaReview:
    shot_id: str
    video_sha256: str
    speech_like_mouth_motion: bool
    audible_speech: bool
    approximate_utterance_count: int | None
    speech_intelligibility: str
    character_attribution: str = "UNSPECIFIED"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VideoDialogueVerdict:
    media_contract_status: str
    prompt_truth_status: str
    root_cause_attribution_status: str
    audio_contract_status: str
    visual_dialogue_contract_status: str
    human_review_status: str
    automated_visual_judge_status: str
    overall_status: str
    subclassifications: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"subclassifications": list(self.subclassifications)}
