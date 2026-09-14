"""Deterministically select the smallest valid V2.4.2 protocol canary set."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.director_tail_repair import REPAIR_SCOPES
from core.director_tail_repair_executor import TARGET_DIMENSIONS
from core.director_tail_repair_ir import ROOT_CAUSE_TYPES


ARTIFACTS = ROOT / "artifacts"
FREEZE_PATH = ARTIFACTS / "director-quality-v2-4-b2-freeze.json"
EVIDENCE_PATH = ARTIFACTS / "director-quality-v2-3-phase-b2-evidence.json"
OUTPUT_PATH = ARTIFACTS / "director-quality-v2-4-2-protocol-canary-manifest.json"


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def build_manifest() -> dict:
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    evidence_by_id = {
        str(item.get("scene", {}).get("scene_id")): item
        for item in evidence.get("scenes", [])
        if isinstance(item, dict) and isinstance(item.get("scene"), dict)
    }
    candidates = []
    for row in freeze.get("scenes", []):
        if not isinstance(row, dict) or not row.get("tail_repair", {}).get("triggered"):
            continue
        scene_id = str(row.get("scene_id") or "")
        ev = evidence_by_id.get(scene_id, {})
        contract = ev.get("contract")
        candidate = ev.get("final_candidate") or ev.get("baseline")
        if not isinstance(contract, dict) or not isinstance(candidate, dict):
            continue
        for root_cause in row.get("tail_repair", {}).get("root_causes", []):
            repair_types = sorted(ROOT_CAUSE_TYPES.get(str(root_cause), set()))
            dimensions = sorted(TARGET_DIMENSIONS.get(str(root_cause), set()))
            if not repair_types or not dimensions or str(root_cause) not in REPAIR_SCOPES:
                continue
            for repair_type in repair_types:
                source = {"freeze": row, "evidence": {"scene": ev.get("scene"), "contract": contract, "candidate": candidate, "strategy": ev.get("strategy"), "treatment": ev.get("evidence", {}).get("treatment"), "blocking": ev.get("evidence", {}).get("blocking")}}
                candidates.append({
                    "sample_id": f"canary-{repair_type}-{_fingerprint({'scene_id': scene_id, 'root_cause': root_cause})[:12]}",
                    "scene_id": scene_id,
                    "root_cause": str(root_cause),
                    "repair_type": repair_type,
                    "target_dimensions": dimensions,
                    "reason_selected": "deterministic first complete frozen sample for repair_type; frozen root cause is repairable and has target dimensions",
                    "source_artifact": "artifacts/director-quality-v2-4-b2-freeze.json",
                    "source_fingerprint": _fingerprint(source),
                    "_source": source,
                })
    # Prefer one sample per repair type, then one scene per sample.  Stable
    # sorting keeps the manifest comparable across runs.
    selected = []
    used_types = set()
    used_scenes = set()
    for item in sorted(candidates, key=lambda x: (x["repair_type"], x["scene_id"], x["root_cause"])):
        if item["repair_type"] in used_types or item["scene_id"] in used_scenes:
            continue
        selected.append({key: value for key, value in item.items() if key != "_source"})
        used_types.add(item["repair_type"])
        used_scenes.add(item["scene_id"])
        if len(selected) >= 5:
            break
    return {
        "schema_version": "director-quality-v2-4-2-protocol-canary-manifest-v1",
        "source_artifacts": [str(FREEZE_PATH.relative_to(ROOT)).replace("\\", "/"), str(EVIDENCE_PATH.relative_to(ROOT)).replace("\\", "/")],
        "selection_policy": "one complete repairable frozen sample per repair_type, at most one sample per scene, stable lexical order",
        "sample_count": len(selected),
        "semantic_attempt_budget": len(selected) * 2,
        "samples": selected,
        "side_effects": {"production": 0, "storyboard": 0, "media": 0, "image": 0, "video": 0, "object_storage": 0, "production_shadow": 0},
    }


if __name__ == "__main__":
    OUTPUT_PATH.write_text(json.dumps(build_manifest(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(OUTPUT_PATH.relative_to(ROOT)).replace("\\", "/"), **build_manifest()}, ensure_ascii=False, indent=2))
