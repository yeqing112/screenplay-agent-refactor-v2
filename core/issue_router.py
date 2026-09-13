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
    "camera_repetition": "DIRECTOR_CREATIVE", "unmotivated_shot": "DIRECTOR_CREATIVE",
    "redundant_shot": "DIRECTOR_CREATIVE", "emotional_flatline": "DIRECTOR_CREATIVE",
    "power_shift_not_visualized": "DIRECTOR_CREATIVE",
}
_VALID_LAYERS = {"FACT", "SCRIPT_IR", "ASSET", "TREATMENT", "BLOCKING", "SHOT_PLAN", "CONTINUITY", "EXECUTABILITY", "PROMPT_IR", "PROMPT_TEXT", "MEDIA", "DIRECTOR_QA", "DIRECTOR_CREATIVE"}
_MANDATORY_LAYER_BY_CODE = {
    "action_overloaded": "SHOT_PLAN", "missing_core_action": "SHOT_PLAN", "duration": "SHOT_PLAN",
    "executability": "EXECUTABILITY", "shot_executability": "EXECUTABILITY",
}

# Director Quality V2.2 repair ownership.  This is intentionally separate
# from the historical layer router above: callers can ask whether an issue is
# eligible for a deterministic/LLM repair without changing the existing
# ``target_layer`` semantics used by other qualification pipelines.
DIRECTOR_REPAIR_ROUTING = {
    # Level 0: equivalent wire representations only.
    "DIRECTOR_PATCH_PATH_CANONICALIZATION": "NORMALIZATION",
    "DIRECTOR_PATCH_SCHEMA_NORMALIZATION": "NORMALIZATION",
    # Level 1: one unambiguous answer.
    "DUPLICATE_IDENTICAL_PATCH": "SAFE_DETERMINISTIC_REPAIR",
    "NON_CONFLICTING_DUPLICATE_PATCH": "SAFE_DETERMINISTIC_REPAIR",
    "DIRECTOR_PATCH_DUPLICATE_TARGET": "SAFE_DETERMINISTIC_REPAIR",
    "KNOWN_ENUM_ALIAS": "SAFE_DETERMINISTIC_REPAIR",
    "SAFE_RANGE_NORMALIZATION": "SAFE_DETERMINISTIC_REPAIR",
    # Level 2: creative semantics require a model proposal.
    "UNMOTIVATED_SHOT": "CREATIVE_SEMANTIC_REPAIR",
    "EMOTIONAL_FLATLINE": "CREATIVE_SEMANTIC_REPAIR",
    "POWER_SHIFT_NOT_VISUALIZED": "CREATIVE_SEMANTIC_REPAIR",
    "INFORMATION_REVEAL_CONFLICT": "CREATIVE_SEMANTIC_REPAIR",
    "GRATUITOUS_CAMERA_MOVEMENT": "CREATIVE_SEMANTIC_REPAIR",
    "REDUNDANT_SHOT": "CREATIVE_SEMANTIC_REPAIR",
    "CREATIVE_SEMANTIC_CONFLICT": "CREATIVE_SEMANTIC_REPAIR",
    "INVALID_CREATIVE_VALUE": "CREATIVE_SEMANTIC_REPAIR",
    # Authority/identity errors must not be repaired by inference.
    "DIRECTOR_FACT_OVERRIDE": "REJECT",
    "IMMUTABLE_VIOLATION": "REJECT",
    "UNKNOWN_PLAN_SHOT_ID": "REJECT",
    "INVALID_SOURCE_BEAT": "REJECT",
    "AUXILIARY_BINDING_FAILURE": "REJECT",
}


def _director_issue_code(issue_or_code: dict | str) -> str:
    if isinstance(issue_or_code, dict):
        value = issue_or_code.get("code") or issue_or_code.get("issue_code") or ""
    else:
        value = issue_or_code
    return str(value or "").strip().upper()


def route_director_repair(issue_or_code: dict | str) -> dict:
    """Return the V2.2 repair level for a Director Quality issue.

    Unknown issues are fail-closed and routed to ``REJECT``.  The function is
    pure and does not call an LLM or alter the legacy ``route_issue`` result.
    """

    code = _director_issue_code(issue_or_code)
    route = DIRECTOR_REPAIR_ROUTING.get(code)
    if route is None:
        # Quality codes may carry a namespace/suffix; only the explicit
        # creative families are allowed to reach Level 2.
        if code.startswith("DIRECTOR_PATCH_PATH") or code.endswith("_NORMALIZATION"):
            route = "NORMALIZATION"
        elif code.startswith("DIRECTOR_FACT") or "IMMUTABLE" in code or code.startswith("UNKNOWN_"):
            route = "REJECT"
        elif code in {"UNMOTIVATED_SHOT", "EMOTIONAL_FLATLINE", "POWER_SHIFT_NOT_VISUALIZED", "INFORMATION_REVEAL_CONFLICT", "GRATUITOUS_CAMERA_MOVEMENT", "REDUNDANT_SHOT"}:
            route = "CREATIVE_SEMANTIC_REPAIR"
        else:
            route = "REJECT"
    level = {"NORMALIZATION": 0, "SAFE_DETERMINISTIC_REPAIR": 1, "CREATIVE_SEMANTIC_REPAIR": 2, "REJECT": None}[route]
    return {"issue_code": code, "route": route, "repair_level": level, "llm_allowed": route == "CREATIVE_SEMANTIC_REPAIR", "fail_closed": route == "REJECT"}


def route_director_repair_issues(issues: list[dict] | None) -> list[dict]:
    return [{**item, **route_director_repair(item)} for item in (issues or []) if isinstance(item, dict)]


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
