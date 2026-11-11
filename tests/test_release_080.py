"""Regression tests for observed setup, history and calendar failures; synthetic data only."""
import base64,json,os,pty,re,select,ssl,subprocess,sys,tempfile,time,unittest,urllib.request,urllib.error,urllib.parse
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'));sys.path.insert(0,str(ROOT/'skills/forge226-coach/scripts'))
from server import App
from analysis import history_summary
from tls import verified_context,network_error
from garmin import GarminError
from calendar_view import calendar_html
from render_dashboard import render
from test_garmin import FakeGarmin
from test_integration import fixture

class ReleaseTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.api=FakeGarmin();self.app=App(self.tmp.name,garmin_http=self.api);self.a=self.app.store.create('Synthetic athlete','UTC')['id']
 def tearDown(self):self.app.garmin.close();self.app.strava.close();self.tmp.cleanup()
 def test_all_supported_import_keeps_datasets_separate(self):
  self.app.garmin.connect_key(self.a,'synthetic-key')
  r=self.app.call('forge226_garmin_sync_all',{'athlete_id':self.a,'activity_days':30,'wellness_days':28})
  self.assertTrue(r['complete']);self.assertEqual(len(self.app.store.activities(self.a)),1);self.assertEqual(len(self.app.store.wellness(self.a)),2)
  self.assertEqual(set(r['datasets']),{'activities','wellness'})
 def test_all_import_reports_partial_failure_without_rollback(self):
  self.app.garmin.connect_key(self.a,'synthetic-key');self.api.sleepfail=True
  r=self.app.call('forge226_garmin_sync_all',{'athlete_id':self.a,'activity_days':30,'wellness_days':28})
  self.assertFalse(r['complete']);self.assertEqual(r['datasets']['activities']['status'],'succeeded');self.assertEqual(r['datasets']['wellness']['status'],'failed');self.assertEqual(len(self.app.store.activities(self.a)),1)
 def test_all_import_rejects_limits_before_side_effects(self):
  with self.assertRaises(ValueError):self.app.call('forge226_garmin_sync_all',{'athlete_id':self.a,'activity_days':731})
  self.assertEqual(self.api.calls,[])
 def test_expiry_error_is_specific_and_no_secret(self):
  for expiry in ['12/9','1900-01-01']:
   with self.assertRaises(GarminError) as e:self.app.garmin.connect_key(self.a,'never-print-this',key_expires_on=expiry)
   self.assertNotIn('never-print-this',str(e.exception));self.assertTrue('expiry' in str(e.exception).lower());self.assertEqual(self.api.calls,[])
 def test_setup_policy_and_origin_protection(self):
  link=self.app.garmin.begin(self.a)['setupUrl'];nonce=link.rsplit('/',1)[1]
  with urllib.request.urlopen(link) as r:self.assertEqual(r.headers['Referrer-Policy'],'same-origin')
  data=urllib.parse.urlencode({'csrf':self.app.garmin.sessions[nonce]['csrf'],'api_key':'synthetic-key'}).encode()
  for origin in ['null','http://evil.example']:
   with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(urllib.request.Request(link,data=data,headers={'Origin':origin}))
   self.assertEqual(e.exception.code,403)
  self.assertFalse(self.app.garmin.status(self.a)['connected']);self.assertEqual(self.api.calls,[])
 def test_expired_form_is_identifiable(self):
  link=self.app.garmin.begin(self.a)['setupUrl'];self.app.garmin.sessions[link.rsplit('/',1)[1]]['expires']=0
  with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(urllib.request.Request(link,data=b'csrf=old',headers={'Origin':self.app.garmin.origin}))
  self.assertIn('expired',e.exception.read().decode())
 def test_strava_policy_preserves_same_origin(self):
  link=self.app.strava.begin(self.a)['setupUrl']
  with urllib.request.urlopen(link) as r:self.assertEqual(r.headers['Referrer-Policy'],'same-origin')
 def test_mac_cert_fallback_keeps_verification(self):
  paths=ssl.DefaultVerifyPaths(None,None,'SSL_CERT_FILE','missing','SSL_CERT_DIR','missing')
  with patch.dict(os.environ,{},clear=True),patch('tls.sys.platform','darwin'),patch('tls.ssl.get_default_verify_paths',return_value=paths),patch('tls.Path.is_file',return_value=True),patch('tls.ssl.create_default_context') as create:
   verified_context();create.assert_called_once_with(cafile='/etc/ssl/cert.pem')
 def test_explicit_ca_configuration_not_overridden(self):
  with patch.dict(os.environ,{'SSL_CERT_FILE':'custom-ca.pem'},clear=True),patch('tls.ssl.create_default_context') as create:
   verified_context();create.assert_called_once_with()
 def test_tls_error_does_not_misdiagnose_bad_key(self):
  error=urllib.error.URLError(ssl.SSLCertVerificationError('sensitive diagnostic'))
  message=network_error('Garmin',error);self.assertIn('certificate',message);self.assertNotIn('sensitive diagnostic',message);self.assertNotIn('key rejected',message)
 def test_history_separates_days_from_files_and_flags_races(self):
  rows=[]
  for i,(day,name,hours) in enumerate([('2026-08-03','warm up',1),('2026-08-03','intervals',2),('2026-08-03','cool down',1),('2026-08-04','Ride',12),('2026-08-10','IRONMAN race',10),('2026-11-02','Return run',1)]):
   rows.append(dict(id=str(i),sourceId=str(i),source='garmin',date=day,startTime=day+f'T{8+i:02}:00:00+00:00',sport='Run' if i<3 else 'Bike',durationSeconds=hours*3600,name=name))
  r=history_summary(rows,'2026-08-03','2026-11-09');w=r['highestObservedWeeks'][0]
  self.assertEqual(w['observedHours'],16);self.assertEqual(w['trainingDays'],2);self.assertEqual(w['recordCount'],4);self.assertEqual(w['trainingDaysBySport']['Run'],1)
  self.assertTrue(r['observedWeeks'][1]['possibleRaceActivityIds']);self.assertTrue(all(x['coverage'].startswith('observed') for x in r['observedWeeks']))
 def test_calendar_is_generic_and_escapes_untrusted_text(self):
  s=fixture(self.a);s['goal']['name']='A different event';s['sessions'][0]['title']='</script><script>bad()</script>'
  html=render(s)
  self.assertIn('data-view="month"',html);self.assertIn('data-view="week"',html);self.assertIn('data-view="day"',html)
  self.assertNotIn('</script><script>bad()',html);self.assertNotIn('Northern California',html);self.assertNotIn('16 h 10',html)
  data=re.search(r'id="fc-data">(.*?)</script>',html,re.S).group(1);loaded=json.loads(data)
  self.assertEqual(loaded['sessions'],s['sessions']);self.assertNotIn('activities',loaded)
 def test_calendar_accepts_legacy_state_without_blocks(self):
  s=fixture(self.a);s.pop('trainingBlocks',None);html=calendar_html(s);self.assertIn('"trainingBlocks": []',html)
 def test_daily_cap_combines_both_slots(self):
  from check_state import validate
  s=fixture(self.a);x=next(x for x in s['sessions'] if x['sport'] not in ('Rest','Race'));x['minutes']=35;x['slot']='AM'
  second=dict(x,id=x['id']+'-second',slot='PM');s['sessions'].append(second)
  s['exceptions']=[{'startDate':x['date'],'endDate':x['date'],'slots':{'AM':{'enabled':True,'minutes':60},'PM':{'enabled':True,'minutes':60}},'maxMinutesPerDay':60}]
  r=validate(s);self.assertFalse(r['passed']);self.assertTrue(any('daily cap' in e for e in r['errors']))
 def test_travel_sport_restriction_is_checked(self):
  from check_state import validate
  s=fixture(self.a);x=next(x for x in s['sessions'] if x['sport'] not in ('Rest','Race'));x['sport']='Bike'
  s['exceptions']=[{'startDate':x['date'],'endDate':x['date'],'slots':{},'allowedSports':['Run','Other']}]
  r=validate(s);self.assertFalse(r['passed']);self.assertTrue(any('Sport unavailable' in e for e in r['errors']))
 def test_large_profile_through_real_pty(self):
  master,slave=pty.openpty()
  process=subprocess.Popen([sys.executable,str(ROOT/'bin/chat-session.py')],stdin=slave,stdout=slave,stderr=slave,env={**os.environ,'FORGE226_DATA_DIR':self.tmp.name})
  os.close(slave)
  try:
   # Wait for initialization reply before sending the long request.
   def exchange(req):
    payload=(json.dumps(req)+'\n').encode();offset=0
    while offset<len(payload):offset+=os.write(master,payload[offset:offset+1024])
    output=b'';deadline=time.monotonic()+10
    while time.monotonic()<deadline:
     ready,_,_=select.select([master],[],[],.2)
     if ready:
      output+=os.read(master,65536)
      for line in output.splitlines():
       try:r=json.loads(line)
       except (ValueError,UnicodeError):continue
       if r.get('id')==req['id'] and 'result' in r:return r['result']
    self.fail('No complete JSON-RPC response')
   exchange({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})
   long_text='training context '*1200
   r=exchange({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'forge226_save_profile','arguments':{'athlete_id':self.a,'expected_revision':1,'profile':{'notes':long_text}}}})
   self.assertFalse(r['isError']);self.assertEqual(r['structuredContent']['profile']['notes'],long_text)
  finally:
   process.terminate();process.wait(timeout=5);os.close(master)

if __name__=='__main__':unittest.main()
