"""Generate provider-free V2.4.1 audit artifacts from the frozen pilot."""
from __future__ import annotations
import copy, json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]; ART = ROOT / "artifacts"
sys.path.insert(0, str(ROOT))
from core.director_quality_validator import score_director_quality

def text(v): return str(v or "").strip()
def d(v): return v if isinstance(v, dict) else {}
def l(v): return v if isinstance(v, list) else []

def inventory():
    p = ART / "director-quality-v2-4-targeted-tail-pilot-20260914T090340Z.json"
    payload = json.loads(p.read_text(encoding="utf-8"))
    errors=[]; attempts=0
    for scene in l(payload.get("scenes")):
        for root in l(d(scene.get("repair")).get("attempts")):
            for attempt in l(root.get("attempts")):
                attempts += 1; errors.append(text(attempt.get("error")))
    field_counts=Counter()
    for error in errors:
        marker = error.split(":",1)[-1]
        for field in [x.strip() for x in marker.split(",") if x.strip()]:
            if field.startswith("document contains forbidden fields"):
                continue
            field_counts[field]+=1
    return {"schema_version":"director-quality-v2-4-1-provider-output-shape-inventory-v1","source_artifact":"artifacts/director-quality-v2-4-targeted-tail-pilot-20260914T090340Z.json","raw_outputs_persisted":False,"raw_output_count":0,"attempt_count":attempts,"observed_error_count":len(errors),"observed_error_shapes":{"forbidden_fields":sum("forbidden fields" in x for x in errors),"target_dimension_not_improved":sum("TARGET_DIMENSION_NOT_IMPROVED" in x for x in errors)},"frequent_forbidden_fields":dict(field_counts.most_common()),"shape_categories":{"request_context_echo": ["protocol_version","root_cause","failed_dimensions","relevant_opportunities","relevant_beats","relevant_shots","scene_strategy_subset","immutable_contract_subset","previous_intervention","validator_findings","target_metric","attempt_number"],"repair_metadata_echo":["patch_type","patch_version","target_dimension"],"descriptive_only":[],"canonical_like":[],"unsafe_fields":["immutable_contract_subset","root_cause","target_dimension"],"ambiguous_fields":[]},"limitations":["V2.4 runner persisted only bounded errors/fingerprints, not raw provider bodies; no unobserved shape is inferred."]}

def base():
    return {"scene_id":"S","scene_name":"N","shots":[{"plan_shot_id":"S01","beat_id":"B01","event":"e","participants":["C1"],"duration_hint_seconds":3},{"plan_shot_id":"S02","beat_id":"B02","event":"e2","participants":["C1"],"duration_hint_seconds":3}]}

def matrix():
    mappings={
      "WEAK_EDIT_STRATEGY":("EDIT_RHYTHM",lambda p:(p["shots"][0].update({"edit":{"cut_reason":"reaction_complete"}}))),
      "WEAK_EMOTION_ARC":("EMOTIONAL_PROGRESSION",lambda p:(p["shots"][0].update({"emotion":{"intensity":2}}),p["shots"][1].update({"emotion":{"intensity":8}}))),
      "WEAK_INFORMATION_STRATEGY":("INFORMATION_STRATEGY",lambda p:p["shots"][0].update({"information_strategy":{"reveals":["照片"]}})),
      "PERFORMANCE_DIRECTION_WEAK":("PERFORMANCE_DIRECTION",lambda p:p["shots"][0].update({"performance_direction":[{"character_id":"C1","objective":"确认","visible_behavior":"抬眼"}]})),
      "CAMERA_LANGUAGE_GENERIC":("SHOT_DIVERSITY",lambda p:(p["shots"][0].update({"camera":{"shot_size":"MS","angle":"eye","movement":"static","speed":"slow","camera_side":"center"}}),p["shots"][1].update({"camera":{"shot_size":"CU","angle":"eye","movement":"static","speed":"slow","camera_side":"center"}}))),
      "OVER_DIRECTING":("SHOT_DIVERSITY",lambda p:(p["shots"][0].update({"edit":{"cut_reason":"beat_change"},"camera":{"shot_size":"MS"}}),p["shots"][1].update({"camera":{"shot_size":"CU"}}))),
      "UNDER_DIRECTING":("EDIT_RHYTHM",lambda p:(p["shots"][0].update({"edit":{"cut_reason":"beat_change"}}),p["shots"][1].update({"edit":{"cut_reason":"reaction_complete"}}))),
    }
    rows=[]
    for cause,(dim,change) in mappings.items():
        before=base(); after=copy.deepcopy(before); change(after)
        b=score_director_quality(before); a=score_director_quality(after)
        delta=round(float(a["dimensions"].get(dim,0))-float(b["dimensions"].get(dim,0)),4)
        rows.append({"root_cause":cause,"repair_scope":"derived from typed IR","allowed_semantic_fields":"derived from core/director_tail_repair_ir.py","canonical_fields":"deterministic compiler paths","target_dimensions":[dim],"scorer_features":[dim],"synthetic_before":b["dimensions"],"synthetic_after":a["dimensions"],"target_dimension_delta":delta,"status":"REPAIRABLE" if delta>0 else "UNREPAIRABLE_BY_CURRENT_SCORER"})
    return {"schema_version":"director-quality-v2-4-1-repairability-matrix-v1","generated_at":datetime.now(timezone.utc).isoformat(),"rows":rows,"scorer_sensitivity_gaps":[r["root_cause"] for r in rows if r["status"]!="REPAIRABLE"]}

def main():
    inv=inventory(); mat=matrix()
    (ART/"director-quality-v2-4-1-provider-output-shape-inventory.json").write_text(json.dumps(inv,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (ART/"director-quality-v2-4-1-repairability-matrix.json").write_text(json.dumps(mat,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    results=[{"attempt_index":i+1,"status":"AMBIGUOUS_REJECTED","reason":"raw provider body unavailable; error-only evidence cannot be converted safely"} for i in range(inv["attempt_count"])]
    replay={"schema_version":"director-quality-v2-4-1-recorded-output-replay-v1","source_artifact":inv["source_artifact"],"raw_outputs_available":False,"replayed_count":inv["attempt_count"],"results":results,"summary":{"SAFE_IR_CONVERTIBLE":0,"UNSAFE_REJECTED":0,"AMBIGUOUS_REJECTED":inv["attempt_count"],"UNKNOWN_EXCEPTION":0},"reason":"Raw provider bodies were not persisted by V2.4; error-only evidence is conservatively classified as ambiguous and never adapted."}
    (ART/"director-quality-v2-4-1-recorded-output-replay.json").write_text(json.dumps(replay,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"inventory":inv["attempt_count"],"matrix_rows":len(mat["rows"]),"scorer_gaps":mat["scorer_sensitivity_gaps"]},ensure_ascii=False))
if __name__=="__main__": main()
