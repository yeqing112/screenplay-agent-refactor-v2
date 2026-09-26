"""Durable Phase F generation execution and media-candidate records."""

from datetime import datetime
import json

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, Text, UniqueConstraint

from .base import Base


class GenerationExecutionRecord(Base):
    """One preview or explicitly authorised provider execution attempt.

    The request fingerprint is the durable idempotency boundary.  Provider
    secrets are intentionally absent; request/response snapshots are
    canonical non-secret audit projections only.
    """

    __tablename__ = "generation_execution_records"
    __table_args__ = (
        UniqueConstraint("provider_request_fingerprint", name="uq_generation_execution_provider_request_fingerprint"),
    )

    id = Column(Integer, primary_key=True)
    execution_id = Column(String, nullable=False, unique=True, index=True)
    schema_version = Column(String, nullable=False, default="generation_execution_request_v1")
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    storyboard_shot_id = Column(Integer, nullable=False, index=True)
    plan_shot_id = Column(String, nullable=False, default="")
    execution_mode = Column(String, nullable=False, default="PREVIEW")
    status = Column(String, nullable=False, default="PREVIEWED", index=True)
    target_media = Column(String, nullable=False, default="IMAGE")
    prompt_ir_version_id = Column(Integer, nullable=False, index=True)
    prompt_ir_authority_id = Column(Integer, nullable=False, index=True)
    prompt_ir_payload_hash = Column(String, nullable=False)
    generation_payload_fingerprint = Column(String, nullable=False, index=True)
    generation_policy_fingerprint = Column(String, nullable=False)
    model_profile_id = Column(String, nullable=False)
    model_profile_fingerprint = Column(String, nullable=False)
    provider_adapter_id = Column(String, nullable=False)
    provider_adapter_version = Column(String, nullable=False)
    reference_bindings_fingerprint = Column(String, nullable=False, default="")
    provider_request_fingerprint = Column(String, nullable=False, index=True)
    request_snapshot_json = Column(Text, nullable=False, default="{}")
    confirmation_binding_hash = Column(String, nullable=False, default="")
    provider = Column(String, nullable=False, default="")
    model = Column(String, nullable=False, default="")
    provider_request_id = Column(String, nullable=False, default="")
    provider_task_id = Column(String, nullable=False, default="")
    provider_response_hash = Column(String, nullable=False, default="")
    logical_provider_calls = Column(Integer, nullable=False, default=0)
    transport_retry_count = Column(Integer, nullable=False, default=0)
    submitted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    failure_code = Column(String, nullable=False, default="")
    failure_message = Column(Text, nullable=False, default="")
    official_promotion_count = Column(Integer, nullable=False, default=0)
    candidate_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Foundation compatibility surface.  The canonical Phase F table already
    # owns these facts under its established names.  The properties below
    # expose the foundation vocabulary without adding a second execution table
    # or changing the existing migration head.
    _FOUNDATION_METADATA_KEY = "_generation_execution_foundation"

    def _snapshot(self) -> dict:
        try:
            value = json.loads(self.request_snapshot_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            value = {}
        return dict(value) if isinstance(value, dict) else {}

    def _set_snapshot(self, value: dict) -> None:
        self.request_snapshot_json = json.dumps(value if isinstance(value, dict) else {}, ensure_ascii=False, sort_keys=True)

    def _foundation_metadata(self) -> dict:
        snapshot = self._snapshot()
        value = snapshot.get(self._FOUNDATION_METADATA_KEY)
        return dict(value) if isinstance(value, dict) else {}

    def _set_foundation_metadata(self, **values) -> None:
        snapshot = self._snapshot()
        metadata = self._foundation_metadata()
        metadata.update(values)
        snapshot[self._FOUNDATION_METADATA_KEY] = metadata
        self._set_snapshot(snapshot)

    @property
    def shot_id(self) -> int:
        return int(self.storyboard_shot_id)

    @shot_id.setter
    def shot_id(self, value: int) -> None:
        self.storyboard_shot_id = int(value)

    @property
    def prompt_pointer_id(self) -> int | None:
        value = self._foundation_metadata().get("prompt_pointer_id")
        return int(value) if value not in (None, "") else None

    @prompt_pointer_id.setter
    def prompt_pointer_id(self, value: int | None) -> None:
        self._set_foundation_metadata(prompt_pointer_id=None if value is None else int(value))

    @property
    def prompt_version_id(self) -> int:
        return int(self.prompt_ir_version_id)

    @prompt_version_id.setter
    def prompt_version_id(self, value: int) -> None:
        self.prompt_ir_version_id = int(value)

    @property
    def execution_status(self) -> str:
        return str(self.status or "")

    @execution_status.setter
    def execution_status(self, value: str) -> None:
        self.status = str(value or "")

    @property
    def request_payload(self) -> dict:
        return self._snapshot()

    @request_payload.setter
    def request_payload(self, value) -> None:
        snapshot = dict(value) if isinstance(value, dict) else {}
        metadata = self._foundation_metadata()
        if metadata:
            snapshot[self._FOUNDATION_METADATA_KEY] = metadata
        self._set_snapshot(snapshot)

    @property
    def response_payload(self) -> dict:
        value = self._foundation_metadata().get("response_payload")
        return dict(value) if isinstance(value, dict) else {}

    @response_payload.setter
    def response_payload(self, value) -> None:
        self._set_foundation_metadata(response_payload=value if isinstance(value, dict) else {})

    @property
    def error_message(self) -> str:
        return str(self.failure_message or "")

    @error_message.setter
    def error_message(self, value: str) -> None:
        self.failure_message = str(value or "")

    @property
    def retry_count(self) -> int:
        return int(self.transport_retry_count or 0)

    @retry_count.setter
    def retry_count(self, value: int) -> None:
        self.transport_retry_count = int(value or 0)

    @property
    def started_at(self):
        return self.submitted_at

    @started_at.setter
    def started_at(self, value) -> None:
        self.submitted_at = value


class MediaCandidateRecord(Base):
    """Canonical bytes and provenance below official media authority."""

    __tablename__ = "media_candidate_records"
    __table_args__ = (
        UniqueConstraint("execution_id", name="uq_media_candidate_execution_id"),
        UniqueConstraint("storage_identity", name="uq_media_candidate_storage_identity"),
    )

    id = Column(Integer, primary_key=True)
    candidate_id = Column(String, nullable=False, unique=True, index=True)
    execution_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="MEDIA_CANDIDATE", index=True)
    # Validation is an independent lifecycle from the immutable candidate
    # status.  A candidate remains MEDIA_CANDIDATE while this field moves
    # through PENDING/REVIEW_REQUIRED/TECHNICALLY_VALID/FAILED.
    validation_status = Column(String, nullable=False, default="PENDING", index=True)
    media_type = Column(String, nullable=False)
    storage_identity = Column(String, nullable=False, index=True)
    storage_reference_json = Column(Text, nullable=False, default="{}")
    metadata_json = Column(Text, nullable=False, default="{}")
    checksum_sha256 = Column(String, nullable=False, index=True)
    mime_type = Column(String, nullable=False)
    byte_size = Column(Integer, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    prompt_ir_version_id = Column(Integer, nullable=False, index=True)
    prompt_ir_payload_hash = Column(String, nullable=False)
    generation_payload_fingerprint = Column(String, nullable=False, index=True)
    model_profile_id = Column(String, nullable=False)
    model_profile_fingerprint = Column(String, nullable=False)
    provider_request_fingerprint = Column(String, nullable=False, index=True)
    provider_response_hash = Column(String, nullable=False)
    provider_task_id = Column(String, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    @property
    def generation_execution_id(self) -> str:
        """Public promotion vocabulary alias for the canonical execution id."""
        return str(self.execution_id or "")

    @generation_execution_id.setter
    def generation_execution_id(self, value: str) -> None:
        self.execution_id = str(value or "")

    @property
    def asset_reference(self) -> str:
        """Canonical storage identity used by the promotion authority."""
        return str(self.storage_identity or "")

    @asset_reference.setter
    def asset_reference(self, value: str) -> None:
        self.storage_identity = str(value or "")

    @property
    def candidate_metadata(self) -> dict:
        """Return bounded candidate metadata without exposing provider secrets."""
        try:
            parsed = json.loads(self.metadata_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        parsed.setdefault("media_type", self.media_type)
        parsed.setdefault("mime_type", self.mime_type)
        parsed.setdefault("byte_size", int(self.byte_size or 0))
        parsed.setdefault("width", self.width)
        parsed.setdefault("height", self.height)
        parsed.setdefault("duration_ms", self.duration_ms)
        return parsed


class MediaPromotionRecord(Base):
    """Explicit review and promotion decision for one immutable candidate."""

    __tablename__ = "media_promotion_records"
    __table_args__ = (
        UniqueConstraint("promotion_id", name="uq_media_promotion_identity"),
        UniqueConstraint("candidate_id", name="uq_media_promotion_candidate"),
        CheckConstraint(
            "review_status IN ('REVIEW_REQUIRED','APPROVED','REJECTED','REQUEST_CHANGE')",
            name="ck_media_promotion_review_status",
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('APPROVE','REJECT','REQUEST_CHANGE')",
            name="ck_media_promotion_decision",
        ),
    )

    id = Column(Integer, primary_key=True)
    promotion_id = Column(String, nullable=False, unique=True, index=True)
    candidate_id = Column(String, nullable=False, index=True)
    validation_id = Column(String, nullable=False, index=True)
    execution_id = Column(String, nullable=False, index=True)
    review_status = Column(String, nullable=False, default="REVIEW_REQUIRED", index=True)
    decision = Column(String, nullable=True)
    reviewer = Column(String, nullable=False, default="")
    review_notes = Column(Text, nullable=False, default="")
    official_media_version_id = Column(String, nullable=True, index=True)
    authority_id = Column(String, nullable=True, index=True)
    promotion_fingerprint = Column(String, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
