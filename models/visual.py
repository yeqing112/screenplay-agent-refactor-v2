"""Visual asset models."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .base import Base


ASSET_STATUS_DRAFT = "draft"
ASSET_STATUS_REF_READY = "ref_ready"
ASSET_STATUS_LOCKED = "locked"


class VisualEraSpec(Base):
    __tablename__ = "visual_era_specs"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, unique=True)
    timeline_start = Column(String, default="")
    timeline_end = Column(String, default="")
    time_periods = Column(Text, default="[]")
    clothing_spec = Column(Text, default="")
    color_palette = Column(Text, default="")
    architecture_spec = Column(Text, default="")
    environment_spec = Column(Text, default="")
    prop_spec = Column(Text, default="")
    color_curve = Column(Text, default="")
    genre_adapt_rules = Column(Text, default="")
    raw_periods = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisualProp(Base):
    __tablename__ = "visual_props"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    book_title = Column(String, default="")
    name = Column(String, nullable=False)
    category = Column(String, default="")
    description = Column(Text, default="")
    associated_characters = Column(Text, default="")
    episodes = Column(Text, default="[]")
    time_period = Column(String, default="")
    visual_prompt_en = Column(Text, default="")
    visual_prompt_zh = Column(Text, default="")
    core_prompt_en = Column(Text, default="")
    core_prompt_zh = Column(Text, default="")
    style_ref_en = Column(Text, default="")
    style_ref_zh = Column(Text, default="")
    importance = Column(String, default="medium")
    notes = Column(Text, default="")
    shot_ids = Column(Text, default="[]")
    jimeng_ref_name = Column(String, default="")
    negative_prompt = Column(Text, default="")
    # Layered prop semantics. Legacy descriptive fields remain authoritative
    # fallbacks so existing assets can migrate incrementally.
    canonical_facts = Column(Text, default="{}")
    state_variants = Column(Text, default="{}")
    look_profile = Column(Text, default="{}")
    asset_status = Column(String, default=ASSET_STATUS_DRAFT)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisualLocation(Base):
    __tablename__ = "visual_locations"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    book_title = Column(String, default="")
    name = Column(String, nullable=False)
    category = Column(String, default="")
    style = Column(String, default="")
    description = Column(Text, default="")
    color_palette = Column(Text, default="")
    lighting_mood = Column(Text, default="")
    key_props = Column(Text, default="[]")
    episodes = Column(Text, default="[]")
    time_period = Column(String, default="")
    visual_prompt_en = Column(Text, default="")
    visual_prompt_zh = Column(Text, default="")
    core_prompt_en = Column(Text, default="")
    core_prompt_zh = Column(Text, default="")
    scene_mood_en = Column(Text, default="")
    scene_mood_zh = Column(Text, default="")
    # Layered scene semantics.  Legacy descriptive fields remain the audit
    # source; these JSON columns let the compiler distinguish reusable space
    # facts from per-state and per-look overrides without breaking imports.
    canonical_facts = Column(Text, default="{}")
    state_variants = Column(Text, default="{}")
    look_profile = Column(Text, default="{}")
    board_spec = Column(Text, default="{}")
    importance = Column(String, default="medium")
    notes = Column(Text, default="")
    shot_ids = Column(Text, default="[]")
    jimeng_ref_name = Column(String, default="")
    negative_prompt = Column(Text, default="")
    asset_status = Column(String, default=ASSET_STATUS_DRAFT)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisualMakeup(Base):
    __tablename__ = "visual_makeups"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    book_title = Column(String, default="")
    episode = Column(Integer, nullable=False)
    character_name = Column(String, nullable=False)
    stage_name = Column(String, default="")
    refined_outfit = Column(Text, default="")
    refined_accessories = Column(Text, default="")
    makeup_spec = Column(Text, default="")
    hair_style = Column(Text, default="")
    expression_mood = Column(Text, default="")
    visual_prompt_en = Column(Text, default="")
    visual_prompt_zh = Column(Text, default="")
    core_prompt_en = Column(Text, default="")
    core_prompt_zh = Column(Text, default="")
    outfit_prompt_en = Column(Text, default="")
    outfit_prompt_zh = Column(Text, default="")
    scene_prompt_en = Column(Text, default="")
    scene_prompt_zh = Column(Text, default="")
    consistency_notes = Column(Text, default="")
    meta_info = Column(Text, default="{}")
    shot_ids = Column(Text, default="[]")
    jimeng_ref_name = Column(String, default="")
    negative_prompt = Column(Text, default="")
    asset_status = Column(String, default=ASSET_STATUS_DRAFT)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisualReferenceAsset(Base):
    __tablename__ = "visual_reference_assets"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    episode = Column(Integer, nullable=True)
    asset_type = Column(String, nullable=False)
    asset_id = Column(String, nullable=False)
    asset_name = Column(String, default="")
    image_url = Column(Text, default="")
    local_path = Column(Text, default="")
    reference_token = Column(String, default="")
    status = Column(String, default="candidate")
    prompt = Column(Text, default="")
    model = Column(String, default="")
    notes = Column(Text, default="")
    meta_info = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class AssetSemanticGovernanceRecord(Base):
    """Auditable, review-first semantic normalization proposal for a visual asset."""

    __tablename__ = "asset_semantic_governance_records"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    asset_type = Column(String, nullable=False)
    asset_id = Column(String, nullable=False)
    plan_fingerprint = Column(String, nullable=False, unique=True)
    source_snapshot = Column(Text, default="{}")
    proposal = Column(Text, default="{}")
    status = Column(String, default="draft")  # draft / confirmed / superseded
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class StoryboardTransitionContract(Base):
    """Reviewed continuity intent between two ordered shots in one episode."""

    __tablename__ = "storyboard_transition_contracts"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    episode = Column(Integer, nullable=False)
    source_shot_id = Column(Integer, nullable=False)
    target_shot_id = Column(Integer, nullable=False)
    continuity_level = Column(String, nullable=False, default="independent")
    entry_state = Column(Text, default="")
    exit_state = Column(Text, default="")
    inherit_rules = Column(Text, default="{}")
    allowed_changes = Column(Text, default="[]")
    forbidden_changes = Column(Text, default="[]")
    required_transition_frame = Column(String, default="")
    source_snapshot = Column(Text, default="{}")
    status = Column(String, nullable=False, default="draft")  # draft / confirmed / superseded
    version = Column(Integer, nullable=False, default=1)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class StoryboardTransitionFrame(Base):
    """A traceable handoff frame. Extraction and locking are always explicit."""

    __tablename__ = "storyboard_transition_frames"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    episode = Column(Integer, nullable=False)
    source_shot_id = Column(Integer, nullable=False)
    target_shot_id = Column(Integer, nullable=False)
    source_video_asset_id = Column(String, default="")
    frame_time_ms = Column(Integer, nullable=False, default=0)
    frame_kind = Column(String, nullable=False, default="last")  # last / near_last
    storage_key = Column(Text, default="")
    public_url = Column(Text, default="")
    checksum = Column(String, default="")
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="candidate")  # candidate / selected / locked / superseded
    extraction_profile = Column(Text, default="{}")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class StoryboardTransitionContinuityReview(Base):
    """Human-reviewed visual continuity result for one generated target video."""

    __tablename__ = "storyboard_transition_continuity_reviews"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    episode = Column(Integer, nullable=False)
    source_shot_id = Column(Integer, nullable=False)
    target_shot_id = Column(Integer, nullable=False)
    transition_frame_id = Column(Integer, nullable=False)
    target_video_asset_id = Column(String, nullable=False)
    target_first_frame_url = Column(Text, default="")
    target_first_frame_storage_key = Column(Text, default="")
    target_first_frame_checksum = Column(String, default="")
    status = Column(String, nullable=False, default="candidate")  # candidate / reviewed / superseded
    review_result = Column(String, default="")  # pass / warning / fail
    drift_categories = Column(Text, default="[]")
    review_notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    reviewed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.now)


class StoryboardVideoRetryAttempt(Base):
    """Immutable audit record for one manually authorised video retry.

    A retry retains the original generation input snapshot rather than resolving
    today's assets or model defaults again.  This makes provider failures and
    continuity remediation reproducible and prevents background auto-retries.
    """

    __tablename__ = "storyboard_video_retry_attempts"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    episode = Column(Integer, nullable=False)
    shot_id = Column(Integer, nullable=False)
    source_task_id = Column(String, nullable=False, unique=True)
    retry_root_task_id = Column(String, nullable=False)
    attempt_number = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="failed")  # failed / retrying / submitted / superseded
    input_fingerprint = Column(String, nullable=False)
    input_snapshot = Column(Text, nullable=False, default="{}")
    error_message = Column(Text, nullable=False, default="")
    provider_response = Column(Text, nullable=False, default="{}")
    retry_task_id = Column(String, default="")
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class PublicAssetStorageMigrationRecord(Base):
    """One immutable, operator-confirmed object-storage migration run."""

    __tablename__ = "public_asset_storage_migration_records"

    id = Column(Integer, primary_key=True)
    plan_fingerprint = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="queued")  # queued / running / completed / partial / failed / dry_run
    storage_snapshot = Column(Text, nullable=False, default="{}")
    plan_snapshot = Column(Text, nullable=False, default="{}")
    result = Column(Text, nullable=False, default="{}")
    error_report = Column(Text, nullable=False, default="[]")
    task_id = Column(String, nullable=False, unique=True, index=True)
    confirmed_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    old_objects_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class DecisionPacketRecord(Base):
    """Auditable evidence packet and LLM proposal for any production domain."""
    __tablename__ = "decision_packet_records"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    domain = Column(String, nullable=False)  # script / storyboard / asset / prompt / continuity
    scope = Column(Text, nullable=False, default="{}")
    packet_fingerprint = Column(String, nullable=False, unique=True)
    evidence = Column(Text, nullable=False, default="[]")
    unknowns = Column(Text, nullable=False, default="[]")
    conflicts = Column(Text, nullable=False, default="[]")
    allowed_operations = Column(Text, nullable=False, default="[]")
    proposal = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="draft")  # draft / confirmed / rejected / superseded
    model_info = Column(Text, nullable=False, default="{}")
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
