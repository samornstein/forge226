"""Evidence summaries. Calculations describe records, never predict fitness or injury."""
from datetime import date, datetime, timedelta
from collections import defaultdict, Counter
import math


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def duplicates(rows):
    candidates, excluded = [], set()
    rows = sorted(rows, key=lambda r: (r['startTime'], r['source'], r['sourceId']))
    for i, r in enumerate(rows):
        if r['id'] in excluded:
            continue
        for x in rows[i + 1:]:
            if r['source'] == x['source'] or r['sport'] != x['sport'] or x['id'] in excluded:
                continue
            dt = abs((datetime.fromisoformat(r['startTime']) - datetime.fromisoformat(x['startTime'])).total_seconds())
            a, b = r.get('distanceMeters'), x.get('distanceMeters')
            longest = max(r['durationSeconds'], x['durationSeconds'])
            if dt <= 120 and longest > 0 and abs(r['durationSeconds'] - x['durationSeconds']) / longest <= .03 and a is not None and b is not None and max(a, b) > 0 and abs(a - b) / max(a, b) <= .03:
                candidates.append({'keptForSummary': r['id'], 'excludedFromSummary': x['id'], 'reason': 'Possible cross-source duplicate; provisional totals only, originals retained.'})
                excluded.add(x['id'])
    return [r for r in rows if r['id'] not in excluded], candidates


def summarize(rows, as_of, coverage=None):
    end = date.fromisoformat(as_of)
    begin = end - timedelta(days=83)
    rows = [r for r in rows if begin <= date.fromisoformat(r['date']) <= end]
    clean, candidates = duplicates(rows)
    weekly = defaultdict(list)
    sports = defaultdict(lambda: {'sessions': 0, 'hours': 0, 'longestMinutes': 0})
    for r in clean:
        d = date.fromisoformat(r['date'])
        weekly[d - timedelta(days=d.weekday())].append(r)
        a = sports[r['sport']]
        a['sessions'] += 1
        a['hours'] += r['durationSeconds'] / 3600
        a['longestMinutes'] = max(a['longestMinutes'], r['durationSeconds'] / 60)
    # Coverage is an explicit assertion about ALL workouts/rest, never inferred from a sync.
    confirmed = set()
    for item in coverage or []:
        if item.get('complete') is not True or not item.get('basis'):
            continue
        a, b = date.fromisoformat(item['startDate']), date.fromisoformat(item['endDate'])
        if b < a:
            raise ValueError('Coverage end precedes start')
        a, b = max(a, begin), min(b, end)
        confirmed.update(a + timedelta(days=i) for i in range(max(0, (b-a).days+1)))
    weeks = []
    w = begin - timedelta(days=begin.weekday())
    while w <= end:
        group = weekly[w]
        bysport = defaultdict(float)
        counts = Counter()
        for r in group:
            bysport[r['sport']] += r['durationSeconds'] / 3600
            counts[r['sport']] += 1
        full = all(w + timedelta(days=i) in confirmed for i in range(7))
        partial = w < begin or w + timedelta(days=6) > end
        hours = sum(bysport.values())
        weeks.append({'weekStart': w.isoformat(), 'observedHours': round(hours, 2),
                      'hours': round(hours, 2) if group or full else None,
                      'sessions': len(group), 'bySport': {s: round(h, 2) for s, h in bysport.items()},
                      'frequencyBySport': dict(counts), 'partial': partial,
                      'coverage': 'confirmed-complete' if full and not partial else 'unknown'})
        w += timedelta(days=7)
    # Use eight COMPLETED Monday-Sunday weeks, excluding the current week.
    last_end = end - timedelta(days=end.weekday() + 1)
    def period(a, b):
        subset = [r for r in clean if a.isoformat() <= r['date'] <= b.isoformat()]
        confirmed_period = all(a + timedelta(days=i) in confirmed for i in range((b-a).days+1))
        bysport = {}
        for sport in sorted({r['sport'] for r in clean}):
            selected = [r for r in subset if r['sport'] == sport]
            bysport[sport] = {'observedHours': round(sum(r['durationSeconds'] for r in selected)/3600, 2),
                             'sessions': len(selected), 'longestMinutes': max((r['durationSeconds']/60 for r in selected), default=None),
                             'sessionsPerWeek': len(selected)/4 if confirmed_period else None}
        return {'startDate': a.isoformat(), 'endDate': b.isoformat(), 'coverageComplete': confirmed_period,
                'observedHours': round(sum(r['durationSeconds'] for r in subset)/3600, 2), 'bySport': bysport}
    recent = period(last_end-timedelta(days=27), last_end)
    prior = period(last_end-timedelta(days=55), last_end-timedelta(days=28))
    comparable = recent['coverageComplete'] and prior['coverageComplete'] and not candidates
    delta = recent['observedHours'] - prior['observedHours'] if comparable else None
    return {'asOf': as_of, 'windowDays': 84, 'activityCount': len(clean),
            'duplicateCandidates': candidates, 'totalsProvisional': bool(candidates), 'weekly': weeks, 'bySport': dict(sports),
            'comparison': {'recentFourCompletedWeeks': recent, 'previousFourCompletedWeeks': prior,
                           'comparable': comparable, 'hoursChange': round(delta, 2) if delta is not None else None,
                           'percentChange': round(delta/prior['observedHours']*100, 1) if comparable and prior['observedHours'] > 0 else None,
                           'reason': 'Descriptive volume comparison, not a progression prescription.' if comparable else 'Confirm complete history/rest and resolve duplicate candidates before interpreting a trend.'},
            'coverageWarning': 'Observed totals only. Empty weeks are unknown unless all training/rest is confirmed. No mixed-scale load, readiness or qualification score.'}


