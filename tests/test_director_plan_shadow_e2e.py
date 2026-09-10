"""Phase 0 shadow-mode end-to-end test.

This test exercises the full director-plan shadow path against a real
project (book 75 if it exists, otherwise the first available book). It:

- reads storyboard shots, asset state, prompt version, QA issues and
  continuity records via the existing ``models`` access layer;
- assembles an evidence snapshot mirroring the DecisionPacket style;
- runs the planner in shadow mode and persists only a draft plan;
- asserts that the plan is either auto-executable (A/B only) or that
  every C / D step is marked ``requires_confirmation``;
- never advances the plan past ``draft``;
- never writes to production tables.
"""
import json

from core.director_plan import build_director_plan, summarise_plan
from core.director_plan_shadow import persist_shadow_plan
from models import (
    AgentPlan,
    Book,
    Chapter,
    EpisodeOutline,
    QAIssue,
    Session,
    StoryboardAcceptanceRecord,
    StoryboardPromptVersion,
    StoryboardShot,
    Script,
    VisualLocation,
    VisualMakeup,
    VisualProp,
    VisualReferenceAsset,
)


def _pick_book() -> int | None:
    with Session() as s:
        row = s.query(Book).order_by(Book.id.asc()).first()
        return int(row.id) if row else None


def _shot_for_book(book_id: int) -> StoryboardShot | None:
    with Session() as s:
        return (
            s.query(StoryboardShot)
            .filter(StoryboardShot.book_id == book_id)
            .order_by(StoryboardShot.shot_id.asc())
            .first()
        )


def _evidence_snapshot(book_id: int, shot: StoryboardShot) -> dict:
    with Session() as s:
        shots = (
            s.query(StoryboardShot)
            .filter(StoryboardShot.book_id == book_id)
            .count()
        )
        acceptance = (
            s.query(StoryboardAcceptanceRecord)
            .filter(StoryboardAcceptanceRecord.book_id == book_id)
            .count()
        )
        prompt_versions = (
            s.query(StoryboardPromptVersion)
            .filter(StoryboardPromptVersion.book_id == book_id)
            .count()
        )
        qa_issues = (
            s.query(QAIssue)
            .filter(QAIssue.book_id == book_id)
            .count()
        )
        characters = s.query(VisualMakeup).filter(VisualMakeup.book_id == book_id).count()
        locations = s.query(VisualLocation).filter(VisualLocation.book_id == book_id).count()
        props = s.query(VisualProp).filter(VisualProp.book_id == book_id).count()
        ref_assets = (
            s.query(VisualReferenceAsset)
            .filter(VisualReferenceAsset.book_id == book_id)
            .count()
        )
    return {
        "items": [
            {
                "id": f"book:{book_id}",
                "tier": "locked_fact",
                "summary": f"shots={shots} acceptance={acceptance} prompt_versions={prompt_versions}",
            },
            {
                "id": f"shot:{shot.id}",
                "tier": "source_text",
                "summary": f"shot {shot.shot_id} scene={shot.scene_name} status={shot.asset_status}",
            },
            {
                "id": f"asset:counts",
                "tier": "derived_fact",
                "summary": f"characters={characters} locations={locations} props={props} refs={ref_assets}",
            },
            {
                "id": f"qa:open",
                "tier": "model_observation",
                "summary": f"open QA issues={qa_issues}",
            },
        ]
    }


def test_shadow_plan_for_real_book_is_draft_only():
    book_id = _pick_book()
    if book_id is None:
        # No projects exist yet; shadow plan is still valid in isolation.
        plan = build_director_plan(
            "diagnose",
            {"key": "shadow-empty"},
            {"items": []},
            [{"operation": "diagnose"}],
        )
        assert plan["status"] == "draft"
        assert plan["auto_executable"] is True
        return
    shot = _shot_for_book(book_id)
    if shot is None:
        plan = build_director_plan(
            "diagnose",
            {"book_id": book_id},
            {"items": []},
            [{"operation": "diagnose"}],
        )
        plan_id = persist_shadow_plan(plan)
        try:
            with Session() as s:
                row = s.get(AgentPlan, plan_id)
                assert row is not None and row.status == "draft"
        finally:
            with Session() as s:
                row = s.get(AgentPlan, plan_id)
                if row is not None:
                    s.delete(row)
                    s.commit()
        return

    evidence = _evidence_snapshot(book_id, shot)
    plan = build_director_plan(
        "diagnose and prepare next step",
        {"book_id": book_id, "shot_id": shot.id, "scene": shot.scene_name},
        evidence,
        [
            {"operation": "diagnose", "description": "summarise current state"},
            {"operation": "continuity_check", "description": "compare with previous shot"},
            {"operation": "draft_prompt", "description": "draft prompt candidate if expired"},
            {"operation": "write_prompt_version", "description": "create new version when confirmed"},
            {"operation": "video_generation", "description": "submit H3 multi-reference"},
        ],
        preconditions=[
            f"book {book_id} has at least one shot",
            f"shot {shot.id} is loaded",
        ],
        blocking_issues=[
            "external public asset domain not yet HTTPS",
        ],
    )
    assert plan["status"] == "draft"
    summary = summarise_plan(plan)
    # Either every step is A/B (auto executable) or every C/D step is
    # marked requires_confirmation, never auto-executable.
    if not summary["auto_executable"]:
        c_d_steps = [s for s in plan["steps"] if s["tier"] in {"C", "D"}]
        assert c_d_steps, "plan should explain why it is not auto-executable"
        for s in c_d_steps:
            assert s["requires_confirmation"] is True
    # Persist as draft only.
    plan_id = persist_shadow_plan(plan)
    try:
        with Session() as s:
            row = s.get(AgentPlan, plan_id)
            assert row is not None
            assert row.status == "draft"
            assert row.plan_fingerprint == plan["plan_fingerprint"]
            payload = json.loads(row.steps or "[]")
            assert isinstance(payload, list) and payload
    finally:
        with Session() as s:
            row = s.get(AgentPlan, plan_id)
            if row is not None:
                s.delete(row)
                s.commit()