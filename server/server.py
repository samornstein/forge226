#!/usr/bin/env python3
"""Forge226 MCP stdio server. Python 3.10+, standard library only."""
import sys,os,json,hashlib,secrets,traceback
from pathlib import Path
from datetime import datetime,date
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/forge226-coach/scripts'))
from store import Store,now
from imports import read_export
from analysis import summarize,benchmark_history,adherence,history_summary
from session_analysis import analyze_laps
from sources import inspect_file,mapped_export,provider_id
from strava import Strava,ApiError
from garmin import Garmin
from render_dashboard import render

S={'type':'string'};I={'type':'integer'};O={'type':'object'}
def spec(name,description,props,required=(),read=True):
 return {'name':'forge226_'+name,'description':description,'inputSchema':{'type':'object','properties':props,'required':list(required),'additionalProperties':False},'annotations':{'readOnlyHint':read,'destructiveHint':False,'openWorldHint':name in ('strava_connect','strava_sync','strava_disconnect','garmin_connect','garmin_sync','garmin_sync_wellness','garmin_sync_all')}}
TOOLS=[
 spec('status','Inspect runtime and available integrations. Does not expose credentials.',{}),
 spec('sources','Read source preferences and actual built-in connection capabilities. Upload or external labels do not mean a live connection is established.',{'athlete_id':S},('athlete_id',)),
 spec('configure_source','Remember provider choice and enabled state. Modes: manual (manual-only coaching, disables other source preferences), upload, native (Strava or Garmin), external (host-managed connector), requested (no integration yet). Does not grant account access or revoke tokens.',{'athlete_id':S,'provider':S,'mode':{'type':'string','enum':['manual','upload','native','external','requested']},'enabled':{'type':'boolean'}},('athlete_id','provider','mode','enabled'),False),
 spec('source_inspect','Inspect a supplied CSV/JSON/ZIP for tables, fields and small samples; no data saved. Provider independent.',{'path':S},('path',)),
 spec('source_preview','Preview a mapped workout or wellness import from any provider. mapping.fields maps canonical fields to columns; units must declare canonical units after numeric scaling. Does not establish any live connection.',{'athlete_id':S,'provider':S,'kind':{'type':'string','enum':['workout','wellness']},'path':S,'mapping':O},('athlete_id','provider','kind','path','mapping')),
 spec('source_import','Save the exact previewed mapped import, verified by SHA256. Separate workout and wellness storage. Keeps other sources/history. Explain rejected rows before allow_partial=true.',{'athlete_id':S,'provider':S,'kind':{'type':'string','enum':['workout','wellness']},'path':S,'mapping':O,'expected_sha256':S,'allow_partial':{'type':'boolean'}},('athlete_id','provider','kind','path','mapping','expected_sha256'),False),
 spec('list_wellness','Read imported recovery/sleep records with original source scales. They are not counted as workouts.',{'athlete_id':S,'offset':I,'limit':I},('athlete_id',)),
 spec('list_athletes','List local athlete IDs. Select explicitly before reading or changing an athlete.',{}),
 spec('create_athlete','Create a separate local athlete. Do not create duplicates when resuming.',{'name':S,'timezone':S},('name','timezone'),False),
 spec('get_profile','Read saved profile, current revision and active plan version.',{'athlete_id':S},('athlete_id',)),
 spec('save_profile','Replace the profile with a merged complete object. Requires expected_revision from get_profile.',{'athlete_id':S,'profile':O,'expected_revision':I},('athlete_id','profile','expected_revision'),False),
 spec('garmin_preview','Read a supplied Garmin ZIP/JSON/CSV and report normalization, warnings and a digest. No records saved. Ambiguous units need an explicit unit choice.',{'athlete_id':S,'path':S,'units':{'type':'string','enum':['auto','seconds_meters','milliseconds_centimeters']},'distance_unit':{'type':'string','enum':['km','mi','m']}},('athlete_id','path')),
 spec('garmin_import','Import the exact previewed export by expected_sha256. Upserts by source ID and preserves unmatched history. Rejects partial imports unless allow_partial is explicitly true after explaining rejected rows.',{'athlete_id':S,'path':S,'expected_sha256':S,'units':{'type':'string','enum':['auto','seconds_meters','milliseconds_centimeters']},'distance_unit':{'type':'string','enum':['km','mi','m']},'allow_partial':{'type':'boolean'}},('athlete_id','path','expected_sha256'),False),
 spec('list_activities','Read paginated normalized activities for this athlete. Optional inclusive date range.',{'athlete_id':S,'from_date':S,'to_date':S,'offset':I,'limit':I},('athlete_id',)),
 spec('history_summary','Inspect all imported training across a chosen window: observed high-volume weeks, training days versus files, weekday patterns and possible race weeks. Does not infer sustainable fitness.',{'athlete_id':S,'from_date':S,'to_date':S},('athlete_id',)),
 spec('garmin_sync_all','Explicit all-supported-data import: activity summaries (default 730 days) and sleep duration/overnight average HRV (default 90 days). Report per-dataset success/failure; not every Garmin metric. Use only when the athlete requests all supported data.',{'athlete_id':S,'activity_days':I,'wellness_days':I},('athlete_id',),False),
 spec('analyze','Calculate weekly volume, sport frequency, coverage-qualified four-week comparisons and benchmark history. No inferred fitness, mixed-scale scores or race prediction.',{'athlete_id':S,'as_of':S},('athlete_id',)),
 spec('review_summary','Read a saved plan alongside recent actual-session candidates, confirmed outcomes, check-ins and evidence. Default review is the last seven days. Does not change the plan or declare unmatched workouts missed.',{'athlete_id':S,'as_of':S,'from_date':S,'version':I},('athlete_id',)),
 spec('analyze_session','Analyze an explicitly normalized JSON lap file for a selected stored activity. Optional comparison: firstLapIds, secondLapIds, context. Descriptive lap metrics only; no FIT/stream ingestion or inferred physiological scores.',{'athlete_id':S,'activity_id':S,'path':S,'comparison':O},('athlete_id','activity_id','path')),
 spec('save_checkin','Persist a dated readiness report. Does not alter the plan.',{'athlete_id':S,'checkin':O},('athlete_id','checkin'),False),
 spec('get_context','Read saved profile, recent check-ins, import receipts, connection status and plan version list. Does not disclose tokens.',{'athlete_id':S},('athlete_id',)),
 spec('get_plan','Read active plan or a specific saved version.',{'athlete_id':S,'version':I},('athlete_id',)),
 spec('save_plan_draft','Save a full canonical state as a versioned draft and validate it. Does not activate. parent_version must match current active version, or null for first plan.',{'athlete_id':S,'state':O,'parent_version':{'type':['integer','null']}},('athlete_id','state','parent_version'),False),
 spec('activate_plan','Activate a validated, reviewed draft after athlete authorization. expected_active must match current active version or null.',{'athlete_id':S,'version':I,'expected_active':{'type':['integer','null']}},('athlete_id','version','expected_active'),False),
 spec('export_dashboard','Generate HTML and portable state from the selected saved plan with latest evidence/check-ins. No external publishing. Returns absolute file paths.',{'athlete_id':S,'version':I},('athlete_id',),False),
 spec('garmin_status','Read last verified Garmin Personal API connection status, token expiry and sync receipts. Does not expose secrets or contact Garmin.',{'athlete_id':S},('athlete_id',)),
 spec('garmin_connect','Start a local private key-entry page for the official Garmin Personal API. The athlete creates their own key and accepts Garmin terms directly, then enters the key outside chat. Verifies account before saving.',{'athlete_id':S},('athlete_id',),False),
 spec('garmin_sync','Sync read-only official Garmin activity summaries for the requested recent days, renewing bearer tokens from the stored key. No background polling or Garmin writes.',{'athlete_id':S,'days':I},('athlete_id',),False),
 spec('garmin_sync_wellness','Import optional Garmin sleep and overnight HRV (1–90 days, default 28). Separate from workouts. Use only when the athlete requests recovery data.',{'athlete_id':S,'days':I},('athlete_id',),False),
 spec('garmin_disconnect','Remove the local Garmin key/token after an explicit disconnect request. Does not revoke the key at Garmin; the athlete deletes it in Garmin Connect if desired. Retains local history.',{'athlete_id':S},('athlete_id',),False),
 spec('strava_status','Read configured/connected status and last successful sync, without secrets.',{'athlete_id':S},('athlete_id',)),
 spec('strava_connect','Start a local browser setup page for app configuration and read-only Strava OAuth. User enters credentials directly in that page. Does not log in or authorize on behalf of the user.',{'athlete_id':S},('athlete_id',),False),
 spec('strava_sync','Fetch read-only Strava activity summaries into this athlete history; refreshes stored tokens when needed. Bounded, complete-window sync; no posts to Strava.',{'athlete_id':S,'days':I},('athlete_id',),False),
 spec('strava_disconnect','Revoke Strava authorization after an explicit user disconnect request. Previously imported local history is retained.',{'athlete_id':S},('athlete_id',),False),
]
def validate_args(args,schema):
 if not isinstance(args,dict):raise ValueError('Arguments must be an object')
 if set(args)-set(schema['properties']):raise ValueError('Unknown arguments')
 if any(k not in args for k in schema['required']):raise ValueError('Missing required arguments')
 for k,v in args.items():
  rule=schema['properties'][k];types=rule['type'] if isinstance(rule['type'],list) else [rule['type']]
  ok=any((t=='null' and v is None) or (t=='string' and isinstance(v,str)) or (t=='integer' and isinstance(v,int) and not isinstance(v,bool)) or (t=='object' and isinstance(v,dict)) or (t=='boolean' and isinstance(v,bool)) for t in types)
  if not ok or ('enum' in rule and v not in rule['enum']):raise ValueError('Invalid argument '+k)
