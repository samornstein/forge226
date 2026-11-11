"""Process-level checks for a chat that lacks registered plugin tools."""
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'server'))
from test_integration import fixture

# Dependency injection is in this test harness only, never a runtime fake mode.
HARNESS = '''
import sys,runpy
sys.path.insert(0,sys.argv[1]+'/server')
sys.path.insert(0,sys.argv[1]+'/tests')
import server
from test_integration import FakeStrava
from test_garmin import FakeGarmin
factory=server.App
server.App=lambda:factory(http=FakeStrava(),garmin_http=FakeGarmin())
runpy.run_path(sys.argv[1]+'/bin/chat-session.py',run_name='__main__')
'''


class ChatSession(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ident = 0
        self.start()
    def start(self):
        self.process = subprocess.Popen([sys.executable, '-u', '-c', HARNESS, str(ROOT)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True,
                                        env={**os.environ, 'FORGE226_DATA_DIR': self.tmp.name})
    def stop(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            self.process.wait(timeout=10)
        self.process.stdout.close()
        self.process.stderr.close()
    def tearDown(self):
        self.stop()
        self.tmp.cleanup()
    def rpc(self, method, params):
        self.ident += 1
        message = {'jsonrpc':'2.0','id':self.ident,'method':method,'params':params}
        self.process.stdin.write(json.dumps(message)+'\n')
        self.process.stdin.flush()
        ready, _, _ = select.select([self.process.stdout], [], [], 15)
        self.assertTrue(ready, 'Engine failed to respond')
        line = self.process.stdout.readline()
        self.assertTrue(line, 'Engine exited without a response')
        response = json.loads(line)
        self.assertEqual(response['id'],self.ident)
        return response['result']
    def call(self, operation, **arguments):
        result = self.rpc('tools/call', {'name':'forge226_'+operation,'arguments':arguments})
        self.assertFalse(result['isError'],result['content'])
        return result['structuredContent']
    def athlete(self):
        return self.call('create_athlete',name='Synthetic same-chat athlete',timezone='America/Los_Angeles')['id']
    def test_tool_discovery_plan_and_resume_in_one_process(self):
        self.rpc('initialize', {'protocolVersion':'2025-06-18'})
        tools=self.rpc('tools/list', {})['tools']
        self.assertTrue({'forge226_history_summary','forge226_garmin_sync_all'}.issubset({t['name'] for t in tools}))
        aid=self.athlete()
        self.call('save_profile',athlete_id=aid,profile={'goal':'synthetic first event'},expected_revision=1)
        draft=self.call('save_plan_draft',athlete_id=aid,state=fixture(aid),parent_version=None)
        self.assertTrue(draft['validation']['passed'])
        self.call('activate_plan',athlete_id=aid,version=draft['version'],expected_active=None)
        output=self.call('export_dashboard',athlete_id=aid)
        self.assertTrue(Path(output['html']).exists())
        self.stop();self.start()
        self.assertEqual(self.call('get_context',athlete_id=aid)['activeVersion'],draft['version'])
        self.assertEqual(self.call('get_profile',athlete_id=aid)['profile']['goal'],'synthetic first event')
    def test_garmin_setup_stays_alive_between_calls(self):
        aid=self.athlete()
        link=self.call('garmin_connect',athlete_id=aid)['setupUrl']
        # This status request must not terminate the earlier private setup page.
        self.assertFalse(self.call('garmin_status',athlete_id=aid)['connected'])
        with urllib.request.urlopen(link,timeout=5) as response:
            page=response.read().decode()
        csrf=re.search(r'name="csrf" value="([^"]+)"',page).group(1)
        origin=urllib.parse.urlunsplit((*urllib.parse.urlsplit(link)[:2],'','',''))
        payload=urllib.parse.urlencode({'csrf':csrf,'api_key':'synthetic-private-key','region':'global'}).encode()
        request=urllib.request.Request(link,data=payload,headers={'Origin':origin},method='POST')
        with urllib.request.urlopen(request,timeout=5) as response:
            self.assertEqual(response.status,200)
        self.assertTrue(self.call('garmin_status',athlete_id=aid)['connected'])
        self.call('garmin_sync',athlete_id=aid,days=183)
        self.assertEqual(self.call('list_activities',athlete_id=aid)['total'],1)
        self.assertNotIn('synthetic-private-key',json.dumps(self.call('get_context',athlete_id=aid)))
    def test_strava_setup_callback_and_sync_in_same_process(self):
        aid=self.athlete()
        link=self.call('strava_connect',athlete_id=aid)['setupUrl']
        self.call('status')
        with urllib.request.urlopen(link,timeout=5) as response:
            page=response.read().decode()
        csrf=re.search(r'name="csrf" value="([^"]+)"',page).group(1)
        origin=urllib.parse.urlunsplit((*urllib.parse.urlsplit(link)[:2],'','',''))
        payload=urllib.parse.urlencode({'csrf':csrf,'client_id':'123','client_secret':'synthetic-secret'}).encode()
        class NoFollow(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        request=urllib.request.Request(link,data=payload,headers={'Origin':origin},method='POST')
        with self.assertRaises(urllib.error.HTTPError) as result:
            urllib.request.build_opener(NoFollow()).open(request,timeout=5)
        self.assertEqual(result.exception.code,303)
        target=result.exception.headers['Location']
        state=urllib.parse.parse_qs(urllib.parse.urlsplit(target).query)['state'][0]
        callback=origin+'/callback?'+urllib.parse.urlencode({'state':state,'code':'synthetic-code','scope':'activity:read_all'})
        with urllib.request.urlopen(callback,timeout=5) as response:self.assertEqual(response.status,200)
        self.assertTrue(self.call('strava_status',athlete_id=aid)['connected'])
        self.call('strava_sync',athlete_id=aid,days=183)
        self.assertEqual(self.call('list_activities',athlete_id=aid)['total'],1)
        self.assertNotIn('synthetic-secret',json.dumps(self.call('get_context',athlete_id=aid)))
    def test_cannot_start_second_writer(self):
        self.call('status')  # first server owns the store lock
        request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'forge226_status','arguments':{}}}
        result=subprocess.run([sys.executable,str(ROOT/'bin/chat-session.py')],input=json.dumps(request)+'\n',text=True,capture_output=True,env={**os.environ,'FORGE226_DATA_DIR':self.tmp.name},timeout=10)
        self.assertEqual(result.returncode,1)
        self.assertEqual(result.stdout,'')
        self.assertIn('already running',result.stderr)
        self.assertEqual(self.call('status')['athletes'],0)
    def test_invalid_request_does_not_stop_session(self):
        result=self.rpc('tools/call',{'name':'forge226_not_a_tool','arguments':{}})
        self.assertTrue(result['isError'])
        self.assertEqual(self.call('status')['athletes'],0)

if __name__ == '__main__':unittest.main()
