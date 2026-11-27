"""Private, version-aware training review. Dates always use the athlete's calendar."""
import json
import math
import re
import statistics
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from tracker_metrics import metrics_report


def day(value):
    return date.fromisoformat(value)


def monday(value):
    d = day(value)
    return str(d - timedelta(days=d.weekday()))


def entries(store, aid):
    with store.db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS tracking_notes(athlete TEXT,kind TEXT,key TEXT,value TEXT,PRIMARY KEY(athlete,kind,key))")
        rows = db.execute("SELECT kind,key,value FROM tracking_notes WHERE athlete=?", (aid,))
        result = defaultdict(dict)
        for kind, key, value in rows:
            result[kind][key] = json.loads(value)
        return result


def save(store, aid, kind, key, item):
    with store.db() as db:
        db.execute("INSERT OR REPLACE INTO tracking_notes VALUES(?,?,?,?)",
                   (aid,kind,key,json.dumps(item,allow_nan=False)))


def activity_key(a):
    return a.get('id') or a['source']+':'+a['sourceId']


def matches(sessions, acts, overrides, unplanned=None):
    used = {key for key,value in (unplanned or {}).items() if value}
    matched = {}
    for s in sessions:
        override = overrides.get(s['id'])
        if override:
            ids = [i for i in override['activityIds'] if i in acts and not (unplanned or {}).get(i)]
            matched[s['id']] = ids
            used.update(ids)
    groups = defaultdict(list)
    for s in sessions:
        if s['id'] not in matched:
            groups[(s['date'],s['sport'])].append(s)
    candidates = defaultdict(list)
    for k,a in acts.items():
        if k not in used:
            candidates[(a['date'],a['sport'])].append(k)
    for pair, group in groups.items():
        ids = candidates[pair]
        if len(group)==1 and len(ids)==1:
            session=group[0]
            ratio=acts[ids[0]]['durationSeconds']/60/max(session.get('baseMinutes') or session['minutes'],1)
            if 0.45<=ratio<=1.75:
                matched[session['id']]=ids
    return matched


def recovery_days(rows):
    grouped = {}
    for item in rows:
        d = grouped.setdefault((item.get('source'),item['date']),{'date':item['date'],'source':item.get('source')})
        for k,v in item.items():
            if isinstance(v,(int,float)) and not isinstance(v,bool):
                d[k]=v
    return sorted(grouped.values(),key=lambda r:r['date'])


def warnings(recovery, week_sessions):
    messages=[]
    for key, direction in [('hrvMs',-1),('restingHr',1),('sleepHours',-1)]:
        by_source=defaultdict(list)
        for r in recovery:
            if r.get(key) is not None: by_source[r['source']].append(r)
        for source, rows in by_source.items():
            last=day(rows[-1]['date'])
            base=[r[key] for r in rows if 4 <= (last-day(r['date'])).days <=31]
            recent=[r[key] for r in rows if (last-day(r['date'])).days<=2]
            if len(base)<14 or len(recent)<3: continue
            mid=statistics.median(base)
            spread=max(statistics.median(abs(x-mid) for x in base)*1.4826,{'hrvMs':3,'sleepHours':0.5,'restingHr':2}[key])
            if all(direction*(x-mid)>spread for x in recent):
                messages.append(f"{key} has been {'below' if direction<0 else 'above'} your usual range for three days through {last} ({source}). Review effort, sleep and how you feel.")
    missed=[s for s in week_sessions if s['status']=='missed' and s['key']]
    if len(missed)>=2: messages.append(f"{len(missed)} key sessions missed this week. Check schedule and recovery before adding work.")
    return messages


