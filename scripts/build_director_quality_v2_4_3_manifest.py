"""Build the immutable V2.4.3 targeted-tail manifest from frozen artifacts.

This script deliberately does not rank, regenerate, or call a provider.  It
only intersects the historical triggered cohort with the historical first-two
root-cause cap and records the evidence fingerprints used by the pilot.
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"

from core.director_tail_repair_context import resolve_tail_repair_context
from core.director_tail_repair_executor import TARGET_DIMENSIONS
from core.director_tail_repair_ir import ROOT_CAUSE_TYPES
from core.local_repair import fingerprint


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _repair_type(root: str) -> str:
    allowed = ROOT_CAUSE_TYPES.get(root, set())
    # Stable preference follows the semantic spec's canonical group names.
    for value in ("edit", "emotion", "information", "performance", "camera"):
        if value in allowed:
            return value
    return sorted(allowed)[0] if allowed else ""


def build_manifest(
    *,
    freeze_path: Path = ARTIFACTS / "director-quality-v2-4-b2-freeze.json",
    targeted_path: Path = ARTIFACTS / "director-quality-v2-4-targeted-tail-pilot-20260914T090340Z.json",
    evidence_path: Path = ARTIFACTS / "director-quality-v2-3-phase-b2-evidence.json",
) -> dict[str, Any]:
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    targeted = json.loads(targeted_path.read_text(encoding="utf-8"))
    evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    freeze_by_id = {_text(row.get("scene_id")): row for row in _list(freeze.get("scenes")) if isinstance(row, dict)}
    evidence_by_id = {
        _text(_dict(row.get("scene")).get("scene_id")): row
        for row in _list(evidence_payload.get("scenes"))
        if isinstance(row, dict)
    }
    scenes: list[dict[str, Any]] = []
    for targeted_row in _list(targeted.get("scenes")):
        if not isinstance(targeted_row, dict):
            continue
        scene_id = _text(targeted_row.get("scene_id"))
        frozen_row = freeze_by_id.get(scene_id, {})
        evidence_row = evidence_by_id.get(scene_id, {})
        scene_meta = _dict(frozen_row.get("scene"))
        frozen_evidence = _dict(evidence_row.get("evidence"))
        candidate = copy.deepcopy(_dict(evidence_row.get("final_candidate")) or _dict(evidence_row.get("baseline")))
        contract = copy.deepcopy(_dict(evidence_row.get("contract")) or _dict(frozen_evidence.get("contract")))
        if not candidate or not contract:
            raise ValueError(f"missing frozen candidate/contract for {scene_id}")
        ranked = _dict(_dict(targeted_row.get("repair")).get("ranked_root_causes")).get("ranked_root_causes")
        if not isinstance(ranked, list):
            raise ValueError(f"missing historical root ranking for {scene_id}")
        roots: list[dict[str, Any]] = []
        for rank, ranked_row in enumerate(ranked[:2], start=1):
            if not isinstance(ranked_row, dict):
                continue
            root = _text(ranked_row.get("code"))
            if root not in TARGET_DIMENSIONS:
                continue
            context = resolve_tail_repair_context(
                root_cause=root,
                opportunities=_list(frozen_row.get("opportunities")),
                treatment=_dict(frozen_evidence.get("treatment")),
                structural_candidate=candidate,
                strategy=_dict(frozen_evidence.get("strategy")),
                quality_issues=_list(_dict(frozen_row.get("quality")).get("issues")) + _list(frozen_row.get("quality_issues")),
            )
            roots.append({
                "root_cause": root,
                "original_rank": rank,
                "rank_score": ranked_row.get("score"),
                "repair_type": _repair_type(root),
                "target_dimensions": sorted(TARGET_DIMENSIONS[root]),
                "relevant_opportunity_ids": context["relevant_opportunity_ids"],
                "relevant_beat_ids": context["relevant_beat_ids"],
                "relevant_plan_shot_ids": context["relevant_plan_shot_ids"],
                "allowed_character_ids": context["allowed_character_ids"],
                "source_fingerprint": fingerprint({
                    "root_cause": root,
                    "opportunities": context["relevant_opportunities"],
                    "beats": context["relevant_beats"],
                    "shots": context["relevant_shots"],
                    "target_dimensions": sorted(TARGET_DIMENSIONS[root]),
                }),
                "historical_evidence": {
                    "root_cause_evidence": _list(_dict(_dict(targeted_row.get("repair")).get("ranked_root_causes")).get("evidence")),
                    "source_targeted_artifact": "artifacts/director-quality-v2-4-targeted-tail-pilot-20260914T090340Z.json",
                },
            })
        if not roots:
            raise ValueError(f"no recoverable historical roots for {scene_id}")
        scene_origin = _text(scene_meta.get("scene_type")) or "unknown"
        scenes.append({
            "scene_id": scene_id,
            "scene_origin": scene_origin,
            "source_type": _text(scene_meta.get("source")),
            "scene_metadata": {"book_id": scene_meta.get("book_id"), "episode": scene_meta.get("episode"), "scene_name": scene_meta.get("scene_name")},
            "baseline_candidate_fingerprint": fingerprint(candidate),
            "contract_fingerprint": _text(contract.get("contract_fingerprint")) or fingerprint(contract),
            "baseline_director_quality": frozen_row.get("director_quality_score"),
            "baseline_creative_value": frozen_row.get("creative_value"),
            "baseline_over_directing": _dict(frozen_row.get("over_directing")),
            "baseline_shot_count": len(_list(candidate.get("shots"))),
            "root_causes": roots,
        })
    approved = sum(item["scene_origin"] == "approved_record" for item in scenes)
    fixtures = len(scenes) - approved
    root_count = sum(len(item["root_causes"]) for item in scenes)
    return {
        "schema_version": "director-quality-v2-4-3-targeted-tail-manifest-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "frozen": True,
        "selection_policy": {
            "source_freeze": "artifacts/director-quality-v2-4-b2-freeze.json",
            "historical_targeted_artifact": "artifacts/director-quality-v2-4-targeted-tail-pilot-20260914T090340Z.json",
            "triggered_tail_only": True,
            "max_root_causes_per_scene": 2,
            "max_semantic_attempts_per_root_cause": 2,
            "ranking_recomputed": False,
        },
        "counts": {
            "selected_scene_count": len(scenes),
            "approved_record_scene_count": approved,
            "fixture_scene_count": fixtures,
            "expected_historical_root_count": 27,
            "recovered_root_count": root_count,
            "max_semantic_attempts": root_count * 2,
        },
        "source_provenance": _dict(freeze.get("provenance")),
        "scenes": scenes,
    }


def main() -> int:
    output = ARTIFACTS / "director-quality-v2-4-3-targeted-tail-manifest.json"
    manifest = build_manifest()
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": output.relative_to(ROOT).as_posix(), "scene_count": manifest["counts"]["selected_scene_count"], "root_count": manifest["counts"]["recovered_root_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
