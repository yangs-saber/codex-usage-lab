#!/usr/bin/env python3
"""Read-only skill fallback; starts the local service on demand."""
import argparse,json,os
from plugin_api import build_application
parser=argparse.ArgumentParser(description='Read Codex usage from local logs')
parser.add_argument('--thread-id',default=os.environ.get('CODEX_THREAD_ID'))
parser.add_argument('--group-by',choices=['thread','turn','model','project'],default='turn')
parser.add_argument('--limit',type=int,default=20)
args=parser.parse_args()
if args.group_by in ('thread','turn') and not args.thread_id:parser.error('Provide --thread-id or CODEX_THREAD_ID; no recent-chat guessing')
query={'group_by':args.group_by,'limit':max(1,min(100,args.limit))}
if args.thread_id:query['thread_id']=args.thread_id
print(json.dumps(build_application().dispatch('query_usage',query),ensure_ascii=False,indent=2))
