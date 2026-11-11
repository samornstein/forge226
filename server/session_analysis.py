"""Read explicitly normalized laps; no unsupported FIT parsing or physiological inference."""
import json
from pathlib import Path
from analysis import finite


def analyze_laps(path, activity, comparison=None):
    p = Path(path)
    if p.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Lap file exceeds 2 MB')
    data = json.loads(p.read_text())
    if data.get('activityId') != activity['id'] or not data.get('source'):
        raise ValueError('Lap file must identify the selected stored activity and its source')
    if data.get('units') != {'duration': 's', 'distance': 'm', 'power': 'W', 'heartRate': 'bpm'}:
        raise ValueError('Declare canonical units: duration s, distance m, power W, heartRate bpm')
    laps = data.get('laps')
    if not isinstance(laps, list) or not 1 <= len(laps) <= 2000:
        raise ValueError('Supply 1–2000 non-overlapping laps')
    output, ids = [], set()
    previous_end = 0
    for lap in sorted(laps, key=lambda x: x['startSeconds']):
        ident = lap.get('id')
        if not isinstance(ident, str) or not ident or ident in ids:
            raise ValueError('Each lap needs a unique string ID')
        ids.add(ident)
        start, duration = lap.get('startSeconds'), lap.get('durationSeconds')
        if not finite(start) or not finite(duration) or start < previous_end or duration <= 0:
            raise ValueError('Laps require nonnegative starts, positive duration and no overlap')
        previous_end = start + duration
        row = dict(lap)
        for field in ('distanceMeters', 'meanPowerWatts', 'meanHeartRateBpm'):
            value = lap.get(field)
            if value is not None and (not finite(value) or value < 0 or (field == 'meanHeartRateBpm' and value == 0)):
                raise ValueError('Invalid lap metric '+field)
        distance = lap.get('distanceMeters')
        row['paceSecondsPerKm'] = round(duration / distance * 1000, 2) if distance and activity['sport'].lower() == 'run' else None
        output.append(row)
    result = {'activityId': activity['id'], 'source': data['source'], 'laps': output,
              'lapDurationSeconds': sum(x['durationSeconds'] for x in output),
              'recordedActivityDurationSeconds': activity['durationSeconds'],
              'limitations': 'Lap duration may differ from moving time. Averages do not establish time in zones, normalized power, decoupling, fitness or race readiness. Check terrain, stops, weather, effort and sensors before interpreting differences.'}
    if comparison:
        first, second = comparison.get('firstLapIds'), comparison.get('secondLapIds')
        if not isinstance(first, list) or not isinstance(second, list) or not first or not second or len(set(first)) != len(first) or len(set(second)) != len(second) or set(first) & set(second) or not (set(first) | set(second)) <= ids or not comparison.get('context'):
            raise ValueError('Comparison needs two disjoint known lap ID lists and context about comparability')
        def group(selected):
            group = [x for x in output if x['id'] in selected]
            duration = sum(x['durationSeconds'] for x in group)
            stats = {'durationSeconds': duration}
            for field in ('meanPowerWatts', 'meanHeartRateBpm'):
                stats[field] = sum(x[field]*x['durationSeconds'] for x in group)/duration if all(x.get(field) is not None for x in group) else None
            stats['speedMetersPerSecond'] = sum(x['distanceMeters'] for x in group)/duration if all(x.get('distanceMeters') is not None for x in group) else None
            return stats
        a, b = group(first), group(second)
        result['comparison'] = {'first': a, 'second': b, 'context': comparison['context'],
                                'percentChange': {k: round((b[k]-a[k])/a[k]*100, 2) if a[k] is not None and a[k] > 0 and b[k] is not None else None for k in ('meanPowerWatts', 'meanHeartRateBpm', 'speedMetersPerSecond')},
                                'interpretation': 'Descriptive difference only; does not isolate fatigue or establish a physiological threshold.'}
    return result
