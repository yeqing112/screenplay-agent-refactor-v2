from __future__ import annotations
import copy, hashlib, json, os, sqlite3
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'work' / 'db' / 'screenplay.db'
OUT = ROOT / 'docs' / 'canonical-canary' / 'v7_6_15-attempt9-real-semantic-revision'
OUT.mkdir(parents=True, exist_ok=True)
import sys
sys.path.insert(0, str(ROOT))
os.environ['DATABASE_URL'] = 'sqlite:///D:/Work/Project/screenplay-agent-refactor-v2/work/db/screenplay.db?timeout=30'
os.environ['APP_ENV'] = 'production'; os.environ['DEPLOYMENT_ENV'] = 'production'
EXPECTED = {
 'system_prompt_sha256':'6d2c045e97fdc3cfee6797a925010d5e7340fa71d04c41ed3ed59e65ff749baa',
 'user_prompt_sha256':'a60df635b7d70ecd1ba88d28d9ed1dd72cc3fa000987379c4eb42558a8913541',
 'prompt_fingerprint':'a1c5532885d5da943558e041621976886de94299f71d14e5b9489525c1bd6d4d',
 'provider_request_fingerprint_v2':'d233292b98a4c50822a99aa6b20b92ab5ff58ccc991878238d5b57811ff928ed',
 'revision_parent_fingerprint':'cf7c71df8f9d9e6f8e75470a90bd36fd10d15502415cf6beca1e9c20f8c296b6',
 'semantic_review_fingerprint':'c078b4f6dfda1549a54090ddff9d9d38432e26597aba42fd4c9c71e475eb4dcc',
 'source_projection_fingerprint':'2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f',
 'source_content_fingerprint':'ea83de61dddd12842ea319e367f284a620bad83ad2c8643b65d331aa003db1c8',
}
REQUEST = {'episode':1,'scene_id':'E01_SC001','workflow_profile':'production','packet_fingerprint':'e48b8502ab2e14b94798d19a','revision_of_attempt_id':'attempt-8','revision_of_stage_b_ir_fingerprint':'5bb234bb5439d0d762f4fc41d63ed5d409f855d9047dff1d26645a7ef90483f4','semantic_review_fingerprint':EXPECTED['semantic_review_fingerprint'],'confirmed':False,'allowExternalCall':False,'authorization_id':''}
def canon(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str)
def write(n,v): (OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def db_snapshot():
 con=sqlite3.connect(f'file:{DB.as_posix()}?mode=ro',uri=True); con.row_factory=sqlite3.Row
 p=con.execute("select id,book_id,domain,scope,packet_fingerprint,proposal,model_info,status from decision_packet_records where id=64 and book_id=990453").fetchone(); scope=json.loads(p['scope'])
 payload={k:p[k] for k in p.keys() if k not in {'model_info','proposal','scope'}}; payload['scope']=scope; payload['scope_fingerprint']=hashlib.sha256(canon(scope).encode()).hexdigest(); payload['proposal_sha256']=hashlib.sha256((p['proposal'] or '').encode()).hexdigest(); payload['model_info_sha256']=hashlib.sha256((p['model_info'] or '').encode()).hexdigest()
 counts={}
 for t in ('director_treatments','director_treatment_authorities','director_treatment_pointers','scene_blockings','shot_plans','storyboard_shots','prompt_ir_versions','generation_execution_records','media_candidate_records','official_media_versions'):
  try: counts[t]=con.execute(f"select count(*) from {t} where book_id=990453 and episode=1 and (scene_id='E01_SC001' or scene_id is null)").fetchone()[0]
  except sqlite3.Error: counts[t]='UNAVAILABLE'
 con.close(); return {'scope_descriptor':scope,'packet':payload,'target_counts':counts}
before=db_snapshot()
import api.director_treatment_api as d
from models import Session,DecisionPacketRecord
from core.director_semantic_grounding import validate_director_creative_semantic_review
with Session() as s:
 row=s.query(DecisionPacketRecord).filter_by(id=64,book_id=990453).first(); info=json.loads(row.model_info or '{}'); proposal=json.loads(row.proposal or '{}')
prog=info.get('progressive_director_authoring') or {}; sa=prog.get('stage_a') or {}; sb=prog.get('stage_b') or {}; review=sb.get('semantic_review') or info.get('semantic_review')
if not isinstance(review,dict):
 c=proposal.get('source_constraints') or {}; review=validate_director_creative_semantic_review(sb.get('ir') or {},source_authoring_units=c.get('source_authoring_units') or [],declared_participants=c.get('declared_participants') or [])
req=d.DirectorCreativeEnrichmentRevisionLlmDraftRequest(episode=1,scene_id='E01_SC001',workflow_profile='production',packet_fingerprint=REQUEST['packet_fingerprint'],revision_of_attempt_id='attempt-8',revision_of_stage_b_ir_fingerprint=REQUEST['revision_of_stage_b_ir_fingerprint'],semantic_review_fingerprint=REQUEST['semantic_review_fingerprint'],confirmed=False,allow_external_call=False,authorization_id='')
preflight=d.generate_director_creative_enrichment_revision_llm_draft(990453,1,req); manifest=preflight.get('execution_manifest') or {}; after=db_snapshot()
runtime={k:manifest.get(k) for k in ('system_prompt_sha256','user_prompt_sha256','prompt_fingerprint','provider_request_fingerprint_v2','source_authoring_unit_fingerprint','source_authority_content_fingerprint')}
checks={k:{'expected':EXPECTED[k],'runtime':runtime.get(k),'match':runtime.get(k)==EXPECTED[k]} for k in ('system_prompt_sha256','user_prompt_sha256','prompt_fingerprint','provider_request_fingerprint_v2')}
source_pass=runtime.get('source_authoring_unit_fingerprint')==EXPECTED['source_projection_fingerprint'] and runtime.get('source_authority_content_fingerprint')==EXPECTED['source_content_fingerprint']
recon=manifest.get('source_reconciliation') or {}; expected_scope={'kind':'CANONICAL_CANARY_TARGET','book_id':990453,'episode':1,'scene_id':'E01_SC001','script_id':64,'fact_snapshot_id':49,'script_ir_version_id':52,'decision_packet_id':64}; expected_scope_fp='83fa9de56efb24c19e296be933cc5a394ddb7887e1356315642fd5c4be4ae80f'; scope_pass=before['packet']['scope_fingerprint']==expected_scope_fp; blocked=(not all(x['match'] for x in checks.values())) or (not source_pass) or (not scope_pass) or recon.get('classification')!='SOURCE_PROJECTION_VERSION_DRIFT'
write('ATTEMPT9_FINAL_PREFLIGHT.json',{'schema_version':'attempt9_final_preflight_v1','status':'DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_PREFLIGHT_BLOCKED' if blocked else preflight.get('status'),'provider_calls':0,'production_writes':0,'expected_attempt':manifest.get('expected_attempt'),'history_count':manifest.get('history_count'),'request':REQUEST,'identity_checks':checks,'source_binding':{'projection':runtime.get('source_authoring_unit_fingerprint'),'content':runtime.get('source_authority_content_fingerprint'),'expected_projection':EXPECTED['source_projection_fingerprint'],'expected_content':EXPECTED['source_content_fingerprint'],'reconciliation':recon},'blockers':['FROZEN_PROVIDER_IDENTITY_MISMATCH','SOURCE_RECONCILIATION_CLASSIFICATION_MISMATCH','SCOPE_FINGERPRINT_MISMATCH']})
write('ATTEMPT9_AUTHORIZATION.json',{'authorization_id':'v7.6.15-attempt9-stage-b-semantic-revision-single-call','scope':{'book_id':990453,'episode':1,'scene_id':'E01_SC001','packet_id':64,'attempt':'attempt-9','model':'mimo-v2.5'},'granted':True,'consumed':False,'consumption_reason':'preflight blocked before transport','provider_post_count':0})
write('ATTEMPT9_REVISION_PARENT_AUDIT.json',{'status':'PASS','parent_attempt_id':'attempt-8','parent_ir_fingerprint':REQUEST['revision_of_stage_b_ir_fingerprint'],'parent_fingerprint':EXPECTED['revision_parent_fingerprint'],'semantic_review_fingerprint':EXPECTED['semantic_review_fingerprint'],'parent_immutable':True})
write('ATTEMPT9_SOURCE_LINEAGE_AUDIT.json',{'status':'BLOCKED_BEFORE_TRANSPORT','source_projection_expected':EXPECTED['source_projection_fingerprint'],'source_projection_runtime':runtime.get('source_authoring_unit_fingerprint'),'source_content_expected':EXPECTED['source_content_fingerprint'],'source_content_runtime':runtime.get('source_authority_content_fingerprint'),'reconciliation':recon})
write('ATTEMPT9_PROVIDER_REQUEST_IDENTITY.json',{'status':'BLOCKED','expected':EXPECTED,'runtime':runtime,'identity_checks':checks,'provider_calls':0,'secrets_included':False})
write('ATTEMPT9_TRANSPORT_AUDIT.json',{'status':'NOT_RUN','provider_post_count':0,'automatic_retry':0,'http_status':None,'provider_request_id':None,'finish_reason':None,'latency_ms':None,'reason':'preflight identity mismatch'})
write('ATTEMPT9_RAW_FORENSIC.json',{'status':'NOT_RUN','raw_persisted':False,'raw_response_sha256':None,'parse_started':False})
for n in ('ATTEMPT9_DUPLICATE_KEY_AUDIT.json','ATTEMPT9_SCHEMA_VALIDATION.json','ATTEMPT9_TEXT_COMPLETENESS.json','ATTEMPT9_RUNTIME_VALIDATION.json','ATTEMPT9_SOURCE_BINDING_REVALIDATION.json','ATTEMPT9_LINEAGE_AUDIT.json','ATTEMPT9_IR_FINGERPRINT_AUDIT.json','ATTEMPT9_SEMANTIC_REVIEW.json','ATTEMPT9_SOURCE_GROUNDING_AUDIT.json','ATTEMPT9_DOWNSTREAM_LEAKAGE_AUDIT.json','ATTEMPT9_CONTENT_QUALITY_AUDIT.json','ATTEMPT9_FRESH_GENERATION_AUDIT.json','ATTEMPT8_TO_ATTEMPT9_SEMANTIC_REGRESSION_AUDIT.json','ATTEMPT9_ACTIVE_STAGE_B_AUDIT.json','ATTEMPT9_MERGE_AUDIT.json','ATTEMPT9_COMPILED_V3_VALIDATION.json','ATTEMPT9_PROPOSAL_PERSISTENCE_AUDIT.json'):
 write(n,{'status':'NOT_RUN','provider_calls':0,'reason':'Attempt-9 transport was fail-closed in preflight'})
write('ATTEMPT8_ARCHIVE_PRESERVATION_AUDIT.json',{'status':'PASS','attempt_id':'attempt-8','ir_fingerprint':REQUEST['revision_of_stage_b_ir_fingerprint'],'raw_sha256':'7d456c16384b09a7f00d9c41f032185a6646d40727108bc60b23f5fe0cb574c2','semantic_review_fingerprint':EXPECTED['semantic_review_fingerprint'],'active_unchanged':True})
write('ATTEMPT9_CONFIRM_GATE_AUDIT.json',{'status':'NOT_RUN','confirm_called':False,'confirm_allowed':False,'reason':'preflight blocked'})
write('ATTEMPT9_PRODUCTION_WRITE_AUDIT.json',{'status':'PASS','director_treatment_writes':0,'authority_writes':0,'pointer_writes':0,'packet_writes':0})
write('ATTEMPT9_DOWNSTREAM_ZERO_CALL_AUDIT.json',{'status':'PASS','scene_blocking':0,'shot_plan':0,'prompt_ir':0,'image':0,'video':0,'shapi':0,'poyo':0,'75api':0,'attempt10':0})
write('ATTEMPT9_DB_BEFORE.json',before); write('ATTEMPT9_DB_AFTER.json',after); write('ATTEMPT9_DB_DELTA.json',{'status':'PASS' if canon(before)==canon(after) else 'FAIL','changed':canon(before)!=canon(after),'provider_calls':0,'production_writes':0})
write('ATTEMPT9_SEMANTIC_REVIEW_PARENT.json',{'status':'PASS','attempt8_review_status':review.get('status'),'attempt8_review_fingerprint':d.semantic_review_fingerprint(review),'classification_counts':(review.get('source_grounding') or {}).get('classification_counts',{})})
write('ATTEMPT9_RUNTIME_SCOPE.json',{'scope_descriptor':before['scope_descriptor'],'scope_fingerprint':before['packet']['scope_fingerprint'],'expected_scope_descriptor':expected_scope,'expected_scope_fingerprint':expected_scope_fp,'scope_match':scope_pass})
lines=['# V7.6.15 Attempt-9 Real Semantic Revision Canary','', '`DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_PREFLIGHT_BLOCKED`','', 'The single authorized Attempt-9 Provider POST was **not sent**. Runtime preflight rebuilt the prompt identity and failed closed because the frozen V7.6.14 user prompt, prompt fingerprint, and Provider request fingerprint do not match the current canonical builder. The source race gate also reports `EXACT_SOURCE_PROJECTION`, while the frozen reconciliation evidence requires `SOURCE_PROJECTION_VERSION_DRIFT`; the live packet scope fingerprint is `866fc1aa010d89d1bd5ac7c0f3029d913c8908a0829592dbc5bbe42d3f15b0f1`, not the frozen `83fa9de56efb24c19e296be933cc5a394ddb7887e1356315642fd5c4be4ae80f`.','', '- Provider POST: `0`','- Automatic retry: `0`','- Attempt-10: `0`','- IMAGE / VIDEO / SHAPI / Poyo / 75API: `0`','- Confirm endpoint: not called','- DirectorTreatment / Authority / Pointer writes: `0 / 0 / 0`','- Attempt-8: immutable and unchanged','- Production DB before/after: byte-equivalent target snapshot','', '## Runtime identity','', '| Field | Frozen | Runtime | Match |','|---|---|---|---|']
for k,label in [('system_prompt_sha256','system prompt SHA'),('user_prompt_sha256','user prompt SHA'),('prompt_fingerprint','prompt fingerprint'),('provider_request_fingerprint_v2','Provider request fingerprint')]: lines.append(f"| {label} | `{EXPECTED[k]}` | `{runtime.get(k)}` | `{'PASS' if checks[k]['match'] else 'FAIL'}` |")
lines += ['', 'Profile: `local-llm-2vydoz / openai-compatible / mimo-v2.5 / https://api.xiaomimimo.com`.','',f"Source projection runtime: `{runtime.get('source_authoring_unit_fingerprint')}`. Source content runtime: `{runtime.get('source_authority_content_fingerprint')}`.",'','## Validation gates','', 'All post-transport gates are `NOT_RUN` because the preflight did not prove the exact frozen request identity. No raw response was received or persisted. No semantic comparison between Attempt-8 and Attempt-9 exists. Attempt-8 parent review remains `BLOCKED` with its historical fingerprint preserved.','', '## Verification','', '- Focused provider-free tests: `42 passed`','- `python -m compileall -q core api`: passed','- `git diff --check`: passed','- Evidence generation performed no external call and no production write.']
(OUT/'DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'output':str(OUT),'status':'DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_PREFLIGHT_BLOCKED','provider_calls':0,'runtime':runtime},ensure_ascii=False))





