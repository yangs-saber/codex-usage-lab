import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'plugins/codex-usage-lab'
spec = importlib.util.spec_from_file_location('usage_stop', ROOT / 'hooks/stop.py')
stop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stop)
sys.path.insert(0, str(ROOT))
from configure_auto_usage import configure, MARKER


class StopHookTests(unittest.TestCase):
    def test_registration_preserves_other_hooks_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'hooks.json'
            other = {'type': 'command', 'command': 'echo existing'}
            path.write_text(json.dumps({'hooks': {'Stop': [{'hooks': [other]}], 'SessionStart': []}}))
            configure(folder, True, Path(folder) / 'space and apostrophe\'s')
            first = path.read_text()
            configure(folder, True, Path(folder) / 'space and apostrophe\'s')
            self.assertEqual(path.read_text(), first)
            self.assertIn(MARKER, first)
            configure(folder, False)
            result = json.loads(path.read_text())
            self.assertEqual(result['hooks']['Stop'], [{'hooks': [other]}])
            self.assertEqual(result['hooks']['SessionStart'], [])

    def test_bad_config_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'hooks.json'
            path.write_text('invalid')
            with self.assertRaises(ValueError):
                configure(folder, True)
            self.assertEqual(path.read_text(), 'invalid')

    def run_report(self, records, **overrides):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'rollout.jsonl'
            events = [{'type': 'session_meta', 'payload': {'id': 'chat'}},
                      {'type': 'turn_context', 'payload': {'model': 'gpt-6.1-sol', 'service_tier': 'default'}}]
            events.extend({'type': 'token_usage_record', 'payload': r} for r in records)
            path.write_text('\n'.join(json.dumps(e) for e in events))
            return stop.report({'hook_event_name': 'Stop', 'session_id': 'chat',
                                'turn_id': 'turn', 'transcript_path': str(path), **overrides})

    def row(self, **overrides):
        return {'response_id': 'r', 'turn_id': 'turn', 'usage': {
            'input_tokens': 1000000, 'cached_input_tokens': 400000,
            'output_tokens': 100000, 'reasoning_output_tokens': 50000}, **overrides}

    def test_exact_turn_and_dedup(self):
        report = self.run_report([self.row(), self.row(), self.row(response_id='other', turn_id='old')])
        self.assertIn('110.00 万 Token', report['systemMessage'])
        self.assertIn('56.000 Credits', report['systemMessage'])
        self.assertIn('缓存 40%', report['systemMessage'])
        self.assertEqual(set(report), {'systemMessage'})  # never continue/block a turn

    def test_unknown_price_is_not_free(self):
        with patch.object(stop, 'cost', return_value=None):
            self.assertIn('未完整计价', self.run_report([self.row()])['systemMessage'])

    def test_no_cross_thread_guessing(self):
        self.assertIn('不匹配', self.run_report([self.row()], session_id='other')['systemMessage'])
        self.assertIn('尚无', self.run_report([self.row()], turn_id='absent')['systemMessage'])
        self.assertIn('尚无', self.run_report([self.row(thread_id='other')])['systemMessage'])

    def test_invalid_count_not_accepted(self):
        self.assertIn('计数异常', self.run_report([self.row(usage={'input_tokens': 1, 'cached_input_tokens': 2})])['systemMessage'])

    def test_missing_and_wrong_event(self):
        self.assertEqual(stop.report({'hook_event_name': 'SessionStart'}), {})
        self.assertIn('未提供', stop.report({'hook_event_name': 'Stop'})['systemMessage'])

    def test_entrypoint_fails_open_with_valid_json(self):
        result = subprocess.run([sys.executable, str(ROOT / 'hooks/stop.py')], input='bad json',
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stderr, '')
        self.assertEqual(set(json.loads(result.stdout)), {'systemMessage'})

    def test_plugin_bundles_hook_in_both_manifests(self):
        for name in ('plugin.json', '.codex-plugin/plugin.json'):
            manifest = json.loads((ROOT / name).read_text())
            extension = manifest.get('extensions', {}).get('com.openai', manifest)
            self.assertEqual(extension['hooks'], './hooks/hooks.json')
        config = json.loads((ROOT / 'hooks/hooks.json').read_text())
        hook = config['hooks']['Stop'][0]['hooks'][0]
        self.assertIn('${PLUGIN_ROOT}', hook['command'])
        self.assertEqual(hook['timeout'], 10)


if __name__ == '__main__':
    unittest.main()
