import json, os, subprocess, sys, time, urllib.request
from pathlib import Path
from dataclasses import dataclass
__version__='0.6.0'
ROOT=Path(__file__).resolve().parent
PORT=int(os.environ.get('USAGE_LAB_PORT','8770'));URL=f'http://127.0.0.1:{PORT}'
@dataclass
class Tool:
    name:str
    description:str
    input_schema:dict
QUERY={'type':'object','properties':{'group_by':{'type':'string','enum':['thread','turn','call','model','project','comparison']},'thread_id':{'type':'string'},'model':{'type':'string'},'project_id':{'type':'string'},'task':{'type':'string'},'search':{'type':'string'},'since':{'type':'string','description':'YYYY-MM-DD Asia/Shanghai'},'until':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':100},'offset':{'type':'integer','minimum':0}},'additionalProperties':False}
ANNOTATE={'type':'object','properties':{'thread_id':{'type':'string'},'turn_id':{'type':'string'},'task':{'type':'string','description':'User-chosen task label; no automatic inference'},'outcome':{'type':'string','enum':['unrated','success','partial','failed']}},'required':['thread_id','turn_id','task','outcome'],'additionalProperties':False}
TOOL_SPECS=[Tool('open_usage_dashboard','Request an optional usage dashboard. Native MCP App rendering depends on host support; otherwise return the local page URL. Optional thread_id binds a known conversation; no ID shows a selector. Automatic refresh needs no model prompts.',{'type':'object','properties':{'thread_id':{'type':'string'}},'additionalProperties':False}),Tool('query_usage','Read bounded local usage totals by thread, turn, call, model, project, or task/model comparison. Credits are estimates, not bills. Missing logs and unpriced calls are explicit.',QUERY),Tool('annotate_usage_turn','Save the user’s task label and outcome for a specific turn. Only use when the user requests or supplies this annotation.',ANNOTATE)]

def validate_schema(schema,a):
    if not isinstance(a,dict):raise ValueError('Expected object')
    props=schema['properties']
    if set(a)-set(props):raise ValueError('Unknown arguments')
    if set(schema.get('required',[]))-set(a):raise ValueError('Missing arguments')
    for k,v in a.items():
        p=props[k]
        if p['type']=='string' and (not isinstance(v,str) or len(v)>160):raise ValueError('Invalid '+k)
        if p['type']=='integer' and (type(v)!=int or v<p.get('minimum',0) or v>p.get('maximum',1000000)):raise ValueError('Invalid '+k)
        if 'enum' in p and v not in p['enum']:raise ValueError('Invalid '+k)

def validate_query(a):
    validate_schema(QUERY,a)
    from datetime import date
    for key in ('since','until'):
        if key in a:date.fromisoformat(a[key])
    if a.get('since','')>a.get('until','9999-12-31'):raise ValueError('since must not exceed until')

def validate_input(name,a):
    spec=next((t for t in TOOL_SPECS if t.name==name),None)
    if spec is None:raise ValueError('Unknown tool')
    validate_schema(spec.input_schema,a)
    if name=='query_usage':validate_query(a)

def http(path,a=None,headers=None):
    req=urllib.request.Request(URL+path,data=json.dumps(a).encode() if a is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
    with urllib.request.urlopen(req,timeout=15) as r:return json.load(r)

def ensure_service():
    try:
        health=http('/health')
        if health.get('app')!='codex-usage-lab':raise RuntimeError('Port is occupied by another service')
        return
    except (OSError,ValueError):pass
    from service import DATA
    DATA.mkdir(parents=True,exist_ok=True)
    with (DATA/'service.log').open('ab') as log:
        subprocess.Popen([sys.executable,str(ROOT/'service.py')],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    for _ in range(20):
        time.sleep(.1)
        try:
            if http('/health').get('app')=='codex-usage-lab':return
        except OSError:pass
    raise RuntimeError('Local dashboard could not start')

class KernelApplication:
    def dispatch(self,name,a):
        ensure_service()
        if name=='open_usage_dashboard':
            result=http('/api/query',{'group_by':'thread','limit':100})
            thread_id=a.get('thread_id') or os.environ.get('CODEX_THREAD_ID')
            return {'url':URL,'thread_id':thread_id,'threads':result.get('rows',[]),'loading':result.get('loading',False),'note':'Renders the MCP App meter. Binds the launching Codex chat when CODEX_THREAD_ID is available; otherwise select a target conversation. Never infer it from recent activity.'}
        if name=='query_usage':return http('/api/query',a)
        if name=='annotate_usage_turn':
            csrf=http('/api/usage')['csrf'];return http('/api/annotate',a,{'X-CSRF-Token':csrf})
        raise ValueError('Unknown tool')

def build_application():return KernelApplication()

if __name__=='__main__':
    ensure_service();print(URL)
