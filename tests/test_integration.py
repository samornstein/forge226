import unittest,tempfile,json,sys,copy,time,zipfile,io,os,subprocess,urllib.request,urllib.parse,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'server'))
from server import App,TOOLS
from imports import read_export
from strava import ApiError
from check_state import DAYS

class FakeStrava:
 def __init__(self):self.calls=[];self.fail=False;self.pages=None;self.athlete=123
 def __call__(self,method,url,form=None,token=None):
  self.calls.append((method,url,form,token))
  if '/oauth/token' in url:return {'access_token':'secret-access','refresh_token':'rotated-refresh','expires_at':int(time.time())+3600,'athlete':{'id':self.athlete}}
  if '/oauth/deauthorize' in url:return {}
  if self.fail:raise ApiError('Strava rate limit reached')
  if self.pages:return self.pages(url)
  return [{'id':42,'name':'Test ride','sport_type':'Ride','start_date':'2026-11-01T16:00:00Z','moving_time':3600,'distance':25000}]

def fixture(aid):
 return {'schemaVersion':1,'athleteId':aid,'version':1,'status':'draft','timezone':'America/Los_Angeles','athlete':{'name':'Synthetic athlete'},'goal':{'name':'Synthetic week','startDate':'2026-11-09','endDate':'2026-11-15','raceDate':None},'availability':{d:{'AM':{'enabled':True,'minutes':60},'PM':{'enabled':False,'minutes':0}} for d in DAYS},'weeklyCapMinutes':180,'exceptions':[],'sessions':[{'id':f's{i}','date':f'2026-11-{9+i:02}','slot':'AM' if i in (0,2,4) else 'Rest','sport':'Bike' if i in (0,2,4) else 'Rest','title':'Test session','minutes':45 if i in (0,2,4) else 0,'intensity':'Easy','details':'Synthetic only','purpose':'Test'} for i in range(7)],'review':{'type':'self-review','decision':'pass','issues':[]}}
