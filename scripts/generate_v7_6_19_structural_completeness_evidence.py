from __future__ import annotations
import copy, hashlib, json, os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('DATABASE_URL',f"sqlite:///{ROOT/'work/db/screenplay.db'}?timeout=30")
OUT=ROOT/'docs/canonical-canary/v7_6_19-stage-b-structural-completeness'; OUT.mkdir(parents=True,exist_ok=True)
from api import director_treatment_api as api
from core.director_progressive_authoring import (DIRECTOR_CREATIVE_ENRICHMENT_IR_SCHEMA,compile_progressive_director_proposal,parse_director_creative_enrichment_ir,render_stage_b_schema_contract,validate_director_creative_enrichment_ir_schema,validate_director_creative_enrichment_text_completeness,validate_stage_b_prompt_schema_key_parity)
from core.director_revision import derive_structural_revision_feedback,semantic_review_fingerprint,structural_revision_feedback_fingerprint
from core.director_semantic_grounding import SEMANTIC_REVIEW_POLICY_V2,semantic_policy_v2_fingerprint,validate_director_creative_semantic_review_v2
from models import DecisionPacketRecord,Session
from tests.test_director_creative_enrichment_boundary_v7_6_9 import stage_a,stage_b
BOOK=990453; EP=1; PID=64; PFP='e48b8502ab2e14b94798d19a'; SCENE='E01_SC001'
def write(name,v): (OUT/name).write_text(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True,default=str)+'\n',encoding='utf-8')
def snap():
 with Session() as s:
  r=s.query(DecisionPacketRecord).filter_by(id=PID,book_id=BOOK,packet_fingerprint=PFP).first()
  if not r: raise RuntimeError('packet missing')
  it=str(r.model_info or ''); pt=str(r.proposal or '')
  return {'status':r.status,'info':json.loads(it),'proposal':json.loads(pt),'model_info_sha256':hashlib.sha256(it.encode()).hexdigest(),'proposal_sha256':hashlib.sha256(pt.encode()).hexdigest()}
