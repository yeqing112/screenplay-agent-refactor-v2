"""Provider-neutral continuity strategy resolution for video generation.

This module deliberately contains no database or network access.  It converts a
reviewed transition contract plus a locked handoff frame into an explicit
provider request policy.  Adapters remain responsible for translating that
policy into vendor payload fields.
"""

from __future__ import annotations

from typing import Any


CONTINUITY_LEVELS = {"strict", "soft", "narrative", "independent"}
STRATEGIES = {
    "strict_first_frame",
    "strict_start_end",
    "reference_anchor",
    "video_extension",
    "soft_continuity",
}


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def normalize_video_capabilities(profile: dict[str, Any] | None) -> dict[str, Any]:
    """Return a serializable capability snapshot with conservative defaults."""
    profile = profile or {}
    params = profile.get("default_params") if isinstance(profile.get("default_params"), dict) else {}
    raw = params.get("video_capabilities") if isinstance(params.get("video_capabilities"), dict) else {}
    provider = str(profile.get("provider") or "").strip()

    # Provider facts take priority over operator-entered profile values.  H3's
    # multimodal references and first/last-frame mode are mutually exclusive.
    if provider == "minimax-h3-async":
        raw = {
            **raw,
            "first_frame": True,
            "last_frame": True,
            "start_end_frames": True,
            "reference_images": True,
            "reference_video": True,
            "reference_audio": True,
            "reference_and_keyframe_compatible": False,
            "max_reference_images": 9,
            "requires_public_media_url": True,
            "webui_export": True,
            "evidence_status": "confirmed",
        }

    return {
        "first_frame": _as_bool(raw.get("first_frame", params.get("supports_first_frame"))),
        "last_frame": _as_bool(raw.get("last_frame", params.get("supports_last_frame"))),
        "start_end_frames": _as_bool(raw.get("start_end_frames")),
        "reference_images": _as_bool(raw.get("reference_images", params.get("supports_reference_images"))),
        "reference_video": _as_bool(raw.get("reference_video")),
        "reference_audio": _as_bool(raw.get("reference_audio")),
        "video_extension": _as_bool(raw.get("video_extension")),
        "reference_and_keyframe_compatible": _as_bool(raw.get("reference_and_keyframe_compatible")),
        "max_reference_images": max(0, int(raw.get("max_reference_images") or params.get("max_reference_images") or 0)),
        "requires_public_media_url": _as_bool(raw.get("requires_public_media_url"), True),
        "webui_export": _as_bool(raw.get("webui_export"), True),
        "evidence_status": str(raw.get("evidence_status") or "pending_field_verification").strip(),
    }


def resolve_video_continuity_strategy(
    *,
    contract: dict[str, Any] | None,
    transition_frame: dict[str, Any] | None,
    model_profile: dict[str, Any] | None,
    reference_images: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Resolve a safe, explainable request strategy without mutating inputs."""
    contract = contract or {}
    frame = transition_frame or {}
    capabilities = normalize_video_capabilities(model_profile)
    level = str(contract.get("continuity_level") or "independent").strip().lower()
    if level not in CONTINUITY_LEVELS:
        level = "independent"
    references = [item for item in (reference_images or []) if isinstance(item, dict)]
    frame_url = str(frame.get("public_url") or frame.get("publicUrl") or "").strip()
    frame_locked = str(frame.get("status") or "").strip().lower() == "locked"
    issues: list[str] = []
    warnings: list[str] = []

    if level == "independent":
        return {
            "strategy": "soft_continuity",
            "continuity_level": level,
            "first_frame_url": "",
            "reference_images": references,
            "blocking_issues": [],
            "warnings": [],
            "capability_snapshot": capabilities,
        }

    if level == "strict":
        if str(contract.get("status") or "").strip().lower() != "confirmed":
            issues.append("strict-continuity-requires-confirmed-contract")
        if not frame_locked:
            issues.append("strict-continuity-requires-locked-transition-frame")
        if not frame_url:
            issues.append("strict-continuity-requires-provider-accessible-transition-frame")
        if capabilities["first_frame"]:
            if references and not capabilities["reference_and_keyframe_compatible"]:
                warnings.append("reference-images-omitted-because-keyframe-mode-is-mutually-exclusive")
                references = []
            return {
                "strategy": "strict_first_frame",
                "continuity_level": level,
                "first_frame_url": frame_url,
                "reference_images": references,
                "blocking_issues": issues,
                "warnings": warnings,
                "capability_snapshot": capabilities,
            }
        issues.append("selected-model-does-not-support-first-frame-continuity")
        return {
            "strategy": "soft_continuity",
            "continuity_level": level,
            "first_frame_url": "",
            "reference_images": references,
            "blocking_issues": issues,
            "warnings": warnings,
            "capability_snapshot": capabilities,
        }

    if references and capabilities["reference_images"]:
        return {
            "strategy": "reference_anchor",
            "continuity_level": level,
            "first_frame_url": "",
            "reference_images": references,
            "blocking_issues": [],
            "warnings": warnings,
            "capability_snapshot": capabilities,
        }
    return {
        "strategy": "soft_continuity",
        "continuity_level": level,
        "first_frame_url": "",
        "reference_images": references,
        "blocking_issues": [],
        "warnings": ["no-supported-visual-continuity-anchor; using-prompt-level-continuity"],
        "capability_snapshot": capabilities,
    }
