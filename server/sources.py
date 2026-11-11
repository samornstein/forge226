"""Provider-neutral, explicitly mapped file imports. Never implies a live API exists."""
import csv,io,json,zipfile,hashlib,re,math
from pathlib import Path
from datetime import date
from imports import timestamp,num,sport,MAX_BYTES

def provider_id(value):
 if not isinstance(value,str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',value) or len(value)>64:raise ValueError('provider must be a short lowercase identifier, e.g. whoop, wahoo or my-training-log')
 return value

def inspect_file(path):
 """List tables/columns and small raw samples without guessing field meanings."""
 tables,digest=read_tables(path)
 return {'sha256':digest,'tables':[{'name':n,'rows':len(rows),'columns':sorted({k for r in rows[:100] for k in r}),'sample':rows[:2]} for n,rows in tables], 'note':'Confirm field meanings and units before mapping. No records saved.'}

def read_tables(path,records_path=None):
 path=Path(path).expanduser().resolve()
 if not path.is_file() or path.stat().st_size>MAX_BYTES:raise ValueError('Input file missing or over 256 MB')
 raw=path.read_bytes();tables=[];expanded=0;entries=0
 def add(data,name,depth=0):
  nonlocal expanded,entries
  if depth>2:raise ValueError('Nested archive limit exceeded')
  if name.lower().endswith('.zip'):
   with zipfile.ZipFile(io.BytesIO(data)) as z:
    for info in z.infolist():
     if info.is_dir():continue
     entries+=1
     if entries>10000:raise ValueError('Archive has too many files')
     if not info.filename.lower().endswith(('.csv','.json','.zip')):continue
     expanded+=info.file_size
     if expanded>MAX_BYTES:raise ValueError('Expanded archive exceeds 256 MB')
     add(z.read(info),info.filename,depth+1)
  elif name.lower().endswith('.csv'):
   rows=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))));tables.append((name,rows))
  elif name.lower().endswith('.json'):
   value=json.loads(data.decode('utf-8-sig'))
   if records_path:
    for k in records_path.split('.'):
     if not isinstance(value,dict) or k not in value:raise ValueError('records_path not found in '+name)
     value=value[k]
   if isinstance(value,list) and all(isinstance(r,dict) for r in value):tables.append((name,value))
   elif isinstance(value,dict):
    # Inspection can expose named tables; import selects one via records_path.
    for k,v in value.items():
     if isinstance(v,list) and all(isinstance(r,dict) for r in v):tables.append((name+'#'+k,v))
   else:raise ValueError('Expected a JSON array of objects or an object with named tables')
  else:raise ValueError('Generic import accepts CSV, JSON or ZIP containing them')
 add(raw,path.name)
 if not tables:raise ValueError('No tabular CSV/JSON records found; inspect the file or supply records_path')
 return tables,hashlib.sha256(raw).hexdigest()

def mapped_export(path,provider,kind,mapping,tz):
 provider_id(provider)
 if kind not in ('workout','wellness'):raise ValueError('kind must be workout or wellness')
 if not isinstance(mapping,dict) or not isinstance(mapping.get('fields'),dict):raise ValueError('mapping.fields must map canonical field names to source column names')
 fields=mapping['fields'];scales=mapping.get('scales',{});units=mapping.get('units',{});constants=mapping.get('constants',{})
 if not all(isinstance(k,str) and isinstance(v,str) for k,v in fields.items()):raise ValueError('Field mappings must contain column-name strings')
 allowed={'id','startTime','date','name','sport','durationSeconds','distanceMeters','averageHr','averagePower','normalizedPower'} if kind=='workout' else {'id','date','sleepHours','hrvMs','restingHr','recoveryScore','fatigue','stress','notes'}
 if set(fields)-allowed or set(scales)-allowed or set(constants)-{'sport','name'}:raise ValueError('Unsupported canonical field')
 for value in scales.values():
  if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:raise ValueError('Scale factors must be finite positive numbers')
 numeric={'durationSeconds','distanceMeters','averageHr','averagePower','normalizedPower','sleepHours','hrvMs','restingHr','recoveryScore','fatigue','stress'}
 expected={'durationSeconds':'s','distanceMeters':'m','averageHr':'bpm','averagePower':'W','normalizedPower':'W','sleepHours':'h','hrvMs':'ms','restingHr':'bpm'}
 for field in set(fields)&numeric:
  if field in expected and units.get(field)!=expected[field]:raise ValueError('Declare canonical unit '+expected[field]+' for '+field+' after scaling')
 for field in ('recoveryScore','fatigue','stress'):
  if field in fields and not units.get(field):raise ValueError('Describe the source-specific scale for '+field+'; it will not be normalized or combined with other sources')
 if kind=='workout' and not {'durationSeconds'}.issubset(fields):raise ValueError('Workout durationSeconds mapping required')
 tables,digest=read_tables(path,mapping.get('records_path'));selected=mapping.get('table')
 if selected:tables=[t for t in tables if t[0]==selected]
 if len(tables)!=1:raise ValueError('Select exactly one table from source_inspect using mapping.table and/or records_path')
 name,rows=tables[0];out=[];warnings=[]
 for index,row in enumerate(rows):
  try:
   data={}
   for key,column in fields.items():
    if column not in row:raise ValueError('Missing column '+column)
    value=row[column]
    if value is None or value=='':data[key]=None
    elif key in numeric:data[key]=num(value)*scales.get(key,1)
    else:data[key]=str(value)
   if kind=='workout':
    if not data.get('startTime'):raise ValueError('Workout startTime required for timezone and duplicate handling')
    instant,local=timestamp(data['startTime'],tz)
    if not data.get('durationSeconds') or data['durationSeconds']<=0:raise ValueError('Positive duration required')
    duration=data['durationSeconds']
    kind_sport=data.get('sport') or constants.get('sport')
    if not kind_sport:raise ValueError('Sport column or explicit sport constant required')
    canonical={**data,'startTime':instant,'date':local,'sport':sport(kind_sport),'durationSeconds':duration,'name':data.get('name') or constants.get('name') or 'Imported workout'}
   else:
    if not data.get('date'):raise ValueError('Local ISO date mapping required for wellness records')
    if date.fromisoformat(data['date']).isoformat()!=data['date']:raise ValueError('Wellness date must be YYYY-MM-DD')
    if not any(data.get(k) is not None for k in numeric):raise ValueError('No recovery measurement supplied')
    canonical=data
   sid=data.get('id') or hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest()
   canonical.update({'id':provider+':'+sid,'sourceId':sid,'source':provider,'recordKind':kind,'units':units,'sourceFile':name,'normalization':{'fields':fields,'scales':scales}})
   out.append(canonical)
  except (ValueError,TypeError,OverflowError) as e:warnings.append({'row':index+1,'reason':str(e)})
 unique={r['sourceId']:r for r in out}
 return list(unique.values()),{'filename':Path(path).name,'table':name,'recordKind':kind,'recognized':len(out),'duplicatesWithinSource':len(out)-len(unique),'rejected':len(warnings),'warnings':warnings[:20],'mapping':mapping,'coverage':{'first':min((r['date'] for r in out),default=None),'last':max((r['date'] for r in out),default=None)}},digest
