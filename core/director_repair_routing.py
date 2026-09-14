"""Repairability routing for Professional Director QA findings."""
from __future__ import annotations

from typing import Any


ROUTES = ("TAIL_REPAIR", "SCENE_REPAIR", "SCENE_REDESIGN", "HUMAN_REVIEW")


def route_qa_findings(findings: list[dict[str, Any]] | None) -> dict[str, Any]:
    rows = [row for row in (findings or []) if isinstance(row, dict)]
    route_counts = {route: 0 for route in ROUTES}
    for row in rows:
        route = str(row.get("repairability") or "HUMAN_REVIEW").strip().upper()
        route_counts[route if route in route_counts else "HUMAN_REVIEW"] += 1
    if route_counts["HUMAN_REVIEW"]:
        next_route = "HUMAN_REVIEW"
    elif route_counts["SCENE_REDESIGN"]:
        next_route = "SCENE_REDESIGN"
    elif route_counts["SCENE_REPAIR"]:
        next_route = "SCENE_REPAIR"
    elif route_counts["TAIL_REPAIR"]:
        next_route = "TAIL_REPAIR"
    else:
        next_route = "NONE"
    return {"schema_version": "director_repairability_routing_v1", "next_route": next_route, "route_counts": route_counts, "principles": {"TAIL_REPAIR": "individual field omission", "SCENE_REPAIR": "coordinated improvement of existing shots with topology fixed", "SCENE_REDESIGN": "strategy cannot be executed by current shot architecture", "HUMAN_REVIEW": "source evidence cannot determine the creative choice"}}


__all__ = ["ROUTES", "route_qa_findings"]