class App:
 def __init__(self,root=None,http=None,garmin_http=None):
  self.store=Store(root);self.strava=Strava(self.store,**({'http':http} if http else {}));self.garmin=Garmin(self.store,**({'http':garmin_http} if garmin_http else {}))
 def versions(self,aid):
  self.store.athlete(aid)
  with self.store.db() as db:return [dict(r) for r in db.execute('SELECT version,parent,created FROM plans WHERE athlete=? ORDER BY version DESC',(aid,))]
 def source_context(self,aid):
  return {'preferences':self.store.source_preferences(aid),'native':{'strava':self.strava.status(aid),'garmin':self.garmin.status(aid)},'uploads':'Garmin dedicated import plus mapped CSV/JSON/ZIP for other providers','external':'Use a verified connector available in the host. This registry does not install or validate external connections.','manual':'No data connection or upload is required for coaching.'}
 def enabled_records(self,aid,kind='workout'):
  prefs=self.store.source_preferences(aid);disabled={p['provider'] for p in prefs if not p['enabled'] or p['mode']=='requested'}
  manual=any(p['provider']=='manual' and p['enabled'] for p in prefs)
  allowed={p['provider'] for p in prefs if p['enabled'] and p['mode'] not in ('manual','requested')}
  rows=self.store.activities(aid) if kind=='workout' else self.store.wellness(aid)
  return [r for r in rows if r['source'] not in disabled and (not manual or r['source'] in allowed)]
 def analysis_coverage(self,aid,profile,enabled):
  # A prior all-training assertion is no longer usable when evidence is hidden.
  return profile.get('evidenceCoverage') if len(enabled)==len(self.store.activities(aid)) else None
 def require_source(self,aid,provider):
  prefs=self.store.source_preferences(aid)
  if any(p['provider']==provider and (not p['enabled'] or p['mode']=='requested') for p in prefs) or (any(p['provider']=='manual' and p['enabled'] for p in prefs) and not any(p['provider']==provider and p['enabled'] for p in prefs)):
   raise ValueError('This source is not enabled for coaching. Enable it explicitly or keep manual-only mode.')
 def call(self,name,args):
  tool=next((x for x in TOOLS if x['name']==name),None)
  if not tool:raise ValueError('Unknown tool')
  validate_args(args,tool['inputSchema']);a=args;aid=a.get('athlete_id');n=name.removeprefix('forge226_')
  if aid:self.store.athlete(aid)
  if n=='status':return {'version':'0.9.1','storage':str(self.store.root),'athletes':len(self.store.athletes()),'garmin':'Official Personal API plus ZIP/JSON/CSV uploads','strava':'Local read-only OAuth; configuration and user consent required','genericImport':'Explicitly mapped CSV/JSON/ZIP workouts or wellness from any source; no universal live API','optionalData':True,'fitTcx':'Not yet supported','persistence':'Local SQLite plus separate restricted credentials; no cloud sync','garminLimits':{'activityDays':730,'activityRecordLimit':2000,'wellnessDays':90,'wellnessFields':['sleepHours','hrvMs']},'calendarViews':['month','week','day']}
  if n=='history_summary':
   athlete=self.store.athlete(aid);end=a.get('to_date') or datetime.now(ZoneInfo(athlete['timezone'])).date().isoformat()
   return history_summary(self.enabled_records(aid),a.get('from_date'),end)
  if n=='garmin_sync_all':
   self.require_source(aid,'garmin')
   activity_days=a.get('activity_days',730);wellness_days=a.get('wellness_days',90)
   if isinstance(activity_days,bool) or not 1<=activity_days<=730 or isinstance(wellness_days,bool) or not 1<=wellness_days<=90:raise ValueError('Use activity_days 1–730 and wellness_days 1–90')
   results={}
   for key,operation,days in [('activities',self.garmin.sync,activity_days),('wellness',self.garmin.sync_wellness,wellness_days)]:
    try:results[key]={'status':'succeeded','receipt':operation(aid,days)}
    except ApiError as exc:results[key]={'status':'failed','error':str(exc)}
   return {'datasets':results,'complete':all(x['status']=='succeeded' for x in results.values()),'scope':'Workout summaries, sleep duration and overnight average HRV only; no streams, sleep stages, Body Battery, stress or Training Readiness.'}
  if n=='sources':return self.source_context(aid)
  if n=='configure_source':return self.store.configure_source(aid,a['provider'],a['mode'],a['enabled'])
  if n=='source_inspect':return inspect_file(a['path'])
  if n in ('source_preview','source_import'):
   provider_id(a['provider'])
   rows,receipt,digest=mapped_export(a['path'],a['provider'],a['kind'],a['mapping'],self.store.athlete(aid)['timezone'])
   if n=='source_preview':return {'sha256':digest,'receipt':receipt,'sample':rows[:5],'ready':bool(rows) and receipt['rejected']==0}
   self.require_source(aid,a['provider'])
   if not secrets.compare_digest(digest,a['expected_sha256']):raise ValueError('File changed after preview')
   if receipt['rejected'] and not a.get('allow_partial'):raise ValueError('Rejected records; resolve mapping or explicitly allow partial import')
   result=self.store.ingest(aid,a['provider'],rows,receipt,digest,a['kind'])
   if not any(p['provider']==a['provider'] for p in self.store.source_preferences(aid)):self.store.configure_source(aid,a['provider'],'upload',True)
   return result
  if n=='list_wellness':
   rows=sorted(self.enabled_records(aid,'wellness'),key=lambda x:x['date'],reverse=True);offset=a.get('offset',0);limit=a.get('limit',50)
   if offset<0 or not 1<=limit<=200:raise ValueError('Use offset >=0 and limit 1–200')
   return {'records':rows[offset:offset+limit],'total':len(rows),'nextOffset':offset+limit if len(rows)>offset+limit else None}
  if n=='list_athletes':return {'athletes':self.store.athletes()}
  if n=='create_athlete':return self.store.create(a['name'],a['timezone'])
  if n=='get_profile':return {**self.store.athlete(aid),'activeVersion':self.store.active_version(aid)}
  if n=='save_profile':return self.store.save_profile(aid,a['profile'],a['expected_revision'])
  if n in ('garmin_preview','garmin_import'):
   rows,receipt,digest=read_export(a['path'],self.store.athlete(aid)['timezone'],a.get('units','auto'),a.get('distance_unit'))
   if n=='garmin_preview':return {'sha256':digest,'receipt':receipt,'sample':rows[:5],'ready':bool(rows) and receipt['rejected']==0}
   if not secrets.compare_digest(digest,a['expected_sha256']):raise ValueError('File changed after preview; preview again.')
   if receipt['rejected'] and not a.get('allow_partial'):raise ValueError('Import has rejected rows; inspect preview, correct units, or explicitly allow a partial import.')
   self.require_source(aid,'garmin')
   result=self.store.ingest(aid,'garmin',rows,receipt,digest)
   if not any(p['provider']=='garmin' for p in self.store.source_preferences(aid)):self.store.configure_source(aid,'garmin','upload',True)
   return result
  if n=='list_activities':
   rows=sorted(self.enabled_records(aid),key=lambda x:x['startTime'],reverse=True)
   for key in ('from_date','to_date'):
    if a.get(key):date.fromisoformat(a[key])
   rows=[x for x in rows if (not a.get('from_date') or x['date']>=a['from_date']) and (not a.get('to_date') or x['date']<=a['to_date'])]
   offset=a.get('offset',0);limit=a.get('limit',50)
   if offset<0 or not 1<=limit<=200:raise ValueError('Use offset >= 0 and limit 1–200')
   return {'total':len(rows),'activities':rows[offset:offset+limit],'nextOffset':offset+limit if len(rows)>offset+limit else None}
  if n in ('analyze','review_summary'):
   athlete=self.store.athlete(aid);profile=athlete['profile'];as_of=a.get('as_of') or datetime.now(ZoneInfo(athlete['timezone'])).date().isoformat()
   rows=self.enabled_records(aid)
   calculated=summarize(rows,as_of,self.analysis_coverage(aid,profile,rows))
   calculated['benchmarkHistory']=benchmark_history(profile,as_of)
   if n=='analyze':return calculated
   plan=self.store.plan(aid,a.get('version'));state=plan['state'] if plan else {}
   return {'asOf':as_of,'planVersion':state.get('version'),'planStatus':state.get('status'),'calculated':calculated,
           'adherence':adherence(state.get('sessions',[]),rows,state.get('sessionOutcomes',[]),as_of,a.get('from_date')),
           'checkins':[x for x in self.store.checkins(aid) if x['date']<=as_of][:14],
           'assessment':state.get('assessment'),'trainingBlocks':state.get('trainingBlocks',[]),'reviewDecisions':state.get('reviewDecisions',[]),
           'nextStep':'Interpret actual execution and recovery; resolve material unknowns, then save a reasoned decision in a new draft if a change is requested.'}
  if n=='analyze_session':
   activity=next((x for x in self.enabled_records(aid) if x['id']==a['activity_id']),None)
   if activity is None:raise ValueError('Activity is unavailable for this athlete or its source is disabled')
   return analyze_laps(a['path'],activity,a.get('comparison'))
  if n=='save_checkin':return self.store.checkin(aid,a['checkin'])
  if n=='get_context':return {'athlete':self.store.athlete(aid),'activeVersion':self.store.active_version(aid),'versions':self.versions(aid),'checkins':self.store.checkins(aid),'imports':self.store.receipts(aid),'strava':self.strava.status(aid),'sources':self.source_context(aid)}
  if n=='get_plan':return self.store.plan(aid,a.get('version')) or {'plan':None}
  if n=='save_plan_draft':return self.store.draft(aid,a['state'],a['parent_version'])
  if n=='activate_plan':return self.store.activate(aid,a['version'],a['expected_active'])
  if n=='export_dashboard':
   plan=self.store.plan(aid,a.get('version'))
   if not plan:raise ValueError('No saved plan; finish intake and create a draft first.')
   state=plan['state'];state['activities']=self.enabled_records(aid);state['wellness']=self.enabled_records(aid,'wellness');state['dataSources']=self.source_context(aid);state['checkins']=self.store.checkins(aid);state['evidence']=self.store.receipts(aid)
   as_of=datetime.now(ZoneInfo(state['timezone'])).date().isoformat();profile=self.store.athlete(aid)['profile']
   state['calculatedAnalysis']=summarize(state['activities'],as_of,self.analysis_coverage(aid,profile,state['activities']))
   state['benchmarkHistory']=benchmark_history(profile,as_of)
   state['adherence']=adherence(state.get('sessions',[]),state['activities'],state.get('sessionOutcomes',[]),as_of)
   state['exportedAt']=now()
   output=self.store.root/'exports'/aid/(str(state['version'])+'-'+secrets.token_hex(4));output.mkdir(parents=True,mode=0o700)
   page=render(state);(output/'training-dashboard.html').write_text(page);(output/'athlete-state.json').write_text(json.dumps(state,indent=2,allow_nan=False))
   return {'version':state['version'],'status':state['status'],'html':str(output/'training-dashboard.html'),'state':str(output/'athlete-state.json'),'note':'Snapshot generated from stored plan and latest imported evidence. No automatic publishing or cross-file sync.'}
  if n=='garmin_status':return self.garmin.status(aid)
  if n=='garmin_connect':
   self.require_source(aid,'garmin');return self.garmin.begin(aid)
  if n=='garmin_sync':
   self.require_source(aid,'garmin');return self.garmin.sync(aid,a.get('days',183))
  if n=='garmin_sync_wellness':
   self.require_source(aid,'garmin');return self.garmin.sync_wellness(aid,a.get('days',28))
  if n=='garmin_disconnect':return self.garmin.disconnect(aid)
  if n=='strava_status':return self.strava.status(aid)
  if n=='strava_connect':
   self.require_source(aid,'strava');self.store.configure_source(aid,'strava','native',True);return self.strava.begin(aid)
  if n=='strava_sync':
   self.require_source(aid,'strava');return self.strava.sync(aid,a.get('days',183))
  if n=='strava_disconnect':return self.strava.disconnect(aid)
  raise ValueError('Tool not implemented')

