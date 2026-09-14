"""Build the deterministic V2.4.2b multi-type Protocol Canary manifest."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.director_tail_repair import REPAIR_SCOPES
from core.director_tail_repair_context import resolve_tail_repair_context
from core.director_tail_repair_executor import TARGET_DIMENSIONS
from core.director_tail_repair_ir import ROOT_CAUSE_TYPES
from core.director_tail_root_cause import rank_tail_root_causes_v2

ARTIFACTS = ROOT / "artifacts"
FREEZE_PATH = ARTIFACTS / "director-quality-v2-4-b2-freeze.json"
EVIDENCE_PATH = ARTIFACTS / "director-quality-v2-3-phase-b2-evidence.json"
OUTPUT_PATH = ARTIFACTS / "director-quality-v2-4-2b-protocol-canary-manifest.json"
REPAIR_TYPES = ("edit", "emotion", "information", "performance", "camera")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _candidate_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    evidence_by_id = {
        _text(_dict(item.get("scene")).get("scene_id")): item
        for item in _list(evidence.get("scenes"))
        if isinstance(item, dict)
    }
    rows: list[dict[str, Any]] = []
    for frozen_row in _list(freeze.get("scenes")):
        if not isinstance(frozen_row, dict) or not _dict(frozen_row.get("tail_repair")).get("triggered"):
            continue
        scene_id = _text(frozen_row.get("scene_id"))
        ev = evidence_by_id.get(scene_id, {})
        evidence_body = _dict(ev.get("evidence"))
        candidate = _dict(ev.get("final_candidate")) or _dict(ev.get("baseline"))
        contract = _dict(ev.get("contract")) or _dict(evidence_body.get("contract"))
        treatment = _dict(evidence_body.get("treatment"))
        if not candidate or not contract or not treatment:
            continue
        ranked = rank_tail_root_causes_v2(frozen_row)
        for rank, ranked_item in enumerate(_list(ranked.get("ranked_root_causes")), start=1):
            root = _text(_dict(ranked_item).get("code"))
            if root not in REPAIR_SCOPES or root not in ROOT_CAUSE_TYPES or not ROOT_CAUSE_TYPES[root]:
                continue
            dimensions = sorted(TARGET_DIMENSIONS.get(root, set()))
            if not dimensions:
                continue
            context = resolve_tail_repair_context(
                root_cause=root,
                opportunities=_list(frozen_row.get("opportunities")),
                treatment=treatment,
                structural_candidate=candidate,
                strategy=_dict(frozen_row.get("strategy")) or _dict(evidence_body.get("strategy")),
                quality_issues=_list(_dict(frozen_row.get("quality")).get("issues")) + _list(frozen_row.get("quality_issues")),
                target_dimensions=dimensions,
            )
            if not context["allowed_plan_shot_ids"]:
                continue
            source = {
                "scene_id": scene_id,
                "root_cause": root,
                "ranked_item": ranked_item,
                "candidate": candidate,
                "contract": contract,
                "treatment": treatment,
                "blocking": _dict(evidence_body.get("blocking")),
                "strategy": _dict(frozen_row.get("strategy")) or _dict(evidence_body.get("strategy")),
                "context": context,
            }
            for repair_type in sorted(ROOT_CAUSE_TYPES[root]):
                rows.append({
                    "sample_id": f"canary-{repair_type}-{_fingerprint({'scene_id': scene_id, 'root_cause': root})[:12]}",
                    "scene_id": scene_id,
                    "root_cause": root,
                    "repair_type": repair_type,
                    "root_cause_rank": rank,
                    "root_cause_score": float(_dict(ranked_item).get("score") or 0.0),
                    "target_dimensions": dimensions,
                    "source_artifact": "artifacts/director-quality-v2-4-b2-freeze.json",
                    "source_fingerprint": _fingerprint(source),
                    "reason_selected": "authoritative ranked root cause with complete Frozen B2 evidence and non-empty scoped shot context",
                    "relevant_opportunity_ids": context["relevant_opportunity_ids"],
                    "relevant_beat_ids": context["relevant_beat_ids"],
                    "relevant_plan_shot_ids": context["relevant_plan_shot_ids"],
                    "_source": source,
                })
    return rows, freeze


def build_manifest() -> dict[str, Any]:
    rows, freeze = _candidate_rows()
    available = sorted({row["repair_type"] for row in rows}, key=lambda value: REPAIR_TYPES.index(value) if value in REPAIR_TYPES else len(REPAIR_TYPES))
    selected: list[dict[str, Any]] = []
    used_scenes: set[str] = set()
    # Select at most one highest-ranked, complete sample for each type while
    # preferring distinct scenes. Stable lexical tie-breaks make replays exact.
    for repair_type in REPAIR_TYPES:
        candidates = [row for row in rows if row["repair_type"] == repair_type and row["scene_id"] not in used_scenes]
        candidates.sort(key=lambda row: (
            0 if repair_type in ROOT_CAUSE_TYPES.get(row["root_cause"], set()) and len(ROOT_CAUSE_TYPES.get(row["root_cause"], set())) == 1 else 1,
            -float(row["root_cause_score"]), int(row["root_cause_rank"]), row["scene_id"], row["root_cause"],
        ))
        if not candidates:
            continue
        row = candidates[0]
        selected.append({key: value for key, value in row.items() if key != "_source"})
        used_scenes.add(row["scene_id"])
    count = len(available)
    coverage = "FULL_TYPE_COVERAGE" if count >= 4 else ("PARTIAL_TYPE_COVERAGE" if count >= 2 else "INSUFFICIENT_CANARY_COVERAGE")
    return {
        "schema_version": "director-quality-v2-4-2b-protocol-canary-manifest-v1",
        "source_artifacts": ["artifacts/director-quality-v2-4-b2-freeze.json", "artifacts/director-quality-v2-3-phase-b2-evidence.json"],
        "selection_policy": "authoritative rank_tail_root_causes_v2; one highest-ranked complete sample per repair_type; prefer distinct scenes; stable lexical ties",
        "available_repair_types": available,
        "selected_repair_types": [row["repair_type"] for row in selected],
        "missing_repair_types": [value for value in REPAIR_TYPES if value not in available],
        "canary_coverage_status": coverage,
        "sample_count": len(selected),
        "semantic_attempt_budget": len(selected) * 2,
        "candidate_count": len(rows),
        "freeze_scene_count": len(_list(freeze.get("scenes"))),
        "samples": selected,
        "side_effects": {"production": 0, "storyboard": 0, "media": 0, "image": 0, "video": 0, "object_storage": 0, "production_shadow": 0},
    }


if __name__ == "__main__":
    payload = build_manifest()
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": OUTPUT_PATH.relative_to(ROOT).as_posix(), **payload}, ensure_ascii=False, indent=2))
