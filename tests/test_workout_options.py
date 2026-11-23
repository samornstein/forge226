import unittest
from test_integration import fixture
from check_state import validate
from calendar_view import calendar_html


class WorkoutOptions(unittest.TestCase):
    def test_optional_steps_and_export(self):
        state = fixture('sample')
        workout = state['sessions'][0]
        workout.update(baseMinutes=30, profileSteps=[dict(label='Easy', time=30)],
                       optionalSteps=[dict(label='Easy', time=30), dict(label='Steady', time=15)])
        self.assertTrue(validate(state)['passed'])
        html = calendar_html(state)
        self.assertIn('Export plan (.xlsx)', html)
        self.assertNotIn('__EXPORT_SCRIPT__', html)
        workout['optionalSteps'][1]['time'] = 20
        self.assertFalse(validate(state)['passed'])

    def test_strength_preference(self):
        state = fixture('sample')
        state['sessions'][0]['sport'] = 'Strength'
        state['weeklyCapMinutes'] = 100
        self.assertFalse(validate(state)['passed'])
        state['timeAccounting'] = {'excludedSports': ['Strength']}
        self.assertTrue(validate(state)['passed'])

    def test_structured_options_sport_and_distance(self):
        from plan_workflow import normalize
        state = fixture('synthetic')
        row = state['sessions'][0]
        step = dict(label='Smooth 100', time=5, distance=100, unit='yd', kind='Steady')
        row.update(sport='Swim', distanceYards=900, baseMinutes=30, workout={
            'sport':'Swim','steps':[{'repeat':2,'steps':[{'repeat':3,'steps':[step]}]}],
            'optionalSteps':[{'repeat':9,'steps':[step]}]})
        self.assertEqual(len(normalize(state)['sessions'][0]['profileSteps']),6)
        self.assertEqual(validate(state)['weeklyRequiredMinutes'],{'2026-11-09':120})
        self.assertEqual(validate(state)['weeklyTrainingMinutes'],{'2026-11-09':135})
        self.assertTrue(validate(state)['passed'])
        row['distanceYards']=800
        self.assertFalse(validate(state)['passed'])
        row['distanceYards']=900
        step['sport']='Run'
        self.assertFalse(validate(state)['passed'])

    def test_share_projection_and_legacy_render(self):
        from calendar_view import share_html
        from render_dashboard import render
        state=fixture('sample')
        state['planningBrief']={'readiness':'private assessment marker'}
        state['wellness']=[{'note':'private recovery marker'}]
        state['sessions'][0]['workout']={'sport':'Bike','steps':[dict(label='Workout marker',time=45,privateNote='private recovery marker')]}
        public=share_html(state)
        self.assertIn('Workout marker',public)
        self.assertNotIn('private recovery marker',public)
        self.assertNotIn('private assessment marker',public)
        self.assertIn('private assessment marker',render(state))

    def test_schedule_request_and_review(self):
        import tempfile
        from server import App
        from plan_workflow import schedule_key
        with tempfile.TemporaryDirectory() as root:
            app=App(root)
            aid=app.store.create('Synthetic','America/Los_Angeles')['id']
            state=fixture(aid)
            app.store.draft(aid,state,None)
            app.store.activate(aid,1,None)
            request={'goal':state['goal']['name'],'version':1,'scheduleKey':schedule_key(state),
                     'moves':[dict(id='s0',date='2026-11-11',slot='AM'),dict(id='s2',date='2026-11-09',slot='AM')]}
            def preview():
                return app.call('forge226_prepare_schedule_change',{'athlete_id':aid,'request':request})
            result=preview()
            self.assertEqual(result['sessionChanges']['edited'],{'s0':['date'],'s2':['date']})
            self.assertEqual(app.store.plan(aid)['state']['sessions'][0]['date'],'2026-11-09')
            self.assertEqual(app.store.plan(aid,2)['state']['sessions'][0]['date'],'2026-11-11')
            with self.assertRaises(ValueError): app.store.activate(aid,2,1)
            candidate=app.store.plan(aid,2)['state']
            candidate['review']=state['review']
            final=app.store.draft(aid,candidate,1)
            app.store.activate(aid,final['version'],1)
            with self.assertRaises(ValueError): preview()

    def test_excluded_sport_still_needs_access(self):
        state=fixture('sample')
        row=state['sessions'][0]
        row.update(sport='Strength',slot='PM')
        state['timeAccounting']={'excludedSports':['Strength']}
        self.assertFalse(validate(state)['passed'])
        row.update(sport='Swim',slot='AM')
        state['sportAccess']={'Swim':['Monday PM']}
        self.assertFalse(validate(state)['passed'])

    def test_evidence_window_boundaries(self):
        from analysis import compare_builds
        window={'startDate':'2026-11-10','endDate':'2026-11-22'}
        records=[dict(id=str(i),date=d,sport='Run',durationSeconds=3600,name='Easy',source='s',sourceId=str(i),startTime=d+'T12:00:00+00:00') for i,d in enumerate(['2026-11-10','2026-11-16','2026-11-18'])]
        summary=compare_builds(records,{'readiness':window})['windows']['readiness']
        self.assertEqual(summary['records'],3)
        self.assertEqual(summary['interiorObservedWeeks'],1)
        self.assertEqual(summary['medianRecordedWeeklyHours'],2)
        self.assertIsNone(compare_builds([],{'comparableRace':window})['windows']['comparableRace']['medianRecordedWeeklyHours'])
        with self.assertRaises(ValueError): compare_builds(records,{'readiness':{}})

    def test_progression_review_links_only_related_sport_and_focus(self):
        from plan_workflow import progression_summary
        state=fixture('sample')
        for i in (0,2,4): state['sessions'][i]['progressionFocus']='Sustained effort'
        state['sessions'][2]['sport']='Run'
        state['sessions'][4]['progressionNote']='Longer continuous rep'
        bike,run=progression_summary(state)
        self.assertEqual([x['daysSincePrevious'] for x in bike['exposures']],[None,4])
        self.assertEqual(bike['exposures'][-1]['note'],'Longer continuous rep')
        self.assertIsNone(run['exposures'][0]['daysSincePrevious'])
