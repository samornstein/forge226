"""Race-relative build comparisons and evidence-limited half-distance scenarios."""
from collections import defaultdict
from datetime import date,datetime,timedelta
from statistics import median
from math import isfinite
import re


def _positive(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and isfinite(v) and v>0


def _monday(d):
    return d - timedelta(days=d.weekday())


def _observed_races(rows):
    by_day=defaultdict(list)
    for a in rows:
        by_day[a['date']].append(a)
    races=[]
    for day,legs in sorted(by_day.items()):
        # A transition record distinguishes a race file from coincidental swim, bike and run days.
        if not any('transition' in (a.get('name') or '').lower() for a in legs):
            continue
        bike=max((a.get('distanceMeters') or 0 for a in legs if a['sport']=='Bike'),default=0)
        run=max((a.get('distanceMeters') or 0 for a in legs if a['sport']=='Run'),default=0)
        length='70.3' if 79000<=bike<=101000 and 18000<=run<=24500 else (
            '140.6' if 145000<=bike<=195000 and 37000<=run<=46500 else None)
        if length:
            location=next(((a.get('name') or '').rsplit(' Road Cycling',1)[0] for a in legs
                           if (a.get('name') or '').endswith(' Road Cycling')), '')
            has_swim=any(a['sport']=='Swim' for a in legs)
            label=' '.join(filter(None,(location,length,'race candidate')))
            races.append(dict(name=label,date=day,distance=length,source='inferred from transition and leg distances',
                              swimRecorded=has_swim))
    return races


def _build(label,anchor,kind,by_day,weeks_out,complete):
    def period(offsets):
        weeks=[]
        for n in offsets:
            start=anchor-timedelta(weeks=n)
            totals=dict(All=0.,Swim=0.,Bike=0.,Run=0.)
            days=0
            for i in range(7):
                d=str(start+timedelta(days=i))
                if complete(d):
                    days+=1
                for sport,minutes in by_day.get(d,[]):
                    totals[sport]+=minutes
                    totals['All']+=minutes
            if not days and not totals['All']:
                totals={k:None for k in totals}
            weeks.append(dict(weeksToRace=n,start=str(start),end=str(start+timedelta(days=6)),
                              minutes={k:round(v,2) if v is not None else None for k,v in totals.items()},
                              coverage=f'{days}/7 days',complete=(days==7)))
        valid=[w for w in weeks if w['complete']]
        med={k:round(median([w['minutes'][k] for w in valid]),2) if valid else None
             for k in ('All','Swim','Bike','Run')}
        return dict(weeks=weeks,medianMinutes=med,coverage=f'{len(valid)}/8 complete weeks')
    out=period(range(weeks_out+7,weeks_out-1,-1))
    return dict(label=label,type=kind,**out,finalEight=period(range(8,0,-1)))


def history_comparison(state,activities,coverage,as_of):
    goal=state.get('goal',{})
    race=goal.get('raceDate')
    if not race:
        return dict(referenceRace=None,weeksToRace=None,builds=[])
    race_monday=_monday(date.fromisoformat(race))
    # Include only weeks that had finished before the analysis date.
    last_complete_week=_monday(date.fromisoformat(as_of))-timedelta(weeks=1)
    weeks_out=max(1,(race_monday-last_complete_week).days//7)
    actual=defaultdict(list)
    planned=defaultdict(list)
    for a in activities:
        if a['sport'] in ('Bike','Run','Swim') and _positive(a.get('durationSeconds')) and a['date']<=as_of:
            actual[a['date']].append((a['sport'],a['durationSeconds']/60))
    for s in state.get('sessions',[]):
        if s['sport'] in ('Bike','Run','Swim') and _positive(s.get('minutes')):
            optional = s.get('optional') or s.get('isOptional') or s.get('priority') == 'optional'
            planned[s['date']].append((s['sport'],s.get('baseMinutes',0 if optional else s['minutes'])))
    def recorded(d):
        return d<=as_of and any(r['start']<=d<=r['end'] for r in coverage)
    planned_start=goal.get('startDate') or min(planned,default=race)
    planned_end=goal.get('endDate') or race
    builds=[]
    for kind,dataset,fn in [('planned',planned,lambda d:planned_start<=d<=planned_end),
                            ('recorded',actual,recorded)]:
        item=_build(goal.get('name','Current race'),race_monday,kind,dataset,weeks_out,fn)
        builds.append(dict(item,raceDate=race,source='saved plan' if kind=='planned' else 'recorded activities'))
    inferred=_observed_races(activities)
    races={r['date']:r for r in inferred}
    for r in state.get('historicalRaces',[]):
        if isinstance(r,dict) and r.get('date') and r.get('name'):
            races[r['date']]=dict(r,source='athlete supplied')
    for d,r in sorted(races.items(),reverse=True):
        if d>=min(race,as_of):
            continue
        item=_build(r['name'],_monday(date.fromisoformat(d)),'recorded',actual,weeks_out,recorded)
        builds.append(dict(item,raceDate=d,source=r['source'],swimRecorded=r.get('swimRecorded')))
    return dict(referenceRace=race,weeksToRace=weeks_out,builds=builds,
                basis='Eight Monday–Sunday weeks ending at the equivalent pre-race week. Medians use complete weeks only. Final-eight comparison excludes race week.')


def _follows_ride(run, activities):
    def stamp(text):
        try:
            return datetime.fromisoformat(text.replace('Z','+00:00')).timestamp()
        except (AttributeError,ValueError):
            return None
    start=stamp(run.get('startTime'))
    if start is None:
        return False
    for ride in activities:
        if ride.get('sport')!='Bike' or ride.get('durationSeconds',0)<3600:
            continue
        begin=stamp(ride.get('startTime'))
        if begin is not None and 0<=start-(begin+ride.get('elapsedSeconds',ride['durationSeconds']))<=1800:
            return True
    return False


def _rehearsal_work(session, activity, detail, execution, activities):
    """Accept identified race-effort laps only; summaries and optional choices cannot prove execution."""
    sport=activity.get('sport')
    text=(session.get('title','')+' '+session.get('details','')).lower()
    if '70.3' not in text and 'race' not in text:
        return
    if sport=='Run' and ('brick' not in text or not _follows_ride(activity,activities)):
        return
    if sport=='Bike':
        conditions=(str(detail.get('subSport',''))+' '+activity.get('name','')+' '+activity.get('terrain','')).lower()
        if any(tag in conditions for tag in ('indoor','zwift','trainer','virtual')) or not any(tag in conditions for tag in ('road','outdoor','gravel')):
            return
    if sport=='Swim' and 'open water' not in activity.get('name','').lower():
        return
    if sport not in ('Swim','Bike','Run'):
        return
    laps=detail.get('laps',[])
    seconds=meters=0.
    comparisons=execution.get('repComparisons') or []
    if comparisons:
        for rep in comparisons:
            if re.search(r'70\.3|race (rhythm|power|effort)',rep.get('label',''),re.I) and _positive(rep.get('distanceMeters')):
                seconds+=rep['actualSeconds']
                meters+=rep['distanceMeters']
    elif sport in ('Run','Bike'):
        # Watch-lap alternative for a continuous rehearsal or prescribed repetitions.
        # Require a unique set of distinct laps with the scheduled work duration.
        repeated=re.search(r'(\d+)\s*[×x]\s*(\d+)\s*min at (?:candidate |sustainable )?(?:70\.3|race)',text)
        continuous=re.search(r'(\d+)\s*min continuous at (?:sustainable )?(?:70\.3|race)', text)
        if repeated:
            count,target=int(repeated[1]),int(repeated[2])*60
        elif continuous:
            count,target=1,int(continuous[1])*60
        else:
            return
        found=[l for l in laps if _positive(l.get('durationSeconds')) and
               _positive(l.get('distanceMeters')) and abs(l['durationSeconds']-target)<=max(5,target*.05)]
        if len(found)!=count:
            return
        seconds=sum(l['durationSeconds'] for l in found)
        meters=sum(l['distanceMeters'] for l in found)
    if seconds and meters:
        return seconds,meters


def race_estimate(state,activities,as_of,match_map,details,intervals):
    """Comparable measured pace/speed evidence only. Scenario widths are assumptions, not probabilities."""
    goal=state.get('goal',{})
    if '70.3' not in str(goal.get('distance','')) and 'half' not in str(goal.get('distance','')).lower():
        return dict(status='Half-distance model requires a 70.3 goal.',legs=[],total=None,missing=[],note='')
    today=date.fromisoformat(as_of)
    by_id={a['id']:a for a in activities}
    measured=defaultdict(dict)
    distances={'Swim':1900,'Bike':90000,'Run':21097.5}
    minimum={'Swim':750,'Bike':20000,'Run':3000}
    def add(leg,activity,seconds,meters,context):
        if not _positive(seconds) or not context or not 0<=(today-date.fromisoformat(activity['date'])).days<=84:
            return
        if leg in distances:
            if activity['sport']!=leg or not _positive(meters) or meters<minimum[leg]:
                return
            projection=seconds/meters*distances[leg]
        elif leg in ('T1','T2'):
            projection=seconds
        else:
            return
        measured[leg][activity['id']]=dict(activityId=activity['id'],date=activity['date'],seconds=round(projection,1),context=context)
    # Prior race-distance splits with a transition recorded supply an independent calibration.
    for race in _observed_races(activities):
        if race['distance']!='70.3':
            continue
        for a in activities:
            if a['date']!=race['date']:
                continue
            leg=a.get('sport')
            distance=a.get('distanceMeters')
            if leg in distances and _positive(distance) and .85*distances[leg]<=distance<=1.15*distances[leg]:
                add(leg,a,a.get('durationSeconds'),distance,'Recorded half-distance leg; course conditions may differ.')
            else:
                leg={'transition 1':'T1','transition 2':'T2'}.get(str(a.get('name','')).lower())
                if leg:
                    add(leg,a,a.get('durationSeconds'),None,'Recorded transition.')
    for session in state.get('sessions',[]):
        ids=match_map.get(session.get('id'),[])
        if isinstance(ids,str):
            ids=[ids]
        if isinstance(ids,dict):
            ids=ids.get('activityIds',[])
        if len(ids)!=1 or ids[0] not in by_id:
            continue
        a=by_id[ids[0]]
        result=_rehearsal_work(session,a,details.get(ids[0],{}),intervals.get(session['id'],{}),activities)
        if result:
            add(a['sport'],a,*result,'Measured race-specific work laps from '+session.get('title','rehearsal'))
    for row in state.get('raceEvidence',[]):
        a=by_id.get(row.get('activityId'))
        if a:
            add(row.get('leg'),a,row.get('seconds'),row.get('distanceMeters'),row.get('context'))
    inputs={'Swim':'A recent sustained swim of at least 750 m at race rhythm; note pool or open water.',
            'Bike':'At least 20 km outdoors at candidate race power; record position, course and conditions.',
            'Run':'At least 3 km at sustainable race effort after a representative ride; record the bike load and fueling.',
            'T1':'A timed swim-to-bike rehearsal or race transition.',
            'T2':'A timed bike-to-run rehearsal or race transition.'}
    bands={'Swim':(.04,.08),'Bike':(.05,.10),'Run':(.06,.12),'T1':(.15,.30),'T2':(.15,.30)}
    legs=[]
    for leg in ('Swim','T1','Bike','T2','Run'):
        observations=list(measured[leg].values())
        row=dict(leg=leg,evidence=observations,basis=inputs[leg],lowSeconds=None,centralSeconds=None,highSeconds=None)
        if observations:
            values=[r['seconds'] for r in observations]
            center=median(values)
            fast,slow=bands[leg]
            row.update(lowSeconds=round(min(min(values),center*(1-fast))),
                       centralSeconds=round(center),highSeconds=round(max(max(values),center*(1+slow))))
        legs.append(row)
    missing=[r['leg'] for r in legs if r['centralSeconds'] is None]
    total=None if missing else {k:sum(r[k] for r in legs) for k in ('lowSeconds','centralSeconds','highSeconds')}
    return dict(status='Awaiting comparable evidence' if missing else 'Evidence-based scenarios',
                legs=legs,total=total,missing=missing,
                note='Conditional extrapolation of observed pace or speed from the last 84 days. Fast and slow scenarios include fixed sport-specific margins; these are sensitivity ranges, not statistical intervals. Compare terrain, aero position, swim environment, pacing and fueling before interpreting. Placement and qualification are not modeled.')
