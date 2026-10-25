"""Deterministic rollups. Measurements are not a judgement of model quality."""
from collections import defaultdict
from statistics import median

def summarize(rows):
    known=[r for r in rows if r['credits'] is not None]
    return {'calls':len(rows),'tokens':sum(r['total'] for r in rows),'input':sum(r['input'] for r in rows),'cached':sum(r['cached'] for r in rows),'output':sum(r['output'] for r in rows),'credits':sum(r['credits'] for r in known) if known else None,'unpricedCalls':len(rows)-len(known),'assumedSpeedCalls':sum(not r.get('tierKnown') for r in rows)}

def query(data,args):
    rows=data.get('records',[]);notes=data.get('annotations',{})
    for field,key in [('thread_id','thread'),('model','model'),('project_id','projectId')]:
        if args.get(field):rows=[r for r in rows if r[key]==args[field]]
    if args.get('since'):rows=[r for r in rows if r['date']>=args['since']]
    if args.get('until'):rows=[r for r in rows if r['date']<=args['until']]
    if args.get('task'):rows=[r for r in rows if notes.get(r['thread']+':'+r['turn'],{}).get('task')==args['task']]
    if args.get('search'):rows=[r for r in rows if args['search'].casefold() in r['title'].casefold()]
    mode=args.get('group_by','thread');groups=defaultdict(list)
    for r in rows:
        if mode=='call':key=r['id']
        elif mode=='turn':key=r['thread']+':'+r['turn']
        elif mode=='comparison':key=(notes.get(r['thread']+':'+r['turn'],{}).get('task','未标注'),r['model'],r['effort'],r['tier'])
        else:key=r[{'thread':'thread','model':'model','project':'projectId'}[mode]]
        groups[key].append(r)
    result=[]
    for key,rs in groups.items():
        first=rs[0];s=summarize(rs);s.update(key=key,first=min(r['time'] for r in rs),last=max(r['time'] for r in rs),threads=len({r['thread'] for r in rs}),turns=len({(r['thread'],r['turn']) for r in rs}))
        if mode in ('turn','thread','call'):s.update(title=first['title'],thread_id=first['thread'],project=first['project'],models=sorted({r['model'] for r in rs}))
        if mode in ('turn','call'):
            k=first['thread']+':'+first['turn'];s.update(turn_id=first['turn'],annotation=notes.get(k,{}),timing=data.get('turnTimes',{}).get(k,{}))
        if mode=='call':s.update(model=first['model'],speed=first['tier'],effort=first['effort'],response_id=first['id'])
        if mode=='project':s['project']=first['project']
        if mode=='comparison':
            turns=defaultdict(list)
            for r in rs:turns[r['thread']+':'+r['turn']].append(r)
            # Only fully priced turns have a comparable credits mean/median.
            priced=[sum(r['credits'] for r in t) for t in turns.values() if all(r['credits'] is not None for r in t)]
            outcomes=[notes.get(k,{}).get('outcome','unrated') for k in turns]
            s.update(task=key[0],model=key[1],effort=key[2],speed=key[3],meanCredits=sum(priced)/len(priced) if priced else None,medianCredits=median(priced) if priced else None,pricedTurns=len(priced),ratedTurns=sum(o!='unrated' for o in outcomes),successfulTurns=outcomes.count('success'))
        result.append(s)
    result.sort(key=lambda x:x['last'],reverse=True)
    offset=args.get('offset',0);limit=args.get('limit',30)
    return {'updated':data.get('updated'),'unit':'tokens and estimated credits; NOT billed credits','coverage':{k:v for k,v in data.get('coverage',{}).items() if k!='gaps'},'summary':summarize(rows),'groupBy':mode,'totalRows':len(result),'rows':result[offset:offset+limit],'nextOffset':offset+limit if offset+limit<len(result) else None,'caveat':'Compare similar tasks and results. Mixed-model turns appear in multiple model groups; success is a turn rating, not causal model attribution.'}