def benchmark_history(profile, as_of):
    """Keep incompatible methods/conditions separate; never infer improvement direction."""
    entries = profile.get('benchmarks', [])
    groups, unverified = defaultdict(list), []
    for item in entries:
        try:
            d = date.fromisoformat(item['date'])
            if not finite(item['value']) or not all(item.get(k) for k in ('sport', 'metric', 'units', 'method', 'source', 'conditions')):
                raise ValueError('Incomplete benchmark')
            if d > date.fromisoformat(as_of):
                raise ValueError('Future benchmark')
        except (KeyError, ValueError, TypeError):
            unverified.append(item)
            continue
        key = tuple(str(item[k]) for k in ('sport', 'metric', 'units', 'method', 'conditions'))
        groups[key].append(item)
    output = []
    for key, items in sorted(groups.items()):
        items = sorted(items, key=lambda x: x['date'])
        latest = items[-1]
        prior = next((x for x in reversed(items[:-1]) if x['date'] < latest['date']), None)
        output.append({'sport': key[0], 'metric': key[1], 'units': key[2], 'method': key[3], 'conditions': key[4],
                       'history': items, 'latestDate': latest['date'],
                       'ageDays': (date.fromisoformat(as_of)-date.fromisoformat(latest['date'])).days,
                       'change': round(latest['value']-prior['value'], 3) if prior else None})
    return {'series': output, 'unverified': unverified, 'note': 'Changes compare the same named method, units and conditions only. Relevance and improvement require coaching interpretation.'}


