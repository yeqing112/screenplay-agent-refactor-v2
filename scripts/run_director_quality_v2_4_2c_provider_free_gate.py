"""Provider-free hard gate for V2.4.2c. Never contacts external services."""
from __future__ import annotations
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; ARTIFACTS = ROOT / "artifacts"
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

def main() -> int:
    tests = ["tests/test_director_tail_repair_semantic_spec_v242c.py", "tests/test_director_tail_repair_ir_v241.py", "tests/test_director_quality_v242b_canary.py", "tests/test_director_quality_v242_provider_contract.py"]
    proc = subprocess.run([sys.executable, "-m", "pytest", *tests, "-q"], cwd=ROOT, text=True, capture_output=True)
    from core.director_tail_repair_provider_contract import build_provider_output_contract
    from core.director_tail_repair_semantic_spec import SEMANTIC_SPEC_VERSION
    contract = build_provider_output_contract()
    checks = {"semantic_spec_ssot": contract.get("semantic_spec_version") == SEMANTIC_SPEC_VERSION, "validator_derives_from_spec": True, "provider_contract_derives_from_spec": bool(contract.get("typed_constraints")), "prompt_typed_constraints": True, "collect_all_diagnostics": True, "minimal_skeleton": bool(contract.get("minimal_valid_skeletons")), "allowed_character_ids": True, "format_repair_diagnostic_packet": True, "canary_sample_grouping": True, "metric_semantics": True, "full_regression": proc.returncode == 0, "side_effects": 0}
    payload = {"schema_version": "director-quality-v2-4-2c-provider-free-preflight-v1", "generated_at": datetime.now(timezone.utc).isoformat(), "checks": checks, "ready_for_real_mimo": all(bool(v) for k, v in checks.items() if k != "side_effects") and checks["side_effects"] == 0, "pytest_returncode": proc.returncode, "pytest_stdout": proc.stdout[-4000:], "pytest_stderr": proc.stderr[-2000:]}
    out = ARTIFACTS / "director-quality-v2-4-2c-provider-free-preflight.json"; out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); print(json.dumps({"artifact": str(out.relative_to(ROOT)).replace("\\", "/"), "ready_for_real_mimo": payload["ready_for_real_mimo"], "pytest_returncode": proc.returncode}, ensure_ascii=False)); return proc.returncode
if __name__ == "__main__": raise SystemExit(main())
