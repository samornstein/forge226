"""Run the tracker on loopback. No athlete information is sent to the hosted plan."""
import argparse
import hmac
import json
import secrets
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from server import App
from tracker import read_snapshot, action

PORT=48226

def serve(app,aid,port=PORT,open_browser=True):
    app.store.athlete(aid)
    token=secrets.token_urlsafe(32)
    lock=threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,status,value,content_type='application/json'):
            data=json.dumps(value,allow_nan=False).encode() if content_type=='application/json' else value
            self.send_response(status)
            for k,v in {'Content-Type':content_type,'Content-Length':str(len(data)),'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY'}.items(): self.send_header(k,v)
            self.end_headers(); self.wfile.write(data)
        def valid_host(self):
            return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
        def authorized(self):
            return self.valid_host() and hmac.compare_digest(self.headers.get('X-Tracker-Token',''),token)
        def do_GET(self):
            if not self.valid_host(): return self.reply(403,{'error':'Open the local tracker address.'})
            u=urlsplit(self.path)
            if u.path=='/':
                html=Path(__file__).with_name('tracker.html').read_text().replace('__TRACKER_TOKEN__',json.dumps(token))
                return self.reply(200,html.encode(),'text/html; charset=utf-8')
            if u.path=='/plan':
                try:
                    from calendar_view import share_html
                    result=share_html(app.store.plan(aid)['state'])
                    return self.reply(200,result.encode(),'text/html; charset=utf-8')
                except (ValueError,KeyError,OSError): return self.reply(400,{'error':'Plan export unavailable.'})
            if not self.authorized(): return self.reply(403,{'error':'Reload the tracker.'})
            if u.path!='/api/tracking': return self.reply(404,{'error':'Unknown page.'})
            try: self.reply(200,read_snapshot(app,aid,parse_qs(u.query).get('week',[None])[0]))
            except (ValueError,KeyError) as exc: self.reply(400,{'error':str(exc)})
        def do_POST(self):
            if not self.authorized() or self.headers.get('Origin')!=f'http://127.0.0.1:{self.server.server_port}':
                return self.reply(403,{'error':'Use the local tracker.'})
            try:
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=32*1024*1024: raise ValueError('Invalid upload size (maximum 32 MB).')
                body=self.rfile.read(size)
                with lock:
                    if self.path=='/api/fit':
                        from tracker_import import import_fit
                        with tempfile.NamedTemporaryFile(suffix='.fit') as f:
                            f.write(body); f.flush()
                            result=import_fit(app.store,aid,f.name)
                    elif self.path=='/api/action': result=action(app,aid,json.loads(body))
                    else: return self.reply(404,{'error':'Unknown action.'})
                self.reply(200,result)
            except (ValueError,KeyError,OSError,RuntimeError,TypeError) as exc: self.reply(400,{'error':str(exc)})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    address=f'http://127.0.0.1:{server.server_port}/'
    print(address,flush=True)
    if open_browser: webbrowser.open(address)
    server.serve_forever()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--athlete'); parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--port',type=int,default=PORT)
    args=parser.parse_args(); app=App(); people=app.store.athletes()
    if not args.athlete and len(people)!=1: parser.error('Specify --athlete for the intended athlete.')
    serve(app,args.athlete or people[0]['id'],args.port,not args.no_browser)
