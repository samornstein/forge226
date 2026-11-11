"""Summarize optional planned run effort minutes without inferring actuals."""
from collections import defaultdict
from datetime import date, timedelta
from html import escape
from math import isfinite


def run_dose_html(sessions):
    weeks = defaultdict(dict)
    estimates = set()
    for session in sessions:
        dose = session.get('runDose')
        if session.get('sport') != 'Run' or not isinstance(dose, dict):
            continue
        day = date.fromisoformat(session['date'])
        week = day - timedelta(days=day.weekday())
        for effort, minutes in dose.items():
            if type(minutes) not in (int, float) or not isfinite(minutes) or minutes <= 0:
                continue
            weeks[week][effort] = weeks[week].get(effort, 0) + minutes
            if session.get('runDoseEstimated'):
                estimates.add((week, effort))
    if not weeks:
        return ''
    rows = []
    for week, efforts in sorted(weeks.items()):
        for effort, minutes in sorted(efforts.items()):
            prefix = '~' if (week, effort) in estimates else ''
            rows.append(f'<tr><td>{week}</td><td>{escape(effort)}</td><td>{prefix}{minutes:.1f}</td></tr>')
    return ('<section><h2>Weekly run work by effort</h2><p>Planned work minutes. '
            '~ includes estimated time for distance repeats.</p><table><thead><tr>'
            '<th>Week of</th><th>Effort</th><th>Minutes</th></tr></thead><tbody>'
            + ''.join(rows) + '</tbody></table></section>')