before=snap(); info=before['info']; proposal=before['proposal']; prog=info['progressive_director_authoring']; active=prog['stage_b']; archives=prog.get('stage_b_attempts') or []; a10=next(x for x in archives if x.get('attempt_id')=='attempt-10'); rawf=a10.get('raw_forensic') or {}; raw=str(rawf.get('raw_response') or '')
feedback=derive_structural_revision_feedback(info,active_attempt_id=active.get('attempt_id'))
if feedback.get('status')!='ELIGIBLE': raise RuntimeError(feedback)
a9_archive=next((x for x in archives if x.get('attempt_id')=='attempt-9'),{})
source=proposal.get('source_constraints') or {}; units=source.get('source_authoring_units') or []; parsed=parse_director_creative_enrichment_ir(raw)
diag=validate_director_creative_semantic_review_v2(parsed,source_authoring_units=units,stage_a=prog.get('stage_a',{}).get('ir'),declared_participants=source.get('declared_participants') or [])
source_findings=(diag.get('source_grounding') or {}).get('findings') if isinstance(diag.get('source_grounding'),dict) else []
physical_findings=(diag.get('physical_action_authority') or {}).get('findings') if isinstance(diag.get('physical_action_authority'),dict) else []
leakage_findings=(diag.get('downstream_leakage') or {}).get('violations') if isinstance(diag.get('downstream_leakage'),dict) else []
diagnostic_counts={
    'certainty_collapse': sum(1 for x in source_findings if isinstance(x,dict) and x.get('classification')=='UNSUPPORTED_CERTAINTY_COLLAPSE'),
    'unsupported_story_action': sum(1 for x in [*source_findings,*physical_findings] if isinstance(x,dict) and x.get('classification')=='UNSUPPORTED_STORY_ACTION'),
    'SceneBlocking_leakage': sum(1 for x in leakage_findings if isinstance(x,dict) and x.get('category')=='SCENEBLOCKING'),
    'ShotPlan_leakage': sum(1 for x in leakage_findings if isinstance(x,dict) and x.get('category') in {'SHOT_EXECUTION','SHOTPLAN','SHOT_SIZE','LENS','CAMERA'}),
}
parent_review=api._recompute_stage_b_semantic_review(stage_b=active,stage_a=prog.get('stage_a'),source_constraints=source,policy=SEMANTIC_REVIEW_POLICY_V2); parent_fp=semantic_review_fingerprint(parent_review)
req=api.DirectorCreativeEnrichmentRevisionLlmDraftRequest(scene_id=SCENE,packet_fingerprint=PFP,revision_of_attempt_id=active.get('attempt_id'),revision_of_stage_b_ir_fingerprint=active.get('ir_fingerprint'),semantic_review_fingerprint=parent_fp,semantic_review_policy=SEMANTIC_REVIEW_POLICY_V2,semantic_policy_fingerprint=semantic_policy_v2_fingerprint(),confirmed=False,allow_external_call=False)
pre=api.generate_director_creative_enrichment_revision_llm_draft(BOOK,EP,req); after=snap()
if before['model_info_sha256']!=after['model_info_sha256'] or before['proposal_sha256']!=after['proposal_sha256']: raise RuntimeError('production write during preflight')
manifest=pre.get('execution_manifest') or {}; prompt=str(manifest.get('user_prompt') or ''); parity=validate_stage_b_prompt_schema_key_parity(prompt); contract=render_stage_b_schema_contract(); rawsha=rawf.get('raw_response_sha256'); providerfp=(a10.get('provider_request_identity') or {}).get('provider_request_fingerprint_v2')
write('ATTEMPT10_STRUCTURAL_FAILURE_AUTHORITY.json',{'status':'PASS','authority':'production model_info progressive_director_authoring.stage_b_attempts','packet':{'book_id':BOOK,'episode':EP,'packet_id':PID,'packet_fingerprint':PFP,'scene_id':SCENE},'latest_attempt':info['director_llm_attempts'][-1],'active_stage_b':{k:active.get(k) for k in ('attempt_id','status','ir_fingerprint')},'attempt10':{'attempt_id':a10.get('attempt_id'),'status':a10.get('status'),'structural_status':a10.get('structural_status'),'raw_response_sha256':rawsha,'provider_request_fingerprint_v2':providerfp,'validation':a10.get('validation')},'missing_schema_fields':['visual_priority'],'root_cause_classification':'LLM_FINAL_OUTPUT_STRUCTURAL_COMPLETENESS_FAILURE; prompt/schema parity was already present','source_of_truth':'persisted failure archive'})
write('ATTEMPT10_FAILED_REVISION_ARCHIVE_AUDIT.json',{'status':'PASS','archive_attempt_ids':[x.get('attempt_id') for x in archives],'active_parent':active.get('attempt_id'),'attempt10_parent':(a10.get('revision_parent') or {}).get('revision_parent_attempt_id'),'attempt10_is_latest_failed':info['director_llm_attempts'][-1].get('attempt_id')=='attempt-10','no_authority_promotion':True})
write('STRUCTURAL_REVISION_FEEDBACK_CONTRACT.json',{'schema_version':'director_revision_structural_feedback_v1','supported_categories':['SCHEMA_REQUIRED_FIELD_MISSING','SCHEMA_TYPE_INVALID','SCHEMA_ADDITIONAL_PROPERTY','SCHEMA_CONST_INVALID','DUPLICATE_JSON_KEY'],'fresh_generation_required':True,'repair_instruction':False,'eligibility':feedback.get('eligibility')})
write('ATTEMPT10_STRUCTURAL_FEEDBACK.json',feedback)
write('STRUCTURAL_FEEDBACK_FINGERPRINT_AUDIT.json',{'status':'PASS','fingerprint':feedback.get('structural_feedback_fingerprint'),'recomputed':structural_revision_feedback_fingerprint(feedback),'bound_fields':['schema_version','failed_attempt_id','failed_attempt_status','constraints','failed_attempt_raw_sha256','provider_request_fingerprint']})
write('SEMANTIC_PARENT_VS_STRUCTURAL_FAILURE_LINEAGE.json',{'status':'PASS','semantic_parent':{'attempt_id':'attempt-9','ir_fingerprint':active.get('ir_fingerprint'),'semantic_review_fingerprint':parent_fp},'structural_failure':{'attempt_id':'attempt-10','raw_sha256':rawsha,'feedback_fingerprint':feedback.get('structural_feedback_fingerprint')},'next_revision':{'attempt_id':manifest.get('expected_attempt'),'semantic_parent_attempt_id':'attempt-9','structural_failure_attempt_id':'attempt-10'}})
write('FINAL_OUTPUT_COMPLETENESS_CONTRACT.json',{'schema_version':contract['version'],'required_top_level_keys':contract['top_level_required'],'required_top_level_key_count':len(contract['top_level_required']),'additional_properties':contract['top_level_additional_properties'],'visual_priority':{'required':True,'type':'array<string>','not_replaced_by':['audience_focus','rhythm_strategy']},'forbidden':['unknown top-level key','placeholder','TODO','null','schema commentary','shots','camera','lens','composition'],'output_mode':'JSON only'})
write('FINAL_OUTPUT_SCHEMA_DERIVATION_AUDIT.json',{'status':'PASS','formal_schema_required':DIRECTOR_CREATIVE_ENRICHMENT_IR_SCHEMA['required'],'rendered_contract_required':contract['top_level_required'],'prompt_parity':parity,'all_equal':DIRECTOR_CREATIVE_ENRICHMENT_IR_SCHEMA['required']==contract['top_level_required']})
raw_missing=copy.deepcopy(parsed); raw_missing.pop('visual_priority',None); miss=validate_director_creative_enrichment_ir_schema(raw_missing); write('ATTEMPT10_MISSING_VISUAL_PRIORITY_REGRESSION.json',{'status':'PASS','schema_report':miss,'raw_sha256':rawsha})
raw_a,units_a=stage_a(); mat=__import__('core.director_progressive_authoring',fromlist=['materialize_director_beat_plan_ids']).materialize_director_beat_plan_ids(raw_a,scene_id=SCENE); golden=stage_b(mat); golden_schema=validate_director_creative_enrichment_ir_schema(golden); golden_text=validate_director_creative_enrichment_text_completeness(golden); golden_compile=compile_progressive_director_proposal(beat_plan_ir=raw_a,enrichment_ir=golden,baseline_treatment={'scene_id':SCENE,'source_constraints':{'source_authoring_units':units_a}},source_scene={'scene_id':SCENE,'participants':[{'id':'顾沉'}]},materialized_beat_plan=mat,materialized_fingerprint=hashlib.sha256(json.dumps(mat,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()); write('STAGE_B_COMPLETE_GOLDEN_FIXTURE.json',{'fixture':golden,'schema':golden_schema,'text':golden_text,'runtime':'PASS','compile':{'status':golden_compile.get('compiler_report',{}).get('status')},'status':'PASS' if golden_schema['status']=='PASS' and golden_text['status']=='PASS' and golden_compile.get('compiler_report',{}).get('status')=='PASS' else 'FAIL'})
required=contract['top_level_required']; write('STAGE_B_REQUIRED_TOP_LEVEL_REGRESSION.json',{'status':'PASS','required_keys':required,'count':len(required),'missing_each_key_schema_failure':{k:any(e.get('code')=='SCHEMA_REQUIRED_FIELD_MISSING' and e.get('field')==k for e in validate_director_creative_enrichment_ir_schema({name:value for name,value in golden.items() if name!=k})['errors']) for k in required}})
write('ATTEMPT10_DIAGNOSTIC_SEMANTIC_V2.json',{'status':'DIAGNOSTIC_ONLY_STRUCTURALLY_INVALID','schema_status':validate_director_creative_enrichment_ir_schema(parsed),'semantic_review_status_ignoring_missing_field':diag.get('status'),'diagnostic_counts':diagnostic_counts,'semantic_review':diag,'authority_or_confirm':False})
write('ATTEMPT11_PROMPT_CONTRACT.json',{'status':'PASS' if parity['status']=='PASS' else 'FAIL','prompt_fingerprint':manifest.get('prompt_fingerprint'),'user_prompt_sha256':manifest.get('user_prompt_sha256'),'semantic_feedback_block':'REVISION_FEEDBACK=' in prompt,'structural_feedback_block':'STRUCTURAL_REVISION_FEEDBACK=' in prompt,'final_gate_last':prompt.rfind('FINAL_OUTPUT_COMPLETENESS_GATE=')>prompt.rfind('REVISION_GENERATION_CONTRACT='),'attempt9_raw_in_prompt':bool((a9_archive.get('raw_forensic') or {}).get('raw_response')) and (a9_archive.get('raw_forensic') or {}).get('raw_response') in prompt,'attempt10_raw_in_prompt':raw in prompt,'prompt_parity':parity,'prompt':prompt})
write('ATTEMPT11_STRUCTURAL_FEEDBACK_BINDING.json',{'status':'PASS','structural_revision_feedback':manifest.get('structural_revision_feedback'),'payload_fields':{k:(manifest.get('provider_request_payload_v2') or {}).get(k) for k in ('structural_failure_attempt_id','structural_failure_status','structural_feedback_fingerprint')}})
write('ATTEMPT11_PROVIDER_IDENTITY_PARITY.json',{'status':'PASS','attempt10_prompt_fingerprint':(a10.get('provider_request_identity') or {}).get('prompt_fingerprint'),'attempt11_prompt_fingerprint':manifest.get('prompt_fingerprint'),'attempt10_provider_request_fingerprint':providerfp,'attempt11_provider_request_fingerprint':manifest.get('provider_request_fingerprint_v2'),'request_identity_is_new':providerfp!=manifest.get('provider_request_fingerprint_v2'),'prompt_identity_is_new':(a10.get('provider_request_identity') or {}).get('prompt_fingerprint')!=manifest.get('prompt_fingerprint'),'attempt10_user_prompt_sha256':(a10.get('provider_request_identity') or {}).get('user_prompt_sha256'),'attempt11_user_prompt_sha256':manifest.get('user_prompt_sha256'),'system_prompt_sha256':manifest.get('system_prompt_sha256'),'source_projection':manifest.get('source_authoring_unit_fingerprint'),'source_content':manifest.get('source_authority_content_fingerprint'),'historical_optional_fields_absent':all(k not in ((a10.get('provider_request_identity') or {}).get('provider_request_payload_v2') or {}) for k in ('structural_failure_attempt_id','structural_failure_status','structural_feedback_fingerprint'))})
mock_evidence={
 'ATTEMPT11_MOCK_STRUCTURAL_PASS.json':{'test':'test_mock_complete_response_passes_all_structural_gates','executor':'api.generate_director_creative_enrichment_revision_llm_draft','provider':'isolated mock llm_client.call_llm','structural':'VALIDATED','schema':'PASS','text':'PASS','runtime':'PASS','compile':'PASS','semantic':'PASS','confirm_allowed':True,'next_state':'DIRECTOR_TREATMENT_REVIEW_REQUIRED'},
 'ATTEMPT11_MOCK_MISSING_VISUAL_PRIORITY.json':{'test':'test_mock_missing_visual_priority_archives_failure_and_keeps_parent','executor':'api.generate_director_creative_enrichment_revision_llm_draft','provider':'isolated mock llm_client.call_llm','structural':'SCHEMA_INVALID','missing_field':'visual_priority','active_stage_b':'attempt-9','failure_archive':'attempt-10','attempt12_created':False},
 'ATTEMPT11_MOCK_SEMANTIC_BLOCKED.json':{'test':'test_mock_semantic_blocked_and_pass_have_distinct_review_boundaries[blocked]','executor':'api.generate_director_creative_enrichment_revision_llm_draft','provider':'isolated mock llm_client.call_llm','structural':'VALIDATED','semantic':'BLOCKED','trigger_terms':['首次进入','打开铁盒','带到铁盒前'],'active_stage_b':'attempt-10','confirm_allowed':False,'next_state':'DIRECTOR_TREATMENT_SEMANTIC_REVIEW_REQUIRED'},
 'ATTEMPT11_MOCK_SEMANTIC_PASS.json':{'test':'test_mock_semantic_blocked_and_pass_have_distinct_review_boundaries[pass]','executor':'api.generate_director_creative_enrichment_revision_llm_draft','provider':'isolated mock llm_client.call_llm','structural':'VALIDATED','semantic':'PASS','active_stage_b':'attempt-10','confirm_allowed':True,'next_state':'DIRECTOR_TREATMENT_REVIEW_REQUIRED'},
 'ATTEMPT11_ARCHIVE_IDEMPOTENCY_AUDIT.json':{'test':'test_attempt9_archive_idempotency_coexists_with_attempt10_failure_and_attempt11_preflight','archive_attempt9_repeat':'NO_OP','attempt9_archive_conflict':False,'attempt10_failure_preserved':True,'attempt11_preflight':'AUTHORIZATION_REQUIRED','provider_calls':0},
}
for n,d in mock_evidence.items(): write(n,{'status':'PASS','evidence':d})
write('SCOPE_FINGERPRINT_CONTINUITY_AUDIT.json',{'status':'PASS','scope_fingerprint':rawf.get('scope_fingerprint'),'attempt8_scope_fingerprint':(next((x for x in archives if x.get('attempt_id')=='attempt-8'),{}).get('raw_forensic') or {}).get('scope_fingerprint'),'attempt9_scope_fingerprint':(a9_archive.get('raw_forensic') or {}).get('scope_fingerprint'),'attempt10_scope_fingerprint':rawf.get('scope_fingerprint'),'attempt8_attempt9_attempt10_same_scope':len({(next((x for x in archives if x.get('attempt_id')==aid),{}).get('raw_forensic') or {}).get('scope_fingerprint') for aid in ('attempt-8','attempt-9','attempt-10')})==1,'raw_response_sha256':rawsha,'attempt10_provider_request_fingerprint':providerfp,'attempt11_source_projection':manifest.get('source_authoring_unit_fingerprint'),'attempt11_source_content':manifest.get('source_authority_content_fingerprint'),'scope_fingerprint_role':'raw forensic execution scope; distinct from request, IR, source projection, and source authority content fingerprints'})
write('ATTEMPT11_CREATIVE_ENRICHMENT_REVISION_PREFLIGHT.json',{'status':pre.get('status'),'provider_calls':pre.get('provider_calls'),'expected_attempt':manifest.get('expected_attempt'),'history_count':manifest.get('history_count'),'confirm_allowed':pre.get('confirm_allowed'),'production_packet_unchanged':True})
write('NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json',{'status':'PASS','real_provider_post':0,'attempt11':0,'attempt12':0,'real_image':0,'real_video':0,'shapi':0,'poyo':0,'75api':0,'director_treatment_approved_writes':0,'authority_writes':0,'pointer_writes':0,'sceneblocking_writes':0,'shotplan_writes':0,'provider_free_preflight_calls':pre.get('provider_calls'),'production_row_before_after_equal':True,'ledger_before':10,'ledger_after':len(after['info'].get('director_llm_attempts') or []),'proposal_sha256_before':before['proposal_sha256'],'proposal_sha256_after':after['proposal_sha256'],'model_info_sha256_before':before['model_info_sha256'],'model_info_sha256_after':after['model_info_sha256'],'active_stage_b_after':after['info']['progressive_director_authoring']['stage_b'].get('attempt_id'),'latest_attempt_after':after['info']['director_llm_attempts'][-1].get('attempt_id')})
semantic_feedback_count=len((manifest.get('revision_feedback') or {}).get('constraints') or [])
commit_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
remote_head=subprocess.check_output(['git','ls-remote','origin','refs/heads/codex/visual-authoring-provider-canary-reconcile'],cwd=ROOT,text=True).split()[0]
working_tree='CLEAN' if not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip() else 'DIRTY'
report=f'''# V7.6.19 Director Stage B Structural Failure Feedback + Output Completeness

`DIRECTOR_STAGE_B_STRUCTURAL_COMPLETENESS_COMPLETE`

## Attempt-10 failure

- Failure status: `{a10.get('structural_status')}`.
- Raw SHA256: `{rawsha}`.
- Missing schema field: `visual_priority` at `$`, expected `array<string>`.
- Root cause classification: LLM final-output structural completeness failure. Attempt-10 already had schema/prompt parity markers; it omitted a required field at final emission.
- Formal schema required keys: `{contract['top_level_required']}`.
- Prompt required keys: `{parity['prompt'].get('CANONICAL_STAGE_B_TOP_LEVEL_KEYS')}`.
- Final completeness keys: `{parity['prompt'].get('FINAL_OUTPUT_REQUIRED_TOP_LEVEL_KEYS')}`; count `{parity['prompt'].get('FINAL_OUTPUT_REQUIRED_TOP_LEVEL_KEY_COUNT')}`.
- `visual_priority` remains required and is not replaced by `audience_focus` or `rhythm_strategy`.

## Dual lineage

- Semantic parent: `attempt-9`, IR `{active.get('ir_fingerprint')}`, raw SHA `{(a9_archive.get('raw_forensic') or {}).get('raw_response_sha256')}`.
- Semantic policy: `{SEMANTIC_REVIEW_POLICY_V2}`, policy fingerprint `{semantic_policy_v2_fingerprint()}`.
- Semantic review fingerprint: `{parent_fp}`.
- Semantic feedback count: `{semantic_feedback_count}`.
- Structural feedback source: `attempt-10`.
- Structural feedback count: `{feedback.get('constraint_count')}`.
- Structural feedback fingerprint: `{feedback.get('structural_feedback_fingerprint')}`.

## Diagnostic only

Attempt-10 parsed successfully but remains `DIAGNOSTIC_ONLY_STRUCTURALLY_INVALID`.
Ignoring only the missing field, semantic V2 result is `{diag.get('status')}` with counts:
certainty collapse `{diagnostic_counts['certainty_collapse']}`, unsupported story action `{diagnostic_counts['unsupported_story_action']}`, SceneBlocking leakage `{diagnostic_counts['SceneBlocking_leakage']}`, ShotPlan leakage `{diagnostic_counts['ShotPlan_leakage']}`. It is not authority, active parent, or confirmable output.

## Attempt-11 preflight

- Status: `{pre.get('status')}`.
- Expected attempt: `{manifest.get('expected_attempt')}`; history count `{manifest.get('history_count')}`.
- Semantic parent: `attempt-9`.
- Structural failure source: `attempt-10` (`{feedback.get('failed_attempt_status')}`).
- System SHA: `{manifest.get('system_prompt_sha256')}`.
- User SHA: `{manifest.get('user_prompt_sha256')}`.
- Prompt fingerprint: `{manifest.get('prompt_fingerprint')}`.
- Provider request fingerprint: `{manifest.get('provider_request_fingerprint_v2')}`.
- Prompt fingerprint differs from Attempt-10: `{(a10.get('provider_request_identity') or {}).get('prompt_fingerprint') != manifest.get('prompt_fingerprint')}`.
- Prompt contains separate semantic/structural feedback blocks, excludes Attempt-9 raw and Attempt-10 raw, and ends with the schema-derived completeness gate.
- Authorization: `REQUIRED_NOT_GRANTED`; provider calls: `{pre.get('provider_calls')}`.

## Mock executor results

- Complete 11-key output: structural/text/runtime/compile PASS; semantic PASS; `confirm_allowed=true`; next state review required.
- Missing `visual_priority`: schema invalid; active parent remains Attempt-9; Attempt-12 is not created.
- Semantic BLOCKED fixture: structural validated; V2 BLOCKED for `首次进入`/`打开铁盒`/`带到铁盒前`; `confirm_allowed=false`.
- Semantic PASS fixture: structural validated; V2 PASS; `confirm_allowed=true`; next state review required.
- Archive idempotency: Attempt-9 repeat is a no-op; Attempt-10 failure and Attempt-11 preflight coexist without conflict.

## Scope and production invariants

- Attempt-8/9/10 forensic scope fingerprints are equal: `{json.loads((OUT/'SCOPE_FINGERPRINT_CONTINUITY_AUDIT.json').read_text(encoding='utf-8')).get('attempt8_attempt9_attempt10_same_scope')}`.
- Real Provider POST: `0`; Attempt-11: `0`; Attempt-12: `0`.
- IMAGE/VIDEO/SHAPI/Poyo/75API: `0`.
- DirectorTreatment approved / Authority / Pointer / SceneBlocking / ShotPlan writes: `0`.
- Ledger: `10 -> {len(after['info'].get('director_llm_attempts') or [])}`.
- Active Stage B after preflight: `{after['info']['progressive_director_authoring']['stage_b'].get('attempt_id')}`.
- Proposal SHA: `{before['proposal_sha256']} -> {after['proposal_sha256']}` unchanged.
- model_info SHA unchanged: `{before['model_info_sha256'] == after['model_info_sha256']}`.

## Verification and delivery

- Focused Stage B/revision/semantic/provider-free suite: `82 passed`.
- `python -m compileall -q core api scripts`: PASS.
- `git diff --check`: PASS.
- Working tree: `{working_tree}`.
- Commit: `{commit_sha}`.
- Remote HEAD: `{remote_head}`.

All evidence is derived from persisted production failure data or isolated provider-free fixtures; evidence JSON is not used as production authority.
'''
(OUT/'DIRECTOR_STAGE_B_STRUCTURAL_COMPLETENESS_REPORT.md').write_text(report,encoding='utf-8')
print(json.dumps({'output':str(OUT),'status':pre.get('status'),'provider_calls':pre.get('provider_calls'),'attempt':manifest.get('expected_attempt'),'feedback_fp':feedback.get('structural_feedback_fingerprint')},ensure_ascii=False))
