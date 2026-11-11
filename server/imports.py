"""Bounded Garmin JSON/ZIP/CSV import with explicit unit handling."""
import csv,io,json,zipfile,hashlib,math
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
MAX_BYTES=256*1024*1024

def sport(v):
 v=str(v).lower()
 if 'swim' in v:return 'Swim'
 if any(k in v for k in ('cycl','ride','bik')):return 'Bike'
 if 'run' in v:return 'Run'
 if any(k in v for k in ('strength','weight')):return 'Strength'
 return 'Other'
def num(v):
 if v is None or v=='':return None
 n=float(v)
 if not math.isfinite(n) or n<0:raise ValueError('Invalid negative/nonfinite measurement')
 return n

def timestamp(v,tz):
 if isinstance(v,(int,float)):
  dt=datetime.fromtimestamp(v/1000 if v>100000000000 else v,timezone.utc)
 else:
  dt=datetime.fromisoformat(str(v).replace('Z','+00:00'))
 if dt.tzinfo is None:dt=dt.replace(tzinfo=ZoneInfo(tz))
 return dt.astimezone(timezone.utc).isoformat(),dt.astimezone(ZoneInfo(tz)).date().isoformat()

def first(row,*keys):
 for k in keys:
  if row.get(k) is not None:return row[k]
 return None

def records(value):
 if isinstance(value,list):
  for x in value:yield from records(x)
 elif isinstance(value,dict):
  if any(k in value for k in ('startTimeLocal','startTimeGMT','startTime','beginTimestamp','start_time')) and any(k in value for k in ('activityId','activityUUID','activityType','activityTypeDTO','sportType','sport_type')):yield value
  else:
   for x in value.values():
    if isinstance(x,(dict,list)):yield from records(x)

def normalize(row,tz,units,filename):
 # Explicit canonical fields win; Garmin's named summarized export has documented-in-receipt scale.
 canonical='durationSeconds' in row or 'duration_seconds' in row
 if canonical:duration=num(first(row,'durationSeconds','duration_seconds'));distance=num(first(row,'distanceMeters','distance_meters'));method='explicit seconds/meters fields'
 else:
  chosen=units
  if chosen=='auto':
   if 'summarizedactivities' in filename.lower():chosen='milliseconds_centimeters'
   elif 'activityTypeDTO' in row:chosen='seconds_meters'
   else:raise ValueError('Ambiguous Garmin units: specify seconds_meters or milliseconds_centimeters after inspecting export metadata.')
  if chosen not in ('seconds_meters','milliseconds_centimeters'):raise ValueError('Unsupported units')
  duration=num(first(row,'duration','movingDuration','elapsedDuration'));distance=num(row.get('distance'))
  if chosen=='milliseconds_centimeters':
   duration=duration/1000 if duration is not None else None;distance=distance/100 if distance is not None else None
  method=chosen
 if duration is None or duration<=0:raise ValueError('Missing or zero duration')
 start=first(row,'startTimeGMT','startTimeLocal','startTime','beginTimestamp','start_time')
 # GMT strings without offsets must be interpreted as UTC, never athlete local.
 use_tz='UTC' if row.get('startTimeGMT') is not None else tz
 instant,_=timestamp(start,use_tz);_,local=timestamp(instant,tz)
 typ=row.get('activityTypeDTO') or {};kind=first(row,'sportType','sport_type','activityType') or (typ.get('typeKey') if isinstance(typ,dict) else typ) or 'Other'
 if isinstance(kind,dict):kind=kind.get('typeKey','Other')
 sid=first(row,'activityId','activityUUID','id')
 if sid is None:sid=hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest()
 return {'id':'garmin:'+str(sid),'sourceId':str(sid),'source':'garmin','name':str(first(row,'activityName','name') or kind),'sport':sport(kind),'startTime':instant,'date':local,'durationSeconds':duration,'distanceMeters':distance,'averageHr':num(first(row,'avgHr','avgHR','averageHR','averageHeartRate')),'averagePower':num(first(row,'avgPower','averagePower')),'normalizedPower':num(first(row,'normPower','normalizedPower')),'normalization':method,'sourceFile':filename}

