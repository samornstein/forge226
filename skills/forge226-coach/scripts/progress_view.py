"""Readable goal and coaching progress panels, all supplied text escaped."""
from html import escape


def progress_html(s):
    e = lambda value: escape(str(value), quote=True)
    assessment = s.get('assessment')
    if not assessment:
        return '<section><h2>Goal progress</h2><p>No saved goal assessment yet. Add one at the next coaching review.</p></section>'
    priorities = ''.join('<li>'+e(x)+'</li>' for x in assessment['priorities'])
    uncertainties = ''.join('<li>'+e(x)+'</li>' for x in assessment['uncertainties']) or '<li>None recorded.</li>'
    qualification = assessment.get('qualification')
    q = ''
    if qualification:
        q = '<h3>Championship qualification</h3><p>'+e(qualification['status'])+' · '+e(qualification['timeGoalRelation'])+'</p><p>'+e(qualification['unknowns'])+'</p>'
    rows = []
    for b in s['trainingBlocks']:
        for c in b['checkpoints']:
            rows.append('<tr><td>'+e(c['date'])+'</td><td>'+e(b['focus'])+'</td><td>'+e(c['measure'])+'<br><small>'+e(c['criterion'])+'</small></td><td>'+e(c['status'])+'<br>'+e(c.get('evidence','Awaiting review'))+'</td></tr>')
    benchmarks = []
    for series in s.get('benchmarkHistory', {}).get('series', []):
        latest = series['history'][-1]
        change = 'No comparable prior result' if series['change'] is None else str(series['change'])+' '+series['units']
        benchmarks.append('<tr><td>'+e(series['sport'])+' · '+e(series['metric'])+'</td><td>'+e(latest['value'])+' '+e(series['units'])+'</td><td>'+e(series['latestDate'])+'<br>'+e(series['ageDays'])+' days old</td><td>'+e(change)+'</td><td>'+e(series['method'])+'<br>'+e(series['conditions'])+'</td></tr>')
    benchmark_html = '<p>No comparable benchmark history yet. Manual and effort-based planning remain available.</p>'
    if benchmarks:
        benchmark_html = '<div class="scroll"><table><tr><th>Benchmark</th><th>Latest</th><th>Evidence date</th><th>Change</th><th>Method & conditions</th></tr>'+''.join(benchmarks)+'</table></div><p>Numeric changes are descriptive; they do not automatically change training zones.</p>'
    if s.get('benchmarkHistory', {}).get('unverified'):
        benchmark_html += '<p>Some benchmark entries lack verified dates, methods or conditions; see the evidence record.</p>'
    decisions = s.get('reviewDecisions', [])
    decision = '<p>No weekly review decision saved yet.</p>'
    if decisions:
        d = sorted(decisions, key=lambda x: x['date'])[-1]
        decision = '<p><strong>'+e(d['action'].capitalize())+'</strong> · '+e(d['date'])+'</p><p>'+e(d['reason'])+'</p><p>Evidence: '+e(d['evidence'])+'</p><p>Changes: '+e(d['changes'])+'</p><p>Next review: '+e(d['nextReviewDate'])+'</p>'
    return '<section><h2>Goal assessment</h2><p><strong>'+e(assessment['track'].capitalize())+' · '+e(assessment['feasibility'])+'</strong> · Assessed '+e(assessment['evidenceDate'])+'</p><p>'+e(assessment['rationale'])+'</p><div class="grid"><div><h3>Current baseline</h3><p>'+e(assessment['baseline'])+'</p></div><div><h3>Goal demands</h3><p>'+e(assessment['goalDemands'])+'</p></div></div><h3>Current priorities</h3><ul>'+priorities+'</ul><h3>What remains uncertain</h3><ul>'+uncertainties+'</ul>'+q+'<p><strong>Next action:</strong> '+e(assessment['nextAction'])+'</p><small>Latest evidence export: '+e(s.get('exportedAt','Not recorded'))+'. New activity data does not automatically revise this saved assessment.</small></section><section><h2>Training checkpoints</h2><div class="scroll"><table><tr><th>Date</th><th>Block focus</th><th>Measure & criterion</th><th>Result</th></tr>'+''.join(rows)+'</table></div></section><section><h2>Benchmark progress</h2>'+benchmark_html+'</section><section><h2>Latest coaching decision</h2>'+decision+'</section>'
