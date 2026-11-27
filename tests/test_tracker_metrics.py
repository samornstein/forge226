import sys
import unittest
from math import exp
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from tracker_metrics import metrics_report, score_activity, planned_score, prescription_steps, best_power, best_run


def threshold(sport, kind, value, units, date='2026-01-01'):
    return dict(sport=sport,kind=kind,value=value,units=units,date=date,source='Field test')


class TrackerMetricsTests(unittest.TestCase):
    def setUp(self):
        self.ride=dict(id='a',date='2026-02-01',sport='Bike',durationSeconds=3600,normalizedPower=250)
        self.ftp=threshold('Bike','ftp',250,'W')
        self.session=dict(id='s',date='2026-02-01',sport='Bike',title='FTP',minutes=60,
                          profileSteps=[dict(label='100% FTP',kind='Quality',time=60)])
        self.state=dict(goal=dict(startDate='2026-02-01',raceDate='2026-02-04'),sessions=[self.session])

    def test_power_score_and_effective_threshold(self):
        self.assertEqual(score_activity(self.ride,[self.ftp])['stress'],100)
        self.assertEqual(score_activity(self.ride,[self.ftp,dict(self.ftp,date='2026-02-03',value=300)])['stress'],100)
        self.assertIsNone(score_activity(self.ride,[dict(self.ftp,date=None)])['stress'])
        average=dict(self.ride,normalizedPower=None,averagePower=250)
        self.assertIsNone(score_activity(average,[self.ftp])['stress'])
        samples=[dict(elapsedSeconds=t,power=250) for t in range(0,3601,5)]
        self.assertEqual(score_activity(average,[self.ftp],dict(samples=samples))['stress'],100)

    def test_hr_gaps_flat_run_and_swim(self):
        hr=threshold('Run','lthr',180,'bpm')
        run=dict(self.ride,sport='Run',averageHr=162,distanceMeters=10000)
        self.assertEqual(score_activity(run,[hr])['stress'],81)
        threshold_pace=threshold('Run','runPace',360,'s/km')
        self.assertIsNone(score_activity(run,[threshold_pace])['stress'])
        self.assertEqual(score_activity(dict(run,terrain='flat'),[threshold_pace])['stress'],100)
        samples=[dict(elapsedSeconds=t,distanceMeters=t*10000/3600,altitudeMeters=50) for t in range(0,3601,5)]
        self.assertAlmostEqual(score_activity(run,[threshold_pace],dict(samples=samples))['stress'],100,places=2)
        swim=dict(self.ride,sport='Swim',distanceMeters=2000)
        css=threshold('Swim','css',90,'s/100m')
        self.assertIsNone(score_activity(swim,[css])['stress'])
        self.assertEqual(score_activity(swim,[css],dict(activeSwimSeconds=1800))['stress'],50)
        self.assertIsNone(score_activity(dict(swim,sport='Strength'),[css])['stress'])

    def test_plan_and_forecast_have_separate_baselines(self):
        cover=[dict(start='2026-02-01',end='2026-02-02')]
        weak=dict(self.ride,normalizedPower=125)
        future=dict(self.session,id='future',date='2026-02-03',baseMinutes=0)
        self.state['sessions'].append(future)
        r=metrics_report(self.state,[weak],[self.ftp],'2026-02-02',coverage=cover)
        day1,day2,day3,day4=r['pmc']['All']
        self.assertAlmostEqual(day1['actual']['ctl'],25*(1-exp(-1/42)),places=2)
        self.assertAlmostEqual(day1['planned']['ctl'],100*(1-exp(-1/42)),places=2)
        self.assertAlmostEqual(day2['actual']['tsb'],25*(exp(-1/7)-exp(-1/42)),places=2)
        self.assertIsNone(day3['actual'])
        self.assertLess(day3['forecast']['ctl'],day3['planned']['ctl'])
        self.assertGreater(day3['forecastHigh']['ctl'],day3['forecast']['ctl'])
        self.assertLess(day4['forecastHigh']['ctl'],day3['forecastHigh']['ctl'])

    def test_rep_duration_alignment_and_no_cross_gap_best(self):
        r=metrics_report(self.state,[self.ride],[self.ftp],'2026-02-01',{'s':'a'},
                         details={'a':{'laps':[dict(durationSeconds=3600,averagePower=250)]}})
        self.assertEqual(r['intervals']['s']['repComparisons'][0]['actualSeconds'],3600)
        samples=[dict(elapsedSeconds=t,power=200,distanceMeters=t*4) for t in [0,5,60,65]]
        self.assertIsNone(best_power(samples,10))
        self.assertIsNone(best_run(samples,40))

    def test_cycling_steps_main_set_and_optional_steady(self):
        s=dict(self.session,minutes=75,profileSteps=[],details='12 min warm-up: 5 easy, 4 moderate, 2 building, 1 easy. Then 10 min aerobic at 65–72% current FTP. 4 × 9 min: 3 min at 101%, then 6 at 97%. Take 3 min easy between. Finish with 8 min easy.')
        steps=prescription_steps(s)
        self.assertEqual([x['level'] for x in steps if x['kind']=='Quality'],[101,97]*4)
        self.assertEqual(sum(x['time'] for x in steps),75)
        self.assertEqual(planned_score(s)['method'],'Prescribed steps')
        s=dict(s,sport='Run',minutes=100,profileSteps=[dict(label='Easy',time=100,kind='Easy')],
               details='Optional: 75 min easy, 15 min steady aerobic, then 10 min easy.')
        self.assertGreater(planned_score(s)['high'],planned_score(s)['low'])

    def test_steady_decoupling_and_records(self):
        samples=[dict(elapsedSeconds=t,power=200,hr=140 if t<1950 else 154) for t in range(0,3601,5)]
        r=metrics_report(self.state,[self.ride],[self.ftp],'2026-02-01',details={'a':dict(samples=samples)})
        b=next(x for x in r['benchmarks'] if x['metric']=='Aerobic decoupling')
        self.assertAlmostEqual(b['value'],9.09,places=2)
        self.assertEqual(next(x for x in r['records'] if x['metric']=='Best 20-min power')['value'],200)

    def test_missing_measurements_do_not_display_measured_zero_fitness(self):
        snap=metrics_report(self.state,[self.ride],[],'2026-02-01')
        self.assertIsNone(snap['pmc']['All'][0]['actual'])
        self.assertIsNone(snap['pmc']['All'][1]['forecast'])
        self.assertIsNotNone(snap['pmc']['All'][1]['planned'])

    def test_build_alignment_skips_race_week_and_incomplete_data(self):
        goal=dict(name='Goal',distance='70.3',startDate='2026-01-01',raceDate='2026-08-30')
        prior=[dict(id='old-bike',date='2025-08-31',sport='Bike',distanceMeters=90000,durationSeconds=8500),
               dict(id='old-run',date='2025-08-31',sport='Run',distanceMeters=21100,durationSeconds=5700),
               dict(id='old-t2',date='2025-08-31',sport='Other',name='Transition',durationSeconds=100),
               dict(self.ride,id='daily',date='2025-08-20')]
        snap=metrics_report(dict(goal=goal,sessions=[]),prior,[],'2026-08-16',
                            coverage=[dict(start='2025-08-18',end='2025-08-24')])
        candidate=snap['historyComparison']['builds'][-1]
        self.assertEqual(candidate['raceDate'],'2025-08-31')
        self.assertEqual(candidate['finalEight']['coverage'],'1/8 complete weeks')
        self.assertEqual(candidate['finalEight']['medianMinutes']['All'],60)
        self.assertEqual(candidate['finalEight']['weeks'][-1]['end'],'2025-08-24')
        self.assertIsNone(candidate['weeks'][0]['minutes']['All'])

    def test_race_ranges_require_current_evidence_for_each_leg(self):
        goal=dict(name='Goal',distance='70.3',raceDate='2026-03-01',startDate='2026-01-01')
        evidence=[]
        activities=[]
        for leg,sec,meters in [('Swim',1500,1700),('Bike',4200,40000),('Run',1250,5000),
                                ('T1',100,None),('T2',80,None)]:
            activities.append(dict(id=leg,date='2026-01-20',sport=leg if leg in ('Swim','Bike','Run') else 'Other',durationSeconds=sec))
            evidence.append(dict(leg=leg,activityId=leg,seconds=sec,distanceMeters=meters,context='Athlete-tagged rehearsal split'))
        state=dict(goal=goal,sessions=[],raceEvidence=evidence)
        result=metrics_report(state,activities,[],'2026-02-01')['raceEstimate']
        self.assertEqual(result['missing'],[])
        self.assertEqual(result['total']['centralSeconds'],sum(i['centralSeconds'] for i in result['legs']))
        self.assertLess(result['total']['lowSeconds'],result['total']['centralSeconds'])
        self.assertGreater(result['total']['highSeconds'],result['total']['centralSeconds'])
        expired=metrics_report(state,activities,[],'2026-06-01')['raceEstimate']
        self.assertIsNone(expired['total'])
        self.assertEqual(len(expired['missing']),5)

    def test_matched_brick_with_race_rhythm_watch_lap(self):
        # Correctly paired on the same day; ordinary standalone running must not be treated as a brick.
        ride=dict(self.ride,startTime='2026-02-01T08:00:00+00:00')
        run=dict(id='run',date=ride['date'],startTime='2026-02-01T09:04:00+00:00',sport='Run',durationSeconds=2400)
        session=dict(id='brick',date=ride['date'],minutes=40,sport='Run',title='Race rehearsal brick',
                     details='8 min easy + 24 min continuous at sustainable 70.3 effort + 8 min easy.')
        state=dict(goal=dict(startDate=ride['date'],raceDate='2026-04-05',distance='70.3'),sessions=[session])
        def projection(acts):
            result=metrics_report(state,acts,[],'2026-02-01',{'brick':'run'},details={'run':dict(laps=[dict(durationSeconds=1440,distanceMeters=5500)])})
            return next(x for x in result['raceEstimate']['legs'] if x['leg']=='Run')['centralSeconds']
        self.assertEqual(projection([ride,run]),round(1440/5500*21097.5))
        self.assertIsNone(projection([run]))
