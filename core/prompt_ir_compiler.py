"""Deterministic Prompt Compiler Phase A and fallback Phase B verbalizer."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from core.prompt_ir import build_shot_ir_from_context, serialize_shot_ir


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def compile_phase_a(shot: dict[str, Any], *, asset_bindings: dict[str, Any] | None = None, continuity: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the machine IR without LLM calls or external side effects."""
    item = shot if isinstance(shot, dict) else {}
    bindings = asset_bindings if isinstance(asset_bindings, dict) else item.get("asset_bindings", {})
    context = {
        "shot_id": item.get("shot_id"), "scene_name": item.get("scene_name"), "duration": item.get("duration"),
        "camera_angle": item.get("camera_angle"), "camera_movement": item.get("camera_movement"), "camera_speed": item.get("camera_speed"),
        "shot_purpose": item.get("shot_purpose"), "transition": item.get("transition", "cut"), "start_state": item.get("start_state"),
        "action_process": item.get("action_process"), "action_beats": item.get("action_beats", []), "end_state": item.get("end_state"),
        "core_action": item.get("action_process"), "dialogue": item.get("dialogue"), "lighting": item.get("lighting", ""),
        "asset_bindings": bindings, "continuity": continuity or item.get("continuity_contract", {}),
        "required_used_assets": [str(value) for value in (item.get("required_used_assets") or []) if str(value).strip()],
    }
    ir = build_shot_ir_from_context(context)
    serialized = serialize_shot_ir(ir)
    diagnostics = {"status": "pass" if ir.executability.get("status") != "blocked" else "blocked", "errors": [], "warnings": list(ir.warnings), "phase": "A"}
    if not ir.scene_name:
        diagnostics["status"] = "blocked"; diagnostics["errors"].append({"code": "SCENE_REQUIRED", "message": "ShotIR requires scene_name."})
    if not ir.action_process and not ir.action_beats:
        diagnostics["status"] = "blocked"; diagnostics["errors"].append({"code": "CORE_ACTION_REQUIRED", "message": "ShotIR requires a core action."})
    return {"phase_a_status": diagnostics["status"], "shot_ir": serialized, "asset_bindings": bindings, "continuity": continuity or item.get("continuity_contract", {}), "executability": ir.executability, "compiler_diagnostics": diagnostics, "compiler_fingerprint": _fingerprint({"shot_ir": serialized, "asset_bindings": bindings, "continuity": continuity or item.get("continuity_contract", {})}), "recompile_required": False}


def verbalize_phase_b_deterministic(phase_a: dict[str, Any]) -> dict[str, str]:
    """Human-readable fallback that never changes Phase A facts."""
    ir = phase_a.get("shot_ir") if isinstance(phase_a, dict) and isinstance(phase_a.get("shot_ir"), dict) else {}
    scene = str(ir.get("scene_name") or "未命名场景")
    camera = ", ".join(str(value) for value in (ir.get("camera_angle"), ir.get("camera_movement"), ir.get("camera_speed")) if str(value).strip())
    static = f"场景：{scene}。镜头：{camera or '默认机位'}。保持已绑定资产身份、服装、发型与场景陈设一致。"
    action = str(ir.get("action_process") or ir.get("core_action") or "").strip()
    motion = f"动作时序：{action or '保持画面稳定'}。从入镜状态自然过渡到出镜状态，不新增角色或道具。"
    negative = "不新增未绑定角色、道具或场景；不改变锁定事实；不出现文字、水印或多余镜头。"
    return {"static_prompt": static, "motion_prompt": motion, "negative_prompt": negative}


def validate_phase_a_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {"status": "blocked", "errors": [{"code": "PHASE_A_STATE_MISSING", "message": "Phase A compiler state is missing."}]}
    required = ("phase_a_status", "shot_ir", "executability", "compiler_diagnostics", "compiler_fingerprint")
    missing = [key for key in required if key not in state]
    return {"status": "blocked" if missing else "pass", "errors": [{"code": "PHASE_A_FIELD_MISSING", "message": key} for key in missing]}

