"""Prepare the reviewed source spine for the controlled Episode 13 pilot.

This command is deliberately provider-free.  It projects a small, explicit
pilot context from the existing Episode 13 ScriptIR/FactSnapshot into the
already existing DirectorReasoning -> StoryboardPlan -> ShotPlan ->
materialization runtime.  The original Script, ScriptIRVersion and
FactSnapshot rows are read-only inputs; the source hashes are copied into the
derived lineage so a later source revision cannot silently become current.

The command never records human approval on behalf of an operator and never
calls an image/video provider.  Re-running it reuses the rows identified by
the pilot marker and does not append another source spine.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, UTC
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from sqlalchemy import desc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.automatic_keyframe_authoring import plan_keyframes
from core.automatic_storyboard import (
    approve_storyboard,
    compile_storyboard,
    get_storyboard,
    persist_storyboard,
    storyboard_from_reasoning,
)
from core.director_reasoning import director_reason, persist_reasoning
from core.episode_rendering import create_episode_render_plan
from core.shot_direction import validate_shot_direction
from core.storyboard_production_materialization import materialize_storyboard_plan
from core.prompt_ir_phase_e import compile_storyboard_snapshot_to_prompt_ir, build_generation_policy, fingerprint as prompt_fingerprint
from core.storyboard_materializer import build_storyboard_production_snapshot
from models import (
    AutomaticKeyframePlan,
    DirectorReasoning,
    EpisodeOutline,
    EpisodeRenderPlan,
    FactSnapshot,
    PromptIRPointer,
    PromptIRAuthority,
    PromptIRVersion,
    Script,
    ScriptIRVersion,
    Session,
    ShotPlan,
    StoryboardPlan,
    StoryboardMaterializationSet,
    StoryboardShot,
)


PILOT_MARKER = "REAL_EPISODE_PRODUCTION_PILOT_SOURCE_FIXTURE_V1"
EPISODE_OUTLINE_ID = 13
BOOK_ID = 990402
EPISODE_NUMBER = 1
SCRIPT_IR_ID = 2
FACT_SNAPSHOT_ID = 1
SCENE_ID = "pilot-e13-scene-1"
SHOT_IDS = ("pilot-e13-shot-a", "pilot-e13-shot-b")
OUTPUT = ROOT / "artifacts" / "e2e-production-pilot" / "REAL_EPISODE_PRODUCTION_SOURCE_FIXTURE.json"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return parsed if parsed is not None else fallback


def _obj(value: Any) -> dict[str, Any]:
    parsed = _json(value, {})
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _marker(value: Any) -> bool:
    return _obj(value).get("pilot_marker") == PILOT_MARKER


def _source(session: Any) -> tuple[EpisodeOutline, Script, ScriptIRVersion, FactSnapshot]:
    outline = session.get(EpisodeOutline, EPISODE_OUTLINE_ID)
    script = session.query(Script).filter_by(book_id=BOOK_ID, episode=EPISODE_NUMBER).one()
    ir = session.get(ScriptIRVersion, SCRIPT_IR_ID)
    facts = session.get(FactSnapshot, FACT_SNAPSHOT_ID)
    if outline is None or outline.book_id != BOOK_ID or outline.episode != EPISODE_NUMBER:
        raise RuntimeError("Episode 13 source outline is missing or mismatched")
    if ir is None or ir.book_id != BOOK_ID or ir.episode != EPISODE_NUMBER:
        raise RuntimeError("Episode 13 ScriptIRVersion 2 is missing or mismatched")
    if facts is None or facts.book_id != BOOK_ID or facts.episode != EPISODE_NUMBER:
        raise RuntimeError("Episode 13 FactSnapshot 1 is missing or mismatched")
    return outline, script, ir, facts


def _pilot_context(ir: ScriptIRVersion, facts: FactSnapshot) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_payload = _json(ir.payload_json, {})
    source_hash = str(ir.payload_hash or _hash(source_payload))
    fact_hash = str(facts.payload_hash or "")
    lineage = {
        "pilot_marker": PILOT_MARKER,
        "source_script_ir_version_id": int(ir.id),
        "source_script_ir_revision": int(ir.revision),
        "source_script_ir_hash": source_hash,
        "source_fact_snapshot_id": int(facts.id),
        "source_fact_snapshot_revision": int(facts.revision),
        "source_fact_snapshot_hash": fact_hash,
        "source_fact_mutated": False,
        "script_ir_mutated": False,
        "timeline_origin": "EXPLICIT_PILOT_AUTHORING_DECISION",
        "production_eligible": True,
    }
    script = {
        "schema_version": "pilot_script_ir_projection_v1",
        "episode_id": str(EPISODE_OUTLINE_ID),
        "episode": EPISODE_NUMBER,
        "timeline_origin": "EXPLICIT_PILOT_AUTHORING_DECISION",
        "production_eligible": True,
        "source_lineage": lineage,
        "scenes": [{
            "scene_id": SCENE_ID,
            "scene_name": "Station platform, pre-dawn",
            "location": "Rainy suburban station platform",
            "time": "pre-dawn",
            "mood": "tense and watchful",
            "participants": ["pilot-detective", "pilot-stranger"],
            "shots": [
                {"shot_id": SHOT_IDS[0], "shot_type": "medium", "action": "The detective notices the stranger under the station light.", "emotion": "alert"},
                {"shot_id": SHOT_IDS[1], "shot_type": "close_up", "action": "The stranger reveals the marked umbrella and turns toward the track.", "emotion": "uneasy revelation"},
            ],
        }],
        "critical_beats": [
            {"beat_id": "PILOT_E13_B01", "scene_id": SCENE_ID, "type": "HOOK", "event": "A lone stranger appears before the first train."},
            {"beat_id": "PILOT_E13_B02", "scene_id": SCENE_ID, "type": "REVERSAL", "event": "The marked umbrella reveals a hidden connection."},
        ],
        "scene_transition_contracts": [{"from_scene_id": SCENE_ID, "to_scene_id": None, "status": "RESOLVED", "transition": "episode_end"}],
    }
    episode = {
        "episode_id": str(EPISODE_OUTLINE_ID),
        "book_id": BOOK_ID,
        "episode": EPISODE_NUMBER,
        "source_script_ir_hash": source_hash,
        "source_fact_snapshot_hash": fact_hash,
        "timeline_origin": "EXPLICIT_PILOT_AUTHORING_DECISION",
        "production_eligible": True,
        "character_profiles": [
            {"character_id": "pilot-detective", "name": "Detective", "role": "protagonist"},
            {"character_id": "pilot-stranger", "name": "Stranger", "role": "mystery"},
        ],
        "visual_style_profiles": [{"visual_style_id": "pilot-noir-rain", "name": "noir rain"}],
        "source_lineage": lineage,
    }
    scene = {
        "scenes": deepcopy(script["scenes"]),
        "visual_styles": [{"visual_style_id": "pilot-noir-rain"}],
        "beats": [
            {"sequence": 1, "scene_id": SCENE_ID, "purpose": "establish the watcher and the arrival", "emotion": "alert", "visual_goal": "rain and sodium-vapor silhouette", "character_refs": ["pilot-detective", "pilot-stranger"], "shot_refs": [SHOT_IDS[0]]},
            {"sequence": 2, "scene_id": SCENE_ID, "purpose": "reveal the marked umbrella and turn", "emotion": "uneasy revelation", "visual_goal": "close detail and eye-line shift", "character_refs": ["pilot-stranger"], "shot_refs": [SHOT_IDS[1]]},
        ],
        "visual_decisions": [
            {"story_beat_sequence": 1, "visual_style_id": "pilot-noir-rain", "camera_strategy": "locked eye-level medium", "lighting_strategy": "backlit rain", "color_strategy": "cold blue with amber practicals", "composition_strategy": "negative space toward track"},
            {"story_beat_sequence": 2, "visual_style_id": "pilot-noir-rain", "camera_strategy": "slow push to close-up", "lighting_strategy": "umbrella edge highlight", "color_strategy": "cold blue with red mark", "composition_strategy": "detail against shallow background"},
        ],
    }
    return episode, script, scene


def _existing_plan(session: Any) -> StoryboardPlan | None:
    rows = session.query(StoryboardPlan).filter_by(episode_id=str(EPISODE_OUTLINE_ID)).order_by(StoryboardPlan.version.desc()).all()
    return next((row for row in rows if _marker(row.lineage_json)), None)


def _existing_shots(session: Any) -> list[StoryboardShot]:
    rows = session.query(StoryboardShot).filter_by(book_id=BOOK_ID, episode=EPISODE_NUMBER).order_by(StoryboardShot.shot_id.asc()).all()
    return [row for row in rows if _marker(row.meta_info)]


def _compile_fixture_prompt_ir(session: Any, *, shots: list[StoryboardShot]) -> list[dict[str, Any]]:
    """Compile current media-scoped PromptIR without re-entering upstream APIs.

    The pilot source is an explicit derived fixture because Episode 13's
    legacy Markdown source is not production authority.  The compiler itself
    remains the canonical Phase E implementation; only its already-resolved
    materialization snapshot is supplied directly so the fixture does not
    pretend that the legacy Treatment/Blocking pointers are current.
    """
    if not shots:
        return []
    set_row = session.get(StoryboardMaterializationSet, int(shots[0].materialization_set_id))
    if set_row is None:
        raise RuntimeError("pilot materialization set is missing")
    envelope = _json(set_row.authority_envelope_json, {})
    snapshot = build_storyboard_production_snapshot(materialization_set=set_row, rows=sorted(shots, key=lambda row: row.shot_id), authority_envelope={**envelope, "storyboard_semantic_ready": True})
    results: list[dict[str, Any]] = []
    for raw_policy in (
        {"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE", "source": "real_episode_pilot_fixture"},
        {"mode": "IMAGE_TO_VIDEO", "target_media": "VIDEO", "duration_seconds": 3, "source": "real_episode_pilot_fixture"},
    ):
        policy = build_generation_policy(raw_policy, allow_default=False)
        compiled = compile_storyboard_snapshot_to_prompt_ir(snapshot, generation_policy=policy, asset_authority={"bindings": [], "source": "pilot_fixture", "authority_fingerprint": prompt_fingerprint([])}, allow_default_policy=False)
        for ir in compiled:
            shot_id = int(ir["storyboard_shot_id"])
            existing_pointer = session.query(PromptIRPointer).filter_by(book_id=BOOK_ID, episode=EPISODE_NUMBER, storyboard_shot_id=shot_id, target_media=str(policy["target_media"])).one_or_none()
            if existing_pointer is not None and str(existing_pointer.payload_hash) == str(ir["payload_hash"]):
                results.append({"storyboard_shot_id": shot_id, "target_media": policy["target_media"], "prompt_ir_version_id": int(existing_pointer.prompt_ir_version_id), "reused": True, "payload_hash": ir["payload_hash"]})
                continue
            now = datetime.now()
            authority = {
                "schema_version": "prompt_ir_authority_envelope_v2",
                "source_authority": ir["source_authority"],
                "compiler_provenance": ir["compiler_provenance"],
                "generation_policy": ir["generation_policy"],
                "asset_authority_bindings": ir["asset_authority_bindings"],
                "prompt_ir_payload_hash": ir["payload_hash"],
                "qualification_state": "PROMPT_IR_QUALIFIED",
                "model_generation_ready": False,
                "stale_status": "FRESH",
                "revision_causes": ["PILOT_SOURCE_FIXTURE"],
            }
            authority["envelope_fingerprint"] = prompt_fingerprint(authority)
            version = PromptIRVersion(book_id=BOOK_ID, episode=EPISODE_NUMBER, scene_id=str(ir.get("scene_id") or SCENE_ID), storyboard_shot_id=shot_id, materialization_set_id=int(ir["source_authority"].get("storyboard_materialization_set_id") or set_row.id), plan_shot_id=str(ir.get("plan_shot_id") or ""), schema_version=str(ir.get("schema_version") or "prompt_ir_v2"), payload_json=_canonical(ir), payload_hash=str(ir["payload_hash"]), compiler_version=str(ir["compiler_provenance"].get("compiler_version") or ""), compiler_policy_version=str(ir["compiler_provenance"].get("compiler_policy_version") or ""), retention_policy_version="generation_policy_v1", authority_envelope_json=_canonical(authority), qualification_state="PROMPT_IR_QUALIFIED", asset_reference_state="ASSET_REFERENCE_PENDING", model_generation_ready="false", stale_status="FRESH", stale_reasons="[]", created_at=now, updated_at=now)
            session.add(version)
            session.flush()
            session.add(PromptIRAuthority(prompt_ir_version_id=int(version.id), book_id=BOOK_ID, episode=EPISODE_NUMBER, storyboard_shot_id=shot_id, envelope_fingerprint=authority["envelope_fingerprint"], envelope_json=_canonical(authority), qualification_state="PROMPT_IR_QUALIFIED", stale_status="FRESH", stale_reasons="[]", created_at=now, updated_at=now))
            pointer = existing_pointer or PromptIRPointer(book_id=BOOK_ID, episode=EPISODE_NUMBER, storyboard_shot_id=shot_id, target_media=str(policy["target_media"]))
            pointer.prompt_ir_version_id = int(version.id)
            pointer.payload_hash = str(version.payload_hash)
            pointer.qualification_state = "PROMPT_IR_QUALIFIED"
            pointer.updated_at = now
            session.add(pointer)
            results.append({"storyboard_shot_id": shot_id, "target_media": policy["target_media"], "prompt_ir_version_id": int(version.id), "reused": False, "payload_hash": version.payload_hash})
    session.flush()
    return results


def prepare(*, compile_prompt_ir: bool = True) -> dict[str, Any]:
    with Session() as session:
        outline, source_script, ir, facts = _source(session)
        episode, script, scene = _pilot_context(ir, facts)
        reasoning = next((row for row in session.query(DirectorReasoning).filter_by(episode_id=str(EPISODE_OUTLINE_ID)).order_by(desc(DirectorReasoning.version)).all() if _marker(row.lineage_json)), None)
        if reasoning is None:
            reasoning_payload = director_reason(episode, script, scene)
            reasoning_payload["lineage"] = {**reasoning_payload.get("lineage", {}), **episode["source_lineage"], "pilot_marker": PILOT_MARKER}
            reasoning_payload["reasoning_trace"] = {**reasoning_payload.get("reasoning_trace", {}), "pilot_marker": PILOT_MARKER, "llm_called": False}
            reasoning_data = persist_reasoning(session, reasoning_payload, source_fact_snapshot_hash=str(facts.payload_hash or ""))
            reasoning_id, reasoning_version = int(reasoning_data["id"]), int(reasoning_data["version"])
            reasoning = session.get(DirectorReasoning, reasoning_id)
        else:
            reasoning_id, reasoning_version = int(reasoning.id), int(reasoning.version)

        plan = _existing_plan(session)
        if plan is None:
            reasoning_payload = _json(reasoning.reasoning_json, {})
            storyboard_payload = storyboard_from_reasoning(reasoning_payload, context={"episode_id": str(EPISODE_OUTLINE_ID), "scenes": script["scenes"], "existing_shots": []}, director_reasoning_id=reasoning_id, director_reasoning_version=reasoning_version)
            storyboard_payload["lineage"] = {**storyboard_payload.get("lineage", {}), **episode["source_lineage"], "pilot_marker": PILOT_MARKER}
            storyboard_payload["reasoning_trace"] = {**storyboard_payload.get("reasoning_trace", {}), "pilot_marker": PILOT_MARKER, "source_script_ir_version_id": int(ir.id), "source_fact_snapshot_id": int(facts.id)}
            persisted = persist_storyboard(session, storyboard_payload)
            plan = session.get(StoryboardPlan, int(persisted["id"]))
            compile_storyboard(session, plan, episode_context=episode, script_ir=script, scene_context=scene, book_id=BOOK_ID, episode_number=EPISODE_NUMBER)
            # Do not approve here.  Approval is an operator decision.
        elif plan.status in {"DRAFT", "REVIEW_REQUIRED"}:
            # A previous invocation may have persisted the draft but not
            # compiled it.  Compile is deterministic and still reviewable.
            compile_storyboard(session, plan, episode_context=episode, script_ir=script, scene_context=scene, book_id=BOOK_ID, episode_number=EPISODE_NUMBER)

        session.flush()
        if plan.status == "APPROVED":
            materialization = materialize_storyboard_plan(session, episode_id=str(EPISODE_OUTLINE_ID), storyboard_plan_id=int(plan.id), storyboard_version=int(plan.version), book_id=BOOK_ID, episode_number=EPISODE_NUMBER)
            session.flush()
            # The first materialization has not received the pilot marker yet;
            # use the materializer's returned identities for that first pass.
            materialized_ids = [int(item) for item in materialization.get("storyboard_shot_ids", []) if str(item).isdigit()]
            shots = session.query(StoryboardShot).filter(StoryboardShot.id.in_(materialized_ids)).order_by(StoryboardShot.shot_id.asc()).all() if materialized_ids else _existing_shots(session)
            if len(shots) != 2:
                raise RuntimeError(f"pilot materialization expected exactly two shots, found {len(shots)}")
            # Add a marker to each materialized row only if it is not already
            # present.  This is derived lineage, not source mutation.
            for shot in shots:
                meta = _obj(shot.meta_info)
                if meta.get("pilot_marker") != PILOT_MARKER:
                    meta.update({"pilot_marker": PILOT_MARKER, "source_script_ir_version_id": int(ir.id), "source_fact_snapshot_id": int(facts.id), "source_script_ir_hash": str(ir.payload_hash), "source_fact_snapshot_hash": str(facts.payload_hash)})
                    shot.meta_info = _canonical(meta)
            for shot_plan in session.query(ShotPlan).filter(ShotPlan.id.in_([int(item) for item in _json(plan.compiled_shot_plan_ids, []) if str(item).isdigit()])).all():
                shot_plan.director_lineage = _canonical({**_obj(shot_plan.director_lineage), **episode["source_lineage"], "pilot_marker": PILOT_MARKER})
                shot_plan.source_script_ir_version_id = int(ir.id)
                shot_plan.source_script_ir_revision = int(ir.revision)
                shot_plan.source_script_ir_hash = str(ir.payload_hash or "")
                shot_plan.source_fact_snapshot_id = str(facts.id)
                shot_plan.source_fact_snapshot_revision = int(facts.revision)
                shot_plan.source_fact_snapshot_hash = str(facts.payload_hash or "")
            session.flush()
            for shot in shots:
                validation = validate_shot_direction(session, shot_id=int(shot.id))
                if validation.get("status") != "PASS":
                    raise RuntimeError(f"ShotDirection invalid for shot {shot.id}")
                if session.query(AutomaticKeyframePlan).filter_by(storyboard_shot_id=int(shot.id)).count() == 0:
                    plan_keyframes(session, shot_id=int(shot.id), created_by="pilot-source-preparer")
            if compile_prompt_ir:
                # PromptIR compilation is deterministic and provider-free. It
                # creates current IMAGE and VIDEO pointers for each fixture
                # shot while preserving the fixture marker in the authority
                # envelope.
                _compile_fixture_prompt_ir(session, shots=shots)
            render = session.query(EpisodeRenderPlan).filter_by(episode_id=EPISODE_OUTLINE_ID).order_by(desc(EpisodeRenderPlan.id)).first()
            if render is None:
                render = create_episode_render_plan(session, episode_id=EPISODE_OUTLINE_ID, items=[{"shot_id": int(shot.id), "order": index, "dependency": [] if index == 0 else [int(shots[index - 1].id)]} for index, shot in enumerate(sorted(shots, key=lambda item: item.shot_id))])
        else:
            materialization = None
            shots = _existing_shots(session)
            render = None
        session.commit()

        pointers = session.query(PromptIRPointer).filter_by(book_id=BOOK_ID, episode=EPISODE_NUMBER).all()
        output = {
            "schema_version": "real_episode_production_pilot_source_fixture_v1",
            "pilot_marker": PILOT_MARKER,
            "status": "SOURCE_SPINE_READY_FOR_HUMAN_REVIEW" if plan.status == "APPROVED" else "STORYBOARD_REVIEW_REQUIRED",
            "episode_id": EPISODE_OUTLINE_ID,
            "book_id": BOOK_ID,
            "episode": EPISODE_NUMBER,
            "shot_ids": [int(item.id) for item in sorted(shots, key=lambda row: row.shot_id)],
            "planned_shot_keys": list(SHOT_IDS),
            "shot_plan_ids": [int(item.id) for item in session.query(ShotPlan).filter_by(book_id=BOOK_ID, episode=EPISODE_NUMBER).all() if _marker(item.director_lineage)],
            "render_plan_id": int(render.id) if render is not None else None,
            "storyboard_plan_id": int(plan.id),
            "storyboard_plan_version": int(plan.version),
            "storyboard_status": plan.status,
            "automatic_keyframe_plans": [{"shot_id": int(row.storyboard_shot_id), "id": int(row.id), "version": int(row.version), "status": row.status} for row in session.query(AutomaticKeyframePlan).filter(AutomaticKeyframePlan.storyboard_shot_id.in_([int(item.id) for item in shots])).order_by(AutomaticKeyframePlan.storyboard_shot_id.asc()).all()],
            "prompt_ir_pointers": [{"shot_id": int(row.storyboard_shot_id), "target_media": row.target_media, "prompt_ir_version_id": int(row.prompt_ir_version_id)} for row in pointers if int(row.storyboard_shot_id) in {int(item.id) for item in shots}],
            "source_lineage": {**episode["source_lineage"], "source_outline_id": int(outline.id), "source_script_id": int(source_script.id), "source_script_content_hash": hashlib.sha256(str(source_script.content or "").encode("utf-8")).hexdigest()},
            "human_review_required": True,
            "provider_calls": {"llm": 0, "image": 0, "video": 0},
            "created_at": datetime.now(UTC).isoformat(),
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-prompt-ir", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(compile_prompt_ir=not args.skip_prompt_ir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