def main():
 os.umask(0o077)
 app=App()
 # One credential-writing process per data store prevents refresh token races.
 import fcntl
 lock=open(app.store.root/'server.lock','a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  lock.seek(0)
  try:owner=json.loads(lock.read() or '{}');pid=owner.get('pid')
  except (ValueError,TypeError):pid=None
  print('Forge226 is already running for this data store'+(' (background process '+str(pid)+')' if isinstance(pid,int) else '')+'. This may be a host-started background connector, not an open window. Use the existing tools. If unavailable, identify the owner before offering an authorized restart; do not delete the lock or create a second store.',file=sys.stderr);return 1
 lock.seek(0);lock.truncate();lock.write(json.dumps({'pid':os.getpid(),'startedAt':now()}));lock.flush()
 try:
  for line in sys.stdin:
   ident=None
   try:
    if len(line)>8*1024*1024:raise ValueError('Request exceeds 8 MB')
    req=json.loads(line);ident=req.get('id');method=req.get('method');params=req.get('params') or {}
    if ident is None:continue
    if method=='initialize':
     requested=params.get('protocolVersion');version=requested if requested in ('2024-11-05','2025-03-26','2025-06-18','2025-11-25') else '2025-06-18'
     result={'protocolVersion':version,'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'forge226','version':'0.9.1'},'instructions':'Start with forge226_status and list_athletes. Keep credentials outside conversation. Never activate a plan without athlete authorization.'}
    elif method=='ping':result={}
    elif method=='tools/list':result={'tools':TOOLS}
    elif method=='tools/call':
     try:
      value=app.call(params['name'],params.get('arguments',{}));result={'content':[{'type':'text','text':json.dumps(value,allow_nan=False)}],'structuredContent':value if isinstance(value,dict) else {'result':value},'isError':False}
     except (ValueError,KeyError,TypeError,ApiError,OSError) as e:result={'content':[{'type':'text','text':str(e)}],'isError':True}
     except Exception:
      print('Forge226 internal operation failed; no credential details logged.',file=sys.stderr);result={'content':[{'type':'text','text':'Internal operation failed. Existing active plan retained. Check input or restart the plugin.'}],'isError':True}
    else:
     print(json.dumps({'jsonrpc':'2.0','id':ident,'error':{'code':-32601,'message':'Method not found'}}),flush=True);continue
    print(json.dumps({'jsonrpc':'2.0','id':ident,'result':result},allow_nan=False),flush=True)
   except (ValueError,TypeError,AttributeError):print(json.dumps({'jsonrpc':'2.0','id':ident,'error':{'code':-32700,'message':'Invalid JSON-RPC request'}}),flush=True)
 finally:app.strava.close();app.garmin.close();lock.close()
 return 0
if __name__=='__main__':sys.exit(main())
