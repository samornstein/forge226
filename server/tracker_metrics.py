"""Personal endurance-load estimates. Missing thresholds and unscored work remain explicit."""
from collections import defaultdict, deque
from datetime import date, timedelta
from math import exp, isfinite
import re
from zoneinfo import ZoneInfo
from datetime import datetime
from tracker_races import history_comparison, race_estimate

SPORTS = ('Bike', 'Run', 'Swim')
MODEL = 'forge-load-1'
UNITS = {'ftp': ('Bike', 'W'), 'runPace': ('Run', 's/km'), 'css': ('Swim', 's/100m')}
# Planning priors, expressed as fractions of individual threshold intensity.
EFFORT = {'recovery': .52, 'easy': .67, 'moderate': .76, 'steady': .83,
          'building': .85, 'quality': .96, 'fast': 1.08, 'session': .72}


def number(value, allow_zero=False):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and isfinite(value) and (value >= 0 if allow_zero else value > 0))


def date_string(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def parameters(rows, sport, day):
    """Select the most recent effective, explicitly sourced sport-specific value."""
    result = {}
    rows = [r for r in rows if isinstance(r, dict) and r.get('sport') == sport
            and date_string(r.get('date')) and r['date'] <= day and r.get('source')]
    for r in sorted(rows, key=lambda item: item['date']):
        kind = r.get('kind')
        unit = r.get('units')
        if (UNITS.get(kind) == (sport, unit) or (kind == 'lthr' and unit == 'bpm')) and number(r.get('value')):
            result[kind] = r
    return result


def segments(samples, key):
    """Piecewise constant recorded measurements; omit gaps over ten seconds and unknowns."""
    for a, b in zip(samples, samples[1:]):
        start, end, value = a.get('elapsedSeconds'), b.get('elapsedSeconds'), a.get(key)
        if number(start, True) and number(end) and 0 < end-start <= 10 and number(value, key == 'power'):
            yield start, end, value


def rolling_power(samples, duration):
    """Thirty-second trailing mean raised to the fourth; reset the window across gaps."""
    chunk = deque()
    total = fourth = count = covered = 0
    previous = None
    for start, end, watts in segments(samples, 'power'):
        if start != previous:
            chunk.clear()
            total = 0
        for _ in range(round(end) - round(start)):
            chunk.append(watts)
            total += watts
            if len(chunk) > 30:
                total -= chunk.popleft()
            if len(chunk) == 30:
                fourth += (total / 30) ** 4
                count += 1
        covered += end - start
        previous = end
    if count and covered >= duration * .90:
        return (fourth / count) ** .25
    return None


def score_activity(activity, thresholds, detail=None):
    sport, day = activity.get('sport'), activity.get('date')
    duration = activity.get('durationSeconds')
    unavailable = dict(stress=None, method='unscored', confidence='unavailable',
                       reason='No suitable measurements and dated threshold for this sport.')
    if sport not in SPORTS or not number(duration) or not date_string(day):
        return dict(unavailable, reason='Outside modeled endurance load or missing duration/date.')
    calibration = parameters(thresholds, sport, day)
    samples = (detail or {}).get('samples', [])
    def score(intensity, seconds, method, confidence, kind, exponent=2):
        return dict(stress=round(100 * seconds / 3600 * intensity ** exponent, 2),
                    method=method, confidence=confidence, intensityFactor=round(intensity, 3),
                    threshold=calibration[kind], durationSeconds=seconds)
    if sport == 'Bike' and 'ftp' in calibration:
        power = activity.get('normalizedPower')
        if not number(power):
            power = rolling_power(samples, duration)
        if number(power):
            return score(power/calibration['ftp']['value'], duration, 'Power / FTP', 'measured', 'ftp')
    if sport == 'Run' and 'runPace' in calibration:
        speed = activity.get('gradeAdjustedSpeedMps')
        method = 'Grade-adjusted pace'
        if not number(speed) and activity.get('terrain') not in ('trail', 'technical'):
            speed = grade_speed(activity, samples)
            method = 'Estimated grade-cost pace'
        if not number(speed) and (activity.get('terrain') in ('flat', 'track', 'treadmill')
                                  or activity.get('isFlat') is True):
            distance = activity.get('distanceMeters')
            speed = distance/duration if number(distance) else None
            method = 'Flat-course pace'
        if number(speed):
            return score(speed * calibration['runPace']['value']/1000, duration, method, 'estimated', 'runPace')
    if sport == 'Swim' and 'css' in calibration:
        lengths = (detail or {}).get('lengths', [])
        active = activity.get('activeSwimSeconds') or (detail or {}).get('activeSwimSeconds')
        distance = activity.get('distanceMeters')
        if not number(active) and lengths:
            moving = [r for r in lengths if r.get('type', r.get('lengthType')) == 'active']
            if moving and all(number(r.get('durationSeconds')) for r in moving):
                active = sum(r['durationSeconds'] for r in moving)
        if number(distance) and number(active) and active <= duration * 1.02:
            return score(distance/active * calibration['css']['value']/100, active,
                         'Active swim pace / CSS', 'estimated', 'css', exponent=3)
    if 'lthr' in calibration:
        lthr = calibration['lthr']['value']
        periods = list(segments(samples, 'hr'))
        covered = sum(b-a for a,b,_ in periods)
        if duration * .90 <= covered <= duration * 1.10:
            # Relative-HR stress is an explicitly approximate quadratic model.
            effective = (sum((b-a)*(v/lthr)**2 for a,b,v in periods)/covered)**.5
            return score(effective, covered, 'Sampled HR / LTHR', 'estimated', 'lthr')
        if number(activity.get('averageHr')):
            return score(activity['averageHr']/lthr, duration, 'Average HR / LTHR', 'low', 'lthr')
    return unavailable


def planning_if(label, kind='session'):
    text = str(label).lower()
    pct = re.search(r'(\d{2,3})(?:\s*[–-]\s*(\d{2,3}))?\s*%\s*(?:of\s+)?(?:current\s+)?ftp', text)
    if pct:
        return (int(pct[1])+int(pct[2] or pct[1]))/200
    for tag, intensity in [('10k',1.04),('5k',1.08),('half-marathon',.94),('threshold',1),
                           ('sweet spot',.90),('marathon effort',.86),('race power',.82),
                           ('70.3',.83),('recovery',.52),('easy',.67)]:
        if tag in text:
            return intensity
    return EFFORT.get(str(kind).lower(),.72)


def prescription_steps(session):
    """Use structured steps first. Decode familiar explicit cycling prescriptions conservatively."""
    explicit = session.get('profileSteps') or []
    if explicit or session.get('sport') != 'Bike':
        return explicit
    text = session.get('details','')
    total = session.get('minutes',0)
    steps = []
    def add(label,minutes,level,kind):
        if minutes>0:
            steps.append(dict(label=label,time=minutes,level=level,kind=kind))
    warm = re.match(r'(\d+) min (progressive )?warm-up',text,re.I)
    if not warm:
        return []
    if '5 easy, 4 moderate, 2 building, 1 easy' in text and int(warm[1])==12:
        for label,time,level in [('Easy',5,55),('Moderate',4,70),('Building',2,80),('Easy',1,55)]:
            add(label,time,level,label)
    else:
        add('Warm-up',int(warm[1]),65,'Easy')
    steady = re.search(r'(\d+) min (?:easy aerobic riding before|aerobic at)',text,re.I)
    if steady:
        add('Aerobic',int(steady[1]),68.5,'Steady')
    recover = re.search(r'(\d+) min easy between',text,re.I)
    pause = int(recover[1]) if recover else 0
    repeated = re.search(r'(\d+)\s*[×x]\s*(\d+)\s*min\s*(?:at\s*)?([^.]*)',text,re.I)
    ladder = re.search(r'(\d+(?:\s*\+\s*\d+)+) min at ((?:\d+%,?\s*)+)',text,re.I)
    if ladder:
        durations = [int(n) for n in re.findall(r'\d+',ladder[1])]
        levels = [int(n) for n in re.findall(r'\d+',ladder[2])]
        if len(durations)!=len(levels):
            return []
        reps = [[(minutes,level)] for minutes,level in zip(durations,levels)]
    elif repeated:
        count,minutes,target = int(repeated[1]),int(repeated[2]),repeated[3]
        if not 1<=count<=40:
            return []
        if target.startswith(':'):
            parts = [(int(m),int(v)) for m,v in re.findall(r'(\d+)(?: min)? at (\d+)%',target)]
            if sum(m for m,v in parts)!=minutes:
                return []
        elif '70.3 effort' in target:
            parts=[(minutes,82)]
        else:
            match=re.match(r'(\d+)(?:[–-](\d+))?%',target)
            if not match:
                return []
            parts=[(minutes,(int(match[1])+int(match[2] or match[1]))/2)]
        reps=[parts]*count
    else:
        return []
    for idx,parts in enumerate(reps):
        for minutes,level in parts:
            label = 'candidate 70.3 effort' if '70.3 effort' in text else f'{level:g}% FTP'
            add(f'Rep {idx+1} · {label}',minutes,level,'Quality')
        if idx+1<len(reps):
            add('Easy between reps',pause,52,'Recovery')
    cool = re.search(r'(?:Finish with (\d+) min easy|(\d+) min easy to finish)',text,re.I)
    if cool:
        add('Cooldown',int(cool[1] or cool[2]),55,'Easy')
    if abs(sum(s['time'] for s in steps)-total)>.1:
        return []
    return steps


def planned_score(session):
    minutes = session.get('minutes')
    if session.get('sport') not in SPORTS or not number(minutes):
        return dict(stress=None, low=None, high=None, method='excluded', confidence='unavailable')
    optional = session.get('optional') or session.get('isOptional') or session.get('priority') == 'optional'
    base = session.get('baseMinutes', 0 if optional else minutes)
    if not number(base,True):
        base = minutes
    base = min(base, minutes)
    exponent = 3 if session['sport'] == 'Swim' else 2
    def dose(steps, total, fallback):
        if not steps:
            return total/60 * 100 * fallback**exponent
        used = result = 0
        for step in steps:
            amount = step.get('time')
            if not number(amount):
                continue
            amount = min(amount, total-used)
            level = step.get('level')
            intensity = level/100 if session['sport']=='Bike' and number(level) else planning_if(step.get('label',''),step.get('kind'))
            result += amount * intensity**exponent
            used += amount
            if used >= total:
                break
        return (result + (total-used)*fallback**exponent)*100/60
    steps = prescription_steps(session)
    # Intensity in the title describes the main set, not the entire workout.
    fallback = .67 if re.search('easy|recovery',session.get('title',''),re.I) else .72
    low = dose(steps,base,fallback)
    high = dose(session.get('optionalSteps') or steps,minutes,fallback)
    if not session.get('optionalSteps') and 'optional' in session.get('details','').lower():
        match = re.search(r'optional:\s*[^.]*?([\d.]+)\s*min\s+steady', session['details'], re.I)
        if match and steps:
            high += min(float(match[1]),minutes)/60*100*(.83**exponent-.67**exponent)
    return dict(stress=round(low,2),low=round(low,2),high=round(max(low,high),2),
                method='Prescribed steps' if steps else 'Duration and effort prior',confidence='estimated' if steps else 'low')


def coverage_ok(day, intervals):
    return any(r.get('start','~') <= day <= r.get('end','') for r in intervals)


def pmc_series(sport, sessions, activities, scores, plans, start, end, today, coverage):
    def accepts(x):
        return x['sport'] in SPORTS and (sport == 'All' or x['sport'] == sport)
    actual = defaultdict(list)
    planned = defaultdict(list)
    for a in activities:
        if accepts(a):
            actual[a['date']].append(scores[a['id']]['stress'])
    for s in sessions:
        if accepts(s):
            planned[s['date']].append(plans[s['id']])
    beginning = min([start]+list(actual))
    day = date.fromisoformat(beginning)
    last = date.fromisoformat(max(end,today))
    smooth = {}
    decay = (exp(-1/42),exp(-1/7))
    known_days = 0
    scored_sessions = 0
    result = []
    def update(name, load, quality):
        ctl,atl = smooth.get(name,(0,0))
        next_ctl,next_atl = (ctl*decay[0]+load*(1-decay[0]),atl*decay[1]+load*(1-decay[1]))
        smooth[name] = (next_ctl,next_atl)
        return dict(ctl=round(next_ctl,2),atl=round(next_atl,2),tsb=round(ctl-atl,2),
                    stress=round(load,2),quality=quality)
    while day<=last:
        d=day.isoformat()
        row=dict(date=d,actual=None,planned=None,forecast=None,forecastHigh=None)
        # Start the plan at the state on the day before plan start. Never use later actuals for this line.
        if d == start:
            smooth['planned']=smooth.get('actual',(0,0))
        if d <= today:
            loads=actual[d]
            measured_count=sum(x is not None for x in loads)
            scored_sessions+=measured_count
            complete=coverage_ok(d,coverage) and measured_count==len(loads)
            known_days=known_days+1 if complete else 0
            row['actual']=update('actual',sum(x for x in loads if x is not None),
                                 'modeled' if known_days>=42 else 'partial coverage / lower-bound load')
            if not scored_sessions:
                row['actual']=None
            else:
                row['actual'].update(scoredSessions=measured_count,recordedSessions=len(loads))
        if d==today:
            smooth['forecast']=smooth['forecastHigh']=smooth.get('actual',(0,0))
        if start<=d<=end:
            low=sum(v['low'] or 0 for v in planned[d])
            high=sum(v['high'] or 0 for v in planned[d])
            row['planned']=update('planned',low,'planned estimate')
            if d>today and scored_sessions:
                row['forecast']=update('forecast',low,'forecast from actual load')
                row['forecastHigh']=update('forecastHigh',high,'including optional work')
        result.append(row)
        day+=timedelta(days=1)
    return result


def grade_speed(activity, samples):
    """Approximate mild-road-grade equivalent using published Minetti running cost vs level cost.

    Use long spans (at least 100 m) to suppress altitude noise. Omit pauses, steep
    sections, GPS jumps and incomplete traces rather than imputing their energy cost.
    """
    previous = anchor = None
    distance = seconds = 0.
    for point in samples:
        t,d,h = (point.get(k) for k in ('elapsedSeconds','distanceMeters','altitudeMeters'))
        if not number(t,True) or not number(d,True) or not isinstance(h,(int,float)) or not isfinite(h):
            previous=anchor=None
            continue
        if previous is None or not 0<t-previous[0]<=10 or d<previous[1]:
            anchor=(t,d,h)
        previous=(t,d)
        elapsed,span=t-anchor[0],d-anchor[1]
        if span<100:
            continue
        g=(h-anchor[2])/span
        if abs(g)<=.15 and 1.0<=span/elapsed<=8.0:
            cost=155.4*g**5-30.4*g**4-43.3*g**3+46.3*g**2+19.5*g+3.6
            distance+=span*cost/3.6
            seconds+=elapsed
        anchor=(t,d,h)
    duration=activity.get('durationSeconds')
    if number(duration) and duration*.9<=seconds<=duration*1.1:
        return distance/seconds
    return None


def best_power(samples, window):
    """Highest complete time-weighted window; never bridge recording gaps."""
    history=deque()
    area=0.
    previous=None
    best=None
    for start,end,watts in segments(samples,'power'):
        if previous!=start:
            history.clear()
            area=0.
        history.append((start,end,watts))
        area+=(end-start)*watts
        limit=end-window
        while history and history[0][1]<=limit:
            a,b,v=history.popleft()
            area-=(b-a)*v
        if history and history[0][0]<=limit:
            a,b,v=history[0]
            candidate=(area-(limit-a)*v)/window
            best=candidate if best is None else max(best,candidate)
        previous=end
    return best


def best_run(samples, target):
    history=deque()
    best=None
    for point in samples:
        t,d=point.get('elapsedSeconds'),point.get('distanceMeters')
        if not number(t,True) or not number(d,True):
            history.clear()
            continue
        if history:
            dt=t-history[-1][0]
            dd=d-history[-1][1]
            if not 0<dt<=10 or not 0<=dd<=dt*10:
                history.clear()
        history.append((t,d))
        while len(history)>1 and history[1][1]<=d-target:
            history.popleft()
        if len(history)>1 and history[0][1]<=d-target:
            ta,da=history[0]
            tb,db=history[1]
            if db>da:
                start=ta+(d-target-da)/(db-da)*(tb-ta)
                candidate=t-start
                best=candidate if best is None else min(best,candidate)
    return best


def benchmarks_and_records(activities, details):
    bench,records,bests=[],[],{}
    def record(a,name,value,unit,direction):
        if not number(value):
            return
        key=(a['sport'],name)
        if key not in bests or (value-bests[key])*direction>0:
            bests[key]=value
            records.append(dict(activityId=a['id'],date=a['date'],sport=a['sport'],
                                metric=name,value=round(value,2),unit=unit))
    for a in sorted(activities,key=lambda x:(x['date'],x.get('startTime') or '',x['id'])):
        sport=a.get('sport')
        if sport not in SPORTS:
            continue
        detail=details.get(a['id'],{})
        samples=detail.get('samples',[])
        record(a,'Longest recorded distance',a.get('distanceMeters'),'m',1)
        record(a,'Longest recorded duration',a.get('durationSeconds'),'s',1)
        if sport=='Bike':
            for minutes in (5,20,60):
                record(a,f'Best {minutes}-min power',best_power(samples,minutes*60),'W',1)
        if sport=='Run':
            for meters in (1000,5000,10000):
                record(a,f'Best {meters//1000} km',best_run(samples,meters),'s',-1)
        def add(metric,value,unit,group,confidence='estimated'):
            bench.append(dict(activityId=a['id'],sport=sport,date=a['date'],metric=metric,
                              value=round(value,2),unit=unit,context=group,
                              series=f'{sport} · {metric} · {group}',confidence=confidence))
        if sport=='Swim':
            for lap in detail.get('laps',[]):
                d,sec=lap.get('distanceMeters'),lap.get('durationSeconds')
                if number(d) and number(sec):
                    pool=a.get('poolLengthMeters') or detail.get('poolLengthMeters')
                    group=f'{round(d)} m repeat · '+(f'{pool:g} m pool' if number(pool) else 'pool length unverified')
                    add('Swim repeat pace',sec/d*100,'s/100m',group)
            continue
        key='power' if sport=='Bike' else 'speed'
        duration=a.get('durationSeconds',0)
        if not number(duration) or duration<1800 or not samples:
            continue
        def steady_window(start_at,end_at):
            stats=[0.,0.,0.,0.]
            for first,second in zip(samples,samples[1:]):
                start,end,val,hr=first.get('elapsedSeconds'),second.get('elapsedSeconds'),first.get(key),first.get('hr')
                if not number(start,True) or not number(end) or not 0<end-start<=10 or not number(val,key=='power') or not number(hr):
                    continue
                elapsed=max(0,min(end_at,end)-max(start_at,start))
                stats[0]+=elapsed
                stats[1]+=val*elapsed
                stats[2]+=hr*elapsed
                stats[3]+=val*val*elapsed
            return stats

        def steady(stats,expected):
            seconds,work,_,squares=stats
            return seconds>=.9*expected and work>0 and (max(0,squares/seconds-(work/seconds)**2)**.5)/(work/seconds)<=.15

        # Decoupling requires a steady central span through both halves.
        cutoff=duration-300
        middle=(600+cutoff)/2
        first,second=steady_window(600,middle),steady_window(middle,cutoff)
        full=list(map(sum,zip(first,second)))
        context=a.get('benchmarkRoute') or a.get('terrain') or detail.get('subSport') or 'route/conditions unverified'
        if sport=='Bike' and steady(full,cutoff-600) and steady(first,middle-600) and steady(second,cutoff-middle):
            rr=first[1]/first[2]
            add('Aerobic decoupling',100*(1-(second[1]/second[2])/rr),'%',context)
            selected=full
            window_label='steady central section'
        else:
            # Comparable 10-minute segments still have value on variable sessions.
            # Use the first steady segment after warm-up to avoid selecting peak efforts.
            selected=next((x for x in (steady_window(start,start+600) for start in range(600,round(cutoff)-599,600)) if steady(x,600)),None)
            window_label='10-min steady segment'
        if selected:
            seconds,work,beats,_=selected
            hr=beats/seconds
            hr_band=f'{5*int(hr//5)}–{5*int(hr//5)+4} bpm · {context} · {window_label}'
            if sport=='Run':
                add('Steady pace at HR',1000/(work/seconds),'s/km',hr_band)
            else:
                add('Steady power at HR',work/seconds,'W',hr_band)
    return bench,records


def interval_view(session, ids, activities, details):
    steps=prescription_steps(session)
    laps=[]
    for ident in ids:
        for lap in details.get(ident,{}).get('laps',[]):
            laps.append(dict(lap,activityId=ident))
    result=dict(prescription=session.get('details',''), plannedSteps=steps,
                actualLaps=laps, alignment='Recorded laps and prescribed steps shown independently.')
    if not steps or len(steps)!=len(laps):
        return result
    # Do not infer rep alignment from count alone; check every boundary against its prescription.
    for step,lap in zip(steps,laps):
        target=step.get('time')
        seconds=lap.get('durationSeconds')
        if not number(target) or not number(seconds) or abs(seconds-target*60)>max(5,target*60*.10):
            return result
    result['alignment']='Comparable lap durations; review effort and recovery for each step.'
    result['repComparisons']=[dict(label=s.get('label',''),plannedSeconds=s['time']*60,
                                   actualSeconds=l['durationSeconds'],averageHr=l.get('averageHr'),
                                   averagePower=l.get('averagePower'),distanceMeters=l.get('distanceMeters'))
                              for s,l in zip(steps,laps)]
    return result


def metrics_report(state, activities, thresholds=None, as_of=None, match_map=None, coverage=None, details=None, comparison_as_of=None):
    """Read-only reproducible load, execution and improvement measures for a plan snapshot."""
    if as_of is None:
        as_of=datetime.now(ZoneInfo(state.get('timezone','UTC'))).date().isoformat()
    if not date_string(as_of):
        raise ValueError('as_of must be a calendar date')
    thresholds=thresholds if thresholds is not None else state.get('athlete',{}).get('thresholds',[])
    details=details or {}
    rows=[a for a in activities if a.get('id') and date_string(a.get('date')) and a['date']<=as_of]
    sessions=[s for s in state.get('sessions',[]) if s.get('id') and date_string(s.get('date'))]
    goal=state.get('goal',{})
    start=goal.get('startDate') or min((s['date'] for s in sessions),default=as_of)
    end=goal.get('raceDate') or goal.get('endDate') or max((s['date'] for s in sessions),default=as_of)
    scores={a['id']:score_activity(a,thresholds,details.get(a['id'])) for a in rows}
    plans={s['id']:planned_score(s) for s in sessions}
    series={sport:pmc_series(sport,sessions,rows,scores,plans,start,end,as_of,coverage or [])
            for sport in ('All',)+SPORTS}
    benchmarks,records=benchmarks_and_records(rows,details)
    intervals={}
    for s in sessions:
        ids=(match_map or {}).get(s['id'],[])
        if isinstance(ids,str):
            ids=[ids]
        if isinstance(ids,dict):
            ids=ids.get('activityIds',[])
        if ids:
            intervals[s['id']]=interval_view(s,ids,rows,details)
    return dict(model=MODEL,asOf=as_of,thresholds=thresholds,scores=scores,plannedScores=plans,
                pmc=series,benchmarks=benchmarks,records=records,intervals=intervals,
                historyComparison=history_comparison(state,rows,coverage or [],comparison_as_of or as_of),
                raceEstimate=race_estimate(state,rows,as_of,match_map or {},details,intervals),
                modelNotes=['Load uses date-effective, sport-specific thresholds. Missing values remain unscored.',
                            'CTL and ATL use exponential time constants of 42 and 7 days; form uses prior-day values.',
                            'Partial-coverage and zero-initialized curves model observed load only; a zero floor is not evidence of rest.',
                            'Relative-HR, grade-cost and swim estimates are local models, not proprietary score reproductions.',
                            'Benchmarks require comparable terrain, sensors, conditions and protocol.'])
