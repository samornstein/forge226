"""Render an offline, escaped HTML snapshot from a validated athlete state."""
import html,json,sys
from pathlib import Path
from check_state import validate,DAYS
from progress_view import progress_html
from calendar_view import calendar_html
from run_dose_view import run_dose_html

def render(s):
    result=validate(s)
    if not result['passed']: raise ValueError('; '.join(result['errors']))
    e=lambda x: html.escape(str(x),quote=True)
    def structured(v):
        if v is None or v==[] or v=={}: return '<p class="muted">Not supplied.</p>'
        if isinstance(v,dict): return '<dl>'+''.join('<dt>'+e(k)+'</dt><dd>'+structured(x)+'</dd>' for k,x in v.items())+'</dl>'
        if isinstance(v,list): return '<ul>'+''.join('<li>'+structured(x)+'</li>' for x in v)+'</ul>'
        return '<span>'+e(v)+'</span>'
    rows=[]
    for x in sorted(s['sessions'],key=lambda x:(x['date'],{'AM':0,'PM':1,'Rest':2,'Race':3}.get(x['slot'],9))):
        rows.append('<tr data-date="'+e(x['date'])+'" data-sport="'+e(x['sport'])+'"><td>'+e(x['date'])+'</td><td>'+e(x['slot'])+'</td><td>'+e(x['sport'])+'</td><td><strong>'+e(x['title'])+'</strong><br>'+e(x['purpose'])+'<details><summary>Prescription</summary><p>'+e(x['details'])+'</p><p>Alternative: '+e(x.get('alternative','Not supplied'))+'</p><p>Success cue: '+e(x.get('successCue','Not supplied'))+'</p><small>'+e(x['id'])+'</small></details></td><td>'+e(x['minutes'])+'</td><td>'+e(x['intensity'])+(' · provisional' if x.get('provisional') else '')+'</td></tr>')
    av=[]; capacity=0
    for day in DAYS:
        cells=[]
        for slot in ('AM','PM'):
            v=s['availability'][day][slot]; n=v['minutes'] if v['enabled'] else 0; capacity+=n
            cells.extend([e('Yes' if v['enabled'] else 'No'),e(n)])
        av.append('<tr><th>'+day+'</th>'+''.join('<td>'+v+'</td>' for v in cells)+'</tr>')
    weeks=''.join('<tr><td>'+e(k)+'</td><td>'+e(round(v/60,2))+'</td></tr>' for k,v in result['weeklyTrainingMinutes'].items())
    sections=''.join('<section><h2>'+label+'</h2>'+structured(s.get(key))+'</section>' for key,label in [('strategy','Training framework'),('exceptions','Travel & schedule exceptions'),('analysis','Saved coaching interpretation'),('calculatedAnalysis','Latest calculated training evidence'),('adherence','Recent planned versus actual'),('benchmarkHistory','Benchmark evidence record'),('reviewDecisions','Coaching decision history'),('activities','Actual sessions & adherence evidence'),('wellness','Imported recovery & sleep'),('dataSources','Data source choices'),('checkins','Readiness check-ins'),('evidence','Evidence & coverage'),('changes','Revision history'),('review','Coaching review')])
    state_json=json.dumps(s,ensure_ascii=True).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Forge226 training dashboard</title><style>
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f5f3ec;color:#182027;font:16px/1.5 system-ui,sans-serif}main{max-width:1280px;margin:auto;padding:28px}header{background:#151e24;color:white;padding:30px;border-top:6px solid #ff512c}h1{font-size:36px;margin:12px 0}h2{font-size:22px}small,.muted{color:#58616a}header small{color:#d5dbdf}.brand{color:#ff795b;letter-spacing:.2em;font-weight:bold}section{background:white;padding:24px;margin:20px 0;border:1px solid #d9d6ce}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}.card{padding:20px;background:#172128;color:white}.card b{display:block;font-size:26px;color:#dfff64}.scroll{overflow:auto}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:12px;border-bottom:1px solid #ddd;vertical-align:top}th{background:#efede7}button,select,input{font:inherit;padding:8px;margin:5px;border:1px solid #aaa;background:white;color:#182027}button{cursor:pointer}details p{white-space:pre-wrap}dt{font-weight:650;margin-top:10px}dd{margin-left:16px;overflow-wrap:anywhere}ul{padding-left:22px}label{display:inline-block}@media print{button,.filters{display:none}body{background:white}main{padding:0}section{break-inside:auto}tr{break-inside:avoid}}[hidden]{display:none!important}</style></head><body><main>
''' + '<header><div class="brand">FORGE226 COACH</div><h1>'+e(s['goal']['name'])+'</h1><p>'+e(s['athlete'].get('name','Athlete'))+' · '+e(s['goal']['startDate'])+' → '+e(s['goal']['endDate'])+'</p><small>Version '+e(s['version'])+' · '+e(s['status']).upper()+' · Generated '+e(s.get('generatedAt','Unknown'))+' · '+e(s['timezone'])+'</small></header>' + '<p>Offline snapshot. Changes in other files are not synchronized. Download the state to resume coaching.</p><button id="download">Download athlete state</button><div class="grid"><div class="card">Current training hours/week<b>'+e(s['athlete'].get('currentWeeklyHours','Unknown'))+'</b></div><div class="card">Weekly slot capacity<b>'+e(f'{int(capacity//60)}h {capacity%60:g}m')+'</b></div><div class="card">Optional weekly cap<b>'+e(str(s['weeklyCapMinutes']/60)+'h' if s.get('weeklyCapMinutes') is not None else 'Not set')+'</b></div></div>' + progress_html(s) + '<section><h2>Weekly availability</h2><div class="scroll"><table><thead><tr><th>Day</th><th>AM available</th><th>AM max min</th><th>PM available</th><th>PM max min</th></tr></thead><tbody>'+''.join(av)+'</tbody></table></div><p>Capacity is a ceiling, not a training target.</p></section><section><h2>Weekly planned hours</h2><p>Monday-start weeks; boundary weeks may be partial. Race minutes separately: '+e(result['raceMinutes'])+'</p><table><thead><tr><th>Week starting</th><th>Training hours</th></tr></thead><tbody>'+weeks+'</tbody></table></section>' + calendar_html(s)+run_dose_html(s['sessions'])+sections+'<section><h2>Next check-in</h2><p>Bring this state back with completed sessions, actual duration/effort, readiness and upcoming schedule changes. Ask for a weekly review before updating the active plan.</p><p>'+e(result['scope'])+'</p></section><script id="state" type="application/json">'+state_json+'''</script><script>
const state=JSON.parse(document.getElementById('state').textContent);
document.getElementById('download').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(state,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='athlete-state.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
</script></main></body></html>'''
if __name__=='__main__':
    state=json.loads(Path(sys.argv[1]).read_text())
    output=Path(sys.argv[2]); output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(render(state)); print(output)
