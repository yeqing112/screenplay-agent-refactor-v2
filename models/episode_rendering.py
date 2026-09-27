"""Episode-level render plans over the existing production batch runtime."""

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from .base import Base


class EpisodeRenderPlan(Base):
    """One durable render plan for an existing episode outline."""

    __tablename__ = "episode_render_plans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','PREPARING','GENERATING','REVIEWING','COMPLETED','FAILED')",
            name="ck_episode_render_plan_status",
        ),
    )

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("episode_outlines.id", ondelete="RESTRICT"), nullable=False, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    episode_number = Column(Integer, nullable=False, index=True)
    status = Column(String, nullable=False, default="DRAFT", index=True)
    render_strategy = Column(String, nullable=False, default="SEQUENTIAL")
    production_batch_id = Column(Integer, ForeignKey("production_batches.id", ondelete="RESTRICT"), nullable=True, index=True)
    error = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class EpisodeRenderItem(Base):
    """One ordered shot and its dependency edges within an episode plan."""

    __tablename__ = "episode_render_items"
    __table_args__ = (
        UniqueConstraint("render_plan_id", "shot_id", name="uq_episode_render_item_shot"),
        UniqueConstraint("render_plan_id", "order_index", name="uq_episode_render_item_order"),
        CheckConstraint(
            "status IN ('PENDING','QUEUED','RUNNING','COMPLETED','FAILED','SKIPPED')",
            name="ck_episode_render_item_status",
        ),
        CheckConstraint("order_index >= 0", name="ck_episode_render_item_order_nonnegative"),
    )

    id = Column(Integer, primary_key=True)
    render_plan_id = Column(Integer, ForeignKey("episode_render_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_id = Column(Integer, nullable=False, index=True)
    shot_id = Column(Integer, ForeignKey("storyboard_shots.id", ondelete="RESTRICT"), nullable=False, index=True)
    order_index = Column(Integer, nullable=False)
    dependency = Column(Text, nullable=False, default="[]")
    status = Column(String, nullable=False, default="PENDING", index=True)
    production_batch_item_id = Column(Integer, ForeignKey("production_batch_items.id", ondelete="SET NULL"), nullable=True, index=True)
    error = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


__all__ = ["EpisodeRenderPlan", "EpisodeRenderItem"]
