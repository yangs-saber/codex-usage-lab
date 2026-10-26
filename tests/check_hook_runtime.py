"""Optional native-runtime integration check, using a local fake model (no paid API).

Run with CODEX_TEST_BINARY=/path/to/codex python3 tests/check_hook_runtime.py.
Hook trust bypass applies ONLY to this isolated temporary test home. Normal plugin
installation never bypasses trust or edits trust records.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1] / 'plugins/codex-usage-lab'
sys.path.insert(0, str(ROOT))
from configure_auto_usage import configure


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', 0)))
        message = {'id': 'msg_fixture', 'type': 'message', 'role': 'assistant',
                   'status': 'completed', 'content': [{'type': 'output_text', 'text': 'OK', 'annotations': []}]}
        response = {'id': 'resp_fixture', 'object': 'response', 'status': 'completed',
                    'model': 'gpt-6.1-sol', 'output': [message], 'usage': {
                        'input_tokens': 1000, 'input_tokens_details': {'cached_tokens': 400},
                        'output_tokens': 10, 'output_tokens_details': {'reasoning_tokens': 0}, 'total_tokens': 1010}}
        events = [('response.created', {'response': {**response, 'status': 'in_progress', 'output': []}}),
                  ('response.output_item.added', {'output_index': 0, 'item': {**message, 'status': 'in_progress', 'content': []}}),
                  ('response.output_text.delta', {'item_id': message['id'], 'output_index': 0, 'content_index': 0, 'delta': 'OK'}),
                  ('response.output_item.done', {'output_index': 0, 'item': message}),
                  ('response.completed', {'response': response})]
        body = ''.join('event: '+name+'\ndata: '+json.dumps({'type': name, 'sequence_number': i, **data})+'\n\n'
                       for i, (name, data) in enumerate(events)).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    binary = os.environ.get('CODEX_TEST_BINARY') or shutil.which('codex')
    if not binary:
        raise SystemExit('Set CODEX_TEST_BINARY to a compatible Codex executable')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix='usage-hook-fixture-') as folder:
            home = Path(folder)
            env = {**os.environ, 'CODEX_HOME': str(home)}
            (home/'config.toml').write_text(
                'model = "gpt-6.1-sol"\nmodel_provider = "fixture"\n[features]\nplugins = false\n'
                '[model_providers.fixture]\nname = "Local fixture"\n'
                f'base_url = "http://127.0.0.1:{server.server_port}/v1"\n'
                'wire_api = "responses"\nrequires_openai_auth = false\n')
            configure(home, True, ROOT)
            # Capture the real hook's stdin/stdout for assertions; do not change
            # its implementation or fabricate a usage record outside the runtime.
            proof = home/'proof.json'
            wrapper = home/'capture.py'
            wrapper.write_text(
                'import sys,json,subprocess\nfrom pathlib import Path\n'
                'event=sys.stdin.read()\n'
                f'p=subprocess.run([sys.executable,{str(ROOT/"hooks/stop.py")!r}],input=event,text=True,capture_output=True)\n'
                f'Path({str(proof)!r}).write_text(json.dumps({{"input":json.loads(event),"output":p.stdout,"exit":p.returncode}}))\n'
                'print(p.stdout)\n')
            config = json.loads((home/'hooks.json').read_text())
            config['hooks']['Stop'][0]['hooks'][0]['command'] = 'python3 '+shlex.quote(str(wrapper))
            (home/'hooks.json').write_text(json.dumps(config))
            result = subprocess.run([binary, 'exec', '--skip-git-repo-check', '--dangerously-bypass-hook-trust',
                                     '-C', str(home), 'Reply OK. Do not call tools.'],
                                    env=env, stdin=subprocess.DEVNULL, text=True, capture_output=True, timeout=40)
            if result.returncode or not proof.exists():
                raise AssertionError(result.stderr[-4000:])
            captured = json.loads(proof.read_text())
            output = json.loads(captured['output'])
            assert captured['input']['hook_event_name'] == 'Stop'
            assert captured['exit'] == 0
            assert '1,010 Token' in output['systemMessage'], output
            assert '缓存 40%' in output['systemMessage'], output
            assert '估算 0.034 Credits' in output['systemMessage'], output
            assert set(output) == {'systemMessage'}, output
            print('PASS: native Stop event, exact turn, final response tokens, cache, estimated Credits; no continuation')
            print(output['systemMessage'])
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
