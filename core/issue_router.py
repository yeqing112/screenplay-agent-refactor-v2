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
_VALID_LAYERS = {"FACT", "SCRIPT_IR", "ASSET", "TREATMENT", "BLOCKING", "SHOT_PLAN", "CONTINUITY", "EXECUTABILITY", "PROMPT_IR", "PROMPT_TEXT", "MEDIA", "DIRECTOR_QA"}
_MANDATORY_LAYER_BY_CODE = {
    "action_overloaded": "SHOT_PLAN", "missing_core_action": "SHOT_PLAN", "duration": "SHOT_PLAN",
    "executability": "EXECUTABILITY", "shot_executability": "EXECUTABILITY",
}


def route_issue(issue: dict) -> dict:
    code = str(issue.get("code") or issue.get("issue_code") or "").strip().lower()
    explicit_layer = str(issue.get("target_layer") or "").strip().upper()
    # Certain structural errors have a non-negotiable owner.  An upstream
    # producer cannot relabel action-budget/executability issues as prompt
    # text repairs to bypass the production boundary.
    layer = next((value for key, value in _MANDATORY_LAYER_BY_CODE.items() if code.startswith(key) or key in code), None)
    if layer is None and explicit_layer in _VALID_LAYERS:
        layer = explicit_layer
    if layer is None:
        layer = next((value for key, value in LAYER_BY_CODE.items() if code.startswith(key) or key in code), "DIRECTOR_QA")
    return {**issue, "target_layer": layer, "blocking": str(issue.get("severity") or "").lower() in {"blocked", "blocker", "error"}}


def route_issues(issues: list[dict] | None) -> list[dict]:
    return [route_issue(item) for item in (issues or []) if isinstance(item, dict)]
