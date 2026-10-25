import json, os, secrets, threading, time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import collector
from analytics import query
ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('USAGE_LAB_DATA') or os.environ.get('PLUGIN_DATA') or str(Path.home()/'.local/share/codex-usage-lab'))
PORT=int(os.environ.get('USAGE_LAB_PORT','8770'))
STATE={'loading':True};LOCK=threading.RLock();CSRF=secrets.token_urlsafe(32)
DEMO=os.environ.get('USAGE_LAB_DEMO')=='1'

def notes():
    try:return json.loads((DATA/'annotations.json').read_text())
    except FileNotFoundError:return {}

def annotate(a):
    if DEMO:raise ValueError('Demo mode is read-only')
    for k in ('thread_id','turn_id','task','outcome'):
        if not isinstance(a.get(k),str) or len(a[k])>160:raise ValueError('Invalid '+k)
    if a['outcome'] not in ('unrated','success','partial','failed'):raise ValueError('Invalid outcome')
    with LOCK:
        if not any(r['thread']==a['thread_id'] and r['turn']==a['turn_id'] for r in STATE.get('records',[])):raise ValueError('Unknown turn')
        n=notes();key=a['thread_id']+':'+a['turn_id']
        n[key]={'task':a['task'].strip(),'outcome':a['outcome']}
        if not n[key]['task'] and n[key]['outcome']=='unrated':n.pop(key,None)
        DATA.mkdir(parents=True,exist_ok=True);p=DATA/'annotations.tmp';p.write_text(json.dumps(n,ensure_ascii=False));p.replace(DATA/'annotations.json')
        return {'saved':True,'key':key}

def refresh():
    global STATE
    while True:
        try:
            snap=collector.snapshot()
            with LOCK:STATE=snap
        except Exception as e:
            with LOCK:STATE={**STATE,'error':str(e)}
        time.sleep(10)

class Handler(BaseHTTPRequestHandler):
    def valid_host(self):return self.headers.get('Host') in (f'127.0.0.1:{PORT}',f'localhost:{PORT}')
    def send(self,obj,status=200,kind='application/json; charset=utf-8'):
        body=obj if isinstance(obj,bytes) else json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if not self.valid_host():self.send_error(403);return
        path=urlparse(self.path).path
        if path=='/health':self.send({'app':'codex-usage-lab','version':'0.5.0','loading':STATE.get('loading',True)})
        elif path=='/api/usage':
            with LOCK:self.send({**STATE,'annotations':notes(),'csrf':CSRF})
        elif path=='/':self.send((ROOT/'index.html').read_bytes(),kind='text/html; charset=utf-8')
        elif path in ('/dashboard.css','/dashboard.js','/demo.json'):
            kind={'/dashboard.css':'text/css; charset=utf-8','/dashboard.js':'text/javascript; charset=utf-8','/demo.json':'application/json; charset=utf-8'}[path]
            self.send((ROOT/path[1:]).read_bytes(),kind=kind)
        else:self.send_error(404)
    def do_POST(self):
        if not self.valid_host():self.send_error(403);return
        origin=self.headers.get('Origin')
        if origin and origin!='http://'+self.headers.get('Host',''):self.send_error(403);return
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':self.send_error(415);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<16384:raise ValueError('Invalid request size')
            a=json.loads(self.rfile.read(length))
            if not isinstance(a,dict):raise ValueError('Expected object')
            if self.path=='/api/annotate':
                if self.headers.get('X-CSRF-Token')!=CSRF:self.send_error(403);return
                self.send(annotate(a))
            elif self.path=='/api/query':
                from plugin_api import validate_query
                validate_query(a)
                with LOCK:
                    if STATE.get('loading'):self.send({'loading':True});return
                    self.send(query({**STATE,'annotations':notes()},a))
            else:self.send_error(404)
        except (ValueError,KeyError) as e:self.send({'error':str(e)},400)
    def log_message(self,*args):pass

if __name__=='__main__':
    http=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    if DEMO:STATE=json.loads((ROOT/'demo.json').read_text())
    else:threading.Thread(target=refresh,daemon=True).start()
    http.serve_forever()
