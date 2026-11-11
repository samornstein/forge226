import unittest,tempfile,sys,time,json,base64,urllib.request,urllib.parse,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'server'))
from server import App
from garmin import GarminError,expiration,request
class FakeGarmin:
 def __init__(self):self.calls=[];self.uid=123;self.fail=None;self.full=False;self.badkey=False;self.sleepfail=False;self.unauthorized=False
 def __call__(self,method,url,authorization,text=False):
  self.calls.append((method,url,authorization,text))
  if method=='POST':
   if self.badkey:raise GarminError('Key rejected',401)
   payload=base64.urlsafe_b64encode(json.dumps({'exp':int(time.time())+86400}).encode()).decode().rstrip('=')
   return 'head.'+payload+'.signature'
  if self.unauthorized:self.unauthorized=False;raise GarminError('Unauthorized',401)
  if self.fail:raise GarminError('Service unavailable',self.fail)
  if 'usersummary/daily' in url:return {'userProfileId':self.uid}
  if 'activities/search' in url:
   row={'activityId':1,'ownerId':self.uid,'activityName':'Ride','activityType':{'typeKey':'cycling'},'startTimeGMT':'2026-11-01 16:00:00','startTimeLocal':'2026-11-01 08:00:00','duration':3600,'distance':20000,'averageHR':120}
   return [dict(row,activityId=i) for i in range(100)] if self.full else [row]
  if 'dailySleepSummaries' in url:
   if self.sleepfail:raise GarminError('Not permitted',403)
   day=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['startDate'][0]
   return [{'calendarDate':day,'userProfilePK':self.uid,'sleepTimeSeconds':25200}]
  if '/hrv/daily/' in url:return {'userProfilePk':self.uid,'hrvSummaries':[{'calendarDate':url.rsplit('/',2)[1],'lastNightAvg':55}]}
  raise AssertionError('Unknown path '+url)
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.http=FakeGarmin();self.app=App(self.tmp.name,garmin_http=self.http);self.g=self.app.garmin;self.a=self.app.store.create('Test','America/Los_Angeles')['id'];self.b=self.app.store.create('Other','UTC')['id']
 def tearDown(self):self.g.close();self.app.strava.close();self.tmp.cleanup()
 def connect(self):return self.g.connect_key(self.a,'fake-private-key')
 def test_connect_and_secret_redaction(self):
  status=self.connect();self.assertTrue(status['connected']);self.assertNotIn('fake-private-key',json.dumps(status));self.assertEqual(self.g.vault._file('garmin-'+self.a).stat().st_mode&0o777,0o600)
  self.assertEqual(self.http.calls[0][2],'ApiKey fake-private-key');self.assertTrue(any(c[2].startswith('Bearer ') for c in self.http.calls[1:]))
 def test_rotation_keeps_identity(self):
  self.connect();self.http.uid=999
  with self.assertRaises(GarminError):self.g.connect_key(self.a,'other-key')
  self.assertEqual(self.g.status(self.a)['userId'],123)
 def test_cross_athlete_binding(self):
  self.connect()
  with self.assertRaises(GarminError):self.g.connect_key(self.b,'another-key')
 def test_key_failure_not_saved(self):
  self.http.badkey=True
  with self.assertRaises(GarminError):self.connect()
  self.assertFalse(self.g.status(self.a)['connected'])
 def test_refresh_from_key_no_refresh_token(self):
  self.connect();c=self.g.vault.get('garmin-'+self.a);c['expires_at']=0;self.g.vault.put('garmin-'+self.a,c);self.g.token(self.a)
  self.assertEqual(len([x for x in self.http.calls if x[0]=='POST']),2);self.assertNotIn('refresh_token',json.dumps(self.g.vault.get('garmin-'+self.a)))
 def test_sync_and_renew_once_on_401(self):
  self.connect();self.http.unauthorized=True;self.g.sync(self.a);rows=self.app.store.activities(self.a)
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['durationSeconds'],3600);self.assertEqual(rows[0]['sport'],'Bike')
  self.assertEqual(len([x for x in self.http.calls if x[0]=='POST']),2)
 def test_sync_failure_preserves_receipt(self):
  self.connect();self.g.sync(self.a);before=self.g.status(self.a)['lastSync'];self.http.fail=429
  with self.assertRaises(GarminError):self.g.sync(self.a)
  self.assertEqual(self.g.status(self.a)['lastSync'],before);self.assertEqual(len(self.app.store.activities(self.a)),1)
 def test_pagination_repetition_rejected(self):
  self.connect();self.http.full=True
  with self.assertRaises(GarminError):self.g.sync(self.a)
  self.assertEqual(self.app.store.activities(self.a),[])
 def test_sleep_hrv_separate_and_chunked(self):
  self.connect();self.g.sync_wellness(self.a,days=32);rows=self.app.store.wellness(self.a)
  self.assertEqual(len(rows),4);self.assertEqual(self.app.store.activities(self.a),[])
  self.assertEqual([r['sleepHours'] for r in rows if 'sleepHours' in r],[7,7]);self.assertEqual(self.app.store.activities(self.b),[])
 def test_wellness_failure_keeps_history(self):
  self.connect();self.http.sleepfail=True
  with self.assertRaises(GarminError):self.g.sync_wellness(self.a)
  self.assertEqual(self.app.store.wellness(self.a),[])
 def test_disconnect_local_only(self):
  self.connect();self.g.sync(self.a);self.g.disconnect(self.a)
  self.assertFalse(self.g.status(self.a)['connected']);self.assertEqual(len(self.app.store.activities(self.a)),1)
 def test_untrusted_token_not_accepted_for_identity(self):
  with self.assertRaises(GarminError):expiration('garbage')
  self.connect();self.http.uid=None
  with self.assertRaises(GarminError):self.g.connect_key(self.b,'no-identity-key')
 def test_api_destination_allowlist(self):
  for url in ['https://evil.example/path','http://personal.connectapi.garmin.com/','https://personal.connectapi.garmin.com.evil.test/']:
   with self.assertRaises(GarminError):request('GET',url,'secret')
 def test_local_setup_and_csrf(self):
  link=self.g.begin(self.a)['setupUrl'];nonce=link.rsplit('/',1)[1]
  with urllib.request.urlopen(link) as r:self.assertIn('Personal API key',r.read().decode())
  bad=urllib.request.Request(link,data=b'csrf=wrong&api_key=secret',headers={'Origin':self.g.origin},method='POST')
  with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(bad)
  self.assertFalse(self.g.status(self.a)['connected'])
  payload=urllib.parse.urlencode({'csrf':self.g.sessions[nonce]['csrf'],'api_key':'fake-private-key','region':'global'}).encode()
  good=urllib.request.Request(link,data=payload,headers={'Origin':self.g.origin},method='POST')
  with urllib.request.urlopen(good) as r:self.assertEqual(r.status,200)
  self.assertTrue(self.g.status(self.a)['connected']);self.assertEqual(self.app.store.source_preferences(self.a)[0]['mode'],'native')
if __name__=='__main__':unittest.main()
