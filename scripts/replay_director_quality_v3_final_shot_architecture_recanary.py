"""Offline adjudication of the captured Final Re-Canary responses.

Used only after the three authorized calls have completed.  It never calls a
provider; it refreshes derived QA after deterministic validator corrections.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
ART = ROOT / "artifacts"
OUT = ART / "director-quality-v3-final-shot-architecture-recanary-scenes"

def _d(v): return v if isinstance(v, dict) else {}
def _l(v): return v if isinstance(v, list) else []
def _write(p, v): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def main():
    import scripts.run_director_quality_v3_final_shot_architecture_recanary as runner
    rows = runner._rows(); requests = [runner._request(r) for r in rows]; scenes=[]
    for row, req in zip(rows, requests):
        name = runner._safe(row["scene_id"]); base = OUT / name; raw = (base / "raw-response.txt").read_text(encoding="utf-8")
        checked = runner._strict_validate(row, raw)
        scenes.append({"scene_id": row["scene_id"], "request_fingerprint": runner._fp(req), "raw_response": raw, "raw_response_fingerprint": runner._fp(raw), "provider_calls": 1, **checked})
    from core.shot_architecture import compare_architectures
    distinct = compare_architectures([s["canonical"] or s["normalized_ir"] for s in scenes])
    for s in scenes: s["distinctiveness"] = distinct
    counts = {"protocol": sum(s["protocol"]["status"] == "PASS" for s in scenes), "canonical": sum(bool(s.get("canonical")) for s in scenes), "authority": sum(s["authority"]["status"] == "SAFE" for s in scenes), "identity": sum(s["identity"]["status"] == "PASS" for s in scenes), "beat_coverage": sum(s["coverage"].get("beat_coverage", False) for s in scenes), "phase_coverage": sum(s["coverage"].get("phase_coverage", False) for s in scenes), "future_information_leak": sum(s["information"].get("future_information_leak_count", 0) for s in scenes), "structural_hard_error": sum(len(s["protocol"].get("errors", [])) for s in scenes), "reaction_hard_error": sum(len(s["reaction"].get("hard_errors", [])) for s in scenes), "reaction_missing_stimulus": sum(s["reaction"].get("missing_stimulus", 0) for s in scenes), "invalid_reaction_order": sum(s["reaction"].get("invalid_order", 0) for s in scenes), "definite_composite": sum(s["atomicity"].get("definite_composite_count", 0) for s in scenes), "continuous_framing": sum(s["atomicity"].get("continuous_framing_count", 0) for s in scenes), "atomicity_review_required": sum(s["atomicity"].get("review_required_count", 0) for s in scenes), "hard_topology": sum(len(s["topology"].get("hard_errors", [])) for s in scenes), "redundant_shots": sum(s["topology"].get("redundancy_count", 0) for s in scenes), "mechanical_dialogue_coverage": sum(s["director_qa"].get("mechanical_dialogue_coverage", 0) for s in scenes), "strong_or_usable": sum(s["director_qa"].get("signal") in {"SHOT_ARCHITECTURE_STRONG", "SHOT_ARCHITECTURE_USABLE"} for s in scenes)}
    result = json.loads((ART / "director-quality-v3-final-shot-architecture-recanary-real.json").read_text(encoding="utf-8")); result.update({"scenes": scenes, "counts": counts, "distinctiveness": distinct, "replay_provider_calls": 0, "adjudication": "OFFLINE_AFTER_CALL_VALIDATOR_CORRECTION", "harness_failure_detected": False, "status": "DIRECTOR_V3_FINAL_SHOT_ARCHITECTURE_RECANARY_FAILED", "ready_for_final_shot_architecture_review": False})
    _write(ART / "director-quality-v3-final-shot-architecture-recanary-real.json", result)
    comparisons = {}
    old = json.loads((ART / "director-quality-v3-shot-architecture-forensic-replay.json").read_text(encoding="utf-8"))
    for i, s in enumerate(scenes): comparisons[s["scene_id"]] = runner._compare(old["scenes"][i], s)
    for row, scene in zip(rows, scenes):
        name = runner._safe(row["scene_id"]); base = OUT / name
        for suffix, value in (("parsed-envelope", scene.get("parsed_envelope")), ("normalized-ir", scene.get("normalized_ir")), ("canonical", scene.get("canonical") or {}), ("protocol", scene["protocol"]), ("authority", scene["authority"]), ("identity", scene["identity"]), ("coverage", scene["coverage"]), ("spatial", scene["spatial"]), ("information", scene["information"]), ("reaction", scene["reaction"]), ("atomicity", scene["atomicity"]), ("topology", scene["topology"]), ("director-qa", scene["director_qa"])): _write(base / f"{suffix}.json", value or {})
    for suffix, payload in (("protocol", {s["scene_id"]: s["protocol"] for s in scenes}), ("authority", {s["scene_id"]: s["authority"] for s in scenes}), ("identity", {s["scene_id"]: s["identity"] for s in scenes}), ("coverage", {s["scene_id"]: s["coverage"] for s in scenes}), ("spatial", {s["scene_id"]: s["spatial"] for s in scenes}), ("information", {s["scene_id"]: s["information"] for s in scenes}), ("reaction", {s["scene_id"]: s["reaction"] for s in scenes}), ("atomicity", {s["scene_id"]: s["atomicity"] for s in scenes}), ("topology", {s["scene_id"]: s["topology"] for s in scenes}), ("director-qa", {s["scene_id"]: s["director_qa"] for s in scenes}), ("comparison", comparisons)): _write(ART / f"director-quality-v3-final-shot-architecture-recanary-{suffix}.json", payload)
    pointer = json.loads((ART / "director-quality-v3-current-stage-authority.json").read_text(encoding="utf-8")); pointer.setdefault("shot_architecture", {})["final_recanary"] = {"status": "FAILED", "prompt_contract_path_exhausted": True, "next_step": "SHOT_ARCHITECTURE_GENERATION_ARCHITECTURE_REDESIGN"}; pointer["shot_architecture"]["production_shotplan"] = "HOLD"; _write(ART / "director-quality-v3-current-stage-authority.json", pointer)
    rows_md = "\n".join(f"| {s['scene_id']} | {len(_l((s.get('normalized_ir') or {}).get('shots')))} | {s['protocol']['status']} | {s['reaction'].get('missing_stimulus',0)} | {s['reaction'].get('invalid_order',0)} | {s['atomicity'].get('definite_composite_count',0)} | {s['director_qa'].get('signal')} |" for s in scenes)
    report = f"# Director Quality V3 — Final Shot Architecture Re-Canary\n\n**Status:** `DIRECTOR_V3_FINAL_SHOT_ARCHITECTURE_RECANARY_FAILED`\n\n## Final As-Built Verification\n\n- Authorized/attempted provider calls: `3/3`; successful responses: `{result.get('successful_http_calls', 0)}`; semantic/format/repair/transport retries: `0/0/0/0`.\n- This report is an offline adjudication of the immutable captured responses; no additional provider call was made.\n- Protocol / Canonical / Authority / Identity: `{counts['protocol']}/3 / {counts['canonical']}/3 / {counts['authority']}/3 / {counts['identity']}/3`.\n- Beat / Phase coverage: `{counts['beat_coverage']}/3 / {counts['phase_coverage']}/3`; future leak: `{counts['future_information_leak']}`.\n- Reaction hard/missing stimulus/invalid order: `{counts['reaction_hard_error']}/{counts['reaction_missing_stimulus']}/{counts['invalid_reaction_order']}`.\n- Definite composite / continuous framing / atomicity review: `{counts['definite_composite']}/{counts['continuous_framing']}/{counts['atomicity_review_required']}`.\n- Hard topology: `{counts['hard_topology']}`; mechanical dialogue: `{counts['mechanical_dialogue_coverage']}`.\n\n| Scene | Shots | Protocol | Missing stimulus | Invalid order | Definite composite | Director signal |\n|---|---:|---|---:|---:|---:|---|\n{rows_md}\n\n## Decision\n\n`FINAL_RECANARY_STATUS=DIRECTOR_V3_FINAL_SHOT_ARCHITECTURE_RECANARY_FAILED`\n`SHOT_ARCHITECTURE_PROMPT_CONTRACT_PATH_EXHAUSTED=true`\n`NEXT_ARCHITECTURE=Scene Strategy → Visual / Editorial Spine → Shot Topology Skeleton → Atomic Shot Expansion → Deterministic QA`\n`READY_FOR_PRODUCTION_SHOTPLAN=false`\n`HUMAN_PREFERENCE_REVIEW=NOT_RECORDED`\n"
    (ART / "director-quality-v3-final-shot-architecture-recanary-report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": result["status"], "counts": counts, "replay_provider_calls": 0}, ensure_ascii=False, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
