"""Structural/scheduling validation, not a medical or coaching assessment."""
import json, math, sys
from collections import defaultdict
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from coaching_check import validate_coaching
DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
def number(n):
    return isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n) and n >= 0
def validate(s):
    errors=[]
    def fail(message): errors.append(message)
    if s.get('schemaVersion') != 1: fail('Unsupported schemaVersion')
    if not isinstance(s.get('version'),int) or isinstance(s.get('version'),bool) or s['version']<1: fail('Invalid version')
    if s.get('status') not in ('draft','active'): fail('Invalid status')
    try: ZoneInfo(s['timezone'])
    except (KeyError,ValueError,TypeError): fail('Invalid timezone')
    def parse(v):
        d=date.fromisoformat(v)
        if d.isoformat()!=v: raise ValueError('Use YYYY-MM-DD')
        return d
    try:
        goal=s['goal']; start=parse(goal['startDate']); end=parse(goal['endDate'])
        race=parse(goal['raceDate']) if goal.get('raceDate') else None
        if end<start or (end-start).days>1095: raise ValueError('Invalid or excessive horizon')
        if race and race!=end: fail('Pre-race horizon must end on race date')
    except (KeyError,TypeError,ValueError) as e:
        return {'passed':False,'errors':errors+['Invalid goal dates: '+str(e)]}
    def capacity(slot,label):
        if not isinstance(slot,dict): fail('Missing slot '+label); return 0
        if slot.get('enabled') is False: return 0
        if slot.get('enabled') is not True or not number(slot.get('minutes')) or slot.get('minutes',0)<=0:
            fail('Unresolved/invalid availability '+label); return 0
        return slot['minutes']
    avail=s.get('availability',{}); base={}
    for day in DAYS:
        for slot in ('AM','PM'): base[day,slot]=capacity(avail.get(day,{}).get(slot),day+' '+slot)
    cap=s.get('weeklyCapMinutes')
    if cap is not None and not number(cap): fail('Invalid weekly cap'); cap=None
    exmap={}; dailycaps={}; allowed_sports={}
    for ex in s.get('exceptions',[]):
        try:
            a,b=parse(ex['startDate']),parse(ex['endDate'])
            if b<a or (b-a).days>1095: raise ValueError('Invalid range')
            slots=ex['slots']
            if not isinstance(slots,dict) or any(k not in ('AM','PM') for k in slots): raise ValueError('Invalid exception slots')
            overrides={k:capacity(v,'exception '+a.isoformat()+' '+k) for k,v in slots.items()}
            for i in range((b-a).days+1):
                d=a+timedelta(days=i)
                if d in exmap: fail('Overlapping exceptions '+d.isoformat())
                exmap[d]=overrides
                if 'maxMinutesPerDay' in ex:
                    if not number(ex['maxMinutesPerDay']): fail('Invalid daily cap '+d.isoformat())
                    else: dailycaps[d]=ex['maxMinutesPerDay']
                if 'allowedSports' in ex:
                    allowed=ex['allowedSports']
                    if not isinstance(allowed,list) or any(v not in ('Swim','Bike','Run','Strength','Other','Rest','Race') for v in allowed): fail('Invalid allowed sports '+d.isoformat())
                    else: allowed_sports[d]=set(allowed)
        except (KeyError,TypeError,ValueError) as e: fail('Invalid exception: '+str(e))
    ids=set(); covered=set(); slotsum=defaultdict(float); weeks=defaultdict(float); race_total=0; race_entries=0
    rests=set(); trained=set(); dailyminutes=defaultdict(float)
    for row in s.get('sessions',[]):
        try:
            ident=row['id']; d=parse(row['date']); slot=row['slot']; sport=row['sport']; minutes=row['minutes']
            if not isinstance(ident,str) or not ident or ident in ids: fail('Duplicate/invalid session ID '+str(ident))
            ids.add(ident)
            if d<start or d>end: fail('Session outside horizon '+str(ident))
            covered.add(d)
            if d in allowed_sports and sport not in allowed_sports[d] and sport!='Rest': fail('Sport unavailable during exception '+str(ident))
            if not number(minutes): fail('Invalid minutes '+str(ident)); continue
            if sport!='Rest': dailyminutes[d]+=minutes
            for field in ('title','intensity','details','purpose'):
                if not isinstance(row.get(field),str) or not row[field].strip(): fail('Missing '+field+' '+str(ident))
            if sport not in ('Swim','Bike','Run','Strength','Other','Rest','Race'): fail('Invalid sport '+str(ident))
            if slot=='Rest' or sport=='Rest':
                if slot!='Rest' or sport!='Rest' or minutes!=0: fail('Invalid rest '+str(ident))
                rests.add(d)
            elif slot=='Race' or sport=='Race':
                if slot!='Race' or sport!='Race' or d!=race or minutes<=0: fail('Invalid race entry '+str(ident))
                if exmap.get(d)=={'AM':0,'PM':0}: fail('Race conflicts with unavailable exception')
                race_total+=minutes; race_entries+=1; trained.add(d)
            elif slot in ('AM','PM'):
                if minutes<=0: fail('Training must have positive minutes '+str(ident))
                slotsum[d,slot]+=minutes; trained.add(d)
                weeks[d-timedelta(days=d.weekday())]+=minutes
            else: fail('Invalid slot '+str(ident))
        except (KeyError,TypeError,ValueError) as e: fail('Malformed session: '+str(e))
    for d,minutes in dailyminutes.items():
        if d in dailycaps and minutes>dailycaps[d]: fail(f'{d}: {minutes:g} minutes exceeds daily cap {dailycaps[d]:g}')
    for d in rests & trained: fail('Rest and training conflict '+d.isoformat())
    if race and race_entries!=1: fail('Exactly one race entry required')
    for i in range((end-start).days+1):
        d=start+timedelta(days=i)
        if d not in covered: fail('Missing calendar date '+d.isoformat())
    for (d,slot),minutes in slotsum.items():
        limit=exmap.get(d,{}).get(slot,base[DAYS[d.weekday()],slot])
        if minutes>limit: fail(f'{d} {slot}: {minutes:g} minutes exceeds {limit:g}')
    for week,minutes in weeks.items():
        capacity_week=0
        for i in range(7):
            d=week+timedelta(days=i)
            if start<=d<=end:
                capacity_week+=sum(exmap.get(d,{}).get(slot,base[DAYS[d.weekday()],slot]) for slot in ('AM','PM'))
        limit=min(capacity_week,cap) if cap is not None else capacity_week
        if minutes>limit: fail(f'Week {week}: {minutes:g} exceeds cap {limit:g}')
    errors.extend(validate_coaching(s))
    return {'passed':not errors,'errors':errors,'weeklyTrainingMinutes':{str(k):v for k,v in sorted(weeks.items())},'raceMinutes':race_total,'scope':'Structural and time constraints only; coaching review required.'}
if __name__=='__main__':
    try:
        result=validate(json.load(open(sys.argv[1])))
    except (OSError,ValueError,KeyError,TypeError,IndexError) as e:
        result={'passed':False,'errors':[str(e)]}
    print(json.dumps(result,indent=2)); sys.exit(0 if result['passed'] else 1)
