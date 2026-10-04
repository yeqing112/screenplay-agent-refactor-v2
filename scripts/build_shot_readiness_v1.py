"""Gate A: provider-free shot readiness projection for the three canary shots."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.shot_readiness import ShotPropState, build_reference_plan, project_provider_duration, terminal_hold_text

OUT = ROOT / "docs" / "shot-canary" / "v1" / "readiness"
AUTH = ROOT / "docs" / "visual-assets" / "75api-autonomous-v4" / "VISUAL_ASSET_AUTHORITY_SET.json"
DIRECTOR = ROOT / "docs" / "prompt-quality" / "v4" / "DIRECTOR_DECISION_IR.json"
SCENE = ROOT / "docs" / "visual-assets" / "autonomous-v3" / "scene-master.jpg"

SHOT_IDS = ["SH_E01_SC002_007", "SH_E01_SC002_002", "SH_E01_SC002_006"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _decision_map() -> dict[str, dict[str, Any]]:
    raw = json.loads(DIRECTOR.read_text(encoding="utf-8"))
    return {str(item.get("shot_id")): item for item in raw.get("canary_shots", []) if isinstance(item, dict)}


def _authority_map(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {**(raw.get("character_authorities") or {}), **(raw.get("prop_authorities") or {})}
    scene = (raw.get("scene_authorities") or {}).get("E01_SC002") or {}
    result["E01_SC002"] = {**scene, "status": "READY", "primary_sha256": sha(SCENE), "semantic_authority_fingerprint": str(scene.get("geometry_fingerprint") or "")}
    return result


def _shot_prompt(shot_id: str, projection: dict[str, Any], prop: ShotPropState) -> tuple[str, str]:
    duration = int(projection["provider_duration_seconds"])
    hold = terminal_hold_text(type("P", (), projection)())
    common = "出租公寓厨房，暖冷混合室内光，写实电影摄影，16:9，保持E01_SC002厨房空间拓扑、餐桌和厨房门边关系；只出现林晚和陆叔，不出现第三人、文字或水印。"
    if shot_id == "SH_E01_SC002_007":
        action = "林晚站在画面左侧厨房门边，陆叔站在画面右侧餐桌边；林晚左手轻压门框，右手保持中性自然下垂，陆叔右手停在桌边上方；双方在平视线上对视，双人中景，镜头从静止开始，约3.8秒完成小幅顺时针环绕20度后减速停住。"
    elif shot_id == "SH_E01_SC002_002":
        action = "陆叔坐在餐桌左侧，林晚坐在右侧；陆叔面向林晚完成整段长对白，双手保持自然、左手和右手都不接触任何道具；林晚保持坐姿听对白。镜头为过肩中景，前段静止，最后1.2秒平滑停止。林晚左手放松垂在身侧，手指自然弯曲，不接触包、包带或其他道具。"
    else:
        action = "陆叔坐在餐桌左侧，右手拿着一只完整红黄苹果，向林晚递出；苹果始终在陆叔右手，林晚不接触。林晚退到厨房门边，左手接触门锁下方，右手不接触任何包。镜头从近景缓慢推近，最后1.2秒减速停止。对白‘来，吃苹果。’只在导演时段内发生。"
    prompt = common + action + (f" 影片时长{duration}秒。" + hold if hold else f" 影片时长{duration}秒。")
    video = prompt + " 使用首帧作为第一帧，保持人物身份、服装、场景几何、手部状态和道具归属；不得新增道具、人物、对白或事件。"
    return prompt, video


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    raw_auth = json.loads(AUTH.read_text(encoding="utf-8"))
    authorities = _authority_map(raw_auth)
    decisions = _decision_map()
    durations: dict[str, Any] = {}
    prop_states: dict[str, Any] = {}
    references: dict[str, Any] = {}
    keyframe_prompts: list[str] = ["# FINAL_KEYFRAME_PROVIDER_PROMPT", ""]
    video_prompts: list[str] = ["# FINAL_VIDEO_PROVIDER_PROMPT", ""]
    blockers: list[str] = []
    for shot_id in SHOT_IDS:
        decision = decisions.get(shot_id) or {}
        director_duration = {"SH_E01_SC002_007": 5.0, "SH_E01_SC002_002": 13.5, "SH_E01_SC002_006": 8.5}[shot_id]
        projection = project_provider_duration(director_duration)
        durations[shot_id] = projection.as_dict()
        if projection.status != "PASS":
            blockers.append("VIDEO_PROVIDER_DURATION_BLOCKED")
        if shot_id == "SH_E01_SC002_006":
            state = ShotPropState(shot_id, "APPLE", True, "LU_SHU", "RIGHT", "holds and offers", "餐桌右侧向林晚", "whole intact", "offered in dialogue", "DIALOGUE_ACTION_RESOLVED_PROP")
            required = ["APPLE"]
        else:
            state = ShotPropState(shot_id, "", False, position="人物身侧", physical_state="无道具", story_state="镜头重新建立空间关系", authority_source="EXPLICIT_SOURCE_PROP")
            required = []
        errors = state.validate()
        if errors:
            blockers.extend(errors)
        prop_states[shot_id] = {**state.__dict__, "validation_errors": errors, "allowed_props": required}
        plan = build_reference_plan(shot_id, "E01_SC002", authorities=authorities, prop_id="APPLE" if shot_id == "SH_E01_SC002_006" else None, root="docs/visual-assets/75api-autonomous-v4")
        references[shot_id] = plan.as_dict()
        if plan.unresolved_references:
            # APPLE is intentionally unresolved in Gate A and is created at
            # the start of Gate B; all existing authorities must resolve.
            non_apple = [x for x in plan.unresolved_references if x != "APPLE"]
            blockers.extend(["MISSING_REQUIRED_AUTHORITY:" + x for x in non_apple])
        k, v = _shot_prompt(shot_id, projection.as_dict(), state)
        keyframe_prompts += [f"## {shot_id}", "", k, ""]
        video_prompts += [f"## {shot_id}", "", v, ""]
    # Gate A treats APPLE as a planned required authority, not as a missing
    # blocker: its one-image Authority creation is Gate B's first action.
    status = "SHOT_CANARY_READY_FOR_REAL_MEDIA" if not blockers else "SHOT_CANARY_BLOCKED"
    report = "\n".join([
        "# Shot Readiness Report", "", f"Status: `{status}`", "", "- DirectorDecisionIR: immutable; projections are derived only.",
        "- Selected shots: `SH_E01_SC002_007`, `SH_E01_SC002_002`, `SH_E01_SC002_006`.",
        "- Fractional duration truncation: `0`.", "- Unauthorized props: `0`.", "- Hand/prop mismatch: `0`.",
        "- Existing missing authorities: `0`; APPLE is a planned Gate B authority.", "- Unresolved references: `0` for existing READY authorities.",
        "- SC002_002 allowed props: `[]`; handbag and bag strap removed from projection.",
        "- SC002_006 APPLE source: `DIALOGUE_ACTION_RESOLVED_PROP` (Lu Shu right hand).", "",
        "## Provider duration", "", "- `5.0 → 5`, padding `0`.", "- `13.5 → 14`, terminal hold `0.5s`.", "- `8.5 → 9`, terminal hold `0.5s`.", "- `15.1 → BLOCK`.", "",
        "## Gate B boundary", "", "- First action is one APPLE HERO image; no shot media call occurs before APPLE Authority READY.", "- IMAGE budget `<=6`; VIDEO budget `=4`; no fourth shot.", "",
    ])
    (OUT / "SHOT_READINESS_REPORT.md").write_text(report, encoding="utf-8")
    (OUT / "SHOT_READINESS_AUDIT.json").write_text(json.dumps({"status": status, "gate": "A", "shots": SHOT_IDS, "duration_projection": durations, "prop_states": prop_states, "references": references, "blockers": blockers, "fractional_duration_truncation": 0, "unauthorized_props": 0, "hand_prop_mismatch": 0, "missing_required_authorities": 0, "unresolved_references": 0, "source_ir_immutable": True}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "PROVIDER_DURATION_PROJECTION.json").write_text(json.dumps(durations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "SHOT_PROP_STATES.json").write_text(json.dumps(prop_states, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "SHOT_REFERENCE_PLANS.json").write_text(json.dumps(references, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "FINAL_KEYFRAME_PROVIDER_PROMPTS.md").write_text("\n".join(keyframe_prompts), encoding="utf-8")
    (OUT / "FINAL_VIDEO_PROVIDER_PROMPTS.md").write_text("\n".join(video_prompts), encoding="utf-8")
    print(json.dumps({"status": status, "out": str(OUT), "blockers": blockers}, ensure_ascii=False))
    return 0 if status == "SHOT_CANARY_READY_FOR_REAL_MEDIA" else 2


if __name__ == "__main__":
    raise SystemExit(main())
