#!/usr/bin/env python3
"""Read-only local Codex usage dashboard. No credentials or conversation text exported."""
import json, os, sqlite3, threading, time, subprocess, shutil
from contextlib import contextmanager
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parent
CODEX=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
PORT=int(os.environ.get('TOKEN_METER_PORT','8769'))
RATES={'gpt-6-astra':[250,25,1250],'gpt-6.1-sol':[50,2.5,250],'gpt-6-sol':[50,5,250],'gpt-6-luna':[2.5,.25,12.5],'gpt-5.6-sol':[100,10,500],'gpt-5.6-terra':[50,5,300],'gpt-5.6-luna':[5,.5,30]}
CACHE={}; LOCK=threading.Lock(); SNAP={'loading':True}; TZ=ZoneInfo('Asia/Shanghai')

def cost(u,model):
    r=RATES.get(model)
    if r is None:return None
    return (max(0,u.get('input_tokens',0)-u.get('cached_input_tokens',0))*r[0]+u.get('cached_input_tokens',0)*r[1]+u.get('output_tokens',0)*r[2])/1e6

@contextmanager
def log_stream(path):
    if path.suffix != '.zst':
        with path.open('rb') as f: yield f
    else:
        binary=shutil.which('zstd') or '/opt/homebrew/bin/zstd'
        proc=subprocess.Popen([binary,'-dc',str(path)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        try: yield proc.stdout
        finally:
            proc.stdout.close()
            if proc.wait()!=0: raise OSError('无法解压日志 '+path.name)

def parse(path):
    st=path.stat(); sig=(st.st_size,st.st_mtime_ns)
    if str(path) in CACHE and CACHE[str(path)][0]==sig:return CACHE[str(path)][1]
    result={'records':[],'total':None,'id':None,'cwd':'','timestamp':'','turns':{}}; model=None; tier=None; effort=None; turn=None
    with log_stream(path) as f:
        for line in f:
            if not any(s in line for s in (b'"session_meta"',b'"turn_context"',b'"token_usage_record"',b'"token_count"',b'"thread_settings_applied"',b'"task_started"',b'"task_complete"')):continue
            try:d=json.loads(line)
            except (ValueError,UnicodeDecodeError):continue
            p=d.get('payload',{}); typ=d.get('type')
            if typ=='session_meta':result.update(id=p.get('id'),cwd=p.get('cwd',''))
            elif typ=='turn_context':
                model=p.get('model') or model
                if 'service_tier' in p:tier=p['service_tier']
                effort=p.get('effort',effort);turn=p.get('turn_id',turn)
            elif typ=='event_msg' and p.get('type')=='thread_settings_applied':
                settings=p.get('thread_settings',{})
                model=settings.get('model',model);tier=settings.get('service_tier',tier)
                effort=settings.get('reasoning_effort',effort)
            elif typ=='event_msg' and p.get('type') in ('task_started','task_complete'):
                turn=p.get('turn_id',turn)
                if turn:result['turns'].setdefault(turn,{})['start' if p['type']=='task_started' else 'end']=d.get('timestamp')
            elif typ=='token_usage_record':
                u=p.get('usage');rid=p.get('response_id')
                if not u or not rid:continue
                result['records'].append({'key':rid,'thread':p.get('thread_id') or result['id'],'turn':p.get('turn_id') or 'unknown','timestamp':d.get('timestamp',''),'model':model,'tier':tier,'effort':effort,'usage':u})
            elif typ=='event_msg' and p.get('type')=='token_count' and p.get('info'):
                result['total']=p['info'].get('total_token_usage');result['timestamp']=d.get('timestamp','')
    CACHE[str(path)]=(sig,result);return result

def snapshot():
    dbs=sorted(CODEX.glob('state_*.sqlite'),key=lambda x:x.stat().st_mtime,reverse=True)
    if not dbs:raise RuntimeError('没有找到 Codex 本地数据库')
    with sqlite3.connect('file:'+str(dbs[0])+'?mode=ro',uri=True) as conn:
        conn.row_factory=sqlite3.Row
        threads={r['id']:dict(r) for r in conn.execute('SELECT id,title,cwd,project_id,rollout_path FROM threads')}
        projects={r['id']:r['name'] for r in conn.execute('SELECT id,name FROM projects')}
    # Desktop still stores project membership separately on this installation.
    try:
        state=json.loads((CODEX/'.codex-global-state.json').read_text())
        for pid,project in state.get('local-projects',{}).items():projects[pid]=project.get('name',pid)
        for tid,assignment in state.get('thread-project-assignments',{}).items():
            if tid in threads and not threads[tid].get('project_id') and isinstance(assignment,dict):
                threads[tid]['project_id']=assignment.get('projectId')
        aliases={p['chatGptBacking']['projectId']:pid for pid,p in state.get('local-projects',{}).items() if p.get('chatGptBacking',{}).get('projectId')}
        for thread in threads.values():thread['project_id']=aliases.get(thread.get('project_id'),thread.get('project_id'))
    except (OSError,ValueError):pass
    try:
        for line in (CODEX/'session_index.jsonl').open():
            try: item=json.loads(line)
            except ValueError:continue
            if item.get('id') in threads and item.get('thread_name'):
                threads[item['id']]['title']=item['thread_name']
    except OSError:pass
    paths=set()
    for folder in ('sessions','archived_sessions'):
        paths.update((CODEX/folder).rglob('*.jsonl'))
        paths.update((CODEX/folder).rglob('*.jsonl.zst'))
    for t in threads.values():
        if t['rollout_path']:
            p=Path(t['rollout_path'])
            paths.add(Path(str(p)+'.zst') if not p.exists() and Path(str(p)+'.zst').exists() else p)
    records={}; legacy={}; errors=0; turns={}
    for path in sorted(paths):
        try:p=parse(path)
        except (OSError,ValueError):errors+=1;continue
        tid=p['id']
        for turn,meta in p['turns'].items():turns.setdefault(str(tid)+':'+turn,{}).update(meta)
        if tid and tid not in threads:threads[tid]={'id':tid,'title':'未索引对话 '+tid[:8],'cwd':p['cwd'],'project_id':None}
        for r in p['records']:records.setdefault(r['key'],r)
        if tid and p['total']:
            old=legacy.get(tid)
            if old is None or p['timestamp']>old['timestamp']:legacy[tid]={'usage':p['total'],'timestamp':p['timestamp']}
    out=[]
    for r in records.values():
        t=threads.get(r['thread'],{}); pid=t.get('project_id');u=r['usage'];c=cost(u,r['model'])
        # Missing service tier is explicitly a Standard-price scenario, not a bill.
        factor={'default':1,'standard':1,None:1,'priority':2,'fast':2,'ultrafast':6}.get(r['tier'])
        if factor is None:c=None
        if r['tier']=='ultrafast' and r['model'] not in ('gpt-6-astra','gpt-6.1-sol'):c=None
        out.append({'id':r['key'],'thread':r['thread'],'turn':r['turn'],'time':r['timestamp'],'date':datetime.fromisoformat(r['timestamp'].replace('Z','+00:00')).astimezone(TZ).strftime('%Y-%m-%d') if r['timestamp'] else '', 'effort':r.get('effort') or '未记录','tierKnown':r['tier'] is not None,'model':r['model'] or '未记录模型','tier':r['tier'] or '未记录速度（按 Standard 折算）','title':t.get('title','未索引对话'),'project':projects.get(pid,pid) if pid else '未归属项目','projectId':pid or '__none__','input':u.get('input_tokens',0),'cached':u.get('cached_input_tokens',0),'output':u.get('output_tokens',0),'reasoning':u.get('reasoning_output_tokens',0),'total':u.get('input_tokens',0)+u.get('output_tokens',0),'credits':c*factor if c is not None else None})
    covered={r['thread'] for r in out}; gaps=[]
    for tid,p in legacy.items():
        # Cumulative totals may include inherited history: report separately, never add them to billable records.
        total=p['usage'].get('total_tokens',0); recorded=sum(r['total'] for r in out if r['thread']==tid)
        if tid not in covered or total>recorded:
            gaps.append({'title':threads.get(tid,{}).get('title',tid),'recorded':recorded,'cumulative':total})
    return {'loading':False,'updated':datetime.now(TZ).isoformat(),'today':datetime.now(TZ).strftime('%Y-%m-%d'),'records':out,'turnTimes':turns,'coverage':{'files':len(paths),'threads':len(threads),'coveredThreads':len(covered),'gaps':gaps,'errors':errors},'rates':RATES,'source':'https://learn.chatgpt.com/docs/pricing','rateDate':'2026-10-23'}
