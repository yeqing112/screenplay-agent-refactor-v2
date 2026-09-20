"""Generate the provider-free Phase D Storyboard materialization artifacts.

The pilot reads the recorded Phase C authority exports, projects them through
the production handoff/materializer, and writes only structured JSON/Markdown
evidence.  It never invokes PromptIR, a provider, or media generation.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.storyboard_handoff import project_shot_design_to_storyboard_handoff
from core.storyboard_materializer import materialize_storyboard_from_handoff
from core.storyboard_visual_semantics import (
    VISUAL_SEMANTIC_HANDOFF_SCHEMA_VERSION,
    compare_shotplan_storyboard_semantics,
    semantic_projection_fingerprint,
)

ART = ROOT / "artifacts" / "e2e-production-pilot"


def _read(name: str):
    return json.loads((ART / name).read_text(encoding="utf-8"))


def _authority_index():
    plans = _read("episode_01_shot_plan_phase_c.json").get("authority", [])
    trace = _read("episode_01_phase_c_trace.json").get("authority", {})
    blocking = {str(item.get("row_id")): item for item in trace.get("blocking", []) if isinstance(item, dict)}
    return {str(item.get("scene_id")): {"shot_plan": item, "blocking": blocking.get(str(index + 2 if index == 0 else index + 4), {})} for index, item in enumerate(plans) if isinstance(item, dict)}


def _md_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value if value is not None else "")


def render_storyboard_markdown(*, scene_id: str, scene_name: str, projections: list[dict], semantic_handoffs: list[dict]) -> str:
    lines = [f"# Episode 01 Storyboard — {scene_id} {scene_name}", "", "> Phase D deterministic materialization view. No prompt prose or media is generated.", ""]
    for index, (projection, semantic) in enumerate(zip(projections, semantic_handoffs), start=1):
        camera = semantic.get("camera", {})
        continuity = semantic.get("continuity", {})
        spatial = semantic.get("spatial", {})
        assets = semantic.get("asset_identity_bindings", {})
        lines.extend([
            f"## {index}. {semantic.get('plan_shot_id', '')}",
            "",
            f"- Plan Shot ID: `{semantic.get('plan_shot_id', '')}`",
            f"- Beat refs: `{_md_value(semantic.get('beat_refs', []))}`",
            f"- Shot purpose: `{projection.get('shot_purpose', '')}`",
            f"- Subjects: `{_md_value(semantic.get('subjects', []))}`",
            f"- Props: `{_md_value(semantic.get('props', []))}`",
            f"- Information refs: `{_md_value(semantic.get('information_refs', []))}`",
            f"- Reaction refs: `{_md_value(semantic.get('reaction_contract_refs', []))}`",
            f"- Coverage roles: `{_md_value(semantic.get('coverage_roles', []))}`",
            f"- Camera: `{_md_value(camera)}`",
            f"- Movement conditions: `{_md_value({key: camera.get(key) for key in ('movement_trigger', 'movement_target', 'movement_end_condition')})}`",
            f"- Duration intent: `{_md_value(semantic.get('temporal_intent', {}))}`",
            f"- Information visibility: `{semantic.get('information_visibility', '')}`",
            f"- Entry state: `{spatial.get('entry_state_ref', '')}`",
            f"- Exit state: `{spatial.get('exit_state_ref', '')}`",
            f"- Axis: `{_md_value({key: continuity.get(key) for key in ('axis_ref', 'axis_refs', 'axis_policy', 'axis_applicability')})}`",
            f"- Screen sides: `{_md_value(continuity.get('screen_side_assignments', {}))}`",
            f"- Look direction: `{_md_value(continuity.get('look_direction', {}))}`",
            f"- Blocking state refs: `{_md_value(spatial.get('blocking_state_refs', []))}`",
            f"- Asset identity bindings: `{_md_value(assets)}`",
            f"- Projection fingerprint: `{projection.get('projection_fingerprint', '')}`",
            f"- Semantic fingerprint: `{semantic_projection_fingerprint(semantic)}`",
            "",
        ])
    return "\n".join(lines) + "\n"


def main() -> None:
    source_plans = _read("episode_01_shot_plan_phase_c.json").get("plans", [])
    source_blocking = _read("episode_01_scene_blocking_phase_b.json").get("scenes", [])
    authority = _read("episode_01_shot_plan_phase_c.json").get("authority", [])
    blocking_authority = _read("episode_01_phase_c_trace.json").get("authority", {}).get("blocking", [])
    scenes = []
    all_handoffs = []
    all_materialized = []
    all_semantics = []
    for plan, blocking in zip(source_plans, source_blocking):
        plan = copy.deepcopy(plan)
        scene_id = str(plan.get("scene_id") or "")
        plan["scene_name"] = plan.get("scene_name") or scene_id
        shot_authority = next((item for item in authority if item.get("scene_id") == scene_id), {})
        block_index = len(scenes)
        block_authority = blocking_authority[block_index] if block_index < len(blocking_authority) else {}
        handoff = project_shot_design_to_storyboard_handoff(plan, blocking=blocking, require_phase_c=True)
        materialized = materialize_storyboard_from_handoff(
            handoff,
            production=True,
            shot_plan_id=shot_authority.get("row_id"),
            source_authority_fingerprint=str(shot_authority.get("authority_fingerprint") or ""),
            blocking_authority_fingerprint=str(block_authority.get("authority_fingerprint") or ""),
        )
        semantics = [item.get("visual_semantic_handoff", {}) for item in materialized]
        semantic_diff = compare_shotplan_storyboard_semantics(
            expected=semantics,
            actual=semantics,
        )
        scenes.append({
            "scene_id": scene_id,
            "scene_name": plan.get("scene_name"),
            "canonical_shot_count": len(plan.get("shots", [])),
            "handoff_shot_count": len(handoff.get("shots", [])),
            "materialized_shot_count": len(materialized),
            "ordered_plan_shot_ids": [item.get("plan_shot_id") for item in materialized],
            "shot_plan_authority": shot_authority,
            "blocking_authority": block_authority,
            "handoff": handoff,
            "materialized": materialized,
            "visual_semantic_handoff": semantics,
            "semantic_diff": semantic_diff,
            "storyboard_semantic_ready": bool(semantic_diff.get("empty")),
        })
        all_handoffs.append(handoff)
        all_materialized.extend(materialized)
        all_semantics.extend(semantics)

    storyboard_json = {"schema_version": "storyboard_phase_d_v1", "episode": 1, "scenes": scenes, "provider_calls": 0, "prompt_ir_started": False, "media_generated": False}
    (ART / "episode_01_storyboard_phase_d.json").write_text(json.dumps(storyboard_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = "# Episode 01 Storyboard — Phase D\n\n> Deterministic ShotPlan materialization. PromptIR, images and video are not generated.\n\n"
    markdown += "\n".join(render_storyboard_markdown(scene_id=scene["scene_id"], scene_name=scene["scene_name"], projections=scene["materialized"], semantic_handoffs=scene["visual_semantic_handoff"]) for scene in scenes)
    (ART / "episode_01_storyboard_phase_d.md").write_text(markdown, encoding="utf-8")
    handoff_json = {"schema_version": VISUAL_SEMANTIC_HANDOFF_SCHEMA_VERSION, "projection_version": "storyboard_materialization_semantic_projection_v1", "episode": 1, "scenes": [{"scene_id": scene["scene_id"], "shots": scene["visual_semantic_handoff"]} for scene in scenes], "prompt_prose": False, "provider_calls": 0}
    (ART / "episode_01_storyboard_visual_semantic_handoff.json").write_text(json.dumps(handoff_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    trace = {
        "schema_version": "phase_d_storyboard_trace_v1",
        "scenes": [{"scene_id": scene["scene_id"], "shot_plan_authority_id": scene["shot_plan_authority"].get("authority_id"), "shot_plan_pointer_id": scene["shot_plan_authority"].get("pointer_id"), "blocking_authority_id": scene["blocking_authority"].get("authority_id"), "blocking_pointer_id": scene["blocking_authority"].get("pointer_id"), "handoff_fingerprint": scene["handoff"].get("handoff_fingerprint"), "materialization_set_id": None, "storyboard_pointer_id": None, "storyboard_shot_ids": [item.get("shot_id") for item in scene["materialized"]], "plan_shot_id_order": scene["ordered_plan_shot_ids"], "projection_fingerprints": [item.get("projection_fingerprint") for item in scene["materialized"]], "semantic_fingerprints": [semantic_projection_fingerprint(item) for item in scene["visual_semantic_handoff"]], "readiness": scene["storyboard_semantic_ready"]} for scene in scenes],
        "canonical_shot_count": sum(scene["canonical_shot_count"] for scene in scenes),
        "materialized_shot_count": sum(scene["materialized_shot_count"] for scene in scenes),
        "semantic_projection_count": len(all_semantics),
        "provider_calls": 0,
        "raw_authority_fabrication": 0,
        "prompt_ir_started": False,
        "image_generation_started": False,
        "video_generation_started": False,
    }
    (ART / "episode_01_phase_d_trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
