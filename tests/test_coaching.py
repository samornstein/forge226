import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import date, timedelta
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'server'))
from server import App
from analysis import summarize, benchmark_history, adherence
from session_analysis import analyze_laps
from check_state import validate
from render_dashboard import render
from test_integration import fixture


def row(ident, day, minutes=60, source='garmin', sport='Bike', hour=8):
    return {'id': source+':'+str(ident), 'sourceId': str(ident), 'source': source,
            'date': day, 'startTime': day+f'T{hour:02}:00:00+00:00',
            'durationSeconds': minutes*60, 'distanceMeters': minutes*300, 'sport': sport}


def coached(aid, track='completion'):
    s = fixture(aid)
    s['coachingVersion'] = 1
    s['assessment'] = {'evidenceDate': '2026-11-08', 'track': track,
                       'disciplineExperience': {'Swim': 'new', 'Bike': 'experienced', 'Run': 'intermediate'},
                       'baseline': 'Athlete reports three comfortable rides per week; swim evidence unknown.',
                       'goalDemands': 'Establish a repeatable starting routine before further progression.',
                       'feasibility': 'insufficient-evidence', 'rationale': 'No recent swim benchmark; use effort and review response.',
                       'priorities': ['Establish repeatable routine'], 'uncertainties': ['Swim endurance unknown'],
                       'nextAction': 'Complete the first week and report effort and recovery.'}
    if track == 'qualification':
        s['assessment']['qualification'] = {'status': 'unverified', 'timeGoalRelation': 'Sub-4:20 is a separate time goal, not a guaranteed slot.', 'unknowns': 'Target race rules and future field/acceptance unknown.'}
    s['trainingBlocks'] = [{'id': 'b1', 'startDate': '2026-11-09', 'endDate': '2026-11-15',
                            'focus': 'Consistency', 'rationale': 'Establish current tolerance',
                            'progressIf': 'Sessions comfortable and recovery acceptable',
                            'repeatIf': 'Response unclear', 'reduceIf': 'Repeated difficulty or recovery concern',
                            'checkpoints': [{'date': '2026-11-15', 'measure': 'Routine and response', 'criterion': 'Review actual sessions and athlete-reported tolerance', 'status': 'planned'}]}]
    s['reviewDecisions'] = []
    for x in s['sessions']:
        if x['sport'] not in ('Rest', 'Race'):
            x.update(blockId='b1', successCue='Comfortable effort throughout', alternative='Shorten to 25 minutes easy')
    return s


class Calculations(unittest.TestCase):
    def test_complete_periods_exclude_current_week(self):
        start = date(2026, 9, 14)
        rows = [row(i, (start+timedelta(days=i*7)).isoformat(), 60 if i<4 else 90) for i in range(8)]
        rows.append(row(100, '2026-11-09', 500))
        coverage = [{'startDate': '2026-09-14', 'endDate': '2026-11-08', 'complete': True, 'basis': 'Athlete reconciled full training/rest'}]
        result = summarize(rows, '2026-11-09', coverage)['comparison']
        self.assertTrue(result['comparable'])
        self.assertEqual(result['recentFourCompletedWeeks']['observedHours'], 6)
        self.assertEqual(result['previousFourCompletedWeeks']['observedHours'], 4)
        self.assertEqual(result['percentChange'], 50)
    def test_missing_weeks_not_zero_or_improvement(self):
        result = summarize([row(1, '2026-11-01')], '2026-11-09')
        self.assertIsNone(result['comparison']['percentChange'])
        self.assertTrue(any(x['hours'] is None for x in result['weekly']))
    def test_duplicate_totals_are_provisional(self):
        rows = [row(1,'2026-11-01'), row(1,'2026-11-01', source='strava')]
        result = summarize(rows, '2026-11-09', [{'startDate':'2026-08-01','endDate':'2026-11-09','complete':True,'basis':'reported'}])
        self.assertEqual(result['activityCount'], 1)
        self.assertTrue(result['totalsProvisional'])
        self.assertFalse(result['comparison']['comparable'])
    def test_zero_prior_period_no_division(self):
        result = summarize([], '2026-11-09', [{'startDate':'2026-08-01','endDate':'2026-11-09','complete':True,'basis':'confirmed rest'}])
        self.assertEqual(result['comparison']['hoursChange'], 0)
        self.assertIsNone(result['comparison']['percentChange'])
    def test_benchmarks_keep_methods_separate(self):
        base = {'sport':'Bike','metric':'FTP','units':'W','method':'protocol A','source':'athlete test','conditions':'same trainer'}
        profile = {'benchmarks':[{**base,'date':'2026-09-01','value':250},{**base,'date':'2026-10-01','value':260},{**base,'method':'protocol B','date':'2026-10-15','value':280},{**base,'date':'2027-01-01','value':300}]}
        result=benchmark_history(profile,'2026-11-09')
        self.assertEqual(len(result['series']),2)
        self.assertEqual(result['series'][0]['change'],10)
        self.assertEqual(len(result['unverified']),1)
    def test_unique_candidate_stays_unknown(self):
        sessions=fixture('a')['sessions']
        result=adherence(sessions,[row(1,'2026-11-09',45)],[],'2026-11-15')
        self.assertEqual(result['sessions'][0]['status'],'unknown')
        self.assertEqual(result['sessions'][0]['suggestedStatus'],'completed')
        self.assertEqual(result['bySport']['Bike']['confirmedActualMinutes'],0)
    def test_double_session_does_not_double_match(self):
        a=fixture('a')['sessions'][0]
        result=adherence([a,{**a,'id':'second'}],[row(1,'2026-11-09',45)],[],'2026-11-15')
        self.assertTrue(all('suggestedStatus' not in x for x in result['sessions']))
    def test_manual_strength_and_missed(self):
        a={**fixture('a')['sessions'][0],'sport':'Strength'}
        b={**a,'id':'second','date':'2026-11-11'}
        outcomes=[{'sessionId':a['id'],'confirmed':True,'status':'completed','basis':'athlete report','actualMinutes':30}, {'sessionId':'second','confirmed':True,'status':'missed-confirmed','basis':'athlete report','actualMinutes':0}]
        result=adherence([a,b],[],outcomes,'2026-11-15')
        self.assertEqual(result['bySport']['Strength']['confirmedActualMinutes'],30)
        self.assertEqual(result['statusCounts'],{'completed':1,'missed-confirmed':1})


class CoachingWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=App(self.tmp.name)
        self.a=self.app.store.create('Synthetic test athlete','America/Los_Angeles')['id']
    def tearDown(self):
        self.app.strava.close();self.app.garmin.close();self.tmp.cleanup()
    def call(self,name,**args):
        return self.app.call('forge226_'+name,{'athlete_id':self.a,**args})
    def test_first_timer_manual_full_save_export_resume(self):
        self.call('configure_source',provider='manual',mode='manual',enabled=True)
        state=coached(self.a)
        draft=self.call('save_plan_draft',state=state,parent_version=None)
        self.assertTrue(draft['validation']['passed'],draft)
        self.call('activate_plan',version=draft['version'],expected_active=None)
        out=self.call('export_dashboard')
        exported=json.loads(Path(out['state']).read_text())
        self.assertEqual(exported['assessment']['track'],'completion')
        self.assertEqual(exported['activities'],[])
        self.assertIn('Training checkpoints',Path(out['html']).read_text())
        restarted=App(self.tmp.name)
        self.assertEqual(restarted.store.plan(self.a)['state']['trainingBlocks'],state['trainingBlocks'])
    def test_qualification_unknown_rules_does_not_fake_verification(self):
        state=coached(self.a,'qualification')
        state['analysis']={'finding':'Aspirational time; no supported race prediction yet.'}
        draft=self.call('save_plan_draft',state=state,parent_version=None)
        self.assertTrue(draft['validation']['passed'])
        out=self.call('export_dashboard',version=draft['version'])
        exported=json.loads(Path(out['state']).read_text())
        self.assertEqual(exported['analysis'],state['analysis'])
        self.assertEqual(exported['assessment']['qualification']['status'],'unverified')
        self.assertIn('separate time goal',Path(out['html']).read_text())
    def test_travel_revision_preserves_active_until_approved(self):
        first=self.call('save_plan_draft',state=coached(self.a),parent_version=None)
        self.call('activate_plan',version=first['version'],expected_active=None)
        state=self.call('get_plan')['state']
        state['exceptions']=[{'startDate':'2026-11-13','endDate':'2026-11-13','reason':'Travel','slots':{'AM':{'enabled':False,'minutes':0},'PM':{'enabled':False,'minutes':0}}}]
        state['reviewDecisions']=[{'date':'2026-11-10','action':'reschedule','evidence':'Athlete supplied travel dates','reason':'No training window Friday','changes':'Drop Friday ride; no catch-up overload','nextReviewDate':'2026-11-17'}]
        bad=self.call('save_plan_draft',state=state,parent_version=first['version'])
        self.assertFalse(bad['validation']['passed'])
        state['sessions'][4].update(slot='Rest',sport='Rest',minutes=0,title='Travel rest')
        good=self.call('save_plan_draft',state=state,parent_version=first['version'])
        self.assertTrue(good['validation']['passed'],good)
        self.assertEqual(self.app.store.active_version(self.a),first['version'])
        self.call('activate_plan',version=good['version'],expected_active=first['version'])
        self.assertEqual(self.call('get_plan',version=first['version'])['state']['sessions'][4]['minutes'],45)
    def test_qualification_claim_needs_event_evidence(self):
        state=coached(self.a,'qualification');state['assessment']['qualification']['status']='verified'
        self.assertFalse(validate(state)['passed'])
    def test_checkpoint_without_evidence_rejected(self):
        state=coached(self.a);state['trainingBlocks'][0]['checkpoints'][0]['status']='met'
        self.assertFalse(validate(state)['passed'])
    def test_unlinked_session_rejected(self):
        state=coached(self.a);state['sessions'][0]['blockId']='missing'
        self.assertFalse(validate(state)['passed'])
    def test_reused_actual_rejected(self):
        state=coached(self.a);state['sessionOutcomes']=[{'sessionId':s,'confirmed':True,'status':'completed','basis':'athlete confirmed','activityIds':['a']} for s in ('s0','s2')]
        self.assertFalse(validate(state)['passed'])
    def test_review_uses_selected_plan_and_does_not_mutate(self):
        draft=self.call('save_plan_draft',state=coached(self.a),parent_version=None)
        report=self.call('review_summary',version=draft['version'],as_of='2026-11-15')
        self.assertEqual(report['adherence']['statusCounts'],{'unknown':3})
        self.assertEqual(report['planVersion'],draft['version'])
        self.assertIsNone(self.app.store.active_version(self.a))
    def test_hidden_source_invalidates_old_coverage(self):
        r=row(1,'2026-11-01');self.app.store.ingest(self.a,'garmin',[r],{},'x')
        self.call('save_profile',profile={'evidenceCoverage':[{'startDate':'2026-08-01','endDate':'2026-11-09','complete':True,'basis':'all history'}]},expected_revision=1)
        self.call('configure_source',provider='garmin',mode='upload',enabled=False)
        self.assertFalse(self.call('analyze',as_of='2026-11-09')['comparison']['comparable'])
    def test_progress_escapes_injected_text(self):
        state=coached(self.a);state['assessment']['rationale']='</section><script>alert(1)</script>'
        self.assertNotIn('<script>alert(1)',render(state))
    def test_legacy_plan_still_valid(self):
        self.assertTrue(validate(fixture(self.a))['passed'])


class LapEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'laps.json'
        self.activity=row(1,'2026-11-09',10)
        self.data={'activityId':self.activity['id'],'source':'synthetic fixture','units':{'duration':'s','distance':'m','power':'W','heartRate':'bpm'},'laps':[{'id':'1','startSeconds':0,'durationSeconds':100,'meanPowerWatts':100},{'id':'2','startSeconds':100,'durationSeconds':300,'meanPowerWatts':200},{'id':'3','startSeconds':400,'durationSeconds':200,'meanPowerWatts':175}]}
    def tearDown(self):self.tmp.cleanup()
    def analyze(self,comparison=None):
        self.path.write_text(json.dumps(self.data));return analyze_laps(self.path,self.activity,comparison)
    def test_weighted_means_and_missing_hr(self):
        result=self.analyze({'firstLapIds':['1','2'],'secondLapIds':['3'],'context':'same steady effort on trainer'})['comparison']
        self.assertEqual(result['first']['meanPowerWatts'],175)
        self.assertEqual(result['percentChange']['meanPowerWatts'],0)
        self.assertIsNone(result['percentChange']['meanHeartRateBpm'])
    def test_overlap_rejected(self):
        self.data['laps'][1]['startSeconds']=50
        with self.assertRaises(ValueError):self.analyze()
    def test_wrong_activity_rejected(self):
        self.data['activityId']='another'
        with self.assertRaises(ValueError):self.analyze()
    def test_comparison_cannot_reuse_laps(self):
        with self.assertRaises(ValueError):self.analyze({'firstLapIds':['1'],'secondLapIds':['1'],'context':'same'})

if __name__=='__main__':unittest.main()
