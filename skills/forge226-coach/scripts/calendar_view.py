"""Self-contained month/week/day calendar for any validated athlete state."""
import json
from pathlib import Path

def calendar_html(state):
    # Only plan fields are needed by the calendar; actual records stay in the report.
    data={k:state.get(k) for k in ('goal','sessions','trainingBlocks','exceptions','version','status','timezone')}
    data['trainingBlocks']=data['trainingBlocks'] or []
    data['exceptions']=data['exceptions'] or []
    encoded=json.dumps(data,ensure_ascii=True).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return Path(__file__).with_name('calendar.html').read_text().replace('__CALENDAR_DATA__',encoded)