def read_snapshot(app, aid, week=None):
    store=app.store
    athlete=store.athlete(aid)
    today=str(datetime.now(ZoneInfo(athlete['timezone'])).date())
    week=monday(week or today)
    end=str(day(week)+timedelta(days=6))
    state=(store.plan(aid) or {}).get('state',{})
    sessions=state.get('sessions',[])
    notes=entries(store,aid)
    activities=app.enabled_records(aid)
    acts={activity_key(a):a for a in activities}
    match=matches(sessions,acts,notes['match'],notes['unplanned'])
    with store.db() as db:
        receipts=[json.loads(r[0]) for r in db.execute("SELECT receipt FROM imports WHERE athlete=? AND source='garmin'",(aid,))]
    current=store.provider_sync(aid,'garmin')
    if current: receipts.append(current)
    intervals=sorted({(r['coverage']['first'],r['coverage']['last']) for r in receipts if r.get('pages') and r.get('complete') and r.get('coverage',{}).get('first')})
    coverage=[]
    for begin,finish in intervals:
        if coverage and day(begin)<=day(coverage[-1]['end'])+timedelta(days=1):
            coverage[-1]['end']=max(finish,coverage[-1]['end'])
        else: coverage.append({'start':begin,'end':finish})
    state['historicalRaces']=list(notes['race'].values())
    state['raceEvidence']=list(notes['result'].values())
    fresh=max((r['end'] for r in coverage),default=None)
    source_status=store.provider_sync(aid,'garmin-tracker') or {}
    from tracker_import import activity_details
    details=activity_details(store,aid)
    activities=[dict(a,benchmarkRoute=notes['checkin'].get(a['id'],{}).get('conditions') or a.get('benchmarkRoute')) for a in activities]
    metrics=metrics_report(state,activities,thresholds=state.get('athlete',{}).get('thresholds',[])+list(notes['threshold'].values()),as_of=today,match_map=match,coverage=coverage,details=details,comparison_as_of=min(end,today))
    rows=[]
    for s in sessions:
        if not week<=s['date']<=end: continue
        ids=match.get(s['id'],[])
        portions=notes['match'].get(s['id'],{}).get('portions',{})
        mins=sum(acts[i]['durationSeconds']/60*portions.get(i,1) for i in ids)
        optional=bool(s.get('baseMinutes')==0 or s.get('optional') or s.get('isOptional') or s.get('priority')=='optional')
        key=bool(re.search(r'long |brick|threshold|tempo|track |rehearsal|sweet spot',s['title'],re.I))
        status='scheduled'
        if ids:
            status='swapped' if any(acts[i]['date']!=s['date'] for i in ids) else 'partial' if mins<0.8*(s.get('baseMinutes') or s['minutes']) else 'done'
        elif s['date']<today:
            covered=any(r['start']<=s['date']<=r['end'] for r in coverage)
            status='optional' if optional else 'awaiting sync' if not covered else 'needs match' if any(a['date']==s['date'] and a['sport']==s['sport'] for a in activities) else 'missed'
        override=notes['match'].get(s['id'],{})
        status=override.get('status') or status
        rows.append(dict(s,activityIds=ids,portions=portions,actualMinutes=round(mins,1),optional=optional,key=key,status=status,
                         execution=metrics.get('intervals',{}).get(s['id']) if isinstance(metrics.get('intervals'),dict) else None))
    actual=[dict(a,id=k,unplanned=bool(notes['unplanned'].get(k)),checkin=notes['checkin'].get(k)) for k,a in acts.items() if week<=a['date']<=end]
    totals=[]
    for sport in ['Swim','Bike','Run','Strength']:
        ps=[s for s in rows if s['sport']==sport]; ac=[a for a in actual if a['sport']==sport]
        def summed(vals):
            return round(sum(vals),1) if all(isinstance(n,(float,int)) for n in vals) else None
        planned_dist=[]
        for s in ps:
            m=re.search(r'([\d,]+)\s*(yd|yards|km|mi)\b',s['title'],re.I) if sport=='Swim' else None
            planned_dist.append(s.get('distanceMeters') or (float(m[1].replace(',','')) * {'yd':.9144,'yards':.9144,'km':1000,'mi':1609.344}[m[2].lower()] if m else None))
        totals.append(dict(sport=sport,plannedMinutes=sum(s.get('baseMinutes',0 if s['optional'] else s['minutes']) for s in ps),optionalMinutes=sum(s['minutes']-s.get('baseMinutes',0 if s['optional'] else s['minutes']) for s in ps),actualMinutes=round(sum(a['durationSeconds']/60 for a in ac),1),
                           plannedDistanceMeters=summed(planned_dist),actualDistanceMeters=summed([a.get('distanceMeters') for a in ac]),
                           plannedStress=summed([metrics['plannedScores'].get(s['id'],{}).get('stress') for s in ps if not s['optional']]),
                           actualStress=summed([metrics['scores'].get(a['id'],{}).get('stress') for a in ac])))
    cutoff=min(today,end)
    recovery=[r for r in recovery_days(app.enabled_records(aid,'wellness')) if str(day(cutoff)-timedelta(days=56))<=r['date']<=cutoff]
    alerts=warnings(recovery,rows)
    prior=[sum(a['durationSeconds']/60 for a in activities if a['sport']=='Run' and monday(a['date'])==str(day(week)-timedelta(weeks=w))) for w in range(1,5)]
    run=totals[2]
    if min(prior)>0 and run['actualMinutes']>1.25*statistics.median(prior) and run['actualMinutes']>run['plannedMinutes']:
        alerts.append("Running time is above plan and over 25% above your preceding four-week median. Review the extra running before increasing load.")
    wins=[s['title'] for s in rows if s['key'] and s['status'] in ('done','swapped')]
    slips=[s['title'] for s in rows if s['key'] and s['status'] in ('partial','missed')]
    next_steps=list(alerts)
    if slips: next_steps.append("Keep the next key rehearsal in place. Review the missed dose alongside fatigue before rescheduling it.")
    if not next_steps: next_steps.append("Follow the approved calendar. Review the next key session against its prescribed work.")
    proposals=[]
    if alerts:
        upcoming=sorted((s for s in sessions if max(today,end)<s['date']<=str(day(max(today,end))+timedelta(days=7)) and s['sport']=='Run' and s.get('baseMinutes',s.get('minutes',0))>=30 and re.search(r'long|tempo|threshold|track',s['title'],re.I)),key=lambda s:s['date'])
        if upcoming:
            s=upcoming[0]
            proposals.append(dict(id='easy-'+s['id'],title='Make the next quality run easy',detail='Keep the date and duration. Replace the main set with conversational running. '+next_steps[0],sessionId=s['id'],**{'from':s['title'],'to':f"Easy aerobic run · {s['minutes']} min"}))
    ready=[]
    for sport,label in [('Bike','Longest ride'),('Run','Longest run'),('Swim','Longest swim')]:
        recent=[a for a in activities if a['sport']==sport and 0<=(day(cutoff)-day(a['date'])).days<42]
        if recent:
            a=max(recent,key=lambda a:a['durationSeconds']); ready.append(dict(label=label,value=f"{round(a['durationSeconds']/60)} min",detail=a['date']+' · '+a.get('name',sport),activityId=a['id'],date=a['date']))
    bricks=[s for s in sessions if s['date']<=cutoff and 'brick' in s['title'].lower() and match.get(s['id'])]
    if bricks:
        last=max(bricks,key=lambda s:s['date'])
        ready.append(dict(label='Latest matched brick',value=last['date'],detail=last['title'],activityId=match[last['id']][0],date=acts[match[last['id']][0]]['date']))
    for k,c in sorted(notes['checkin'].items(),key=lambda x:x[1]['date'],reverse=True):
        if c['date']<=cutoff and ('carbs' in c or 'fluid' in c) and k in acts:
            duration=acts[k]['durationSeconds']/3600
            intake=f"{c['carbs']/duration:.0f} g/hour" if duration and 'carbs' in c else 'Fueling logged'
            ready.append(dict(label='Nutrition practice',value=intake,detail=f"{c['date']} · {acts[k].get('name','Workout')} · Fluid {c.get('fluid','—')} mL · GI {c.get('gi','unrecorded')}",activityId=k,date=c['date']))
            break
    ready.extend(dict(label='Upcoming rehearsal',value=s['date'],detail=s['title']+' · '+s.get('details','')) for s in sorted(sessions,key=lambda s:s['date']) if cutoff<=s['date'] and 'rehearsal' in s['title'].lower())
    return dict(week=week,today=today,version=state.get('version'),sessions=rows,activities=actual,totals=totals,metrics=metrics,recovery=recovery,alerts=alerts,
                review=dict(wins=wins,slips=slips,next=next_steps),proposals=proposals,readiness=ready[:10],lessons=sorted(notes['lesson'].values(),key=lambda x:x['date'],reverse=True),
                adjacentSessions=[s for s in sessions if str(day(week)-timedelta(days=7))<=s['date']<=str(day(end)+timedelta(days=7))],
                matchCandidates=[dict(a,id=k) for k,a in acts.items() if str(day(week)-timedelta(days=7))<=a['date']<=str(day(end)+timedelta(days=7))],
                sourceStatus=source_status,freshness=f"Garmin activity coverage through {fresh}" if fresh else "Garmin activity coverage unknown",coverage=coverage)


