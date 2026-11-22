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
