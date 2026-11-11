"""Official Garmin Personal API, local key entry and read-only on-request sync."""
import base64,json,math,time,threading,secrets,hashlib,html,urllib.request,urllib.parse,urllib.error
from datetime import datetime,date,timedelta
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from strava import Secrets,ApiError
from store import now
from tls import https_handler, network_error
from imports import normalize,num
HOSTS={'global':'https://personal.connectapi.garmin.com','china':'https://personal.connectapi.garmin.cn'}
TOKEN_PATH='/personalapitoken-service/personal-api/personal-api-key/token'
class GarminError(ApiError):
 def __init__(self,message,status=None):super().__init__(message);self.status=status
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise GarminError('Garmin redirect refused; no credentials forwarded.')
def request(method,url,authorization,text=False):
 parsed=urllib.parse.urlsplit(url)
 if parsed.scheme!='https' or parsed.netloc not in ('personal.connectapi.garmin.com','personal.connectapi.garmin.cn') or parsed.username or parsed.fragment:raise GarminError('Unsupported Garmin API destination')
 req=urllib.request.Request(url,method=method,headers={'Authorization':authorization,'Accept':'text/plain' if text else 'application/json','User-Agent':'Forge226Local/0.9.1'})
 try:
  with urllib.request.build_opener(NoRedirect(), https_handler()).open(req,timeout=25) as response:
   if response.status==204:return None
   raw=response.read(16*1024*1024+1)
   if len(raw)>16*1024*1024:raise GarminError('Garmin response exceeds size limit')
   return raw.decode().strip() if text else json.loads(raw)
 except urllib.error.HTTPError as e:
  message='Garmin key/token rejected; replace the key through local setup.' if e.code in (401,403,404) else 'Garmin rate limit reached; retry later.' if e.code==429 else 'Garmin request failed; retry later.'
  raise GarminError(message,e.code) from None
 except (urllib.error.URLError,TimeoutError) as exc:raise GarminError(network_error('Garmin',exc)) from None
 except (UnicodeError,ValueError):raise GarminError('Unexpected Garmin response format; no new data saved.') from None

def expiration(token):
 # Decode only for cache scheduling, never as proof of account identity.
 try:
  part=token.split('.')[1];value=json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))['exp'];exp=float(value)
  if isinstance(value,bool) or not math.isfinite(exp) or exp<=time.time():raise ValueError()
  return min(exp,time.time()+86400)
 except (ValueError,TypeError,KeyError,IndexError):raise GarminError('Garmin did not return a usable bearer token.') from None

