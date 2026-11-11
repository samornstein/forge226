"""Private, transactional athlete storage. No service credentials in this database."""
import os,json,sqlite3,uuid,hashlib,contextlib
from pathlib import Path
from datetime import datetime,timezone

def now(): return datetime.now(timezone.utc).isoformat()
def encode(x): return json.dumps(x,allow_nan=False,separators=(',',':'))
class Store:
 def __init__(self,root=None):
  self.root=Path(root or os.environ.get('FORGE226_DATA_DIR',Path.home()/'Library/Application Support/Forge226Work')).expanduser().resolve()
  self.root.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(self.root,0o700)
  self.path=self.root/'athletes.sqlite3'
  with self.db() as db:
   db.executescript('''
   CREATE TABLE IF NOT EXISTS provider_sync_status(athlete TEXT NOT NULL,provider TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(athlete,provider));
   CREATE TABLE IF NOT EXISTS data_sources(athlete TEXT NOT NULL,provider TEXT NOT NULL,mode TEXT NOT NULL,enabled INTEGER NOT NULL,PRIMARY KEY(athlete,provider));
   CREATE TABLE IF NOT EXISTS wellness(athlete TEXT NOT NULL,source TEXT NOT NULL,source_id TEXT NOT NULL,payload TEXT NOT NULL,import_id TEXT NOT NULL,PRIMARY KEY(athlete,source,source_id));
   CREATE TABLE IF NOT EXISTS athletes(id TEXT PRIMARY KEY,name TEXT NOT NULL,timezone TEXT NOT NULL,profile TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,created TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS activities(athlete TEXT NOT NULL,source TEXT NOT NULL,source_id TEXT NOT NULL,payload TEXT NOT NULL,import_id TEXT NOT NULL,PRIMARY KEY(athlete,source,source_id));
   CREATE TABLE IF NOT EXISTS imports(id TEXT PRIMARY KEY,athlete TEXT NOT NULL,source TEXT NOT NULL,digest TEXT NOT NULL,receipt TEXT NOT NULL,created TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS plans(athlete TEXT NOT NULL,version INTEGER NOT NULL,parent INTEGER,state TEXT NOT NULL,validation TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(athlete,version));
   CREATE TABLE IF NOT EXISTS active(athlete TEXT PRIMARY KEY,version INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS checkins(athlete TEXT NOT NULL,date TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(athlete,date));
   CREATE TABLE IF NOT EXISTS sync_status(athlete TEXT PRIMARY KEY,payload TEXT NOT NULL);
   ''')
  os.chmod(self.path,0o600)
 @contextlib.contextmanager
 def db(self):
  db=sqlite3.connect(self.path,timeout=20);db.row_factory=sqlite3.Row
  try:
   with db: yield db
  finally: db.close()
 def athlete(self,aid):
  with self.db() as db: row=db.execute('SELECT * FROM athletes WHERE id=?',(aid,)).fetchone()
  if not row: raise ValueError('Unknown athlete; use list_athletes or create_athlete.')
  out=dict(row);out['profile']=json.loads(out['profile']);return out
 def create(self,name,tz):
  from zoneinfo import ZoneInfo
  ZoneInfo(tz)
  if not isinstance(name,str) or not name.strip() or len(name)>200: raise ValueError('Supply an athlete display name.')
  aid=uuid.uuid4().hex
  with self.db() as db:db.execute('INSERT INTO athletes VALUES(?,?,?,?,?,?)',(aid,name,tz,'{}',1,now()))
  return self.athlete(aid)
 def athletes(self):
  with self.db() as db:return [dict(x) for x in db.execute('SELECT id,name,timezone,revision FROM athletes ORDER BY created')]
 def save_profile(self,aid,profile,expected_revision):
  self.athlete(aid)
  if not isinstance(profile,dict):raise ValueError('profile must be an object')
  with self.db() as db:
   cur=db.execute('UPDATE athletes SET profile=?,revision=revision+1 WHERE id=? AND revision=?',(encode(profile),aid,expected_revision))
   if cur.rowcount!=1:raise ValueError('Profile changed since read; reload before saving.')
  return self.athlete(aid)
 def ingest(self,aid,source,rows,receipt,digest,kind="workout"):
  self.athlete(aid)
  if not rows:raise ValueError('No valid activities; existing history unchanged.')
  if kind not in ("workout","wellness"):raise ValueError("Unsupported record kind")
  table="activities" if kind=="workout" else "wellness"
  iid=uuid.uuid4().hex
  # A single transaction protects the existing history even if one row fails.
  with self.db() as db:
   for r in rows:
    if not r.get('sourceId'):raise ValueError('Missing source ID')
    db.execute('INSERT INTO '+table+' VALUES(?,?,?,?,?) ON CONFLICT(athlete,source,source_id) DO UPDATE SET payload=excluded.payload,import_id=excluded.import_id',(aid,source,r['sourceId'],encode(r),iid))
   receipt={**receipt,'id':iid,'source':source,'saved':len(rows),'importedAt':now(),'mode':'upsert; existing unmatched activities retained'}
   db.execute('INSERT INTO imports VALUES(?,?,?,?,?,?)',(iid,aid,source,digest,encode(receipt),now()))
  return receipt
 def activities(self,aid):
  self.athlete(aid)
  with self.db() as db:return [json.loads(r[0]) for r in db.execute('SELECT payload FROM activities WHERE athlete=?',(aid,))]
 def receipts(self,aid):
  self.athlete(aid)
  with self.db() as db:return [json.loads(r[0]) for r in db.execute('SELECT receipt FROM imports WHERE athlete=? ORDER BY created DESC LIMIT 30',(aid,))]
 def active_version(self,aid):
  with self.db() as db:
   r=db.execute('SELECT version FROM active WHERE athlete=?',(aid,)).fetchone();return r[0] if r else None
 def plan(self,aid,version=None):
  self.athlete(aid)
  version=version if version is not None else self.active_version(aid)
  with self.db() as db:r=db.execute('SELECT state,validation FROM plans WHERE athlete=? AND version=?',(aid,version)).fetchone()
  if not r:return None
  state=json.loads(r[0]);state['status']='active' if version==self.active_version(aid) else 'draft'
  return {'state':state,'validation':json.loads(r[1])}
 def draft(self,aid,state,parent):
  from check_state import validate
  athlete=self.athlete(aid)
  if state.get('athleteId') not in (None,aid):raise ValueError('Plan belongs to a different athlete.')
  if state.get('timezone')!=athlete['timezone']:raise ValueError('Plan timezone must match athlete timezone.')
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE')
   row=db.execute('SELECT version FROM active WHERE athlete=?',(aid,)).fetchone();active=row[0] if row else None
   if active!=parent:raise ValueError('Active plan changed; reload before drafting.')
   version=db.execute('SELECT COALESCE(MAX(version),0)+1 FROM plans WHERE athlete=?',(aid,)).fetchone()[0]
   state={**state,'athleteId':aid,'version':version,'parentVersion':parent,'status':'draft','generatedAt':now()}
   check=validate(state)
   db.execute('INSERT INTO plans VALUES(?,?,?,?,?,?)',(aid,version,parent,encode(state),encode(check),now()))
  return {'version':version,'status':'draft','validation':check}
 def activate(self,aid,version,expected_active):
  from check_state import validate
  self.athlete(aid)
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE')
   row=db.execute('SELECT version FROM active WHERE athlete=?',(aid,)).fetchone();active=row[0] if row else None
   if active!=expected_active:raise ValueError('Active plan changed; reload before activation.')
   row=db.execute('SELECT state,parent FROM plans WHERE athlete=? AND version=?',(aid,version)).fetchone()
   if not row:raise ValueError('Draft not found')
   if row['parent']!=active:raise ValueError('Draft is stale; create a revision from the current active plan.')
   state=json.loads(row['state']);check=validate(state)
   if not check['passed']:raise ValueError('Plan fails validation: '+ '; '.join(check['errors'][:8]))
   review=state.get('review',{})
   if review.get('decision')!='pass' or review.get('type') not in ('self-review','independent-review'):
    raise ValueError('A documented coaching review with decision pass is required.')
   if any(x.get('severity') in ('blocking','material') for x in review.get('issues',[])):
    raise ValueError('Resolve blocking/material coaching findings before activation.')
   db.execute('INSERT INTO active VALUES(?,?) ON CONFLICT(athlete) DO UPDATE SET version=excluded.version',(aid,version))
  return {'activeVersion':version,'previousVersion':active}
 def checkin(self,aid,payload):
  from datetime import date
  self.athlete(aid);date.fromisoformat(payload['date'])
  with self.db() as db:db.execute('INSERT INTO checkins VALUES(?,?,?) ON CONFLICT(athlete,date) DO UPDATE SET payload=excluded.payload',(aid,payload['date'],encode(payload)))
  return {'saved':payload['date']}
 def checkins(self,aid):
  self.athlete(aid)
  with self.db() as db:return [json.loads(r[0]) for r in db.execute('SELECT payload FROM checkins WHERE athlete=? ORDER BY date DESC LIMIT 60',(aid,))]
 def set_sync(self,aid,payload):
  self.athlete(aid)
  with self.db() as db:db.execute('INSERT INTO sync_status VALUES(?,?) ON CONFLICT(athlete) DO UPDATE SET payload=excluded.payload',(aid,encode(payload)))
 def sync(self,aid):
  self.athlete(aid)
  with self.db() as db:r=db.execute('SELECT payload FROM sync_status WHERE athlete=?',(aid,)).fetchone()
  return json.loads(r[0]) if r else None

 def source_preferences(self,aid):
  self.athlete(aid)
  with self.db() as db:return [dict(r) for r in db.execute('SELECT provider,mode,enabled FROM data_sources WHERE athlete=? ORDER BY provider',(aid,))]
 def configure_source(self,aid,provider,mode,enabled):
  from sources import provider_id
  self.athlete(aid);provider_id(provider)
  if mode not in ('manual','upload','native','external','requested'):raise ValueError('Invalid source mode')
  if mode=='native' and provider not in ('strava','garmin'):raise ValueError('Only Strava and Garmin have bundled live integrations. Use upload, an available external connector, or requested.')
  if mode=='manual' and provider!='manual':raise ValueError('Use provider manual for manual-only coaching')
  with self.db() as db:
   if mode=='manual' and enabled:db.execute('UPDATE data_sources SET enabled=0 WHERE athlete=?',(aid,))
   db.execute('INSERT INTO data_sources VALUES(?,?,?,?) ON CONFLICT(athlete,provider) DO UPDATE SET mode=excluded.mode,enabled=excluded.enabled',(aid,provider,mode,int(enabled)))
  return {'sources':self.source_preferences(aid),'note':'Preferences do not establish or revoke an account connection. Imports/history are retained. External connections must be verified through their host connector.'}
 def wellness(self,aid):
  self.athlete(aid)
  with self.db() as db:return [json.loads(r[0]) for r in db.execute('SELECT payload FROM wellness WHERE athlete=?',(aid,))]

 def provider_sync(self,aid,provider):
  self.athlete(aid)
  with self.db() as db:r=db.execute('SELECT payload FROM provider_sync_status WHERE athlete=? AND provider=?',(aid,provider)).fetchone()
  return json.loads(r[0]) if r else None
 def set_provider_sync(self,aid,provider,payload):
  self.athlete(aid)
  with self.db() as db:db.execute('INSERT INTO provider_sync_status VALUES(?,?,?) ON CONFLICT(athlete,provider) DO UPDATE SET payload=excluded.payload',(aid,provider,encode(payload)))
