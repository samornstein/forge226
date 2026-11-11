"""Read-only Strava OAuth/API; credentials stay in restricted local files."""
import os,json,secrets,time,threading,urllib.request,urllib.parse,urllib.error,hashlib,html
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from imports import from_strava
from store import now
from tls import https_handler, network_error

class ApiError(Exception):pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ApiError('Unexpected redirect from Strava; request stopped.')
def request_json(method,url,form=None,token=None):
 if not url.startswith('https://www.strava.com/'):raise ApiError('Invalid API host')
 headers={'Accept':'application/json','User-Agent':'Forge226Local/0.9.1'}
 if token:headers['Authorization']='Bearer '+token
 body=urllib.parse.urlencode(form).encode() if form else None
 if body:headers['Content-Type']='application/x-www-form-urlencoded'
 req=urllib.request.Request(url,data=body,headers=headers,method=method)
 try:
  with urllib.request.build_opener(NoRedirect(), https_handler()).open(req,timeout=25) as response:
   return json.loads(response.read(16*1024*1024))
 except urllib.error.HTTPError as e:
  if e.code==429:raise ApiError('Strava rate limit reached. Retry later; no successful-sync timestamp was advanced.') from None
  if e.code in (400,401,403):raise ApiError(f'Strava authorization/access error ({e.code}); reconnect or check app permissions.') from None
  raise ApiError(f'Strava API returned {e.code}; retry later.') from None
 except (urllib.error.URLError,TimeoutError) as exc:raise ApiError(network_error('Strava',exc)) from None

class Secrets:
 def __init__(self,root):
  self.path=Path(root)/'credentials';self.path.mkdir(mode=0o700,exist_ok=True);os.chmod(self.path,0o700)
 def _file(self,key):
  if not key.replace('-','').isalnum():raise ValueError('Invalid credential key')
  return self.path/(key+'.json')
 def get(self,key):
  p=self._file(key)
  if p.is_symlink():raise ValueError('Credential symlinks are not allowed')
  if not p.exists():return None
  if p.stat().st_mode&0o077:raise ValueError('Credential file permissions must be 0600')
  return json.loads(p.read_text())
 def put(self,key,value):
  p=self._file(key);tmp=self.path/('.'+secrets.token_hex(16))
  fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
  try:
   with os.fdopen(fd,'w') as f:json.dump(value,f);f.flush();os.fsync(f.fileno())
   os.replace(tmp,p)
  finally:
   if tmp.exists():tmp.unlink()
 def remove(self,key):self._file(key).unlink(missing_ok=True)

