#!/usr/bin/env python3
"""Run the loopback-only dashboard. Demo never scans local logs."""
import argparse,os,sys
from pathlib import Path

parser=argparse.ArgumentParser(description='Codex Usage Lab local dashboard')
parser.add_argument('--demo',action='store_true',help='Use synthetic data; do not scan Codex logs')
parser.add_argument('--port',type=int,default=8770)
args=parser.parse_args()
if not 1024<=args.port<=65535:parser.error('port must be 1024–65535')
os.environ['USAGE_LAB_PORT']=str(args.port)
if args.demo:os.environ['USAGE_LAB_DEMO']='1'
plugin=Path(__file__).resolve().parent/'plugins/codex-usage-lab'
print(f'Codex Usage Lab: http://127.0.0.1:{args.port}/'+('?demo=1' if args.demo else ''),flush=True)
os.execv(sys.executable,[sys.executable,str(plugin/'service.py')])