class Garmin:
 def __init__(self,store,http=request):
  self.store=store;self.vault=Secrets(store.root);self.http=http;self.lock=threading.RLock();self.server=None;self.sessions={}
 def status(self,aid):
  self.store.athlete(aid);c=self.vault.get('garmin-'+aid)
  return {'connected':bool(c),'identityVerified':bool(c and c.get('user_id')),'region':c.get('region') if c else None,'userId':c.get('user_id') if c else None,'tokenExpiresAt':c.get('expires_at') if c else None,'keyExpiresOn':c.get('key_expires_on') if c else None,'lastSync':self.store.provider_sync(aid,'garmin'),'lastWellnessSync':self.store.provider_sync(aid,'garmin-wellness'),'note':'Local personal API key; access tokens renewed from key, no refresh token. Status is last verified, not a live key-validity test.'}
 def _new_token(self,key,region):
  token=self.http('POST',HOSTS[region]+TOKEN_PATH,'ApiKey '+key,text=True)
  if not isinstance(token,str) or not token:raise GarminError('Garmin returned an invalid bearer token.')
  return token,expiration(token)
 def _identity(self,token,region,tz):
  today=datetime.now(ZoneInfo(tz)).date().isoformat();base=HOSTS[region]
  daily=self.http('GET',base+'/usersummary-service/usersummary/daily?'+urllib.parse.urlencode({'calendarDate':today}),'Bearer '+token)
  uid=daily.get('userProfileId') if isinstance(daily,dict) else None
  if uid is None:
   batch=self.http('GET',base+'/activitylist-service/activities/search/activities?start=0&limit=1','Bearer '+token)
   uid=batch[0].get('ownerId') if isinstance(batch,list) and batch and isinstance(batch[0],dict) else None
  if not isinstance(uid,int) or isinstance(uid,bool) or uid<=0:raise GarminError('Could not verify Garmin account identity from supported data. No connection saved; uploads remain available.')
  return uid
 def connect_key(self,aid,key,region='global',key_expires_on=None):
  athlete=self.store.athlete(aid)
  if region not in HOSTS:raise GarminError('Choose Global or China for your Garmin account.')
  if not isinstance(key,str) or not key.strip() or len(key)>8192 or any(c.isspace() for c in key.strip()):raise GarminError('Enter only the Personal API key, without an ApiKey prefix, quotes or embedded whitespace.')
  key=key.strip()
  if key_expires_on:
   try:expiry=date.fromisoformat(key_expires_on)
   except (ValueError,TypeError):raise GarminError('Expiry must be YYYY-MM-DD, or leave the optional expiry field blank.') from None
   if expiry<datetime.now(ZoneInfo(athlete['timezone'])).date():raise GarminError('The optional expiry date is in the past. Check it or leave it blank; Garmin still enforces the real key expiry.')
  with self.lock:
   token,exp=self._new_token(key,region);uid=self._identity(token,region,athlete['timezone'])
   prior=self.vault.get('garmin-'+aid)
   if prior and (prior['user_id']!=uid or prior['region']!=region):raise GarminError('Different Garmin account. Use a separate athlete or explicitly disconnect before changing accounts.')
   for other in self.store.athletes():
    c=self.vault.get('garmin-'+other['id'])
    if other['id']!=aid and c and c['region']==region and c['user_id']==uid:raise GarminError('Garmin account is already assigned to another local athlete.')
   self.vault.put('garmin-'+aid,{'api_key':key,'access_token':token,'expires_at':exp,'user_id':uid,'region':region,'key_expires_on':key_expires_on,'connectedAt':now()})
  return self.status(aid)
 def token(self,aid,force=False):
  with self.lock:
   c=self.vault.get('garmin-'+aid)
   if not c:raise GarminError('Connect Garmin through local setup first.')
   if force or c['expires_at']<time.time()+3600:
    t,exp=self._new_token(c['api_key'],c['region']);c.update(access_token=t,expires_at=exp);self.vault.put('garmin-'+aid,c)
   return c['access_token']
 def get(self,aid,path,query=None):
  c=self.vault.get('garmin-'+aid)
  if not c:raise GarminError('Connect Garmin first.')
  url=HOSTS[c['region']]+path+('?' +urllib.parse.urlencode(query) if query else '')
  try:return self.http('GET',url,'Bearer '+self.token(aid))
  except GarminError as e:
   if e.status!=401:raise
   return self.http('GET',url,'Bearer '+self.token(aid,True))
 def check_owner(self,aid,uid):
  expected=self.vault.get('garmin-'+aid)['user_id']
  if uid is not None and uid!=expected:raise GarminError('Garmin account identity mismatch; no records committed.')
 def sync(self,aid,days=183):
  athlete=self.store.athlete(aid)
  if isinstance(days,bool) or not isinstance(days,int) or not 1<=days<=730:raise ValueError('days must be 1–730')
  end=datetime.now(ZoneInfo(athlete['timezone'])).date();start=end-timedelta(days=days-1)
  with self.lock:
   raw=[];pages=0;seen=set()
   for offset in range(0,2000,100):
    batch=self.get(aid,'/activitylist-service/activities/search/activities',{'start':offset,'limit':100,'startDate':start.isoformat(),'endDate':end.isoformat(),'sortOrder':'desc','excludeChildren':'false'})
    pages+=1
    if not isinstance(batch,list):raise GarminError('Unexpected Garmin activity list; no records saved.')
    if len(batch)>100:raise GarminError('Garmin pagination response exceeds requested limit')
    for row in batch:
     if not isinstance(row,dict) or row.get('activityId') in seen:raise GarminError('Invalid/repeated Garmin pagination; try a smaller window.')
     self.check_owner(aid,row.get('ownerId'));seen.add(row.get('activityId'));raw.append(row)
    if len(batch)<100:break
   else:raise GarminError('More than 2,000 activities; choose a smaller sync window. Existing history retained.')
   parent_ids={row.get('parentId') for row in raw if row.get('parentId')}
   rows=[normalize(r,athlete['timezone'],'seconds_meters','Garmin Personal API') for r in raw if r.get('activityId') not in parent_ids]
   receipt={'source':'garmin','method':'official Personal API','coverage':{'first':start.isoformat(),'last':end.isoformat()},'pages':pages,'complete':True,'multisportParentsExcluded':len(raw)-len(rows),'saved':len(rows),'syncedAt':now()}
   if rows:receipt=self.store.ingest(aid,'garmin',rows,receipt,hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest())
   self.store.set_provider_sync(aid,'garmin',receipt);return receipt
 def sync_wellness(self,aid,days=28):
  athlete=self.store.athlete(aid)
  if isinstance(days,bool) or not isinstance(days,int) or not 1<=days<=90:raise ValueError('wellness days must be 1–90')
  end=datetime.now(ZoneInfo(athlete['timezone'])).date();start=end-timedelta(days=days-1);cursor=start;rows=[]
  with self.lock:
   while cursor<=end:
    stop=min(cursor+timedelta(days=30),end)
    sleeps=self.get(aid,'/sleep-service/sleep/dailySleepSummariesByDate',{'startDate':cursor.isoformat(),'endDate':stop.isoformat()})
    hrvs=self.get(aid,'/hrv-service/hrv/daily/'+cursor.isoformat()+'/'+stop.isoformat())
    if sleeps is not None and not isinstance(sleeps,list):raise GarminError('Unexpected Garmin sleep response')
    if hrvs is not None and (not isinstance(hrvs,dict) or not isinstance(hrvs.get('hrvSummaries'),list)):raise GarminError('Unexpected Garmin HRV response')
    if hrvs:self.check_owner(aid,hrvs.get('userProfilePk'))
    for kind,records in [('sleep',sleeps or []),('hrv',(hrvs or {}).get('hrvSummaries',[]))]:
     for r in records:
      if not isinstance(r,dict):raise GarminError('Invalid Garmin wellness record')
      day=date.fromisoformat(r['calendarDate']).isoformat()
      if not cursor.isoformat()<=day<=stop.isoformat():raise GarminError('Garmin wellness record outside requested range')
      self.check_owner(aid,r.get('userProfilePK'))
      sid=kind+':'+day;out={'id':'garmin:'+sid,'sourceId':sid,'source':'garmin','recordKind':'wellness','date':day,'method':'official Personal API','units':{}}
      if kind=='sleep':
       n=num(r.get('sleepTimeSeconds'))
       if n is None:continue
       out['sleepHours']=n/3600;out['units']['sleepHours']='h'
      else:
       n=num(r.get('lastNightAvg'))
       if n is None:continue
       out['hrvMs']=n;out['units']['hrvMs']='ms'
      rows.append(out)
    cursor=stop+timedelta(days=1)
   rows=list({r['sourceId']:r for r in rows}.values());receipt={'source':'garmin','recordKind':'wellness','method':'official Personal API sleep and overnight HRV','coverage':{'first':start.isoformat(),'last':end.isoformat()},'saved':len(rows),'complete':True,'syncedAt':now()}
   if rows:receipt=self.store.ingest(aid,'garmin',rows,receipt,hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),'wellness')
   self.store.set_provider_sync(aid,'garmin-wellness',receipt);return receipt
 def disconnect(self,aid):
  self.store.athlete(aid)
  with self.lock:self.vault.remove('garmin-'+aid)
  return {'connected':False,'note':'Local key and token removed. Delete the key in Garmin Connect to revoke it at Garmin. Imported history retained.'}
 def begin(self,aid):
  self.store.athlete(aid)
  with self.lock:
   self._serve();nonce=secrets.token_urlsafe(32);self.sessions[nonce]={'athlete':aid,'csrf':secrets.token_urlsafe(32),'expires':time.time()+900}
  return {'setupUrl':self.origin+'/setup/'+nonce,'expiresInSeconds':900,'instructions':'Create your own Personal API key in Garmin Connect, accepting Garmin terms yourself, then enter it directly on this local page. Do not paste it in chat. Keep the plugin running.'}
 def _serve(self):
  if self.server:return
  owner=self
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def reply(self,status,content):
    self.send_response(status);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','same-origin');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'");self.end_headers();self.wfile.write(content.encode())
   def session(self):
    if self.headers.get('Host')!=urllib.parse.urlsplit(owner.origin).netloc:return None
    path=urllib.parse.urlsplit(self.path).path
    if not path.startswith('/setup/'):return None
    entry=owner.sessions.get(path[7:])
    return entry if entry and entry['expires']>time.time() else None
   def do_GET(self):
    entry=self.session()
    if not entry:return self.reply(404,'Setup link expired or unavailable')
    name=html.escape(owner.store.athlete(entry['athlete'])['name']);csrf=html.escape(entry['csrf'])
    self.reply(200,'<!doctype html><meta name="viewport" content="width=device-width"><title>Forge226 Garmin setup</title><style>body{font:17px/1.5 system-ui;background:#f5f3ec;color:#182027;max-width:680px;margin:40px auto;padding:24px}label{display:block}input,select,button{font:inherit;padding:10px;margin:10px 0;width:100%;box-sizing:border-box}button{background:#ff512c;border:0;color:white}</style><h1>Garmin Personal API</h1><p>Connect for '+name+'. Use your own key for your own Garmin account.</p><p>Create a key at <a href="https://connect.garmin.com/app/settings/personalApiToken" target="_blank" rel="noreferrer">Garmin Connect Personal API settings</a>. Accept Garmin’s terms there and choose an expiry. The key is displayed once.</p><form method="post"><input type="hidden" name="csrf" value="'+csrf+'"><label>Personal API key<input name="api_key" type="password" required autocomplete="off"></label><label>Region<select name="region"><option value="global">Global</option><option value="china">China</option></select></label><label>Key expiry date (optional, as shown by Garmin)<input name="key_expires_on" type="date"></label><button>Verify and save connection</button></form><p>Credentials stay in owner-only local files, outside shared exports. This verifies your account; syncing workouts or sleep/HRV is a separate request.</p>')
   def do_POST(self):
    entry=self.session()
    if not entry:return self.reply(403,'Setup link expired or unavailable. Ask for a fresh link.')
    if self.headers.get('Origin')!=owner.origin:return self.reply(403,'Setup browser origin could not be verified. Open the fresh link directly in Safari, Chrome or Firefox.')
    try:
     length=int(self.headers.get('Content-Length','0'))
     if not 0<length<=16000:raise ValueError()
     data=urllib.parse.parse_qs(self.rfile.read(length).decode())
     if not secrets.compare_digest(data.get('csrf',[''])[0],entry['csrf']):return self.reply(403,'Setup form verification failed. Reload a fresh setup link before submitting.')
     with owner.lock:
      owner.connect_key(entry['athlete'],data.get('api_key',[''])[0],data.get('region',['global'])[0],data.get('key_expires_on',[''])[0] or None)
      owner.store.configure_source(entry['athlete'],'garmin','native',True)
      owner.sessions.pop(urllib.parse.urlsplit(self.path).path[7:],None)
     return self.reply(200,'Garmin is connected. Return to your coach to sync activities, and optionally sleep/HRV.')
    except GarminError as e:return self.reply(400,html.escape(str(e)))
    except (ValueError,TypeError,KeyError):return self.reply(400,'Setup processing failed. This does not establish that the key is invalid. No successful connection was saved; inspect the connector without sharing the key.')
  self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.origin='http://127.0.0.1:'+str(self.server.server_port);threading.Thread(target=self.server.serve_forever,daemon=True).start()
 def close(self):
  if self.server:self.server.shutdown();self.server.server_close()