def adherence(sessions, activities, outcomes, as_of, from_date=None):
    """Offer unique candidates without declaring device evidence athlete-confirmed."""
    end = date.fromisoformat(as_of)
    begin = date.fromisoformat(from_date) if from_date else end-timedelta(days=6)
    if begin > end:
        raise ValueError('Review start must not follow as_of')
    selected = [s for s in sessions if begin.isoformat() <= s['date'] <= as_of and s['sport'] not in ('Rest', 'Race')]
    actual = {r['id']: r for r in activities if r['date'] <= as_of}
    reports = {x['sessionId']: x for x in outcomes or [] if x.get('confirmed') is True}
    used = set()
    for s in selected:
        report = reports.get(s['id'], {})
        used.update(report.get('activityIds', []))
    candidates = {}
    for s in selected:
        if s['id'] in reports:
            continue
        candidates[s['id']] = [r for r in actual.values() if r['id'] not in used and r['date'] == s['date'] and r['sport'].lower() == s['sport'].lower() and abs(r['durationSeconds']/60-s['minutes']) <= max(15, s['minutes']*.5)]
    claims = Counter(r['id'] for group in candidates.values() for r in group)
    result = []
    for s in selected:
        report = reports.get(s['id'])
        row = {'sessionId': s['id'], 'date': s['date'], 'sport': s['sport'], 'plannedMinutes': s['minutes'], 'status': 'unknown', 'actualMinutes': None}
        if report:
            ids = report.get('activityIds', [])
            row.update(status=report['status'], evidence=report.get('basis'), activityIds=ids)
            if ids and all(x in actual for x in ids):
                row['actualMinutes'] = round(sum(actual[x]['durationSeconds'] for x in ids)/60, 2)
            elif finite(report.get('actualMinutes')):
                row['actualMinutes'] = report['actualMinutes']
            if ids and not all(x in actual for x in ids):
                row['evidenceWarning'] = 'Some linked activities are unavailable or their source is disabled.'
        else:
            options = candidates.get(s['id'], [])
            row['candidateActivityIds'] = [r['id'] for r in options]
            if len(options) == 1 and claims[options[0]['id']] == 1:
                minutes = options[0]['durationSeconds']/60
                row['suggestedStatus'] = 'shortened' if minutes < s['minutes']*.9 else 'extended' if minutes > s['minutes']*1.1 else 'completed'
                row['candidateMinutes'] = round(minutes, 2)
                row['matchBasis'] = 'Unique same-day/sport/duration candidate; confirm session intent and execution.'
        result.append(row)
    bysport = {}
    for sport in sorted({x['sport'] for x in result}):
        group = [x for x in result if x['sport'] == sport]
        bysport[sport] = {'plannedMinutes': sum(x['plannedMinutes'] for x in group),
                         'confirmedActualMinutes': sum(x['actualMinutes'] for x in group if x['actualMinutes'] is not None),
                         'unknownSessions': sum(x['status'] == 'unknown' for x in group)}
    return {'fromDate': begin.isoformat(), 'throughDate': as_of, 'sessions': result, 'bySport': bysport,
            'statusCounts': dict(Counter(x['status'] for x in result)),
            'note': 'No imported match means unknown, never automatically missed. Candidate matches are not confirmed completion; no automatic intensity/execution assessment.'}


def history_summary(rows, from_date=None, to_date=None):
    """Whole-history descriptive evidence, not a capacity/fitness prediction."""
    end=date.fromisoformat(to_date) if to_date else date.today()
    begin=date.fromisoformat(from_date) if from_date else min((date.fromisoformat(r['date']) for r in rows),default=end)
    if begin>end:raise ValueError('History start must not follow end')
    clean,candidates=duplicates([r for r in rows if begin.isoformat()<=r['date']<=end.isoformat()])
    groups=defaultdict(list)
    for r in clean:
        d=date.fromisoformat(r['date']);groups[d-timedelta(days=d.weekday())].append(r)
    weeks=[]
    for w,group in sorted(groups.items()):
        daily=defaultdict(lambda:defaultdict(float));sportdays=defaultdict(set);sporthours=defaultdict(float)
        for r in group:
            daily[r['date']][r['sport']]+=r['durationSeconds']/60
            sportdays[r['sport']].add(r['date']);sporthours[r['sport']]+=r['durationSeconds']/3600
        flags=[r['id'] for r in group if any(t in r.get('name','').lower() for t in ('ironman','race','marathon','70.3','triathlon'))]
        weeks.append({'weekStart':w.isoformat(),'observedHours':round(sum(r['durationSeconds'] for r in group)/3600,2),
                      'recordCount':len(group),'trainingDays':len(daily),'trainingDaysBySport':{k:len(v) for k,v in sportdays.items()},
                      'hoursBySport':{k:round(v,2) for k,v in sporthours.items()},
                      'days':[{'date':d,'weekday':date.fromisoformat(d).strftime('%A'),'minutesBySport':{k:round(v,1) for k,v in sp.items()}} for d,sp in sorted(daily.items())],
                      'possibleRaceActivityIds':flags,'raceClassification':'name-based candidates only; verify event dates and purpose',
                      'partial':w<begin or w+timedelta(days=6)>end,'coverage':'observed-only; unrecorded days unknown'})
    full=[w for w in weeks if not w['partial']]
    return {'fromDate':begin.isoformat(),'throughDate':end.isoformat(),'activityCount':len(clean),'observedWeeks':weeks,
            'highestObservedWeeks':sorted(full,key=lambda w:w['observedHours'],reverse=True)[:12],
            'duplicateCandidates':candidates,'totalsProvisional':bool(candidates),
            'note':'Compare recent re-entry with repeated historical blocks and weekday patterns. Files are not sessions: warm-up/cooldown splits can inflate record counts. Possible race weeks are not peak training evidence until reviewed. No record is not proof of rest; prior volume is not current readiness.'}
