"""Freeze an existing V2.3 B2 artifact for the V2.4 repair pilot.

Freezing is a metadata operation only.  It copies no media and makes no
provider call; the original B2 artifact remains immutable and is referenced
through repo-relative provenance paths and hashes.
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
DEFAULT_PILOT = ARTIFACTS / "director-quality-v2-3-phase-b2-pilot-20260914T040506Z.json"
DEFAULT_EVIDENCE = ARTIFACTS / "director-quality-v2-3-phase-b2-evidence.json"
DEFAULT_OUTPUT = ARTIFACTS / "director-quality-v2-4-b2-freeze.json"


def freeze_b2(*, pilot_path: Path = DEFAULT_PILOT, evidence_path: Path = DEFAULT_EVIDENCE) -> dict[str, Any]:
    from core.director_quality_provenance import build_provenance

    payload = json.loads(pilot_path.read_text(encoding="utf-8"))
    rows = [item for item in payload.get("scenes", []) if isinstance(item, dict)]
    frozen = copy.deepcopy(payload)
    frozen["protocol_version"] = "director-quality-v2-4-b2-freeze"
    frozen["frozen"] = True
    frozen["frozen_at"] = datetime.now(timezone.utc).isoformat()
    frozen["source_evidence"] = {
        "pilot": pilot_path.resolve().relative_to(ROOT.resolve()).as_posix(),
        "evidence": evidence_path.resolve().relative_to(ROOT.resolve()).as_posix(),
    }
    frozen["provenance"] = build_provenance(
        protocol_version="director-quality-v2-4-b2-freeze",
        model=payload.get("model"),
        model_profile=payload.get("model"),
        scenes=rows,
        source_artifacts=[pilot_path, evidence_path],
        evidence_path=evidence_path,
        gate_version=str((payload.get("shadow_gate") or {}).get("schema_version") or ""),
        metric_schema_version="director-quality-v2-4-b2-freeze-v1",
        generated_at=frozen["frozen_at"],
    )
    return frozen


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Freeze B2 artifact for V2.4 offline/targeted replay")
    parser.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = freeze_b2(pilot_path=args.pilot, evidence_path=args.evidence)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "b2_freeze_complete", "output": args.output.resolve().relative_to(ROOT.resolve()).as_posix(), "scene_count": len(result.get("scenes") or []), "commit_sha": result.get("provenance", {}).get("commit_sha"), "source_artifacts": result.get("provenance", {}).get("source_artifacts")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