def read_export(path,tz,units='auto',distance_unit=None):
 path=Path(path).expanduser().resolve()
 if not path.is_file() or path.stat().st_size>MAX_BYTES:raise ValueError('File missing or exceeds 256 MB input limit.')
 data=path.read_bytes();budget=[0,0];found=[];rejected=[];files=[]
 def visit(blob,name,depth=0):
  if depth>2:raise ValueError('Nested ZIP limit exceeded')
  low=name.lower()
  if low.endswith('.zip'):
   with zipfile.ZipFile(io.BytesIO(blob)) as z:
    for info in z.infolist():
     if info.is_dir():continue
     budget[1]+=1
     if budget[1]>10000:raise ValueError('ZIP entry limit exceeded')
     if not info.filename.lower().endswith(('.json','.csv','.zip')):continue
     budget[0]+=info.file_size
     if budget[0]>MAX_BYTES or info.file_size>MAX_BYTES:raise ValueError('Expanded archive exceeds 256 MB limit')
     visit(z.read(info),info.filename,depth+1)
  elif low.endswith('.json'):
   files.append(name)
   for row in records(json.loads(blob.decode('utf-8-sig'))):
    try:found.append(normalize(row,tz,units,name))
    except (ValueError,TypeError,OverflowError) as e:rejected.append({'file':name,'reason':str(e)})
  elif low.endswith('.csv'):
   files.append(name)
   for row in csv.DictReader(io.StringIO(blob.decode('utf-8-sig'))):
    try:
     if 'durationSeconds' in row:found.append(normalize(row,tz,units,name));continue
     time=row.get('Time') or row.get('Moving Time')
     parts=[float(x) for x in time.split(':')]
     if len(parts) not in (2,3):raise ValueError('CSV Time must be MM:SS or HH:MM:SS')
     seconds=sum(x*60**i for i,x in enumerate(reversed(parts)))
     dist=num(row.get('Distance'))
     if dist is not None and distance_unit not in ('km','mi','m'):raise ValueError('CSV distance unit required: km, mi or m')
     meters=dist*{'km':1000,'mi':1609.344,'m':1}[distance_unit] if dist is not None else None
     canonical={'startTime':row.get('Date'),'sportType':row.get('Activity Type'),'durationSeconds':seconds,'distanceMeters':meters,'activityName':row.get('Title'),'activityId':row.get('Activity ID') or hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest(),'averageHeartRate':row.get('Avg HR')}
     found.append(normalize(canonical,tz,'seconds_meters',name))
    except (ValueError,TypeError,AttributeError) as e:rejected.append({'file':name,'reason':str(e)})
  else:raise ValueError('Supported Garmin exports: ZIP containing JSON, activity JSON, or CSV. FIT/TCX parsing is not installed.')
 visit(data,path.name)
 # Within-source IDs are reliable dedup keys; cross-source duplicates are reported by analysis.
 unique={r['sourceId']:r for r in found}
 receipt={'filename':path.name,'filesRead':files,'recognized':len(found),'duplicatesWithinSource':len(found)-len(unique),'rejected':len(rejected),'warnings':rejected[:20],'unitsRequested':units,'timezone':tz,'coverage':{'first':min((r['date'] for r in found),default=None),'last':max((r['date'] for r in found),default=None)}}
 return list(unique.values()),receipt,hashlib.sha256(data).hexdigest()

def from_strava(row,tz):
 instant,local=timestamp(row['start_date'],tz)
 duration=num(row.get('moving_time'))
 if duration is None:duration=num(row.get('elapsed_time'))
 if duration is None or duration<=0:raise ValueError('Invalid Strava duration')
 return {'id':'strava:'+str(row['id']),'sourceId':str(row['id']),'source':'strava','name':row.get('name','Strava activity'),'sport':sport(row.get('sport_type') or row.get('type')),'startTime':instant,'date':local,'durationSeconds':duration,'elapsedSeconds':num(row.get('elapsed_time')),'distanceMeters':num(row.get('distance')),'averageHr':num(row.get('average_heartrate')),'averagePower':num(row.get('average_watts')),'normalizedPower':num(row.get('weighted_average_watts')),'normalization':'Strava API seconds/meters'}
