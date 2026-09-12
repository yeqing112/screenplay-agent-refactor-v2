"""Route validation diagnostics to the layer responsible for repairing them."""
from __future__ import annotations

LAYER_BY_CODE = {
    "gender": "FACT", "relationship": "FACT", "fact_": "FACT",
    "script_": "SCRIPT_IR", "scene_asset": "ASSET", "asset_": "ASSET",
    "blocking": "BLOCKING", "position": "BLOCKING",
    "executability": "EXECUTABILITY", "shot_executability": "EXECUTABILITY",
    "action_overloaded": "SHOT_PLAN", "missing_core_action": "SHOT_PLAN", "duration": "SHOT_PLAN",
    "continuity": "CONTINUITY", "screen_direction": "CONTINUITY",
    "phase_a": "PROMPT_IR", "prompt_ir": "PROMPT_IR",
    "prompt": "PROMPT_TEXT", "reference_url": "MEDIA", "media": "MEDIA",
}


def route_issue(issue: dict) -> dict:
    code = str(issue.get("code") or issue.get("issue_code") or "").strip().lower()
    layer = str(issue.get("target_layer") or "").strip().upper()
    if not layer:
        layer = next((value for key, value in LAYER_BY_CODE.items() if code.startswith(key) or key in code), "DIRECTOR_QA")
    return {**issue, "target_layer": layer, "blocking": str(issue.get("severity") or "").lower() in {"blocked", "blocker", "error"}}


def route_issues(issues: list[dict] | None) -> list[dict]:
    return [route_issue(item) for item in (issues or []) if isinstance(item, dict)]
