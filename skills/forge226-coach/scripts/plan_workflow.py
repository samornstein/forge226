"""Normalize structured plan prescriptions at the save boundary."""
from copy import deepcopy
from datetime import date
from math import isfinite
import hashlib
import json


def expand_steps(nodes, sport):
    steps = []
    def visit(items, depth):
        if not isinstance(items, list) or depth > 4:
            raise ValueError('Invalid workout step list or repeat depth')
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('Invalid workout step')
            if item.get('sport', sport) != sport:
                raise ValueError('Workout step belongs to another sport')
            if 'repeat' in item:
                count = item['repeat']
                if type(count) is not int or not 1 <= count <= 100 or not item.get('steps'):
                    raise ValueError('Invalid workout repeat')
                for _ in range(count):
                    visit(item['steps'], depth + 1)
            else:
                if len(steps) >= 1000:
                    raise ValueError('Too many workout steps')
                duration = item.get('time')
                if type(duration) not in (int, float) or not isfinite(duration) or duration <= 0 or not isinstance(item.get('label'), str) or not item['label'].strip():
                    raise ValueError('Each workout step needs a label and positive minutes')
                if 'distance' in item or 'unit' in item:
                    distance = item.get('distance')
                    if type(distance) not in (float, int) or not isfinite(distance) or distance <= 0 or item.get('unit') not in ('yd','m','km','mi'):
                        raise ValueError('Step distance needs a positive value and unit')
                value = item.get('intensityPct')
                if value is not None and (type(value) not in (int,float) or not isfinite(value) or value <= 0):
                    raise ValueError('intensityPct must be a positive percentage')
                steps.append(item.copy())
    visit(nodes, 0)
    return steps


def describe(step):
    distance = f" · {step['distance']} {step['unit']}" if 'distance' in step else ''
    target = ' · ' + str(step['target']) if step.get('target') else ''
    return f"{step['label']}{distance} · {step['time']:g} min{target}"


def normalize(state):
    state = deepcopy(state)
    for row in state.get('sessions', []):
        workout = row.get('workout')
        if workout is None:
            continue
        if not isinstance(workout, dict) or workout.get('sport') != row.get('sport'):
            raise ValueError('Structured workout sport differs from scheduled sport')
        base = expand_steps(workout.get('steps'), row['sport'])
        row['profileSteps'] = base
        row['details'] = '\n'.join(map(describe, base)) or 'Optional session'
        row.pop('optionalSteps', None)
        if 'optionalSteps' in workout:
            row['optionalSteps'] = expand_steps(workout['optionalSteps'], row['sport'])
            row['details'] += '\nOptional session: ' + '\n'.join(map(describe, row['optionalSteps']))
        elif row.get('baseMinutes',row['minutes']) != row['minutes']:
            raise ValueError('Provide the full optional sequence for an extended workout')
        if row.get('distanceYards') and row['sport']=='Swim':
            swim = row.get('optionalSteps',base)
            yards = sum(step.get('distance',0) for step in swim if step.get('unit')=='yd')
            if abs(yards-row['distanceYards']) > 0.01:
                raise ValueError('Swim steps do not match prescribed yards')
    return state


def session_diff(before, after):
    old = {x['id']:x for x in before.get('sessions',[])}
    new = {x['id']:x for x in after.get('sessions',[])}
    return {'added':sorted(new.keys()-old.keys()),'removed':sorted(old.keys()-new.keys()),
            'edited':{key:sorted(field for field in old[key].keys()|new[key].keys()
                                 if old[key].get(field)!=new[key].get(field))
                      for key in sorted(old.keys()&new.keys()) if old[key]!=new[key]}}


def schedule_key(state):
    identity = [state.get('athleteId'), state['goal'], state['version'],
                [(x['id'], x['date'], x['slot']) for x in state['sessions']]]
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def move_sessions(state, request):
    if not isinstance(request, dict) or type(request.get('version')) is not int:
        raise ValueError('Invalid schedule request or version')
    if request.get('version') != state['version'] or request.get('goal') != state['goal']['name'] or request.get('scheduleKey') != schedule_key(state):
        raise ValueError('Schedule preview is for another plan or version')
    moves = request.get('moves')
    if not isinstance(moves,list) or not moves:
        raise ValueError('No schedule moves supplied')
    revised = deepcopy(state)
    rows = {x['id']:x for x in revised['sessions']}
    seen = set()
    for edit in moves:
        if not isinstance(edit, dict) or not all(isinstance(edit.get(k), str) for k in ('id','slot','date')):
            raise ValueError('Each move needs a session ID, slot and date')
        key = edit['id']
        row = rows.get(key)
        if key in seen or not row or row['slot'] not in ('AM','PM') or edit.get('slot') not in ('AM','PM'):
            raise ValueError('Invalid or repeated schedule move')
        if date.fromisoformat(edit['date']).isoformat() != edit['date']:
            raise ValueError('Use YYYY-MM-DD for schedule requests')
        if row['date'] == edit['date'] and row['slot'] == edit['slot']:
            raise ValueError('Schedule request includes an unchanged session')
        row.update(date=edit['date'],slot=edit['slot'])
        seen.add(key)
    return revised


def progression_summary(state):
    """Return dated exposures and their spacing for the coach's season review."""
    groups = {}
    for row in sorted(state.get('sessions', []), key=lambda x: (x['date'], x['slot'])):
        focus = row.get('progressionFocus')
        if not focus:
            continue
        group = groups.setdefault((row['sport'], focus), [])
        previous = date.fromisoformat(group[-1]['date']) if group else None
        group.append({'id': row['id'], 'date': row['date'], 'title': row['title'],
                      'minutes': row['minutes'], 'requiredMinutes': row.get('baseMinutes', row['minutes']),
                      'daysSincePrevious': (date.fromisoformat(row['date']) - previous).days if previous else None,
                      'blockId': row.get('blockId'), 'runDose': row.get('runDose'),
                      'swimYards': row.get('distanceYards'), 'note': row.get('progressionNote')})
    return [{'sport':sport, 'focus':focus, 'exposures':exposures}
            for (sport,focus),exposures in groups.items()]
