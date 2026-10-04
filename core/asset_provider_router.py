"""Capability ranked provider routing for autonomous visual assets.

The router is session scoped.  A provider that is terminally unhealthy for a
known reason is skipped for the remainder of the current canary, while the
model registry itself remains unchanged for the next session.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable

from core.provider_transport_registry import get_provider_transport_binding


class AssetOperation(str, Enum):
    TEXT_TO_IMAGE = "TEXT_TO_IMAGE"
    REFERENCE_IMAGE_DERIVATION = "REFERENCE_IMAGE_DERIVATION"
    IMAGE_REPAIR = "IMAGE_REPAIR"


class ProviderFailureClassification(str, Enum):
    CREDITS_INSUFFICIENT = "CREDITS_INSUFFICIENT"
    CHANNEL_UNAVAILABLE = "CHANNEL_UNAVAILABLE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    AUTH_FAILED = "AUTH_FAILED"
    PAYLOAD_INVALID = "PAYLOAD_INVALID"
    NETWORK_TRANSIENT = "NETWORK_TRANSIENT"
    SUBMISSION_AMBIGUOUS = "SUBMISSION_AMBIGUOUS"
    PROVIDER_RESPONSE_CONTRACT_MISMATCH = "PROVIDER_RESPONSE_CONTRACT_MISMATCH"
    PROVIDER_LOGICAL_ERROR = "PROVIDER_LOGICAL_ERROR"
    UNKNOWN = "UNKNOWN"


class PostSubmissionState(str, Enum):
    """What the client knows about a provider submission at failure time."""

    NOT_SENT = "NOT_SENT"
    REJECTED_BEFORE_TASK = "REJECTED_BEFORE_TASK"
    TASK_CONFIRMED = "TASK_CONFIRMED"
    TASK_NOT_CONFIRMED = "TASK_NOT_CONFIRMED"
    AMBIGUOUS_AFTER_SEND = "AMBIGUOUS_AFTER_SEND"


@dataclass
class ProviderSelectionTrace:
    profile_id: str
    provider: str
    model: str
    operation: str
    credential_ready: bool
    text_to_image: bool
    reference_image: bool
    connection_probe: str = "NOT_RUN"
    model_available: bool | None = None
    priority: int = 99
    selected: bool = False
    rejected_reason: str = ""


@dataclass
class ProviderHealthSnapshot:
    unhealthy: dict[str, str] = field(default_factory=dict)

    def mark(self, profile_id: str, reason: ProviderFailureClassification | str) -> None:
        self.unhealthy[str(profile_id)] = str(reason.value if isinstance(reason, ProviderFailureClassification) else reason)

    def is_healthy(self, profile_id: str) -> bool:
        return str(profile_id) not in self.unhealthy


def classify_provider_failure(
    error: BaseException | str,
    *,
    post_submission_state: PostSubmissionState | str = PostSubmissionState.NOT_SENT,
) -> ProviderFailureClassification:
    try:
        submission_state = PostSubmissionState(post_submission_state)
    except ValueError:
        submission_state = PostSubmissionState.AMBIGUOUS_AFTER_SEND
    text = str(error or "").lower()
    if "provider_response_contract_mismatch" in text or "75api_image_response_schema_unknown" in text or "75api_image_response_media_missing" in text:
        return ProviderFailureClassification.PROVIDER_RESPONSE_CONTRACT_MISMATCH
    if "provider_logical_error" in text or "75api_image_response_logical_error" in text:
        return ProviderFailureClassification.PROVIDER_LOGICAL_ERROR
    if submission_state in {PostSubmissionState.AMBIGUOUS_AFTER_SEND, PostSubmissionState.TASK_NOT_CONFIRMED} and any(
        token in text for token in ("timeout", "timed out", "超时", "连接超时", "connection reset", "unknown task", "no task", "request id")
    ):
        return ProviderFailureClassification.SUBMISSION_AMBIGUOUS
    if any(token in text for token in ("credits are insufficient", "insufficient credits", "insufficient balance", "余额不足", "credits_insufficient")):
        return ProviderFailureClassification.CREDITS_INSUFFICIENT
    if any(token in text for token in ("401", "403", "认证未通过", "invalid api key", "unauthorized", "forbidden")):
        return ProviderFailureClassification.AUTH_FAILED
    if any(token in text for token in ("model unavailable", "model not found", "没有该模型", "模型不可用", "channel unavailable")):
        return ProviderFailureClassification.MODEL_UNAVAILABLE
    if any(token in text for token in ("invalid payload", "payload", "参数错误", "缺少必要字段", "bad request")):
        return ProviderFailureClassification.PAYLOAD_INVALID
    if any(token in text for token in ("timeout", "timed out", "超时", "connecterror", "connection refused", "temporarily unavailable")):
        return ProviderFailureClassification.NETWORK_TRANSIENT
    if any(token in text for token in ("connection reset", "possible task", "request id", "submitted but", "提交成功")):
        return ProviderFailureClassification.SUBMISSION_AMBIGUOUS
    if any(token in text for token in ("503", "502", "service unavailable", "not found")):
        return ProviderFailureClassification.CHANNEL_UNAVAILABLE
    return ProviderFailureClassification.UNKNOWN


_TERMINAL_FAILOVER = {
    ProviderFailureClassification.CREDITS_INSUFFICIENT,
    ProviderFailureClassification.CHANNEL_UNAVAILABLE,
    ProviderFailureClassification.MODEL_UNAVAILABLE,
    ProviderFailureClassification.AUTH_FAILED,
    ProviderFailureClassification.NETWORK_TRANSIENT,
}


def can_failover(
    classification: ProviderFailureClassification | str,
    *,
    task_created: bool = False,
    post_submission_state: PostSubmissionState | str = PostSubmissionState.NOT_SENT,
    reconciled_no_task: bool = False,
) -> bool:
    """Return whether another provider may be tried without risking a duplicate task."""

    try:
        value = ProviderFailureClassification(classification)
    except ValueError:
        value = ProviderFailureClassification.UNKNOWN
    try:
        state = PostSubmissionState(post_submission_state)
    except ValueError:
        state = PostSubmissionState.AMBIGUOUS_AFTER_SEND
    if state == PostSubmissionState.TASK_CONFIRMED:
        return False
    if task_created and state != PostSubmissionState.REJECTED_BEFORE_TASK:
        return False
    if value == ProviderFailureClassification.SUBMISSION_AMBIGUOUS:
        return reconciled_no_task and state in {
            PostSubmissionState.REJECTED_BEFORE_TASK,
            PostSubmissionState.TASK_NOT_CONFIRMED,
            PostSubmissionState.AMBIGUOUS_AFTER_SEND,
        }
    if state in {PostSubmissionState.AMBIGUOUS_AFTER_SEND, PostSubmissionState.TASK_NOT_CONFIRMED}:
        return False
    return value in _TERMINAL_FAILOVER


def _params(profile: dict[str, Any]) -> dict[str, Any]:
    value = profile.get("default_params")
    return value if isinstance(value, dict) else {}


def _credential_ready(profile: dict[str, Any]) -> bool:
    return bool(str(profile.get("api_key") or "").strip() or profile.get("credential_configured") or profile.get("key_configured"))


class AssetProviderRouter:
    def __init__(self, profiles: Iterable[dict[str, Any]], *, default_image_profile_id: str | None = None, health: ProviderHealthSnapshot | None = None) -> None:
        self.profiles = [dict(item) for item in profiles]
        self.default_image_profile_id = str(default_image_profile_id or "")
        self.health = health or ProviderHealthSnapshot()

    def rank(self, asset_type: str, operation: AssetOperation | str) -> list[ProviderSelectionTrace]:
        op = AssetOperation(operation)
        traces: list[ProviderSelectionTrace] = []
        for profile in self.profiles:
            if str(profile.get("capability") or "") != "image" or not profile.get("enabled", True):
                continue
            profile_id = str(profile.get("id") or "")
            provider = str(profile.get("provider") or "")
            model = str(profile.get("model_name") or "")
            params = _params(profile)
            text_to_image = "text_to_image" in (params.get("task_modes") or []) or provider in {"openai-compatible", "75api-image"}
            # Reference support is declared by the model profile.  75api
            # GPT-image-2 accepts the canonical `images` array, so it must
            # participate in reference derivation when the profile declares
            # that capability.
            reference = bool(params.get("supports_reference_images"))
            credential_ready = _credential_ready(profile)
            reasons: list[str] = []
            if not profile_id or not model:
                reasons.append("MODEL_NOT_CONFIGURED")
            if not credential_ready:
                reasons.append("CREDENTIAL_NOT_READY")
            if not self.health.is_healthy(profile_id):
                reasons.append(f"SESSION_HEALTH:{self.health.unhealthy.get(profile_id)}")
            if get_provider_transport_binding(provider_id=provider, target_media="IMAGE", binding_id=str(profile.get("transport_binding_id") or "") or None) is None:
                reasons.append("TRANSPORT_NOT_REGISTERED")
            if op in {AssetOperation.REFERENCE_IMAGE_DERIVATION, AssetOperation.IMAGE_REPAIR} and not reference:
                reasons.append("REFERENCE_IMAGE_NOT_SUPPORTED")
            if op == AssetOperation.TEXT_TO_IMAGE and not text_to_image:
                reasons.append("TEXT_TO_IMAGE_NOT_SUPPORTED")
            if profile_id == self.default_image_profile_id and reference and text_to_image:
                priority = 1
            elif reference and text_to_image:
                priority = 2
            elif profile_id == self.default_image_profile_id and text_to_image:
                priority = 3
            elif text_to_image:
                priority = 3
            else:
                priority = 99
            traces.append(ProviderSelectionTrace(profile_id, provider, model, op.value, credential_ready, text_to_image, reference, priority=priority, rejected_reason=";".join(reasons)))
        traces.sort(key=lambda row: (row.priority, row.provider, row.profile_id))
        return traces

    def candidates(self, asset_type: str, operation: AssetOperation | str) -> list[ProviderSelectionTrace]:
        return [row for row in self.rank(asset_type, operation) if not row.rejected_reason]

    @staticmethod
    def to_json(rows: Iterable[ProviderSelectionTrace]) -> list[dict[str, Any]]:
        return [asdict(row) for row in rows]


__all__ = [
    "AssetOperation",
    "AssetProviderRouter",
    "ProviderFailureClassification",
    "ProviderHealthSnapshot",
    "ProviderSelectionTrace",
    "PostSubmissionState",
    "classify_provider_failure",
    "can_failover",
]
