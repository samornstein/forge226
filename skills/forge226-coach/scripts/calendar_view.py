"""Render the same plan calendar for private review and plan-only hosting."""
import html
import json
from pathlib import Path
from plan_workflow import normalize, schedule_key

SCRIPTS = Path(__file__).parent
SESSION_FIELDS = ('id','date','slot','sport','title','minutes','baseMinutes','blockId',
                  'provisional','details','intensity','purpose','successCue','alternative',
                  'distanceYards','progressionFocus','progressionNote','profileSteps','optionalSteps')


def calendar_html(state):
    state = normalize(state)
    data = {key:state.get(key) for key in ('timeAccounting','version','status','timezone',
           'weeklyCapMinutes','sportAccess')}
    def slots(mapping):
        return {k:{f:v[f] for f in ('enabled','minutes') if f in v} for k,v in mapping.items() if k in ('AM','PM')}
    data['timeAccounting'] = {'excludedSports':(state.get('timeAccounting') or {}).get('excludedSports',[])}
    data['availability'] = {k:slots(v) for k,v in state.get('availability',{}).items()}
    def select(row, keys):
        return {k:row[k] for k in keys if k in row}
    data['scheduleKey'] = schedule_key(state)
    data['goal'] = select(state['goal'], ('name','startDate','endDate','raceDate'))
    data['sessions'] = [select(row, SESSION_FIELDS) for row in state['sessions']]
    for row, source in zip(data['sessions'],state['sessions']):
        if 'workout' in source:
            row['structured'] = True
        for field in ('profileSteps','optionalSteps'):
            if field in row:
                row[field] = [select(step,('label','time','kind','target','distance','unit','intensityPct')) for step in row[field]]
    data['trainingBlocks'] = [select(b, ('id','startDate','endDate','focus','rationale','progressIf','repeatIf','reduceIf')) for b in state.get('trainingBlocks',[])]
    for block, source in zip(data['trainingBlocks'],state.get('trainingBlocks',[])):
        block['checkpoints'] = [select(c,('date','measure','criterion','status')) for c in source.get('checkpoints',[])]
    data['exceptions'] = [select(e, ('startDate','endDate','slots','allowedSports','maxMinutesPerDay')) for e in state.get('exceptions',[])]
    for exception in data['exceptions']:
        exception['slots'] = slots(exception.get('slots',{}))
    encoded = json.dumps(data,ensure_ascii=True).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return (SCRIPTS/'calendar.html').read_text().replace('__EXPORT_SCRIPT__',(SCRIPTS/'plan_export.js').read_text()).replace('__WORKFLOW__',(SCRIPTS/'plan_calendar.js').read_text()).replace('__CALENDAR_DATA__',encoded)


def share_html(state):
    title = html.escape(state['goal']['name'])
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>'+title+'</title><style>body{font:16px system-ui;max-width:1400px;margin:auto;padding:16px;color:#22352b}button,input,select{font:inherit;padding:6px}#fc .grid,#fc .week{overflow:auto}dialog{max-width:min(94vw,640px)}</style><main><h1>'+title+'</h1>'+calendar_html(state)+'</main></html>')
