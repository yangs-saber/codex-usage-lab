#!/usr/bin/env python3
"""Register/unregister the usage hook on request; never grant hook trust."""
import argparse
import json
import os
from pathlib import Path
import shlex
import tempfile

MARKER = '# codex-usage-lab:auto-usage'


def configure(home, enabled, plugin_root=None):
    path = Path(home) / 'hooks.json'
    config = json.loads(path.read_text()) if path.exists() else {}
    hooks = config.setdefault('hooks', {})
    groups = []
    for group in hooks.get('Stop', []):
        remaining = [h for h in group['hooks'] if not h.get('command', '').endswith(MARKER)]
        if remaining:
            groups.append({**group, 'hooks': remaining})
    if enabled:
        root = Path(plugin_root or Path(__file__).resolve().parent)
        command = 'python3 ' + shlex.quote(str(root / 'hooks/stop.py')) + ' ' + MARKER
        groups.append({'hooks': [{'type': 'command', 'command': command,
                                 'timeout': 10, 'statusMessage': '统计本轮用量'}]})
    hooks['Stop'] = groups
    content = json.dumps(config, ensure_ascii=False, indent=2) + '\n'
    if path.exists() and path.read_text() == content:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as file:
        file.write(content)
        temporary = file.name
    os.replace(temporary, path)
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--disable', action='store_true')
    args = parser.parse_args()
    path = configure(os.environ.get('CODEX_HOME', Path.home() / '.codex'), not args.disable)
    print(json.dumps({'configured': not args.disable, 'path': str(path),
                      'trustGranted': False,
                      'next': 'Review and trust this hook in Codex; compatible CLI: /hooks' if not args.disable else 'Automatic usage hook removed'}, ensure_ascii=False))