class Integration(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.fake=FakeStrava();self.app=App(self.tmp.name,self.fake);self.a=self.app.store.create('Test athlete','America/Los_Angeles')['id'];self.b=self.app.store.create('Other athlete','America/Los_Angeles')['id']
 def tearDown(self):self.app.strava.close();self.tmp.cleanup()
 def call(self,n,**args):return self.app.call('forge226_'+n,args)
 def export(self,rows,name='activities.json'):
  p=Path(self.tmp.name)/name;p.write_text(json.dumps(rows));return p
 def row(self):return {'activityId':1,'startTimeLocal':'2026-11-01T08:00:00','sportType':'cycling','durationSeconds':3600,'distanceMeters':20000}
 def connect(self):
  self.app.strava.vault.put('strava-app',{'client_id':'123','client_secret':'test-secret'});self.app.strava.exchange(self.a,'code','read,activity:read_all')
 def test_profile_persistence_and_isolation(self):
  self.call('save_profile',athlete_id=self.a,profile={'goal':'triathlon'},expected_revision=1)
  restarted=App(self.tmp.name,self.fake)
  self.assertEqual(restarted.store.athlete(self.a)['profile']['goal'],'triathlon');self.assertEqual(restarted.store.athlete(self.b)['profile'],{})
  with self.assertRaises(ValueError):self.call('save_profile',athlete_id=self.a,profile={},expected_revision=1)
 def test_import_digest_upsert_and_other_athlete(self):
  p=self.export([self.row()]);preview=self.call('garmin_preview',athlete_id=self.a,path=str(p));self.assertTrue(preview['ready'])
  for _ in range(2):self.call('garmin_import',athlete_id=self.a,path=str(p),expected_sha256=preview['sha256'])
  self.assertEqual(len(self.app.store.activities(self.a)),1);self.assertEqual(self.app.store.activities(self.b),[])
  p.write_text('[]')
  with self.assertRaises(ValueError):self.call('garmin_import',athlete_id=self.a,path=str(p),expected_sha256=preview['sha256'])
  self.assertEqual(len(self.app.store.activities(self.a)),1)
 def test_garmin_named_summary_units(self):
  p=self.export([{'activityId':9,'startTimeLocal':'2026-11-01T08:00:00','activityType':'running','duration':3600000,'distance':1000000}],'summarizedActivities.json')
  rows,receipt,_=read_export(p,'America/Los_Angeles');self.assertEqual(rows[0]['durationSeconds'],3600);self.assertEqual(rows[0]['distanceMeters'],10000)
 def test_unknown_units_rejected_not_guessed(self):
  row=self.row();row.pop('durationSeconds');row['duration']=3600;p=self.export([row]);rows,receipt,_=read_export(p,'UTC');self.assertFalse(rows);self.assertEqual(receipt['rejected'],1)
 def test_partial_import_requires_choice(self):
  bad=self.row();bad.pop('durationSeconds');p=self.export([self.row(),bad]);v=self.call('garmin_preview',athlete_id=self.a,path=str(p))
  with self.assertRaises(ValueError):self.call('garmin_import',athlete_id=self.a,path=str(p),expected_sha256=v['sha256'])
  self.assertEqual(self.app.store.activities(self.a),[])
 def test_nested_zip(self):
  inner=io.BytesIO()
  with zipfile.ZipFile(inner,'w') as z:z.writestr('activities.json',json.dumps([self.row()]))
  p=Path(self.tmp.name)/'export.zip'
  with zipfile.ZipFile(p,'w') as z:z.writestr('nested.zip',inner.getvalue())
  rows,_,_=read_export(p,'America/Los_Angeles');self.assertEqual(len(rows),1)
 def test_csv_units(self):
  p=Path(self.tmp.name)/'export.csv';p.write_text('Activity Type,Date,Title,Time,Distance\nRunning,2026-11-01 08:00:00,Run,00:30:00,5\n')
  rows,_,_=read_export(p,'UTC',distance_unit='km');self.assertEqual(rows[0]['distanceMeters'],5000)
  rows,receipt,_=read_export(p,'UTC');self.assertFalse(rows)
 def test_timezone_midnight(self):
  row=self.row();row.pop('startTimeLocal');row['startTimeGMT']='2026-11-01T02:00:00';p=self.export([row]);rows,_,_=read_export(p,'America/Los_Angeles');self.assertEqual(rows[0]['date'],'2026-10-31')
 def test_plan_activation_and_stale_draft(self):
  d=self.call('save_plan_draft',athlete_id=self.a,state=fixture(self.a),parent_version=None);self.assertTrue(d['validation']['passed']);self.assertIsNone(self.app.store.active_version(self.a))
  other=self.call('save_plan_draft',athlete_id=self.a,state=fixture(self.a),parent_version=None)
  self.call('activate_plan',athlete_id=self.a,version=d['version'],expected_active=None)
  with self.assertRaises(ValueError):self.call('activate_plan',athlete_id=self.a,version=other['version'],expected_active=d['version'])
  self.assertEqual(self.app.store.active_version(self.a),d['version'])
 def test_invalid_plan_cannot_activate(self):
  state=fixture(self.a);state['sessions'][0]['minutes']=80;d=self.call('save_plan_draft',athlete_id=self.a,state=state,parent_version=None)
  self.assertFalse(d['validation']['passed'])
  with self.assertRaises(ValueError):self.call('activate_plan',athlete_id=self.a,version=d['version'],expected_active=None)
 def test_review_required(self):
  state=fixture(self.a);state['review']={};d=self.call('save_plan_draft',athlete_id=self.a,state=state,parent_version=None)
  with self.assertRaises(ValueError):self.call('activate_plan',athlete_id=self.a,version=d['version'],expected_active=None)
 def test_plan_identity(self):
  with self.assertRaises(ValueError):self.call('save_plan_draft',athlete_id=self.b,state=fixture(self.a),parent_version=None)
 def test_export_escaped_state_no_credentials(self):
  self.connect();s=fixture(self.a);s['athlete']['name']='</script><script>alert(1)</script>';d=self.call('save_plan_draft',athlete_id=self.a,state=s,parent_version=None)
  out=self.call('export_dashboard',athlete_id=self.a,version=d['version']);h=Path(out['html']).read_text()
  self.assertNotIn('</script><script>alert(1)',h);self.assertNotIn('test-secret',h);self.assertNotIn('secret-access',Path(out['state']).read_text())
 def test_checkin_resume(self):
  self.call('save_checkin',athlete_id=self.a,checkin={'date':'2026-11-08','fatigue':3})
  self.assertEqual(self.call('get_context',athlete_id=self.a)['checkins'][0]['fatigue'],3)
 def test_strava_scope_denied(self):
  self.app.strava.vault.put('strava-app',{'client_id':'123','client_secret':'test-secret'})
  with self.assertRaises(ApiError):self.app.strava.exchange(self.a,'code','read')
  self.assertFalse(self.app.strava.status(self.a)['connected'])
 def test_strava_token_refresh_and_permissions(self):
  self.connect();t=self.app.strava.vault.get('strava-'+self.a);t['expires_at']=0;self.app.strava.vault.put('strava-'+self.a,t)
  self.app.strava.token(self.a);self.assertEqual(self.fake.calls[-1][2]['grant_type'],'refresh_token')
  self.assertEqual(self.app.strava.vault._file('strava-'+self.a).stat().st_mode&0o777,0o600)
  self.assertNotIn('secret-access',json.dumps(self.app.strava.status(self.a)))
 def test_strava_identity_mismatch(self):
  self.connect();self.fake.athlete=999
  with self.assertRaises(ApiError):self.app.strava.exchange(self.a,'code','activity:read_all')
  self.assertEqual(self.app.strava.status(self.a)['stravaAthleteId'],123)
 def test_strava_account_cannot_cross_local_athletes(self):
  self.connect()
  with self.assertRaises(ApiError):self.app.strava.exchange(self.b,'code','activity:read_all')
 def test_strava_sync_failure_preserves_data_and_watermark(self):
  self.connect();self.app.strava.sync(self.a);before=self.app.store.sync(self.a);self.fake.fail=True
  with self.assertRaises(ApiError):self.app.strava.sync(self.a)
  self.assertEqual(self.app.store.sync(self.a),before);self.assertEqual(len(self.app.store.activities(self.a)),1)
 def test_strava_truncation_not_success(self):
  self.connect();self.fake.pages=lambda _: [{'id':42,'name':'Test','sport_type':'Ride','start_date':'2026-11-01T16:00:00Z','moving_time':3600,'distance':25000}]*200
  with self.assertRaises(ApiError):self.app.strava.sync(self.a)
  self.assertIsNone(self.app.store.sync(self.a));self.assertEqual(self.app.store.activities(self.a),[])
 def test_unknown_arguments_rejected(self):
  with self.assertRaises(ValueError):self.call('strava_status',athlete_id=self.a,secret='no')
 def test_local_setup_origin_and_state(self):
  link=self.app.strava.begin(self.a)['setupUrl'];owner=self.app.strava
  with urllib.request.urlopen(link) as r:body=r.read().decode();self.assertIn('Client secret',body)
  req=urllib.request.Request(link,data=b'csrf=wrong',headers={'Origin':owner.origin},method='POST')
  with self.assertRaises(urllib.error.HTTPError) as c:urllib.request.urlopen(req)
  self.assertEqual(c.exception.code,403)
  with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(owner.origin+'/callback?state=bad&code=bad')
  self.assertIsNone(owner.config())
 def test_oauth_full_local_roundtrip_with_mock_api(self):
  link=self.app.strava.begin(self.a)['setupUrl'];owner=self.app.strava;nonce=link.rsplit('/',1)[1]
  class NoFollow(urllib.request.HTTPRedirectHandler):
   def redirect_request(self,*args,**kwargs):return None
  data=urllib.parse.urlencode({'csrf':owner.sessions[nonce]['csrf'],'client_id':'123','client_secret':'entered-directly'}).encode()
  req=urllib.request.Request(link,data=data,headers={'Origin':owner.origin},method='POST')
  try:urllib.request.build_opener(NoFollow()).open(req)
  except urllib.error.HTTPError as e:
   self.assertEqual(e.code,303);target=e.headers['Location']
  params=urllib.parse.parse_qs(urllib.parse.urlsplit(target).query)
  with urllib.request.urlopen(owner.origin+'/callback?'+urllib.parse.urlencode({'state':params['state'][0],'code':'test-code','scope':'activity:read_all'})) as r:self.assertEqual(r.status,200)
  self.assertTrue(owner.status(self.a)['connected'])
  with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(owner.origin+'/callback?state='+params['state'][0]+'&code=test')
 def test_setup_can_correct_credentials(self):
  self.app.strava.vault.put('strava-app',{'client_id':'123','client_secret':'wrong'})
  link=self.app.strava.begin(self.a)['setupUrl'];owner=self.app.strava;nonce=link.rsplit('/',1)[1]
  with urllib.request.urlopen(link) as response:self.assertIn('name="client_secret"',response.read().decode())
  class NoFollow(urllib.request.HTTPRedirectHandler):
   def redirect_request(self,*args,**kwargs):return None
  data=urllib.parse.urlencode({'csrf':owner.sessions[nonce]['csrf'],'client_id':'123','client_secret':'corrected'}).encode()
  req=urllib.request.Request(link,data=data,headers={'Origin':owner.origin},method='POST')
  with self.assertRaises(urllib.error.HTTPError) as result:urllib.request.build_opener(NoFollow()).open(req)
  self.assertEqual(result.exception.code,303);self.assertEqual(owner.config()['client_secret'],'corrected')
 def test_manual_only_no_upload_required(self):
  self.call('configure_source',athlete_id=self.a,provider='manual',mode='manual',enabled=True)
  state=fixture(self.a);draft=self.call('save_plan_draft',athlete_id=self.a,state=state,parent_version=None)
  self.call('activate_plan',athlete_id=self.a,version=draft['version'],expected_active=None)
  self.assertEqual(self.call('list_activities',athlete_id=self.a)['total'],0)
  self.assertEqual(self.call('sources',athlete_id=self.a)['preferences'][0]['mode'],'manual')
 def test_generic_workout_mapping(self):
  p=Path(self.tmp.name)/'other.csv';p.write_text('identifier,start,minutes,km,type\nabc,2026-11-01T08:00:00,60,25,cycling\n')
  mapping={'fields':{'id':'identifier','startTime':'start','durationSeconds':'minutes','distanceMeters':'km','sport':'type'},'scales':{'durationSeconds':60,'distanceMeters':1000},'units':{'durationSeconds':'s','distanceMeters':'m'}}
  preview=self.call('source_preview',athlete_id=self.a,provider='wahoo',kind='workout',path=str(p),mapping=mapping)
  self.assertTrue(preview['ready']);self.assertEqual(preview['sample'][0]['durationSeconds'],3600)
  self.call('source_import',athlete_id=self.a,provider='wahoo',kind='workout',path=str(p),mapping=mapping,expected_sha256=preview['sha256'])
  self.assertEqual(self.call('list_activities',athlete_id=self.a)['total'],1)
  self.assertEqual(self.call('sources',athlete_id=self.a)['preferences'][0]['provider'],'wahoo')
  self.assertEqual(self.call('list_activities',athlete_id=self.b)['total'],0)
 def test_wellness_separate_from_workouts(self):
  p=Path(self.tmp.name)/'sleep.json';p.write_text(json.dumps([{'day':'2026-11-01','sleepMinutes':420,'hrv':65,'score':75}]))
  mapping={'fields':{'date':'day','sleepHours':'sleepMinutes','hrvMs':'hrv','recoveryScore':'score'},'scales':{'sleepHours':1/60},'units':{'sleepHours':'h','hrvMs':'ms','recoveryScore':'provider scale 0–100'}}
  v=self.call('source_preview',athlete_id=self.a,provider='whoop',kind='wellness',path=str(p),mapping=mapping)
  self.call('source_import',athlete_id=self.a,provider='whoop',kind='wellness',path=str(p),mapping=mapping,expected_sha256=v['sha256'])
  wellness=self.call('list_wellness',athlete_id=self.a);self.assertEqual(wellness['records'][0]['sleepHours'],7)
  self.assertEqual(self.call('list_activities',athlete_id=self.a)['total'],0)
  self.assertEqual(self.call('analyze',athlete_id=self.a,as_of='2026-11-08')['activityCount'],0)
 def test_source_choices_persist_and_do_not_fake_live_support(self):
  self.call('configure_source',athlete_id=self.a,provider='whoop',mode='external',enabled=True)
  restarted=App(self.tmp.name,self.fake)
  self.assertEqual(restarted.store.source_preferences(self.a)[0]['mode'],'external')
  with self.assertRaises(ValueError):self.call('configure_source',athlete_id=self.a,provider='whoop',mode='native',enabled=True)
  self.assertNotIn('whoop',self.call('sources',athlete_id=self.a)['native'])
 def test_source_disabled_preserves_history(self):
  p=self.export([self.row()]);v=self.call('garmin_preview',athlete_id=self.a,path=str(p))
  self.call('garmin_import',athlete_id=self.a,path=str(p),expected_sha256=v['sha256'])
  self.call('configure_source',athlete_id=self.a,provider='manual',mode='manual',enabled=True)
  self.assertEqual(self.call('list_activities',athlete_id=self.a)['total'],0)
  self.assertEqual(len(self.app.store.activities(self.a)),1)
  self.call('configure_source',athlete_id=self.a,provider='garmin',mode='upload',enabled=True)
  self.assertEqual(self.call('list_activities',athlete_id=self.a)['total'],1)
 def test_generic_units_and_hash_validation(self):
  p=Path(self.tmp.name)/'other.csv';p.write_text('start,time\n2026-11-01T08:00:00,30\n')
  mapping={'fields':{'startTime':'start','durationSeconds':'time'},'constants':{'sport':'run'}}
  with self.assertRaises(ValueError):self.call('source_preview',athlete_id=self.a,provider='custom',kind='workout',path=str(p),mapping=mapping)
  mapping['units']={'durationSeconds':'s'}
  v=self.call('source_preview',athlete_id=self.a,provider='custom',kind='workout',path=str(p),mapping=mapping)
  p.write_text('start,time\n2026-11-01T08:00:00,45\n')
  with self.assertRaises(ValueError):self.call('source_import',athlete_id=self.a,provider='custom',kind='workout',path=str(p),mapping=mapping,expected_sha256=v['sha256'])
  self.assertEqual(self.app.store.activities(self.a),[])
 def test_mcp_protocol(self):
  with tempfile.TemporaryDirectory() as tmp:
   requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'test','version':'1'}}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/list'},{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'forge226_status','arguments':{}}}]
   p=subprocess.run([sys.executable,str(ROOT/'server/server.py')],input='\n'.join(map(json.dumps,requests))+'\n',capture_output=True,text=True,env={**os.environ,'FORGE226_DATA_DIR':tmp},timeout=15)
   self.assertEqual(p.returncode,0,p.stderr);out=[json.loads(x) for x in p.stdout.splitlines()];self.assertEqual(len(out),3);self.assertEqual(len(out[1]['result']['tools']),len(TOOLS));self.assertFalse(out[2]['result']['isError'])
if __name__=='__main__':unittest.main()