class Strava:
 def __init__(self,store,http=request_json):
  self.store=store;self.vault=Secrets(store.root);self.http=http;self.lock=threading.RLock();self.server=None;self.sessions={};self.pending={}
 def config(self):
  if os.environ.get('FORGE226_STRAVA_CLIENT_ID') and os.environ.get('FORGE226_STRAVA_CLIENT_SECRET'):
   return {'client_id':os.environ['FORGE226_STRAVA_CLIENT_ID'],'client_secret':os.environ['FORGE226_STRAVA_CLIENT_SECRET']}
  return self.vault.get('strava-app')
 def status(self,aid):
  self.store.athlete(aid);c=self.config();t=self.vault.get('strava-'+aid)
  return {'configured':bool(c),'connected':bool(t),'stravaAthleteId':t.get('athlete_id') if t else None,'scope':t.get('scope') if t else None,'expiresAt':t.get('expires_at') if t else None,'lastSync':self.store.sync(aid),'storage':'Credentials remain in owner-only local files; never included in athlete exports.'}
 def token(self,aid,force=False):
  with self.lock:
   t=self.vault.get('strava-'+aid);c=self.config()
   if not t or not c:raise ApiError('Connect Strava first.')
   if force or float(t['expires_at'])<time.time()+60:
    fresh=self.http('POST','https://www.strava.com/oauth/token',form={**c,'grant_type':'refresh_token','refresh_token':t['refresh_token']})
    self.validate_token(fresh)
    t={**t,**{k:fresh[k] for k in ('access_token','refresh_token','expires_at')}};self.vault.put('strava-'+aid,t)
   return t['access_token']
 @staticmethod
 def validate_token(t):
  if not isinstance(t,dict) or not all(isinstance(t.get(k),str) and t[k] for k in ('access_token','refresh_token')) or not isinstance(t.get('expires_at'),(int,float)) or t['expires_at']<=time.time():raise ApiError('Invalid token response; connection was not saved.')
 def exchange(self,aid,code,scope):
  scopes=set(scope.replace(',',' ').split())
  if not scopes.intersection({'activity:read','activity:read_all'}):raise ApiError('Activity read permission was not granted; reconnect and enable it.')
  c=self.config()
  if not c:raise ApiError('Configure Strava app first.')
  t=self.http('POST','https://www.strava.com/oauth/token',form={**c,'grant_type':'authorization_code','code':code});self.validate_token(t)
  athlete_id=t.get('athlete',{}).get('id')
  if not isinstance(athlete_id,int):raise ApiError('Missing Strava athlete identity')
  prior=self.vault.get('strava-'+aid)
  if prior and prior.get('athlete_id')!=athlete_id:raise ApiError('This is a different Strava athlete. Disconnect first or use a separate athlete profile.')
  for other in self.store.athletes():
   connection=self.vault.get('strava-'+other['id'])
   if other['id']!=aid and connection and connection.get('athlete_id')==athlete_id:raise ApiError('This Strava account is already connected to another local athlete.')
  self.vault.put('strava-'+aid,{**{k:t[k] for k in ('access_token','refresh_token','expires_at')},'athlete_id':athlete_id,'scope':sorted(scopes),'connectedAt':now()})
 def sync(self,aid,days=183):
  athlete=self.store.athlete(aid)
  if not isinstance(days,int) or not 1<=days<=730:raise ValueError('days must be 1–730')
  # Serialize token rotation and the commit/watermark across this server's operations.
  with self.lock:
   token=self.token(aid);end=int(time.time());after=end-days*86400;rows=[];page=1;complete=False
   # Fixed window and bounded pages. A truncated sync never claims complete coverage.
   while page<=10:
    query=urllib.parse.urlencode({'after':after,'before':end,'page':page,'per_page':200})
    try:batch=self.http('GET','https://www.strava.com/api/v3/athlete/activities?'+query,token=token)
    except ApiError as exc:
     if '(401)' not in str(exc):raise
     token=self.token(aid,True);batch=self.http('GET','https://www.strava.com/api/v3/athlete/activities?'+query,token=token)
    if not isinstance(batch,list):raise ApiError('Unexpected activities response')
    for r in batch:rows.append(from_strava(r,athlete['timezone']))
    if len(batch)<200:complete=True;break
    page+=1
   if not complete:raise ApiError('Sync exceeds 2,000 activities; use a shorter window. Existing history is unchanged.')
   unique=list({r['sourceId']:r for r in rows}.values())
   receipt={'coverageStartEpoch':after,'coverageEndEpoch':end,'complete':True,'pages':page,'source':'strava','saved':len(unique),'syncedAt':now()}
   if unique:receipt=self.store.ingest(aid,'strava',unique,receipt,hashlib.sha256(json.dumps(unique,sort_keys=True).encode()).hexdigest())
   self.store.set_sync(aid,receipt)
   return receipt
 def disconnect(self,aid):
  # Revokes the connection at Strava, preserving local historical records.
  self.store.athlete(aid)
  with self.lock:
   token=self.token(aid)
   self.http('POST','https://www.strava.com/oauth/deauthorize',form={'access_token':token})
   self.vault.remove('strava-'+aid)
  return {'connected':False,'history':'Previously imported activities retained locally.'}
 def begin(self,aid):
  self.store.athlete(aid)
  with self.lock:
   self._serve();nonce=secrets.token_urlsafe(32);self.sessions[nonce]={'athlete':aid,'expires':time.time()+900,'csrf':secrets.token_urlsafe(32)}
   return {'setupUrl':self.origin+'/setup/'+nonce,'expiresInSeconds':900,'instructions':'Open this local page to configure your Strava app and authorize read-only activity access. Never paste credentials into chat. Keep the plugin session running during authorization.'}
 def _serve(self):
  if self.server:return
  owner=self
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def reply(self,code,body):
    self.send_response(code);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','same-origin');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'");self.end_headers();self.wfile.write(body.encode())
   def valid_host(self):return self.headers.get('Host')==urllib.parse.urlparse(owner.origin).netloc
   def page(self,content):return '<!doctype html><meta name="viewport" content="width=device-width"><title>Forge226 Strava setup</title><style>body{font:17px/1.5 system-ui;max-width:680px;margin:40px auto;padding:24px;background:#f5f3ec;color:#182027}input,button{font:inherit;padding:10px;margin:8px 0;width:100%;box-sizing:border-box}button{background:#ff512c;border:0;color:white}label{display:block}small{display:block}</style><h1>Forge226 · Strava</h1>'+content
   def do_GET(self):
    if not self.valid_host():return self.reply(403,'Invalid host')
    parsed=urllib.parse.urlsplit(self.path)
    if parsed.path=='/callback':
     q=urllib.parse.parse_qs(parsed.query);state=q.get('state',[''])[0]
     with owner.lock:pending=owner.pending.pop(state,None)
     if not pending or pending['expires']<time.time():return self.reply(400,'Authorization expired or invalid. Start again in Forge226.')
     if q.get('error'):return self.reply(400,'Authorization declined. No connection saved.')
     try:
      with owner.lock:owner.exchange(pending['athlete'],q.get('code',[''])[0],q.get('scope',[''])[0])
      return self.reply(200,self.page('<p>Strava is connected. Return to your coach and ask to sync recent activities.</p>'))
     except (ApiError,ValueError) as e:return self.reply(400,self.page('<p>'+html.escape(str(e))+'</p>'))
    nonce=parsed.path.removeprefix('/setup/') if parsed.path.startswith('/setup/') else ''
    with owner.lock:session=owner.sessions.get(nonce)
    if not session or session['expires']<time.time():return self.reply(404,'Setup link expired or unavailable.')
    configured=bool(owner.config());name=html.escape(owner.store.athlete(session['athlete'])['name']);csrf=html.escape(session['csrf'])
    fields='<p>Create a Strava API application at <a href="https://www.strava.com/settings/api" target="_blank" rel="noreferrer">Strava API settings</a>. Use <b>localhost</b> for the callback domain. Each friend should configure their own app unless your Strava app is approved for additional athletes.</p><label>Client ID<input name="client_id" inputmode="numeric" autocomplete="off"></label><label>Client secret<input name="client_secret" type="password" autocomplete="off"></label><small>Stored in owner-only files on this computer, outside the plugin and athlete exports.</small>'
    content='<p>Connect for <b>'+name+'</b>. This requests read access, including private activities. No workouts will be posted or changed.</p>'+('<p>Your Strava application is already configured. Leave both credential fields blank to keep it, or enter both to correct the configuration.</p>' if configured else '')+'<form method="post" action="'+html.escape(parsed.path)+'"><input type="hidden" name="csrf" value="'+csrf+'">'+fields+'<button>Continue to Strava authorization</button></form>'
    self.reply(200,self.page(content))
   def do_POST(self):
    if not self.valid_host() or self.headers.get('Origin')!=owner.origin:return self.reply(403,'Invalid origin')
    try:n=int(self.headers.get('Content-Length','0'))
    except ValueError:return self.reply(400,'Invalid length')
    if n<1 or n>8192:return self.reply(400,'Invalid request size')
    q=urllib.parse.parse_qs(self.rfile.read(n).decode());nonce=urllib.parse.urlsplit(self.path).path.removeprefix('/setup/')
    with owner.lock:
     session=owner.sessions.get(nonce)
     if not session or session['expires']<time.time() or not secrets.compare_digest(q.get('csrf',[''])[0],session['csrf']):return self.reply(403,'Invalid or expired setup request')
     if not owner.config() or q.get('client_id',[''])[0].strip() or q.get('client_secret',[''])[0].strip():
      client=q.get('client_id',[''])[0].strip();secret=q.get('client_secret',[''])[0].strip()
      if not client.isdigit() or not secret or len(secret)>512:return self.reply(400,'Supply valid Strava app credentials')
      prior=owner.config()
      if prior and prior['client_id']!=client and any(owner.vault.get('strava-'+a['id']) for a in owner.store.athletes()):return self.reply(400,'Disconnect existing Strava connections before switching applications.')
      owner.vault.put('strava-app',{'client_id':client,'client_secret':secret})
     state=secrets.token_urlsafe(32);owner.pending[state]={'athlete':session['athlete'],'expires':time.time()+600};owner.sessions.pop(nonce)
     target='https://www.strava.com/oauth/authorize?'+urllib.parse.urlencode({'client_id':owner.config()['client_id'],'redirect_uri':owner.origin+'/callback','response_type':'code','approval_prompt':'force','scope':'read,activity:read_all','state':state})
    self.send_response(303);self.send_header('Location',target);self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','same-origin');self.end_headers()
  self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.origin='http://127.0.0.1:'+str(self.server.server_port)
  threading.Thread(target=self.server.serve_forever,daemon=True).start()
 def close(self):
  if self.server:self.server.shutdown();self.server.server_close()