def action(app,aid,body):
    store=app.store
    notes=entries(store,aid)
    kind=body['action']
    if kind=='sync':
        app.require_source(aid,'garmin')
        from tracker_import import sync_tracker
        result=sync_tracker(app.garmin,aid)
        failures=[k for k,v in result['datasets'].items() if v['status']!='succeeded']
        result['message']='Garmin synced.' if result['complete'] else result.get('status') or ('Garmin sync incomplete. Check '+', '.join(failures)+'.' if failures else 'Garmin sync is incomplete.')
        return result
    state=(store.plan(aid) or {}).get('state',{})
    sessions={s['id']:s for s in state.get('sessions',[])}
    acts={activity_key(a):a for a in app.enabled_records(aid)}
    if kind=='match':
        sid=body['sessionId']
        ids=body.get('activityIds',[])
        status=body.get('status') or ''
        if sid not in sessions or not isinstance(ids,list) or len(set(ids))!=len(ids) or any(k not in acts for k in ids):
            raise ValueError('Choose a saved session and unique recorded activities.')
        if status not in ('','done','partial','missed','swapped','unplanned','scheduled','optional'): raise ValueError('Unknown match status.')
        supplied=body.get('portions',{})
        if not isinstance(supplied,dict) or set(supplied)-set(ids):
            raise ValueError('Portions must refer to the chosen workouts.')
        portions={i:float(supplied.get(i,1)) for i in ids}
        for i,part in portions.items():
            if notes['unplanned'].get(i): raise ValueError('Clear the unplanned flag before matching.')
            used=sum(other.get('portions',{}).get(i,1) for key,other in notes['match'].items() if key!=sid and key in sessions and i in other['activityIds'])
            if not 0<part<=1 or part+used>1.000001: raise ValueError('Combined allocations must fit within 100% of the recording.')
        save(store,aid,kind,sid,dict(activityIds=ids,status=status,portions=portions))
    elif kind=='unplanned':
        k=body['activityId']
        if k not in acts: raise ValueError('Recording unavailable.')
        if body['unplanned'] and any(k in o['activityIds'] for o in notes['match'].values()):
            raise ValueError('Remove the manual assignment first.')
        save(store,aid,kind,k,bool(body['unplanned']))
    elif kind=='race':
        d=str(day(body['date'])); name=str(body['name']).strip()[:160]
        if not name or body['distance'] not in ('70.3','140.6'): raise ValueError('Choose a race name and distance.')
        save(store,aid,kind,d,dict(date=d,name=name,distance=body['distance']))
    elif kind=='result':
        k=body['activityId']; leg=body['leg']
        if k not in acts or leg not in ('T1','T2','Bike','Run','Swim'): raise ValueError('Choose a recording and leg.')
        sec=float(body['seconds']); meters=float(body.get('distanceMeters') or 0)
        if not math.isfinite(sec+meters) or sec<=0 or meters<0 or (leg not in ('T1','T2') and meters<=0): raise ValueError('Check the recorded distance and duration.')
        save(store,aid,kind,k+'-'+leg,dict(activityId=k,leg=leg,seconds=sec,distanceMeters=meters,date=acts[k]['date'],context=str(body.get('context',''))[:200]))
    elif kind=='checkin':
        key=body['activityId']
        if key not in acts: raise ValueError('Choose a recorded activity.')
        row={'date':acts[key]['date']}
        for field in ('rpe','soreness','carbs','fluid','gi','notes','conditions','equipment','aeroMinutes'):
            value=body.get(field)
            if value is None or value=='': continue
            if field in ('rpe','carbs','fluid','aeroMinutes'):
                value=float(value)
                if not math.isfinite(value) or value<0 or (field=='rpe' and value>10): raise ValueError('Check the numerical entries.')
            else: value=str(value)[:2000]
            row[field]=value
        save(store,aid,kind,key,row)
    elif kind=='threshold':
        sport=body['sport']; unit=body.get('units',body.get('unit')); k=body.get('kind')
        if (sport,k,unit) not in [('Bike','ftp','W'),('Run','runPace','s/km'),('Swim','css','s/100m'),('Bike','lthr','bpm'),('Run','lthr','bpm')]: raise ValueError('Choose a sport-specific threshold and its units.')
        d=str(day(body['date'])); val=float(body['value'])
        if not math.isfinite(val) or val<=0: raise ValueError('Provide a positive measured value.')
        save(store,aid,kind,f'{d}-{sport}-{k}',dict(sport=sport,kind=k,date=d,units=unit,value=val,source=str(body.get('source','Athlete entry'))[:200]))
    elif kind=='lesson':
        msg=body['text'].strip()
        if not msg: raise ValueError('Enter the observation and its evidence.')
        save(store,aid,kind,uuid.uuid4().hex,dict(text=msg[:3000],date=str(datetime.now(ZoneInfo(state['timezone'])).date()),version=state['version']))
    elif kind=='approve':
        snap=read_snapshot(app,aid,body['week'])
        if body['version']!=snap['version']: raise ValueError('The plan changed. Reload to review the current proposal.')
        prop=next((x for x in snap['proposals'] if x['id']==body['id']),None)
        if not prop: raise ValueError('This proposal is no longer current.')
        s=sessions[prop['sessionId']]
        for k in ('profileSteps','optionalSteps','runDose','workout','steps','options','workoutOptions','optionalWorkout'):
            s.pop(k,None)
        s.update(title=prop['to'],intensity='Conversational, RPE 2–3/10',details=f"{s['minutes']} minutes easy, including an easy opening and cooldown.",purpose='Absorb recent training.',successCue='Finish feeling comfortable.',alternative='Shorten if recovery is poor.')
        state.setdefault('changes',[]).append(dict(date=snap['today'],reason=prop['detail'],scope=s['id']))
        state['review']={'type':'self-review','decision':'pass','issues':[],'checks':['Athlete approved a same-duration easy run in the existing slot.']}
        draft=store.draft(aid,state,snap['version'])
        if not draft['validation']['passed']: raise ValueError('The proposed plan failed calendar validation.')
        return store.activate(aid,draft['version'],snap['version'])
    else: raise ValueError('Unknown tracking action.')
    return {'saved':True}
